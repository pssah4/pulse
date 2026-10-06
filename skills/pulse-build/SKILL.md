---
name: pulse-build
description: >
  Implements a ready item test-first against its Plan, captures bugs,
  writes tests for existing code, and closes only with fresh evidence. Use
  for "implement", "build", "code", "fix this bug", "I found a bug",
  "realize the plan", "write tests", "tests missing", "test coverage", "the
  suite is red", or /pulse-build <n>.
---

# Builder

You implement one item: test-first, the smallest complete change, and
nothing is done until the evidence says so.

## Start

1. `pulse status <n>`: title, stage (what it waits for), spec, Plan and
   the branch it lives on, blockers. Blocked items do not start. Without
   a number, take the first item `pulse status` shows as "starts next".
2. Claim it unless an orchestrator already did: `pulse claim <n>`. The
   claim belongs to this session. Exit code 1 prints why:
   - is closed: pick the next item from `pulse status`.
   - was held while claiming: stop; the person deferred the item or set a hold while the claim was in flight.
   - is on hold: keep the work paused; only the person resumes deferred work.
   - is blocked by an open item: that item comes first.
   - names a file another item holds (`<file> is in use by #m`): #m
     comes first; pick the next item.
   - is held by another person or another session, one of your own
     included: pick the next item. The refusal names the command that
     frees it. `pulse release --take <n>` hands another person's claim
     over after its writer stops and preserved work is recorded, also
     from a session of your own that has ended; `pulse claim --take <n>`
     would hold the item for the terminal it is typed in. Neither is
     yours to run: when the user wants the item, tell the person the
     release command for their own terminal, then claim again and start
     from the item branch on origin, where the last holder pushed the
     work or preserved worktree (the refusal names it): step 3.
   - went to a session that claimed at the same moment: pick the next
     item.
3. Start from the start point `pulse claim` names: the item's branch on
   origin (a planning run or an earlier holder pushed it), where you
   continue and merge `refs/remotes/origin/<base>` in first, else `refs/remotes/origin/<base>`,
   fetched by the claim, for a new branch `<type>/<n>-<slug>` (`feat`,
   `imp`, or `fix`). When it says the start point is not checked, the
   rest of the line says why: branch only after `pulse claim <n>`, run
   again, names a start point, and show the person that line while it
   does not. When it names a branch only this clone has, push that
   first. A dependent waits for its blocker to be integrated; it never
   branches from the blocker's unfinished work.

   When several items run in parallel, each gets its own worktree;
   `pulse go` sets each of its worktrees up with `setup` from the config,
   so its agents install no dependencies.
4. No Plan? Run the pulse-plan skill here first, validate it with
   `pulse check --plan <path>`, commit it alone and publish it on the
   same item branch. Continue the authorized build without an early
   approval stop. A supervised planner returns its result to the runner.
   Build only against the published spec and valid Plan.

## Spec tests first

Before the first task, write the spec tests of the Plan's wave 1: one test
per FR, named after its id (for example `test_fr_01_...`), from the EARS
line and its examples, at the boundary the Activation Path names. Run them
once: each fails for the stated reason. Commit them alone as
`test: spec tests for #<n>`. From then on they are frozen: change the code,
never these tests. If one is wrong, change its requirement first, record
why in the Plan change log, and show the exact test diff to the user
before editing it. A changed requirement is never permission to silently
weaken a test. `pulse go` sends a changed spec test back as a blocking
finding.

## Build, wave by wave

Go task by task, wave by wave: the tasks of one wave touch disjoint
files by construction, and when a wave is done, run its checks before
the next wave starts.

Where you can start subagents, give each task of a wave to a subagent
of its own, in parallel, in the same worktree: the files are disjoint
(P4). Commit their results one after another, then run the wave's check
once. Without subagents, go task by task as below.

For each task of the Plan:

1. **Reuse first.** Search for an existing helper, pattern, or
   dependency before writing anything new.
2. **Test first** (`references/tdd.md`): state the expected failure, run
   it, quote the output, then the minimal code that passes, then
   refactor green.
3. **Stay in budget.** A task that runs over twice its diff budget gets
   one Plan change-log line saying why.
4. **Run the task's check** before the next task: the tests the task
   touches, not the whole suite.
5. **Close it.** Make one commit for the finished task with the trailers
   `Pulse-Task: <n>`, the task's `#` in the Plan's Tasks table, and
   `Refs: #<n>` of the item. The map counts these as "Plan k/n"; the
   gates never read them.

After each step, run the tests that step affects, not the whole suite;
use targeted checks. Under `pulse go`, the supervisor runs the full
`verify` once on the completed result. Its build and fix agents run
targeted checks and additional Plan checks that `verify` does not cover,
then return the result to the supervisor. In an interactive build, run
`verify` once before review and audit, and again only after a relevant change.

Push the item branch after every commit (`git push -u origin <branch>`):
the team sees the work, and whoever takes the item over starts from it.

When this session stops before the item is done and will not go on
with it (the user ends the work, or it waits on another item): commit
what holds, push the item branch, and give the item back with
`pulse release <n>`: whoever takes it next goes on from that branch.

A session that learns it no longer holds the item (`pulse claim` or
`pulse release` names another holder) stops the work on it: it pushes
nothing of it, gives nothing back, and tells the person.

When something breaks unexpectedly: `references/debugging.md`. Root cause
before any fix; after three failed fixes, stop and question the design
with the user.

When the work learns something, stop the code edit and route it first:

- **Work that has to be built first** and is not in the Plan: one short
  title per line under `needs:` in the frontmatter of
  `_devprocess/plans/<n>-needs.md`. Commit and push it, and stop the
  build: `pulse go` makes each title a draft item this one waits for.
  With a person, tell them, then give the item back with
  `pulse release <n>`.
- **A new bug:** record it as under Bugs below, with "Discovered in
  #<n>". Fix it test-first on this branch with `Refs: #<n>, #<new>`. The
  result names both items and their evidence; completion follows integration.
- **A decision or a spec that no longer holds:** amend it within the
  authorized scope, add a Plan change-log line, revalidate and publish.
  Preserve frozen test boundaries. A headless session that cannot settle
  a necessary product decision preserves its work and reports it.

**The system map.** As the last task, update `_devprocess/SYSTEM-MAP.md`
where it exists (a build never creates it) when the item changes what it
describes: an entry point, data ownership, an invariant, or a quality
goal. The review blocks a diff that changes
one of these while the map stays silent. A rule for one area of the code
goes into the path-local AGENTS.md there.

**Stubs.** Code that deliberately returns a placeholder carries
`FIXME(stub): <reason> -- see #<n>` naming an open item. A stub without
an item is invisible; `pulse check` finds it.

## Bugs

**Found by the user, no fix wanted yet:** write the fix spec
`_devprocess/requirements/fixes/{slug}.md` from `templates/FIX-TEMPLATE.md`,
with the symptom and what is known about the cause, and `parent:` set;
`pulse number --apply` gives it its logical ID. Register a draft to obtain
the item number, publish on `fix/<n>-<slug>`, then attach the spec with
`pulse new fix "<symptom>" --parent <feature> --spec <path> --issue <n>`.
Commit and push its metadata changes. If the user requested a fix,
continue with the Plan and tests; a request to record it alone ends with
the published finding. There is no early spec approval or separate spec
merge.

**Fixing one:** a test that reproduces the bug comes first. Then the
regression cycle: the test passes with the fix, fails with the fix
reverted, passes again restored. Note the date in the fix spec's
"Regression test" section.

## Tests for existing code

Existing code without tests, coverage gaps after a build, and a red suite
are build work too. New tests belong to an item (a feature, an
improvement, or a fix); ask once which one if the prompt does not say.
Read-only work (a coverage report, a gap analysis) needs no item.

1. Read the project first: test framework and config, where tests live
   and how they are named, the mocking and assertion style. Adopt it; add
   no framework unless the project has none.
2. Write in this order: integration tests across modules (endpoints, DB
   access, event flows, external services mocked at the boundary), then
   unit gaps (edge cases, error paths, boundaries), then a coverage report
   against the targets; gaps are listed, not filled on their own. Code
   built without TDD gets its unit tests here as well.
   `references/test-checklist.md` holds the rules per test and the
   targets, `references/test-anti-patterns.md` what to avoid.
3. Run the suite in this turn. Green means 0 failures, 0 lint errors when
   lint runs in the suite, coverage not below where it was. Otherwise
   report each failure with its cause (code bug, wrong expectation,
   missing implementation) and ask: fix all, fix one by one with each fix
   shown first, change tests because the spec changed, or stop. Loop until
   green or until the user stops.
4. A test changes only with its requirement, and only with all three: the
   success criterion amended with a one-line reason, the Plan change log
   naming the test path, and the test diff shown to the user before the
   edit. "The test is inconvenient" is a code bug.
5. Commit `test: <what>` with `Refs: #<n>`; the body names accepted
   coverage gaps with their reason, deferred cases, and flaky patterns.

## Temporary files

A file you write only to find something out is temporary: a
reproduction script, a probe, a throwaway check, a one-off fixture or
one-off sample data, a proof-of-concept harness, scratch output saved
from a test run. Write it under `_devprocess/temp/testing/`, never into
the project's test directories or the repository root, and never commit
it. Give it a name the test runner does not collect, for example
`probe_<topic>.py` (never `test_*.py` or `*.test.ts`), and run it by
path: a bare `pytest` collects a file named like a test there, even
when the folder is ignored. Delete it once it has served its purpose,
at the latest before the handoff.

When `_devprocess/temp/` is not ignored yet, add it to
`.git/info/exclude` before the first file: that holds for this clone,
needs no commit, and changes nothing in the working tree. From the
repository root (`--git-path` finds the file from a linked worktree
too):

```bash
git check-ignore -q _devprocess/temp/testing/x || printf '\n_devprocess/temp/\n' >> "$(git rev-parse --git-path info/exclude)"
```

This rule deletes no test of the project. Spec tests (one per
requirement, written first and frozen), regression tests of fixed bugs,
the suite's unit and integration tests, and the fixtures and data they
read are permanent and stay. A reproduction that becomes a fix's
regression test moves into the suite and is permanent from then on;
everything else temporary is deleted.

## Done

In a supervised build, finish the assigned phase after its targeted
checks and report the result. The runner owns the full verification,
review, audit, publication, and integration. Do not repeat those phases in its agent.
The following completion evidence and gates apply to the supervisor or
to an interactive build that owns the whole item.

Nothing closes on a claim. Before calling the item done, in this turn:

| Claim | Evidence |
|---|---|
| Tests and build pass | one run of the configured `verify` (`.pulse/config.toml`; the Plan's verify commands only when there is none), exit 0, 0 failures |
| Every requirement is proven | each FR's spec test is green and unchanged since `test: spec tests for #<n>` |
| New symbols are reachable | a caller outside the definition file and outside tests (`references/reachability.md`) |
| Feature works for its user | every Activation Path entry matches an identifier in the code |
| Bug fixed | the red-green regression cycle ran |

Then run, without asking between the steps, the gates in this order.
There is one fix round per item (test first, commit), followed by tests
and the red gates. Green review or audit evidence may carry to a new
commit only when its Git tree is identical. If contents change, rerun
both review and audit.
A gate still red preserves the result and names the open findings.

1. Plan change log: deviations, if any. Commit `feat|fix|refactor: <what
   and why>` with `Refs: #<n>`.
2. **Tests:** that one run of the configured `verify`, exit 0,
   0 failures: the evidence "Tests and build pass" above, not a second
   run.
3. **Review and security audit** in one fresh session, also with
   `risk: [security]`, never in this one: it built the item. Give a subagent both briefs,
   `references/review.md` and the pulse-audit skill, section "In the
   chain" (scope branch against the base); without subagents, start one
   headless (`claude -p`, `codex exec`). Delete a `REVIEW.md` or
   `AUDIT.md` at the worktree root before it starts: it writes both there
   anew, each with its own verdict; the audit blocks while a Critical or
   High finding is open. Neither report is committed:
   preserve their text with the result's evidence and return their paths
   to the supervisor. After a fix, rerun the checks that need fresh
   evidence; every verdict names the commit it checked.
4. Publish the item branch and result summary: exact head and base,
   tests, review, audit, remaining findings and deviations from the Plan.
   The runner records the shared result after its gates. An interactive
   builder publishes and releases the item so `pulse go` can verify and
   record it. Release inactive claims while retaining work and evidence.
   When manual approval is explicitly configured and a verified result is current,
   tell the person `pulse approve <n>`
   in their terminal or `a` in the Map. That final approval binds head and
   base. Pulse checks it afresh, integrates with normal hooks and a
   fast-forward-only remote update, then records completion. A changed
   head or base needs revalidation and a new approval. The default automatic
   final policy uses the same gates and bindings; the agent never
   changes that person-owned setting.

   If the project's own merge procedure already published this result,
   tell the person to run `pulse done <n> --merge <full-merge-sha>` in
   their terminal. It confirms that exact result and closes its record
   through Pulse. Missing bound evidence gets the same command with
   `--verify`: tests and a fresh review/audit only, without another
   Plan, build, fix or merge. Existing local reports alone are not gate
   evidence. Release inactive claims first; `done` cannot take another
   writer's claim and remains a person-only command.

5. After integration, sweep the Plan's decisions: the ones with a
   `read-when` a future agent will hit become decision records
   (the pulse-plan skill, kind `post-hoc`).
