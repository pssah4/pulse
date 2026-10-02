"""The review and audit sessions of pulse go, their reports, and their local evidence.

Two parts: the review (spec, PLAN, decisions, lean code; ADR-05) and the
security audit of the branch, in one session, also for an item with
risk: [security] (#126). Whoever built the feature does neither. This
module gathers their inputs, adds what a script can see, and keeps each
verdict in config.evidence_dir, outside the git dir a Codex phase writes,
stamped with the commit it looked at; a session that changes the branch
gets no verdict. Item comments carry reports for the team and the next
holder. Those reports never create this clone's integration evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from pulse import config, ready, state

SKILLS = Path(__file__).resolve().parents[1] / "skills"
SKILL = SKILLS / "pulse-build" / "references" / "review.md"
AUDIT_SKILL = SKILLS / "pulse-audit" / "SKILL.md"
AUDIT_SCAN = SKILLS / "pulse-audit" / "tools" / "audit_scan.py"
REPORTS = {"review": "REVIEW.md", "audit": "AUDIT.md"}
SYSTEM_MAP = "_devprocess/SYSTEM-MAP.md"
KEPT = {"review": "reviews", "audit": "audits"}
VERDICT = re.compile(r"^Verdict:\s*(pass|block)\s*$", re.M | re.I)
SCAN_JSON = "_devprocess/temp/audit-scan.json"    # the scan Pulse runs for the auditor, where it can read it
CONTEXT = "audit-context.json"                    # the last audit that counted, in config.evidence_dir
MANIFEST = re.compile(r"(^|/)(package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|requirements[^/]*\.txt|pyproject\.toml"
                      r"|poetry\.lock|uv\.lock|Pipfile(\.lock)?|go\.(mod|sum)|Cargo\.(toml|lock)|setup\.(py|cfg)"
                      r"|Gemfile(\.lock)?|composer\.(json|lock)|bun\.lockb?|npm-shrinkwrap\.json|\.npmrc)$")
COVERAGE = re.compile(r"^Coverage:(.*)$", re.M | re.I)
MARKER = re.compile(r"<!-- pulse:verdict (\{[^{}\[\]]*\}) -->")   # flat report metadata on an item comment
INSTRUCTIONS = re.compile(r"(^|/)(CLAUDE\.md|AGENTS\.md|\.mcp\.json|\.(claude|codex|agents)/.*)$", re.I)   # read at start
PROMPT = """You review {what} in a fresh session; you did not build it.
Follow {skill}. Inputs: {inputs}the changes {changes}, the system map as the base has it ({map};
the branch's own change to it is part of the changes), and the decision
records whose "Read When" matches ({decisions}).
Found by script: {found}
{tests}
Do not change code, do not commit, do not touch GitHub. Write {report}: first line
`Verdict: pass` or `Verdict: block`, then one line per finding,
`- [block|note] <file>:<line> <check>: <what>`."""
AUDIT_PROMPT = """You audit the security of {what} in a fresh session; you did not build it.
Follow {skill}, section "In the chain": the scope below, no question to anyone,
no live lookup. Pulse ran `audit_scan.py {args}` for you: {scan}.
Since the previous audit: {since}.
Found by script: {found}
Triage the scan's JSON (source to sink, false positives) and read the changed code yourself.
Do not change code, do not commit, do not touch GitHub. Write {report}: first line
`Verdict: pass` or `Verdict: block` (block while a Critical or High finding is open), then
`Coverage: <what the scan and you checked, and what not>` (a report without it gives no
verdict), with `SCA unavailable` in it when SCA was `offline`, `error` or `partial` (a pass
without that does not count), then one line per finding,
`- [H-1|M-1|L-1] <file>:<line> <CWE>: <what>`."""
CHECK = """You check {what} in a fresh session; you did not build it. Two parts, the review and then the
security audit, each with its own report and its own verdict: a finding of one never goes into the other.

{review}

{audit}"""


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
    what is in it, as in ready.ramp."""
    plans = ready.plans(root)
    if n not in plans:
        return [f"no PLAN for #{n}: scope unknown"]
    listed = ready.plan_files(root, plans)[n]
    return [f"outside the PLAN: {f}" for f in changed
            if not any(f == l or f.startswith(l + "/") for l in listed)
            and not f.startswith("_devprocess/")]     # spec and PLAN writeback is allowed


def _snapshot(root: Path):
    """HEAD and the working tree, every untracked file whatever status.showUntrackedFiles says, and
    without the temporary folder (a session may ignore it through .git/info/exclude while it runs).
    git leaves the folder out itself, so a file moved out of it still shows where it went. The
    report is gone by then (_note_before, record). None when git cannot tell."""
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", ".",
                             ":(exclude)_devprocess/temp"], capture_output=True, text=True)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if status.returncode or head.returncode:
        return None
    return {"head": head.stdout.strip(), "status": status.stdout.splitlines()}


def _tracked(root: Path, kind: str) -> bool:
    """Whether the branch itself carries the report; then it is nobody's verdict."""
    return bool(_git(root, "ls-files", "--", REPORTS[kind]).strip())


def _report(root: Path, kind: str, report=None) -> Path:
    """Where the session writes its report: the path pulse go named, else the worktree root."""
    return Path(report) if report else root / REPORTS[kind]


def _present(path: Path) -> bool:
    """A report file with exactly this name: macOS and Windows fold case, so a tracked audit.md
    would pass for AUDIT.md. A directory, a link, or a FIFO is no report."""
    try:
        return path.name in os.listdir(path.parent) and stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _note_before(root: Path, n: int, kind: str, report=None) -> None:
    """HEAD and the working tree before a fresh session starts, so record() can tell whether
    it changed anything (it must not, ADR-05). A report left by an earlier session goes, so
    that whatever record() finds was written by this one."""
    src = _report(root, kind, report)
    if _present(src) and (report or not _tracked(root, kind)):
        src.unlink()
    before = _kept(root, n, kind).with_suffix(".before")
    before.parent.mkdir(parents=True, exist_ok=True)
    before.write_text(json.dumps(_snapshot(root)), encoding="utf-8")


def _instructions(changed: list) -> list:
    """What a script can see too: changed files an agent session reads as its instructions when
    it starts in the checkout (FR-03)."""
    return [f"agent instructions changed: {f}" for f in changed if INSTRUCTIONS.search(f)]


def _at(root: Path, report) -> str:
    """How a session reaches root from where it starts: a gate session of pulse go starts beside
    its checkout (`tree/`), a session by hand in the worktree ("")."""
    return f"{os.path.relpath(root, Path(report).parent)}/" if report else ""


def _where(root: Path, kind: str, report) -> str:
    """Where the prompt sends the report: the worktree root, or the path pulse go gives a gate
    session, outside the checkout it reads (FR-02)."""
    at = _at(root, report)[:-1]
    return f"{REPORTS[kind]} at the worktree root" if not report else \
        f"your report to {report}, outside the checkout (the code is in {root}, `{at}` from where you " \
        f"start; run git on it as `git -C {at} diff`, `log`, `show`, or `status`, since a headless " \
        f"session refuses `cd {at} && git ...`)"


def _what(n, title: str, scope: str) -> str:
    return f"item #{n}" + (f' "{title}"' if title else "") if n is not None else f"the {scope} scope"


def brief(root: Path, n: int = None, title: str = "", spec=None, base=None, scope: str = "branch",
          rng: str = None, tests: str = None, report=None) -> dict:
    """The reviewer's inputs, and what a script already found. With an item number the
    verdict is kept for that item; without one it is only printed. tests: pass or fail when
    Pulse just ran the project's tests at HEAD (the tests gate), so the reviewer need not.
    report: where the session writes its report, outside root (pulse go)."""
    if n is not None:
        _note_before(root, n, "review", report)
    base = base or config.base_ref(root)
    changed = files(root, scope, base, rng) if scope != "full" else []
    found = (outside_plan(root, n, changed) if n is not None and scope != "full" else []) + _instructions(changed) + \
        [f"system map changed: {f}" for f in changed if f == SYSTEM_MAP] + \
        [f"runner or setup file changed since the spec tests were frozen: {f}"
         for f in (_loosened(root, n, base) if n is not None and scope == "branch" else [])]
    at = _at(root, report)                     # the paths and the git a gate session reads from session/
    diff = changes(scope, base, rng)
    plan = (ready.plans(root).get(n) or {}).get("path") if n is not None else ""
    inputs = f"the spec {f'{at}{spec}' if spec else f'(see `pulse status {n}`)'}, " \
             f"the PLAN {f'{at}{plan}' if plan else '(none)'}, " if n is not None else ""
    head = _git(root, "rev-parse", "--short=12", "HEAD").strip()
    ran = f"tests: {tests} for HEAD {head} (Pulse ran them there; do not run them again)" if tests else \
        f"tests: skipped for HEAD {head} (Pulse did not run them)"
    prompt = PROMPT.format(what=_what(n, title, scope), skill=SKILL, inputs=inputs, tests=ran,
                           changes=diff.replace("`git ", f"`git -C {at[:-1]} ") if at else diff,
                           found="; ".join(found) or "nothing", decisions=f"{at}_devprocess/decisions/README.md",
                           map=f"`git {f'-C {at[:-1]} ' if at else ''}show {base}:{SYSTEM_MAP}`",
                           report=_where(root, "review", report))
    return {"number": n, "base": base, "found": found, "prompt": prompt}


# What decides how spec tests run: conftest.py, runner configs, and test setup files (M-1 of #117)
RUNNING = re.compile(r"(^|/)(conftest\.py|pytest\.ini|tox\.ini|(playwright|vitest|jest)\.config\.[^/]+|"
                     r"(setupTests|setup|[^/]*[._-]setup)\.([cm]?[jt]sx?|py|cfg))$")


def _runs(root: Path, ref: str, path: str):
    """The part of pyproject.toml or package.json at ref that decides how tests run: the sections named for
    pytest, or the scripts."""
    text = _git(root, "show", f"{ref}:{path}")
    if path.endswith("package.json"):
        try:
            return json.loads(text).get("scripts")
        except (ValueError, AttributeError):
            return text
    return [s for s in re.split(r"(?m)^(?=\[)", text) if "pytest" in s.partition("\n")[0]]


def _loosened(root: Path, n: int, base: str) -> list:
    """Files that decide how the spec tests of #n run, changed after the first commit that froze them by a commit
    that froze none: RUNNING, the pytest sections of pyproject.toml, and the scripts of package.json."""
    grep = f"--grep=^test: spec tests for #{n}$"
    frozen = _git(root, "log", "--format=%H", grep, f"{base}..HEAD").split()
    if not frozen:
        return []
    changed = dict.fromkeys(filter(None, _git(root, "log", "--format=", "--name-only", "--invert-grep", grep,
                                              f"{frozen[-1]}..HEAD").splitlines()))
    return [f for f in changed if RUNNING.search(f) or f.rpartition("/")[2] in ("pyproject.toml", "package.json")
            and _runs(root, frozen[-1], f) != _runs(root, "HEAD", f)]


def _sca(scan: dict) -> dict:
    """The scan's SCA entry; a scan without one checked no dependency."""
    return next((t for t in scan.get("tools", []) if t.get("name") == "osv"),
                {"status": "missing", "reason": "the scan has no SCA entry"})


def _scan(root: Path, args: list) -> tuple:
    """Run the scanner for the auditor in the calling process: pulse go, outside any agent sandbox and
    with the network. Its JSON goes where the session can read it; returns what the brief tells the
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
    return (f"its JSON is at {out}; SCA (OSV) "
            + (f"ran over {sca.get('packages', 0)} packages" if sca["status"] == "ran"
               else f"{sca['status']}: {sca.get('reason', '')}")
            + f"; bundled references as of {dates[0] if dates else 'no date'}"
            + (f"; {meta['taxonomy_warning']}" if meta.get("taxonomy_warning") else "")), ""


def _since(root: Path) -> str:
    """The files and manifests changed since the last audit that counted in this clone: on this
    line of history, so an audit of another branch adds nothing."""
    try:
        last = json.loads((config.evidence_dir(root) / CONTEXT).read_text(encoding="utf-8"))
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
                rng: str = None, report=None) -> dict:
    """The auditor's inputs; in the chain always the branch against its base. Pulse runs the
    scan itself and names what changed since the previous audit. unscanned: why the scan gave
    nothing, so the audit gives no verdict; "" when it ran. report: as in brief()."""
    if n is not None:
        _note_before(root, n, "audit", report)
    base = base or config.base_ref(root)
    found = _instructions(files(root, scope, base, rng)) if scope != "full" else []
    flags = {"branch": ["--scope", "branch", "--base", base], "range": ["--scope", "range", "--range", rng]}.get(
        scope, ["--scope", scope])
    args = ["all", *flags, "--no-baseline"]
    said, unscanned = _scan(root, args)
    prompt = AUDIT_PROMPT.format(what=_what(n, title, scope), skill=AUDIT_SKILL, args=" ".join(args),
                                 scan=said or f"{unscanned}, so this audit gives no verdict", since=_since(root),
                                 found="; ".join(found) or "nothing", report=_where(root, "audit", report))
    return {"number": n, "base": base, "found": found, "prompt": prompt, "unscanned": unscanned}


def check_brief(root: Path, n: int, title: str, spec, base, kinds: tuple, tests: str, where: Path) -> dict:
    """The fresh session of pulse go for the gates in kinds, review and audit: each part with its own brief
    and its report in where, two parts in one prompt (#120). An audit whose scan failed leaves the session
    (unscanned: why), so its gate gets no verdict; kinds in the result: the parts the session answers."""
    parts, unscanned = {}, ""
    if "review" in kinds:
        parts["review"] = brief(root, n, title, spec, base, tests=tests, report=where / REPORTS["review"])["prompt"]
    if "audit" in kinds:
        b = audit_brief(root, n, title, base, report=where / REPORTS["audit"])
        unscanned = b["unscanned"]
        if not unscanned:
            parts["audit"] = b["prompt"]
    prompt = CHECK.format(what=_what(n, title, "branch"), **parts) if len(parts) == 2 else "".join(parts.values())
    return {"kinds": tuple(parts), "prompt": prompt, "unscanned": unscanned}


def _kept(root: Path, n: int, kind: str = "review") -> Path:
    return config.evidence_dir(root) / KEPT[kind] / f"{n}.md"


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
        return f"no scan of {head[:12]}: only an audit whose brief ran the scan at this commit counts"
    sca, coverage = _sca(scan), COVERAGE.search(text)
    if verdict == "pass" and sca["status"] not in ("ran", "not-applicable") \
            and "sca unavailable" not in (coverage.group(1).lower() if coverage else ""):
        return f"SCA unavailable ({sca['status']}: {sca.get('reason', '')}), and the Coverage line does not say so"
    if not coverage:
        return "the report has no Coverage line (what the scan and the audit checked, and what not)"
    return ""


def _remember(root: Path, head: str) -> None:
    """The audit that counted, for the next one's "since": its date, commit, and manifests."""
    path = config.evidence_dir(root) / CONTEXT
    path.parent.mkdir(parents=True, exist_ok=True)
    manifests = [f for f in _git(root, "ls-files").splitlines() if MANIFEST.search(f)]
    path.write_text(json.dumps({"date": date.today().isoformat(), "commit": head, "manifests": manifests}),
                    encoding="utf-8")


BLOCKING = re.compile(r"^\s*[-*]\s*\[block\]", re.M | re.I)       # a finding line that blocks


def verdict(text: str) -> bool:
    """Whether a review or audit report is green: its first line reads exactly `Verdict: pass`, whatever the case
    (IMP-03-13 FR-06), and no finding below it blocks (B-1). A reservation on that line, such as "pass (stays
    draft)", or a pass further down is none."""
    return text.strip().partition("\n")[0].strip().lower() == "verdict: pass" and not BLOCKING.search(text)


def _judged(text: str):
    """pass, block, or None: what the first line of a report says."""
    if verdict(text):
        return "pass"
    m = VERDICT.match(text.strip().partition("\n")[0])
    return "block" if m and (m.group(1).lower() == "block" or BLOCKING.search(text)) else None


def record(root: Path, n: int = None, kind: str = "review", failed: str = "", report=None) -> dict:
    """Keep the session's REVIEW.md or AUDIT.md in config.evidence_dir, stamped with HEAD; report:
    where the brief sent it, outside root. Without an item number the verdict is read and nothing
    is kept; with one it counts only after the brief of this run noted the tree (FR-05). failed:
    how the session ended when it did not end cleanly; its report and its note go, and nothing
    counts. An audit without its scan is nobody's verdict; one that counts is noted for the next
    audit."""
    name, src = REPORTS[kind], _report(root, kind, report)
    scan = _take_scan(root) if kind == "audit" else {}
    if not report and _tracked(root, kind):
        return {"number": n, "verdict": None, "why": f"{name} is committed on the branch; only a fresh "
                                                     f"session writes it. Remove it from the branch and run the {kind} again"}
    if failed:
        if _present(src):
            src.unlink()
        if n is not None:
            _kept(root, n, kind).with_suffix(".before").unlink(missing_ok=True)
        return {"number": n, "verdict": None, "why": f"the {kind} session {failed}", "report": ""}
    if not _present(src):
        return {"number": n, "verdict": None, "why": f"no {name} in {src.parent}"}
    text = src.read_text(encoding="utf-8").strip()
    src.unlink()
    head = _git(root, "rev-parse", "HEAD").strip()
    verdict = _judged(text)
    why = "" if verdict else "the report's first line is neither `Verdict: pass` nor `Verdict: block`"
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
        return {"number": n, "verdict": None, "commit": head, "report": text,
                "why": f"no brief of this run noted the tree for #{n}: the {kind} counts only after its brief"}
    now = _snapshot(root)
    if was is None or now is None:
        return {"number": n, "verdict": None, "commit": head, "report": text,
                "why": f"git status failed, so nobody can tell whether the {kind} session changed the branch"}
    if was != now:
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
    commit = re.search(r"^Commit:\s*(\S*)", text, re.M)       # the line record() puts above the report
    return {"commit": commit.group(1) if commit else "", "verdict": _judged(text.partition("\n")[2])}


def last(root: Path, n: int, kind: str = "review", known: dict = None):
    """The kept verdict of #n and the commit it saw; without one in this clone, the newest one on
    the item (the clone that made it handed the item over). None when #n never had
    this session, or when GitHub could not say whether the author of that newest one may push.
    known: the answers about authors, as state.writer keeps them, shared by the reads of one event."""
    found = _local(root, n, kind)
    if found:
        return found
    try:                       # gh looked up per call so tests can swap it
        repo_name = state.repo(root, state.gh)
        v = next((v for v in reversed(_published(_issue(n, repo_name, state.gh), repo_name, state.gh, known, n))
                  if v["gate"] == kind), None)
    except (state.StateError, OSError, ValueError):
        return None            # no answer from GitHub: no verdict, the hook asks for the gates
    return {"commit": v["commit"], "verdict": v["verdict"]} if v and "unchecked" not in v else None


def _issue(n: int, repo_name: str, run) -> dict:
    raw = json.loads(run(["issue", "view", str(n), "--repo", repo_name, "--json", "number,comments"]))
    if not isinstance(raw, dict) or raw.get("number") != n:
        raise state.StateError("review reports came from a different item")
    return state.complete_comments(repo_name, raw, run)


def _marks(body: str, full=False) -> list:
    """The verdicts a comment carries, each on a line of its own as publish writes it: none in a quote, a code
    block, or a sentence, which may be someone else's text (audit L-1 of #74). A line ends only at a newline, never
    at U+2028 or the like, where Markdown goes on. Linear in the text, and flat: publish writes no array and no
    object into a marker (M-1)."""
    out, code = [], None
    lines = body.replace("\r", "").split("\n")
    for index, line in enumerate(lines):
        fence = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if code:
            if re.fullmatch(r" {0,3}" + re.escape(code[0]) + "{" + str(code[1]) + r",}[ \t]*", line):
                code = None
            continue
        if fence:
            code = (fence[1][0], len(fence[1]))
            continue
        m = MARKER.fullmatch(line)
        try:
            v = json.loads(m.group(1)) if m else {}
            if v.get("verdict") in ("pass", "block"):
                out.append({**{k: str(v[k]) for k in ("gate", "commit", "verdict")},
                            **{k: v[k] for k in ("item", "digest") if k in v}})
                if full:
                    out[-1]["text"] = _marked_text(lines, index + 1)
        except (ValueError, KeyError, RecursionError):
            continue           # a marker nobody can read is no verdict
    return out


def _marked_text(lines, start):
    """Only the immediately following fenced block belongs to this marker."""
    opening = re.fullmatch(r"(`{3,})text", lines[start]) if start < len(lines) else None
    if opening:
        closing = re.compile(r"`{" + str(len(opening[1])) + r",}[ \t]*")
        for end in range(start + 1, len(lines)):
            if closing.fullmatch(lines[end]):
                return "\n".join(lines[start + 1:end])
    return None


def _published(thread: dict, repo_name: str, run, known: dict = None, n=None, full=False) -> list:
    """The reports on an item, oldest first, from people who may push: anyone may comment, so the
    comment of anyone else is not even read (audit M-1). A verdict whose author GitHub could not check carries
    its reason as "unchecked": it counts for nothing, and while it is the newest of its gate no older one counts
    in its place. known: as state.writer keeps it."""
    out, known = [], {} if known is None else known
    for c in thread.get("comments") or []:
        marks = _marks(c.get("body") or "", full=full) if c.get("authorAssociation") in state.WRITERS else []
        if n is not None:
            marks = [v for v in marks if v.get("item") == n and v["gate"] in KEPT
                     and re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", v["commit"])
                     and isinstance(v.get("digest"), str) and re.fullmatch(r"[0-9a-f]{64}", v["digest"])]
            if urlsplit(c.get("url") or "").path != f"/{repo_name}/issues/{n}":
                continue
            if c.get("edited") or c.get("lastEditedAt") or c.get("includesCreatedEdit"):
                out += [{**v, "unchecked": "report comment was edited"} for v in marks]
                continue
        ok = marks and state.writer(c, repo_name, run, known)      # asks only for an author of a marker
        if ok is True and n is not None:
            login = (c.get("author") or {}).get("login")
            ok = state.pusher(repo_name, login, run, known)
            if not ok and isinstance(known.get(login), str):
                ok = known[login]
        if ok:
            out += marks if ok is True else [{**v, "unchecked": ok} for v in marks]
    return out


def result_reports(root, n, head, *, thread=None, repo_name="", run=None, known=None, cached=None):
    """Display exact-head reports without importing gate evidence or reading an issue.

    Only the background reader supplies a thread and rights transport. Cached
    projections and protected local reports remain available without network.
    """
    reports, known = {}, {} if known is None else known

    def accept(kind, value, source):
        text = value.get("text")
        if (kind in KEPT and value.get("commit") == head and "unchecked" not in value
                and isinstance(text, str) and _judged(text) == value.get("verdict")
                and value.get("verdict") in {"pass", "block"}
                and hashlib.sha256(text.encode("utf-8")).hexdigest() == value.get("digest")):
            reports[kind] = {key: value[key] for key in ("commit", "verdict", "text", "digest")}
            reports[kind]["source"] = source

    if thread is None:
        for kind, value in (cached or {}).items():
            if isinstance(value, dict) and value.get("source") in {"comment", "local"}:
                accept(kind, value, value["source"])
    for kind in KEPT:
        if kind in reports:
            continue
        path = _kept(root, n, kind)
        try:
            if not _present(path):
                continue
            binding, _, text = path.read_text(encoding="utf-8").partition("\n")
        except (OSError, UnicodeError):
            continue
        text = text.strip()
        if binding == f"Commit: {head}":
            accept(kind, {"commit": head, "verdict": _judged(text), "text": text,
                          "digest": hashlib.sha256(text.encode("utf-8")).hexdigest()}, "local")
    if thread is not None:
        for comment in thread.get("comments") or []:
            # A newer unusable report must not leave an older green one displayed.
            for value in _marks(comment.get("body") or ""):
                if value.get("item") == n:
                    reports.pop(value["gate"], None)
            if run is not None:
                for value in _published({"comments": [comment]}, repo_name, run, known, n, full=True):
                    accept(value["gate"], value, "comment")
    findings = [line.strip() for report in reports.values() for line in report["text"].splitlines()
                if re.match(r"\s*[-*]\s+\[(?:block|note|[HML]-[0-9]+)\]", line, re.I)]
    return {"reports": reports, "findings": findings if reports else None,
            "missing": [kind for kind in KEPT if kind not in reports]}


def publish(root: Path, n: int, run=state.gh, pr: int = None, repo_name: str = None) -> list:
    """Publish local HEAD reports on item n, once per content digest. The old pr argument is ignored.

    These comments support team handover and human review; they grant no local gate authority.
    Errors leave the protected local reports intact for retry.
    """
    head = _git(root, "rev-parse", "HEAD").strip()
    kept = {k: v["verdict"] for k in KEPT for v in [_local(root, n, k)] if v and v["verdict"] and v["commit"] == head}
    if not kept:
        return []
    repo_name = repo_name or state.repo(root, run)
    thread = _issue(n, repo_name, run)
    own = [v for c in thread.get("comments") or [] if c.get("viewerDidAuthor") and not c.get("edited")
           and urlsplit(c.get("url") or "").path == f"/{repo_name}/issues/{n}"
           for v in _marks(c.get("body") or "") if v.get("item") == n]
    on = {(v["gate"], v["commit"], v["verdict"], v.get("digest"))
          for v in [*_published(thread, repo_name, run, n=n), *own] if "unchecked" not in v}
    reports = {k: _kept(root, n, k).read_text(encoding="utf-8").partition("\n")[2].strip() for k in kept}
    digests = {k: hashlib.sha256(text.encode("utf-8")).hexdigest() for k, text in reports.items()}
    new = [k for k in kept if (k, head, kept[k], digests[k]) not in on]
    body = []
    for k in new:
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_kept(root, n, k).stat().st_mtime))
        mark = json.dumps({"item": n, "gate": k, "commit": head, "verdict": kept[k], "at": at, "digest": digests[k]})
        fence = "`" * max(3, 1 + max((len(m[0]) for m in re.finditer(r"`+", reports[k])), default=0))
        body.append(f"Pulse {k}: {kept[k]} for {head}.\n<!-- pulse:verdict {mark} -->\n"
                    f"{fence}text\n{reports[k]}\n{fence}")
    if body:
        run(["issue", "comment", str(n), "--repo", repo_name, "--body", "\n\n".join(body)])
    return new


def template(cfg: dict, agent=None) -> str:
    try:
        name = agent or next(iter(config.agent_slots(cfg["agent"], 1)), "")
    except ValueError as e:
        raise state.StateError(str(e)) from None
    found = cfg["agents"].get(name)
    if not found:
        raise state.StateError(f"no agent template '{name}' in [agents] of .pulse/config.toml")
    return found


def gate_template(cfg: dict, agent=None) -> str:
    """The template of a gate session of pulse go: its allow list also runs git on the checkout the
    way the prompt says (`git -C tree ...`); a template without {allow} stays as it is."""
    allow = config._allow(cfg["verify"])
    tree = " ".join(f"'Bash(git -C tree {g}:*)'" for g in ("diff", "log", "show", "status"))
    return template(cfg, agent).replace(allow, f"{allow} {tree}")
