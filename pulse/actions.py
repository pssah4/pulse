"""Durable local person intent. Only confirmed shared receipts change team state.

CLI and map check the person source before submit. The protected cache is the
trust boundary; a queued approval itself is never an integration permission.
"""
from __future__ import annotations

import fcntl
import functools
import json
import os
import sqlite3
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from pulse import config
from pulse.state import StateError

KINDS = {"defer", "resume", "approve", "revoke", "handoff", "stopped", "policy"}   # an older Pulse rejects any other
STATUSES = {"queued", "syncing", "confirmed", "conflict", "error"}
ATTEMPTS = 5
DATABASE = "outbox.sqlite"


@functools.lru_cache(maxsize=128)
def _location(root, cache):
    # Cache the shared-git lookup for linked worktrees. Never read project config.
    path = config.evidence_dir(root) / "actions"
    common = config.common_dir(root)
    if not path.is_absolute() or ".." in path.parts or any(
            path == parent or parent in path.parents for parent in (root, common, common.parent)):
        raise StateError("action outbox must be outside the worktree and shared git directory")
    return path


def _private(fd, directory=False):
    info = os.fstat(fd)
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 or \
            not directory and info.st_nlink != 1:
        raise StateError("unsafe action outbox ownership, permissions or link")


@contextmanager
def _directory(root):
    path = _location(Path(root).resolve(), os.environ.get("XDG_CACHE_HOME", ""))
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        # Walk with no-follow at every component, including custom cache parents.
        for index, part in enumerate(path.parts[1:]):
            try:
                os.mkdir(part, 0o700, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            if index >= len(path.parts) - 5:
                _private(directory, directory=True)
        yield path, directory
    except (OSError, sqlite3.Error) as error:
        raise StateError("action outbox unavailable (" + type(error).__name__ + ")") from None
    finally:
        os.close(directory)


def _file(directory, name, create=True):
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(name, flags | (os.O_CREAT | os.O_EXCL if create else 0), 0o600, dir_fd=directory)
    except FileExistsError:
        if not create:
            raise
        fd = os.open(name, flags, dir_fd=directory)
    try:
        if not create and os.fstat(fd).st_nlink == 0:
            # another command's transaction ended and SQLite deleted its journal after our open (#189)
            raise FileNotFoundError(name)
        _private(fd)
    except BaseException:
        os.close(fd)
        raise
    return fd


@contextmanager
def _database(root):
    with _directory(root) as (path, directory):
        os.close(_file(directory, DATABASE))
        for suffix in ("-journal", "-wal", "-shm"):
            try:
                os.close(_file(directory, DATABASE + suffix, create=False))
            except FileNotFoundError:
                pass
        # another command's short transaction is waited for, well below a hook's 5 s limit (#204)
        db = sqlite3.connect((path / DATABASE).as_uri() + "?mode=rw", uri=True, timeout=1)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA trusted_schema=OFF")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise StateError("unsupported action outbox version")
            db.execute("""CREATE TABLE IF NOT EXISTS actions (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                item INTEGER NOT NULL, kind TEXT NOT NULL, expected TEXT NOT NULL,
                payload TEXT NOT NULL, predecessor TEXT, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, next_due REAL NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '', receipt TEXT NOT NULL DEFAULT '{}')""")
            db.execute("CREATE INDEX IF NOT EXISTS actions_item ON actions(item,seq)")
            db.execute("""CREATE TABLE IF NOT EXISTS claim_receipts (
                session TEXT NOT NULL, item INTEGER NOT NULL, operation TEXT NOT NULL,
                PRIMARY KEY(session,item))""")
            # failures pulse go could not send (#209): a table of their own, which an older Pulse never reads
            db.execute("""CREATE TABLE IF NOT EXISTS failures (
                item INTEGER PRIMARY KEY, id TEXT NOT NULL, operation TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, next_due REAL NOT NULL DEFAULT 0)""")
            if version == 0:                  # a write: a reader that writes it waits for every other writer (#204)
                db.execute("PRAGMA user_version=1")
            with db:
                yield db
        finally:
            db.close()


def claim_receipt(root, session, item, operation=..., previous=...):
    """Read or compare-and-swap one locally acquired generation; no remote inference."""
    with _database(root) as db:
        if operation is not ...:
            db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT operation FROM claim_receipts WHERE session=? AND item=?",
                         (session, item)).fetchone()
        try:
            saved = json.loads(row["operation"]) if row else None
            if row and not isinstance(saved, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise StateError("invalid local claim receipt") from None
        if operation is ... or saved != previous:
            return saved
        if operation is None:
            db.execute("DELETE FROM claim_receipts WHERE session=? AND item=?", (session, item))
        else:
            db.execute("INSERT OR REPLACE INTO claim_receipts VALUES (?,?,?)",
                       (session, item, json.dumps(operation, sort_keys=True, allow_nan=False)))
        return operation


def _decode(saved):
    try:
        entry = dict(saved)
        entry["payload"], entry["receipt"] = json.loads(entry["payload"]), json.loads(entry["receipt"])
        if entry["kind"] not in KINDS or entry["status"] not in STATUSES or \
                not isinstance(entry["payload"], dict) or not isinstance(entry["receipt"], dict):
            raise ValueError()
        return entry
    except (ValueError, TypeError, KeyError):
        raise StateError("invalid action outbox row") from None


def submit(root, item, kind, payload, expected):
    """Commit locally before returning. No network, board reads or worker launch.

    An unresolved preceding local operation binds causal order. Its confirmed
    item revision becomes this operation's expectation, never a snapshot SHA.
    """
    expected = "" if expected is None else expected
    if type(item) is not int or not 0 <= item < 2 ** 63 or (item == 0) != (kind == "policy") or not isinstance(kind, str) or \
            kind not in KINDS or not isinstance(payload, dict) or \
            not isinstance(expected, str) or len(expected) > 128:
        raise StateError("invalid local action")
    try:
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        if len(encoded) > 65536:
            raise ValueError()
    except (ValueError, TypeError):
        raise StateError("invalid local action payload") from None
    ident = uuid.uuid4().hex
    with _database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT id,status FROM actions WHERE item=? ORDER BY seq DESC LIMIT 1",
                              (item,)).fetchone()
        after = previous["id"] if previous and previous["status"] in {"queued", "syncing", "error"} else None
        if kind == "stopped":
            entries = [_decode(row) for row in db.execute("SELECT * FROM actions WHERE item=? ORDER BY seq", (item,))]
            resumed = max((row["seq"] for row in entries if row["kind"] == "resume" and
                           row["status"] == "confirmed"), default=0)
            pause = next((row for row in entries if row["seq"] > resumed and row["kind"] == "defer" and
                          row["status"] != "conflict"), None)
            after = pause["id"] if pause else None
            if after:
                # A factual stop must precede a resume already accepted locally.
                # Only unsent intent moves; delivered conflicts remain visible.
                db.execute("UPDATE actions SET predecessor=? WHERE predecessor=? AND status='queued' AND attempts=0",
                           (ident, after))
        db.execute("INSERT INTO actions(id,item,kind,expected,payload,predecessor,status) VALUES(?,?,?,?,?,?,?)",
                   (ident, item, kind, expected, encoded, after, "queued"))
        accepted = _decode(db.execute("SELECT * FROM actions WHERE id=?", (ident,)).fetchone())
    return accepted


def pending(root):
    """Ordered local views, including terminal errors/conflicts and confirmations.

    Confirmed entries remain for local hold history and operation receipts.
    Callers must distinguish these views from the authoritative shared state.
    """
    with _database(root) as db:
        return [_decode(saved) for saved in db.execute("SELECT * FROM actions ORDER BY seq")]


def held(root, item):
    """A local defer stops starts immediately; only confirmed later resume clears it."""
    hold = False
    for entry in pending(root):
        if entry["item"] == item:
            if entry["kind"] == "defer":
                hold = True
            elif entry["kind"] == "resume" and entry["status"] == "confirmed":
                hold = False
    return hold


def integration_held(root, item):
    """Unsynced revocation blocks integration locally; newer confirmed approval clears it."""
    if held(root, item):
        return True
    entries = [row for row in pending(root) if row["item"] == item]
    approved = max((row["seq"] for row in entries if row["kind"] == "approve" and
                    row["status"] == "confirmed"), default=0)
    return any(row["seq"] > approved and row["kind"] == "revoke" and row["status"] != "confirmed"
               for row in entries)


def keep_failure(root, operation):
    """Keep a failure pulse go could not send (#209), one per item, its operation as it was: sent again with the same
    id, it is found on the board when only the answer of its push got lost."""
    with _database(root) as db:
        db.execute("INSERT OR REPLACE INTO failures(item,id,operation) VALUES(?,?,?)",
                   (operation["item"], operation["id"], json.dumps(operation, sort_keys=True, allow_nan=False)))


def failures(root):
    """The failures this clone keeps until the board has them: [{item, id, operation, attempts, next_due}]."""
    with _database(root) as db:
        rows = db.execute("SELECT * FROM failures ORDER BY item").fetchall()
    out = []
    for row in rows:
        try:
            out.append({**dict(row), "operation": json.loads(row["operation"])})
        except ValueError:
            continue           # a row that is no operation sends nothing
    return out


def retry_failures(root):
    """Every kept failure is due again: each pulse go run sends them anew, until the board has them."""
    with _database(root) as db:
        return db.execute("UPDATE failures SET attempts=0,next_due=0").rowcount


def _send_failures(root, send, clock):
    """Send each kept failure that is due; its row goes once send says the board has it or its claim moved on. A
    failed try waits as an action's does. -> how many it tried."""
    tried = 0
    for row in failures(root):
        if row["attempts"] >= ATTEMPTS or row["next_due"] > clock():
            continue
        tried += 1
        try:
            done = send(root, row["operation"])
        except (StateError, OSError, ValueError, TypeError, KeyError):
            done = False
        with _database(root) as db:
            if done:
                db.execute("DELETE FROM failures WHERE item=? AND id=?", (row["item"], row["id"]))
            else:
                db.execute("UPDATE failures SET attempts=attempts+1,next_due=? WHERE item=? AND id=?",
                           (clock() + min(2 ** (row["attempts"] + 1), 8), row["item"], row["id"]))
    return tried


def _send(root, operation):
    from pulse import shared
    return shared.send_failure(root, operation)


def retry(root, ident):
    """Explicit retry of a retained transport error; conflicts need new observed intent."""
    with _database(root) as db:
        return bool(db.execute("UPDATE actions SET status='queued',attempts=0,next_due=0,error='' "
                               "WHERE id=? AND status='error'", (ident,)).rowcount)


@contextmanager
def _lock(root):
    with _directory(root) as (_, directory):
        fd = _file(directory, "worker.lock")
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield None
            else:
                yield fd
        finally:
            # An inherited descriptor keeps the lock until the child closes it.
            os.close(fd)


def _transport(root, operation):
    from pulse import state
    adapter = getattr(state, "sync_action", None)
    if adapter is None:
        raise StateError("authenticated action transport is unavailable")
    return adapter(root, operation)


def _recover(root):
    # Only the holder of the process lock may recover a killed worker's row.
    with _database(root) as db:
        db.execute("UPDATE actions SET status='queued',next_due=0,attempts=MIN(attempts,?) "
                   "WHERE status='syncing'", (ATTEMPTS - 1,))


def _eligible(entries):
    by_id = {entry["id"]: entry for entry in entries}
    return [entry for entry in entries if entry["status"] in {"queued", "error"} and
            entry["attempts"] < ATTEMPTS and (not entry["predecessor"] or
            by_id.get(entry["predecessor"], {}).get("status") == "confirmed")]


def _sync(root, transport, clock):
    with _database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        entries = [_decode(saved) for saved in db.execute("SELECT * FROM actions ORDER BY seq")]
        by_id = {entry["id"]: entry for entry in entries}
        for entry in entries:
            if entry["status"] in {"queued", "error"} and \
                    by_id.get(entry["predecessor"], {}).get("status") == "conflict":
                entry["status"] = "conflict"
                db.execute("UPDATE actions SET status='conflict',error=? WHERE id=?",
                           ("Preceding local action conflicted; refresh before a new action.", entry["id"]))
        selected = next((entry for entry in _eligible(entries) if entry["next_due"] <= clock()), None)
        if selected is None:
            return 0
        if selected["predecessor"]:
            previous = next(entry for entry in entries if entry["id"] == selected["predecessor"])
            selected["expected"] = previous["receipt"]["data"]["revision"]
        db.execute("UPDATE actions SET status='syncing',attempts=attempts+1,expected=? WHERE id=?",
                   (selected["expected"], selected["id"]))
    operation = {key: selected[key] for key in ("id", "item", "kind", "expected", "payload")}
    try:
        receipt = transport(root, operation)
        status = receipt.get("status") if isinstance(receipt, dict) else None
        revision = (receipt.get("data") or {}).get("revision") if isinstance(receipt, dict) else None
        if status not in {"confirmed", "conflict"} or status == "confirmed" and not isinstance(revision, str):
            raise StateError("invalid shared action receipt")
        # The error display never persists transport text, which may contain credentials.
        error, due = ("Shared item changed; refresh before a new action." if status == "conflict" else ""), 0
        # when the result came: the map lets a confirmation go after two minutes (#215)
        saved_receipt = json.dumps({**{key: value for key, value in receipt.items() if key != "error"},
                                    "at": clock()}, allow_nan=False)
    except (StateError, OSError, ValueError, TypeError, KeyError):
        status, error = "error", "Action sync failed; retry pending."
        due = clock() + min(2 ** selected["attempts"], 8)
        saved_receipt = "{}"
        if selected["attempts"] + 1 >= ATTEMPTS:
            error = "Action sync failed; retry limit reached. Retry explicitly."
    with _database(root) as db:
        db.execute("UPDATE actions SET status=?,error=?,next_due=?,receipt=? WHERE id=?",
                   (status, error, due, saved_receipt, selected["id"]))
    return 1


def sync_once(root, transport=None, clock=time.time):
    """Deliver one due operation. A competing worker returns zero without recovery."""
    with _lock(root) as lock:
        if lock is None:
            return 0
        _recover(root)
        return _sync(root, transport or _transport, clock)


def _drain(root, transport, clock, sleep, send=_send):
    _recover(root)
    count = 0
    while True:
        attempted = _sync(root, transport, clock) + _send_failures(root, send, clock)
        count += attempted
        if not attempted:
            ready = _eligible(pending(root)) + [row for row in failures(root) if row["attempts"] < ATTEMPTS]
            if not ready:
                return count
            sleep(max(0, min(entry["next_due"] for entry in ready) - clock()))


def drain(root, transport=None, clock=time.time, sleep=time.sleep, send=None):
    """Finish available local intent and kept failures with at most five transport attempts per row."""
    with _lock(root) as lock:
        return 0 if lock is None else _drain(root, transport or _transport, clock, sleep, send or _send)


def start(root):
    """Start one detached non-agent worker, inheriting its already acquired lock."""
    with _lock(root) as lock:
        if lock is None:
            return False
        entries = pending(root)
        if not _eligible(entries) and not any(entry["status"] == "syncing" for entry in entries) and \
                not any(row["attempts"] < ATTEMPTS for row in failures(root)):
            return False
        try:
            subprocess.Popen([sys.executable, "-m", "pulse.actions", str(Path(root).resolve()), str(lock)],
                             cwd=Path(__file__).resolve().parents[1], pass_fds=(lock,), start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            raise StateError("action worker could not start; local intent is retained") from None
    return True


def _main():
    root, inherited = Path(sys.argv[1]), int(sys.argv[2])
    try:
        with _directory(root) as (_, directory):
            saved = os.stat("worker.lock", dir_fd=directory, follow_symlinks=False)
            opened = os.fstat(inherited)
            _private(inherited)
            if (saved.st_dev, saved.st_ino) != (opened.st_dev, opened.st_ino):
                raise StateError("invalid action worker lock")
            fcntl.flock(inherited, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _drain(root, _transport, time.time, time.sleep)
    finally:
        os.close(inherited)
    # Covers submission just before this worker released its lock: a simultaneous
    # start saw the old worker, so hand the newly queued work to its successor.
    start(root)


if __name__ == "__main__":
    _main()
