---
title: /pulse-build
description: Implement one item test-first against its PLAN, capture bugs, write tests for existing code, and close only with fresh evidence.
---

# /pulse-build

`/pulse-build` (in Codex `$pulse:pulse-build`) implements one item: test first, the smallest complete change, and nothing is done until the evidence says so.

## /pulse-build or pulse go

`/pulse-build <n>` is the way one item gets built, in your session, with you watching and answering when something comes up. [`pulse go`](./pulse-go) is a script that runs this same discipline for every ready item at once: it claims each item, gives it its own worktree, starts one headless agent per item, checks itself that the spec tests failed before the code, and runs the same gates after each build ([the chain](../concepts/verification-gates#the-chain-after-the-build)). Build one item together: `/pulse-build <n>`. Build everything the ramp has released: `pulse go` in your own terminal.

## Start

`pulse status <n>` gives the item, its spec, and its PLAN. `pulse claim <n>` assigns it to this session (exit code 1 names why: the item is closed, not approved, or blocked, another item holds one of its files, another person or another of your sessions holds it, or a claim in the same moment won). The claim fetches from origin and names the start point: the item's branch on origin when an earlier holder or a planning run pushed it, else a new `<type>/<n>-<slug>` from `origin/<base>`, never from the local base branch; a feature whose one blocker has a ready pull request that is not merged yet branches from the blocker's branch instead, and its PR targets that branch. Without a PLAN, the build runs the [planning step](./pulse-plan) first and then continues.

## Build

The spec tests come first: one per requirement from the PLAN's wave 1, run red once, and committed alone. From then on they are frozen; the code changes, never these tests.

Then the PLAN's tasks, task by task, wave by wave (the wave's checks before the next wave). Where the agent can start subagents, each task of a wave goes to a subagent of its own, in parallel in the same worktree; their results are committed one after another, and the wave's check runs once. For every task:

1. **Reuse first.** Search for an existing helper, pattern, or dependency before writing anything new.
2. **Test first.** State the expected failure, run the test, quote the actual output. Then the minimal code that passes. Then refactor while green. A test that passes at once, or fails for another reason, is a failed RED step.
3. **Stay in budget.** A task that runs over twice its diff budget gets one line in the PLAN's change log.
4. **Run the task's check** before the next task: the tests the task touches, not the whole suite.

After each step, run the tests that step affects; `verify`, the whole suite, runs once, before the gates, and again only after a change.

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
| Tests and build pass | one run of the configured `verify` (the PLAN's verify commands only when there is none), exit 0 |
| Every requirement is proven | each spec test is green and unchanged since it was committed |
| New code is reachable | a caller outside its own file and outside tests, see [Reachability by stack](../reference/reachability-by-stack) |
| The feature works for its user | every Activation Path entry matches an identifier in the code |
| A bug is fixed | the regression test failed without the fix and passes with it |

Then, without asking in between: the commit (`Refs: #<n>`) and three gates in order:

1. **Tests:** that one run of the configured `verify`, exit 0: the evidence above, not a second run.
2. **Review and security audit** in one fresh session, never the one that built the item: a subagent (without subagents, a headless session) gets the review brief and the audit's ([/pulse-audit](./pulse-audit), scope branch against the base, the scan run by the subagent itself) and writes `REVIEW.md` and `AUDIT.md` with its `Coverage:` line, each with its own verdict. The audit blocks while a Critical or High finding is open. An item whose spec or PLAN has `risk: [security]` gets the same one session. `REVIEW.md` and `AUDIT.md` are deleted before the session starts and after their text went into the pull request; neither is committed.

A red gate gets a fix, test first, and after it the tests run again and only the gates that were red; one fix round per item. Then one PR, `Closes #<n>`, against the base branch, with the state of the three gates, the review and audit reports, and a section `## Deviations from the PLAN` when the build departed from it. It is ready only when all three passed, each on the commit its table row names (a gate that stayed green after a fix did not run again), and a draft otherwise, naming what is open; a departure from the PLAN alone never makes it a draft. The merge is yours; after a merge on GitHub, the next `pulse go` closes the item, on any base branch. After the merge, a sweep over the PLAN's decisions for the ones worth a record. A stub left behind carries `FIXME(stub): <reason> -- see #<n>` naming an open item; `pulse check` finds the ones without.
