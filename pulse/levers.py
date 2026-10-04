"""Lever grants (FEAT-03-05, ADR-13): a person lets an attended Claude Code session pull their levers.

A grant needs Claude Code's own dialog. The guard answers the plain command `pulse levers allow <scope>` with
"ask" and notes its tool use; the CLI, which runs only after the person agreed, notes a request from the
session's own environment; PostToolUse of that tool use turns both into the grant. Grants live in the local
outbox outside the clone; nothing in the repository, the config or the environment grants anything (FR-07).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager

from pulse import actions, auto, state

SCOPES = ("run", "session", "always")
GRANTABLE = {"approve", "approve-plan", "revoke", "handoff", "retry", "defer", "resume", "discard", "delete",
             "auto", "claim --take", "release --take"}
ALLOW = re.compile(r"pulse[ \t]+levers[ \t]+allow[ \t]+(run|session|always)")    # the whole command, alone
HINT = "ask the person once to grant their levers: pulse levers allow run|session|always"
ASK = 600                      # seconds the dialog of a request may stay open
KEEP = 200                     # uses the log keeps
IDENT = re.compile(r"[\w.:-]{1,160}\Z", re.ASCII)
TABLES = (
    "CREATE TABLE IF NOT EXISTS lever_grants (id TEXT PRIMARY KEY, scope TEXT NOT NULL, session TEXT NOT NULL, "
    "run TEXT NOT NULL, by TEXT NOT NULL, at REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS lever_asks (tool_use TEXT PRIMARY KEY, session TEXT NOT NULL, scope TEXT NOT NULL, "
    "at REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS lever_requests (session TEXT NOT NULL, scope TEXT NOT NULL, run TEXT NOT NULL, "
    "at REAL NOT NULL, PRIMARY KEY(session, scope))",
    "CREATE TABLE IF NOT EXISTS lever_uses (at REAL NOT NULL, session TEXT NOT NULL, scope TEXT NOT NULL, "
    "grant_id TEXT NOT NULL, by TEXT NOT NULL, lever TEXT NOT NULL, source TEXT NOT NULL)")


def session(env) -> str | None:
    """The attended Claude Code session a grant can cover, else None: no runner agent, no Codex thread
    (no dialog the model cannot answer, and no way to tell an attended one apart, FR-11), no unattended or
    child session without the attended flag (FR-06)."""
    if env.get("PULSE_HOLDER") or env.get("CODEX_THREAD_ID") or env.get("CLAUDE_CODE_SESSION_ATTENDED") != "1":
        return None
    sid = env.get("CLAUDE_CODE_SESSION_ID") or ""
    return sid if IDENT.fullmatch(sid) else None


def why_not(env) -> str:
    if env.get("PULSE_HOLDER"):
        return "an agent of pulse go gets no lever grant; the person pulls the lever"
    if env.get("CODEX_THREAD_ID"):
        return ("Codex has no confirmation the model cannot answer and does not tell an attended session apart, "
                "so its levers stay the person's: name the command for their terminal")
    return "only an attended Claude Code session gets a lever grant; the person pulls the lever"


def grantable(lever) -> bool:
    lever = " ".join(str(lever or "").split())
    return lever in GRANTABLE or lever.split(" ")[0] in GRANTABLE - {"claim", "release"}


@contextmanager
def _db(root):
    with actions._database(root) as db:
        for table in TABLES:
            db.execute(table)
        yield db


def run_id(root) -> str:
    """The id of the pulse go run that runs in this clone now, else ""."""
    from pulse import go
    run = (go.last_run(root) or {}).get("run") or {}
    return str(run.get("id") or "") if run.get("running") else ""


def _covers(row, sid, current) -> bool:
    if row["scope"] == "always":
        return True
    if row["session"] != sid:
        return False
    return row["scope"] == "session" or row["scope"] == "run" and (not row["run"] or row["run"] == current)


def allowed(root, env) -> dict | None:
    """The grant that covers this process's session now, else None; a store that cannot be read grants nothing."""
    sid = session(env)
    if not sid or root is None:
        return None
    try:
        with _db(root) as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM lever_grants ORDER BY at DESC")]
    except (state.StateError, OSError, sqlite3.Error):
        return None
    current = run_id(root) if any(r["scope"] == "run" and r["run"] for r in rows) else ""
    return next((r for r in rows if _covers(r, sid, current)), None)


def may(root, env, lever=None, tty=True) -> bool:
    """The one decision behind every person check (FEAT-03-05): a person in their terminal, or a grant that
    covers the session; lever None stands for any grantable lever."""
    return auto.person(env, tty) or (lever is None or grantable(lever)) and allowed(root, env) is not None


def who(root) -> str:
    """The person's login as this clone knows it, without the network."""
    def offline(*a, **k):
        raise state.StateError("no cached login")
    try:
        return state.me(root, run=offline, ttl=86400) or "the person"
    except (state.StateError, OSError, ValueError):
        return "the person"


def grant(root, scope, sid, by, run="") -> str:
    if scope not in SCOPES:
        raise state.StateError("scope is run, session or always")
    gid = uuid.uuid4().hex
    with _db(root) as db:
        db.execute("INSERT INTO lever_grants VALUES (?,?,?,?,?,?)", (gid, scope, sid or "", run or "", by, time.time()))
    return gid


def off(root) -> int:
    with _db(root) as db:
        n = db.execute("DELETE FROM lever_grants").rowcount
        db.execute("DELETE FROM lever_asks")
        db.execute("DELETE FROM lever_requests")
    return n


def ask(root, tool_use, sid, scope):
    """The guard showed the dialog for this tool use."""
    with _db(root) as db:
        db.execute("DELETE FROM lever_asks WHERE at < ?", (time.time() - ASK,))
        db.execute("INSERT OR REPLACE INTO lever_asks VALUES (?,?,?,?)", (tool_use, sid, scope, time.time()))


def request(root, sid, scope, run=""):
    """The CLI ran in that session: only after the person agreed, when the guard asked."""
    with _db(root) as db:
        db.execute("INSERT OR REPLACE INTO lever_requests VALUES (?,?,?,?)", (sid, scope, run or "", time.time()))


def confirm(root, tool_use, sid, scope) -> bool:
    """PostToolUse of the asked tool use: the dialog, the command and its request together make the grant."""
    now = time.time()
    with _db(root) as db:
        asked = db.execute("SELECT * FROM lever_asks WHERE tool_use = ?", (tool_use,)).fetchone()
        wanted = db.execute("SELECT * FROM lever_requests WHERE session = ? AND scope = ?", (sid, scope)).fetchone()
        db.execute("DELETE FROM lever_asks WHERE tool_use = ? OR at < ?", (tool_use, now - ASK))
        if not (sid and asked and wanted and asked["session"] == sid and asked["scope"] == scope
                and now - asked["at"] <= ASK and asked["at"] <= wanted["at"] <= now):
            return False
        db.execute("DELETE FROM lever_requests WHERE session = ? AND scope = ?", (sid, scope))
        db.execute("INSERT INTO lever_grants VALUES (?,?,?,?,?,?)",
                   (uuid.uuid4().hex, scope, sid, wanted["run"], who(root), now))
    return True


def answered(root, tool_use, sid, scope) -> bool:
    """PostToolUse of a tool use the guard asked the person about, for this session and scope, within ASK: the
    person agreed in Claude Code's dialog (#231). The ask is spent either way."""
    now = time.time()
    with _db(root) as db:
        asked = db.execute("SELECT * FROM lever_asks WHERE tool_use = ?", (tool_use,)).fetchone()
        db.execute("DELETE FROM lever_asks WHERE tool_use = ? OR at < ?", (tool_use, now - ASK))
    return bool(sid and asked and asked["session"] == sid and asked["scope"] == scope and now - asked["at"] <= ASK)


def _host_asks():
    """The asks for the computer's switch (#231): beside that switch, since it needs no repository."""
    from pulse import config
    return config.host_switch().parent / "asks.json"


def ask_host(tool_use, sid, scope):
    """The guard showed the dialog for the computer's switch, maybe outside any repository (#231)."""
    path, now = _host_asks(), time.time()
    try:
        asks = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if now - v["at"] <= ASK}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        asks = {}
    asks[tool_use] = {"session": sid, "scope": scope, "at": now}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".asks.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(asks, out)
    os.replace(name, path)


def answered_host(tool_use, sid, scope) -> bool:
    """answered() for the computer's switch: the ask is spent either way."""
    path = _host_asks()
    try:
        asks = json.loads(path.read_text(encoding="utf-8"))
        asked = asks.pop(tool_use, None)
        fd, name = tempfile.mkstemp(prefix=".asks.", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(asks, out)
        os.replace(name, path)
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    return bool(sid and isinstance(asked, dict) and asked.get("session") == sid and asked.get("scope") == scope
                and time.time() - asked.get("at", 0) <= ASK)


def prompted(root, sid):
    """The person wrote to this session: a run grant made without a run ends (FR-05)."""
    if sid:
        with _db(root) as db:
            db.execute("DELETE FROM lever_grants WHERE scope = 'run' AND run = '' AND session = ?", (sid,))


def use(root, row, lever, source, sid):
    """FR-08: who granted, which session pulled, which scope, which lever, when."""
    with _db(root) as db:
        db.execute("INSERT INTO lever_uses VALUES (?,?,?,?,?,?,?)",
                   (time.time(), sid or "", row["scope"], row["id"], row["by"], str(lever)[:300], source))
        db.execute("DELETE FROM lever_uses WHERE rowid NOT IN (SELECT rowid FROM lever_uses ORDER BY at DESC LIMIT ?)",
                   (KEEP,))


def until(row) -> str:
    return {"always": "until revoked", "session": f"for session {row['session'][:8]} until revoked"}.get(
        row["scope"]) or (f"until run {row['run'][:8]} ends" if row["run"] else
                          f"until your next message to session {row['session'][:8]}")


def listing(root) -> dict:
    """The grants that still hold and the latest uses (FR-10)."""
    with _db(root) as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM lever_grants ORDER BY at DESC")]
        uses = [dict(r) for r in db.execute("SELECT * FROM lever_uses ORDER BY at DESC LIMIT 20")]
    current = run_id(root) if any(r["scope"] == "run" and r["run"] for r in rows) else ""
    grants = [{**r, "until": until(r)} for r in rows if not (r["scope"] == "run" and r["run"] and r["run"] != current)]
    return {"grants": grants, "uses": uses}
