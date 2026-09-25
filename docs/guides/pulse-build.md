---
title: /pulse-build
description: Implement one item test-first against its PLAN, capture bugs, write tests for existing code, and close only with fresh evidence.
---

# /pulse-build

`/pulse-build` (in Codex `$pulse:pulse-build`) implements one item: test first, the smallest complete change, and nothing is done until the evidence says so.

## /pulse-build or /pulse-go

`/pulse-build <n>` is the way one item gets built, in your session, with you watching and answering when something comes up. [`/pulse-go`](./pulse-go) is a script that runs this same discipline for every ready item at once: it claims each item, gives it its own worktree, starts one headless agent per item, checks itself that the spec tests failed before the code, and runs the same gates after each build ([the chain](../concepts/verification-gates#the-chain-after-the-build)). Build one item together: `/pulse-build <n>`. Build everything the ramp has released: `/pulse-go`.

## Start

`pulse show <n>` gives the item, its spec, and its PLAN. `pulse claim <n>` assigns it to this session (exit code 1 means another person or another of your sessions has it, or another item holds one of its files). The branch is `<type>/<n>-<slug>` from the base branch; a feature whose one blocker has a ready pull request that is not merged yet branches from the blocker's branch instead, and its PR targets that branch. Without a PLAN, a trivial bug takes the hotfix lane; for anything else the build runs the [planning step](./pulse-plan) first and then continues.

## Build

The spec tests come first: one per requirement from the PLAN's wave 1, run red once, and committed alone. From then on they are frozen; the code changes, never these tests.

Then the PLAN's tasks, wave by wave at `parallel = max` (one subagent per task, the wave's checks before the next wave), task by task otherwise. For every task:

1. **Reuse first.** Search for an existing helper, pattern, or dependency before writing anything new.
2. **Test first.** State the expected failure, run the test, quote the actual output. Then the minimal code that passes. Then refactor while green. A test that passes at once, or fails for another reason, is a failed RED step.
3. **Stay in budget.** A task that runs over twice its diff budget gets one line in the PLAN's change log.
4. **Run the task's check** before the next task.

## When something breaks

Root cause before any fix: read the whole error, reproduce it, check what changed, trace the bad value backwards, then test one hypothesis at a time. After three failed fixes, stop: that is a design problem, not a bug, and it goes to the user.

## When the work learns something

| Discovery | What happens |
|---|---|
| A new bug | stop, write a fix spec and register it ("Discovered in #n"), root cause, then fix it test-first |
| A decision is wrong | stop, update the decision or the PLAN, then continue |
| The spec has a gap | stop, amend the spec, re-run the coverage gate |
| An unplanned user-facing capability | stop, ask for persona, job, and outcome one question at a time, write the spec, register it |

Each gets a line in the PLAN's change log; the commit names every item it touched.

## Hotfix lane

A trivial bug may be fixed first and recorded right after when all five hold: at most 3 files, no new feature or dependency, no breaking change, under 15 minutes, an existing feature as parent. The regression test still comes first. When hotfixes pass 30% of an iteration, the lane has become a bypass and needs an improvement item of its own.

## Tests for existing code

Code without tests, coverage gaps after a build, and a red suite are build work too; ask with "write tests" or "the suite is red". New tests belong to an item (a feature, an improvement, or a fix), and the skill asks once which one if you did not say. A coverage report or a gap analysis alone needs no item.

1. **Read the project first:** its test framework and config, where tests live and how they are named, its mocking and assertion style. The tests adopt all of it; a new framework comes only when the project has none.
2. **Write in this order:** integration tests across modules (endpoints, database access, event flows, external services mocked at the boundary), then unit gaps (edge cases, error paths, boundaries), then a coverage report. Gaps are listed, not filled on their own. Code built without tests first gets its unit tests here too. Every test follows Arrange, Act, Assert and the FIRST principles, and mocks only external dependencies, never the unit under test.
3. **Run the suite in the same turn.** Green means 0 failures, 0 lint errors where lint runs in the suite, and coverage not below where it was. Otherwise each failure comes with its cause (code bug, wrong expectation, missing implementation) and one question: fix all, fix one by one with each fix shown first, change tests because the spec changed, or stop. The loop runs until the suite is green or you stop it.
4. **A test changes only with its requirement**, and only with all three: the success criterion amended with a one-line reason, the PLAN change log naming the test path, and the test diff shown to you before the edit. "The test is inconvenient" is a code bug.
5. **Commit** `test: <what>` with `Refs: #<n>`; the body names accepted coverage gaps with their reason, deferred cases, and flaky patterns.

| Coverage | Target | Minimum |
|---|---|---|
| Line | 85% | 70% |
| Branch | 80% | 65% |
| Function | 90% | 75% |

Targets in the project's `AGENTS.md`, `CLAUDE.md`, or the spec win over these defaults.

Reproduction scripts, probes, and one-off fixtures live under `_devprocess/temp/testing/` while in use, under names the test runner does not collect (`probe_<topic>.py`), and are deleted before the handoff. The project's tests are never temporary: spec tests, regression tests, and the suite's unit and integration tests stay.

## Done

Nothing closes on a claim:

| Claim | Evidence |
|---|---|
| Tests and build pass | the PLAN's verify commands, exit 0 |
| Every requirement is proven | each spec test is green and unchanged since it was committed |
| New code is reachable | a caller outside its own file and outside tests, see [Reachability by stack](../reference/reachability-by-stack) |
| The feature works for its user | every Activation Path entry matches an identifier in the code |
| A bug is fixed | the regression test failed without the fix and passes with it |

Then, without asking in between: the commit (`Refs: #<n>`) and three gates in order:

1. **Tests:** the `verify` command from `.pulse/config.toml`, or the PLAN's verify commands, exit 0.
2. **Review** in a fresh session, never the one that built the item ([review](./pulse-review), scope branch): a subagent gets the brief from `pulse review <n>` and writes `REVIEW.md`, then `pulse review <n> --record` keeps the verdict; without subagents, `pulse review <n> --run`.
3. **Security audit** of the branch in a fresh session ([/pulse-audit](./pulse-audit)): `pulse audit <n>` runs the scan and prints the brief, the subagent writes `AUDIT.md` with its `Coverage:` line, `pulse audit <n> --record` keeps the verdict; or `pulse audit <n> --run`. It blocks while a Critical or High finding is open.

A red gate gets a fix, test first, and after every fix the gates start again at the tests; at most two fix rounds per gate. Then one PR, `Closes #<n>`, against the base branch or the blocker's branch when stacked, with the state of the three gates, the review and audit reports, and a section `## Deviations from the PLAN` when the build departed from it. It is ready only when all three passed on the last commit, and a draft otherwise, naming what is open; a departure from the PLAN alone never makes it a draft. Right after opening it, `pulse review <n> --publish` puts the review and audit verdicts for the last commit on the PR, so whoever takes the item over in another clone need not run them again ([verdicts on the pull request](./pulse-review#verdicts-on-the-pull-request)). The merge is yours; when the PR went into a base other than the default branch, the next `pulse status` or `pulse go` closes the item. After the merge, a sweep over the PLAN's decisions for the ones worth a record. A stub left behind carries `FIXME(stub): <reason> -- see #<n>` naming an open item; `pulse check` finds the ones without.
