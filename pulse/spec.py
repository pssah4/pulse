"""Spec files: readiness (R1 to R6), frontmatter edits, parent links, the Items list.

Readiness asks one thing: can an agent write a complete PLAN from this spec
alone? The rules read text only; the caller decides which version of the
file counts (the base branch, which every worktree starts from).

The tree epic > feature > fix or improvement lives in the repository too:
every spec names its `parent:` as a relative path, and the epic lists its
items under `## Items`. link_problems() compares both directions locally.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from pulse import config

SECTIONS = {"feat": ("Feature description", "Scope", "Requirements", "Success criteria", "Activation Path"),
            "imp": ("Description", "Reason", "Scope", "Requirements", "Success criteria"),
            "fix": ("Symptom", "Root cause", "Expected behavior", "Unchanged behavior")}
LATE = {"fix", "regression test", "change log"}             # filled when the work lands
QUESTION = r"\[(?:CLARIFY|KLÄREN|AWAITING BA)\b"          # it ends at "]" or, left open, at the next one: linear
HOLE = re.compile(r"\{[^{}\n]+\}|" + QUESTION + r"(?:(?!" + QUESTION + r")[^\]])*\]|\bTODO\b|\?\?\?")
COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)      # an unclosed comment runs to the end: linear, as in HTML
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
REQ = re.compile(r"^[^\S\n]*[-*]\s*(?:\*\*|`)?(FR-\d+)\b(.*)$", re.M)  # [^\S\n]: one start per line, not per blank line
MODAL = re.compile(r"\b(SHALL|MUST|SOLL|MUSS)\b")
PRIORITY = ("P0", "P1", "P2")
EFFORT = ("XS", "S", "M", "L")                              # XL: split it first
# an open entry ends at the next item
ITEM = re.compile(r"^( *)- \[#(\d+)(?!\d)(?:(?!\n *- \[#)[^\]])*\]\(([^)\s]+)\)", re.M)
TERMS = Path(__file__).resolve().parents[1] / "skills" / "pulse-re" / "references" / "tech-agnostic-rules.md"
REQUIREMENTS = "_devprocess/requirements"


def on_base(root: Path, path: str, ref: str = None):
    """The file as the base branch has it, or None."""
    out = subprocess.run(["git", "-C", str(root), "show", f"{ref or config.base_ref(root)}:{path}"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return out.stdout if out.returncode == 0 else None


def split(text: str) -> tuple:
    """(frontmatter lines, body) of a spec; no frontmatter gives ([], text)."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    return (m.group(1).splitlines(), text[m.end():]) if m else ([], text)


def front(text: str) -> dict:
    out = {}
    for line in split(text)[0]:
        m = re.match(r"^([\w-]+):\s*(.*?)(?:\s#.*)?$", line)      # no \s* behind (.*?): linear on spaces
        if not m:
            continue
        value = m.group(2).rstrip()
        if value.lower() in ("", "~", "null"):                    # YAML's null: no value
            continue
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        out[m.group(1).lower()] = value
    return out


def sections(text: str) -> dict:
    """{heading in lower case: content} for every `## ` heading, comments removed."""
    body = COMMENT.sub("", split(text)[1])
    parts = re.split(r"^## +(.*\S|.)\s*$", body, flags=re.M)      # .*\S, not .+?: linear on spaces
    return {parts[k].strip().lower(): parts[k + 1] for k in range(1, len(parts) - 1, 2)}


def _rows(content: str) -> list:
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in content.splitlines()
            if l.strip().startswith("|")]
    return [r for r in rows[1:] if not set("".join(r)) <= set("-: ")]


def _terms() -> list:
    """The forbidden terms: every line under a `## ` heading, up to the transformation guide."""
    try:
        text = TERMS.read_text(encoding="utf-8").split("## Transformation Guide")[0]
    except OSError:
        return []
    listed = text.split("\n## ", 1)[-1].split("\n", 1)[-1]
    return [t.strip() for l in listed.splitlines() if l.strip() and not l.startswith("## ")
            for t in l.split(",") if t.strip()]


def refusal(text, kind: str, number, base: str) -> str:
    """Why pulse approve and the map's key a refuse #number, or "": its spec is not on the base
    branch (R1, D-43), or for a work item it breaks R2 to R6 there, which pulse check would hold
    against every commit. An epic needs R1 only."""
    wrong = [f for f in findings(text, kind, number) if f.startswith("R1 ") or kind in SECTIONS]
    if not wrong:
        return ""
    return f"{'; '.join(wrong)} ({base}); " + ("merge its spec there first" if text is None
                                               else "fix its spec with /pulse-re and merge it there first")


def findings(text, kind: str, number=None) -> list:
    """['R2 missing section: Scope', ...]; [] means an agent can plan from this spec."""
    if text is None:
        return ["R1 spec missing on the base branch"]
    fm, sec, out = front(text), sections(text), []
    if number is not None and str(fm.get("issue", "")).lstrip("#") != str(number):
        out.append(f"R1 issue: {fm.get('issue', 'missing')} in the spec, item is #{number}")
    for name in SECTIONS.get(kind, ()):
        if name.lower() not in sec:
            out.append(f"R2 missing section: {name}")
        elif not sec[name.lower()].strip():
            out.append(f"R2 empty section: {name}")
    head = "\n".join(split(text)[0])
    holes = [h for name, content in sec.items() if name not in LATE
             for h in HOLE.findall(FENCE.sub("", content))] + HOLE.findall(head)
    if holes:
        out.append(f"R3 open: {', '.join(dict.fromkeys(holes))}")
    reqs = [m for name, content in sec.items() for m in REQ.finditer(content)]
    if kind in SECTIONS and not reqs:
        out.append("R4 no requirements: no line like '- FR-01: WHEN ... THE SYSTEM SHALL ...'")
    out += [f"R4 {m.group(1)} has no SHALL (EARS)" for m in reqs if not MODAL.search(m.group(2))]
    terms = _terms()
    for row in _rows(sec.get("success criteria", "")):
        if len(row) > 1:
            hit = [t for t in terms if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", row[1])]
            if hit:
                out.append(f"R5 tech terms in {row[0]}: {', '.join(hit)}")
    for row in _rows(sec.get("non-functional requirements", "")):
        if len(row) > 1 and not re.search(r"\d", row[1]):
            out.append(f"R5 NFR without a number: {row[0]}")
    if fm.get("priority") not in PRIORITY:
        out.append("R6 priority must be P0, P1 or P2")
    if fm.get("effort") == "XL":
        out.append("R6 effort XL: split it into smaller items first")
    elif fm.get("effort") not in EFFORT:
        out.append("R6 effort must be XS, S, M or L")
    return out


def kind_and_number(path: Path, text: str) -> tuple:
    """(kind, number) of a spec file, None where it names neither: the kind from its folder, else from
    type: in its frontmatter; the number from issue:."""
    fm, kinds = front(text), {"epics": "epic", "features": "feat", "improvements": "imp", "fixes": "fix"}
    kind = kinds.get(path.parent.name) or (fm.get("type") if fm.get("type") in kinds.values() else None)
    n = str(fm.get("issue", "")).lstrip("#")
    return kind, int(n) if n.isdigit() else None


def set_front(path: Path, key: str, value: str) -> None:
    """Replace or append one top-level frontmatter key; nothing else changes."""
    text = path.read_text(encoding="utf-8")
    lines, body = split(text)
    rx = re.compile(rf"^{re.escape(key)}:")
    if any(rx.match(l) for l in lines):
        lines = [f"{key}: {value}" if rx.match(l) else l for l in lines]
    else:
        lines.append(f"{key}: {value}")
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body, encoding="utf-8")


def items(text: str) -> list:
    """[(depth, link)] of the epic's Items list, in order."""
    content = sections(text).get("items", "")
    return [(len(m.group(1)) // 2, m.group(3)) for m in ITEM.finditer(content)]


def add_item(epic: Path, number: int, title: str, link: str, under: str = None) -> None:
    """Append `- [#n title](link)` to the epic's Items list; under a feature when given."""
    lines = epic.read_text(encoding="utf-8").splitlines()
    entry = ("  " if under else "") + f"- [#{number} {title}]({link})"
    if any(f"[#{number} " in l and f"]({link})" in l for l in lines):      # listed already, by hand or a rerun
        return
    start = next((k for k, l in enumerate(lines) if re.match(r"^## +Items\s*$", l)), None)
    if start is None:
        lines += ["", "## Items", "", entry]
    else:
        end = next((k for k in range(start + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
        at = max([k for k in range(start + 1, end) if lines[k].lstrip().startswith("- [")], default=start + 1)
        if under:
            parent = next((k for k in range(start + 1, end) if f"]({under})" in lines[k]), None)
            if parent is not None:
                at = parent
                while at + 1 < end and lines[at + 1].startswith("  - ["):
                    at += 1
        lines.insert(at + 1, entry)
    epic.write_text("\n".join(lines) + "\n", encoding="utf-8")


def link_problems(root: Path) -> list:
    """[(spec path, problem)] where parent links and Items lists disagree. A spec without an issue
    number may name a parent that does not list it yet: pulse new --spec lists it there."""
    base = root / REQUIREMENTS
    specs = {p.resolve(): p.read_text(encoding="utf-8", errors="replace") for p in sorted(base.rglob("*.md"))}
    parent = {p: (p.parent / fm["parent"]).resolve() for p, t in specs.items()
              if (fm := front(t)).get("parent")}
    rel = lambda p: p.relative_to(root.resolve()).as_posix()
    listed = {}                                   # child -> the spec it is listed under
    out = []
    for epic, text in specs.items():
        top = None
        for depth, link in items(text):
            child = (epic.parent / link).resolve()
            if depth == 0:
                top = child
            owner = epic if depth == 0 else top
            listed[child] = owner
            if parent.get(child) != owner:
                where = "" if depth == 0 else f" under {Path(link).name}"
                out.append((rel(epic), f"Items lists {link}{where}, whose parent is not "
                                       f"{'this epic' if depth == 0 else 'that feature'}"))
    for child, up in parent.items():
        if up not in specs:                       # relpath: a parent may point out of the repository
            out.append((rel(child), f"parent {front(specs[child])['parent']} does not exist: from the spec's "
                                    f"folder it is {Path(os.path.relpath(up, root.resolve())).as_posix()}"))
        elif listed.get(child) != up and str(front(specs[child]).get("issue", "")).lstrip("#").isdigit():
            out.append((rel(child), f"parent {front(specs[child])['parent']} does not list it under Items"))
    return sorted(out)
