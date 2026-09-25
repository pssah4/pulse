"""pulse go: build everything that can run, in parallel, until the ramp is empty.

Deterministic, so no model can forget to parallelize: this script reads the
ramp, claims each item, gives it its own worktree beside the repo, and
starts one headless agent per item (a template from .pulse/config.toml:
Claude Code, Codex, or your own). After the build pulse go checks RED
itself: verify must fail at the commit that froze the spec tests. Then three
gates run in order: the project's tests (verify), a review, and a security
audit, the last two in fresh sessions (ADR-05); an audit whose scan failed
starts no session, and its gate says why. A red gate gets up to two fix
rounds, and after every fix the gates start again at the tests. What an
agent leaves uncommitted is committed before the next gate, and a phase
that committed pushes the item branch at once, so the next holder builds on
the work. The claim mark names the phase, and for a build the PLAN's files,
so every ramp holds them (WP-56); each later phase start puts the phase and
the time on it, and a phase that runs long renews them every 10 minutes: the
heartbeat every clone's map reads (D-43). The feature
gets one PR ("Closes #n") with the gates' results: ready when all passed,
draft while one is red; the review and audit verdicts go on it as comments
the next holder finds. A stacked feature's PR targets its blocker's branch.
A slot stays busy until the PR exists and is refilled at once. A failed
build gives its claim back and keeps its worktree for inspection. An item
without a PLAN is planned first; a PLAN that fails P1 to P5 gets up to two
fix rounds as well, then the item fails. An item given back after a
failure, a usage limit, or a stop keeps a note with the phase, the reason,
and its branch; a PLAN that still fails and an item held for a person
(D-42) keep one too. Each agent phase adds a line to .git/pulse/usage.jsonl.

One run drives several agents, each with its own slots ("claude:2,codex:2"),
so two subscriptions work at once. An agent that hits its usage limit gets
no new item for the rest of the run, and its item goes to another agent.
One run per clone (a lock the kernel frees however the run ends); a stopped
run gives its claims back, and the next start takes over what a killed one
left: it ends that run's agents and gives its claims back to the ramp,
except an item held for a person (D-42). A run of the same login in another
clone shares the ramp through claims; the start names what it keeps alive.

A draft whose branch got commits since its gates ran (a person fixed it) is
taken up: the gates run again, and the PR turns ready once all pass; bent
spec tests keep it draft without gates, and a held draft (D-42) waits for a
person. At the end of a run with two ready PRs or more, pulse go merges
their branches in dependency order in a scratch worktree and runs verify
there, so conflicts between parallel work show up before anyone merges.
Everything a run learns goes into .git/pulse/go/report.json as it happens.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import math
import shlex
import shutil
import signal
import subprocess
import sys
import time
import traceback
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pulse import config, dispatch, ready, review, spec, state

TIMEOUT_UNIT = 60              # agent_timeout is in minutes
REVIEW_ROUNDS = 2              # fix rounds per gate, the plan gate and RED too; then the PR says why
TOKENS = ("input", "output", "cache_read", "cache_write")
GATES = ("tests", "review", "audit")           # in this order after every build and every fix
# How Claude Code and Codex say that a subscription is used up.
LIMIT = re.compile(r"usage limit|hit your limit|spend limit reached|usage credit limit", re.I)
SPELLED = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
SKILLS = Path(__file__).resolve().parents[1] / "skills"
BUILD_SKILL = SKILLS / "pulse-build" / "SKILL.md"
PLAN_SKILL = SKILLS / "pulse-plan" / "SKILL.md"
PLAN_TEMPLATE = SKILLS / "pulse-plan" / "templates" / "PLAN-TEMPLATE.md"
RULES = """pulse go builds from the PLAN only when it passes P1 to P5:
P1 the frontmatter names issue, spec, files, and verify.
P2 a task covers every FR and SC of the spec (or a line "Deferred: SC-nn
reason"), every task covers one, and every FR not marked (unchanged) has its
spec test in wave 1, named after its id.
P3 every task names its files in backticks and a check; files in the
frontmatter is exactly the union of the tasks' files.
P4 tasks of one wave touch disjoint files.
P5 no placeholder outside inline code and the change log: no {...}, TODO,
???, or [CLARIFY]."""
PLAN_PROMPT = """You plan item #{n} "{title}" in this worktree, on branch {branch}.
Read its spec ({spec}), the decision records whose Read When fits, and the
code the spec touches. Write the PLAN with the discipline in {skill}, from
the template {template}, to _devprocess/plans/{n}-{slug}.md.{after} If the
item needs other work first that is not an item yet, list it under needs:
in the frontmatter and write it into DISCOVERED.md at the worktree root.
Commit the PLAN alone as "docs(plan): #{n}"; if git refuses to commit (a
sandbox), leave it, pulse go commits it. Write no code. Do not touch GitHub.
Nobody answers or approves anything in this session: a command that is
denied is not available to you, so plan from what you can read.{again}

{rules}"""
NO_PLAN = """

Your last session on this item ended without a PLAN. Write it now."""
PLAN_FIX = """You fix the PLAN of item #{n} "{title}" ({plan}) in this worktree, on
branch {branch}, with the discipline in {skill}. It fails these checks:

{findings}

Change the PLAN until none of them holds. Commit it as "docs(plan): #{n}";
if git refuses to commit (a sandbox), leave it, pulse go commits it. Write
no code. Do not touch GitHub.

{rules}"""
PROMPT = """You are one of several Pulse agents building in parallel.
Build item #{n} "{title}" in this worktree, on branch {branch}{stack}.
Follow its PLAN ({plan}) and its spec ({spec}) with the discipline in
{skill}. First write the spec tests of the PLAN's first wave, one per
requirement and named after its id; run them once, they must fail, and
commit them alone as "test: spec tests for #{n}". From then on do not
change those tests, change the code. Inside, work test first, stay within
the PLAN's files, run the PLAN's verify commands until they pass. Commit
your work on {branch} with "Refs: #{n}"; if git refuses to commit (a
sandbox), leave the changes, pulse go commits them. The worktree may hold
work from an earlier attempt: check git status and git log first.
Do not touch GitHub: no pulse claim, done, or new, no push, no PR; the
orchestrator does that. Write new work and bugs you discover into
DISCOVERED.md at the worktree root, one line per item, instead of pulse new;
the orchestrator records them once the user agrees. End with a short summary and the
output of the verify commands."""
FIX = """You are fixing item #{n} "{title}" in this worktree, on branch {branch}. Its
{gate} gate is red. Fix each blocking finding
below with the discipline in {skill}: test first, stay within the PLAN's files,
run the PLAN's verify commands until they pass. Commit on {branch} with
"Refs: #{n}"; if git refuses to commit (a sandbox), leave the changes, pulse go
commits them. Do not touch GitHub. Notes do not block; leave them.

{findings}"""


@dataclass
class Job:
    number: int
    title: str
    branch: str
    base: str
    start: str
    worktree: Path
    proc: subprocess.Popen = None
    log: object = None
    started: float = field(default_factory=time.time)
    rc: int = None
    why: str = ""
    phase: str = "build"       # plan, build, spec tests (RED), tests, review, audit, fix
    rounds: dict = field(default_factory=dict)     # gate -> fix rounds spent on it
    results: dict = field(default_factory=dict)    # gate -> pass, fail, block, none, or what is wrong
    reports: dict = field(default_factory=dict)    # gate -> what the tests or the session said
    notes: list = field(default_factory=list)      # what else the PR has to say
    fixing: str = ""           # the gate the running fix round answers
    plan: str = ""
    spec: str = ""
    agent: str = ""
    head: str = ""             # HEAD when the phase started: did the agent commit?
    env: dict = None           # the agent's environment: it claims as the run (PULSE_HOLDER)
    limited: bool = False      # the agent stopped at its usage limit; the item goes back
    stacked_on: int = None     # the one blocker whose ready branch this item builds on
    blockers: list = field(default_factory=list)   # its blocker edges; its PLAN need not name them
    open_: set = None          # the open issues at its claim: a needs: entry that names a closed one is done
    usage: dict = None         # tokens, cost, and seconds its agent phases reported, summed
    kept: bool = False         # planned and ready: its claim goes on into the build
    pr: int = None             # the draft this job takes up, when it does
    body: str = ""             # that draft's text
    guard: dict = None         # what no phase may change, as it was when the phase started (D-42)

    def public(self, **extra):
        return {"number": self.number, "title": self.title, "branch": self.branch,
                "base": self.base, "worktree": str(self.worktree), **extra}


def _git(cwd, *args, check=False):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise state.StateError(f"git {' '.join(args[:2])}: {out.stderr.strip()}")
    return out


def slug(title: str) -> str:
    """The title in a branch name, ASCII only: ä to ae, ö to oe, ü to ue, ß to ss, other accents go (N3.01)."""
    text = unicodedata.normalize("NFC", title).lower().translate(SPELLED)       # an ä taken apart is still ä
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40] or "item"


def _branch_of(root: Path, n: int) -> str:
    """The branch item #n already has, here or pushed from any clone: a new title keeps it (F7.06)."""
    refs = _git(root, "for-each-ref", "--format=%(refname:lstrip=2)", "refs/heads",
                "refs/remotes/origin").stdout.split()
    return next((b for b in (r.removeprefix("origin/") for r in refs) if state.item_of(b) == n), "")


def job_for(root: Path, item: dict, base_branch: str) -> Job:
    n = item["number"]
    kind = item["type"] if item["type"] in state.WORK else "feat"
    branch = _branch_of(root, n) or f"{kind}/{n}-{slug(item['title'])}"
    return Job(n, item["title"], branch, item.get("base") or base_branch, "",
               root.parent / f"{root.name}-{branch.split('/', 1)[1]}",
               stacked_on=item.get("stacked_on"), blockers=item.get("blocked_by") or [])


def _start(root: Path, cfg: dict, template: str, job: Job, plans: dict, specs: dict, logs: Path,
           phase: str = "build") -> str:
    ready.net_git(root, "fetch", "-q", "--prune", "origin")     # what landed since, and this branch from any clone
    job.start = config.base_ref(root, job.base)
    pushed = f"origin/{job.branch}"
    if not job.worktree.exists():
        exists, on_origin = (_git(root, "rev-parse", "--verify", "-q", ref).returncode == 0
                             for ref in (job.branch, pushed))
        args = ["worktree", "add", str(job.worktree), job.branch] if exists else \
            ["worktree", "add", "--no-track", "-b", job.branch, str(job.worktree), pushed if on_origin else job.start]
        _git(root, *args, check=True)
    _git(job.worktree, "merge", "-q", "--ff-only", pushed)      # behind a PLAN pushed elsewhere: catch up
    if phase == "build" and _git(job.worktree, "merge", "-q", "--no-edit", job.start).returncode:
        _git(job.worktree, "merge", "--abort")     # planned earlier: build on what landed since
        return f"does not merge with {job.start}; resolve it in {job.worktree}"
    job.plan = plans.get(job.number, "")
    job.spec = specs.get(job.number) or ""
    if phase == "resume":      # a draft with commits since its gates ran: the gates again
        changed = frozen_changes(job.worktree, job.number, job.start)
        if changed:            # bent tests prove nothing: no gates, and no phase starts (run finishes it)
            job.results["spec tests"] = f"changed after the freeze: {', '.join(changed)}"
        else:
            _gates(job, cfg, logs)
        return ""
    if phase == "plan":
        prompt = _plan_prompt(job)
    else:
        prompt = PROMPT.format(n=job.number, title=job.title, branch=job.branch, skill=BUILD_SKILL,
                               stack=f" (stacked on #{job.stacked_on}, branch {job.base})" if job.stacked_on else "",
                               plan=job.plan, spec=job.spec or "see the issue")
    _launch(job, config.agent_argv(_allowing(template, cfg, job), prompt), logs, phase)
    return ""


def _plan_prompt(job: Job, again: str = "") -> str:
    refs = ", ".join(f"#{b}" for b in job.blockers)
    return PLAN_PROMPT.format(n=job.number, title=job.title, branch=job.branch, skill=PLAN_SKILL,
                              template=PLAN_TEMPLATE, spec=job.spec, slug=slug(job.title), rules=RULES, again=again,
                              after=f" It waits for {refs} on the board already; needs: does not repeat "
                                    "that." if refs else "")


# What a verify line of the PLAN never gets unasked (D2/D3): a download, a package runner, another
# user or environment anywhere in its rule, or a rule that ends at a shell, an interpreter, or a
# runner, which runs whatever code follows it.
# ponytail: word lists; a program the configured verify runs keeps its other subcommands (git push,
# when verify starts with git), name those here when a project needs that
NEVER_ANYWHERE = re.compile(r"curl|wget|npx|pnpx|bunx|uvx|env|sudo|doas|su|xargs|eval")
NEVER_AFTER = re.compile(r"exec|x|dlx|i|install|add|get|pip[\d.]*|tool|timeit")     # fetch or run a package
NEVER_LAST = re.compile(r"(ba|da|k|z)?sh|fish|python[\d.]*|node|deno|bun|ruby|perl|php|run|pip[\d.]*")


def _allowing(template: str, cfg: dict, job: Job) -> str:
    """The template with its allow list widened to the verify commands of the item's PLAN, each
    cut as the configured verify is (config._allow), so the agent runs what the PLAN says (N4.03).
    The planning agent wrote them: a line adds a rule only as a test command of the project, one
    that starts with a program of the configured verify or runs a script of the repository; the item
    log and the PR name the others. load() put _allow(verify) where the template said {allow}; a
    template without it stays."""
    plan = ready._git(job.worktree, "show", f"HEAD:{job.plan}") if job.plan else ""
    rules = dict.fromkeys(shlex.split(config._allow(cfg["verify"])))
    programs = {c.split()[0] for c in re.split(r"[;&|]+", cfg["verify"]) if c.split()}
    refused = []
    for v in ready.listed(plan, "verify"):
        rule = shlex.split(config._allow(v))[0]
        words = rule[len("Bash("):-len(":*)")].split()
        inside = "/" in words[0] and not words[0].startswith("/") and ".." not in words[0].split("/")
        if (words[0] in programs or inside) and all(re.fullmatch(r"[\w./:@+=-]+", w) for w in words) \
                and not any(NEVER_ANYWHERE.fullmatch(os.path.basename(w)) for w in words) \
                and not any(NEVER_AFTER.fullmatch(w) for w in words[1:]) \
                and not NEVER_LAST.fullmatch(os.path.basename(words[-1])):
            rules.setdefault(rule)
        elif rule not in rules:        # the configured verify allows it anyway
            refused.append(v)
    note = (f"The agent could not run these verify lines of the PLAN: {', '.join(f'`{v}`' for v in refused)}. "
            "A PLAN's verify line runs unasked only when it starts with a program of the configured verify "
            "or with a script of the repository; a shell, interpreter, or runner given code, a download, env, "
            "or sudo never does. The tests gate runs the configured verify.")
    if refused and note not in job.notes:
        job.notes.append(note)
        with open(config.pulse_dir(job.worktree) / "go" / f"{job.number}.log", "a", encoding="utf-8") as f:
            f.write(f"pulse go: {note}\n")
    return template.replace(config._allow(cfg["verify"]), " ".join(shlex.quote(r) for r in rules))


def _launch(job: Job, argv: list, logs: Path, phase: str, cwd: Path = None) -> None:
    logs.mkdir(parents=True, exist_ok=True)
    job.log = open(logs / f"{job.number}.log", "a", encoding="utf-8")    # every phase, run, and agent of the item
    job.log.write(f"--- phase {phase} ---\n")
    job.log.flush()
    (logs / f"{job.number}.phase").write_text(phase, encoding="utf-8")     # for the map; the log grows large
    job.phase, job.rc, job.why = phase, None, ""
    job.head = _git(job.worktree, "rev-parse", "HEAD").stdout.strip()
    job.guard = _guard(job, logs.parents[1])
    job.proc = subprocess.Popen(argv, cwd=cwd or job.worktree, stdin=subprocess.DEVNULL, stdout=job.log,
                                stderr=subprocess.STDOUT, start_new_session=True, env=job.env)
    job.started = time.time()
    _group(logs, job.number, job.proc.pid)


def _stop(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)            # the whole group: agents spawn children
            proc.wait(timeout=5)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired, PermissionError):
            continue


def _wait(jobs: dict, limit: float, poll: float, until: float = math.inf) -> list:
    """The jobs whose phase ended; a quick phase (the tests) is seen at once, a long one every poll s.
    [] once the clock passed `until`: a sign of life is due."""
    nap = 0.05
    while True:
        done = []
        for job in jobs.values():
            rc = job.proc.poll()
            if rc is None and time.time() - job.started > limit:
                _stop(job.proc)
                job.why, rc = "timed out", job.proc.wait()
            if rc is not None:
                job.rc = rc
                _reap(job.proc)
                done.append(job)
        if done or time.time() >= until:
            return done
        time.sleep(nap)
        nap = min(poll, nap * 2)


def _reap(proc: subprocess.Popen) -> None:
    """What a phase left running in its process group goes with it: a leftover could write the
    next session's verdict."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _commit_leftovers(job: Job, subject: str = None) -> None:
    """Commit what an agent left uncommitted: Codex's sandbox keeps .git read-only (#7).
    Temporary test files under _devprocess/temp and DISCOVERED.md never go in, ignored or not,
    and staged by the agent or not."""
    _git(job.worktree, "add", "-A", "--", ".", ":(exclude)DISCOVERED.md", ":(exclude)_devprocess/temp")
    _git(job.worktree, "reset", "-q", "--", "DISCOVERED.md", "_devprocess/temp")
    if _git(job.worktree, "diff", "--cached", "--quiet").returncode:
        kind = "fix" if job.branch.startswith("fix/") else "feat"
        c = _git(job.worktree, "commit", "-q", "-m", f"{subject or f'{kind}: {job.title}'}\n\n"
                 f"Refs: #{job.number}\nCommitted by pulse go: {job.agent} left these changes uncommitted.")
        job.why = job.why or (f"commit failed: {c.stderr.strip()}" if c.returncode else "")


def _limited(job: Job) -> bool:
    """The agent stopped at its usage limit: the end of its phase's output says so."""
    return bool(LIMIT.search(_section(job.log.name, job.phase)[-4000:]))


def _worked(job: Job) -> bool:
    """Code on the branch beyond its start, from this run or an earlier one; a PLAN alone is none."""
    count = _git(job.worktree, "rev-list", "--count", f"{job.start}..HEAD", "--", ".",
                 ":(exclude)_devprocess").stdout.strip()
    return count not in ("", "0")


def _section(log: str, phase: str) -> str:
    """The output of the last run of a phase."""
    return Path(log).read_text(encoding="utf-8", errors="replace").rsplit(f"--- phase {phase} ---", 1)[-1]


def _tail(log: str, phase: str, lines: int = 40) -> str:
    """The output of the last run of a phase, its last lines."""
    return "\n".join(_section(log, phase).strip().splitlines()[-lines:])


def _fix(job: Job, cfg: dict, logs: Path, gate: str, findings: str) -> bool:
    """One more fix round for a red gate, the plan gate too, while it has rounds left; False when it
    has none."""
    if job.rounds.get(gate, 0) >= REVIEW_ROUNDS:
        return False
    job.rounds[gate] = job.rounds.get(gate, 0) + 1
    job.fixing = gate
    if gate == "plan":
        prompt = PLAN_FIX.format(n=job.number, title=job.title, plan=job.plan, branch=job.branch,
                                 skill=PLAN_SKILL, findings=findings, rules=RULES) if job.plan else \
            _plan_prompt(job, NO_PLAN)
    else:
        prompt = FIX.format(n=job.number, title=job.title, branch=job.branch, gate=gate, skill=BUILD_SKILL,
                            findings=findings)
    _launch(job, config.agent_argv(_allowing(cfg["agents"][job.agent], cfg, job), prompt), logs,
            "plan" if gate == "plan" else "fix")
    return True


def _gates(job: Job, cfg: dict, logs: Path) -> bool:
    """Start the chain after a build or a fix: the project's tests first."""
    _launch(job, ["sh", "-c", cfg["verify"]], logs, "tests")
    return False


def _scratch(logs: Path, n: int) -> Path:
    """Where the RED check of #n checks out the commit that froze its spec tests."""
    return logs.parent / "red" / str(n)


def _red(job: Job, cfg: dict, logs: Path) -> bool:
    """RED, evidenced by pulse go itself before the gates, whatever the agent said: the project's
    tests must fail at the last commit that froze spec tests, in a scratch worktree; a RED fix
    round freezes its failing tests anew, the lines the build froze stay frozen (frozen_changes).
    Without that commit the PR says so."""
    frozen = _frozen_at(job.worktree, job.number, job.start, last=True)
    if not frozen:
        job.notes.append(f'No spec-test commit, RED not evidenced: no commit "test: spec tests for '
                         f'#{job.number}" froze the spec tests before the code.')
        return _gates(job, cfg, logs)
    scratch = _scratch(logs, job.number)
    _git(job.worktree, "worktree", "remove", "--force", str(scratch))        # one a stopped run left
    _git(job.worktree, "worktree", "add", "--detach", str(scratch), frozen, check=True)
    # ponytail: any failure counts as RED, a setup the scratch lacks too (node_modules); compare the
    # failing tests with the frozen ones when that fools the check
    _launch(job, ["sh", "-c", cfg["verify"]], logs, "spec tests", cwd=scratch)
    return False


def _red_seen(job: Job, cfg: dict, logs: Path) -> bool:
    """The RED check ended: tests that pass before the code get a fix round, then the PR says so.
    The gates follow either way; only a red gate makes a draft (D-19)."""
    scratch = _scratch(logs, job.number)
    sha = _git(scratch, "rev-parse", "--short", "HEAD").stdout.strip()
    _git(job.worktree, "worktree", "remove", "--force", str(scratch))
    at = f"at {sha}, where the spec tests were frozen, before the code"
    if job.rc and not job.why:
        job.notes.append(f"RED evidenced: the tests fail {at}.")
    elif not job.why and _fix(job, cfg, logs, "spec tests", f"- [block] spec tests must fail first: "
                              f"`{cfg['verify']}` passes {at}. Commit the spec tests alone, before any code, "
                              "where they fail."):
        return False
    else:
        job.notes.append(f"RED not evidenced: the tests {job.why or 'pass'} {at}.")
    return _gates(job, cfg, logs)


def _session(job: Job, cfg: dict, logs: Path, kind: str) -> bool:
    """A fresh session that did not build the feature: the review, then the security audit. True when
    none starts: an audit whose scan failed gives no verdict, so its gate says why instead (N3.11)."""
    b = review.brief(job.worktree, job.number, job.title, job.spec, job.start, tests=job.results.get("tests")) \
        if kind == "review" else review.audit_brief(job.worktree, job.number, job.title, job.start)
    if b.get("unscanned"):     # as review.run reads it
        rec = review.record(job.worktree, job.number, kind, failed=f"did not start: {b['unscanned']}")
        job.results[kind], job.reports[kind] = "none", rec["why"]
        return True
    _launch(job, config.agent_argv(review.template(cfg, cfg["review_agent"] or job.agent), b["prompt"]),
            logs, kind)
    return False


def _advance(root: Path, repo: str, cfg: dict, job: Job, gh_run, rep: dict, logs: Path,
             who: dict, spent: set) -> bool:
    """A job's agent ended: start its next phase or finish it. True when the job is finished.
    The chain per feature: build, tests, review, audit, PR; a red gate gets up to two fix
    rounds, and after every fix the chain starts again at the tests."""
    job.log.close()
    _record(job, cfg, logs)
    changed = sorted(p for p, b in _guard(job, logs.parents[1], list(job.guard)).items() if b != job.guard.get(p))
    if changed:
        return _hold(root, repo, job, gh_run, rep, logs, changed, who)
    moved = _git(job.worktree, "rev-parse", "HEAD").stdout.strip() != job.head
    if job.phase in ("plan", "build", "fix"):
        if not (job.why or job.rc):    # what the agent left goes in first: every gate judges one state (N4.02)
            _commit_leftovers(job, f"docs(plan): #{job.number}" if job.phase == "plan" else None)
        if _git(job.worktree, "rev-parse", "HEAD").stdout.strip() != job.head and \
                not _pushed(root, repo, job, gh_run, rep, who):
            return True
    # ponytail: only a build checks for the limit; a spent agent in a gate or a fix
    # leaves a draft PR and drops out at its next build.
    if job.phase in ("plan", "build") and (job.why or job.rc or not moved) and _limited(job):
        stays = _release(root, repo, job.number, gh_run, who, _handover(job, f"{job.agent} hit its usage limit"))
        spent.add(job.agent)
        job.limited = True
        _event(rep, "limited", job.public(agent=job.agent, log=job.log.name,
                                          why=f"{job.agent} hit its usage limit{stays}"))
        return True
    if job.phase == "plan":
        return _planned(root, repo, job, gh_run, rep, cfg, who, logs)
    if job.phase == "build":
        why = job.why or (f"exit {job.rc}" if job.rc else "") or ("" if _worked(job) else "no commits")
        if why:
            _discovered(job, rep)
            _event(rep, "failed", job.public(why=why + _release(root, repo, job.number, gh_run, who,
                                                                 _handover(job, why)), log=job.log.name))
            return True
    if job.phase == "fix" and (job.why or job.rc):
        job.notes.append(f"The fix round for {job.fixing} ended early: {job.why or f'exit {job.rc}'}.")
        return _finish(root, repo, job, gh_run, rep, who, cfg)
    if job.phase in ("build", "fix"):
        changed = frozen_changes(job.worktree, job.number, job.start)
        if changed and _fix(job, cfg, logs, "spec tests",
                            f"- [block] the spec tests changed after they were frozen: {', '.join(changed)}. "
                            "Restore them and change the code instead."):
            return False
        if changed:                    # bent tests prove nothing: no gates, a draft that says so
            job.results["spec tests"] = f"changed after the freeze: {', '.join(changed)}"
            return _finish(root, repo, job, gh_run, rep, who, cfg)
        if job.phase == "build" or job.fixing == "spec tests":     # only these move the freeze
            return _red(job, cfg, logs)
        return _gates(job, cfg, logs)
    if job.phase == "spec tests":
        return _red_seen(job, cfg, logs)
    if job.phase == "tests":
        if not (job.why or job.rc):
            job.results["tests"] = "pass"
            return _session(job, cfg, logs, "review")
        job.results["tests"] = "fail"
        job.reports["tests"] = _tail(job.log.name, "tests")
        if _fix(job, cfg, logs, "tests", f"- [block] the tests fail (`{cfg['verify']}`):\n\n"
                                         f"{job.reports['tests']}"):
            return False
        return _finish(root, repo, job, gh_run, rep, who, cfg)
    kind = job.phase                   # review or audit
    rec = review.record(job.worktree, job.number, kind,     # a session that failed or was stopped judges nothing
                        failed=job.why or (f"ended with exit {job.rc}" if job.rc else ""))
    job.results[kind] = rec["verdict"] or "none"
    job.reports[kind] = rec["report"] if rec["verdict"] else f"{rec['why']}\n\n{rec.get('report', '')}".strip()
    if rec["verdict"] == "block" and _fix(job, cfg, logs, kind, job.reports[kind]):
        return False
    if rec["verdict"] == "pass" and kind == "review" and not _session(job, cfg, logs, "audit"):
        return False
    return _finish(root, repo, job, gh_run, rep, who, cfg)


def _log_path(job: Job, logs: Path = None) -> str:
    return job.log.name if job.log else str(logs / f"{job.number}.log") if logs else ""


def _trouble(job: Job, e: Exception, logs: Path = None) -> str:
    """What went wrong with one item, for the report; the traceback goes into its log for whoever
    looks."""
    try:
        path = Path(_log_path(job, logs))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"--- pulse go: {type(e).__name__} ---\n{traceback.format_exc()}")
    except OSError:
        pass                   # the report still says what happened
    return f"{job.phase}: {type(e).__name__}: {e}"


def _discovered(job: Job, rep: dict) -> list:
    """What the agent wrote into DISCOVERED.md: into the report and .git/pulse/go/discovered.md at
    once, so no stop loses it (F9.03); the PR names it too."""
    found = job.worktree / "DISCOVERED.md"
    if not found.is_file():
        return []
    lines = [l.strip("- ").strip() for l in found.read_text(encoding="utf-8", errors="replace").splitlines()
             if l.strip()]
    rep["discovered"] += [{"from": job.number, "item": l} for l in lines]
    with open(Path(rep["report"]).with_name("discovered.md"), "a", encoding="utf-8") as f:
        f.write("".join(f"- #{job.number}: {l}\n" for l in lines))
    found.unlink()
    _save(rep)
    return lines


def _planned(root: Path, repo: str, job: Job, gh_run, rep: dict, cfg: dict, who: dict, logs: Path) -> bool:
    """A planning agent ended: a PLAN that fails P1 to P5 goes back to it with the findings, up to two
    rounds. Each round's PLAN is pushed already (_advance). Then name the gate and give the claim
    back last, so an error on the way keeps it (ADR-04) and no run builds the item before a person
    looked."""
    why = job.why or (f"exit {job.rc}" if job.rc else "")
    written = _git(job.worktree, "diff", "--name-only", "--diff-filter=d", f"{job.head}..HEAD", "--",
                   ready.PLANS).stdout.split()
    job.plan = job.plan or (written[0] if written else "")        # a fix round works on the first one
    if not (why or job.plan) and _fix(job, cfg, logs, "plan", ""):    # it ended asking, not planning
        return False
    why = why or ("" if job.plan else "no PLAN written")
    _discovered(job, rep)
    if not why:
        text = ready._git(job.worktree, "show", f"HEAD:{job.plan}")     # the committed blob: no link, no FIFO
        spec_text = spec.on_base(root, job.spec) if job.spec else None
        wrong = ready.plan_findings(text, spec_text)
        if wrong and _fix(job, cfg, logs, "plan", "\n".join(f"- {w}" for w in wrong)):
            return False
    if why:
        _event(rep, "failed", job.public(why=why + _release(root, repo, job.number, gh_run, who, _handover(job, why)),
                                         log=job.log.name, usage=job.usage))
        return True
    gate = ready.plan_gate(text, spec_text, cfg, blockers=job.blockers, open_=job.open_) or "ready"
    job.kept = gate == "ready"         # the next round builds it on this claim when the ramp lets it
    failed = gate.startswith("plan: ")     # its fix rounds are spent: a person fixes the pushed PLAN
    stays = "" if job.kept else _release(root, repo, job.number, gh_run, who, _handover(
        job, f"{gate} (after {REVIEW_ROUNDS} fix rounds)") if failed else "")
    if failed:
        _event(rep, "failed", job.public(why=f"{gate} (after {REVIEW_ROUNDS} fix rounds; the PLAN is on "
                                             f"{job.branch}){stays}", plan=job.plan, log=job.log.name,
                                         usage=job.usage))
    else:
        _event(rep, "planned", job.public(plan=job.plan, gate=gate + stays, usage=job.usage))
    return True


def _freezes(worktree: Path, n: int, since: str) -> list:
    """The commits "test: spec tests for #n" since `since`, newest first."""
    return _git(worktree, "log", "--format=%H", f"--grep=^test: spec tests for #{n}$",
                f"{since}..HEAD").stdout.split()


def _frozen_at(worktree: Path, n: int, since: str, last: bool = False) -> str:
    """The first commit "test: spec tests for #n" since `since`, the last one with `last`, or ""."""
    shas = _freezes(worktree, n, since)
    return (shas[0] if last else shas[-1]) if shas else ""


def frozen_changes(worktree: Path, n: int, since: str) -> list:
    """Spec test files whose frozen lines changed after a freeze commit ("test: spec tests for
    #n", the build's and any a RED fix round adds): each run of lines such a commit added must
    still stand at HEAD, unchanged and in one piece. An older test in the same file may go or
    change (N4.01), and the blank lines at either end of a run with it: git hands them to
    whichever hunk it likes."""
    changed = []
    for frozen, f in ((c, f) for c in _freezes(worktree, n, since) for f in filter(
            None, _git(worktree, "show", "--name-only", "--format=", "-z", c).stdout.split("\0"))):
        if f in changed:
            continue
        blocks = []
        for line in ready._git(worktree, "show", "--format=", "--unified=0", frozen, "--", f).split("\n"):
            if line.startswith("@@"):              # with --unified=0 each hunk adds one run of lines
                blocks.append([])
            elif blocks and line.startswith("+"):
                blocks[-1].append(line[1:])
        now = ready._git(worktree, "show", f"HEAD:{f}").split("\n")
        text = [[k for k, line in enumerate(b) if line.strip()] for b in blocks]     # its lines that are not blank
        blocks = [b[k[0]:k[-1] + 1] for b, k in zip(blocks, text) if k]
        if any(not any(now[k:k + len(b)] == b for k in range(len(now) - len(b) + 1)) for b in blocks):
            changed.append(f)
    return changed


def _finite(v) -> bool:
    """A number an agent reported, not a string, a bool, NaN, infinity, or an integer no float
    holds: the log holds any output."""
    try:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    except OverflowError:
        return False


def _usage(text: str):
    """What an agent reported as JSON in one phase's output, summed; None without any. Claude's
    result line counts cache reads and writes beside its input tokens, Codex's turn.completed
    (codex exec --json) counts them inside."""
    out, cost, models, seen = dict.fromkeys(TOKENS, 0), None, [], False
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        try:                   # the log holds any output: a line that does not add up is skipped
            d = json.loads(line)
            u = d.get("usage")
            if not isinstance(u, dict) and "total_cost_usd" not in d:
                continue
            n = {k: v for k, v in (u if isinstance(u, dict) else {}).items() if _finite(v)}
            inside = n.get("cached_input_tokens", 0) + n.get("cache_write_input_tokens", 0)
            add = {"input": n.get("input_tokens", 0) - inside, "output": n.get("output_tokens", 0),
                   "cache_read": n.get("cache_read_input_tokens", 0) + n.get("cached_input_tokens", 0),
                   "cache_write": n.get("cache_creation_input_tokens", 0) + n.get("cache_write_input_tokens", 0)}
            out = {k: out[k] + add[k] for k in TOKENS}          # all or nothing per line
            if _finite(d.get("total_cost_usd")):
                cost = (cost or 0.0) + float(d["total_cost_usd"])
            if isinstance(d.get("modelUsage"), dict):
                models += [m for m in d["modelUsage"] if m not in models]
        except (ValueError, TypeError, OverflowError, RecursionError):
            continue
        seen = True
    if not (seen and all(_finite(v) for v in out.values()) and (cost is None or _finite(cost))):
        return None
    return {**out, "cost_usd": None if cost is None else round(cost, 4), "model": ",".join(models) or None}


def _record(job: Job, cfg: dict, logs: Path) -> None:
    """One line per agent phase in .git/pulse/usage.jsonl, kept across runs to compare agents, models,
    and ways of working; the report sums the job's phases."""
    if job.phase in ("tests", "spec tests"):
        return                 # the project's own command, no agent
    agent = (cfg["review_agent"] or job.agent) if job.phase in ("review", "audit") else job.agent
    try:
        u = _usage(_section(job.log.name, job.phase)) or {}
    except OSError:
        u = {}
    row = {"at": _now(), "item": job.number, "phase": job.phase,
           "agent": agent, "model": u.get("model") or _model(cfg["agents"].get(agent, "")),
           **{k: u.get(k) for k in TOKENS + ("cost_usd",)}, "seconds": round(time.time() - job.started)}
    try:
        with open(logs.parent / "usage.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass                   # a lost line loses a measurement, never the item
    if u:
        was = job.usage or {"tokens": 0, "cost_usd": 0.0, "seconds": 0}
        job.usage = {"tokens": was["tokens"] + sum(u[k] for k in TOKENS),
                     "cost_usd": round(was["cost_usd"] + (u["cost_usd"] or 0), 4),
                     "seconds": was["seconds"] + row["seconds"]}


def _model(template: str):
    """The model a template names with its own -m or --model token (Codex's output names none);
    never a word inside another argument, such as "-m pytest" in an allowed command (N3.06)."""
    try:
        tokens = shlex.split(template)
    except ValueError:
        return None
    for k, tok in enumerate(tokens):
        if tok.startswith("--model="):
            return tok.split("=", 1)[1]
        if tok in ("-m", "--model") and k + 1 < len(tokens):
            return tokens[k + 1]
    return None


def _result(job: Job, gate: str) -> str:
    r = job.results.get(gate, "not run")
    n = job.rounds.get(gate, 0)
    return r + (f" after {n} fix round{'s' if n != 1 else ''}" if n and r == "pass" else
                f", {n} fix round{'s' if n != 1 else ''} spent" if n else "")


def _finish(root: Path, repo: str, job: Job, gh_run, rep: dict, who: dict, cfg: dict = None) -> bool:
    """One feature, one PR: against the base branch, or against the blocker's branch when it is
    stacked. Ready when every gate passed, else a draft that names what is open; the claim stays.
    What departs from the PLAN is a section for the person who merges, never a draft (D-19)."""
    found = _discovered(job, rep)
    if not _pushed(root, repo, job, gh_run, rep, who):
        return True
    gates = GATES + tuple(g for g in job.results if g not in GATES)          # spec tests, when they were bent
    green = all(job.results.get(g, "").startswith("pass") for g in gates)
    head = ("Ready for review: tests, review, and security audit are through." if green else
            "Draft: a gate is still red. It stays draft until the findings below are resolved and a "
            "fresh run of the gates passes.")
    table = "| Gate | Result |\n|---|---|\n" + "\n".join(f"| {g} | {_result(job, g)} |" for g in gates)
    gated = _git(job.worktree, "rev-parse", "HEAD").stdout.strip()
    parts = [f"Closes #{job.number}", f"Built by `pulse go` ({job.agent}). {head}", table,
             f"Gates ran at `{gated}`.", *job.notes]
    outside = review.outside_plan(job.worktree, job.number, review.files(job.worktree, "branch", job.start))
    if outside:
        parts.append("## Deviations from the PLAN\n\n" + "\n".join(f"- {o}" for o in outside))
    if found:
        parts.append("## Discovered\n\n" + "\n".join(f"- {l}" for l in found))
    if job.results.get("tests") == "fail":     # the output stays local: a test may print what a PR must not
        parts.append(f"The tests' output is in `.git/pulse/go/{job.number}.log`, section `phase tests`.")
    parts += [f"### {g.capitalize()}\n\n{job.reports[g]}" for g in ("review", "audit") if job.reports.get(g)]
    if job.pr:                 # a draft taken up: its text anew, ready once every gate passed
        url = gh_run(["pr", "edit", str(job.pr), "--repo", repo, "--body", "\n\n".join(parts)])
        if green:
            gh_run(["pr", "ready", str(job.pr), "--repo", repo])
    else:
        url = gh_run(["pr", "create", "--repo", repo, "--base", job.base, "--head", job.branch,
                      "--title", job.title, "--body", "\n\n".join(parts)] + ([] if green else ["--draft"]))
    opened = re.search(r"/pull/(\d+)$", url.strip())
    try:                       # the verdicts travel with the PR: the next holder's hook finds them (WP-58)
        review.publish(job.worktree, job.number, gh_run, job.pr or (int(opened.group(1)) if opened else None))
    except (state.StateError, OSError, ValueError) as e:
        _say(job, f"the gate verdicts did not reach the pull request: {e}")
    state.drop_cache(root)
    _event(rep, "done", job.public(pr=url.strip().splitlines()[-1] if url.strip() else "",
                                   **{g: job.results.get(g, "not run") for g in GATES},
                                   rounds=sum(job.rounds.values()), usage=job.usage))
    return True


def _pushed(root: Path, repo: str, job: Job, gh_run, rep: dict, who: dict) -> bool:
    """The item branch to origin, a fast-forward only, so the next holder builds on the work (WP-51).
    A rejected push stops the item: the report says why, and the claim goes back."""
    push = ready.net_git(job.worktree, "push", "-q", "origin", job.branch)
    if push.returncode:
        why = f"push failed: {push.stderr.strip()}"
        _event(rep, "failed", job.public(why=why + _release(root, repo, job.number, gh_run, who, _handover(job, why)),
                                         log=_log_path(job)))
    return not push.returncode


def _bytes(path: Path):
    try:
        return path.read_bytes()
    except OSError:
        return None


def _guard(job: Job, gitdir: Path, paths=()) -> dict:
    """What no phase may change, with its bytes: the shared git dir's config and hooks, and the files
    that point this worktree at its git dir. A phase that could write there (Codex with --add-dir)
    could leave a hook that runs later outside every sandbox and shows in no diff (D-42)."""
    if not paths:
        own = Path(_git(job.worktree, "rev-parse", "--absolute-git-dir").stdout.strip())
        paths = [gitdir / "config", own / "commondir", own / "config.worktree", job.worktree / ".git"]
    hooks = gitdir / "hooks"
    found = {str(p) for p in paths} | {str(h) for h in (hooks.iterdir() if hooks.is_dir() else ())}
    return {p: _bytes(Path(p)) for p in found}


def _hold(root: Path, repo: str, job: Job, gh_run, rep: dict, logs: Path, changed: list, who: dict) -> bool:
    """A phase changed what _guard watches: nothing more runs, nothing is pushed, the claim stays,
    and a person looks first (D-42). The item keeps a note as after a hand-back (D-43)."""
    if job.phase == "spec tests":
        _git(root, "worktree", "remove", "--force", str(_scratch(logs, job.number)))
    why = (f"the {job.phase} phase changed {', '.join(os.path.relpath(p, root.parent) for p in changed)}: "
           f"nothing is pushed and the claim stays until a person has looked (D-42)")
    _group(logs, job.number, None, held=True)       # a start after a hard stop keeps the claim too
    try:                       # as state.release leaves it, but the claim stays
        state.leave_note(repo, job.number, _handover(job, why), state.me(root, run=gh_run), who, gh_run)
    except state.StateError as e:
        _say(job, f"the note of the hold did not reach the item: {e}")
    if job.pr:                 # a draft taken up says it too, and no run takes it up while it does
        gh_run(["pr", "edit", str(job.pr), "--repo", repo, "--body", f"{HELD}{why}.\n\n{job.body}"])
    _event(rep, "failed", job.public(why=why, log=job.log.name))
    return True


GATED = re.compile(r"^Gates ran at `([0-9a-f]{40})`\.$", re.M)
HELD = "Held by `pulse go`: "


def _takes_up(root: Path, repo: str, item: dict, job: Job, gh_run) -> tuple:
    """(its text, "") when _draft takes this draft of pulse go up: its branch has commits since its
    gates ran (F6.03), a person fixed it, here or pushed from anywhere; a run of mine holds it, not a
    session; its text starts with no hold (D-42), which a person takes out. Else ("", why), why ""
    when it waits for a person. Reads alone, so --dry-run asks it too."""
    try:
        body = json.loads(gh_run(["pr", "view", str(item["pr"]["number"]), "--repo", repo, "--json",
                                  "body"]))["body"] or ""
        if body.startswith(HELD):
            return "", "held until a person has looked and taken the hold note out of its PR (D-42)"
        gated = GATED.search(body)
        heads = [_git(root, "rev-parse", "-q", "--verify", r).stdout.strip()
                 for r in (job.branch, f"origin/{job.branch}")]
        if not gated or not any(h and _git(root, "merge-base", "--is-ancestor", h, gated.group(1)).returncode
                                for h in heads):
            return "", ""          # nothing new since its gates: it waits for a person
        marks = state._marks(state._view(repo, job.number, gh_run))
    except (state.StateError, ValueError, KeyError) as e:
        return "", f"its draft: {e}"
    if not (marks and marks[0]["mine"] and marks[0]["id"].startswith("go:")):
        return "", ""              # a session of mine works on it
    return body, ""


def _draft(root: Path, repo: str, item: dict, job: Job, gh_run, who: dict) -> tuple:
    """Take up a draft of pulse go that _takes_up names: the gates run again."""
    body, why = _takes_up(root, repo, item, job, gh_run)
    if not body:
        return False, why
    # ponytail: a run of mine in another clone that holds this draft right now loses it; its lock
    # is local, so a mark that names the clone would be the upgrade
    job.pr, job.body, job.base = item["pr"]["number"], body, item["pr"]["base"] or job.base
    job.notes = [p for p in body.split("\n\n")
                 if p.startswith(("RED ", "No spec-test commit", "The agent could not run"))]
    return state.claim(root, repo, job.number, run=gh_run, who=who, take=True, blockers=False)


def _tidy(root: Path, open_: set, rep: dict) -> None:
    """The clean worktree pulse go made for an item that is closed now (merged, or dropped) goes; one
    with changes stays and the report names it (F7.07). Then the local branch of each closed item
    goes too, where git branch -d takes it: no worktree on it, and all of it on origin's copy of the
    branch (the base here may not have the merge yet) or in HEAD."""
    for entry in _git(root, "worktree", "list", "--porcelain").stdout.split("\n\n"):
        wt, br = re.search(r"^worktree (.+)$", entry, re.M), re.search(r"^branch refs/heads/(.+)$", entry, re.M)
        n = br and state.item_of(br.group(1))
        if not (wt and n) or n in open_ or \
                Path(wt.group(1)).resolve() != (root.parent / f"{root.name}-{br.group(1).split('/', 1)[1]}").resolve():
            continue
        gone = _git(root, "worktree", "remove", wt.group(1))
        if gone.returncode:
            rep["unclean"].append({"number": n, "worktree": wt.group(1), "why": gone.stderr.strip()})
    for b in _git(root, "for-each-ref", "--format=%(refname:lstrip=2)", "refs/heads").stdout.split():
        if (n := state.item_of(b)) and n not in open_:              # -d against origin/<b>, else HEAD
            _git(root, "-c", f"branch.{b}.remote=origin", "-c", f"branch.{b}.merge=refs/heads/{b}", "branch", "-d", b)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


REPORTED = ("run", "items", "discovered", "took", "unclean", "integration", "elsewhere")   # report.json (D-14)


def _event(rep: dict, kind: str, entry: dict) -> None:
    """One result of the run: into the list of its kind, and at once into report.json, the latest
    per item, so that a stop loses nothing that happened before (D-14)."""
    n = entry["number"]
    rep["skipped"] = [e for e in rep["skipped"] if e["number"] != n]      # tried again, or it moved on
    rep[kind].append(entry)
    rep["items"][str(n)] = {"result": kind, "at": _now(), "pr": entry.get("pr", ""), "log": entry.get("log", ""),
                            "why": entry.get("why") or entry.get("gate") or
                            ", ".join(f"{g} {entry[g]}" for g in GATES if g in entry)}
    _save(rep)


def _save(rep: dict) -> None:
    if not rep["report"]:
        return                 # a dry run
    path = Path(rep["report"])
    try:
        path.with_suffix(".tmp").write_text(json.dumps({k: rep[k] for k in REPORTED if k in rep}, indent=1),
                                            encoding="utf-8")
        path.with_suffix(".tmp").replace(path)         # readers (status, the map) never see half a report
    except OSError:
        pass                   # the run goes on; its output on stdout still has everything


def last_run(root: Path):
    """report.json of the last pulse go run in this clone, or of the one running; None without one."""
    try:
        rep = json.loads((config.pulse_dir(root) / "go" / "report.json").read_text(encoding="utf-8"))
        run = rep["run"]
        run["running"] = not run.get("ended") and _alive(int(run["pid"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return rep


def _take(root: Path, repo: str, item: dict, job: Job, gh_run, who: dict) -> tuple:
    try:
        return _draft(root, repo, item, job, gh_run, who)
    except (state.StateError, ValueError, KeyError) as e:
        return False, f"its draft: {e}"


def _claim(root: Path, repo: str, item: dict, gh_run, who: dict, kind: str, files=None) -> tuple:
    """Claim for a plan (blockers need not be done) or a build (they must, but the one it stacks on).
    The mark names the phase, so no heartbeat follows the claim, and a build's files, so every ramp
    holds them without a fetch (WP-56)."""
    try:
        return state.claim(root, repo, item["number"], run=gh_run, who=who, blockers=kind == "build",
                           stacked_on=item.get("stacked_on"), phase=kind, files=files)
    except state.StateError as e:
        return False, str(e)


def _missing(template: str) -> str:
    """The command of an agent template when it is not installed here, else "". A template that does
    not split fails at its start, as any other start."""
    try:
        cmd = config.agent_argv(template, "")[0]
    except (ValueError, IndexError):
        return ""
    return "" if shutil.which(cmd) else cmd


def _slots(spec: str, cap: int, cfg: dict) -> dict:
    """The agents of this run with their slots; one that is not installed claims nothing (F7.01)."""
    try:
        slots = config.agent_slots(spec, cap)
    except ValueError as e:
        raise state.StateError(str(e)) from None
    for name in list(slots) + ([cfg["review_agent"]] if cfg["review_agent"] else []):
        if name not in cfg["agents"]:
            raise state.StateError(f"no agent template '{name}' in [agents] of .pulse/config.toml")
    if not slots:
        raise state.StateError("no agent given: agent = \"claude\" or \"claude:2,codex:2\"")
    gone = {a: c for a in [*slots, cfg["review_agent"]] if a for c in [_missing(cfg["agents"][a])] if c}
    if gone:
        why = "; ".join(f"agent {a}: {c} not found" for a, c in gone.items())
        if cfg["review_agent"] in gone or not set(slots) - set(gone):
            raise state.StateError(why)            # nobody left to build, or nobody to review
        print(f"pulse go: {why}; it claims nothing in this run", file=sys.stderr)
    return {a: n for a, n in slots.items() if a not in gone}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True            # another user's process, but alive
    except OSError:
        return False
    return True


def phases(root: Path) -> dict:
    """{item: the phase its job is in} while pulse go runs in this clone; {} otherwise."""
    common = config.pulse_dir(root)
    try:
        pid = common / "go.pid"
        if not _alive(int(pid.read_text().strip())):
            return {}
        since = pid.stat().st_mtime
    except (OSError, ValueError):
        return {}
    return {int(f.stem): f.read_text(encoding="utf-8").strip() for f in (common / "go").glob("*.phase")
            if f.stem.isdigit() and f.stat().st_mtime >= since}        # older ones are from an earlier run


def _lock(common: Path) -> tuple:
    """One run per clone drives every agent; a second would only compete for the same slots. The
    kernel frees the lock however a run ends; what a run noted in it (pid, holder, its agents'
    process groups) and never cleared tells the next start that it died (D-12). -> (lock, that note)
    go.pid stays for the hook and the map."""
    path = common / "go" / "lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        other = _noted(lock).get("pid", "?")
        lock.close()
        raise state.StateError(f"pulse go already runs here (pid {other}); one run drives all agents, "
                               'e.g. agent = "claude:2,codex:2"') from None
    (common / "go.pid").write_text(str(os.getpid()))
    return lock, _noted(lock)


def _noted(f) -> dict:
    f.seek(0)
    try:
        note = json.loads(f.read() or "{}")
    except ValueError:
        return {}
    return note if isinstance(note, dict) else {}


def _note(f, note: dict) -> None:
    """Rewrite the lock's note in place: a new file would be a new lock."""
    f.seek(0)
    f.truncate()
    f.write(json.dumps(note))
    f.flush()


def _group(logs: Path, n: int, pgid, held: bool = False) -> None:
    """Note the process group of #n's phase in the run's lock (None: the job ended), so that a start
    after a hard stop can end it; and #n when a person looks first (D-42), so that start keeps its claim."""
    try:
        with open(logs / "lock", "r+", encoding="utf-8") as f:
            note = _noted(f)
            groups = {k: v for k, v in (note.get("groups") or {}).items() if k != str(n)}
            _note(f, {**note, "groups": {**groups, **({str(n): pgid} if pgid else {})},
                      **({"held": [*(note.get("held") or []), n]} if held else {})})
    except OSError:
        pass                   # a lost note loses the takeover of one group, never the item


def _end(pgid: int) -> None:
    """A process group a stopped run left behind: SIGTERM, SIGKILL after 5 s."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
            for _ in range(50):
                time.sleep(0.1)
                os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return


def _release(root: Path, repo: str, n: int, gh_run, who: dict, note: str = "") -> str:
    """Give #n back, with a note for its next holder when there is one: "" when it went back, else
    why the claim stays and how to free it."""
    try:
        ok, why = state.release(root, repo, n, run=gh_run, who=who, note=note)
    except state.StateError as e:
        ok, why = False, str(e)
    return "" if ok else f" (the claim stays; pulse release {n} --take: {why})"


def _handover(job: Job, why: str) -> str:
    """The note an item keeps when pulse go gives it back after a failure, a limit, or a stop: the
    phase, why, and the branch whoever goes on builds on (D-43). Its first line is what the map shows."""
    return (f"{job.phase}: {why.removeprefix(job.phase + ': ')}\n"
            f"Its branch {job.branch} carries the work pushed so far.")


def _say(job: Job, line: str) -> None:
    """A line in the item's log for whoever looks; a log out of reach loses the line, never the item."""
    try:
        with open(_log_path(job), "a", encoding="utf-8") as f:
            f.write(f"pulse go: {line}\n")
    except OSError:
        pass


def _beat(root: Path, repo: str, job: Job, gh_run, who: dict) -> None:
    """The phase that starts now goes onto the item's claim mark with the time, so every clone's map
    sees the run alive (D-43). A beat that fails costs a sign of life, never the item."""
    try:
        state.beat(root, repo, job.number, job.phase, run=gh_run, who=who)
    except (state.StateError, OSError, ValueError) as e:
        _say(job, f"no sign of life on the board for the {job.phase} phase: {e}")


def _elsewhere(repo: str, items: list, login: str, mine: set, gh_run) -> list:
    """Items another pulse go run of my login holds with a sign of life within the map's SILENT: a
    run in another clone (WP-59). An item with a PR keeps its claim and its last beat until the
    merge, with no run on it. This run starts all the same; the claims decide who builds what."""
    from pulse import map as pmap      # the map imports this module
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - pmap.SILENT))
    out = []
    for i in items:
        if i.get("claimed_by") != login or i.get("pr") or (i.get("claimed_beat") or "") < since:
            continue
        m = (state._marks(state._view(repo, i["number"], gh_run)) or [{}])[0]
        if m.get("mine") and m["id"].startswith("go:") and m["id"] not in mine:
            out.append({"number": i["number"], "phase": m["phase"], "beat": m["beat"]})
    return out


def _take_over(root: Path, repo: str, login: str, left: dict, gh_run, rep: dict, base_branch: str) -> None:
    """A run that ended without its cleanup (SIGKILL, a crash, the power) left agents and claims; the
    free lock proves it is gone (D-12). Its agents stop, and its claims under my login go back, so the
    loop claims them anew. An item with a PR keeps its claim until the merge, and one it held for a
    person (D-42) until that person frees it."""
    # ponytail: a pgid the system gave to a new group since the crash would be ended too; note each
    # agent's start time as well if that ever happens
    for pgid in (left.get("groups") or {}).values():
        if isinstance(pgid, int) and pgid > 1 and pgid != os.getpgrp():
            _end(pgid)
    for i in state.load(root, repo, run=gh_run, fresh=True):
        n = i["number"]
        if login not in i["assignees"] or i.get("pr"):
            continue
        marks = state._marks(state._view(repo, n, gh_run))
        if not (marks and marks[0]["mine"] and marks[0]["id"] == left["holder"]):
            continue                   # another session holds it, or a person assigned it by hand
        if n in (left.get("held") or []):
            _event(rep, "failed", job_for(root, i, base_branch).public(
                why=f"a stopped run held it until a person has looked (D-42); pulse release {n} --take frees it",
                log=""))
            continue
        stays = _release(root, repo, n, gh_run, {"id": left["holder"]})
        if stays:
            _event(rep, "failed", job_for(root, i, base_branch).public(why="a stopped run held it" + stays, log=""))
        else:
            rep["took"].append(n)


STOPS = tuple(s for s in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)) if s)


class Stopped(KeyboardInterrupt):
    """SIGTERM or SIGHUP: the run stops as on Ctrl-C and says which."""


def _exit(signum, frame):
    raise Stopped(signal.Signals(signum).name)     # so a closed terminal still runs the cleanup


def run(root: Path, cap=None, agent=None, dry_run=False, gh_run=state.gh, poll=5.0) -> dict:
    cfg = config.load(root)
    if not cfg["verify"]:      # the tests gate and the RED check need it; no PR goes out untested
        raise state.StateError('no verify command: set verify = "<the command that runs your tests>" in '
                               '.pulse/config.toml (pulse setup --verify ...)')
    repo, login = state.repo(root, run=gh_run), state.me(root, run=gh_run)
    spec, limit = agent or cfg["agent"], cap or cfg["cap"]
    slots = _slots(spec, limit, cfg)
    base_branch = cfg["base_branch"] or config.default_branch(root)
    common = config.pulse_dir(root)
    rep = {"agent": spec, "level": cfg["parallel"], "started": [], "planned": [], "done": [],
           "failed": [], "limited": [], "skipped": [], "stopped": [], "discovered": [], "merged": [],
           "sync_error": "", "took": [], "unclean": [], "integration": None, "items": {}, "elsewhere": [],
           "report": "" if dry_run else str(common / "go" / "report.json"),
           "run": {"pid": os.getpid(), "started": _now(), "ended": None, "stopped": ""}}
    jobs: dict = {}
    tried: set = set()         # one plan and one build per item and run: nothing loops
    spent: set = set()         # agents at their usage limit
    kept: dict = {}            # planned items whose claim goes on into their build: n -> its planning job
    alive: dict = {}           # n -> when a phase of #n that runs long last beat
    from pulse import map as pmap      # the map imports this module
    life = pmap.SILENT / 3     # a phase keeps a sign of life this often, so no map calls it silent (D-43)
    who = state.run_holder()
    env = {**os.environ, "PULSE_HOLDER": json.dumps(who)}
    handlers = {}
    last, read = None, True    # read reads the board in the next round: a slot came free
    lock, left = (None, {}) if dry_run else _lock(common)
    if not dry_run:
        handlers = {s: signal.signal(s, _exit) for s in STOPS[1:]}
    try:
        if not dry_run:
            if left.get("holder"):
                _take_over(root, repo, login, left, gh_run, rep, base_branch)
            _note(lock, {"pid": os.getpid(), "holder": who["id"], "groups": {}})
            _save(rep)
            try:               # merges since the last run: close what was merged, retarget stacks
                items = state.load(root, repo, run=gh_run, fresh=True)
                rep["merged"] = state.sync_merged(root, repo, items, run=gh_run)
                _tidy(root, {i["number"] for i in items} - set(rep["merged"]), rep)
            except state.StateError as e:
                rep["sync_error"] = str(e)
            else:
                try:           # one run per clone; a run of mine in another clone shares through claims
                    rep["elsewhere"] = _elsewhere(repo, items, login, {who["id"], left.get("holder")}, gh_run)
                except (state.StateError, ValueError):
                    pass       # a look that failed warns nobody; the claims still decide
                if rep["elsewhere"]:
                    print("pulse go: another pulse go run of " + login + " keeps " + ", ".join(
                        f"#{e['number']} ({e['phase']})" for e in rep["elsewhere"]) + " alive; this run "
                        "starts too, and the claims decide", file=sys.stderr)
        while True:          # at the start and whenever a slot came free: read the board, fill the slots (F5.09)
            try:               # fresh in a run: sync_merged read it
                items = state.load(root, repo, run=gh_run, fresh=dry_run) if read else last
            except state.StateError:
                if last is None:
                    raise
                items = last           # gh failed for a moment: go on with what it said last
            last, read = items, False
            free = {a: n - sum(j.agent == a for j in jobs.values()) for a, n in slots.items() if a not in spent}
            ready.fetch(root)          # what the other clones planned and hold, at most every 30 s (D-10)
            found = ready.plans(root)
            # what this run holds is held on a board read before its claims too: a round without a read
            ramped = [dict(i, assignees=[]) if i["number"] in kept else
                      dict(i, assignees=[login]) if i["number"] in jobs else i for i in items]
            gates = ready.gates(root, ramped, cfg, found)
            files = dispatch.plan_files(root, found)
            r = dispatch.ramp(ramped, files, min(limit, sum(slots.values())),
                              login, level=cfg["parallel"], gates=gates)
            plans = {n: p["path"] for n, p in found.items()}
            specs = {i["number"]: i.get("spec") for i in items}
            unplanned = [i for i in dispatch.order(items) if gates.get(i["number"]) == "needs a plan"]
            drafts = [i for i in items if (i.get("pr") or {}).get("draft") and login in i["assignees"]
                      and _branch_of(root, i["number"]) == i["pr"]["branch"]]
            for i in items:            # a PLAN that fails P1 to P5 waits for a person: say so once a run
                if gates.get(i["number"], "").startswith("plan: ") and ("plan", i["number"]) not in tried:
                    tried.add(("plan", i["number"]))
                    _event(rep, "skipped", job_for(root, i, base_branch).public(why=gates[i["number"]]))
            for kind, item in [("resume", i) for i in drafts] + [("build", i) for i in r["next"]] + \
                    [("plan", i) for i in unplanned]:
                n = item["number"]
                if n in jobs or (kind, n) in tried:
                    continue
                a = max(free, key=free.get, default=None)      # most free slots; a tie goes to the first named
                if a is None or free[a] < 1:
                    break
                job = job_for(root, item, base_branch)
                job.agent, job.env, job.open_ = a, env, {i["number"] for i in items}
                if dry_run:
                    if kind == "resume" and not _takes_up(root, repo, item, job, gh_run)[0]:
                        continue       # the run leaves it too: nothing new since its gates, held, or a session's
                    tried.add((kind, n))
                    free[a] -= 1
                    rep["started"].append(job.public(agent=a, phase=kind))
                    continue
                if kind == "resume":
                    tried.add((kind, n))           # one look per run at a draft
                    ok, why = _take(root, repo, item, job, gh_run, who)
                else:                  # planned in this run: a second claim puts the build on its mark
                    ok, why = _claim(root, repo, item, gh_run, who, kind, files.get(n) if kind == "build" else None)
                if not ok:             # the next round tries again: its holder may give it back
                    if why:
                        _event(rep, "skipped", job.public(why=why))
                    continue           # a planned one stays in kept and goes back below
                kept.pop(n, None)
                tried.add((kind, n))
                jobs[n] = job          # from the claim on: a stop gives it back (finally)
                job.phase = kind
                log = ""
                try:       # a start that fails (git, a gone worktree, a missing agent) must not stop the others
                    why = _start(root, cfg, cfg["agents"][a], job, plans, specs, common / "go", phase=kind)
                    if not (why or job.proc):      # a draft whose spec tests were bent: its text says so
                        _finish(root, repo, job, gh_run, rep, who, cfg)
                        del jobs[n]
                        continue
                except Exception as e:
                    why, log = _trouble(job, e, common / "go"), _log_path(job, common / "go")
                    if isinstance(e, FileNotFoundError):      # the agent's command itself is missing
                        spent.add(a)
                        free.pop(a, None)
                        why += f"; agent {a} is out of this run"
                if why:
                    why += _release(root, repo, n, gh_run, who, _handover(job, why)) or " (the claim went back)"
                    del jobs[n]
                    if job.log:
                        try:
                            job.log.close()
                        except OSError:
                            pass
                    _event(rep, "failed", job.public(why=why, log=log))
                    continue
                free[a] -= 1
                rep["started"].append(job.public(agent=a, phase=kind))
                if kind == "resume":           # the claim named its phase; a draft taken up starts at the tests
                    _beat(root, repo, job, gh_run, who)
            for n, planned in kept.items():     # planned, but the ramp does not let it build now
                stays = _release(root, repo, n, gh_run, who)
                if stays:
                    _event(rep, "failed", planned.public(why="planned" + stays, log=planned.log.name))
            kept.clear()
            if dry_run or not jobs:
                break
            freed = False
            while not freed:
                due = min(max(j.started, alive.get(n, 0)) for n, j in jobs.items()) + life
                for job in _wait(jobs, cfg["agent_timeout"] * TIMEOUT_UNIT, poll, due):
                    try:
                        finished = _advance(root, repo, cfg, job, gh_run, rep, common / "go", who, spent)
                    except Exception as e:      # one item's failure must not stop the others; Ctrl-C and SIGTERM do
                        why = (f"{_trouble(job, e, common / 'go')} (the claim stays and holds a slot, so no run "
                               f"retries it before you looked; pulse release {job.number} --take)")
                        _event(rep, "failed", job.public(why=why, log=_log_path(job, common / "go")))
                        finished = True
                    if finished:
                        del jobs[job.number]
                        _group(common / "go", job.number, None)
                        freed = True
                        read = read or not job.kept        # a planned item going on into its build frees none
                        if job.kept:
                            kept[job.number] = job
                        if job.limited:
                            tried.discard((job.phase, job.number))      # another agent may take it in this run
                    else:                      # its next phase started
                        _beat(root, repo, job, gh_run, who)
                for n, job in jobs.items():    # a phase that runs long: its beat, one per `life`
                    if time.time() - max(job.started, alive.get(n, 0)) >= life:
                        _beat(root, repo, job, gh_run, who)
                        alive[n] = time.time()
        if not dry_run:        # two PRs or more wait for a merge: do they merge together, do the tests pass then?
            try:
                prs = [i for i in state.load(root, repo, run=gh_run) if i.get("pr") and not i["pr"]["draft"]]
                rep["integration"] = integrate(root, prs) if len(prs) > 1 else None
            except state.StateError as e:
                rep["integration"] = {"error": str(e)}
            _save(rep)
    except KeyboardInterrupt as e:     # Ctrl-C, SIGTERM, SIGHUP: the claims go back, the report stays
        rep["run"]["stopped"] = e.args[0] if isinstance(e, Stopped) else "SIGINT"
    finally:
        # a second Ctrl-C or SIGTERM must not cut the cleanup short: agents would work on unclaimed
        quiet = {} if dry_run else {s: signal.signal(s, signal.SIG_IGN) for s in STOPS}
        stop = f"the run was stopped ({rep['run']['stopped']})" if rep["run"]["stopped"] else \
            "the run ended on an error"
        for job in jobs.values():
            if job.proc:
                _stop(job.proc)
            if job.phase == "spec tests":
                _git(root, "worktree", "remove", "--force", str(_scratch(common / "go", job.number)))
            _event(rep, "stopped", job.public(phase=job.phase, log=_log_path(job, common / "go"),
                                              why=_release(root, repo, job.number, gh_run, who,
                                                           _handover(job, stop)).strip(" ()")
                                              or "the claim went back"))
        for n, planned in kept.items():
            _release(root, repo, n, gh_run, who, _handover(planned, stop))
        if lock:
            rep["run"]["ended"] = _now()
            _save(rep)
            if _noted(lock).get("pid") == os.getpid():
                _note(lock, {})        # a clean end: nothing for the next start to take over
            lock.close()
            try:
                (common / "go.pid").unlink()
            except FileNotFoundError:
                pass
        for s, h in {**quiet, **handlers}.items():
            signal.signal(s, h)
    return rep


def _order(items: list) -> list:
    """Items with an open PR, blockers before the items they block."""
    todo = {i["number"]: i for i in items if i.get("pr")}
    out = []
    while todo:
        ready = sorted(n for n, i in todo.items() if not set(i["blocked_by"]) & set(todo))
        ready = ready or [min(todo)]            # a cycle must not hang the check
        for n in ready:
            out.append(todo.pop(n))
    return out


def integrate(root: Path, items: list) -> dict:
    """The items' open branches merged in dependency order in a scratch worktree, and verify run
    there: a clash between parallel work shows before anyone merges."""
    cfg = config.load(root)
    base = cfg["base_branch"] or config.default_branch(root)
    scratch = config.pulse_dir(root) / "integrate"
    order = _order(items)
    _git(root, "worktree", "remove", "--force", str(scratch))
    ready.net_git(root, "fetch", "-q", "origin", base, *[i["pr"]["branch"] for i in order])
    _git(root, "worktree", "add", "--detach", str(scratch), f"origin/{base}", check=True)
    rep = {"base": base, "merged": [], "conflict": None, "verify": None}
    try:
        for i in order:
            br = i["pr"]["branch"]
            m = _git(scratch, "-c", "user.name=pulse", "-c", "user.email=pulse@localhost",
                     "merge", "--no-ff", "--no-edit", f"origin/{br}")
            if m.returncode:
                _git(scratch, "merge", "--abort")
                rep["conflict"] = {"branch": br, "after": list(rep["merged"])}
                break
            rep["merged"].append(br)
        if rep["conflict"] is None and cfg.get("verify"):
            try:               # at the end of a run nobody watches: a hanging test must not keep it
                v = subprocess.run(cfg["verify"], shell=True, cwd=scratch, capture_output=True, text=True,
                                   errors="replace", timeout=cfg["agent_timeout"] * TIMEOUT_UNIT)
                ok, out = v.returncode == 0, v.stdout + v.stderr
            except subprocess.TimeoutExpired:
                ok, out = False, f"no end within {cfg['agent_timeout']} min"
            rep["verify"] = {"command": cfg["verify"], "ok": ok, "tail": out.strip().splitlines()[-5:]}
    finally:
        _git(root, "worktree", "remove", "--force", str(scratch))
    return rep
