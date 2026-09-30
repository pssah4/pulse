"""Confirmed feature removal, separate from the original item's build and completion.

The caller resolves operation from a trusted lifecycle event, never from user JSON.
It supplies id, action=delete, phase=paused, item, actor and inventory=preview().
Only a person requests removal actions. The go runner produces gate evidence;
this module never produces it. Failed or ambiguous operations retain the issue.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from pulse import auto, base, config, merge as gates, state


SUMMARY = "number,state,headRefName,baseRefName,headRefOid,mergeCommit,isCrossRepository,closingIssuesReferences"
FIELDS = SUMMARY + ",files,changedFiles,commits"
PR_FIELDS = FIELDS + ",isDraft,mergeable,statusCheckRollup,comments"
ISSUE_FIELDS = "id,number,title,state,body,labels,assignees,parent,blocking,blockedBy,comments"
MARK = re.compile(r"<!-- pulse:remove (\{[^\n]*\}) -->")
GATES = ("tests", "review", "audit")


def _git(root, *args, input=None):
    try:
        result = subprocess.run(["git", *args], cwd=root, input=input, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise state.StateError(f"removal git failed: {error}") from None
    if result.returncode:
        raise state.StateError(f"removal git {' '.join(args[:2])}: {result.stderr.strip()}")
    return result.stdout.strip()


def _origin(root, repo):
    for flags in ((), ("--push",)):
        urls = _git(root, "remote", "get-url", "--all", *flags, "origin").splitlines()
        for url in urls:
            found = state.REMOTE.fullmatch(url.removeprefix("https://").removeprefix("ssh://git@").removeprefix("git@"))
            if not found or found.group(1).lower() != repo.lower():
                raise state.StateError("removal requires origin fetch and push URLs to name the confirmed repository")


def _identity(root, repo, number):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or type(number) is not int or number <= 0:
        raise state.StateError("invalid removal repository or item")
    _origin(root, repo)


def _base(root):
    branch = config.load(root)["base_branch"] or config.default_branch(root)
    _git(root, "check-ref-format", "refs/heads/" + branch)
    remote = _git(root, "ls-remote", "--exit-code", "origin", "refs/heads/" + branch).split()
    if len(remote) != 2 or not base.SHA.fullmatch(remote[0]):
        raise state.StateError("cannot resolve removal base")
    _git(root, "fetch", "-q", "--no-tags", "origin", remote[0])
    return branch, remote[0]


def _json(run, args):
    try:
        return json.loads(run(args))
    except (ValueError, TypeError):
        raise state.StateError("unreadable GitHub removal state") from None


def _issue(repo, number, run):
    raw = _json(run, ["issue", "view", str(number), "--repo", repo, "--json", ISSUE_FIELDS])
    return {**raw, "comments": _comments(repo, number, run), "_comments_complete": True}


def _comments(repo, number, run):
    return [{**raw, "author": raw.get("user", raw.get("author")),
             "authorAssociation": raw.get("author_association", raw.get("authorAssociation")),
             "edited": bool(raw.get("edited") or raw.get("lastEditedAt") or
                            raw.get("updated_at") != raw.get("created_at"))}
            for raw in state.pages(run, f"repos/{repo}/issues/{number}/comments?per_page=100")]


def _target(issue):
    return _digest({**{key: issue.get(key) for key in ("id", "number", "title", "body", "state", "parent")},
                    "labels": sorted(label["name"] for label in issue.get("labels", [])
                                     if label["name"] != state.HOLD)})


def _prs(repo, run):
    found = _json(run, ["pr", "list", "--repo", repo, "--state", "all", "--limit", "1000", "--json", SUMMARY])
    if not isinstance(found, list) or len(found) >= 1000:
        raise state.StateError("PR inventory may be incomplete; manual scope review required")
    return found


def _paths(root, before, after):
    return sorted(filter(None, _git(root, "diff", "--name-only", "-z", "--no-renames", before, after).split("\0")))


def _patch(root, before, after):
    patch = _git(root, "diff", "--binary", "--no-ext-diff", "--no-textconv", before, after)
    return _git(root, "patch-id", "--verbatim", input=patch + "\n").split()[:1]


def _work(root, number):
    branches, problems = [], []
    refs = _git(root, "for-each-ref", "--format=%(refname)", "refs/heads").splitlines()
    remote = {ref.removeprefix("refs/heads/"): sha for sha, ref in
              (line.split() for line in _git(root, "ls-remote", "--heads", "origin").splitlines())}
    for branch, head in remote.items():
        if state.item_of(branch) == number or config.is_spec_branch(config.load(root), branch, number):
            branches.append(["refs/remotes/origin/" + branch, head])
    for ref in refs:
        branch = ref.removeprefix("refs/heads/").removeprefix("refs/remotes/origin/")
        if state.item_of(branch) != number and not config.is_spec_branch(config.load(root), branch, number):
            continue
        head = _git(root, "rev-parse", ref)
        branches.append([ref, head])
        if ref.startswith("refs/heads/") and remote.get(branch) != head:
            problems.append(f"unpushed or divergent item branch {branch}; preserve and resolve before removal")
    for tree in _git(root, "worktree", "list", "--porcelain").split("\n\n"):
        fields = dict(line.split(" ", 1) for line in tree.splitlines() if " " in line)
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if state.item_of(branch) == number or config.is_spec_branch(config.load(root), branch, number):
            path = Path(fields["worktree"])
            dirty = _git(path, "status", "--porcelain", "--untracked-files=all", "--ignored")
            if dirty:
                problems.append(f"item worktree has uncommitted or ignored work: {path}")
            for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
                if Path(_git(path, "rev-parse", "--path-format=absolute", "--git-path", name)).exists():
                    problems.append(f"unfinished git operation in {path}")
    return sorted(branches), problems


def preview(root: Path, repo: str, n: int, run=state.gh) -> dict:
    """Fresh inventory; blocked reasons require scope clarification, not a best-effort revert."""
    _identity(root, repo, n)
    branch, sha = _base(root)
    issue = _issue(repo, n, run)
    normalized = state.normalize(issue)
    spec = normalized.get("spec") or ""
    blocked = []
    if normalized.get("type") not in state.WORK:
        blocked.append("only features, improvements and fixes can be removed")
    if issue.get("assignees"):
        blocked.append("the holder must acknowledge the stop and release the claim")
    dependents = issue.get("blocking", {}).get("nodes", [])
    if dependents:
        blocked.append("dependent items require manual scope review")
    if not spec or PurePosixPath(spec).is_absolute() or ".." in PurePosixPath(spec).parts:
        blocked.append("missing or unsafe spec scope")
    spec_commits = set(_git(root, "log", "--full-history", "-m", "--format=%H", sha, "--", spec).splitlines()) if spec else set()
    sources = []
    for pr in _prs(repo, run):
        linked = {entry["number"] for entry in pr.get("closingIssuesReferences", [])}
        paths = [entry["path"] for entry in pr.get("files", [])]
        named = state.item_of(pr.get("headRefName"))
        carries_spec = (pr.get("mergeCommit") or {}).get("oid") in spec_commits or spec and spec in paths
        if n not in linked and named != n and not carries_spec:
            continue
        pr = _json(run, ["pr", "view", str(pr["number"]), "--repo", repo, "--json", FIELDS])
        paths = [entry["path"] for entry in pr.get("files", [])]
        if pr.get("state") == "OPEN":
            blocked.append(f"open work in PR #{pr['number']}; preserve and resolve its scope first")
            continue
        if pr.get("state") != "MERGED":
            continue
        if n not in linked and named != n and set(paths) != {spec}:
            blocked.append(f"ambiguous shared spec PR #{pr['number']}; manual scope required")
            continue
        if pr.get("isCrossRepository") or pr.get("baseRefName") != branch or linked - {n} or named not in (None, n):
            blocked.append(f"ambiguous scope in PR #{pr['number']} (other item, fork or base)")
            continue
        if len(paths) != pr.get("changedFiles"):
            blocked.append(f"incomplete scope of PR #{pr['number']}")
            continue
        commit = (pr.get("mergeCommit") or {}).get("oid", "")
        head = pr.get("headRefOid") or ""
        if not base.SHA.fullmatch(commit) or not base.SHA.fullmatch(head):
            blocked.append(f"missing commit provenance for PR #{pr['number']}")
            continue
        _git(root, "merge-base", "--is-ancestor", commit, sha)
        parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        if len(parents) not in (1, 2):
            blocked.append(f"ambiguous merge parents in PR #{pr['number']}")
            continue
        if len(parents) == 1 and head == commit:
            commits = pr.get("commits") or []
            if len(commits) != 1 or commits[0].get("oid") != head:
                blocked.append(f"multi-commit or unverifiable rebase in PR #{pr['number']}; manual scope required")
                continue
        try:
            _git(root, "cat-file", "-e", head + "^{commit}")
        except state.StateError:
            _git(root, "fetch", "-q", "--no-tags", "origin", f"refs/pull/{pr['number']}/head")
            _git(root, "cat-file", "-e", head + "^{commit}")
        ancestor = _git(root, "merge-base", parents[0], head)
        if _patch(root, ancestor, head) != _patch(root, parents[0], commit):
            blocked.append(f"ambiguous squash/rebase or merge resolution in PR #{pr['number']}; manual scope required")
            continue
        changed = _paths(root, parents[0], commit)
        if set(changed) != set(paths):
            blocked.append(f"incomplete changed-file provenance in PR #{pr['number']}")
            continue
        sources.append({"pr": pr["number"], "commit": commit, "head": head, "parent": parents[0],
                        "mainline": 1 if len(parents) == 2 else None, "files": changed})
    if not sources:
        blocked.append("no complete merged PR provenance; manual scope required")
    order = _git(root, "rev-list", "--first-parent", sha).splitlines()
    if any(source["commit"] not in order for source in sources):
        blocked.append("source merges are not on the base first-parent history; manual scope required")
    sources.sort(key=lambda source: order.index(source["commit"]) if source["commit"] in order else len(order))
    branches, work_problems = _work(root, n)
    blocked.extend(work_problems)
    for ref, head in branches:
        if head in {source["head"] for source in sources}:
            continue
        try:
            _git(root, "merge-base", "--is-ancestor", head, sha)
        except state.StateError:
            blocked.append(f"unintegrated work on {ref}; secure and explicitly review its scope")
    return {"repo": repo, "item": n, "issue_id": issue["id"], "target": _target(issue),
            "base": branch, "base_sha": sha, "spec": spec,
            "sources": sources, "files": sorted({path for source in sources for path in source["files"]}),
            "branches": branches, "dependents": dependents, "blocked": blocked}


def marker(value: dict) -> str:
    """Machine record written as its own line in an append-only PR comment."""
    return "<!-- pulse:remove " + json.dumps(value, sort_keys=True, separators=(",", ":")) + " -->"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _operation(repo, number, operation):
    if not isinstance(operation, dict) or operation.get("action") != "delete" or \
            operation.get("phase") != "paused" or operation.get("item") != number or \
            not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(operation.get("id", ""))) or \
            not state.LOGIN.fullmatch(str(operation.get("actor", ""))):
        raise state.StateError("removal requires a trusted, paused delete operation")
    inventory = operation.get("inventory")
    if not isinstance(inventory, dict) or inventory.get("repo") != repo or inventory.get("item") != number:
        raise state.StateError("delete operation lacks its confirmed inventory")
    return inventory


def _paused(issue, operation, repo, run):
    from pulse import lifecycle
    known = {}
    for comment in issue.get("comments", []):
        if comment.get("edited") and comment.get("body", "").startswith("<!-- pulse:lifecycle ") and \
                state.writer(comment, repo, run, known) is not False:
            raise state.StateError("edited lifecycle operation; keep the issue")
    current = lifecycle.operation(issue, lambda comment: state.writer(comment, repo, run, known))
    if any(current.get(key) != operation.get(key) for key in ("id", "action", "phase", "actor")) or \
            any(key in current and current[key] != operation.get(key) for key in ("item", "inventory")) or \
            current.get("retained"):
        raise state.StateError("the trusted paused delete operation changed or still retains work; stop removal")


def _find(repo, number, run):
    prs = _json(run, ["pr", "list", "--repo", repo, "--head", f"pulse-remove/{number}",
                      "--state", "all", "--limit", "100", "--json", PR_FIELDS])
    if len(prs) > 1:
        raise state.StateError("multiple removal PRs; resolve manually")
    return prs[0] if prs else None


def _post(repo, pr, value, run):
    run(["pr", "comment", str(pr), "--repo", repo, "--body", marker(value)])


def _records(pr, repo, run):
    found, known = [], {}
    for comment in _comments(repo, pr["number"], run):
        match = MARK.fullmatch(comment.get("body", "").strip())
        if not match:
            continue
        authority = state.writer(comment, repo, run, known)
        if authority is False:
            continue
        if authority is not True:
            raise state.StateError("removal comment authority cannot be verified; keep the issue")
        if comment.get("lastEditedAt") or comment.get("edited") or \
                comment.get("updated_at") != comment.get("created_at"):
            raise state.StateError("edited removal binding; manual clarification required")
        try:
            value = json.loads(match.group(1))
        except ValueError:
            raise state.StateError("malformed trusted removal binding") from None
        if not isinstance(value, dict):
            raise state.StateError("malformed trusted removal binding")
        found.append((value, (comment.get("author") or {}).get("login")))
    return found


def _absent(root, ref, inventory):
    paths = _git(root, "ls-tree", "-r", "--name-only", "-z", ref).split("\0")
    spec = inventory["spec"]
    if spec in paths:
        raise state.StateError("spec still present; manual scope removal required")
    needles = [spec, PurePosixPath(spec).name]
    logical = re.match(r"(?:FEAT|IMP|FIX)-[0-9-]+", PurePosixPath(spec).name)
    if logical:
        needles.append(logical.group().rstrip("-"))
    result = subprocess.run(["git", "grep", "-I", "-l", "-F", *[arg for word in needles for arg in ("-e", word)],
                             ref, "--", "."],
                            cwd=root, capture_output=True, text=True, timeout=120)
    if result.returncode not in (0, 1):
        raise state.StateError("cannot check remaining active references")
    if result.returncode == 0:
        raise state.StateError("active feature references remain; manual scope removal required: " + result.stdout.strip())


def prepare(root: Path, repo: str, n: int, operation: dict, run=state.gh) -> dict:
    """Reserve once, revert only attributed changes, and publish a draft plus trusted binding.

    A reservation without a bound PR is deliberately not stolen after an interrupted
    preparation. Its retained worktree is reported for a person's recovery.
    """
    if not auto.person(os.environ, sys.stdin is not None and sys.stdin.isatty()):
        raise state.StateError("only a person may prepare a removal")
    inventory = _operation(repo, n, operation)
    _identity(root, repo, n)
    if _find(repo, n, run):
        return status(root, repo, operation, run)
    fresh = preview(root, repo, n, run)
    if fresh != inventory:
        raise state.StateError("removal inventory changed; refresh and confirm again")
    if fresh["blocked"]:
        raise state.StateError("; ".join(fresh["blocked"]))
    issue = _issue(repo, n, run)
    _paused(issue, operation, repo, run)
    if state.HOLD not in {label["name"] for label in issue.get("labels", [])} or issue.get("assignees"):
        raise state.StateError("removal waits for hold and the holder's completed stop")
    if not state.can_push(repo, operation["actor"], run):
        raise state.StateError("delete operation actor no longer has write permission")
    branch = f"pulse-remove/{n}"
    home = config.common_dir(root) / "pulse" / "removals"
    home.mkdir(parents=True, exist_ok=True)
    worktree = home / operation["id"]
    if worktree.exists() or worktree.is_symlink():
        raise state.StateError(f"removal worktree already exists; inspect preserved work at {worktree}")
    run(["api", f"repos/{repo}/git/refs", "-f", f"ref=refs/heads/{branch}", "-f", f"sha={fresh['base_sha']}"])
    try:
        _git(root, "worktree", "add", "--detach", str(worktree), fresh["base_sha"])
        _git(worktree, "switch", "-c", branch)
        for source in fresh["sources"]:
            flags = ["-m", "1"] if source["mainline"] else []
            _git(worktree, "revert", "--no-commit", *flags, source["commit"])
        tree = _git(worktree, "write-tree")
        _absent(worktree, tree, fresh)
        actual = _paths(worktree, fresh["base_sha"], tree)
        if not actual or set(actual) - set(fresh["files"]):
            raise state.StateError("revert has empty or unexpected scope; manual scope review required")
        _git(worktree, "commit", "-m", f"revert: remove item #{n} ({operation['id']})")
        head = _git(worktree, "rev-parse", "HEAD")
        _git(worktree, "push", "origin", f"HEAD:refs/heads/{branch}")
        url = run(["pr", "create", "--repo", repo, "--base", fresh["base"], "--head", branch, "--draft",
                   "--title", f"Remove item #{n}", "--body",
                   f"Removal operation {operation['id']} for #{n}.\n\n"
                   "Requires fresh tests, review and audit, scope review, and separate exact-head human approval. "
                   "The original issue and comments are deleted only after verified integration."])
        match = re.search(r"/pull/(\d+)\s*$", url)
        if not match:
            raise state.StateError("removal PR creation returned no identifiable PR")
        binding = {"phase": "prepared", "id": operation["id"], "repo": repo, "item": n,
                   "inventory": fresh, "actor": operation["actor"], "head": head, "tree": tree,
                   "files": actual, "branch": branch, "pr": int(match.group(1))}
        _post(repo, binding["pr"], binding, run)
    except (state.StateError, OSError) as error:
        raise state.StateError(f"removal preparation stopped; original issue retained; work preserved at {worktree}: {error}") from None
    result = status(root, repo, operation, run)
    return {**result, "worktree": str(worktree)}


def status(root: Path, repo: str, operation: dict | int, run=state.gh) -> dict:
    """Read progress; an item number recovers the operation from its trusted PR binding."""
    number = operation if type(operation) is int else operation.get("item")
    _identity(root, repo, number)
    listed = _find(repo, number, run)
    if not listed:
        return {"phase": "paused", "item": number, "blocked": ["no bound removal PR; prepare or inspect reservation"]}
    pr = _json(run, ["pr", "view", str(listed["number"]), "--repo", repo, "--json", PR_FIELDS])
    records = _records(pr, repo, run)
    bindings = [value for value, author in records if value.get("phase") == "prepared"]
    if len(bindings) != 1:
        raise state.StateError("removal PR needs exactly one trusted prepared binding")
    binding = bindings[0]
    if type(operation) is int:
        operation = {**{key: binding.get(key) for key in ("id", "item", "actor", "inventory")},
                     "action": "delete", "phase": "paused"}
    inventory = _operation(repo, number, operation)
    if binding.get("id") != operation["id"] or binding.get("item") != number or binding.get("repo") != repo or \
            binding.get("inventory") != inventory or binding.get("actor") != operation["actor"] or \
            binding.get("pr") != pr["number"] or pr.get("isCrossRepository") or \
            pr.get("baseRefName") != inventory["base"] or pr.get("headRefName") != binding.get("branch") or \
            not base.SHA.fullmatch(binding.get("head", "")):
        raise state.StateError("removal binding or PR head changed; fresh scope approval required")
    previous = None
    for candidate, author in records:
        if candidate.get("phase") != "rebound":
            continue
        same = ("id", "repo", "item", "actor", "branch", "pr", "files")
        new_inventory = candidate.get("inventory") or {}
        if candidate.get("previous") != _digest(binding) or \
                any(candidate.get(key) != binding.get(key) for key in same) or \
                new_inventory != {**binding["inventory"], "base_sha": new_inventory.get("base_sha")} or \
                not all(base.SHA.fullmatch(candidate.get(key, "")) for key in ("head", "tree")) or \
                not base.SHA.fullmatch(new_inventory.get("base_sha", "")):
            raise state.StateError("invalid removal rebind chain; manual scope review required")
        previous, binding = binding, candidate
    pending = binding["head"] != pr.get("headRefOid")
    if pending and (not previous or previous["head"] != pr.get("headRefOid") or pr["state"] != "OPEN"):
        raise state.StateError("removal binding or PR head changed; fresh scope approval required")
    digest = _digest(binding)
    phases = [value["phase"] for value, author in records
              if value.get("binding") == digest and value.get("id") == operation["id"]]
    complete = any(value.get("phase") == "deleted" and value.get("binding") == digest and
                   value.get("id") == operation["id"] and
                   value.get("issue_id") == inventory["issue_id"] and
                   value.get("commit") == (pr.get("mergeCommit") or {}).get("oid")
                   for value, author in records)
    phase = "deleted" if complete and pr["state"] == "MERGED" else \
        "integrated" if "integrated" in phases and pr["state"] == "MERGED" else \
        "merged" if pr["state"] == "MERGED" else "rebind-pending" if pending else "prepared"
    current = {**binding, "phase": phase, "binding": digest, "pr_state": pr["state"], "view": pr,
               "operation": operation,
               "records": records, "confirmation": f"{repo}#{number}@{binding['head']}"}
    if phase != "deleted" and _receipt(root, current):
        current["phase"] = "receipt-pending"
    return current


def _person(confirmation, current, repo, run):
    if not auto.person(os.environ, sys.stdin is not None and sys.stdin.isatty()):
        raise state.StateError("only a person may approve removal merges or delete the issue")
    if confirmation != current.get("confirmation"):
        raise state.StateError("confirm the removal separately with " + current.get("confirmation", "a bound PR head"))
    login = run(["api", "user", "--jq", ".login"]).strip()
    if not state.can_push(repo, login, run):
        raise state.StateError("removal requires repository write permission")
    return login


def _checked(root, repo, operation, confirmation, run, final=False):
    current = status(root, repo, operation, run)
    _person(confirmation, {**current, "confirmation": ("delete " if final else "") + current["confirmation"]}, repo, run)
    return current


def _approval(current):
    return any(value.get("phase") == "merge-approved" and value.get("binding") == current["binding"]
               and value.get("id") == current["id"]
               and value.get("head") == current["head"] for value, author in current["records"])


def _event(current, phase, **extra):
    return {"id": current["id"], "binding": current["binding"], "phase": phase, **extra}


def _receipt_path(root, current):
    return config.evidence_dir(root) / "removals" / (current["id"] + ".json")


def _completion(current):
    return _event(current, "deleted", issue_id=current["inventory"]["issue_id"],
                  commit=(current["view"].get("mergeCommit") or {}).get("oid"))


def _receipt(root, current):
    path = _receipt_path(root, current)
    if path.parent.is_symlink() or current["pr_state"] != "MERGED":
        return False
    return base._read(path) == {"repo": current["repo"], "pr": current["pr"], "head": current["head"],
                                "completion": _completion(current)}


@contextmanager
def _acknowledge(root, current):
    """Open protected durable storage before deletion; persist only an acknowledged API success."""
    path = _receipt_path(root, current)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise state.StateError("unsafe removal success receipt directory")
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as receipt:
            yield
            json.dump({"repo": current["repo"], "pr": current["pr"], "head": current["head"],
                       "completion": _completion(current)}, receipt)
            receipt.flush()
            os.fsync(receipt.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise state.StateError(f"removal success receipt unavailable; inspect outcome, never infer from 404: {error}") from None
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive(root, repo, current, run):
    """Atomic remote reservation plus a locked local retry receipt; never steals another clone's attempt."""
    folder = config.common_dir(root) / "pulse" / "removals"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (current["id"] + ".finalize")
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "r+") as receipt:
            info = os.fstat(receipt.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise state.StateError("unsafe removal reservation receipt")
            fcntl.flock(receipt, fcntl.LOCK_EX | fcntl.LOCK_NB)
            saved = receipt.read()
            ref = f"refs/heads/pulse-remove-finalize/{current['item']}"
            if not saved:
                try:
                    run(["api", f"repos/{repo}/git/refs", "-f", f"ref={ref}", "-f", f"sha={current['head']}"])
                except state.StateError as error:
                    raise state.StateError(f"deletion reserved or reservation uncertain; inspect the original clone: {error}") from None
                receipt.write(current["binding"])
                receipt.flush()
                os.fsync(receipt.fileno())
            elif saved != current["binding"]:
                raise state.StateError("another removal owns the local reservation")
            if _git(root, "ls-remote", "--exit-code", "origin", ref).split() != [current["head"], ref]:
                raise state.StateError("removal reservation changed; keep the issue")
            yield
    except OSError as error:
        raise state.StateError(f"removal reserved by another process or receipt unavailable: {error}") from None


def _live_issue(repo, current, run):
    issue = _issue(repo, current["item"], run)
    _paused(issue, current["operation"], repo, run)
    if _target(issue) != current["inventory"]["target"] or issue.get("assignees") or \
            state.HOLD not in {label["name"] for label in issue.get("labels", [])} or \
            issue.get("blocking", {}).get("nodes", []):
        raise state.StateError("item identity, hold, holder or dependencies changed; deletion stopped")
    for pr in _prs(repo, run):
        if pr["number"] != current["pr"] and pr.get("state") == "OPEN":
            detail = _json(run, ["pr", "view", str(pr["number"]), "--repo", repo, "--json", "files,changedFiles"])
            paths = [entry["path"] for entry in detail.get("files", [])]
            if current["item"] in state.pr_items(pr) or current["inventory"]["spec"] in paths or \
                    len(paths) != detail.get("changedFiles"):
                raise state.StateError("new open or incompletely inventoried work requires scope review before removal")
    return issue


def check_scope(root: Path, repo: str, current: dict, run=state.gh) -> None:
    """Revalidate the bound, paused removal before running gates or merging."""
    if current["pr_state"] != "OPEN":
        raise state.StateError("removal PR is not open")
    if current["phase"] == "rebind-pending":
        raise state.StateError("removal rebind push is pending; confirm rebind first")
    _live_issue(repo, current, run)
    branches, problems = _work(root, current["item"])
    if problems or branches != current["inventory"]["branches"]:
        raise state.StateError("original item work changed; preserve and review before removal merge")
    branch, sha = _base(root)
    if sha != current["inventory"]["base_sha"]:
        raise state.StateError("base changed; rebuild removal and obtain fresh scope review")
    _git(root, "fetch", "-q", "--no-tags", "origin", current["head"])
    if _git(root, "rev-parse", current["head"] + "^{tree}") != current["tree"] or \
            _paths(root, sha, current["head"]) != current["files"]:
        raise state.StateError("removal tree or scope changed")
    _absent(root, current["head"], current["inventory"])


def _rebind_inventory(root, repo, current, run):
    _live_issue(repo, current, run)
    fresh = preview(root, repo, current["item"], run)
    if fresh["blocked"] or fresh != {**current["inventory"], "base_sha": fresh["base_sha"]}:
        raise state.StateError("removal scope changed beyond independent base commits; manual scope review required")
    before = current["inventory"]["base_sha"]
    _git(root, "merge-base", "--is-ancestor", before, fresh["base_sha"])
    if set(_paths(root, before, fresh["base_sha"])) & set(current["inventory"]["files"]):
        raise state.StateError("new base work overlaps removal scope; manual scope review required")
    return fresh


def rebind(root: Path, repo: str, operation: dict, inventory: dict, confirmation: str, run=state.gh) -> dict:
    """Confirm independent base advancement, append its binding, and fast-forward the removal branch.

    A posted binding precedes the push: retries can finish that exact head after an
    interrupted push. Prior bindings, approvals, worktrees and history remain intact.
    """
    current = status(root, repo, operation, run)
    expected = f"rebind {current['confirmation']} base {inventory['base_sha']}"
    _person(confirmation, {**current, "confirmation": expected}, repo, run)
    fresh = _rebind_inventory(root, repo, current, run)
    expected_inventory = current["inventory"] if current["phase"] == "rebind-pending" else fresh
    if current["pr_state"] != "OPEN" or inventory != expected_inventory:
        raise state.StateError("rebind scope changed; inspect and confirm again")
    if current["phase"] != "rebind-pending":
        if inventory == current["inventory"]:
            raise state.StateError("no new base to bind")
        home = config.pulse_dir(root) / "removals"
        home.mkdir(parents=True, exist_ok=True)
        worktree = Path(tempfile.mkdtemp(prefix=current["id"] + "-rebind-", dir=home)) / "tree"
        _git(root, "fetch", "-q", "--no-tags", "origin", current["head"])
        _git(root, "worktree", "add", "--detach", str(worktree), current["head"])
        _git(worktree, "merge", "--no-ff", "--no-edit", inventory["base_sha"])
        head = _git(worktree, "rev-parse", "HEAD")
        tree = _git(worktree, "rev-parse", "HEAD^{tree}")
        if _paths(root, inventory["base_sha"], head) != current["files"]:
            raise state.StateError("rebound removal changed scope; inspect retained worktree " + str(worktree))
        _absent(root, head, inventory)
        binding = {key: current[key] for key in ("id", "repo", "item", "actor", "branch", "pr", "files")}
        binding.update(phase="rebound", previous=current["binding"], inventory=inventory, head=head, tree=tree)
        if status(root, repo, operation, run)["binding"] != current["binding"] or _base(root)[1] != inventory["base_sha"]:
            raise state.StateError("removal changed while preparing rebind; inspect retained worktree")
        if not current["view"].get("isDraft"):
            run(["pr", "ready", str(current["pr"]), "--repo", repo, "--undo"])
        _post(repo, current["pr"], binding, run)
        current = status(root, repo, operation, run)
        if current["binding"] != _digest(binding):
            raise state.StateError("rebind comment not verified; no push")
    _git(root, "cat-file", "-e", current["head"] + "^{commit}")
    _git(root, "merge-base", "--is-ancestor", current["view"]["headRefOid"], current["head"])
    if _git(root, "rev-parse", current["head"] + "^{tree}") != current["tree"] or \
            _paths(root, inventory["base_sha"], current["head"]) != current["files"]:
        raise state.StateError("bound rebind tree changed; preserve and inspect it")
    _absent(root, current["head"], inventory)
    _git(root, "push", "origin", f"{current['head']}:refs/heads/{current['branch']}")
    result = status(root, repo, operation, run)
    if result["phase"] == "rebind-pending":
        raise state.StateError("rebind push not yet visible; retry the same confirmed rebind")
    return result


def merge_proof(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> dict:
    """Fresh merge preconditions for go; does not approve, merge or close anything."""
    current = _checked(root, repo, operation, confirmation, run)
    check_scope(root, repo, current, run)
    why = gates.evidence(root, current["head"], GATES) or gates.ready(current["view"])
    if why:
        raise state.StateError(why)
    carried = base._read(base._gates(root) / current["head"])
    if any(key.endswith(" carried from") for key in carried):
        raise state.StateError("removal requires fresh gates, not carried evidence")
    return current


def merge(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> dict:
    """Record a person's exact-head approval, then ask the go runner to merge it."""
    from pulse import go
    current = _checked(root, repo, operation, confirmation, run)
    if current["phase"] == "deleted" or current["pr_state"] == "MERGED":
        return current
    current = merge_proof(root, repo, operation, confirmation, run)
    if not _approval(current):
        _post(repo, current["pr"], _event(current, "merge-approved", head=current["head"]), run)
    checked = status(root, repo, operation, run)
    if checked["binding"] != current["binding"] or not _approval(checked):
        raise state.StateError("exact-head removal approval could not be verified")
    return go.removal(root, repo, operation, confirmation, gh_run=run)


def finalize(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> str:
    """Verify integrated removal, delete the issue last, and record an acknowledged result."""
    current = _checked(root, repo, operation, confirmation, run, final=True)
    if current["phase"] == "deleted":
        return f"#{current['item']} deleted; removal PR #{current['pr']} records completion"
    if _receipt(root, current):
        _post(repo, current["pr"], _completion(current), run)
        if status(root, repo, operation, run)["phase"] != "deleted":
            raise state.StateError("deletion acknowledged locally; completion repair not yet verified")
        return f"#{current['item']} deleted; repaired completion in removal PR #{current['pr']}"
    if current["pr_state"] != "MERGED" or not _approval(current):
        raise state.StateError("removal must be merged after separate exact-head approval before deletion")
    why = gates.evidence(root, current["head"], GATES)
    if why:
        raise state.StateError(why)
    _live_issue(repo, current, run)
    branch, sha = _base(root)
    integrated = (current["view"].get("mergeCommit") or {}).get("oid", "")
    if not base.SHA.fullmatch(integrated):
        raise state.StateError("merged PR has no integration commit")
    _git(root, "merge-base", "--is-ancestor", integrated, sha)
    if _git(root, "rev-parse", integrated + "^{tree}") != current["tree"]:
        raise state.StateError("integrated tree differs from reviewed removal; keep issue for review")
    if set(_paths(root, integrated, sha)) & set(current["inventory"]["files"]):
        raise state.StateError("removal scope changed since integration; renewed review required before deletion")
    _absent(root, sha, current["inventory"])
    branches, problems = _work(root, current["item"])
    if problems or branches != current["inventory"]["branches"]:
        raise state.StateError("original item work changed; preserve and review before deletion")
    _post(repo, current["pr"], _event(current, "integrated", commit=integrated), run)
    with _exclusive(root, repo, current, run):
        if status(root, repo, operation, run)["phase"] == "deleted":
            return f"#{current['item']} deleted; removal PR #{current['pr']} records completion"
        _live_issue(repo, current, run)
        if _base(root)[1] != sha:
            raise state.StateError("base changed before deletion; retain issue for review")
        try:
            with _acknowledge(root, current):
                run(["issue", "delete", str(current["item"]), "--repo", repo, "--yes"])
        except state.StateError as error:
            raise state.StateError(f"removal integrated, delete outcome uncertain; inspect and retry: {error}") from None
        state.drop_cache(root)
        try:
            _post(repo, current["pr"], _completion(current), run)
        except state.StateError as error:
            raise state.StateError(f"GitHub acknowledged deletion, completion receipt failed; retain PR #{current['pr']}: {error}") from None
    return f"#{current['item']} deleted after verified removal in PR #{current['pr']}"


def finish(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> str:
    """Perform one confirmed step; final deletion always needs a distinct confirmation."""
    if confirmation.startswith("delete "):
        return finalize(root, repo, operation, confirmation, run)
    current = merge(root, repo, operation, confirmation, run)
    if current["phase"] == "deleted":
        return f"#{current['item']} deleted; completion is recorded in PR #{current['pr']}"
    return f"Removal PR #{current['pr']} merged; issue retained until final confirmation: delete {current['confirmation']}"


def action_preview(root: Path, repo: str, n: int, run=state.gh) -> dict:
    """CLI/Map proposal: stage, lines, exact confirmation and snapshot. Never prompts or writes GitHub."""
    from pulse import lifecycle
    _identity(root, repo, n)
    actor = lifecycle._actor(repo, run)
    planned = {"repo": repo, "item": n, "actor": actor, "confirmation": "", "stage": "pending"}
    lines = [f"{repo}#{n}: removal as @{actor}.",
             "Code, specs and active references will be removed through a reviewed PR. "
             "The issue and ALL its comments will then be permanently deleted.",
             "Original branches, worktrees and Git history are retained; no force push or history reset."]
    if _find(repo, n, run):
        current = status(root, repo, n, run)
        planned["current"] = current
        inventory = current["inventory"]
        if current["phase"] == "deleted":
            planned["stage"] = "done"
            lines.append(f"Deleted; completion recorded in removal PR #{current['pr']}.")
        elif current["phase"] == "receipt-pending":
            planned.update(stage="finalize", confirmation="delete " + current["confirmation"])
            lines.append("GitHub acknowledged deletion; protected local receipt exists. "
                         "Confirm completion-comment repair only. The issue will NOT be deleted again.")
        elif current["pr_state"] == "OPEN" and (current["phase"] == "rebind-pending" or
                                                _base(root)[1] != inventory["base_sha"]):
            fresh_inventory = _rebind_inventory(root, repo, current, run)
            inventory = inventory if current["phase"] == "rebind-pending" else fresh_inventory
            planned.update(stage="rebind", inventory=inventory,
                           confirmation=f"rebind {current['confirmation']} base {inventory['base_sha']}")
            lines.append("Confirm the refreshed scope against the new base. The removal branch advances "
                         "without force; previous bindings stay recorded. Fresh gates and separate exact-head "
                         "merge approval are required before integration.")
        elif current["pr_state"] == "MERGED":
            why = gates.evidence(root, current["head"], GATES)
            if why:
                lines.append(why)
            elif not _approval(current):
                lines.append("Merged without a verified removal approval; keep the issue and investigate.")
            else:
                planned.update(stage="finalize", confirmation="delete " + current["confirmation"])
                lines.append("The removal PR is merged. Confirm irreversible issue/comment deletion separately; "
                             "integration and the stopped operation will be checked again before deleting.")
        else:
            why = gates.evidence(root, current["head"], GATES)
            carried = base._read(base._gates(root) / current["head"])
            why = why or ("Fresh review and audit required; carried evidence is not sufficient."
                          if any(key.endswith(" carried from") for key in carried) else "")
            if why or current["view"].get("isDraft"):
                planned.update(stage="check", confirmation="check " + current["confirmation"])
                lines.append(f"PR #{current['pr']} needs its own gates: {why or 'draft'}. "
                             "Confirm to run configured tests and a fresh review/audit session through pulse go. "
                             "This does not approve a merge or delete the issue.")
            elif gates.ready(current["view"]):
                lines.append(f"PR #{current['pr']} waits: {gates.ready(current['view'])}.")
            else:
                planned.update(stage="merge", confirmation=current["confirmation"])
                lines.append("Confirm the complete removal scope and preservation of unrelated features. "
                             "This merges the exact reviewed head; it does NOT delete the issue yet.")
        lines.append(f"Removal PR #{current['pr']}; exact head {current['head']}.")
    else:
        raw = _issue(repo, n, run)
        current = lifecycle.operation(raw, lifecycle.trusted(repo, run))
        if current.get("phase") == "invalid":
            raise state.StateError(current["error"])
        inventory = preview(root, repo, n, run)
        planned["inventory"] = inventory
        if current.get("action") == "delete" and current.get("phase") in ("requested", "stopped", "paused"):
            if current["phase"] != "paused" or current.get("retained"):
                lines.append("Stop pending: the original holder must acknowledge and secure the work. No PR prepared.")
            elif inventory["blocked"]:
                lines.extend(inventory["blocked"])
            else:
                planned.update(stage="prepare", confirmation=f"{repo}#{n}",
                               operation={**current, "item": n, "inventory": inventory})
                lines.append("Work is paused. Confirm this scope to prepare the removal PR.")
        else:
            life = lifecycle.preview(root, repo, n, "delete", run)
            planned.update(stage="stop", lifecycle=life, confirmation=life["confirmation"])
            lines.extend(life["lines"])
            lines.extend(inventory["blocked"])
    lines.append(f"Base: {inventory['base']} at {inventory['base_sha']}.")
    lines.append("Sources: " + (", ".join(f"PR #{entry['pr']} ({entry['commit']})"
                                         for entry in inventory["sources"]) or "not established; manual scope required"))
    lines.append("Affected paths: " + (", ".join(inventory["files"]) or "scope not established"))
    lines.append("Dependent items: " + (", ".join(f"#{entry['number']}" for entry in inventory["dependents"]) or "none"))
    lines.extend(f"Preserved branch: {ref} at {head}" for ref, head in inventory["branches"])
    planned["lines"] = [config.printable(line) for line in lines]
    planned["snapshot"] = _digest(planned)
    return planned


def apply_action(root: Path, repo: str, planned: dict, confirmation: str, run=state.gh) -> str:
    """Apply one unchanged proposal. Shared by CLI and Map; no terminal input or implicit final deletion."""
    from pulse import lifecycle
    if not confirmation:
        return "cancelled; nothing changed"
    if not auto.person(os.environ, sys.stdin is not None and sys.stdin.isatty()):
        raise state.StateError("only a person may perform deletion actions")
    if repo != planned.get("repo") or confirmation != planned.get("confirmation"):
        raise state.StateError("confirmation does not match the deletion preview")
    fresh = action_preview(root, repo, planned["item"], run)
    if fresh != planned:
        raise state.StateError("deletion state changed after preview; inspect and confirm again")
    stage, number = planned["stage"], planned["item"]
    if stage == "stop":
        message = lifecycle.apply(root, repo, planned["lifecycle"], confirmation, run)
        raw = _issue(repo, number, run)
        current = lifecycle.operation(raw, lifecycle.trusted(repo, run))
        if current.get("phase") != "paused" or current.get("retained"):
            return message + "; deletion pending, original issue retained"
        inventory = preview(root, repo, number, run)
        if inventory != planned["inventory"] or inventory["blocked"]:
            return message + "; scope changed or needs clarification; run pulse delete again for a fresh preview"
        operation = {**current, "item": number, "inventory": inventory}
    elif stage == "prepare":
        operation = planned["operation"]
    elif stage in ("merge", "finalize"):
        return finish(root, repo, planned["current"]["operation"], confirmation, run)
    elif stage == "check":
        from pulse import go
        result = go.removal(root, repo, planned["current"]["operation"], confirmation, gh_run=run, check=True)
        return f"Removal gates passed for PR #{result['pr']}; run pulse delete {number} for separate merge approval."
    elif stage == "rebind":
        result = rebind(root, repo, planned["current"]["operation"], planned["inventory"], confirmation, run)
        return f"Removal PR #{result['pr']} rebound at {result['head']}; run pulse delete {number} for fresh gates."
    else:
        raise state.StateError("no deletion action is ready")
    result = prepare(root, repo, number, operation, run)
    return f"Removal PR #{result['pr']} prepared; issue retained. Run pulse delete {number} again " \
           "to confirm and start its real tests, review and audit."


def command(root: Path, repo: str, n: int, run=state.gh) -> int:
    """Interactive pulse delete entry point; repeated calls advance only explicitly confirmed stages."""
    try:
        if not auto.person(os.environ, sys.stdin is not None and sys.stdin.isatty()):
            raise state.StateError("only a person may run pulse delete in their terminal or Map")
        planned = action_preview(root, repo, n, run)
        print("\n".join(planned["lines"]))
        if not planned["confirmation"]:
            return 0
        confirmation = input(f"Type {planned['confirmation']} to confirm, or Enter to cancel: ").strip()
        print(config.printable(apply_action(root, repo, planned, confirmation, run)))
        return 0
    except (EOFError, KeyboardInterrupt):
        print("Cancelled; no further deletion action requested.")
        return 0
    except state.StateError as error:
        print(config.printable(f"pulse delete: {error}"))
        return 1
