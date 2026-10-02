"""Issue identity and cached board views, overlaid with canonical shared workflow state.

Claims, holds, result bindings and approvals live on the shared state branch.
Issue comments authenticate person intent and preserve legacy history only.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import math
import os
import posixpath
import random
import re
import shlex
import subprocess
import stat
import time
import uuid
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from pathlib import Path

from pulse import config

TTL = 30                 # refresh issue structure; canonical state is read independently
POLL = 2                 # seconds between the free conditional checks for a change
FORMAT = 18              # of the issue cache, raised when an item gains a field or load attaches differently
# ponytail: comments ride along only for the claim marks (who holds an item, since when); a repo
# with long issue threads pays for them in every full reload
FIELDS = "number,title,state,labels,assignees,parent,blockedBy,blocking,body,url,updatedAt,comments,author"
TYPES = ("epic", "feat", "imp", "fix")
WORK = ("feat", "imp", "fix")          # epics are containers, never picked up
APPROVED = "pulse:approved"            # a person wants it built
LEGACY_READY = "pulse:ready"           # the same label before 2026-09
PLAN_OK = "pulse:plan-ok"              # before #115: an old Plan-ok line of 12 characters counts with it
DRAFT = "pulse:draft"                  # a record without a spec yet: BA or RE works on it
HOLD = "pulse:hold"                    # a person holds it: pulse go neither plans nor builds it (#111)
FAIL = "pulse:failed"                  # pulse go gave up on it: no run takes it again until pulse approve (#114)
BASE = "pulse:base"                    # it fixes a red base: pulse go plans and builds it on one too (#113)
WRITERS = {"OWNER", "MEMBER", "COLLABORATOR"}     # may push; anyone may comment on a public issue or PR
CLAIMING = 10 * 60         # seconds a mark of someone not assigned may be a claim in flight (#77)
WAIT = 3                   # seconds a claim waits for such a claim's assignee to show
SPEC = re.compile(r"^Spec: `([^`]+)`(?: \(PR #(\d+)\))?", re.M)     # the docs PR that brings it (#116)
PLAN_OK_LINE = re.compile(r"^Plan-ok:[ \t]*([0-9a-f]+)(?:[ \t]+([0-9a-f]+))?[ \t]*$", re.M)  # PLAN and spec blob
PLAN_SAID = re.compile(r"^plan ok at ([0-9a-f]{40,64}) ([0-9a-f]{40,64})\b")    # who approved them: gate 2 (#115)
MERGE_SAID = re.compile(r"^merge ok at ([0-9a-f]{40,64})\b")      # a person's gate 3 for a PR head (#118)
GATE1_SAID = re.compile(r"^gate 1 ok at ([0-9a-f]{40,64}) (.+?): gate 1 approved by ")    # docs PR head, spec path
REMOTE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")
MARK = re.compile(r"<!-- pulse:claim (\{.*?\}) -->")
NOTE = re.compile(r"<!-- pulse:note (\{.*?\}) -->")
TAKE = "Released from {} by {} with pulse release --take {}."      # a person's release --take says so on the item
# and taken reads it (#84): a login holds no space or comma, so a comment anyone wrote is read in linear time
TAKEN = re.compile(r"{}([^\s,]+(?:, [^\s,]+)*){}\S+{}\d+{}".format(*map(re.escape, TAKE.split("{}"))))
COMMENT = re.compile(r"#issuecomment-(\d+)$")
ITEM_BRANCH = re.compile(r"^(?:feat|imp|fix)/(\d+)-")        # how pulse names an item's branch
# what tells a hook where its chat runs; a headless job of pulse go has no chat (#61)
SURFACE = ("CLAUDE_CODE_ENTRYPOINT", "CODEX_INTERNAL_ORIGINATOR_OVERRIDE")
TAIL = 256 * 1024          # the end of a Codex rollout that ran_in reads
SHELL = {"exec_command", "shell", "shell_command"}
WORKDIR = re.compile(r"""\bworkdir["']?\s*:\s*["']([^"']+)["']""")


class StateError(Exception):
    pass


class RateLimitError(StateError):
    def __init__(self, resource: str, retry_at: float, source="backoff"):
        self.resource, self.retry_at, self.source = resource, retry_at, source
        when = time.strftime("%H:%M:%S UTC", time.gmtime(retry_at))
        super().__init__(f"GitHub API rate limit ({resource}); retry after {when}")


def _gh_route(args):
    host = os.environ.get("GH_HOST") or "github.com"
    for index, arg in enumerate(args):
        if arg == "--hostname" and index + 1 < len(args):
            host = args[index + 1]
        if arg.startswith("--hostname="):
            host = arg.split("=", 1)[1]
        if arg in ("--repo", "-R") and index + 1 < len(args):
            named = args[index + 1].removeprefix("https://").split("/")
            if len(named) >= 3:
                host = named[0]
    if args[:1] != ["api"]:
        read = args[:2] in (["issue", "list"], ["issue", "view"], ["pr", "list"], ["pr", "view"])
        return host.lower(), "graphql", read
    endpoint, method, fields, known = "", "", False, True
    values = {"--hostname", "--jq", "-q", "--template", "-t", "--header", "-H", "--cache",
              "--method", "-X", "--field", "-F", "--raw-field", "-f", "--input"}
    flags = {"--include", "-i", "--paginate", "--slurp", "--silent"}
    index = 1
    while index < len(args):
        arg, equal, value = args[index].partition("=")
        if arg in values:
            if not equal:
                index += 1
                value = args[index] if index < len(args) else ""
            if arg in ("--method", "-X"):
                method = value.upper()
            fields |= arg in ("--field", "-F", "--raw-field", "-f", "--input")
        elif arg in flags:
            pass
        elif arg.startswith("-") or endpoint:
            known = False
        else:
            endpoint = args[index]
        index += 1
    resource = "graphql" if endpoint == "graphql" else "search" if endpoint.startswith("search/") else "core"
    read = known and bool(endpoint) and resource != "graphql" and (method == "GET" or not method and not fields)
    return host.lower(), resource, read


def _rate_key(host):
    conf = Path(os.environ.get("GH_CONFIG_DIR") or
                Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "gh")
    names = ("GH_TOKEN", "GITHUB_TOKEN") if host == "github.com" or host.endswith(".ghe.com") else \
        ("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
    token = next((os.environ[name] for name in names if os.environ.get(name)), "")
    if token:
        account = "token:" + hashlib.sha256(token.encode()).hexdigest()
    else:
        found = subprocess.run(["gh", "config", "get", "user", "--host", host],
                               capture_output=True, text=True, timeout=5)
        account = "user:" + found.stdout.strip() if not found.returncode and found.stdout.strip() else str(conf.resolve())
    return hashlib.sha256(f"{host}\0{account}".encode()).hexdigest()


def _private(fd, directory=False):
    info = os.fstat(fd)
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise StateError("unsafe GitHub rate-limit cache permissions")
    return fd


@contextmanager
def _rate_cache(key):
    folder = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    if not folder.is_absolute():
        raise StateError("GitHub rate-limit cache requires an absolute cache directory")
    folder.mkdir(parents=True, exist_ok=True)
    directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = None
    try:
        for part in ("pulse", "rate-limits"):
            try:
                os.mkdir(part, 0o700, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            _private(directory, directory=True)
        try:
            lock = os.open(key + ".lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=directory)
        except FileExistsError:
            lock = os.open(key + ".lock", os.O_RDWR | os.O_NOFOLLOW, dir_fd=directory)
        _private(lock)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            opened = os.open(key + ".json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            data = {}
        else:
            with os.fdopen(opened, encoding="utf-8") as saved:
                _private(saved.fileno())
                data = json.loads(saved.read(65537))
            if not isinstance(data, dict) or any(
                resource not in ("graphql", "core", "search", "all") or not isinstance(entry, dict) or
                type(entry.get("retry_at")) not in (int, float) or not math.isfinite(entry["retry_at"]) or
                not 0 < entry["retry_at"] <= time.time() + 7 * 86400 or
                type(entry.get("attempt")) is not int or not 1 <= entry["attempt"] <= 5 or
                entry.get("source") not in ("reset", "retry-after", "backoff")
                for resource, entry in data.items()
            ):
                raise StateError("invalid GitHub rate-limit cache")
        yield directory, data
    finally:
        if lock is not None:
            os.close(lock)
        os.close(directory)


def _save_rate(directory, key, data):
    temporary = f".{key}.{os.getpid()}.{os.urandom(8).hex()}"
    opened = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(opened, "w", encoding="utf-8") as saved:
            json.dump(data, saved)
        os.replace(temporary, key + ".json", src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def _rate_failure(out, host, resource, previous, timeout):
    message = out.stdout + "\n" + out.stderr
    headers = dict((name.lower(), value.strip()) for name, value in
                   re.findall(r"^([\w-]+):[ \t]*(.*?)\r?$", message, re.M))
    secondary = bool(re.search(r"secondary rate limit|abuse detection|HTTP[^\n]*\b429\b", message, re.I))
    if not (secondary or re.search(r"rate limit (?:already )?exceeded", message, re.I) or
            headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers):
        return None
    resource = "all" if secondary else headers.get("x-ratelimit-resource", resource)
    if resource not in ("graphql", "core", "search", "all"):
        resource = "all"
    now, deadline, source = time.time(), 0, "backoff"
    for header, kind in (("x-ratelimit-reset", "reset"), ("retry-after", "retry-after")):
        value = headers.get(header, "")
        try:
            candidate = float(value) + (now if kind == "retry-after" else 0)
        except ValueError:
            try:
                candidate = parsedate_to_datetime(value).timestamp() if kind == "retry-after" else 0
            except (ValueError, TypeError, OverflowError):
                candidate = 0
        if math.isfinite(candidate) and max(deadline, now) < candidate <= now + 7 * 86400:
            deadline, source = candidate, kind
    if not deadline and not secondary:
        try:
            probe = subprocess.run(["gh", "api", "rate_limit", "--hostname", host],
                                   capture_output=True, text=True, timeout=min(timeout, 10))
            limits = json.loads(probe.stdout).get("resources", {}).get(resource, {}) if not probe.returncode else {}
            reset = limits.get("reset")
            if limits.get("remaining") == 0 and type(reset) in (int, float) and math.isfinite(reset) and \
                    now < reset <= now + 7 * 86400:
                deadline, source = reset, "reset"
        except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
            pass
    attempt = min(previous.get(resource, {}).get("attempt", 0) + 1, 5)
    return resource, {"retry_at": deadline or now + min(60 * 2 ** (attempt - 1), 900),
                      "attempt": attempt, "source": source}


def item_of(branch):
    """The item a branch builds; any branch pulse did not name <type>/<n>-<slug> is no item's."""
    m = ITEM_BRANCH.match(branch or "")
    return int(m.group(1)) if m else None


def _tail(path) -> list:
    """The lines in the last TAIL bytes of a transcript or rollout; [] when it cannot be read."""
    try:
        with open(path or "", "rb") as f:
            start = max(0, f.seek(0, 2) - TAIL)
            f.seek(start)
            return f.read().decode("utf-8", "replace").split("\n")[1 if start else 0:]   # a cut first line
    except (OSError, TypeError, ValueError):
        return []


def ran_in(payload: dict) -> str:
    """Where a Codex command ran: its hook names the session's directory, the workdir of the call
    stands only in its rollout (transcript_path). The last shell call there; '' when none says."""
    for line in reversed(_tail(payload.get("transcript_path"))):
        try:                                   # Codex's format: a line of another shape is skipped
            item = json.loads(line)["payload"]
            if item["type"] == "function_call" and item["name"] in SHELL:
                wd = json.loads(item["arguments"]).get("workdir")
            elif item["type"] == "custom_tool_call" and item["name"] != "apply_patch" \
                    and "exec_command" in item["input"]:
                # ponytail: code mode may call exec_command more than once; the last workdir stands for all
                found = WORKDIR.findall(item["input"])
                if "workdir" in item["input"] and not found:
                    return ""                  # a workdir it computes: the place stays as it was
                wd = found[-1] if found else None
            else:
                continue
            cwd = payload.get("cwd") or ""
            return os.path.join(cwd, wd) if wd else cwd
        except (ValueError, LookupError, TypeError, AttributeError, RecursionError):
            continue
    return ""


def gh(args: list, timeout=60) -> str:
    try:
        if args in (["--version"], ["repo", "set-default", "--view"]):
            local = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
            if local.returncode:
                raise StateError(f"gh {' '.join(args[:2])}: {local.stderr.strip() or local.stdout.strip()}")
            return local.stdout
        host, resource, read = _gh_route(args)
        key = _rate_key(host)
        with _rate_cache(key) as (directory, cooldowns):
            for limited, entry in cooldowns.items():
                if not read or limited in (resource, "all") and entry["retry_at"] > time.time():
                    raise RateLimitError(limited, entry["retry_at"], entry["source"])
            out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
            if out.returncode != 0:
                failure = _rate_failure(out, host, resource, cooldowns, timeout)
                if failure:
                    limited, entry = failure
                    _save_rate(directory, key, {**cooldowns, limited: entry})
                    raise RateLimitError(limited, entry["retry_at"], entry["source"])
                raise StateError(f"gh {' '.join(args[:2])}: {out.stderr.strip() or out.stdout.strip()}")
            if read and (resource in cooldowns or "all" in cooldowns):
                _save_rate(directory, key, {name: entry for name, entry in cooldowns.items()
                                            if name not in (resource, "all")})
    except subprocess.TimeoutExpired:
        raise StateError(f"gh {' '.join(args[:2])}: no answer within {timeout} s") from None
    except (OSError, ValueError) as error:
        raise StateError(f"GitHub rate-limit cache unavailable: {error}") from None
    return out.stdout


def repo(root: Path, run=gh) -> str:
    """owner/name to act on. Never guessed when several GitHub remotes exist."""
    pinned = config.clone_config(root)["repo"]
    if pinned:
        return pinned
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


WRITE = ("admin", "maintain", "write")    # the permissions that may push; GitHub names maintain as write
LOGIN = re.compile(r"[A-Za-z0-9_-]+")       # a person's login; an Enterprise Managed User's is handle_shortcode


def can_push(repo_name: str, login: str, run=gh) -> bool:
    """Whether login may push to the repository, as GitHub answers now; a login GitHub never gives may not.
    Without an answer (an error, the rate limit, the 403 GitHub gives a gh user who cannot push) gh's
    StateError passes through: then nobody knows."""
    if not LOGIN.fullmatch(login or ""):
        return False
    said = run(["api", f"repos/{repo_name}/collaborators/{login}/permission", "--jq", ".permission"])
    return said.strip() in WRITE


def pusher(repo_name: str, login: str, run, known: dict) -> bool:
    """Whether login may push, asked once per login (known, as writer() keeps it); without an answer, no (#115)."""
    if login not in known:
        try:
            known[login] = can_push(repo_name, login, run)
        except (StateError, OSError) as e:
            known[login] = str(e) or type(e).__name__
    return known[login] is True


def pages(run, path: str) -> list:
    """Every entry of a REST list over all its pages: gh writes one JSON array per page."""
    text, dec, k, out = run(["api", "--paginate", path]).strip(), json.JSONDecoder(), 0, []
    while k < len(text):
        page, k = dec.raw_decode(text, k)
        out += page if isinstance(page, list) else []
        k = len(text) - len(text[k:].lstrip())
    return out


def complete_comments(repo, raw, run=gh):
    """Complete a capped thread and normalize REST/GraphQL authors and edit metadata."""
    comments = raw.get("comments") or []
    original = {entry["url"]: entry for entry in comments if entry.get("url")}
    viewer = next(((entry.get("author") or {}).get("login") for entry in comments
                   if entry.get("viewerDidAuthor")), None)
    if len(comments) >= 100 and not raw.get("_comments_complete"):
        comments = pages(run, f"repos/{repo}/issues/{raw['number']}/comments?per_page=100")
        if not viewer and any(MARK.match(entry.get("body") or "") for entry in comments):
            viewer = run(["api", "user", "--jq", ".login"]).strip()
    normalized = []
    for entry in comments:
        url = entry.get("html_url") or entry.get("url")
        author = entry.get("user") or entry.get("author") or {}
        created = entry.get("created_at") or entry.get("createdAt")
        updated = entry.get("updated_at") or entry.get("updatedAt")
        comment = {**original.get(url, {}), **entry, "url": url, "author": author, "createdAt": created,
                   "authorAssociation": entry.get("author_association", entry.get("authorAssociation"))}
        comment["edited"] = bool(comment.get("edited") or comment.get("includesCreatedEdit") or
                                 comment.get("lastEditedAt") or updated not in (None, created))
        if viewer:
            comment["viewerDidAuthor"] = author.get("login") == viewer
        normalized.append(comment)
    return {**raw, "comments": normalized, "_comments_complete": True}


def labelers(repo_name: str, n: int, run=gh) -> dict:
    """{label: the login that added it last} for every label n carries, from its events, oldest first (#115):
    GitHub keeps who set a label, which the issue itself does not say."""
    out = {}
    for e in pages(run, f"repos/{repo_name}/issues/{n}/events?per_page=100"):
        name = (e.get("label") or {}).get("name")
        if e.get("event") == "labeled":
            out[name] = (e.get("actor") or {}).get("login") or ""
        elif e.get("event") == "unlabeled":
            out.pop(name, None)
    return out


def item(repo_name: str, n: int, run=gh) -> dict:
    """Issue n as normalize reads it, from GitHub now."""
    raw = json.loads(run(["issue", "view", str(n), "--repo", repo_name, "--json",
                         "number,title,labels,body,comments,assignees,url,author"]))
    known = {}
    trusted = lambda entry: writer(entry, repo_name, run, known)
    return normalize(complete_comments(repo_name, raw, run), lambda entry: trusted(entry) is True,
                     lifecycle_trusted=trusted)


def writer(comment: dict, repo_name: str, run, known: dict):
    """Whether the author of a comment may push (#74): True for the owner at once, and for a member or a
    collaborator (GitHub calls readers so too) once can_push says so; False for anyone else; GitHub's
    reason when it gave no answer: then the verdict counts for nothing, and no older one counts in its place.
    known holds the answers of one read or event (login: True, False, or that reason), so each author is asked
    once."""
    who, login = comment.get("authorAssociation"), (comment.get("author") or {}).get("login") or ""
    if who == "OWNER" or who not in WRITERS:
        return who == "OWNER"
    if login not in known:
        try:
            known[login] = can_push(repo_name, login, run)
        except (StateError, OSError) as e:
            known[login] = str(e) or type(e).__name__
    return known[login]


def _owner(comment: dict) -> bool:
    return comment.get("authorAssociation") == "OWNER"


def pushers(repo_name: str, run=gh):
    """comment -> whether its author may push (writer), each login asked once: GitHub calls readers MEMBER or
    COLLABORATOR too (#89)."""
    known = {}
    return lambda comment: writer(comment, repo_name, run, known) is True


def _plan_ok(labels: list, body: str):
    """[the blob of the PLAN, the blob of the spec] a Plan-ok line names (#115), [its digest, None] for an old line
    of 12 characters with its label; None without one."""
    m = PLAN_OK_LINE.search(body)
    return list(m.groups()) if m and (m.group(2) or PLAN_OK in labels) else None


def normalize(issue: dict, trusted=_owner, lifecycle_trusted=None) -> dict:
    """The record of an issue; trusted(comment) says whether its author may push, for a note (#89)."""
    from pulse import lifecycle
    labels = [l["name"] for l in issue.get("labels", [])]
    operation = lifecycle.operation(issue, lifecycle_trusted or trusted)
    kind = next((t for t in TYPES if f"pulse:{t}" in labels), None)
    spec = SPEC.search(issue.get("body") or "")
    assignees = [a["login"] for a in issue.get("assignees", [])]
    marks = _marks(issue)
    mark = next((m for m in marks if m["author"] in assignees), None)     # the oldest holds it
    last = max((m["at"] for m in marks), default="")      # a note from before the last claim is that holder's past
    note = next((c for c in reversed(issue.get("comments") or []) if NOTE.match(c.get("body") or "")
                 and (c.get("createdAt") or "") > last and (c.get("viewerDidAuthor")
                                                        or (c.get("author") or {}).get("login") in assignees
                                                        or trusted(c))),
                None)          # a note steers the next holder; the newest first, so few authors are asked
    return {
        "number": issue["number"],
        "title": issue["title"],
        "type": kind,
        "approved": APPROVED in labels or LEGACY_READY in labels,
        "plan_ok": _plan_ok(labels, issue.get("body") or ""),
        "author": (issue.get("author") or {}).get("login") or "",      # may edit the body, the Plan-ok line too
        "plan_oks": [{"blobs": list(m.groups()), "author": c.get("author") or {},            # gate 2 by whom (#115)
                      "authorAssociation": c.get("authorAssociation")}
                     for c in issue.get("comments") or [] for m in [PLAN_SAID.match(c.get("body") or "")] if m],
        "merge_oks": [{"sha": m.group(1), "author": c.get("author") or {},                     # gate 3 (#118)
                       "authorAssociation": c.get("authorAssociation")}
                      for c in issue.get("comments") or [] for m in [MERGE_SAID.match(c.get("body") or "")] if m],
        "gate1_oks": [{"head": m.group(1), "path": m.group(2), "author": c.get("author") or {},   # gate 1 at (M-1)
                       "authorAssociation": c.get("authorAssociation")}
                      for c in issue.get("comments") or [] for m in [GATE1_SAID.match(c.get("body") or "")] if m],
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
        "hold": HOLD in labels or bool(operation and operation.get("phase") != "resumed"),
        "lifecycle": operation,
        "failed": FAIL in labels,
        "base_fix": BASE in labels,
        "priority": next((k for k in range(3) if f"P{k}" in labels), 3),    # P0 to P2 (#116); none after P2 (#119)
        "parent": (issue.get("parent") or {}).get("number"),
        "blocked_by": [n["number"] for n in (issue.get("blockedBy") or {}).get("nodes", [])
                       if n.get("state") == "OPEN"],
        "blocking": [n["number"] for n in (issue.get("blocking") or {}).get("nodes", [])
                     if n.get("state") == "OPEN"],
        "edges": [[n["number"], n.get("title") or ""] for n in (issue.get("blockedBy") or {}).get("nodes", [])],
        "spec": spec.group(1) if spec else None,
        "pr": None,            # historical compatibility; PRs no longer steer workflow
        "approval": None, "result": None, "revision": "", "shared_revision": "",
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
    GitHub replaces the whole body, so a concurrent write of another line (spec against a Plan-ok)
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


def spec_line(path: str, pr=None) -> str:
    return f"Spec: `{path}`" + (f" (PR #{pr})" if pr else "")


def set_spec(root: Path, repo_name: str, n: int, path: str, run=gh) -> None:
    """The record links its spec at a new path (pulse number renamed it once the base branch had it, so its
    docs PR is merged and the line names it no more)."""
    _set_line(root, repo_name, n, SPEC, spec_line(path), run)


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


def changed(repo_name: str, etag: str, run=gh) -> tuple:
    """(changed, etag): did any issue or pull request move since etag? GitHub answers an
    unchanged state with 304, which does not count against the rate limit."""
    args = ["api", "-i", f"repos/{repo_name}/issues?state=all&sort=updated&direction=desc&per_page=1"]
    if etag:
        args[2:2] = ["-H", f"If-None-Match: {etag}"]
    try:
        out = run(args)
    except RateLimitError:
        raise
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


def load(root: Path, repo_name: str, run=gh, fresh: bool = False, ttl: float = TTL, *, order_info=None) -> list:
    """All open issues, normalized. Every POLL seconds a free check whether anything moved;
    a full reload only on a change, or after ttl (a waiting pulse go: 300, #119).
    order_info, when supplied, receives the shared order and conflicts even on an empty board."""
    from pulse import order

    def loaded(items, seen, threads=None):
        if order_info is not None:
            order_info.clear()
            order_info.update({**seen, "positions": {int(number): position
                                                    for number, position in seen["positions"].items()}})
        items = _overlay(root, items)
        from pulse import review
        authors = {}
        for item in items:
            result = item.get("result")
            if result:
                item.update(review.result_reports(root, item["number"], result["head"],
                    thread=threads.get(item["number"]) if threads is not None else None,
                    repo_name=repo_name, run=run, known=authors, cached=item.get("reports")))
            else:
                for key in ("reports", "findings", "missing"):
                    item.pop(key, None)
        # The last displayed bindings are available to a later local CLI action.
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            _keep(path, {**saved, "items": items})
        except (OSError, ValueError):
            pass
        return items

    path, now = cache_path(root), time.time()
    if not fresh and path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
        if cached.get("repo") == repo_name and cached.get("format") == FORMAT and "order" in cached:
            if now - max(cached.get("fetched_at", 0), cached.get("checked_at", 0)) < POLL:
                return loaded(cached["items"], cached["order"])
            if now - cached.get("fetched_at", 0) < ttl:
                moved, _ = changed(repo_name, cached.get("etag", ""), run)
                if not moved:
                    _keep(path, {**cached, "checked_at": now})
                    return loaded(cached["items"], cached["order"])
    _, etag = changed(repo_name, "", run)
    raw = json.loads(run(["issue", "list", "--repo", repo_name, "--state", "open",
                          "--limit", "1000", "--json", FIELDS]))
    raw = [complete_comments(repo_name, record, run) for record in raw]
    known = {}
    trusted = lambda entry: writer(entry, repo_name, run, known)
    seen = order.read(raw, trusted)
    items = [normalize(record, lambda entry: trusted(entry) is True, lifecycle_trusted=trusted) for record in raw
             if order.LABEL not in [label["name"] for label in record.get("labels", [])]]
    if seen["issue"] is not None or seen["why"]:
        for record in items:
            record.update(manual_position=seen["positions"].get(record["number"]),
                          order_revision=seen["revision"], order_issue=seen["issue"], order_conflict=seen["why"])
    _keep(path, {"repo": repo_name, "format": FORMAT, "fetched_at": now, "checked_at": now, "etag": etag,
                 "items": items, "order": seen})
    return loaded(items, seen, {record["number"]: record for record in raw})


def _overlay(root, entries):
    from pulse import auto, shared
    revision, snapshot = shared.read(root)
    policy = shared.policy(snapshot)
    try:
        auto._cache(root, policy)
    except StateError:
        pass                                # a read-only board still shows its fresh canonical state
    rows = []
    for original in entries:
        if original["number"] == (policy.get("proof") or {}).get("issue") or (
                original.get("title") == auto.CONTROL and not original.get("type")):
            continue
        entry = dict(original)
        current = snapshot["items"].get(str(entry["number"]))
        if current is None:
            entry.update(approval=None, result=None, revision="", shared_revision="",
                         migration_required=bool(entry.get("claimed_by") or entry.get("hold") or entry.get("failed")))
        else:
            claim = current.get("claim") or {}
            entry.update({key: current.get(key) for key in
                          ("revision", "result", "approval", "claim", "stop", "work", "removal", "revoked")})
            entry.update(shared_revision=revision, migration_required=False, hold=current["hold"],
                         failed=current.get("failed", False), failure=current.get("failure", ""),
                         claimed_holder=claim.get("session") or claim.get("holder"), claim_token=claim.get("holder"),
                         claimed_by=claim.get("actor") or claim.get("holder"), claimed_files=claim.get("files", []),
                         claimed_phase=(current.get("work") or {}).get("phase"),
                         assignees=[claim["actor"]] if claim.get("actor") else [], done=current["done"])
            stop = current.get("stop") or {}
            entry["lifecycle"] = {"action": "defer", "phase": "requested" if stop.get("status") == "requested"
                                  else "paused" if current["hold"] else "resumed", "work": stop.get("work") or {}} \
                if stop or current["hold"] else None
        rows.append(entry)
    return rows


def _action_body(operation):
    payload = {key: value for key, value in operation["payload"].items() if key != "proof"}
    if operation["kind"] == "approve":
        if set(payload) != {"head", "base"}:
            raise StateError("integration approval needs the displayed head and base")
        value = {"operation": operation["id"], "item": operation["item"], **payload}
        prefix = "pulse integration approval "
    else:
        value = {"operation": operation["id"], "item": operation["item"], "kind": operation["kind"],
                 "expected": operation["expected"], "payload": payload}
        prefix = "pulse action "
    return prefix + json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _action_proof(repo_name, operation, actor, run, *, issue=None, body=None):
    issue = operation["item"] if issue is None else issue
    body = _action_body(operation) if body is None else body
    comments = pages(run, f"repos/{repo_name}/issues/{issue}/comments?per_page=100")
    matches = []
    for comment in comments:
        text = comment.get("body") or ""
        prefix = next((p for p in ("pulse integration approval ", "pulse action ", "pulse final approval policy ")
                       if text.startswith(p)), None)
        try:
            value = json.loads(text[len(prefix):]) if prefix else {}
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get("operation") == operation["id"]:
            matches.append(comment)
    if len(matches) > 1:
        raise StateError("action has ambiguous person proofs")
    comment = matches[0] if matches else json.loads(run(
        ["api", "-X", "POST", f"repos/{repo_name}/issues/{issue}/comments", "-f", "body=" + body]))
    ident = comment.get("id")
    if type(ident) is not int or ident < 1:
        raise StateError("action comment has no authenticated identity")
    comment = json.loads(run(["api", f"repos/{repo_name}/issues/comments/{ident}"]))
    user = comment.get("user") or {}
    if comment.get("id") != ident or comment.get("issue_url") != \
            f"https://api.github.com/repos/{repo_name}/issues/{issue}" or \
            user.get("login") != actor or user.get("type", "User") != "User" or \
            not comment.get("created_at") or comment.get("updated_at") != comment["created_at"] or \
            any(comment.get(key) for key in ("edited", "lastEditedAt", "includesCreatedEdit")) or \
            comment.get("body") != body:
        raise StateError("action person proof was edited or does not match this item and intent")
    return {"comment": ident, "author": actor, "operation": operation["id"]}


def sync_action(root, operation, run=None):
    """Authenticate durable person intent, then apply exactly its stable operation."""
    from pulse import auto, shared
    run = gh if run is None else run
    factual = operation.get("kind") == "stopped"
    if not factual and (not holder()["id"].startswith("terminal:") or not auto.person(os.environ, True)):
        raise StateError("person actions cannot be synchronized from an agent source")
    if operation.get("kind") not in {"defer", "resume", "approve", "revoke", "handoff", "stopped", "policy"}:
        raise StateError("unknown person action")
    shared._operation(operation)
    repo_name = repo(root, run=run)
    actor = run(["api", "user", "--jq", ".login"]).strip()
    if not can_push(repo_name, actor, run):
        raise StateError("repository push permission is required")
    if operation["kind"] == "policy":
        proof = auto.proof(root, repo_name, operation, actor, run)
        receipt = shared.update(root, {**operation, "payload": {**operation["payload"], "proof": proof}})
        auto._cache(root, shared.policy(shared.read(root)[1]))
        return receipt
    if factual:
        _, snapshot = shared.read(root)
        token = operation["payload"].get("holder")
        claims = [(record["result"]["data"].get("claim") or {}) for record in snapshot["operations"].values()
                  if record["operation"]["item"] == operation["item"]]
        if not any(claim.get("holder") == token and claim.get("actor") == actor for claim in claims):
            raise StateError("stop acknowledgement requires its original writer account and claim generation")
        saved = snapshot["operations"].get(operation["id"])
        if saved:
            prior = saved["operation"]
            if any(prior[key] != operation[key] for key in ("item", "kind", "payload")):
                raise StateError("stop acknowledgement identity changed")
            return shared.update(root, prior)
        current = snapshot["items"].get(str(operation["item"]), {})
        # This factual acknowledgement grants no new work: matching the unique
        # stopped generation remains mandatory, including across a replacement.
        return shared.update(root, {**operation, "expected": current.get("revision", "")})
    proof = _action_proof(repo_name, operation, actor, run)
    _, snapshot = shared.read(root)
    current = snapshot["items"].get(str(operation["item"]))
    if current is None:
        entries = load(root, repo_name, run=run, fresh=True)
        _migrate(root, repo_name, [entry for entry in entries if entry["number"] == operation["item"]], run)
        # Migration may advance the revision. The original expectation then
        # conflicts visibly; legacy reservations and holds stay preserved.
    elif operation["kind"] == "resume" and operation["id"] not in snapshot["operations"] and \
            operation["expected"] == current["revision"]:
        from pulse import lifecycle
        stop = current.get("stop") or {}
        work = stop.get("work") or {}
        if stop.get("status") == "completed" and work:
            claims = [(record["result"]["data"].get("claim") or {})
                      for record in snapshot["operations"].values()
                      if record["operation"]["item"] == operation["item"] and
                      record["result"]["status"] == "confirmed"]
            owners = {claim["actor"] for claim in claims
                      if claim.get("holder") == stop.get("holder") and claim.get("actor")}
            lifecycle._resume_work(root, {"work": work, "retained": not work.get("remote"),
                "holder": {"author": next(iter(owners)) if len(owners) == 1 else ""}}, actor)
    receipt = shared.update(root, {**operation, "payload": {**operation["payload"], "proof": proof}})
    drop_cache(root)
    return receipt


def me(root: Path, run=gh, ttl=60) -> str:
    """My GitHub login, kept with the caches ttl seconds or until gh logs in anew (its hosts file): a minute, so a
    gh auth switch shows within one (#111). The hooks ask no network and take it for longer. It counts only for
    the gh config dir and token that asked (a key of both, never the token): a map with a colleague's GH_TOKEN
    in the same clone keeps his login apart (#111 B-1). A cache without a key, as an older Pulse wrote it, counts."""
    path = cache_dir(root) / "me"
    conf = os.environ.get("GH_CONFIG_DIR") or \
        os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "gh")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    key = hashlib.sha256(f"{conf}\0{token}".encode()).hexdigest()[:12]
    try:
        login_at = os.stat(os.path.join(conf, "hosts.yml")).st_mtime
    except OSError:
        login_at = 0
    try:
        kept = path.stat().st_mtime
        login, _, whose = path.read_text(encoding="utf-8").partition("\n")
        if kept > login_at and time.time() - kept < ttl and whose.strip() in ("", key):
            return login.strip()
    except OSError:
        pass
    login = run(["api", "user", "--jq", ".login"]).strip()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{login}\n{key}\n", encoding="utf-8")
    except OSError:
        pass                   # asked again next time
    return login


def who(root: Path, login=None, run=gh) -> str:
    """The person as every surface of Pulse names them (#111): `Klarname (@login)`, the name from git config
    user.name, the login given, else from me(); the name alone without a login, @login alone without a name."""
    name = subprocess.run(["git", "-C", str(root), "config", "user.name"], capture_output=True,
                          text=True).stdout.strip()
    if login is None:
        try:
            login = me(root, run=run)
        except StateError:
            login = ""
    return f"{name} (@{login})" if name and login else name or (f"@{login}" if login else "")


def blocked(items: list) -> list:
    return [i for i in items if i["blocked_by"]]


def create(root: Path, repo_name: str, kind: str, title: str, parent=None, blocked_by=(),
           spec=None, body="", run=gh, draft=False, pr=None, labels=()) -> int:
    if kind not in TYPES:
        raise StateError(f"type must be one of {', '.join(TYPES)}")
    text = (spec_line(spec, pr) + "\n\n" if spec else "") + body
    args = ["issue", "create", "--repo", repo_name, "--title", title,
            "--label", f"pulse:{kind}", "--body", text or title]
    for label in ([DRAFT] if draft else []) + list(labels):
        args += ["--label", label]
    if parent:
        args += ["--parent", str(parent)]
    if blocked_by:
        args += ["--blocked-by", ",".join(map(str, blocked_by))]
    url = run(args).strip().splitlines()[-1]
    drop_cache(root)
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def approve(root: Path, repo_name: str, n: int, gate: int, blobs=(), run=gh, by=None) -> dict:
    """Accept final head/base approval using the already displayed board revision."""
    from pulse import actions
    if gate != 3 or len(blobs) != 2:
        raise StateError("only final integration approval exists; show the result and base first")
    observed = next((entry for entry in cached(root) if entry["number"] == n), None)
    if not observed or not observed.get("revision"):
        raise StateError("read the current result before approving integration")
    accepted = actions.submit(root, n, "approve", dict(zip(("head", "base"), blobs)), observed["revision"])
    actions.start(root)
    return accepted


def _view(repo_name, n, run):
    raw = json.loads(run(["issue", "view", str(n), "--repo", repo_name,
                         "--json", "state,body,labels,assignees,blockedBy,comments,parent"]))
    return complete_comments(repo_name, {**raw, "number": n}, run)


def holder(env=None) -> dict:
    """Who claims: the run of pulse go that started this agent, else the agent session, else a terminal:
    its session on this host (one per terminal window, tab, or tmux pane; a script and all it starts)."""
    env = os.environ if env is None else env
    try:
        given = json.loads(env.get("PULSE_HOLDER") or "null")
        if isinstance(given, dict) and given.get("id"):
            return {"id": str(given["id"]), "claims": dict(given.get("claims") or {})}
    except ValueError:
        pass
    for kind, var in (("codex", "CODEX_THREAD_ID"), ("claude", "CLAUDE_CODE_SESSION_ID")):
        if env.get(var):       # Codex first: a Codex started from a Claude shell inherits Claude's id
            return {"id": f"{kind}:{env[var]}"}
    return {"id": f"terminal:{os.uname().nodename}:{os.getsid(0)}"}


def run_holder(root: Path) -> dict:
    """pulse go's holder: go:<clone>:<pid>, the clone as 8 hex of its shared git dir. The next run in this clone
    knows its marks by the prefix and takes over those whose PR waits for a merge (#118)."""
    return {"id": f"{clone_prefix(root)}{os.getpid()}"}


def clone_prefix(root: Path) -> str:
    """go:<clone>:, the clone as 8 random hex written once to .git/pulse/clone (audit M-4 of #118): its path names
    it no better than a guess, since another clone can sit at the same path later."""
    path = config.pulse_dir(root) / "clone"
    try:
        said = path.read_text(encoding="utf-8").strip()
    except OSError:
        said = ""
    if not re.fullmatch(r"[0-9a-f]{8}", said):
        said, new = os.urandom(4).hex(), path.with_name(f".clone.{os.getpid()}")
        path.parent.mkdir(parents=True, exist_ok=True)
        new.write_text(said, encoding="utf-8")
        os.replace(new, path)
    return f"go:{said}:"


def _marks(v) -> list:
    """Claim marks on an issue, oldest first. A mark counts when I wrote it or its author is assigned."""
    assigned = {a["login"] for a in v.get("assignees", [])}
    out = []
    for c in v.get("comments") or []:
        m, cid = MARK.match(c.get("body") or ""), COMMENT.search(c.get("url") or "")    # a mark starts its comment
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


def _utc(ago=0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago))


def _mark(who: dict, phase, files=None) -> str:
    """A claim mark: the holder, its phase, the time now, and the files the work changes for Pulse;
    one line for people."""
    at = _utc()
    data = {**who, "phase": phase, "beat": at, **({"files": files} if files else {})}
    return (f"<!-- pulse:claim {json.dumps(data)} -->\n"
            f"Held by {_name({**who, 'mine': True, 'at': ''})}{': ' + phase if phase else ''}, "
            f"as of {at[11:16]} UTC.")


def _name(m: dict) -> str:
    """Who holds a mark, for people and sessions to read: another person's login, or the kind of my
    session and eight plain characters of its id. The id is free text in a comment (#77 audit L-1)."""
    kind, _, sid = m["id"].partition(":")
    sid = re.sub(r"[^0-9A-Za-z_.-]", "", sid)[:8]
    who = m["author"] if not m["mine"] else {"go": "a pulse go run", "terminal": "a terminal", "claude": f"claude session {sid}",
                                             "codex": f"codex session {sid}"}.get(kind, "another session")
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


def _lead(v, who: dict) -> tuple:
    """Does this session hold the item: its mark leads and my login (its author) is assigned? Else
    who holds it, or "" when this session has no mark on it."""
    marks = _marks(v)
    mine = next((m for m in marks if m["mine"] and m["id"] == who["id"]), None)
    if mine is None:
        return False, ""
    if marks[0] is not mine:
        return False, _name(marks[0])
    held = mine["author"] in [a["login"] for a in v.get("assignees", [])]
    return held, "" if held else (_people(v, mine["author"]) or "nobody")


def holds(repo_name: str, n: int, run=gh, who=None, *, root=None) -> tuple:
    """Verify this acquisition's generation immediately before protected work."""
    from pulse import actions, shared
    root = root or config.find_root()
    if root is None:
        raise StateError("claim verification needs a repository root")
    if actions.held(root, n):
        return False, "local stop requested"
    current = shared.read(root)[1]["items"].get(str(n), {})
    claim = current.get("claim")
    token = _claim_id(who or holder(), n, root)
    if claim and claim["holder"] == token and not current.get("hold"):
        return True, ""
    return False, (claim.get("actor") or claim.get("session") or claim["holder"]) if claim else "claim released"


def taken(v, login: str, trusted=_owner) -> str:
    """Who has the item now (the people assigned, else who took it) when a person took it from my login
    with release --take (#84); "" otherwise. Only the comment of someone assigned to it or who may push counts
    (trusted, #89), as for a note; a hand-over between sessions of my login leaves none. A take read halfway, its
    comment there and my marks not yet gone, counts too."""
    held = {a["login"] for a in v.get("assignees", [])}
    for c in reversed(v.get("comments") or []):
        said, by = TAKEN.fullmatch((c.get("body") or "").strip()), (c.get("author") or {}).get("login")
        if said and by and login in said.group(1).split(", ") and (by in held or trusted(c)):
            return _people(v, login) or by
    return ""


def _in_flight(v, cid: str) -> bool:
    """A fresh claim mark before mine (comment cid) whose author is not assigned: a claim in flight,
    its assignee not there yet, or a mark of someone who may not claim (#77)."""
    assigned = {a["login"] for a in v.get("assignees", [])}
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - CLAIMING))
    for c in v.get("comments") or []:
        if (c.get("url") or "").endswith(f"-{cid}"):
            return False
        if MARK.match(c.get("body") or "") and not c.get("viewerDidAuthor") and \
                (c.get("author") or {}).get("login") not in assigned and (c.get("createdAt") or "") >= since:
            return True
    return False


def _give_way(repo_name: str, n: int, marks: list, who: dict, run) -> None:
    """A claim that lost takes its mark back, and my assignee unless another session of mine holds n."""
    if not marks or not marks[0]["mine"]:                  # the winner is another person
        run(["issue", "edit", str(n), "--repo", repo_name, "--remove-assignee", "@me"])
    for m in marks:
        if m["mine"] and m["id"] == who["id"]:
            _unmark(repo_name, m["cid"], run)            # after the assignee


def docs_branch(root: Path, n: int) -> str:
    """The docs branch of draft n on origin as the last fetch left it (named as spec_branch says, or
    docs/<n>-<slug>), where its analysis and spec are (#99 FR-05, #116); "" without one."""
    from pulse import ready
    cfg = config.load(root)
    refs = ready._git(root, "for-each-ref", "--format=%(refname:lstrip=3)", "refs/remotes/origin").split()
    return next((b for b in refs if config.is_spec_branch(cfg, b, n)), "")


def _work(root: Path, n: int, v: dict) -> str:
    """Where the work on n is, for whoever holds it next: for a draft (v, its issue) its docs branch (#99 FR-05),
    else the branch pulse go would build on, never a spec branch (#83), when origin has it. Fetched just now,
    since the holder may have pushed after my last fetch; offline, as the last fetch saw it, where names that
    differ only in case cannot share a ref file (#97)."""
    from pulse import go, ready    # both read the board through this module
    ready.fetch(root, now=True)
    base = config.load(root)["base_branch"] or config.default_branch(root)
    b = docs_branch(root, n) if DRAFT in {l.get("name") for l in v.get("labels", [])} else \
        go._branch_of(root, n, base, origin_first=True)
    named = b and ready._tip(root, f"refs/remotes/origin/{b}")
    twin = ready.folded(root, base, b, item=n)      # a ref file two names share names no work (#97)
    if twin and (named or twin != ready.NO_ANSWER):
        return f"; where the work is stays unnamed: {twin}"
    # quoted as a shell reads it: an agent may run what the hint names (#83 audit L-1, as the start point, #78)
    return "; the work is on " + ready.printable(shlex.quote(f"origin/{b}")) if named else ""


_CLAIMS = {}               # a process remembers only generations it actually acquired


def _claim_id(who, number, root=None):
    known = (who.get("claims") or {}).get(str(number))
    if root is None:
        return known or _CLAIMS.get((who["id"], number), who["id"])
    if not known:
        saved = _claim_receipt(root, who, number)
        known = _receipt_claim(saved)["holder"] if saved else None
    return known or who["id"]


def _receipt_claim(operation):
    return operation["payload"]["claim"] if operation["kind"] == "migrate" else operation["payload"]


def _claim_receipt(root, who, number):
    from pulse import actions, shared
    saved = actions.claim_receipt(root, who["id"], number)
    if saved is not None:
        try:
            shared._operation(saved)
            payload = _receipt_claim(saved)
            if (not isinstance(payload, dict) or saved["kind"] not in {"claim", "migrate"} or saved["item"] != number
                    or payload.get("session") != who["id"]
                    or not shared.ID.fullmatch(str(payload.get("holder", "")))
                    or not LOGIN.fullmatch(str(payload.get("actor", "")))
                    or shared._files(payload.get("files")) != payload["files"]):
                raise ValueError()
        except (StateError, ValueError, TypeError, KeyError):
            raise StateError("invalid local claim receipt") from None
    return saved


def _prepare_claim(root, who, number, payload, snapshot, current, kind="claim"):
    """Persist our exact operation before push; identical simultaneous callers share it."""
    from pulse import actions, shared
    saved = _claim_receipt(root, who, number)
    if kind == "claim":
        payload = {**payload, "files": shared._files(payload["files"])}
    proposed = {"id": uuid.uuid4().hex, "item": number, "kind": kind,
                "expected": current.get("revision", ""), "payload": payload}

    def scope(operation):
        claim = _receipt_claim(operation)
        claim = {k: v for k, v in claim.items() if k != "holder"}
        return {**operation["payload"], "claim": claim} if operation["kind"] == "migrate" else claim

    def same(candidate):
        return (candidate and candidate["kind"] == kind and candidate["item"] == number
                and candidate["expected"] == proposed["expected"]
                and scope(candidate) == scope(proposed))

    prior = snapshot["operations"].get(saved["id"]) if saved else None
    if saved and (not prior or prior["result"]["status"] == "confirmed" and same(saved)):
        if not same(saved):
            if saved["expected"] != proposed["expected"]:
                raise StateError("pending claim's revision changed; release its obsolete local intent, then retry")
            raise StateError("pending claim has another account or scope; repeat the original claim before releasing")
        proposed = saved
    chosen = actions.claim_receipt(root, who["id"], number, proposed, previous=saved)
    if not same(chosen):
        raise StateError("local claim preparation changed; read current state and retry")
    return chosen


def _forget_claim(root, who, number, token=None):
    from pulse import actions
    saved = _claim_receipt(root, who, number)
    if saved and (token is None or _receipt_claim(saved)["holder"] == token):
        actions.claim_receipt(root, who["id"], number, None, previous=saved)


def _own_legacy(repo_name, number, claim, who, login, run):
    """The exact old claim still belongs to this authenticated writer and session."""
    from pulse import shared
    raw = _view(repo_name, number, run)
    observed = normalize({"title": "", **raw})
    if (observed["claimed_by"] != login or observed["claimed_holder"] != who["id"]
            or claim.get("actor") != login or claim.get("session") != who["id"]
            or shared._files(observed["claimed_files"] or ["."]) != claim["files"]):
        return False
    marks = [mark for mark in _marks(raw) if mark["author"] in observed["assignees"]]
    if not marks:
        return False
    cid = marks[0]["cid"]
    original = next(c for c in raw["comments"] if COMMENT.search(c.get("url") or "")
                    and COMMENT.search(c["url"]).group(1) == cid)
    proof = json.loads(run(["api", f"repos/{repo_name}/issues/comments/{cid}"]))
    if (proof.get("id") != int(cid) or (proof.get("user") or {}).get("login") != login
            or proof.get("issue_url") != f"https://api.github.com/repos/{repo_name}/issues/{number}"
            or not proof.get("created_at") or proof.get("body") != original["body"]):
        return False
    if proof["created_at"] == proof.get("updated_at"):
        return True
    if not proof.get("node_id"):
        return False
    query = "query($id:ID!){node(id:$id){... on IssueComment{databaseId body updatedAt " + \
            "author{login} editor{login} issue{number repository{nameWithOwner}}}}}"
    latest = json.loads(run(["api", "graphql", "-f", "query=" + query, "-f", "id=" + proof["node_id"]]))
    node = (latest.get("data") or {}).get("node") or {}
    return (node.get("databaseId") == int(cid) and node.get("body") == proof["body"]
            and node.get("updatedAt") == proof.get("updated_at")
            and (node.get("author") or {}).get("login") == login
            and (node.get("editor") or {}).get("login") == login
            and node.get("issue") == {"number": number, "repository": {"nameWithOwner": repo_name}})


def _remember(who, number, token):
    who.setdefault("claims", {})[str(number)] = token
    _CLAIMS[(who["id"], number)] = token


def _change(root, number, kind, payload, expected):
    from pulse import shared
    return shared.update(root, {"id": uuid.uuid4().hex, "item": number, "kind": kind,
                                "expected": expected, "payload": payload})


def _migrate(root, repo_name, entries, run, who=None, login=None):
    """Import restrictive legacy claims/holds during an authenticated mutation.

    Unknown legacy reservation scope conservatively covers the whole project.
    No old spec, PLAN or PR approval becomes an integration approval.
    """
    from pulse import shared
    for entry in entries:
        if not entry.get("migration_required"):
            continue
        number = entry["number"]
        if str(number) in shared.read(root)[1]["items"]:
            continue
        claimed = entry.get("claimed_by")
        legacy = {"holder": uuid.uuid4().hex, "files": shared._files(entry.get("claimed_files") or ["."]),
                  "actor": claimed, "session": entry.get("claimed_holder") or "legacy:" + claimed} if claimed else None
        payload = {"claim": legacy, "hold": bool(entry.get("hold")),
                   "hold_origin": "legacy" if entry.get("hold") else "",
                   "failed": bool(entry.get("failed")),
                   "failure": "Legacy work failed; explicit resume is required" if entry.get("failed") else ""}
        if who and legacy and legacy["session"] == who["id"] and legacy["actor"] == login:
            if not _own_legacy(repo_name, number, legacy, who, login, run):
                raise StateError(f"#{number}: original own legacy claim could not be authenticated")
            operation = _prepare_claim(root, who, number, payload, shared.read(root)[1], {}, kind="migrate")
            _remember(who, number, _receipt_claim(operation)["holder"])
            receipt = shared.update(root, operation)
        else:
            receipt = _change(root, number, "migrate", payload, "")
        if receipt["status"] != "confirmed":
            raise StateError(f"legacy claim #{number} needs review: {receipt.get('reason', 'state changed')}")


def claim(root: Path, repo_name: str, n: int, run=gh, who=None, take=False, blockers=True,
          phase=None, files=None, labels=None, expected_spec=...) -> tuple:
    """Acquire one serialized generation, including its file reservations."""
    from pulse import actions, ready, shared
    who = who or holder()
    if actions.held(root, n):
        return False, f"#{n} has a local stop request"
    initial = shared.read(root)[1]["items"].get(str(n), {}).get("claim")
    same_files = initial and (files is None or sorted(set(files)) == initial["files"])
    continuing = initial if same_files and initial["holder"] == _claim_id(who, n, root) else None
    if continuing:
        # No new reservation: check this issue now, without reloading unrelated
        # metadata. First acquisition and every file change still migrate the
        # complete fresh board, including legacy holders on other items.
        raw = _view(repo_name, n, run)
        if raw.get("state") != "OPEN":
            return False, f"#{n} is closed or unavailable"
        known = {}
        trusted = lambda entry: writer(entry, repo_name, run, known)
        entries = _overlay(root, [normalize({"title": "", **raw}, lambda entry: trusted(entry) is True,
                                            lifecycle_trusted=trusted)])
    else:
        entries = load(root, repo_name, run=run, fresh=True)
    observed = next((entry for entry in entries if entry["number"] == n), None)
    if observed is None:
        return False, f"#{n} is closed or unavailable"
    if expected_spec is not ... and observed.get("spec") != expected_spec:
        return False, f"#{n}: spec changed before {phase or 'claim'}; refresh the item and its Plan"
    if labels is not None:
        labels.update(label for label, enabled in ((DRAFT, observed.get("draft")), (HOLD, observed.get("hold")),
                                                 (FAIL, observed.get("failed")), (BASE, observed.get("base_fix"))) if enabled)
    if observed.get("hold"):
        return False, f"#{n} is held; complete its stop and explicitly resume it first"
    if blockers and observed.get("blocked_by") and not observed.get("draft"):
        return False, f"#{n} is blocked by " + ", ".join(f"#{other}" for other in observed["blocked_by"])
    login = run(["api", "user", "--jq", ".login"]).strip()
    if not can_push(repo_name, login, run):
        raise StateError("repository push permission is required")
    _migrate(root, repo_name, entries, run, who=who, login=login)
    snapshot = shared.read(root)[1]
    current = snapshot["items"].get(str(n), {})
    previous = current.get("claim")
    if continuing and (previous != continuing or current.get("hold") or current.get("failed")):
        # A handoff/release cannot turn this narrow phase check into a fresh
        # acquisition without the complete legacy reservation check.
        return False, f"#{n}: claim changed while checking its phase; retry from current state"
    if previous:
        if previous.get("actor", login) != login:
            return False, f"#{n} is held by {ready.printable(previous['actor'])} (another account); nothing changed"
        if previous["holder"] != _claim_id(who, n, root):
            return False, f"#{n} is held by {previous.get('actor') or previous['holder']}; a person may release it"
        _remember(who, n, previous["holder"])
        if (files is None or sorted(set(files)) == previous["files"]) and \
                (not phase or phase == (current.get("work") or {}).get("phase")):
            return (False, f"#{n} has a local stop request") if actions.held(root, n) else (True, f"claimed #{n}")
    token = previous["holder"] if previous else uuid.uuid4().hex
    # Retain the proposed generation in this caller across a lost push response.
    # A different process must carry the generation explicitly; session alone
    # never borrows a newer acquisition after a person's handoff.
    payload = {"holder": token, "session": who["id"], "actor": login,
               "files": previous["files"] if files is None and previous else files or [],
               **({"phase": phase} if phase else {})}
    if previous:
        operation = {"id": uuid.uuid4().hex, "item": n, "kind": "claim",
                     "payload": payload, "expected": current["revision"]}
    else:
        operation = _prepare_claim(root, who, n, payload, snapshot, current)
        token = operation["payload"]["holder"]
    _remember(who, n, token)
    receipt = shared.update(root, operation)
    if receipt["status"] != "confirmed":
        return False, f"#{n}: {receipt.get('reason', 'claim changed')}"
    _remember(who, n, token)
    current = shared.read(root)[1]["items"].get(str(n), {})
    if (current.get("claim") or {}).get("holder") != token:
        return False, f"#{n} changed holder while claiming; no work started"
    if current.get("hold") or actions.held(root, n):
        # A local or shared defer may arrive during the claim push. No writer
        # started, so acknowledge the stop without requiring a new worktree.
        if (current.get("claim") or {}).get("holder") == token:
            stop = current.get("stop") or {}
            kind = "stopped" if stop.get("holder") == token and stop.get("status") == "requested" else "release"
            _change(root, n, kind, {"holder": token, "work": current.get("work") or {},
                                   "reason": "stop arrived before work started"}, current["revision"])
        drop_cache(root)
        return False, f"#{n} received a stop while claiming; no work started"
    return True, f"claimed #{n}"


def beat(root: Path, repo_name: str, n: int, phase: str, run=gh, who=None) -> bool:
    """Publish phase transitions once; unchanged heartbeats only verify ownership."""
    from pulse import actions, shared
    who = who or holder()
    if actions.held(root, n):
        return False
    current = shared.read(root)[1]["items"].get(str(n), {})
    claim = current.get("claim") or {}
    if claim.get("holder") != _claim_id(who, n, root) or current.get("hold") or current.get("failed"):
        return False
    if (current.get("work") or {}).get("phase") == phase:
        return True
    receipt = _change(root, n, "claim", {**claim, "phase": phase}, current["revision"])
    if receipt["status"] != "confirmed":
        return False
    return True


def release(root: Path, repo_name: str, n: int, run=gh, who=None, take=False, take_person=False,
            note="", work=None, expected=None, previous_holder=None) -> tuple:
    """Release idle own work, or authenticate a person's explicit foreign handoff."""
    from pulse import shared
    who = who or holder()
    if take or take_person:
        if not holder()["id"].startswith("terminal:"):
            raise StateError("only a person may explicitly release another claim")
        login = run(["api", "user", "--jq", ".login"]).strip()
        if not can_push(repo_name, login, run):
            raise StateError("repository push permission is required")
        entries = load(root, repo_name, run=run, fresh=True)
        _migrate(root, repo_name, [entry for entry in entries if entry["number"] == n], run)
    snapshot = shared.read(root)[1]
    current = snapshot["items"].get(str(n), {})
    existing = current.get("claim")
    if not existing:
        saved = _claim_receipt(root, who, n)
        if saved and saved["id"] not in snapshot["operations"] and saved["expected"] == current.get("revision", ""):
            return False, f"#{n}: claim outcome is still unknown; retry its original claim before releasing"
        _forget_claim(root, who, n)
        return True, f"#{n} has no claim to release"
    observed = current.get("revision", "") if expected is None else expected
    token = previous_holder or existing["holder"]
    if take or take_person:
        operation = {"id": uuid.uuid4().hex, "item": n, "kind": "handoff", "expected": observed,
                     "payload": {"holder": token, "reason": note or "Person requested a claim handoff",
                                 "work": work or current.get("work") or {}}}
        receipt = sync_action(root, operation, run=run)
    else:
        if not (who.get("claims") or {}).get(str(n)) and _claim_receipt(root, who, n):
            login = run(["api", "user", "--jq", ".login"]).strip()
            if not can_push(repo_name, login, run):
                raise StateError("repository push permission is required")
            if existing.get("actor") != login:
                return False, f"#{n} was acquired by another account; nothing released"
        if existing["holder"] != _claim_id(who, n, root):
            return False, f"#{n} is held by {existing.get('actor') or existing['holder']}; nothing released"
        receipt = _change(root, n, "release", {"holder": existing["holder"], "reason": note,
                          "work": work or current.get("work") or {}}, observed)
    if receipt["status"] != "confirmed":
        return False, f"#{n}: {receipt.get('reason', 'claim changed')}"
    _forget_claim(root, who, n, existing["holder"])
    _CLAIMS.pop((who["id"], n), None)
    who.get("claims", {}).pop(str(n), None)
    return True, f"released #{n}; work is preserved"


def leave_note(repo_name: str, n: int, text: str, by: str, who: dict, run=gh) -> None:
    """A note on n for whoever takes it next (why, where the work is); normalize reads the last one."""
    run(["issue", "comment", str(n), "--repo", repo_name, "--body",
         f"<!-- pulse:note {json.dumps({'at': _utc(), 'by': by, 'holder': who['id']})} -->\n{text}"])


def attach(root: Path, repo_name: str, n: int, kind: str, path=None, parent=None, blocked_by=(),
           run=gh, who=None, title=None, pr=None, labels=()) -> tuple:
    """Make an open issue that links no spec (a draft, an issue from the BA) a record of this kind,
    as create makes a new one: its type, parent, blockers, labels, and spec path with its title.
    Without a path it becomes a draft. Attaching a spec changes no claim; its current writer
    releases that generation explicitly when the work stops."""
    have = spec_of(repo_name, n, run)
    if have:
        return False, f"#{n} already links {have}"
    v = _view(repo_name, n, run)
    if v.get("state") != "OPEN":
        return False, f"#{n} is closed"
    on = {l["name"] for l in v.get("labels", [])}
    was = next((t for t in TYPES if f"pulse:{t}" in on), kind)
    if was != kind:
        return False, f"#{n} has the type {was}, not {kind}"
    add = [l for l in (f"pulse:{kind}", None if path else DRAFT, *labels) if l and l not in on]
    edit = (["--title", title] if path and title else []) + (["--add-label", ",".join(add)] if add else []) + \
        (["--remove-label", DRAFT] if path and DRAFT in on else []) + \
        (["--parent", str(parent)] if parent and parent != (v.get("parent") or {}).get("number") else []) + \
        (["--add-blocked-by", ",".join(map(str, blocked_by))] if blocked_by else [])
    if edit:                   # before the Spec line: an edit GitHub refuses (a label it lacks) leaves no link, so a
        run(["issue", "edit", str(n), "--repo", repo_name, *edit])      # rerun goes through (#116 fix round 1)
    if path:
        _set_line(root, repo_name, n, SPEC, spec_line(path, pr), run)
    drop_cache(root)
    return True, f"#{n} links {path}" if path else f"#{n} is a draft"
