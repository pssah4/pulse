"""Prove that the project's real commit gates accept a valid Plan with future files."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path

from pulse import base, config, ready


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, timeout=10).stdout.strip()


def _hooks(root):
    query = subprocess.run(["git", "-C", str(root), "config", "--get", "core.hooksPath"],
                           capture_output=True, text=True, timeout=10)
    relative = query.stdout.strip()
    if relative and (Path(relative).is_absolute() or ".." in Path(relative).parts):
        raise ValueError("external hook configuration cannot be isolated")
    path = root / relative if relative else config.common_dir(root) / "hooks"
    if path.resolve() != path.absolute():
        raise ValueError("a hook path contains a symlink")
    files = {}
    for p in sorted(path.rglob("*")):
        mode = p.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("a hook is not a regular file")
        files[str(p.relative_to(path))] = (p.read_bytes(), stat.S_IMODE(mode))
    return relative or ".git/hooks", files


def _plan(work, cfg):
    tag = "pulse_plan_probe_" + uuid.uuid4().hex[:12]
    candidates = [f"tests/test_{tag}.py"] + [re.sub(r"\*\*/", tag + "/", p).replace("*", tag).replace("?", "p")
                                           for p in (cfg.get("spec_tests") or {})]
    test = next((p for p in candidates if not Path(p).is_absolute() and ".." not in Path(p).parts
                 and ready.TESTISH.search(p) and config.spec_runner(cfg, p) and not (work / p).exists()), None)
    if not test or not cfg.get("verify"):
        raise ValueError("a verify command and a spec-test runner for a future test file are required")
    files = [f"src/{tag}.py", test]
    spec = "_devprocess/requirements/improvements/IMP-99-99-" + tag + ".md"
    plan = "_devprocess/plans/2147483647-" + tag + ".md"
    requirement = ("---\ntitle: Plan commit compatibility\nissue: 2147483647\npriority: P2\neffort: S\n---\n"
                   "## Requirements\n\n- FR-01: WHEN a Plan names future files THE SYSTEM SHALL accept its commit.\n"
                   "\n## Success criteria\n\n| ID | Criterion | Target | Measurement |\n|---|---|---|---|\n"
                   "| SC-01 | Future files are permitted | Successful commit | Project commit gates |\n")
    text = (f"---\ntitle: Plan commit compatibility\nissue: 2147483647\nspec: {spec}\nfiles:\n"
            + "".join(f"  - {p}\n" for p in files) + f"verify:\n  - {json.dumps(cfg['verify'])}\n---\n"
            "\n# Plan: commit compatibility\n\n## Tasks\n\n| # | Task | Covers | Files | Wave | Check |\n"
            "|---|---|---|---|---|---|\n"
            f"| 1 | Test future paths | FR-01 | `{test}` | 1 | Run the configured spec tests |\n"
            f"| 2 | Implement future behavior | SC-01 | `{files[0]}` | 2 | Run project verification |\n")
    findings = ready.plan_findings(text, requirement, cfg.get("spec_tests") or {})
    if findings or any((work / p).exists() for p in files):
        raise ValueError("; ".join(findings) or "future probe files already exist")
    for name, body in ((spec, requirement), (plan, text)):
        target = work / name
        if target.resolve() != target.absolute():
            raise ValueError("probe document path contains a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return spec, plan


def probe(root: Path, cfg: dict, sha: str, force=False, timeout=120) -> dict:
    """cfg and sha come from the fetched trusted base. No verify suite, push, claim or approval runs here."""
    root, work, log = Path(root).resolve(), None, None
    result = dict(state="unchecked", step="prerequisites", sha=sha, fingerprint="", why="", log="",
                  next="Fix the reported prerequisite, then run pulse setup --check-plan", cleanup="")
    try:
        folder = config.evidence_dir(root) / "compatibility"
        if folder.resolve() != folder.absolute() or any(p == folder or p in folder.parents
                                                       for p in (root, config.common_dir(root))):
            raise ValueError("probe evidence must be outside the worktree, without symlinks")
        folder.mkdir(parents=True, exist_ok=True)
        log = folder / (uuid.uuid4().hex + ".log")
        log.touch(mode=0o600, exist_ok=False)
        result["log"] = str(log)
        if not base.SHA.fullmatch(sha) or any(os.environ.get(k) for k in
                ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                 "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")):
            raise ValueError("a full trusted base SHA and an unredirected Git environment are required")
        if os.environ.get("HUSKY") == "0" or os.environ.get("SKIP"):
            raise ValueError("hook-skipping environment cannot prove compatibility")
        settings = [(key, value if sep else "true") for key, sep, value in
                    (entry.partition("\n") for entry in _git(root, "config", "--list", "-z").split("\0") if entry)]
        if any(k.startswith(("include.", "includeif.")) for k, v in settings):
            raise ValueError("Git includes cannot safely preserve the hook configuration in a private checkout")
        hook_path, hooks = _hooks(root)
        digest = hashlib.sha256(json.dumps([sha, cfg.get("setup"), cfg.get("setup_timeout"),
                    cfg.get("verify"), cfg.get("spec_tests"), settings], sort_keys=True).encode())
        for p, (data, mode) in hooks.items():
            digest.update(p.encode() + str(mode).encode() + data)
        for module in (__file__, ready.__file__, ready.spec.__file__, config.__file__, base.__file__):
            digest.update(Path(module).read_bytes())
        result["fingerprint"] = digest.hexdigest()
        cached = base._read(base._gates(root) / sha).get("plan-commit")
        if not force and isinstance(cached, dict) and cached.get("state") in {"compatible", "incompatible"} and \
                cached.get("fingerprint") == result["fingerprint"] and Path(cached.get("log", "")).is_file():
            log.unlink()
            return cached
        work = Path(tempfile.mkdtemp(prefix="pulse-plan-probe-", dir=folder))
        result["step"] = "checkout"
        why = base.run(shlex.join(["git", "clone", "-q", "--shared", "--no-checkout", "--template=",
                                   str(root), str(work)]), root, timeout, log)
        if why:
            raise ValueError(why)
        (work / ".git/config").write_text("", encoding="utf-8")
        for key, value in settings:
            if key not in ("core.worktree", "extensions.worktreeconfig"):
                _git(work, "config", "--add", key, value)
        _git(work, "config", "core.worktree", str(work))
        # git commit starts no detached maintenance that still writes while the clone goes (#201)
        _git(work, "config", "--replace-all", "maintenance.auto", "false")
        why = base.run(shlex.join(["git", "checkout", "-q", "--detach", sha]), work, timeout, log)
        if why:
            raise ValueError(why)
        target = work / hook_path
        if target.resolve() != target.absolute():
            raise ValueError("private hook path contains a symlink")
        for name, (data, mode) in hooks.items():
            p = target / name
            if p.resolve() != p.absolute():
                raise ValueError("private hook destination contains a symlink")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            p.chmod(mode)
        result["step"] = "setup"
        if cfg.get("setup"):
            why = base.run(cfg["setup"], work, min(timeout, cfg.get("setup_timeout", 20) * 60), log)
            if why:
                raise ValueError(why)
        installed_path, installed = _hooks(work)
        active = any("/" not in n and "." not in n and mode & 0o111 for n, (_, mode) in hooks.items())
        if active and (installed_path != hook_path or any(installed.get(n) != entry for n, entry in hooks.items()
                                                         if not n.endswith(".sample"))):
            raise ValueError("setup changed an inherited hook; compatibility remains unchecked")
        result["step"] = "plan"
        documents = _plan(work, cfg)
        why = base.run(shlex.join(["git", "add", "--", *documents]), work, timeout, log)
        if why:
            raise ValueError(why)
        result["step"] = "commit"
        why = base.run("git commit -m 'docs(plan): #2147483647 compatibility probe' "
                       "-m 'Co-Authored-By: Claude <noreply@anthropic.com>'", work, timeout, log)
        result.update(state="unchecked" if "did not end within" in why else "incompatible" if why else
                      "compatible", why=why or "Project commit gates accepted the valid Plan")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result["why"] = str(error) if not isinstance(error, subprocess.SubprocessError) else \
            "Git preparation failed; the probe could not complete"
    except (KeyboardInterrupt, SystemExit):
        result.update(state="unchecked", why="Probe interrupted")
        raise
    finally:
        if work is not None:
            try:
                shutil.rmtree(work)
            except OSError as error:
                result.update(state="unchecked", step="cleanup", cleanup=str(work),
                              why=f"Probe cleanup failed: {error}; retained at {work}")
        if log is not None and log.exists():
            with log.open("a", encoding="utf-8") as out:
                out.write(json.dumps(result) + "\n")
    if result["fingerprint"]:
        base.vouch(root, sha, "plan-commit", result, "Plan compatibility probe")
    return result
