"""pulse map --ensure: a live map of this clone where the user works, once per clone (D-48).

Each live map notes its pid on a line of map.pid under the shared git dir while it runs, and in a
Herdr or tmux pane its pane in map-pane, which the lever guard keeps agents out of (#121 FR-10).
In Herdr --ensure opens the map beside the session's pane, one per tab and repository (#121).
Elsewhere it opens a map when no process has one of those pids and no map it opened is still
starting (map.command younger than 15 s): in tmux a pane beside; in VS Code the task "Pulse map"
runs it, so --ensure only names that task, where .vscode/tasks.json has it, and the command;
elsewhere one line names the command for a second terminal. It opens no window, and nothing
here starts pulse go: a person starts it in a terminal. Every line it prints goes to stderr, the
stdout of claim and new --draft stays theirs. PULSE_MAP=off switches it off; an agent of pulse go
opens none.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from pulse import config, go, setup, state


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


def panes(root: Path) -> dict:
    """{pane id: {tab, started_at, pid, label}}: the Herdr (w1:p2) and tmux (%3) panes live maps of this clone run
    in, or were opened for and start in; pid comes once the map runs, label where --ensure gave the pane one. A sandbox that keeps .git read-only reads the
    one a map outside it wrote there."""
    found = {}
    for path in (config.pulse_dir(root) / "map-pane", state.cache_dir(root) / "map-pane"):
        with contextlib.suppress(OSError, ValueError, TypeError):
            found.update(json.loads(path.read_text(encoding="utf-8")))
    return found


def _note_pane(root: Path, pane: str, entry) -> None:
    """Set the entry of pane in map-pane, or drop it (None)."""
    # ponytail: two maps that start or end at the same moment can lose an entry; a lost one leaves its pane
    # unguarded until its map starts again, which notes it anew; lock map-pane when that shows in practice
    known = panes(root)
    if entry is None:
        known.pop(pane, None)
    else:
        known[pane] = entry
    state._keep(state.cache_dir(root) / "map-pane", known)


def _herdr_bin(env) -> str:
    return env.get("HERDR_BIN_PATH") or "herdr"


@contextlib.contextmanager
def noted(root: Path):
    """While a live map runs: its pid on a line of map.pid, beside those of the clone's other live
    maps, and in a Herdr or tmux pane its pane in map-pane. map.main turns SIGTERM and SIGHUP into an
    end, so its line and its pane go with it, the file with the last map, and the label --ensure gave
    its Herdr pane (FR-03); a map killed outright leaves a pid no process has, which the next one drops.
    The caller sets end["code"] to the map's exit code. A map in Herdr that ends otherwise than with 0 (an
    error, a failed switch) keeps its pane's entry and label without its pid: the pane stays open with the
    reason, and the next --ensure starts the map in it again (#192)."""
    path, me = pid_file(root), os.getpid()
    pane = os.environ.get("HERDR_PANE_ID") or os.environ.get("TMUX_PANE")
    labelled = (panes(root).get(pane) or {}).get("label") if pane else None     # by --ensure, in Herdr

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
        if pane:
            _note_pane(root, pane, {**panes(root).get(pane, {"tab": os.environ.get("HERDR_TAB_ID"),
                                                            "started_at": time.time()}), "pid": me})
    except OSError:
        pass                   # the map runs all the same
    end = {"code": 0}
    try:
        yield end
    except BaseException:
        end["code"] = 1
        raise
    finally:
        kept = end["code"] != 0 and os.environ.get("HERDR_PANE_ID")      # q, Ctrl-C, a signal end with 0
        with contextlib.suppress(OSError):
            note()
            if pane:
                entry = {k: v for k, v in panes(root).get(pane, {}).items() if k != "pid"}
                _note_pane(root, pane, {**entry, "started_at": 0} if kept and entry else None)
        if labelled and os.environ.get("HERDR_PANE_ID") and not kept:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run([_herdr_bin(os.environ), "pane", "rename", pane, "--clear"], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=3)


STARTING = 10                  # seconds a map opened in Herdr may take to note its pid


def _shown(env, pane: str) -> str:
    """The last lines pane shows, in one printable line of 300 characters at most: why its map did not start,
    as far as the pane says."""
    try:
        out = subprocess.run([_herdr_bin(env), "pane", "read", pane, "--source", "recent-unwrapped", "--lines", "20"],
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    with contextlib.suppress(ValueError, KeyError, TypeError):
        out = json.loads(out)["result"]["read"]["text"]
    return config.printable(" | ".join([line.strip() for line in str(out).splitlines() if line.strip()][-3:]))[-300:]


def _herdr(root: Path, env, repo: str) -> str:
    """The map beside the session's Herdr pane, one per tab and repository (#121 FR-01 to FR-03), and the line
    that says so. Under a lock per tab: a pane of this repository's map (its label, or its entry in map-pane)
    whose map runs, or started less than STARTING s ago, is left be; one whose map is gone, as after a cold
    start, gets the map again; else a new pane to the right, the focus staying. Entry and label come before
    the map runs, so a session that starts at the same moment finds them and types into no pane. The pane's
    shell runs the map and closes only when it ends with exit 0 (q, Ctrl-C); else it keeps what the map said
    and a hint. "opened beside" comes once the map noted its pid, within STARTING s (#192)."""
    import fcntl                               # Herdr runs on macOS and Linux

    pane = env.get("HERDR_PANE_ID") or env.get("HERDR_ACTIVE_PANE_ID")
    label = f"pulse map {repo}"               # two repositories in one tab get two maps
    pulse = str(pulse_bin())
    # fish reads a backslash inside '...', and a control character can end the line typed into the pane
    if any(c == "\\" or not c.isprintable() for c in str(root) + pulse):
        return ("pulse map: no map beside: the path of this clone or of pulse has a backslash or a control "
                "character, which the pane's command line cannot carry; run pulse map in a terminal of its own")

    def call(*args):
        out = subprocess.run([_herdr_bin(env), *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             timeout=3, check=True).stdout
        return (json.loads(out) if out.strip() else {}).get("result") or {}
    tab = call("pane", "get", pane)["pane"]["tab_id"]        # a moved pane keeps its old HERDR_TAB_ID
    lock = state.cache_dir(root) / f"map-{re.sub(r'[^A-Za-z0-9.-]', '_', tab)}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        known = panes(root)
        mine = [p["pane_id"] for p in call("pane", "list").get("panes", [])
                if p.get("tab_id") == tab and (p.get("label") == label or p.get("pane_id") in known)]
        for p in mine:
            pid = (known.get(p) or {}).get("pid") or 0
            if pid > 0 and go._alive(pid) or not pid and time.time() - known.get(p, {}).get("started_at", 0) < STARTING:
                return "pulse map: runs beside"
        new = mine[0] if mine else call("pane", "split", "--pane", pane, "--direction", "right", "--no-focus",
                                        "--cwd", str(root))["pane"]["pane_id"]
        _note_pane(root, new, {"tab": tab, "started_at": time.time(), "label": label})
        call("pane", "rename", new, label)
        pulse = shlex.quote(pulse)
        hint = f"pulse map ended; the lines above say why. To start it again: {pulse} map"
        call("pane", "run", new, f"cd {shlex.quote(str(root))} && {pulse} map && exit || echo {shlex.quote(hint)}")
    end = time.monotonic() + STARTING          # outside the lock: a second session leaves the starting map be
    while time.monotonic() < end:
        pid = (panes(root).get(new) or {}).get("pid") or 0
        if pid > 0 and go._alive(pid):
            return "pulse map: opened beside"
        time.sleep(0.1)
    return f"pulse map: the map in {new} did not start: {_shown(env, new) or f'no pid within {STARTING} s'}"


def _repo(root: Path) -> str:
    """owner/name, else the folder of the clone: what the label of its map pane names."""
    try:
        return state.repo(root)
    except (state.StateError, OSError):
        return config.common_dir(root).parent.name


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
        if env.get("PULSE_MAP", "").lower() == "off":
            return 0
        if (env.get("HERDR_PANE_ID") or env.get("HERDR_ACTIVE_PANE_ID")) and \
                (env.get("HERDR_ENV") == "1" or env.get("HERDR_ACTIVE_PANE_ID")):
            try:                                   # one map per tab: a map elsewhere does not count here
                print(_herdr(root, env, _repo(root)), file=sys.stderr)
                return 0
            except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
                pass                               # Herdr did not answer: as in any other terminal
        pid = running(root)
        if pid:
            print(f"pulse map: the map of this clone runs (pid {pid})", file=sys.stderr)
            return 0
        script = state.cache_dir(root) / "map.command"   # what the tmux pane runs
        with contextlib.suppress(OSError):         # the map the last open wrote it for has no pid yet
            if time.time() - script.stat().st_mtime < 15:
                print("pulse map: the map of this clone is starting", file=sys.stderr)
                return 0
        here, pulse = shlex.quote(str(root)), shlex.quote(str(pulse_bin()))
        cmd = f"cd {here} && {pulse} map"
        if env.get("TERM_PROGRAM") == "vscode" or "vscode" in env.get("CLAUDE_CODE_ENTRYPOINT", "") \
                or env.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE") == "codex_vscode":
            try:                                   # the task, where /pulse wrote it at setup
                task = re.search(r'"label"\s*:\s*"Pulse map"',
                                 (root / ".vscode" / "tasks.json").read_text(errors="replace"))
            except OSError:
                task = None
            codex = env.get("CODEX_THREAD_ID") or env.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE")
            skill = "$pulse:pulse" if codex else "/pulse"    # the name the session calls it by
            print(f'pulse map: run the task "Pulse map" (Terminal > Run Task), or in a terminal panel: {cmd}'
                  if task else f'pulse map: in a terminal panel: {cmd} ({skill} adds the task "Pulse map")',
                  file=sys.stderr)
            return 0
        if env.get("TMUX"):
            try:
                script.parent.mkdir(parents=True, exist_ok=True)
                script.write_text(f"#!/bin/sh\ncd {here} && exec {pulse} map\n")
                script.chmod(0o755)
                split = subprocess.run(["tmux", "split-window", "-d", "-h", "-P", "-F", "#{pane_id}",
                                        shlex.quote(str(script))], cwd=root, stdin=subprocess.DEVNULL,
                                       capture_output=True, text=True, timeout=3)   # tmux hands its one word to sh
                if split.returncode == 0:
                    if split.stdout.strip():               # the guard keeps agents out of it (FR-10)
                        _note_pane(root, split.stdout.strip(), {"tab": None, "started_at": time.time()})
                    print("pulse map: opened in a tmux pane beside", file=sys.stderr)
                    return 0
            except (OSError, subprocess.SubprocessError):
                pass
        print(f"pulse map: run pulse map in a second terminal: {cmd}", file=sys.stderr)
    except Exception as e:
        print(f"pulse map: no map opened: {e}", file=sys.stderr)
    return 0
