"""The Pulse map: who is doing what, what is ready, what goes out next.

One renderer for every surface: the terminal (`pulse map`, `pulse status`)
prints these lines, and the demo page of the docs converts the very same
lines to HTML (serve.py). The map is as wide as its terminal (D-45).
render() is pure; gather() reads the world.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from pulse import archmap, config, dispatch, go, mapstart, presence, ready, setup, spec, state

WIDTH = 80                      # columns without a terminal, and of the demo page and the GIF (D-45)
FEWEST, MOST = 60, 160          # the map follows its terminal's width within these
STATE = .45                     # the most of a line a state takes when its title needs the rest
ANSI = re.compile(r"\033\[[0-9;]*m|\033\]8;;[^\033]*\033\\")     # colors, and terminal links (OSC 8)
DOT = {"working": ("●", "32"), "error": ("●", "31"), "waiting": ("●", "33"), "idle": ("●", "90")}
RANK = ("error", "waiting", "working", "idle")
ROWS_SHOWN = 40                 # the ramp lists all open work; past this, a count
REFRESH = 2                     # seconds between two reads of the board in the live map
TICK = 0.5                      # seconds per frame of the live map
UPGRADE = 60                    # seconds between two looks for a newer Pulse than the live map runs
DAY = 24 * 3600                 # how long the answer about the newest release holds
RELEASES = "https://github.com/pssah4/pulse.git"      # its tags v* are the released versions
UPDATE = ("Pulse {v} is out, this map runs {own}. Claude Code: with auto-update on it comes by itself, "
          "else claude plugin marketplace update pssah4-skills, then claude plugin update pulse@pssah4-skills. "
          "Codex: codex plugin marketplace upgrade pssah4-skills, then codex plugin add pulse@pssah4-skills")
BREATH = (1, .8, .6, .45, .6, .8)   # a working light's brightness per frame: one breath in 3 s (D-38)
GREEN, DARK = (46, 229, 157), (13, 17, 23)   # that light at full brightness, and what it fades toward
TRUE = 1 << 24                  # the colors of a truecolor terminal; 256 and 16 for the others
# the signet beside the header, as docs/public/assets/pulse-icon.ansi draws it in 256 colors
SIGNET = ('\033[0m \033[38;5;37m▀▀▀▀▀▀▜▄\033[0m',
          '\033[0m \033[38;5;30m▟\033[38;5;31m▛▀\033[38;5;37m▀▀▀▐█▌\033[0m',
          '\033[0m \033[38;5;30m▄██\033[38;5;31m███▛▀\033[0m',
          '\033[0m\033[38;5;30m▐█▗█▛▀▘\033[0m',
          '\033[0m\033[38;5;24m▐\033[38;5;30m▛▝▘\033[0m')
INSET = 12                      # the header's first column: the signet, 10 wide, and a gap
HEAD = len(SIGNET) + 1          # the header's lines and the blank below it: on every screen (#57)
# what the map asks of a person, the most urgent first, in the color of its state
NEXT = {"failing": "31", "asks you": "33", "your review": "33", "waits for merge": "33",
        "plan waits for you": "33", "not approved": "33", "spec rule": "90", "last run": "90", "needs a plan": "90",
        "starts next": "90", "spec in progress": "90", "nothing open": "90"}
SILENT = 30 * 60                # a claim without a heartbeat this long shows no sign of life (D-43)
PHASE = {"plan": "planning", "build": "building", "spec tests": "RED check running", "tests": "tests running",
         "review": "review running", "audit": "audit running", "fix": "fix round"}   # pulse go, per feature
# the live map is a tree walked without Shift (D-44): the map, an item, and what acts on it; below
# the map every way back drops what is not written yet, q too (#55)
UP, DOWN, ENTER, RIGHT = ("\x1b[A", "k"), ("\x1b[B", "j"), ("\r", "\n"), ("\x1b[C",)
BACK = ("\x1b", "\x1b[D", "\x7f", "\x08", "q")
KEYS = {"map": "↑ ↓ pick  enter open  m move  ? help  q quit",
        "item": "↑ ↓ pick  enter do it  ? help  esc back",
        "move": "↑ ↓ move  enter place  esc cancel",
        "confirm": "enter confirm  esc cancel",
        "help": "esc back"}
HELP = """map      ↑ ↓ or j k pick an item, enter or → opens it
         enter on an asks you line opens that chat in
           VS Code
         m moves a ramp row, enter places it
         ? shows this help, q quits
item     its goal, stage, holder, blockers, PR, and plan,
           then what you can do with it now: ↑ ↓ pick,
           enter does it
         approve: agents plan and build it; unapprove
           takes that back
         approve plan: the agent builds it as that plan
           says; both approvals show what they bind
           first, enter confirms, esc cancels
         read plan, read spec: open it in a window and
           the map runs on (PULSE_EDITOR, else VS Code or
           Cursor, else the system's app)
         prioritize: top of the ramp, one write
         a, p, o: approve, approve plan, read spec
back     q goes back one level, as esc, ← and backspace
           do, and drops what is not written yet
         q quits only on the map, esc never quits it"""
# what the item view offers, in this order (#55): the words, and what it does
OFFER = {"approve": ("approve", "agents plan and build it when its turn comes"),
         "unapprove": ("unapprove", "nobody builds it until you approve it again"),
         "approve-plan": ("approve plan", "the agent builds it as this plan says"),
         "read-plan": ("read plan", "open it in your editor"),
         "top": ("prioritize", "top of the ramp: it gets the next free slot"),
         "open": ("read spec", "open it in your editor")}
# the line an action shows while it runs; the ones not named here only open a window
DOING = {"rank": "moving #{}…", "approve": "approving #{}…", "unapprove": "taking back the approval of #{}…",
         "approve-plan": "approving the plan of #{}…"}
# what opens a chat in VS Code, from its session id (FIX-02-04-03): only a UUID becomes a link (FR-06)
LINKS = {"claude": "vscode://anthropic.claude-code/open?session={}", "codex": "vscode://openai.chatgpt/local/{}"}
EDITORS = ("Cursor", "VS Code Insiders")     # where else a chat of the extensions runs, without a link
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VERB = {"Edit": "editing", "MultiEdit": "editing", "Write": "writing", "NotebookEdit": "editing",
        "Read": "reading", "Bash": "running", "Grep": "searching", "Glob": "searching",
        "Agent": "delegating", "Task": "delegating", "WebFetch": "reading", "WebSearch": "searching",
        "TodoWrite": "planning", "Skill": "using"}


def vlen(s: str) -> int:
    return len(ANSI.sub("", s))


def fit(s: str, w: int) -> str:
    """Exactly w visible characters: cut without splitting an escape, then pad."""
    if vlen(s) > w:
        out, used = [], 0
        for part in re.split(f"({ANSI.pattern})", s):
            if part.startswith("\033"):
                out.append(part)
                continue
            take = part[:w - used]
            out.append(take)
            used += len(take)
        s = "".join(out) + ("\033[0m" if ANSI.search(s) else "") + ("\033]8;;\033\\" if "\033]8" in s else "")
    return s + " " * (w - vlen(s))


def beside(left: str, w: int) -> int:
    """How wide the note beside left may be (D-45): what left leaves, and at least STATE of the line."""
    return max(int(w * STATE), w - vlen(left.rstrip()) - 2)


def lr(left: str, right: str, w: int) -> str:
    """left text, right note, two spaces apart: the note gets beside(left), the left the rest; a
    side cut short ends in an ellipsis."""
    def cut(s: str, most: int) -> str:
        return s if vlen(s.rstrip()) <= most else fit(s, most - 1) + "…"
    right = cut(right, beside(left, w))
    room = w - vlen(right) - 2
    return fit(fit(cut(left, room), room) + "  " + right, w)


def depth(env=os.environ) -> int:
    """How many colors the terminal shows (D-38): truecolor, 256, else 16."""
    if env.get("COLORTERM", "") in ("truecolor", "24bit"):
        return TRUE
    return 256 if "256color" in env.get("TERM", "") else 16


def glow(level: float, colors: int) -> str:
    """The SGR color of a working light at this brightness: 24-bit, or the nearest in the 256-color cube."""
    rgb = [round(d + (g - d) * level) for g, d in zip(GREEN, DARK)]
    if colors >= TRUE:
        return "38;2;%d;%d;%d" % tuple(rgb)
    steps = (0, 95, 135, 175, 215, 255)
    r, g, b = (min(range(6), key=lambda k: abs(steps[k] - c)) for c in rgb)
    return f"38;5;{16 + 36 * r + 6 * g + b}"


class Paint:
    def __init__(self, color: int):
        self.color = int(color)         # colors the terminal shows; 0 none, True means 16

    def __call__(self, s: str, code: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.color and s else s

    def link(self, text: str, url) -> str:
        """text as a terminal link to url (OSC 8), with color only: a pipe gets no escapes."""
        return f"\033]8;;{url}\033\\{text}\033]8;;\033\\" if self.color and url else text


def roll(states) -> str:
    """The worst state wins, so a red dot deep in the tree reaches the top."""
    return next((s for s in RANK if s in states), "idle")


def _doing(actor: dict) -> tuple:
    """What an agent does right now, in words a newcomer reads without a legend."""
    st = actor["state"]
    if st == "waiting":
        return ("asks you a question" if actor.get("tool") == "AskUserQuestion" else "needs you"), "33"
    if st == "error":
        return actor.get("note") or "a check failed", "31"
    if st == "idle":
        return "idle", "90"
    tool, target = actor.get("tool", ""), actor.get("target", "")
    if "/" in target and " " not in target:
        target = target.rsplit("/", 1)[-1]
    return (f"{VERB.get(tool, tool.lower())} {target}".strip() or "working"), "90"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _secs(at):
    """Seconds since an ISO time or an epoch; None when it is none."""
    if isinstance(at, (int, float)):
        return time.time() - at
    try:
        return time.time() - datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def _age(at) -> str:
    """How long ago an ISO time or an epoch was, in the coarsest unit that fits: 12 min, 3 h, 2 d."""
    s = _secs(at)
    if s is None:
        return "a while"
    return f"{int(s // 60)} min" if s < 3600 else f"{int(s // 3600)} h" if s < 2 * 86400 else f"{int(s // 86400)} d"


def _life(phase: str, beat: str) -> str:
    """The holder's last sign of life (D-43): its phase and age, or none for 30 min."""
    if (_secs(beat) or 0) >= SILENT:
        return f"no sign of life for {_age(beat)}"
    return f"{PHASE.get(phase, phase)}, {_age(beat)} ago"


def _refs(numbers: list, room: int) -> str:
    """#1, #2 +3: as many item numbers as fit in room characters, then how many more (WP-60)."""
    for k in range(len(numbers), 0, -1):
        s = ", ".join(f"#{n}" for n in numbers[:k]) + (f" +{len(numbers) - k}" if k < len(numbers) else "")
        if len(s) <= room:
            return s
    return f"+{len(numbers)}"


def _goal(text) -> str:
    """The first line of a spec's first section: what the item is for."""
    return next(iter(spec.sections(text or "").values()), "").strip().split("\n")[0]


def places(vm: dict) -> dict:
    """{item number, else branch or "no branch": every agent on it}. An agent counts for the item
    its claim holds, wherever its directory stands (FIX-02), else for the item of its branch."""
    by_number = {i["number"]: i for i in vm["items"]}
    holds = {}                            # session or Codex subagent id -> the items its claims hold
    for x in vm["items"]:
        holds.setdefault((x.get("claimed_holder") or "").partition(":")[2], []).append(x)
    holds.pop("", None)                   # no claim mark
    feats = {}
    for s in vm["sessions"]:
        for a in [s, *s["agents"]]:
            b = vm["branches"].get(a.get("cwd", ""), "")
            i = by_number.get(state.item_of(b)) or next(
                (x for x in vm["items"] if b and (x.get("pr") or {}).get("branch") == b), None)
            own = holds.get(a["id"]) or holds.get(s["id"]) or []
            if own and i not in own:
                i = own[0]
            feats.setdefault(i["number"] if i else (b or "no branch"), []).append(a)
    return feats


def chats(vm: dict) -> list:
    """Every chat that waits for the person, once, the longest waiting first (FIX-02-04-03): the
    agent of the chat that asks first (a subagent's prompt reaches its session too, #61 gate round
    1), its cursor stop, who it is, its title, where it stands, where it runs, since when it asks,
    and the link that opens it in VS Code. The link comes from the session's id, and only for a UUID
    of a chat in VS Code (FR-06); a chat elsewhere gets none (FR-05)."""
    where = {id(a): f"#{k}" if isinstance(k, int) else k for k, agents in places(vm).items() for a in agents}
    out = []
    for s in vm["sessions"]:
        ask = [a for a in [s, *s["agents"]] if a["state"] == "waiting"]
        if not ask:
            continue
        a = min(ask, key=lambda a: a.get("asked") or a.get("last") or 0)
        app = "codex" if a.get("app") == "codex" else "claude"
        out.append({"pick": f"chat:{a['id']}", "who": app.title(), "title": presence.clean(a.get("title")),
                    "where": where[id(a)], "asked": a.get("asked") or a.get("last"),
                    "runs": "VS Code" if a.get("vs") else "the Codex app" if a.get("desk") else
                    a["ide"] if a.get("ide") in EDITORS else "a terminal",
                    "link": LINKS[app].format(s["id"]) if a.get("vs") and UUID.fullmatch(str(s["id"])) else ""})
    return sorted(out, key=lambda c: c["asked"] or 0)


def _named(c: dict) -> str:
    """A chat in words: its agent and title, else where it stands."""
    return f'{c["who"]} "{c["title"]}"' if c["title"] else f"{c['who']} on {c['where']}"


def board(vm: dict) -> dict:
    """Every open work item in one group: startable, held (a draft whose spec someone writes too,
    #55), held with a PR, waiting for an open blocker (whatever else gates it), and the rest (not
    approved, a gate, a file in use, a draft nobody holds)."""
    rows = vm["ramp"].get("rows", [])
    held = [i for i in vm["items"] if i["assignees"] and (i["type"] in state.WORK or i.get("draft"))]
    start = [x for x in rows if x["stage"].startswith(("starts next", "queued"))]
    blocked = [x for x in rows if x["blocked_by"] and x not in start]
    return {"ready to start": start, "in progress": [i for i in held if not i.get("pr")],
            "in review": [i for i in held if i.get("pr")], "blocked": blocked,
            "not ready yet": [x for x in rows if x not in start and x not in blocked]}


def render(vm: dict, frame: int = 0, color: int = True, width: int = WIDTH, selected: int = None,
           picks: list = None, item: dict = None) -> list:
    """color: how many colors the terminal shows (depth()), 0 for none; selected: the item the
    terminal cursor is on (marked ›); picks: gets the items on the map top down, the way the cursor
    walks them; item: the item view in place of the map (D-44), its number and what look() read."""
    p, w = Paint(color), width
    by_number = {i["number"]: i for i in vm["items"]}
    shown = [] if picks is None else picks

    def dot(st: str) -> str:
        ch, code = DOT.get(st, DOT["idle"])
        if st == "working" and p.color >= 256:
            code = glow(BREATH[frame % len(BREATH)], p.color)   # it breathes; yellow and red stay lit
        return p(ch, code)

    def section(title: str, note: str = "", right: str = "") -> str:
        head = p(title, "1;36") + (" " + p(note, "90") if note else "")
        tail = (" " + p(right, "90")) if right else ""
        return head + " " + p("─" * max(0, w - vlen(head) - vlen(tail) - 1), "90") + tail

    actors = [a for s in vm["sessions"] for a in [s, *s["agents"]]]
    groups = board(vm)
    rows, phases, failed = vm["ramp"].get("rows", []), vm.get("phases", {}), vm.get("failed", {})
    held = sorted(((login, i) for i in groups["in progress"] + groups["in review"]      # held drafts too (#55)
                   for login in i["assignees"]), key=lambda x: (x[0].lower(), x[1]["number"]))

    def mine(i) -> bool:
        return bool(vm["me"]) and vm["me"] in i["assignees"]

    def light(i):
        """(state, words, next step) of a claimed item: its pulse go job, its pull request, or the claim."""
        pr, n = i.get("pr"), i["number"]
        fix = ("failing", f"/pulse-build {n} takes it on in a session") if mine(i) else None
        if not pr:
            if n in failed:                   # its phase file stays until the run ends
                return "error", f"failed: {failed[n]}", fix
            if n in phases:                   # a job of pulse go: working, whether its agent reports or not
                return "working", PHASE.get(phases[n], phases[n]), None
            if mine(i) and n in vm["ramp"].get("plan_waits", ()):     # /pulse-build keeps the claim meanwhile
                return "waiting", "plan waits for you", ("plan waits for you", f"pulse approve-plan {n}")
            beat = i.get("claimed_beat")
            if beat and not mine(i):          # the holder's last sign of life (D-43)
                return "idle", _life(i.get("claimed_phase") or "working", beat), None
            return "idle", "no PR yet", None
        ref = f"PR #{pr['number']}"
        if pr.get("checks") == "fail":
            return "error", f"{ref}, checks failing", fix
        if pr.get("draft"):                   # pulse go opens a draft only when a gate is red (D-19)
            return "error", f"draft {ref}, a gate is red", fix
        if vm["me"] and vm["me"] in pr.get("reviewers", []):
            return "waiting", f"{ref}, needs your review", ("your review", f"review {ref} on GitHub")
        if mine(i):
            return "waiting", f"{ref}, waits for merge", ("waits for merge", f"merge {ref} on GitHub")
        return "idle", f"{ref}, waits for merge", None

    def wants(row):
        """(state, next step) of a ramp row: red when the last run failed it, yellow when a person
        decides; a row that waits for a blocker waits for nobody else (WP-60). A held draft is no row
        and says the same."""
        n, s = row["number"], row.get("stage", "")
        if n in failed:
            return "error", ("failing", f"/pulse-build {n} takes it on in a session")
        if row.get("draft"):                  # /pulse-ba or /pulse-re writes its spec (D-43)
            who = row.get("claimed_by") or next(iter(row["assignees"]), "")
            return "idle", ("spec in progress", f"{who or '/pulse-re'} writes the spec of #{n}")
        if row in groups["blocked"]:
            return "idle", None
        if s == "not approved":               # pulse approve refuses a spec not on the base (R1, D-43)
            if n in vm.get("unready", ()):    # or one that breaks R2 to R6 there
                return "idle", ("spec rule", f"/pulse-re on the spec of #{n}")
            return "waiting", (s, f"merge the spec of #{n} into the base branch first" if n in vm.get("unmerged", ())
                               else f"pulse approve {n}, or approve in its view")
        if s.startswith("spec:"):
            return "idle", ("spec rule", f"/pulse-re on the spec of #{n}")
        if s.startswith("plan waits"):
            return "waiting", ("plan waits for you", f"pulse approve-plan {n}, or approve plan in its view")
        if row.get("note"):                   # a run gave it back (D-43); its branch holds the work
            return "idle", ("last run", f"/pulse-build {n} goes on from where it stopped")
        if s == "needs a plan":
            return "idle", (s, "/pulse-go writes its plan")
        return "idle", (("starts next", "/pulse-go builds it") if s.startswith(("starts next", "queued")) else None)

    def says(row, room: int = 0) -> tuple:
        """(words, color) of a ramp row: what it waits for, as the board counts it, then what the
        last run left (D-43); as many blockers as fit in room, else in STATE of the line."""
        n, note = row["number"], str(row.get("note") or "").strip().partition("\n")[0]
        since = row.get("claimed_beat") or row.get("claimed_at")
        stage = f"failed: {failed[n]}" if n in failed else \
            row["stage"] + (f", {_age(since)}" if row.get("draft") and since else "")
        if row in groups["blocked"]:           # as the board counts it (N1.13), before details a cut may take
            head, cut, detail = ("", "", "") if stage.startswith("waits for") else stage.partition(" (")
            lead = head + ", waits for " if head else "waits for "
            stage = lead + _refs(row["blocked_by"], (room or int(w * STATE)) - len(lead)) + cut + detail
        stage += f", last run: {note}" if note and n not in failed else ""
        stage += f", for #{row['via']}" if row.get("via") else ""
        return stage, "31" if stage.startswith(("locked", "failed")) else \
            "33" if stage.startswith(("waits for", "plan waits", "spec:", "plan:", "not approved")) else "90"

    feats, asking = places(vm), chats(vm)        # feature (or branch without one) -> every agent on it
    chat_of = {id(a): s["id"] for s in vm["sessions"] for a in [s, *s["agents"]]}
    lit = {i["number"]: light(i) for _, i in held if not i.get("draft")}     # a draft says what its row says
    jobs = [n for n, (st, *_) in lit.items() if st == "working"     # no hooks, or a long command: all idle
            and all(a["state"] == "idle" for a in feats.get(n, []))]
    counts = Counter([a["state"] for a in actors] + [st for n, (st, *_) in lit.items() if st != "working" or n in jobs]
                     + [wants(x)[0] for x in rows])
    tone = {"error": "31", "waiting": "33"}

    def gate(i):
        """Where a feature stands, and for someone else's claim without a PR or heartbeat since when:
        the state a person acts on first, the age after it, where a cut takes it. An item nobody
        holds says what its ramp row says."""
        if i["number"] not in lit:
            if i.get("draft") and i["assignees"]:      # its spec is being written, under its holder only (#55)
                since = i.get("claimed_beat") or i.get("claimed_at")
                who = i.get("claimed_by") or i["assignees"][0]
                return "idle", f"spec in progress by {who}" + (f", {_age(since)}" if since else "")
            row = next((x for x in rows if x["number"] == i["number"]), None)
            return (wants(row)[0], says(row)[0]) if row else ("idle", "")
        st, words, _ = lit[i["number"]]
        on = state.item_of((i.get("pr") or {}).get("base"))
        since = f", held {_age(i['claimed_at'])}" if i.get("claimed_at") and not mine(i) and not i.get("pr") \
            and not i.get("claimed_beat") else ""
        return st, (f"on #{on}, " if on else "") + words + since

    def inside(seen) -> list:
        """The item view: what the item is for, where it stands, who holds it, what it waits for."""
        i = by_number.get(seen["number"])
        if not i:
            return [p(f"#{seen['number']} is merged or closed", "90")]
        n, pr, beat = i["number"], i.get("pr") or {}, i.get("claimed_beat")
        st, words = gate(i)
        who, phase = i.get("claimed_by") or next(iter(i["assignees"]), ""), phases.get(n) or i.get("claimed_phase")
        life = _life(phase or "working", beat) if beat else PHASE.get(phase, phase) if phase else ""
        facts = [("goal", seen["goal"] or "-"), ("stage", p(words or "-", tone.get(st, "90"))),
                 ("holder", ", ".join(filter(None, [who, life])) if who else "nobody"),
                 ("blocked by", _refs(i["blocked_by"], w - 13) if i["blocked_by"] else "nothing"),
                 ("PR", ", ".join(filter(None, [f"#{pr['number']}", pr.get("draft") and "draft",
                                                 pr.get("checks") and f"checks {pr['checks']}"])) if pr else "none"),
                 ("plan", seen["plan"] or "none yet")]
        menu = offers(vm, seen)
        pick = min(seen.get("pick", 0), len(menu) - 1)
        choice = [(p(f" › {words:<14}", "1") if k == pick else f"   {words:<14}")
                  + p(note, "33" if note.startswith("not yet") else "90")
                  for k, (_, words, note) in enumerate(menu)] or [p("   nothing to do here now", "90")]
        return [section(f"{p.link(f'#{n}', i.get('url'))} {i['title']}"), ""] + \
            [f" {k:<12}{v}" for k, v in facts] + [""] + choice
    parts = [(dot("working") if counts["working"] else dot("idle")) + f" {counts['working']} working"]
    if counts["waiting"]:
        parts.append(dot("waiting") + " " + p.link(f"{counts['waiting']} need{'s' if counts['waiting'] == 1 else ''} you",
                                                  next((c["link"] for c in asking if c["link"]), "")))   # FR-04
    if counts["error"]:
        parts.append(dot("error") + f" {counts['error']} failing")
    head = ["", lr(p("pulse", "1") + "  " + p(vm["repo"] or "no repo", "90"), p(vm["now"], "1"), w - INSET),
            "   ".join(parts), p("! " + vm["error"], "33") if vm.get("error") else ""]
    signet = [l if p.color >= 256 else re.sub(r"38;5;\d+", "36", l) if p.color else ANSI.sub("", l) for l in SIGNET]
    out = [fit(mark, INSET) + text for mark, text in zip(signet, head + [""])]   # 256 colors as drawn, else cyan
    out.append("")
    if item:                              # the item view (D-44), live like the map
        return [fit(l, w) for l in out + inside(item)]

    # --- board ------------------------------------------------------------
    total = max(1, sum(map(len, groups.values())))
    out.append(section("BOARD"))
    for (label, group), code in zip(groups.items(), ("36", "32", "35", "33", "90")):
        n = len(group)
        filled = max(1, round(n * 24 / total)) if n else 0
        out.append(f" {label:<15}" + p("█" * filled, code) + p("░" * (24 - filled), "90") + f"{n:>4}")
    for e in (i for i in vm["items"] if i["type"] == "epic"):         # how far each epic is (WP-60)
        done = vm.get("closed", {}).get(e["number"], 0)
        total = done + sum(i.get("parent") == e["number"] for i in vm["items"])
        if total:
            k, ref = round(10 * done / total), p.link(f"#{e['number']}", e.get("url"))
            out.append(lr(f" {ref} {e['title']}",
                          p("█" * k, "32") + p("░" * (10 - k), "90") + f" {done} of {total} done", w))
    out.append("")

    # --- who is doing what ------------------------------------------------
    out.append(section("WHO IS DOING WHAT"))

    def focus(agents):
        """The agent to show: one that needs you or failed first, then the latest activity."""
        return min(agents, key=lambda a: (RANK.index(a["state"]), -a.get("last", 0)))

    def said(agents) -> tuple:
        """What the agents on one line do: the one focus picks, or, where several chats stand and
        some ask, how many ask and what a working one does (FIX-02-04-03)."""
        ask = [a for a in agents if a["state"] == "waiting"]
        if not ask or len({chat_of[id(a)] for a in agents}) < 2:
            return _doing(focus(agents))
        k = len({chat_of[id(a)] for a in ask})         # chats, not agents (#61 gate round 1)
        words = f"{k} chat asks you" if k == 1 else f"{k} chats ask you"
        rest = [a for a in agents if a["state"] not in ("waiting", "idle")]
        if rest:
            a = focus(rest)
            words += f", {'Codex' if a.get('app') == 'codex' else 'Claude'}: {_doing(a)[0]}"
        return words, "33"

    def tree(entries):
        """Features, each with what its agent does below it; agents outside any feature by branch."""
        rows = []
        for k, (e, agents) in enumerate(entries):
            stem, pad = ("└ ", "  ") if k == len(entries) - 1 else ("├ ", "│ ")
            states = [a["state"] for a in agents]
            if isinstance(e, str):            # an agent on a branch that is no open feature
                doing, code = said(agents)
                rows.append(lr(stem + dot(roll(states)) + " " + e, p(doing, code), w))
                continue
            st, words = gate(e)
            label = p.link(f"#{e['number']}", e.get("url")) + f" {e['title']}"
            if e["number"] not in shown:
                shown.append(e["number"])
            if e["number"] == selected:
                stem, label = p("› ", "1"), p(label, "1")
            rows.append(lr(stem + dot(roll(states + [st])) + " " + label, p(words, tone.get(st, "90")), w))
            if agents:
                doing, code = said(agents)
                rows.append(lr(pad + "└ " + p(doing, code), "", w))
        return rows

    others = {}                           # the holder's claim mark decides, else the assignee
    for login, i in held:
        holder = i.get("claimed_by") or login
        if holder != vm["me"]:
            others.setdefault(holder, {})[i["number"]] = i
    theirs = {n for items in others.values() for n in items}          # shown once, under the holder
    entries = [(by_number[k] if isinstance(k, int) else k, agents) for k, agents in feats.items() if k not in theirs]
    entries += [(i, []) for login, i in held if login == vm["me"] and i["number"] not in feats
                and i["number"] not in theirs]

    r = vm["ramp"]
    busy = sum(a["state"] != "idle" for a in actors) + len(jobs)
    agents = _plural(busy, "agent") if busy else "no agent"
    out.append(lr(dot(roll([a["state"] for a in actors] + [gate(i)[0] for login, i in held
                                                            if login == vm["me"]]))
                  + " " + p(vm["person"], "1"),
                  p(f"{len(r['busy'])} of {r['cap']} slots busy, {agents} active", "90"), w))
    out += tree(entries)
    for login in sorted(others, key=str.lower):
        items = list(others[login].values())
        out.append(lr(dot(roll([gate(i)[0] for i in items])) + " " + p(login, "1"),
                      p(_plural(len(items), "item"), "90"), w))
        out += tree([(i, feats.get(i["number"], [])) for i in items])       # my agent on their item too
    out.append("")

    # --- next ---------------------------------------------------------------
    todo = {}                             # state -> the step that moves its first item
    steps = [x[2] for x in lit.values()] + [wants(i)[1] for _, i in held if i.get("draft")] + \
        [wants(x)[1] for x in rows]
    for step in filter(None, steps):
        todo.setdefault(*step)
    if not rows and not held:
        todo["nothing open"] = "/pulse-ba explores, /pulse-re writes specs"
    out.append(section("NEXT"))
    for state_ in NEXT:
        if state_ == "asks you":          # a line and a cursor stop per chat (FIX-02-04-03)
            for c in asking:
                shown.append(c["pick"])
                tail = ("" if c["runs"] == "VS Code" else " in its terminal" if c["runs"] == "a terminal"
                        else f" in {c['runs']}") + f" ({_age(c['asked'])})"
                over, cut = len(f"answer {_named(c)}{tail}") - beside(" asks you", w), "title" if c["title"] else "where"
                if over > 0:                  # the wait stays in sight (FR-02): the title, else the place, gives way
                    c = {**c, cut: c[cut][:max(0, len(c[cut]) - over - 1)] + "…"}
                words = f"answer {_named(c)}{tail}"
                out.append(lr((p("›", "1") if c["pick"] == selected else " ") + p(state_, NEXT[state_]),
                              p.link(words, c["link"]), w))
        elif state_ in todo:
            out.append(lr(" " + p(state_, NEXT[state_]), todo[state_], w))
    out.append("")

    # --- ramp ---------------------------------------------------------------
    out.append(section("RAMP", "all open work, in team order"))
    for row in rows[:ROWS_SHOWN]:
        title = p.link(f"#{row['number']}", row.get("url")) + f" {row['title']}"
        if row["number"] not in shown:
            shown.append(row["number"])
        left = p("▲ " + title, "36") if row["stage"].startswith("starts next") else "  " + title
        if row["number"] == selected:
            left = p("› " + title, "1")
        stage, code = says(row, beside(left, w))
        out.append(lr(left, p(stage, code), w))
    if len(rows) > ROWS_SHOWN:
        out.append(p(f"  +{len(rows) - ROWS_SHOWN} more", "90"))
    if not rows:
        out.append(p("  nothing ready", "90"))
    return [fit(l, w) for l in out]


def columns() -> int:
    """How wide the map is (D-45): as its terminal, else COLUMNS (pulse status, a pipe), else 80;
    always 60 to 160 columns. The live map asks on every frame."""
    try:
        cols = os.get_terminal_size(sys.__stdout__.fileno()).columns
    except (AttributeError, ValueError, OSError):
        cols = 0
    if cols <= 0:                       # none, or a pty nobody sized: 0 columns
        cols = shutil.get_terminal_size((WIDTH, 40)).columns or WIDTH
    return max(FEWEST, min(MOST, cols))


def once(vm: dict, color) -> str:
    """One frame as wide as columns() says: `pulse status` and `pulse map --once`.
    color: True for the terminal's depth, else as render() takes it."""
    return "\n".join(render(vm, color=depth() if color is True else color, width=columns()))


def offers(vm: dict, seen: dict) -> list:
    """[(action, words, what it does)]: what the item view offers in the item's stage (#55), in the
    order of OFFER. An approval that cannot be given now says why in place of what it does."""
    i = next((x for x in vm["items"] if x["number"] == seen["number"]), None)
    if not i:
        return []
    n, ramp = i["number"], vm["ramp"].get("rows", [])
    rows, stage = [r["number"] for r in ramp], next((r["stage"] for r in ramp if r["number"] == n), "")
    why = ""
    if i.get("draft"):
        why = "not yet: its spec is still being written"
    elif not i.get("spec"):
        why = "not yet: it has no spec, /pulse-re writes one"
    elif n in vm.get("unmerged", ()):            # pulse approve refuses it too (R1, D-43)
        why = "not yet: its spec is still on a branch, merge it first"
    elif n in vm.get("unready", ()):
        why = "not yet: its spec breaks a rule, /pulse-re fixes it"
    out = [("approve", why)] if not i["approved"] else [("unapprove", "")] if n in rows else []
    if n in vm["ramp"].get("plan_waits", ()) or stage.startswith("plan waits"):
        out.append(("approve-plan", ""))
    out += [("read-plan", "")] * bool(seen.get("plan")) + [("top", "")] * (n in rows[1:]) + \
        [("open", "")] * bool(i.get("spec"))
    return [(a, OFFER[a][0], note or OFFER[a][1]) for a, note in out]


def key(ui: dict, picks: list, rows: list, ch: str, acts=()) -> tuple:
    """(ui, action) for one key of the live map, a tree walked without Shift (D-44). ui: the level
    (map, item, move, confirm, help), the item it is at, in the item view the action picked, in the
    move mode the place among the other ramp rows the item goes to, the approval Enter confirms, and
    the level a move or the help began on. picks: the items on the map, top down; rows: the items of
    the ramp, in order; acts: what the item view offers (offers())."""
    level, n = ui["level"], ui.get("at")
    if level == "map":
        if ch in UP + DOWN and picks:
            k = picks.index(n) if n in picks else -1
            return {**ui, "at": picks[max(0, k - 1) if ch in UP else min(len(picks) - 1, k + 1)]}, None
        if ch in ENTER + RIGHT and n in picks:  # a chat opens where it runs (FIX-02-04-03)
            return (ui, ("chat", n)) if str(n).startswith("chat:") else ({"level": "item", "at": n}, None)
        if ch == "m" and isinstance(n, int) and n in picks:     # sort the ramp without opening the item
            if n not in rows:
                return ui, ("say", f"#{n} is held: only items on the ramp move")
            return {"level": "move", "at": n, "to": rows.index(n), "from": "map"}, None
        if ch == "?":
            return {"level": "help", "at": n, "from": "map"}, None
        return ui, ("say", "q quits the map") if ch in BACK else None     # Esc never ends it (D-44)
    back = {"level": ui.get("from", "item"), "at": n}     # a move and the help end where they began
    if back["level"] == "item":
        back["pick"] = ui.get("pick", 0)
    if ch in BACK:                              # one level up, and what is not written yet is dropped
        return (back if level != "item" else {"level": "map", "at": n}), None
    if level == "item":
        pick = min(ui.get("pick", 0), len(acts) - 1) if acts else ui.get("pick", 0)   # the offers may have changed
        if ch in UP + DOWN:
            return ({**ui, "pick": max(0, pick - 1) if ch in UP else min(len(acts) - 1, pick + 1)}
                    if acts else ui), None
        if ch == "?":
            return {"level": "help", "at": n, "from": "item", "pick": pick}, None
        if ch in ENTER and acts:
            return ui, ("rank", n, {"top": True}) if acts[pick] == "top" else (acts[pick], n)
        return ui, {"a": ("approve", n), "p": ("approve-plan", n), "o": ("open", n)}.get(ch)
    if level == "move":
        if n not in rows:                       # claimed since the move began
            return back, ("say", f"#{n} left the ramp; nothing moved")
        rest = [m for m in rows if m != n]
        to = min(ui["to"], len(rest))           # the rows it moved among may have left the ramp since
        if ch in UP + DOWN:
            return {**ui, "to": max(0, to - 1) if ch in UP else min(len(rest), to + 1)}, None
        if ch not in ENTER:
            return ui, None
        where = None if to == rows.index(n) else {"before": rest[to]} if to < len(rest) else {"after": rest[-1]}
        return back, where and ("rank", n, where)
    if level == "confirm":                      # any other key: no approval
        return back, ui["sure"] if ch in ENTER else None
    return ui, None


def brief(root: Path, vm: dict, action: tuple) -> tuple:
    """What a person reads before a or p approves (F6.08): the goal, what holds it, and for a PLAN
    the digest the approval binds to. (lines, the action Enter confirms), or (why not, None). a
    refuses what pulse approve refuses: a spec not on the base branch (R1, D-43), and for a work
    item a spec there that breaks R2 to R6, which pulse check would hold against every commit."""
    kind, n = action
    i = next((x for x in vm["items"] if x["number"] == n), {})
    if kind == "unapprove":                   # Enter confirms it too: a stray Enter takes nothing back (#55)
        return [f"take back the approval of #{n} {i.get('title', '')}: nobody builds it until someone "
                "approves it again"], action
    if kind == "approve" and i.get("approved"):
        return [f"#{n} is approved already (pulse approve --undo {n} takes it back)"], None
    text = spec.on_base(root, i["spec"]) if i.get("spec") else None
    if kind == "approve":
        why = spec.refusal(text, i.get("type"), n, config.base_ref(root))
        if why:
            return [f"#{n} not approved: {why}"], None
        return ([f"approve #{n} {i.get('title', '')}", f"goal: {_goal(text) or '-'}",
                 f"risk: {ready.hold(text, '').replace('risk: ', '') or 'none'}"], action)
    d, why = ready.approvable(root, vm["items"], config.load(root), n)
    if not d:
        return [why.replace("PLAN", "plan")], None
    plan = ready.plans(root)[n]["text"]
    goal = spec.sections(plan).get("goal", "").strip().split("\n")[0]
    return ([f"approve the plan of #{n}, digest {d}", f"goal: {goal or '-'}",
             f"risk: {ready.hold(text or '', plan).replace('risk: ', '') or 'none'}"], (kind, n, d))


def own_version() -> str:
    """The version of the Pulse this process runs; '' when its manifest cannot be read."""
    try:
        return setup._version(setup.PULSE_BIN.parents[1])
    except (OSError, ValueError, KeyError):
        return ""


def newer_copy() -> str:
    """The pulse command when it starts a newer Pulse than this map runs, else '' (IMP-14). A map
    that runs from a clone, not from a plugin cache, stays with it."""
    if "plugins/cache" not in setup.PULSE_BIN.as_posix():
        return ""
    shim = Path.home() / ".local" / "bin" / "pulse"
    try:
        found = subprocess.run([str(shim)], env={**os.environ, "PULSE_WHICH": "1"}, capture_output=True,
                               text=True, timeout=5).stdout.strip()
        theirs = setup._version(Path(found).parents[1])
    except (OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired):
        return ""
    return str(shim) if setup.version_key(theirs) > setup.version_key(own_version()) else ""


def latest(root: Path) -> str:
    """The newest released Pulse, asked of its repository once a day and kept in the clone's cache,
    where the session start reads it too; '' when nobody answered (IMP-14)."""
    path = state.cache_dir(root) / "latest"
    with contextlib.suppress(OSError):
        if time.time() - path.stat().st_mtime < DAY:
            return path.read_text(encoding="utf-8").strip()
    out = ready.net_git(root, "ls-remote", "--tags", "--refs", os.environ.get("PULSE_RELEASES") or RELEASES)
    tags = [l.rsplit("/v", 1)[-1] for l in out.stdout.splitlines() if re.search(r"/v\d", l)] if out.returncode == 0 else []
    found = ".".join(map(str, max(map(setup.version_key, tags), default=())))
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(found, encoding="utf-8")
    return found


def look(root: Path, vm: dict, n: int) -> dict:
    """What the item view reads from git: the goal of the spec on the base, and where the PLAN is."""
    i = next((x for x in vm["items"] if x["number"] == n), {})
    p = ready.plans(root).get(n)
    return {"number": n, "goal": _goal(spec.on_base(root, i["spec"]) if i.get("spec") else None),
            "plan": p["path"] + (f" on {p['ref']}" if p["ref"] else "") if p else ""}


def opener(env=os.environ) -> list:
    """The command that shows a file in a window and gives the terminal back at once (D-44):
    PULSE_EDITOR, else the VS Code or Cursor window this terminal belongs to, else the system's
    app for the file; [] for none."""
    if env.get("PULSE_EDITOR"):
        return shlex.split(env["PULSE_EDITOR"])
    if env.get("TERM_PROGRAM") == "vscode":        # both set it; Cursor's own git helper names Cursor
        clis = ("cursor", "code") if "cursor" in env.get("VSCODE_GIT_ASKPASS_NODE", "").lower() else ("code", "cursor")
        found = next(filter(shutil.which, clis), None)
        if found:
            return [found, "-r"]                   # -r: that window, no new one
    if sys.platform == "darwin":
        return ["open"]
    return ["xdg-open"] if shutil.which("xdg-open") else []


def _show(path, name: str, cmd: list = None) -> str:
    """Open path (or a link) in a window and give the terminal back at once (D-44), with cmd, else
    the opener(); the line for the status bar."""
    cmd = opener() if cmd is None else cmd
    try:
        if cmd:                         # never waits for it: the map runs on (D-44)
            subprocess.Popen(cmd + [str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return f"opened {name} with {Path(cmd[0]).name}"
    except OSError:
        pass
    return f"open it yourself: {path}"


def act(root: Path, vm: dict, action: tuple) -> str:
    """Carry out one action from the map; returns a line for the status bar. An approved plan
    is the one brief() showed: its digest comes with the action."""
    kind, n = action[0], action[1]
    if kind == "chat":                  # through the system's opener: code -r takes a link for a file
        c = next((c for c in chats(vm) if c["pick"] == n), None)
        if not c:
            return "that chat asks nothing any more"
        return _show(c["link"], _named(c), opener({})) if c["link"] else \
            f"{_named(c)} runs in {c['runs']}: answer it there"
    repo = state.repo(root)
    if kind == "rank":                  # the frame may be old: place on the board as it is now (F9.01)
        try:
            writes = dispatch.place(state.load(root, repo, fresh=True), n, **action[2])
        except ValueError:              # the neighbour left the free list since the frame (N4.07)
            return f"#{n} and the item it goes next to must both be open and free"
        for m, value in writes:
            state.set_rank(root, repo, m, value)
        return f"#{n} moved"
    if kind in ("approve", "unapprove"):
        state.approve(root, repo, [n], undo=kind == "unapprove")
        return f"#{n} approved" if kind == "approve" else f"#{n} is no longer approved"
    if kind == "approve-plan":
        d, why = ready.approvable(root, vm["items"], config.load(root), n)
        if not d:
            return why.replace("PLAN", "plan")
        if d != action[2]:
            return f"the plan of #{n} changed since you read it; approve plan shows it again"
        state.approve_plan(root, repo, n, d)
        return f"plan of #{n} approved"
    if kind == "read-plan":
        plan = ready.plans(root).get(n)
        if not plan:
            return f"#{n} has no plan"
        if not plan["ref"]:
            return _show(root / plan["path"], plan["path"])
        copy = state.cache_dir(root) / "plans" / f"{n}-{Path(plan['path']).name}"   # on its branch only: a copy
        try:
            copy.parent.mkdir(parents=True, exist_ok=True)
            if copy.is_symlink() or copy.exists():
                copy.unlink()                 # a new file, never written through a link at its place
            copy.write_text(plan["text"], encoding="utf-8")
        except OSError as e:
            return f"no copy of {plan['path']} to read: {e}"
        return _show(copy, f"a copy of {plan['path']} from {plan['ref']}")
    item = next((i for i in vm["items"] if i["number"] == n), {})
    if not item.get("spec"):
        return f"#{n} has no spec"
    return _show(root / item["spec"], item["spec"])


def _fetch(root: Path) -> None:
    """What every clone planned and holds arrives beside the live map, which never waits for the
    network: ready.fetch in the background, at most every 30 s, with a time limit. pulse status
    fetches first and waits."""
    threading.Thread(target=ready.fetch, args=(root,), daemon=True).start()


def _git(cwd: str, *args) -> str:
    try:
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                              timeout=2).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def failures(root: Path, items=()) -> dict:
    """{item: why} for what the last run of pulse go failed, from its report (D-14). A claim or a
    sign of life on the item since then is newer work, whoever holds it: the map shows that one."""
    since = {i["number"]: max(i.get("claimed_at") or "", i.get("claimed_beat") or "") for i in items}
    try:
        report = json.loads((config.pulse_dir(root) / "go" / "report.json").read_text(encoding="utf-8"))
        return {int(n): r.get("why") or "failed" for n, r in report["items"].items()
                if r.get("result") == "failed" and since.get(int(n), "") <= (r.get("at") or "")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


_merged: dict = {}                      # root -> (read at, the items of the merged PRs)


def merged(root: Path, repo: str, items: list) -> set:
    """The claimed items whose PR was merged, also into a base GitHub closes nothing on (not the
    default branch): done, though open until pulse status closes them (ADR-06). Read at most every
    state.TTL s."""
    held = {i["number"] for i in items if i["assignees"] and not i.get("pr")}
    at, done = _merged.get(root, (0.0, set()))
    if held and repo and time.time() - at >= state.TTL:
        try:
            done = {n for pr in json.loads(state.gh(["pr", "list", "--repo", repo, "--state", "merged", "--limit", "50",
                                                     "--json", "headRefName,closingIssuesReferences,files,changedFiles"]))
                    for n in state.pr_items(pr)}
        except (state.StateError, ValueError):
            pass                        # offline: the last answer stands
        _merged[root] = (time.time(), done)
    return done & held


_closed: dict = {}                      # root -> (read at, {epic: its closed children})


def closed(root: Path, repo: str, items: list) -> dict:
    """{epic: how many of its children are closed as completed} for the open epics (WP-60); one
    closed as not planned leaves the count (N5.01). Read at most every state.TTL s, and only while
    an epic is open."""
    epics = {i["number"] for i in items if i["type"] == "epic"}
    at, done = _closed.get(root, (0.0, {}))
    if epics and repo and time.time() - at >= state.TTL:
        try:                            # ponytail: the last 1000 closed issues; a long epic's oldest may drop out
            done = Counter((i.get("parent") or {}).get("number") for i in json.loads(state.gh(
                ["issue", "list", "--repo", repo, "--state", "closed", "--limit", "1000",
                 "--json", "number,parent,stateReason"])) if i.get("stateReason") == "COMPLETED")
        except (state.StateError, ValueError):
            pass                        # offline: the last answer stands
        _closed[root] = (time.time(), done)
    return {e: done[e] for e in epics if done.get(e)}


def _job(root: Path, cwd: str):
    """The item whose pulse go worktree holds cwd (go.job_for puts it beside the repo), else None."""
    m = re.match(re.escape(str(root)) + r"-(\d+)-[^/]+(?:/|$)", cwd or "")
    return int(m.group(1)) if m else None


def gather(root: Path) -> dict:
    _fetch(root)
    cfg, error, repo, items, me = config.load(root), "", "", [], ""
    try:
        repo = state.repo(root, run=state.gh)      # looked up per call so tests can swap gh
        me = state.me(root, run=state.gh)
        items = state.load(root, repo, run=state.gh)
    except state.StateError as e:
        items = state.cached(root)
        error = f"offline, showing the last known state ({e})" if items else str(e)
    done = merged(root, repo, items)          # off the map at once, done for its epic (#57)
    finished = Counter(i["parent"] for i in items if i["number"] in done and i.get("parent"))
    items = [i for i in items if i["number"] not in done]
    phases = go.phases(root)
    holders = {(i.get("claimed_holder") or "").partition(":")[2] for i in items}
    sessions = [s for s in presence.read(root) if _job(root, s.get("home") or s["cwd"]) in (None, *phases)
                or s["id"] in holders]      # no job, no agent, unless it holds an item (FIX-02)
    cwds = {a.get("cwd") for s in sessions for a in [s, *s["agents"]] if a.get("cwd")}
    specs = {i["spec"] for i in items if not i["approved"] and i.get("spec")}   # on the base, or approve refuses
    there = set(_git(str(root), "ls-tree", "-rz", "--name-only", config.base_ref(root), "--", *specs)
                .split("\0")) if specs else set()
    return {"repo": repo, "now": time.strftime("%H:%M:%S"),
            "person": _git(str(root), "config", "user.name") or me or "you", "me": me,
            "items": items, "sessions": sessions, "error": error, "phases": phases, "failed": failures(root, items),
            "closed": dict(Counter(closed(root, repo, items)) + finished),
            "unmerged": [i["number"] for i in items if not i["approved"] and i.get("spec") not in there],
            # ponytail: one git show per unapproved spec each refresh; git cat-file --batch if the ramp is long
            "unready": [i["number"] for i in items if not i["approved"] and i.get("spec") in there and spec.refusal(
                spec.on_base(root, i["spec"]), i.get("type"), i["number"], "")],
            "branches": {c: _git(c, "rev-parse", "--abbrev-ref", "HEAD") for c in cwds},
            "ramp": dispatch.view(root, items, cfg, me)}


# --- demo: a time-lapse of one morning ------------------------------------
STEP_SECONDS = 2.5
DEMO_ITEMS = [  # number, title, type, ready, blocked by, files
    (10, "sign-in that lasts", "epic", True, (), []),
    (11, "auth: session refresh", "feat", True, (), ["src/auth/session.ts", "src/auth/token.ts"]),
    (12, "api: rate limiting", "feat", True, (), ["src/api/limit.ts"]),
    (13, "ui: token banner", "feat", True, (11,), ["src/ui/Banner.tsx"]),
    (14, "fix: typo in login", "fix", True, (), ["src/ui/login.tsx"]),
    (15, "ui: dark mode", "feat", False, (), []),
    (16, "perf: query cache", "imp", True, (), ["src/db/query.ts"]),
    (17, "docs: auth flow", "feat", True, (), ["docs/auth.md"]),
    (18, "ui: settings panel", "feat", True, (), ["src/auth/token.ts", "src/ui/Settings.tsx"]),
    (19, "fix: token expiry", "fix", True, (), ["src/auth/expiry.ts"]),
    (20, "api: pagination cursor", "feat", True, (), ["src/api/cursor.ts"]),
    (21, "ui: empty states", "feat", True, (), ["src/ui/Empty.tsx"]),
    (22, "db: session index", "imp", True, (), ["src/db/index.sql"]),
    (23, "api: error envelope", "feat", True, (), []),
    (24, "ui: keyboard shortcuts", "feat", True, (), []),
]
# one list per step, applied on top of the steps before; an agent is
# (id, item or None, model, state, tool, target, note); an agent's item is
# building until a ("phase", item, phase) says otherwise
SCRIPT = [
    [("claim", 11, "Sebastian"), ("claim", 17, "Sebastian"), ("claim", 19, "Sebastian"),
     ("claim", 12, "Alice"),
     ("agent", "lead", None, "opus", "working", "Bash", "pulse go", ""),
     ("agent", "s19", 19, "sonnet", "working", "Edit", "src/auth/expiry.ts", ""),
     ("agent", "s11", 11, "opus", "working", "Edit", "src/auth/session.ts", ""),
     ("agent", "s17", 17, "opus", "working", "Edit", "docs/auth.md", "")],
    [("claim", 14, "Sebastian"), ("agent", "s14", 14, "opus", "working", "Read", "src/ui/login.tsx", "")],
    [("agent", "s17", 17, "opus", "error", "Bash", "npm test", "npm test failed"), ("phase", 17, "tests"),
     ("agent", "s11", 11, "opus", "working", "Bash", "npm test", ""), ("claim", 23, "Alice")],
    [("agent", "s19", 19, "sonnet", "waiting", "AskUserQuestion", "", ""), ("claim", 16, "Bob")],
    [("agent", "s17", 17, "opus", "working", "Edit", "docs/auth.md", ""), ("phase", 17, "fix"), ("pr", 14),
     ("gone", "s14")],
    [("agent", "s19", 19, "sonnet", "working", "Edit", "src/auth/expiry.ts", ""),
     ("claim", 20, "Sebastian"), ("agent", "s20", 20, "opus", "working", "Read", "src/api/cursor.ts", ""),
     ("pr", 16, "fail"), ("phase", 11, "review")],
    [("pr", 11), ("gone", "s11"), ("claim", 24, "Bob")],
    [("merge", 11), ("pr", 12, "pass", ["Sebastian"]), ("claim", 21, "Sebastian"),
     ("agent", "s21", 21, "opus", "working", "Edit", "src/ui/Empty.tsx", "")],
    [("pr", 17), ("gone", "s17"), ("agent", "s20", 20, "opus", "working", "Bash", "npm test", ""),
     ("pr", 16, "pass")],
    [("merge", 12), ("merge", 14), ("claim", 22, "Alice"), ("claim", 13, "Sebastian"),
     ("agent", "s13", 13, "opus", "working", "Edit", "src/ui/Banner.tsx", "")],
]


def demo_step(t: float) -> int:
    """The step for a moment in time, so every surface shows the same one."""
    return int(t // STEP_SECONDS) % len(SCRIPT)


def demo(step: int = 0) -> dict:
    """A plausible morning for screenshots, docs, and a first look without a repo."""
    items = {n: {"number": n, "title": title, "type": kind, "approved": ok, "assignees": [],
                 "parent": None if kind == "epic" else 10, "blocked_by": list(blocked), "blocking": [],
                 "spec": None, "pr": None}
             for n, title, kind, ok, blocked, _ in DEMO_ITEMS}
    items[11]["blocking"] = [13]
    files = {n: f for n, *_, f in DEMO_ITEMS if f}
    branch = {n: f"{i['type']}/{n}-{go.slug(i['title'])}" for n, i in items.items()}   # as pulse go names them
    agents, phases, closed, t = {}, {}, {10: 0}, time.time()
    for change in (c for batch in SCRIPT[:step + 1] for c in batch):
        op, *a = change
        if op == "claim":
            items[a[0]]["assignees"] = [a[1]]
        elif op == "pr":                 # item, then optionally its checks and who is asked to review
            i = items[a[0]]
            i["pr"] = {"number": 100 + a[0], "branch": branch[a[0]], "draft": False,
                       "checks": a[1] if len(a) > 1 else None, "reviewers": a[2] if len(a) > 2 else []}
        elif op == "merge":
            items.pop(a[0])
            closed[10] += 1
            for i in items.values():
                i["blocked_by"] = [b for b in i["blocked_by"] if b != a[0]]
        elif op == "gone":
            agents.pop(a[0], None)
        elif op == "phase":
            phases[a[0]] = a[1]
        else:
            aid, n, model, st, tool, target, note = a
            agents[aid] = {"id": aid, "type": "", "cwd": f"/repo-{n}" if n else "/repo", "started": t,
                           "last": t, "tool": tool, "target": target, "note": note, "state": st,
                           "model": model, "agents": [], "order": agents.get(aid, {}).get("order", len(agents))}
            if st == "waiting":          # its chat asks in VS Code, for 4 minutes now (FIX-02-04-03)
                agents[aid].update(title="Which clock decides when a token expires?", vs=True, asked=t - 4 * 60)
    sessions = sorted(agents.values(), key=lambda s: s["order"])
    order = [i for i in items.values()]
    phases = {n: phases.get(n, "build") for n in {int(s["cwd"].rsplit("-", 1)[1]) for s in sessions
                                                   if s["cwd"] != "/repo"} if not items[n]["pr"]}
    branches = {"/repo": "develop"}
    branches.update({f"/repo-{n}": branch[n] for n in items})
    minutes = 9 * 60 + 4 * step
    return {"repo": "acme/shop", "now": f"{minutes // 60:02d}:{minutes % 60:02d}", "person": "Sebastian",
            "me": "Sebastian", "items": order, "sessions": sessions, "error": "", "branches": branches,
            "phases": phases, "closed": closed,
            "ramp": dispatch.ramp(order, files, 4, "Sebastian",       # like pulse go: no PLAN, no build
                                  gates={n: "needs a plan" for n, i in items.items()
                                         if i["approved"] and n not in files and not i["assignees"]})}


def _keys():
    """A reader for single keys when stdin is a terminal; None elsewhere (pipes, Windows)."""
    try:
        import termios
        import tty
    except ImportError:
        return None
    if not sys.stdin.isatty():
        return None
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    def read(wait: float):
        if not select.select([sys.stdin], [], [], wait)[0]:
            return None
        ch = os.read(fd, 1).decode(errors="ignore")
        if ch == "\x1b" and select.select([sys.stdin], [], [], 0.01)[0]:
            ch += os.read(fd, 2).decode(errors="ignore")
        return ch

    def restore():
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        except termios.error:
            pass                       # the terminal is gone (SIGHUP)

    def drop():
        """Forget what was typed meanwhile: keys pressed during a write act on no board (#55)."""
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
        except termios.error:
            pass

    read.restore, read.drop = restore, drop
    return read


def fitted(lines: list, height: int, keep: int) -> list:
    """At most height lines, so a frame taller than the terminal never scrolls it: the header (the
    first HEAD lines, #57) and the last keep lines (status and keys) stay, the rest is cut around
    the picked row (›), and one line says how much is hidden. A terminal too low for all of it
    gives header lines up first."""
    if len(lines) <= height:
        return lines
    head = lines[:min(HEAD, max(0, height - keep - 2))]
    body, foot = lines[len(head):len(lines) - keep], lines[len(lines) - keep:]
    room = max(1, height - len(head) - len(foot) - 1)
    at = next((i for i, line in enumerate(body) if "›" in ANSI.sub("", line)), 0)
    top = max(0, min(at - room // 2, len(body) - room))
    return head + body[top:top + room] + [f"  … {len(body) - room} more lines; a taller terminal shows them"] + foot


def _beside(fn) -> threading.Thread:
    """fn in a thread of its own: the live map reads beside its keys, so none waits for GitHub (#55)."""
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    return t


def main(args) -> int:
    root = config.find_root()
    if not args.demo and root is None:
        print("pulse map: not inside a git repository (try --demo)")
        return 2
    color = depth() if not args.no_color and sys.stdout.isatty() or args.color else 0
    if args.once or not sys.stdout.isatty():            # a pipe, a file, a chat: one frame
        print(once(demo(demo_step(time.time())) if args.demo else gather(root), color))
        return 0
    vm, fetched, ui, status, seen, shown, told, waiting = None, 0.0, {"level": "map"}, "", None, [], "", ""
    restart, reading, todo = "", None, None          # a newer copy; the read beside the keys; an action to run
    offered = {}                                     # item -> what its view offered on the last frame
    # what the read brings, the writes so far, the last look for a newer copy and for a newer release
    box = {"writes": 0, "looked": time.time(), "asked": -math.inf}
    drawn, drawn_at = [], None                       # the rows on the screen, and the size they were drawn at
    keys = _keys()                                   # the demo too: no typed key lands in its frame
    read = None if args.demo else keys               # but it takes none
    handlers = {s: signal.signal(s, go._exit)          # a closed terminal still runs the cleanup
                for s in (signal.SIGTERM, getattr(signal, "SIGHUP", None)) if s}

    def world():
        """What the live map reads that waits for git, GitHub, or the network, beside its keys (#55):
        the board, a start of pulse go, a newer release, a newer copy of Pulse."""
        try:
            writes, board_, update, newer = box["writes"], gather(root), "", ""
            said = mapstart.runner(root, board_)       # approved work waits: pulse go starts (#44)
            archmap.refresh(root)                      # the base moved: the architecture map follows (#67)
            if time.time() - box["asked"] >= DAY:      # a newer release: named once a day (IMP-14)
                box["asked"], own = time.time(), own_version()
                out = latest(root)
                if setup.version_key(out) > setup.version_key(own):
                    update = UPDATE.format(v=out, own=own)
            if time.time() - box["looked"] >= UPGRADE:
                box["looked"], newer = time.time(), newer_copy()
            box["new"] = (writes, board_, said, update, newer)
        except Exception as e:                         # the map ends on it, as when it read in its loop
            box["new"] = e
    try:
        sys.stdout.write("\033[?1049h\033[?25l")     # the alternate screen: the shell comes back as it was
        while True:
            fresh = False
            if args.demo:
                vm = demo(demo_step(time.time()))
            while not args.demo:                       # take what the last read brought, start the next
                if reading and not reading.is_alive():
                    new, reading = box.pop("new"), None
                    if isinstance(new, Exception):
                        raise new
                    writes, board_, said, update, restart = new
                    if said and said != told:
                        told = waiting = said
                    waiting = "\n".join(filter(None, [waiting, update]))
                    if writes == box["writes"]:        # a read from before a write never lands after it
                        vm, fresh = board_, True
                if restart:
                    break
                if reading is None and (vm is None or time.time() - fetched >= REFRESH):
                    fetched, reading = time.time(), _beside(world)
                if vm is not None:
                    break
                reading.join()                         # the first frame, and the first after a write:
                getattr(read, "drop", lambda: None)()  # no key typed until now acts on the board it brings
            if restart:                                # a newer Pulse: this map makes room for it
                break
            if waiting and ui["level"] == "map":       # the line waits: never over what a step binds
                status, waiting = waiting, ""
            if not args.demo:
                vm["now"] = time.strftime("%H:%M:%S")
            width, level, n = columns(), ui["level"], ui.get("at")
            frame, rows = int(time.time() / TICK), vm["ramp"].get("rows", [])    # by the clock: all breathe in step
            acts = ()                                  # what the item view offers, as this frame draws it
            if level in ("item", "confirm"):
                if fresh or not seen or seen["number"] != n:
                    seen = look(root, vm, n)
                acts, was = [a for a, *_ in offers(vm, seen)], offered.get(n, [])
                k = ui.get("pick", 0)
                if acts != was and k < len(was):       # the list shifted: the cursor keeps its action, or
                    ui = {**ui, "pick": acts.index(was[k]) if was[k] in acts else 0}   # goes to the top,
                                                           # which never writes without asking first (#55)
                offered = {n: acts}
                lines = render(vm, frame=frame, color=color, width=width, item=dict(seen, pick=ui.get("pick", 0)))
            elif level == "help":                      # under the header, as every screen (#57)
                lines = render(vm, frame=frame, color=color, width=width)[:HEAD] + HELP.split("\n")
            else:
                view = vm
                if level == "move" and n in (r["number"] for r in rows):     # the ramp as it would be
                    rest = [r for r in rows if r["number"] != n]
                    rest.insert(ui["to"], next(r for r in rows if r["number"] == n))
                    view = dict(vm, ramp=dict(vm["ramp"], rows=rest))
                shown = []
                lines = render(view, frame=frame, color=color, width=width, selected=n, picks=shown)
            foot = [part for s in status.split("\n") + [KEYS[level]]   # footers wrap: the end of a refusal
                    for part in textwrap.wrap(s, width, break_on_hyphens=False)] if read else []   # says why (D-45)
            height = shutil.get_terminal_size((WIDTH, 40)).lines or 40     # a pty nobody sized: 0 rows
            cells = [fit(l, width) for l in fitted(lines + foot, height, len(foot))]
            if (width, height) != drawn_at:          # new or resized: draw it whole, once
                out = "\033[H\033[2J" + "\n".join(cells)
            else:                                    # then only the rows that changed, in place
                out = "".join(f"\033[{i + 1};1H{c}\033[K" for i, c in enumerate(cells)
                              if i >= len(drawn) or drawn[i] != c)
                out += f"\033[{len(cells) + 1};1H\033[J" if len(cells) < len(drawn) else ""
            drawn, drawn_at = cells, (width, height)
            if out:
                sys.stdout.write(out)
                sys.stdout.flush()
            if todo:                                   # its line is on the screen: now it runs (#55)
                wrote = todo[0] in DOING
                if wrote and reading:
                    reading.join()                     # no read from before the write lands after it
                try:
                    status = act(root, vm, todo)
                except (state.StateError, ValueError) as e:
                    status = f"! {e}"
                if wrote:
                    box["writes"] += 1
                    vm = None                          # the board as the write left it, at once
                todo = None
                continue
            ch = read(TICK) if read else time.sleep(TICK)
            if ch == "q" and level == "map":
                return 0
            if ch:
                ui, action = key(ui, shown, [r["number"] for r in rows], ch, acts)
                status = ""
                if action and action[0] == "say":
                    status, action = action[1], None
                if action and level == "item" and action[0] in ("approve", "approve-plan", "unapprove"):
                    text, sure = brief(root, vm, action)     # what it binds; Enter confirms it
                    status, action = "\n".join(text), None
                    if sure:
                        ui = {"level": "confirm", "at": n, "sure": sure, "pick": ui.get("pick", 0)}
                if action:                             # the next frame says what runs, then it runs
                    status, todo = DOING.get(action[0], "opening it…").format(action[1]), action
    except KeyboardInterrupt:
        return 0
    finally:
        for s, h in handlers.items():
            signal.signal(s, h)
        try:                                   # after SIGHUP the terminal may be gone
            if keys:
                keys.restore()
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()
        except OSError:
            pass
    if restart:                                # the same terminal, the newer Pulse (IMP-14)
        os.execv(restart, [restart, "map"] + ["--no-color"] * bool(args.no_color) + ["--color"] * bool(args.color))
    return 0
