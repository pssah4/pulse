"""Project command execution and protected exact-commit evidence for pulse go.

The runner owns verification of completed results. GitHub CI does not schedule
work or supply integration authority. Commands retain normal project checks.
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


def vouch(root: Path, sha: str, gate: str, result: str | dict, by: str) -> None:
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


def check(root: Path, cfg: dict, sha: str, repo: str, gh_run, unit: float = 60, detail: dict | None = None) -> tuple:
    """Starting work needs a fetched base, not GitHub CI; Pulse verifies the completed result."""
    why = "verify the completed result before integration"
    if detail is not None:
        detail.clear()
        detail.update(state="ready", cause=why, next="plan and build ready work")
    return True, why, True
