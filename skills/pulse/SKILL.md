---
name: pulse
description: >
  Pulse entry point: where the work stands, what comes next, and which
  Pulse command fits. Use when the user types /pulse, asks "where do I
  start", "what's next", or starts new work without saying what kind it
  is.
---

# Pulse

Pulse runs the V-Model method (the Digital Innovation Agents), keeps
the specs in the repository and a record per item on the board, and
spreads agents over everything that is ready. This command reads the situation and recommends one next step.
The user decides.

## Where things stand

Run `pulse status`. If Pulse is not active here (no `.pulse/config.toml`),
say so in one line and offer `/pulse-setup` (in Codex
`$pulse:pulse-setup`). Otherwise summarize in at most five lines: ready
items, work in progress and who holds it, what waits on the user, what
is failing, what is blocked and on what.

## What comes next

Take the first row that applies. In Codex, name each command as
`$pulse:<name>`, so `$pulse:pulse-ba` for `/pulse-ba`.

| Situation | Recommend |
|---|---|
| Something waits on the user (an open question, a red test) | name it first |
| No method artifacts, empty or greenfield repo | `/pulse-ba` for the Project-BA |
| Code exists but no BA and no specs, or legacy DIA artifacts | `/pulse-realign` |
| Project-BA is a Draft | `/pulse-ba` in Validation Mode |
| A new epic or feature is wanted | `/pulse-ba` for its Item-BA |
| A validated Project-BA or an Item-BA exists, no epics or features registered yet | `/pulse-re` |
| Specs wait for approval (`pulse status`: "not approved") | show each spec's goal, scope, and success criteria; once the user merged its pull request into the base branch, `pulse approve <n>` on the user's yes, which means build it; it refuses a spec that is not on the base branch (R1) and, for a feature, improvement, or fix, one there that breaks R2 to R6: then `/pulse-re` on that spec (an epic needs R1 only) |
| Items are approved but their spec does not pass R1 to R6 (`pulse check`) | `/pulse-re` on that spec |
| A PLAN waits for a person (`pulse status`: "plan waits for you") | show its goal, decisions, and risks; `pulse approve-plan <n>` on a yes |
| Approved items with a ready spec, or ready items, and free slots | `/pulse-go` (plans what has no PLAN, then builds all in parallel), or `/pulse-build <n>` for one in this session (it plans first when there is no PLAN) |
| A feature PR is ready (tests, review, and audit passed) | name it: it waits for the user's merge, the last stop |
| A draft feature PR names a red gate | fix the findings on its branch test-first and push them; the next `pulse go` takes up a draft that a run under the user's login holds, repeats the gates, and marks it ready once all three pass |
| A PR whose last commit has no review or no audit | run the missing gates on a yes, each in a fresh session: `pulse review <n> --run`, `pulse audit <n> --run` |
| The newest `_devprocess/analysis/REVIEW-*.md` is older than two weeks, or there is none | a repo review (the pulse-review skill in repo mode) on a yes |
| Release pending | `/pulse-audit` |

## New work without a kind

Ask exactly one question: "Is this a new feature, an improvement on an
existing feature, or a fix for a bug?" A new feature with an unclear
problem goes to `/pulse-ba`, with a clear one to `/pulse-re`. An
improvement or a fix goes to `/pulse-build`; small fixes take the
hotfix lane there.

## The V is a decision graph

Phases run forward by default, but work loops back when it learns
something:

1. **Bug found while building:** stop, record a fix item
   ("Discovered in #n"), find the root cause, then fix it test-first.
2. **Design proves wrong while building:** stop, amend the decision or
   the PLAN, then continue.
3. **Requirement gap while planning or building:** route it back to the
   spec, re-check the PLAN covers every success criterion, continue.

A loop back does not re-run later phases on its own. The user decides,
and the item's spec records the decision.

## Commands

| Command | Does |
|---|---|
| `/pulse-ba` | business analysis: problem, users, scope |
| `/pulse-re` | epic, features, success criteria, registered items |
| `/pulse-build` | one item test-first (planned first when it has no PLAN), bugs, tests for existing code |
| `/pulse-audit` | security audit |
| `/pulse-go` | start everything unblocked, in parallel |
| `/pulse-map` | live map: who works on what, what is ready |
| `/pulse-setup` | activate, configure, deactivate |
| `/pulse-realign` | take over an existing codebase or a DIA project |
