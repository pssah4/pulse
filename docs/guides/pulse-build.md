---
title: /pulse-build
description: Implement one item test-first against its Plan, capture bugs, write tests for existing code, and close only with fresh evidence.
---

# /pulse-build

`/pulse-build` (in Codex `$pulse:pulse-build`) implements one item: test first, the smallest complete change, and nothing is done until the evidence says so.

## /pulse-build or pulse go

`/pulse-build <n>` is the way one item gets built, in your session, with you watching and answering when something comes up. [`pulse go`](./pulse-go) is a script that runs this same discipline for every ready item at once: it claims each item, gives it its own worktree, starts one headless agent per item, checks itself that the spec tests failed before the code, and runs the same gates after each build ([the chain](../concepts/verification-gates#the-chain-after-the-build)). Build one item together: `/pulse-build <n>`. Build everything the backlog has released: `pulse go` in your own terminal.

## Start

`pulse status <n>` gives the item, its spec, Plan, publication branch and blockers. `pulse claim <n>` claims it for this session; exit code 1 names why it cannot: the item is closed, held or blocked, a file is reserved elsewhere, another session owns it, or a simultaneous claim won. A person requests handoff with `pulse release --take <n>` in their own terminal. Continue only after the writer stopped and its work was preserved.

Use the start point the claim names: continue the published item branch or create `<type>/<n>-<slug>` from the fetched `refs/remotes/origin/<base>`, never from the local base branch. Unpublished work stays in its original worktree. A dependent waits for its blocker's integration and never branches from that unfinished work. Without a Plan, run [planning](./pulse-plan), validate with `pulse check --plan <path>`, commit and publish it, then continue the authorized build.

## Build

The spec tests come first: one per requirement from the Plan's wave 1, run red once, and committed alone. From then on they are frozen. A necessary correction first changes the requirement, records why in the Plan change log and shows the exact test diff before any test edit.

Then the Plan's tasks, task by task, wave by wave (the wave's checks before the next wave). Where the agent can start subagents, each task of a wave goes to a subagent of its own, in parallel in the same worktree; their results are committed one after another, and the wave's check runs once. For every task:

1. **Reuse first.** Search for an existing helper, pattern, or dependency before writing anything new.
2. **Test first.** State the expected failure, run the test, quote the actual output. Then the minimal code that passes. Then refactor while green. A test that passes at once, or fails for another reason, is a failed RED step.
3. **Stay in budget.** A task that runs over twice its diff budget gets one line in the Plan's change log.
4. **Run the task's check** before the next task: the tests the task touches, not the whole suite.

After each step, run targeted checks. Under `pulse go`, the supervisor owns one full `verify` of the completed result; agents run affected tests and additional Plan checks it does not cover. Repeat checks only when a relevant change requires fresh evidence. Push the item branch after each commit; supervised agents leave publication to the runner. Release inactive claims while retaining the branch, worktree and evidence.

## When something breaks

Root cause before any fix: read the whole error, reproduce it, check what changed, trace the bad value backwards, then test one hypothesis at a time. After three failed fixes, stop: that is a design problem, not a bug, and it goes to the user.

## When the work learns something

| Discovery | What happens |
|---|---|
| A new bug | stop, write a fix spec and register it ("Discovered in #n"), root cause, then fix it test-first |
| A decision is wrong | stop, update the decision or the Plan, then continue |
| The spec has a gap | stop, amend the spec, re-run the coverage gate |
| An unplanned user-facing capability | stop, ask for persona, job, and outcome one question at a time, write the spec, register it |

Each gets a line in the Plan's change log; the commit names every item it touched.

## Tests for existing code

Code without tests, coverage gaps after a build, and a red suite are build work too; ask with "write tests" or "the suite is red". New tests belong to an item (a feature, an improvement, or a fix), and the skill asks once which one if you did not say. A coverage report or a gap analysis alone needs no item.

1. **Read the project first:** its test framework and config, where tests live and how they are named, its mocking and assertion style. The tests adopt all of it; a new framework comes only when the project has none.
2. **Write in this order:** integration tests across modules (endpoints, database access, event flows, external services mocked at the boundary), then unit gaps (edge cases, error paths, boundaries), then a coverage report. Gaps are listed, not filled on their own. Code built without tests first gets its unit tests here too. Every test follows Arrange, Act, Assert and the FIRST principles, and mocks only external dependencies, never the unit under test.
3. **Run the suite in the same turn.** Green means 0 failures, 0 lint errors where lint runs in the suite, and coverage not below where it was. Otherwise each failure comes with its cause (code bug, wrong expectation, missing implementation) and one question: fix all, fix one by one with each fix shown first, change tests because the spec changed, or stop. The loop runs until the suite is green or you stop it.
4. **A test changes only with its requirement**, and only with all three: the success criterion amended with a one-line reason, the Plan change log naming the test path, and the test diff shown to you before the edit. "The test is inconvenient" is a code bug.
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
| Tests and build pass | one run of the configured `verify` (the Plan's verify commands only when there is none), exit 0 |
| Every requirement is proven | each spec test is green and unchanged since it was committed |
| New code is reachable | a caller outside its own file and outside tests, see [Reachability by stack](../reference/reachability-by-stack) |
| The feature works for its user | every Activation Path entry matches an identifier in the code |
| A bug is fixed | the regression test failed without the fix and passes with it |

Commit with `Refs: #<n>`, then run the gates without another routine permission question:

1. **Tests:** that one run of the configured `verify`, exit 0: the evidence above, not a second run.
2. **Review and security audit** run in one fresh session, also for `risk: [security]`. The reviewer receives the review brief and [/pulse-audit](./pulse-audit), scope branch against the base, and runs the scan itself. It writes separate `REVIEW.md` and `AUDIT.md` verdicts for the checked commit. A Critical or High audit finding blocks completion. The reports become result evidence and are not committed.

A red gate gets one fix round, test-first, followed by the checks that need fresh evidence. A result still red preserves its work and findings. Record deviations in the Plan change log and publish the item branch with its exact head, base, tests, review, audit and remaining findings. An interactive builder releases the item for `pulse go` to verify and record the shared result.

Regular checked results integrate automatically by default. Read the result and its evidence in the Map. If manual approval is configured, approve that head and base there or with `pulse approve <n>` in your own terminal. Both policies use the same evidence and version checks. This does not authorize destructive removal. Pulse integrates with normal hooks and a fast-forward remote update; completion follows proof that the result reached the shared base. A changed head or base needs revalidation. No pull request is involved.

After integration, sweep the Plan's decisions for those worth a record. A stub left behind carries `FIXME(stub): <reason> -- see #<n>` naming an open item; `pulse check` finds untracked stubs.