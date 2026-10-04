---
title: Planning
description: From a ready spec to a Plan the builder can execute, after checking the design against the real code. Decisions live in the Plan; a record only for what constrains future changes.
---

# Planning

Planning turns a ready spec into a Plan. It reads the code first, plans so that as much as possible can run in parallel, and keeps the few decisions that a future agent needs to know.

Planning runs as a step of other commands: [`/pulse-re`](./pulse-re) plans ready published work items in its session, [`/pulse-build`](./pulse-build) (in Codex `$pulse:pulse-build`) plans an item before building it, and [`pulse go`](./pulse-go) prepares published items in the backlog. An epic gets no implementation Plan. All three follow the `pulse-plan` skill, marked `user-invocable: false`; Codex still lists that skill, so start through `/pulse-build` there as well.

## Code first

The planner reads the item (`pulse status <n>`), its spec, the decision records whose "Read When" matches, and then the code the spec touches. Before planning it checks the design against the code and reports only what diverges: decisions that no longer match, patterns that contradict them, modules the spec forgot. A gap in the spec stops planning for that item and goes back to [`/pulse-re`](./pulse-re); planning around a broken spec carries the fault into the code.

The architect handoff from RE carries a Dialog section for open questions. It never blocks more than the item that depends on it: the planner answers what it can from the artifacts and the code and asks the rest in one question.

## The Plan

Saved in `_devprocess/plans/{n}-{slug}.md` on the same item branch as the spec, with `issue:`, `spec:`, `files:` and `verify:` in the frontmatter. The Plan is self-contained: an agent that never saw the repository can build from it. Before an interactive build, refresh the claim so its files are reserved. A supervised planner returns the Plan to the runner, which manages the claim. If work must wait, publish the Plan and release the inactive claim.

Runner agents execute a command of a Plan's `verify:` line only when `.pulse/config.toml` on the base names it too, in `verify`, `setup` (a setup command only without arguments, such as `npm ci`) or a `[spec_tests]` runner, or when it is `pulse check`. Every other line is left out and named in the item log. A check the agents need, such as a typecheck, goes into the configured `verify`.

| Section | Holds |
|---|---|
| Goal | what is different afterwards, observable |
| Context | the modules and files involved, patterns to reuse, terms |
| Decisions | each open question with the chosen option and the rejected ones with their reason |
| Interfaces | signatures, types, schemas the item creates or changes |
| Tasks | the requirement and criterion ids each covers, files, wave, diff budget, and the check that proves it; wave 1 holds the spec tests, one per requirement |
| Not touched | the files and modules near the change that stay as they are: the blast radius |
| Verification | build first, then the checks that prove the goal, then the regression checks |
| Stop conditions | when the builder stops and reports instead of guessing |

The rejected options matter most: the code will only ever show the winner.

The Plan file is the item's only plan. Plan mode displays that file and keeps no separate plan outside the repository. Commit it alone as `docs(plan): #<n>` and publish it on the item's branch.

**Coverage gate.** Before any code, checked mechanically as P1 to P6: the frontmatter names issue, spec, files, and verify, and the file is UTF-8; every requirement and success criterion is covered by a task or deferred with a reason, and every requirement has its spec test in wave 1; every task names files and a check, and `files` is exactly their union; tasks in one wave touch disjoint files; no placeholder is left; every spec test file of wave 1 matches a pattern in `[spec_tests]` of the config on the base branch. Every decision the plan relies on has a task that puts it into effect. The gate runs again whenever the spec or a decision changes.

Before committing or handing over the Plan, run:

```bash
pulse check --plan _devprocess/plans/<n>-<slug>.md
```

The command reports all P1 to P6 findings against the selected published spec and test-runner configuration. It makes no network request and runs no test suite. Resolve the findings before handing the Plan to a builder. Runner and Map select it against concrete commits; a changed spec or Plan needs fresh validation.

**When building starts.** A valid published Plan permits the authorized build. Its `needs:` entries become blockers, and prerequisites hold the build until integrated. Share the Plan's goal, choices, risks and files as a progress update; no separate Plan approval is needed.

**Repairing an existing Plan.** Preserve its path, scope and risk declarations. An unpublished or invalid Plan stays visible with its findings; correct and revalidate it before building. Missing decisions outside the authorized task are reported rather than guessed. Legacy Plan approvals grant no final integration authority.

**Final approval.** The checked, published result receives approval bound to its exact head and base. This is automatic by default. A person may choose manual approval for regular integration with the same checks; destructive removal retains its separate confirmations.

Planning reads the current fetched base and its configuration without a full local test suite. CI status does not hold planning or building. Agents run targeted checks during implementation; the supervisor runs full `verify` once on the completed result before integration.

## Planning for parallel work

- **Disjoint files.** Two items that change the same file cannot run at once; avoid shared files where a new module or a registry entry in its own file would do.
- **Contract first.** If one item needs another only for an interface, the interface becomes its own small blocking item, and the rest runs in parallel.
- **Unmerged code waits.** An item that needs a blocker's code (more than its interface) keeps that item as its blocker and starts once it is merged; nothing builds on a blocker's branch.
- **One feature, one traceable merge.** Cut features so that each merge back to the base branch reads well on its own. A Plan whose tasks would make a merge nobody can follow in one reading is two features: split the spec with [`/pulse-re`](./pulse-re) before planning on.
- **Waves.** Tasks of one wave touch disjoint files; a task that needs another one's result goes into a later wave.

## Decision records, only with a read-when

A record goes into `_devprocess/decisions/` only if you can write a "Read When" that an agent in six months will actually hit: "changing how sessions persist" qualifies, "we split the migration into three steps" does not and stays in the Plan. High reversal cost (data model, persistence, external contracts, authentication) almost always qualifies.

- `constraint`: known before the code (compliance, platform); full MADR with real alternatives.
- `post-hoc`: the normal case, written after the item merges for the Plan decisions that pass the test.
- `choice`: a real pre-code choice; rare.

Records follow MADR and carry `applies-to` and `read-when`; the router `decisions/README.md` has one row each. When a decision changes, the record is updated with a dated section that names what became history, instead of a new record superseding it. Core sections carry no code paths; `pulse check` enforces that.

## System map and arc42

Every planner reads `_devprocess/SYSTEM-MAP.md` where it exists: system shape, data ownership, invariants, quality goals, constraints, risks and fast paths into the code, at most 150 lines. An interactive planner or `/pulse-realign` can create it from observed code on the authorized work branch; missing navigation adds no separate approval or merge stop. A build updates an existing map when those facts change, and review blocks a diff that leaves the map stale. arc42 remains available on a person's request, with all 12 sections from its template.