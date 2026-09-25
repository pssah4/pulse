#!/usr/bin/env python3
"""Pulse hook: one entry for every hook event.

  session-start, subagent-start   inject the rules plus the active item
  stop                            nudge once when code changed but no check ran,
                                  or a PR's last commit has no review
  presence                        record the event for the live map, and keep
                                  the heartbeat of held items (async)

Every event of an active project also lands in the presence log.

A hook must never break a session: any failure is swallowed and the hook
prints nothing. The active item comes from the issue cache that the pulse
CLI keeps (state.cache_path). Two paths reach GitHub through gh: the stop
verdict, where review.last reads the verdicts on the item's PR when this
clone keeps none, and the heartbeat on a tool event, at most every 10
minutes per session and in the background.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from pulse import config, dispatch, go, presence, review, setup, state  # noqa: E402

PARALLEL = {
    "off": "Parallel: off (.pulse/config.toml). Work on one item at a time.",
    "items": ("Parallel: items (.pulse/config.toml). Independent ready items run side by side "
              "through `pulse go`, each in its own worktree; inside one item, work task by task."),
    "max": ("Parallel: max (.pulse/config.toml). Never do independent work one after another. "
            "Items: `pulse go`. Inside a PLAN: run each task wave (same wave = disjoint files) as "
            "parallel subagents, then run the wave's checks before the next wave. Plan dependencies "
            "contract-first so dependents start on the interface; a dependent that needs unmerged "
            "code stacks on its blocker's branch once the blocker's PR is ready."),
}
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
PATCHED = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.M)
PROSE = re.compile(r"(\.(md|mdx|txt|rst|adoc)$)|(^|/)(docs|_devprocess)/")
CHECK = presence.CHECK
BEAT = 10 * 60                 # seconds between two heartbeats of one session (D-43)


def platform(env):
    if env.get("CURSOR_PLUGIN_ROOT") or env.get("CURSOR_VERSION"):
        return "cursor"
    if env.get("COPILOT_CLI") or env.get("COPILOT_PLUGIN_DATA"):
        return "copilot"
    return "claude"            # Claude Code and Codex share the nested form


def emit(event, text, env):
    kind = platform(env)
    if kind == "cursor":
        return json.dumps({"additional_context": text})
    if kind == "copilot":
        return json.dumps({"additionalContext": text}) if event == "SessionStart" else ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def active_item(root):
    try:
        branch = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    n = state.item_of(branch)          # feat/, imp/, fix/: a docs/12-x branch is no item's
    if not n:
        return ""
    item = {}
    try:
        item = next((i for i in state.cached(root) if i.get("number") == n), {})
    except (OSError, subprocess.TimeoutExpired):
        pass
    line = f"Active item: #{n} {item.get('title', '')}".rstrip() + f" (branch {branch})."
    if item.get("spec"):
        line += f" Spec: {item['spec']}."
    return line + f" Details: `pulse show {n}`."


def context(event, root, cfg, env):
    if cfg["mode"] == "off":
        return ""
    if cfg["mode"] is None:
        if event != "SessionStart":
            return ""
        return ("Pulse is installed but not active in this project. `/pulse-setup` "
                "(in Codex `$pulse:pulse-setup`) activates it.")
    own = ROOT / "bin" / "pulse"
    # Claude Code runs its hooks with CLAUDECODE=1 and appends this plugin's bin/ to its Bash tool's PATH,
    # so there `pulse` is this plugin's unless another one comes first on PATH.
    # ponytail: a Codex started from that Bash tool inherits both, so its `pulse` is Claude Code's copy,
    # maybe of another version; compare the versions as shim_runs does if that ever bites
    found = shutil.which("pulse", path=env.get("PATH"))
    claude_code = env.get("CLAUDECODE") == "1" and Path(env.get("CLAUDE_PLUGIN_ROOT") or "/").resolve() == ROOT \
        and (not found or Path(found).resolve() == own)
    cli = ("Pulse CLI: `pulse`." if claude_code or setup.shim_runs(ROOT, env) else
           f"Pulse CLI: `{own}`. Wherever these rules or a Pulse skill say `pulse`, run that path.")
    parts = [(HERE / "rules.md").read_text(encoding="utf-8").strip(), PARALLEL[cfg["parallel"]], cli]
    item = active_item(root)
    if item:
        parts.append(item)
    if event == "SessionStart":
        idle = idle_capacity(root, cfg)
        if idle:
            parts.append(idle)
    return "\n\n".join(parts)


def codex_uses(call):
    """A tool call from a Codex rollout as Claude tool uses: apply_patch edits each file its
    patch names, exec_command (or shell) runs a command."""
    try:
        args = json.loads(call["arguments"]) if call["type"] == "function_call" else {"input": call["input"]}
    except (KeyError, TypeError, ValueError):
        return []
    if call.get("name") == "apply_patch":
        return [{"name": "Edit", "input": {"file_path": f.strip()}} for f in PATCHED.findall(args.get("input", ""))]
    cmd = args.get("cmd") or args.get("command")
    return [{"name": "Bash", "input": {"command": " ".join(cmd) if isinstance(cmd, list) else cmd}}] if cmd else []


def read_transcript(path):
    """Parse a Claude Code transcript or Codex rollout once into its JSON lines: broken lines
    are skipped, an unreadable file yields no entries."""
    try:
        raw_lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries = []
    for raw in raw_lines:
        try:
            entries.append(json.loads(raw))
        except ValueError:
            continue
    return entries


def failed_tool_uses(entries):
    """The tool_use ids whose result anywhere in the transcript is an error."""
    failed = set()
    for entry in entries:
        content = entry.get("message", {}).get("content")
        if isinstance(content, list):
            failed |= {p.get("tool_use_id") for p in content if isinstance(p, dict) and p.get("is_error")}
    return failed


def last_turn_tools(entries):
    """Tool uses since the last real user prompt (tool results do not count), from a Claude Code
    transcript or a Codex rollout."""
    uses = []
    for entry in entries:
        if entry.get("type") == "response_item":            # Codex
            item = entry.get("payload") or {}
            if item.get("type") == "message" and item.get("role") == "user":
                uses = []
            elif item.get("type") in ("function_call", "custom_tool_call"):
                uses += codex_uses(item)
            continue
        content = entry.get("message", {}).get("content")
        if entry.get("type") == "user" and (isinstance(content, str) or any(
                isinstance(p, dict) and p.get("type") == "text" for p in content or [])):
            uses = []
        elif entry.get("type") == "assistant" and isinstance(content, list):
            uses += [p for p in content if isinstance(p, dict) and p.get("type") == "tool_use"]
    return uses


def cached_only(args):
    """gh for state.me in the stop verdict: the login comes from its cache or not at all."""
    raise state.StateError("no cached login")


def idle_capacity(root, cfg):
    """At parallel = max, ready work with free slots must not wait for the next prompt."""
    if cfg["parallel"] != "max" or go.running(root):
        return ""
    try:
        login = state.me(root, run=cached_only)
    except state.StateError:
        return ""              # without a cached login the slots are unknown; never guess
    r = dispatch.view(root, state.cached(root), {**cfg, "parallel": "max"}, login)
    if not r["next"]:
        return ""
    names = ", ".join(f"#{i['number']}" for i in r["next"])
    return (f"Pulse runs at parallel = max: {names} {'is' if len(r['next']) == 1 else 'are'} ready "
            f"and {r['free']} slot{'s' if r['free'] != 1 else ''} free. Start them with `pulse go` "
            "(or as parallel subagents), or say in one sentence why not.")


def unreviewed_pr(root, payload, entries):
    """A pull request is ready only with a review and a security audit of its last commit
    (ADR-05). The cache may not know a PR opened this turn yet, so `gh pr create` in this
    turn counts too, unless its tool result is an error (denied, or gh failed)."""
    if payload.get("agent_id"):
        return ""
    try:
        branch, head = [subprocess.run(["git", "-C", str(root), "rev-parse", *a], capture_output=True,
                                       text=True, timeout=2).stdout.strip()
                        for a in (["--abbrev-ref", "HEAD"], ["HEAD"])]
    except (OSError, subprocess.TimeoutExpired):
        return ""
    n = state.item_of(branch)
    if not n:
        return ""
    item = next((i for i in state.cached(root) if i.get("number") == n), {})
    creates = [u for u in last_turn_tools(entries)
               if u.get("name") == "Bash" and "gh pr create" in u["input"].get("command", "")]
    failed = failed_tool_uses(entries) if creates else set()
    opened = any(u.get("id") not in failed for u in creates)
    if not (item.get("pr") or opened):
        return ""
    missing = [k for k in ("review", "audit") if (review.last(root, n, k) or {}).get("commit") != head]
    if not missing:
        return ""
    how = "; ".join(f"`pulse {k} {n} --run`, or a subagent with the brief from `pulse {k} {n}`, "
                    f"then `pulse {k} {n} --record`" for k in missing)
    return (f"Pulse: #{n} has a pull request, but its last commit has no {' and no '.join(missing)}. "
            f"Run {'them' if len(missing) > 1 else 'it'} in a fresh session ({how}); "
            "the PR stays draft until both pass.")


def untested_code(entries):
    uses, failed = last_turn_tools(entries), failed_tool_uses(entries)     # a refused edit changed nothing
    edited = sorted({u["input"].get("file_path") or u["input"].get("notebook_path") or ""
                     for u in uses if u.get("name") in EDIT_TOOLS and u.get("id") not in failed} - {""})
    code = [f for f in edited if not PROSE.search(f)]
    checked = any(u.get("name") == "Bash" and CHECK.search(u["input"].get("command", ""))
                  for u in uses)
    if not code or checked:
        return ""
    shown = ", ".join(code[:3]) + (f" and {len(code) - 3} more" if len(code) > 3 else "")
    return (f"Pulse: code changed this turn ({shown}) but no test or build ran. "
            "Run the smallest check that can disprove the change, "
            "or say in one sentence why none applies.")


def heartbeat(root, payload, env):
    """A session that holds an item keeps a sign of life on the board: on a tool event, at most every
    BEAT seconds (a stamp per session in the shared git dir), its claim marks name the phase `working`
    and the time; a draft keeps its phase, analysis or spec. pulse go beats for its own sessions."""
    sid = str(payload.get("session_id") or "")
    if not (sid and payload.get("tool_name")) or env.get("PULSE_HOLDER"):
        return
    stamp = config.pulse_dir(root) / "beats" / re.sub(r"[^\w.-]", "_", sid)
    try:
        if time.time() - stamp.stat().st_mtime < BEAT:
            return
    except OSError:
        stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()              # before gh: a round that fails waits its ten minutes too
    gh = state.gh              # looked up per call so tests can swap it
    # ponytail: a Codex session is its hook's session_id, taken to be CODEX_THREAD_ID (the docs show
    # thread ids there); if they differ, its claims get no heartbeat. Each session leaves its empty
    # stamp behind; SessionEnd could take it along if they ever pile up.
    who = {"id": f"{'codex' if 'turn_id' in payload else 'claude'}:{sid}"}
    repo, login = state.repo(root, gh), state.me(root, gh)
    for i in state.cached(root) or state.load(root, repo, run=gh):
        if i.get("claimed_by") == login:
            state.beat(root, repo, i["number"], (i.get("draft") and i.get("claimed_phase")) or "working",
                       run=gh, who=who)


def stop_verdict(root, cfg, payload, env):
    # PULSE_HOLDER: an agent or gate session of pulse go, which runs the gates itself
    if platform(env) != "claude" or payload.get("stop_hook_active") or env.get("PULSE_HOLDER"):
        return ""
    path = payload.get("transcript_path")
    entries = read_transcript(path) if path else []
    reasons = [r for r in (untested_code(entries), unreviewed_pr(root, payload, entries)) if r]
    return json.dumps({"decision": "block", "reason": " ".join(reasons)}) if reasons else ""


def main(argv, stdin_text, env):
    try:
        event = {"session-start": "SessionStart", "subagent-start": "SubagentStart",
                 "stop": "Stop", "presence": "presence"}.get(argv[0] if argv else "")
        root = config.find_root()
        if not event or root is None:
            return ""
        cfg = config.load(root)
        if cfg["source"] is None and (root / ".git").is_file():      # a worktree follows its main copy
            cfg = config.load(config.common_dir(root).parent)
        if cfg["mode"] == "on" and stdin_text.strip():
            try:
                presence.record(root, json.loads(stdin_text))
            except (ValueError, OSError, AttributeError):
                pass
        if event == "presence":
            if cfg["mode"] == "on":
                heartbeat(root, json.loads(stdin_text), env)
            return ""
        if event == "Stop":
            return stop_verdict(root, cfg, json.loads(stdin_text), env) if cfg["mode"] == "on" else ""
        text = context(event, root, cfg, env)
        return emit(event, text, env) if text else ""
    except Exception:          # a hook must never break the session
        return ""


if __name__ == "__main__":
    out = main(sys.argv[1:], sys.stdin.read() if not sys.stdin.isatty() else "", dict(os.environ))
    if out:
        sys.stdout.write(out)
