---
title: Planning
description: From a ready spec to a PLAN the builder can execute, after checking the design against the real code. Decisions live in the PLAN; a record only for what constrains future changes.
---

# Planning

Planning turns a ready spec into a PLAN. It reads the code first, plans so that as much as possible can run in parallel, and keeps the few decisions that a future agent needs to know.

Planning runs as a step of other commands: [`/pulse-build`](./pulse-build) (in Codex `$pulse:pulse-build`) plans an item that has no PLAN before it builds, and [`pulse go`](./pulse-go) plans every approved item without one. Both follow the `pulse-plan` skill, which carries `user-invocable: false` and so stays out of the command menu. Codex does not read that field and still lists the skill; start planning through `/pulse-build` there as well.

## Code first

The planner reads the item (`pulse show <n>`), its spec, the decision records whose "Read When" matches, and then the code the spec touches. Before planning it checks the design against the code and reports only what diverges: decisions that no longer match, patterns that contradict them, modules the spec forgot. A gap in the spec stops planning for that item and goes back to [`/pulse-re`](./pulse-re); planning around a broken spec carries the fault into the code.

The architect handoff from RE carries a Dialog section for open questions. It never blocks more than the item that depends on it: the planner answers what it can from the artifacts and the code and asks the rest in one question.

## The PLAN

Saved in `_devprocess/plans/{n}-{slug}.md` on the item's branch, with `issue:`, `spec:`, a `files:` list that the [ramp](../concepts/parallel-work) reads, and the `verify:` commands in the frontmatter. The agents of `pulse go` run a `verify:` command only when it starts with a program of the configured `verify` or with a script of the repository, such as `bin/pulse check`; a shell or interpreter given code, a download, `npx`, `env`, or `sudo` is left out, and the item log and the pull request name each one. It is self-contained: an agent that never saw the repository can build from it. Once the PLAN is saved, the planner claims the item again: the claim on the board then carries the `files:` list, so every teammate's ramp keeps other items off those files even before the PLAN is pushed.

| Section | Holds |
|---|---|
| Goal | what is different afterwards, observable |
| Context | the modules and files involved, patterns to reuse, terms |
| Decisions | each open question with the chosen option and the rejected ones with their reason |
| Interfaces | signatures, types, schemas the item creates or changes |
| Tasks | the requirement and criterion ids each covers, files, wave, diff budget, and the check that proves it; wave 1 holds the spec tests, one per requirement |
| Stop conditions | when the builder stops and reports instead of guessing |

The rejected options matter most: the code will only ever show the winner.

**Coverage gate.** Before any code, checked mechanically as P1 to P5: the frontmatter names issue, spec, files, and verify, and the file is UTF-8; every requirement and success criterion is covered by a task or deferred with a reason, and every requirement has its spec test in wave 1; every task names files and a check, and `files` is exactly their union; tasks in one wave touch disjoint files; no placeholder is left. Every decision the plan relies on has a task that puts it into effect. The gate runs again whenever the spec or a decision changes.

**Who approves it.** With `plan_approval = "auto"` (the default) a PLAN that passes the gate is approved at once, unless a risk flag (`risk:`) or `effort: L` in the spec, or an entry under `needs:` in the PLAN, holds it for a person. With `manual`, every PLAN waits. A person approves with `pulse approve-plan <n>` or in the ramp. The approval binds to the PLAN as it is at that moment: `pulse approve-plan` prints its digest and its goal, and a PLAN rewritten afterwards waits again. The map sends back the digest of the PLAN the person read and refuses the approval when the PLAN changed since. [`pulse go`](./pulse-go) writes PLANs for approved items by itself, in ramp order.

## Planning for parallel work

- **Disjoint files.** Two items that change the same file cannot run at once; avoid shared files where a new module or a registry entry in its own file would do.
- **Contract first.** If one item needs another only for an interface, the interface becomes its own small blocking item, and the rest runs in parallel.
- **Stacking.** An item that needs a blocker's unmerged code (more than its interface) keeps that item as its one blocker. As soon as the blocker's PR is ready, it starts on the blocker's branch and its PR targets that branch, at every parallel level and without a line in the PLAN. When two or more pull requests are ready, the integration check at the end of a `pulse go` run merges their branches in that order in a scratch checkout and runs `verify` there, before anyone merges.
- **One feature, one traceable merge.** Cut features so that each merge back to the base branch reads well on its own. A PLAN whose tasks would make a merge nobody can follow in one reading is two features: split the spec with [`/pulse-re`](./pulse-re) before planning on.
- **Waves.** Tasks of one wave run at once at `max`; a task that needs another one's result goes into a later wave.

## Decision records, only with a read-when

A record goes into `_devprocess/decisions/` only if you can write a "Read When" that an agent in six months will actually hit: "changing how sessions persist" qualifies, "we split the migration into three steps" does not and stays in the PLAN. High reversal cost (data model, persistence, external contracts, authentication) almost always qualifies.

- `constraint`: known before the code (compliance, platform); full MADR with real alternatives.
- `post-hoc`: the normal case, written after the item merges for the PLAN decisions that pass the test.
- `choice`: a real pre-code choice; rare.

Records follow MADR and carry `applies-to` and `read-when`; the router `decisions/README.md` has one row each. When a decision changes, the record is updated with a dated section that names what became history, instead of a new record superseding it. Core sections carry no code paths; `pulse check` enforces that.

## On request

arc42 constraints before the code (quality goals, constraints, scenarios, risks), the full arc42 reference after it for auditors and customers, and a system map with fast paths into the code.
