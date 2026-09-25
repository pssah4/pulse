---
title: /pulse
description: The entry point. Where the work stands, what comes next, and which command fits.
---

# /pulse

`/pulse` reads the situation and recommends one next step. You decide.

## Where things stand

It runs `pulse status` and sums up in a few lines: what is ready, what is in progress and who holds it, what waits for you, what is failing, and what is blocked by what. If Pulse is not active in the repository, it says so and offers [`/pulse-setup`](./pulse-setup) (in Codex `$pulse:pulse-setup`).

## What comes next

The commands are spelled as in Claude Code, on this page and on the map. In Codex, type `$pulse:<name>` for `/<name>`, so `$pulse:pulse-ba` for `/pulse-ba`.

| Situation | Recommendation |
|---|---|
| Something waits for you (an open question, a red test) | that first |
| No method artifacts, an empty or new repository | [`/pulse-ba`](./pulse-ba) for the project BA |
| Code exists but no BA and no specs, or a project from the predecessor plugin | [`/pulse-realign`](./pulse-realign) |
| The project BA is a draft | `/pulse-ba` in Validation Mode |
| A new epic or feature is wanted | `/pulse-ba` for its item BA |
| A validated project BA or an item BA exists, no epics or features yet | [`/pulse-re`](./pulse-re): it commits and pushes the specs, registers them with `pulse new --spec`, commits and pushes what that wrote, and opens a pull request |
| Specs wait for approval ("not approved" in the ramp) | read each spec, merge the pull request that carries it, then `pulse approve <n>` means build it; `pulse approve` refuses before the merge (R1) and, for a feature, improvement, or fix, while the spec there breaks one of R2 to R6 (an epic needs R1 only) |
| Approved items whose spec does not pass `pulse check` (R1 to R6) | [`/pulse-re`](./pulse-re) on that spec |
| A PLAN waits for a person ("plan waits for you" in the ramp) | read its goal, decisions, and risks; `pulse approve-plan <n>` |
| Approved items and free slots | [`/pulse-go`](./pulse-go) plans what has no PLAN and builds all of them, [`/pulse-build <n>`](./pulse-build) for one |
| A feature pull request is ready (tests, review, and audit passed) | read it and merge it: the last stop |
| A draft feature pull request names a red gate | fix the findings on its branch test first and push them; the next [`pulse go`](./pulse-go#a-draft-taken-up) takes up a draft that a run under your login holds, repeats the gates, and marks it ready once all three pass |
| A pull request whose last commit has no review or no audit | the missing [review](./pulse-review) and [audit](./pulse-audit), each in a fresh session (`pulse review <n> --run`, `pulse audit <n> --run`) |
| The last repository review is older than two weeks | a [repository review](./pulse-review#repository-mode) |
| A release is coming | [`/pulse-audit`](./pulse-audit) |

## New work without a kind

`/pulse` asks one question: a new feature, an improvement on an existing feature, or a fix? A new feature with an unclear problem goes to `/pulse-ba`, with a clear one to `/pulse-re`. Improvements and fixes go to `/pulse-build`, small fixes through its hotfix lane.

## The V is a decision graph

Phases run forward by default and loop back when the work learns something: a bug found while building becomes a fix item ("Discovered in #n"), a design that proves wrong updates the decision or the PLAN, a requirement gap goes back to the spec. A loop back never re-runs later phases on its own; the item's spec records what was decided.

## Commands

| Command | Does |
|---|---|
| `/pulse-ba` | business analysis: problem, users, scope |
| `/pulse-re` | epic, features, success criteria, registered items |
| `/pulse-build` | implementation, test first (planned first when it has no PLAN), bugs, tests for existing code |
| `/pulse-audit` | security audit: the third gate of every feature, or by hand with a chosen scope |
| `/pulse-go` | build everything ready, in parallel |
| `/pulse-map` | the live map |
| `/pulse-setup` | activate, configure, deactivate |
| `/pulse-realign` | take over existing code, or move a project from the predecessor plugin |

[Planning](./pulse-plan) and [review](./pulse-review) run as steps inside `/pulse-build` and `/pulse-go`.

The `pulse` command line behind these commands is documented in [Commands](../reference/commands).
