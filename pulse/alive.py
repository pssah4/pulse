"""Signs of life of a session that holds an item by hand (#195, ADR-10).

One comment `<!-- pulse:beat {...} -->` per holding session on the item's issue, edited in place: on a claim, on a
phase change, and from the hook at most every SILENT / 3 per session through a detached `python3 -m pulse.alive`.
The shared state stays free of heartbeats. A run of pulse go keeps its own (D-43) and writes none.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pulse import state

BEAT = re.compile(r"<!-- pulse:beat (\{.*?\}) -->")
UTC = "%Y-%m-%dT%H:%M:%SZ"
STAMP = re.compile(r"(20[2-9][0-9])-([01][0-9])-([0-3][0-9])T([0-2][0-9]):([0-5][0-9]):([0-5][0-9])Z")   # 2020-2099
PHASE = re.compile(r"[a-z][a-z -]{0,39}")      # what a phase may say: pulse's words, never a control or surrogate
MOST = 1024                     # characters of a comment a beat reads: a beat is small, anyone may comment (M-1)
AHEAD = 5 * 60                  # seconds a writer's clock may run ahead; a beat further ahead proves nothing (L-2)
EVERY = 10 * 60                 # SILENT / 3 of the map: a working session never looks silent there
HERE = Path(__file__).resolve().parent.parent


def _at(beat):
    """Seconds since the epoch of a beat's UTC time, by arithmetic alone; None for anything else."""
    m = STAMP.fullmatch(beat) if isinstance(beat, str) else None
    if not m:
        return None
    try:
        time.strptime(beat, UTC)        # a real date: no 2026-02-30
    except ValueError:
        return None
    return calendar.timegm(tuple(map(int, m.groups())))


def said(comment: dict):
    """The beat a comment holds, {session, phase, beat}; None for any other comment."""
    m = BEAT.match((comment.get("body") or "")[:MOST])
    try:
        data = json.loads(m.group(1)) if m else None
        valid = isinstance(data.get("session"), str) and _at(data.get("beat")) is not None
    except (ValueError, TypeError, AttributeError, RecursionError):
        return None
    return data if valid else None


def latest(comments: list, claim: dict):
    """(phase, at) of the newest beat the claim's own account wrote for its session; None without one. A beat of
    another login proves nothing, whatever session it names, and is never parsed. A beat from a clock ahead counts
    as now, one more than AHEAD ahead not at all; a phase other than plain words counts as none."""
    now, found = time.time(), []
    for c in comments:
        if not claim.get("actor") or (c.get("author") or c.get("user") or {}).get("login") != claim["actor"]:
            continue
        data = said(c)
        at = _at(data["beat"]) if data else None
        if at is not None and data["session"] == claim.get("session") and at <= now + AHEAD:
            phase = data.get("phase")
            found.append((min(at, now), phase if isinstance(phase, str) and PHASE.fullmatch(phase) else None))
    if not found:
        return None
    at, phase = max(found, key=lambda f: f[0])
    return phase, time.strftime(UTC, time.gmtime(at))


def write(root, repo_name: str, n: int, who: dict, phase, run=None) -> bool:
    """Leave or renew this session's beat on #n; False when GitHub took none. A beat is never worth a failed
    command, so nothing here raises."""
    run = run or state.gh
    try:
        login, at = state.me(root, run=run), state._utc()
        body = (f"<!-- pulse:beat {json.dumps({'session': who['id'], 'phase': phase, 'beat': at})} -->\n"
                f"Sign of life from {state._name({'id': who['id'], 'mine': True, 'author': '', 'at': ''})}"
                f"{': ' + phase if phase else ''}, as of {at[11:16]} UTC.")
        own = [c for c in state.pages(run, f"repos/{repo_name}/issues/{n}/comments?per_page=100")
               if (c.get("user") or {}).get("login") == login and (said(c) or {}).get("session") == who["id"]]
        if own:
            run(["api", "-X", "PATCH", f"repos/{repo_name}/issues/comments/{own[-1]['id']}", "-f", "body=" + body])
        else:
            run(["api", "-X", "POST", f"repos/{repo_name}/issues/{n}/comments", "-f", "body=" + body])
        return True
    except Exception:
        return False


def kick(payload: dict, env: dict) -> bool:
    """From the hook, on every tool call: start main detached at most every EVERY seconds per session, and only
    for a session that claimed here (its local claim receipts). Never for an agent of pulse go; never raises."""
    try:
        session = payload.get("session_id")
        if env.get("PULSE_HOLDER") or not isinstance(session, str):
            return False
        from pulse import presence
        if not presence.IDENT.fullmatch(session):
            return False
        who = f"{presence.harness(payload, env)}:{session}"
        # ponytail: one stamp per session, whatever clone it works in; a session in two clones beats for the
        # one its last due call names, key the stamp by clone too if that matters
        stamp = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pulse" / "alive" / \
            hashlib.sha256(who.encode()).hexdigest()[:32]
        now = time.time()
        try:
            seen = os.stat(stamp)
        except FileNotFoundError:
            seen = None
        if seen is not None:
            if now - seen.st_mtime < EVERY:
                return False
            old = stamp.with_name(f".{stamp.name}.{os.getpid()}.{os.urandom(4).hex()}")
            os.rename(stamp, old)           # of several hooks at once, one takes the turn; the others fail here
            taken = os.stat(old)
            if (taken.st_ino, taken.st_dev) != (seen.st_ino, seen.st_dev):
                os.rename(old, stamp)       # or here: that was the fresh stamp of the hook that took this turn
                return False
            os.unlink(old)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(stamp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))     # or here
        os.utime(stamp, (now, now))
        where = presence._location(payload.get("cwd") or ".", env)       # a clone without Pulse: once per turn
        if where is None:
            return False
        from pulse import actions
        # the checkout of the shared git dir names the same outbox as any worktree, without a git process per call
        with actions._database(where[2].parent.parent.parent) as db:
            if not db.execute("SELECT 1 FROM claim_receipts WHERE session=? LIMIT 1", (who,)).fetchone():
                return False
        subprocess.Popen([sys.executable, "-m", "pulse.alive", str(where[0]), who], cwd=str(HERE),
                         start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def main(argv: list) -> int:
    """The detached half of kick: a beat for every item this session still holds in the shared state."""
    from pulse import shared
    where, who = argv
    root = Path(where)
    repo_name, login = state.repo(root, run=state.gh), state.me(root, run=state.gh)
    for number, item in shared.read(root)[1]["items"].items():
        claim = item.get("claim") or {}
        if claim.get("session") == who and claim.get("actor") == login and not item.get("hold"):
            write(root, repo_name, int(number), {"id": who}, (item.get("work") or {}).get("phase"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception:
        raise SystemExit(1)
