"""Spec files: readiness (R1 to R6), frontmatter edits, parent links, the Items list.

Readiness asks one thing: can an agent write a complete PLAN from this spec
alone? The rules read text only; the caller decides which version of the
file counts (the base branch, which every worktree starts from).

The tree epic > feature > fix or improvement lives in the repository too:
every spec names its `parent:` as a relative path, and the epic lists its
items under `## Items`. link_problems() compares both directions locally.
Each file name starts with the spec's ID, its type and the numbers of its
parent plus its own counter (EPIC-04, FEAT-04-02, FIX-04-02-01); numbering()
finds the specs whose name does not carry the ID their place calls for,
renumber() moves them. The issue number stays the ID of the record.
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
# an open entry ends at the next item; `#n ` leads it once the item has a record
ITEM = re.compile(r"^( *)- \[(?:(?!\n *- \[)[^\]])*\]\(([^)\s]+)\)", re.M)
FOLDERS = {"epics": "EPIC", "features": "FEAT", "improvements": "IMP", "fixes": "FIX"}
SPEC_ID = re.compile(r"^(EPIC|FEAT|IMP|FIX)-(\d+(?:-\d+)*?)-(?=[^\W\d_])")     # the name goes on with a letter
LETTER = re.compile(r"[^\W\d_]")                          # any letter, ü too, as SPEC_ID reads one
LIKE_ID = re.compile(r"^(?:EPIC|FEAT|IMP|FIX)-\d")
TITLE_ID = re.compile(r"^(?:EPIC|FEAT|IMP|FIX)(?:-\d+)+\s+")
ENTRY = re.compile(r"^( *- \[)(#\d+ )?(?:(?:EPIC|FEAT|IMP|FIX)(?:-\d+)+ )?([^\]\n]*\]\(([^)\s]+)\))", re.M)
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
    return [(len(m.group(1)) // 2, m.group(2)) for m in ITEM.finditer(content)
            if Path(m.group(2)).parent.name in FOLDERS]      # a board link or the BA is no item


def add_item(epic: Path, number: int, title: str, link: str, under: str = None) -> None:
    """Append `- [#n title](link)` to the epic's Items list; under a feature when given. A line for
    the link without its number, as /pulse-realign lists an item that has no record, gets it."""
    lines = epic.read_text(encoding="utf-8").splitlines()
    entry = ("  " if under else "") + f"- [#{number} {title}]({link})"
    start = next((k for k, l in enumerate(lines) if re.match(r"^## +Items\s*$", l)), None)
    if start is None:
        lines += ["", "## Items", "", entry]
    else:
        end = next((k for k in range(start + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
        have = next((k for k in range(start + 1, end) if f"]({link})" in lines[k]), None)
        if have is not None and f"[#{number} " in lines[have]:       # listed already, by hand or a rerun
            return
        at = max([k for k in range(start + 1, end) if lines[k].lstrip().startswith("- [")], default=start + 1)
        parent = None
        if under:
            parent = next((k for k in range(start + 1, end) if f"]({under})" in lines[k]), None)
            if parent is not None:
                at = parent
                while at + 1 < end and lines[at + 1].startswith("  - ["):
                    at += 1
            else:                                                # its feature is not listed yet: it comes first
                found = id_of(under)
                lines.insert(at + 1, f"- [{id_text(*found) if found else Path(under).stem}]({under})")
                parent, at, end = at + 1, at + 1, end + 1
        if have is not None and (not under or parent is None or parent < have <= at):
            lines[have] = entry                                  # in its place already
        else:
            if have is not None:                                 # listed under another feature
                del lines[have]
                at -= have < at
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


def id_of(name) -> tuple:
    """("FEAT", (4, 2)) for a spec file named FEAT-04-02-speech-input.md; None without an ID."""
    m = SPEC_ID.match(Path(str(name)).name)
    return (m.group(1), tuple(int(n) for n in m.group(2).split("-"))) if m else None


def id_text(kind: str, numbers: tuple) -> str:
    return kind + "".join(f"-{n:02d}" for n in numbers)


def with_id(path, title: str) -> str:
    """The title with the ID of its spec's file name in front, once; a spec without one keeps it."""
    found = id_of(path) if path else None
    return f"{id_text(*found)} {TITLE_ID.sub('', title, count=1)}" if found else title


def registered(root: Path) -> dict:
    """{issue number: spec path} for every spec that names its record in issue:."""
    out = {}
    for folder in FOLDERS:
        for p in (root / REQUIREMENTS / folder).glob("*.md"):
            n = str(front(p.read_text(encoding="utf-8", errors="replace")).get("issue", "")).lstrip("#")
            if n.isdigit():
                out[int(n)] = p.relative_to(root).as_posix()
    return out


def _git_out(root: Path, *args) -> str:
    out = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *args],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return out.stdout if out.returncode == 0 else ""


def _taken(root: Path) -> set:
    """(kind, numbers) of every ID a spec's file name has had: in the history of every ref, branches
    of other clones as far as the last fetch brought them, and in the working tree of every worktree.
    With ids_since in the config, a project numbers anew from that commit: only what came after it,
    on refs and in worktrees that have it, counts."""
    since = config.load(root).get("ids_since")
    if since and not _git_out(root, "rev-parse", "--verify", "-q", f"{since}^{{commit}}"):
        config._warn(f"ids_since {since} is no commit here, so all history counts")
        since = None
    if since:
        refs = _git_out(root, "for-each-ref", "--contains", since, "--format=%(refname)").split()
        names = _git_out(root, "log", *refs, f"^{since}", "--name-only", "--format=", "--",
                         REQUIREMENTS).splitlines() if refs else []
    else:
        names = _git_out(root, "log", "--all", "--name-only", "--format=", "--", REQUIREMENTS).splitlines()
    trees, head = [root], None
    for line in _git_out(root, "worktree", "list", "--porcelain").splitlines() + [""]:
        if line.startswith("worktree "):
            tree = Path(line[9:])
        elif line.startswith("HEAD "):
            head = line[5:]
        elif not line and head:
            if not since or subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", since, head],
                                           capture_output=True).returncode == 0:
                trees.append(tree)
            head = None
    names += [p.name for t in trees for p in (t / REQUIREMENTS).glob("*/*.md")]
    return {found for n in names if (found := id_of(n))}


def numbering(root: Path) -> list:
    """[(spec path, problem, new path or None)] for each spec whose file name does not carry the ID its
    place in the tree calls for: it has none, one of another folder's type, one that does not fit its
    parent, or one another spec holds too (the one on the base branch keeps it). Parents come first and
    their children are measured against the parent's new ID. A new ID is the next after every one that
    _taken() finds, so none is handed out twice, and a gap stays a gap."""
    base, top = root / REQUIREMENTS, root.resolve()
    specs = []                                    # (path, kind, parent), parents before children
    for folder, kind in FOLDERS.items():
        found = []
        for p in (base / folder).glob("*.md"):
            text = p.read_text(encoding="utf-8", errors="replace")
            if not split(text)[0]:                # a README beside the specs is no spec
                continue
            fm = front(text)
            n = str(fm.get("issue", "")).lstrip("#")
            found.append((int(n) if n.isdigit() else float("inf"), p.name, p.resolve(),
                          (p.parent / fm["parent"]).resolve() if fm.get("parent") else None))
        specs += [(p, kind, up) for _, _, p, up in sorted(found)]
    holders = {}
    for p, _, _ in specs:
        if id_of(p):
            holders.setdefault(id_of(p), []).append(p)
    rel = lambda p: p.relative_to(top).as_posix()
    final, out, taken = {}, [], None
    for p, kind, up in specs:
        if up is not None and up not in final:    # a parent that is gone, or has no ID yet: C9 names it
            continue
        above, got = final[up][1] if up is not None else (), id_of(p)
        if got is None:
            why = "no ID in the file name"
        elif got[0] != kind:
            why = f"{id_text(*got)} is no ID for the folder {p.parent.name}"
        elif got[1][:-1] != above:
            why = f"{id_text(*got)} does not fit " + (f"its parent {id_text(*final[up])}" if up else "a spec without parent")
        else:
            same = holders[got]
            keeper = next((q for q in same if on_base(root, rel(q)) is not None), same[0]) if len(same) > 1 else p
            if keeper == p:
                final[p] = got
                continue
            why = f"{id_text(*got)} is taken by {rel(keeper)}"
        name = p.name[SPEC_ID.match(p.name).end():] if got else p.name
        if not LETTER.match(name) or (got is None and LIKE_ID.match(name)):
            out.append((rel(p), "the name must start with a letter, rename it by hand", None))
            continue
        taken = _taken(root) if taken is None else taken
        n = 1 + max((t[1][-1] for t in taken if t[0] == kind and t[1][:-1] == above), default=0)
        final[p] = (kind, above + (n,))
        taken.add(final[p])
        out.append((rel(p), why, rel(p.parent / f"{id_text(*final[p])}-{name}")))
    return out


def _bytes_text(path: Path) -> str:
    """The file as text, every byte kept: not UTF-8 and CRLF come back as they were."""
    return path.read_bytes().decode("utf-8", "surrogateescape")


def renumber(root: Path, moves: list) -> None:
    """Rename each spec (old path, new path), with git where git tracks it, and rewrite every path to it
    in the repository's text files, tracked or not: a path that leads to the old file, from the file's
    folder or from the repository root, gets the new name; every other byte stays. An epic's Items
    lines take the new ID into their text."""
    top = root.resolve()
    moves = [(Path(old), Path(new)) for old, new in moves if new]
    if not moves:
        return
    olds = {(top / o).resolve(): n.name for o, n in moves}
    for old, new in moves:
        _git_out(root, "mv", "-k", old.as_posix(), new.as_posix())
        if (root / old).exists():                 # not tracked yet
            (root / old).rename(root / new)
    # a path token that ends in an old name: `../features/x.md`, `features/x.md`, `./x.md`, `x.md`
    token = re.compile(r"(?<![\w./-])((?:[\w.-]*/)*)(" + "|".join(re.escape(o.name) for o, _ in moves) + r")(?!\w)")

    def moved(m, here):
        for base, path in ((here, m.group(1)), (top, m.group(1).lstrip("/"))):      # /x from the root, as GitHub reads it
            name = olds.get((base / (path + m.group(2))).resolve())
            if name:
                return m.group(1) + name
        return m.group(0)
    grep = ["grep", "-l", "-I", "--untracked", "-F"] + [a for o, _ in moves for a in ("-e", o.name)]
    for f in _git_out(root, *grep).splitlines():
        path = top / f
        text = _bytes_text(path)
        new = token.sub(lambda m: moved(m, path.parent), text)
        if new != text:
            path.write_bytes(new.encode("utf-8", "surrogateescape"))
    ids = {n.name: id_text(*id_of(n)) for _, n in moves}
    for epic in (root / REQUIREMENTS / "epics").glob("*.md"):
        text = _bytes_text(epic)
        m = re.search(r"^## +Items[ \t]*\r?$(.*?)(?=^## |\Z)", text, re.M | re.S)
        if not m:
            continue
        one = lambda e: (f"{e.group(1)}{e.group(2) or ''}{ids[Path(e.group(4)).name]} {e.group(3)}"
                         if Path(e.group(4)).name in ids else e.group(0))
        new = text[:m.start(1)] + ENTRY.sub(one, m.group(1)) + text[m.end(1):]
        if new != text:
            epic.write_bytes(new.encode("utf-8", "surrogateescape"))
