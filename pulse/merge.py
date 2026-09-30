"""Gate 3 of pulse go (IMP-03-09): the merge ok of a person that holds for a head, the evidence this clone keeps for a
head, whether GitHub may merge a PR now, the paths a person must see before a merge, and closing an item with its
epic. pulse go merges only with all of them; the merge itself is state.merge, bound to the head it checked."""
from __future__ import annotations

import fnmatch
import json
import re
import shlex
import subprocess
from pathlib import Path

from pulse import base, config, lifecycle, review, state

DEFAULTS = (".pulse/", ".github/", ".husky/")       # what runs or guards the project, whatever the config says
RUNNERS = re.compile(r"(^|/)(Makefile|tox\.ini|noxfile\.py|pytest\.ini|conftest\.py|setup\.cfg|"
                     r"\.pre-commit-config\.yaml|(jest|vitest|playwright)\.config\.[cm]?[jt]s)$")   # test runners


def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def protected(cfg: dict, files: list) -> list:
    """The files of a PR a person must see before it merges (FR-04), in their order: .pulse/, .github/, .husky/,
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


def seen(root: Path, repo: str, pr: int, run, who: str) -> str:
    """The line that names what PR #pr changes that a person must see, for pulse approve and the map before gate 3
    is approved (L-2 of #118)."""
    files = [f.get("path", "") for f in json.loads(run(["pr", "view", str(pr), "--repo", repo, "--json", "files"]))
             .get("files") or []]
    hit = protected(config.load(root), files)
    return f"{who} changes {', '.join(hit)}, which a person must see" if hit else \
        f"{who} changes no protected path, manifest, or lockfile"


def covers(root: Path, said: str, head: str, base_ref: str) -> bool:
    """Whether a merge ok at `said` holds for head (FR-02): the same commit, or head adds to it on its first-parent
    line nothing but merges of the base as git makes them: each second parent on base_ref, each tree the one
    `git merge-tree` writes for the two parents, so no line of a conflict resolution rides along."""
    if said == head:
        return True
    walk = _git(root, "rev-list", "--first-parent", "--parents", f"{said}..{head}")
    if walk.returncode:
        return False
    expect = head
    for row in filter(None, walk.stdout.split("\n")):
        c, *parents = row.split()
        if c != expect or len(parents) != 2 or \
                _git(root, "merge-base", "--is-ancestor", parents[1], base_ref).returncode:
            return False
        tree = _git(root, "merge-tree", "--write-tree", *parents)
        if tree.returncode or tree.stdout.split()[:1] != [_git(root, "rev-parse", f"{c}^{{tree}}").stdout.strip()]:
            return False
        expect = parents[0]
    return expect == said


def approved(root: Path, item: dict, head: str, base_ref: str, repo: str, run, known: dict) -> str:
    """The login of someone who may push whose `merge ok at <sha>` on the item holds for head (covers); "" when
    nobody's does. known: the answers about logins, as state.writer keeps them."""
    if item.get("hold"):
        return ""
    for ok in item.get("merge_oks") or ():
        if covers(root, ok["sha"], head, base_ref) and state.writer(ok, repo, run, known) is True:
            return (ok.get("author") or {}).get("login") or "?"
    return ""


def evidence(root: Path, head: str, gates) -> str:
    """"" when this clone's pulse go vouches for head (FR-03): gates/<head> in config.evidence_dir, written for
    exactly that commit (#117) where no agent writes (FIX-02-06-11), shows pass for every gate; else what is
    missing. A status on GitHub is no evidence: anyone who may push can set one."""
    entry = base._read(base._gates(root) / head) if base.SHA.fullmatch(head) else {}
    missing = [g for g in gates if entry.get(g) != "pass"]
    return f"no own evidence at {head[:12]}: {', '.join(missing)} did not pass here on it" if missing else ""


def ready(pr: dict) -> str:
    """"" when GitHub may merge the PR now (FR-03): open, no draft, mergeable, and its whole rollup passed, never an
    empty one; else why not, "waits for GitHub checks" while one still runs."""
    if pr.get("state") != "OPEN" or pr.get("isDraft"):
        return "it is a draft" if pr.get("isDraft") else f"it is {str(pr.get('state')).lower()}"
    if pr.get("mergeable") != "MERGEABLE":
        return f"GitHub cannot merge it ({str(pr.get('mergeable') or 'unknown').lower()})"
    checks = state.checks(pr.get("statusCheckRollup") or [])
    return "" if checks == "pass" else f"waits for GitHub checks ({checks or 'none'})"


def close(root: Path, repo: str, n: int, run) -> list:
    """Close #n once its PR is merged, then its epic when the board, read afresh, has no open item with that parent
    any more (FR-05): GitHub closes an issue only for a PR into the default branch. The numbers it closed."""
    raw = state._view(repo, n, run)
    if lifecycle.blocked(raw, lifecycle.trusted(repo, run)):
        return []
    parent = (raw.get("parent") or {}).get("number")
    if not state.done(root, repo, n, run=run, take=True)[0]:
        return []
    items = state.load(root, repo, run=run, fresh=True)
    if parent and parent in {i["number"] for i in items} and not any(i.get("parent") == parent for i in items):
        if state.done(root, repo, parent, run=run, take=True)[0]:
            return [n, parent]
    return [n]
