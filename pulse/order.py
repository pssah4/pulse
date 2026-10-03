"""Shared manual ordering (#132), carried by one trusted append-only control issue."""
from __future__ import annotations

import datetime
import hashlib
import json
import re

from pulse import ready, state

LABEL, TITLE = "pulse:order", "Pulse manual order"
MARKER = re.compile(r"<!-- pulse:order (\{[^\n]*\}) -->")


def read(raw: list, trusted) -> dict:
    """Read raw gh issues with state.writer-compatible trust; no I/O or mutations.

    Returns issue, positions (number -> zero-based position), revision and why.
    Conflicts disable manual order. Complete paginated comments can be marked
    _comments_complete on their issue; a capped list otherwise fails closed.
    """
    controls = [record for record in raw if record.get("state", "OPEN") == "OPEN"
                and LABEL in [label["name"] for label in record.get("labels", [])]]
    result = {"issue": None, "positions": {}, "revision": None, "why": ""}
    if len(controls) > 1:
        return dict(result, why="manual order conflict: multiple pulse:order issues; close all but one")
    if not controls:
        return result
    record = controls[0]
    result.update(issue=record["number"], revision=[record["number"], "", "", ""])
    comments = record.get("comments") or []
    if len(comments) >= 100 and not (record.get("_comments_complete") or record.get("_order_complete")):
        return dict(result, why="manual order comments may be incomplete; read all comments first")
    candidates = []
    for entry in comments:
        if "<!-- pulse:order" not in (entry.get("body") or ""):
            continue
        permission = trusted(entry)
        if permission is not True:
            if permission is not False:
                return dict(result, why=f"manual order author permission unknown: {permission}")
            continue
        stamp, url = entry.get("createdAt") or "", entry.get("url") or ""
        identity = re.search(r"#issuecomment-(\d+)$", url)
        try:
            datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return dict(result, why="manual order comment has no valid server timestamp")
        if not identity:
            return dict(result, why="manual order comment has no server identity")
        candidates.append((stamp, int(identity.group(1)), entry))
    if not candidates:
        return result
    latest = max(candidates, key=lambda candidate: candidate[:2])[2]
    body = latest["body"]
    result["revision"] = [record["number"], latest["createdAt"], latest["url"],
                          hashlib.sha256(body.encode()).hexdigest()]
    try:
        marker = MARKER.fullmatch(body.strip())
        data = json.loads(marker.group(1)) if marker else None
        if (not isinstance(data, dict) or set(data) != {"version", "items"}
                or type(data["version"]) is not int or data["version"] != 1
                or not isinstance(data["items"], list)
                or any(type(number) is not int or number <= 0 for number in data["items"])
                or len(set(data["items"])) != len(data["items"])
                or latest.get("edited") or latest.get("lastEditedAt") or latest.get("includesCreatedEdit")
                or latest.get("updatedAt") not in (None, latest["createdAt"])):
            raise ValueError
    except (ValueError, TypeError):
        return dict(result, why="invalid or edited manual order snapshot; confirm a supported version 1 list")
    result["positions"] = {number: position for position, number in enumerate(data["items"])}
    return result


def _binding(items):
    return [(record["number"], record.get("type"), record.get("priority", 3),
             tuple(sorted(record.get("assignees") or [])), record.get("claimed_by"),
             record.get("claimed_holder"), record.get("claimed_at"), record.get("claimed_phase"),
             tuple(sorted(record.get("claimed_files") or [])), tuple(sorted(record.get("blocked_by") or [])),
             bool(record.get("approved")), bool(record.get("draft")), bool(record.get("hold")))
            for record in sorted(items, key=lambda record: record["number"])]


def preview(items: list, seen: dict, number: int, target: int, *, complete=True) -> dict:
    """Pure move proposal; target indexes unclaimed work items in ready.order.

    Pass the complete open board, including held items and epics. Keep the
    returned proposal unchanged until apply; cancellation simply drops it.
    """
    if seen["why"]:
        raise state.StateError(seen["why"])
    if not complete or len(items) >= 1000 or len({record["number"] for record in items}) != len(items):
        raise state.StateError("manual order board is incomplete")
    ordered = ready.order([dict(record, manual_position=seen["positions"].get(
        record["number"], seen["positions"].get(str(record["number"]))))
                           for record in items])
    movable = [record["number"] for record in ordered if record.get("type") in state.WORK
               and not record.get("assignees") and not record.get("claimed_holder")]
    if number not in movable:
        raise state.StateError(f"#{number} is missing, claimed, or not a movable work item")
    if type(target) is not int or not 0 <= target < len(movable):
        raise state.StateError("manual order target is missing")
    moved = list(movable)
    moved.remove(number)
    moved.insert(target, number)
    replacements = iter(moved)
    sequence = [next(replacements) if record["number"] in movable else record["number"] for record in ordered]
    positions = {identifier: position for position, identifier in enumerate(sequence)}
    for record in ordered:
        for blocker in record.get("blocked_by") or []:
            if blocker not in positions:
                raise state.StateError(f"incomplete board: open blocker #{blocker} is missing")
            if positions[blocker] >= positions[record["number"]]:
                raise state.StateError(f"#{record['number']} must follow blocker #{blocker} (or dependency cycle)")
    work = {record["number"] for record in items if record.get("type") in state.WORK}
    return {"number": number, "target": target, "items": [identifier for identifier in sequence if identifier in work],
            "binding": _binding(items), "revision": seen["revision"]}


def _fresh(repo, run):
    raw = state.issues(repo, run)
    if len(raw) >= 1000:
        raise state.StateError("manual order board may be incomplete (1000 issue limit)")
    for record in raw:
        connection = record.get("blockedBy") or {}
        count, returned = connection.get("totalCount"), len(connection.get("nodes") or [])
        if (count is None and returned >= 50 or count is not None and
                (type(count) is not int or count != returned)):
            raise state.StateError("manual order dependencies may be incomplete")
    raw = [state.complete_comments(repo, record, run) for record in raw]
    known = {}
    trusted = lambda entry: state.writer(entry, repo, run, known)
    seen = read(raw, trusted)
    items = [state.normalize(record, lambda entry: trusted(entry) is True, lifecycle_trusted=trusted) for record in raw
             if LABEL not in [label["name"] for label in record.get("labels", [])]]
    return items, seen


def apply(root, repo: str, proposal: dict, run=None) -> dict:
    """Recheck, append one snapshot, return the actual server winner and any warning.

    No retries or claimed atomic compare-and-swap: a competing later comment
    wins and is reported. A failed readback raises; never infer success from it.
    """
    run = run or state.gh
    login = state.me(root, run=run, ttl=0)
    if not state.can_push(repo, login, run):
        raise state.StateError("manual order requires repository write permission")
    items, seen = _fresh(repo, run)
    fresh = preview(items, seen, proposal["number"], proposal["target"])
    if fresh != proposal:
        raise state.StateError("manual order preview changed; refresh and confirm again")
    if seen["issue"] is None:
        try:
            run(["api", f"repos/{repo}/labels/{LABEL}"])
        except state.StateError as error:
            raise state.StateError(f"manual order label unavailable; run pulse setup --labels ({error})") from None
        created = run(["issue", "create", "--repo", repo, "--title", TITLE, "--label", LABEL,
                       "--body", "Team order lives in trusted versioned comments. This body does not set order."])
        issue = int(created.strip().splitlines()[-1].rstrip("/").rsplit("/", 1)[-1])
        items, seen = _fresh(repo, run)
        if seen["why"] or seen["issue"] != issue or seen["revision"] != [issue, "", "", ""]:
            raise state.StateError(seen["why"] or "manual order changed while creating its control issue")
        fresh = preview(items, seen, proposal["number"], proposal["target"])
        if dict(fresh, revision=proposal["revision"]) != proposal:
            raise state.StateError("manual order preview changed; refresh and confirm again")
    body = '<!-- pulse:order ' + json.dumps({"version": 1, "items": proposal["items"]}, separators=(",", ":")) + ' -->'
    try:
        url = run(["issue", "comment", str(seen["issue"]), "--repo", repo, "--body", body]).strip()
        items, result = _fresh(repo, run)
    finally:
        state.drop_cache(root)
    if result["why"]:
        return result
    expected = {number: position for position, number in enumerate(proposal["items"])}
    if (result["positions"] != expected or not result["revision"] or result["revision"][2] != url
            or _binding(items) != proposal["binding"]):
        return dict(result, why="manual order changed during save; showing the latest server state")
    return result
