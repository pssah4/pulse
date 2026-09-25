"""pulse check: drift that a script can see, so no model has to look for it.

  C1  a relative Markdown link in _devprocess/ or an agent guide resolves
  C2  a backticked repo path in an agent guide exists
  C3  no code paths in the core sections of a decision record
  C4  no work state (status, phase, claim, ...) in any _devprocess/ frontmatter
  C5  artifacts stay within their line cap (+10%), unless they state a
      reasoned exception; lines of an HTML comment do not count
  C6  every feature spec has an Activation Path with Type and Identifier
  C7  every stub marker in the code names an issue, an open one when the
      issue cache is available
  C8  tasks in one wave of a PLAN touch disjoint files (they run in parallel)
  C9  every spec's parent: link and its epic's Items list agree
  R1 to R6  an approved item's spec is one an agent can plan from (pulse/spec.py),
      read from the base branch; without an issue cache the board is loaded,
      without a board a finding says they were skipped; --spec <path> applies them to spec
      files as they are here, before approval, and asks no board
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pulse import config, ready, spec, state

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".vitepress"}
GUIDES = {"AGENTS.md", "CLAUDE.md"}
TEMP = "_devprocess/temp/"          # temporary test files, deleted after use, never committed
TOLERANCE = 0.10
CAPS = {"project-ba": 200, "epic-ba": 120, "feature-ba": 60, "mini-ba": 40, "exploration": 70,
        "epic": 40, "feature": 80, "handoff": 60, "adr": 60, "plan": 80, "audit": 65,
        "arc42": 40, "system-map": 120}
STATE_KEYS = {"status", "phase", "claim", "last-change", "assignee", "owner"}
CORE = {"context", "kontext", "decision drivers", "begründung", "begruendung",
        "considered options", "betrachtete optionen", "decision", "entscheidung",
        "consequences", "konsequenzen"}
CODE_EXT = r"(?:py|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|rb|cs|cpp|cc|c|h|hpp|sh|sql|swift|php|vue|svelte)"
CODE_NAME = re.compile(r"(?<![\w/.-])([\w.-]*[a-z_][\w.-]*\.%s)\b" % CODE_EXT)
TECH_NAMES = {"node.js", "vue.js", "next.js", "nuxt.js", "express.js", "d3.js", "three.js", "chart.js"}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
TICK = re.compile(r"`([^`\s]+)`")
STUB = re.compile(r"FIXME\(stub\):(.*)")
COMMENT = re.compile(r"^[ \t]*<!--.*?-->[ \t]*\n?", re.M | re.S)     # template guidance, not content
TESTISH = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*$|\.(test|spec)\.[^/]*$")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


def _walk(root: Path):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            yield Path(d) / f


def _frontmatter(text: str) -> dict:
    """Top-level keys with their line numbers (1-based) from a leading --- block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for n, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            break
        m = re.match(r"^([\w-]+):\s*(.*)$", line)
        if m:
            out[m.group(1).lower()] = (m.group(2).strip(), n)
    return out


def _path_like(token: str) -> str | None:
    token = re.sub(r":\d+(-\d+)?$", "", token)
    if token.startswith(("/", "~", ".git/", "http")) or any(c in token for c in "{}<>*$:"):
        return None
    if "/" not in token:
        return None
    last = token.rstrip("/").rsplit("/", 1)[-1]
    return token if token.endswith("/") or "." in last.strip(".") else None


def _exists(root: Path, base: Path, token: str) -> bool:
    return (root / token).exists() or (base / token).exists()


def check_links(root, path, text):
    for n, line in enumerate(text.splitlines(), 1):
        for m in LINK.finditer(line):
            target = m.group(1).split("#", 1)[0]
            if not target or re.match(r"^[a-z]+:", target) or any(c in target for c in "{}<>"):
                continue
            if not (path.parent / target).exists():
                yield Finding(str(path.relative_to(root)), n, "C1", f"link target does not exist: {target}")


def check_guide_paths(root, path, text):
    for n, line in enumerate(text.splitlines(), 1):
        for m in TICK.finditer(line):
            token = _path_like(m.group(1))
            if token and not _exists(root, path.parent, token):
                yield Finding(str(path.relative_to(root)), n, "C2", f"path does not exist: {token}")


def check_decision(root, path, text):
    core = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            core = line[3:].strip().lower() in CORE
            continue
        if not core:
            continue
        hits = [t for t in (m.group(1) for m in TICK.finditer(line)) if _path_like(t)]
        hits += [c for c in CODE_NAME.findall(line) if c.lower() not in TECH_NAMES]
        if hits:
            yield Finding(str(path.relative_to(root)), n, "C3",
                          f"code path in a core section: {hits[0]} (move it to Sources or Implementation Notes)")


def check_state(root, path, fm):
    for key in sorted(STATE_KEYS & fm.keys()):
        yield Finding(str(path.relative_to(root)), fm[key][1], "C4",
                      f"work state '{key}' in frontmatter; it lives in the item's record on the board (pulse show)")


def _kind(rel: str, name: str, fm: dict) -> str | None:
    if rel.startswith("_devprocess/analysis/"):
        if name.startswith("BA-"):
            if name.endswith("-full.md") or "extended" in name.lower() \
                    or "(extended)" in fm.get("title", ("", 0))[0]:
                return None
            target = fm.get("target-type", ("", 0))[0].lower()
            if fm.get("type", ("", 0))[0] == "ba" or target in ("improvement", "fix", "imp"):
                return "mini-ba"
            return {"project": "project-ba", "epic": "epic-ba",
                    "feature": "feature-ba", "feat": "feature-ba"}.get(target)
        if name.startswith("EXPLORE-"):
            return "exploration"
        if name.startswith("AUDIT-"):
            return "audit"
    for prefix, kind in (("_devprocess/requirements/epics/", "epic"),
                         ("_devprocess/requirements/features/", "feature"),
                         ("_devprocess/decisions/ADR-", "adr"),
                         ("_devprocess/plans/", "plan")):
        if rel.startswith(prefix):
            return kind
    return {"_devprocess/requirements/handoff/architect-handoff.md": "handoff",
            "_devprocess/arc42.md": "arc42", "_devprocess/SYSTEM-MAP.md": "system-map"}.get(rel)


def _counted(text: str, kind: str) -> int:
    text = COMMENT.sub("", text)
    if kind == "epic":                  # pulse new --parent writes the Items list, a line per item
        text = re.sub(r"^## +Items[ \t]*$.*?(?=^## |\Z)", "", text, flags=re.M | re.S)
    stop = {"plan": r"^## change log", "adr": r"^## implementation notes"}.get(kind)
    if stop:
        m = re.search(stop, text, re.I | re.M)
        text = text[:m.start()] if m else text
    lines = text.splitlines()
    return sum(1 for l in lines if not l.lstrip().startswith("|")) if kind == "audit" else len(lines)


def check_cap(root, path, text, fm):
    rel = path.relative_to(root).as_posix()
    kind = _kind(rel, path.name, fm)
    if kind is None or re.search(r"^## +Reasoned exception\b", text, re.M | re.I):
        return
    n, cap = _counted(text, kind), CAPS[kind]
    if n > int(cap * (1 + TOLERANCE)):
        yield Finding(rel, 1, "C5", f"{kind}: {n} lines, cap {cap} (+10%); shrink it or add a "
                                    "'## Reasoned exception' section")


def check_activation(root, path, text):
    m = re.search(r"^## Activation Path\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    body = m.group(1) if m else ""
    missing = [k for k in ("Type", "Identifier") if not re.search(rf"^\s*-\s*{k}:", body, re.M)]
    if missing:
        yield Finding(path.relative_to(root).as_posix(), 1, "C6",
                      "no '## Activation Path' section" if not m else f"Activation Path lacks {', '.join(missing)}")


def check_waves(root, path, text):
    rel = path.relative_to(root).as_posix()
    for n, msg in ready.wave_clashes(text):
        yield Finding(rel, n, "C8", msg)


def _tracked(root: Path):
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    return [root / f for f in out.stdout.splitlines()] if out.returncode == 0 else []


def check_stubs(root: Path):
    open_issues = None
    try:
        if state.cache_path(root).is_file():
            open_issues = {i["number"] for i in state.cached(root)}
    except (OSError, subprocess.SubprocessError):
        pass
    for f in _tracked(root):
        rel = f.relative_to(root).as_posix()
        if f.suffix.lower() in (".md", ".mdx", ".txt", ".rst") or TESTISH.search(rel):
            continue
        try:
            if f.stat().st_size > 1_000_000:
                continue
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            m = STUB.search(line)
            if not m:
                continue
            ref = re.search(r"#(\d+)", m.group(1))
            if not ref:
                yield Finding(rel, n, "C7", "stub without an issue: add '-- see #<n>'")
            elif open_issues is not None and int(ref.group(1)) not in open_issues:
                yield Finding(rel, n, "C7", f"stub points at #{ref.group(1)}, which is not an open issue")


def check_readiness(root: Path):
    """Approved items: their spec must be one an agent can plan from. Every write drops the
    issue cache, so without one the board itself is read."""
    try:
        board = state.cached(root) if state.cache_path(root).is_file() else state.load(root, state.repo(root))
    except (state.StateError, OSError, ValueError) as e:
        why = str(e).partition("\n")[0]                 # gh adds a login hint on a second line
        yield Finding("board", 0, "R1-R6", f"skipped: no board ({why})")
        return
    items = [i for i in board if i.get("approved") and i.get("type") in state.WORK and i.get("spec")]
    ref = config.base_ref(root) if items else None
    for i in items:
        for f in spec.findings(spec.on_base(root, i["spec"], ref), i["type"], i["number"]):
            code, msg = f.split(" ", 1)
            yield Finding(i["spec"], 1, code, f"#{i['number']}: {msg}")


def check_specs(paths) -> list:
    """pulse check --spec: what pulse approve refuses once these specs are merged (spec.refusal),
    read from the files as they are here."""
    found = []
    for p in map(Path, paths):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            found.append(Finding(str(p), 0, "R1", f"spec missing: {e.strerror}"))
            continue
        kind, n = spec.kind_and_number(p, text)
        if kind is None:
            found.append(Finding(str(p), 1, "R2", "no kind: not in epics/, features/, improvements/, or fixes/, "
                                                  "and no type: epic, feat, imp, or fix"))
            continue
        for f in spec.findings(text, kind, n):
            if f.startswith("R1 ") or kind in spec.SECTIONS:          # an epic needs R1 only
                code, msg = f.split(" ", 1)
                found.append(Finding(str(p), 1, code, f"#{n}: {msg}" if n else msg))
    return found


def run(root: Path) -> list:
    found = []
    for path in _walk(root):
        rel = path.relative_to(root).as_posix()
        if path.suffix != ".md" or path.is_symlink():   # a linked guide is checked as its target
            continue
        if rel.startswith(TEMP):
            continue
        in_dev = rel.startswith("_devprocess/")
        guide = path.name in GUIDES or rel in ("_devprocess/SYSTEM-MAP.md", "_devprocess/decisions/README.md")
        if not (in_dev or guide):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = _frontmatter(text)
        found += check_links(root, path, text)
        if guide:
            found += check_guide_paths(root, path, text)
        if in_dev:
            found += check_state(root, path, fm)
            found += check_cap(root, path, text, fm)
        if rel.startswith("_devprocess/decisions/ADR-"):
            found += check_decision(root, path, text)
        if rel.startswith("_devprocess/requirements/features/"):
            found += check_activation(root, path, text)
        if rel.startswith("_devprocess/plans/"):
            found += check_waves(root, path, text)
    found += check_stubs(root)
    found += check_readiness(root)
    found += [Finding(p, 1, "C9", msg) for p, msg in spec.link_problems(root)]
    return sorted(found, key=lambda f: (f.path, f.line, f.rule))


def main(args) -> int:
    root = config.find_root()
    if root is None:
        print("pulse check: not inside a git repository")
        return 2
    found = check_specs(args.spec) if args.spec else run(root)
    skipped = [f for f in found if f.rule == "R1-R6"]      # no board: said, but no reason to block
    found = [f for f in found if f.rule != "R1-R6"]
    for f in found + skipped:
        print(f)
    if found:
        print(f"{len(found)} finding{'s' if len(found) != 1 else ''}")
        return 1
    print("pulse check: C1-C9 clean, R1-R6 not checked" if skipped else "pulse check: clean")
    return 0
