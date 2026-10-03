#!/usr/bin/env python3
"""Pulse hook: one entry for each hook event Pulse registers.

  session-start, subagent-start   inject the rules plus the active item; in Herdr a session
                                  start opens the live map beside it
  stop                            nudge once when code changed but no check ran,
                                  or the item branch has commits origin lacks
  guard                           deny a command that pulls a person's lever
                                  (PreToolUse, synchronous, pulse/guard.py)
  presence                        update local activity metadata, without commands or transcripts; a
                                  session that holds items renews its sign of life on them at most
                                  every 10 min, in a detached process (pulse/alive.py)

The guard runs for commands that reach a shell or a tool
server. A hook must never break a session: any failure
is swallowed and the hook prints nothing. The active item comes from the
issue cache that the pulse CLI keeps (state.cache_path). Two paths reach
GitHub through gh: the stop verdict for unpushed commits, one read of the
item within 2 s for who holds it, and a session start on an item the board
cache lacks, one read within 2 s.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from pulse import alive, auto, config, guard, levers, presence, ready, settings, setup, state  # noqa: E402

KEPT = 86400                   # seconds a hook takes the login the CLI kept: it asks no network (#111)
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
PATCHED = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.M)
PROSE = re.compile(r"(\.(md|mdx|txt|rst|adoc)$)|(^|/)(docs|_devprocess)/")
# a command that tests or builds: the stop verdict counts it as a check that ran
CHECK = re.compile(
    r"\b(pytest|unittest|tox|nox|jest|vitest|mocha|playwright|cypress|phpunit|rspec"
    r"|go (test|build|vet)|cargo (test|build|check|clippy)|dotnet (test|build)"
    r"|mvn|gradle|tsc|mypy|ruff|eslint|make (test|check)"
    r"|(npm|pnpm|yarn|bun)( run)? (test|build|lint|check|typecheck))\b")


def platform(env):
    if env.get("COPILOT_CLI") or env.get("COPILOT_PLUGIN_DATA"):
        return "copilot"
    return "claude"            # Claude Code and Codex share the nested form


def emit(event, text, env):
    kind = platform(env)
    if kind == "copilot":
        return json.dumps({"additionalContext": text}) if event == "SessionStart" else ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def quick(args):
    """gh within 2 s: a hook never waits long for GitHub. state.gh is looked up per call, so tests can swap it."""
    return state.gh(args, timeout=2)


def clip(text, n=100):
    """A value from git or the board, printable and at most n characters: the whole context stays under the
    10,000 characters Claude Code passes on in full (#179)."""
    text = ready.printable(text)
    return text if len(text) <= n else text[:n - 1] + "…"


def active_item(root):
    """The item of the checked-out branch, from the board cache, else from one read of it (a claim or a take
    drops the cache); and who holds it when another login does (#99 FR-06)."""
    try:
        branch = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    n = state.item_of(branch)          # feat/, imp/, fix/: a docs/12-x branch is no item's
    if not n:
        return ""
    item, held = {}, ""
    try:
        item = next((i for i in state.cached(root) if i.get("number") == n), None)
        if item is None:
            v = json.loads(quick(["issue", "view", str(n), "--repo", state.repo(root, quick),
                                  "--json", "title,body,assignees"]))
            spec = state.SPEC.search(v.get("body") or "")
            item = {"title": v["title"], "assignees": [a["login"] for a in v["assignees"]],
                    "spec": spec.group(1) if spec else None}
        who = item.get("assignees") or []
        held = "" if not who or state.me(root, run=cached_only, ttl=KEPT) in who else ", ".join(who)
    except (OSError, subprocess.TimeoutExpired, state.StateError, ValueError, KeyError, TypeError):
        item = item or {}
    line = f"Active item: #{n} {clip(item.get('title') or '')}".rstrip() + f" (branch {clip(branch)})."
    if item.get("spec"):
        line += f" Spec: {clip(item['spec'])}."
    if held:
        line += f" It is held by {clip(held)}: work on it only when the person says so."
    return line + f" Details: `pulse status {n}`."


def context(event, root, cfg, env):
    if cfg["mode"] == "off":
        return ""
    if cfg["mode"] is None:
        if event != "SessionStart":
            return ""
        return ("Pulse is installed but not active in this project. `/pulse` "
                "(in Codex `$pulse:pulse`) sets it up.")
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
    parts = [(HERE / "rules.md").read_text(encoding="utf-8").strip(), cli]
    try:                       # the login as the CLI kept it, never asked here (#111)
        login = state.me(root, run=cached_only, ttl=KEPT)
    except (OSError, state.StateError):
        login = ""
    person = state.who(root, login)
    if person:
        parts.append(f"Pulse: {clip(person)}.")
    try:                       # the auto switches as the CLI or the map last read them, never asked here (#124)
        parts.append(ready.printable(auto.said(auto.read(root, run=cached_only, ttl=KEPT), login)))
    except (OSError, state.StateError):
        pass
    item = active_item(root)
    if item:
        parts.append(item)
    return "\n\n".join(parts)


def beside(root, cfg, stdin_text, env):
    """In Herdr, the live map beside an interactive session that starts, resumes, or forks (#121 FR-01): pulse map
    --ensure apart, never waited for. Not after clear or compact, so a map closed with q stays closed; not for
    agents of pulse go, subagents, claude -p, or with PULSE_MAP=off. HERDR_ACTIVE_PANE_ID: a Herdr key command."""
    try:
        source = json.loads(stdin_text).get("source")
    except (ValueError, AttributeError):
        return
    if cfg["mode"] != "on" or source not in ("startup", "resume", "fork") or \
            not (env.get("HERDR_ENV") == "1" or env.get("HERDR_ACTIVE_PANE_ID")) or \
            auto.nested(env) or \
            env.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk-") or env.get("PULSE_MAP", "").lower() == "off":
        return
    subprocess.Popen([str(ROOT / "bin" / "pulse"), "map", "--ensure"], cwd=root, env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


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


def held_here(root, n, payload, memo):
    """Whether this session holds n as the board says now: its login is assigned and no mark stands before its
    own (state._lead); None when the read fails or no login is cached. One read of the item within 2 s per stop,
    shared by its reasons, and never the board cache, which may still name the old holder after a take
    (#99 FR-01, FR-02)."""
    if n not in memo:
        who = {"id": f"{'codex' if 'turn_id' in payload else 'claude'}:{payload.get('session_id') or ''}"}
        try:
            v = json.loads(quick(["issue", "view", str(n), "--repo", state.repo(root, quick),
                                  "--json", "assignees,comments"]))
            memo[n] = state.me(root, run=cached_only, ttl=KEPT) in [a["login"] for a in v["assignees"]] and \
                not state._lead(v, who)[1]
        except (OSError, subprocess.TimeoutExpired, state.StateError, ValueError, KeyError, TypeError):
            memo[n] = None
    return memo[n]


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


def unpushed_work(root, cfg, payload, memo=None):
    """Commits on the checked-out branch of an item this login holds, or its docs branch, that origin
    lacks: the session pushes before it ends, so the team sees the work and whoever takes the item
    over starts from it (#79). Local first; only then the holder, from one read of the item within 2 s
    (held_here), so a slow gh never costs this stop its other reasons and a read that fails asks for
    nothing. A session whose item an older claim holds, or a person took, pushes nothing (#77, #99 FR-01).
    A branch name is quoted as a shell reads it (#79 audit L-1)."""
    if payload.get("agent_id"):
        return ""
    try:
        branch = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=2).stdout.strip()
        docs = re.match(r"docs/(\d+)-", branch)
        n = state.item_of(branch) or (int(docs.group(1)) if docs else None)
        kept = n and [k for b, k in ready.unpushed(root, n, cfg["base_branch"] or config.default_branch(root))
                      if b == branch]
    except (OSError, subprocess.TimeoutExpired, state.StateError, ValueError):
        return ""
    if not kept or not held_here(root, n, payload, {} if memo is None else memo):
        return ""
    return (f"Pulse: {branch} has {kept[0]} commit{'s' if kept[0] != 1 else ''} only this clone has. Push "
            f"before you end: `git push -u origin {shlex.quote(branch)}`; the team sees the work on #{n}, and "
            "whoever takes it over starts from it.")


def stop_verdict(root, cfg, payload, env):
    """The reasons to go on before a session ends: code that no check ran for, and commits origin lacks. The one
    call of gh reads who holds the item (held_here), and only for unpushed commits."""
    # PULSE_HOLDER: an agent or gate session of pulse go, which runs the gates itself
    if platform(env) != "claude" or payload.get("stop_hook_active") or env.get("PULSE_HOLDER"):
        return ""
    path = payload.get("transcript_path")
    entries = read_transcript(path) if path else []
    reasons = [r for r in (untested_code(entries), unpushed_work(root, cfg, payload)) if r]
    return json.dumps({"decision": "block", "reason": " ".join(reasons)}) if reasons else ""


def _inside(root, cwd) -> bool:
    """Whether the command runs in this clone: a lever grant holds there only (#197)."""
    try:
        here, top = Path(cwd).resolve(), Path(root).resolve()
    except (TypeError, OSError, ValueError):
        return False
    return here == top or top in here.parents


def _pulse_on(place):
    """(root, config) of the project around place (None: this process's directory) where Pulse is on, else None."""
    root = config.find_root(Path(place) if place else None)
    if root is None:
        return None
    cfg = config.clone_config(root)                            # a worktree follows its main copy
    return (root, cfg) if cfg["mode"] == "on" else None


def map_panes(root):
    """The panes live maps of this clone run in, as mapstart keeps them in map-pane: nothing goes in there (FR-10
    of #121). Read without network; a sandbox that keeps .git read-only has its copy in the cache folder."""
    found = set()
    for d in {config.pulse_dir(root), state.cache_dir(root)}:
        try:
            found |= set(json.loads((d / "map-pane").read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            pass
    return found


def lever_guard(stdin_text, env):
    """PreToolUse: deny a call that pulls a person's lever (FEAT-03-01), in a project where Pulse is on: the one
    around this process, else around the session's directory, else CLAUDE_PROJECT_DIR (Claude Code sets it for
    hooks). It asks no network; a payload it cannot read, or a check that fails, errs toward the levers
    (FR-08), from the command alone: a directory or a description that names pulse is no lever."""
    try:
        try:
            said = json.loads(stdin_text)
        except ValueError:
            said = {}
        here = said.get("cwd") if isinstance(said, dict) and isinstance(said.get("cwd"), str) else None
        found = next(filter(None, (_pulse_on(p) for p in (None, here, env.get("CLAUDE_PROJECT_DIR")) if p != "")), None)
        if found is None:
            return ""
        root, cfg = found
        payload = json.loads(stdin_text)
        asked = _asking(payload)
        if asked:
            return _decide(root, payload, env, asked)
        # Claude Code names the command's directory; Codex its session's, the workdir stands in its rollout.
        cwd = (lambda: state.ran_in(payload) or None) if "turn_id" in payload else payload.get("cwd") or "."
        tool, given, panes = payload.get("tool_name") or "", payload.get("tool_input") or {}, map_panes(root)
        why = guard.verdict(tool, given, cfg["base_branch"], config.default_branch(root), cwd, panes)
        if why and "turn_id" not in payload and levers.session(env) and _inside(root, payload.get("cwd")) and not guard.verdict(
                tool, given, cfg["base_branch"], config.default_branch(root), cwd, panes, granted=True):
            grant = levers.allowed(root, env)        # the lever is one a grant opens (#197 FR-04)
            if grant:
                levers.use(root, grant, clip(str(given.get("command") or tool), 300), "guard", levers.session(env))
                return ""
            why = f"{why} Or {levers.HINT}."          # FR-01: how the session asks the person
    except Exception:
        try:
            payload = json.loads(stdin_text)
        except ValueError:     # not a payload at all: all it says
            text = stdin_text
        else:
            got = payload.get("tool_input") if isinstance(payload, dict) else None
            command = next((got[k] for k in ("command", "cmd") if k in got), None) if isinstance(got, dict) else None
            text = command if isinstance(command, str) else json.dumps(command)
        why = guard.REASON if guard.RISKY.search(text) else ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": why}}) if why else ""


def _asking(payload) -> str:
    """The scope of a plain `pulse levers allow <scope>` (Bash, the whole command), else ""."""
    given = payload.get("tool_input") if isinstance(payload, dict) else None
    command = given.get("command") if isinstance(given, dict) else None
    m = levers.ALLOW.fullmatch(command.strip()) if isinstance(command, str) and payload.get("tool_name") == "Bash" \
        else None
    return m.group(1) if m else ""


def _decide(root, payload, env, scope):
    """#197 FR-02: Claude Code's own dialog for an attended session, which neither the model nor a classifier
    answers; its tool use is noted, and only PostToolUse of it makes the grant. Codex is left to the CLI, which
    names the gap (FR-11); anyone else is denied (FR-06)."""
    if "turn_id" in payload:
        return ""
    sid, tool_use = levers.session(env), payload.get("tool_use_id")
    if not sid or not isinstance(tool_use, str) or not tool_use:
        why = levers.why_not(env) if not sid else "no tool use to bind the confirmation to"
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": f"pulse levers allow: {why}"}})
    levers.ask(root, tool_use, sid, scope)
    said = {"run": "until this pulse go run ends, or without a run until your next message",
            "session": "for this Claude Code session and its subagents",
            "always": "for every attended Claude Code session in this clone until you revoke it"}[scope]
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                              "permissionDecisionReason":
                                                  f"Pulse: let the agent pull your levers (approve, defer, resume, "
                                                  f"take over, merge, push to the base) {said}? Every use is logged; "
                                                  f"pulse levers off or the Pulse map ends it."}})


def lever_event(stdin_text, env):
    """PostToolUse of an asked `pulse levers allow` makes its grant; a prompt ends a run grant made without a
    run (#197 FR-02, FR-05). Errors stay silent: the grant is simply not made."""
    try:
        payload = json.loads(stdin_text)
        event = payload.get("hook_event_name")
        if event not in ("PostToolUse", "UserPromptSubmit"):
            return
        scope = _asking(payload) if event == "PostToolUse" else ""
        if event == "PostToolUse" and not scope:
            return
        found = _pulse_on(payload.get("cwd") if isinstance(payload.get("cwd"), str) else None)
        if found is None:
            return
        if scope:
            levers.confirm(found[0], payload.get("tool_use_id") or "", levers.session(env), scope)
        else:
            levers.prompted(found[0], env.get("CLAUDE_CODE_SESSION_ID"))
    except Exception:
        pass


def main(argv, stdin_text, env):
    if argv[:1] in (["presence"], ["guard"], ["session-start"], ["subagent-start"], ["stop"]):
        try:
            payload = json.loads(stdin_text)
            presence.record(payload, env)
            alive.kick(payload, env)       # a holding session's sign of life, detached, every 10 min (#195)
        except (ValueError, TypeError):
            pass
    if argv[:1] == ["presence"]:
        lever_event(stdin_text, env)
        return ""
    if argv[:1] == ["guard"]:
        return lever_guard(stdin_text, env)
    try:
        event = {"session-start": "SessionStart", "subagent-start": "SubagentStart",
                 "stop": "Stop"}.get(argv[0] if argv else "")
        root = config.find_root()
        if not event or root is None:
            return ""
        cfg = config.clone_config(root)
        if event == "Stop":
            return stop_verdict(root, cfg, json.loads(stdin_text), env) if cfg["mode"] == "on" else ""
        if event == "SessionStart":
            beside(root, cfg, stdin_text, env)
        text = context(event, root, cfg, env)
        if event == "SessionStart" and cfg["mode"] == "on":
            try:               # the evidence the map shows (#182); it never changes what the session gets
                payload = json.loads(stdin_text or "{}")
                settings.delivered(root, presence.harness(payload if isinstance(payload, dict) else {}, env), len(text))
            except Exception:
                pass
        return emit(event, text, env) if text else ""
    except Exception:          # a hook must never break the session
        return ""


if __name__ == "__main__":
    out = main(sys.argv[1:], sys.stdin.read() if not sys.stdin.isatty() else "", dict(os.environ))
    if out:
        sys.stdout.write(out)
