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
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from pulse import auto, base, config, merge as gates, ready, shared, state


ISSUE_FIELDS = "id,number,title,state,body,labels,assignees,parent,blocking,blockedBy,comments"
MARK = re.compile(r"<!-- pulse:remove (\{[^\n]*\}) -->")
GATES = ("tests", "review", "audit")


def _git(root, *args, input=None):
    try:
        result = ready.net_git(root, *args) if args[0] in ("ls-remote", "fetch", "push") else \
            subprocess.run(["git", *args], cwd=root, input=input, capture_output=True, text=True, timeout=120)
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
    """Inventory only proven canonical integration; missing attribution requires manual scope review."""
    _identity(root, repo, n)
    branch, sha = _base(root)
    issue = _issue(repo, n, run)
    normalized = state.normalize(issue)
    spec = normalized.get("spec") or ""
    items = shared.read(root)[1]["items"]
    current = items.get(str(n), {})
    original = (current.get("removal") or {}).get("original", current)
    blocked, sources = [], []
    if normalized.get("type") not in state.WORK:
        blocked.append("only features, improvements and fixes can be removed")
    if current.get("claim") or issue.get("assignees"):
        blocked.append("the holder must acknowledge the stop and release the claim")
    dependents = issue.get("blocking", {}).get("nodes", [])
    if dependents:
        blocked.append("dependent items require manual scope review")
    if not spec or PurePosixPath(spec).is_absolute() or ".." in PurePosixPath(spec).parts:
        blocked.append("missing or unsafe spec scope")
    result, commit = original.get("result") or {}, original.get("merge")
    for number, item in items.items():
        other = (item.get("removal") or {}).get("original", item)
        if number != str(n) and commit and other.get("merge") == commit:
            blocked.append(f"canonical integration also belongs to #{number}; manual scope review required")
    if not original.get("done") or not commit or not result:
        blocked.append("no complete canonical integration provenance; manual scope required")
    else:
        _git(root, "fetch", "-q", "--no-tags", "origin", commit, result["head"])
        parents = _git(root, "rev-list", "--parents", "-1", commit).split()[1:]
        order = _git(root, "rev-list", "--first-parent", sha).splitlines()
        if parents != [result["base"], result["head"]] or commit not in order or \
                _patch(root, result["base"], result["head"]) != _patch(root, result["base"], commit):
            blocked.append("ambiguous integration parents, history or merge resolution; manual scope required")
        else:
            files = _paths(root, result["base"], commit)
            if spec not in files:
                blocked.append("spec lacks canonical change provenance; manual scope required")
            sources.append({"commit": commit, "head": result["head"], "parent": result["base"],
                            "mainline": 1, "files": files})
    branches, problems = _work(root, n)
    blocked.extend(problems)
    for ref, head in branches:
        try:
            _git(root, "merge-base", "--is-ancestor", head, sha)
        except state.StateError:
            blocked.append(f"unintegrated work on {ref}; secure and explicitly review its scope")
    return {"repo": repo, "item": n, "issue_id": issue["id"], "target": _target(issue),
            "base": branch, "base_sha": sha, "spec": spec, "sources": sources,
            "files": sorted({path for source in sources for path in source["files"]}),
            "branches": branches, "dependents": dependents, "blocked": blocked}


def marker(value: dict) -> str:
    """Machine record retained for historical removal comments."""
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
    if not state.can_push(repo, operation["actor"], run):
        raise state.StateError("deletion actor no longer has write permission")
    for comment in reversed(issue.get("comments", [])):
        body = comment.get("body", "")
        if body.startswith("<!-- pulse:lifecycle ") and operation["id"] in body and \
                '"paused"' in body and type(comment.get("id")) is int and state.writer(comment, repo, run, known) is True:
            return {"comment": comment["id"], "author": comment["author"]["login"], "operation": operation["id"]}
    raise state.StateError("deletion operation has no authenticated comment reference")








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


def _change(root, n, kind, current, **payload):
    receipt = shared.update(root, gates._transition(n, kind, current, **payload))
    if receipt["status"] != "confirmed":
        raise state.StateError(receipt["reason"])
    return receipt["data"]


def _claim(root, current):
    holder = uuid.uuid4().hex
    item = _change(root, current["item"], "claim", current["canonical"], holder=holder,
                   files=current["inventory"]["files"], removal=current["id"])
    return item, holder


def _release(root, number, holder, work=None):
    item = shared.read(root)[1]["items"][str(number)]
    if (item.get("claim") or {}).get("holder") == holder:
        _change(root, number, "release", item, holder=holder, work={**(item.get("work") or {}), **(work or {})})


def _fresh(root, head):
    why = gates.evidence(root, head, GATES)
    if why:
        raise state.StateError(why)
    if any(key.endswith(" carried from") for key in base._read(base._gates(root) / head)):
        raise state.StateError("removal requires fresh gates, not carried evidence")


def record_gates(root, repo, operation, run=state.gh):
    """Publish only this supervisor's fresh evidence; human review approval remains separate."""
    current = status(root, repo, operation, run)
    check_scope(root, repo, current, run)
    _fresh(root, current["head"])
    item, holder = _claim(root, current)
    try:
        op = gates._transition(current["item"], "result", item, holder=holder, branch=current["branch"],
                               head=current["head"], base=current["inventory"]["base_sha"],
                               gates={gate: "pass" for gate in GATES})
        receipt = shared.publish(root, op, current["branch"], current["head"], current["head"])
        if receipt["status"] != "confirmed":
            raise state.StateError(receipt["reason"])
    finally:
        _release(root, current["item"], holder)
    return status(root, repo, operation, run)


def integration_proof(root, repo, number, item, run=state.gh):
    """Fresh removal-specific scope and authority for the common integration engine."""
    current = status(root, repo, number, run)
    check_scope(root, repo, current, run)
    _fresh(root, current["head"])
    if not _approval(current) or current["approval"] != item.get("approval"):
        raise state.StateError("removal approval changed")
    why = gates.approval_proof(repo, number, current["approval"], run, removal=current["binding"])
    if why:
        raise state.StateError(why)


def integrate(root, repo, operation, confirmation, run=state.gh):
    current = _checked(root, repo, operation, confirmation, run)
    if current["phase"] != "prepared":
        return _recovered(root, repo, current, run)
    integration_proof(root, repo, current["item"], current["canonical"], run)
    _, holder = _claim(root, current)
    try:
        outcome = gates.integrate(root, repo, current["item"], holder, run=run)
        if outcome["status"] != "done":
            raise state.StateError(outcome["why"])
    finally:
        snapshot = shared.read(root)[1]
        if not snapshot["integration"]:
            _release(root, current["item"], holder)
    return status(root, repo, operation, run)


def _recovered(root, repo, current, run):
    outcome = gates.integrate(root, repo, current["item"], "", run=run)
    if outcome["status"] != "done":
        raise state.StateError(outcome["why"])
    return current


def prepare(root: Path, repo: str, n: int, operation: dict, run=state.gh) -> dict:
    """Archive the completed generation, then publish its reviewed-scope revert without touching the caller."""
    inventory = _operation(repo, n, operation)
    _person(f"{repo}#{n}", {"confirmation": f"{repo}#{n}"}, repo, run)
    _identity(root, repo, n)
    previous = shared.read(root)[1]["items"].get(str(n), {})
    if previous.get("removal"):
        return status(root, repo, operation, run)
    fresh = preview(root, repo, n, run)
    if fresh != inventory or fresh["blocked"]:
        raise state.StateError("removal inventory changed or blocked: " + "; ".join(fresh["blocked"]))
    issue = _issue(repo, n, run)
    proof = _paused(issue, operation, repo, run)
    if state.HOLD not in {label["name"] for label in issue.get("labels", [])}:
        raise state.StateError("removal waits for the confirmed deletion hold")
    branch = f"pulse-remove/{n}"
    if shared.remote_head(root, branch):
        raise state.StateError("removal branch already reserved; inspect retained work")
    current = _change(root, n, "removal_begin", previous, operation=operation, proof=proof)
    holder = uuid.uuid4().hex
    current = _change(root, n, "claim", current, holder=holder, files=fresh["files"], removal=operation["id"])
    home = config.pulse_dir(root) / "removals"
    home.mkdir(parents=True, exist_ok=True)
    tree = home / operation["id"]
    try:
        if tree.exists() or tree.is_symlink():
            raise state.StateError("removal worktree already exists")
        _git(root, "worktree", "add", "--detach", str(tree), fresh["base_sha"])
        for source in fresh["sources"]:
            _git(tree, "revert", "--no-commit", "-m", "1", source["commit"])
        prepared = _git(tree, "write-tree")
        _absent(tree, prepared, fresh)
        files = _paths(tree, fresh["base_sha"], prepared)
        if not files or set(files) - set(fresh["files"]):
            raise state.StateError("revert has empty or unexpected scope; manual scope review required")
        _git(tree, "commit", "-m", f"revert: remove item #{n} ({operation['id']})")
        head = _git(tree, "rev-parse", "HEAD")
        if preview(root, repo, n, run) != {**fresh, "blocked": ["the holder must acknowledge the stop and release the claim"]}:
            raise state.StateError("scope changed during removal preparation")
        op = gates._transition(n, "published", current, holder=holder, branch=branch, head=head,
                               phase="removal", worktree=str(tree))
        receipt = shared.publish(tree, op, branch, head, "")
        if receipt["status"] != "confirmed":
            raise state.StateError(receipt["reason"])
    except (state.StateError, OSError) as error:
        raise state.StateError(f"removal preparation stopped; original retained; work preserved at {tree}: {error}") from None
    finally:
        _release(root, n, holder, {"branch": branch, "worktree": str(tree), "phase": "removal"})
    return status(root, repo, operation, run)


def status(root: Path, repo: str, operation: dict | int, run=state.gh) -> dict:
    """Canonical status remains recoverable after the original issue and its comments are deleted."""
    number = operation if type(operation) is int else operation.get("item")
    _identity(root, repo, number)
    item = shared.read(root)[1]["items"].get(str(number), {})
    metadata = item.get("removal")
    if not metadata:
        return {"phase": "paused", "item": number, "blocked": ["no prepared removal"]}
    stored = metadata["operation"]
    if type(operation) is not int and operation != stored:
        raise state.StateError("removal operation or inventory changed")
    inventory = metadata["inventory"]
    work, result = item.get("work") or {}, item.get("result") or {}
    head, branch = result.get("head") or work.get("head", ""), result.get("branch") or work.get("branch", "")
    if not head:
        raise state.StateError("removal preparation incomplete; inspect preserved work: " + str(work))
    _git(root, "fetch", "-q", "--no-tags", "origin", head)
    binding = _digest({"id": stored["id"], "inventory": inventory, "head": head, "branch": branch})
    current = {"id": stored["id"], "repo": repo, "item": number, "actor": stored["actor"],
               "operation": stored, "inventory": inventory, "head": head, "branch": branch,
               "tree": _git(root, "rev-parse", head + "^{tree}"),
               "files": _paths(root, inventory["base_sha"], head), "binding": binding,
               "phase": "deleted" if metadata["deleted"] else "integrated" if item["done"] else "prepared",
               "merge": item["merge"], "approval": item["approval"], "canonical": item,
               "worktree": work.get("worktree", ""), "confirmation": f"{repo}#{number}@{head}"}
    if current["phase"] == "integrated" and _receipt(root, current):
        current["phase"] = "receipt-pending"
    if current["phase"] == "prepared":
        pending = _pending_rebind(root, current)
        if pending:
            current.update(phase="rebind-pending", pending=pending, head=pending["head"],
                           inventory=pending["inventory"], worktree=pending["worktree"],
                           tree=_git(root, "rev-parse", pending["head"] + "^{tree}"),
                           confirmation=f"{repo}#{number}@{pending['head']}")
    return current


def _person(confirmation, current, repo, run):
    if not auto.person(os.environ, sys.stdin is not None and sys.stdin.isatty()):
        raise state.StateError("only a person may approve removal merges or delete the issue")
    if confirmation != current.get("confirmation"):
        raise state.StateError("confirm the removal separately with " + current.get("confirmation", "a bound removal head"))
    login = run(["api", "user", "--jq", ".login"]).strip()
    if not state.can_push(repo, login, run):
        raise state.StateError("removal requires repository write permission")
    return login


def _checked(root, repo, operation, confirmation, run, final=False):
    current = status(root, repo, operation, run)
    _person(confirmation, {**current, "confirmation": ("delete " if final else "") + current["confirmation"]}, repo, run)
    return current


def _approval(current):
    approval = current.get("approval") or {}
    return approval.get("head") == current["head"] and approval.get("base") == current["inventory"]["base_sha"]


def _event(current, phase, **extra):
    return {"id": current["id"], "binding": current["binding"], "phase": phase, **extra}


def _receipt_path(root, current):
    return config.evidence_dir(root) / "removals" / (current["id"] + ".json")


def _completion(current):
    return _event(current, "deleted", issue_id=current["inventory"]["issue_id"], commit=current["merge"])


def _receipt(root, current):
    path = _receipt_path(root, current)
    if path.parent.is_symlink() or not current["merge"]:
        return False
    return base._read(path) == {"repo": current["repo"], "head": current["head"], "completion": _completion(current)}


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
            json.dump({"repo": current["repo"], "head": current["head"],
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
    """One local retry owner reserves deletion in canonical state before its irreversible API call."""
    folder = config.evidence_dir(root) / "removals"
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink():
        raise state.StateError("unsafe removal reservation directory")
    path = folder / (current["id"] + ".finalize")
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "r+") as receipt:
            info = os.fstat(receipt.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise state.StateError("unsafe removal reservation receipt")
            fcntl.flock(receipt, fcntl.LOCK_EX | fcntl.LOCK_NB)
            holder = receipt.read()
            if not holder:
                holder = uuid.uuid4().hex
                receipt.write(holder)
                receipt.flush()
                os.fsync(receipt.fileno())
            item = shared.read(root)[1]["items"][str(current["item"])]
            _change(root, current["item"], "removal_finalize", item, holder=holder,
                    id=current["id"], merge=current["merge"])
            yield holder
    except OSError as error:
        raise state.StateError(f"deletion reserved or receipt unavailable: {error}") from None


def _live_issue(repo, current, run):
    issue = _issue(repo, current["item"], run)
    _paused(issue, current["operation"], repo, run)
    if _target(issue) != current["inventory"]["target"] or issue.get("assignees") or \
            state.HOLD not in {label["name"] for label in issue.get("labels", [])} or \
            issue.get("blocking", {}).get("nodes", []):
        raise state.StateError("item identity, hold, holder or dependencies changed; deletion stopped")
    return issue


def check_scope(root: Path, repo: str, current: dict, run=state.gh) -> None:
    """Revalidate retained original work, exact removal scope and the current base."""
    if current["phase"] != "prepared":
        raise state.StateError("removal is not awaiting integration")
    _live_issue(repo, current, run)
    branches, problems = _work(root, current["item"])
    if problems or branches != current["inventory"]["branches"]:
        raise state.StateError("original item work changed; preserve and review before removal")
    if _base(root) != (current["inventory"]["base"], current["inventory"]["base_sha"]):
        raise state.StateError("base changed; rebind removal and obtain fresh scope review")
    if shared.remote_head(root, current["branch"]) != current["head"]:
        raise state.StateError("removal head changed")
    if not current["files"] or set(current["files"]) - set(current["inventory"]["files"]):
        raise state.StateError("removal scope changed")
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


def _rebind_path(root, current):
    path = config.evidence_dir(root) / "removals" / (current["id"] + ".rebind")
    if path.parent.is_symlink() or path.is_symlink():
        raise state.StateError("unsafe removal rebind receipt")
    return path


def _pending_rebind(root, current):
    path = _rebind_path(root, current)
    if not path.exists():
        return None
    pending = base._read(path)
    if (set(pending) != {"repo", "binding", "previous", "inventory", "head", "worktree"}
            or not all(isinstance(pending[key], str) for key in ("repo", "binding", "previous", "head", "worktree"))
            or not isinstance(pending["inventory"], dict) or not base.SHA.fullmatch(pending["head"])):
        raise state.StateError("unreadable removal rebind receipt; inspect retained work")
    if pending["repo"] != current["repo"]:
        raise state.StateError("removal rebind receipt names another repository")
    if pending["binding"] == current["binding"] and pending["previous"] == current["head"]:
        inventory = pending["inventory"]
        if (not isinstance(inventory.get("base_sha"), str) or not base.SHA.fullmatch(inventory["base_sha"])
                or inventory != {**current["inventory"], "base_sha": inventory["base_sha"]}):
            raise state.StateError("prepared rebind inventory changed; inspect retained work")
        return pending
    if pending["head"] == current["head"] and pending["inventory"] == current["inventory"]:
        return None  # The exact attempt was published, including after a lost response.
    raise state.StateError("retained rebind binding is stale; inspect preserved work at " + pending["worktree"])


def _save_rebind(root, current, inventory, tree, head):
    path = _rebind_path(root, current)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = {"repo": current["repo"], "binding": current["binding"], "previous": current["head"],
               "inventory": inventory, "head": head, "worktree": str(tree)}
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as saved:
            json.dump(pending, saved)
            saved.flush()
            os.fsync(saved.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise state.StateError(f"cannot preserve prepared rebind at {tree}: {error}") from None
    finally:
        temporary.unlink(missing_ok=True)


def rebind(root: Path, repo: str, operation: dict, inventory: dict, confirmation: str, run=state.gh) -> dict:
    current = status(root, repo, operation, run)
    _person(confirmation, {**current, "confirmation": f"rebind {current['confirmation']} base {inventory['base_sha']}"}, repo, run)
    fresh = _rebind_inventory(root, repo, current, run)
    pending = current.get("pending")
    if current["phase"] not in {"prepared", "rebind-pending"} or inventory != (pending["inventory"] if pending else fresh):
        raise state.StateError("rebind scope changed")
    previous = pending["previous"] if pending else current["head"]
    if shared.remote_head(root, current["branch"]) != previous:
        raise state.StateError("removal head changed before rebind publication")
    item, holder = _claim(root, current)
    home = config.pulse_dir(root) / "removals"
    tree = Path(pending["worktree"]) if pending else Path(tempfile.mkdtemp(prefix=current["id"] + "-rebind-", dir=home)) / "tree"
    try:
        if not pending:
            _git(root, "worktree", "add", "--detach", str(tree), current["head"])
            _git(tree, "merge", "--no-ff", "--no-edit", inventory["base_sha"])
        elif (tree.is_symlink() or config.common_dir(tree) != config.common_dir(root)
              or _git(tree, "status", "--porcelain", "--untracked-files=all", "--ignored")
              or _git(tree, "rev-parse", "HEAD") != pending["head"]):
            raise state.StateError("prepared rebind worktree changed; preserve and inspect " + str(tree))
        head = _git(tree, "rev-parse", "HEAD")
        if (_git(root, "rev-list", "--parents", "-1", head).split()[1:] != [previous, inventory["base_sha"]]
                or _paths(root, inventory["base_sha"], head) != current["files"]):
            raise state.StateError("rebound removal changed scope; inspect retained worktree " + str(tree))
        _absent(root, head, inventory)
        if not pending:
            _save_rebind(root, current, inventory, tree, head)
        op = gates._transition(current["item"], "removal_rebind", item, holder=holder, inventory=inventory,
                               branch=current["branch"], head=head, phase="removal", worktree=str(tree))
        receipt = shared.publish(tree, op, current["branch"], head, previous)
        if receipt["status"] != "confirmed":
            raise state.StateError(receipt["reason"])
    finally:
        _release(root, current["item"], holder)
    return status(root, repo, operation, run)


def merge_proof(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> dict:
    current = _checked(root, repo, operation, confirmation, run)
    check_scope(root, repo, current, run)
    _fresh(root, current["head"])
    return current


def merge(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> dict:
    from pulse import go
    current = _checked(root, repo, operation, confirmation, run)
    if current["phase"] != "prepared":
        return _recovered(root, repo, current, run)
    current = merge_proof(root, repo, operation, confirmation, run)
    if not current["canonical"].get("result"):
        raise state.StateError("removal gates have not published their result")
    if not _approval(current):
        oid = uuid.uuid4().hex
        binding = {"operation": oid, "item": current["item"], "head": current["head"],
                   "base": current["inventory"]["base_sha"], "removal": current["binding"]}
        url = run(["issue", "comment", str(current["item"]), "--repo", repo, "--body",
                   "pulse removal approval " + json.dumps(binding, sort_keys=True, separators=(",", ":"))])
        match = re.fullmatch(r"https://github[.]com/" + re.escape(repo) + r"/issues/" + str(current["item"]) +
                             r"#issuecomment-([1-9][0-9]*)\s*", url)
        if not match:
            raise state.StateError("removal approval comment was not acknowledged")
        actor = run(["api", "user", "--jq", ".login"]).strip()
        approval = {"head": binding["head"], "base": binding["base"],
                    "proof": {"comment": int(match.group(1)), "author": actor, "operation": oid}}
        why = gates.approval_proof(repo, current["item"], approval, run, removal=current["binding"])
        if why:
            raise state.StateError(why)
        _change(root, current["item"], "approve", current["canonical"], **approval)
    return go.removal(root, repo, operation, confirmation, gh_run=run)


def finalize(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> str:
    current = _checked(root, repo, operation, confirmation, run, final=True)
    if current["phase"] == "deleted":
        return f"#{current['item']} deleted; canonical removal records completion"
    repair = _receipt(root, current)
    if not repair:
        if current["phase"] != "integrated" or not _approval(current):
            raise state.StateError("removal requires separately approved integration before deletion")
        why = gates.approval_proof(repo, current["item"], current["approval"], run, removal=current["binding"])
        if why:
            raise state.StateError(why)
        _fresh(root, current["head"])
        _recovered(root, repo, current, run)
        _live_issue(repo, current, run)
        _, sha = _base(root)
        integrated = current["merge"]
        _git(root, "merge-base", "--is-ancestor", integrated, sha)
        if _git(root, "rev-parse", integrated + "^{tree}") != current["tree"] or \
                set(_paths(root, integrated, sha)) & set(current["inventory"]["files"]):
            raise state.StateError("integrated removal tree or later scope changed")
        _absent(root, sha, current["inventory"])
        branches, problems = _work(root, current["item"])
        if problems or branches != current["inventory"]["branches"]:
            raise state.StateError("original work changed before deletion")
    with _exclusive(root, repo, current, run) as holder:
        if not repair:
            _live_issue(repo, current, run)
            if _base(root)[1] != sha:
                raise state.StateError("base changed before deletion")
            try:
                with _acknowledge(root, current):
                    run(["issue", "delete", str(current["item"]), "--repo", repo, "--yes"])
            except state.StateError as error:
                raise state.StateError(f"delete outcome uncertain; retain receipt and inspect: {error}") from None
        item = shared.read(root)[1]["items"][str(current["item"])]
        _change(root, current["item"], "removal_deleted", item, holder=holder, id=current["id"], merge=current["merge"])
    state.drop_cache(root)
    return f"#{current['item']} deleted after verified removal; canonical completion retained"


def finish(root: Path, repo: str, operation: dict, confirmation: str, run=state.gh) -> str:
    if confirmation.startswith("delete "):
        return finalize(root, repo, operation, confirmation, run)
    current = merge(root, repo, operation, confirmation, run)
    return f"Removal {current['phase']}; issue retained until final confirmation: delete {current['confirmation']}"


def action_preview(root: Path, repo: str, n: int, run=state.gh) -> dict:
    """One explicit deletion step for CLI and Map, with the complete bound scope."""
    from pulse import lifecycle
    _identity(root, repo, n)
    actor = lifecycle._actor(repo, run)
    planned = {"repo": repo, "item": n, "actor": actor, "confirmation": "", "stage": "pending"}
    lines = [f"{repo}#{n}: removal as @{actor}.",
             "Remove code, spec and active references through a separately reviewed result.",
             "The issue and ALL its comments will be permanently deleted only after another confirmation.",
             "Original branches, worktrees and Git history are retained."]
    item = shared.read(root)[1]["items"].get(str(n), {})
    if item.get("removal"):
        current = status(root, repo, n, run)
        planned["current"] = current
        inventory = current["inventory"]
        if current["phase"] == "deleted":
            planned["stage"] = "done"
            lines.append("Deleted; canonical completion retained.")
        elif current["phase"] in {"receipt-pending", "integrated"}:
            planned.update(stage="finalize", confirmation="delete " + current["confirmation"])
            lines.append("Confirm irreversible issue/comment deletion separately; a saved success receipt repairs only completion.")
        elif current["phase"] == "rebind-pending":
            _rebind_inventory(root, repo, current, run)
            planned.update(stage="rebind", inventory=inventory,
                           confirmation=f"rebind {current['confirmation']} base {inventory['base_sha']}")
            lines.append("Retry publication of the preserved exact rebind commit; fresh gates follow publication.")
        elif _base(root)[1] != inventory["base_sha"]:
            inventory = _rebind_inventory(root, repo, current, run)
            planned.update(stage="rebind", inventory=inventory,
                           confirmation=f"rebind {current['confirmation']} base {inventory['base_sha']}")
            lines.append("Confirm this independent base change; fresh gates and personal removal approval follow.")
        else:
            try:
                _fresh(root, current["head"])
                why = "" if current["canonical"].get("result") else "gates are not published"
            except state.StateError as error:
                why = str(error)
            planned.update(stage="check" if why else "merge",
                           confirmation=("check " if why else "") + current["confirmation"])
            lines.append("Run fresh tests, review and audit: " + why if why else
                         "Personally approve this exact removal scope and its integration; retain the issue.")
        lines.append(f"Removal branch {current['branch']}; exact head {current['head']}.")
    else:
        raw = _issue(repo, n, run)
        current = lifecycle.operation(raw, lifecycle.trusted(repo, run))
        if current.get("phase") == "invalid":
            raise state.StateError(current["error"])
        inventory = preview(root, repo, n, run)
        planned["inventory"] = inventory
        if current.get("action") == "delete" and current.get("phase") in ("requested", "stopped", "paused"):
            if current["phase"] != "paused" or current.get("retained"):
                lines.append("Stop pending: the original holder must acknowledge and secure the work.")
            elif not inventory["blocked"]:
                planned.update(stage="prepare", confirmation=f"{repo}#{n}",
                               operation={**current, "item": n, "inventory": inventory})
                lines.append("Work is paused. Confirm this scope to prepare the removal result.")
        else:
            life = lifecycle.preview(root, repo, n, "delete", run)
            planned.update(stage="stop", lifecycle=life, confirmation=life["confirmation"])
            lines.extend(life["lines"])
    lines.append(f"Base: {inventory['base']} at {inventory['base_sha']}.")
    lines.append("Sources: " + (", ".join(source["commit"] for source in inventory["sources"]) or "manual scope required"))
    lines.append("Affected paths: " + (", ".join(inventory["files"]) or "scope not established"))
    lines.extend(inventory["blocked"])
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
        return f"Removal gates passed at {result['head']}; run pulse delete {number} for personal removal approval."
    elif stage == "rebind":
        result = rebind(root, repo, planned["current"]["operation"], planned["inventory"], confirmation, run)
        return f"Removal rebound at {result['head']}; run pulse delete {number} for fresh gates."
    else:
        raise state.StateError("no deletion action is ready")
    result = prepare(root, repo, number, operation, run)
    return f"Removal result {result['head']} prepared; issue retained. Run pulse delete {number} again " \
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
