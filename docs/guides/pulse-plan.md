---
title: Planning
description: From a ready spec to a PLAN the builder can execute, after checking the design against the real code. Decisions live in the PLAN; a record only for what constrains future changes.
---

# Planning

Planning turns a ready spec into a PLAN. It reads the code first, plans so that as much as possible can run in parallel, and keeps the few decisions that a future agent needs to know.

Planning runs as a step of other commands: [`/pulse-re`](./pulse-re) plans every feature, improvement, or fix you approve in its session, right after the approval and without asking, and an epic gets no PLAN; [`/pulse-build`](./pulse-build) (in Codex `$pulse:pulse-build`) plans an item that has no PLAN before it builds; and [`pulse go`](./pulse-go) plans every approved item without one, or repairs a structurally invalid PLAN that has never been approved. All three follow the `pulse-plan` skill, which carries `user-invocable: false` and so stays out of the command menu. Codex does not read that field and still lists the skill; start planning through `/pulse-build` there as well.

## Code first

The planner reads the item (`pulse status <n>`), its spec, the decision records whose "Read When" matches, and then the code the spec touches. Before planning it checks the design against the code and reports only what diverges: decisions that no longer match, patterns that contradict them, modules the spec forgot. A gap in the spec stops planning for that item and goes back to [`/pulse-re`](./pulse-re); planning around a broken spec carries the fault into the code.

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
| Not touched | the files and modules near the change that stay as they are: the blast radius |
| Verification | build first, then the checks that prove the goal, then the regression checks |
| Stop conditions | when the builder stops and reports instead of guessing |

The rejected options matter most: the code will only ever show the winner.

The PLAN file is the item's only plan. A plan mode, such as the one in Claude Code, shows it for approval and keeps no plan of its own: a plan outside the repository reaches no teammate, no other agent, and no ramp.

**Coverage gate.** Before any code, checked mechanically as P1 to P6: the frontmatter names issue, spec, files, and verify, and the file is UTF-8; every requirement and success criterion is covered by a task or deferred with a reason, and every requirement has its spec test in wave 1; every task names files and a check, and `files` is exactly their union; tasks in one wave touch disjoint files; no placeholder is left; every spec test file of wave 1 matches a pattern in `[spec_tests]` of the config on the base branch. Every decision the plan relies on has a task that puts it into effect. The gate runs again whenever the spec or a decision changes.

Before committing or handing over the PLAN, run:

```bash
pulse check --plan _devprocess/plans/<n>-<slug>.md
```

The command reports all P1 to P6 findings together, using the spec and test-runner configuration from the current locally available base. It makes no network request and runs no test suite. Fix the findings and repeat the command until it succeeds. Runner and map select the PLAN against concrete Git commits, so a spec merge refreshes its path, source and validation.

**Who approves it.** Spec approval for planning is automatic by default; the completed PLAN waits for manual approval before implementation. Show its goal, decisions, risks and files, then approve it with `pulse approve <n>`, or `a` in the map. That personal approval binds the PLAN and spec as origin has them, and a changed PLAN or spec waits again. The map refuses approval when the blobs changed since the person read them; the approving person must have repository write access. Explicit `pulse auto build on` may delegate this decision under the existing risk and prerequisite checks. An explicit off or expired delegation stays off. The runner turns each `needs:` entry into a blocker, and open prerequisites hold the build.

**Repairing an existing PLAN.** A structurally invalid PLAN with no previous PLAN approval can return to the planner at its existing path. Repairs preserve risk declarations and use the existing limit of two fix rounds. If validation still fails, the item stops with the findings and a concrete next action. A PLAN that was previously approved returns to a person before automatic rewriting. Claude Code and Codex follow these same limits.

Planning reads the current fetched base and its CI metadata without a full local test suite. Pending CI permits planning and holds the build. Agents run targeted checks during implementation; the supervisor runs full `verify` once on the completed result.

## Planning for parallel work

- **Disjoint files.** Two items that change the same file cannot run at once; avoid shared files where a new module or a registry entry in its own file would do.
- **Contract first.** If one item needs another only for an interface, the interface becomes its own small blocking item, and the rest runs in parallel.
- **Unmerged code waits.** An item that needs a blocker's code (more than its interface) keeps that item as its blocker and starts once it is merged; nothing builds on a blocker's branch.
- **One feature, one traceable merge.** Cut features so that each merge back to the base branch reads well on its own. A PLAN whose tasks would make a merge nobody can follow in one reading is two features: split the spec with [`/pulse-re`](./pulse-re) before planning on.
- **Waves.** Tasks of one wave touch disjoint files; a task that needs another one's result goes into a later wave.

## Decision records, only with a read-when

A record goes into `_devprocess/decisions/` only if you can write a "Read When" that an agent in six months will actually hit: "changing how sessions persist" qualifies, "we split the migration into three steps" does not and stays in the PLAN. High reversal cost (data model, persistence, external contracts, authentication) almost always qualifies.

- `constraint`: known before the code (compliance, platform); full MADR with real alternatives.
- `post-hoc`: the normal case, written after the item merges for the PLAN decisions that pass the test.
- `choice`: a real pre-code choice; rare.

Records follow MADR and carry `applies-to` and `read-when`; the router `decisions/README.md` has one row each. When a decision changes, the record is updated with a dated section that names what became history, instead of a new record superseding it. Core sections carry no code paths; `pulse check` enforces that.

## System map and arc42

Every planner reads `_devprocess/SYSTEM-MAP.md` before a PLAN: system shape, data ownership, invariants, quality goals, constraints, risks, and fast paths into the code, at most 150 lines. The plan prompt of `pulse go` names it; where it is missing, a planning session with a person, or `/pulse-realign`, creates it on a docs branch into the base, never on an item branch. A build updates an existing map as its last task when the item changes one of these, and the review blocks a diff that changes one while the map stays silent. arc42 comes only on request of a person, for auditors or customers: `_devprocess/arc42.md` with all 12 sections from one template, allowed to lag behind the code.
