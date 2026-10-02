---
title: {symptom in a few words}
issue: {N}          # leave it: registering the spec fills it in
parent: ../features/FEAT-{ee}-{nn}-{feature}.md
priority: P1          # P0 immediate | P1 short term | P2 mid term
effort: S             # XS | S | M | L
risk: []              # consequential choices to retain in Plan and final result review
---

<!-- Fix spec, saved as _devprocess/requirements/fixes/{slug}.md with parent
     set, named by `pulse number --apply` (FIX-{ee}-{ff}-{nn}-{slug}.md),
     committed and pushed, then registered:
     pulse new fix "<title>" --parent <feature> --spec <path> --issue <n>,
     which writes issue and parent here. Reserve <n> with --draft first;
     use its fix/<n>-<slug> branch for spec, Plan and implementation. The record on the board only links
     this file. The published spec must pass R1 to R6 before planning. -->

## Symptom

{One sentence: the observable bad behavior.}

## Root cause

```
step 1 -> step 2 -> ... -> error
```

## Expected behavior

- FR-01: WHEN {trigger} THE SYSTEM SHALL {correct response}.

## Unchanged behavior

<!-- What must keep working. Each line gets a test, so the fix breaks nothing else. -->

- FR-02 (unchanged): THE SYSTEM SHALL {keep what works}.

## Fix

{The direction now; one line in business terms once the fix lands.}

## Regression test

{Test that reproduced the bug and now locks the fix; red-green verified on YYYY-MM-DD.}

{Discovered in #N, when it surfaced during other work.}
