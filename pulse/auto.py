"""Auto mode per person and gate (FEAT-03-03, #124): each person switches their own, and pulse go pulls a gate's
lever without asking only for the login whose switch is on, and only on that login's items (#125).

The source is the control issue "Pulse auto mode" (label pulse:auto), one comment per toggle with the line
`<!-- pulse:auto gate=<gate> state=on|off until=<UTC minute>|- -->`. Per login and gate its newest toggle counts,
the comment's GitHub author is the one who set it, and the issue body is an overview only (Analysis 5.2). Exactly
one open control issue counts; with two or more every gate is off. Without an explicit plan switch, trusted
own specs proceed to planning (#154). Builds wait for PLAN approval. An expired switch stays off.
The interface #125 builds on: switches, control, on, read.
"""
from __future__ import annotations

import calendar
import json
import re
import time

from pulse import config, setup, state

GATES = ("plan", "build", "merge")          # gate 1, 2, 3
LABEL, TITLE = "pulse:auto", "Pulse auto mode"
MARKERS = ("PULSE_HOLDER", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")
TOGGLE = re.compile(r"^<!-- pulse:auto gate=(plan|build|merge) state=(on|off) "
                    r"until=(-|\d{4}-\d\d-\d\dT\d\d:\d\dZ) -->$", re.M)
INTENT = re.compile(r"<!--\s*pulse:auto\b[^\r\n]*")
STAMP = "%Y-%m-%dT%H:%MZ"                   # an until: UTC to the minute
MINE = {"plan": "Your items only: issues you opened.",
        "build": "Your items only: issues you opened or claims you hold.",
        "merge": "Your items only: issues you opened or claims you hold."}
DOES = {"plan": "Gate 1 plan: pulse go running as {login} approves the specs of your items and plans them, "
                "without asking you. Never with pulse:hold.",
        "build": "Gate 2 build: pulse go running as {login} approves the plans of your items and builds them, "
                 "without asking you. Never with risk or pulse:hold.",
        "merge": "Gate 3 merge: pulse go running as {login} merges your PRs into {base} when every check on the "
                 "head is green (tests, review, audit, project CI), without asking you. Never with risk, "
                 "pulse:hold, a conflict, or changes to protected paths."}
SHORT = {"plan": "pulse go plans your items", "build": "pulse go builds your plans",
         "merge": "pulse go merges your green PRs"}
BODY = ("Auto mode of this repository, per person and gate. `pulse auto <gate> on|off` in your own terminal, or "
        "1, 2, 3 in the Pulse map, switches yours. The comments below count, the newest of each login per gate; "
        "this text is an overview only. Planning is automatic by default; builds wait for PLAN approval.\n\n")


def person(env, tty) -> bool:
    """A person's terminal (Analysis 5.3): no agent marker (pulse go's agents carry PULSE_HOLDER, Claude Code and
    Codex their session ids; CLAUDECODE is none, IDE terminals have it too) and a terminal on stdin."""
    return bool(tty) and not any(env.get(k) for k in MARKERS)


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


def switches(issue: dict, now=None) -> dict:
    """{login: {gate: {on, since, until, expired}}} from the comments of issue, oldest first: per comment author and
    gate the newest toggle (FR-04). The author set it, whatever its words say; the issue body counts for nothing.
    Once one toggle of a login's gate was edited, whoever edited it, that gate is off for good (#125); a deleted
    comment leaves no trace here, and the toggle before it counts again."""
    now = time.time() if now is None else now
    out = {}
    for c in issue.get("comments") or ():
        login, body = (c.get("author") or {}).get("login"), c.get("body") or ""
        intent, matches = INTENT.findall(body), list(TOGGLE.finditer(body))
        if not login or not intent:
            continue
        malformed = len(intent) != 1 or len(matches) != 1
        gates = set(re.findall(r"\bgate=(plan|build|merge)\b", "\n".join(intent))) or set(GATES)
        for gate in gates:
            edited = c.get("edited") or (out.get(login, {}).get(gate) or {}).get("edited", False)
            since = c.get("createdAt") or ""
            if malformed or edited:
                out.setdefault(login, {})[gate] = {"on": False, "since": since, "until": None,
                                                   "expired": False, "edited": bool(edited)}
                continue
            m = matches[0]
            st, until = m.group(2), None if m.group(3) == "-" else m.group(3)
            over = st == "on" and until is not None and _epoch(until) <= now
            out.setdefault(login, {})[gate] = {"on": st == "on" and not over and _epoch(since) > 0,
                                               "since": since, "until": until, "expired": over}
    return out


def _setting(gates: dict, gate: str):
    """A missing plan choice delegates planning; a present invalid choice remains off."""
    if not isinstance(gates, dict):
        return None
    if gate == "plan" and gate not in gates:
        return {"on": True, "since": "", "until": None, "expired": False, "default": True}
    return gates.get(gate)


def on(switches: dict, login: str, gate: str, now=None):
    """An active switch, or default plan delegation when never configured; otherwise None. Callers check read's
    why first. Another login's explicit choice never counts for this login (SC-01)."""
    gates = switches.get(login, {}) if isinstance(switches, dict) and login else None
    s = _setting(gates, gate)
    now = time.time() if now is None else now
    if not isinstance(s, dict) or s.get("on") is not True or s.get("expired") is not False or s.get("edited"):
        return None
    if "until" not in s or (gate != "plan" or gate in gates) and _epoch(s.get("since")) <= 0:
        return None
    return s if s["until"] is None or _epoch(s["until"]) > now else None


def control(issues) -> tuple:
    """(n, "") when exactly one open issue carries pulse:auto, (None, "") without one, (None, why) with more: then
    every gate is off for everyone until a person closes all but one (FR-06)."""
    found = sorted({i["number"] for i in issues})
    if len(found) < 2:
        return (found[0] if found else None), ""
    return None, (f"auto off: {'two' if len(found) == 2 else len(found)} auto issues "
                  f"{' '.join(f'#{n}' for n in found)}, close {'one' if len(found) == 2 else 'all but one'}")


def read(root, repo=None, run=None, fresh=False, ttl=state.TTL) -> dict:
    """{"issue", "why", "switches"} as of now: from auto.json in the cache folder while it is younger than ttl, else
    from GitHub; fresh reads GitHub past the cache, as pulse go does before each lever. repo None: the cache alone, as
    the hooks read it. Offline, a read that is not fresh keeps the last answer."""
    path = state.cache_dir(root) / "auto.json"
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = None
    known = isinstance(kept, dict) and repo in (None, kept.get("repo"))
    if known and not fresh and time.time() - kept.get("at", 0) < ttl:
        return _seen(kept)
    try:
        if not repo:
            raise state.StateError("no auto switches read here yet")
        run = run or state.gh
        n, why = control(json.loads(run(["issue", "list", "--repo", repo, "--label", LABEL, "--state", "open",
                                         "--json", "number"]) or "[]"))
        comments = [{"author": {"login": (c.get("user") or {}).get("login")}, "body": c.get("body") or "",
                     "createdAt": c.get("created_at"), "edited": c.get("updated_at") not in (None, c.get("created_at"))}
                    for c in (state.pages(run, f"repos/{repo}/issues/{n}/comments?per_page=100") if n else ())
                    if INTENT.search(c.get("body") or "")]
    except (state.StateError, ValueError) as e:
        if fresh or not known:
            raise state.StateError(str(e)) from None
        return _seen(kept)
    kept = {"repo": repo, "at": time.time(), "issue": n, "why": why, "comments": comments}
    state._keep(path, kept)
    return _seen(kept)


def _seen(kept: dict) -> dict:
    why = kept.get("why") or ""
    if any(not (c.get("author") or {}).get("login") for c in kept.get("comments") or ()):
        why = why or "auto off: a toggle has no identifiable author"
    return {"issue": kept.get("issue"), "why": why, "switches": switches(kept)}


def toggle(root, repo: str, gate: str, switch_on: bool, until=None, run=None) -> str:
    """Write the toggle for the login gh runs as. The first on or plan/build off creates the control issue and pins it
    where a slot is free; the body becomes the overview. Returns what happened, in one line."""
    run = run or state.gh
    login, note = state.me(root, run=run), ""
    seen = read(root, repo, run=run, fresh=True)
    if seen["why"]:
        raise state.StateError(seen["why"])
    n = seen["issue"]
    if n is None and not switch_on and gate not in ("plan", "build"):
        return f"{gate} is off: nobody switched auto mode on in {repo}"
    if n is None:
        color, desc = setup.LABELS[LABEL]     # a repository set up before #124 lacks it
        run(["label", "create", LABEL, "--repo", repo, "--color", color, "--description", desc, "--force"])
        n = int(run(["issue", "create", "--repo", repo, "--title", TITLE, "--label", LABEL, "--body", BODY])
                .strip().splitlines()[-1].rstrip("/").rsplit("/", 1)[-1])
        try:
            run(["issue", "pin", str(n), "--repo", repo])
        except state.StateError as e:
            note = f"; #{n} is not pinned ({e}), the switches work all the same"
    word, until = ("on", until) if switch_on else ("off", None)
    run(["issue", "comment", str(n), "--repo", repo, "--body",
         f"@{login} switched gate {GATES.index(gate) + 1} {gate} {word}" + (f" until {until}" if until else "") +
         f"\n<!-- pulse:auto gate={gate} state={word} until={until or '-'} -->"])
    try:
        run(["issue", "edit", str(n), "--repo", repo, "--body", overview(read(root, repo, run=run, fresh=True)["switches"])])
    except state.StateError:
        pass                                  # the body only shows them: a lost update there changes nothing
    return f"{gate} {word} for your items as @{login}" + (f" until {when(until)}" if until else "") + f" (#{n}){note}"


def overview(switches: dict) -> str:
    return BODY + "\n".join(f"- @{login}: " + ", ".join(f"{g} " + ("auto" if
                                                         (s or {}).get("default") else
                                                         "on" if (s or {}).get('on') else "off") +
                                                         (f" until {s['until']}" if (s or {}).get("on") and s["until"]
                                                          else "") for g in GATES for s in [_setting(gates, g)])
                            for login, gates in sorted(switches.items(), key=lambda x: x[0].lower()))


def when(at: str, now=None) -> str:
    """A time of GitHub's (UTC) as this machine tells it: 18:00 today, else 29.09. 02:10."""
    t, today = time.localtime(_epoch(at)), time.localtime(time.time() if now is None else now)
    return time.strftime("%H:%M" if t[:3] == today[:3] else "%d.%m. %H:%M", t)


def word(s, since=False) -> str:
    """on, on until 18:00, on since 10:12 (since), off, or off (expired 02:10) (FR-07)."""
    if s and s.get("default"):
        return "auto"
    if s and s["expired"]:
        return f"off (expired {when(s['until'])})"
    if not s or not s["on"]:
        return "off"
    return f"on until {when(s['until'])}" if s["until"] else f"on since {when(s['since'])}" if since and s["since"] \
        else "on"


def line(gates: dict, since=False, only_on=False, sep="  ") -> str:
    """The three gates including the plan default; only_on leaves out the gates that are off."""
    return sep.join(f"{k} {g} {word(s, since)}" for k, g in enumerate(GATES, 1) for s in [_setting(gates, g)]
                     if not only_on or (s or {}).get("on"))


def show(root, repo: str, run=None) -> str:
    """What pulse auto prints: every login's switches with since and until, yours first (FR-08)."""
    run = run or state.gh
    login, seen = state.me(root, run=run), read(root, repo, run=run)
    base = config.load(root)["base_branch"] or config.default_branch(root)
    rows = [f"{repo}, base {base}, you are {state.who(root, login)}"]
    if seen["why"]:
        return "\n".join(rows + [seen["why"]])
    others = sorted((l for l in seen["switches"] if l != login), key=str.lower)
    w = max([3] + [len(l) + 1 for l in others])
    rows += [f"{'you':<{w}}  {line(seen['switches'].get(login, {}), since=True)}"]
    rows += [f"{'@' + l:<{w}}  {line(seen['switches'][l], since=True)}" for l in others]
    return "\n".join(rows + ["Auto levers act only in your own pulse go and only on your own items."])


def explain(gate: str, login: str, base: str, until=None) -> str:
    """What happens from now on without asking, for which items, as whom (FR-01): printed before the question."""
    return "\n".join([DOES[gate].format(login=f"@{login}", base=base), MINE[gate],
                      "Other people's switches never act for you.",
                      f"Until {when(until)}." if until else
                      f"Until you switch it off: pulse auto {gate} off, or {GATES.index(gate) + 1} in the Pulse map."])


def short(gate: str, switch_on: bool, login: str) -> str:
    """The map's confirmation of 1, 2, 3 (FR-09): gate, effect, and login, in a line or two of 44 columns."""
    k = GATES.index(gate) + 1
    return f"{k} {gate} on: {SHORT[gate]}, as @{login}?" if switch_on else \
        f"{k} {gate} off: pulse go asks you again, as @{login}?"


def said(seen: dict, login: str) -> str:
    """The SessionStart sentence (FR-08): your switches, then the others' that are on."""
    if seen["why"]:
        return f"Auto mode: {seen['why']}."
    mine = seen["switches"].get(login, {})
    others = [f"@{l} {line(gates, only_on=True)}" for l, gates in sorted(seen["switches"].items())
              if l != login and any(s["on"] for s in gates.values())]
    return "Your auto mode: " + ", ".join(f"{g} {word(_setting(mine, g))}" for g in GATES) + "." + \
        (" Others, for their own items only: " + "; ".join(others) + "." if others else "")
