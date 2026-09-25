"""pulse map --ensure: a live map of this clone where the user works, once per clone (D-48).

Each live map notes its pid on a line of map.pid under the shared git dir while it runs.
--ensure opens a map when no process has one of those pids and no map it opened is still
starting (map.command younger than 15 s): a tmux pane beside, a window of the terminal app on
macOS or Linux; in VS Code the task "Pulse map" runs it, so --ensure only names that task, where
.vscode/tasks.json has it, and the command. Every line it prints goes to stderr, the stdout of
claim and new --draft stays theirs. `map_autostart = false` in .pulse/config.toml or PULSE_MAP=off
switch it off; an agent of pulse go opens none. A Codex session whose hooks never reached the presence
log hears first that they wait for the person's trust: without them the map cannot show it.

runner() is the other way round: the live map starts pulse go when approved work waits (#44).
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from pulse import config, go, presence, setup, state

LINUX = ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm")
PAUSE = 60                     # seconds between two starts of pulse go from the maps of a clone
OFF = ("off", "0", "false", "no")                  # PULSE_GO values that switch the start off
HELD = ("failed", "limited", "stopped", "skipped")  # what the last run did not finish waits for a person


def pid_file(root: Path) -> Path:
    return state.cache_dir(root) / "map.pid"


def _pids(path: Path) -> list:
    """The pids a map.pid names, one line per live map of the clone; none when it cannot be read."""
    try:
        return [int(w) for w in path.read_text().split() if w.isdecimal()]
    except OSError:
        return []


def running(root: Path) -> int:
    """The pid of a live map of this clone, else 0; a pid no process has is no map. A sandbox that
    keeps .git read-only also reads the map.pid a map outside it wrote there."""
    # ponytail: a pid the system gave to another process since counts as a map; compare the
    # process start time with the file's when a stale file after a crash keeps a map away
    return next((pid for path in (pid_file(root), config.pulse_dir(root) / "map.pid") for pid in _pids(path)
                 if pid > 0 and go._alive(pid)), 0)


@contextlib.contextmanager
def noted(root: Path):
    """While a live map runs: its pid on a line of map.pid, beside those of the clone's other live
    maps. map.main turns SIGTERM and SIGHUP into an end, so its line goes with it, and the file with
    the last map; a map killed outright leaves a pid no process has, which the next one drops."""
    path, me = pid_file(root), os.getpid()

    def note(*mine):
        # ponytail: two maps of one clone that start or end at the same moment can lose a line;
        # lock map.pid when a third map opens that way in practice
        others = [pid for pid in _pids(path) if pid != me and go._alive(pid)]
        if others or mine:
            path.write_text("".join(f"{pid}\n" for pid in others + list(mine)))
        else:
            path.unlink()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        note(me)
    except OSError:
        pass                   # the map runs all the same
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            note()


def pulse_bin() -> Path:
    """The pulse the caller runs: the shim of pulse setup --cli when there is one, else this copy."""
    shim = Path.home() / ".local" / "bin" / "pulse"
    return shim if shim.exists() else setup.PULSE_BIN


def ensure(root: Path) -> int:
    """pulse map --ensure, and pulse go, claim, and new --draft as work starts: whatever goes wrong
    here is one line and exit 0, a map is never worth a failed command."""
    env = os.environ
    try:
        # the agents of pulse go carry PULSE_HOLDER: the run opened the map, they work in worktrees
        if env.get("PULSE_HOLDER"):
            return 0
        cfg = config.load(root)
        tid = env.get("CODEX_THREAD_ID")     # a Codex hook's session_id is its thread id (audit phase 4)
        if tid and cfg["mode"] == "on" and not presence.seen(root, tid):
            print("pulse: this Codex session reaches no Pulse hook: no light on the map, no heartbeat, "
                  "and no rules unless AGENTS.md brings them. Trust the pulse hooks (/hooks in the CLI, "
                  "then t; the Hooks page of the IDE extension's settings), then start a new chat; "
                  "Pulse installed from a clone has no hooks to trust", file=sys.stderr)
        if env.get("PULSE_MAP", "").lower() == "off" or not cfg["map_autostart"]:
            return 0
        pid = running(root)
        if pid:
            print(f"pulse map: the map of this clone runs (pid {pid})", file=sys.stderr)
            return 0
        script = state.cache_dir(root) / "map.command"   # .command: Terminal and iTerm run it
        with contextlib.suppress(OSError):         # the map the last open wrote it for has no pid yet
            if time.time() - script.stat().st_mtime < 15:
                print("pulse map: the map of this clone is starting", file=sys.stderr)
                return 0
        here, pulse = shlex.quote(str(root)), shlex.quote(str(pulse_bin()))
        cmd = f"cd {here} && {pulse} map"
        if env.get("TERM_PROGRAM") == "vscode" or "vscode" in env.get("CLAUDE_CODE_ENTRYPOINT", "") \
                or env.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE") == "codex_vscode":
            try:                                   # the task, where /pulse-setup wrote it
                task = re.search(r'"label"\s*:\s*"Pulse map"',
                                 (root / ".vscode" / "tasks.json").read_text(errors="replace"))
            except OSError:
                task = None
            codex = env.get("CODEX_THREAD_ID") or env.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE")
            skill = "$pulse:pulse-setup" if codex else "/pulse-setup"    # the name the session calls it by
            print(f'pulse map: run the task "Pulse map" (Terminal > Run Task), or in a terminal panel: {cmd}'
                  if task else f'pulse map: in a terminal panel: {cmd} ({skill} adds the task "Pulse map")',
                  file=sys.stderr)
            return 0
        how = where = None
        if env.get("TMUX"):
            how, where = ["tmux", "split-window", "-d", "-h"], "a tmux pane beside"
        elif sys.platform == "darwin" and env.get("TERM_PROGRAM"):
            app = "iTerm" if env["TERM_PROGRAM"] == "iTerm.app" else "Terminal"
            how, where = ["open", "-a", app], f"a new {app} window"
        elif sys.platform.startswith("linux") and (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
            term = next((t for t in LINUX if shutil.which(t)), None)
            if term:
                how, where = [term, "--" if term == "gnome-terminal" else "-e"], f"a new {term} window"
        if how:
            # ponytail: an opener that starts and then fails (no display, a refused window) says
            # nothing back; wait for its exit code when that happens in practice
            try:
                script.parent.mkdir(parents=True, exist_ok=True)
                script.write_text(f"#!/bin/sh\ncd {here} && exec {pulse} map\n")
                script.chmod(0o755)
                word = shlex.quote(str(script)) if how[0] == "tmux" else str(script)   # tmux hands it to sh
                subprocess.Popen(how + [word], cwd=root, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                print(f"pulse map: opened in {where}", file=sys.stderr)
                return 0
            except OSError:
                pass
        print(f"pulse map: in a terminal of its own: {cmd}", file=sys.stderr)
    except Exception as e:
        print(f"pulse map: no map opened: {e}", file=sys.stderr)
    return 0


def start_go(root: Path, extra=(), by: str = "pulse go --detach") -> tuple:
    """pulse go in a session of its own, apart from the terminal, chat, or map that starts it; its
    output goes to run.log (F2.07), under a line that says who started it. -> (the process, run.log,
    where this start's output begins)"""
    log = config.pulse_dir(root) / "go" / "run.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as out:
        out.write(f"--- {by}, {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        out.flush()
        since = out.tell()
        p = subprocess.Popen([str(setup.PULSE_BIN), "go", *extra], cwd=root, stdin=subprocess.DEVNULL,
                             stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    return p, log, since


def _on_origin(root: Path, ref: str):
    """The .pulse/config.toml of exactly this ref, a full name under refs/remotes/origin/: git show-ref
    --verify never falls back to a tag or a branch of that name. None when there is none."""
    if not ref.startswith("refs/remotes/origin/") or ".." in ref or not re.fullmatch(r"[\w./-]+", ref):
        return None
    out = subprocess.run(["git", "-C", str(root), "show-ref", "--verify", "--hash", ref],
                         capture_output=True, text=True, timeout=5)
    sha = out.stdout.strip()
    if out.returncode or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return None
    out = subprocess.run(["git", "-C", str(root), "show", f"{sha}:.pulse/config.toml"], capture_output=True, timeout=5)
    return out.stdout if out.returncode == 0 else None


def trusted(root: Path) -> bool:
    """The config in the working tree is, byte for byte, the one origin holds on its default branch
    (refs/remotes/origin/HEAD), or on the base branch that one names. The working tree names no ref:
    checking out someone's branch, even one pushed to origin, must never run the verify or agents its
    config names (audit of #44, H-1 and H-2)."""
    try:
        here = (root / ".pulse" / "config.toml").read_bytes()
        head = subprocess.run(["git", "-C", str(root), "symbolic-ref", "refs/remotes/origin/HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except OSError:
        return False
    default = _on_origin(root, head)
    if default is None:
        return False
    if here == default:
        return True
    base = config._parse(default.decode("utf-8", "replace")).get("base_branch")
    # a plain branch name only: "origin/x", "remotes/...", "heads/..." would name a branch anyone with push
    # access can create under refs/remotes/origin/ (audit of #44, L-1)
    return isinstance(base, str) and base.split("/")[0] not in ("origin", "remotes", "heads", "tags", "refs") \
        and _on_origin(root, f"refs/remotes/origin/{base}") == here


def runner(root: Path, vm: dict, env=os.environ) -> str:
    """The live map starts pulse go (#44) when approved work waits and no run of this clone lives: a
    build that starts next, or an approved item nobody holds that waits for its PLAN. What the last run
    did not finish (failed, at a usage limit, stopped, a claim refused) waits for a person; so does
    every start after a run a person stopped or one that ended before its report, until pulse go
    runs by hand. It starts only with the config origin holds (trusted), and a minute passes between
    two starts. `go_autostart = false` or PULSE_GO=off switch it off. -> the line the map shows, or
    ''; whatever goes wrong is that line, the map runs on."""
    # ponytail: a draft PR with new commits (pulse go takes it up) starts no run; the next run does
    try:
        cfg = config.load(root)
        if env.get("PULSE_GO", "").strip().lower() in OFF or cfg["mode"] != "on" \
                or cfg["go_autostart"] is not True or vm.get("error") or go.running(root):
            return ""
        last = go.last_run(root) or {}
        stopped = (last.get("run") or {}).get("stopped")
        if stopped:
            return f"the last pulse go run was stopped ({stopped}): the map starts none until pulse go runs by hand"
        ramp = vm["ramp"]
        work = {i["number"] for i in ramp["next"]} | {r["number"] for r in ramp["rows"]
                                                      if r["stage"] == "needs a plan" and not r["assignees"]}
        held = work & {int(n) for n, r in (last.get("items") or {}).items() if r.get("result") in HELD}
        work -= held
        if not work:
            return (f"{', '.join(f'#{n}' for n in sorted(held))} wait for you: the last pulse go run did not "
                    "finish them (pulse show <n>)") if held else ""
        if not cfg["verify"]:
            return 'pulse go waits for a test command: pulse setup --verify "<the command that runs your tests>"'
        if not trusted(root):
            if subprocess.run(["git", "-C", str(root), "symbolic-ref", "-q", "refs/remotes/origin/HEAD"],
                              capture_output=True, timeout=5).returncode:
                return "pulse go starts by hand here: git knows no origin/HEAD yet (git remote set-head origin -a)"
            return ("pulse go starts by hand here: .pulse/config.toml differs from the one on origin's "
                    "default branch or the base it names, and the map runs no command a checked-out branch brings")
        stamp, log = state.cache_dir(root) / "go.autostart", config.pulse_dir(root) / "go" / "run.log"
        rep = config.pulse_dir(root) / "go" / "report.json"
        names = ", ".join(f"#{n}" for n in sorted(work))
        with contextlib.suppress(OSError, ValueError):
            if time.time() - stamp.stat().st_mtime < PAUSE:
                return ""
            if not rep.is_file() or rep.stat().st_mtime < stamp.stat().st_mtime:
                return f"pulse go ended before it wrote its report ({log}): the map starts none until it runs by hand"
            # the map counts slots as the ramp does, pulse go as its agents allow: the same items a run
            # left alone start no second one, a changed ramp (an approval, a slot come free) does
            tried = set(json.loads(stamp.read_text(encoding="utf-8") or "{}").get("work") or ())
            if tried == work and not tried & {int(n) for n in last.get("items") or {}}:
                return f"the last pulse go run started nothing for {names}: the map starts it again when the ramp changes"
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(json.dumps({"work": sorted(work)}), encoding="utf-8")
        # ponytail: a checkout between trusted() and the run's own config read (under a second) still
        # reaches the run; hand the checked bytes' hash to go.run if that window ever matters
        p, log, _ = start_go(root, by="pulse go started by the live map")
        return f"pulse go started (pid {p.pid}) for {names}; log {log}"
    except Exception as e:
        return f"pulse go not started: {e}"
