"""pulse migrate: a DIA project becomes a Pulse project.

Two steps, each its own commit on its own branch, each shown before it runs.
A DIA file goes once its content has a new home and git history keeps it;
what history cannot bring back stays in place and is named:

  local    .dia/config.toml -> .pulse/config.toml (DIA mode off stays off),
           DIA anchor blocks replaced in place, work state dropped from
           _devprocess frontmatter (a BA's status becomes validity); .dia's
           tracked files and the git hooks DIA installed in this clone go.
  issues   every open backlog item becomes a GitHub issue, or reuses the
           one DIA created ("FEAT-01-02: ..." or "[EPIC-01] ...") or this
           migration made before (the legacy id in its body and its
           pulse:<kind> label), each only from an author with write access
           or the gh user; epic ->
           parent, depends-on -> blocked-by; specs get issue: and legacy-id:.
           Nothing is approved (the preview marks what DIA had ready, a person
           approves), and a record it creates holds only its spec link and
           legacy id. Done items stay history. The backlog goes only when
           every row got a record or is done.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from pulse import config, setup, state

ROW_KINDS = {"feature": "feat", "improvement": "imp", "refactor": "imp", "fix": "fix", "bug": "fix",
             "security": "fix"}
NOT_WORK = {"adr", "plan", "epic"}
READY = {"ready", "in progress", "in review"}
DONE = {"done", "released", "resolved", "implemented", "closed", "superseded", "withdrawn", "rejected"}
LEGACY = r"(?:EPIC|FEAT|IMP|FIX|BL)-\d+(?:-\d+)*"          # numbered ids, the ones file names carry
ITEM_ID = r"[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+"              # any row id: FIX-SEC-28-01, IMP-54-04a, SEC-034-H5
OWN_FILE = r"(?:ADR|PLAN)-\d+(?:-\d+)*|EPIC-\d+"           # rows whose content lives in their own file
LEGACY_LINE = "Legacy DIA id: "                           # the body line that marks an issue this migration made
CLAIM = re.compile(rf"^{LEGACY_LINE}(\S+)\s*$", re.M)
WRITE = ("admin", "maintain", "write")                    # a claim counts only from the gh user or these authors
STATE_KEYS = ("status", "phase", "claim", "last-change")
DIA_HOOKS = ("pre-commit", "pre-merge-commit")


class MigrateError(Exception):
    pass


def _git(root, *args, check=True):
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and out.returncode:
        raise MigrateError(f"git {' '.join(args[:2])}: {out.stderr.strip()}")
    return out.stdout.strip()


def _own(root: Path, rel) -> bool:
    """rel lies in this repository's own _devprocess once resolved: no ../ and no symlink leads elsewhere,
    and a symlink loop never counts, whether Path.resolve raises on it (up to 3.12) or not (3.13)."""
    p = root / rel
    try:
        os.stat(p)
    except FileNotFoundError:
        pass                                # not there (yet): where it would lie decides
    except OSError:                         # a symlink loop (ELOOP), no access
        return False
    try:
        return (root.resolve() / "_devprocess") in p.resolve().parents
    except (OSError, RuntimeError):
        return False


def printable(text: str) -> str:
    """text with a visible placeholder for each character a terminal would not show as itself (CR,
    U+202E, U+200B, ...): what the preview prints from issues must look like what it is."""
    return "".join(c if c.isprintable() else "\ufffd" for c in text)


def _shown(root: Path, p: Path) -> str:
    return os.path.relpath(p, root.resolve())


def _backlog(root: Path) -> Path | None:
    """This repository's own backlog; never one that a symlink leads to."""
    for name in ("BACKLOG.md", "BACKLOG-DIA-ARCHIVE.md"):     # the archive: from an older pulse migrate
        p = root / "_devprocess" / "context" / name
        if p.is_file() and p.resolve() == root.resolve() / "_devprocess" / "context" / name:
            return p
    return None


def _dia_hook(p: Path) -> bool:
    """DIA's install-git-hooks.sh wrote it: DIA's header is its second line."""
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[:2]
    return len(lines) == 2 and lines[1].startswith(tuple(f"# DIA {h} hook" for h in DIA_HOOKS))


def _dia_leftovers(root: Path) -> tuple:
    """(tracked, installed, keep) besides the backlog. tracked: .dia's files, git history keeps them.
    installed: what DIA's install-git-hooks.sh put into .git; the hooks would run DIA's checks on every
    commit, the migration's own included. keep: (path, why) for what neither covers."""
    top, git_dir = root.resolve(), config.common_dir(root)
    listed = lambda *opt: [top / f for f in _git(root, "ls-files", "-z", *opt, "--", ".dia").split("\0") if f]
    keep = [(p, "not tracked by git, so its history cannot bring it back") for p in listed("-o")]
    installed = [p for p in (git_dir / "hooks-data", git_dir / "consistency-check.last-run.json")
                 if os.path.lexists(p)]
    hooks = git_dir / "hooks"
    for name in DIA_HOOKS:
        hook, bak = hooks / name, hooks / f"{name}.bak"
        dias = [p for p in (hook, bak) if p.is_file() and _dia_hook(p)]
        if hooks.is_symlink():
            keep += [(p, "DIA's hook in a hooks folder other clones share") for p in dias]
            continue
        installed += dias
        if hook in dias and bak.is_file() and bak not in dias:
            keep.append((bak, f"the hook DIA's installer set aside; rename it to {name} to use it again"))
    return listed(), installed, keep


def _own_file(row: dict) -> bool:
    """A decision, a PLAN, or an epic: its content lives in its own file, not in the row."""
    return bool(re.fullmatch(OWN_FILE, row["id"])) or row.get("type", "").strip().lower() in NOT_WORK


def _done(row: dict) -> bool:
    return re.match(r"\s*([A-Za-z]*)", row["status"] or "").group(1).lower() in DONE


def kind_of(row: dict) -> str | None:
    rid, typ = row["id"], row.get("type", "").strip().lower()
    if not re.fullmatch(ITEM_ID, rid):
        return None
    for prefix, kind in (("FEAT-", "feat"), ("IMP-", "imp"), ("FIX-", "fix")):
        if rid.startswith(prefix):
            return kind
    if _own_file(row):
        return None
    return ROW_KINDS.get(typ, "imp" if rid.startswith("BL-") else None)


def _fate(row: dict) -> str:
    """open, done, file (its content lives in its own file), or why the migration passes the row over."""
    kind = kind_of(row)
    if not kind and _own_file(row):
        return "file"
    if row["status"] is None:
        return "no Status column outside the Deferred section"
    if _done(row):
        return "done"
    if kind:
        return "open"
    return "no Pulse type" if re.fullmatch(ITEM_ID, row["id"]) else "id not recognised"


def _cells(line: str) -> list:
    """A table row's cells; an escaped \\| stays inside its cell."""
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def parse_backlog(text: str) -> tuple:
    """(epics, rows) from a DIA BACKLOG.md: every row of a table with an ID column. The bug index
    repeats rows and is skipped. A row without a Status column is open only in the Deferred section
    (its status None elsewhere: a legend or a history table must not turn into records)."""
    epics, rows, seen = {}, [], set()
    section, epic, header = "", None, None
    for line in text.splitlines():
        if line.startswith("### "):
            m = re.match(r"^### (EPIC-\d+):\s*(.+?)\s*$", line)
            epic, header = (m.group(1), None) if m else (None, None)
            if m:
                epics[epic] = {"id": epic, "title": m.group(2), "source": None}
            continue
        if line.startswith("## "):
            section, epic, header = line[3:].strip().lower(), None, None
            continue
        if line.startswith("Source:") and epic:
            m = re.search(r"`([^`]+)`", line)
            epics[epic]["source"] = m.group(1) if m else None
            continue
        if not line.startswith("|"):
            header = None
            continue
        cells = _cells(line)
        if not "".join(cells).replace("-", "").replace(":", "").strip():
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if section.startswith("open bugs") or "id" not in header:
            continue
        row = dict(zip(header, cells))
        rid = row["id"]
        if rid and rid in seen:
            continue
        seen.add(rid)
        status = row.get("status", "Backlog" if section.startswith("deferred") else None)
        rows.append({"id": rid, "type": row.get("type", ""), "title": row.get("title", rid),
                     "status": status, "epic": epic})
    return epics, rows


def _frontmatter(path: Path) -> tuple:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1), text[m.end():]) if m else (None, text)


def _specs(root: Path) -> dict:
    out = {}
    for path in sorted((root / "_devprocess" / "requirements").rglob("*.md")):
        try:
            head, _ = _frontmatter(path)
        except OSError:                     # a symlink loop, a dangling link: nothing to read
            continue
        m = re.search(r"^id:\s*(\S+)", head or "", re.M)
        ids = {m.group(1)} if m else set()
        n = re.match(r"^(" + LEGACY + r")(?:-[a-z]|\.md)", path.name)
        ids |= {n.group(1)} if n else set()
        for i in ids:
            out.setdefault(i, path.relative_to(root).as_posix())
    return out


def _depends(root: Path, path: str | None) -> list:
    if not path:
        return []
    head, _ = _frontmatter(root / path)
    m = re.search(r"^depends-on:\s*\[(.*?)\]", head or "", re.M)
    if m:
        return re.findall(ITEM_ID, m.group(1))
    m = re.search(r"^depends-on:\s*\n((?:\s+-.*\n?)+)", (head or "") + "\n", re.M)
    return re.findall(ITEM_ID, m.group(1)) if m else []


def _title_id(title: str) -> str | None:
    """The legacy id in a title the way DIA wrote it: "FEAT-01-02: ..." or "[EPIC-01] ..."."""
    m = re.match(r"^\[?(" + ITEM_ID + r")\]?[:\s]", title) or re.search(r"\[(" + ITEM_ID + r")\]", title)
    return m.group(1) if m else None


def _trusted(repo: str, login: str, me: str, run) -> bool:
    """The gh user, or someone with write access to the records repository; no answer means no."""
    if not login or login == me:
        return bool(login)
    try:
        return run(["api", f"repos/{repo}/collaborators/{login}/permission", "--jq", ".permission"]).strip() in WRITE
    except state.StateError:
        return False


def issues(repo: str, run=state.gh) -> list:
    """Every issue with body, labels, and author. One that claims a row (the body line, or an open
    DIA-style title) learns whether its author is trusted: the gh user as GitHub names it now, not a
    cached login, or write access to the repository; each author is asked once."""
    listed = json.loads(run(["issue", "list", "--repo", repo, "--state", "all", "--limit", "1000",
                             "--json", "number,title,state,body,labels,author"]))
    try:
        me = run(["api", "user", "--jq", ".login"]).strip()
    except state.StateError:
        me = ""
    known = {}
    for issue in listed:
        login = (issue.get("author") or {}).get("login") or ""
        claims = CLAIM.search(issue.get("body") or "") or (issue.get("state") == "OPEN" and _title_id(issue["title"]))
        if claims and login not in known:
            known[login] = _trusted(repo, login, me, run)
        issue["trusted"] = known.get(login, False)
    return listed


def _claims(existing: list) -> dict:
    """{legacy id: [(how, issue)]}: issues that claim to stand for a row, ours by the body line first,
    then open ones by a DIA-style title."""
    out = {}
    for issue in existing:
        m = CLAIM.search(issue.get("body") or "")
        if m:
            out.setdefault(m.group(1), []).append(("body", issue))
    for issue in existing:
        rid = issue.get("state") == "OPEN" and _title_id(issue["title"])
        if rid:
            out.setdefault(rid, []).append(("title", issue))
    return out


def _pick(rid: str, kind: str, claims: list) -> dict:
    """The issue a row reuses and the claims passed over. Every claim needs a trusted author; ours also
    the pulse:<kind> label state.create gave it (labeling needs triage access), open or closed. A person
    sees each reuse in the preview, and each claim passed over without its title: that text is
    whatever its author wrote."""
    use, passed = None, []
    for how, issue in claims:
        labels = [label.get("name") for label in issue.get("labels") or []]
        author = (issue.get("author") or {}).get("login") or "unknown"
        head = f"#{issue['number']} {issue['state'].lower()}, by {author}"
        why = None
        if not issue.get("trusted"):
            why = f"{author} has no write access"
        elif how == "body" and f"pulse:{kind}" not in labels:
            why = f"no pulse:{kind} label"
        if not why and use is None:
            use = {"match": issue["number"], "ours": how == "body", "reuse": f"{head}: {issue['title']}"}
        elif why:
            passed.append(f"{head} ({rid}: {why})")
    return {**(use or {"match": None, "ours": False, "reuse": None}), "passed": passed}


def _checked(root: Path, rel: str | None) -> tuple:
    """(spec, refused): a spec path counts only inside this repository's own _devprocess, so a ../ in a
    Source: line or a symlink never lets the migration rewrite a file elsewhere."""
    return (None, rel) if rel and not _own(root, rel) else (rel, None)


def plan(root: Path, existing: list) -> list:
    bl = _backlog(root)
    if bl is None:
        return []
    epics, rows = parse_backlog(bl.read_text(encoding="utf-8"))
    specs, claims = _specs(root), _claims(existing)
    work = [r for r in rows if _fate(r) == "open"]
    open_ids = {r["id"] for r in work}
    actions = []
    for e in epics.values():
        if any(r["epic"] == e["id"] for r in work):
            spec, refused = _checked(root, e["source"] or specs.get(e["id"]))
            actions.append({"id": e["id"], "kind": "epic", "title": e["title"], "status": "", "ready": False,
                            "parent": None, "blocked_by": [], "spec": spec, "refused": refused,
                            **_pick(e["id"], "epic", claims.get(e["id"], []))})
            open_ids.add(e["id"])
    for r in work:
        m = re.match(r"^(?:FIX|IMP)-(\d+)-(\d+)-\d+$", r["id"])
        feature = f"FEAT-{m.group(1)}-{m.group(2)}" if m else None
        parent = feature if feature in open_ids else (r["epic"] if r["epic"] in open_ids else None)
        spec, refused = _checked(root, specs.get(r["id"]))
        actions.append({"id": r["id"], "kind": kind_of(r), "title": r["title"], "status": r["status"],
                        "ready": r["status"].strip().lower() in READY, "parent": parent,
                        "blocked_by": [d for d in _depends(root, spec) if d in open_ids],
                        "spec": spec, "refused": refused,
                        **_pick(r["id"], kind_of(r), claims.get(r["id"], []))})
    return actions


def _skipped(root: Path, actions: list) -> list:
    """What the migration does not carry over; the backlog stays while anything is listed here."""
    bl = _backlog(root)
    rows = parse_backlog(bl.read_text(encoding="utf-8"))[1] if bl else []
    out = [f"{r['id'] or '(no id)'} ({r['type'] or 'no type'}, {r['status'] or 'no status'}): {_fate(r)}"
           for r in rows if _fate(r) not in ("open", "done", "file")]
    return out + [f"{a['id']}: spec {a['refused']} lies outside _devprocess, not linked"
                  for a in actions if a["refused"]]


def _backlog_stays(root: Path, bl: Path, skipped: list) -> str | None:
    """Why --issues keeps the backlog, or None when it may go."""
    if skipped:
        return "not all of it is carried over, see skipped"
    if not _git(root, "ls-files", "--", bl.relative_to(root).as_posix()):
        return "not tracked by git, so its history cannot bring it back"
    return None


def detect(root: Path) -> dict:
    dia = root / ".dia" / "config.toml"
    mode = _toml_str(dia.read_text(encoding="utf-8"), "mode") if dia.is_file() else None
    anchors = [t.path for t in setup.TARGETS if (root / t.path).is_file()
               and t.block_re(setup.LEGACY).search((root / t.path).read_text(encoding="utf-8"))]
    bl = _backlog(root)
    rows = parse_backlog(bl.read_text(encoding="utf-8"))[1] if bl else []
    fates = [_fate(r) for r in rows if kind_of(r)]
    backlog = bl.relative_to(root).as_posix() if bl else None
    tracked, installed, keep = _dia_leftovers(root)
    skipped = _skipped(root, plan(root, []))
    why = bl and _backlog_stays(root, bl, skipped)
    return {"dia_mode": mode, "anchors": anchors,
            "pulse_config": (root / ".pulse" / "config.toml").exists(), "backlog": backlog,
            "open_items": fates.count("open"), "done_items": fates.count("done"),
            "removes": [_shown(root, p) for p in tracked + installed] + ([backlog] if bl and not why else []),
            "keeps": [f"{_shown(root, p)}: {w}" for p, w in keep] + ([f"{backlog}: {why}"] if why else []),
            "skipped": skipped}


def _toml_str(text: str, key: str) -> str | None:
    m = re.search(rf"""^\s*{key}\s*=\s*["']([^"']+)""", text, re.M)
    return m.group(1) if m else None


def _branch(root: Path, base: str) -> str:
    current = _git(root, "branch", "--show-current")
    if current not in {"main", "master", "develop", "dev", base}:
        return current
    name = f"chore/pulse-migrate-{datetime.date.today():%Y%m%d}"
    k, candidate = 1, name
    while _git(root, "rev-parse", "--verify", "-q", candidate, check=False):
        k += 1
        candidate = f"{name}-{k}"
    _git(root, "checkout", "-q", "-b", candidate)
    return candidate


def _commit(root: Path, message: str, base: str) -> str:
    """Commit what changed on the migration's own branch; with nothing to commit, no branch either."""
    _git(root, "add", "-A")
    if not _git(root, "status", "--porcelain"):
        return _git(root, "branch", "--show-current")
    branch = _branch(root, base)
    _git(root, "commit", "-q", "-m", message)
    return branch


def _require_clean(root: Path) -> None:
    if _git(root, "status", "--porcelain"):
        raise MigrateError("the working tree is not clean; commit or stash first")


def apply_local(root: Path) -> dict:
    _require_clean(root)
    dia = root / ".dia" / "config.toml"
    text = dia.read_text(encoding="utf-8") if dia.is_file() else ""
    mode = config.DIA_MODES.get(_toml_str(text, "mode"), "on")
    base = _toml_str(text, "source_branch") or config.default_branch(root)
    config.write(root, mode=mode, base_branch=base)
    audit = re.search(r"^\[audit\.supply_chain\].*?(?=^\[|\Z)", text, re.M | re.S)
    if audit:
        with open(root / ".pulse" / "config.toml", "a", encoding="utf-8") as f:
            f.write("\n" + audit.group(0).strip() + "\n")
    tracked, installed, keep = _dia_leftovers(root)     # the settings live in .pulse/config.toml now
    if tracked:
        _git(root, "rm", "-r", "-q", "--", ".dia")         # history keeps them; untracked files stay
    for p in installed:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink()
    anchors = []
    for t in setup.TARGETS:
        p = root / t.path
        if p.is_file() and t.block_re(setup.LEGACY).search(p.read_text(encoding="utf-8")):
            p.write_text(setup.write_anchor(p.read_text(encoding="utf-8"), t, mode), encoding="utf-8")
            anchors.append(t.path)
    touched = 0
    for p in sorted((root / "_devprocess").rglob("*.md")):
        if not _own(root, p):               # a symlink out of the repository: another project's file
            continue
        try:
            head, body = _frontmatter(p)
        except (OSError, ValueError):       # a dangling link, a folder named *.md: passed over, as in _specs
            continue
        if head is None:
            continue
        lines = head.splitlines()
        if p.parent.name == "analysis" and p.name.startswith("BA-"):
            new = [re.sub(r"^status:", "validity:", l) for l in lines]
        else:
            new = [l for l in lines if not re.match(r"^(%s):" % "|".join(STATE_KEYS), l)]
        if new != lines:
            p.write_text("---\n" + "\n".join(new) + "\n---\n" + body, encoding="utf-8")
            touched += 1
    branch = _commit(root, "chore: migrate DIA to Pulse (config, anchors, frontmatter)", base)
    return {"branch": branch, "mode": mode, "base_branch": base, "anchors": anchors, "frontmatter": touched,
            "removed": [_shown(root, p) for p in tracked + installed],
            "kept": [f"{_shown(root, p)}: {w}" for p, w in keep]}


def _stamp(root: Path, rel: str, legacy: str, number: int) -> None:
    p = root / rel
    head, body = _frontmatter(p)
    lines, out, skip = (head or "").splitlines(), [f"issue: {number}"], False
    for l in lines:
        if skip and re.match(r"^\s+-", l):
            continue
        skip = bool(re.match(r"^(epic|feature|depends-on):\s*$", l))
        if re.match(r"^(epic|feature|depends-on|issue):", l):
            continue
        out.append(re.sub(r"^id:\s*", "legacy-id: ", l) if l.startswith("id:") else l)
    if not any(l.startswith("legacy-id:") for l in out):
        out.append(f"legacy-id: {legacy}")
    p.write_text("---\n" + "\n".join(out) + "\n---\n" + body, encoding="utf-8")


def apply_issues(root: Path, repo: str, run=state.gh) -> dict:
    _require_clean(root)
    rank = {"epic": 0, "feat": 1}
    actions = sorted(plan(root, issues(repo, run)),
                     key=lambda a: (rank.get(a["kind"], 3 if a["id"].startswith("BL-") else 2)))
    numbers, created, reused = {}, 0, 0
    for a in actions:
        parent = numbers.get(a["parent"])
        if a["match"]:
            if not a["ours"]:           # DIA made it; ours got labels and parent when it was created
                args = ["issue", "edit", str(a["match"]), "--repo", repo, "--add-label", f"pulse:{a['kind']}"]
                args += ["--parent", str(parent)] if parent else []
                run(args)
            numbers[a["id"]], reused = a["match"], reused + 1
            continue
        numbers[a["id"]] = state.create(root, repo, a["kind"], a["title"], parent=parent,
                                        spec=a["spec"], body=LEGACY_LINE + a["id"], run=run)
        created += 1
    for a in actions:
        for b in a["blocked_by"]:
            run(["issue", "edit", str(numbers[a["id"]]), "--repo", repo, "--add-blocked-by", str(numbers[b])])
    for a in actions:
        if a["spec"] and (root / a["spec"]).is_file():
            _stamp(root, a["spec"], a["id"], numbers[a["id"]])
    bl, skipped = _backlog(root), _skipped(root, actions)
    why = bl and _backlog_stays(root, bl, skipped)
    rel = bl.relative_to(root).as_posix() if bl else None
    if bl and not why:                  # every row is on the board or done; git history keeps the file
        _git(root, "rm", "-q", "--", rel)   # and an emptied folder goes with it
    branch = _commit(root, "chore: link DIA specs to their GitHub issues"
                     + ("" if why or not bl else ", remove the backlog"),
                     config.load(root)["base_branch"] or config.default_branch(root))
    state.drop_cache(root)
    return {"branch": branch, "created": created, "reused": reused, "numbers": numbers,
            "removed": [rel] if bl and not why else [], "kept": [f"{rel}: {why}"] if why else [],
            "skipped": skipped, "passed": [p for a in actions for p in a["passed"]]}
