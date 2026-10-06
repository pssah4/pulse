"""Integration of exact published results, backed by protected local gate evidence and current authority.
Normal project hooks run before the shared state and base advance together through one atomic push."""
from __future__ import annotations

import fnmatch
import json
import re
import shlex
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from pulse import base, config, review, state

DEFAULTS = (".pulse/", ".github/", ".husky/")       # what runs or guards the project, whatever the config says
RUNNERS = re.compile(r"(^|/)(Makefile|tox\.ini|noxfile\.py|pytest\.ini|conftest\.py|setup\.cfg|"
                     r"\.pre-commit-config\.yaml|(jest|vitest|playwright)\.config\.[cm]?[jt]s)$")   # test runners


def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def protected(cfg: dict, files: list) -> list:
    """The result files shown before integration (FR-04), in their order: .pulse/, .github/, .husky/,
    manifests and lockfiles, test-runner configs, what `protected` names (a directory with a trailing /, a path, or
    a glob), and every word setup and verify name that is one of the files."""
    words = " ".join(c for c in (cfg.get("setup"), cfg.get("verify")) if c)
    try:
        named = set(shlex.split(words))
    except ValueError:         # an unclosed quote: the words as they stand
        named = set(words.split())
    rules = (*DEFAULTS, *(cfg.get("protected") or ()))
    return [f for f in files if f in named or review.MANIFEST.search(f) or RUNNERS.search(f) or
            any(f.startswith(p) if p.endswith("/") else fnmatch.fnmatchcase(f, p) for p in rules)]


def evidence(root: Path, head: str, gates, *, binding=None) -> str:
    """"" when this clone's pulse go vouches for head (FR-03): gates/<head> in config.evidence_dir, written for
    exactly that commit (#117) where no agent writes (FIX-02-06-11), shows pass for every gate; else what is
    missing. A status on GitHub is no evidence: anyone who may push can set one."""
    entry = base._read(base._gates(root) / head) if base.SHA.fullmatch(head) else {}
    if binding is not None and entry.get("binding") != binding:
        return "no own gate evidence bound to this item, head, base and tree"
    missing = [g for g in gates if entry.get(g) != "pass"]
    return f"no own evidence at {head[:12]}: {', '.join(missing)} did not pass here on it" if missing else ""


def approval_proof(repo: str, n: int, approval: dict, run=state.gh, *, removal=None) -> str:
    """Authenticate an unedited same-item GitHub comment, including its exact operation and binding."""
    proof = approval.get("proof") or {}
    comment_id, operation = proof.get("comment"), proof.get("operation")
    if type(comment_id) is not int or comment_id < 1 or not isinstance(operation, str):
        return "integration approval has no authenticated operation reference"
    comment = json.loads(run(["api", f"repos/{repo}/issues/comments/{comment_id}"]))
    if not isinstance(comment, dict):
        return "integration approval comment is unavailable"
    login = (comment.get("user") or comment.get("author") or {}).get("login")
    who = {**comment, "author": {"login": login},
           "authorAssociation": comment.get("author_association", comment.get("authorAssociation"))}
    if (comment.get("id") != comment_id or not login or proof.get("author", login) != login
            or urlsplit(comment.get("issue_url", "")).path != f"/repos/{repo}/issues/{n}"
            or not comment.get("created_at") or comment.get("created_at") != comment.get("updated_at")
            or comment.get("lastEditedAt") or state.writer(who, repo, run, {}) is not True
            or not state.can_push(repo, login, run)):
        return "integration approval is edited, belongs elsewhere, or lacks a writer's authority"
    prefix = "pulse removal approval " if removal else "pulse integration approval "
    body = comment.get("body", "")
    try:
        said = json.loads(body[len(prefix):]) if body.startswith(prefix) else None
    except (ValueError, TypeError):
        said = None
    wanted = {"operation": operation, "item": n, "head": approval.get("head"), "base": approval.get("base")}
    if removal:
        wanted["removal"] = removal
    return "" if said == wanted else "integration approval does not bind this result and base"


def _fetch_branch(root, branch):
    from pulse import ready
    got = ready.net_git(root, "fetch", "--no-write-fetch-head", "--no-tags", "origin", f"refs/heads/{branch}")
    if got.returncode:
        raise state.StateError(got.stderr.strip() or "origin did not answer")


def _transition(n, kind, current, **payload):
    return {"id": uuid.uuid4().hex, "item": n, "kind": kind,
            "expected": current["revision"], "payload": payload}


def _contained(root, commit, branch):
    from pulse import shared
    tip = shared.remote_head(root, branch)
    if not tip:
        return False
    _fetch_branch(root, branch)
    return _git(root, "--no-replace-objects", "merge-base", "--is-ancestor", commit, tip).returncode == 0


def _abort_integration(root, n, holder, branch, merge_sha, attempted):
    """Release only after a failed attempt is proven unpublished; uncertainty keeps the reservation."""
    from pulse import shared
    if attempted and (not merge_sha or _contained(root, merge_sha, branch)):
        return
    _, snapshot = shared.read(root)
    reservation = snapshot["integration"]
    if reservation and reservation["item"] == n and reservation["holder"] == holder:
        current = snapshot["items"][str(n)]
        shared.update(root, _transition(n, "integration_aborted", current, holder=holder))


def _close_integrated(root, repo, n, current, branch, run):
    result, merged = current.get("result"), current.get("merge")
    try:
        binding = _merged(root, merged, branch)
    except state.StateError as error:
        return {"status": "conflict", "why": str(error)}
    if not result or any(binding[key] != result[key] for key in ("base", "head")):
        return {"status": "conflict", "why": "recorded merge does not contain the approved result and base"}
    if current.get("removal"):
        return {"status": "done", "why": "removal integrated; original issue retained", "merge": merged}
    raw = json.loads(run(["issue", "view", str(n), "--repo", repo, "--json", "state,parent"]))
    parent = (raw.get("parent") or {}).get("number")
    if parent:
        from pulse import actions
        items = state.load(root, repo, run=run, fresh=True)
        container = next((item for item in items if item["number"] == parent), None)
        if container and container.get("type") == "epic" and not any(
                container.get(key) for key in ("draft", "hold", "failed", "claimed_holder", "assignees", "result", "removal")) and \
                not any(item["number"] != n and item.get("parent") == parent for item in items) and \
                not actions.integration_held(root, parent):
            # Keep the integrated child open until parent closure succeeds, so retry needs no extra state.
            run(["issue", "close", str(parent), "--repo", repo])
    if raw.get("state") != "CLOSED":
        run(["issue", "close", str(n), "--repo", repo])
    state.drop_cache(root)
    return {"status": "done", "why": "integrated and closed", "merge": merged}


def _merged(root, merged, branch):
    """The exact result and base of a published merge, independent of its subject."""
    if not isinstance(merged, str) or not base.SHA.fullmatch(merged) or not _contained(root, merged, branch):
        raise state.StateError("merge is not confirmed on the remote base; publish the project merge first")
    if _git(root, "--no-replace-objects", "cat-file", "-t", merged).stdout.strip() != "commit":
        raise state.StateError("completion needs the merge commit SHA itself, not a tag object")
    parents = _git(root, "--no-replace-objects", "rev-list", "--parents", "-1", merged).stdout.split()[1:]
    if len(parents) != 2:
        raise state.StateError("completion needs one ordinary two-parent project merge")
    before, head = parents
    tree = _git(root, "--no-replace-objects", "rev-parse", head + "^{tree}").stdout.strip()
    if (_git(root, "--no-replace-objects", "merge-base", "--is-ancestor", before, head).returncode
            or tree != _git(root, "--no-replace-objects", "rev-parse", merged + "^{tree}").stdout.strip()):
        raise state.StateError("merge changes the checked result or reverses its parents; verify the actual integrated contents")
    return {"head": head, "base": before, "tree": tree}


def completion(root, repo, n, merged, run):
    """Observe one explicit completion. This does not claim, approve, run gates or write state."""
    from pulse import actions, ready, shared, spec
    branch = config.clone_config(root).get("base_branch") or config.default_branch(root)
    binding = _merged(root, merged, branch)
    _, snapshot = shared.read(root)
    current = snapshot["items"].get(str(n), shared._empty())
    item = state.item(repo, n, run=run)
    if current["done"]:
        if current["merge"] != merged or any(current["result"][k] != binding[k] for k in ("head", "base")):
            raise state.StateError("item already has a different confirmed completion")
        own = current["result"]["branch"]
    else:
        if (current["claim"] or not current["revision"] and (item.get("claimed_by") or item.get("assignees"))):
            raise state.StateError(f"#{n} is still claimed; its writer must release it, or a person can use pulse handoff {n}")
        if (current["hold"] or current.get("failed") or current.get("revoked") or current.get("removal")
                or (current.get("stop") or {}).get("status") == "requested" or snapshot["integration"]
                or actions.integration_held(root, n)
                or not current["revision"] and any(item.get(k) for k in ("hold", "failed"))):
            raise state.StateError(f"#{n} has an active hold, stop, revocation or integration; inspect pulse status {n} first")
        refs = ready.net_git(root, "ls-remote", "--heads", "origin")
        if refs.returncode:
            raise state.StateError(ready.git_error(refs.stderr) or "origin did not answer")
        candidates = [ref.removeprefix("refs/heads/") for row in refs.stdout.splitlines()
                      for sha, ref in [row.split()] if sha == binding["head"] and state.item_of(ref.removeprefix("refs/heads/")) == n]
        known = (current.get("result") or current.get("work") or {}).get("branch")
        own = known if known in candidates else candidates[0] if len(candidates) == 1 else ""
        text = ready._git(root, "show", f"{binding['head']}:{item.get('spec')}") if item.get("spec") else ""
        if not own or str(spec.front(text).get("issue", "")).lstrip("#") != str(n):
            raise state.StateError(f"merge result is not the uniquely published branch and registered spec of #{n}")
    return current, item, {**binding, "branch": own, "merge": merged, "gates": dict.fromkeys(("tests", "review", "audit"), "pass")}


def complete(root, repo, operation, run):
    """Authenticated transport for the existing outbox. Retry closure after a confirmed shared write."""
    from pulse import shared
    n, payload = operation["item"], operation["payload"]
    current, _, observed = completion(root, repo, n, payload.get("merge"), run)
    if observed != {k: v for k, v in payload.items() if k != "proof"}:
        raise state.StateError("completion binding changed; inspect the published result again")
    binding = {"item": n, **{k: observed[k] for k in ("head", "base", "tree")}}
    why = "" if current["done"] else evidence(root, observed["head"], observed["gates"], binding=binding)
    if why:
        raise state.StateError(why + f"; run pulse done {n} --merge {observed['merge']} --verify")
    receipt = shared.update(root, operation)
    if receipt["status"] == "confirmed":
        branch = config.clone_config(root).get("base_branch") or config.default_branch(root)
        outcome = _close_integrated(root, repo, n, receipt["data"], branch, run)
        if outcome["status"] != "done":
            raise state.StateError(outcome["why"])
    return receipt


def integrate(root: Path, repo: str, n: int, holder: str, run=state.gh) -> dict:
    """Integrate one approved result through normal hooks and an atomic state/base fast-forward push."""
    from pulse import actions, shared
    root = Path(root)
    branch = config.clone_config(root).get("base_branch") or config.default_branch(root)
    reserved, attempted, merge_sha, scratch = False, False, "", None
    try:
        _, snapshot = shared.read(root)
        current = snapshot["items"].get(str(n), {})
        removal = current.get("removal")
        if removal:
            branch = removal["inventory"]["base"]
        if current.get("done"):
            return _close_integrated(root, repo, n, current, branch, run)
        result, approval, claim = (current.get(key) for key in ("result", "approval", "claim"))
        if not result or not approval or current.get("hold"):
            return {"status": "waiting", "why": "integration waits for a confirmed result approval"}
        if not claim or claim["holder"] != holder:
            return {"status": "conflict", "why": "integration requires the current claim holder"}
        if any(approval[key] != result[key] for key in ("head", "base")):
            return {"status": "conflict", "why": "result approval is stale"}
        def proof():
            if actions.integration_held(root, n):
                return "local defer or revocation blocks integration while synchronization is pending"
            if approval.get("policy"):
                from pulse import auto
                if removal:
                    return "removal always requires a separate personal approval"
                latest = shared.read(root)[1]
                return (shared.policy_reason(latest, current) or auto.authority(root, repo, shared.policy(latest), run)
                        or evidence(root, result["head"], ("tests", "review", "audit")))
            if removal:
                from pulse import remove
                remove.integration_proof(root, repo, n, current, run)
                return ""
            return approval_proof(repo, n, approval, run) or evidence(root, result["head"], ("tests", "review", "audit"))

        why = proof()
        if why:
            return {"status": "waiting", "why": why}
        if (shared.remote_head(root, branch) != result["base"]
                or shared.remote_head(root, result["branch"]) != result["head"]):
            return {"status": "conflict", "why": "published result or base changed"}
        _fetch_branch(root, branch)
        _fetch_branch(root, result["branch"])
        if _git(root, "merge-base", "--is-ancestor", result["base"], result["head"]).returncode:
            return {"status": "conflict", "why": "verified result does not contain its base"}
        reservation = snapshot["integration"]
        wanted = {"item": n, "holder": holder, "head": result["head"], "base": result["base"]}
        if reservation and reservation != wanted:
            return {"status": "waiting", "why": "another integration holds the reservation"}
        if not reservation:
            receipt = shared.update(root, _transition(n, "integrating", current, holder=holder,
                                                     head=result["head"], base=result["base"]))
            if receipt["status"] != "confirmed":
                return {"status": "conflict", "why": receipt["reason"]}
            current = receipt["data"]
        reserved = True
        folder = config.pulse_dir(root)
        folder.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix="integration-", dir=str(folder))) / "work"
        added = _git(root, "worktree", "add", "--detach", str(scratch), result["base"])
        if added.returncode:
            raise state.StateError(added.stderr.strip())
        merged = _git(scratch, "merge", "--no-ff", "--no-edit", "-m", f"Merge item #{n}", result["head"])
        if merged.returncode:
            raise state.StateError(merged.stderr.strip() or merged.stdout.strip() or "merge hook rejected integration")
        merge_sha = _git(scratch, "rev-parse", "HEAD").stdout.strip()
        why = proof()
        if why:
            raise state.StateError(why)
        if shared.remote_head(root, result["branch"]) != result["head"]:
            raise state.StateError("published result changed while merging")
        operation = _transition(n, "integrated", current, holder=holder, merge=merge_sha)
        attempted = True
        receipt = shared.publish(scratch, operation, branch, merge_sha, result["base"])
        if receipt["status"] != "confirmed":
            _abort_integration(root, n, holder, branch, merge_sha, attempted)
            reserved = False
            return {"status": "conflict", "why": receipt["reason"]}
        reserved = False
        return _close_integrated(root, repo, n, receipt["data"], branch, run)
    except (state.StateError, OSError, ValueError, TypeError) as exc:
        if reserved:
            try:
                _abort_integration(root, n, holder, branch, merge_sha, attempted)
            except (state.StateError, OSError, ValueError):
                pass
        return {"status": "error", "why": str(exc) or type(exc).__name__}
    finally:
        if scratch is not None:
            base.drop(root, scratch)
            try:
                scratch.parent.rmdir()
            except OSError:
                pass
