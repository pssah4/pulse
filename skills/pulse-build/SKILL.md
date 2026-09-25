---
name: pulse-build
description: >
  Implements a ready item test-first against its PLAN, captures bugs,
  writes tests for existing code, and closes only with fresh evidence. Use
  for "implement", "build", "code", "fix this bug", "I found a bug",
  "realize the plan", "write tests", "tests missing", "test coverage", "the
  suite is red", or /pulse-build <n>.
---

# Builder

You implement one item: test-first, the smallest complete change, and
nothing is done until the evidence says so.

## Start

1. `pulse show <n>`: title, stage (what it waits for), spec, PLAN and
   the branch it lives on, blockers. Blocked items do not start. Without
   a number, take the first item `pulse status` shows as "starts next";
   the ramp follows the team's order.
2. Claim it unless an orchestrator already did: `pulse claim <n>`. The
   claim belongs to this session. Exit code 1 prints why:
   - is closed: pick the next item from `pulse status`.
   - is not approved: ask the user whether to build it. Its spec must be
     merged into the base branch first (the user merges its pull
     request); on the user's yes, after that merge, run
     `pulse approve <n>` and claim again. Never approve on your own.
   - is blocked by an open item: that item comes first.
   - is held by another person or another session, one of your own
     included: pick the next item. The refusal names the command that
     frees it; run that only on the user's yes. `pulse release <n> --take`
     hands another person's claim over (their assignee and marks go, a
     comment names who did it), then claim again. `pulse claim <n> --take`
     takes over from a session of your own that has ended. After either,
     start from the item branch on origin, where the last holder pushed
     the work (the refusal names it): step 3.
   - went to a session that claimed at the same moment: pick the next
     item.
3. Branch `<type>/<n>-<slug>` from the base branch in `.pulse/config.toml`
   (`feat`, `imp`, or `fix`). When that branch is on origin already (a
   planning run or an earlier holder pushed it, `pulse show` names it),
   continue on it and merge the current base in first. A feature whose
   one blocker has a ready pull request but is not merged yet branches
   from the blocker's branch instead, and its PR targets that branch.
   When several items run in parallel, each gets its own worktree.
4. No PLAN? A trivial bug takes the hotfix lane
   (`references/hotfix-lane.md`); for anything else run the pulse-plan
   skill in this session first, then continue here without asking. A PLAN that
   waits for a person (`manual`, a risk flag, effort L, or `needs:`):
   show the user its goal, decisions, risks, and files, keep the claim
   and wait for `pulse approve-plan <n>`. Nothing is built before it.

## Spec tests first

Before the first task, write the spec tests of the PLAN's wave 1: one test
per FR, named after its id (for example `test_fr_01_...`), from the EARS
line and its examples, at the boundary the Activation Path names. Run them
once: each fails for the stated reason. Commit them alone as
`test: spec tests for #<n>`. From then on they are frozen: change the code,
never these tests. If one is wrong, stop and route it as a requirements
discovery (`references/mid-course.md`); `pulse go` sends a changed spec
test back as a blocking finding.

## Build, wave by wave

At `parallel = max` (see `.pulse/config.toml`), the tasks of one wave run
at the same time: one subagent per task in this worktree, each told its
task, its files, and its check; they touch disjoint files by
construction. When the wave's subagents are done, run the wave's checks,
then start the next wave. At `items` or `off`, go task by task.

For each task of the PLAN:

1. **Reuse first.** Search for an existing helper, pattern, or
   dependency before writing anything new.
2. **Test first** (`references/tdd.md`): state the expected failure, run
   it, quote the output, then the minimal code that passes, then
   refactor green.
3. **Stay in budget.** A task that runs over twice its diff budget gets
   one PLAN change-log line saying why.
4. **Run the task's check** before the next task.

Push the item branch after every commit (`git push -u origin <branch>`):
the team sees the work, and whoever takes the item over starts from it.

When this session stops before the item is done and will not go on
with it (the user ends the work, or it waits on another item): commit
what holds, push the item branch, and give the item back with a note
that stays on the item for whoever takes it next:
`pulse release <n> --note "<why>; the work is on origin/<branch>"`.

When something breaks unexpectedly: `references/debugging.md`. Root cause
before any fix; after three failed fixes, stop and question the design
with the user.

When the work learns something (a new bug, a wrong decision, a spec gap,
an unplanned user-facing capability): `references/mid-course.md`. Stop,
route it, log it, then continue.

**Stubs.** Code that deliberately returns a placeholder carries
`FIXME(stub): <reason> -- see #<n>` naming an open item. A stub without
an item is invisible; `pulse check` finds it.

## Bugs

**Found by the user, no fix wanted yet:** write the fix spec
`_devprocess/requirements/fixes/{slug}.md` from `templates/FIX-TEMPLATE.md`,
with the symptom and what is known about the cause. Commit it on a docs
branch from the base branch and push it, then register it:
`pulse new fix "<symptom>" --parent <feature> --spec <path>`. Commit what
it wrote, push again, and open a pull request into the base branch. Ask
whether to fix it now; on the user's yes the user merges that pull
request, then run `pulse approve <n>` and build it here.

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
   success criterion amended with a one-line reason, the PLAN change log
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

Nothing closes on a claim. Before calling the item done, in this turn:

| Claim | Evidence |
|---|---|
| Tests and build pass | the PLAN's verify commands, exit 0, 0 failures |
| Every requirement is proven | each FR's spec test is green and unchanged since `test: spec tests for #<n>` |
| New symbols are reachable | a caller outside the definition file and outside tests (`references/reachability.md`) |
| Feature works for its user | every Activation Path entry matches an identifier in the code |
| Bug fixed | the red-green regression cycle ran |

Then, without asking between the steps, the gates in this order; a red
gate gets a fix (test first, commit), and after every fix the gates start
again at 1. At most two fix rounds per gate.

1. PLAN change log: deviations, if any. Commit `feat|fix|refactor: <what
   and why>` with `Refs: #<n>`.
2. **Tests:** the `verify` command from `.pulse/config.toml` (or the
   PLAN's verify commands), exit 0, 0 failures.
3. **Review** in a fresh session (the pulse-review skill, scope branch), never
   in this one: it built the item. Where the tool has subagents, give one
   the brief from `pulse review <n>` and let it write `REVIEW.md`, then
   run `pulse review <n> --record`; otherwise `pulse review <n> --run`.
4. **Security audit** of the branch in a fresh session (`/pulse-audit`,
   scope branch against the base): the brief from `pulse audit <n>` and
   `pulse audit <n> --record`, or `pulse audit <n> --run`. It blocks
   while a Critical or High finding is open.
5. Push and open one PR for the feature: `gh pr create --base <base
   branch, or the blocker's branch when stacked>`, body "Closes #<n>",
   the state of the three gates, the review and audit reports, and
   `## Deviations from the PLAN` when the build departed from it. Ready
   when all three passed on the last commit; only a red gate makes it
   `--draft`, naming what is open. Right after `gh pr create`, run
   `pulse review <n> --publish`: it puts the review and audit verdicts
   for the last commit on the PR, so whoever takes the item over need
   not run them again. The merge is the user's; after it,
   the item closes (GitHub closes it on the default branch; on another
   base, the next `pulse status` or `pulse go` closes it).
6. After the merge, sweep the PLAN's decisions: the ones with a
   `read-when` a future agent will hit become decision records
   (the pulse-plan skill, kind `post-hoc`).
7. A new entry point updates the navigation it belongs to: the system
   map or the path-local AGENTS.md.
