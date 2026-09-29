"""What pulse go runs of the project itself, outside every agent sandbox: setup in each worktree, and the
base check (IMP-03-08).

The base check says whether the base branch is green at a commit, once per base SHA and clone; the commit
status pulse/base shares the answer with every other clone. In this order: a pulse/base status on the SHA
counts. A tree that equals the tree of a head whose tests gate passed here is green without a run ("same
tree as #n head"; after a merge of pulse go that is the rule). Else the project's CI at the SHA (its
statuses and check runs, never pulse/*) and a run of setup and verify in a scratch worktree on the SHA
decide: red as soon as one is red, green when both are, and a SHA without CI counts as green. While the CI
still runs and setup and verify passed, the last known state of the base holds, as a provisional answer go
asks again; pulse/base goes on the SHA with the final result only. A fault of the tools here (git cannot make
the scratch worktree) leaves the state unknown and publishes nothing.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path

from pulse import config, state

CONTEXT = "pulse/base"
SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")          # a commit's full name, sha1 or sha256
LOCK = Path.home() / ".cache" / "pulse" / "spec-tests.lock"
# sys.argv = [lock, cmd]: cmd under an exclusive lock on the file, with CI=1; the lock goes with the process
LOCKED = ("import fcntl, os, subprocess, sys\nlock = open(sys.argv[1], 'a')\nfcntl.flock(lock, fcntl.LOCK_EX)\n"
          "sys.exit(subprocess.call(['sh', '-c', sys.argv[2]], env={**os.environ, 'CI': '1'}))\n")


def run(cmd: str, cwd: Path, seconds: float, log: Path) -> str:
    """cmd in cwd, its output at the end of log, ended with everything it started after `seconds`: "" when it
    passed, else what went wrong."""
    with open(log, "a", encoding="utf-8") as out:
        out.write(f"--- {cmd} in {cwd} ---\n")
        out.flush()
        p = subprocess.Popen(["sh", "-c", cmd], cwd=cwd, stdin=subprocess.DEVNULL, stdout=out,
                             stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = p.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            rc = None
        finally:               # what it started ends with it: at its end, its time limit, a Ctrl-C or SIGTERM
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            p.wait()
    if rc is None:
        return f"`{cmd}` did not end within {seconds / 60:g} min"
    return f"`{cmd}` failed with exit {rc}" if rc else ""


def locked(cmd: str) -> str:
    """cmd as a shell command that runs under the machine's spec-test lock (LOCK) with CI=1: runners of parallel
    items and clones never share a port, and Playwright starts its own server or fails loudly (IMP-03-13 FR-04)."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    return " ".join(shlex.quote(a) for a in (sys.executable, "-c", LOCKED, str(LOCK), cmd))


def drop(root: Path, path: Path) -> None:
    """A scratch worktree of pulse go goes, and only one git lists at exactly this path, where no link leads,
    neither the path nor a directory above it (M-2, M-D): a directory by rmtree, which follows no link, a file
    as itself; then git forgets it. Else nothing goes: git worktree remove or rmtree through a link would
    delete what it points at. path comes from config.pulse_dir, which is resolved."""
    if os.path.realpath(path) != str(path):
        return
    listed = str(path) in re.findall(r"^worktree (.+)$", _git(root, "worktree", "list", "--porcelain").stdout, re.M)
    if path.is_file():
        path.unlink()
    elif path.is_dir() and listed:
        shutil.rmtree(path, ignore_errors=True)
    if listed and not os.path.lexists(path):
        _git(root, "worktree", "remove", "-f", "-f", str(path))


def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _gates(root: Path) -> Path:
    return config.evidence_dir(root) / "gates"


def vouch(root: Path, sha: str, gate: str, result: str, by: str) -> None:
    """A gate of pulse go ended at commit sha here: its result goes into gates/<sha> of config.evidence_dir (IMP-03-13
    FR-05), outside the git dir a Codex phase writes (FIX-02-06-11), where the commit status is open to anyone with
    write access to the repository. Written through no link: a new file that takes the entry's place (L-2). A base
    on the tree of a commit whose tests gate passed here is green without a run."""
    folder = _gates(root)
    folder.mkdir(parents=True, exist_ok=True)
    if not SHA.fullmatch(sha) or folder.is_symlink():
        return
    path, new = folder / sha, folder / f".{sha}.{os.getpid()}"
    try:
        fd = os.open(new, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(json.dumps({**_read(path), "by": by, gate: result}))
        os.replace(new, path)
    except OSError:
        new.unlink(missing_ok=True)


def _read(path: Path) -> dict:
    """An entry of the gates' evidence; a link, a directory, or anything but a regular file is none (L-2)."""
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return {}
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return entry if isinstance(entry, dict) else {}


def _green(root: Path, tree: str) -> str:
    """Who vouched for this tree: an entry named for a commit whose tests gate passed here and whose tree, as git
    has it, is this one; "" without one. The entry's own words about its tree count for nothing (M-3)."""
    # ponytail: one git call per passed entry and base SHA; an index by tree when a clone keeps thousands
    folder = _gates(root)
    for path in ([] if folder.is_symlink() or not tree else folder.glob("*")):
        entry = _read(path) if SHA.fullmatch(path.name) else {}
        if entry.get("tests") == "pass" and \
                _git(root, "rev-parse", "-q", "--verify", f"{path.name}^{{tree}}").stdout.strip() == tree:
            return str(entry.get("by") or path.name[:12])
    return ""


def _noted(root: Path) -> dict:
    """What the last checks noted in this clone: the SHA setup and verify last ran on and how ("ran": [sha,
    why]), and the last final state of the base ("known": [ok, why]). An entry of another shape is none (L-3)."""
    try:
        note = json.loads((config.evidence_dir(root) / "base.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    note = note if isinstance(note, dict) else {}
    kinds = {"ran": str, "known": bool}
    return {k: v for k, v in note.items() if k in kinds and isinstance(v, list) and len(v) == 2
            and isinstance(v[0], kinds[k]) and isinstance(v[1], str)}


def _note(root: Path, **values) -> None:
    path = config.evidence_dir(root) / "base.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**_noted(root), **values}), encoding="utf-8")


def _mark(root: Path, repo: str, sha: str, ok: bool, why: str, gh_run) -> tuple:
    """The final state of the base at sha, as pulse/base on the SHA for every clone and as the known state here."""
    try:
        gh_run(["api", f"repos/{repo}/statuses/{sha}", "-f", f"state={'success' if ok else 'failure'}",
                "-f", f"context={CONTEXT}", "-f", f"description={why[:140]}"])
    except state.StateError:
        pass                   # another clone checks again; this one knows
    _note(root, known=[ok, why])
    return ok, why


def _ci(combined: dict, repo: str, sha: str, gh_run) -> tuple:
    """("fail", the check), ("pending", ""), or ("pass", "") for the project's CI at sha: its statuses and check
    runs, never pulse/*; no CI at all passes."""
    runs = json.loads(gh_run(["api", f"repos/{repo}/commits/{sha}/check-runs?per_page=100"]) or "{}")
    seen = [(s.get("context") or "", (s.get("state") or "").upper()) for s in combined.get("statuses") or []] + \
        [(c.get("name") or "", (c.get("conclusion") or "").upper() if c.get("status") == "completed" else "PENDING")
         for c in runs.get("check_runs") or []]
    seen = [(name, st) for name, st in seen if not name.startswith("pulse/")]
    red = [name for name, st in seen if st in state.FAILED]
    return ("fail", red[0]) if red else ("pending" if any(st == "PENDING" for _, st in seen) else "pass", "")


def _scratch(root: Path, cfg: dict, sha: str, unit: float) -> tuple:
    """setup and verify in a scratch worktree on sha, once per SHA and clone: ("", False) when both passed,
    (why, False) when one failed, (why, True) when git here could not make the worktree, which says nothing
    about the base (N2)."""
    noted = _noted(root).get("ran")
    if noted and noted[0] == sha:
        return noted[1], False
    scratch, log = config.pulse_dir(root) / "base", config.pulse_dir(root) / "go" / "base.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    drop(root, scratch)                # one a stopped run left
    add = _git(root, "worktree", "add", "--detach", str(scratch), sha)
    if add.returncode:
        return f"no scratch worktree on {sha[:7]}: {add.stderr.strip()}", True
    try:
        why = (cfg["setup"] and run(cfg["setup"], scratch, cfg["setup_timeout"] * unit, log)) or \
            run(cfg["verify"], scratch, cfg["agent_timeout"] * unit, log)
    finally:
        drop(root, scratch)
    _note(root, ran=[sha, why])
    return why, False


def check(root: Path, cfg: dict, sha: str, repo: str, gh_run, unit: float = 60) -> tuple:
    """(ok, why, final) for the base at sha: ok True when green, False when red, None while nothing is known
    (its CI runs and no state is known here, GitHub does not answer, git here fails). Not final while the CI
    runs: go asks again each round (B5). unit: seconds per minute of setup_timeout and agent_timeout."""
    try:
        combined = json.loads(gh_run(["api", f"repos/{repo}/commits/{sha}/status"]) or "{}")
        own = next((s for s in combined.get("statuses") or [] if s.get("context") == CONTEXT), None)
        if own and own.get("state") in ("success", "failure", "error"):
            return own["state"] == "success", own.get("description") or "", True
        tree = _git(root, "rev-parse", f"{sha}^{{tree}}").stdout.strip()
        by = _green(root, tree)
        if by:
            return (*_mark(root, repo, sha, True, f"same tree as {by}", gh_run), True)
        ci, name = _ci(combined, repo, sha, gh_run)
    except (state.StateError, ValueError, AttributeError) as e:
        return None, f"GitHub gave no CI state for {sha[:7]}: {e}", False
    if ci == "fail":
        return (*_mark(root, repo, sha, False, name, gh_run), True)
    why, local = _scratch(root, cfg, sha, unit)
    if local:
        return None, why, False
    if why:
        return (*_mark(root, repo, sha, False, why, gh_run), True)
    if ci == "pending":        # the last known state holds meanwhile, so no foreign merge stops every start
        known = _noted(root).get("known")
        return (*known, False) if known else (None, f"the CI at {sha[:7]} still runs", False)
    return (*_mark(root, repo, sha, True, "setup and verify passed", gh_run), True)
