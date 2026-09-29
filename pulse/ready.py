"""Readiness: which items may be planned, which may be built, and why the others wait.

An item is ready when a person approved it (gate 1), its spec is on the
base branch and passes R1 to R6 (pulse/spec.py), it has a PLAN that passes
P1 to P5, a person approved that PLAN (gate 2: a Plan-ok that names the
blobs of PLAN and spec as origin has them, #115), and no blocker is open.
pulse go asks GitHub whether the people who approved may push.

PLANs live in the working tree (interactive /pulse-plan) or on the pushed
item branch (planning runs of pulse go); fetch() brings the item branches
of every clone. The rules read text only; plans() and gates() read git.

The ramp (ramp(), view()) says what goes out next, without two agents
stepping on each other: every blocker is closed (a dependent waits for
its blocker's merge), and items that run at the same time touch disjoint
files (their PLANs list them under `files:`). The order is order(): no item
before its blocker, then effective priority and number. Files of anyone's running item are held;
only my own running items take my slots (`cap` in .pulse/config.toml).
"""
from __future__ import annotations

import hashlib
import heapq
import json
import os
import posixpath
import re
import signal
import subprocess
import time
import unicodedata
from pathlib import Path

from pulse import config, spec, state

FETCH_EVERY = 30                     # seconds between two fetches of one clone, whoever asks
GIT_TIMEOUT = 60                     # seconds for git over the network, as for gh
NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""}   # a password prompt fails at once
PLANS = "_devprocess/plans"
IDS = re.compile(r"\b(?:FR|SC)-\d+\b")
TICK = re.compile(r"`([^`\s]+)`")
CODE = re.compile(r"`[^`\n]*`")         # inline code: braces there are code, not a placeholder
REF = re.compile(r"#(\d+)(?=[\s,:;]|$)")  # a needs: entry that names an item first (pulse go makes it a blocker)
WAITS = ("plan waits", "plan changed", "spec changed")      # a gate at which a PLAN waits for a person (#115)
MOVED = "docs PR changed since approval"      # gate 1 waits again: no approval names its head and spec path (M-1)
SAID = re.compile(r"^(?=(?:error|fatal|warning|hint):)", re.M)     # where each message of git starts
HEADS = re.compile(r"^([0-9a-f]{40}(?:[0-9a-f]{24})?)\trefs/heads/(.+)$", re.M)   # a line git ls-remote writes
NO_ANSWER = "origin did not answer"
_memo: dict = {}                     # (branch sha, base ref) -> its PLAN; git history never changes
_specs: dict = {}                    # (base sha, path) -> the spec text there, or None


def _git(root: Path, *args) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout      # one bad byte in a PLAN stops nothing


def net_git(cwd, *args) -> subprocess.CompletedProcess:
    """git over the network: no prompt, no terminal, stdin closed, and a time limit that ends git with
    everything it started (ssh, a remote helper). A run out of time reads as a failure."""
    with subprocess.Popen(["git", "-C", str(cwd), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, errors="replace", env={**os.environ, **NO_PROMPT},
                          start_new_session=True) as p:
        try:
            out, err = p.communicate(timeout=GIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = "", f"no answer within {GIT_TIMEOUT} s"
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def fetch(root: Path, now=False):
    """Every branch on origin, and none it dropped, so this clone sees what the others planned
    and hold (D-10); at most every FETCH_EVERY seconds per clone, or `now` whatever the last one
    was: before an ID is handed out or a claim names its start point (#78). True when the fetch went
    through, this one or the last; False when it failed, and the stamp keeps `offline` and what git
    said for every command (#85); None without a place to note the fetch (a read-only .git), where no
    fetch runs. Silent, and nothing waits long."""
    stamp = config.pulse_dir(root) / "fetched"
    try:
        if not now and time.time() - stamp.stat().st_mtime < FETCH_EVERY:
            return stamp.read_text(encoding="utf-8").partition("\n")[0] != "offline"
    except OSError:
        pass
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        was = stamp.stat().st_mtime if now and stamp.exists() else 0
        stamp.touch()
    except OSError:
        return None            # no fetch rather than one per call
    got = net_git(root, "fetch", "-q", "--prune", "origin")
    answered = got.returncode == 0
    said = git_error(got.stderr) if got.returncode > 0 else ""    # killed at the time limit: git said nothing
    try:
        stamp.write_text("" if answered else f"offline\n{said}", encoding="utf-8")
        if now:                # a fetch of its own: the map and the others keep their pace (#78 E2E m1)
            os.utime(stamp, (was, was))
    except OSError:
        pass
    return answered


def git_error(text: str) -> str:
    """git's error: and fatal: messages with the lines they wrap onto, on one line fit for a terminal;
    all of it from a git that speaks another language (#85)."""
    parts = [p for p in SAID.split(text) if p.startswith(("error:", "fatal:"))]
    return printable(" ".join(" ".join(parts or [text]).split()))


def fetch_said(root) -> str:
    """What git said at the last fetch of this clone, as its stamp keeps it for every command: "" after
    a fetch that went through, or one the time limit ended, where git said nothing (#85)."""
    try:
        return (config.pulse_dir(root) / "fetched").read_text(encoding="utf-8").partition("\n")[2]
    except (OSError, state.StateError):
        return ""


def behind(root) -> dict | None:
    """{branch: the commit origin names} for each branch whose refs/remotes/origin/<branch> git lists here
    on another commit, and {branch: ""} for a listed ref whose branch origin no longer has: what a fetch
    git could not finish leaves. Where one ref file holds names that differ only in case (_folds), every
    such name too, on origin or a local branch (""), whatever its ref shows now: a twin loose beside a
    packed origin/main resolves elsewhere while the list matches origin (#97). None when git ls-remote
    fails, as offline. Only lines of a commit and a branch count: a name with a newline forges no revision (#85)."""
    heads = net_git(root, "ls-remote", "--heads", "origin")
    if heads.returncode:
        return None
    there = {b: c for c, b in HEADS.findall(heads.stdout)}
    here = {b: c for b, c, link in (line.split(" ") for line in _git(      # "\n" only: a ref name may hold U+2028
        root, "for-each-ref", "--format=%(refname:lstrip=3) %(objectname) %(symref)", "refs/remotes/origin"
    ).split("\n") if line) if not link}                            # origin/HEAD names a branch, it is none
    local = _git(root, "for-each-ref", "--format=%(refname:lstrip=2)", "refs/heads").split("\n")
    same = twins({*there, *local} - {""})
    return {b: c for b, c in there.items() if here.get(b) != c} | {b: "" for b in here if b not in there} | \
        ({b: there.get(b, "") for b in same} if same and _folds(root) else {})


def twins(names) -> list:
    """The names among names that another one equals but for case or Unicode normalization, sorted (#97)."""
    groups: dict = {}
    for b in names:
        groups.setdefault(unicodedata.normalize("NFC", b).casefold(), set()).add(b)
    return sorted(b for g in groups.values() if len(g) > 1 for b in g)


def conflict(names) -> str:
    """One line on the branches among names that share a ref file here, "" without any (#97)."""
    same = twins(names)
    return ("branch names that differ only in case share one ref file here: " + ", ".join(map(printable, same)) +
            "; delete or rename one of them on origin") if same else ""


def _folds(root) -> bool:
    """Whether one ref file here holds names that differ only in case: core.ignorecase, which git sets on macOS and
    Windows, and refs as files (#97)."""
    # ponytail: trusts core.ignorecase; a clone copied from Linux onto macOS says false and goes unchecked
    return _git(root, "config", "--type=bool", "core.ignorecase").strip() == "true" and \
        _git(root, "config", "extensions.refstorage").strip().lower() != "reftable"


def folded(root, *names, item=None) -> str:
    """conflict() when a branch among names, or a branch of item, shares its ref file here with another name: its
    ref may show the other's commit, or none of item's work; "origin did not answer" when that cannot be told; ""
    where every name has its own ref, without asking origin (#97)."""
    if not _folds(root):
        return ""
    got = behind(root)
    if got is None:
        return NO_ANSWER
    local = _git(root, "for-each-ref", "--format=%(refname:lstrip=2)", "refs/heads").split("\n")
    same = twins({*got, *local, *names} - {""})
    hit = [b for b in same if b in names or item is not None and state.item_of(b) == item]
    return conflict(same) if hit else ""


def listed(text: str, key: str) -> list:
    """A block list (`key:` then `  - item` lines) or an inline list from the frontmatter."""
    out, on = [], False
    for line in spec.split(text)[0]:
        if re.match(rf"^{re.escape(key)}:\s*(?:#.*)?$", line):      # a comment may follow, as in the template
            on = True
            continue
        if on and re.match(r"^\s+-", line):
            out.append(re.sub(r"\s#.*", "", line.split("-", 1)[1]).strip().strip("'\""))    # \s, not \s+: linear
            continue
        on = False
    inline = spec.front(text).get(key)
    return [x for x in out + [v.strip("'\"") for v in (inline if isinstance(inline, list) else [])] if x]


def _issue(text: str):
    n = str(spec.front(text).get("issue", "")).lstrip("#")
    return int(n) if n.isdigit() else None


def _branch_plan(root: Path, base: str, ref: str, n: int):
    """The PLAN of #n on its pushed branch: a Markdown file in the plans folder itself, as in the
    working tree; the map opens it with the system's app (audit of #55)."""
    for path in _git(root, "diff", "-z", "--name-only", "--diff-filter=AM", f"{base}...{ref}", "--",
                     f":(glob){PLANS}/*.md").split("\0"):
        if Path(path).parent.as_posix() != PLANS or not path.endswith(".md"):   # a space splits nothing now
            continue
        text = _git(root, "show", f"{ref}:{path}")
        if _issue(text) == n:
            return {"path": path, "ref": ref, "text": text, "blob": _git(root, "rev-parse", f"{ref}:{path}").strip()}
    return None


def plans(root: Path, base: str = None) -> dict:
    """{issue: {"path", "ref", "text", "blob"}}: pushed item branches, then the working tree, which wins
    unless the item's branch on origin moved past it: the copy here is committed as it is, and
    that branch holds this commit and a different PLAN. blob is the PLAN at that path as origin has it, on the
    item's branch, else on the base: what a Plan-ok binds, the same for every clone (#115); "" where origin has
    none."""
    base = base or config.base_ref(root)
    out = {}
    tree = {e.partition("\t")[2]: e.split()[2] for e in _git(root, "ls-tree", "-z", base, "--", f"{PLANS}/")
            .split("\0") if "\t" in e}
    for line in _git(root, "for-each-ref", "--format=%(objectname) %(refname:short)",
                     "refs/remotes/origin").splitlines():
        sha, _, ref = line.partition(" ")
        n = state.item_of(ref.removeprefix("origin/"))
        if n:
            key = (sha, base)
            if key not in _memo:
                _memo[key] = _branch_plan(root, base, ref, n)
            if _memo[key]:
                out[n] = _memo[key]
    for path, text in spec.readable(sorted((root / PLANS).glob("*.md"))).items():
        n, rel = _issue(text), path.relative_to(root).as_posix()
        p = out.get(n)
        behind = p and p["ref"] and p["text"] != text and not _git(root, "status", "--porcelain", "--", rel) \
            and _git(root, "rev-list", "--count", f"{p['ref']}..HEAD").strip() == "0"
        if n and not behind:   # behind: a teammate pushed a newer PLAN on the item's branch
            out[n] = {"path": rel, "ref": None, "text": text,
                      "blob": p["blob"] if p and p["path"] == rel else tree.get(rel, "")}
    return out


def tasks(text: str) -> list:
    """The rows of the Tasks table as dicts keyed by the lower-cased header."""
    rows = [[c.strip() for c in l.strip().strip("|").split("|")]
            for l in spec.sections(text).get("tasks", "").splitlines() if l.strip().startswith("|")]
    if not rows:
        return []
    head = [h.lower() for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if not set("".join(r)) <= set("-: ")]


def wave_clashes(text: str) -> list:
    """[(line, message)] for files touched twice in one wave of a Tasks table."""
    out, cols, seen = [], None, {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if "files" in low and "wave" in low:
            cols, seen = (low.index("files"), low.index("wave")), {}
            continue
        if cols is None or not line.replace("|", "").replace("-", "").replace(":", "").strip():
            continue
        files_at, wave_at = cols
        if max(cols) >= len(cells):
            continue
        wave = seen.setdefault(cells[wave_at], {})
        for m in TICK.finditer(cells[files_at]):
            f = m.group(1)
            if f in wave:
                out.append((n, f"wave {cells[wave_at]}: {f} is also touched on line {wave[f]}; "
                               "tasks in one wave need disjoint files"))
            else:
                wave[f] = n
    return out


def _ids(spec_text: str) -> list:
    sec = spec.sections(spec_text)
    frs = [m.group(1) for content in sec.values() for m in spec.REQ.finditer(content)]
    scs = [row[0] for row in spec._rows(sec.get("success criteria", "")) if re.match(r"SC-\d+$", row[0])]
    return frs + scs


# A test file by its name: tests/, __tests__/, test_*, *.test.*, *.spec.*, *_test.* (Go), *_spec.* (RSpec).
TESTISH = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*$|[._](test|spec)\.[^/]*$")


def spec_test_files(text: str) -> list:
    """The test files wave 1 of a PLAN names (TESTISH), each spelled one way: its spec tests. Code in wave 1 is
    none of them."""
    return list(dict.fromkeys(posixpath.normpath(f) for r in tasks(text) if r.get("wave") == "1"
                              for f in TICK.findall(r.get("files", "")) if TESTISH.search(f)))


def plan_findings(text: str, spec_text, spec_tests=None) -> list:
    """['P2 not covered: SC-01', ...]; [] means an agent can build from this PLAN. spec_tests: [spec_tests] of the
    config on the base, for P6; None leaves P6 out."""
    fm, rows, out = spec.front(text), tasks(text), []
    missing = [k for k in ("issue", "spec") if not fm.get(k)] + \
              [k for k in ("files", "verify") if not listed(text, k)]
    if missing:
        out.append(f"P1 missing in frontmatter: {', '.join(missing)}")
    if "\ufffd" in text:      # read with replacement: approving it would bind the replaced text
        out.append("P1 the PLAN holds bytes outside UTF-8; save it as UTF-8")
    if spec_text is None:
        out.append("P2 the spec is not readable")
    else:
        covered = {i for r in rows for i in IDS.findall(r.get("covers", ""))}
        covered |= set(re.findall(r"Deferred:\s*((?:FR|SC)-\d+)", text))
        gaps = [i for i in _ids(spec_text) if i not in covered]
        if gaps:
            out.append(f"P2 not covered: {', '.join(gaps)}")
        first = {i for r in rows if r.get("wave") == "1" for i in IDS.findall(r.get("covers", ""))}
        kept = {m.group(1) for c in spec.sections(spec_text).values() for m in spec.REQ.finditer(c)
                if m.group(2).lstrip().lower().startswith("(unchanged)")}     # an existing test may prove it
        late = [i for i in _ids(spec_text)
                if i.startswith("FR-") and i in covered and i not in first and i not in kept]
        if late:
            out.append(f"P2 no spec test in wave 1 for: {', '.join(late)}")
    out += [f"P2 task {r.get('#', '?')} covers nothing" for r in rows if not IDS.search(r.get("covers", ""))]
    named = set()
    for r in rows:
        files = TICK.findall(r.get("files", ""))
        named |= set(files)
        if not files:
            out.append(f"P3 task {r.get('#', '?')} names no file")
        if not r.get("check", "").strip():
            out.append(f"P3 task {r.get('#', '?')} has no check")
    front_files = set(listed(text, "files"))
    if rows and named and front_files != named:
        diff = [f"+ {f}" for f in sorted(front_files - named)] + [f"- {f}" for f in sorted(named - front_files)]
        out.append(f"P3 files in the frontmatter and the tasks differ: {', '.join(diff)}")
    out += [f"P4 {msg}" for _, msg in wave_clashes(text)]
    head = "\n".join(re.sub(r"(^|\s)#.*", "", line) for line in spec.split(text)[0])     # YAML comments go
    holes = [h for name, content in spec.sections(text).items() if name != "change log"
             for h in spec.HOLE.findall(CODE.sub("", spec.FENCE.sub("", content)))] + spec.HOLE.findall(head)
    if holes:
        out.append(f"P5 open: {', '.join(dict.fromkeys(holes))}")
    if spec_tests is not None:         # every spec test of wave 1 has a runner (IMP-03-13 FR-02); its code has none
        bare = [f for f in spec_test_files(text) if not config.spec_runner({"spec_tests": spec_tests}, f)]
        if bare:
            out.append(f"P6 no pattern in [spec_tests] for: {', '.join(bare)}")
    return out


def hold(spec_text: str, plan_text: str) -> str:
    """What the person who approves this PLAN looks at twice: `risk:` in the spec or the PLAN (a new dependency,
    a schema, a public interface, a destructive change); "" when nothing holds it. Neither effort L nor needs:
    holds a PLAN: pulse go makes needs: blocker edges (FR-06 of #114)."""
    risk = spec.front(spec_text or "").get("risk") or []
    risk = (risk if isinstance(risk, list) else [risk]) + listed(plan_text, "risk")
    return f"risk: {', '.join(dict.fromkeys(risk))}" if risk else ""


def gates(root: Path, items: list, cfg: dict, found: dict = None) -> dict:
    """{issue: the first thing it waits for} for open, unclaimed work; no entry means ready."""
    base = config.base_ref(root)
    found = plans(root, base) if found is None else found
    sha = _git(root, "rev-parse", "--verify", "-q", base).strip()
    out = {}
    for i in items:
        if i.get("type") not in state.WORK or i.get("assignees"):
            continue
        n = i["number"]
        if i.get("hold"):                      # a person set pulse:hold: go plans and builds nothing of it (#111)
            out[n] = "on hold (pulse:hold)"
            continue
        if i.get("failed"):                    # pulse go gave up on it: no run takes it again (#114)
            out[n] = f"failed (pulse:failed): pulse approve {n} lets it try again"
            continue
        if not i.get("approved"):
            out[n] = "not approved"
            continue
        key = (sha, i.get("spec"))
        if key not in _specs:          # the text, and the blob a Plan-ok binds (#115)
            _specs[key] = (spec.on_base(root, i["spec"], sha or base),
                           _git(root, "rev-parse", f"{sha or base}:{i['spec']}").strip()) if i.get("spec") else (None, "")
        spec_text, spec_blob = _specs[key]
        if i.get("spec") and spec_text is None:     # pulse go merges its docs PR first, else it plans nothing (#115)
            branch = base.removeprefix("origin/")
            pr, why = spec_pr(i, branch) if any(p["base"] == branch for p in i.get("spec_prs") or ()) else (None, "")
            out[n] = (f"spec in PR #{pr['number']}: pulse go merges it" if approved_at(i, pr["head"]) else
                      f"{MOVED}: pulse approve {n} again") if pr else \
                f"spec not on {branch}" + (f": {why}" if why else "")
            continue
        wrong = spec.findings(spec_text, i["type"], n)
        if wrong:
            out[n] = f"spec: {wrong[0]}"
            continue
        p = found.get(n)
        if not p:
            out[n] = "needs a plan"
            continue
        old = (i.get("plan_ok") or [None, ""])[1] is None and p.get("blob")     # a line from before #115
        gate = plan_gate(p["text"], spec_text, cfg, plan_ok(i, p.get("blob", ""), spec_blob,
                                                           _git(root, "cat-file", "blob", p["blob"]) if old else ""))
        if gate:
            out[n] = gate
    return out


def digest(text: str) -> str:
    """What a PLAN approval bound to before #115: this text, and no later rewrite of it."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def plan_ok(item: dict, plan_blob: str, spec_blob: str, pushed: str = "") -> str:
    """"" when a person approved this PLAN at gate 2 (#115): the Plan-ok line of item names the blobs of the PLAN and
    of the spec as origin has them, and a comment `plan ok at` with the same blobs comes from an owner, member, or
    collaborator (pulse go asks GitHub whether that one may push). An old line of 12 characters counts, with its
    label, for the PLAN whose text (pushed, as origin has it) it digests. Else why the PLAN waits for a person."""
    ok = item.get("plan_ok")
    if not ok:
        return "plan waits for you"
    if ok[1] is None:
        return "" if pushed and ok[0] == digest(pushed) else "plan changed since plan ok"
    if ok[0] != plan_blob:
        return "plan changed since plan ok"
    if ok[1] != spec_blob:
        return "spec changed since plan ok"
    said = any(c["blobs"] == ok and c.get("authorAssociation") in state.WRITERS for c in item.get("plan_oks") or ())
    return "" if said else "plan waits for you"


def plan_gate(plan_text: str, spec_text, cfg: dict, waits: str = "plan waits for you"):
    """Why a PLAN keeps its item from being built, or None when it may be built: a P finding (P6 against the
    [spec_tests] of cfg), else plan_ok()'s answer (waits, "" when a person approved this PLAN) with what holds it for
    a closer look."""
    wrong = plan_findings(plan_text, spec_text, cfg.get("spec_tests"))
    if wrong:
        return f"plan: {wrong[0]}"
    why = hold(spec_text, plan_text)
    return waits + (f" ({why})" if why else "") if waits else None


def waiting(root: Path, item: dict) -> tuple:
    """(gate, blobs, "") of the approval item waits for, which pulse approve and the map's a write (#115): 0 when
    pulse go gave up on it (pulse:failed goes), 1 before its approval (blobs: the head of the docs PR that carries its
    spec and the spec path, while it lies in one; again once that PR moved, M-1), 2 when its PLAN, pushed, passes P1 to
    P5 on the spec of the base and no Plan-ok names both: blobs are then theirs, as origin has them; 3 when its PR is
    open and ready and no merge ok names its head: blobs is then (the head,) (#118). (None, (), why) when
    nothing waits for a person, why in a person's words. A spec on the base is held to R1 to R6 there; one in an
    open PR, pulse go checks before it merges it."""
    n, path = item["number"], item.get("spec")
    no = f"#{n} not approved: "
    if item.get("draft") or not path:
        return None, (), no + ("its spec is still being written" if item.get("draft") else "it has no spec")
    if item.get("hold"):
        return None, (), no + "on hold (pulse:hold)"
    if item.get("failed"):
        return 0, (), ""
    base = config.base_ref(root)
    text, branch = spec.on_base(root, path, base), base.removeprefix("origin/")
    pr, gone = spec_pr(item, branch) if text is None and any(p["base"] == branch for p in item.get("spec_prs") or ()) \
        else (None, "")
    if pr and not (item.get("approved") and approved_at(item, pr["head"])):
        return 1, (pr["head"], path), ""        # at the head pulse go merges; again once the PR moved (M-1)
    if not item.get("approved"):
        why = spec.refusal(text, item.get("type"), n, base) if text is not None else gone or \
            f"R1 spec not on {base} and in no open pull request; /pulse-re pushes it"
        return (None, (), no + why) if why else (1, (), "")
    pr = item.get("pr") or {}
    if pr.get("head") and not pr.get("draft") and not pr.get("fork"):       # gate 3: the head of its ready PR (#118)
        return (None, (), f"#{n} is approved already, its merge too: pulse go merges it") \
            if pr["head"] in [m["sha"] for m in item.get("merge_oks") or ()     # a writer's, as at gates 1 and 2 (L-1)
                              if m.get("authorAssociation") in state.WRITERS] else (3, (pr["head"],), "")
    p = plans(root, base).get(n)
    if not p:
        return None, (), f"#{n} is approved already; pulse go writes its PLAN"
    if not p["blob"]:
        return None, (), no + f"its PLAN {p['path']} is not on origin: push it"
    wrong = plan_findings(_git(root, "cat-file", "blob", p["blob"]), text, config.load(root).get("spec_tests"))
    if wrong:
        return None, (), no + f"plan: {wrong[0]}"
    blobs = (p["blob"], _git(root, "rev-parse", f"{base}:{path}").strip())
    return (None, (), f"#{n} is approved already, its PLAN too") if item.get("plan_ok") == list(blobs) else \
        (2, blobs, "")


def approved_at(item: dict, head: str) -> bool:
    """Whether an owner, member, or collaborator approved gate 1 of item at this head of its docs PR, for the spec
    path its Spec: line names (M-1); pulse go asks GitHub whether that one may push."""
    return any(c["head"] == head and c["path"] == item.get("spec") and c.get("authorAssociation") in state.WRITERS
               for c in item.get("gate1_oks") or ())


def spec_pr(item: dict, branch: str) -> tuple:
    """(the one open PR into branch that carries the item's spec and changes only _devprocess/, "")
    or (None, why not): the docs PR pulse go merges at gate 1 while the spec is not on branch yet (#69, #115);
    ask only when one carries it."""
    prs = [p for p in item.get("spec_prs") or () if p["base"] == branch]
    if len(prs) > 1:
        return None, f"open pull requests {', '.join('#%d' % p['number'] for p in prs)} carry it: close all but one"
    if not prs[0]["docs"]:
        return None, (f"PR #{prs[0]['number']} that carries it changes more than _devprocess/, or more files than "
                      "gh lists: pulse go merges only a docs pull request")
    return prs[0], ""


printable = config.printable                # one definition, in config, which cannot import this module


def _shown(paths: list) -> str:
    """Paths a PR chose, fit for a terminal, three at most."""
    return ", ".join(map(printable, paths[:3])) + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")


def _fetch_base(root: Path, branch: str) -> bool:
    """origin's branch into refs/remotes/origin/<branch> whatever the clone's refspec says (a clone of
    one other branch fetched into FETCH_HEAD alone); True when origin answered."""
    return not net_git(root, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}").returncode


def unpushed(root: Path, n: int, base: str) -> list:
    """(branch, commits) for each branch of item n in this clone, its docs branch too, with commits
    origin lacks: against origin/<branch>, else against the base branch on origin. Only this clone
    has them; the team sees no work there, and whoever takes n over starts without it (#79)."""
    out, cfg = [], config.load(root)
    for ref in _git(root, "for-each-ref", "--format=%(refname)", "refs/heads").split():
        b = ref.removeprefix("refs/heads/")
        if state.item_of(b) != n and not config.is_spec_branch(cfg, b, n):
            continue
        since = _tip(root, f"refs/remotes/origin/{b}") or _tip(root, f"refs/remotes/origin/{base}")
        count = _git(root, "rev-list", "--count", f"{since}..{ref}").strip() if since else ""
        if count.isdigit() and int(count):
            out.append((b, int(count)))
    return out


def _tip(root: Path, ref: str) -> str:
    """The commit of exactly this full ref, or "": git's own lookup would fall through to a tag named like
    it, refs/tags/refs/remotes/origin/main say, that anyone with push access can place (#69 final check)."""
    return _git(root, "show-ref", "--verify", "-s", ref).strip()


_merges: dict = {}                   # (root, base commit, head commit) -> what their merge writes


def merge_of(root: Path, real: str, head: str) -> tuple:
    """(tree, [(path, ":old new sha sha status")]) of the merge of head into real as git's merge-ort makes it,
    each path as `git diff --raw` names it from real, renames split, submodules shown whatever the config;
    (None, []) when it does not merge cleanly (or git is older than 2.38). Once per pair of commits: their
    history never changes (#88 gate round 1)."""
    key = (str(root), real, head)
    if key not in _merges:
        merged = subprocess.run(["git", "-C", str(root), "merge-tree", "--write-tree", real, head],
                                capture_output=True, text=True)
        tree = merged.stdout.split("\n", 1)[0].strip()
        if merged.returncode or not re.fullmatch(r"[0-9a-f]{40,64}", tree):
            tree, changed = None, []
        else:
            raw = _git(root, "diff", "--raw", "-z", "--no-renames", "--no-abbrev", "--ignore-submodules=none",
                       real, tree).split("\0")
            changed = list(zip(raw[1::2], raw[0::2]))
        if len(_merges) > 1024:
            _merges.clear()
        _merges[key] = (tree, changed)
    return _merges[key]


def _merge_check(root: Path, real: str, head: str, path: str, branch: str, pr: int) -> tuple:
    """([(status, path)], "") when the merge of head, docs PR #pr, into real, the base branch freshly fetched,
    changes only plain files under _devprocess/, path among them; status A, M, D, or T as git names it from real.
    Else ([], why). It judges what the merge writes, as GitHub's merge-ort makes it: a criss-cross history, a
    file the base moved out of _devprocess/ (audit H-1 of #69, round 2 M-1), renames split, submodules shown
    whatever the config (M-2)."""
    tree, changed = merge_of(root, real, head)
    outside = [c for c, _ in changed if not c.startswith("_devprocess/")]
    odd = [c for c, m in changed if {m[1:7], m[8:14]} & {"120000", "160000"}]     # a link, a submodule (M-2)
    if not tree:
        return [], f"PR #{pr} does not merge cleanly into {branch} here (or git is older than 2.38); nothing merged"
    if outside:
        return [], f"PR #{pr} changes {_shown(outside)} outside _devprocess/: pulse go merges only a docs pull request"
    if odd:
        return [], f"PR #{pr} adds a link or a submodule under _devprocess/: {_shown(odd)}; pulse go merges only files"
    if path not in dict(changed):
        return [], f"PR #{pr} does not carry the spec"
    return [(m.split()[-1], c) for c, m in changed], ""


# --- the ramp ---------------------------------------------------------------------------------------

def plan_files(root: Path, found: dict = None) -> dict:
    """{issue number: [files]} from the frontmatter of every PLAN, each spelled one way (`./a.py`
    is `a.py`, `docs/` is `docs`)."""
    return {n: [posixpath.normpath(f) for f in listed(p["text"], "files")]
            for n, p in (plans(root) if found is None else found).items()}


def order(items: list) -> list:
    """The one order of pulse go and the ramp (#119): no item before an open blocker (Kahn over blocked_by), else by
    effective priority, the best of the item and all it unblocks, then by number. Items in a cycle come last."""
    by = {i["number"]: i for i in items}
    after = {n: [] for n in by}                # n -> the items that wait for n
    for i in items:
        for b in i.get("blocked_by") or ():
            if b in by:
                after[b].append(i["number"])
    best: dict = {}

    def eff(n, seen=()):
        if n not in best:
            best[n] = min([by[n].get("priority", 3)] + [eff(m, seen + (n,)) for m in after[n] if m not in seen])
        return best[n]
    waits = {n: sum(b in by for b in by[n].get("blocked_by") or ()) for n in by}
    heap = [(eff(n), n) for n in by if not waits[n]]
    heapq.heapify(heap)
    out = []
    while heap:
        _, n = heapq.heappop(heap)
        out.append(by[n])
        for m in after[n]:
            waits[m] -= 1
            if not waits[m]:
                heapq.heappush(heap, (eff(m), m))
    return out + sorted((i for i in items if waits[i["number"]]), key=lambda i: (eff(i["number"]), i["number"]))


def _row(i: dict) -> bool:
    """A ramp row: a work item or a draft of any kind, epics too, that nobody holds (D-43). A held
    draft is in progress and stands under its holder only (#55)."""
    return not i["assignees"] and (bool(i.get("draft")) or i["type"] in state.WORK)


def view(root: Path, items: list, cfg: dict, me: str, cap: int = None) -> dict:
    """The ramp as a person sees it: gates and PLANs on item branches. A claim changes no PLAN,
    so claimed items get their gate too (plan_waits)."""
    found = plans(root)
    return ramp(items, plan_files(root, found), cap or cfg["cap"], me,
                gates=gates(root, [dict(i, assignees=[]) for i in items], cfg, found))


def held(items: list, files: dict) -> dict:
    """{file: item} of the running items: the files of their PLANs here and the files their claims
    name, which hold even where a PLAN is unpushed or there is none."""
    return {f: i["number"] for i in items if i["type"] in state.WORK and i["assignees"] and not i.get("draft")
            for f in files.get(i["number"], []) + (i.get("claimed_files") or [])}


def clash(mine: list, held: dict):
    """(file, holder) for the first of mine another item holds, else None. A held directory holds
    what is in it."""
    return next(((f, n) for f in mine for h, n in held.items()
                 if f == h or f.startswith(h + "/") or h.startswith(f + "/")), None)


def ramp(items: list, files: dict, cap: int, me: str, gates=None) -> dict:
    """gates: {issue: why it waits} from gates(); a gated item never goes out. A draft nobody
    holds (its spec is to be written, D-43) is a row, never goes out, and takes no bay."""
    running = [i for i in items if i["type"] in state.WORK and i["assignees"] and not i.get("draft")]
    taken = held(items, files)
    busy = [i for i in running if me in i["assignees"] and not i.get("pr")]   # in review: no slot
    free = max(0, cap - len(busy))
    pos = {i["number"]: k for k, i in enumerate(order(items))}
    gates = gates or {}
    pool = sorted((i for i in items if i["type"] in state.WORK and i["approved"] and not i["assignees"] and
                   not i["blocked_by"] and i["number"] not in gates and not i.get("draft")), key=lambda i: pos[i["number"]])
    nxt, wait, locked = [], [], []
    for i in pool:
        mine = files.get(i["number"], [])
        hit = clash(mine, taken)
        if hit:
            locked.append({**i, "file": hit[0], "holder": hit[1]})
        elif len(nxt) < free:
            nxt.append(i)
            taken.update({f: i["number"] for f in mine})
        else:
            wait.append(i)
    pooled = {i["number"] for i in pool}
    stage = {i["number"]: "starts next" for i in nxt}
    stage.update({i["number"]: "queued" for i in wait})
    stage.update({i["number"]: f"locked: {Path(i['file']).name} in use by #{i['holder']}" for i in locked})
    rows = []
    for i in order(items):
        if not _row(i):
            continue
        n = i["number"]
        s = ("spec in progress" if i.get("draft") else None) or \
            stage.get(n) or gates.get(n) or ("not approved" if not i["approved"] else None) or \
            ("waits for " + ", ".join(f"#{b}" for b in i["blocked_by"]) if i["blocked_by"] else "ready")
        rows.append({**i, "stage": s})
    return {"cap": cap, "free": free, "busy": busy, "next": nxt, "wait": wait, "locked": locked, "rows": rows,
            "plan_waits": [i["number"] for i in running if gates.get(i["number"], "").startswith(WAITS)],
            "after": [i for i in state.blocked(items) if i["type"] in state.WORK and i["number"] not in pooled]}
