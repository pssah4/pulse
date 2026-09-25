---
title: Artifacts
description: Every file the method writes, where it lives, and how long it may get.
---

# Artifacts

Everything the method writes lives in `_devprocess/` in your repository, next to the code and reviewed in pull requests like code. The state of each item (approved, taken, blocked, done) never goes into these files; it sits in the item's record on the board ([Where things live](../concepts/where-things-live)).

## Directory tree

```
_devprocess/
├─ analysis/
│  ├─ BA-{PROJECT}.md              Project-BA: personas, value, hypotheses        /pulse-ba
│  ├─ BA-{slug}.md                 Item-BA for one epic or feature                /pulse-ba
│  ├─ EXPLORE-{PROJECT}.md         Exploration Board (proof of concept, MVP)      /pulse-ba
│  └─ AUDIT-{PROJECT}-{date}.md    security audit report                          /pulse-audit
├─ requirements/
│  ├─ epics/EPIC-{nn}-{slug}.md    epic: hypothesis, outcomes, features           /pulse-re
│  ├─ features/FEAT-{ee}-{nn}-…    feature: stories, success criteria, activation /pulse-re
│  ├─ improvements/IMP-{ee}-{ff}-… improvement: what changes and why              /pulse-re, /pulse-build
│  ├─ fixes/FIX-{ee}-{ff}-{nn}-…   fix: symptom, root cause, regression test      /pulse-build
│  └─ handoff/architect-handoff.md the bridge from requirements to the plan       /pulse-re
├─ plans/{n}-{slug}.md             PLAN: tasks, files, waves, decisions           planning
├─ decisions/
│  ├─ README.md                    router: which record to read when              planning
│  └─ ADR-{nn}-{slug}.md           a decision that constrains later changes       planning
├─ temp/testing/                   temporary, ignored, deleted after use          /pulse-build, review
├─ SYSTEM-MAP.md                   system shape and fast paths (on request)      planning, /pulse-realign
└─ arc42.md                        constraints and quality goals (on request)    planning
```

[Planning](../guides/pulse-plan) and [review](../guides/pulse-review) are steps inside `/pulse-build` and `pulse go`. Settings live in `.pulse/config.toml` ([Configuration](./configuration)). Rules for one area of the code live in a path-local `AGENTS.md` beside that code, where an agent finds them when it reads a file there.

## Front matter

Every spec carries identity and links, nothing else:

```yaml
---
title: Auto-resolve password reset tickets
issue: 14                                  # the item number on GitHub
parent: ../epics/EPIC-01-agent-core.md     # the epic (or, for a fix, the feature)
ba-ref: ../../analysis/BA-agent-core.md    # where the why comes from
subtype: user-facing                       # or library
priority: P1                               # P0 to P2
effort: M                                  # XS to L
risk: []                                   # flags that make a person approve the PLAN
---
```

`pulse new` writes `issue:` and `parent:` and adds the item to its epic's `## Items` list, so the tree survives in the repository after the records close.

## File names and IDs

A spec's file name starts with its ID: the type, the numbers of its parent, and its own counter.

| Spec | ID | File |
|---|---|---|
| epic | `EPIC-04` | `epics/EPIC-04-speech.md` |
| feature of epic 04 | `FEAT-04-02` | `features/FEAT-04-02-speech-input.md` |
| fix of feature 04-02 | `FIX-04-02-01` | `fixes/FIX-04-02-01-drops-words.md` |
| improvement of feature 04-02 | `IMP-04-02-01` | `improvements/IMP-04-02-01-faster-start.md` |
| fix or improvement of the epic itself | `FIX-04-01` | `fixes/FIX-04-01-...md` |
| spec without a parent | `FEAT-07`, `FIX-03` | `features/FEAT-07-...md` |

A folder listing thus groups the features of an epic, and every ID names its epic. Write a spec under its slug (starting with a letter) with `parent:` set, then run `pulse number`: it shows which specs lack the ID of their place, and `pulse number --apply` renames them, rewrites every path to them in the repository, puts the IDs into the epics' `## Items` lines, and moves the records along (their `Spec:` line and the ID in their title). An open record moves only once the base branch has the new path, because agents read the spec there: run `pulse number --apply` again after the merge. A spec keeps a fitting ID; one moved to another parent gets a new one, and its children follow. A new ID comes after every ID a spec file name has had in any branch, in the history, and in any worktree, so parallel sessions do not collide, and a gap stays a gap. A project that starts its numbering anew, say a version 2 on the history of version 1, sets `ids_since` in `.pulse/config.toml` to the commit where it starts ([Configuration](./configuration)); IDs before that commit, and on branches without it, no longer count. `pulse check` (C10) reports a missing or misplaced ID; two branches that took the same ID on different machines show up there after the merge, and `pulse number --apply` moves the one the base branch does not have.

The issue number stays the ID of the record: branches, commits (`Refs: #14`), and every `pulse` command use it. `pulse new` puts the spec's ID in front of the record's title, so the board and the map show it.

A PLAN adds `spec:` and the `files:` it touches, which the ramp compares to keep parallel work apart. A decision record adds `applies-to` and `read-when`. Keys like `status`, `phase`, or `claim` are flagged by `pulse check`.

## Line caps

Short documents get read. `pulse check` counts lines (an audit report without its tables, an epic without the `## Items` list that `pulse new` writes) and allows 10% over the cap; a longer artifact explains why in a `## Reasoned exception` section, a heading `pulse check` takes in any case.

| Artifact | Cap |
|---|---|
| Project-BA | 200 |
| Epic Item-BA | 120 |
| Feature Item-BA | 60 |
| Mini-BA (improvement, fix) | 40 |
| Exploration Board | 70 |
| Epic | 40 |
| Feature | 80 |
| Architect handoff | 60 |
| PLAN (up to its change log) | 80 |
| Decision record (up to its implementation notes) | 60 |
| Audit report | 65 |
| arc42 constraints | 40 |
| System map | 120 |

## The traceability chain

Every artifact names the one it came from, so any line of code leads back to a business reason:

```
BA  ->  epic  ->  feature  ->  PLAN  ->  decision record  ->  commit (Refs: #n)  ->  pull request (Closes #n)
```

## See also

- [Where things live](../concepts/where-things-live)
- [The V-Model](../concepts/v-model)
- [Commands](./commands)
