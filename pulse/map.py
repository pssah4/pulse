"""The Pulse map: who is doing what, what is ready, what goes out next.

One renderer for both commands: `pulse map` and `pulse status` print these
lines. The map is as wide as its terminal (D-45).
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
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from pulse import auto, config, go, lifecycle, merge, order, ready, remove, setup, spec, state

WIDTH = 80                      # columns without a terminal (D-45)
TITLE = 60                      # the most of a file name a row keeps (FIX-02-04-03)
FEWEST, MOST = 44, 160          # the map follows its terminal's width within these, beside a session in Herdr too
LONGEST = 2000                  # the most of a text the map reads: a few of its widest rows (#56 audit L-4)
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
# 16 by 16 dots from the shared P paths in pulse-icon-dunkel.svg and pulse-icon-hell.svg.
# Each Braille cell holds 2 by 4 dots; colors sample the SVG gradients at its lit dots.
SIGNET = ('⠈⢛⣛⣛⣛⡛⢷⡄', '⠸⢛⣛⣛⣛⣫⣼⠇', '⢰⡟⣭⣭⣭⠍⠁', '⢸⠇⠟')
SIGNET_DARK = ('10c1c9 10c1c9 12c1c9 17c3ca 1bc4ca 20c6cb 22c6cc 22c6cb',
               '07b9c3 06bbc5 06bcc6 08bdc7 0abfc8 0ec0c8 11c1c9 17c3ca',
               '0eafb9 0cb2bc 0bb3bd 09b5bf 08b7c1 05bbc5 06bec7', '12a9b3 11aab4 0fadb7')
SIGNET_LIGHT = ('007b84 007c84 007e86 008189 00848b 00878e 008990 00868d',
                '007079 00737c 00767f 007982 007c85 007c84 007880 007a82',
                '00636d 006872 006b75 006d76 006d76 006f79 007179', '005b64 005e68 00606a')
INSET = 10
HEAD = len(SIGNET) + 1          # the header's lines and the blank below it: on every screen (#57)
# what the map asks of a person, the most urgent first, in the color of its state
NEXT = {"failing": "31", "your review": "33", "waits for merge": "33",
        "plan waits for you": "33", "not approved": "33", "spec rule": "90", "spec waits": "90", "last run": "90",
        "needs a plan": "90", "starts next": "90", "queued": "90", "spec in progress": "90", "nothing open": "90"}
SILENT = 30 * 60                # a run's claim without a heartbeat this long shows no sign of life (D-43)
PHASE = {"plan": "planning", "build": "building", "spec tests": "RED check running", "tests": "tests running",
         "check": "review and audit running", "review": "review running", "audit": "audit running",
         "fix": "fix round"}                                                             # pulse go, per feature
# the live map is a tree walked without Shift but for ? (D-44): the map, an item, and what acts on it; below
# the map every way back drops what is not written yet, q too (#55)
UP, DOWN, ENTER, RIGHT = ("\x1b[A", "k"), ("\x1b[B", "j"), ("\r", "\n"), ("\x1b[C",)
BACK = ("\x1b", "\x1b[D", "\x7f", "\x08", "q")
KEYS = {"map": "↑↓ pick m move a approve enter open q quit",       # 44 columns: ? shows the help all the same
        "item": "↑ ↓ pick  a approve  enter do it  esc back",
        "move": "↑ ↓ move  enter save  esc cancel",
        "confirm": "enter confirm  esc cancel",
        "number": "type issue number  enter open  esc cancel",
        "help": "esc back"}
HELP = """map      ↑ ↓ or j k pick a line, enter or →
           opens it, a approves what it
           waits for
         epics in the board are pickable too
         m move: pick unclaimed ramp work;
           arrows move it, enter saves,
           esc cancels
           dependencies always come first
         g opens an issue by number,
           closed too
         ? shows this help, q quits; no key
           but ? needs Shift
item     its goal, stage, holder, blockers,
           PR, and plan, then what you can
           do with it now: ↑ ↓ or j k pick,
           enter does it; it opens on a
           reading one
         PgUp PgDn scroll long details
         defer keeps work as-is in the
           backlog;
           resume continues it explicitly
         discard closes without rollback
         delete removes code, specs and
           issue
           through a separately reviewed PR
         a, approve: the approval it waits
           for, and nothing else; pulse go
           acts on it. Gate 1, approve spec:
           agents may plan it, and pulse go
           merges its docs PR first. Gate 2,
           approve plan: agents may build it
           as that plan says, pushed. After
           pulse:failed, try again
         read plan, read spec: open it in a
           window and the map runs on
           (PULSE_EDITOR, else VS Code or
           Cursor, else the system's app)
         read PR opens its PR in the
           browser; the merge is a person's,
           on GitHub
         a, o: approve spec or plan, read
           spec
auto     1 2 3 switch your auto mode of
           gate 1 plan, 2 build, 3 merge:
           pulse go passes it for your
           items without asking you. The
           head shows yours, others' below
confirm  what it does shows first; enter
           confirms, but not within a second
           of opening it; esc cancels
back     q goes back one level, as esc, ←
           and backspace do, and drops what
           is not written yet
         q quits only on the map, esc never
           quits it; ctrl-c quits anywhere"""
GATE_ROW = re.compile(r"^\| ([a-z][a-z ]*) \| ([^|\n]+) \|(?: [0-9a-f]* \|)?$", re.M)   # a row of pulse go's gate table
# what the item view can offer (#55): the words, and what it does; offers() puts them in order
OFFER = {"approve": ("approve", "the approval it waits for; pulse go acts on it"),
         "read-plan": ("read plan", "open it in a window"),
         "open": ("read spec", "open it in a window"),
         "read-pr": ("read PR", "open it in your browser")}
OFFER.update({"defer": ("defer", "pause as-is in the backlog"),
              "resume": ("resume", "continue the preserved work"),
              "discard": ("discard", "close as not planned; keep code and specs"),
              "delete": ("delete", "review removal of code, specs, issue and comments")})
READS = ("read-pr", "read-plan", "open")      # what the item view opens on: nothing that writes (#99 FR-09)
# the approval a writes at each gate (#115): its words in the item view, and what it lets happen
GATE = {0: ("try again", "pulse:failed goes, pulse go tries it again"),
        1: ("approve spec", "gate 1: agents may plan it"),
        2: ("approve plan", "gate 2: agents may build it as this plan says"),
        3: ("approve merge", "gate 3: pulse go merges its PR at this head")}
# the line an action shows while it runs; the ones not named here only open a window
DOING = {"approve": "approving #{}…", "auto": "switching {}…"}
DOING.update({action: action + " #{}…" for action in lifecycle.ACTIONS})
SMALL = "the terminal is too low or too narrow to show what enter would confirm: make it larger"   # #76, #56
SOON = 1.0                      # seconds after a confirmation opened in which an Enter came unread (#86, #90)
VERB = {"Edit": "editing", "MultiEdit": "editing", "Write": "writing", "NotebookEdit": "editing",
        "Read": "reading", "Bash": "running", "Grep": "searching", "Glob": "searching",
        "Agent": "delegating", "Task": "delegating", "WebFetch": "reading", "WebSearch": "searching",
        "TodoWrite": "planning", "Skill": "using"}


def _cols(c: str) -> int:
    """The columns a character fills in a terminal (#56): two for a wide one (CJK), none for a combining
    mark, but one for a spacing mark (Mc), as terminals draw it (final check M-2)."""
    return 2 if unicodedata.east_asian_width(c) in "WF" else \
        0 if unicodedata.combining(c) and unicodedata.category(c) != "Mc" else 1


def wide(s: str) -> int:
    """The most columns s fills in any terminal: two for every character that is not ASCII, as no terminal
    draws one wider. What a confirmation shows is measured so (#56 final check M-2)."""
    return 2 * len(s) - len(s.encode("ascii", "ignore"))


def _pieces(s: str, w: int) -> list:
    """s in pieces of w columns at most by wide(), each as long as it can be; one pass."""
    out, piece, used = [], [], 0
    for c in s:
        n = 1 if c.isascii() else 2
        if used + n > w and piece:
            out.append("".join(piece))
            piece, used = [], 0
        piece.append(c)
        used += n
    return out + ["".join(piece)]


def vlen(s: str) -> int:
    t = ANSI.sub("", s)
    return len(t) if t.isascii() else sum(map(_cols, t))


def fit(s: str, w: int) -> str:
    """Exactly w columns: cut without splitting an escape or a wide character, then pad."""
    if vlen(s) > w:
        out, used = [], 0
        for part in re.split(f"({ANSI.pattern})", s):
            if part.startswith("\033"):
                out.append(part)
                continue
            for c in part:
                if used + _cols(c) > w:
                    used = w + 1        # nothing after the cut, not even a narrow character that fits
                    break
                out.append(c)
                used += _cols(c)
        s = "".join(out) + ("\033[0m" if ANSI.search(s) else "") + ("\033]8;;\033\\" if "\033]8" in s else "")
    return s + " " * (w - vlen(s))


def beside(left: str, w: int) -> int:
    """How wide the note beside left may be (D-45): what left leaves, and at least STATE of the line."""
    return max(int(w * STATE), w - vlen(left.rstrip()) - 2)


def short(s: str, most: int) -> str:
    """s in most columns at most: where it is wider, cut short with an ellipsis."""
    return s if vlen(s.rstrip()) <= most else fit(s, most - 1) + "…"


def lr(left: str, right: str, w: int) -> str:
    """left text, right note, two spaces apart: the note gets beside(left), the left the rest; a
    side cut short ends in an ellipsis."""
    right = short(right, beside(left, w))
    room = w - vlen(right) - 2
    return fit(fit(short(left, room), room) + "  " + right, w)


def wrap(s: str, w: int) -> list:
    """s in rows of w columns at most by wide() (D-45, #56): broken at spaces, which a break drops, and a
    word wider than a row cut across rows of its own. Each row fits a row of any terminal, so a
    confirmation takes no more rows than shows() counts (final check M-2)."""
    rows = []
    for word in re.findall(r" *[^ ]+", s):         # each word with the spaces before it
        if rows and wide(rows[-1]) + wide(word) <= w:
            rows[-1] += word
            continue
        rows += _pieces(word.lstrip(" ") if rows else word, w)
    return rows


def _row(s: str, w: int) -> str:
    """s fit for one footer row of w columns in any terminal: printable, cut short with … (#56 M-1, M-2)."""
    s = ready.printable(s)
    return s if wide(s) <= w else _pieces(s[:w], w - 2)[0] + "…"      # w characters hold the first piece


def footer(status: str, keys: str, w: int) -> list:
    """The rows below the map: the status, then the keys, wrapped at w columns so that the end of a
    refusal says why (D-45), and without a character that is not printable (#56)."""
    return [row for s in status.split("\n") + [keys] for row in wrap(ready.printable(s), w)]


def depth(env=os.environ) -> int:
    """How many colors the terminal shows (D-38): truecolor, 256, else 16."""
    if env.get("COLORTERM", "") in ("truecolor", "24bit"):
        return TRUE
    return 256 if "256color" in env.get("TERM", "") else 16


def rgbcode(rgb, colors: int) -> str:
    """An RGB foreground as truecolor or the nearest in the 256-color cube."""
    if colors >= TRUE:
        return "38;2;%d;%d;%d" % tuple(rgb)
    steps = (0, 95, 135, 175, 215, 255)
    r, g, b = (min(range(6), key=lambda k: abs(steps[k] - c)) for c in rgb)
    return f"38;5;{16 + 36 * r + 6 * g + b}"


def glow(level: float, colors: int) -> str:
    """The SGR color of a working light at this brightness."""
    return rgbcode([round(d + (g - d) * level) for g, d in zip(GREEN, DARK)], colors)


class Paint:
    def __init__(self, color: int):
        self.color = int(color)         # colors the terminal shows; 0 none, True means 16

    def __call__(self, s: str, code: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.color and s else s

    def link(self, text: str, url) -> str:
        """text as a terminal link to url (OSC 8), with color only: a pipe gets no escapes."""
        return f"\033]8;;{url}\033\\{text}\033]8;;\033\\" if self.color and url else text


def signet(colors: int, env=os.environ) -> list:
    """Four rows, with the light SVG's petrol or the dark SVG's aqua gradient."""
    paint = Paint(colors)
    if colors < 256:
        return [paint(row, "36") for row in SIGNET]
    # ponytail: COLORFGBG reports the theme; query OSC 11 if unreported light backgrounds need detection.
    palette = SIGNET_LIGHT if env.get("COLORFGBG", "").rsplit(";", 1)[-1] in ("7", "15") else SIGNET_DARK
    return ["".join(paint(glyph, rgbcode(bytes.fromhex(hexrgb), colors))
                    for glyph, hexrgb in zip(row, shades.split())) for row, shades in zip(SIGNET, palette)]


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


def _plain(x):
    """x with every string in it fit for the map (#56): LONGEST characters of it at most, its first line,
    every other character that is not printable as ?, in dicts (keys too), lists, and tuples. Text from
    issues and branches."""
    if isinstance(x, str):
        x = x[:LONGEST]                 # no row shows more, and a frame takes no longer for a long text
        return x if x.isprintable() else ready.printable(next(iter(x.splitlines()), ""))
    if isinstance(x, dict):
        return {_plain(k): _plain(v) for k, v in x.items()}
    return type(x)(map(_plain, x)) if isinstance(x, (list, tuple)) else x


def clean(text) -> str:
    """A name fit for a terminal (FIX-02-04-03 FR-06): printable characters only, whitespace
    collapsed, TITLE long at most."""
    return " ".join("".join(c if c.isprintable() else " " for c in str(text or "")).split())[:TITLE]


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


def _run(i: dict) -> bool:
    """Whether a run of pulse go holds i: only it renews the time on its claim (D-43); since #107 no hook does
    that for a session, whose claim shows how long it is held instead."""
    return (i.get("claimed_holder") or "").startswith("go:")


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
    its claim holds, wherever its directory stands (FIX-02), else for the item of its branch; the
    branch of a fork's PR, named in the fork, builds no item here (#63)."""
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
                (x for x in vm["items"] if b and (x.get("pr") or {}).get("branch") == b and not x["pr"].get("fork")),
                None)
            own = holds.get(a["id"]) or holds.get(s["id"]) or []
            if own and i not in own:
                i = own[0]
            feats.setdefault(i["number"] if i else (b or "no branch"), []).append(a)
    return feats


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
           picks: list = None, item: dict = None, stages: dict = None) -> list:
    """color: how many colors the terminal shows (depth()), 0 for none; selected: the item the
    terminal cursor is on (marked ›); picks: gets the items on the map top down, the way the cursor
    walks them; item: the item view in place of the map (D-44), its number and what look() read;
    stages: gets the stage of every item in the map's words, as pulse status <n> prints it (#99 FR-14).
    Only the map writes escapes: every string of vm and item loses its control characters first (#56)."""
    vm, item, p, w = _plain(vm), _plain(item), Paint(color), width
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
                return "error", f"failed: {failed[n]}".replace("PLAN", "plan"), fix
            if n in phases:                   # a job of pulse go: working, whether its agent reports or not
                return "working", PHASE.get(phases[n], phases[n]), None
            if n in vm["ramp"].get("plan_waits", ()):     # /pulse-build keeps the claim meanwhile; whose (#99 FR-14)
                if mine(i):
                    return "waiting", "plan waits for you", ("plan waits for you", f"pulse approve {n}")
                return "idle", f"plan waits for {i.get('claimed_by') or i['assignees'][0]}", None
            beat = i.get("claimed_beat")
            if beat and not mine(i) and _run(i):      # the run's last sign of life (D-43)
                return "idle", _life(i.get("claimed_phase") or "working", beat), None
            return "idle", "no PR yet", None
        ref = f"PR #{pr['number']}"
        if pr.get("checks") == "fail":
            return "error", f"{ref}, checks failing", fix
        if pr.get("draft"):                   # pulse go opens a draft only when a gate is red (D-19)
            return "error", f"draft {ref}, a gate is red", ("failing", f"/pulse-build {n} fixes it in a session, or "
                                                            "the next pulse go takes it up") if mine(i) else None
        if vm["me"] and vm["me"] in pr.get("reviewers", []):
            return "waiting", f"{ref}, needs your review", ("your review", f"review {ref} on GitHub")
        if mine(i) and not pr.get("fork") and pr.get("base") not in (None, vm.get("base")):   # stacked, older Pulse
            return "waiting", f"{ref} targets {pr['base']}", ("waits for merge",
                                                              f"retarget {ref} to {vm.get('base')} on GitHub")
        if mine(i):                           # the map merges nothing (#115): a person on GitHub, until gate 3
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
        if s == "not approved":               # approve writes gate 1, pulse go merges the docs PR (#115)
            if n in vm.get("unready", ()):    # a spec on the base that breaks R2 to R6 there
                return "idle", ("spec rule", f"/pulse-re on the spec of #{n}")
            if n in vm.get("nowhere", ()):    # no spec, or neither on the base nor in an open pull request: what
                return "idle", ("spec waits", f"/pulse-re {'pushes' if row.get('spec') else 'writes'} the spec "
                                              f"of #{n}")      # approve cannot move is grey (#99 FR-12)
            return "waiting", (s, f"pulse approve {n}, or approve spec in its view")
        if s.startswith("spec:"):
            return "idle", ("spec rule", f"/pulse-re on the spec of #{n}")
        if s.startswith(ready.WAITS):
            return "waiting", ("plan waits for you", f"pulse approve {n}, or approve plan in its view")
        if s.startswith(ready.MOVED):          # its docs PR moved since gate 1 (M-1)
            return "waiting", ("docs PR changed", f"pulse approve {n}, or approve spec in its view")
        if row.get("note"):                   # a run gave it back (D-43); its branch holds the work
            return "idle", ("last run", f"/pulse-build {n} goes on from where it stopped")
        if s == "needs a plan":
            return "idle", (s, "pulse go writes its plan")
        return "idle", ("starts next", "pulse go builds it") if s.startswith("starts next") else \
            ("queued", "waits for a free slot") if s.startswith("queued") else None      # #99 FR-12

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
        grey = stage.startswith("not approved") and row not in groups["blocked"] and wants(row)[0] == "idle"
        return stage.replace("PLAN", "plan"), "31" if stage.startswith(("locked", "failed")) else \
            "33" if stage.startswith(("waits for", "plan waits", "spec:", "plan:", "not approved")) and not grey \
            else "90"

    feats = places(vm)                    # feature (or branch without one) -> every agent on it
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
        held = i.get("claimed_at") or i.get("claimed_beat")
        since = f", held {_age(held)}" if held and not mine(i) and not i.get("pr") \
            and not (_run(i) and i.get("claimed_beat")) else ""
        return st, words + since

    if stages is not None:
        stages.update({i["number"]: gate(i)[1] for i in vm["items"]})

    def inside(seen) -> list:
        """The item view: what the item is for, where it stands, who holds it, what it waits for."""
        i = by_number.get(seen["number"])
        if not i:
            return [p(f"#{seen['number']} is merged or closed", "90")]
        n, pr, beat = i["number"], i.get("pr") or {}, i.get("claimed_beat")
        st, words = gate(i)
        operation = i.get("lifecycle") or {}
        if operation and operation.get("phase") != "resumed":
            words = f"{operation.get('action', 'lifecycle')}: {operation['phase']}"
        elif i.get("state") == "CLOSED":
            words = "closed"
        who, phase = i.get("claimed_by") or next(iter(i["assignees"]), ""), phases.get(n) or i.get("claimed_phase")
        held = i.get("claimed_at") or beat
        life = _life(phase or "working", beat) if beat and _run(i) else f"held {_age(held)}" if held and not _run(i) \
            else PHASE.get(phase, phase) if phase else ""
        got = seen.get("approvals")                # a list, None when GitHub did not answer, or READING
        said = [got] if isinstance(got, str) else [f"gate {g} by @{login}, {_when(at)}" for g, login, at in got or ()] \
            or ["none" if got == [] else "could not be read"]
        facts = [("goal", seen["goal"] or "-"), ("stage", p(words or "-", tone.get(st, "90")))] + \
            [(k, v) for k, v in zip(["approvals"], said[:1]) if "approvals" in seen] + \
            [("", v) for v in said[1:]] + [
                 ("holder", ", ".join(filter(None, [who, life])) if who else "nobody"),
                 ("blocked by", _refs(i["blocked_by"], w - 13) if i["blocked_by"] else "nothing"),
                 ("PR", ", ".join(filter(None, [f"#{pr['number']}", pr.get("draft") and "draft",
                                                 pr.get("checks") and f"checks {pr['checks']}"])) if pr else "none"),
                 ("spec", i.get("spec") or "none"), ("plan", seen["plan"] or "none yet")]
        menu = offers(vm, seen)
        pick = min(seen.get("pick", 0), len(menu) - 1)
        choice = [(p(f" › {words:<14}", "1") if k == pick else f"   {words:<14}")
                  + p(note, "33" if note.startswith("not yet") else "90")
                  for k, (_, words, note) in enumerate(menu)] or [p("   nothing to do here now", "90")]
        title = wrap(f"#{n} {i['title']}", w)
        title[0] = title[0].replace(f"#{n}", p.link(f"#{n}", i.get("url")), 1)
        heading = [section(title[0])] if len(title) == 1 else [p(line, "1;36") for line in title]
        details = []
        for label, value in facts:
            pieces = wrap(value, w - 13) if label == "goal" else [value]
            details += [f" {label if index == 0 else '':<12}{piece}" for index, piece in enumerate(pieces)]
        return heading + [""] + details + [""] + choice
    parts = [(dot("working") if counts["working"] else dot("idle")) + f" {counts['working']} working"]
    if counts["waiting"]:
        parts.append(dot("waiting") + f" {counts['waiting']} need{'s' if counts['waiting'] == 1 else ''} you")
    if counts["error"]:
        parts.append(dot("error") + f" {counts['error']} failing")
    warn = "; ".join(filter(None, (vm.get("error"), vm.get("halt"), vm.get("untrusted"),
                                  (vm.get("order") or {}).get("why"))))
    inset = INSET if w >= 60 else 0       # beside a session the header keeps its words and leaves out the signet
    head = [lr(p("pulse", "1") + "  " + p(vm["repo"] or "no repo", "90") + "  " + vm["person"], p(vm["now"], "1"),
                   w - inset),
            "   ".join(parts), p("! " + warn, "33") if warn else ""]
    mark = signet(p.color)
    switched = vm.get("auto") or {}
    mode = p(vm["auto_why"], "31") if vm.get("auto_why") else \
        "auto you  " + auto.line(switched.get(vm["me"], {}), sep="  " if inset else " ")    # 44 columns hold it
    out = [(fit(mark[index], inset) if inset else "") + text for index, text in enumerate(head + [mode])]
    out.append("")
    if item:                              # the item view (D-44), live like the map
        return [fit(l, w) for l in out + inside(item)]
    theirs = [p(f"auto @{login}  {auto.line(gates, only_on=True)} (their items)", "90")
              for login, gates in sorted(switched.items(), key=lambda x: x[0].lower())
              if login != vm["me"] and any(s["on"] for s in gates.values())]
    out += theirs + [""] * bool(theirs)

    # --- board ------------------------------------------------------------
    total = max(1, sum(map(len, groups.values())))
    out.append(section("BOARD"))
    for (label, group), code in zip(groups.items(), ("36", "32", "35", "33", "90")):
        n = len(group)
        filled = max(1, round(n * 24 / total)) if n else 0
        out.append(f" {label:<15}" + p("█" * filled, code) + p("░" * (24 - filled), "90") + f"{n:>4}")
    epics = []
    for e in (i for i in vm["items"] if i["type"] == "epic"):
        done = vm.get("closed", {}).get(e["number"], 0)
        total = done + sum(i.get("parent") == e["number"] for i in vm["items"])
        if total:
            epics.append((e, round(10 * done / total), f"{done} of {total} done"))
    if epics:
        out.append("")
    count_width = max((vlen(count) for _, _, count in epics), default=0)
    title_width = w - 13 - count_width
    for epic, filled, count in epics:
        number = epic["number"]
        if number not in shown:
            shown.append(number)
        ref = p.link(f"#{number}", epic.get("url"))
        title = ("› " if number == selected else " ") + ref + " " + epic["title"]
        label = fit(short(title, title_width), title_width)
        out.append((p(label, "1") if number == selected else label) + "  " +
                   p("█" * filled, "32") + p("░" * (10 - filled), "90") + " " + fit(count, count_width))
    out.append("")

    # --- who is doing what ------------------------------------------------
    out.append(section("WHO IS DOING WHAT"))

    def focus(agents):
        """The agent to show: one that needs you or failed first, then the latest activity."""
        return min(agents, key=lambda a: (RANK.index(a["state"]), -a.get("last", 0)))

    def said(agents) -> tuple:
        """What the agents on one line do: the one focus picks."""
        return _doing(focus(agents))

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
        if state_ in todo:
            out.append(lr(" " + p(state_, NEXT[state_]), todo[state_], w))
    out.append("")

    # --- ramp ---------------------------------------------------------------
    out.append(section("RAMP", "all open work, in the order it goes out"))
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


def terminal_size():
    try:
        size = os.get_terminal_size(sys.__stdout__.fileno())
        if size.columns > 0 and size.lines > 0:
            return size
    except (AttributeError, ValueError, OSError):
        pass
    return shutil.get_terminal_size((WIDTH, 40))


def columns() -> int:
    """How wide the map is (D-45): as its terminal, else COLUMNS (pulse status, a pipe), else 80;
    always 44 to 160 columns. The live map asks on every frame."""
    try:
        cols = os.get_terminal_size(sys.__stdout__.fileno()).columns
    except (AttributeError, ValueError, OSError):
        cols = 0
    if cols <= 0:                       # none, or a pty nobody sized: 0 columns
        cols = shutil.get_terminal_size((WIDTH, 40)).columns or WIDTH
    return max(FEWEST, min(MOST, cols))


def once(vm: dict, color) -> str:
    """One frame as wide as columns() says: `pulse status`, and `pulse map` in a pipe.
    color: True for the terminal's depth, else as render() takes it."""
    return "\n".join(render(dict(vm, once=True), color=depth() if color is True else color, width=columns()))


def offers(vm: dict, seen: dict) -> list:
    """[(action, words, what it does)]: what the item view offers in the item's stage (#55): the approval it waits
    for (#115), merge, read PR, read plan, read spec. An approval that cannot be given now says why in place of
    what it does."""
    i = next((x for x in vm["items"] if x["number"] == seen["number"]), None)
    if not i:
        return []
    n, ramp = i["number"], vm["ramp"].get("rows", [])
    stage = next((r["stage"] for r in ramp if r["number"] == n), "")
    gate = 0 if i.get("failed") else 1 if not i["approved"] or stage.startswith(ready.MOVED) else \
        2 if n in vm["ramp"].get("plan_waits", ()) or stage.startswith(ready.WAITS) else None
    why = ""
    if gate == 1 and i.get("draft"):
        why = "not yet: its spec is still being written"
    elif gate == 1 and not i.get("spec"):
        why = "not yet: it has no spec, /pulse-re writes one"
    elif gate == 1 and n in vm.get("nowhere", ()):
        why = "not yet: its spec is neither on the base nor in an open pull request"
    elif gate == 1 and n in vm.get("unready", ()):
        why = "not yet: its spec breaks a rule, /pulse-re fixes it"
    elif gate == 1 and i.get("type") == "epic":
        why = "approves the epic; its features are approved one by one"
    said = seen.get("waiting")                 # what pulse approve would write now, as the live map asked (#121)
    if said and not why.startswith("not yet"):
        if said[0] is not None:
            gate = said[0]
        elif gate is not None:                 # the row says why, and a writes nothing
            why = "not yet: " + re.sub(r"^#\d+ not approved: ", "", said[2]).replace("PLAN", "plan")
    out = [] if gate is None else [("approve", GATE[gate][0], why or GATE[gate][1])]
    pr = i.get("pr") or {}
    out += [(a, *OFFER[a]) for a in ["read-pr"] * bool(pr) + ["read-plan"] * bool(seen.get("plan")) +
            ["open"] * bool(i.get("spec"))]
    if i.get("state") == "CLOSED" or i.get("hold"):
        out = [entry for entry in out if entry[0] != "approve"]
    if i.get("type") in state.WORK:
        operation = i.get("lifecycle") or {}
        actions = ["discard", "delete"]
        if i.get("state", "OPEN") == "OPEN":
            actions.insert(0, "resume" if operation.get("action") == "defer" and
                           operation.get("phase") == "paused" else "defer")
        out += [(action, *OFFER[action]) for action in actions]
    return out


def key(ui: dict, picks: list, ch: str, acts=()) -> tuple:
    """(ui, action) for one key of the live map, a tree walked without Shift (D-44). ui: the level
    (map, item, confirm, help), the item it is at, in the item view the action picked, the approval
    Enter confirms, and the level the help began on. picks: the items on the map, top down; acts:
    what the item view offers (offers())."""
    level, n = ui["level"], ui.get("at")
    if level == "move":
        if ch in BACK:
            return {"level": "map", "at": n}, None
        if ch in UP + DOWN:
            target = max(0, min(ui["count"] - 1, ui["target"] + (-1 if ch in UP else 1)))
            return ui, ("move-preview", n, target)
        return ui, ("move-save", n) if ch in ENTER and not ui.get("invalid") else None
    if level == "number" or level == "confirm" and "expected" in ui:
        back = {"level": "map" if level == "number" else ui.get("from", "item"), "at": n}
        typed = ui.get("typed", "")
        if ch in ("\x1b", "\x1b[D"):
            return back, None
        if ch in ("\x7f", "\x08"):
            return {**ui, "typed": typed[:-1]}, None
        if ch in ENTER:
            if level == "number" and typed and int(typed) > 0:
                return back, ("lookup", int(typed))
            if level == "confirm" and typed == ui["expected"]:
                return back, ui["sure"]
            return ui, None
        allowed = ch in "0123456789" if level == "number" else len(ch) == 1 and ch.isprintable()
        limit = 10 if level == "number" else len(ui["expected"])
        return ({**ui, "typed": typed + ch} if allowed and len(typed) < limit else ui), None
    if level == "map":
        if ch == "m" and n in picks:
            return ui, ("move", n)
        if ch == "g":
            return {"level": "number", "at": n, "typed": ""}, None
        if ch in UP + DOWN and picks:
            k = picks.index(n) if n in picks else -1
            return {**ui, "at": picks[max(0, k - 1) if ch in UP else min(len(picks) - 1, k + 1)]}, None
        if ch in ENTER + RIGHT and n in picks:
            return {"level": "item", "at": n}, None
        if ch == "a" and n in picks:              # the approval the picked item waits for (#121 FR-04)
            return ui, ("approve", n)
        if ch in ("1", "2", "3"):                 # your auto mode of gate 1, 2, 3 (#124 FR-09)
            return ui, ("auto", auto.GATES[int(ch) - 1])
        if ch == "?":
            return {"level": "help", "at": n, "from": "map"}, None
        return ui, ("say", "q quits the map") if ch in BACK else None     # Esc never ends it (D-44)
    back = {"level": ui.get("from", "item"), "at": n}     # the help ends where it began
    if back["level"] == "item":
        back["pick"] = ui.get("pick", 0)
    if ch in BACK:                              # one level up, and what is not written yet is dropped
        return (back if level != "item" else {"level": "map", "at": n}), None
    if level == "item":
        if ch in ("\x1b[5~", "\x1b[6~"):
            step = ui.get("page", 1) * (-1 if ch == "\x1b[5~" else 1)
            return {**ui, "scroll": max(0, ui.get("scroll", 0) + step)}, None
        pick = min(ui.get("pick", 0), len(acts) - 1) if acts else ui.get("pick", 0)   # the offers may have changed
        if ch in UP + DOWN:
            return ({**{k: v for k, v in ui.items() if k != "scroll"},
                     "pick": max(0, pick - 1) if ch in UP else min(len(acts) - 1, pick + 1)}
                    if acts else ui), None
        if ch == "?":
            return {"level": "help", "at": n, "from": "item", "pick": pick}, None
        if ch in ENTER and acts:
            return ui, (acts[pick], n)
        return ui, {"a": ("approve", n), "o": ("open", n)}.get(ch)
    if level == "confirm":                      # any other key: no approval
        return back, ui["sure"] if ch in ENTER else None
    return ui, None


def move(root: Path, vm: dict, ui: dict, action: tuple, size: tuple) -> tuple:
    """Start from fresh authority; arrows only replace an in-memory proposal."""
    kind, number = action[:2]
    if not auto.person(os.environ, True):
        raise state.StateError("only a person moves items, in their own terminal or map")
    if kind == "move":
        candidate = next((record for record in vm["ramp"].get("rows", []) if record["number"] == number), {})
        if candidate.get("type") not in state.WORK or candidate.get("assignees") or candidate.get("claimed_holder"):
            raise state.StateError(f"#{number} is not an unclaimed work item on the ramp")
        if vm.get("error") or (vm.get("order") or {}).get("why"):
            raise state.StateError(vm.get("error") or vm["order"]["why"])
        items, seen = order._fresh(vm["repo"], state.gh)
        positions = seen["positions"]
        movable = [record["number"] for record in ready.order([
            dict(record, manual_position=positions.get(record["number"])) for record in items])
                   if record.get("type") in state.WORK and not record.get("assignees")
                   and not record.get("claimed_holder")]
        if number not in movable:
            raise state.StateError(f"#{number} is no longer an unclaimed work item")
        ui = {"level": "move", "at": number, "target": movable.index(number), "count": len(movable),
              "items": items, "order": seen, "size": size, "repo": vm["repo"],
              "board_binding": order._binding(vm["items"]), "board_revision": (vm.get("order") or {}).get("revision")}
    if kind == "move-save":
        if ui.get("invalid") or tuple(terminal_size()) != ui["size"]:
            raise state.StateError("move cancelled: its target or terminal size changed")
        result = order.apply(root, ui["repo"], ui["proposal"], run=state.gh)
        return {"level": "map", "at": number}, result["why"] or f"saved the shared order for #{number}"
    target = action[2] if kind == "move-preview" else ui["target"]
    proposal = order.preview(ui["items"], ui["order"], number, target)
    positions = {identifier: position for position, identifier in enumerate(proposal["items"])}
    items = [dict(record, manual_position=positions.get(record["number"])) for record in ui["items"]]
    ramp = ready.view(root, items, config.load(root), vm["me"])
    preview_vm = {**vm, "ramp": ramp}
    return {**{key: value for key, value in ui.items() if key != "opened"}, "target": target,
            "proposal": proposal, "vm": preview_vm, "invalid": False}, \
        f"move #{number}: position {target + 1} of {ui['count']}; preview only, enter saves"


def brief(root: Path, vm: dict, action: tuple) -> tuple:
    """What a person reads before a approves (F6.08): the approval it writes, the goal, what holds it, and for a
    PLAN the blobs the approval binds to, as pulse approve reads them (#115). (lines, the action Enter confirms),
    or (why not, None). A goal takes one row of the map, so what an approval binds stays on the screen (#56 audit
    M-1)."""
    kind, n = action
    if not auto.person(os.environ, True):     # its keys come from a terminal: an agent's marker is what tells
        return ["only a person does this, in their own terminal or map; tell the person which gate waits"], None
    if kind in lifecycle.ACTIONS:
        planned = remove.action_preview(root, vm["repo"], n, run=state.gh) if kind == "delete" else \
            lifecycle.preview(root, vm["repo"], n, kind, run=state.gh)
        return planned["lines"], (kind, n, planned) if planned.get("confirmation") else None
    if kind == "auto":                        # n: the gate; a short confirmation (#124 FR-09)
        if vm.get("auto_why") or not vm.get("me"):
            return [vm.get("auto_why") or "no GitHub login known: gh auth login"], None
        switch_on = not auto.on(vm.get("auto") or {}, vm["me"], n)
        return [auto.short(n, switch_on, vm["me"])], ("auto", n, switch_on)
    one = lambda goal: _row(f"goal: {goal or '-'}", columns())
    as_ = f" as {vm['person']}" if vm.get("person") else ""       # the account the lever acts as (#111)
    i = next((x for x in vm["items"] if x["number"] == n), {})
    if not i:                                 # merged or closed while its view stood (#99 FR-12)
        return [f"#{n} is merged or closed"], None
    gate, blobs, why = ready.waiting(root, i)
    if gate is None:
        return [ready.printable(why.replace("PLAN", "plan"))], None
    text = spec.find(root, i["spec"])[0] if i.get("spec") else None      # on the base, else in its docs PR
    plan = ready._git(root, "cat-file", "blob", blobs[0]) if gate == 2 else ""
    head = [f"try #{n} {i.get('title', '')} again{as_}: {GATE[0][1]}",
            f"approve spec #{n} {i.get('title', '')}{as_}: {GATE[1][1]}",
            f"approve the plan of #{n} at {' '.join(b[:12] for b in blobs)}{as_}: {GATE[2][1]}",
            f"approve the merge of #{n} {i.get('title', '')} at {' '.join(b[:12] for b in blobs)}{as_}: {GATE[3][1]}"][gate]
    goal = spec.sections(plan).get("goal", "").strip().split("\n")[0] if plan else _goal(text)
    holds = f"holds: {ready.hold(text or '', plan).replace('risk: ', 'risk ') or 'none'}"
    if gate == 3:              # what waits for a person in the PR, before the approval is written (L-2 of #118)
        try:
            holds = merge.seen(root, state.repo(root, run=state.gh), i["pr"]["number"], state.gh, "it")
        except (state.StateError, ValueError) as e:
            return [ready.printable(f"#{n}: what its PR changes is not known ({e})")], None
    return [ready.printable(line) for line in (head, one(goal), holds)], (kind, n, gate, blobs)


APPROVAL = re.compile(r"(?:gate ([123]) (?:approved by|ok at)|(plan) ok at|(merge) ok at)\b")   # as pulse approve writes them


def approvals(comments) -> list:
    """[(gate, login, at)]: the approvals among an item's comments, each by the GitHub account that wrote it and
    when, oldest first; the comment of someone who may not push is none (#121 FR-05)."""
    return [(int(m.group(1) or (2 if m.group(2) else 3)), (c.get("author") or {}).get("login") or "?",
             c.get("createdAt") or "")
            for c in comments or () for m in [APPROVAL.match(c.get("body") or "")]
            if m and c.get("authorAssociation") in state.WRITERS]


READING = "reading…"            # the approvals of an item view until GitHub answered


def read_approvals(vm: dict, n: int):
    """The approvals of item n, read from GitHub once as its view opens, beside the keys (L-3); None when GitHub
    did not answer."""
    try:
        return approvals(json.loads(state.gh(["issue", "view", str(n), "--repo", vm["repo"], "--json", "comments"],
                                             timeout=10)).get("comments"))
    except (state.StateError, OSError, ValueError, AttributeError):
        return None


def waits(root: Path, vm: dict, n: int):
    """ready.waiting for item n, the approval a would write now or why none (#121); None when it cannot say."""
    i = next((x for x in vm["items"] if x["number"] == n), None)
    try:
        return ready.waiting(root, i) if i else None
    except (state.StateError, OSError, ValueError, KeyError, TypeError):
        return None


def _when(at: str) -> str:
    """An ISO time of GitHub as the clock here shows it: 27.09. 16:40."""
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone().strftime("%d.%m. %H:%M")
    except (ValueError, AttributeError):
        return at or "?"


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
    """What the item view reads from git: the goal of the spec on the base, else on the branch of origin
    that has it (#68), and where the PLAN is."""
    i = next((x for x in vm["items"] if x["number"] == n), {})
    p = ready.plans(root).get(n)
    return {"number": n, "goal": _goal(spec.find(root, i["spec"])[0] if i.get("spec") else None),
            "plan": p["path"] + (f" on {p['ref']}" if p["ref"] else "") if p else ""}


def by_number(root: Path, vm: dict, number: int) -> dict:
    if type(number) is not int or number <= 0:
        raise state.StateError("enter a positive issue number")
    raw = lifecycle._read(vm["repo"], number, state.gh)
    trusted = lifecycle.trusted(vm["repo"], state.gh)
    found = state.normalize(raw, lambda entry: trusted(entry) is True, lifecycle_trusted=trusted)
    if found["type"] not in (*state.WORK, "epic"):
        raise state.StateError("this issue is not a Pulse item")
    return {**found, "state": raw.get("state", "OPEN")}


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
    """Carry out one action from the map; returns a line for the status bar. An approval writes what brief()
    showed, and only while the item still waits for it: the gate and blobs come with the action (#115)."""
    kind, n = action[0], action[1]
    if kind in DOING and (vm.get("error") or vm.get("rate_limit")):
        raise state.StateError("the board is not current; wait for a successful fresh read before writing")
    repo = state.repo(root, run=state.gh)
    if kind in lifecycle.ACTIONS:
        planned = action[2]
        apply = remove.apply_action if kind == "delete" else lifecycle.apply
        return apply(root, repo, planned, planned["confirmation"], run=state.gh)
    if kind == "auto":                          # n: the gate, as brief() showed it
        return auto.toggle(root, repo, n, action[2], run=state.gh)
    if kind == "approve":
        current = next((i for i in vm["items"] if i["number"] == n), None)
        if current is None or current.get("hold") or current.get("state") == "CLOSED":
            return f"#{n} is held or closed; nothing approved"
        gate, blobs, why = ready.waiting(root, current)
        if gate is None:
            return ready.printable(why.replace("PLAN", "plan"))
        if tuple(action[2:]) != (gate, blobs):
            return f"#{n} changed since you read it; a shows it again"
        state.approve(root, repo, n, gate, blobs)
        return f"#{n} approved, waits for pulse go"
    if kind == "read-pr":
        i = next((x for x in vm["items"] if x["number"] == n), {})
        pr = (i.get("pr") or {}).get("number")
        if not pr:
            return f"#{n} has no PR"
        url = re.sub(r"/issues/\d+$", f"/pull/{pr}", i.get("url") or "")     # a link: the system's opener (#61)
        return _show(url, f"PR #{pr}", opener({})) if "/pull/" in url else f"#{n}: no link to PR #{pr}"
    if kind == "read-plan":
        plan = ready.plans(root).get(n)
        if not plan:
            return f"#{n} has no plan"
        if not plan["ref"]:
            return _show(root / plan["path"], plan["path"])
        return _copy(root, "plans", n, plan["path"], plan["text"], plan["ref"])     # on its branch only
    item = next((i for i in vm["items"] if i["number"] == n), {})
    if not item.get("spec"):
        return f"#{n} has no spec"
    path = item["spec"]                         # from the issue text: it may point anywhere (#56)
    here = (root / path).resolve()
    if not here.is_relative_to(root.resolve()):
        return f"#{n}: its spec path leads out of the repository; nothing opened"
    if not path.endswith(".md") or here.suffix != ".md":    # the opener picks a program by it, a link's target
        return f"#{n}: its spec is no Markdown file; nothing opened"       # too (audit and final check of #68)
    text, ref = spec.find(root, path)           # what agents plan from, else its branch (#68)
    if text is None:
        try:
            there = here.is_file()
        except OSError as e:                    # a path the system refuses, longer than it takes (#56 L-5)
            return f"#{n}: the system cannot read its spec path ({e.strerror}); nothing opened"
        return _show(root / path, path) if there else f"#{n}: its spec {path} is on no branch of origin and not here"
    try:
        same = here.read_text(encoding="utf-8") == text
    except (OSError, UnicodeDecodeError):
        same = False
    return _show(root / path, path) if same else _copy(root, "specs", n, path, text, ref)


def _copy(root: Path, kind: str, n: int, path: str, text: str, ref: str) -> str:
    """Open a copy to read of path as ref has it, named by the item, in the clone's cache: a new file,
    never written through a link at its place (audit of #55)."""
    copy = state.cache_dir(root) / kind / f"{n}-{Path(path).name}"
    try:
        copy.parent.mkdir(parents=True, exist_ok=True)
        if copy.is_symlink() or copy.exists():
            copy.unlink()
        copy.write_text(text, encoding="utf-8")
    except OSError as e:
        return f"no copy of {path} to read: {e}"
    return _show(copy, f"a copy of {path} from {ref}")


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
_limited: dict = {}


def merged(root: Path, repo: str, items: list) -> set:
    """The claimed items whose PR was merged, also into a base GitHub closes nothing on (not the
    default branch): done, though open until pulse status closes them (ADR-06). Read at most every
    state.TTL s."""
    held = {i["number"] for i in items if i["assignees"] and not i.get("pr") and not i.get("hold")}
    at, done = _merged.get(root, (0.0, set()))
    if held and repo and time.time() - at >= state.TTL:
        try:
            done = {n for pr in json.loads(state.gh(["pr", "list", "--repo", repo, "--state", "merged", "--limit", "50",
                                                     "--json", "headRefName,closingIssuesReferences,files,changedFiles,"
                                                               "isCrossRepository"]))
                    for n in state.pr_items(pr)}
        except state.RateLimitError as error:
            _limited[root] = error
            return done & held
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
        except state.RateLimitError as error:
            _limited[root] = error
            return {epic: done[epic] for epic in epics if done.get(epic)}
        except (state.StateError, ValueError):
            pass                        # offline: the last answer stands
        _closed[root] = (time.time(), done)
    return {e: done[e] for e in epics if done.get(e)}


def _cache_notice(root: Path) -> str:
    try:
        snapshot = json.loads(state.cache_path(root).read_text(encoding="utf-8"))
        if not isinstance(snapshot.get("items"), list):
            return "no cached state"
    except (OSError, ValueError, AttributeError):
        return "no cached state"
    try:
        fetched = float(snapshot.get("fetched_at", "nan"))
    except (ValueError, TypeError):
        fetched = math.nan
    age = _age(fetched) if math.isfinite(fetched) and 0 <= fetched <= time.time() else "unknown"
    return f"showing last known state, cache age {age}"


def gather(root: Path, board: bool = True, *, fresh: bool = False) -> dict:
    """The view model of the map; board=False leaves out what only the board section shows, the epics' closed
    children and the merges GitHub closes nothing for: pulse status <n> asks GitHub for neither (#99 fix round 1)."""
    _fetch(root)
    cfg, error, repo, items, me = config.load(root), "", "", [], ""
    try:
        repo = state.repo(root, run=state.gh)      # looked up per call so tests can swap gh
        me = state.me(root, run=state.gh)
        if root in _limited and _limited[root].retry_at > time.time():
            raise _limited[root]
        items = state.load(root, repo, run=state.gh, **({"fresh": True} if fresh or root in _limited else {}))
        _limited.pop(root, None)
    except state.StateError as e:
        if isinstance(e, state.RateLimitError):
            _limited[root] = e
        items = state.cached(root)
        error = f"offline, showing the last known state ({e})" if items else str(e)
    annotated = next((record for record in items if "order_revision" in record), {})
    order_info = {"issue": annotated.get("order_issue"), "revision": annotated.get("order_revision"),
                  "positions": {record["number"]: record["manual_position"] for record in items
                                if record.get("manual_position") is not None},
                  "why": annotated.get("order_conflict", "")}
    try:
        cached = json.loads(state.cache_path(root).read_text(encoding="utf-8"))
        if (cached.get("repo") == repo and cached.get("format") == state.FORMAT and
                cached.get("items") == items and isinstance(cached.get("order"), dict)):
            order_info = cached["order"]
    except (OSError, ValueError, AttributeError):
        pass
    done = merged(root, repo, items) if board else set()      # off the map at once, done for its epic (#57)
    finished = Counter(i["parent"] for i in items if i["number"] in done and i.get("parent"))
    items = [i for i in items if i["number"] not in done]
    phases = go.phases(root)
    specs = {i["spec"] for i in items if not i["approved"] and i.get("spec")}   # on the base, else in its PR
    there = set(_git(str(root), "ls-tree", "-rz", "--name-only", config.base_ref(root), "--", *specs)
                .split("\0")) if specs else set()
    base = cfg["base_branch"] or config.default_branch(root)
    vm = {"repo": repo, "now": time.strftime("%H:%M:%S"), "base": base,
            "person": state.who(root, me) or "you", "me": me,      # Klarname (@login), as every surface (#111)
            # no sessions: the live state of agents comes with the Herdr map (phase 2); the map shows claims
            "items": items, "sessions": [], "error": error, "order": order_info,
            "phases": phases, "failed": failures(root, items),
            "halt": go.halt(root),              # base red, or a hook refused pulse go (#113)
            "closed": dict(Counter(closed(root, repo, items) if board else {}) + finished),
            # no spec, or neither on the base nor in an open pull request: approve refuses it (#115)
            "nowhere": [i["number"] for i in items if not i["approved"] and i.get("spec") not in there
                        and not i.get("spec_prs")],
            # ponytail: one git show per unapproved spec each refresh; git cat-file --batch if the ramp is long
            "unready": [i["number"] for i in items if not i["approved"] and i.get("spec") in there
                        and spec.refusal(spec.on_base(root, i["spec"]), i.get("type"), i["number"], "")],
            "branches": {},
            "untrusted": setup.untrusted(cfg["agent"]),       # the lever guard does not run in Codex yet (#111)
            "ramp": ready.view(root, items, cfg, me)}
    try:                                        # every person's auto switches (#124): per login in status --json
        seen = auto.read(root, repo, run=state.gh) if repo else {"switches": {}, "why": ""}
    except state.StateError as e:
        if isinstance(e, state.RateLimitError):
            _limited[root] = e
        seen = {"switches": {}, "why": f"auto switches not known: {e}"}
    vm.update(auto=seen["switches"], auto_why=seen["why"])
    vm["rate_limit"] = root in _limited
    if vm["rate_limit"]:
        reason = str(_limited[root]).replace("GitHub API rate limit", "GitHub rate limit", 1)
        vm["error"] = reason + "; " + _cache_notice(root)
    return vm


# --- demo: one morning at a sample project, the fixture of the map's tests ---
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


def demo(step: int = 0) -> dict:
    """A plausible morning at a sample project, step by step of SCRIPT."""
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
            "ramp": ready.ramp(order, files, 4, "Sebastian",       # like pulse go: no PLAN, no build
                                  gates={n: "needs a plan" for n, i in items.items()
                                         if i["approved"] and n not in files and not i["assignees"]})}


def _keys():
    """A reader for single keys when stdin is a terminal; None elsewhere (pipes)."""
    if not sys.stdin.isatty():
        return None
    if sys.platform == "win32":
        return _windows_keys()
    try:
        import termios
        import tty
    except ImportError:
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
            if ch in ("\x1b[5", "\x1b[6") and select.select([sys.stdin], [], [], 0.01)[0]:
                ch += os.read(fd, 1).decode(errors="ignore")
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


def _windows_keys():
    """The keys of a Windows terminal through msvcrt, which has no termios (#121 FR-09): an arrow comes as two
    characters, and the map gets it as any other terminal sends it."""
    import msvcrt
    arrows = {"H": UP[0], "P": DOWN[0], "K": "\x1b[D", "M": RIGHT[0], "I": "\x1b[5~", "Q": "\x1b[6~"}

    def read(wait: float):
        end = time.monotonic() + wait
        while not msvcrt.kbhit():
            if time.monotonic() >= end:
                return None
            time.sleep(0.01)
        ch = msvcrt.getwch()
        return arrows.get(msvcrt.getwch()) if ch in ("\x00", "\xe0") else ch

    def drop():
        while msvcrt.kbhit():
            msvcrt.getwch()
    read.restore, read.drop = lambda: None, drop
    return read


def fitted(lines: list, height: int, keep: int, offset: int = None) -> list:
    """At most height lines, so a frame taller than the terminal never scrolls it: the header (the
    first HEAD lines, #57) and the last keep lines (status and keys) stay, the rest is cut around
    the picked row, the one that starts with › (a title may hold one too, #56), and one line says
    how much is hidden. A terminal too low for all of it gives header lines up first."""
    if len(lines) <= height:
        return lines
    head = lines[:min(HEAD, max(0, height - keep - 2))]
    body, foot = lines[len(head):len(lines) - keep], lines[len(lines) - keep:]
    room = max(1, height - len(head) - len(foot) - 1)
    at = next((i for i, line in enumerate(body) if ANSI.sub("", line).lstrip().startswith("›")), 0)
    top = max(0, min(at - room // 2 if offset is None else offset, len(body) - room))
    return head + body[top:top + room] + [f"  … {len(body) - room} more lines; a taller terminal shows them"] + foot


def shows(text: list, width: int, height: int) -> bool:
    """Whether a confirmation shows whole, so Enter binds nothing the person did not see (#76, #56 audit
    M-1): fitted keeps a row of the map and the row that counts what it hides beside the footer (the
    text, the keys), and a terminal narrower than the map wraps every row. The footer counts every
    character that is not ASCII as two columns: a text the terminal draws wider than the map counts it
    can make the map refuse, never hide a line (final check M-2)."""
    return len(footer("\n".join(text), KEYS["confirm"], width)) + 2 <= height and \
        terminal_size().columns >= width


def _beside(fn) -> threading.Thread:
    """fn in a thread of its own: the live map reads beside its keys, so none waits for GitHub (#55)."""
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    return t


def main(args) -> int:
    root = config.find_root()
    if root is None:
        print("pulse map: not inside a git repository")
        return 2
    if not sys.stdout.isatty():                         # a pipe, a file, a chat: one frame, no color
        print(once(gather(root), 0))
        return 0
    color = depth()
    vm, fetched, ui, status, seen, shown, waiting = None, 0.0, {"level": "map"}, "", None, [], ""
    restart, reading, todo = "", None, None          # a newer copy; the read beside the keys; an action to run
    offered = {}                                     # item -> what its view offered on the last frame
    approved = {}                                    # item -> its approvals, once read beside the keys (L-3)
    detached = None
    # what the read brings, the writes so far, the last look for a newer copy and for a newer release
    box = {"writes": 0, "looked": time.time(), "asked": -math.inf}
    drawn, drawn_at = [], None                       # the rows on the screen, and the size they were drawn at
    read = keys = _keys()
    handlers = {s: signal.signal(s, go._exit)          # a closed terminal still runs the cleanup
                for s in (signal.SIGTERM, getattr(signal, "SIGHUP", None)) if s}

    def world():
        """What the live map reads that waits for git, GitHub, or the network, beside its keys (#55):
        the board, a newer release, a newer copy of Pulse."""
        try:
            writes, board_, update, newer = box["writes"], gather(root), "", ""
            if time.time() - box["asked"] >= DAY:      # a newer release: named once a day (IMP-14)
                box["asked"], own = time.time(), own_version()
                out = latest(root)
                if setup.version_key(out) > setup.version_key(own):
                    update = UPDATE.format(v=out, own=own)
            if time.time() - box["looked"] >= UPGRADE:
                box["looked"], newer = time.time(), newer_copy()
            box["new"] = (writes, board_, update, newer)
        except Exception as e:                         # the map ends on it, as when it read in its loop
            box["new"] = e
    try:
        sys.stdout.write("\033[?1049h\033[?25l")     # the alternate screen: the shell comes back as it was
        while True:
            fresh = False
            while True:                                # take what the last read brought, start the next
                if reading and not reading.is_alive():
                    new, reading = box.pop("new"), None
                    if isinstance(new, Exception):
                        raise new
                    writes, board_, update, restart = new
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
            vm["now"] = time.strftime("%H:%M:%S")
            width, size = columns(), tuple(terminal_size())
            height = size[1] or 40                     # a pty nobody sized: 0 rows
            if ui["level"] == "move":
                changed = (order._binding(vm["items"]) != ui["board_binding"] or
                           (vm.get("order") or {}).get("revision") != ui["board_revision"] or
                           bool(vm.get("error")) or bool((vm.get("order") or {}).get("why")))
                if ui["size"] != size or changed or not shows([status], width, height):
                    ui, status = {"level": "map", "at": ui["at"]}, "move cancelled: board or terminal changed; refresh"
                    getattr(read, "drop", lambda: None)()
            confirm_notice = status + ("\n> " + ui["expected"] if "expected" in ui else "")
            if ui["level"] == "confirm" and not shows([confirm_notice], width, height):
                ui, status = key(ui, shown, BACK[0])[0], SMALL
            elif ui["level"] == "confirm" and ui["size"] != size:   # resized: drawn whole anew, its second anew
                ui = {**{k: v for k, v in ui.items() if k != "opened"}, "size": size}
            level, n = ui["level"], ui.get("at")
            view = vm
            if detached and detached["number"] == n and level in ("item", "confirm") and \
                    not any(entry["number"] == n for entry in vm["items"]):
                view = {**vm, "items": [*vm["items"], detached]}
            frame = int(time.time() / TICK)            # by the clock: all breathe in step
            acts = ()                                  # what the item view offers, as this frame draws it
            if level == "item" or level == "confirm" and ui.get("from") != "map":   # a on the map asks over the map
                if fresh or not seen or seen["number"] != n:
                    if not seen or seen["number"] != n:    # the view opens: its approvals come beside the keys
                        approved.pop(n, None)

                        def approvals_of(n=n, vm=vm):
                            approved[n] = read_approvals(vm, n)
                        _beside(approvals_of)
                    seen = {**look(root, view, n), "waiting": waits(root, view, n)}
                # from the plain copy render() draws them from: Enter runs the row it shows (#56 audit L-3)
                acts, was = [a for a, *_ in offers(_plain(view), _plain(seen))], offered.get(n, [])
                k = ui.get("pick")
                if k is None:                          # the view opens on a reading entry (#99 FR-09), whatever
                    ui = {**ui, "pick": next((k for k, a in enumerate(acts) if a in READS), 0)}   # an earlier visit
                elif acts != was and k < len(was):     # offered. The list shifted: the cursor keeps its action, or
                    ui = {**ui, "pick": acts.index(was[k]) if was[k] in acts else 0}   # goes to the top,
                                                           # which never writes without asking first (#55)
                offered = {n: acts}
                lines = render(view, frame=frame, color=color, width=width,
                               item=dict(seen, pick=ui.get("pick", 0), approvals=approved.get(n, READING)))
            elif level == "help":                      # under the header, as every screen (#57)
                lines = render(vm, frame=frame, color=color, width=width)[:HEAD] + HELP.split("\n")
            elif level == "move":
                shown = []
                lines = render(ui["vm"], frame=frame, color=color, width=width, selected=n, picks=shown)
            else:
                shown = []
                lines = render(vm, frame=frame, color=color, width=width, selected=n, picks=shown)
            notice = status or (vm.get("error", "") if vm.get("rate_limit") else (vm.get("order") or {}).get("why", ""))
            if level == "number":
                notice = "Issue number: " + ui.get("typed", "")
            elif level == "confirm" and "expected" in ui:
                notice = status + "\n> " + ui.get("typed", "")
            foot = footer(notice, KEYS[level], width) if read else []
            if level == "item":
                ui["page"] = max(1, height - min(HEAD, max(0, height - len(foot) - 2)) - len(foot) - 1)
                if "scroll" in ui:
                    ui["scroll"] = min(ui["scroll"], max(0, len(lines) - HEAD - ui["page"]))
            cells = [fit(l, width) for l in fitted(lines + foot, height, len(foot),
                                                  ui.get("scroll") if level == "item" else None)]
            clear = (width, height) != drawn_at      # new or resized: cleared, then every row once (#98)
            if clear:
                drawn = []
            # each row at its own place, so a row the terminal draws wider moves none below it (#98); the rows that
            # changed, and those of an open confirmation on every frame, after the map's: a row of the map written
            # again, wider than the map counts, cannot cover what Enter confirms (#56 M-3)
            bound = len(cells) - len(foot) if level == "confirm" else len(cells)
            out = "\033[H\033[2J" * clear + "".join(f"\033[{i + 1};1H\033[K{c}" for i, c in enumerate(cells)
                                                   if i >= len(drawn) or drawn[i] != c or i >= bound)
            out += f"\033[{len(cells) + 1};1H\033[J" if len(cells) < len(drawn) else ""
            drawn, drawn_at = cells, (width, height)
            if out:
                sys.stdout.write(out)
                sys.stdout.flush()
            # the frame with a confirmation is written: its second starts now, on a clock no NTP step or wake
            # moves, and what was typed until now confirms nothing (#86 audit L-1, L-2; #90)
            if ui["level"] in ("confirm", "move") and "opened" not in ui:
                ui = {**ui, "opened": time.monotonic()}
                getattr(read, "drop", lambda: None)()
            if todo:                                   # its line is on the screen: now it runs (#55)
                wrote = todo[0] in DOING
                try:
                    if wrote:
                        if reading:
                            reading.join()
                            new, reading = box.pop("new"), None
                            if isinstance(new, Exception):
                                raise state.StateError(f"the board could not be refreshed: {new}")
                            writes, board_, update, restart = new
                            if writes != box["writes"]:
                                raise state.StateError("the board changed while confirming; inspect it again")
                            vm = board_
                        view = vm = gather(root, fresh=True)
                    status = act(root, view, todo)
                except (state.StateError, ValueError) as e:
                    status = f"! {e}"
                if wrote:
                    box["writes"] += 1
                    if detached:
                        ui, detached = {"level": "map", "at": n}, None
                    vm = None                          # the board as the write left it, at once
                todo = None
                continue
            ch = read(TICK) if read else time.sleep(TICK)
            if ui["level"] == "move" and tuple(terminal_size()) != ui["size"]:
                ui, status, ch = {"level": "map", "at": ui["at"]}, "move cancelled: terminal resized", None
            if ch in ENTER and ui["level"] == "confirm" and tuple(terminal_size()) != ui["size"]:
                ch = None                              # resized since it was drawn: the next frame decides (#98)
            if ch == "q" and level == "map":
                return 0
            if ch in ENTER and "opened" in ui and time.monotonic() - ui["opened"] < SOON:
                ui, ch = key(ui, shown, BACK[0])[0], None   # typed unread: it closes
                status = "nothing done: enter came within a second of opening it; open it again, read, then enter"
            if ch:
                ui, action = key(ui, shown, ch, acts)
                if level not in ("confirm", "move") or ui["level"] != level:
                    status = ""
                if action and action[0] == "say":
                    status, action = action[1], None
                if action and action[0] in ("move", "move-preview", "move-save"):
                    saving = action[0] == "move-save"
                    if saving and reading:
                        reading.join()
                    try:
                        ui, status = move(root, vm, ui, action, size)
                    except (state.StateError, ValueError) as error:
                        status = f"! {error}"
                        if action[0] == "move-preview":
                            ui = {**ui, "invalid": True}
                        else:
                            ui = {"level": "map", "at": action[1]}
                    if saving:
                        box["writes"] += 1
                        vm = None
                    action = None
                if action and action[0] == "lookup":
                    try:
                        detached = by_number(root, vm, action[1])
                        ui, seen = {"level": "item", "at": action[1]}, None
                    except (state.StateError, ValueError) as error:
                        status = str(error)
                    action = None
                if action and level in ("map", "item") and action[0] in ("approve", "auto", *lifecycle.ACTIONS):
                    try:
                        text, sure = brief(root, view, action)
                    except (state.StateError, ValueError) as error:
                        text, sure = [str(error)], None
                    expected = sure[2]["confirmation"] if sure and sure[0] in lifecycle.ACTIONS else ""
                    if expected:
                        text = [*text, "Type " + expected + " to confirm."]
                    status, action = "\n".join(text), None
                    if sure and not shows([*text, *( ["> " + expected] if expected else [])], width, height):
                        status = SMALL
                    elif sure:
                        ui = {"level": "confirm", "at": n, "sure": sure, "pick": ui.get("pick", 0), "from": level,
                              "size": size}
                        if expected:
                            ui.update(expected=expected, typed="")
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
        os.execv(restart, [restart, "map"])
    return 0
