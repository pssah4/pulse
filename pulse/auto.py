"""Automatic completion by default, with explicit personal policy overrides and fresh integration rights."""
from __future__ import annotations

import calendar
import json
import os
import re
import time
import uuid

from pulse import config, state

GATES = ("merge",)
MARKERS = ("PULSE_HOLDER", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")
STAMP = "%Y-%m-%dT%H:%MZ"
POLICY = "Integration approval is required for each result and base commit."
DETAIL = "Automatic integration by default after the required checks pass. A person with repository write access may choose manual approval."
PREFIX = "pulse final approval policy "
CONTROL = "Pulse integration approval policy"


def person(env, tty) -> bool:
    """A person's terminal (Analysis 5.3): no agent marker (pulse go's agents carry PULSE_HOLDER, Claude Code and
    Codex their session ids; CLAUDECODE is none, IDE terminals have it too) and a terminal on stdin."""
    return bool(tty) and not any(env.get(k) for k in MARKERS)


def nested(env) -> str:
    """Why a runner, a Plan publication, or a map beside a session may not start here, else "": pulse go's own
    agents carry PULSE_HOLDER, and a Claude Code session nobody attends (claude -p, background) has
    CLAUDE_CODE_SESSION_ATTENDED=0. Claude Code gives every process of every session CLAUDE_CODE_CHILD_SESSION=1
    (#183); without the attended flag that still counts as a child session, as before."""
    if env.get("PULSE_HOLDER"):
        return "a runner agent"
    attended = env.get("CLAUDE_CODE_SESSION_ATTENDED")
    if attended is not None:
        return "" if attended == "1" else "an unattended session"
    return "a child session" if env.get("CLAUDE_CODE_CHILD_SESSION") else ""


def span(text: str) -> int:
    """--for: the seconds of <n>h or <n>d."""
    m = re.fullmatch(r"([1-9]\d*)([hd])", text.strip().lower())
    if not m:
        raise ValueError(f"{text}: hours or days, as 8h or 2d")
    return int(m.group(1)) * (3600 if m.group(2) == "h" else 86400)


def stamp(epoch: float) -> str:
    return time.strftime(STAMP, time.gmtime(epoch))


def _epoch(at: str) -> float:
    for form in ("%Y-%m-%dT%H:%M:%SZ", STAMP):
        try:
            return calendar.timegm(time.strptime(at, form))
        except (ValueError, TypeError):
            pass
    return 0.0                                # a date that is none (month 13): long run out


def on(switches: dict, login: str, gate: str, now=None):
    """No historical automatic setting grants approval for a concrete result."""
    return None


def active(policy):
    return policy.get("mode") == "automatic" and bool(policy.get("revision")) and \
        (policy.get("until") is None or _epoch(policy["until"]) > time.time())


def _cache(root, value=None):
    from pulse import actions, shared
    with actions._database(root) as db:
        db.execute("CREATE TABLE IF NOT EXISTS policy_cache (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        if value is not None:
            db.execute("INSERT OR REPLACE INTO policy_cache VALUES (0, ?)", (json.dumps(value),))
        row = db.execute("SELECT body FROM policy_cache WHERE id=0").fetchone()
    try:
        cached = json.loads(row[0]) if row else shared.policy({})
        shared._policy(cached)
        if cached == {"revision": "", "mode": "manual", "proof": None, "until": None}:
            return shared.policy({})          # the former unbound default, never a person's saved override
        return cached
    except (ValueError, TypeError, state.StateError):
        return shared.policy({})


def read(root, repo=None, run=None, fresh=False, ttl=state.TTL) -> dict:
    """A local view by default. A fresh shared read never imports historical issue switches."""
    from pulse import actions, shared
    policy = _cache(root, shared.policy(shared.read(root)[1])) if fresh else _cache(root)
    rows = [row for row in actions.pending(root) if row["kind"] == "policy"]
    confirmed = max((row["seq"] for row in rows if row["status"] == "confirmed"), default=0)
    pending = [row for row in rows if row["status"] != "confirmed"]
    blocked = any(row["seq"] > confirmed and row["payload"].get("mode") == "manual" for row in pending)
    return {"policy": policy, "pending": pending, "blocked": blocked, "why": "", "switches": {},
            "issue": (policy.get("proof") or {}).get("issue")}


def toggle(root, repo: str, gate: str, switch_on: bool, until=None, run=None, *, expected=None) -> dict:
    from pulse import actions, levers
    if not levers.may(root, os.environ, "auto"):        # a person, or a session under their grant (#197)
        raise state.StateError("only a person may change integration approval policy")
    if gate != "merge" or type(switch_on) is not bool or until is not None and (
            not switch_on or _epoch(until) <= time.time()):
        raise state.StateError("invalid final approval policy or expiration")
    return actions.submit(root, 0, "policy", {"mode": "automatic" if switch_on else "manual", "until": until},
                          read(root)["policy"]["revision"] if expected is None else expected)


def body(operation):
    return PREFIX + json.dumps({"operation": operation["id"], "mode": operation["payload"]["mode"],
                                "until": operation["payload"].get("until")}, sort_keys=True, separators=(",", ":"))


def proof(root, repo, operation, actor, run):
    """Use an existing control issue or create one; only our new immutable comment grants authority."""
    from pulse import shared
    policy = shared.policy(shared.read(root)[1])
    issue = (policy.get("proof") or {}).get("issue")
    if not issue:
        matches = state.issues(repo, run, "all", "number,title", search=CONTROL + " in:title")
        matches = [i for i in matches if i.get("title") == CONTROL]
        if len(matches) > 1:
            raise state.StateError("approval policy control issue is ambiguous")
        issue = matches[0]["number"] if matches else json.loads(run([
            "api", "-X", "POST", f"repos/{repo}/issues", "-f", "title=" + CONTROL,
            "-f", "body=Repository-wide final approval overrides. Only confirmed policy actions change the default."
        ]))["number"]
    result = state._action_proof(repo, operation, actor, run, issue=issue, body=body(operation))
    return {**result, "issue": issue}


def authority(root, repo, policy, run=None):
    """Check delegation afresh, including local pending off, exact comment, current rights and expiration."""
    from pulse import shared
    if not active(policy):
        return "automatic integration approval is disabled or expired"
    if read(root)["blocked"]:
        return "local policy off is awaiting synchronization"
    run = state.gh if run is None else run
    if policy == shared.DEFAULT_POLICY:
        actor = run(["api", "user", "--jq", ".login"]).strip()
        return "" if actor and state.can_push(repo, actor, run) else "current integration account lacks write access"
    proof = policy.get("proof") or {}
    comment = json.loads(run(["api", f"repos/{repo}/issues/comments/{proof.get('comment')}"]))
    actor = (comment.get("user") or {}).get("login")
    operation = {"id": policy["revision"], "payload": policy}
    if (not actor or actor != proof.get("author") or proof.get("operation") != policy["revision"]
            or comment.get("id") != proof.get("comment") or (comment.get("user") or {}).get("type", "User") != "User"
            or comment.get("issue_url") != f"https://api.github.com/repos/{repo}/issues/{proof.get('issue')}"
            or not comment.get("created_at") or comment.get("updated_at") != comment["created_at"]
            or any(comment.get(k) for k in ("edited", "lastEditedAt", "includesCreatedEdit"))
            or comment.get("body") != body(operation) or not state.can_push(repo, actor, run)):
        return "approval policy proof changed or its author lacks current write access"
    return ""


def approve(root, repo, item, run=None):
    """The supervisor delegates to the ordinary reducer; a queue or cached policy grants no approval."""
    from pulse import actions, merge, ready, shared
    run = state.gh if run is None else run
    _, snapshot = shared.read(root)
    current, policy = snapshot["items"].get(str(item["number"]), {}), shared.policy(snapshot)
    _cache(root, policy)
    why = "automatic approval excludes held, failed, revoked or removal work" if (
        current.get("hold") or current.get("failed") or current.get("removal") or current.get("revoked")
        or actions.integration_held(root, item["number"])) else ""
    why = why or ready.result_reason(root, {**current, "number": item["number"]}) or authority(root, repo, policy, run)
    result = current.get("result") or {}
    why = why or merge.evidence(root, result["head"], ("tests", "review", "audit"))
    if why:
        return {"status": "waiting", "why": why}
    approval = current.get("approval") or {}
    if approval and (not approval.get("policy") or approval["policy"] == policy["revision"]):
        return {"status": "confirmed", "data": current}
    operation = {"id": uuid.uuid5(uuid.NAMESPACE_URL, f"{repo}:{item['number']}:{current['revision']}:{policy['revision']}").hex,
                 "item": item["number"], "kind": "autoapprove", "expected": current["revision"],
                 "payload": {"head": result["head"], "base": result["base"], "policy": policy["revision"]}}
    return shared.update(root, operation)


def line(gates: dict, since=False, only_on=False, sep="  ") -> str:
    policy = gates.get("policy", gates)
    proof = policy.get("proof") or {}
    text = "automatic final approval" if active(policy) else "manual integration approval required"
    return text + (f", set by {proof['author']} ({policy['revision'][:8]})" if proof.get("author") else "")


def show(root, repo: str = "", run=None) -> str:
    branch = config.load(root)["base_branch"] or config.default_branch(root)
    seen = read(root, repo, run=run)
    pending = "\nPolicy synchronization pending" if seen["pending"] else ""
    return f"{repo or 'This repository'}, base {branch}\n{line(seen)}\n{DETAIL}{pending}"


def explain(gate: str, login: str, base: str, until=None) -> str:
    return POLICY + " " + DETAIL


def short(gate: str, switch_on: bool, login: str) -> str:
    return POLICY


def said(seen: dict, login: str) -> str:
    return POLICY + " " + DETAIL


def when(at: str, now=None) -> str:
    t, today = time.localtime(_epoch(at)), time.localtime(time.time() if now is None else now)
    return time.strftime("%H:%M" if t[:3] == today[:3] else "%d.%m. %H:%M", t)
