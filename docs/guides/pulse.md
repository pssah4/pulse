---
title: /pulse
description: The entry point. Where the work stands, what comes next, and which command fits.
---

# /pulse

`/pulse` reads the situation and recommends one next step. You decide.

## Where things stand

It runs `pulse status` and sums up in a few lines: what is ready, what is in progress and who holds it, what waits for you, what is failing, and what is blocked by what. If Pulse is not active in the repository, it says so and sets it up with you ([below](#set-up-go-and-the-map)).

## What comes next

The commands are spelled as in Claude Code, on this page and on the map. In Codex, type `$pulse:<name>` for `/<name>`, so `$pulse:pulse-ba` for `/pulse-ba`.

| Situation | Recommendation |
|---|---|
| Something waits for you (an open question, a red test) | that first |
| No method artifacts, an empty or new repository | [`/pulse-ba`](./pulse-ba) for the project BA |
| Code exists but no BA and no specs, or a project from the predecessor plugin | [`/pulse-realign`](./pulse-realign) |
| The project BA is a draft | `/pulse-ba` in Validation Mode |
| A new epic or feature is wanted | `/pulse-ba` for its item BA |
| A validated project BA or an item BA exists, no epics or features yet | [`/pulse-re`](./pulse-re): it commits the specs; the push, their docs PR, and the records come from `pulse new --spec`; then it commits and pushes what that wrote |
| Specs wait for approval ("not approved" in the ramp) | read each spec, then `pulse approve <n>`, or `a` in the map, means build it. It writes the approval and nothing else; [`pulse go`](./pulse-go) merges a spec not yet on the base branch into it first, through its docs PR, so nobody merges it on GitHub. `pulse approve` refuses a spec neither on the base branch nor in an open pull request (R1) and, for a feature, improvement, or fix, one on the base branch that breaks one of R2 to R6 (an epic needs R1 only) |
| An approved spec waits for its merge ("spec in PR #m: pulse go merges it" in the ramp) | `pulse go` in your own terminal merges the docs PR once every spec in it passes R1 to R6, it changes only `_devprocess/`, and its checks pass; the run names why it did not |
| Approved items whose spec does not pass `pulse check` (R1 to R6) | [`/pulse-re`](./pulse-re) on that spec |
| A PLAN waits for a person ("plan waits for you", "plan changed since plan ok", or "spec changed since plan ok" in the ramp) | read its goal, decisions, and risks; `pulse approve <n>`, or `a` in the map, approves the PLAN as origin has it |
| Approved items and free slots | [`pulse go`](./pulse-go) in your own terminal plans what has no PLAN and builds all of them, [`/pulse-build <n>`](./pulse-build) for one |
| A feature pull request is ready (tests, review, and audit passed) | read it, then `pulse approve <n>`, or `a` in the map, approves its merge at its head (gate 3); the next [`pulse go`](./pulse-go#gate-3-the-merge) merges it and closes the item |
| A draft feature pull request names a red gate | fix the findings on its branch test first and push them; then `pulse release <n>`: the next [`pulse go`](./pulse-go#given-back-with-code) runs the gates on it and marks it ready once all three pass |
| A pull request whose last commit has no review or no audit | the missing review and [audit](./pulse-audit) in a fresh subagent, as in [/pulse-build](./pulse-build), with the reports put into the pull request |
| A release is coming | [`/pulse-audit`](./pulse-audit) |

## New work without a kind

`/pulse` asks one question: a new feature, an improvement on an existing feature, or a fix? A new feature with an unclear problem goes to `/pulse-ba`, with a clear one to `/pulse-re`. Improvements and fixes go to `/pulse-build`.

## The V is a decision graph

Phases run forward by default and loop back when the work learns something: a bug found while building becomes a fix item ("Discovered in #n"), a design that proves wrong updates the decision or the PLAN, a requirement gap goes back to the spec. A loop back never re-runs later phases on its own; the item's spec records what was decided.

## Three gates

Pulse stops for you at three gates per item. `pulse approve <n>`, or `a` in the map, writes the approval the item waits for, and [`pulse go`](./pulse-go) acts on it:

| Gate | You approve | Then `pulse go` |
|---|---|---|
| 1 plan | the spec | merges its docs PR and plans the item |
| 2 build | the PLAN, as origin has it | builds it and runs tests, review, and audit |
| 3 merge | the ready pull request, at its head | merges it and closes the item |

Your own auto mode can pass a gate for your items; it is off until you switch it on ([Auto mode](./pulse-go#auto-mode)).

## Set up, go, and the map

`/pulse` also tells you, one paragraph each, how you set Pulse up, start `pulse go`, and work the live map. It runs [`pulse setup`](./pulse-setup) with your answers, which outside Herdr also adds the task "Pulse map" for VS Code, and on your yes it adds the `pulse` command and the Codex rules; switching Pulse off or out stays yours. In Herdr the live map opens beside each chat by itself. [`pulse go`](./pulse-go) plans and builds every approved item in parallel. You can start it in your own terminal or explicitly ask the Pulse skill to run it in a foreground TTY. Runner agents cannot start a nested runner. In the [live map](./pulse-map) you pick an item and press `a` for the approval it waits for. Your auto mode per gate is yours too: `pulse auto <gate> on` in your own terminal, or `1` `2` `3` in the map, lets your own `pulse go` pass that gate for your items without asking you ([Commands](../reference/commands#pulse-auto)). Every such step is yours: the agent names the key or the command for your own terminal and never takes it itself; the [Pulse guard](../concepts/parallel-work#levers-belong-to-a-person) refuses it when it tries.

## Commands

| Command | Does |
|---|---|
| `/pulse-ba` | business analysis: problem, users, scope |
| `/pulse-re` | epic, features, success criteria, registered items |
| `/pulse-build` | implementation, test first (planned first when it has no PLAN), bugs, tests for existing code |
| `/pulse-audit` | security audit: the third gate of every feature, or by hand with a chosen scope |
| `/pulse-realign` | take over existing code, or move a project from the predecessor plugin |

[Planning](./pulse-plan) runs as a step inside `/pulse-re`, for each feature, improvement, or fix you approve in its session (an epic gets no PLAN), and inside `/pulse-build` and `pulse go`; review and audit run inside `/pulse-build` and `pulse go`.

The `pulse` command line behind these commands is documented in [Commands](../reference/commands).
