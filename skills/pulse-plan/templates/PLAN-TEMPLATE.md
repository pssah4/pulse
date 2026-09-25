---
title: {short plan title}
issue: {N}
spec: _devprocess/requirements/features/FEAT-{ee}-{nn}-{slug}.md
decisions: []                 # decision records this plan relies on
files:                        # every file the tasks create or change, the union of the Files column
  - {src/path/file.ext}
  - {tests/path/test_file.ext}
verify:                       # the commands that prove the item; the builder runs them. The tests gate of pulse go runs verify from .pulse/config.toml instead
  - {build command}
  - {test command}
# needs:                      # holds the PLAN for a person: work that comes first, or a person's OK (a new dependency, a schema, a public interface, a breaking or destructive change); #M holds only while #M is open and no blocker of this item
#   - {#M or a short description}
---

<!-- See skills/pulse-plan/SKILL.md. `pulse go` and the ramp check P1 to
     P5 (`pulse check` only the waves, as C8): every FR and SC of the spec
     covered by a task (or "Deferred: SC-nn reason"), one spec test per FR
     in wave 1 (an FR the spec marks `(unchanged)` may keep an existing
     test), files and a check for every task, tasks of one wave on disjoint
     files, no placeholder left. The PLAN is committed on the item's branch
     and pushed; after the item merges, git keeps it. -->

# PLAN: {title}

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

| # | Task | Covers | Files | Wave | Diff budget | Check |
|---|---|---|---|---|---|---|
| 1 | spec tests, one per FR, named after its id | FR-01, FR-02 | `{tests/path/test_file.ext}` (create) | 1 | ~{n} lines | `{test command}` fails first |
| 2 | {task} | SC-01 | `{src/path/file.ext}` (modify) | 2 | ~{n} lines | `{command}` |

## Stop conditions

Stop instead of guessing when the work needs: a file outside `files`, a
schema or data migration not in this PLAN, a new dependency, or a change to
a spec test after it was frozen. Ask the user; headless (an agent `pulse go`
started), write it into DISCOVERED.md at the worktree root.

## Change log

<!-- Append-only. Progress, surprises, and decisions made while building, one line each:
     YYYY-MM-DD trigger=bug|design|requirement|capability|coverage|budget: what changed and why -->
