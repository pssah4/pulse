"""Project config: .pulse/config.toml, with the DIA config as read fallback.

A project without either file has not activated Pulse (mode None). DIA
modes map onto Pulse: off stays off, git-only and github-sync mean on.
"""
from __future__ import annotations

import functools
import itertools
import json
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

DEFAULTS = {"mode": None, "cap": 4, "base_branch": None, "repo": None, "source": None,
            "parallel": "items", "agent": "claude", "agent_timeout": 60, "verify": None,
            "review_agent": None, "plan_approval": "auto", "map_autostart": True, "ids_since": None,
            "go_autostart": True}
DIA_MODES = {"off": "off", "git-only": "on", "github-sync": "on"}
PARALLEL = ("off", "items", "max")
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
PLAN_APPROVAL = ("auto", "manual")


def _unescape(s: str) -> str:
    """A basic TOML string's escapes are JSON's, but for \\U########; keep the raw text then."""
    try:
        return json.loads(f'"{s}"')
    except ValueError:
        return s


@functools.lru_cache(maxsize=None)          # each warning once, however often a command reads the config
def _warn(msg: str) -> None:
    print(f"pulse: {msg}", file=sys.stderr)


def _parse(text: str, path: Path = None) -> dict:
    """TOML where Python has tomllib (3.11+). Else, or when tomllib rejects the file, flat
    key = value pairs plus [sections], enough for this config; with a path, a line of the top
    level or [agents] that this does not understand is skipped with a warning naming it."""
    if tomllib:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            pass                           # the lines below name the line; the settings stay
    out: dict = {}
    cur, mine = out, True
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[([\w.]+)\]\s*(?:#.*)?$", line)
        if m:
            cur, mine = out, m.group(1) == "agents"      # other sections have their own readers
            for part in m.group(1).split("."):
                cur = cur.setdefault(part, {})
            continue
        m = re.match(r"""^(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|'([^']*)'|(-?\d+)|(true|false))\s*(?:#.*)?$""", line)
        if m:
            k, s1, s2, n, b = m.groups()
            cur[k] = (_unescape(s1) if s1 is not None else s2 if s2 is not None
                      else int(n) if n is not None else b == "true")
        elif path and mine:
            _warn(f"{path}:{no}: not understood, skipped: {line}")
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
    """pulse/ in the shared git dir: what all worktrees of a clone share (caches, presence, runs)."""
    return common_dir(root) / "pulse"


def _allow(verify) -> str:
    """What a headless Claude runs unasked: verify up to its first option or path argument, and git."""
    # ponytail: verify is kept up to its first option or path argument, so a runner without
    # subcommands keeps its plain arguments (pytest tests), and a verify that chains commands
    # (a && b) gets a rule for its start only; parse per runner when a project needs that
    words = str(verify or "").split()
    if words[1:2] == ["-m"]:
        words = words[:3]                                    # python3 -m pytest
    else:                                                    # uv run pytest -q; go test ./... -> go test
        words = words[:1] + list(itertools.takewhile(lambda w: not re.match(r"[-&|;]|.*[/.]", w), words[1:]))
    cmds = [" ".join(words)] if words else []
    cmds += [f"git {g}" for g in ("add", "commit", "status", "diff", "log")]
    return " ".join(shlex.quote(f"Bash({c}:*)") for c in cmds)


PINNED: dict = {}               # a clone's root -> the config its pulse go run read at the start


def load(root: Path) -> dict:
    """.pulse/config.toml of this clone, with defaults. While a pulse go run lives in this process, the
    config it started with: a branch checked out meanwhile changes nothing (audit of #44, H-1)."""
    pinned = PINNED.get(str(Path(root).resolve()))
    if pinned is not None:
        return {**pinned, "agents": dict(pinned["agents"])}
    cfg = dict(DEFAULTS)
    pulse, dia = root / ".pulse" / "config.toml", root / ".dia" / "config.toml"
    if pulse.is_file():
        data = _parse(pulse.read_text(encoding="utf-8"), pulse)
        cfg.update({k: data[k] for k in DEFAULTS if k in data})
        cfg["agents"] = {**AGENTS, **(data.get("agents") or {})}
        cfg["source"] = ".pulse"
    elif dia.is_file():
        data = _parse(dia.read_text(encoding="utf-8"))
        cfg["mode"] = DIA_MODES.get(data.get("mode"), "on")
        cfg["base_branch"] = data.get("source_branch", cfg["base_branch"])
        cfg["source"] = ".dia"
    cfg.setdefault("agents", dict(AGENTS))
    allow, gitdir = _allow(cfg["verify"]), shlex.quote(str(common_dir(root)))
    cfg["agents"] = {k: str(t).replace("{allow}", allow).replace("{gitdir}", gitdir)
                     for k, t in cfg["agents"].items()}
    if cfg["parallel"] not in PARALLEL:
        cfg["parallel"] = "items"
    if cfg["plan_approval"] not in PLAN_APPROVAL:
        cfg["plan_approval"] = "auto"
    return cfg


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


def agent_argv(template: str, prompt: str) -> list:
    """One agent template from [agents], {prompt} filled in, ready for subprocess. An agent
    missing on PATH runs from the newest VS Code extension that bundles it (D-27)."""
    argv = [tok.replace("{prompt}", prompt) for tok in shlex.split(template)]
    if argv and argv[0] in BUNDLED and not shutil.which(argv[0]):
        found = max(Path.home().glob(f".vscode*/extensions/{BUNDLED[argv[0]]}"), key=_version, default=None)
        argv[0] = str(found or argv[0])
    return argv


def default_branch(root: Path) -> str:
    """origin's default branch, or main when there is no remote to ask."""
    out = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short",
                          "refs/remotes/origin/HEAD"], capture_output=True, text=True, timeout=2)
    return out.stdout.strip().split("/", 1)[-1] if out.returncode == 0 else "main"


def write(root: Path, **values) -> Path:
    """Set top-level keys in place; everything else in the file stays as it was."""
    path = root / ".pulse" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else \
        "# Pulse settings. /pulse-setup writes this file.\n"
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
