"""pulse setup: config, anchor blocks in agent files, GitHub labels, and outside Herdr the VS Code
task that starts the live map.

Anchor blocks point agents without hook support at Pulse. Blocks that DIA
wrote are recognised and replaced in place, so a migrated project never
ends up with two blocks.

`--cli` and `--codex-rules` set up this machine instead of a project: the
`pulse` command in ~/.local/bin and the Codex rules for it.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pulse import config, state

GH_MIN = (2, 94, 0)            # parent, sub-issues and blockers in gh issue --json

MARKERS = {
    "markdown": ("<!-- PULSE-START (managed by pulse) -->", "<!-- PULSE-END -->"),
    "hash": ("# === PULSE-START (managed by pulse) ===", "# === PULSE-END ==="),
}
LEGACY = {
    "markdown": ("<!-- DIA-WORKFLOW-START (managed by digital-innovation-agents) -->",
                 "<!-- DIA-WORKFLOW-END -->"),
    "hash": ("# === DIA-WORKFLOW-START (managed by digital-innovation-agents) ===",
             "# === DIA-WORKFLOW-END ==="),
}

LABELS = {                     # name: (color, description)
    "pulse:epic": ("5319e7", "Pulse: epic, parent of features"),
    "pulse:feat": ("0e8a16", "Pulse: feature"),
    "pulse:imp": ("1d76db", "Pulse: improvement on an existing feature"),
    "pulse:fix": ("d93f0b", "Pulse: fix for a bug or drift"),
    "pulse:approved": ("fbca04", "Pulse: legacy intent label; integration approval binds a checked result"),
    "pulse:draft": ("d4c5f9", "Pulse: no spec yet, analysis or spec work in progress"),
    "pulse:hold": ("b60205", "Pulse: a person holds it; pulse go neither plans nor builds it"),
    "pulse:failed": ("e99695", "Pulse: work failed; inspect retained work, then pulse resume permits another try"),
    "pulse:base": ("0052cc", "Pulse: base-repair work; base CI does not gate planning"),
    "pulse:auto": ("c5def5", "Pulse: legacy auto-mode record; each checked result needs final integration approval"),
    "pulse:order": ("c5def5", "Pulse: the shared manual order, one control issue per repository"),
    "P0": ("b60205", "Priority: at once"),              # pulse new copies priority: of the spec (#116)
    "P1": ("d93f0b", "Priority: soon"),
    "P2": ("fbca04", "Priority: later"),
}

BODY = """## Pulse

This project runs Pulse: the V-Model method, specs in the repository with
a shared board on GitHub with one record per item, and parallel agents.

- Settings: `.pulse/config.toml` (mode: {mode})
- Start with `/pulse` (in Codex `$pulse:pulse`): where things stand, what
  comes next, and the command for it.
- Pulse keeps claims, holds, results and confirmed final approvals in shared
  state, with one board record per item. Never write status into Markdown.
- Parallel work runs through `pulse go`, which a person explicitly starts:
  ready items with disjoint files never wait for each other, up to `cap` in
  the settings.
- An item's plan is its Plan file `_devprocess/plans/{{n}}-{{slug}}.md`. A
  plan mode, where the agent has one, shows that same Plan and
  keeps no plan of its own; in this project this holds over any other rule about plans.
- Specs and Plans proceed when structurally valid. Integration of checked results
  is automatic by default; an explicit manual final approval policy waits for a person.
- The always-on rules arrive through the Pulse hooks. An agent without
  hook support reads them from hooks/rules.md in the Pulse plugin.

A person changes the mode or removes this block with `pulse setup`, in their own terminal."""


@dataclass(frozen=True)
class Target:
    path: str
    style: str                 # markdown or hash

    def block_re(self, markers):
        start, end = markers[self.style]
        return re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)


EVERY = (                      # every agent file a block of Pulse or DIA may sit in: --remove and migrate
    Target("CLAUDE.md", "markdown"),
    Target("AGENTS.md", "markdown"),
    Target("GEMINI.md", "markdown"),
    Target(".cursorrules", "hash"),
    Target(".github/copilot-instructions.md", "markdown"),
    Target(".windsurfrules", "hash"),
)
CLAUDE, AGENTS = EVERY[:2]
# the files setup writes the block into; an older Pulse also wrote the others of EVERY (#109) and CLAUDE.md (#123)
TARGETS = tuple(t for t in EVERY if t.path in ("AGENTS.md", ".github/copilot-instructions.md"))
IMPORT = "@AGENTS.md <!-- pulse -->"   # the line setup sets in CLAUDE.md, marked so --remove takes only its own
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,}).*?(?:^ {0,3}\1|\Z)", re.M | re.S)   # Claude imports nothing from there


def target(path: str, pool=TARGETS) -> Target:
    found = next((t for t in pool if t.path == path), None)
    if found is None:          # one line, no traceback (#109 gate)
        raise state.StateError(f"{path} is no agent file of pulse setup: {', '.join(t.path for t in pool)}")
    return found


def anchor_block(t: Target, mode: str) -> str:
    start, end = MARKERS[t.style]
    return f"{start}\n{BODY.format(mode=mode)}\n{end}\n"


def write_anchor(text: str, t: Target, mode: str) -> str:
    block = anchor_block(t, mode)
    for markers in (MARKERS, LEGACY):          # replace in place, Pulse first
        rx = t.block_re(markers)
        if rx.search(text):
            return rx.sub(lambda _m: block, text, count=1)
    return _append(text, block)


def _append(text: str, piece: str) -> str:
    if not text:
        return piece
    return text + ("" if text.endswith("\n") else "\n") + ("" if text.endswith("\n\n") else "\n") + piece


def remove_anchor(text: str, t: Target) -> str:
    for markers in (MARKERS, LEGACY):
        text = t.block_re(markers).sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip() + "\n" if text.strip() else ""


def claude_import(text: str) -> str:
    """CLAUDE.md without a Pulse block and with a line that imports AGENTS.md (#123): Claude Code reads
    AGENTS.md by itself only where no CLAUDE.md is, the import brings it in with every setting."""
    if any(CLAUDE.block_re(m).search(text) for m in (MARKERS, LEGACY)):
        text = remove_anchor(text, CLAUDE)
    if re.search(r"(?m)(^|\s)@(\./)?AGENTS\.md(\s|$)", FENCE.sub("", text)):   # the person's own import, or ours
        return text
    return _append(text, IMPORT + "\n")


def remove_claude_import(text: str) -> str:
    """CLAUDE.md without the line setup set and without a Pulse block; a line the person wrote stays."""
    return remove_anchor(re.sub(r"(?m)^" + re.escape(IMPORT) + r"[ \t]*(\n|$)", "", text), CLAUDE)


def shared(root: Path) -> bool:
    """CLAUDE.md and AGENTS.md are one file, linked either way: it carries the block, never an import of itself."""
    try:
        return (root / CLAUDE.path).samefile(root / AGENTS.path)
    except OSError:
        return False


def gh_version(output: str) -> tuple:
    m = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", output or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


PULSE_BIN = Path(__file__).resolve().parent.parent / "bin" / "pulse"


def remove_git_hook(root: Path) -> dict:
    """The pre-commit hook an older Pulse installed (setup --git-hook, which kept a foreign one as
    pre-commit.bak): take out only ours (its marker line says `written by pulse setup`) and put the kept
    one back."""
    rel = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-path", "hooks"],
                         capture_output=True, text=True).stdout.strip()
    hooks = Path(rel) if Path(rel).is_absolute() else root / rel
    hook, bak = hooks / "pre-commit", hooks / "pre-commit.bak"
    status = _machine_file(hook, "", True, False)
    if status == "removed" and bak.exists():
        bak.replace(hook)
        status = "removed, pre-commit.bak put back"
    return {"path": str(hook), "status": status}


MARK = "written by `pulse setup"      # in every file pulse setup owns outside the project
SHIM = r"""#!/bin/sh
# pulse, written by `pulse setup --cli`. Each call looks the Pulse up again,
# so a plugin update needs no new setup: $PULSE_HOME, else the agent's own
# copy, so neither agent needs the other, else the newest of both caches.
newest() {
  for c; do for b in "$c"/plugins/cache/*/pulse/*/bin/pulse; do
    d=${b%/bin/pulse}
    [ -x "$b" ] && [ ! -e "$d/.orphaned_at" ] && printf '%s %s\n' "${d##*/}" "$b"
  done; done | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1 | cut -d' ' -f2-
}
cl=${CLAUDE_CONFIG_DIR:-$HOME/.claude} cx=${CODEX_HOME:-$HOME/.codex}
bin=${PULSE_HOME:+$PULSE_HOME/bin/pulse}
[ -n "$bin" ] || [ -z "${CODEX_THREAD_ID:-}" ] || bin=$(newest "$cx")   # a Codex session
[ -n "$bin" ] || [ "${CLAUDECODE:-}" != 1 ] || bin=$(newest "$cl")      # a Claude Code session
[ -n "$bin" ] || bin=$(newest "$cl" "$cx")                               # a terminal of its own
[ -z "${PULSE_WHICH:-}" ] || { echo "$bin"; exit 0; }    # for the Pulse hook
if [ ! -x "$bin" ]; then
  echo "pulse: no installed Pulse found. Install it: claude plugin install pulse@pssah4-skills" \
    "(Claude Code CLI), /plugins (Claude Code in VS Code), or codex plugin add pulse@pssah4-skills (Codex)" >&2
  exit 127
fi
exec "$bin" "$@"
"""
CODEX_RULES = """# Pulse, written by `pulse setup --codex-rules`: Codex runs `pulse` without
# asking, outside its sandbox, and never pulls a person's lever, in any mode.
prefix_rule(
    pattern = ["pulse"],
    decision = "allow",
    justification = "Pulse reads and writes the board on GitHub",
)
# `pulse -- <command>` too: Python 3.12 reads it as the command itself.
prefix_rule(
    pattern = ["pulse", ["approve", "approve-plan", "revoke", "handoff", "retry", "done", "--"]],
    decision = "forbidden",
    justification = "A person's lever, in their own terminal.",
)
prefix_rule(
    pattern = ["pulse", ["defer", "resume", "discard", "delete"]],
    decision = "forbidden",
    justification = "A person decides what gets built and when it is done, in their own terminal",
)
# A rule matches a prefix only: pulse takes --take right after the command and nowhere else.
prefix_rule(
    pattern = ["pulse", ["release", "claim"], "--take"],
    decision = "forbidden",
    justification = "A person decides who takes over a claim",
)
prefix_rule(
    pattern = ["pulse", ["on", "off"]],
    decision = "forbidden",
    justification = "A person switches Pulse for themselves, in their own terminal",
)
prefix_rule(
    pattern = ["pulse", "auto", ["plan", "build", "merge"]],
    decision = "forbidden",
    justification = "A person switches their own auto mode, in their own terminal or the Pulse map",
)
prefix_rule(
    pattern = ["gh", "pr", ["merge", "ready"]],
    decision = "forbidden",
    justification = "A person marks a pull request ready and merges it",
)
prefix_rule(
    pattern = ["gh", "issue", ["edit", "close", "reopen"]],
    decision = "forbidden",
    justification = "Only pulse writes the records on the board",
)
"""


def _machine_file(path: Path, body: str, remove: bool, dry_run: bool) -> str:
    """Write or remove one file outside the project; one pulse setup did not write stays."""
    if path.is_symlink() or path.exists() and MARK not in path.read_text(encoding="utf-8", errors="replace"):
        return "kept: not written by pulse setup"
    if remove and not path.exists():
        return "unchanged"
    if dry_run:
        return "would change"
    if remove:
        path.unlink()
        return "removed"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755 if body.startswith("#!") else 0o644)
    return "written"


def machine(cli: bool, codex_rules: bool, remove: bool, dry_run: bool) -> int:
    """`pulse setup --cli` and `--codex-rules`, with --remove to take them back. They need no
    repository and touch no project; `on_path` tells whether `pulse` now runs the shim."""
    shim = Path.home() / ".local" / "bin" / "pulse"
    rules = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "rules" / "pulse.rules"
    chosen = []
    if cli:
        chosen.append((shim, SHIM))
    if codex_rules:
        chosen.append((rules, CODEX_RULES))
    rep = {"changes": []}
    for path, body in chosen:
        late = "" if path != rules or remove else _late_take_in_codex()
        if late:
            status = f"not written: {late}, the pulse Codex runs, takes --take after the item number; update Pulse " \
                     "in Codex, then run pulse setup --codex-rules again"
        else:
            status = _machine_file(path, body, remove, dry_run)
        rep["changes"].append({"path": str(path), "status": status})
    if cli and not remove:
        rep["on_path"] = shutil.which("pulse") == str(shim)
    print(json.dumps(rep, indent=2))
    return 1 if any(c["status"].startswith(("kept", "not written")) for c in rep["changes"]) else 0


def _late_take_in_codex() -> str:
    """The `pulse` a Codex session runs by name when it still takes --take after the item number, else "". The rules
    let Codex run claim and release unasked, which holds only with a pulse that takes it right after the
    command and nowhere else (#58); such a pulse says so in its help. No pulse on PATH, or none installed
    (127), runs nothing the rules could let through."""
    # ponytail: asks this PATH and environment, not Codex's; a PULSE_HOME only one of them has goes unseen
    found = shutil.which("pulse")
    if not found:
        return ""
    try:
        run = subprocess.run([found, "claim", "--help"], env={**os.environ, "CODEX_THREAD_ID": "rules-probe"},
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return found
    late = run.returncode != 127 and "right after claim" not in " ".join(run.stdout.split())
    return found if late else ""


def shim_runs(root: Path, env: dict) -> bool:
    """Whether `pulse` on PATH is the shim and runs a copy of root's version, so an agent that
    types `pulse` gets the code its rules and skills came from."""
    found = shutil.which("pulse", path=env.get("PATH"))
    try:
        if not found or MARK not in Path(found).read_text(encoding="utf-8", errors="replace"):
            return False
        copy = subprocess.run([found], env={**env, "PULSE_WHICH": "1"}, capture_output=True,
                              text=True, timeout=5).stdout.strip()
        return bool(copy) and _version(Path(copy).parents[1]) == _version(root)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return False


UNTRUSTED = "Codex hooks not trusted: run /hooks in Codex"


def codex_hooks_trusted(home=None) -> bool:
    """Whether Codex keeps a trust entry for a Pulse hook, as the install script reads it (#111): the person gave
    it with /hooks, and Codex asks again after a change. home: CODEX_HOME, else ~/.codex."""
    path = Path(home or os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    try:
        return '[hooks.state."pulse@pssah4-skills:' in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def untrusted(agent: str) -> str:
    """UNTRUSTED where agent (the config's) names Codex and Codex runs no Pulse hook yet, else "":
    until then the lever guard does not run there."""
    try:
        codex = "codex" in config.agent_slots(agent or "", 1)
    except ValueError:
        codex = False
    return UNTRUSTED if codex and not codex_hooks_trusted() else ""


def _version(root: Path) -> str:
    return json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def version_key(text) -> tuple:
    """(0, 1, 10) for "0.1.10": versions compare by their numbers."""
    return tuple(int(n) for n in re.findall(r"\d+", text or ""))


TASK = {"label": "Pulse map", "type": "shell", "command": "pulse map", "runOptions": {"runOn": "folderOpen"},
        "problemMatcher": [], "presentation": {"panel": "dedicated"}}


def vscode_task(root: Path, dry_run: bool) -> dict:
    """The task "Pulse map" in .vscode/tasks.json, which starts the live map in a terminal panel as VS Code opens
    the folder (#121 FR-06); the other tasks stay. A file that is no plain JSON (comments, trailing commas) is
    never rewritten: the report carries the task to add by hand."""
    path, rel = root / ".vscode" / "tasks.json", ".vscode/tasks.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": "2.0.0", "tasks": []}
        tasks = data.setdefault("tasks", [])
        if not isinstance(tasks, list):
            raise ValueError("tasks is no list")
    except (OSError, ValueError, AttributeError):
        return {"path": rel, "status": "kept: no plain JSON, add the task by hand", "task": TASK}
    if any(isinstance(t, dict) and t.get("label") == TASK["label"] for t in tasks):
        return {"path": rel, "status": "unchanged"}
    if dry_run:
        return {"path": rel, "status": "would change"}
    tasks.append(TASK)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"path": rel, "status": "written"}


def herdr_key() -> str:
    """The key of Herdr's config.toml that opens the live map beside the focused pane; setup names it and never
    writes it. The path is absolute: a key command runs with the PATH of the Herdr server."""
    from pulse import mapstart          # which imports this module
    command = f"{shlex.quote(str(mapstart.pulse_bin()))} map --ensure"
    return f'[[keys.command]]\nkey = "prefix+m"\ntype = "shell"\ncommand = {json.dumps(command)}'


def _gh(*args) -> bool:
    """gh through state.gh, looked up per call so tests can swap it; True when it succeeded."""
    try:
        state.gh(list(args))
        return True
    except state.StateError:
        return False


def check_plan(root: Path, force=False) -> dict:
    """Use the freshly fetched base's commands for the same probe that gates planning in pulse go."""
    from pulse import compat, go
    result = dict(state="unchecked", step="prerequisites", sha="", fingerprint="", log="", cleanup="",
                  why="", next="Publish the required configuration on the base, then run pulse setup --check-plan")
    try:
        branch = config.load(root)["base_branch"] or config.default_branch(root)
        sha, why = go._fetch_base(root, branch)
        result["sha"] = sha
        if not sha:
            raise state.StateError(f"origin/{branch} could not be fetched: {why}")
        cfg = config.load(root, ref=sha)
        if (cfg["base_branch"] or config.default_branch(root)) != branch:
            raise state.StateError("base_branch differs from the trusted base configuration")
        if not cfg["verify"] or not cfg.get("spec_tests"):
            raise state.StateError(f"origin/{branch} needs verify and [spec_tests] before Plan compatibility can run")
        return compat.probe(root, cfg, sha, force=force)
    except (OSError, state.StateError) as error:
        result["why"] = config.printable(str(error))[:2000]
    return result


def run(root: Path, mode: str, cap: int, base_branch: str, files: list,
        labels: bool, remove: bool, dry_run: bool,
        agent: str = None, verify: str = None) -> dict:
    report = {"root": str(root), "changes": []}
    pool = EVERY if remove else TARGETS + (CLAUDE,)        # setup gives CLAUDE.md the import line (#123)
    chosen = [target(f, pool) for f in files] if files else [t for t in pool if (root / t.path).exists()]
    one = shared(root)
    if CLAUDE in chosen and AGENTS not in chosen and (one or not remove):
        chosen.insert(0, AGENTS)                         # the block that line imports, or the one file itself
    if one:
        chosen = [t for t in chosen if t != CLAUDE]
    if not remove:
        values = {k: v for k, v in dict(mode=mode, cap=cap, base_branch=base_branch,
                                        agent=agent, verify=verify).items()
                  if v is not None}
        path = root / ".pulse" / "config.toml"
        before = path.read_text(encoding="utf-8") if path.is_file() else None
        if dry_run:                    # the values it would write, and the base branch among them
            known = config.load(root)
            same = before is not None and all(known[k] == v for k, v in values.items())
        else:
            same = config.write(root, **values).read_text(encoding="utf-8") == before
        status = "unchanged" if same else ("would change" if dry_run else "written")
        report["config"] = values
        report["changes"].append({"path": ".pulse/config.toml", "status": status})
    for t in chosen:
        path = root / t.path
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        if t == CLAUDE:
            after = remove_claude_import(before) if remove else claude_import(before)
        else:
            after = remove_anchor(before, t) if remove else write_anchor(before, t, mode)
        status = "unchanged" if after == before else ("would change" if dry_run else "written")
        if status == "written" and not after and not (one and t == AGENTS):    # it held the Pulse block only
            path.unlink()
            status = "removed"
        if status == "written":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(after, encoding="utf-8")
        report["changes"].append({"path": t.path, "status": status})
    if remove and not dry_run:
        report["git_hook"] = remove_git_hook(root)
    if not remove:                     # in Herdr the map opens beside each session, no task needed
        if not os.environ.get("HERDR_ENV") and mode != "off":      # Pulse off: no map starts with the folder
            report["vscode_task"] = vscode_task(root, dry_run)
        report["herdr_key"] = herdr_key()
    try:
        found = gh_version(state.gh(["--version"]))
    except (OSError, state.StateError):
        found = (0, 0, 0)
    report["gh"] = {"found": ".".join(map(str, found)), "ok": found >= GH_MIN,
                    "needed": ".".join(map(str, GH_MIN))}
    if labels and not dry_run and report["gh"]["ok"]:
        _gh("label", "edit", "pulse:ready", "--name", "pulse:approved")   # keeps it on every issue
        report["labels"] = {name: _gh("label", "create", name, "--color", color, "--description", desc, "--force")
                            for name, (color, desc) in LABELS.items()}
    if mode == "on" and not remove and not dry_run:
        report["compatibility"] = check_plan(root)
    return report


def anchors(root: Path, mode: str, dry_run: bool = False) -> list:
    """The Pulse block with mode, only where a file has one (IMP-14); the map's settings change it too (#182). A block
    an older Pulse wrote into CLAUDE.md moves to AGENTS.md (#123). The changes, as pulse setup --anchors prints them."""
    changes = []
    claude = root / CLAUDE.path
    moves = claude.is_file() and bool(CLAUDE.block_re(MARKERS).search(claude.read_text(encoding="utf-8")))
    for t in TARGETS + (() if shared(root) else (CLAUDE,)):
        path = root / t.path
        before = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not t.block_re(MARKERS).search(before) and not (moves and t == AGENTS):
            continue
        after = claude_import(before) if t == CLAUDE else write_anchor(before, t, mode)
        if after != before and not dry_run:
            path.write_text(after, encoding="utf-8")
        changes.append({"path": t.path, "status": "unchanged" if after == before else
                        "would change" if dry_run else "written"})
    return changes


def main(args) -> int:
    root = config.find_root()
    if root is None:
        print("pulse setup: not inside a git repository")
        return 2
    if getattr(args, "check_plan", False):
        result = check_plan(root, force=True)
        print(json.dumps({"root": str(root), "compatibility": result}, indent=2))
        return 0 if result["state"] == "compatible" else 1
    known = config.load(root)
    if getattr(args, "anchors", False):
        print(json.dumps({"root": str(root), "changes": anchors(root, known["mode"] or "on", args.dry_run)}, indent=2))
        return 0
    rep = run(root, args.mode or known["mode"] or "on", args.cap or known["cap"],
              args.base_branch or known["base_branch"] or config.default_branch(root),
              args.files or [], args.labels, args.remove, args.dry_run,
              args.agent, args.verify)
    print(json.dumps(rep, indent=2))
    return 0
