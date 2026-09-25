"""pulse review: the fresh sessions that check a feature before its PR is ready.

Two of them, one after the other: the review (spec, PLAN, decisions, lean
code; ADR-05) and the security audit of the branch. Whoever built the
feature does neither. This module gathers their inputs, adds what a script
can see, and keeps each verdict in the shared git dir, stamped with the
commit it looked at; a session that changes the branch gets no verdict.
Once the branch has an open PR, the verdict goes there too, as a hidden
marker, so whoever holds the item next finds it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from pulse import config, dispatch, ready, state

SKILLS = Path(__file__).resolve().parents[1] / "skills"
SKILL = SKILLS / "pulse-review" / "SKILL.md"
AUDIT_SKILL = SKILLS / "pulse-audit" / "SKILL.md"
AUDIT_SCAN = SKILLS / "pulse-audit" / "tools" / "audit_scan.py"
REPORT = "REVIEW.md"
REPORTS = {"review": REPORT, "audit": "AUDIT.md"}
KEPT = {"review": "reviews", "audit": "audits"}
VERDICT = re.compile(r"^Verdict:\s*(pass|block)\s*$", re.M | re.I)
SCOPES = ("full", "branch", "commit", "working", "staged", "range")    # the same as /pulse-audit's
SCAN_JSON = "_devprocess/temp/audit-scan.json"    # the scan Pulse runs for the auditor, where it can read it
CONTEXT = "audit-context.json"                    # the last audit that counted, under the shared git dir
MANIFEST = re.compile(r"(^|/)(package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|requirements[^/]*\.txt|pyproject\.toml"
                      r"|poetry\.lock|uv\.lock|Pipfile(\.lock)?|go\.(mod|sum)|Cargo\.(toml|lock))$")
COVERAGE = re.compile(r"^Coverage:(.*)$", re.M | re.I)
MARKER = re.compile(r"<!-- pulse:verdict (\{.*?\}) -->")   # a verdict on the PR, for the next holder
PROMPT = """You review {what} in a fresh session; you did not build it.
Follow {skill}, {mode}. Inputs: {inputs}the changes {changes}, and the decision
records whose "Read When" matches (_devprocess/decisions/README.md).
Found by script: {found}
{tests}
Do not change code, do not commit, do not touch GitHub. Write {report} at the
worktree root: first line `Verdict: pass` or `Verdict: block`, then one line per
finding, `- [block|note] <file>:<line> <check>: <what>`."""
AUDIT_PROMPT = """You audit the security of {what} in a fresh session; you did not build it.
Follow {skill}, section "In the chain": the scope below, no question to anyone,
no live lookup. Pulse ran `audit_scan.py {args}` for you: {scan}.
Since the previous audit: {since}.
Triage the scan's JSON (source to sink, false positives) and read the changed code yourself.
Do not change code, do not commit, do not touch GitHub. Write AUDIT.md at the worktree
root: first line `Verdict: pass` or `Verdict: block` (block while a Critical or High
finding is open), then `Coverage: <what the scan and you checked, and what not>` (a report
without it gives no verdict), with `SCA unavailable` in it when SCA was `offline`, `error`
or `partial` (a pass without that does not count), then one line per finding,
`- [H-1|M-1|L-1] <file>:<line> <CWE>: <what>`."""


def _git(root: Path, *args) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout


def changes(scope: str, base: str, rng: str = None) -> str:
    """How a session reads the changes of a scope."""
    return {"full": "of the whole repository", "branch": f"`git diff {base}...HEAD`",
            "commit": "`git show HEAD`", "staged": "`git diff --cached`", "range": f"`git diff {rng}`",
            "working": "`git diff HEAD` and the untracked files `git status` lists"}[scope]


def files(root: Path, scope: str, base: str, rng: str = None) -> list:
    """The files a scope covers."""
    if scope == "full":
        return _git(root, "ls-files").splitlines()
    if scope == "working":
        return sorted(set(_git(root, "diff", "--name-only", "HEAD").splitlines()) |
                      set(_git(root, "ls-files", "--others", "--exclude-standard").splitlines()))
    if scope == "commit":
        return sorted(_git(root, "show", "--name-only", "--format=", "HEAD").split())
    args = {"branch": [f"{base}...HEAD"], "staged": ["--cached"], "range": [rng]}[scope]
    return _git(root, "diff", "--name-only", *args).splitlines()


def outside_plan(root: Path, n: int, changed: list) -> list:
    """What a script can see: changed files #n's PLAN does not list. A listed directory holds
    what is in it, as in dispatch.ramp."""
    plans = ready.plans(root)
    if n not in plans:
        return [f"no PLAN for #{n}: scope unknown"]
    listed = dispatch.plan_files(root, plans)[n]
    return [f"outside the PLAN: {f}" for f in changed
            if not any(f == l or f.startswith(l + "/") for l in listed)
            and not f.startswith("_devprocess/")]     # spec and PLAN writeback is allowed


def _snapshot(root: Path, kind: str = "review") -> dict:
    """HEAD and the working tree, without the report the session is asked to write and without
    the temporary folder (a session may ignore it through .git/info/exclude while it runs). git
    leaves the folder out itself, so a file moved out of it still shows where it went."""
    status = [l for l in _git(root, "status", "--porcelain", "--", ".", ":(exclude)_devprocess/temp").splitlines()
              if not l.endswith(REPORTS[kind])]
    return {"head": _git(root, "rev-parse", "HEAD").strip(), "status": status}


def _tracked(root: Path, kind: str) -> bool:
    """Whether the branch itself carries the report; then it is nobody's verdict."""
    return bool(_git(root, "ls-files", "--", REPORTS[kind]).strip())


def _present(root: Path, kind: str) -> bool:
    """A report file with exactly this name: macOS and Windows fold case, so a tracked audit.md
    would pass for AUDIT.md, and a directory is no report."""
    return REPORTS[kind] in os.listdir(root) and (root / REPORTS[kind]).is_file()


def _note_before(root: Path, n: int, kind: str) -> None:
    """HEAD and the working tree before a fresh session starts, so record() can tell whether
    it changed anything (it must not, ADR-05). A report left by an earlier session goes, so
    that whatever record() finds was written by this one."""
    if _present(root, kind) and not _tracked(root, kind):
        (root / REPORTS[kind]).unlink()
    before = _kept(root, n, kind).with_suffix(".before")
    before.parent.mkdir(parents=True, exist_ok=True)
    before.write_text(json.dumps(_snapshot(root, kind)), encoding="utf-8")


def _what(n, title: str, scope: str) -> str:
    return f"item #{n}" + (f' "{title}"' if title else "") if n is not None else f"the {scope} scope"


def brief(root: Path, n: int = None, title: str = "", spec=None, base=None, scope: str = "branch",
          rng: str = None, tests: str = None) -> dict:
    """The reviewer's inputs, and what a script already found. With an item number the
    verdict is kept for that item; without one it is only printed. tests: pass or fail when
    Pulse just ran the project's tests at HEAD (the tests gate), so the reviewer need not."""
    if n is not None:
        _note_before(root, n, "review")
    base = base or config.base_ref(root)
    found = outside_plan(root, n, files(root, scope, base, rng)) if n is not None and scope != "full" else []
    plan = (ready.plans(root).get(n) or {}).get("path", "(none)") if n is not None else ""
    inputs = f"the spec {spec or f'(see `pulse show {n}`)'}, the PLAN {plan}, " if n is not None else ""
    head = _git(root, "rev-parse", "--short=12", "HEAD").strip()
    ran = f"tests: {tests} for HEAD {head} (Pulse ran them there; do not run them again)" if tests else \
        f"tests: skipped for HEAD {head} (Pulse did not run them)"
    prompt = PROMPT.format(what=_what(n, title, scope), skill=SKILL, inputs=inputs,
                           mode="repo mode" if scope == "full" else "item mode", tests=ran,
                           changes=changes(scope, base, rng), found="; ".join(found) or "nothing", report=REPORT)
    return {"number": n, "base": base, "found": found, "prompt": prompt}


def _sca(scan: dict) -> dict:
    """The scan's SCA entry; a scan without one checked no dependency."""
    return next((t for t in scan.get("tools", []) if t.get("name") == "osv"),
                {"status": "missing", "reason": "the scan has no SCA entry"})


def _scan(root: Path, args: list) -> tuple:
    """Run the scanner for the auditor in the calling process and its sandbox: outside any agent
    sandbox and with the network only when pulse go or a person calls it, not when an agent runs
    `pulse audit`. Its JSON goes where the session can read it; returns what the brief tells the
    session about it, and why the scan gave nothing ("" when it ran)."""
    out, timeout = root / SCAN_JSON, config.load(root)["agent_timeout"] * 60
    out.unlink(missing_ok=True)
    try:
        cp = subprocess.run([sys.executable, os.environ.get("PULSE_AUDIT_SCAN") or str(AUDIT_SCAN), *args],
                            cwd=root, capture_output=True, text=True, timeout=timeout)
        scan = json.loads(cp.stdout)
    except subprocess.TimeoutExpired:
        return "", "the scan timed out"
    except ValueError:
        why = (cp.stderr.strip().splitlines() or [f"exit {cp.returncode}"])[-1]
        return "", f"the scan failed ({why})"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(cp.stdout, encoding="utf-8")
    sca, meta = _sca(scan), scan.get("meta", {})
    dates = sorted(d for d in (meta.get("taxonomy") or {}).values() if d)
    return (f"its JSON is at {SCAN_JSON}; SCA (OSV) "
            + (f"ran over {sca.get('packages', 0)} packages" if sca["status"] == "ran"
               else f"{sca['status']}: {sca.get('reason', '')}")
            + f"; bundled references as of {dates[0] if dates else 'no date'}"
            + (f"; {meta['taxonomy_warning']}" if meta.get("taxonomy_warning") else "")), ""


def _since(root: Path) -> str:
    """The files and manifests changed since the last audit that counted in this clone: on this
    line of history, so an audit of another branch adds nothing."""
    try:
        last = json.loads((config.pulse_dir(root) / CONTEXT).read_text(encoding="utf-8"))
        commit, when = last["commit"], last["date"]
    except (OSError, ValueError, KeyError):
        return "no earlier audit in this clone"
    if not _git(root, "rev-parse", "-q", "--verify", f"{commit}^{{commit}}").strip():
        return f"{when} at {commit[:12]}, a commit this clone no longer has"
    changed = _git(root, "diff", "--name-only", f"{commit}...HEAD").splitlines()
    shown = ", ".join(changed[:50]) + (f" and {len(changed) - 50} more" if len(changed) > 50 else "")
    return (f"{when} at {commit[:12]}; changed since: {shown or 'nothing'}; manifests among them: "
            f"{', '.join(f for f in changed if MANIFEST.search(f)) or 'none'}")


def audit_brief(root: Path, n: int = None, title: str = "", base=None, scope: str = "branch",
                rng: str = None) -> dict:
    """The auditor's inputs; in the chain always the branch against its base. Pulse runs the
    scan itself and names what changed since the previous audit. unscanned: why the scan gave
    nothing, so the audit gives no verdict; "" when it ran."""
    if n is not None:
        _note_before(root, n, "audit")
    base = base or config.base_ref(root)
    flags = {"branch": ["--scope", "branch", "--base", base], "range": ["--scope", "range", "--range", rng]}.get(
        scope, ["--scope", scope])
    args = ["all", *flags, "--no-baseline"]
    said, unscanned = _scan(root, args)
    prompt = AUDIT_PROMPT.format(what=_what(n, title, scope), skill=AUDIT_SKILL, args=" ".join(args),
                                 scan=said or f"{unscanned}, so this audit gives no verdict", since=_since(root))
    return {"number": n, "base": base, "prompt": prompt, "unscanned": unscanned}


def _kept(root: Path, n: int, kind: str = "review") -> Path:
    return config.pulse_dir(root) / KEPT[kind] / f"{n}.md"


def _take_scan(root: Path) -> dict:
    """The scan audit_brief saved, gone once taken: one scan gives one verdict, and no later agent
    commits it."""
    try:
        raw = (root / SCAN_JSON).read_text(encoding="utf-8")
        (root / SCAN_JSON).unlink()
        return json.loads(raw)
    except (OSError, ValueError):
        return {}


def _unscanned(scan: dict, text: str, verdict, head: str) -> str:
    """Why an AUDIT.md is no verdict: it stands on the scan audit_brief ran at this commit, a pass
    names an SCA lookup that failed, and a Coverage line says what was checked. "" when it counts."""
    if scan.get("git_head") != head:
        return f"no scan of {head[:12]}: run the audit again with `pulse audit`, which runs the scan"
    sca, coverage = _sca(scan), COVERAGE.search(text)
    if verdict == "pass" and sca["status"] not in ("ran", "not-applicable") \
            and "sca unavailable" not in (coverage.group(1).lower() if coverage else ""):
        return f"SCA unavailable ({sca['status']}: {sca.get('reason', '')}), and the Coverage line does not say so"
    if not coverage:
        return "the report has no Coverage line (what the scan and the audit checked, and what not)"
    return ""


def _remember(root: Path, head: str) -> None:
    """The audit that counted, for the next one's "since": its date, commit, and manifests."""
    path = config.pulse_dir(root) / CONTEXT
    path.parent.mkdir(parents=True, exist_ok=True)
    manifests = [f for f in _git(root, "ls-files").splitlines() if MANIFEST.search(f)]
    path.write_text(json.dumps({"date": date.today().isoformat(), "commit": head, "manifests": manifests}),
                    encoding="utf-8")


def record(root: Path, n: int = None, kind: str = "review", failed: str = "") -> dict:
    """Keep the session's REVIEW.md or AUDIT.md in the shared git dir, stamped with HEAD.
    Without an item number the verdict is read and nothing is kept. failed: how the session
    ended when it did not end cleanly; its report and its note go, and nothing counts. An audit
    without its scan is nobody's verdict; one that counts is noted for the next audit."""
    report = REPORTS[kind]
    src = root / report
    scan = _take_scan(root) if kind == "audit" else {}
    if _tracked(root, kind):
        return {"number": n, "verdict": None, "why": f"{report} is committed on the branch; only a fresh "
                                                     f"session writes it. Remove it from the branch and run the {kind} again"}
    if failed:
        if _present(root, kind):
            src.unlink()
        if n is not None:
            _kept(root, n, kind).with_suffix(".before").unlink(missing_ok=True)
        return {"number": n, "verdict": None, "why": f"the {kind} session {failed}", "report": ""}
    if not _present(root, kind):
        return {"number": n, "verdict": None, "why": f"no {report} in {root}"}
    text = src.read_text(encoding="utf-8").strip()
    src.unlink()
    m = VERDICT.search(text)
    head = _git(root, "rev-parse", "HEAD").strip()
    verdict, why = (m.group(1).lower(), "") if m else (None, "the report has no Verdict line")
    unscanned = _unscanned(scan, text, verdict, head) if kind == "audit" else ""
    if unscanned:
        verdict, why = None, unscanned
    if n is None:
        if verdict and kind == "audit":
            _remember(root, head)
        return {"number": None, "verdict": verdict, "commit": head, "report": text, "why": why}
    before = _kept(root, n, kind).with_suffix(".before")
    try:
        was = json.loads(before.read_text(encoding="utf-8"))
        before.unlink()
    except (OSError, ValueError):
        was = None
    if was and was != _snapshot(root, kind):
        return {"number": n, "verdict": None, "commit": head, "report": text,
                "why": f"the {kind} session changed the branch (HEAD or the working tree); run it again"}
    if unscanned:                     # not kept: last() would read its Verdict line as a verdict
        return {"number": n, "verdict": None, "commit": head, "report": text, "why": why}
    if verdict and kind == "audit":
        _remember(root, head)
    kept = _kept(root, n, kind)
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(f"Commit: {head}\n{text}\n", encoding="utf-8")
    return {"number": n, "verdict": verdict, "commit": head, "path": str(kept), "report": text, "why": why}


def _local(root: Path, n: int, kind: str):
    """The verdict of #n kept in this clone and the commit it saw; None without one."""
    try:
        text = _kept(root, n, kind).read_text(encoding="utf-8")
    except OSError:
        return None
    commit, verdict = re.search(r"^Commit:\s*(\S*)", text, re.M), VERDICT.search(text)
    return {"commit": commit.group(1) if commit else "", "verdict": verdict.group(1).lower() if verdict else None}


def last(root: Path, n: int, kind: str = "review"):
    """The kept verdict of #n and the commit it saw; without one in this clone, the newest one on
    the item's open PR (the clone that made it handed the item over). None when #n never had
    this session."""
    found = _local(root, n, kind)
    if found:
        return found
    try:                       # gh looked up per call so tests can swap it
        pr = _pr(root, n, state.repo(root, state.gh), state.gh)
    except (state.StateError, OSError, ValueError):
        return None            # no answer from GitHub: no verdict, the hook asks for the gates
    return next(({"commit": v["commit"], "verdict": v["verdict"]} for v in reversed(_published(pr))
                 if v["gate"] == kind), None)


def _pr(root: Path, n: int, repo_name: str, run) -> dict:
    """The open PR of the checked-out branch when it builds #n, with its comments; {} without one."""
    # ponytail: gh pr list brings the first 100 comments of a PR; a marker after them goes unseen
    # and the hook asks for the gates again. Paging the comments lifts that.
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    prs = json.loads(run(["pr", "list", "--repo", repo_name, "--head", branch, "--state", "open",
                          "--json", "number,headRefName,closingIssuesReferences,comments"]) or "[]")
    return next((p for p in prs if n in state.pr_items(p)), {})


def _published(pr: dict) -> list:
    """The verdicts on a PR, oldest first."""
    out = []
    for c in pr.get("comments") or []:
        if c.get("authorAssociation") not in state.WRITERS:
            continue
        for m in MARKER.finditer(c.get("body") or ""):
            try:
                v = json.loads(m.group(1))
                if v["verdict"] in ("pass", "block"):
                    out.append({k: str(v[k]) for k in ("gate", "commit", "verdict")})
            except (ValueError, KeyError):
                continue           # a marker nobody can read is no verdict
    return out


def publish(root: Path, n: int, run=state.gh, pr: int = None) -> list:
    """Put the verdicts of #n kept here for HEAD on the open PR of this branch, one marker per gate
    and commit, all in one comment (D-49), so the next holder of the item finds them through
    last(). `pr` is the PR pulse go just opened or rewrote after its gates ran at HEAD: not looked
    up again, its verdicts go on as new. Returns the gates it published; an error of gh passes
    through as StateError and changes nothing kept here."""
    head = _git(root, "rev-parse", "HEAD").strip()
    kept = {k: v["verdict"] for k in KEPT for v in [_local(root, n, k)] if v and v["verdict"] and v["commit"] == head}
    if not kept:
        return []
    repo_name = state.repo(root, run)
    pr = {"number": pr} if pr else _pr(root, n, repo_name, run)
    on = {(v["gate"], v["commit"]) for v in _published(pr)}
    new = [k for k in kept if (k, head) not in on] if pr else []
    body = []
    for k in new:
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_kept(root, n, k).stat().st_mtime))
        mark = json.dumps({"gate": k, "commit": head, "verdict": kept[k], "at": at})
        body.append(f"Pulse {k}: {kept[k]} for {head[:12]}.\n<!-- pulse:verdict {mark} -->")
    if body:
        run(["pr", "comment", str(pr["number"]), "--repo", repo_name, "--body", "\n\n".join(body)])
    return new


def template(cfg: dict, agent=None) -> str:
    try:
        name = agent or cfg["review_agent"] or next(iter(config.agent_slots(cfg["agent"], 1)), "")
    except ValueError as e:
        raise state.StateError(str(e)) from None
    found = cfg["agents"].get(name)
    if not found:
        raise state.StateError(f"no agent template '{name}' in [agents] of .pulse/config.toml")
    return found


def run(root: Path, n: int = None, title: str = "", spec=None, base=None, agent=None, kind: str = "review",
        scope: str = "branch", rng: str = None) -> dict:
    """Start the review or the audit headless in root, wait for it, read its verdict. The session
    carries PULSE_HOLDER like the gate sessions of pulse go, so the Stop hook leaves it alone. An
    audit whose scan failed gives no verdict, so it starts no session."""
    cfg = config.load(root)
    b = brief(root, n, title, spec, base, scope, rng) if kind == "review" else \
        audit_brief(root, n, title, base, scope, rng)
    found = b.get("found", [])
    if b.get("unscanned"):
        return {**record(root, n, kind, failed=f"did not start: {b['unscanned']}"), "found": found}
    try:
        cp = subprocess.run(config.agent_argv(template(cfg, agent), b["prompt"]), cwd=root,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            timeout=cfg["agent_timeout"] * 60,
                            env={**os.environ, "PULSE_HOLDER": json.dumps(state.holder())})
        failed = f"ended with exit {cp.returncode}" if cp.returncode else ""
    except subprocess.TimeoutExpired:
        failed = "timed out"
    return {**record(root, n, kind, failed=failed), "found": found}
