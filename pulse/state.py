"""Work state in GitHub issues, read through a local cache.

GitHub is the only store (ADR-02). Reads come from one cached
`gh issue list` in the shared git dir, refreshed at most every TTL seconds;
every write goes straight to GitHub and drops the cache. Callers pass
`run` to replace gh in tests.

A claim is the assignee plus a claim mark: a comment that names the agent
session holding the item. All agents of one person share a login, so the
mark is what keeps a second session off an item the first one holds. The
oldest mark of an assignee holds the item. The mark also tells the phase
of the work and the last sign of life (its beat); a release may leave a
note for whoever takes the item next.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import random
import re
import subprocess
import time
import uuid
from pathlib import Path

from pulse import config

TTL = 30                 # a full reload at least this often: PR checks move without a new tag
POLL = 2                 # seconds between the free conditional checks for a change
FORMAT = 2               # of the issue cache, raised when normalize gains a field: another one is read again
# ponytail: comments ride along only for the claim marks (who holds an item, since when); a repo
# with long issue threads pays for them in every full reload
FIELDS = "number,title,state,labels,assignees,parent,blockedBy,blocking,body,url,updatedAt,comments"
TYPES = ("epic", "feat", "imp", "fix")
WORK = ("feat", "imp", "fix")          # epics are containers, never picked up
APPROVED = "pulse:approved"            # a person wants it built
LEGACY_READY = "pulse:ready"           # the same label before 2026-09
PLAN_OK = "pulse:plan-ok"              # a person approved the PLAN
DRAFT = "pulse:draft"                  # a record without a spec yet: BA or RE works on it
WRITERS = {"OWNER", "MEMBER", "COLLABORATOR"}     # may push; anyone may comment on a public issue or PR
SPEC = re.compile(r"^Spec: `([^`]+)`", re.M)
RANK = re.compile(r"^Rank:[ \t]*(-?\d+(?:\.\d+)?)[ \t]*$", re.M)     # the team order, lowest first
PLAN_OK_LINE = re.compile(r"^Plan-ok:[ \t]*([0-9a-f]+)[ \t]*$", re.M)   # the PLAN a person approved
REMOTE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")
MARK = re.compile(r"<!-- pulse:claim (\{.*?\}) -->")
NOTE = re.compile(r"<!-- pulse:note (\{.*?\}) -->")
COMMENT = re.compile(r"#issuecomment-(\d+)$")
ITEM_BRANCH = re.compile(r"^(?:feat|imp|fix)/(\d+)-")        # how pulse names an item's branch


class StateError(Exception):
    pass


def item_of(branch):
    """The item a branch builds; any branch pulse did not name <type>/<n>-<slug> is no item's."""
    m = ITEM_BRANCH.match(branch or "")
    return int(m.group(1)) if m else None


def gh(args: list) -> str:
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise StateError(f"gh {' '.join(args[:2])}: no answer within 60 s") from None
    if out.returncode != 0:
        raise StateError(f"gh {' '.join(args[:2])}: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout


def repo(root: Path, run=gh) -> str:
    """owner/name to act on. Never guessed when several GitHub remotes exist."""
    cfg = config.load(root)
    if cfg["source"] is None and (root / ".git").is_file():      # a worktree follows its main copy
        cfg = config.load(config.common_dir(root).parent)
    if cfg["repo"]:
        return cfg["repo"]
    try:
        chosen = run(["repo", "set-default", "--view"]).strip()
    except StateError:
        chosen = ""
    if chosen:
        return chosen
    urls = subprocess.run(["git", "-C", str(root), "remote", "-v"], capture_output=True,
                          text=True).stdout.split()
    found = sorted({m.group(1) for u in urls for m in [REMOTE.search(u)] if m})
    if len(found) == 1:
        return found[0]
    raise StateError(f"{len(found)} GitHub remotes ({', '.join(found) or 'none'}); "
                     'set repo = "owner/name" in .pulse/config.toml')


def _rank(body: str):
    m = RANK.search(body)
    return float(m.group(1)) if m else None


def _plan_ok(labels: list, body: str):
    """The digest of the PLAN a person approved, or None; the label alone binds no PLAN."""
    m = PLAN_OK_LINE.search(body)
    return m.group(1) if PLAN_OK in labels and m else None


def normalize(issue: dict) -> dict:
    labels = [l["name"] for l in issue.get("labels", [])]
    kind = next((t for t in TYPES if f"pulse:{t}" in labels), None)
    spec = SPEC.search(issue.get("body") or "")
    assignees = [a["login"] for a in issue.get("assignees", [])]
    marks = _marks(issue)
    mark = next((m for m in marks if m["author"] in assignees), None)     # the oldest holds it
    notes = [c for c in issue.get("comments") or [] if NOTE.search(c.get("body") or "") and
             (c.get("viewerDidAuthor") or (c.get("author") or {}).get("login") in assignees
              or c.get("authorAssociation") in WRITERS)]      # a note steers the next holder
    note = notes[-1] if notes and notes[-1].get("createdAt", "") > max((m["at"] for m in marks), default="") \
        else None              # a note from before the last claim is that holder's past
    return {
        "number": issue["number"],
        "title": issue["title"],
        "type": kind,
        "approved": APPROVED in labels or LEGACY_READY in labels,
        "plan_ok": _plan_ok(labels, issue.get("body") or ""),
        "assignees": assignees,
        "claimed_by": mark["author"] if mark else (assignees[0] if assignees else None),
        "claimed_holder": mark["id"] if mark else None,       # the session that holds it: codex:<thread>
        "claimed_at": (mark["at"] or None) if mark else None,
        "claimed_phase": mark["phase"] if mark else None,
        "claimed_beat": mark["beat"] if mark else None,
        "claimed_files": mark["files"] if mark else [],        # what it changes; every ramp holds them
        "note": note["body"].partition("\n")[2].strip() if note else "",
        "note_at": note.get("createdAt", "") if note else "",
        "draft": DRAFT in labels,
        "parent": (issue.get("parent") or {}).get("number"),
        "blocked_by": [n["number"] for n in (issue.get("blockedBy") or {}).get("nodes", [])
                       if n.get("state") == "OPEN"],
        "blocking": [n["number"] for n in (issue.get("blocking") or {}).get("nodes", [])
                     if n.get("state") == "OPEN"],
        "spec": spec.group(1) if spec else None,
        "rank": _rank(issue.get("body") or ""),
        "pr": None,            # attached in load(): the open PR that closes this item
        "url": issue.get("url"),
        "updated": issue.get("updatedAt"),
    }


def cache_dir(root: Path) -> Path:
    """pulse/ in the shared git dir. Where that is read-only (Codex's sandbox keeps .git so), a
    folder of mine in TMPDIR, one per repository: a cache is never worth a failed command."""
    d = config.pulse_dir(root)
    if os.access(d if d.exists() else d.parent, os.W_OK):       # the sandbox answers here too
        return d
    mine = Path(os.environ.get("TMPDIR") or "/tmp") / f"pulse-{os.getuid()}"
    try:
        mine.mkdir(mode=0o700, exist_ok=True)
        if mine.lstat().st_uid == os.getuid():                  # a shared /tmp: never another user's
            return mine / hashlib.sha256(str(d).encode()).hexdigest()[:16]
    except OSError:
        pass
    return d                   # writes fail quietly then


def cache_path(root: Path) -> Path:
    return cache_dir(root) / "issues.json"


def _body(repo_name: str, n: int, run) -> str:
    return json.loads(run(["issue", "view", str(n), "--repo", repo_name, "--json", "body"])).get("body") or ""


def spec_of(repo_name: str, n: int, run=gh):
    """The spec an item links, open or closed; None without one."""
    m = SPEC.search(_body(repo_name, n, run))
    return m.group(1) if m else None


def _set_line(root: Path, repo_name: str, n: int, rx, line: str, run) -> None:
    """Replace or append one `Key: value` line in the issue body; nothing else in the body changes.
    GitHub replaces the whole body, so a concurrent write of another line (rank against approve-plan)
    can drop mine, even one that lands after I read mine back. So I read again after a short random
    pause until two reads agree, and put my line back whenever it is gone. A later value of my own
    line is another writer's, and stays."""
    def put(body):
        body = rx.sub(line, body, count=1) if rx.search(body) else body.rstrip("\n") + "\n\n" + line + "\n"
        run(["issue", "edit", str(n), "--repo", repo_name, "--body", body])

    put(_body(repo_name, n, run))
    last = None
    for _ in range(5):         # ponytail: GitHub has no compare-and-swap for a body, so a write that
        time.sleep(random.uniform(0.1, 0.4))      # lands after my last read still drops my line
        body = _body(repo_name, n, run)
        if not rx.search(body):
            put(body)
            body = None        # my write is no read: two reads after it must agree
        elif body == last:
            break
        last = body
    drop_cache(root)


def set_rank(root: Path, repo_name: str, n: int, value: float, run=gh) -> None:
    _set_line(root, repo_name, n, RANK, "Rank: " + ("%f" % value).rstrip("0").rstrip("."), run)


def set_spec(root: Path, repo_name: str, n: int, path: str, run=gh) -> None:
    """The record links its spec at a new path (pulse number renamed it)."""
    _set_line(root, repo_name, n, SPEC, f"Spec: `{path}`", run)


def drop_cache(root: Path) -> None:
    try:
        cache_path(root).unlink()
    except OSError:            # gone already, or no folder takes a write
        pass


def cached(root: Path) -> list:
    """The last cached items regardless of age; [] without a cache."""
    try:
        return json.loads(cache_path(root).read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        return []


FAILED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def checks(rollup: list):
    """A PR's checks in one word: fail beats pending beats pass; None without checks."""
    def one(c):
        if c.get("__typename") == "StatusContext":
            return c.get("state") or "PENDING"
        return (c.get("conclusion") or "PENDING") if c.get("status") == "COMPLETED" else "PENDING"

    if not rollup:
        return None
    states = {one(c) for c in rollup}
    if states & FAILED:
        return "fail"
    return "pending" if states & {"PENDING", "EXPECTED"} else "pass"


def changed(repo_name: str, etag: str, run=gh) -> tuple:
    """(changed, etag): did any issue or pull request move since etag? GitHub answers an
    unchanged state with 304, which does not count against the rate limit."""
    args = ["api", "-i", f"repos/{repo_name}/issues?state=all&sort=updated&direction=desc&per_page=1"]
    if etag:
        args[2:2] = ["-H", f"If-None-Match: {etag}"]
    try:
        out = run(args)
    except StateError as e:
        return ("HTTP 304" not in str(e)), etag       # gh exits 1 on a 304
    m = re.search(r"^etag:\s*(.+?)\s*$", out, re.M | re.I)
    return True, m.group(1) if m else ""


def _keep(path: Path, data: dict) -> None:
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)      # readers (hooks, map) never see a half-written file
    except OSError:
        pass                   # no cache: the next read asks GitHub again


def load(root: Path, repo_name: str, run=gh, fresh: bool = False) -> list:
    """All open issues, normalized. Every POLL seconds a free check whether anything moved;
    a full reload only on a change, or after TTL."""
    path, now = cache_path(root), time.time()
    if not fresh and path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
        if cached.get("repo") == repo_name and cached.get("format") == FORMAT:
            if now - max(cached.get("fetched_at", 0), cached.get("checked_at", 0)) < POLL:
                return cached["items"]
            if now - cached.get("fetched_at", 0) < TTL:
                moved, _ = changed(repo_name, cached.get("etag", ""), run)
                if not moved:
                    _keep(path, {**cached, "checked_at": now})
                    return cached["items"]
    _, etag = changed(repo_name, "", run)
    raw = json.loads(run(["issue", "list", "--repo", repo_name, "--state", "open",
                          "--limit", "1000", "--json", FIELDS]))
    items = [normalize(i) for i in raw]
    prs = json.loads(run(["pr", "list", "--repo", repo_name, "--state", "open", "--limit", "200",
                          "--json", "number,headRefName,baseRefName,isDraft,closingIssuesReferences,"
                                    "statusCheckRollup,reviewRequests"]))
    closes = {n: {"number": pr["number"], "branch": pr["headRefName"], "base": pr.get("baseRefName"),
                  "draft": pr["isDraft"], "checks": checks(pr.get("statusCheckRollup") or []),
                  "reviewers": [r["login"] for r in pr.get("reviewRequests") or [] if r.get("login")]}
              for pr in prs for n in pr_items(pr)}
    for i in items:
        i["pr"] = closes.get(i["number"])
    _keep(path, {"repo": repo_name, "format": FORMAT, "fetched_at": now, "checked_at": now, "etag": etag, "items": items})
    return items


def pr_items(pr: dict) -> set:
    """The items a PR builds: its branch name, and what GitHub links. GitHub links "Closes #n"
    only in a PR against the default branch; against develop or a blocker's branch the branch
    name is all there is."""
    n = item_of(pr.get("headRefName"))
    return {ref["number"] for ref in pr.get("closingIssuesReferences") or [] if "number" in ref} | \
        ({n} if n else set())


def sync_merged(root: Path, repo_name: str, items: list, run=gh) -> list:
    """Catch up with merges GitHub does not act on: close an open item whose PR was merged
    (GitHub closes only on the default branch; a stacked PR merges into its blocker's branch),
    and retarget a stacked PR whose blocker's branch was merged. Returns the items it closed."""
    merged = json.loads(run(["pr", "list", "--repo", repo_name, "--state", "merged", "--limit", "50",
                             "--json", "number,headRefName,baseRefName,closingIssuesReferences"]) or "[]")
    open_ = {i["number"] for i in items}
    closed = []
    for pr in merged:
        for n in sorted(pr_items(pr) & open_ - set(closed)):
            done(root, repo_name, n, run=run, take=True)
            closed.append(n)
    # only an item branch carries a stack; a merged release PR (develop into main) moves nothing
    into = {pr["headRefName"]: pr.get("baseRefName") for pr in merged if item_of(pr["headRefName"])}
    for i in items:
        pr = i.get("pr") or {}
        if pr.get("base") in into:
            run(["pr", "edit", str(pr["number"]), "--repo", repo_name, "--base", into[pr["base"]]])
    if closed:
        drop_cache(root)
    return closed


def me(root: Path, run=gh) -> str:
    """My GitHub login, kept with the caches for a day, or until gh logs in anew (its hosts file)."""
    path = cache_dir(root) / "me"
    conf = os.environ.get("GH_CONFIG_DIR") or \
        os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "gh")
    try:
        login_at = os.stat(os.path.join(conf, "hosts.yml")).st_mtime
    except OSError:
        login_at = 0
    try:
        kept = path.stat().st_mtime
        if kept > login_at and time.time() - kept < 86400:
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    login = run(["api", "user", "--jq", ".login"]).strip()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(login, encoding="utf-8")
    except OSError:
        pass                   # asked again next time
    return login


def critical_path(items: list) -> dict:
    """Length of the longest chain of open work each item unblocks, itself included."""
    by = {i["number"]: i for i in items}
    memo: dict = {}

    def walk(n, seen=()):
        if n in memo:
            return memo[n]
        if n in seen or n not in by:
            return 0
        memo[n] = 1 + max((walk(m, seen + (n,)) for m in by[n]["blocking"]), default=0)
        return memo[n]

    return {n: walk(n) for n in by}


def ready(items: list) -> list:
    crit = critical_path(items)
    pick = [i for i in items if i["type"] in WORK and i["approved"]
            and not i["assignees"] and not i["blocked_by"]]
    return sorted(pick, key=lambda i: (-crit[i["number"]], i["number"]))


def blocked(items: list) -> list:
    return [i for i in items if i["blocked_by"]]


def create(root: Path, repo_name: str, kind: str, title: str, parent=None, blocked_by=(),
           spec=None, body="", run=gh, draft=False) -> int:
    if kind not in TYPES:
        raise StateError(f"type must be one of {', '.join(TYPES)}")
    text = (f"Spec: `{spec}`\n\n" if spec else "") + body
    args = ["issue", "create", "--repo", repo_name, "--title", title,
            "--label", f"pulse:{kind}", "--body", text or title]
    if draft:
        args += ["--label", DRAFT]
    if parent:
        args += ["--parent", str(parent)]
    if blocked_by:
        args += ["--blocked-by", ",".join(map(str, blocked_by))]
    url = run(args).strip().splitlines()[-1]
    drop_cache(root)
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def block(root: Path, repo_name: str, n: int, blockers, run=gh) -> None:
    run(["issue", "edit", str(n), "--repo", repo_name, "--add-blocked-by", ",".join(map(str, blockers))])
    drop_cache(root)


def approve(root: Path, repo_name: str, numbers, run=gh, undo=False) -> None:
    """Approve, or take the approval back. The label from before 2026-09 stays: gh fails on a label
    the repo no longer has, and `pulse setup --labels` renamed it on every issue."""
    for n in numbers:
        run(["issue", "edit", str(n), "--repo", repo_name, "--remove-label" if undo else "--add-label", APPROVED])
    drop_cache(root)


def approve_plan(root: Path, repo_name: str, n: int, digest: str, run=gh) -> None:
    """A person approved exactly this PLAN (its digest); a rewritten PLAN waits again."""
    _set_line(root, repo_name, n, PLAN_OK_LINE, f"Plan-ok: {digest}", run)
    run(["issue", "edit", str(n), "--repo", repo_name, "--add-label", PLAN_OK])
    drop_cache(root)


def _view(repo_name, n, run):
    return json.loads(run(["issue", "view", str(n), "--repo", repo_name,
                           "--json", "state,labels,assignees,blockedBy,comments"]))


def holder(env=None) -> dict:
    """Who claims: the run of pulse go that started this agent, else the agent session, else a terminal:
    its session on this host (one per terminal window, tab, or tmux pane; a script and all it starts)."""
    env = os.environ if env is None else env
    try:
        given = json.loads(env.get("PULSE_HOLDER") or "null")
        if isinstance(given, dict) and given.get("id"):
            return {"id": str(given["id"])}
    except ValueError:
        pass
    for kind, var in (("codex", "CODEX_THREAD_ID"), ("claude", "CLAUDE_CODE_SESSION_ID")):
        if env.get(var):       # Codex first: a Codex started from a Claude shell inherits Claude's id
            return {"id": f"{kind}:{env[var]}"}
    return {"id": f"terminal:{os.uname().nodename}:{os.getsid(0)}"}


def run_holder() -> dict:
    return {"id": f"go:{uuid.uuid4().hex[:12]}"}


def _marks(v) -> list:
    """Claim marks on an issue, oldest first. A mark counts when I wrote it or its author is assigned."""
    assigned = {a["login"] for a in v.get("assignees", [])}
    out = []
    for c in v.get("comments") or []:
        m, cid = MARK.search(c.get("body") or ""), COMMENT.search(c.get("url") or "")
        author = (c.get("author") or {}).get("login", "")
        if not (m and cid and (c.get("viewerDidAuthor") or author in assigned)):
            continue
        try:
            data = json.loads(m.group(1))
            hid = str(data["id"])
        except (ValueError, KeyError, TypeError):
            continue
        files = data.get("files") if isinstance(data.get("files"), list) else []
        out.append({"id": hid, "cid": cid.group(1), "mine": bool(c.get("viewerDidAuthor")),
                    "author": author, "at": c.get("createdAt") or "",
                    "phase": data.get("phase"), "beat": data.get("beat"),
                    "files": [posixpath.normpath(f) for f in files if isinstance(f, str) and f]})
    return out


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _mark(who: dict, phase, files=None) -> str:
    """A claim mark: the holder, its phase, the time now, and the files the work changes for Pulse;
    one line for people."""
    at = _utc()
    data = {**who, "phase": phase, "beat": at, **({"files": files} if files else {})}
    return (f"<!-- pulse:claim {json.dumps(data)} -->\n"
            f"Held by {_name({**who, 'mine': True, 'at': ''})}{': ' + phase if phase else ''}, "
            f"as of {at[11:16]} UTC.")


def _name(m: dict) -> str:
    kind, _, sid = m["id"].partition(":")
    who = m["author"] if not m["mine"] else \
        {"go": "a pulse go run", "terminal": "a terminal"}.get(kind, f"{kind} session {sid[:8]}")
    return who + (f" since {m['at'][:10]} {m['at'][11:16]} UTC" if m["at"] else "")


def _people(v, login: str) -> str:
    """The other people an item is assigned to, each with the age of their claim when a mark tells it."""
    marks = _marks(v)
    return ", ".join(next((_name(m) for m in marks if m["author"] == a), a)
                     for a in (a["login"] for a in v.get("assignees", [])) if a != login)


def _unmark(repo_name, cid, run) -> None:
    try:
        run(["api", "-X", "DELETE", f"repos/{repo_name}/issues/comments/{cid}"])
    except StateError as e:
        if "HTTP 404" not in str(e):
            raise              # a mark left behind holds the item against every later claim
        # already gone: another claimer cleaned up first


def _other_session(v, who: dict):
    """The mark of another session of mine that holds the item, if one does."""
    marks = _marks(v)
    return marks[0] if marks and marks[0]["mine"] and marks[0]["id"] != who["id"] else None


def _work(root: Path, n: int) -> str:
    """Where the work on n is, for whoever holds it next: its branch, when origin has one. Asked of
    origin itself, since the holder may have pushed after my last fetch."""
    from pulse import ready    # ready reads the board through this module
    for line in ready.net_git(root, "ls-remote", "--heads", "origin").stdout.splitlines():
        branch = line.partition("\trefs/heads/")[2]
        if item_of(branch) == n:
            return f"; the work is on origin/{branch}"
    return ""


def claim(root: Path, repo_name: str, n: int, run=gh, who=None, take=False, blockers=True,
          stacked_on=None, phase=None, files=None) -> tuple:
    """Assign me and mark this session. Another session is refused, even under my login;
    of two concurrent claims the older mark wins. `blockers=False` for planning, which does
    not wait for blockers; building does, except for the one blocker it stacks on. A draft
    is claimed for its spec work: no approval, no blockers. `files` go on the mark, so every
    ramp holds them without a fetch. A claim again of the session that holds n only puts new files
    (a PLAN written since) or a new phase on its mark, whatever approval and blockers say by now."""
    who = who or holder()
    v = _view(repo_name, n, run)
    open_blockers = [b["number"] for b in (v.get("blockedBy") or {}).get("nodes", [])
                     if b.get("state") == "OPEN" and b["number"] != stacked_on]
    labels = {l["name"] for l in v.get("labels", [])}
    if v.get("state") != "OPEN":
        return False, f"#{n} is closed"
    login, marks = me(root, run=run), _marks(v)
    mine = next((m for m in marks if m["mine"] and m["id"] == who["id"]), None)
    again = mine is not None and marks[0] is mine and login in [a["login"] for a in v.get("assignees", [])]
    if not again and not {APPROVED, LEGACY_READY, DRAFT} & labels:
        return False, f"#{n} is not approved"
    if not again and blockers and open_blockers and DRAFT not in labels:
        return False, f"#{n} is blocked by " + ", ".join(f"#{b}" for b in open_blockers)
    whom = _others(v, login)
    if whom:
        return False, f"#{n} is held by {whom}; to hand it over: pulse release {n} --take" + _work(root, n)
    other = _other_session(v, who)
    if other and not take:
        return False, f"#{n} is held by {_name(other)}; if that session has ended: pulse claim {n} --take" + \
            _work(root, n)
    for m in marks:
        if m["mine"] and m["id"] != who["id"]:
            _unmark(repo_name, m["cid"], run)            # taken over on purpose
    posted, key = None, (root, repo_name, n, who["id"])
    if mine:
        new = {**mine, "phase": phase or mine["phase"], "files": files or mine["files"]}
        if new != mine:        # a PLAN written since the claim, or the next phase
            _rewrite(repo_name, new, who, new["phase"], run)
            drop_cache(root)
        mine = new
    else:
        posted = COMMENT.search(run(["issue", "comment", str(n), "--repo", repo_name, "--body",
                                     _mark(who, phase, files)]).strip())
        mine = posted and {"cid": posted.group(1), "files": files or []}
    if again:
        _KEPT[key] = mine
        return True, f"claimed #{n}"
    try:
        run(["issue", "edit", str(n), "--repo", repo_name, "--add-assignee", "@me"])   # a no-op when set
    except StateError:
        if posted:
            _unmark(repo_name, posted.group(1), run)      # a mark without the assignee would hold the item
        raise
    # ponytail: two reads right after two writes; if GitHub serves a stale read, both claimers
    # can lose (safe) or, rarely, both win. A short wait before this read would narrow it.
    v = _view(repo_name, n, run)
    try:
        drop_cache(root)
    except OSError:
        pass                   # the board decides the claim; a cache out of reach is stale for POLL s
    held, marks = [a["login"] for a in v.get("assignees", [])], _marks(v)
    if marks and marks[0]["mine"] and marks[0]["id"] == who["id"] and login in held:
        if mine:
            _KEPT[key] = mine
        return True, f"claimed #{n}" + (_work(root, n) if other else "")
    if not marks or not marks[0]["mine"]:                  # the winner is another person
        run(["issue", "edit", str(n), "--repo", repo_name, "--remove-assignee", "@me"])
    for m in marks:
        if m["mine"] and m["id"] == who["id"]:
            _unmark(repo_name, m["cid"], run)            # lost: take my mark back, after the assignee
    return False, f"#{n} went to {_name(marks[0]) if marks else 'nobody; try again'}"


def _rewrite(repo_name: str, mark: dict, who: dict, phase, run) -> None:
    run(["api", "-X", "PATCH", f"repos/{repo_name}/issues/comments/{mark['cid']}",
         "-f", "body=" + _mark(who, phase, mark["files"])])


# ponytail: kept per process, so pulse go beats with one write; a hook or `pulse beat` is a process of
# its own and looks the mark up first. An agent of the run that claims with other files in its own
# process loses them to the next beat; the agents are told not to touch GitHub.
_KEPT = {}                 # (root, repo, n, holder id) -> my mark on n as I last wrote or read it: cid, files


def beat(root: Path, repo_name: str, n: int, phase: str, run=gh, who=None) -> bool:
    """A sign of life: my mark on n names this phase and the time now; it keeps its age. False,
    and nothing written, when this session holds no mark on n. Once my claim or a first beat
    found the mark, a beat is one write; a mark gone since is looked up once more."""
    who = who or holder()
    key = (root, repo_name, n, who["id"])
    mine = _KEPT.pop(key, None)
    try:
        if mine:
            _rewrite(repo_name, mine, who, phase, run)
    except StateError as e:
        if "HTTP 404" not in str(e):
            raise
        mine = None            # released and claimed anew, or taken over
    if not mine:
        mine = next((m for m in _marks(_view(repo_name, n, run)) if m["mine"] and m["id"] == who["id"]), None)
        if not mine:
            return False
        _rewrite(repo_name, mine, who, phase, run)
    _KEPT[key] = mine
    drop_cache(root)
    return True


def _others(v, login: str) -> str:
    """Who holds the item when it is assigned and I am not among its assignees; empty otherwise."""
    held = [a["login"] for a in v.get("assignees", [])]
    return _people(v, login) if held and login not in held else ""


def release(root: Path, repo_name: str, n: int, run=gh, who=None, take=False, take_person=False,
            note="") -> tuple:
    """Unassign me, then take my marks back; in this order, no claim can adopt a half-released item.
    `take` frees what another session of mine holds; `take_person` also what another person holds:
    a person hands the item over, their assignee and marks go, and a comment says who did it.
    Without it, a person assigned next to me keeps their part. A note (why, where the work is)
    goes on the item once the claim is gone, for whoever takes it next."""
    who = who or holder()
    v = _view(repo_name, n, run)
    login = me(root, run=run)
    whom = _others(v, login)
    if whom and not take_person:
        return False, f"#{n} is held by {whom}; to hand it over: pulse release {n} --take" + _work(root, n)
    gone = [a["login"] for a in v.get("assignees", []) if a["login"] != login] if take_person else []
    other = _other_session(v, who)
    if other and not (take or take_person):
        return False, f"#{n} is held by {_name(other)}; if that session has ended: pulse release {n} --take" + \
            _work(root, n)
    run(["issue", "edit", str(n), "--repo", repo_name, "--remove-assignee", ",".join(gone + ["@me"])])
    if gone:
        run(["issue", "comment", str(n), "--repo", repo_name, "--body",
             f"Released from {', '.join(gone)} by {login} with pulse release {n} --take."])
    for m in _marks(v):
        if m["mine"] or m["author"] in gone:
            _unmark(repo_name, m["cid"], run)
    if note:
        leave_note(repo_name, n, note, login, who, run)
    drop_cache(root)
    return True, f"released #{n}" + (f" from {', '.join(gone)}" if gone else "") + \
        (_work(root, n) if gone or other else "")


def leave_note(repo_name: str, n: int, text: str, by: str, who: dict, run=gh) -> None:
    """A note on n for whoever takes it next (why, where the work is); normalize reads the last one."""
    run(["issue", "comment", str(n), "--repo", repo_name, "--body",
         f"<!-- pulse:note {json.dumps({'at': _utc(), 'by': by, 'holder': who['id']})} -->\n{text}"])


def attach(root: Path, repo_name: str, n: int, kind: str, path=None, parent=None, blocked_by=(),
           run=gh, who=None, title=None) -> tuple:
    """Make an open issue that links no spec (a draft, an issue from the BA) a record of this kind,
    as create makes a new one: its type, parent, blockers, and the spec at path with its title. Without a
    path it becomes a draft. A draft that gets its spec is one no more, and my claim for its spec work goes back."""
    have = spec_of(repo_name, n, run)
    if have:
        return False, f"#{n} already links {have}"
    v = _view(repo_name, n, run)
    if v.get("state") != "OPEN":
        return False, f"#{n} is closed"
    labels = {l["name"] for l in v.get("labels", [])}
    was = next((t for t in TYPES if f"pulse:{t}" in labels), kind)
    if was != kind:
        return False, f"#{n} has the type {was}, not {kind}"
    if path:
        _set_line(root, repo_name, n, SPEC, f"Spec: `{path}`", run)
    add = [l for l in (f"pulse:{kind}", None if path else DRAFT) if l and l not in labels]
    edit = (["--title", title] if path and title else []) + (["--add-label", ",".join(add)] if add else []) + \
        (["--remove-label", DRAFT] if path and DRAFT in labels else []) + \
        (["--parent", str(parent)] if parent else []) + \
        (["--add-blocked-by", ",".join(map(str, blocked_by))] if blocked_by else [])
    if edit:
        run(["issue", "edit", str(n), "--repo", repo_name, *edit])
    if path and DRAFT in labels and me(root, run=run) in [a["login"] for a in v.get("assignees", [])]:
        release(root, repo_name, n, run=run, who=who, take=True)
    drop_cache(root)
    return True, f"#{n} links {path}" if path else f"#{n} is a draft"


def done(root: Path, repo_name: str, n: int, run=gh, who=None, take=False) -> tuple:
    """Close the item; `take` closes it whoever holds it (a merged pull request, a person's call)."""
    if not take:
        v = _view(repo_name, n, run)
        other = _other_session(v, who or holder())
        whom = _others(v, me(root, run=run)) or (_name(other) if other else "")
        if whom:
            return False, f"#{n} is held by {whom}; to close it all the same: pulse done {n} --take"
    run(["issue", "close", str(n), "--repo", repo_name, "--reason", "completed"])
    drop_cache(root)
    return True, f"closed #{n}"
