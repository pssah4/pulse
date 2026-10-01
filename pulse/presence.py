"""Local, disposable activity snapshots. No transcripts, commands, network or claims."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import time
import stat
from contextlib import contextmanager
from pathlib import Path

from pulse import config

EXPIRE = 30 * 60
EVENTS = {"SessionStart", "SubagentStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
          "PostToolUse", "Stop", "SubagentStop", "SessionEnd"}
IDENT = re.compile(r"[\w.:-]{1,160}\Z", re.ASCII)
PATCH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.M)


def _text(value, limit=512):
    return value[:limit] if isinstance(value, str) and value.isprintable() else ""


def _small(path):
    with path.open(encoding="utf-8") as stream:
        return stream.read(16384)


def _location(root, env):
    """Git's worktree pointer and commondir files need no git process per tool."""
    root = config.find_root(Path(root))
    if root is None or env.get("PULSE_PRESENCE") == "off":
        return None
    gitdir = root / ".git"
    if gitdir.is_file():
        pointer = _small(gitdir).strip()
        if not pointer.startswith("gitdir: "):
            return None
        gitdir = (root / pointer[8:]).resolve()
    if not (gitdir / "HEAD").is_file():
        return None
    common = (gitdir / _small(gitdir / "commondir").strip()).resolve() \
        if (gitdir / "commondir").is_file() else gitdir
    source = next((root / d / "config.toml" for d in (".pulse", ".dia")
                   if (root / d / "config.toml").is_file()), None)
    if source is None:
        source = next((common.parent / d / "config.toml" for d in (".pulse", ".dia")
                       if (common.parent / d / "config.toml").is_file()), None)
    if source is None:
        return None
    data = config._parse(_small(source), strict=True)
    mode = config.DIA_MODES.get(data.get("mode"), "on") if source.parent.name == ".dia" else data.get("mode")
    return (root, gitdir, common / "pulse" / "presence") if mode == "on" else None


def _target(tool, given):
    if not isinstance(given, dict):
        return ""
    if tool == "apply_patch":
        patch = given.get("command")
        paths = [m.group(1) or m.group(2) for m in PATCH.finditer(patch[:65536])] if isinstance(patch, str) else []
        return ", ".join(filter(None, (_text(path, 256) for path in paths[:3])))
    if tool in {"Edit", "Write", "Read", "MultiEdit", "NotebookEdit"}:
        return _text(given.get("file_path") or given.get("notebook_path"), 256)
    return ""                             # shell commands and arbitrary MCP inputs are never activity text


@contextmanager
def _directory(path, create=False):
    fd = os.open(path.parent.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in ("pulse", "presence"):
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _lock(directory, name):
    fd = os.open(name.removesuffix(".json") + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                 0o600, dir_fd=directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            raise OSError("not a private actor lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _snapshot(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, encoding="utf-8") as stream:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("not a snapshot")
        return json.loads(stream.read(16384))


def record(payload, env, now=None):
    """One bounded atomic snapshot per actor; an event never changes approval or claim state."""
    try:
        event, session = payload.get("hook_event_name"), payload.get("session_id")
        agent = payload.get("agent_id") or ""
        if event not in EVENTS or not isinstance(session, str) or not IDENT.fullmatch(session) or \
                agent and (not isinstance(agent, str) or not IDENT.fullmatch(agent)):
            return
        where = _location(payload.get("cwd") or Path.cwd(), env)
        if where is None:
            return
        root, gitdir, directory = where
        who = agent or session
        name = hashlib.sha256(who.encode()).hexdigest() + ".json"
        with _directory(directory, create=True) as opened, _lock(opened, name):
            _update(payload, env, now, event, session, agent, who, root, gitdir, opened, name)
    except (OSError, ValueError, TypeError, AttributeError):
        pass                                # observation never interferes with the tool or its guard


def _update(payload, env, now, event, session, agent, who, root, gitdir, directory, path):
    try:
        previous = _snapshot(directory, path)
    except (OSError, ValueError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}
    if previous.get("state") == "ended" and event not in {"SessionStart", "SubagentStart", "UserPromptSubmit"}:
        return                                # a late parallel tool result cannot revive an ended actor
    tool = _text(payload.get("tool_name"), 100)
    tool = tool if IDENT.fullmatch(tool) else ""
    waiting = previous.get("waiting", {})
    call = _text(payload.get("tool_use_id"), 160) or "tool:" + tool
    if event == "PermissionRequest" or tool == "AskUserQuestion" and event == "PreToolUse":
        if len(waiting) < 16:
            waiting[call] = tool
        else:
            waiting["overflow"] = ""           # stays waiting until Stop or the next prompt
    elif event == "PostToolUse":
        waiting.pop(call, None)                # another parallel tool never answers this permission
    elif event in {"UserPromptSubmit", "Stop", "SessionStart"}:
        waiting = {}
    status = "ended" if event in {"SessionEnd", "SubagentStop"} else \
        "waiting" if waiting else "idle" if event in {"Stop", "SessionStart"} else "working"
    harness = "codex" if "turn_id" in payload or env.get("CODEX_THREAD_ID") and not env.get("CLAUDECODE") \
        else previous.get("harness", "claude")
    try:
        holder = json.loads(env.get("PULSE_HOLDER") or "null")
    except ValueError:
        holder = None
    holder = _text(holder.get("id"), 160) if isinstance(holder, dict) else ""
    head = _small(gitdir / "HEAD").strip()
    row = {"id": who, "parent": session if agent else previous.get("parent", ""),
           "cwd": str(root), "branch": head[16:] if head.startswith("ref: refs/heads/") else "",
           "harness": harness, "holder": holder,
           "waiting": waiting,
           "state": status, "tool": next(iter(waiting.values())) if waiting else
           tool if event in {"PreToolUse", "PermissionRequest"} else "",
           "target": _target(tool, payload.get("tool_input")) if event in {"PreToolUse", "PermissionRequest"} else "",
           "last": time.time() if now is None else now}
    temporary = "." + os.urandom(8).hex()
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(row, stream, separators=(",", ":"), ensure_ascii=False)
        os.replace(temporary, path, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def read(root, now=None, env=None):
    """Map shape, with separate subagents. Expired snapshots retire under their writer's lock."""
    try:
        where = _location(root, os.environ if env is None else env)
        if where is None:
            return []
        rows, ended = {}, set()
        now = time.time() if now is None else now
        with _directory(where[2]) as directory:
            for name in os.listdir(directory):
                if not name.endswith(".json"):
                    continue
                try:
                    if now - os.stat(name, dir_fd=directory, follow_symlinks=False).st_mtime >= EXPIRE:
                        # Recheck under the writer's lock; a newly replaced snapshot must survive.
                        with _lock(directory, name):
                            if now - os.stat(name, dir_fd=directory, follow_symlinks=False).st_mtime >= EXPIRE:
                                os.unlink(name, dir_fd=directory)
                                continue
                    row = _snapshot(directory, name)
                    if not isinstance(row, dict) or not all(isinstance(row.get(key), str) for key in
                            ("id", "parent", "cwd", "branch", "harness", "state", "tool", "target", "holder")):
                        continue
                    if row["state"] == "ended":
                        ended.add(row["id"])
                        continue
                    if not 0 <= now - row["last"] < EXPIRE or row["state"] not in {"working", "waiting", "idle"}:
                        continue
                    rows[row["id"]] = {**row, "agents": [], "note": ""}
                except (OSError, ValueError, KeyError, TypeError):
                    continue
        rows = {key: row for key, row in rows.items() if row["parent"] not in ended}
        for row in rows.values():
            parent = rows.get(row["parent"])
            if parent and parent is not row:
                parent["agents"].append(row)
        return [row for row in rows.values() if row["parent"] not in rows]
    except (OSError, ValueError, TypeError, AttributeError):
        return []
