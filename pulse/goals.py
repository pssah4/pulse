"""Durable user objectives. Agents propose work; the ordinary runner owns every writer."""
from __future__ import annotations

import copy
import json
import re
import subprocess
import uuid
from pathlib import PurePosixPath

from pulse import actions, state

KINDS = {"epic", "feat", "imp", "fix"}
ARTIFACTS = {"ba", "re", "spec", "decision", "plan"}
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _read(db):
    db.execute("CREATE TABLE IF NOT EXISTS goals (singleton INTEGER PRIMARY KEY CHECK(singleton=1), data TEXT NOT NULL)")
    row = db.execute("SELECT data FROM goals WHERE singleton=1").fetchone()
    return json.loads(row[0]) if row else None


def read(root):
    with actions._database(root) as db:
        return _read(db)


def _edit(root, change, expected=None, ident=None):
    with actions._database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        current = _read(db)
        if expected is not None and (current or {}).get("revision") != expected or \
                ident is not None and (current or {}).get("id") != ident:
            raise state.StateError("goal changed; read its current state")
        goal = change(current)
        goal["revision"] = uuid.uuid4().hex
        db.execute("INSERT OR REPLACE INTO goals VALUES(1,?)", (json.dumps(goal, allow_nan=False),))
        return goal


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise state.StateError("goal text must contain 1 to 4000 characters")
    return value.strip()


def _selector(value):
    if not isinstance(value, dict) or len(value) != 1 or next(iter(value)) not in {"epic", "item"}:
        raise state.StateError("use an explicit epic or item selector")
    kind, name = next(iter(value.items()))
    if not isinstance(name, str) or not (re.fullmatch(r"#[1-9][0-9]*", name) or
                                        kind == "epic" and re.fullmatch(r"EPIC-[0-9]+", name)):
        raise state.StateError("use EPIC-04 for a logical epic or #4 for an issue number")
    return dict(value)


def _scope(text, selector=None, previous=None):
    restricted = bool(re.search(r"\b(nur|only|ausschließlich|exclusively)\b", text, re.I))
    epic = re.search(r"\bepic[\s-]*(#?[0-9]+)\b", text, re.I) if restricted else None
    if selector is None and epic:
        name = epic.group(1)
        selector = {"epic": name if name.startswith("#") else f"EPIC-{int(name):02d}"}
    if selector is not None:
        return {"mode": "restricted", "selector": _selector(selector), "items": []}
    if previous and previous["mode"] == "restricted" and not restricted:
        return copy.deepcopy(previous)
    return {"mode": "restricted" if restricted else "additive", "selector": None, "items": []}


def submit(root, objective=None, selector=None, expected=None):
    objective = _text(objective) if objective is not None else "Process the Pulse queue"
    scope = _scope(objective, selector)

    def change(old):
        if old and expected is None:
            raise state.StateError("read the existing goal before changing it")
        return {"version": 1, "id": old["id"] if old else uuid.uuid4().hex, "objective": objective,
                "status": "resolving" if selector or objective != "Process the Pulse queue" else "active",
                "reason": "", "scope": scope, "items": [], "tasks": (old or {}).get("tasks", []),
                "criteria": [], "queue": (old or {}).get("queue", []), "progress": {"done": [], "remaining": []}}
    return _edit(root, change, expected)


def control(root, action, expected, text=None):
    def change(goal):
        if not goal or action not in {"pause", "resume", "steer"}:
            raise state.StateError("no goal or invalid goal control")
        if action == "steer":
            addition = _text(text)
            goal["objective"] = _text(goal["objective"] + "\n" + addition)
            goal["scope"] = _scope(addition, previous=goal["scope"])
            goal.update(status="resolving", criteria=[], reason="")
        else:
            goal["status"] = "paused" if action == "pause" else "active" if goal["criteria"] else "resolving"
        return goal
    return _edit(root, change, expected)


def note(root, goal, why):
    def change(current):
        current.update(status="paused" if current["status"] == "paused" else "waiting", reason=_text(why))
        return current
    return _edit(root, change, goal["revision"], goal["id"])


def select(goal, items):
    """Select candidates only. The caller retains the whole board for claims and blocker checks."""
    scope = goal["scope"]
    if scope["mode"] == "additive":
        return list(items)
    selector = scope.get("selector")
    if not selector:
        return [row for row in items if row["number"] in scope.get("items", [])]
    kind, name = next(iter(selector.items()))
    roots = {int(name[1:])} if name.startswith("#") else \
        {row["number"] for row in items if row.get("type") == "epic" and
         re.match(re.escape(name) + r"(?:\b|:)", row.get("title", ""))}
    allowed = set(scope.get("items", [])) | roots
    if kind == "epic":
        while True:
            descendants = {row["number"] for row in items if row.get("parent") in allowed}
            if descendants <= allowed:
                break
            allowed |= descendants
    return [row for row in items if row["number"] in allowed]


def _path(path):
    if not isinstance(path, str) or not path.startswith("_devprocess/") or "\\" in path or \
            any(part in {"", ".", ".."} for part in path.split("/")) or PurePosixPath(path).is_absolute():
        raise state.StateError("goal artifacts must stay under _devprocess")


def _task_allowed(goal, entry):
    if goal["scope"]["mode"] == "additive":
        return True
    if not goal["scope"].get("selector"):
        return entry["key"] in goal["scope"].get("tasks", [])
    tasks, visited = {row["key"]: row for row in goal["tasks"]}, set()
    parent = entry["parent"]
    while isinstance(parent, str) and parent in tasks and parent not in visited:
        visited.add(parent)
        parent = tasks[parent]["parent"]
    return parent in goal["scope"]["items"] or (entry.get("registration") or {}).get("item") in goal["scope"]["items"]


def resolve(root, goal, proposal, items):
    try:
        return _resolve(root, goal, proposal, items)
    except (KeyError, TypeError, ValueError):
        raise state.StateError("invalid goal proposal") from None


def _resolve(root, goal, proposal, items):
    resolved = copy.deepcopy(goal)
    selected = select(goal, items)
    numbers = {row["number"] for row in items} | set(goal["items"])
    allowed = {row["number"] for row in selected}
    finite = goal["scope"]["mode"] == "restricted" and not goal["scope"].get("selector")
    if finite and isinstance(proposal, dict) and isinstance(proposal.get("items"), list):
        allowed = set(proposal["items"])
    if goal["scope"]["mode"] == "restricted":
        if not allowed and not (finite and isinstance(proposal, dict) and proposal.get("tasks")):
            raise state.StateError("goal restriction is unresolved or matches no items")
        resolved["scope"]["items"] = sorted(allowed)
    if proposal is None:
        work = [row["number"] for row in selected if row.get("type") in state.WORK]
        proposal = {"items": work, "tasks": [],
                    "criteria": [{"text": "Selected work is integrated and checked", "items": work, "artifacts": []}]}
    if not isinstance(proposal, dict) or set(proposal) != {"items", "tasks", "criteria"} or \
            any(not isinstance(proposal[key], list) for key in proposal):
        raise state.StateError("invalid goal proposal")
    existing, tasks, criteria = copy.deepcopy([proposal[key] for key in ("items", "tasks", "criteria")])
    if any(type(n) is not int or n not in numbers or goal["scope"]["mode"] == "restricted" and n not in allowed
           for n in existing):
        raise state.StateError("proposal names unknown work or work outside the goal")
    keys, previous = set(), {row["key"]: row for row in goal["tasks"]}
    for entry in tasks:
        if not isinstance(entry, dict) or set(entry) != {"key", "type", "title", "parent", "artifacts"} or \
                not isinstance(entry["key"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", entry["key"]) or \
                entry["key"] in keys or entry["type"] not in KINDS or not isinstance(entry["artifacts"], list):
            raise state.StateError("invalid or duplicate goal task")
        _text(entry["title"])
        keys.add(entry["key"])
        for artifact in entry["artifacts"]:
            if not isinstance(artifact, dict) or set(artifact) != {"kind", "path"} or artifact["kind"] not in ARTIFACTS:
                raise state.StateError("invalid DIA artifact")
            _path(artifact["path"])
        old = previous.get(entry["key"])
        if old and old.get("registration"):
            if any(old[field] != entry[field] for field in ("type", "parent", "title")):
                raise state.StateError("a registered task cannot change its identity")
            entry["registration"] = old["registration"]
    by_key = {entry["key"]: entry for entry in tasks}
    for entry in tasks:
        parent, visited = entry["parent"], {entry["key"]}
        while isinstance(parent, str) and parent in by_key and parent not in visited:
            visited.add(parent)
            parent = by_key[parent]["parent"]
        if parent is not None and (type(parent) is not int or parent not in numbers) or \
                goal["scope"]["mode"] == "restricted" and not finite and parent not in allowed:
            raise state.StateError("task hierarchy is cyclic, unknown or outside the goal")
    if finite:
        resolved["scope"]["tasks"] = sorted(keys)
    if not criteria:
        raise state.StateError("the goal needs verifiable completion criteria")
    for criterion in criteria:
        if not isinstance(criterion, dict) or set(criterion) != {"text", "items", "artifacts"} or \
                not isinstance(criterion["items"], list) or not isinstance(criterion["artifacts"], list) or \
                not (criterion["items"] or criterion["artifacts"]):
            raise state.StateError("completion criteria need assigned evidence")
        _text(criterion["text"])
        if any(ref not in existing and ref not in keys for ref in criterion["items"]):
            raise state.StateError("criterion refers to unassigned work")
        for artifact in criterion["artifacts"]:
            if not isinstance(artifact, dict) or set(artifact) != {"path", "commit"} or \
                    not isinstance(artifact["commit"], str) or not SHA.fullmatch(artifact["commit"]):
                raise state.StateError("artifact evidence needs an exact commit")
            _path(artifact["path"])
    # Previously registered work survives a new interpretation, including ambiguous remote replies.
    tasks += [entry for key, entry in previous.items() if key not in keys]
    queue = set(goal["queue"]) | {row["number"] for row in selected if row.get("type") in state.WORK}
    resolved.update(items=existing, tasks=tasks, criteria=criteria, queue=sorted(queue), reason="",
                    status="paused" if goal["status"] == "paused" else "active")
    return _edit(root, lambda current: resolved, goal["revision"], goal["id"])


def register(root, task_key, lookup, create):
    """Persist before GitHub. Once creation was attempted, only reconciliation can finish it."""
    goal = read(root)
    if not goal:
        raise state.StateError("no goal to register")

    def entry(current):
        found = next((row for row in current["tasks"] if row["key"] == task_key), None)
        if found is None:
            raise state.StateError("unknown goal task")
        return found

    def update(**values):
        def change(current):
            row = entry(current)
            row.setdefault("registration", {"marker": f"pulse goal {goal['id']} task {task_key}",
                                              "status": "pending", "item": None, "attempted": False})
            if row["registration"]["status"] != "confirmed":
                row["registration"].update(values)
            if row["registration"]["status"] == "confirmed" and current["scope"]["mode"] == "restricted" and \
                    _task_allowed(current, row):
                current["scope"]["items"] = sorted(set(current["scope"]["items"]) | {row["registration"]["item"]})
            return current
        return _edit(root, change, ident=goal["id"])

    current = update()
    record = entry(current)["registration"]
    if not _task_allowed(current, entry(current)):
        return entry(update(status="pending", reason="task is outside the current goal scope"))["registration"]
    if record["status"] == "confirmed":
        return record
    try:
        matches = lookup(record["marker"])
    except Exception:
        matches = None
    if matches is None or not isinstance(matches, list) or len(matches) > 1 or \
            any(type(number) is not int or number <= 0 for number in matches):
        return entry(update(status="pending", reason="registration lookup is unresolved"))["registration"]
    if matches:
        return entry(update(status="confirmed", item=matches[0], reason=""))["registration"]
    if record["attempted"]:
        return entry(update(status="pending", reason="creation reply is missing; waiting for its marker"))["registration"]
    prepared = copy.deepcopy(entry(current))
    if isinstance(prepared["parent"], str):
        parent = next((row for row in current["tasks"] if row["key"] == prepared["parent"]), {})
        prepared["parent"] = (parent.get("registration") or {}).get("item")
        if prepared["parent"] is None:
            return entry(update(reason="parent registration is pending"))["registration"]
    claimed = []

    def sending(current):
        pending = entry(current)["registration"]
        if current["status"] in {"active", "waiting"} and not pending["attempted"] and \
                pending["status"] != "confirmed" and _task_allowed(current, entry(current)):
            pending.update(status="sending", attempted=True, reason="")
            claimed.append(True)
        return current
    current = _edit(root, sending, ident=goal["id"])
    if not claimed:
        return entry(current)["registration"]
    try:
        number = create(prepared, record["marker"])
        if type(number) is not int or number <= 0:
            raise ValueError("invalid registration receipt")
    except Exception:
        return entry(update(status="pending", reason="creation reply is missing; waiting for its marker"))["registration"]
    return entry(update(status="confirmed", item=number, reason=""))["registration"]


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _ancestor(root, commit, base):
    return isinstance(commit, str) and bool(SHA.fullmatch(commit)) and isinstance(base, str) and bool(SHA.fullmatch(base)) and \
        _git(root, "merge-base", "--is-ancestor", commit, base).returncode == 0


def progress(root, goal, items, snapshot, base_head):
    """The runner supplies a freshly fetched base and shared snapshot. No GitHub access here."""
    observed = copy.deepcopy(goal)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), dict) or \
            not isinstance(base_head, str) or not SHA.fullmatch(base_head):
        return note(root, goal, "waiting for current shared state and base")
    selected = select(goal, items)
    queue = set(goal["queue"]) | {row["number"] for row in selected if row.get("type") in state.WORK}
    if goal["scope"]["mode"] == "restricted":
        queue &= set(goal["scope"]["items"])
    tasks = {row["key"]: row for row in goal["tasks"] if _task_allowed(goal, row)}
    registered = {key: (row.get("registration") or {}).get("item") for key, row in tasks.items()}
    required = queue | {n for n in registered.values() if n is not None}

    def done(number, seen=()):
        record = snapshot["items"].get(str(number), {})
        result = record.get("result") or {}
        if record.get("done") and not record.get("hold") and not record.get("failed") and \
                all((result.get("gates") or {}).get(gate) == "pass" for gate in ("tests", "review", "audit")) and \
                _ancestor(root, result.get("head"), record.get("merge")) and _ancestor(root, record.get("merge"), base_head):
            return True
        key = next((key for key in tasks if registered[key] == number and tasks[key]["type"] == "epic"), None)
        children = [registered[k] for k in tasks if tasks[k]["parent"] in (key, number)] if key else []
        return bool(children) and number not in seen and all(n is not None and done(n, (*seen, number)) for n in children)

    def artifact(entry):
        if not _ancestor(root, entry["commit"], base_head):
            return False
        blobs = [_git(root, "rev-parse", f"{ref}:{entry['path']}") for ref in (entry["commit"], base_head)]
        return all(out.returncode == 0 for out in blobs) and blobs[0].stdout == blobs[1].stdout and \
            _git(root, "ls-tree", base_head, "--", entry["path"]).stdout.startswith(("100644 blob ", "100755 blob "))

    criteria_met = bool(goal["criteria"])
    for criterion in goal["criteria"]:
        numbers = [registered.get(ref) if isinstance(ref, str) else ref for ref in criterion["items"]]
        required.update(n for n in numbers if n is not None)
        criteria_met &= all(n is not None and done(n) for n in numbers) and all(map(artifact, criterion["artifacts"]))
    completed = {n for n in required if done(n)}
    unresolved = any((row.get("registration") or {}).get("status") != "confirmed" for row in tasks.values())
    complete = criteria_met and not unresolved and completed == required
    observed.update(queue=sorted(queue), progress={"done": sorted(completed), "remaining": sorted(required - completed)})
    if goal["status"] not in {"paused", "resolving"}:
        unresolved_reason = goal["reason"] if not goal["criteria"] else ""
        observed.update(status="complete" if complete else "waiting", reason="" if complete else
                        unresolved_reason or "waiting for queue work and assigned completion evidence")
    return _edit(root, lambda current: observed, goal["revision"], goal["id"])
