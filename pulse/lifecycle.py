"""Person-confirmed pauses and holder-acknowledged handovers, recorded on the item."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path

from pulse import config, ready, state

MARK = re.compile(r"^<!-- pulse:lifecycle (\{[^\n]*\}) -->")
ACTIONS = {"defer", "resume", "discard", "delete"}
PHASES = {"requested", "stopped", "paused", "resumed", "discarded"}


def trusted(repo, run=state.gh):
    known = {}
    return lambda comment: state.writer(comment, repo, run, known)


def operation(raw, trusted=state._owner) -> dict:
    if len(raw.get("comments") or []) >= 100 and raw.get("_comments_complete") is not True:
        return {"phase": "invalid", "error": "possibly incomplete lifecycle history; keep the item held"}
    current = {}
    for comment in raw.get("comments") or []:
        body = comment.get("body") or ""
        if not body.startswith("<!-- pulse:lifecycle "):
            continue
        authority = trusted(comment)
        if authority is False:
            continue
        try:
            match = MARK.match(body)
            event = json.loads(match.group(1)) if match else None
            author = (comment.get("author") or {}).get("login", "")
            if authority is not True or comment.get("edited") or comment.get("lastEditedAt") or \
                    comment.get("includesCreatedEdit") or \
                    not isinstance(event, dict) or event.get("v") != 1 or \
                    not re.fullmatch(r"[a-f0-9]{32}", event.get("id", "")) or \
                    event.get("action") not in ACTIONS - {"resume"} or event.get("phase") not in PHASES or \
                    not state.LOGIN.fullmatch(event.get("actor", "")) or \
                    not isinstance(event.get("holder"), dict) or not isinstance(event.get("work"), dict) or \
                    type(event.get("hold_before")) is not bool or type(event.get("retained")) is not bool:
                raise ValueError("unverifiable lifecycle event")
            if event["phase"] == "requested":
                if event["actor"] != author:
                    raise ValueError("request author does not match")
                if event.get("previous", "") != current.get("id", "") or \
                        current.get("phase") in ("requested", "stopped"):
                    continue
            else:
                if not current or event["id"] != current.get("id"):
                    continue
                if any(event.get(key) != current.get(key) for key in ("action", "actor", "holder")):
                    raise ValueError("operation identity changed")
                if event["phase"] == "resumed":
                    if current["phase"] != "paused" or current["action"] != "defer":
                        raise ValueError("resume without a completed defer")
                elif event["phase"] in ("stopped", "paused", "discarded"):
                    allowed = current["holder"].get("author") or current["actor"]
                    if author != allowed or current["phase"] in ("resumed", "discarded"):
                        raise ValueError("stop was not acknowledged by its holder")
            current = event
        except (ValueError, TypeError, KeyError):
            return {"phase": "invalid", "error": "unverifiable lifecycle history; keep the item held"}
    return current


def blocked(raw, trusted=state._owner) -> bool:
    current = operation(raw, trusted)
    return state.HOLD in {label.get("name") for label in raw.get("labels", [])} or \
        bool(current and current.get("phase") != "resumed")


def current(root, repo, number, run=state.gh):
    """Canonical stop state, with conservative legacy history before migration."""
    from pulse import shared
    item = shared.read(root)[1]["items"].get(str(number))
    if item is None:
        return operation(_read(repo, number, run), trusted(repo, run))
    claim, stop = item.get("claim") or {}, item.get("stop") or {}
    stopped_claim = claim if claim.get("holder") == stop.get("holder") else {}
    requested = stop.get("status") == "requested"
    return {"action": "defer", "phase": "requested" if requested else "paused" if item["hold"] else "resumed",
            "holder": {"id": stopped_claim.get("session") or stop.get("holder", ""),
                       "claim": stop.get("holder", ""), "author": stopped_claim.get("actor", "")},
            "work": stop.get("work") or item.get("work") or {}, "revision": item["revision"],
            "retained": bool(stop.get("work") or item.get("work")), "error": ""}


def _actor(repo, run):
    login = run(["api", "user", "--jq", ".login"]).strip()
    if not state.can_push(repo, login, run):
        raise state.StateError("repository push permission is required")
    return login


def _read(repo, number, run):
    raw = json.loads(run(["issue", "view", str(number), "--repo", repo, "--json",
                          "number,title,state,stateReason,labels,assignees,comments,parent,blockedBy,blocking,body,updatedAt"]))
    return state.complete_comments(repo, raw, run)


def _hold_event(repo, number, run):
    events = state.pages(run, f"repos/{repo}/issues/{number}/events?per_page=100")
    return next(({"id": event.get("id"), "event": event.get("event"),
                  "actor": (event.get("actor") or {}).get("login")}
                 for event in reversed(events) if (event.get("label") or {}).get("name") == state.HOLD and
                 event.get("event") in ("labeled", "unlabeled")), {})


def _git(root, *args):
    try:
        result = ready.net_git(root, *args) if args[0] == "ls-remote" else \
            subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise state.StateError("cannot verify preserved work: git did not answer") from None
    if result.returncode:
        raise state.StateError("cannot verify preserved work: " + (result.stderr.strip() or "git refused the read"))
    return result.stdout.strip()


def _remote(root, branch, head):
    try:
        remote = _git(root, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}")
        return remote.split()[0] == head
    except (state.StateError, subprocess.TimeoutExpired, IndexError):
        return False


def _work(root, worktree, branch, remote=True):
    path = Path(worktree)
    if not path.is_absolute() or path.is_symlink() or str(path.resolve()) != str(path) or \
            not branch or branch.startswith("-"):
        raise state.StateError("a preserved worktree and branch must be unambiguous")
    common = config.common_dir(Path(root)).resolve()
    if config.common_dir(path).resolve() != common or \
            str(path) not in re.findall(r"^worktree (.+)$", _git(root, "worktree", "list", "--porcelain"), re.M) or \
            _git(path, "branch", "--show-current") != branch:
        raise state.StateError("the original branch must remain in its registered worktree")
    head = _git(path, "rev-parse", "HEAD")
    dirty = bool(_git(path, "status", "--porcelain", "--untracked-files=all"))
    return {"worktree": str(path), "common": str(common), "branch": branch, "head": head,
            "dirty": dirty, "remote": bool(remote and not dirty and _remote(root, branch, head))}


def queue_stop(root, number, who, worktree, branch):
    """Keep a factual acknowledgement after the caller confirmed physical process end."""
    from pulse import actions
    token = state._claim_id(who, number, root)
    rows = [row for row in actions.pending(root) if row["item"] == number]
    existing = next((row for row in rows if row["kind"] == "stopped" and
                     row["payload"].get("holder") == token), None)
    if existing:
        actions.start(root)
        return existing
    if state.item_of(branch) != number:
        raise state.StateError("the preserved branch must belong to this item")
    work = _work(root, worktree, branch, remote=False)
    observed = next((row for row in state.cached(root) if row["number"] == number), {})
    accepted = actions.submit(root, number, "stopped", {"holder": token, "work": work}, observed.get("revision", ""))
    actions.start(root)
    return accepted


def _resume_work(root, current, actor):
    work = current.get("work") or {}
    if not work:
        return {}
    if work.get("common") == str(config.common_dir(Path(root)).resolve()):
        preserved = _work(root, work.get("worktree", ""), work.get("branch", ""))
        if (current.get("retained") or not preserved["remote"]) and current.get("holder", {}).get("author") != actor:
            raise state.StateError("the original holder must resume its retained worktree")
        return preserved
    if current.get("retained") or not work.get("remote") or \
            not _remote(root, work.get("branch", ""), work.get("head", "")):
        raise state.StateError("another clone needs a secured remote handover; preserve the original worktree")
    return work


def _interactive_work(root, raw, current, actor):
    marks = state._marks(raw)
    holder = current.get("holder", {}) if current.get("phase") in ("requested", "stopped", "paused") else \
        (marks[0] if marks else {})
    if holder.get("author") != actor or not holder.get("id", "").startswith(("claude:", "codex:")) or \
            [assignee["login"] for assignee in raw.get("assignees", [])] != [actor]:
        return {}
    candidates = []
    for block in _git(root, "worktree", "list", "--porcelain", "-z").split("\0\0"):
        fields = dict(field.split(" ", 1) for field in block.split("\0") if " " in field)
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if state.item_of(branch) == raw["number"]:
            candidates.append((fields.get("worktree", ""), branch))
    return _work(root, *candidates[0]) if len(candidates) == 1 else {}


def preview(root, repo, number, action, run=state.gh) -> dict:
    if type(number) is not int or number <= 0 or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise state.StateError("a repository and positive item number are required")
    if action not in ACTIONS:
        raise state.StateError("unknown lifecycle action")
    if action in {"defer", "resume"}:
        actor = _actor(repo, run)
        entry = next((entry for entry in state.load(root, repo, run=run, fresh=True)
                      if entry["number"] == number), None)
        if not entry:
            raise state.StateError("only open work can be deferred or resumed")
        if entry.get("type") not in state.WORK:
            raise state.StateError("select a feature, improvement or fix; no epic cascade")
        return {"repo": repo, "number": number, "action": action, "actor": actor,
                "revision": entry.get("revision", ""), "confirmation": action,
                "record": entry, "work": entry.get("work") or {},
                "lines": [f"#{number}: {entry['title']}",
                          "Defer requests a stop and preserves work." if action == "defer" else
                          "Resume waits for the writer to stop and preserves other holds."]}
    actor = _actor(repo, run)
    raw = _read(repo, number, run)
    if raw.get("number") != number or raw.get("state") not in ("OPEN", "CLOSED"):
        raise state.StateError("GitHub did not verify the selected item")
    if len(raw.get("assignees") or []) > 1:
        raise state.StateError("multiple assignees require separate holder coordination before a lifecycle change")
    if not {f"pulse:{kind}" for kind in state.WORK} & {label["name"] for label in raw.get("labels", [])}:
        raise state.StateError("select a feature, improvement or fix; no epic cascade")
    current = operation(raw, trusted(repo, run))
    if current.get("phase") == "invalid":
        raise state.StateError(current["error"])
    if action in ("defer", "resume") and raw.get("state") != "OPEN":
        raise state.StateError("only open work can be deferred or resumed")
    hold = _hold_event(repo, number, run)
    work = {}
    if action == "resume":
        if current.get("action") != "defer" or current.get("phase") not in ("paused", "resumed"):
            raise state.StateError("resume requires a completed defer pause")
        held = state.HOLD in {label["name"] for label in raw.get("labels", [])}
        if current["phase"] == "paused" and held and \
                (current.get("hold_before") or not current.get("hold_event") or hold != current["hold_event"]):
            raise state.StateError("an unrelated or unverifiable hold remains; resume cannot remove it")
        if current["phase"] == "paused":
            work = _resume_work(root, current, actor)
    elif current.get("phase") in ("requested", "stopped") and current.get("action") != action:
        raise state.StateError("the current stop request must finish first")
    if action == "defer":
        work = _interactive_work(root, raw, current, actor)
    parents = []
    if (raw.get("parent") or {}).get("number"):
        parents.append(_read(repo, raw["parent"]["number"], run))
    bound = {"item": raw,
             "parents": parents, "actor": actor, "hold": hold, "work": work, "action": action, "repo": repo}
    snapshot = hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()
    consequences = {"defer": "Stop work and keep code, specs, PRs, approvals and notes as-is in the paused backlog.",
                    "resume": "Resume the preserved work explicitly; existing approval and SHA checks still apply.",
                    "discard": "Stop work, then close as not planned. Keep files, PRs and history; no code rollback.",
                    "delete": "Prepare a controlled stop for code rollback, spec/reference removal and irreversible "
                              "deletion of the issue and all comments. Dependent features and open work need review; "
                              "a removal PR and a separate merge approval are required before issue deletion."}
    lines = [f"{repo}#{number}: {raw['title']} ({raw['state']}); acting as @{actor}", consequences[action],
             "Holders: " + (", ".join(assignee["login"] for assignee in raw.get("assignees", [])) or "none"),
             "Affected records: " + ", ".join(f"#{entry['number']}" for entry in [raw, *parents])]
    if action == "defer" and work:
        lines += ["Confirm that your original interactive session has stopped before releasing its claim.",
                  f"Preserve local work in {work['worktree']} on {work['branch']}; no files are changed."]
    return {"repo": repo, "number": number, "action": action, "actor": actor, "snapshot": snapshot,
            "confirmation": f"{repo}#{number}" if action == "delete" else
                            "defer stopped" if action == "defer" and work else action, "lines": lines,
            "record": raw, "work": work}


def _append(root, repo, number, event, run):
    run(["issue", "comment", str(number), "--repo", repo, "--body",
         "<!-- pulse:lifecycle " + json.dumps(event, sort_keys=True) + " -->\n" +
         f"{event['action']}: {event['phase']} ({event['id']}). Work, approvals and notes are preserved."])
    state.drop_cache(Path(root))
    actual = operation(_read(repo, number, run), trusted(repo, run))
    if actual.get("id") != event["id"] or actual.get("phase") != event["phase"]:
        raise state.StateError("another lifecycle operation won; read a fresh preview")


def _ensure_hold(root, repo, number, raw, current, run):
    added = state.HOLD not in {label["name"] for label in raw.get("labels", [])}
    if added:
        try:
            run(["issue", "edit", str(number), "--repo", repo, "--add-label", state.HOLD])
        except state.StateError:
            labels = state.pages(run, f"repos/{repo}/labels?per_page=100")
            if any(label.get("name") == state.HOLD for label in labels):
                raise
            from pulse import setup
            color, description = setup.LABELS[state.HOLD]
            run(["label", "create", state.HOLD, "--repo", repo, "--color", color, "--description", description])
            run(["issue", "edit", str(number), "--repo", repo, "--add-label", state.HOLD])
        state.drop_cache(Path(root))
    held = _hold_event(repo, number, run)
    if held.get("actor") not in (current["actor"], current["holder"].get("author")) or \
            not added and current.get("hold_event") and current["hold_event"] != held:
        current = {**current, "hold_before": True}
    return {**current, "hold_event": held}


def _finish(root, repo, number, current, run, who=None):
    raw = _read(repo, number, run)
    current = _ensure_hold(root, repo, number, raw, current, run)
    if not current["holder"] and (raw.get("assignees") or state._marks(raw)):
        raise state.StateError("a holder arrived during the stop request; keep the operation pending")
    if current["holder"] and (not current["retained"] or current["action"] == "defer") and \
            (raw.get("assignees") or state._marks(raw)):
        work = current["work"]
        if _work(root, work["worktree"], work["branch"]) != work:
            raise state.StateError("work changed after the stop acknowledgement; keep the claim and acknowledge again")
        released, why = state.release(Path(root), repo, number, run=run, who=who)
        if not released:
            raise state.StateError("stop acknowledged; claim remains: " + why)
        if _read(repo, number, run).get("assignees"):
            raise state.StateError("another holder remains; the operation stays stopped")
    if current["action"] == "discard":
        if current["retained"]:
            return f"#{number} stopped; claim retained until a safe handover permits discarding"
        if raw.get("state") == "CLOSED":
            run(["api", "-X", "PATCH", f"repos/{repo}/issues/{number}", "-f", "state=closed", "-f", "state_reason=not_planned"])
        else:
            run(["issue", "close", str(number), "--repo", repo, "--reason", "not planned"])
        phase = "discarded"
    else:
        phase = "paused"
    _append(root, repo, number, {**current, "phase": phase}, run)
    return f"#{number} {phase}" + (("; worktree retained for local resume" if current["action"] == "defer" else
                                   "; worktree and claim retained for local resume") if current["retained"] else "")


def apply(root, repo, planned, confirmation, run=state.gh) -> str:
    if not confirmation:
        return "cancelled; nothing changed"
    if not state.holder().get("id", "").startswith("terminal:"):
        raise state.StateError("a person must confirm lifecycle actions; agents cannot apply them")
    if repo != planned.get("repo") or confirmation != planned.get("confirmation"):
        raise state.StateError("confirmation does not match the preview")
    number, action = planned["number"], planned["action"]
    if action in {"defer", "resume"}:
        from pulse import actions
        accepted = actions.submit(root, number, action, {}, planned.get("revision", ""))
        actions.start(root)
        return f"#{number} {action} queued locally ({accepted['id']}); shared confirmation pending"
    fresh = preview(root, repo, number, action, run)
    if fresh != planned:
        raise state.StateError("state changed after the preview; confirm a fresh preview")
    raw = fresh["record"]
    current = operation(raw, trusted(repo, run))
    if action == "resume":
        if current["phase"] == "resumed":
            return f"#{number} already resumed; other holds are unchanged"
        if state.HOLD in {label["name"] for label in raw.get("labels", [])}:
            run(["issue", "edit", str(number), "--repo", repo, "--remove-label", state.HOLD])
        _append(root, repo, number, {**current, "phase": "resumed", "work": fresh["work"]}, run)
        return f"#{number} resumed from its preserved work"
    if current.get("action") == action and current.get("phase") in ("paused", "discarded"):
        if action == "defer" and fresh["work"] and current.get("retained"):
            return acknowledge(root, repo, number, {"id": current["holder"]["id"]},
                               fresh["work"]["worktree"], fresh["work"]["branch"], run=run)
        return f"#{number} already {current['phase']}"
    if current.get("phase") not in ("requested", "stopped"):
        marks = state._marks(raw)
        assignees = [assignee["login"] for assignee in raw.get("assignees", [])]
        original = next((mark for mark in marks if mark["author"] in assignees), marks[0] if marks else None)
        holder = {key: original[key] for key in ("id", "author")} if original else \
            ({"id": "", "author": assignees[0]} if assignees else {})
        current = {"v": 1, "id": uuid.uuid4().hex, "previous": current.get("id", ""), "action": action,
                   "phase": "requested", "actor": fresh["actor"], "holder": holder,
                   "hold_before": current.get("hold_before", False) if current.get("phase") == "paused" else
                                  state.HOLD in {label["name"] for label in raw.get("labels", [])},
                   "hold_event": current.get("hold_event", {}) if current.get("phase") == "paused" else {},
                   "work": current.get("work", {}), "retained": bool(holder)}
        _append(root, repo, number, current, run)
    current = _ensure_hold(root, repo, number, _read(repo, number, run), current, run)
    if current["holder"]:
        if action == "defer" and fresh["work"]:
            return acknowledge(root, repo, number, {"id": current["holder"]["id"]},
                               fresh["work"]["worktree"], fresh["work"]["branch"], run=run)
        return f"#{number} stop requested; waiting for its original holder"
    return _finish(root, repo, number, current, run)


def acknowledge(root, repo, number, who, worktree, branch, run=state.gh) -> str:
    if not isinstance(who, dict) or not who.get("id"):
        raise state.StateError("the original holder identity is required")
    if state.item_of(branch) != number:
        raise state.StateError("the preserved branch must belong to this item")
    from pulse import shared
    canonical = shared.read(root)[1]["items"].get(str(number))
    if canonical is not None:
        token = state._claim_id(who, number, root)
        stop = canonical.get("stop") or {}
        if stop.get("holder") != token:
            raise state.StateError("only the original claim generation may acknowledge its stop")
        if stop.get("status") == "completed":
            return f"#{number} already paused"
        work = _work(root, worktree, branch)
        receipt = state._change(root, number, "stopped", {"holder": token, "work": work}, canonical["revision"])
        if receipt["status"] != "confirmed":
            raise state.StateError(receipt.get("reason") or "stop state changed")
        state.drop_cache(Path(root))
        return f"#{number} paused; work is preserved"
    actor = _actor(repo, run)
    raw = _read(repo, number, run)
    if any(assignee.get("login") != actor for assignee in raw.get("assignees", [])):
        raise state.StateError("another holder is assigned; no claim may be released")
    current = operation(raw, trusted(repo, run))
    if current.get("phase") not in ("requested", "stopped", "paused") or \
            current.get("holder", {}).get("id") != who.get("id") or \
            current.get("holder", {}).get("author") != actor:
        raise state.StateError("only the original holder can acknowledge this stop")
    if current["phase"] == "paused" and not current["retained"]:
        return f"#{number} already paused"
    if raw.get("assignees") and not state._lead(raw, who)[0] or \
            any(mark["id"] != who["id"] or mark["author"] != actor or not mark["mine"]
                for mark in state._marks(raw)):
        raise state.StateError("the original holder no longer holds this claim; nothing released")
    if current["phase"] == "requested" and not state._lead(raw, who)[0]:
        raise state.StateError("holder disappeared before acknowledging its stop")
    work = _work(root, worktree, branch)
    current = _ensure_hold(root, repo, number, raw, current, run)
    current = {**current, "work": work, "retained": not work["remote"],
               "phase": "paused" if current["phase"] == "paused" else "stopped"}
    _append(root, repo, number, current, run)
    return _finish(root, repo, number, current, run, who)
