"""The Pulse map: who is doing what, what is ready, what goes out next.

One renderer for both commands: `pulse map` and `pulse status` print these
lines. The map is as wide as its terminal (D-45).
render() is pure; gather() reads the world.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import math
import os
import posixpath
import re
import select
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from pulse import (actions, auto, config, go, goals, lifecycle, mapstart, merge, order, presence, ready, remove,
                   settings, setup, spec, state)

WIDTH = 80                      # columns without a terminal (D-45)
TITLE = 60                      # the most of a file name a row keeps (FIX-02-04-03)
FEWEST, MOST = 44, 160          # the map follows its terminal's width within these, beside a session in Herdr too
LONGEST = 2000                  # the most of a text the map reads: a few of its widest rows (#56 audit L-4)
STATE = .45                     # the most of a line a state takes when its title needs the rest
ANSI = re.compile(r"\033\[[0-9;]*m|\033\]8;;[^\033]*\033\\")     # colors, and terminal links (OSC 8)
DOT = {"working": ("●", "32"), "error": ("●", "31"), "waiting": ("●", "33"), "idle": ("●", "90")}
RANK = ("error", "waiting", "working", "idle")
ROWS_SHOWN = 40                 # the ramp lists all open work; past this, a count
DONE_DAYS = 7                   # DONE lists what Pulse integrated in these last days (#217)
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
# The P of pulse-icon-hell.svg as an image, drawn by scripts/logo_png.py, in place of SIGNET where the terminal
# confirms the Kitty graphics protocol (#166); every command but the question asks for no answer (q=2)
LOGO = Path(__file__).with_name("logo.png")
LOGO_ID = 166166
GRAPHICS_ASK = f"\033_Gi={LOGO_ID},s=1,v=1,a=q,t=d,f=24;AAAA\033\\"
GRAPHICS_OK = f"\033_Gi={LOGO_ID};OK\033\\"
LOGO_OFF = f"\033_Ga=d,d=i,i={LOGO_ID},q=2\033\\"        # its place on the screen
LOGO_GONE = f"\033_Ga=d,d=I,i={LOGO_ID},q=2\033\\"       # its place and its data
# what the map asks of a person, the most urgent first, in the color of its state
NEXT = {"failing": "31", "your review": "33", "integration": "33", "waits for merge": "33",
        "spec rule": "90", "spec waits": "90", "last run": "90",
        "plan repair": "90", "plan needs you": "33", "needs a plan": "90", "starts next": "90", "queued": "90",
        "spec in progress": "90", "nothing open": "90", "held silent": "33", "on hold": "33"}
SILENT = 30 * 60                # a run's claim without a heartbeat this long shows no sign of life (D-43)
PHASE = {"spec": "specifying", "documents": "checking documents", "plan": "planning", "build": "building", "spec tests": "RED check running", "tests": "tests running",
         "check": "review and audit running", "review": "review running", "audit": "audit running",
         "fix": "fix round"}                                                             # pulse go, per feature
# the live map is a tree walked without Shift but for ? (D-44): the map, an item, and what acts on it; below
# the map every way back drops what is not written yet, q too (#55)
UP, DOWN, ENTER, RIGHT = ("\x1b[A", "k"), ("\x1b[B", "j"), ("\r", "\n"), ("\x1b[C",)
HOME = ("\x1b[H", "\x1b[1~", "\x1b[7~", "\x1bOH")    # Home and End in the forms terminals send them
END = ("\x1b[F", "\x1b[4~", "\x1b[8~", "\x1bOF")
PAGE = ("\x1b[5~", "\x1b[6~")                    # PgUp, PgDn
FOLDS = "map-folds"             # the sections folded in this clone's map, one title a line, in its git dir (#214)
BACK = ("\x1b", "\x1b[D", "\x7f", "\x08", "q")
MOUSE_ON, MOUSE_OFF = "\033[?1000h\033[?1006h", "\033[?1006l\033[?1000l"   # button and wheel reports, SGR form (#180)
SGR = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
WHEEL = 3                       # rows one notch of the mouse wheel scrolls
READ_MOST = 256 * 1024          # the most of a file the reader reads: the start of a text, the end of a log
# what the reader drops of a line: a color, an OSC closed on that line; any other ESC shows as ? (#180)
CONTROL = re.compile(r"\x1b\[[0-9;]*m|\x1b\][^\x07\x1b\n]*(?:\x07|\x1b\\)")
BACK_ROW = " ‹ back"            # the first row under the header of the help and the reader: a click goes back
KEYS = {"map": "↑↓ pick m move enter open ? help q quit",       # one key row at 44 columns; a still approves
        "item": "↑↓ pick a approve enter do ? help esc back",
        "move": "↑ ↓ move  enter save  esc cancel",
        "confirm": "enter confirm  esc cancel",
        "number": "type issue number  enter open  esc cancel",
        "help": "↑↓ scroll PgUp/PgDn page esc back",
        "read": "↑↓ wheel scroll PgUp/PgDn page esc back",
        "settings": "↑↓ pick enter change ? help esc back",
        "value": "type slots  enter preview  esc cancel"}
JUMP_KEYS = "↑↓ enter/click jump l levers ? help q quit"   # the map's keys on a session row (#181, #197)
FOLD_KEYS = "↑↓ pick enter fold PgUp/PgDn ? help q quit"     # on a section's heading (#214)
HERDR_WAIT = 2                  # seconds the map waits for each Herdr call of a jump (#181)
HELP = """map      ↑ ↓ or j k pick a line, enter or →
           opens it, a previews approval
         m moves unclaimed backlog work;
           arrows move it, enter saves,
           esc cancels; dependencies first
         g opens an issue by number
         PgUp PgDn Home End scroll the map;
           ↑ ↓ keep the picked line in sight
         enter or a click on a heading folds
           its section or opens it again;
           the folds stay with this clone
         enter or a click on ▸ n sessions
           unfolds the sessions there, with
           their running subagents
         s or a click on the approval line
           opens the settings
         r reads the report of the last run
         ? shows this help, q quits
session  enter or a click on a session in
           WHO IS DOING WHAT shows its
           Herdr pane, in any tab or
           workspace; only the focus moves
         a subagent leads to its session
         without a pane the line says why
         l shows your lever grants in the
           settings: grant a Claude Code
           session run or session, all
           attended ones always, or revoke
item     goal, stage, holder, blockers,
           result, checks and plan
         ↑ ↓ or j k pick, enter acts;
           PgUp PgDn scroll long details
         approve binds the published result
           and base after reviewing its diff
           checks and findings
         read result opens the complete diff
         revoke withdraws final approval
         defer pauses and preserves work;
           resume awaits shared confirmation
         handoff stops the current writer
           before releasing its claim
         these actions save locally first;
           their sync state stays on the map
         read spec, read plan, read run log
           and read result diff show the
           text in the reader of the map
         discard closes without rollback
         delete prepares removal of work
settings each setting with where it comes
           from and what it does, and the
           last session start per harness
           that got the Pulse rules here
         enter previews a change; enter
           again commits it on a pushed
           branch of its own, which counts
           once it is integrated
policy   3 shows final approval settings;
           automatic is the default
         manual waits for a person with
           repository write access
         holds, checks and bindings remain
           required
help     ↑ ↓ or j k scroll one line
         PgUp PgDn scroll a page
         enter and action keys do nothing
reader   ↑ ↓, wheel, PgUp PgDn scroll
         esc, q, ← or a click on ‹ back
           return to where it opened
mouse    a click on a row opens it, on an
           entry acts as enter; a write
           still asks, only enter confirms
         the wheel picks on the map and
           scrolls a long view
         shift with the mouse selects text
           and opens terminal links
         Windows: keys only, no mouse
confirm  enter confirms after one second;
           esc cancels
back     q, esc, ← or backspace go back and
           drop an unconfirmed action
         q quits only on the map;
           ctrl-c quits anywhere"""
WORKFLOW = """Workflow
1. Orient: pulse shows the current state; pulse setup configures a project when needed.
2. Spec: clarify the goal and record its scope and success criteria on the board.
3. Plan: define tasks and tests, validate the plan and publish its exact contents.
4. Build: first run and freeze the RED tests, then implement and run the project checks.
5. Review and audit: inspect the result, fix findings and refresh affected checks.
6. Integration: publish the checked result bound to its exact head and base. Regular results complete automatically by default; explicitly chosen manual waits for personal approval.
Hooks, holds, prerequisites and current rights still apply. Removal always needs separate personal confirmation.
Use pulse go with an optional goal to follow this process. A goal adds to queue work; --epic or --item restricts it. No spec or plan approval and no PR is required.

Chat skills (in your coding agent)
/pulse: find the current state and the next suitable step.
/pulse-realign: onboard an existing project and its retained work.
/pulse-ba: clarify a problem, its users and the intended benefit.
/pulse-re: turn that understanding into a spec and success criteria.
/pulse-build: implement a ready item against its plan, test first.
/pulse-audit: inspect security risks and report concrete findings.
/pulse-go: start or steer pulse go with your goal.
/pulse-off, /pulse-on: turn Pulse off or on for you here, or with --host on this computer.
In Codex use $pulse:pulse, $pulse:pulse-build and the corresponding $pulse:skill-name form. Planning is a phase managed by Pulse, not an additional public CLI command.

Command reference (examples are text, not actions)
"""
# what the item view can offer (#55): the words, and what it does; offers() puts them in order
OFFER = {"approve": ("approve integration", "approve the reviewed result and base"),
         "revoke": ("revoke approval", "withdraw integration approval"),
         "handoff": ("hand off claim", "stop the current writer and preserve its work"),
         "read-result": ("read result diff", "open the published result, checks and findings"),
         "read-plan": ("read plan", "show it here"),
         "open": ("read spec", "show it here")}
OFFER.update({"defer": ("defer", "pause as-is in the backlog"),
              "resume": ("resume", "continue the preserved work"),
              "discard": ("discard", "close as not planned; keep code and specs"),
              "delete": ("delete", "review removal of code, specs, issue and comments")})
READS = ("read-result", "read-plan", "open", "read-plan-error", "read-log", "read-doc", "read-report",
         "read-check-output")
# the approval a writes at each gate (#115): its words in the item view, and what it lets happen
GATE = {3: ("approve integration", "approve this result and base after reviewing the diff and checks")}
# the line an action shows while it runs; the ones not named here only open a window
DOING = {"auto": "saving approval policy…", "publish-plan": "starting plan publication #{}…",
         "setting": "committing the setting on a branch of its own…",
         "retry-sync": "queueing synchronization retry #{}…"}
DOING.update({action: action + " #{}…" for action in lifecycle.ACTIONS})
LOCAL_ACTIONS = {"approve", "defer", "resume", "revoke", "handoff"}
LOCAL_WRITES = LOCAL_ACTIONS | {"publish-plan", "retry-sync", "auto", "setting", "levers"}
DOING["levers"] = "saving the lever grant…"           # local only: the store beside the outbox (#197)
DOING.update({action: "queueing " + action + " #{}…" for action in LOCAL_ACTIONS})
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


def help_lines(width: int) -> list:
    """Navigation, process and the current parser's command help, wrapped for this terminal."""
    from pulse import cli                       # cli already imports this renderer
    return [row for text in (HELP, "", WORKFLOW, *cli.command_help()) for line in text.split("\n")
            for row in (wrap(ready.printable(line), width) or [""])]


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


def logo_png():
    """The logo as PNG, None when its file is missing or holds no PNG (#166)."""
    try:
        data = LOGO.read_bytes()
    except OSError:
        return None
    return data if data.startswith(b"\x89PNG\r\n\x1a\n") else None


def picture(png: bytes, send: bool) -> str:
    """The logo over the header's first 8 columns and 4 rows, from the top left corner: sent with its PNG in
    pieces of 4096 characters, or put there again. The cursor stays where it is (C=1)."""
    keys = f"a={'T' if send else 'p'},i={LOGO_ID},p=1,c=8,r=4,C=1,q=2"
    if not send:
        return f"\033[H\033_G{keys}\033\\"
    data = base64.standard_b64encode(png).decode()
    pieces = [data[k:k + 4096] for k in range(0, len(data), 4096)]
    return "\033[H" + "".join(f"\033_G{keys + ',f=100,' if k == 0 else ''}m={int(k < len(pieces) - 1)};{piece}\033\\"
                              for k, piece in enumerate(pieces))


# the stages of a job in the command center (#215 FR-01), and the stage each phase of pulse go belongs to
STAGES = ("spec", "plan", "build", "tests", "review/audit", "fix", "integrate")
STAGE = {"spec": "spec", "documents": "spec", "plan": "plan", "setup": "build", "build": "build", "spec tests": "tests",
         "tests": "tests", "check": "review/audit", "review": "review/audit", "audit": "review/audit", "fix": "fix",
         "integrate": "integrate", "integration": "integrate"}
LADDER = {"done": "✓", "active": "▸", "open": "·"}
SETTLED = 120                   # seconds a confirmed action of the outbox stays on the map (#215 FR-05)


def ladder(phase, since=None) -> list:
    """[(stage, done, active, or open)] of a job in phase (#215 FR-01): the stages before its own done, its own
    active, with how long it runs when since says when it began, the rest open; [] for a phase that names none."""
    stage = STAGE.get(phase)
    if stage is None:
        return []
    at = STAGES.index(stage)
    return [(name + (f" {_age(since)}" if k == at and since is not None else ""),
             "done" if k < at else "active" if k == at else "open") for k, name in enumerate(STAGES)]


TASK = "Pulse-Task"             # the commit trailer that checks off a task of the Plan (#216): display only


def tasks_done(root, refs: list, base: str, item: int = None) -> set:
    """The task numbers that the commits of refs not on base check off with a line "Pulse-Task: <n>" (#216), in any
    paragraph of the message, as real commits put it above their attribution: at most 300 commits, digits only and
    at most 4 of them, as a message is any text an agent writes; with item only commits with a line "Refs:" that
    names #item, so a branch stacked on another item's counts none of its tasks. The map shows them; no gate reads
    them."""
    done = set()
    log = ready._git(root, "log", "-z", "-n", "300", "--format=%B", *refs, "--not", base, "--")   # no NUL in a message
    for message in log.split("\0"):
        lines = message.split("\n")
        if item is None or any(re.match(rf"(?i)refs:.*#{item}(?![0-9])", line) for line in lines):
            done |= {int(m.group(1)) for m in (re.match(r"(?i)pulse-task:\s*([0-9]{1,4})\s*$", line) for line in lines)
                     if m}
    return done


def plan_progress(text: str, done: set):
    """(k, n, the title of the first open task) of a Plan whose Tasks table done checks off, each task once and no
    number the Plan does not know; None without tasks or without one checked off (#216 FR-03, FR-04)."""
    rows = [(int(row["#"]), row.get("task", "")) for row in ready.tasks(text or "")
            if re.fullmatch(r"[0-9]{1,4}", row.get("#", "").strip())]
    checked = set(done) & {n for n, _ in rows}
    if not rows or not checked:
        return None
    return len(checked), len(rows), next((title for n, title in rows if n not in checked), "")


def plan_tasks(root, items: list, phases: dict, me: str, base: str, found: dict) -> dict:
    """{item: (k, n, next title)} of my running jobs, at most 8 (#216 FR-02): the Plan of each against the commits
    of its branch here and as fetched from origin that the base does not hold."""
    mine = [i["number"] for i in items if i["number"] in found and
            (me and me in i["assignees"] or not i["assignees"] and i["number"] in phases)][:8]
    if not mine:
        return {}
    names = [name for name in ready._git(root, "for-each-ref", "--format=%(refname)", "refs/heads",
                                          "refs/remotes/origin").split("\n") if "\ufffd" not in name]   # git reads it
    base_ref = next((r for r in (f"refs/remotes/origin/{base}", f"refs/heads/{base}") if r in names), None)
    if base_ref is None:
        return {}
    refs = {}
    for name in names:
        n = state.item_of(name.removeprefix("refs/heads/").removeprefix("refs/remotes/origin/"))
        if n in mine and name != base_ref:
            refs.setdefault(n, []).append(name)
    out = {}
    for n, own in refs.items():
        progress = plan_progress(found[n].get("text", ""), tasks_done(root, own, base_ref, item=n))
        if progress:
            out[n] = progress
    return out


def _latest(entries) -> dict:
    """{(item, kind): the newest action of the outbox of that kind}: a newer one, a redo too, ends an older one."""
    return {(entry["item"], entry["kind"]): entry for entry in entries}


def redo(vm: dict, kind: str, n: int):
    """(the action, n) that "redo:<id>" asks again: the latest of its kind on n, in conflict; else None (#215)."""
    entry = next((e for e in _latest(vm.get("actions", [])).values()
                  if f"redo:{e['id']}" == kind and e["item"] == n and e["status"] == "conflict"), None)
    return (entry["kind"], n) if entry and entry["kind"] in LOCAL_ACTIONS else None


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
    if actor.get("denied"):                    # an agent of pulse go asked nobody: its call was denied (#210)
        return f"permission denied: {actor['denied']}", "90"
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


def _diagnostic_url(value) -> str:
    """Only bounded GitHub check and settings destinations become terminal links (#149)."""
    return value if isinstance(value, str) and len(value) <= 500 and re.fullmatch(
        r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
        r"(?:settings/secrets/dependabot|actions/runs/[0-9]+(?:/(?:job|attempts)/[0-9]+)?|"
        r"runs/[0-9]+(?:\?check_suite_focus=true)?|commit/[0-9a-f]+/checks(?:\?check_run_id=[0-9]+)?)",
        value) else ""


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
    s = max(0, s)                       # a clock ahead of this one says no time passed
    return f"{int(s // 60)} min" if s < 3600 else f"{int(s // 3600)} h" if s < 2 * 86400 else f"{int(s // 86400)} d"


def _took(at) -> str:
    """How long something runs since at: seconds under a minute, else as _age (#234)."""
    s = _secs(at)
    return "" if s is None else f"{max(0, int(s))} s" if s < 60 else _age(at)


def _sessions(agents: list) -> list:
    """The sessions among the agents on one line of the tree: each one with a harness whose parent stands elsewhere;
    a subagent shows under its session (#234)."""
    ids = {a["id"] for a in agents}
    return [a for a in agents if a.get("harness") and a.get("parent", "") not in ids]


def _run(i: dict) -> bool:
    """Whether a run of pulse go holds i: it keeps its own signs of life (D-43); a session's come from its beat
    comment (#195, holding)."""
    return (i.get("claimed_holder") or "").startswith("go:")


def _life(phase: str, beat: str) -> str:
    """The holder's last sign of life (D-43): its phase and age, or none for 30 min."""
    if (_secs(beat) or 0) >= SILENT:
        return f"no sign of life for {_age(beat)}"
    return f"{PHASE.get(phase, phase)}, {_age(beat)} ago"


def holding(i: dict) -> tuple:
    """(words, step) for an item a session holds by hand (#195): its holder, session, phase, and the age of its last
    sign of life; once that is SILENT old, the step a person takes. ("", "") for a run's claim, a result, or none."""
    if not i.get("claim") or not i.get("claimed_holder") or _run(i) or i.get("result"):
        return "", ""
    n, who, beat, phase = i["number"], i.get("claimed_by") or "", i.get("claimed_beat"), i.get("claimed_phase")
    by = f"held by {who}, " + state._name({"id": i["claimed_holder"], "mine": True, "author": "", "at": ""})
    if not beat:
        return by + (f": {PHASE.get(phase, phase)}" if phase else ""), ""
    if (_secs(beat) or 0) < SILENT:
        return f"{by}: {_life(phase or 'working', beat)}", ""
    step = f"ask {who} or take it over: pulse release --take {n}"
    return f"{by}; {_life(phase, beat)}; {step}", step


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
    """{item number, else branch, "detached", or "pulse go": every agent on it}. An agent of pulse go counts for
    the item the run gave it, also in a detached gate or goal folder (#213); any other agent for the item its claim
    holds, wherever its directory stands (FIX-02), else for the item of its branch; a result branch also
    identifies the item whose writer published it. One without an item stands by its branch, a run's by the run."""
    by_number = {i["number"]: i for i in vm["items"]}
    holds = {}                            # session or Codex subagent id -> the items its claims hold
    for x in vm["items"]:
        holds.setdefault(x.get("claimed_holder") or "", []).append(x)
        holds.setdefault((x.get("claimed_holder") or "").partition(":")[2], []).append(x)
    holds.pop("", None)                   # no claim mark
    feats = {}
    for s in vm["sessions"]:
        for a in [s, *s["agents"]]:
            b = vm["branches"].get(a.get("cwd", ""), "")
            i = by_number.get(int(a["item"])) if str(a.get("item") or "").isdecimal() else None
            if i is None:
                i = by_number.get(state.item_of(b)) or next(
                    (x for x in vm["items"] if b and (x.get("result") or {}).get("branch") == b),
                    None)
                own = holds.get(a.get("holder")) or holds.get(a["id"]) or holds.get(s["id"]) or []
                if own and i not in own:
                    i = own[0]
            run = str(a.get("holder") or "").startswith("go:")
            feats.setdefault(i["number"] if i else "pulse go" if run else b or "detached", []).append(a)
    return feats


def board(vm: dict) -> dict:
    """Group ready work, active writers, published results and blocked items."""
    rows = vm["ramp"].get("rows", [])
    held = [i for i in vm["items"] if i["assignees"] and (i["type"] in state.WORK or i.get("draft"))]
    start = [x for x in rows if x["stage"].startswith(("starts next", "queued"))]
    blocked = [x for x in rows if x["blocked_by"] and x not in start]
    return {"ready to start": start, "in progress": [i for i in held if not i.get("result")],
            "in review": [i for i in held if i.get("result")], "blocked": blocked,
            "not ready yet": [x for x in rows if x not in start and x not in blocked]}


def render(vm: dict, frame: int = 0, color: int = True, width: int = WIDTH, selected: int = None,
           picks: list = None, item: dict = None, stages: dict = None, marks: dict = None,
           settings: dict = None, folded=()) -> list:
    """color: how many colors the terminal shows (depth()), 0 for none; selected: the item the
    terminal cursor is on (marked ›); picks: gets the items on the map top down, the way the cursor
    walks them; item: the item view in place of the map (D-44), its number and what look() read;
    stages: gets the stage of every item in the map's words, as pulse status <n> prints it (#99 FR-14);
    marks: gets {row: what a click there does} (#180), ("item", n) for an item row, ("offer", k) for an entry of
    the item view, ("read", action) for its spec, plan and checks rows and, only with marks, the runner's row of the
    run report, and ("settings",) for the approval line of the header (#182); settings: the settings view in place of
    the map, settings.read() and its pick; folded: the titles of the sections folded on the map (#214), whose
    headings are picks ("section", title) and targets there. Only the map writes escapes: every string of vm and
    item loses its control characters first (#56)."""
    if vm.get("goal"):
        vm = {**vm, "goal": {**vm["goal"], "objective": " ".join(vm["goal"]["objective"].splitlines())}}
    vm, item, settings, p, w = _plain(vm), _plain(item), _plain(settings), Paint(color), width
    by_number = {i["number"]: i for i in vm["items"]}
    shown = [] if picks is None else picks
    live, marks = marks is not None, {} if marks is None else marks
    runner = vm.get("runner") if isinstance(vm.get("runner"), dict) else {}
    # the base's remedy for a base or a failed start that holds the run, never for the commit gates or a hook (#178)
    diagnostic = vm.get("base_status") if vm.get("halt") and vm.get("halt_kind") not in go.OWN_REMEDY and \
        isinstance(vm.get("base_status"), dict) else {}
    refused = [r for r in vm.get("refusals") or () if isinstance(r, dict)]
    doing = " ".join(filter(None, (runner.get("title") or runner.get("phase"), runner.get("target"))))
    remedy = diagnostic.get("next") or ""
    destination = _diagnostic_url(diagnostic.get("url"))
    showing = {}                    # item -> its actions in the outbox, 0 the approval settings (#215 FR-05)
    for entry in _latest(vm.get("actions", [])).values():   # until two minutes after the shared state confirms
        if entry["status"] != "confirmed" or time.time() - ((entry.get("receipt") or {}).get("at") or 0) < SETTLED:
            label = "approval settings" if entry["kind"] == "policy" else entry["kind"]
            showing.setdefault(entry["item"], []).append(
                f"{label}: {entry['status']}" + (f" ({entry['error']})" if entry.get("error") else ""))

    def dot(st: str) -> str:
        ch, code = DOT.get(st, DOT["idle"])
        if st == "working" and p.color >= 256:
            code = glow(BREATH[frame % len(BREATH)], p.color)   # it breathes; yellow and red stay lit
        return p(ch, code)

    def section(title: str, note: str = "", right: str = "", pick: bool = False) -> str:
        head = (p("› ", "1") if pick else "") + p(title, "1;36") + (" " + p(note, "90") if note else "")
        tail = (" " + p(right, "90")) if right else ""
        return head + " " + p("─" * max(0, w - vlen(head) - vlen(tail) - 1), "90") + tail

    def opens(title: str, note: str = ""):
        """A section's heading; on the map a pick and a target, which Enter or a click folds (#214). -> where its
        rows and picks begin, for closes()."""
        if item is not None or settings is not None:
            out.append(section(title, note))
            return None
        target = ("section", title)
        shown.append(target)
        marks[len(out)] = target
        out.append(section(title, note, pick=target == selected))
        return len(out), len(shown)

    def closes(title: str, at, count: int) -> None:
        """A folded section, once its rows are built: one line, its title with count, and its rows, picks and
        targets gone (#214). Any section folds this way."""
        if at is None or title not in folded:
            return
        rows_at, picks_at = at
        del out[rows_at:], shown[picks_at:]
        for row in [k for k in marks if k >= rows_at]:
            del marks[row]
        out[rows_at - 1] = section(f"{title} ({count})", pick=("section", title) == selected)

    actors = [a for s in vm["sessions"] for a in [s, *s["agents"]]]
    groups = board(vm)
    rows, phases, failed = vm["ramp"].get("rows", []), vm.get("phases", {}), vm.get("failed", {})
    # what the local runner prepares or runs a job on stands under WHO IS DOING WHAT only, also before the board
    # shows its claim (#211)
    local = {n for n in [runner.get("item"), *phases] if n in by_number and not by_number[n].get("hold")}
    rows = [x for x in rows if x["number"] not in local]
    held = sorted(((login, i) for i in groups["in progress"] + groups["in review"]      # held drafts too (#55)
                   for login in i["assignees"]), key=lambda x: (x[0].lower(), x[1]["number"]))

    def mine(i) -> bool:
        return bool(vm["me"]) and vm["me"] in i["assignees"]

    def automatic(i):
        setting = vm.get("auto") or {}
        return auto.active(setting.get("policy") or {}) and not setting.get("blocked") and not (
            i.get("removal") or i.get("revoked"))

    def light(i):
        """The current writer or the published result awaiting final integration."""
        n, result = i["number"], i.get("result")
        fix = ("failing", f"/pulse-build {n} takes it on in a session") if mine(i) else None
        if i.get("local_hold"):
            return "waiting", "on hold locally", None
        if i.get("hold"):
            return "waiting", "on hold", ("on hold", f"pulse resume {n}")     # the person paused it (#233)
        if n in failed:
            return "error", f"failed: {failed[n]}".replace("PLAN", "plan"), fix
        if n in phases:
            return "working", PHASE.get(phases[n], phases[n]), None
        if i.get("integration_wait"):
            return "waiting", "integration: " + i["integration_wait"], \
                ("integration", f"Resolve #{n}: {i['integration_wait']}; then pulse go retries")
        if result:
            if any(value != "pass" for value in result.get("gates", {}).values()):
                return "error", "published result has a failed check", fix
            if i.get("approval"):
                return "idle", "integration approved; waits for current-base checks", None
            if automatic(i):
                return "idle", "automatic integration pending", None
            return "waiting", "result waits for integration approval", ("your review", f"pulse approve {n}")
        beat = i.get("claimed_beat")
        if beat and not mine(i) and _run(i):
            return "idle", _life(i.get("claimed_phase") or "working", beat), None
        words, step = holding(i)
        if words:                              # a session holds it by hand (#195); a silent one needs a person
            return ("waiting" if step else "idle"), words, ("held silent", step) if step else None
        return "idle", "work in progress; no published result", None

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
        if row in groups["blocked"] and not ready.repairable(row, s):
            return "idle", None
        if s.startswith("spec:"):
            return "idle", ("spec rule", f"/pulse-re on the spec of #{n}")
        if s.startswith("plan: "):
            return ("idle", ("plan repair", f"Runner: repair #{n} plan and check it again")) \
                if ready.repairable(row, s) else \
                ("waiting", ("plan needs you", f"You: review #{n} plan findings"))
        if s.startswith(("plan publication", "plan versions", "plan commit", "plan push")):
            return "waiting", ("plan needs you", f"Open #{n}: inspect and publish the preserved plan")
        if s == "integration waits for approval":
            if automatic(by_number.get(n, {})):
                return "idle", None
            return "waiting", ("your review", f"pulse approve {n}")
        if s.startswith("integration: "):
            return "waiting", ("integration", f"Resolve #{n}: {s[13:]}; then pulse go retries")
        if s.startswith("result:"):
            return "waiting", ("your review", f"#{n} needs result revalidation: {s[7:].strip()}")
        if row.get("note"):                   # a run gave it back (D-43); its branch holds the work
            return "idle", ("last run", f"/pulse-build {n} goes on from where it stopped")
        if remedy or runner and runner.get("item") in (None, n):
            return "idle", None              # the preparation or base action below explains what happens next
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
        if stage == "integration waits for approval" and automatic(by_number.get(n, {})):
            stage = "automatic integration pending"
        if row in groups["blocked"]:           # as the board counts it (N1.13), before details a cut may take
            head, cut, detail = ("", "", "") if stage.startswith("waits for") else stage.partition(" (")
            lead = head + ", waits for " if head else "waits for "
            stage = lead + _refs(row["blocked_by"], (room or int(w * STATE)) - len(lead)) + cut + detail
        stage += f", last run: {note}" if note and n not in failed else ""
        return stage.replace("PLAN", "plan"), "31" if stage.startswith(("locked", "failed")) else \
            "33" if stage.startswith(("waits for", "integration", "on hold", "plan:", "result:")) \
            else "90"

    feats = places(vm)                    # feature (or branch without one) -> every agent on it
    lit = {i["number"]: light(i) for _, i in held if not i.get("draft")}     # a draft says what its row says
    jobs = [n for n, (st, *_) in lit.items() if st == "working"     # no hooks, or a long command: all idle
            and all(a["state"] == "idle" for a in feats.get(n, []))]
    counts = Counter([a["state"] for a in actors] + [st for n, (st, _, step) in lit.items()     # waiting: NEEDS YOU names it
                                                     if (st != "working" or n in jobs) and (st != "waiting" or step)]
                     + [wants(x)[0] for x in rows])
    tone = {"error": "31", "waiting": "33"}

    def gate(i):
        """Where a feature stands, and for someone else's claim without a result or heartbeat since when:
        the state a person acts on first, the age after it, where a cut takes it. An item nobody
        holds says what its ramp row says."""
        if i["number"] not in lit:
            if i["number"] in local:               # the runner's, its claim not on the board yet (#211)
                n = i["number"]
                return "working", (runner.get("title") or runner.get("phase", "")) if runner.get("item") == n \
                    else PHASE.get(phases[n], phases[n])
            if i.get("draft") and i["assignees"]:      # its spec is being written, under its holder only (#55)
                since = i.get("claimed_beat") or i.get("claimed_at")
                who = i.get("claimed_by") or i["assignees"][0]
                return "idle", f"spec in progress by {who}" + (f", {_age(since)}" if since else "")
            row = next((x for x in rows if x["number"] == i["number"]), None)
            return (wants(row)[0], says(row)[0]) if row else ("idle", "")
        st, words, _ = lit[i["number"]]
        held = i.get("claimed_at") or i.get("claimed_beat")
        since = f", held {_age(held)}" if held and not mine(i) and not i.get("result") \
            and not (_run(i) and i.get("claimed_beat")) and not holding(i)[0] else ""
        return st, words + since

    if stages is not None:
        stages.update({i["number"]: gate(i)[1] for i in vm["items"]})

    def inside(seen) -> list:
        """The item view: what the item is for, where it stands, who holds it, what it waits for."""
        i = by_number.get(seen["number"])
        row = next((r for r in vm.get("done") or () if r["number"] == seen["number"]), None)
        if not i and row:                          # integrated lately: what DONE says of it, as a view (#217)
            title = wrap(f"#{row['number']} {row['title']}".rstrip(), w)
            facts = [("stage", f"integrated by {row['who'] or '?'}, {_when(row['at'])}"),
                     ("merge", row["merge"][:12]), ("plan", seen.get("plan") or "none")]
            return ([section(title[0])] if len(title) == 1 else [p(line, "1;36") for line in title]) + [""] + \
                [f" {label:<12}{piece}" if k == 0 else " " * 13 + piece
                 for label, value in facts for k, piece in enumerate(wrap(value, w - 13))]
        if not i:
            return [p(f"#{seen['number']} is merged or closed", "90")]
        n, result, beat = i["number"], i.get("result") or {}, i.get("claimed_beat")
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
        if holding(i)[0]:                          # the session, its phase, and its last sign of life (#195)
            who, life = holding(i)[0].removeprefix("held by "), ""
        got = seen.get("approvals")                # a list, None when GitHub did not answer, or READING
        said = [got] if isinstance(got, str) else [f"integration by @{login}" + (f", {_when(at)}" if at else "") for g, login, at in got or ()] \
            or ["none" if got == [] else "could not be read"]
        facts = [("goal", seen["goal"] or "-"), ("stage", p(words or "-", tone.get(st, "90")))] + \
            [(k, v) for k, v in zip(["approvals"], said[:1]) if "approvals" in seen] + \
            [("", v) for v in said[1:]] + [
                 ("holder", ", ".join(filter(None, [who, life])) if who else "nobody"),
                 ("blocked by", _refs(i["blocked_by"], w - 13) if i["blocked_by"] else "nothing"),
                 ("result", result.get("head", "")[:12] or "none"),
                 ("base", result.get("base", "")[:12] or "none"),
                 ("checks", ", ".join(f"{name}: {value}" for name, value in sorted(result.get("gates", {}).items())) or "none"),
                 ("spec", i.get("spec") or "none"), ("plan", seen["plan"] or "none yet")]
        facts += [("action" if k == 0 else "", text) for k, text in enumerate(showing.get(n, []))]     # #215
        if "plan_blob" in seen:
            facts.append(("plan blob", seen["plan_blob"] or "local preview; publish before building"))
        facts += [("plan issue", finding) for finding in seen.get("plan_findings", ())]
        observed = vm.get("plans", {}).get(n)
        if observed:
            facts += [("plan state", "versions differ; choose a source" if observed["conflict"] else
                       "validated locally" if observed["selected"] and not observed["validation"]["findings"] else
                       "validation blocked" if observed["exists"] else "missing"),
                      ("commit", "exact content committed" if observed["commit"]["matches"] else "not committed"),
                      ("publication", "exact content published" if observed["publication"]["matches"] else "not published")]
            for _, source, _ in _plan_entries(observed):
                facts.append(("plan source", f"{source['path']} ({source['layer']}) in " +
                              (source.get("worktree") or source.get("ref") or "unknown")))
            failure = observed.get("failure") or {}
            if failure:
                facts += [("plan failed", ("previous: " if failure.get("stale") else "") +
                           f"{failure.get('step', 'publication')} blocked: {failure.get('cause', '')}")]
        r = next((x for x in refused if x.get("number") == n and not x.get("legacy")), None)
        if r:                                  # what a hook refused, what it does now, how its output ends (#178)
            facts += [("refused", f"{go.refusal_cause(r)}, {_when(r.get('at'))}" +
                       (f", base {str(r['sha'])[:12]}" if r.get("sha") else "")),
                      ("effect", f"{go.refusal_standing(r)}; {go.refusal_effect(r)}" if r.get("current") else
                       "earlier; " + go.refusal_effect(r))]
            facts += [("output" if k == 0 else "", line) for k, line in enumerate((r.get("lines") or [])[-4:])]
        menu = offers(vm, seen)
        pick = min(seen.get("pick", 0), len(menu) - 1)
        choice = [(p(f" › {words:<14} ", "1") if k == pick else f"   {words:<14} ")
                  + p(note, "33" if note.startswith("not yet") else "90")
                  for k, (_, words, note) in enumerate(menu)] or [p("   nothing to do here now", "90")]
        title = wrap(f"#{n} {i['title']}", w)
        title[0] = title[0].replace(f"#{n}", p.link(f"#{n}", i.get("url")), 1)
        heading = [section(title[0])] if len(title) == 1 else [p(line, "1;36") for line in title]
        details, top = [], len(out) + len(heading) + 1          # the row of the first detail
        reads = {"spec": ("open", n) if i.get("spec") else None,
                 "plan": ("read-plan", n) if seen["plan"] not in ("", "versions differ") else None,
                 "checks": ("read-log", n) if seen.get("log") else None,
                 "refused": ("read-check-output", n) if r and r.get("output") else None,     # #178 in the reader
                 "output": ("read-check-output", n) if r and r.get("output") else None}
        for label, value in facts:
            pieces = wrap(value, w - 13) if label in ("goal", "stage", "plan", "plan blob", "plan issue", "action",
                         "plan state", "commit", "publication", "plan source", "plan failed", "refused",
                         "effect", "output", "") else [value]
            if reads.get(label):                # a click on the row reads it (#180)
                marks.update({top + len(details) + k: ("read", reads[label]) for k in range(len(pieces))})
            details += [f" {label if index == 0 else '':<12}{piece}" for index, piece in enumerate(pieces)]
        first = len(out) + len(heading) + 1 + len(details) + 1          # the row of the first entry
        marks.update({first + k: ("offer", k) for k in range(len(menu))})
        return heading + [""] + details + [""] + choice
    parts = [(dot("working") if counts["working"] else dot("idle")) + f" {counts['working']} working"]
    if counts["waiting"]:
        parts.append(dot("waiting") + f" {counts['waiting']} need{'s' if counts['waiting'] == 1 else ''} you")
    if counts["error"]:
        parts.append(dot("error") + f" {counts['error']} failing")
    warn = "; ".join(filter(None, (vm.get("off"), vm.get("error"), vm.get("halt"), *(
        f"#{r['number']} {go.refusal_standing(r)}: {go.refusal_cause(r)}" for r in refused if r.get("current")),
        vm.get("untrusted"), (vm.get("order") or {}).get("why"))))
    inset = INSET if w >= 60 else 0       # beside a session the header keeps its words and leaves out the signet
    if remedy:
        # The action stays in the fixed header even on a short screen. NEEDS YOU keeps the whole explanation.
        action = short("You: " + remedy.partition(" in ")[0], w - inset - 2)
        warn = p.link(action, destination)
    head = [lr(p("pulse", "1") + "  " + p(vm["repo"] or "no repo", "90") + "  " + vm["person"], p(vm["now"], "1"),
                   w - inset),
            "   ".join(parts), p("! " + warn, "33") if warn else ""]
    mark = signet(p.color)
    mode = p(vm["auto_why"], "31") if vm.get("auto_why") else auto.line(vm.get("auto") or {})
    mode += "".join(p("; " + text, "90") for text in showing.get(0, []))      # its local change, as the outbox has it
    out = [(fit(mark[index], inset) if inset else "") + text for index, text in enumerate(head + [mode])]
    if live:
        marks[3] = ("settings",)               # a click on the approval line opens the settings (#182)
    out.append("")
    goal, aims = vm.get("goal"), []    # the goal, at the row of the runner that follows it (#215 FR-02)
    if goal:
        report = vm.get("goal_report") or {}
        applied = report.get("goal") or {}
        pending = (report.get("run") or {}).get("running") and any(
            goal.get(key) != applied.get(key) for key in ("id", "revision"))
        status = goal["status"]
        if pending:
            status = ("pause requested; " if status == "paused" else "") + "runner update pending"
        scope = goal["scope"]
        scope_text = "queue + goal" if scope["mode"] == "additive" else "restricted: " + (
            ", ".join((scope.get("selector") or {}).values()) or
            ", ".join(f"#{number}" for number in scope.get("items", [])) or "being resolved")
        progress = goal.get("progress") or {}
        done, remaining = len(progress.get("done", [])), len(progress.get("remaining", []))
        aims = [short(f"goal: {status} · {goal['objective']}", w - 2), f"scope: {scope_text} · {done} of "
                f"{done + remaining} done", "holds: " + goal["reason"] if goal.get("reason") else "",
                "resume: pulse go --resume" if goal["status"] == "paused" else ""]
    if item:
        return [fit(line, w) for line in out + inside(item)]
    if settings is not None:
        return [fit(line, w) for line in out + _settings_view(settings, p, w, section, marks, len(out))]

    # --- needs you ----------------------------------------------------------
    # only what the person must do (#215 FR-03): what NEXT showed yellow or red, a decision of the run, and an
    # attended session that waits; each an item or session pick with its reason and key
    needs = []                            # (target, label, key, the reason's lines, color)
    if remedy:                            # the base holds the run; the header keeps its first words
        cause = ": ".join(filter(None, (diagnostic.get("check"), diagnostic.get("cause"))))
        needs.append((None, "base", "", [t for t in ("You: " + remedy, cause, "Saved base verdict still blocks new "
                                                       "work." if diagnostic.get("cached") else "", destination,
                                                       vm.get("error"), vm.get("halt"), vm.get("untrusted"),
                                                       (vm.get("order") or {}).get("why")) if t], "33"))
    if vm.get("halt_kind") == "compatibility":     # the decision and the whole output of the probe (FR-05 of #178)
        probe = vm.get("compatibility") or {}
        needs.append((None, "plan commit gates", "", [t for t in ("You: " + probe["next"] if probe.get("next") else
                                                                   "", "check output: " + probe["log"]
                                                                   if probe.get("log") else "") if t], "33"))
    for r in refused:                     # a hook's refusal that a person decides
        if r.get("current") and not r.get("legacy") and r.get("state") == "decision":
            n = r.get("number")
            label = f"#{n} {by_number[n]['title']}" if n in by_number else f"#{n}"
            needs.append((("item", n) if n in by_number else None, label,
                          "enter opens" if live else f"pulse status {n}", ["You: " + (r.get("why") or f"decide #{n}") +
                           (f"; the failure is {go.UNSENT}" if r.get("unsent") else "")],
                          "33"))
    asked = [(i, lit[i["number"]]) for _, i in held if i["number"] in lit] + \
        [(x, (wants(x)[0], says(x)[0], wants(x)[1])) for x in rows]
    for i, (st, words, step) in asked:
        if step and NEXT.get(step[0]) in ("31", "33") and ("item", i["number"]) not in [e[0] for e in needs]:
            n, approves = i["number"], step[1] == f"pulse approve {i['number']}"   # a result: base changed is none
            key_ = ("a approves" if approves else "enter opens") if live else \
                (step[1] if approves else f"pulse status {n}")       # pulse status prints the commands (#215)
            needs.append((("item", n), f"#{n} {i['title']}", key_,
                          [words] if approves or step[0] == "held silent" else
                          [words, step[1]] if step[0] in ("failing", "integration", "plan needs you", "on hold") else [step[1]],
                          NEXT[step[0]]))
    for a in actors:                      # an attended session asks for a permission or an answer
        if a["state"] == "waiting":
            needs.append((("session", a["id"]), f"{a.get('harness') or 'agent'} {a['id'][:8]}",
                          "enter jumps" if live else "",
                          [_doing(a)[0] + (f": {a['tool']}" if a.get("tool") and a["tool"] != "AskUserQuestion"
                                           else "")], "33"))
    if needs:
        at = opens("NEEDS YOU")
        for target, label, key_, reasons, code in needs:
            pick = target and (target[1] if target[0] == "item" else target)
            if target and pick not in shown:
                shown.append(pick)
            if target:
                marks[len(out)] = target
            left = (p("› ", "1") if target and pick == selected else " ") + label
            out.append(lr(p(left, "1") if target and pick == selected else left, p(key_, "90"), w))
            out += ["   " + (p.link(line, destination) if text == destination else p(line, code))
                    for text in reasons for line in wrap(text, w - 3)]
        out.append("")
        closes("NEEDS YOU", at, len(needs))

    # --- board ------------------------------------------------------------
    total = max(1, sum(map(len, groups.values())))
    at = opens("BOARD")
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
        marks[len(out)] = ("item", number)
        out.append((p(label, "1") if number == selected else label) + "  " +
                   p("█" * filled, "32") + p("░" * (10 - filled), "90") + " " + fit(count, count_width))
    out.append("")
    closes("BOARD", at, sum(map(len, groups.values())))

    # --- who is doing what ------------------------------------------------
    at = opens("WHO IS DOING WHAT")

    def focus(agents):
        """The agent to show: one that needs you or failed first, then the latest activity."""
        return min(agents, key=lambda a: (RANK.index(a["state"]), -a.get("last", 0)))

    def said(agents) -> tuple:
        """What the agents on one line do: the one focus picks."""
        return _doing(focus(agents))

    def pick(target, at) -> bool:
        """target is a pick and the target of row at; whether the cursor is on it."""
        if target not in shown:
            shown.append(target)
        marks[at] = target
        return target == selected

    def details(sessions, pad, at):
        """A row per session from row at of out on, with its place, what it does and since when, and below it its
        running subagents (#234): each a pick and a target, Enter or a click jumps to its Herdr pane (#181), a
        subagent's to its session's."""
        rows = []
        for k, a in enumerate(sessions):
            corner = "  └ " if k == len(sessions) - 1 else "  ├ "            # the last one closes the branch (#239)
            lead = (p("› ", "1") if pick(("session", a["id"]), at + len(rows)) else pad) + corner + \
                dot(a["state"]) + f" {a['harness']} {a['id'][:8]}"
            doing, code, took = *_doing(a), _took(a.get("since"))
            room = beside(lead, w) - vlen(took) - 1         # the duration stays, the activity shortens (#234)
            note = p(" ".join(filter(None, (short(doing or "thinking", max(6, room)), took))), code)
            place = vm["branches"].get(a.get("cwd", ""), "") or a.get("branch") or os.path.basename(a.get("cwd", ""))
            whole = lead + (f" · {place}" if place else "")
            if vlen(whole) + 2 + vlen(note) <= w or not place:
                rows.append(lr(whole, note, w))
            else:                              # narrow: the place on a row of its own
                rows += [lr(lead, note, w), fit(pad + "      " + p(place, "90"), w)]
            for s in a.get("agents") or ():
                kind, what = s.get("type") or s["id"][:8], s.get("description") or ""
                lead = (p("› ", "1") if pick(("session", s["id"]), at + len(rows)) else pad) + "      ↳ "
                took = p(_took(s.get("began")), "90")
                if what and vlen(lead + kind + what) + 4 + vlen(took) > w:     # narrow: what it does below
                    rows += [lr(lead + kind, took, w)] + [fit(pad + "        " + line, w)
                                                          for line in wrap(what, w - len(pad) - 8)]
                else:
                    rows.append(lr(lead + kind + (f": {what}" if what else ""), took, w))
        return rows

    def unfolds(key, sessions, pad, at):
        """The row that counts the sessions of an item (#n) or a branch, folded at first; Enter, → or a click unfold
        them and their subagents, kept per clone as a section's fold (#234 FR-03). Only the live map has it: pulse
        status counts them on the item's row."""
        if not live:
            return []
        title = f"{key} sessions"
        picked = pick(("section", title), at)
        rows = [(p("› ", "1") if picked else pad) + "  " + p(("▾ " if title in folded else "▸ ") +
                                                             _plural(len(sessions), "session"), "1" if picked else "90")]
        return rows + (details(sessions, pad, at + 1) if title in folded else [])

    def ladder_of(i):
        """The ladder of my job (#215 FR-01): its phase in this run, the runner's step before its claim, a
        session's phase, or a published result at integrate; [] for no job of mine."""
        n = i["number"]
        if not (mine(i) or n in local) or n in failed:
            return []
        if n in phases:
            return ladder(phases[n], vm.get("phase_since", {}).get(n))
        if runner.get("item") == n:
            words = runner.get("title") or ""
            return ladder("spec" if "spec" in words else "plan" if "plan" in words else "build")
        if i.get("result"):
            return ladder("integrate")
        plan = (vm.get("plans") or {}).get(n) or {}       # a held item without a phase stands where its work is (#234)
        return ladder(i.get("claimed_phase")) or ladder("spec" if i.get("draft") else
                                                        "build" if plan.get("ready") else "plan")

    def tree(entries, theirs=False):
        """Features, each with what its agent does below it; agents outside any feature by branch. Of someone
        else's items only the item and its branch (#215 FR-06)."""
        rows = []
        for k, (e, agents) in enumerate(entries):
            stem, pad = ("└ ", "  ") if k == len(entries) - 1 else ("├ ", "│ ")
            states = [a["state"] for a in agents]
            count = "" if live or not _sessions(agents) else _plural(len(_sessions(agents)), "session")
            if isinstance(e, str):            # an agent on a branch that is no open feature
                doing, code = said(agents)
                rows.append(lr(stem + dot(roll(states)) + " " + e, p(", ".join(filter(None, (doing, count))), code), w))
                rows += unfolds(e, _sessions(agents), pad, len(out) + len(rows)) if _sessions(agents) else []
                continue
            st, words = gate(e)
            if not theirs:                     # the tree names the holder already (#234 FR-02)
                words = re.sub(r"^held by [^,]+, ", "", words)
            label = p.link(f"#{e['number']}", e.get("url")) + f" {e['title']}"
            if e["number"] not in shown:
                shown.append(e["number"])
            if e["number"] == selected:
                stem, label = p("› ", "1"), p(label, "1")
            marks[len(out) + len(rows)] = ("item", e["number"])     # out takes these rows next
            rows.append(lr(stem + dot(roll(states + [st])) + " " + label, p(count, "90") if theirs else
                           p(", ".join(filter(None, (count, words))), tone.get(st, "90")), w))     # the count first
            steps = [] if theirs else ladder_of(e)
            if steps:                          # its ladder; Plan k/n (#216) goes below it
                lines = [""]                   # whole stages a row, as the terminal counts them
                for piece in (f"{LADDER[s]} {name}" for name, s in steps):
                    gap = "  " if lines[-1] else ""
                    if lines[-1] and vlen(lines[-1] + gap + piece) > w - len(pad) - 2:
                        lines.append(piece)
                    else:
                        lines[-1] += gap + piece
                rows += [pad + "  " + p(line, "90") for line in lines]
                done = vm.get("tasks", {}).get(e["number"])
                if done:                       # how far its Plan is: Plan k/n and the next open task (#216)
                    k, total, title = done
                    rows.append(pad + "  " + p(short(f"Plan {k}/{total}" + (f": {title}" if title else ""),
                                                     w - len(pad) - 2), "90"))
            rows += [pad + "  " + p(line, "33") for text in showing.get(e["number"], [])    # my actions (FR-05)
                     for line in wrap(text, w - len(pad) - 2)]
            if agents:                         # my sessions, a teammate's item too (WP-54), folded (#234)
                if _sessions(agents):
                    rows += unfolds(f"#{e['number']}", _sessions(agents), pad, len(out) + len(rows))
                else:
                    doing, code = said(agents)
                    rows.append(lr(pad + "└ " + p(doing, code), "", w))
            branch = (e.get("result") or {}).get("branch") or e.get("branch") or (e.get("work") or {}).get("branch") \
                or next((b for a in agents for b in [vm["branches"].get(a.get("cwd", ""), "")]
                         if state.item_of(b) == e["number"]), "")
            if branch:                         # the branch its work goes on (#213)
                rows.append(fit(pad + "  " + p(branch, "90"), w))
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
    entries += [(by_number[n], []) for n in sorted(local) if n not in feats and not by_number[n]["assignees"]]

    count = sum(len(_sessions(agents)) for _, agents in entries)       # items, sessions, a run's slots (#234 FR-01)
    summary = [_plural(sum(not isinstance(e, str) for e, _ in entries), "item")] + \
        ([_plural(count, "session")] if count else [])
    left = dot(roll([a["state"] for a in actors] + [gate(i)[0] for login, i in held if login == vm["me"]])) + \
        " " + p(vm["person"], "1")
    k, n = len(phases), vm["ramp"]["cap"]
    for slots in ([f"pulse go: {k} of {n} slots", f"go: {k} of {n} slots", f"go {k}/{n}"] if runner else [""]):
        right = ", ".join(filter(None, (*summary, slots)))      # as much as fits at 44 columns too
        if vlen(right) <= beside(left, w):
            break
    out.append(lr(left, p(right, "90"), w))
    out += tree(entries)
    if runner or aims or refused or live and vm.get("run"):    # the runner: its goal, what it does, what comes next
        seconds = _secs(runner.get("started"))
        elapsed = "not running" if not runner else f"{max(0, int(seconds))} s" \
            if seconds is not None and 0 <= seconds < 60 else _age(runner.get("started"))
        out.append(lr(dot("working" if runner else "idle") + " " + p("Pulse runner", "1"), p(elapsed, "90"), w))
        named = runner.get("workers") if isinstance(runner.get("workers"), dict) else {}
        hints = [*aims, doing, "then: " + runner["next"] if runner.get("next") else "", runner.get("detail"),
                 named and f"workers {named.get('spec')} ({named.get('why')})"]      # #182, #215 FR-02, FR-04
        for r in refused:                     # a hook's refusal the run handles: a fix round, a wait, the past
            n, cause, effect = r.get("number"), go.refusal_cause(r), go.refusal_effect(r)
            if r.get("legacy") or not r.get("current"):
                when = f"run ended {_when(r.get('at'))}" if r.get("legacy") else _when(r.get("at"))
                hints.append(f"earlier, {when}: " + (cause if r.get("legacy") else f"#{n} {cause}" +
                             (f" on base {str(r['sha'])[:12]}" if r.get("sha") else "")) + f"; {effect}")
            elif r.get("state") == "waits":
                stand = "; ".join(f"#{m} {by_number[m]['title']}: {gate(by_number[m])[1] or 'open'}"
                                  if m in by_number else f"#{m} closed" for m in r.get("needs") or ())
                hints.append(f"#{n} {go.refusal_standing(r)} ({stand}): {cause}; {effect}")
            elif r.get("state") != "decision":
                hints.append(f"fix round for #{n}: {cause}")
        for k, text in enumerate(filter(None, hints)):
            lines = [short(text, w - 2)] if k == 0 and aims else wrap(text, w - 2)     # the goal in one line
            out += ["  " + p(line, "90") for line in lines]
        if live and vm.get("run"):            # the live map only: pulse status prints as before (#180)
            marks[len(out)] = ("read", ("read-report", None))
            out.append(lr("  " + p("run report", "90"), "r reads the last run of pulse go", w))
    for login in sorted(others, key=str.lower):
        items = list(others[login].values())
        out.append(lr(dot(roll([gate(i)[0] for i in items])) + " " + p(login, "1"),
                      p(_plural(len(items), "item"), "90"), w))
        out += tree([(i, feats.get(i["number"], [])) for i in items], theirs=True)     # item and branch only
    out.append("")
    closes("WHO IS DOING WHAT", at, len(entries) + len(theirs))

    # --- ramp ---------------------------------------------------------------
    at = opens("BACKLOG", "all open work, in the order it goes out")
    for row in rows[:ROWS_SHOWN]:
        title = p.link(f"#{row['number']}", row.get("url")) + f" {row['title']}"
        if row["number"] not in shown:
            shown.append(row["number"])
        left = p("▲ " + title, "36") if row["stage"].startswith("starts next") and row["number"] not in failed \
            else "  " + title
        if row["number"] == selected:
            left = p("› " + title, "1")
        stage, code = says(row, beside(left, w))
        marks[len(out)] = ("item", row["number"])
        out.append(lr(left, p(stage, code), w))
        step = wants(row)[1]
        if step and step[0] in ("spec rule", "plan repair"):     # what moves it, no person's lever (3af25a75)
            out += ["    " + p(line, "90") for line in wrap(step[1], w - 4)]
        out += ["    " + p(line, "33") for text in showing.get(row["number"], [])    # its actions (#215 FR-05)
                for line in wrap(text, w - 4)]
    if len(rows) > ROWS_SHOWN:
        out.append(p(f"  +{len(rows) - ROWS_SHOWN} more", "90"))
    if not rows:
        out.append(p("  nothing ready", "90"))
        if not (held or runner or remedy):    # an empty board says how work begins, as NEXT did
            out.append(p("  nothing open: /pulse-ba explores, /pulse-re writes specs", "90"))
    done = vm.get("done")
    if done is not None:
        out.append("")
    closes("BACKLOG", at, len(rows))

    # --- done (#217): what Pulse integrated lately, who and when; only when the board was read --------------
    if done is not None:
        at = opens("DONE", f"integrated in the last {DONE_DAYS} days")
        for row in done[:ROWS_SHOWN]:
            n, title = row["number"], f"#{row['number']} {row['title']}".rstrip()
            if n not in shown:
                shown.append(n)
            left = p("› " + title, "1") if n == selected else "  " + title
            marks[len(out)] = ("item", n)
            out.append(lr(left, p(f"{row['who'] or '?'}, {_when(row['at'])}", "90"), w))
        if len(done) > ROWS_SHOWN:
            out.append(p(f"  +{len(done) - ROWS_SHOWN} more", "90"))
        if not done:
            out.append(p(f"  nothing integrated in the last {DONE_DAYS} days", "90"))
        closes("DONE", at, len(done))
    return [fit(l, w) for l in out]


def _settings_view(seen: dict, p, w: int, section, marks: dict, top: int) -> list:
    """The settings view under the header (#182): each setting with its value, where it comes from and what it does,
    the rules evidence, and the changes Enter previews; marks gets ("offer", k) for the rows of entry k."""
    rows = [section("SETTINGS")]
    if seen.get("reading"):
        return rows + [p("  " + READING, "90")]
    for label, value, where, effect in seen["rows"]:
        rows += [f" {label if k == 0 else '':<12}{piece}" for k, piece in enumerate(wrap(f"{value} ({where})", w - 13))]
        rows += [" " * 13 + p(piece, "90") for piece in wrap(effect, w - 13)]
    rows += ["", section("RULES")] + [" " + piece for line in seen["rules"] for piece in wrap(line, w - 1)] + [""]
    if seen.get("levers"):                      # the person's lever grants and their latest uses (#197 FR-10)
        rows.append(section("LEVERS"))
        for label, value, where, effect in seen["levers"]:
            rows += [f" {label if k == 0 else '':<12}{piece}" for k, piece in enumerate(wrap(f"{value} ({where})", w - 13))]
            rows += [" " * 13 + p(piece, "90") for piece in wrap(effect, w - 13)]
        rows.append("")
    menu = seen["offers"]
    pick, col = min(seen.get("pick", 0), len(menu) - 1), max((len(words) for _, words, _ in menu), default=0)
    for k, (_, words, note) in enumerate(menu):
        first = (" › " if k == pick else "   ") + f"{words:<{col}}  "
        lines = [first + note] if vlen(first + note) <= w else [first.rstrip()] + ["     " + x for x in wrap(note, w - 5)]
        marks.update({top + len(rows) + j: ("offer", k) for j in range(len(lines))})
        rows += [p(lines[0], "1") if k == pick else lines[0]] + [p(x, "90") for x in lines[1:]]
    return rows


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


def _plan_entries(observed: dict) -> list:
    """Stable menu keys bind a source and its exact content, even when variants disagree."""
    out, seen = [], set()
    for variant in observed.get("variants", []):
        for source in variant["sources"]:
            selection = {key: source[key] for key in ("path", "content")}
            selection["worktree" if source.get("worktree") else "ref"] = source.get("worktree") or source["ref"]
            token = hashlib.sha256(json.dumps([selection, source["layer"]], sort_keys=True).encode()).hexdigest()[:16]
            if token not in seen:
                out.append((token, source, selection))
                seen.add(token)
    return out


def _plan_log(root: Path, number: int, value: str, suffix: str = ".log") -> Path | None:
    """Only this item's existing ordinary log (or hook output, .hook.txt) inside this clone's common directory may
    open."""
    expected = config.pulse_dir(root) / "go" / f"{number}{suffix}"
    try:
        if value and Path(value) == expected and expected.resolve() == expected and \
                stat.S_ISREG(expected.lstat().st_mode):
            return expected
    except (OSError, ValueError):
        pass
    return None


def _plan_observed(root: Path, item: dict, cfg: dict, sources: dict, report: dict) -> dict:
    observed = ready.plan_state(root, item, cfg, sources)
    prior = (report.get("items") or {}).get(str(item["number"])) or {}
    work = item.get("work") if isinstance(item.get("work"), dict) else prior.get("work") or {}
    failure = work.get("failure") or (prior.get("failure") if "work" not in item else None)
    if isinstance(failure, dict) and failure.get("phase") == "plan":
        failure = dict(failure)
        same = next((selection for _, _, selection in _plan_entries(observed)
                     if selection["content"] == failure.get("content")), None)
        current = ready.plan_state(root, item, cfg, sources, same) if same and observed["conflict"] else observed
        failure["stale"] = not same or current["ready"] or \
            failure.get("checked_against") != current["validation"]["checked_against"]
        observed["failure"] = failure
        log = _plan_log(root, item["number"], failure.get("log"))
        if log:
            observed["error_log"] = str(log)
    return observed


def _publishable(item: dict) -> bool:
    return bool(item) and item.get("state", "OPEN") == "OPEN" and not any(item.get(key) for key in
        ("hold", "local_hold", "failed", "claim", "claim_token", "claimed_holder", "assignees", "result"))


def offers(vm: dict, seen: dict) -> list:
    """Actions for the published result and the observed shared item."""
    item = next((x for x in vm["items"] if x["number"] == seen["number"]), None)
    if not item:
        return []
    out = []
    if item.get("result"):
        if item.get("approval"):
            out.append(("revoke", *OFFER["revoke"]))
        elif not (item.get("hold") or item.get("failed") or item.get("state") == "CLOSED"):
            waiting = seen.get("waiting")
            why = "not yet: " + waiting[2] if waiting and waiting[0] is None else OFFER["approve"][1]
            out.append(("approve", OFFER["approve"][0], why))
        out.append(("read-result", *OFFER["read-result"]))
    observed = vm.get("plans", {}).get(seen["number"])
    if observed is not None:
        for index, (token, source, _) in enumerate(_plan_entries(observed), 1):
            label = f"plan source {index}"
            out.append(("read-plan:" + token, "read " + label, source["layer"] + ": " + source["path"]))
            if source["layer"] == "file" and not observed["ready"] and _publishable(item):
                out.append(("publish-plan:" + token, "publish " + label, "preview this preserved content"))
        if observed.get("error_log"):
            out.append(("read-plan-error", "read plan error", "open the publication log"))
    elif seen.get("plan"):
        out.append(("read-plan", *OFFER["read-plan"]))
    if any(r.get("number") == item["number"] and r.get("output") for r in vm.get("refusals") or ()):
        out.append(("read-check-output", "read check output", "show the whole output of the refused check"))
    if item.get("spec"):
        out.append(("open", *OFFER["open"]))
    out += [("read-doc:" + path, "read " + label, path) for label, path in seen.get("docs", ())]
    if seen.get("log") and not (observed or {}).get("error_log"):     # read plan error shows it already
        out.append(("read-log", "read run log", "output of gates and hooks in the last run"))
    out += [("retry-sync:" + entry["id"], "retry sync", f"{entry['kind']}: {entry['id']}")
            for entry in vm.get("actions", []) if entry["item"] == item["number"] and entry["status"] == "error"]
    out += [("redo:" + entry["id"], "redo " + entry["kind"], "reload the item, then confirm it again")    # #215
            for entry in _latest(vm.get("actions", [])).values()
            if entry["item"] == item["number"] and entry["status"] == "conflict" and entry["kind"] in LOCAL_ACTIONS]
    if item.get("type") in state.WORK:
        choices = ["resume" if item.get("hold") or item.get("failed") else "defer"] \
            if item.get("state", "OPEN") == "OPEN" else []
        if item.get("claim_token"):
            choices.append("handoff")
        choices += ["discard", "delete"]
        out += [(action, *OFFER[action]) for action in choices]
    return out


def key(ui: dict, picks: list, ch: str, acts=()) -> tuple:
    """(ui, action) for one key of the live map, a tree walked without Shift (D-44). ui: the level
    (map, item, confirm, help, read), the item it is at, in the item view the action picked, the approval
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
    if level in ("number", "value") or level == "confirm" and "expected" in ui:
        back = {"level": {"number": "map", "value": "settings"}.get(level) or ui.get("from", "item"), "at": n}
        if level == "value":                    # back in the settings, on the entry it came from (#182)
            back["pick"] = ui.get("pick", 0)
        typed = ui.get("typed", "")
        if ch in ("\x1b", "\x1b[D"):
            return back, None
        if ch in ("\x7f", "\x08"):
            return {**ui, "typed": typed[:-1]}, None
        if ch in ENTER:
            if level == "number" and typed and int(typed) > 0:
                return back, ("lookup", int(typed))
            if level == "value" and typed:      # the preview says whether the value holds
                return back, (f"setting:{ui['key']}={typed}", n)
            if level == "confirm" and typed == ui["expected"]:
                return back, ui["sure"]
            return ui, None
        allowed = ch in "0123456789" if level in ("number", "value") else len(ch) == 1 and ch.isprintable()
        limit = {"number": 10, "value": 3}.get(level) or len(ui["expected"])
        return ({**ui, "typed": typed + ch} if allowed and len(typed) < limit else ui), None
    if level == "map" and isinstance(n, tuple) and n[0] == "section":    # a heading: Enter or → folds it (#214)
        if ch in ENTER + RIGHT:
            return ui, ("fold", n[1])
        if ch in ("m", "a"):
            return ui, None
    elif level == "map" and isinstance(n, tuple):  # a session row (#181): Enter jumps, m, a and → do nothing
        if ch in ENTER:
            return ui, ("jump", n[1])
        if ch == "l":                            # its lever grants, in the settings (#197 FR-03)
            return {"level": "settings", "at": n}, None
        if ch in ("m", "a") + RIGHT:
            return ui, None
    if level == "map":
        if ch == "m" and n in picks:
            return ui, ("move", n)
        if ch == "g":
            return {"level": "number", "at": n, "typed": ""}, None
        if ch in PAGE + HOME + END:            # the map scrolls, the pick stays; main() keeps it in bounds (#214)
            scroll = 0 if ch in HOME else 1 << 30 if ch in END else \
                max(0, ui.get("scroll", 0) + ui.get("page", 1) * (-1 if ch == PAGE[0] else 1))
            return {**ui, "scroll": scroll}, None
        if ch in UP + DOWN and picks:          # main() keeps the pick in sight (#214 FR-04)
            k = picks.index(n) if n in picks else -1
            if k < 0 and ch in DOWN:            # the first pick is the first item, its heading comes by ↑ (#214)
                k = next((j for j, p in enumerate(picks) if not isinstance(p, tuple) or p[0] != "section"), 0) - 1
            return {**ui, "at": picks[max(0, k - 1) if ch in UP else min(len(picks) - 1, k + 1)]}, None
        if ch in ENTER + RIGHT and n in picks:
            return {"level": "item", "at": n}, None
        if ch == "a" and n in picks:              # the approval the picked item waits for (#121 FR-04)
            return ui, ("approve", n)
        if ch in ("1", "2", "3"):                 # only the final approval policy remains
            return ui, ("auto", "merge") if ch == "3" else None
        if ch == "?":
            return {"level": "help", "at": n, "from": "map"}, None
        if ch == "r":                             # the report of the last run, in the reader (#180)
            return ui, ("read-report", n)
        if ch == "s":                             # the settings of the project (#182)
            return {"level": "settings", "at": n}, None
        return ui, ("say", "q quits the map") if ch in BACK else None     # Esc never ends it (D-44)
    if level == "read":                         # the reader goes back to the view it opened from (#180)
        back = ui["back"]
    else:
        back = {"level": ui.get("from", "item"), "at": n}     # the help ends where it began
        if back["level"] in ("item", "settings"):
            back["pick"] = ui.get("pick", 0)
    if ch in BACK:                              # one level up, and what is not written yet is dropped
        return (back if level not in ("item", "settings") else {"level": "map", "at": n}), None
    if level in ("help", "read"):
        if ch in UP + DOWN + ("\x1b[5~", "\x1b[6~"):
            step = -1 if ch in UP + ("\x1b[5~",) else 1
            if ch in ("\x1b[5~", "\x1b[6~"):
                step *= ui.get("page", 1)
            return {**ui, "scroll": max(0, ui.get("scroll", 0) + step)}, None
        return ui, None
    if level in ("item", "settings"):          # the settings walk as the item view, without a and o (#182)
        if ch in ("\x1b[5~", "\x1b[6~"):
            step = ui.get("page", 1) * (-1 if ch == "\x1b[5~" else 1)
            return {**ui, "scroll": max(0, ui.get("scroll", 0) + step)}, None
        pick = min(ui.get("pick", 0), len(acts) - 1) if acts else ui.get("pick", 0)   # the offers may have changed
        if ch in UP + DOWN:
            return ({**{k: v for k, v in ui.items() if k != "scroll"},
                     "pick": max(0, pick - 1) if ch in UP else min(len(acts) - 1, pick + 1)}
                    if acts else ui), None
        if ch == "?":
            return {"level": "help", "at": n, "from": level, "pick": pick}, None
        if ch in ENTER and acts and acts[pick].startswith("setting:") and "=" not in acts[pick]:
            return {"level": "value", "at": n, "key": acts[pick].partition(":")[2], "typed": "", "pick": pick,
                    "from": "settings"}, None          # the settings stay on screen while it is typed
        if ch in ENTER and acts:
            return ui, (acts[pick], n)
        return ui, {"a": ("approve", n), "o": ("open", n)}.get(ch) if level == "item" else None
    if level == "confirm":                      # any other key: no approval
        return back, ui["sure"] if ch in ENTER else None
    return ui, None


def mouse(ch: str):
    """(button, column, row, pressed) of a mouse report in SGR form, 1-based as the terminal sends it; None for
    anything else (#180). Buttons 64 and 65 are the wheel."""
    m = SGR.fullmatch(ch or "")
    return (int(m[1]), int(m[2]), int(m[3]), m[4] == "M") if m else None


def pointer(ui: dict, picks: list, event: tuple, target, acts=()) -> tuple:
    """(ui, action) for one mouse report, as key() for a key (#180): the wheel moves the pick on the map and
    scrolls a view; a press of the left button on a target does what Enter does there. Only render() makes
    targets. A click confirms nothing: on a confirmation, a move, and the number prompt it does nothing."""
    button, _, _, pressed = event
    level, n = ui["level"], ui.get("at")
    if level in ("confirm", "move", "number", "value") or not pressed:
        return ui, None
    if button in (64, 65):
        if level == "map":
            return key(ui, picks, (UP if button == 64 else DOWN)[0])
        return {**ui, "scroll": max(0, ui.get("scroll", 0) + (WHEEL if button == 65 else -WHEEL))}, None
    kind = target[0] if button == 0 and target else ""
    if kind == "item" and level == "map":
        return {"level": "item", "at": target[1]}, None
    if kind == "session" and level == "map":     # picks the row and jumps, as Enter there (#181)
        return {**ui, "at": target}, ("jump", target[1])
    if kind == "section" and level == "map":     # picks the heading and folds its section, as Enter there (#214)
        return {**ui, "at": target}, ("fold", target[1])
    if kind == "offer" and level in ("item", "settings") and target[1] < len(acts):
        return key({**ui, "pick": target[1]}, picks, ENTER[0], acts)
    if kind == "settings" and level in ("map", "item"):
        return {"level": "settings", "at": n}, None
    if kind == "read" and level in ("map", "item") and target[1][0].partition(":")[0] in READS:
        return ui, target[1]
    if kind == "back" and level in ("help", "read"):
        return key(ui, picks, "\x1b")
    return ui, None


def move(root: Path, vm: dict, ui: dict, action: tuple, size: tuple) -> tuple:
    """Start from fresh authority; arrows only replace an in-memory proposal."""
    kind, number = action[:2]
    if not auto.person(os.environ, True):
        raise state.StateError("only a person moves items, in their own terminal or map")
    if kind == "move":
        candidate = next((record for record in vm["ramp"].get("rows", []) if record["number"] == number), {})
        if candidate.get("type") not in state.WORK or candidate.get("assignees") or candidate.get("claimed_holder"):
            raise state.StateError(f"#{number} is not an unclaimed work item in the backlog")
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


def _result_notes(item):
    findings = item.get("findings", (item.get("result") or {}).get("findings"))
    missing = item.get("missing") or []
    words = "; ".join(str(finding) for finding in findings) if findings else \
        "unavailable until full reports are read" if findings is None or missing else "none reported"
    return ["findings: " + words] + (["reports unavailable: " + ", ".join(missing)] if missing else [])


def _cached_person(root: Path) -> str:
    def offline(args):
        raise state.StateError("no cached account")
    try:
        login = state.me(root, run=offline, ttl=86400)
    except (OSError, state.StateError):
        login = ""
    return state.who(root, login) or "you"


def action_preview(root: Path, item: dict, kind: str, *, person=None) -> dict:
    """Prepare a local intent from exactly the revision the person has observed."""
    number, revision = item["number"], item.get("revision")
    if not revision:
        raise state.StateError(f"#{number}: open or refresh the Pulse map first; no shared revision is cached")
    if kind not in LOCAL_ACTIONS:
        raise state.StateError("unknown local action")
    payload = {}
    person = person or _cached_person(root)
    lines = [f"#{number} {item.get('title', '')}: {OFFER[kind][0]}", f"requested by: {person}"]
    if kind == "approve":
        if actions.held(root, number):
            raise state.StateError(f"#{number}: held locally; resume must synchronize before approval")
        gate, binding, why = ready.waiting(root, item)
        if gate != 3:
            raise state.StateError((why or f"#{number}: no verified result is ready for approval").replace("PLAN", "plan"))
        head, base = binding
        payload = {"head": head, "base": base}
        lines += [f"result: {head}", f"base: {base}"]
        diff = _git(str(root), "diff", "--no-ext-diff", "--no-textconv", "--stat", base, head, "--")
        lines += diff.splitlines() or ["No changed files in the cached result."]
        files = _git(str(root), "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                     "--name-only", "-z", base, head, "--").split("\0")
        protected = merge.protected(config.load(root), [path for path in files if path])
        if protected:
            lines.append("protected files: " + ", ".join(protected))
        lines += [f"{gate}: {value}" for gate, value in sorted(item["result"].get("gates", {}).items())]
        lines += _result_notes(item)
    elif kind == "handoff":
        holder = item.get("claim_token") or (item.get("claim") or {}).get("holder")
        if not holder:
            raise state.StateError(f"#{number}: no observed claim to hand off; refresh the map")
        payload = {"holder": holder, "reason": "Person requested a claim handoff", "work": item.get("work") or {}}
        lines.append("Request the current writer to stop and preserve its work before the claim is released.")
    elif kind == "defer":
        lines.append("Pause this item locally now; share the hold in the background.")
    elif kind == "resume":
        lines.append("Resume after the shared state confirms this request.")
    elif kind == "revoke":
        lines.append("Withdraw approval of the observed result and base.")
    return {"kind": kind, "item": number, "expected": revision, "payload": payload, "person": person,
            "lines": [ready.printable(line) for line in lines]}


def queue_action(root: Path, intent: dict) -> str:
    """Persist first, then wake the detached non-LLM synchronization worker."""
    saved = actions.submit(root, intent["item"], intent["kind"], intent["payload"], intent["expected"])
    answer = f"#{saved['item']}: {saved['kind']} queued locally by {intent.get('person') or 'you'}; synchronization pending"
    try:
        actions.start(root)
    except (state.StateError, OSError) as error:
        answer += f"; worker could not start: {error}; the request is saved"
    return ready.printable(answer)


def retry_action(root: Path, ident: str) -> str:
    """Retry the existing operation locally. Conflicts require newly observed intent."""
    from pulse import levers
    if not levers.may(root, os.environ, "retry"):      # a person, or a session under their grant (#197)
        raise state.StateError("only a person retries an action, in their own terminal or map")
    if not actions.retry(root, ident):
        raise state.StateError("no saved sync error to retry; refresh before submitting a new action")
    answer = f"{ident}: retry queued locally; synchronization pending"
    try:
        actions.start(root)
    except (state.StateError, OSError) as error:
        answer += f"; worker could not start: {error}; the request is saved"
    return ready.printable(answer)


def queue_policy(root: Path, enabled: bool, *, expected=None, until=None) -> str:
    accepted = auto.toggle(root, "", "merge", enabled, until=until, expected=expected)
    answer = f"Approval settings: {'automatic' if enabled else 'manual'} queued locally; synchronization pending"
    try:
        actions.start(root)
    except (state.StateError, OSError) as error:
        answer += f"; worker could not start: {error}; the request is saved"
    return ready.printable(answer + f" ({accepted['id']})")


def brief(root: Path, vm: dict, action: tuple) -> tuple:
    """The exact local intent Enter confirms; synchronization later checks its revision."""
    kind, number = action
    if not auto.person(os.environ, True):
        return ["only a person does this, in their own terminal or map"], None
    if kind.startswith("retry-sync:"):
        ident = kind.partition(":")[2]
        entry = next((e for e in vm.get("actions", []) if e["id"] == ident and e["item"] == number and
                      e["status"] == "error"), None)
        return ([f"Retry {entry['kind']} of #{number}: {ident}",
                 "The saved intent and version binding stay unchanged."], ("retry-sync", number, ident)) if entry else \
            (["Sync state changed; refresh before retrying."], None)
    if kind.startswith("publish-plan:"):
        item = next((x for x in vm["items"] if x["number"] == number), {})
        entry = next((row for row in _plan_entries(vm.get("plans", {}).get(number, {}))
                      if row[0] == kind.partition(":")[2] and row[1]["layer"] == "file"), None)
        if not entry or not _publishable(item):
            return [f"#{number}: plan selection changed or publication is blocked; refresh"], None
        selection = entry[2]
        return [f"Publish the preserved plan of #{number} through the normal commit and push checks.",
                *(f"{key}: {value}" for key, value in selection.items()),
                "No planner starts. Implementation waits for confirmed exact publication."], \
               ("publish-plan", number, selection)
    if kind.startswith("levers:"):              # a grant or revocation of the person's levers (#197)
        return settings.lever_preview(root, kind), ("levers", number, kind)
    if kind.startswith("setting:"):             # a commit on a branch of its own, after Enter (#182)
        key_, _, value = kind.partition(":")[2].partition("=")
        lines, intent = settings.preview(root, key_, value)
        return lines, (("setting", number, intent) if intent else None)
    if kind in LOCAL_ACTIONS:
        item = next((x for x in vm["items"] if x["number"] == number), None)
        if not item:
            return [f"#{number}: refresh the map first"], None
        try:
            intent = action_preview(root, item, kind, person=vm.get("person"))
        except state.StateError as error:
            return [ready.printable(str(error))], None
        return intent["lines"], (kind, number, intent)
    if kind == "auto":
        seen = auto.read(root)
        policy = seen["policy"]
        pending = [entry for entry in seen["pending"] if entry["status"] != "conflict"]
        enabled = pending[-1]["payload"]["mode"] != "automatic" if pending else not auto.active(policy)
        proposed = "automatic" if enabled else "manual"
        return [auto.line(seen), f"Set final approval to {proposed} for this repository?",
                "Automatic approval requires verified results, exact versions and current authority.",
                "Holds and revocations still block; destructive removal requires personal approval.",
                "Saved locally first; confirmed changes apply across the repository."], \
            ("auto", "merge", {"enabled": enabled, "expected": policy["revision"]})
    if kind in lifecycle.ACTIONS:
        planned = remove.action_preview(root, vm["repo"], number, run=state.gh) if kind == "delete" else \
            lifecycle.preview(root, vm["repo"], number, kind, run=state.gh)
        return planned["lines"], (kind, number, planned) if planned.get("confirmation") else None
    return ["no action is ready"], None


READING = "reading…"            # canonical approval details while the item view opens


def read_approvals(vm: dict, n: int):
    """Display the canonical final approval; old issue comments authorize no gate."""
    item = next((item for item in vm["items"] if item["number"] == n), {})
    approval = item.get("approval") or {}
    if approval.get("policy"):
        policy = (vm.get("auto") or {}).get("policy") or {}
        author = (policy.get("proof") or {}).get("author")
        if approval["policy"] == "default:auto:v1":
            return "automatic approval under the default policy"
        return "automatic approval, policy " + approval["policy"][:12] + \
            (f" set by @{author}" if author and policy.get("revision") == approval["policy"] else " (previous setting)")
    proof = approval.get("proof") or {}
    return [(3, proof.get("author") or "?", proof.get("at") or "")] if proof else []


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
    that has it (#68), and where the PLAN is; docs, what else it offers to read, and log, the run log (#180)."""
    i = next((x for x in vm["items"] if x["number"] == n), {})
    text = spec.find(root, i["spec"])[0] if i.get("spec") else None
    observed = vm.get("plans", {}).get(n)
    if observed is not None:
        selected = observed["selected"]
        seen = {"number": n, "goal": _goal(text),
                "plan": selected["path"] if selected else "versions differ" if observed["conflict"] else "",
                "plan_blob": observed["publication"]["blob"],
                "plan_findings": observed["validation"]["findings"]}
        plan = (selected or {}).get("text")
    else:
        p = ready.plans(root).get(n)
        seen = {"number": n, "goal": _goal(text),
                "plan": p["path"] + (f" on {p['ref']}" if p["ref"] else "") if p else "",
                **({"plan_blob": p.get("blob"), "plan_findings": ready.plan_validation(root, p["text"], i.get("spec"))}
                   if p else {})}
        plan = p["text"] if p else None
    docs = _docs(root, i.get("spec"), text, plan)
    log = _plan_log(root, n, str(config.pulse_dir(root) / "go" / f"{n}.log"))
    return {**seen, **({"docs": docs} if docs else {}), **({"log": str(log)} if log else {})}


def _docs(root: Path, path, text, plan) -> list:
    """[(label, path)] to read beside spec and plan (#180): the spec its spec names as parent, and each decision
    record its plan names, found as _devprocess/decisions/ADR-nn-*.md."""
    out = []
    parent = spec.front(text or "").get("parent")
    if isinstance(parent, str) and path:
        out.append(("parent spec", posixpath.normpath(posixpath.join(posixpath.dirname(path), parent))))
    names = spec.front(plan or "").get("decisions") or []
    for name in list(dict.fromkeys([names] if isinstance(names, str) else names))[:20]:    # each once, 20 at most
        found = sorted((root / "_devprocess" / "decisions").glob(name + "-*.md")) if re.fullmatch(r"ADR-\d+", name) \
            else []
        out += [(name, found[0].relative_to(root).as_posix())] if found else []
    return out


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


def _show(path, name: str, cmd: list = None):
    """A file for the reader in the map (#180), or a link (https://) opened in its window with cmd, else the
    opener(), giving the terminal back at once (D-44). What the reader shows, else the line for the status bar.
    It reads a regular file only, through no link at its place, and READ_MOST bytes at most: the end of a log,
    else the start, and names the cut."""
    if str(path).startswith("https://"):
        cmd = opener() if cmd is None else cmd
        try:
            if cmd:                     # never waits for it: the map runs on (D-44)
                subprocess.Popen(cmd + [str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                return f"opened {name} with {Path(cmd[0]).name}"
        except OSError:
            pass
        return f"open it yourself: {path}"
    got = _read(path)
    if got is None:
        return f"{name} cannot be read"
    data, size, tail = got
    if b"\0" in data:
        return f"{name}: no text to show"
    text = data.decode("utf-8", "replace")
    cut = f"the {'last' if tail else 'first'} {READ_MOST // 1024} KiB of {size // 1024} KiB" if size > READ_MOST else ""
    return _reading(name, str(path), text.partition("\n")[2] if tail else text, cut)


def _read(path):
    """(bytes, size, from the end) of a regular file, read through no link at its place and never waiting on a
    pipe (#180): READ_MOST bytes at most, the end of a .log, else the start; None when it cannot be read."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode):
                return None
            tail = info.st_size > READ_MOST and str(path).endswith(".log")
            if tail:
                f.seek(info.st_size - READ_MOST)
            return f.read(READ_MOST), info.st_size, tail
    except OSError:
        return None


def _reading(title: str, source: str, text: str, cut: str = ""):
    """What the reader shows (#180): {title, source, text: its rows, cut}, else why it shows nothing. A text
    longer than READ_MOST keeps its start and says so. Per line, colors and OSC sequences closed on that line
    go; any other escape or control character shows as ?, so no text acts on the terminal or disappears."""
    if not text.strip() or "\0" in text:
        return f"{ready.printable(title)}: no text to show"
    raw = text.encode("utf-8", "replace")
    if not cut and len(raw) > READ_MOST:
        text = raw[:READ_MOST].decode("utf-8", "ignore")
        cut = f"the first {READ_MOST // 1024} KiB of {len(raw) // 1024} KiB"

    def plain(s):
        return ready.printable(CONTROL.sub("", s).expandtabs(4))
    return {"title": plain(title), "source": plain(source),
            "text": [plain(row) for row in text.splitlines()], "cut": cut}


def _report_text(rep: dict) -> str:
    """The last run of pulse go as its report has it (#180): the run, its end, a halt, the base, and per item
    its result, time, phase, reason and log, the latest first."""
    run, base = rep.get("run") or {}, rep.get("base") if isinstance(rep.get("base"), dict) else {}
    end = "still running" if run.get("running") else run.get("ended") or "unknown"
    lines = [f"run: {run.get('id', '')}", f"started: {run.get('started', '')}",
             f"ended: {end}" + (f", stopped ({run['stopped']})" if run.get("stopped") else "")]
    lines += [f"halt: {rep['halt']}"] if rep.get("halt") else []
    lines += ["base: " + "; ".join(str(base[k]) for k in ("state", "cause", "next") if base.get(k))] if base else []
    items = [(n, e) for n, e in (rep["items"] if isinstance(rep.get("items"), dict) else {}).items()
             if isinstance(e, dict)]
    for n, entry in sorted(items, key=lambda x: str(x[1].get("at", "")), reverse=True):
        lines += ["", f"#{n} {entry.get('result', '')}"] + [
            f"  {word}: {entry[k]}" for k, word in (("at", "time"), ("phase", "phase"), ("why", "why"), ("log", "log"))
            if entry.get(k)]
    return "\n".join(lines)


def _publish_plan(root: Path, vm: dict, number: int, selection: dict) -> str:
    """Recheck the displayed file locally, then give publication to a detached CLI process."""
    if not auto.person(os.environ, True):
        return "only a person does this, in their own terminal or map"
    item = next((item for item in vm["items"] if item["number"] == number), {})
    if not _publishable(item) or actions.held(root, number):
        return f"#{number}: publication blocked; resume the item or wait for its writer"
    if not isinstance(selection, dict) or set(selection) != {"worktree", "path", "content"}:
        return f"#{number}: plan selection changed; open its preview again"
    cfg = config.load(root, ready._plan_ref(root)[1] or None)
    observed = ready.plan_state(root, item, cfg, selection=selection)
    if not observed["selected"] or observed["selected"]["layer"] != "file":
        return f"#{number}: plan selection changed or is unavailable; open its preview again"
    if observed["validation"]["findings"]:
        return f"#{number}: publication blocked: {observed['why']}"
    log = config.pulse_dir(root) / "go" / f"{number}.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.parent.resolve() != log.parent or log.exists() and not _plan_log(root, number, str(log)):
            return f"#{number}: publication log is unavailable"
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        with open(log, "ab", opener=lambda path, _: os.open(path, flags, 0o600)) as output:
            argv = [sys.executable, str(setup.PULSE_BIN), "publish-plan", str(number)]
            for key in ("worktree", "path", "content"):
                argv += ["--" + key, selection[key]]
            subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=output,
                             stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as error:
        return f"#{number}: plan publication could not start: {error}"
    return f"#{number}: plan publication started; not yet published; log: {log}"


def jump(root: Path, ident: str, env=os.environ) -> str:
    """Focus the Herdr pane that runs session ident now, in any tab or workspace (#181), and the line that says so.
    Presence, read anew, tells an ended or replaced session; Herdr's agent list, read at this moment, names the one
    pane that reports ident as its session, so a moved pane is found under its new id. A subagent without a pane
    of its own leads to its parent session. Only agent list and agent focus: the agent gets no input."""
    if env.get("HERDR_ENV") != "1":
        return "no jump: this map does not run in Herdr"
    found = next(((s, a) for s in presence.read(root) for a in [s, *s["agents"]] if a["id"] == ident), None)
    if not found:
        return "no jump: the session has ended or another session replaced it"
    session, actor = found

    def herdr(*args) -> dict:
        out = subprocess.run([mapstart._herdr_bin(env), *args], stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, timeout=HERDR_WAIT, check=True).stdout
        return json.loads(out)["result"]
    try:
        agents = herdr("agent", "list")["agents"]

        def pane(who):                         # the one pane that reports who as its session, else None
            held = [a.get("pane_id") for a in agents if isinstance(a, dict) and
                    isinstance(a.get("agent_session"), dict) and a["agent_session"].get("value") == who]
            ok = len(held) == 1 and isinstance(held[0], str) and held[0][:1] not in ("", "-")   # never an option
            return held[0] if ok else None
        own = pane(ident)
        target = own or actor["parent"] and pane(actor["parent"])
        if not target:
            return "no jump: Herdr reports no single pane with this session's identity"
        herdr("agent", "focus", target)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return "no jump: Herdr does not answer"
    if own:
        return f"jumped to the Herdr pane of {actor['harness']} {ident[:8]}"
    return f"jumped to the Herdr pane of its parent session {session['harness']} {actor['parent'][:8]}; " \
        f"subagent {ident[:8]} has no pane of its own"


def act(root: Path, vm: dict, action: tuple):
    """Carry out one action from the map; returns a line for the status bar, or a text for the reader (#180).
    An approval writes what brief() showed, and only while the item still waits for it: the gate and blobs
    come with the action (#115)."""
    kind, n = action[0], action[1]
    if kind == "jump":
        return jump(root, n)
    if kind == "auto":
        if not auto.person(os.environ, True):
            return "only a person changes approval policy, in their own terminal or map"
        intended = action[2] if len(action) == 3 else {}
        if intended.get("expected") != auto.read(root)["policy"]["revision"]:
            return "Approval policy changed; review the current settings before confirming."
        return queue_policy(root, intended["enabled"], expected=intended["expected"])
    if kind == "levers":                        # the person's own map grants or revokes (#197 FR-03, FR-09)
        return settings.lever_act(root, action[2])
    if kind == "setting":                       # what brief() showed, against the base fetched anew (#182)
        return settings.change(root, **action[2])
    if kind == "retry-sync":
        ident = action[2] if len(action) == 3 else None
        if not any(entry["id"] == ident and entry["item"] == n and entry["status"] == "error"
                   for entry in actions.pending(root)):
            return "Sync state changed; refresh before retrying."
        return retry_action(root, ident)
    if kind in LOCAL_ACTIONS:
        if not auto.person(os.environ, True):
            return "only a person does this, in their own terminal or map"
        current = next((item for item in vm["items"] if item["number"] == n), None)
        intent = action[2] if len(action) > 2 else None
        if not isinstance(intent, dict) or not {"expected", "payload", "kind", "item"} <= intent.keys():
            return f"#{n}: approval preview changed; open it again"
        if intent["kind"] != kind or intent["item"] != n:
            return f"#{n}: action preview changed; open it again"
        if current is None or current.get("revision") != intent["expected"]:
            return f"#{n} changed since you read it; open its preview again"
        try:
            now = action_preview(root, current, kind)
        except state.StateError as error:
            return ready.printable(str(error))
        if now["payload"] != intent["payload"]:
            return f"#{n} changed since you read it; open its preview again"
        return queue_action(root, intent)
    if kind in DOING and (vm.get("error") or vm.get("rate_limit")):
        raise state.StateError("the board is not current; wait for a successful fresh read before writing")
    if kind == "publish-plan":
        return _publish_plan(root, vm, n, action[2] if len(action) > 2 else None)
    if kind == "read-check-output":
        r = next((r for r in vm.get("refusals") or () if r.get("number") == n and r.get("output")), {})
        log = _plan_log(root, n, r.get("output"), ".hook.txt")
        return _show(log, f"check output #{n}") if log else f"#{n}: the check output is unavailable"
    if kind == "read-plan-error":
        log = _plan_log(root, n, vm.get("plans", {}).get(n, {}).get("error_log"))
        return _show(log, f"plan publication log #{n}") if log else f"#{n}: plan error log is unavailable"
    if kind == "read-log":                      # gate and hook output of the last run (#180)
        log = _plan_log(root, n, str(config.pulse_dir(root) / "go" / f"{n}.log"))
        return _show(log, f"run log #{n}") if log else f"#{n}: its run log is unavailable"
    if kind == "read-report":
        rep = go.last_run(root)
        return _reading("run report", str(config.pulse_dir(root) / "go" / "report.json"), _report_text(rep)) \
            if rep else "no run of pulse go in this clone yet"
    if kind.startswith("read-doc:"):            # the parent spec, a decision of the plan
        return _doc(root, n, kind.partition(":")[2], "document")
    if kind.startswith("read-plan:"):
        entry = next((row for row in _plan_entries(vm.get("plans", {}).get(n, {}))
                      if row[0] == kind.partition(":")[2]), None)
        item = next((item for item in vm["items"] if item["number"] == n), {})
        if not entry or not item:
            return f"#{n}: plan source changed or is unavailable"
        sources = ready.plan_sources(root)
        current = next((source for source in sources.get(n, []) if source["layer"] == entry[1]["layer"] and
                        all(source.get(key) == value for key, value in entry[2].items())), None)
        if not current:
            return f"#{n}: plan source changed or is unavailable"
        if current["layer"] == "file":
            return _show(Path(current["worktree"]) / current["path"], current["path"])
        return _copy(root, "plans", n, current["path"], current["text"], current.get("ref") or "index")
    if kind in lifecycle.ACTIONS:
        planned = action[2]
        apply = remove.apply_action if kind == "delete" else lifecycle.apply
        return apply(root, vm["repo"], planned, planned["confirmation"], run=state.gh)
    if kind == "read-result":
        item = next((item for item in vm["items"] if item["number"] == n), {})
        result = item.get("result") or {}
        if not result:
            return f"#{n} has no published result"
        head, base = result.get("head", ""), result.get("base", "")
        if not all(re.fullmatch(r"[0-9a-f]{40,64}", sha) for sha in (head, base)):
            return f"#{n}: the cached result binding is invalid; refresh the map"
        diff = _git(str(root), "diff", "--no-ext-diff", "--no-textconv", base, head, "--")
        text = f"# Result #{n}\n\nHead: {head}\nBase: {base}\n\n" + \
            "\n".join(f"{gate}: {value}" for gate, value in sorted(result.get("gates", {}).items())) + \
            "\n\n" + "\n".join(_result_notes(item)) + \
            "\n\n```diff\n" + diff + "\n```\n"
        for kind, report in sorted((item.get("reports") or {}).items()):
            if report.get("commit") == head:
                text += f"\n## {kind.capitalize()} report ({report['source']})\n\n{report['text']}\n"
        return _copy(root, "results", n, f"result-{n}.md", text, head)
    if kind == "read-plan":
        plan = ready.plans(root).get(n)
        if not plan:
            return f"#{n} has no plan"
        if not plan["ref"]:
            return _show(Path(plan.get("worktree") or root) / plan["path"], plan["path"])
        return _copy(root, "plans", n, plan["path"], plan["text"], plan["ref"])     # on its branch only
    item = next((i for i in vm["items"] if i["number"] == n), {})
    if not item.get("spec"):
        return f"#{n} has no spec"
    return _doc(root, n, item["spec"], "spec")


def _doc(root: Path, n: int, path: str, what: str):
    """A Markdown file of the repository for the reader (#180): as the base has it, else the branch of origin
    that has it (#68), else the working tree; what names it in a refusal."""
    here = (root / path).resolve()              # from the issue text: it may point anywhere (#56)
    if not here.is_relative_to(root.resolve()):
        return f"#{n}: its {what} path leads out of the repository; nothing opened"
    if not path.endswith(".md") or here.suffix != ".md":    # a link's target too (audit and final check of #68)
        return f"#{n}: its {what} is no Markdown file; nothing opened"
    text, ref = spec.find(root, path)           # what agents plan from, else its branch (#68)
    if text is None:
        try:
            there = here.is_file()
        except OSError as e:                    # a path the system refuses, longer than it takes (#56 L-5)
            return f"#{n}: the system cannot read its {what} path ({e.strerror}); nothing opened"
        return _show(root / path, path) if there else f"#{n}: its {what} {path} is on no branch of origin and not here"
    got = _read(root / path)                    # the reader's own read: no pipe holds the map (#180)
    same = got is not None and got[1] <= READ_MOST and got[0].decode("utf-8", "replace") == text
    return _show(root / path, path) if same else _copy(root, "specs", n, path, text, ref)


def _copy(root: Path, kind: str, n: int, path: str, text: str, ref: str):
    """path as ref has it, for the reader (#180): read from git, written to no file."""
    return _reading(path, f"{path} from {ref}", text)


def _fetch(root: Path) -> None:
    """What every clone planned and holds arrives beside the live map, which never waits for the
    network: ready.fetch in the background, at most every 30 s, with a time limit. pulse status
    fetches first and waits."""
    threading.Thread(target=ready.fetch, args=(root,), daemon=True).start()


def _git(cwd: str, *args) -> str:
    try:
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=2).stdout.strip()     # bytes anyone pushed (#217)
    except (OSError, subprocess.TimeoutExpired):
        return ""


def failures(root: Path, items=()) -> dict:
    """{item: why} for what the last run of pulse go failed, from its report (D-14). A claim or a
    sign of life on the item since then is newer work, whoever holds it: the map shows that one. A failure this
    clone keeps until the board has it says so first, where no cut takes it (FR-03 of #209)."""
    since = {i["number"]: max(i.get("claimed_at") or "", i.get("claimed_beat") or "") for i in items}
    try:
        report = json.loads((config.pulse_dir(root) / "go" / "report.json").read_text(encoding="utf-8"))
        kept = go.unsent(root)
        return {int(n): (f"{go.UNSENT}: " if int(n) in kept else "") + (r.get("why") or "failed")
                for n, r in report["items"].items()
                if r.get("result") == "failed" and since.get(int(n), "") <= (r.get("at") or "")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


_merged: dict = {}                      # root -> (read at, the items of the merged PRs)
_limited: dict = {}


def _phase_since(root: Path, phases: dict) -> dict:
    """{item: when its job's phase began}: the time the runner wrote its phase file."""
    since = {}
    for n in phases:
        try:
            since[n] = (config.pulse_dir(root) / "go" / f"{n}.phase").stat().st_mtime
        except (OSError, state.StateError):
            pass
    return since


def merged(root: Path, repo: str, items: list) -> set:
    """Only confirmed canonical integration removes work from the live board."""
    return {item["number"] for item in items if item.get("done")}


_closed: dict = {}                      # root -> (read at, {epic: its closed children}, {closed issue: its title})


def closed(root: Path, repo: str, items: list, titles: bool = False) -> dict:
    """{epic: how many of its children are closed as completed} for the open epics (WP-60); one
    closed as not planned leaves the count (N5.01). Read at most every state.TTL s, and only while
    an epic is open or, with titles, DONE needs a title (#217)."""
    epics = {i["number"] for i in items if i["type"] == "epic"}
    at, done, named = _closed.get(root, (0.0, {}, {}))
    if (epics or titles) and repo and time.time() - at >= state.TTL:
        try:                            # ponytail: the last 1000 closed issues; a long epic's oldest may drop out
            rows = state.issues(repo, state.gh, "closed", "number,title,parent,stateReason")
            done = Counter((i.get("parent") or {}).get("number") for i in rows if i.get("stateReason") == "COMPLETED")
            named = {i["number"]: i.get("title") or "" for i in rows}
        except state.RateLimitError as error:
            _limited[root] = error
            return {epic: done[epic] for epic in epics if done.get(epic)}
        except (state.StateError, ValueError):
            pass                        # offline: the last answer stands
        _closed[root] = (time.time(), done, named)
    return {e: done[e] for e in epics if done.get(e)}


def closed_titles(root: Path) -> dict:
    """{issue: its title} of the closed issues closed() read last."""
    return _closed.get(root, (0.0, {}, {}))[2]


def integrated(root: Path, base: str, titles: dict) -> list:
    """DONE (#217): what Pulse integrated into the fetched base in the last DONE_DAYS days, newest first, from its
    merge commits "Merge item #n" (merge.integrate): who is the author git records for the merge, the name of the
    person whose clone integrated it; at is its commit time. Local git only; the map never waits for the network."""
    out, seen = [], set()
    log = _git(str(root), "log", "--merges", f"--since={DONE_DAYS}.days.ago",
               "--format=%H%x1f%ct%x1f%cI%x1f%an%x1f%s", config.base_ref(root, base), "--")
    for line in log.split("\n"):              # never splitlines: git leaves \x0b, \x1c, U+2028 in a subject
        merge, stamp, at, who, subject = (line.split("\x1f") + ["", "", "", ""])[:5]
        m = re.fullmatch(r"Merge item #([1-9][0-9]{0,9})", subject)        # an issue number, never a huge int
        if m and int(m.group(1)) not in seen:
            seen.add(int(m.group(1)))
            out.append({"number": int(m.group(1)), "title": titles.get(int(m.group(1)), ""), "who": clean(who),
                        "at": at, "merge": merge, "stamp": int(stamp) if stamp.isdigit() else 0})
    return sorted(out, key=lambda row: row["stamp"], reverse=True)      # the moment, whatever its time zone


def _cache_notice(root: Path) -> str:
    snapshot = state.stored(root)
    if snapshot is None:
        return "no cached state"
    try:
        fetched = float(snapshot.get("fetched_at", "nan"))
    except (ValueError, TypeError):
        fetched = math.nan
    age = _age(fetched) if math.isfinite(fetched) and 0 <= fetched <= time.time() else "unknown"
    return f"showing last known state, cache age {age}"


def local(root: Path, vm: dict):
    """Local activity stays fresh while the board reader waits for the network."""
    vm["goal"] = goals.read(root)
    vm["goal_report"] = go.last_run(root) if vm["goal"] else None
    entries = actions.pending(root)
    vm["actions"] = entries
    vm["auto"] = auto.read(root)
    vm["approval_policy"] = vm["auto"]["policy"]["mode"]
    holds = {}
    for entry in entries:
        if entry["kind"] == "defer":
            holds[entry["item"]] = True
        elif entry["kind"] == "resume" and entry["status"] == "confirmed":
            holds[entry["item"]] = False
    for item in vm.get("items", []):
        if item["number"] not in holds and "local_hold" not in item:
            continue
        item.setdefault("_shared_hold", bool(item.get("hold")))
        item["local_hold"] = bool(holds.get(item["number"]))
        item["hold"] = item["_shared_hold"] or item["local_hold"]
    ramp = vm.get("ramp", {})
    for row in ramp.get("rows", []):
        if holds.get(row["number"]):
            row.setdefault("_stage_before_local_hold", row.get("stage", ""))
            row["stage"] = "on hold locally"
        elif "_stage_before_local_hold" in row:
            row["stage"] = row.pop("_stage_before_local_hold")
    for key in ("next", "queued"):
        if key in ramp:
            ramp[key] = [row for row in ramp[key] if not holds.get(row["number"] if isinstance(row, dict) else row)]
    now = time.monotonic()
    if now - vm.get("_presence_at", -math.inf) < 1:
        return
    vm["_presence_at"] = now
    vm["sessions"] = presence.read(root)
    vm["branches"] = {a["cwd"]: a.get("branch", "") for s in vm["sessions"] for a in [s, *s["agents"]]}
    vm["runner"] = go.activity(root)


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
        items = state.cached(root) or []
        error = f"offline, showing the last known state ({e})" if items else str(e)
    annotated = next((record for record in items if "order_revision" in record), {})
    order_info = {"issue": annotated.get("order_issue"), "revision": annotated.get("order_revision"),
                  "positions": {record["number"]: record["manual_position"] for record in items
                                if record.get("manual_position") is not None},
                  "why": annotated.get("order_conflict", "")}
    try:
        cached = state.stored(root) or {}
        if (cached.get("repo") == repo and cached.get("format") == state.FORMAT and
                cached.get("items") == items and isinstance(cached.get("order"), dict)):
            order_info = cached["order"]
    except (OSError, ValueError, AttributeError):
        pass
    done = merged(root, repo, items) if board else set()      # off the map at once, done for its epic (#57)
    finished = Counter(i["parent"] for i in items if i["number"] in done and i.get("parent"))
    titles = {i["number"]: i.get("title") or "" for i in items}      # before the done ones leave, for DONE (#217)
    items = [i for i in items if i["number"] not in done]
    items = ready.current(root, items)      # a result for an old head goes back to the build (#191)
    phases = go.phases(root)
    base = cfg["base_branch"] or config.default_branch(root)
    report = go.last_run(root) or {}
    sources = ready.plan_sources(root)
    found = ready.plans(root, sources=sources)
    trusted = config.load(root, ready._plan_ref(root)[1] or None)
    plans = {item["number"]: _plan_observed(root, item, trusted, sources, report)
             for item in items if item["type"] in state.WORK}
    gates = ready.gates(root, [dict(item, assignees=[]) for item in items], trusted, found, sources)
    for item in items:
        prior = report.get("items", {}).get(str(item["number"]), {})
        if (item.get("result") and not item.get("approval") and prior.get("phase") == "integration"
                and prior.get("revision") == item.get("revision") and prior.get("why")):
            item["integration_wait"] = prior["why"]
            gates[item["number"]] = "integration: " + prior["why"]
        else:
            item.pop("integration_wait", None)
        failure = plans.get(item["number"], {}).get("failure") or {}
        if failure and not failure.get("stale") and not plans[item["number"]]["conflict"] and _publishable(item):
            gates[item["number"]] = f"plan {failure.get('step', 'publication')} blocked: {failure.get('cause', '')}"
    vm = {"repo": repo, "now": time.strftime("%H:%M:%S"), "base": base,
            "person": state.who(root, me) or "you", "me": me,      # Klarname (@login), as every surface (#111)
            "items": items, "sessions": [], "error": error, "order": order_info,
            "phases": phases, "failed": failures(root, items),
            "phase_since": _phase_since(root, phases),       # when each job's phase began (#215 FR-01)
            "tasks": plan_tasks(root, items, phases, me, base, found),     # Plan k/n of my jobs (#216)
            "halt": go.halt(root),              # what holds the whole run (#113, #178)
            "halt_kind": go.halt_kind(report), "compatibility": report.get("compatibility") or {},
            "refusals": go.refusals(root, items),       # a hook's refusals, current or earlier (#178)
            "runner": go.activity(root),        # live preparations too, before a claim or an agent exists (#149)
            "base_status": report.get("base") or {}, "plans": plans, "run": report.get("run"),
            "closed": dict(Counter(closed(root, repo, items) if board else {}) + finished),
            "nowhere": [], "unready": [],
            "branches": {},
            "untrusted": setup.untrusted(cfg["agent"]),       # the lever guard does not run in Codex yet (#111)
            "ramp": ready.ramp(items, ready.plan_files(root, found), cfg["cap"], me, gates=gates)}
    vm["done"] = None          # DONE (#217) only where the board was read; pulse status leaves it out
    if board:                  # a missing title comes from the closed issues closed() reads
        vm["done"] = integrated(root, base, {**closed_titles(root), **titles})
        if any(not row["title"] for row in vm["done"]):
            closed(root, repo, [], titles=True)
            vm["done"] = [{**row, "title": row["title"] or closed_titles(root).get(row["number"], "")}
                          for row in vm["done"]]
    vm["off"] = config.off(root)          # which switch keeps Pulse off, and the way back (#231)
    vm["auto_why"] = ""
    local(root, vm)
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
    [("agent", "s17", 17, "opus", "working", "Edit", "docs/auth.md", ""), ("phase", 17, "fix"), ("result", 14),
     ("gone", "s14")],
    [("agent", "s19", 19, "sonnet", "working", "Edit", "src/auth/expiry.ts", ""),
     ("claim", 20, "Sebastian"), ("agent", "s20", 20, "opus", "working", "Read", "src/api/cursor.ts", ""),
     ("result", 16, "fail"), ("phase", 11, "review")],
    [("result", 11), ("gone", "s11"), ("claim", 24, "Bob")],
    [("merge", 11), ("result", 12, "pass", ["Sebastian"]), ("claim", 21, "Sebastian"),
     ("agent", "s21", 21, "opus", "working", "Edit", "src/ui/Empty.tsx", "")],
    [("result", 17), ("gone", "s17"), ("agent", "s20", 20, "opus", "working", "Bash", "npm test", ""),
     ("result", 16, "pass")],
    [("merge", 12), ("merge", 14), ("claim", 22, "Alice"), ("claim", 13, "Sebastian"),
     ("agent", "s13", 13, "opus", "working", "Edit", "src/ui/Banner.tsx", "")],
]


def demo(step: int = 0) -> dict:
    """A plausible morning at a sample project, step by step of SCRIPT."""
    items = {n: {"number": n, "title": title, "type": kind, "approved": ok, "assignees": [],
                 "parent": None if kind == "epic" else 10, "blocked_by": list(blocked), "blocking": [],
                 "spec": None, "result": None}
             for n, title, kind, ok, blocked, _ in DEMO_ITEMS}
    items[11]["blocking"] = [13]
    files = {n: f for n, *_, f in DEMO_ITEMS if f}
    branch = {n: go.item_branch(i["type"], n, i["title"]) for n, i in items.items()}   # as pulse go names them
    agents, phases, closed, t = {}, {}, {10: 0}, time.time()
    for change in (c for batch in SCRIPT[:step + 1] for c in batch):
        op, *a = change
        if op == "claim":
            items[a[0]]["assignees"] = [a[1]]
        elif op == "result":
            item = items[a[0]]
            item["result"] = {"branch": branch[a[0]], "head": "a" * 40, "base": "b" * 40,
                              "gates": {"tests": a[1] if len(a) > 1 else "pass", "review": "pass", "audit": "pass"}}
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
                                                   if s["cwd"] != "/repo"} if not items[n]["result"]}
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
    saved, on, answer = termios.tcgetattr(fd), [], [""]     # answer: a terminal's answer read so far (#166)
    tty.setcbreak(fd)

    def byte() -> str:
        return os.read(fd, 1).decode(errors="ignore") if select.select([sys.stdin], [], [], 0.05)[0] else ""

    def read(wait: float):
        if not select.select([sys.stdin], [], [], wait)[0]:
            answer[0] = ""                         # an answer that pauses a whole wait ends there
            return None
        ch = os.read(fd, 1).decode(errors="ignore")
        if ch == "\x1b" and not answer[0] and select.select([sys.stdin], [], [], 0.01)[0]:
            ch += os.read(fd, 2).decode(errors="ignore")
            if ch in ("\x1b[1", "\x1b[4", "\x1b[5", "\x1b[6", "\x1b[7", "\x1b[8") and \
                    select.select([sys.stdin], [], [], 0.01)[0]:      # PgUp, PgDn, and Home and End (#214)
                ch += os.read(fd, 1).decode(errors="ignore")
            if ch == "\x1b[M":                     # an X10 report: its three bytes are no keys (#180)
                ch += byte() + byte() + byte()
            while ch.startswith("\x1b[<") and len(ch) < 16 and not ch.endswith(("M", "m")):
                more = byte()                         # an SGR report, one key up to its M or m
                if not more:
                    break
                ch += more
        if answer[0] or ch.startswith("\x1b_"):    # a terminal's answer (APC) up to its ESC \ comes whole, also
            answer[0] += ch                         # in pieces (#166); main() hands none to key()
            while not answer[0].endswith("\x1b\\") and len(answer[0]) < 4096:
                more = byte()
                if not more:
                    return None                    # its rest comes with the next read
                answer[0] += more
            ch, answer[0] = answer[0], ""
        return ch

    def mouse():
        """Clicks and the wheel as reports (#180), until restore()."""
        sys.stdout.write(MOUSE_ON)
        sys.stdout.flush()
        on.append(True)

    def restore():
        if on:
            on.clear()
            try:
                sys.stdout.write(MOUSE_OFF)
                sys.stdout.flush()
            except (OSError, ValueError):
                pass                   # the terminal is gone (SIGHUP)
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            termios.tcflush(fd, termios.TCIFLUSH)   # a late answer of the terminal never reaches the shell (#166)
        except termios.error:
            pass                       # the terminal is gone (SIGHUP)

    def drop():
        """Forget what was typed meanwhile: keys pressed during a write act on no board (#55)."""
        answer[0] = ""
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
        except termios.error:
            pass

    read.restore, read.drop, read.mouse = restore, drop, mouse
    return read


def _windows_keys():
    """The keys of a Windows terminal through msvcrt, which has no termios (#121 FR-09): an arrow comes as two
    characters, and the map gets it as any other terminal sends it."""
    import msvcrt
    arrows = {"H": UP[0], "P": DOWN[0], "K": "\x1b[D", "M": RIGHT[0], "I": PAGE[0], "Q": PAGE[1], "G": HOME[0],
              "O": END[0]}

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


def folds(root: Path, titles=None) -> set:
    """The titles of the sections folded in this clone's live map, with titles written first (#214): in the clone's
    git dir, never shared. A write that fails keeps them for this map only."""
    try:
        path = config.pulse_dir(root) / FOLDS
        if titles is None:          # an agent may write the git dir: through no link, never waiting on a pipe (H-1)
            read = _read(path)
            text = read[0].decode("utf-8", errors="replace") if read else ""
            return {line for line in text.splitlines()[:50] if line.strip()}
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{FOLDS}-", dir=path.parent)       # a name nobody can plant
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:      # sections first: a read keeps 50 lines (#234)
                out.write("".join(f"{title}\n" for title in sorted(titles, key=lambda t: (t.endswith(" sessions"), t))))
            os.replace(name, path)                                               # replaces a link, never follows it
        finally:
            Path(name).unlink(missing_ok=True)
    except (OSError, ValueError, state.StateError):
        pass
    return set() if titles is None else set(titles)


def pruned(vm: dict, titles) -> set:
    """The folds worth keeping: every section's, and the unfolded sessions of an open item or a branch on the map
    now (#234); those of closed items go. Without a view model all stay."""
    if not vm:
        return set(titles)
    here = {f"#{i['number']} sessions" for i in vm.get("items", ())} | {f"{k} sessions" for k in places(vm)
                                                                      if isinstance(k, str)}
    return {t for t in titles if not t.endswith(" sessions") or t in here}


def fitted(lines: list, height: int, keep: int, offset: int = None, kept: list = None, top: int = HEAD) -> list:
    """At most height lines, so a frame taller than the terminal never scrolls it: the header (the
    first top lines, #57) and the last keep lines (status and keys) stay, the rest is cut around
    the picked row, the one that starts with › (a title may hold one too, #56), and one line says
    how much is hidden. A terminal too low for all of it gives header lines up first. kept gets, per
    row returned, its index in lines, None for the line that counts what is hidden (#180)."""
    kept = [] if kept is None else kept
    if len(lines) <= height:
        kept[:] = range(len(lines))
        return lines
    head = lines[:min(top, max(0, height - keep - 2))]
    body, foot = lines[len(head):len(lines) - keep], lines[len(lines) - keep:]
    room = max(1, height - len(head) - len(foot) - 1)
    if offset is None:
        at = next((i for i, line in enumerate(body) if ANSI.sub("", line).lstrip().startswith("›")), 0)
    start = max(0, min(at - room // 2 if offset is None else offset, len(body) - room))
    shown = body[start:start + room]
    kept[:] = [*range(len(head)), *range(len(head) + start, len(head) + start + len(shown)), None,
               *range(len(lines) - len(foot), len(lines))]
    where = f"  lines {start + 1} to {start + len(shown)} of {len(body)}; PgUp/PgDn scroll" if offset is not None \
        else f"  … {len(body) - room} more lines; a taller terminal shows them"       # where it stands (#214)
    return head + shown + [where] + foot


def shows(text: list, width: int, height: int) -> bool:
    """Whether a confirmation shows whole, so Enter binds nothing the person did not see (#76, #56 audit
    M-1): fitted keeps a row of the map and the row that counts what it hides beside the footer (the
    text, the line over the keys, the keys), and a terminal narrower than the map wraps every row. The footer counts every
    character that is not ASCII as two columns: a text the terminal draws wider than the map counts it
    can make the map refuse, never hide a line (final check M-2)."""
    return len(footer("\n".join(text), KEYS["confirm"], width)) + 3 <= height and \
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
    unread = ""                                      # why the last read failed, over the keys until one succeeds
    offered = {}                                     # item -> what its view offered on the last frame
    approved = {}                                    # item -> its approvals, once read beside the keys (L-3)
    detached = None
    help_pages = {}                            # built once per width, never on an animation frame
    folded = folds(root)                       # the sections this clone keeps folded (#214)
    followed = None                            # the pick the map's window last followed (#214 FR-04)
    # what the read brings, the writes so far, the last look for a newer copy and for a newer release
    box = {"writes": 0, "looked": time.time(), "asked": -math.inf}
    drawn, drawn_at = [], None                       # the rows on the screen, and the size they were drawn at
    read = keys = _keys()
    # the image logo (#166): where the terminal answers its question; never on Windows, in GNU screen (STY) or in tmux
    # (TMUX), which pass no graphics command on and show one as their status line or pane title, nor in a Herdr pane,
    # which confirms the question and then prints each placement as text (#212)
    png = (logo_png() if color and keys and sys.platform != "win32" and not {"STY", "TMUX"} & set(os.environ)
           and os.environ.get("HERDR_ENV") != "1" else None)
    graphic = asked = sent = placed = False         # confirmed; question written; data and place on the screen
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
                if newer and not os.access(newer, os.X_OK):    # this map runs on and says so once (#192 FR-04)
                    if box.get("refused") != newer:
                        update = "\n".join(filter(None, [update, f"! the switch to the newer Pulse failed: {newer} "
                                                                  "is not executable; this map runs on"]))
                    box["refused"], newer = newer, ""
            box["new"] = (writes, board_, update, newer)
        except Exception as e:                         # the loop names it and reads again (#192 FR-01)
            box["new"] = e

    def draw(*args, **kw):
        """render(), or one line that names why it could not: a frame never ends the map (#192 FR-01)."""
        try:
            return render(*args, **kw)
        except Exception as e:
            return [ready.printable(f"! this view could not be drawn: {type(e).__name__}: {e}")]
    try:
        sys.stdout.write("\033[?1049h\033[?25l")     # the alternate screen: the shell comes back as it was
        getattr(keys, "mouse", lambda: None)()       # clicks and the wheel; restore() switches them off (#180)
        while True:
            fresh = False
            while True:                                # take what the last read brought, start the next
                if reading and not reading.is_alive():
                    new, reading = box.pop("new"), None
                    if isinstance(new, Exception):     # the last board stays; the next read after REFRESH (#192)
                        unread = ready.printable(f"! the board could not be read: {type(new).__name__}: {new}; "
                                                 "the map reads again")
                        if vm is None:                 # no board yet: the reason alone until a read brings one
                            sys.stdout.write("\033[H\033[2J" + "\n".join(wrap(unread, columns())))
                            sys.stdout.flush()
                            drawn_at = None
                            if (read(REFRESH) if read else time.sleep(REFRESH)) == "q":
                                return 0
                        continue
                    writes, board_, update, restart = new
                    unread = ""
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
            local(root, vm)
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
            marks = {}                                 # row of lines -> what a click there does (#180)
            if level == "map":
                box.pop("settings", None)              # the settings are read anew each time they open (#182)
            if level == "settings" or level in ("value", "confirm") and ui.get("from") == "settings":
                if "settings" not in box:              # beside the keys: git, and the hook measures the rules

                    def settings_of(vm=vm):
                        try:
                            box["settings"] = settings.read(root, vm["repo"])
                        except Exception as error:     # the view says so; the map goes on
                            box["settings"] = {"rows": [], "offers": [],
                                               "rules": [f"The settings could not be read: {error}"]}
                    box["settings"] = None
                    _beside(settings_of)
                shown_settings = box["settings"] or {"reading": True, "offers": []}
                acts = [a for a, *_ in shown_settings["offers"]]
                lines = draw(vm, frame=frame, color=color, width=width, marks=marks,
                               settings={**shown_settings, "pick": ui.get("pick", 0)})
            elif level == "item" or level == "confirm" and ui.get("from") != "map":   # a on the map asks over the map
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
                    ui = {**ui, "pick": next((k for k, a in enumerate(acts) if a.partition(":")[0] in READS), 0)}
                elif acts != was and k < len(was):     # offered. The list shifted: the cursor keeps its action, or
                    ui = {**ui, "pick": acts.index(was[k]) if was[k] in acts else 0}   # goes to the top,
                                                           # which never writes without asking first (#55)
                offered = {n: acts}
                lines = draw(view, frame=frame, color=color, width=width, marks=marks,
                               item=dict(seen, pick=ui.get("pick", 0), approvals=approved.get(n, READING)))
            elif level == "help":                      # under the header, as every screen (#57)
                if width not in help_pages:
                    help_pages[width] = help_lines(width)
                lines = draw(vm, frame=frame, color=color, width=width)[:HEAD] + [BACK_ROW] + help_pages[width]
                marks = {HEAD: ("back",)}
            elif level == "read":                      # the reader, under the header as the help (#180)
                if ui.get("width") != width:           # its rows, wrapped once per width
                    rows = [Paint(color)(row, "1") for row in wrap(ui["title"], width)] + \
                        wrap("source: " + ui["source"], width) + (wrap("cut: " + ui["cut"], width) if ui["cut"] else [])
                    ui = {**ui, "width": width, "rows": rows + [""] + [row for line in ui["text"]
                                                                      for row in (wrap(line, width) or [""])]}
                lines = draw(vm, frame=frame, color=color, width=width)[:HEAD] + [BACK_ROW] + ui["rows"]
                marks = {HEAD: ("back",)}
            elif level == "move":
                shown = []
                lines = draw(ui["vm"], frame=frame, color=color, width=width, selected=n, picks=shown,
                               marks=marks)            # the rows of the live map, run report too (#180)
            else:
                shown = []
                lines = draw(vm, frame=frame, color=color, width=width, selected=n, picks=shown, marks=marks,
                             folded=folded)
            notice = status or unread or \
                (vm.get("error", "") if vm.get("rate_limit") else (vm.get("order") or {}).get("why", ""))
            if level == "number":
                notice = "Issue number: " + ui.get("typed", "")
            elif level == "value":
                notice = "Slots: " + ui.get("typed", "")
            elif level == "confirm" and "expected" in ui:
                notice = status + "\n> " + ui.get("typed", "")
            # the status, a line over the keys on every level (#180), the keys
            legend = KEYS[level] if level != "map" or not isinstance(n, tuple) else \
                FOLD_KEYS if n[0] == "section" else JUMP_KEYS        # a heading (#214), a session row (#181)
            foot = footer(notice, "", width) + [Paint(color)("─" * width, "90")] + footer("", legend, width) \
                if read else []
            top = HEAD + 1 if level in ("help", "read") else HEAD      # the back row stays with the header
            if level in ("map", "item", "help", "read", "settings"):
                kept = min(top, max(0, height - len(foot) - 2))
                ui["page"] = max(1, height - kept - len(foot) - 1)
                if level == "map" and (n != followed or "scroll" not in ui):   # a new pick: in sight (#214)
                    want, followed = ("item", n) if isinstance(n, int) else n, n
                    row = min((r for r, target in marks.items() if target == want), default=None)
                    scroll = ui.get("scroll", 0)
                    if row is not None and row >= kept:          # just far enough, never past it
                        scroll = min(max(scroll, row - kept - ui["page"] + 1), row - kept)
                    ui["scroll"] = scroll
                if "scroll" in ui or level not in ("item", "settings"):
                    ui["scroll"] = min(ui.get("scroll", 0), max(0, len(lines) - kept - ui["page"]))
            where = []                                 # screen row -> row of lines, for a click
            cells = [fit(l, width) for l in fitted(lines + foot, height, len(foot),
                                                  ui.get("scroll") if level in ("map", "item", "help", "read",
                                                                                "settings") else None,
                                                  kept=where, top=top)]
            mark = [fit(row, INSET) for row in signet(color)]
            whole = len(lines) + len(foot) <= height or height - len(foot) - 2 >= HEAD    # fitted() cut no header row
            logo = graphic and whole and all(c.startswith(m) for c, m in zip(cells, mark))
            if logo:                                   # the image in place of the text logo, only over all of it
                cells[:len(mark)] = [" " * INSET + c[len(m):] for c, m in zip(cells, mark)]
            clear = (width, height) != drawn_at      # new or resized: cleared, then every row once (#98)
            if clear:
                drawn, sent = [], False                # a cleared screen may have dropped the image's data
            # each row at its own place, so a row the terminal draws wider moves none below it (#98); the rows that
            # changed, and those of an open confirmation on every frame, after the map's: a row of the map written
            # again, wider than the map counts, cannot cover what Enter confirms (#56 M-3)
            bound = len(cells) - len(foot) if level == "confirm" else len(cells)
            written = [i for i, c in enumerate(cells) if i >= len(drawn) or drawn[i] != c or i >= bound]
            out = "\033[H\033[2J" * clear + "".join(f"\033[{i + 1};1H\033[K{cells[i]}" for i in written)
            out += f"\033[{len(cells) + 1};1H\033[J" if len(cells) < len(drawn) else ""
            if logo and (not placed or written and written[0] < len(mark)):    # a row under it written: put it back
                out, sent = out + picture(png, not sent), True
            elif placed and not logo:
                out += LOGO_OFF
            placed = logo
            if png and not asked:                      # its answer comes as a key; the first drop() is past
                out, asked = out + GRAPHICS_ASK, True
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
                    if wrote and todo[0] not in LOCAL_WRITES:
                        if reading:
                            reading.join()
                            new, reading = box.pop("new"), None
                            if isinstance(new, Exception):
                                raise state.StateError(f"the board could not be refreshed: {new}")
                            writes, board_, update, restart = new
                            waiting = "\n".join(filter(None, [waiting, update]))
                            if writes != box["writes"]:
                                raise state.StateError("the board changed while confirming; inspect it again")
                            vm = board_
                        view = vm = gather(root, fresh=True)
                    said = act(root, view, todo)
                    if isinstance(said, dict):          # a text to read: the reader opens over this view (#180)
                        ui, said = {"level": "read", "at": ui.get("at"), **said, "scroll": 0, "back": ui}, ""
                    status = said
                except (state.StateError, ValueError) as e:
                    status = f"! {e}"
                if todo[0] == "jump":                  # keys typed while Herdr answered start no second jump
                    getattr(read, "drop", lambda: None)()
                if wrote:
                    box["writes"] += 1
                    if detached:
                        ui, detached = {"level": "map", "at": n}, None
                    if todo[0] in LOCAL_WRITES:
                        local(root, vm)
                        seen = None
                        box.pop("settings", None)      # the settings view shows what the write left
                    else:
                        vm = None
                todo = None
                continue
            ch = read(TICK) if read else time.sleep(TICK)
            if ch and ch.startswith("\x1b_"):         # a terminal's answer is no key (#166)
                graphic = graphic or bool(png) and ch == GRAPHICS_OK
                continue
            if ui["level"] == "move" and tuple(terminal_size()) != ui["size"]:
                ui, status, ch = {"level": "map", "at": ui["at"]}, "move cancelled: terminal resized", None
            if ch in ENTER and ui["level"] == "confirm" and tuple(terminal_size()) != ui["size"]:
                ch = None                              # resized since it was drawn: the next frame decides (#98)
            if ch == "q" and level == "map":
                return 0
            if ch in ENTER and "opened" in ui and time.monotonic() - ui["opened"] < SOON:
                ui, ch = key(ui, shown, BACK[0])[0], None   # typed unread: it closes
                status = "nothing done: enter came within a second of opening it; open it again, read, then enter"
            if ch and ch.startswith(("\x1b[<", "\x1b[M")):    # a mouse report acts through pointer() only (#180)
                event = mouse(ch)
                target = marks.get(where[event[2] - 1]) if event and 0 < event[2] <= len(where) else None
                new, action = pointer(ui, shown, event, target, acts) if event else (ui, None)
                if new is ui and not action:           # a release, a click on no target: the status stays
                    continue
            elif ch:
                new, action = key(ui, shown, ch, acts)
            if ch:
                ui = new
                if level not in ("confirm", "move") or ui["level"] != level:
                    status = ""
                if action and action[0] == "say":
                    status, action = action[1], None
                if action and action[0] == "fold":     # at once, and kept for this clone (#214)
                    folded, action = folds(root, pruned(vm, folded ^ {action[1]})), None
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
                if action and action[0].startswith("redo:"):    # a conflict: the item read anew, then asked again (#215)
                    try:
                        view = vm = gather(root, fresh=True)
                        local(root, vm)
                        action = redo(vm, *action)
                    except (state.StateError, ValueError) as error:
                        status, action = f"! {error}", None
                    if action is None and not status:
                        status = "the action changed meanwhile; open the item again"
                if action and level in ("map", "item", "settings", "value") and (action[0].startswith(
                        ("publish-plan:", "retry-sync:", "setting:", "levers:")) or action[0] in (*LOCAL_ACTIONS, "auto", *lifecycle.ACTIONS)):
                    try:
                        text, sure = brief(root, view, action)
                    except (state.StateError, ValueError) as error:
                        text, sure = [str(error)], None
                    expected = sure[2]["confirmation"] if sure and sure[0] in lifecycle.ACTIONS and sure[0] not in LOCAL_ACTIONS else ""
                    if expected:
                        text = [*text, "Type " + expected + " to confirm."]
                    status, action = "\n".join(text), None
                    if sure and not shows([*text, *( ["> " + expected] if expected else [])], width, height):
                        status = SMALL
                    elif sure:
                        ui = {"level": "confirm", "at": n, "sure": sure, "pick": ui.get("pick", 0), "from": ui["level"],
                              "size": size}
                        if expected:
                            ui.update(expected=expected, typed="")
                if action:                             # the next frame says what runs, then it runs
                    status, todo = "asking Herdr for its pane…" if action[0] == "jump" else \
                        DOING.get(action[0], "opening it…").format(action[1]), action
    except KeyboardInterrupt:
        return 0
    finally:
        for s, h in handlers.items():
            signal.signal(s, h)
        try:                                   # after SIGHUP the terminal may be gone
            if keys:
                keys.restore()
            sys.stdout.write(LOGO_GONE * graphic + "\033[?25h\033[?1049l")
            sys.stdout.flush()
        except OSError:
            pass
    if restart:                                # the same terminal, the newer Pulse (IMP-14)
        try:
            os.execv(restart, [restart, "map"])
        except OSError as e:                   # the terminal is the shell's again: the reason stays in the pane
            print(f"pulse map: the switch to the newer Pulse failed: {e}")
            return 1
    return 0
