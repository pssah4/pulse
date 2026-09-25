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
│  ├─ epics/{slug}.md              epic: hypothesis, outcomes, features           /pulse-re
│  ├─ features/{slug}.md           feature: stories, success criteria, activation /pulse-re
│  ├─ improvements/{slug}.md       improvement: what changes and why              /pulse-re, /pulse-build
│  ├─ fixes/{slug}.md              fix: symptom, root cause, regression test      /pulse-build
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
parent: ../epics/agent-core.md             # the epic (or, for a fix, the feature)
ba-ref: ../../analysis/BA-agent-core.md    # where the why comes from
subtype: user-facing                       # or library
priority: P1                               # P0 to P2
effort: M                                  # XS to L
risk: []                                   # flags that make a person approve the PLAN
---
```

`pulse new` writes `issue:` and `parent:` and adds the item to its epic's `## Items` list, so the tree survives in the repository after the records close.

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
