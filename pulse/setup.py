"""/pulse-setup: config, anchor blocks in agent files, GitHub labels.

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
    "pulse:approved": ("fbca04", "Pulse: the team wants it built"),
    "pulse:plan-ok": ("c2e0c6", "Pulse: a person approved the PLAN a hold stopped"),
    "pulse:draft": ("d4c5f9", "Pulse: no spec yet, analysis or spec work in progress"),
}

BODY = """## Pulse

This project runs Pulse: the V-Model method, specs in the repository with
a shared board on GitHub with one record per item, and parallel agents.

- Settings: `.pulse/config.toml` (mode: {mode})
- Start with `/pulse` (in Codex `$pulse:pulse`): where things stand, what
  comes next, and the command for it.
- Item state (draft, approved, taken, blocked, done) lives on the board on GitHub, one record per item
  and only `pulse` writes it. Never write status into Markdown.
- Parallel work runs through `pulse go`, as far as `parallel` in the
  settings allows: ready items with disjoint files never wait for each other.
- An item's plan is its PLAN file `_devprocess/plans/{{n}}-{{slug}}.md`. A
  plan mode, where the agent has one, only shows that PLAN for approval and
  keeps no plan of its own; in this project this holds over any other rule about plans.
- The always-on rules arrive through the Pulse hooks. An agent without
  hook support reads them from hooks/rules.md in the Pulse plugin.

`/pulse-setup` changes the mode or removes this block."""


@dataclass(frozen=True)
class Target:
    path: str
    style: str                 # markdown or hash

    def block_re(self, markers):
        start, end = markers[self.style]
        return re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)


TARGETS = (
    Target("CLAUDE.md", "markdown"),
    Target("AGENTS.md", "markdown"),
    Target("GEMINI.md", "markdown"),
    Target(".cursorrules", "hash"),
    Target(".github/copilot-instructions.md", "markdown"),
    Target(".windsurfrules", "hash"),
)


def target(path: str) -> Target:
    return next(t for t in TARGETS if t.path == path)


def anchor_block(t: Target, mode: str) -> str:
    start, end = MARKERS[t.style]
    return f"{start}\n{BODY.format(mode=mode)}\n{end}\n"


def write_anchor(text: str, t: Target, mode: str) -> str:
    block = anchor_block(t, mode)
    for markers in (MARKERS, LEGACY):          # replace in place, Pulse first
        rx = t.block_re(markers)
        if rx.search(text):
            return rx.sub(lambda _m: block, text, count=1)
    if not text:
        return block
    return text + ("" if text.endswith("\n") else "\n") + ("" if text.endswith("\n\n") else "\n") + block


def remove_anchor(text: str, t: Target) -> str:
    for markers in (MARKERS, LEGACY):
        text = t.block_re(markers).sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip() + "\n" if text.strip() else ""


def gh_version(output: str) -> tuple:
    m = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", output or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


HOOK_TEMPLATE = Path(__file__).resolve().parent.parent / "hooks" / "git-pre-commit"
PULSE_BIN = Path(__file__).resolve().parent.parent / "bin" / "pulse"


def write_git_hook(root: Path, remove: bool = False) -> dict:
    """Install the pre-commit hook, a foreign one kept as pre-commit.bak; remove takes out only
    ours (its marker line says `written by pulse setup`) and puts the kept one back."""
    rel = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-path", "hooks"],
                         capture_output=True, text=True).stdout.strip()
    hooks = Path(rel) if Path(rel).is_absolute() else root / rel
    hook, bak = hooks / "pre-commit", hooks / "pre-commit.bak"
    if not remove and hook.exists() and MARK not in hook.read_text(encoding="utf-8", errors="replace"):
        hook.replace(bak)
    body = HOOK_TEMPLATE.read_text(encoding="utf-8").replace("{{pulse_bin}}", str(PULSE_BIN))
    status = _machine_file(hook, body, remove, False)
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
# asking, outside its sandbox; what a person decides still asks.
prefix_rule(
    pattern = ["pulse"],
    decision = "allow",
    justification = "Pulse reads and writes the board on GitHub",
)
prefix_rule(
    pattern = ["pulse", ["approve", "approve-plan", "rank", "done"]],
    decision = "prompt",
    justification = "A person decides what gets built, in which order, and when it is done",
)
# A rule matches a prefix only and cannot see --take after a note or a file list: every release and claim asks,
# and so does `pulse -- <command>`, which Python 3.12 reads as the command itself.
prefix_rule(
    pattern = ["pulse", ["release", "claim", "--"]],
    decision = "prompt",
    justification = "A person decides who takes over a claim (--take)",
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
    rep = {"changes": [{"path": str(p), "status": _machine_file(p, body, remove, dry_run)} for p, body in chosen]}
    if cli and not remove:
        rep["on_path"] = shutil.which("pulse") == str(shim)
    print(json.dumps(rep, indent=2))
    return 1 if any(c["status"].startswith("kept") for c in rep["changes"]) else 0


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


def _version(root: Path) -> str:
    return json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def version_key(text) -> tuple:
    """(0, 1, 10) for "0.1.10": versions compare by their numbers."""
    return tuple(int(n) for n in re.findall(r"\d+", text or ""))


def _gh(*args) -> bool:
    """gh through state.gh, looked up per call so tests can swap it; True when it succeeded."""
    try:
        state.gh(list(args))
        return True
    except state.StateError:
        return False


def run(root: Path, mode: str, cap: int, base_branch: str, files: list,
        labels: bool, remove: bool, dry_run: bool, git_hook: bool = False,
        parallel: str = None, agent: str = None, verify: str = None, plan_approval: str = None) -> dict:
    report = {"root": str(root), "changes": []}
    if not remove:
        values = {k: v for k, v in dict(mode=mode, cap=cap, base_branch=base_branch, parallel=parallel,
                                        agent=agent, verify=verify, plan_approval=plan_approval).items()
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
    chosen = [target(f) for f in files] if files else [t for t in TARGETS if (root / t.path).exists()]
    for t in chosen:
        path = root / t.path
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        after = remove_anchor(before, t) if remove else write_anchor(before, t, mode)
        status = "unchanged" if after == before else ("would change" if dry_run else "written")
        if status == "written" and not after:          # it held the Pulse block only
            path.unlink()
            status = "removed"
        if status == "written":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(after, encoding="utf-8")
        report["changes"].append({"path": t.path, "status": status})
    if (git_hook or remove) and not dry_run:
        report["git_hook"] = write_git_hook(root, remove)
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
    return report


def main(args) -> int:
    root = config.find_root()
    if root is None:
        print("pulse setup: not inside a git repository")
        return 2
    known = config.load(root)
    if getattr(args, "anchors", False):        # the Pulse block only, where a file has one (IMP-14)
        changes = []
        for t in TARGETS:
            path = root / t.path
            before = path.read_text(encoding="utf-8") if path.is_file() else ""
            if not t.block_re(MARKERS).search(before):
                continue
            after = write_anchor(before, t, known["mode"] or "on")
            if after != before and not args.dry_run:
                path.write_text(after, encoding="utf-8")
            changes.append({"path": t.path, "status": "unchanged" if after == before else
                            "would change" if args.dry_run else "written"})
        print(json.dumps({"root": str(root), "changes": changes}, indent=2))
        return 0
    rep = run(root, args.mode or known["mode"] or "on", args.cap or known["cap"],
              args.base_branch or known["base_branch"] or config.default_branch(root),
              args.files or [], args.labels, args.remove, args.dry_run, args.git_hook,
              args.parallel, args.agent, args.verify, args.plan_approval)
    print(json.dumps(rep, indent=2))
    return 0
