---
title: {short plan title}
issue: {N}
spec: _devprocess/requirements/features/FEAT-{ee}-{nn}-{slug}.md
decisions: []                 # decision records this plan relies on
files:                        # every file the tasks create or change, the union of the Files column
  - {src/path/file.ext}
  - {tests/path/test_file.ext}
verify:                       # the commands that prove the item; the builder runs them
  - {build command}
  - {test command}
# needs:                      # work that has to be built first; pulse go makes each entry a blocker of this item, a new title a draft item
#   - '{#M title}', or {a short title}
# risk:                       # consequential choices for final review: dependency, schema, public interface, compatibility or destructive effect
#   - {dependency, schema, public-api, or destructive}
---

<!-- See skills/pulse-plan/SKILL.md. `pulse go` and the backlog check P1 to
     P6: every FR and SC of the spec
     covered by a task (or "Deferred: SC-nn reason"), one spec test per FR
     in wave 1 (an FR the spec marks `(unchanged)` may keep an existing
     test), files and a check for every task (the test files it affects;
     the full verify is no task's check), tasks of one wave on disjoint
     files, no placeholder left, a configured runner for every spec test.
     Run pulse check --plan <this-file> before committing or handing over.
     The Plan is committed on the item's branch
     and pushed with its spec; a valid Plan permits the authorized build.
     Final approval binds the checked result head and base. Git keeps the Plan. -->

# Plan: {title}

## Goal

{Two or three lines: what is different afterwards, observable by a user or caller.}

## Context

{The modules and files involved, the patterns to reuse, the terms a newcomer
needs. Self-contained: an agent that never saw this repository can start.}

## Decisions

| Question | Chosen | Rejected, and why |
|---|---|---|
| {question} | {option} | {option}: {reason} |

## Interfaces

{Signatures, types, schemas, or endpoints this item creates or changes. "None"
when nothing crosses a module boundary.}

## Tasks

<!-- Each finished task gets one commit with the trailer `Pulse-Task: <n>`, n its # below;
     the Map shows "Plan k/n" from them. Display only, no gate reads it. -->

| # | Task | Covers | Files | Wave | Diff budget | Check |
|---|---|---|---|---|---|---|
| 1 | spec tests, one per FR, named after its id | FR-01, FR-02 | `{tests/path/test_file.ext}` (create) | 1 | ~{n} lines | `{test command}` fails first |
| 2 | {task} | SC-01 | `{src/path/file.ext}` (modify) | 2 | ~{n} lines | `{test command} {affected test files}` |

## Not touched

{The files and modules near the change that stay as they are: the blast radius a reviewer checks.}

## Verification

{Build first, then the checks that prove the goal, then the regression checks; the commands
under verify run them.}

## Stop conditions

Stop instead of guessing when a requirement, ownership conflict or
consequential action falls outside the authorized task. Record a routine
scope correction in this Plan's change log and revalidate it. A frozen
spec test changes only after its requirement and change-log entry are
updated and the exact diff has been shown to the user. Headless agents
preserve work and report decisions they cannot resolve. Work that must
come first goes under `needs:` in `_devprocess/plans/<n>-needs.md`.

## Change log

<!-- Append-only. Progress, surprises, and decisions made while building, one line each:
     YYYY-MM-DD trigger=bug|design|requirement|capability|coverage|budget: what changed and why -->
