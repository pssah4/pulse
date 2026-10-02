---
title: {what improves, in a few words}
issue: {N}          # leave it: registering the spec fills it in
parent: ../features/FEAT-{ee}-{nn}-{feature}.md
priority: P2          # P0 | P1 | P2
effort: S             # XS | S | M | L
risk: []              # consequential choices to retain in Plan and final result review
---

<!-- Improvement spec, saved as _devprocess/requirements/improvements/{slug}.md
     with parent set, named by `pulse number --apply`
     (IMP-{ee}-{ff}-{nn}-{slug}.md), committed and pushed, then registered:
     pulse new imp "<title>" --parent <feature> --spec <path> --issue <n>,
     which writes issue and parent here. Reserve <n> with --draft first;
     use its imp/<n>-<slug> branch for spec, Plan and implementation. The record on the board only links
     this file. The published spec must pass R1 to R6 before planning. -->

## Description

{What changes about existing behavior? One to two sentences.}

## Reason

{The concrete trigger or signal that motivated the work.}

## Scope

- In: {what changes}
- Out: {what stays as it is}

## Requirements

- FR-01: WHEN {trigger} THE SYSTEM SHALL {new response}.
- FR-02 (unchanged): THE SYSTEM SHALL {keep what works today}.

## Success criteria

| ID    | Criterion                                    | Target  | Measurement |
|-------|----------------------------------------------|---------|-------------|
| SC-01 | {observable improvement, in user-outcome terms} | {value} | {how}    |

## Assumptions and dependencies

- {assumption or dependency; dependencies also with --blocked-by}

## Open questions

<!-- Only questions the user keeps open, each as [CLARIFY: question]. -->
