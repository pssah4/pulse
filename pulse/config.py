"""Project config: .pulse/config.toml, with the DIA config as read fallback.

A project without either file has not activated Pulse (mode None). DIA
modes map onto Pulse: off stays off, git-only and github-sync mean on.
"""
from __future__ import annotations

import functools
import hashlib
import itertools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:            # Python < 3.11, e.g. the macOS system python
    tomllib = None

DEFAULTS = {"mode": None, "cap": 4, "base_branch": None, "repo": None,
            "agent": "claude", "agent_timeout": 60, "verify": None,
            "setup": None, "setup_timeout": 20, "protected": (),   # setup_timeout in minutes
            "ids_since": None,             # other keys of an older config are read past (#107), plan_approval too
            "spec_branch": "docs/{n}-{slug}",                # where specs are written, {type} too (#116)
            "spec_tests": None}                              # pattern -> {run, localhost}; pulse go needs it (#117)
# What runs a program, with [agents]: pulse go takes these as the base branch on origin has them, where a
# person merged them, never from a working tree a branch or an agent may have changed (IMP-03-08 FR-06).
# base_branch runs nothing but names the base the rest comes from: pulse go refuses a working tree that names
# another (M-1 of #113).
EXECUTABLE = ("setup", "setup_timeout", "verify", "protected", "base_branch", "spec_tests")
DIA_MODES = {"off": "off", "git-only": "on", "github-sync": "on"}
# How `pulse go` starts one headless agent per item, cwd = the item's worktree.
# Headless runs keep the user's permission rules and ask nobody: acceptEdits lets edits through,
# {allow} what the build runs (verify and git; a flag must follow the list, or it takes the prompt),
# and {gitdir} opens the shared git dir, which Codex's sandbox keeps read-only, so a worktree can
# commit. load() fills both, in any template.
# Both print JSON, so pulse go can read what each phase used (.git/pulse/usage.jsonl).
AGENTS = {"claude": "claude -p --allowedTools {allow} --output-format json --permission-mode acceptEdits {prompt}",
          "codex": "codex exec --json --sandbox workspace-write --add-dir {gitdir} {prompt}"}
# Where a VS Code extension keeps the agent it bundles, for people who have only the extension.
BUNDLED = {"claude": "anthropic.claude-code-*/resources/native-binary/claude",
           "codex": "openai.chatgpt-*/bin/*/codex"}


def _unescape(s: str) -> str:
    """A basic TOML string's escapes are JSON's, but for \\U########; keep the raw text then."""
    try:
        return json.loads(f'"{s}"')
    except ValueError:
        return s


def printable(text: str) -> str:
    """Text from a branch or a PR, fit for a terminal: every character that is not printable becomes "?"
    (audit L-1 of #69). Here, where every module that prints such text can reach it (#56)."""
    return "".join(c if c.isprintable() else "?" for c in text)


@functools.lru_cache(maxsize=None)          # each warning once, however often a command reads the config
def _warn(msg: str) -> None:
    print(f"pulse: {printable(msg)}", file=sys.stderr)     # a line of a checked-out branch's config (#56)


# A TOML array or inline table on one line, as JSON: basic strings stay, literal strings and bare keys become
# JSON strings, = becomes :, a comma before the closing bracket and a comment go.
_TOKEN = re.compile(r"""("(?:[^"\\]|\\.)*")|'([^']*)'|([A-Za-z_][\w-]*)(?=\s*=)|(=)|,(?=\s*[\]}])|#.*""")
_KEY = r"""(?:([\w-]+)|"((?:[^"\\]|\\.)*)"|'([^']*)')"""


def _json(m) -> str:
    basic, literal, key, eq = m.groups()
    return basic or (json.dumps(literal) if literal is not None else json.dumps(key) if key else ":" if eq else "")


def _value(text: str):
    """A value of the config: a string, an integer, a boolean, or an array or inline table on one line.
    ValueError when it is none of these."""
    m = re.fullmatch(r"""(?:"((?:[^"\\]|\\.)*)"|'([^']*)'|(-?\d+)|(true|false))\s*(?:#.*)?""", text)
    if m:
        s1, s2, n, b = m.groups()
        return _unescape(s1) if s1 is not None else s2 if s2 is not None else int(n) if n is not None else b == "true"
    if text[:1] not in ("[", "{"):
        raise ValueError(text)
    value = json.loads(_TOKEN.sub(_json, text))
    if not isinstance(value, (list, dict)):
        raise ValueError(text)
    return value


def _parse(text: str, path: Path = None, strict: bool = False) -> dict:
    """TOML where Python has tomllib (3.11+). Else, or when tomllib rejects the file, key = value pairs (bare or
    quoted keys; strings, integers, booleans, and arrays and inline tables on one line) plus [sections], enough
    for this config; with a path, a line of the top level, [agents], or [spec_tests] that this does not
    understand is skipped with a warning naming it. strict: any line it does not understand, a table or a key
    given twice, is a ValueError that names it instead (M-2 of #117)."""
    if tomllib:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            pass                           # the lines below name the line; the settings stay
    out: dict = {}
    cur, mine, tables = out, True, set()
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[([\w.]+)\]\s*(?:#.*)?$", line)
        if m:
            if strict and m.group(1) in tables:
                raise ValueError(f"{path}:{no}: table given twice: {printable(line)}")
            tables.add(m.group(1))
            cur, mine = out, m.group(1) in ("agents", "spec_tests")      # other sections have their own readers
            for part in m.group(1).split("."):
                cur = cur.setdefault(part, {})
            continue
        m = re.match(rf"^{_KEY}\s*=\s*(.+)$", line)
        try:
            k = m.group(1) or (_unescape(m.group(2)) if m.group(2) is not None else m.group(3))
            value = _value(m.group(4))
        except (AttributeError, ValueError):
            if strict:
                raise ValueError(f"{path}:{no}: not understood: {printable(line)}") from None
            if path and mine:
                _warn(f"{path}:{no}: not understood, skipped: {line}")
            continue
        if strict and k in cur:
            raise ValueError(f"{path}:{no}: key given twice: {printable(line)}")
        cur[k] = value
    return out


def find_root(start: Path | None = None) -> Path | None:
    """Nearest directory with a .git entry (a worktree's .git is a file)."""
    here = Path(start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / ".git").exists():
            return d
    return None


def base_ref(root: Path, base: str = None) -> str:
    """origin/<base> when it exists: what the gates judge and worktrees start from. Else the local branch."""
    base = base or load(root)["base_branch"] or default_branch(root)
    remote = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", f"origin/{base}"],
                            capture_output=True, text=True)
    return f"origin/{base}" if remote.returncode == 0 else base


def common_dir(root: Path) -> Path:
    """The git dir all worktrees share. A worktree whose git dir git cannot read has none: StateError,
    never the project itself (F7.12)."""
    if (root / ".git").is_dir():           # a main clone: no git process for load() on every hook event
        return (root / ".git").resolve()
    out = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"],
                         capture_output=True, text=True, timeout=2)
    if out.returncode or not out.stdout.strip():
        from pulse import state            # state reads the config through this module
        raise state.StateError(f"git finds no repository in {root}: {out.stderr.strip()}")
    p = Path(out.stdout.strip())
    return (p if p.is_absolute() else root / p).resolve()


def pulse_dir(root: Path) -> Path:
    """pulse/ in the shared git dir: what all worktrees of a clone share (caches, runs)."""
    return common_dir(root) / "pulse"


def evidence_dir(root: Path) -> Path:
    """What counts for pulse go in this clone, the gates' evidence, the kept verdicts, and the base check's note:
    in the user's cache, one folder per shared git dir. Custom cache locations must remain outside the
    agent's writable paths; this helper does not validate sandbox policy (FIX-02-06-11)."""
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "pulse" / hashlib.sha256(str(common_dir(root)).encode()).hexdigest()[:16]


def _cut(command) -> str:
    """A command up to its first option, path, or placeholder argument: what a rule of it allows."""
    # ponytail: a runner without subcommands keeps its plain arguments (pytest tests), and a command that
    # chains others (a && b) gets a rule for its start only; parse per runner when a project needs that
    words = str(command or "").split()
    if words[1:2] == ["-m"]:
        return " ".join(words[:3])                           # python3 -m pytest
    # uv run pytest -q; go test ./... -> go test; npx playwright test {files} -> npx playwright test
    return " ".join(words[:1] + list(itertools.takewhile(lambda w: not re.match(r"[-&|;]|.*[/.{]", w), words[1:])))


def _allow(verify, runs=()) -> str:
    """What a headless Claude runs unasked: verify and each runner of [spec_tests] (#119) cut by _cut, and git.
    _allow(verify) starts _allow(verify, runs), so a template's allow list widens in place."""
    cmds = [c for c in [_cut(verify)] if c] + [f"git {g}" for g in ("add", "commit", "status", "diff", "log")]
    cmds += [c for c in map(_cut, runs) if c and not _loose(c)]      # the tests gate still runs the others
    return " ".join(shlex.quote(f"Bash({c}:*)") for c in dict.fromkeys(cmds))


# A rule that ends at a shell or an interpreter runs whatever code follows it, env any program: gh too (M2 of #119).
INTERPRETER = re.compile(r"(ba|da|k|z)?sh|fish|python[\d.]*|node|deno|bun|ruby|perl|php|env")


def _loose(rule: str) -> bool:
    """Whether a runner's rule would let a headless Claude run any code: it ends at an interpreter or names env."""
    words = [os.path.basename(w) for w in rule.split()]
    return INTERPRETER.fullmatch(words[-1]) is not None or "env" in words


def runs(cfg: dict) -> list:
    """The run commands of [spec_tests]."""
    table = cfg.get("spec_tests")
    return [e["run"] for e in (table.values() if isinstance(table, dict) else ())
            if isinstance(e, dict) and isinstance(e.get("run"), str)]


PINNED: dict = {}               # a clone's root -> the config its pulse go run read at the start


def at(root: Path, ref: str) -> str:
    """.pulse/config.toml as commit `ref` holds it; "" without one."""
    out = subprocess.run(["git", "-C", str(root), "show", f"{ref}:.pulse/config.toml"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    return out.stdout if out.returncode == 0 else ""


def load(root: Path, ref: str = None) -> dict:
    """.pulse/config.toml of this clone, with defaults; with `ref` (the base on origin), EXECUTABLE and
    [agents] as that commit holds them, defaults where it holds none. Without an explicit ref, a running
    pulse go keeps its pinned config; an explicit trusted revision always takes precedence."""
    pinned = PINNED.get(str(Path(root).resolve()))
    if pinned is not None and ref is None:
        return {**pinned, "agents": dict(pinned["agents"])}
    cfg = dict(DEFAULTS)
    pulse, dia = root / ".pulse" / "config.toml", root / ".dia" / "config.toml"
    if pulse.is_file():
        data = _parse(pulse.read_text(encoding="utf-8"), pulse)
        cfg.update({k: data[k] for k in DEFAULTS if k in data})
        if "plan_approval" in data:
            _warn("plan_approval is ignored: valid published specs and Plans need no early approval; "
                  "pulse auto merge on|off selects the final integration policy")
        if "go_autostart" in data:
            _warn("go_autostart is ignored: only an explicit pulse go request starts the runner")
        cfg["agents"] = {**AGENTS, **(data.get("agents") or {})}
    elif dia.is_file():
        data = _parse(dia.read_text(encoding="utf-8"))
        cfg["mode"] = DIA_MODES.get(data.get("mode"), "on")
        cfg["base_branch"] = data.get("source_branch", cfg["base_branch"])
    cfg.setdefault("agents", dict(AGENTS))
    if ref is not None:
        text, where = at(root, ref) if ref else "", f"{ref[:12]}:.pulse/config.toml"
        if tomllib:            # what runs a program is never guessed line by line from a file tomllib rejects (L-6)
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError as e:
                from pulse import state
                raise state.StateError(f"{where} is no valid TOML ({e}): pulse go runs nothing from it") from None
        else:                  # without tomllib: what the fallback does not understand runs nothing either (M-2)
            try:
                data = _parse(text, where, strict=True)
            except ValueError as e:
                from pulse import state
                raise state.StateError(f"{e}: pulse go runs nothing from a config it cannot read whole "
                                       "(Python without tomllib)") from None
        cfg.update({k: data.get(k, DEFAULTS[k]) for k in EXECUTABLE})
        cfg["agents"] = {**AGENTS, **(data.get("agents") or {})}
    allow, gitdir = _allow(cfg["verify"], runs(cfg)), shlex.quote(str(common_dir(root)))
    cfg["agents"] = {k: str(t).replace("{allow}", allow).replace("{gitdir}", gitdir)
                     for k, t in cfg["agents"].items()}
    sb = str(cfg["spec_branch"] or "")         # without {n}, or named like a build branch, every item's would be one
    if "{n}" not in sb or any(is_spec_branch({"spec_branch": sb}, f"{t}/1-a-slug", 1) for t in ("feat", "imp", "fix")):
        _warn(f"{pulse}: spec_branch = {sb!r} needs {{n}} and a name no build branch has ({{type}}/{{n}}-{{slug}}); "
              f"{DEFAULTS['spec_branch']} applies")
        cfg["spec_branch"] = DEFAULTS["spec_branch"]
    return cfg


def _glob(pattern: str) -> str:
    """A [spec_tests] pattern as a regex, read as git reads a glob: * and ? stay within a directory, **/ spans
    any number of them, ** anything."""
    signs = {r"\*\*/": "(?:.*/)?", r"\*\*": ".*", r"\*": "[^/]*", r"\?": "[^/]"}
    return re.sub(r"\\\*\\\*/|\\\*\\\*|\\\*|\\\?", lambda m: signs[m.group(0)], re.escape(pattern))


def spec_runner(cfg: dict, path: str):
    """(run, localhost) of the first pattern in [spec_tests] that path matches, or None: what runs a spec test
    file. pulse go passes the config on the base, never a branch's (IMP-03-13 FR-02)."""
    table = cfg.get("spec_tests")
    for pattern, entry in (table.items() if isinstance(table, dict) else ()):
        if isinstance(entry, dict) and isinstance(entry.get("run"), str) and re.fullmatch(_glob(pattern), path):
            return entry["run"], entry.get("localhost") is True
    return None


def spec_branch(cfg: dict, n, slug: str, kind: str) -> str:
    """Item n's spec branch: spec_branch of the config with {n}, {slug}, and {type} filled in (#116). A project
    whose branch rule refuses docs/ names its own there, say {type}/{n}-{slug}-spec."""
    pattern = cfg.get("spec_branch") or DEFAULTS["spec_branch"]
    return str(pattern).replace("{n}", str(n)).replace("{slug}", slug).replace("{type}", kind)


def is_spec_branch(cfg: dict, branch: str, n) -> bool:
    """Whether branch is named as item n's spec branch: spec_branch with any slug and type, or docs/<n>-<slug>, the
    name before spec_branch existed."""
    # spec_branch() fills in two characters no pattern holds, and the regex puts any slug and type in their place
    rx = re.escape(spec_branch(cfg, n, "\x00", "\x01")).replace("\x00", ".+").replace("\x01", "(?:epic|feat|imp|fix)")
    return bool(re.fullmatch(rx, branch)) or branch.startswith(f"docs/{n}-")


def clone_config(root: Path) -> dict:
    """load(), where a worktree without a config of its own follows its main copy: pulse go's worktrees
    start from the base branch, which need not hold .pulse/config.toml (FX3.01, f6-go2)."""
    if (root / ".git").is_file() and not any((root / d / "config.toml").is_file() for d in (".pulse", ".dia")):
        root = common_dir(root).parent
    return load(root)


def agent_slots(spec: str, cap: int) -> dict:
    """'claude:2,codex:2' -> {'claude': 2, 'codex': 2}; a bare name gets cap slots."""
    out = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, n = (x.strip() for x in part.partition(":"))
        if n and not (n.isdigit() and int(n) > 0):
            raise ValueError(f"slots for '{name}' must be a positive number, not '{n}'")
        out[name] = int(n) if n else cap
    return out


def _version(path: Path) -> tuple:
    """.../extensions/openai.chatgpt-26.917.62051-darwin-arm64/... -> (26, 917, 62051)"""
    m = re.search(r"/extensions/[^/]+?-(\d+(?:\.\d+)*)", path.as_posix())
    return tuple(map(int, m.group(1).split("."))) if m else ()


NO_NET = "sandbox_workspace_write.network_access=false"
# What opens the Codex sandbox or its network past NO_NET: full access, a sandbox or network setting of the template's
# own, or a profile of ~/.codex/config.toml, which can set both (M1 of #119).
OPEN = re.compile(r"danger-full-access|--dangerously-bypass-approvals-and-sandbox|--yolo|network_access|sandbox_mode|"
                  r"^(-p|--profile)$|^--profile=")
WORKSPACE = ("--sandbox workspace-write", "-s workspace-write", "--sandbox=workspace-write", "--full-auto")


def program(argv: list) -> tuple:
    """(index, name) of the program a template runs: its first word that is no option, no VAR=value, and not env or
    npx, by its base name without .exe (npx @openai/codex is codex); (-1, "") for none."""
    for k, w in enumerate(argv):
        name = os.path.basename(w).removesuffix(".exe")
        if not (w.startswith("-") or re.match(r"[A-Za-z_]\w*=", w) or name in ("env", "npx")):
            return k, name
    return -1, ""


def unsandboxed(argv: list) -> str:
    """Why a Codex template leaves its sandbox to ~/.codex/config.toml, which may open it: it names no workspace
    sandbox (M1 of #119). "" for one that does, and for another program. pulse go refuses such an agent at its start;
    agent_argv still resolves a bare `codex`, as a lookup of where it lives."""
    k, prog = program(argv)
    if prog != "codex" or any(" ".join(argv[j:j + 2]) in WORKSPACE or argv[j] in WORKSPACE
                              for j in range(k + 1, len(argv))):
        return ""
    return "the Codex template names no sandbox, so ~/.codex/config.toml picks one: pulse go needs --sandbox " \
           "workspace-write (or --full-auto) in it"


def confine(argv: list) -> list:
    """A template's words as pulse go starts them, whatever the person's own settings allow (IMP-03-06 FR-04): the
    program codex in its workspace sandbox without network, never with a word that could open either (ValueError);
    the program claude without gh, which reaches GitHub with the person's token. Another program, whatever [agents]
    calls it, stays as it is: flags of these two would break it."""
    k, prog = program(argv)
    if prog == "codex":
        opened = next((w for w in argv if OPEN.search(w)), None)
        if opened:
            raise ValueError(f"{opened} can open the Codex sandbox or its network: pulse go runs Codex only in its "
                             "workspace sandbox, without network")
        return [*argv[:k + 1], "-c", NO_NET, *argv[k + 1:]]
    if prog == "claude":         # --disallowedTools takes every word up to the next option: -p follows in a template
        # ponytail: a template whose next word is {prompt} loses its prompt to the list; none of Pulse's is one
        return [*argv[:k + 1], "--disallowedTools", "Bash(gh:*)", *argv[k + 1:]]
    return argv


def agent_argv(template: str, prompt: str) -> list:
    """One agent template from [agents], confined, {prompt} filled in, ready for subprocess: the template is
    checked before the prompt, so no text of it reads as a flag. An agent missing on PATH runs from the
    newest VS Code extension that bundles it (D-27)."""
    argv = [tok.replace("{prompt}", prompt) for tok in confine(shlex.split(template))]
    if argv and argv[0] in BUNDLED and not shutil.which(argv[0]):
        found = max(Path.home().glob(f".vscode*/extensions/{BUNDLED[argv[0]]}"), key=_version, default=None)
        argv[0] = str(found or argv[0])
    return argv


def default_branch(root: Path) -> str:
    """origin's default branch, or main when there is no remote to ask. The full name: a short one turns
    ambiguous next to a tag named origin/main, and git answers remotes/origin/main (#69 final check)."""
    out = subprocess.run(["git", "-C", str(root), "symbolic-ref", "refs/remotes/origin/HEAD"],
                         capture_output=True, text=True, timeout=2)
    name = out.stdout.strip()
    return name.removeprefix("refs/remotes/origin/") if out.returncode == 0 and name.startswith(
        "refs/remotes/origin/") else "main"


def write(root: Path, **values) -> Path:
    """Set top-level keys in place; everything else in the file stays as it was."""
    path = root / ".pulse" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else \
        "# Pulse settings. pulse setup writes this file.\n"
    i = text.find("\n[")
    top, rest = (text[:i + 1], text[i + 1:]) if i >= 0 else (text, "")
    for key, value in values.items():
        if value is None:
            continue
        line = f"{key} = {json.dumps(value, ensure_ascii=False)}" if isinstance(value, str) else \
            f"{key} = {str(value).lower() if isinstance(value, bool) else value}"
        rx = re.compile(rf"^{re.escape(key)}\s*=.*$", re.M)
        top = rx.sub(line, top, count=1) if rx.search(top) else top.rstrip("\n") + "\n" + line + "\n"
    path.write_text(top + rest, encoding="utf-8")
    return path
