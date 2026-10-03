"""Serialized workflow state on origin/pulse-state, without touching HEAD or the index.

Only a successful ordinary push confirms an operation. The reducer checks state,
not identity: callers must authenticate approval proofs before allowing a merge.
"""
from __future__ import annotations

import copy
import json
import posixpath
import re
import subprocess
import unicodedata

from pulse import ready
from pulse.state import StateError

REF = "refs/heads/pulse-state"
RETRIES = 6
SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
ID = re.compile(r"[0-9a-f]{32}\Z")
DEFAULT_POLICY = {"revision": "default:auto:v1", "mode": "automatic", "proof": None, "until": None}
KINDS = {"claim", "release", "defer", "stopped", "resume", "approve", "revoke",
         "result", "integrating", "integrated", "integration_aborted", "migrate", "handoff", "published", "failed",
         "removal_begin", "removal_rebind", "removal_finalize", "removal_deleted", "policy", "autoapprove"}


def _git(root, *args, text=None):
    result = subprocess.run(["git", "-C", str(root), *args], input=text, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise StateError(result.stderr.strip() or "shared state git command failed")
    return result.stdout.strip()


def _network(root, *args):
    result = ready.net_git(root, *args)
    if result.returncode:
        raise StateError(result.stderr.strip() or result.stdout.strip() or "shared state transport failed")
    return result.stdout


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate state key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"invalid JSON state value: {value}")


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _sha(value):
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def _files(values):
    if not isinstance(values, list) or any(not _text(v) or "\\" in v or v.startswith("/")
                                         or ".." in v.split("/") or posixpath.normpath(v) != v
                                         for v in values):
        raise StateError("invalid shared state file reservation")
    return sorted(set(unicodedata.normalize("NFC", posixpath.normpath(v)) for v in values))


def _binding(value):
    return isinstance(value, dict) and _sha(value.get("head")) and _sha(value.get("base"))


def _gates(value):
    return isinstance(value, dict) and all(_text(key) and isinstance(status, str)
            and status in {"pass", "fail", "block", "none", "pending", "error"} for key, status in value.items())


def _proof(value):
    return (isinstance(value, dict) and not set(value) - {"comment", "author", "operation", "issue"}
            and type(value.get("comment")) is int and value["comment"] > 0
            and ("issue" not in value or type(value["issue"]) is int and value["issue"] > 0)
            and ("author" not in value or _text(value["author"]))
            and ("operation" not in value or isinstance(value["operation"], str)
                 and bool(ID.fullmatch(value["operation"]))))


def _operation(op):
    if (not isinstance(op, dict) or set(op) != {"id", "item", "kind", "expected", "payload"}
            or not isinstance(op["id"], str) or not ID.fullmatch(op["id"])
            or type(op["item"]) is not int or op["item"] < 0 or (op["item"] == 0) != (op["kind"] == "policy")
            or not isinstance(op["kind"], str) or op["kind"] not in KINDS
            or not isinstance(op["expected"], str) or not isinstance(op["payload"], dict)):
        raise StateError("invalid shared state operation")
    try:
        if json.loads(json.dumps(op, allow_nan=False)) != op:
            raise ValueError("operation changes during JSON serialization")
    except (ValueError, TypeError) as exc:
        raise StateError("invalid shared state operation payload") from exc


def policy(snapshot):
    return snapshot.get("policy", dict(DEFAULT_POLICY))


def _policy(value):
    if value == DEFAULT_POLICY:
        return
    if (not isinstance(value, dict) or set(value) != {"revision", "mode", "proof", "until"}
            or not isinstance(value["mode"], str) or value["mode"] not in {"manual", "automatic"}
            or not isinstance(value["revision"], str) or value["revision"] and not ID.fullmatch(value["revision"])
            or value["until"] is not None and not _text(value["until"])
            or value["revision"] and (not _proof(value["proof"]) or not value["proof"].get("issue"))
            or not value["revision"] and (value["mode"] != "manual" or value["proof"] is not None)):
        raise StateError("invalid integration approval policy")


def policy_reason(snapshot, item):
    from pulse import auto
    approval, current = item.get("approval") or {}, policy(snapshot)
    if approval.get("policy") and (item.get("removal") or approval["policy"] != current["revision"]
                                   or not auto.active(current) or approval["proof"] != current["proof"]):
        return "automatic approval policy changed or expired"
    return ""


def _item(value, initial=False):
    keys = {"revision", "claim", "hold", "hold_origin", "stop", "result", "approval", "done", "merge"}
    if (not isinstance(value, dict) or not keys <= set(value) or set(value) - keys - {"work", "failed", "failure", "removal", "revoked"}
            or not isinstance(value["revision"], str)
            or not (ID.fullmatch(value["revision"]) or initial and value["revision"] == "")
            or type(value["hold"]) is not bool or type(value["done"]) is not bool
            or not isinstance(value["hold_origin"], str)
            or value.get("work") is not None and not isinstance(value["work"], dict)
            or type(value.get("failed", False)) is not bool or not isinstance(value.get("failure", ""), str)
            or value["merge"] is not None and not _sha(value["merge"])):
        raise StateError("invalid shared state item schema")
    claim, stop, result, approval = (value[key] for key in ("claim", "stop", "result", "approval"))
    if claim is not None:
        if (not isinstance(claim, dict) or not {"holder", "files"} <= set(claim)
                or set(claim) - {"holder", "files", "session", "actor"} or not _text(claim["holder"])
                or any(not _text(claim[key]) for key in ("session", "actor") if key in claim)):
            raise StateError("invalid shared state claim")
        if _files(claim["files"]) != claim["files"]:
            raise StateError("invalid shared state reservation paths")
    if stop is not None and (not isinstance(stop, dict) or set(stop) != {"holder", "status", "work"}
                             or not _text(stop["holder"]) or stop["status"] not in {"requested", "completed"}
                             or stop["work"] is not None and not isinstance(stop["work"], dict)):
        raise StateError("invalid shared state stop")
    if result is not None and (not _binding(result) or set(result) != {"branch", "head", "base", "gates"}
                               or not _text(result["branch"]) or not _gates(result["gates"])):
        raise StateError("invalid shared state result")
    if approval is not None and (not _binding(approval) or not {"head", "base", "proof"} <= set(approval)
                                 or set(approval) - {"head", "base", "proof", "policy"}
                                 or (approval["proof"] is not None if approval.get("policy") == DEFAULT_POLICY["revision"]
                                     else not _proof(approval["proof"]))
                                 or "policy" in approval and approval["policy"] != DEFAULT_POLICY["revision"]
                                 and not ID.fullmatch(str(approval["policy"]))):
        raise StateError("invalid shared state approval")
    if value.get("revoked") is not None and (not _binding(value["revoked"]) or set(value["revoked"]) != {"head", "base"}):
        raise StateError("invalid revoked result binding")
    removal = value.get("removal")
    if removal is not None:
        if (not isinstance(removal, dict) or set(removal) != {"operation", "inventory", "original", "finalizer", "deleted"}
                or not isinstance(removal["operation"], dict) or not ID.fullmatch(str(removal["operation"].get("id", "")))
                or removal["operation"].get("action") != "delete" or removal["operation"].get("phase") != "paused"
                or not isinstance(removal["inventory"], dict) or not _sha(removal["inventory"].get("base_sha"))
                or not isinstance(removal["finalizer"], str) or type(removal["deleted"]) is not bool
                or not isinstance(removal["original"], dict) or "removal" in removal["original"]):
            raise StateError("invalid removal metadata")
        _item(removal["original"])


def _validate(snapshot):
    if (not isinstance(snapshot, dict) or set(snapshot) - {"policy"} != {"version", "items", "operations", "integration"}
            or type(snapshot["version"]) is not int or snapshot["version"] != 1
            or not isinstance(snapshot["items"], dict) or not isinstance(snapshot["operations"], dict)):
        raise StateError("unknown or invalid shared state schema version")
    _policy(policy(snapshot))
    for number, item in snapshot["items"].items():
        if not re.fullmatch(r"[1-9][0-9]*", number):
            raise StateError("invalid shared state item number")
        _item(item)
    for oid, record in snapshot["operations"].items():
        if not isinstance(record, dict) or set(record) != {"operation", "result"}:
            raise StateError("invalid shared state operation record")
        _operation(record["operation"])
        result = record["result"]
        if (oid != record["operation"]["id"] or not isinstance(result, dict)
                or set(result) != {"status", "data", "reason"}
                or result["status"] not in {"confirmed", "conflict"} or not isinstance(result["reason"], str)):
            raise StateError("invalid shared state operation outcome")
        if record["operation"]["kind"] == "policy":
            _policy(result["data"])
        else:
            _item(result["data"], initial=True)
    reservation = snapshot["integration"]
    if reservation is not None and (not _binding(reservation)
            or set(reservation) != {"item", "holder", "head", "base"}
            or type(reservation["item"]) is not int or not _text(reservation["holder"])
            or str(reservation["item"]) not in snapshot["items"]):
        raise StateError("invalid shared state integration reservation")


def read(root):
    """Return a fresh origin revision and validated snapshot; an absent branch starts empty."""
    remote = ready.net_git(root, "ls-remote", "--exit-code", "origin", REF)
    if remote.returncode == 2 and not remote.stdout.strip():
        return "", {"version": 1, "items": {}, "operations": {}, "integration": None}
    if remote.returncode:
        raise StateError(remote.stderr.strip() or "shared state origin did not answer")
    rows = [row.split() for row in remote.stdout.splitlines()]
    if len(rows) != 1 or len(rows[0]) != 2 or not _sha(rows[0][0]) or rows[0][1] != REF:
        raise StateError("invalid shared state remote revision")
    revision = rows[0][0]
    _network(root, "fetch", "--no-write-fetch-head", "--no-tags", "origin", REF)
    try:
        snapshot = json.loads(_git(root, "show", f"{revision}:state.json"), object_pairs_hook=_object,
                              parse_constant=_constant)
        _validate(snapshot)
    except (ValueError, TypeError, KeyError) as exc:
        raise StateError("invalid shared state schema") from exc
    return revision, snapshot


def _empty():
    return {"revision": "", "claim": None, "hold": False, "hold_origin": "", "stop": None,
            "result": None, "approval": None, "done": False, "merge": None,
            "work": None, "failed": False, "failure": ""}


def _overlap(left, right):
    a, b = left.casefold(), right.casefold()
    return a == b or a == "." or b == "." or a.startswith(b + "/") or b.startswith(a + "/")


def _reduce(snapshot, op, item):
    kind, payload, holder = op["kind"], op["payload"], op["payload"].get("holder")
    claim, reservation = item["claim"], snapshot["integration"]
    owns = claim is not None and claim["holder"] == holder
    removal = item.get("removal")
    if kind in {"integrating", "integrated"} and policy_reason(snapshot, item):
        return policy_reason(snapshot, item)
    if kind == "removal_begin":
        operation = payload.get("operation") or {}
        if (removal or not item["done"] or not item["result"] or not item["merge"] or claim or reservation
                or item["hold"] and item["hold_origin"] != "delete:" + str(operation.get("id"))
                or not _proof(payload.get("proof"))):
            return "removal needs an unclaimed completed item and its confirmed deletion operation"
        original = copy.deepcopy(item)
        item.update(_empty())
        item["removal"] = {"operation": operation, "inventory": operation.get("inventory"),
                           "original": original, "finalizer": "", "deleted": False}
        return ""
    if kind in {"removal_finalize", "removal_deleted"}:
        if (not removal or not item["done"] or removal["deleted"] or payload.get("id") != removal["operation"]["id"]
                or payload.get("merge") != item["merge"] or not _text(holder)
                or removal["finalizer"] not in ("", holder)):
            return "removal completion requires its integrated binding and reservation owner"
        if kind == "removal_deleted" and removal["finalizer"] != holder:
            return "deletion needs its reserved, acknowledged outcome"
        removal["finalizer"] = holder
        removal["deleted"] = kind == "removal_deleted"
        return ""
    if item["done"]:
        return "item is complete"
    if kind == "removal_rebind":
        inventory = payload.get("inventory") or {}
        if (not removal or not owns or inventory != {**removal["inventory"], "base_sha": inventory.get("base_sha")}
                or not _sha(inventory.get("base_sha"))):
            return "removal rebind needs unchanged scope and its current writer"
        removal["inventory"] = inventory
        kind = "published"
    if kind == "migrate":
        if item["revision"]:
            return "legacy state was already imported"
        item.update(claim=payload.get("claim"), hold=payload.get("hold", False),
                    hold_origin=payload.get("hold_origin", "legacy") if payload.get("hold") else "",
                    failed=payload.get("failed", False), failure=payload.get("failure", ""))
        _item(item, initial=True)
        if item["claim"] and any(other["claim"] and any(_overlap(a, b) for a in item["claim"]["files"]
                for b in other["claim"]["files"]) for other in snapshot["items"].values()):
            return "legacy files overlap a current reservation"
    elif kind == "claim":
        if (item["hold"] or item.get("failed") or claim and not owns or not _text(holder)
                or removal and payload.get("removal") != removal["operation"]["id"]):
            return "item is held or already claimed"
        files = _files(payload.get("files"))
        for number, other in snapshot["items"].items():
            if number == str(op["item"]):
                continue
            if other["claim"] and any(_overlap(a, b) for a in files for b in other["claim"]["files"]):
                return "files are reserved by another item"
        metadata = {key: payload[key] for key in ("session", "actor") if key in payload}
        if any(not _text(v) for v in metadata.values()) or claim and any(claim.get(k) != v for k, v in metadata.items()):
            return "claim identity cannot change during reservation refresh"
        item["claim"] = {**(claim or {}), "holder": holder, "files": files, **metadata}
        if "phase" in payload:
            if not _text(payload["phase"]):
                return "claim phase is invalid"
            item["work"] = {**(item.get("work") or {}), "phase": payload["phase"]}
    elif kind == "release":
        if (not owns or reservation and reservation["item"] == op["item"]
                or item["stop"] and item["stop"]["holder"] == holder and item["stop"]["status"] == "requested"):
            return "only the current writer can release an idle claim"
        item["claim"] = None
        if "work" in payload:
            item["work"] = payload["work"]
    elif kind in {"handoff", "failed"}:
        if (not owns or not _text(payload.get("reason")) or not isinstance(payload.get("work"), dict)
                or kind == "handoff" and not _proof(payload.get("proof"))):
            return "claim handoff requires the current holder, a reason, retained work and person proof"
        item.update(claim=None, approval=None, work=payload["work"])
        if kind == "handoff":
            item["stop"] = {"holder": holder, "status": "requested", "work": payload["work"]}
        else:
            item.update(failed=True, failure=payload["reason"])
        if reservation and reservation["item"] == op["item"]:
            snapshot["integration"] = None
    elif kind == "defer":
        origin = payload.get("origin", "defer")
        if not _text(origin) or item["hold"] and item["hold_origin"] != origin:
            return "another hold remains active"
        item.update(hold=True, hold_origin=origin, approval=None)
        if claim:
            item["stop"] = {"holder": claim["holder"], "status": "requested", "work": None}
    elif kind == "stopped":
        if (not item["stop"] or item["stop"]["status"] != "requested"
                or item["stop"]["holder"] != holder or not isinstance(payload.get("work"), dict)):
            return "stop needs the requested writer's acknowledgement and retained work"
        item["stop"].update(status="completed", work=payload["work"])
        if owns:
            item["claim"] = None
            item["work"] = payload["work"]
    elif kind == "resume":
        if (claim or item["stop"] and item["stop"]["status"] != "completed"
                or item["hold"] and item["hold_origin"] != payload.get("origin", "defer")):
            return "writer has not stopped or another hold remains active"
        item.update(hold=False, hold_origin="", failed=False, failure="")
    elif kind == "published":
        if (not owns or item["hold"] or item.get("failed") or not _sha(payload.get("head"))
                or not _text(payload.get("branch")) or not _text(payload.get("phase"))):
            return "publication requires the active claim and concrete work"
        item["work"] = {key: payload[key] for key in ("branch", "head", "phase", "worktree", "reason") if key in payload}
        if item["result"] and any(item["result"][key] != payload[key] for key in ("branch", "head")):
            item.update(result=None, approval=None)
    elif kind == "result":
        if not owns or item["hold"] or not _binding(payload) or not _text(payload.get("branch")):
            return "result requires the current writer and concrete head and base"
        if not _gates(payload.get("gates")):
            return "result requires gate evidence"
        item["result"] = {key: payload[key] for key in ("branch", "head", "base", "gates")}
        item["approval"] = None
        if item.get("revoked") != {key: payload[key] for key in ("head", "base")}:
            item.pop("revoked", None)
    elif kind in {"approve", "autoapprove"}:
        if (item["hold"] or not item["result"] or not _binding(payload)
                or any(payload[key] != item["result"][key] for key in ("head", "base"))
                or kind == "approve" and not _proof(payload.get("proof"))):
            return "approval requires the current result binding and a person proof reference"
        approval = {key: payload[key] for key in ("head", "base")}
        if kind == "autoapprove":
            current = policy(snapshot)
            approval.update(policy=payload.get("policy"), proof=current["proof"])
            if (not approval["policy"] or policy_reason(snapshot, {**item, "approval": approval})
                    or item.get("failed") or item.get("revoked") == {key: payload[key] for key in ("head", "base")}
                    or any(item["result"]["gates"].get(g) != "pass" for g in ("tests", "review", "audit"))
                    or any(v != "pass" for v in item["result"]["gates"].values())):
                return "automatic approval needs current policy, gates and an unrevoked regular result"
        else:
            approval["proof"] = payload["proof"]
            item.pop("revoked", None)
        item["approval"] = approval
    elif kind == "revoke":
        if item["result"]:
            item["revoked"] = {key: item["result"][key] for key in ("head", "base")}
        item["approval"] = None
    elif kind == "integrating":
        if (reservation or not owns or item["hold"] or not item["approval"] or not item["result"]
                or any(payload.get(key) != item["approval"][key] or payload.get(key) != item["result"][key]
                       for key in ("head", "base"))):
            return "integration needs the current approved result and a free reservation"
        snapshot["integration"] = {"item": op["item"], "holder": holder,
                                   "head": payload["head"], "base": payload["base"]}
    elif kind == "integrated":
        if (not reservation or reservation["item"] != op["item"] or reservation["holder"] != holder
                or not _sha(payload.get("merge"))):
            return "integration completion needs its reservation holder and merge commit"
        item.update(done=True, claim=None, approval=item["approval"] if removal else None, merge=payload["merge"])
        snapshot["integration"] = None
    elif kind == "integration_aborted":
        if not reservation or reservation["item"] != op["item"] or reservation["holder"] != holder:
            return "only the integration holder can acknowledge an aborted merge"
        snapshot["integration"] = None
    return ""


def _commit(root, snapshot, parent, operation):
    blob = _git(root, "hash-object", "-w", "--stdin", text=json.dumps(snapshot, sort_keys=True, allow_nan=False))
    tree = _git(root, "mktree", text=f"100644 blob {blob}\tstate.json\n")
    args = ("-p", parent) if parent else ()
    return _git(root, "-c", "user.name=Pulse", "-c", "user.email=pulse@localhost", "commit-tree", tree,
                *args, text=f"pulse state: {operation['kind']} #{operation['item']} {operation['id']}\n")


def _prepare(snapshot, operation):
    record = snapshot["operations"].get(operation["id"])
    if record:
        if record["operation"] == operation:
            return copy.deepcopy(record["result"]), False
        return {"status": "conflict", "data": copy.deepcopy(record["result"]["data"]),
                "reason": "operation identity was reused with different content"}, False
    key, setting = str(operation["item"]), operation["kind"] == "policy"
    current = policy(snapshot) if setting else snapshot["items"].get(key, _empty())
    item = copy.deepcopy(current)
    why = "item revision changed" if operation["expected"] != item["revision"] else ""
    if not why and setting:
        item = {"revision": operation["id"], **{k: operation["payload"].get(k) for k in ("mode", "proof", "until")}}
        _policy(item)
    elif not why:
        why = _reduce(snapshot, operation, item)
    if not why:
        item["revision"] = operation["id"]
        if setting:
            snapshot["policy"] = item
        else:
            snapshot["items"][key] = item
    result = {"status": "conflict" if why else "confirmed", "data": copy.deepcopy(current if why else item),
              "reason": why}
    snapshot["operations"][operation["id"]] = {"operation": operation, "result": result}
    _validate(snapshot)
    return result, True


def remote_head(root, branch):
    """Read a branch's advertised SHA, including an explicitly absent branch."""
    _git(root, "check-ref-format", f"refs/heads/{branch}")
    got = ready.net_git(root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}")
    if got.returncode == 2 and not got.stdout.strip():
        return ""
    if got.returncode:
        raise StateError(got.stderr.strip() or "origin did not answer")
    rows = [row.split() for row in got.stdout.splitlines()]
    if len(rows) != 1 or len(rows[0]) != 2 or not _sha(rows[0][0]) or rows[0][1] != f"refs/heads/{branch}":
        raise StateError("invalid remote branch revision")
    return rows[0][0]


def publish(root, operation, branch, head, expected_head):
    """Publish state and one branch atomically. A race requires a fresh authority check, never a retry."""
    _operation(operation)
    if (operation["kind"] not in {"published", "result", "integrated", "removal_rebind"}
            or not _sha(head) or expected_head and not _sha(expected_head) or branch == "pulse-state"):
        raise StateError("invalid atomic publication binding")
    revision, snapshot = read(root)
    result, changed = _prepare(snapshot, operation)
    if result["status"] == "conflict":
        return {**result, "revision": revision}
    current_head = remote_head(root, branch)
    if not changed:
        if current_head != head:
            return {**result, "status": "conflict", "revision": revision, "reason": "published branch changed"}
        return {**result, "revision": revision}
    if current_head != expected_head:
        return {**result, "status": "conflict", "revision": revision, "reason": "published branch changed"}
    payload = operation["payload"]
    if (operation["kind"] == "integrated" and payload.get("merge") != head
            or operation["kind"] != "integrated" and (payload.get("head") != head or payload.get("branch") != branch)):
        raise StateError("operation does not bind this publication")
    commit = _commit(root, snapshot, revision, operation)
    try:
        for previous, following in ((expected_head, head), (revision, commit)):
            if _git(root, "cat-file", "-t", following) != "commit":
                raise StateError("publication target is not a commit")
            if previous:
                _git(root, "--no-replace-objects", "merge-base", "--is-ancestor", previous, following)
    except StateError:
        return {**result, "status": "conflict", "revision": revision,
                "reason": "publication would replace history or its ancestry cannot be proven"}
    # Explicit expected SHAs provide compare-and-swap. The ancestry proof above forbids history replacement.
    pushed = ready.net_git(root, "push", "--atomic", "--porcelain", "origin",
                           f"--force-with-lease={REF}:{revision}",
                           f"--force-with-lease=refs/heads/{branch}:{expected_head}",
                           f"{commit}:{REF}", f"{head}:refs/heads/{branch}")
    if pushed.returncode == 0:
        return {**result, "revision": commit}
    reason = pushed.stderr.strip() or pushed.stdout.strip() or "atomic publication failed"
    if "[rejected]" in pushed.stdout or "[remote rejected]" in pushed.stdout:
        return {**result, "status": "conflict", "revision": revision, "reason": reason}
    # a pre-push hook writes to stdout too, npm's header with the script's name (#178)
    raise StateError("\n".join(filter(None, (pushed.stdout.strip(), pushed.stderr.strip()))) or reason)


def update(root, operation):
    """Apply an operation once; stale state is a persisted conflict, transport errors raise."""
    _operation(operation)
    for _ in range(RETRIES):
        revision, snapshot = read(root)
        result, changed = _prepare(snapshot, operation)
        if not changed:
            return {**result, "revision": revision}
        commit = _commit(root, snapshot, revision, operation)
        push = ready.net_git(root, "push", "--porcelain", "origin", f"{commit}:{REF}")
        if push.returncode == 0:
            return {**result, "revision": commit}
        said = push.stderr.strip() or push.stdout.strip() or "shared state push failed"
        if "[rejected]" not in push.stdout and "[remote rejected]" not in push.stdout:
            raise StateError(said)
        # Only a rejected push may be a competing writer. An uncertain response is never confirmation.
        next_revision, _ = read(root)
        if next_revision == revision:
            raise StateError(said)
    raise StateError("shared state changed too often; retry this operation later")
