"""pulse map --ensure: a live map of this clone where the user works, once per clone (D-48).

Each live map notes its pid on a line of map.pid under the shared git dir while it runs.
--ensure opens a map when no process has one of those pids and no map it opened is still
starting (map.command younger than 15 s): a tmux pane beside, a window of the terminal app on
macOS or Linux; in VS Code the task "Pulse map" runs it, so --ensure only names that task, where
.vscode/tasks.json has it, and the command. Every line it prints goes to stderr, the stdout of
claim and new --draft stays theirs. `map_autostart = false` in .pulse/config.toml or PULSE_MAP=off
switch it off; an agent of pulse go opens none.
"""
from __future__ import annotations

import contextlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from pulse import config, go, setup, state

LINUX = ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm")


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
        if env.get("PULSE_MAP", "").lower() == "off" or env.get("PULSE_HOLDER") \
                or not config.load(root)["map_autostart"]:
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
