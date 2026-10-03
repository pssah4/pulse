"""Readiness: which items may be planned, which may be built, and why the others wait.

An item advances after its published spec passes R1 to R6 and its PLAN
passes P1 to P6. Publication uses the same item branch throughout. Only
the verified result needs a person's approval, bound to its head and base.

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
NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "",
             "SSH_ASKPASS_REQUIRE": "never", "GCM_INTERACTIVE": "0"}   # no inherited GUI/TTY auth prompt
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
_memo: dict = {}                     # immutable (common git dir, base sha, head) -> Plan blobs


def _git(root: Path, *args) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout      # one bad byte in a PLAN stops nothing


def net_git(cwd, *args, timeout=None) -> subprocess.CompletedProcess:
    """git over the network: no prompt, no terminal, stdin closed, and a time limit (GIT_TIMEOUT unless given) that
    ends git with everything it started (ssh, a remote helper, a hook). A run out of time reads as a failure."""
    timeout = timeout or GIT_TIMEOUT
    with subprocess.Popen(["git", "-C", str(cwd), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, errors="replace", env={**os.environ, **NO_PROMPT},
                          start_new_session=True) as p:
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = "", f"no answer within {timeout} s"
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
    said = git_error(got.stderr) if got.returncode else ""    # retain the helper's timeout cause too
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
    """What git or the time limit said at the last fetch, kept for every command; "" after success."""
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


def _plan_bytes(root, obj):
    got = subprocess.run(["git", "-C", str(root), "cat-file", "blob", obj], capture_output=True)
    return got.stdout if got.returncode == 0 else None


def _plan_file(root, head, path):
    entry = _git(root, "ls-tree", head, "--", path) if head else ""
    return _plan_bytes(root, f"{head}:{path}") if entry.startswith(("100644 blob ", "100755 blob ")) else None


def _plan_ref(root, ref=None):
    """Resolve only real branch refs (or an explicit commit), never a same-named tag."""
    if ref is None:
        name = config.load(root)["base_branch"] or config.default_branch(root)
        remote = "refs/remotes/origin/" + name
        ref = remote if _tip(root, remote) else "refs/heads/" + name
    if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", ref):
        return ref, ref if _git(root, "cat-file", "-t", ref).strip() == "commit" else ""
    full = ref if ref.startswith("refs/") else "refs/remotes/" + ref if ref.startswith("origin/") else \
        "refs/heads/" + ref
    return full, _tip(root, full)


def plan_sources(root: Path, base: str = None) -> dict:
    """Observe exact Plan bytes on published refs and registered worktrees of this repository.

    No fetch, staging or file copying. Index contents differing from both HEAD and disk remain
    separate sources. Superseded clean copies keep their provenance but do not create conflicts.
    """
    root = Path(root).resolve()
    base_ref, base_sha = _plan_ref(root, base)
    base = base_ref.removeprefix("refs/remotes/").removeprefix("refs/heads/")
    common, out = config.common_dir(root).resolve(), {}

    def add(data, path, **source):
        if data is None:
            return
        text = data.decode("utf-8", errors="replace")
        n = _issue(text)
        if not n:
            return
        ref, branch = source.get("ref"), source.get("branch")
        if ref and ref != base and state.item_of(branch) != n:
            if state.item_of(branch) or spec.published(root, spec.front(text).get("spec"), n,
                                                       base=base_sha or base_ref)[1] != ref:
                return
        out.setdefault(n, []).append({"path": path, "text": text,
            "content": hashlib.sha256(data).hexdigest(), "worktree": "", "ref": None,
            "blob": "", "head": "", "branch": "", "layer": "file", **source})

    refs = [(base_sha, base_ref)] + [tuple(line.split(" ", 1)) for line in _git(
        root, "for-each-ref", "--format=%(objectname) %(refname)", "refs/remotes/origin").split("\n") if line]
    for head, full in refs:
        if full in ("refs/remotes/origin/HEAD", "refs/remotes/origin/pulse-state"):
            continue
        ref = full.removeprefix("refs/remotes/").removeprefix("refs/heads/")
        if not head:
            continue
        key = (str(common), base_sha, head)
        if key not in _memo:
            paths = [PLANS + "/"] if ref == base or not base_sha else [p for p in _git(
                root, "diff", "--name-only", "--diff-filter=AM", "-z", f"{base_sha}...{head}", "--",
                PLANS + "/").split("\0") if p]
            blobs = []
            for entry in (_git(root, "ls-tree", "-z", head, "--", *paths).split("\0") if paths else []):
                meta, _, path = entry.partition("\t")
                fields = meta.split()
                if len(fields) == 3 and fields[0] in ("100644", "100755") and \
                        Path(path).parent.as_posix() == PLANS and path.endswith(".md"):
                    blobs.append((path, fields[2], _plan_bytes(root, fields[2])))
            if len(_memo) >= 512:
                _memo.clear()
            _memo[key] = blobs
        for path, blob, data in _memo[key]:
            add(data, path, ref=ref, head=head, blob=blob, layer="ref",
                branch=ref.removeprefix("refs/remotes/").removeprefix("origin/"))
    for entry in _git(root, "worktree", "list", "--porcelain", "-z").split("\0\0"):
        fields = dict(line.split(" ", 1) for line in entry.split("\0") if " " in line)
        if not fields.get("worktree"):
            continue
        tree = Path(fields["worktree"])
        try:
            if not tree.is_dir() or config.common_dir(tree).resolve() != common or \
                    Path(_git(tree, "rev-parse", "--show-toplevel").strip()).resolve() != tree.resolve():
                continue
            tree = tree.resolve()
            folder = tree / PLANS
            if folder.resolve() != folder or not folder.is_dir():
                continue
            staged = {}
            for row in _git(tree, "ls-files", "--stage", "-z", "--", PLANS + "/").split("\0"):
                meta, _, path = row.partition("\t")
                parts = meta.split()
                if len(parts) == 3 and parts[0] in ("100644", "100755") and parts[2] == "0":
                    staged[path] = parts[1]
            paths = {p.relative_to(tree).as_posix() for p in folder.glob("*.md")} | set(staged)
            for path in sorted(paths):
                target = tree / path
                if Path(path).parent.as_posix() != PLANS or not path.endswith(".md") or target.is_symlink():
                    continue
                data = target.read_bytes() if target.is_file() else None
                source = {"worktree": str(tree), "branch": fields.get("branch", "").removeprefix("refs/heads/"),
                          "head": fields.get("HEAD", "")}
                add(data, path, **source)
                index = staged.get(path)
                committed = _git(tree, "rev-parse", "--verify", "-q", f"HEAD:{path}").strip()
                if index and index != committed:
                    cached = _plan_bytes(tree, index)
                    if cached != data:
                        add(cached, path, **source, layer="index", blob=index)
        except (OSError, ValueError, state.StateError):
            continue
    for rows in out.values():
        published = [source for source in rows if source["ref"]]
        for source in rows:
            for newer in published:
                if source["path"] != newer["path"] or source["content"] == newer["content"]:
                    continue
                head = source["head"]
                ancestor = _git(root, "merge-base", head, newer["head"]).strip() if head else ""
                old = _plan_bytes(root, f"{ancestor}:{source['path']}") if ancestor else None
                unchanged = old is not None and hashlib.sha256(old).hexdigest() == source["content"]
                if unchanged and (source["ref"] and ancestor == head or source["worktree"] and
                                  not _git(Path(source["worktree"]), "status", "--porcelain", "--", source["path"])):
                    source["superseded"] = True
                    break
    return out


def _plan_choice(root, rows, selection=None):
    active = [source for source in rows if not source.get("superseded")]
    variants = [{"content": content, "sources": [s for s in active if s["content"] == content]}
                for content in sorted({s["content"] for s in active})]
    selected = None
    if selection is not None:
        bound = isinstance(selection, dict) and all(selection.get(k) for k in ("path", "content")) and \
                (selection.get("worktree") or selection.get("ref"))
        selected = next((s for s in active if bound and all(s.get(k) == v for k, v in selection.items())), None)
    elif len(variants) == 1:
        selected = min(active, key=lambda s: (s["worktree"] != str(Path(root).resolve()),
                                              not bool(s["worktree"]), s["layer"] != "file",
                                              s["worktree"], s["ref"] or "", s["path"]))
    return variants, selected


def plans(root: Path, base: str = None, sources: dict = None) -> dict:
    """Compatibility projection of unambiguous Plan contents. Conflicts select no version."""
    sources = plan_sources(root, base) if sources is None else sources
    out = {}
    for n, rows in sources.items():
        _, selected = _plan_choice(root, rows)
        if selected:
            published = next((s for s in rows if s["ref"] and not s.get("superseded") and
                              s["path"] == selected["path"] and s["content"] == selected["content"]), {})
            out[n] = {"path": selected["path"], "ref": selected["ref"], "text": selected["text"],
                      "blob": published.get("blob", "")}
            if selected["worktree"] and selected["worktree"] != str(Path(root).resolve()):
                out[n]["worktree"] = selected["worktree"]
    return out


def plan_state(root: Path, item: dict, cfg: dict, sources: dict = None, selection: dict = None) -> dict:
    """Existence, validation, commit and exact publication, read independently without granting approval."""
    base, base_sha = _plan_ref(root)
    rows = (plan_sources(root, base) if sources is None else sources).get(item["number"], [])
    variants, chosen = _plan_choice(root, rows, selection)
    out = {"exists": bool(rows), "variants": variants, "conflict": len(variants) > 1 and chosen is None,
           "selected": chosen, "validation": {"findings": [], "checked_against": {}},
           "commit": {"matches": False, "head": ""},
           "publication": {"matches": False, "ref": None, "head": "", "blob": ""}, "ready": False, "why": ""}
    if chosen is None:
        out["why"] = "plan selection changed or is unavailable" if selection is not None else \
            "plan versions differ; choose the preserved content" if variants else "needs a plan"
        return out
    branch = item.get("branch") or (item.get("work") or {}).get("branch") or \
        ((item.get("lifecycle") or {}).get("work") or {}).get("branch")
    # A retained checkout may reuse exact artifact bytes already published on the base.
    if branch and not item.get("branch") and not _tip(root, f"refs/remotes/origin/{branch}"):
        branch = None
    _, ref, why = spec.published(root, item.get("spec"), item["number"], branch=branch, base=base_sha or base)
    spec_sha = _plan_ref(root, ref)[1] if ref else ""
    text = spec.on_base(root, item["spec"], spec_sha) if spec_sha and item.get("spec") else None
    base_text = spec.on_base(root, item.get("spec"), base_sha) if base_sha and item.get("spec") else None
    if base_text is not None and spec_sha != base_sha:
        ancestor = _git(root, "merge-base", base_sha, spec_sha).strip() if spec_sha else ""
        original = spec.on_base(root, item["spec"], ancestor) if ancestor else None
        if (text is None and branch and not _tip(root, f"refs/remotes/origin/{branch}")) or \
                (text is not None and text == original):
            text, spec_sha, why = base_text, base_sha, ""
        elif text is not None and base_text not in (original, text):
            why = "spec versions differ between the item and current base"
    base_ref = base.removeprefix("refs/remotes/").removeprefix("refs/heads/")
    published_ref = base_ref if ref == base_sha else ref
    findings = plan_findings(chosen["text"], text, cfg.get("spec_tests"))
    planned_spec = str(spec.front(chosen["text"]).get("spec") or "")
    if item.get("spec") and posixpath.normpath(planned_spec) != posixpath.normpath(item["spec"]):
        findings.append("P1 spec does not match the item's current spec")
    if why:
        findings.append("P2 " + why)
    out["validation"] = {"findings": findings, "checked_against": {
        "base": base_sha,
        "spec": _git(root, "rev-parse", "--verify", "-q", f"{spec_sha}:{item.get('spec')}").strip() if spec_sha else ""}}
    data = _plan_file(root, chosen["head"], chosen["path"])
    out["commit"] = {"matches": data is not None and hashlib.sha256(data).hexdigest() == chosen["content"],
                     "head": chosen["head"]}
    expected_refs = [f"origin/{branch}"] if item.get("branch") else list(dict.fromkeys(
        [f"origin/{branch}" if branch else None, published_ref, base_ref]))
    for expected in expected_refs:
        if not expected or not expected.startswith(("origin/", "refs/remotes/origin/")):
            continue
        full = "refs/remotes/" + expected if expected.startswith("origin/") else expected
        head = _tip(root, full)
        there = _plan_file(root, head, chosen["path"])
        if there is not None and hashlib.sha256(there).hexdigest() == chosen["content"]:
            out["publication"] = {"matches": True, "ref": expected, "head": head,
                "blob": _git(root, "rev-parse", "--verify", "-q", f"{head}:{chosen['path']}").strip()}
            break
    out["ready"] = not findings and out["publication"]["matches"]
    out["why"] = "plan: " + findings[0] if findings else "" if out["ready"] else "plan publication pending"
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


def plan_validation(root: Path, text: str, spec_path: str = None) -> list:
    """Offline structural validation against the published item spec and trusted base test runners."""
    base, sha = _plan_ref(root)
    path = spec_path or spec.front(text).get("spec")
    _, ref, why = spec.published(root, path, _issue(text), base=sha or base)
    spec_sha = _plan_ref(root, ref)[1] if ref else ""
    given = spec.on_base(root, path, spec_sha) if spec_sha else None
    wrong = plan_findings(text, given, config.load(root, sha).get("spec_tests") or {})
    return wrong + ([f"P2 {why}"] if why and given is None and "multiple" in why else [])


def repairable(item: dict, gate: str) -> bool:
    """An unclaimed structural PLAN error may be repaired automatically. Explicit holds and failed
    work retain their state; legacy approval records do not create a new permission requirement."""
    return bool(gate.startswith("plan: ") and
                not any(item.get(k) for k in ("hold", "failed", "draft", "assignees", "claimed_holder", "result")) and
                (not item.get("lifecycle") or item["lifecycle"].get("phase") == "resumed"))


def hold(spec_text: str, plan_text: str) -> str:
    """Risk categories to show when the result is reviewed; these do not add a PLAN approval gate."""
    risk = spec.front(spec_text or "").get("risk") or []
    risk = (risk if isinstance(risk, list) else [risk]) + listed(plan_text, "risk")
    return f"risk: {', '.join(dict.fromkeys(risk))}" if risk else ""


def document_candidates(root: Path, items: list, selected) -> list:
    """Published leaf epics can finish as documents. Container epics finish through their children."""
    parents = {item.get("parent") for item in items}
    out = []
    for item in items:
        if item.get("type") != "epic" or item["number"] not in selected or item["number"] in parents or \
                any(item.get(key) for key in ("draft", "done", "result", "hold", "failed", "assignees", "claimed_holder")):
            continue
        text, _, why = spec.published(root, item.get("spec"), item["number"], branch=item.get("branch"))
        base_text = spec.on_base(root, item["spec"]) if item.get("spec") else None
        if not why and not spec.items(text or "") and not spec.items(base_text or ""):
            out.append(item)
    return out


def spec_candidates(root: Path, items: list, selected=None, ancestors=None) -> list:
    """Unclaimed drafts with published ancestor specs. Keep the full board for hierarchy checks."""
    by = {**(ancestors or {}), **{i["number"]: i for i in items}}
    out = []
    for item in items:
        if not item.get("draft") or item.get("type") not in (*state.WORK, "epic") or \
                selected is not None and item["number"] not in selected or \
                any(item.get(k) for k in ("hold", "failed", "assignees", "claimed_holder")):
            continue
        parents, number, seen = [], item.get("parent"), {item["number"]}
        while number and number not in seen:
            seen.add(number)
            parent = by.get(number)
            if not parent or not parent.get("spec") or spec.published(root, parent["spec"], number,
                                                                      branch=parent.get("branch"))[2]:
                break
            parents.append(parent)
            number = parent.get("parent")
        else:
            if not number:
                out.append(dict(item, parents=parents))
    return out


def gates(root: Path, items: list, cfg: dict, found: dict = None, sources: dict = None) -> dict:
    """{issue: the first unmet prerequisite}; spec and PLAN validation need no human approval."""
    base, base_sha = _plan_ref(root)
    sources = plan_sources(root, base) if sources is None else sources
    found = plans(root, base, sources) if found is None else found
    out = {}
    for i in items:
        if i.get("type") not in state.WORK or i.get("assignees"):
            continue
        n = i["number"]
        if i.get("hold"):
            out[n] = "on hold (pulse:hold)"
        elif i.get("failed"):
            out[n] = "failed (pulse:failed): inspect the preserved work before resuming"
        elif i.get("draft"):
            out[n] = "spec in progress"
        elif i.get("result"):
            why = result_reason(root, i)
            approval, result = i.get("approval") or {}, i["result"]
            approved = not why and (approval.get("proof") or approval.get("policy")) and \
                all(approval.get(k) == result[k] for k in ("head", "base"))
            out[n] = f"result: {why}" if why else ("integration approved" if approved else
                                                  "integration waits for approval")
        else:
            branch = i.get("branch") or (i.get("work") or {}).get("branch") or \
                ((i.get("lifecycle") or {}).get("work") or {}).get("branch")
            if branch and not i.get("branch") and not _tip(root, f"refs/remotes/origin/{branch}"):
                branch = None
            _, ref, why = spec.published(root, i.get("spec"), n, branch=branch, base=base_sha or base)
            spec_sha = _plan_ref(root, ref)[1] if ref else ""
            text = spec.on_base(root, i["spec"], spec_sha) if spec_sha and i.get("spec") else None
            wrong = spec.findings(text, i["type"], n)
            if why or wrong:
                out[n] = f"spec: {why or wrong[0]}"
                continue
            p = found.get(n)
            gate = plan_gate(p["text"], text, cfg) if p else None
            if gate:
                out[n] = gate
                continue
            status = plan_state(root, i, cfg, sources)
            if status["why"]:
                out[n] = status["why"]
    return out


def digest(text: str) -> str:
    """What a PLAN approval bound to before #115: this text, and no later rewrite of it."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def plan_gate(plan_text: str, spec_text, cfg: dict, waits: str = ""):
    """The first structural finding, or None. The legacy waits argument grants or blocks nothing."""
    wrong = plan_findings(plan_text, spec_text, cfg.get("spec_tests"))
    return f"plan: {wrong[0]}" if wrong else None


def result_reason(root: Path, item: dict) -> str:
    """Why a cached published result cannot yet be offered for approval. This reads fetched refs only;
    the integration path checks the real remote and authenticated approval again before publishing."""
    result = item.get("result") or {}
    head, starting, branch = (result.get(k) for k in ("head", "base", "branch"))
    if not all(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", sha)
               for sha in (head, starting)) or not isinstance(branch, str) or state.item_of(branch) != item["number"]:
        return "no published result"
    gates = result.get("gates") or {}
    if not isinstance(gates, dict) or any(gates.get(g) != "pass" for g in ("tests", "review", "audit")) or \
            any(v != "pass" for v in gates.values()):
        return "result checks have not all passed"
    remote = f"refs/remotes/origin/{branch}"
    if _git(root, "rev-parse", "--verify", "-q", f"{remote}^{{commit}}").strip() != head:
        return "result is not the published item branch head"
    base_branch = config.load(root).get("base_branch") or config.default_branch(root)
    tip = _git(root, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{base_branch}^{{commit}}").strip()
    if tip != starting:
        return "base changed since result verification"
    return ""


def waiting(root: Path, item: dict) -> tuple:
    """Only the final integration approval: (3, (head, base), ""), otherwise (None, (), why).
    Old spec, PLAN and PR approvals confer no authority on a result."""
    n = item["number"]
    reason = ("on hold (pulse:hold)" if item.get("hold") else
              "failed work needs inspection and resume" if item.get("failed") else
              "its spec is still being written" if item.get("draft") else
              "its spec is missing" if not item.get("spec") else result_reason(root, item))
    if reason:
        return None, (), f"#{n}: {reason}"
    result, approval = item["result"], item.get("approval") or {}
    binding = (result["head"], result["base"])
    if (approval.get("proof") or approval.get("policy")) and (approval.get("head"), approval.get("base")) == binding:
        return None, (), f"#{n}: this result and base already have an integration approval"
    return 3, binding, ""


printable = config.printable                # one definition, in config, which cannot import this module


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


# --- the ramp ---------------------------------------------------------------------------------------

def plan_files(root: Path, found: dict = None) -> dict:
    """{issue number: [files]} from the frontmatter of every PLAN, each spelled one way (`./a.py`
    is `a.py`, `docs/` is `docs`)."""
    return {n: [posixpath.normpath(f) for f in listed(p["text"], "files")]
            for n, p in (plans(root) if found is None else found).items()}


def order(items: list) -> list:
    """The one order of pulse go and the ramp (#119): no item before an open blocker (Kahn over blocked_by), else by
    manual position, effective priority (the best of the item and all it unblocks), then by number.
    Items without a manual position follow positioned items. Items in a cycle come last."""
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
    def position(number):
        value = by[number].get("manual_position")
        return value if type(value) is int and value >= 0 else float("inf")

    heap = [(position(n), eff(n), n) for n in by if not waits[n]]
    heapq.heapify(heap)
    out = []
    while heap:
        _, _, n = heapq.heappop(heap)
        out.append(by[n])
        for m in after[n]:
            waits[m] -= 1
            if not waits[m]:
                heapq.heappush(heap, (position(m), eff(m), m))
    return out + sorted((i for i in items if waits[i["number"]]),
                        key=lambda i: (position(i["number"]), eff(i["number"]), i["number"]))


def _row(i: dict) -> bool:
    """A ramp row: a work item or a draft of any kind, epics too, that nobody holds (D-43). A held
    draft is in progress and stands under its holder only (#55)."""
    return not i["assignees"] and (bool(i.get("draft")) or i["type"] in state.WORK)


def view(root: Path, items: list, cfg: dict, me: str, cap: int = None) -> dict:
    """The ramp as a person sees it: gates and PLANs on item branches. A claim changes no PLAN,
    so claimed items get their gate too (plan_waits)."""
    found = plans(root)
    return ramp(items, plan_files(root, found), cap or cfg["cap"], me,
                gates=gates(root, [dict(i, assignees=[]) for i in items], config.load(root, config.base_ref(root)), found))


def held(items: list, files: dict) -> dict:
    """Canonical claims reserve exactly their files. A stopped or idle claim reserves no inferred PLAN
    files. Legacy records keep their old display until migration confirms the shared record."""
    out = {}
    for item in items:
        if item.get("revision"):
            reserved = (item.get("claim") or {}).get("files", [])
        elif item["type"] in state.WORK and item["assignees"] and not item.get("draft"):
            reserved = files.get(item["number"], []) + (item.get("claimed_files") or [])
        else:
            reserved = []
        out.update({f: item["number"] for f in reserved})
    return out


def clash(mine: list, held: dict):
    """(file, holder) for the first of mine another item holds, else None. A held directory holds
    what is in it."""
    return next(((f, n) for f in mine for h, n in held.items()
                 if f == h or f.startswith(h + "/") or h.startswith(f + "/")), None)


def ramp(items: list, files: dict, cap: int, me: str, gates=None) -> dict:
    """gates: {issue: why it waits} from gates(); a gated item never goes out. A draft nobody
    holds (its spec is to be written, D-43) is a row, never goes out, and takes no bay."""
    running = [i for i in items if i["type"] in state.WORK and i["assignees"] and not i.get("draft")]
    holders = {i["number"] for i in running}
    taken = held(items, files)
    busy = [i for i in running if me in i["assignees"] and not i.get("result")]  # published: no agent slot
    free = max(0, cap - len(busy))
    pos = {i["number"]: k for k, i in enumerate(order(items))}
    gates = gates or {}
    pool = sorted((i for i in items if i["type"] in state.WORK and not i["assignees"] and
                   not i.get("hold") and not i.get("failed") and not i.get("result") and not i["blocked_by"] and
                   i["number"] not in gates and not i.get("draft")), key=lambda i: pos[i["number"]])
    nxt, wait, locked = [], [], []
    for i in pool:
        mine = files.get(i["number"], [])
        hit = clash(mine, taken)
        if hit:
            locked.append({**i, "file": hit[0], "holder": hit[1], "reserved": hit[1] not in holders})
        elif len(nxt) < free:
            nxt.append(i)
            taken.update({f: i["number"] for f in mine})
        else:
            wait.append(i)
    pooled = {i["number"] for i in pool}
    stage = {i["number"]: "starts next" for i in nxt}
    stage.update({i["number"]: "queued" for i in wait})
    stage.update({i["number"]: (f"reserved: {Path(i['file']).name} for #{i['holder']} (starts next)" if i["reserved"]
                               else f"locked: {Path(i['file']).name} in use by #{i['holder']}") for i in locked})
    rows = []
    for i in order(items):
        if not _row(i):
            continue
        n = i["number"]
        s = ("spec in progress" if i.get("draft") else None) or \
            stage.get(n) or gates.get(n) or ("on hold" if i.get("hold") else None) or \
            ("failed" if i.get("failed") else "integration waits for approval" if i.get("result") else None) or \
            ("waits for " + ", ".join(f"#{b}" for b in i["blocked_by"]) if i["blocked_by"] else "ready")
        rows.append({**i, "stage": s})
    return {"cap": cap, "free": free, "busy": busy, "next": nxt, "wait": wait, "locked": locked, "rows": rows,
            "plan_waits": [i["number"] for i in running if gates.get(i["number"], "").startswith(WAITS)],
            "after": [i for i in state.blocked(items) if i["type"] in state.WORK and i["number"] not in pooled]}
