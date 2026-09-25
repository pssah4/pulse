"""Readiness: which items may be planned, which may be built, and why the others wait.

An item is ready when a person approved it, its spec passes R1 to R6
(pulse/spec.py), it has a PLAN that passes P1 to P5, the PLAN is approved,
and no blocker is open. The PLAN approval is computed: `plan_approval =
"auto"` approves every PLAN that nothing holds (a risk flag in the spec,
`needs:` in the PLAN); `manual`, or a hold, waits for `pulse approve-plan`.

PLANs live in the working tree (interactive /pulse-plan) or on the pushed
item branch (planning runs of pulse go); fetch() brings the item branches
of every clone. The rules read text only; plans() and gates() read git.
"""
from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from pulse import config, spec, state

FETCH_EVERY = 30                     # seconds between two fetches of one clone, whoever asks
GIT_TIMEOUT = 60                     # seconds for git over the network, as for gh
NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""}   # a password prompt fails at once
PLANS = "_devprocess/plans"
IDS = re.compile(r"\b(?:FR|SC)-\d+\b")
TICK = re.compile(r"`([^`\s]+)`")
CODE = re.compile(r"`[^`\n]*`")         # inline code: braces there are code, not a placeholder
REF = re.compile(r"#(\d+)(?=[\s,:;]|$)")  # a needs: entry that names an item first
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


def fetch(root: Path):
    """Every branch on origin, and none it dropped, so this clone sees what the others planned
    and hold (D-10); at most every FETCH_EVERY seconds per clone. True when origin answered, at
    this fetch or the last one; False offline or without origin; None without a place to note
    the fetch (a read-only .git), where no fetch runs. Silent, and nothing waits long."""
    stamp = config.pulse_dir(root) / "fetched"
    try:
        if time.time() - stamp.stat().st_mtime < FETCH_EVERY:
            return stamp.read_text(encoding="utf-8") != "offline"
    except OSError:
        pass
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:
        return None            # no fetch rather than one per call
    answered = net_git(root, "fetch", "-q", "--prune", "origin").returncode == 0
    try:
        stamp.write_text("" if answered else "offline", encoding="utf-8")
    except OSError:
        pass
    return answered


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
    return [x for x in out + (inline if isinstance(inline, list) else []) if x]


def _issue(text: str):
    n = str(spec.front(text).get("issue", "")).lstrip("#")
    return int(n) if n.isdigit() else None


def _branch_plan(root: Path, base: str, ref: str, n: int):
    for path in _git(root, "diff", "--name-only", "--diff-filter=AM", f"{base}...{ref}", "--", PLANS).split():
        text = _git(root, "show", f"{ref}:{path}")
        if _issue(text) == n:
            return {"path": path, "ref": ref, "text": text}
    return None


def plans(root: Path, base: str = None) -> dict:
    """{issue: {"path", "ref", "text"}}: pushed item branches, then the working tree, which wins
    unless the item's branch on origin moved past it: the copy here is committed as it is, and
    that branch holds this commit and a different PLAN."""
    base = base or config.base_ref(root)
    out = {}
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
    for path in sorted((root / PLANS).glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        n, rel = _issue(text), path.relative_to(root).as_posix()
        p = out.get(n)
        behind = p and p["ref"] and p["text"] != text and not _git(root, "status", "--porcelain", "--", rel) \
            and _git(root, "rev-list", "--count", f"{p['ref']}..HEAD").strip() == "0"
        if n and not behind:   # behind: a teammate pushed a newer PLAN on the item's branch
            out[n] = {"path": rel, "ref": None, "text": text}
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


def plan_findings(text: str, spec_text) -> list:
    """['P2 not covered: SC-01', ...]; [] means an agent can build from this PLAN."""
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
    return out


def hold(spec_text: str, plan_text: str, blockers=(), open_=None) -> str:
    """Why a person has to approve this PLAN even at plan_approval = auto; "" when nothing holds it.
    A needs: entry that names an item (#n) holds only while that item is open (open_: the open
    issues, None when unknown) and no blocker of this one: the board waits for a blocker already,
    and a closed item is done."""
    fm = spec.front(spec_text or "")
    risk = fm.get("risk") or []
    risk = risk if isinstance(risk, list) else [risk]
    refs = [(x, int(m.group(1)) if m else None) for x in listed(plan_text, "needs") for m in [REF.match(x)]]
    needs = [x for x, n in refs if n is None or n not in blockers and (open_ is None or n in open_)]
    return "; ".join(filter(None, [f"risk: {', '.join(risk)}" if risk else "",
                                   f"needs {', '.join(needs)}" if needs else "",
                                   "effort L" if fm.get("effort") == "L" else ""]))


def gates(root: Path, items: list, cfg: dict, found: dict = None) -> dict:
    """{issue: the first thing it waits for} for open, unclaimed work; no entry means ready."""
    base = config.base_ref(root)
    found = plans(root, base) if found is None else found
    sha = _git(root, "rev-parse", "--verify", "-q", base).strip()
    open_ = {i["number"] for i in items}
    out = {}
    for i in items:
        if i.get("type") not in state.WORK or i.get("assignees"):
            continue
        n = i["number"]
        if not i.get("approved"):
            out[n] = "not approved"
            continue
        key = (sha, i.get("spec"))
        if key not in _specs:
            _specs[key] = spec.on_base(root, i["spec"], sha or base) if i.get("spec") else None
        spec_text = _specs[key]
        wrong = spec.findings(spec_text, i["type"], n)
        if wrong:
            out[n] = f"spec: {wrong[0]}"
            continue
        p = found.get(n)
        if not p:
            out[n] = "needs a plan"
            continue
        gate = plan_gate(p["text"], spec_text, cfg, i.get("plan_ok"), i.get("blocked_by") or (), open_)
        if gate:
            out[n] = gate
    return out


def digest(text: str) -> str:
    """What a PLAN approval binds to: this text, and no later rewrite of it."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def plan_gate(plan_text: str, spec_text, cfg: dict, plan_ok: str = None, blockers=(), open_=None):
    """Why a PLAN keeps its item from being built, or None when it may be built.
    plan_ok: the digest of the PLAN a person approved; it counts only for that PLAN."""
    wrong = plan_findings(plan_text, spec_text)
    if wrong:
        return f"plan: {wrong[0]}"
    if plan_ok and plan_ok == digest(plan_text):
        return None
    why = hold(spec_text, plan_text, blockers, open_)
    if cfg.get("plan_approval") == "manual" or why:
        return "plan waits for you" + (f" ({why})" if why else "")
    return None


def approvable(root: Path, items: list, cfg: dict, n: int) -> tuple:
    """(digest, "") when #n's PLAN waits for a person; (None, why) for anything else."""
    found = plans(root)
    free = [dict(i, assignees=[]) if i["number"] == n else i for i in items]     # a claim changes no PLAN
    gate = gates(root, free, cfg, found).get(n, "")
    if not gate.startswith("plan waits for you"):
        return None, f"#{n}: no PLAN waiting for approval" + (f" ({gate})" if gate else "")
    return digest(found[n]["text"]), ""
