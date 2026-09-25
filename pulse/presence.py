"""Presence: who is doing what right now, from hook events.

Hooks append one compact line per event to presence.jsonl in the shared
git dir; fold() turns the tail of that log into sessions and their
subagents. Local to this machine; nothing leaves it.

States: working, waiting (a question or a permission prompt is open),
error (the last test or build command failed), idle (turn ended).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from pulse import config

STALE = 30 * 60                # a session silent this long is gone from the map, unless it asks
QUIET = 5 * 60                 # a working agent silent this long is idle: likely stopped without a word
MAX_BYTES = 1_000_000          # trim the log beyond this
KEEP_LINES = 2000
WAITING = {"permission_prompt", "elicitation_dialog", "elicitation_url_dialog", "agent_needs_input"}
CHECK = re.compile(
    r"\b(pytest|unittest|tox|nox|jest|vitest|mocha|playwright|cypress|phpunit|rspec"
    r"|go (test|build|vet)|cargo (test|build|check|clippy)|dotnet (test|build)"
    r"|mvn|gradle|tsc|mypy|ruff|eslint|make (test|check)"
    r"|(npm|pnpm|yarn|bun)( run)? (test|build|lint|check|typecheck))\b")


def _path(root: Path) -> Path:
    return config.pulse_dir(root) / "presence.jsonl"


def target(tool: str, inp: dict, cwd: str) -> str:
    inp = inp or {}
    raw = (inp.get("file_path") or inp.get("notebook_path") or inp.get("command")
           or inp.get("pattern") or inp.get("description") or inp.get("url") or "")
    raw = str(raw).splitlines()[0] if raw else ""
    if cwd and raw.startswith(cwd.rstrip("/") + "/"):
        raw = raw[len(cwd.rstrip("/")) + 1:]
    return raw[:80]


def compact(payload: dict, t: float) -> dict | None:
    event, session = payload.get("hook_event_name"), payload.get("session_id")
    if not event or not session:
        return None
    row = {"t": t, "e": event, "s": session, "cwd": payload.get("cwd", ""),
           "a": payload.get("agent_id") or "", "at": payload.get("agent_type") or ""}
    if "tool_name" in payload:
        row["tool"] = payload["tool_name"]
        row["target"] = target(payload["tool_name"], payload.get("tool_input"), row["cwd"])
    if event == "SessionStart" and payload.get("model"):
        row["model"] = payload["model"]
    if event == "Notification":
        row["nt"] = payload.get("notification_type", "")
    if event == "PostToolUse":
        resp = payload.get("tool_response") or {}
        code = next((resp[k] for k in ("exit_code", "exitCode", "returnCode") if isinstance(resp, dict) and k in resp), 0)
        row["fail"] = bool(code)
    if event == "PostToolUseFailure":
        row["fail"] = True
    return row


def record(root: Path, payload: dict, t: float | None = None) -> None:
    row = compact(payload, time.time() if t is None else t)
    if row is None:
        return
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    if path.stat().st_size > MAX_BYTES:        # keep the newest half, by bytes
        keep, size = [], 0
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            size += len(line) + 1
            if size > MAX_BYTES // 2:
                break
            keep.append(line)
        lines = keep[::-1]
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(path)


def _actor(row: dict) -> dict:
    return {"id": row["a"], "type": row["at"], "cwd": row["cwd"], "started": row["t"], "last": row["t"],
            "tool": "", "target": "", "waiting": False, "error": False, "idle": False, "note": ""}


def fold(rows: list, now: float) -> list:
    sessions: dict = {}
    for r in rows:
        if r["e"] == "SessionEnd":
            sessions.pop(r["s"], None)
            continue
        s = sessions.get(r["s"])
        if s is None:
            s = sessions[r["s"]] = {**_actor({**r, "a": "", "at": ""}), "id": r["s"], "model": "", "agents": {}}
        s["last"] = r["t"]
        if r["e"] == "SubagentStop" and r["a"]:
            s["agents"].pop(r["a"], None)
            continue
        actor = s if not r["a"] else s["agents"].setdefault(r["a"], _actor(r))
        actor["last"] = r["t"]
        if r.get("cwd"):
            actor["cwd"] = r["cwd"]
        if r.get("model"):
            s["model"] = r["model"]
        e = r["e"]
        if e in ("PreToolUse", "UserPromptSubmit", "SubagentStart", "SessionStart"):
            actor["idle"] = False
            # async hooks: the PreToolUse of the call waiting for approval may land after its PermissionRequest
            same = (r.get("tool", ""), r.get("target", "")) == (actor["tool"], actor["target"])
            actor["waiting"] = e == "PreToolUse" and (r.get("tool") == "AskUserQuestion" or actor["waiting"] and same)
        if e in ("PreToolUse", "PermissionRequest"):
            actor["tool"], actor["target"] = r.get("tool", ""), r.get("target", "")
        if e == "PermissionRequest":           # Codex's only approval signal; Claude sends it too
            actor["waiting"] = True
        if e in ("PostToolUse", "PostToolUseFailure"):
            actor["waiting"] = False           # the prompt was answered, the tool ran
            if r.get("tool") == "Bash" and CHECK.search(r.get("target", "")):
                actor["error"] = r.get("fail", False)
                actor["note"] = f"{r['target']} failed" if actor["error"] else ""
        if e == "Notification":
            s["waiting"] = r.get("nt") in WAITING
            s["idle"] = r.get("nt") == "idle_prompt"
        if e == "Stop" and not r["a"]:
            s["idle"] = not s["waiting"]
    out = []
    for s in sessions.values():
        s["agents"] = sorted(s["agents"].values(), key=lambda a: a["started"])
        for a in [s, *s["agents"]]:
            a["state"] = ("waiting" if a["waiting"] else "error" if a["error"]
                          else "idle" if a["idle"] else "working")
        # ponytail: a question waits as long as it takes, so a session killed while it asked
        # stays until its SessionEnd or the log trim
        if now - s["last"] <= STALE or any(a["waiting"] for a in [s, *s["agents"]]):
            out.append(s)
    return sorted(out, key=lambda s: s["started"])


def read(root: Path, now: float | None = None) -> list:
    try:
        lines = _path(root).read_text(encoding="utf-8").splitlines()[-KEEP_LINES:]
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    now = time.time() if now is None else now
    sessions = fold(rows, now)
    for a in (a for s in sessions for a in [s, *s["agents"]]):
        if a["state"] == "working" and now - a["last"] > QUIET:
            a["state"] = "idle"            # a question or a failure still waits for a person
    return sessions
