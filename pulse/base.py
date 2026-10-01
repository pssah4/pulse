"""Project commands and base evidence for pulse go (IMP-03-08, #149, #151).

The current SHA's project CI takes precedence over saved pulse/base statuses. Without CI, an existing
verdict or a locally verified equal tree counts; without either, work can start and the result's tests
gate supplies the verification before integration. Proven Dependabot maintenance and matching records of
old local startup failures cannot block that work. Assessing the base runs no setup or local tests.
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


def _updaters(checks: list, repo: str, sha: str, gh_run) -> set:
    """Suites proven to be GitHub's automatic Dependabot update search (#151).
    Names alone never exempt a check. Missing metadata leaves it gating; API faults propagate."""
    candidates = {(c.get("check_suite") or {}).get("id") for c in checks
                  if c.get("name") == "Dependabot" and (c.get("app") or {}).get("slug") == "github-actions"}
    candidates = {n for n in candidates if type(n) is int and n > 0}
    if not candidates:
        return set()
    runs = json.loads(gh_run(["api", f"repos/{repo}/actions/runs?event=dynamic&head_sha={sha}&per_page=100"]) or "{}")
    return {r.get("check_suite_id") for r in runs.get("workflow_runs") or []
            if r.get("path") == "dynamic/dependabot/dependabot-updates" and r.get("event") == "dynamic"
            and (r.get("actor") or {}).get("login") == "dependabot[bot]" and r.get("head_sha") == sha
            and type(r.get("check_suite_id")) is int and r.get("check_suite_id") in candidates}


def _ci(combined: dict, repo: str, sha: str, gh_run) -> tuple:
    """Project CI verdict, first blocking check and proven maintenance suites. pulse/* never counts."""
    runs = json.loads(gh_run(["api", f"repos/{repo}/commits/{sha}/check-runs?per_page=100"]) or "{}")
    statuses, checks = combined.get("statuses") or [], runs.get("check_runs") or []
    updaters = _updaters(checks, repo, sha, gh_run)
    seen = [(s, (s.get("state") or "").upper()) for s in statuses] + \
        [(c, (c.get("conclusion") or "").upper() if c.get("status") == "completed" else "PENDING") for c in checks
         if not (c.get("name") == "Dependabot" and (c.get("app") or {}).get("slug") == "github-actions"
                 and (c.get("check_suite") or {}).get("id") in updaters)]
    seen = [(c, st) for c, st in seen if not (c.get("context") or c.get("name") or "").startswith("pulse/")]
    for outcome, matches in (("fail", state.FAILED), ("pending", {"PENDING", ""})):
        found = next((c for c, st in seen if st in matches), None)
        if found is not None:
            return outcome, found, updaters
    if runs.get("total_count", len(checks)) > len(checks) or combined.get("total_count", len(statuses)) > len(statuses):
        raise ValueError("incomplete CI response")
    return ("pass" if seen else "absent"), {}, updaters


def _label(value: object, fallback: str = "project CI") -> str:
    """Only short check labels, never output bodies, credentials, or terminal controls."""
    if not isinstance(value, str):
        return fallback
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value[:512]).strip()
    return value if re.fullmatch(r"[A-Za-z0-9#][A-Za-z0-9 _./():+\-]{0,79}", value) else fallback


def _check_url(check: dict, repo: str, sha: str) -> str:
    home = f"https://github.com/{repo}"
    url = check.get("html_url") or check.get("target_url") or ""
    route = r"(?:actions/runs/\d+(?:/(?:job|attempts)/\d+)?|runs/\d+)(?:\?check_suite_focus=true)?"
    route += r"|commit/[0-9a-f]{40,64}/checks(?:\?check_run_id=\d+)?"
    return url if isinstance(url, str) and len(url) < 512 and re.fullmatch(re.escape(home) + "/(?:" + route + ")", url) \
        else f"{home}/commit/{sha}/checks"


def _diagnostic(check: dict, repo: str, sha: str, cached: bool = False) -> dict:
    """Derive an allowlisted action from bounded metadata. Raw summaries, logs and errors never leave here."""
    name = _label(check.get("context") or check.get("name") or check.get("description"))
    detail = {"state": "failure", "check": name, "cached": cached,
              "cause": "saved pulse/base failure still blocks builds" if cached else "check failed; cause unavailable",
              "next": "fix the check and rerun project CI at this commit" if cached else "inspect the failed check",
              "url": _check_url(check, repo, sha)}
    output = check.get("output") or {}
    if "dependabot" in name.lower() and isinstance(output, dict):
        text = " ".join(s[:4096] for key in ("title", "summary", "text") if isinstance(s := output.get(key), str))
        patterns = [r"\b[Ss]ecret\s+[`'\"]?([A-Z_][A-Z0-9_]{0,63})[`'\"]?\s+(?:(?:was|is)\s+)?"
                    r"(?:not found|missing|not available|not set|could not be found)\b",
                    r"\b[Mm]issing\s+secret\s+[`'\"]?([A-Z_][A-Z0-9_]{0,63})\b"]
        secret = next((m.group(1) for pattern in patterns if (m := re.search(pattern, text))), "")
        if secret:
            detail.update(cause=f"missing secret {secret}",
                          next=f"add {secret} in Settings > Secrets and variables > Dependabot",
                          url=f"https://github.com/{repo}/settings/secrets/dependabot")
    return detail


def check(root: Path, cfg: dict, sha: str, repo: str, gh_run, unit: float = 60, detail: dict | None = None) -> tuple:
    """(ok, why, final) from existing evidence only. Pending or unreadable CI is unknown and provisional.
    An optional detail dict receives safe fields for the runner report. cfg and unit remain API-compatible;
    setup and verification run in item worktrees, after this assessment."""
    if detail is None:
        detail = {}
    detail.clear()
    try:
        combined = json.loads(gh_run(["api", f"repos/{repo}/commits/{sha}/status"]) or "{}")
        own = next((s for s in combined.get("statuses") or [] if s.get("context") == CONTEXT), None)
        ci, failed, updaters = _ci(combined, repo, sha, gh_run)
    except (state.StateError, ValueError, AttributeError, TypeError):
        why = f"GitHub gave no complete CI state for {sha[:7]}"
        detail.update(state="unknown", cause=why, next="inspect project CI and retry the base assessment",
                      url=_check_url({}, repo, sha))
        return None, why, False
    if ci == "fail":
        detail.update(_diagnostic(failed, repo, sha))
        if own and own.get("state") == "failure" and own.get("description") == detail["check"]:
            return False, detail["check"], True
        return (*_mark(root, repo, sha, False, detail["check"], gh_run), True)
    if ci == "pending":
        why = f"the CI at {sha[:7]} still runs"
        detail.update(state="pending", check=_label(failed.get("context") or failed.get("name")),
                      cause=why, next="wait for project CI before building", url=_check_url(failed, repo, sha))
        return None, why, False
    ran = _noted(root).get("ran")
    negative = own and own.get("state") in ("failure", "error")
    local_failure = negative and ran and ran[0] == sha and ran[1] and own.get("description") == ran[1][:140]
    maintenance = negative and own.get("description") == "Dependabot" and updaters
    recheck = local_failure or maintenance
    if recheck:
        detail["rechecked"] = "saved local startup failure" if local_failure else "saved Dependabot maintenance failure"
    if ci == "pass":
        why = "project CI passed"
    elif own and own.get("state") in ("success", "failure", "error") and not recheck:
        if own["state"] != "success":
            detail.update(_diagnostic({"name": own.get("description")}, repo, sha, cached=True))
            return False, detail["check"], True
        why = _label(own.get("description"), "saved pulse/base success")
        detail.update(state="success", cause=why, cached=True)
        return True, why, True
    else:
        by = "" if recheck else _green(root, _git(root, "rev-parse", f"{sha}^{{tree}}").stdout.strip())
        if not by:
            why = "no project CI; verify the built result before integration"
            detail.update(state="absent", cause=why, next="build, then verify the result before integration")
            return True, why, True
        why = f"same tree as {_label(by, 'a verified head')}"
    detail.update(state="success", cause=why)
    if own and own.get("state") == "success" and own.get("description") == why:
        return True, why, True
    return (*_mark(root, repo, sha, True, why, gh_run), True)
