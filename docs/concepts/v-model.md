---
title: The V-Model
description: "The Pulse workflow from idea to release: who works, why, which artifacts they produce, and how people and agents hand the work on."
---

# The V-Model

The Digital Innovation Agents follow the V-Model, a sequential process that bends in the middle. The left side is design (what do we build and why?), the bottom is the build, and the right side is verification (does it work, is it safe?). Each design phase has a verification phase that checks it.

## Why the V-Model?

A plain AI coding session looks like this:

```
User idea -> Agent writes code -> PR
```

That skips what matters for real projects: understanding the problem, fixing the scope, deciding the architecture on purpose, verifying the result. Small changes survive the shortcut. Anything bigger does not.

The V-Model sets a deliberate path:

1. Understand the problem before designing the solution
2. Define requirements before deciding the architecture
3. Plan before building
4. Write the tests that prove the requirements before the code, and review before anything merges
5. Audit before anything merges, and again before releasing

Each phase leaves an artifact the next one reads, so nothing lives only in an agent's context. The artifacts sit in `_devprocess/` in the repository; the state of each item sits on a shared board on GitHub, one small record per item ([Where things live](./where-things-live)).

## The phases

[![Top: the Pulse workflow as a line of ten steps from business analysis to release, each with who works (a person, an agent, or pulse) and the artifact it leaves behind; amber outlines where you decide; dashed paths back. Bottom: the map everyone sees, with the ramp in team order, the pairs of a person and their agents who claim items and build them, the pull requests they hand back for your merge, and the board on GitHub behind it.](/v-model-overview.svg)](/v-model-overview.svg)

The top row is the flow, read from left to right. Each step shows who works (a person, an agent, or `pulse` itself), its command, and below it the artifact it leaves for the next step. Amber outlines mark where Pulse stops for you; the dashed outline around the plan applies only when something holds the PLAN. Dashed paths lead back: a red gate to the build, a requirement gap to requirements, a design gap to planning, and the outcomes of a release to `/pulse-ba`.

`pulse go` runs plan to pull request on its own, for every approved feature and in parallel where dependencies and files allow. Each feature gets its own branch, worktree, and pull request. The project's test command runs the tests; review and audit run in fresh sessions that did not build the item. A red gate hands its findings back to the build, and after the fix the gates start again at the tests. The pull request is ready only when all three gates pass on its last commit.

The bottom half shows how people and their agents share the work. Each person runs `pulse go` with their own agents, and everyone sees the same [map](../guides/pulse-map):

1. `pulse go` claims the front of the ramp, which the team orders and approves. A claim belongs to one session, so no second pair takes the item.
2. The agent runs plan to pull request in the item's own worktree and branch; the map shows its step and a light.
3. The pair hands back a pull request with the gate reports, and you merge it.
4. The merge closes the item, and work that waited for it moves up the ramp. A failed build gives its claim back and the item returns to the ramp; a draft pull request keeps its claim.

Documents and code travel through Git: BA documents, specs, PLANs, and decisions under `_devprocess/`, code and tests on the feature branch, gate results and reports in the pull request. The board on GitHub stores what the map shows, one record per item, and only `pulse` writes it. Workers commit locally in their worktree; the runner pushes, opens the pull request, and refills the slot. With in-session subagents, the parent session runs the same loop. [Parallel work](./parallel-work) and [Where things live](./where-things-live) give the details.

**Business analysis (`/pulse-ba`).** Exploration, ideation, validation. Produces the Project-BA `BA-{PROJECT}.md` (personas, How-Might-We question, value proposition, idea potential, critical hypotheses) and an Item-BA per epic or feature that inherits from it. It ends with your approval.

**Requirements engineering (`/pulse-re`).** Turns the BA into an epic, features, requirements, and tech-agnostic success criteria, writes the architect handoff, and registers each item on the board. Features are cut so that each merge back to the base branch reads well on its own: one feature, one traceable merge, never a monolith. You read each spec and approve it with `pulse approve`: that means build it.

**Plan (inside `/pulse-build` and `/pulse-go`).** A PLAN per item: tasks, the files each task touches, waves of tasks that can run at once, the spec tests as the first wave, and the decisions made on the way. `pulse go` plans every approved item on its own; a PLAN waits for you only when something holds it (a risk flag or `effort: L` in the spec, `needs:` in the PLAN, or `plan_approval = "manual"`). A decision that constrains later work gets a record behind the router in `_devprocess/decisions/`.

**Build (`/pulse-build`).** The spec tests come first, one per requirement, red, then frozen: from there the code changes, never those tests. Unit tests where logic branches, the smallest change, and done only when the feature's Activation Path exists in the code. `/pulse-build` also writes tests for code that has none yet.

**Review (inside `/pulse-build` and `/pulse-go`).** The second gate, after the project's tests (`verify`) passed on the branch. A reviewer in a fresh session, one that did not build the item, checks the changes against the spec, the PLAN, and the decisions: scope, tests that prove the criteria, duplicates, dead code, abstractions with one use. Every two weeks the same reviewer looks at the whole repository for drift.

**Security audit (`/pulse-audit`).** The third gate: Pulse runs the scanner itself, with dependency advisories live from OSV, and a fresh session audits the feature branch against the base on that scan. It blocks while a Critical or High finding is open, and a report that does not say what it covered gives no verdict. Before a release, and regularly in between, it audits the whole codebase: OWASP Top 10, OWASP LLM Top 10, static analysis, dependencies, supply chain, Zero Trust. The release itself (version, tag, publish) belongs to the project; after it, `/pulse-ba` looks back at the hypotheses.

**Pull request and merge.** Each feature gets its own branch, `<type>/<n>-<slug>`, and exactly one pull request back to the base branch (for example `develop`). Before the gates, `pulse go` checks that the frozen spec tests still stand line by line and that they failed at the commit that froze them. A red gate gets a fix round, at most two per gate, and after every fix the gates start again at the tests. The pull request carries `Closes #n`, a table of the three gates, and the review and audit reports. It is ready only when all three passed; otherwise it stays a draft that names what is open, and the item keeps its claim. A draft of `pulse go` that gets a new commit (you fixed it) is taken up by the next run, which runs the gates again. You merge it, and that merge is the last stop.

## Where Pulse stops for you

Every command can be called on its own. In the flow, one phase hands over to the next without asking, and Pulse stops for a person only where a person owns the decision:

| Stop | What you decide |
|---|---|
| The business analysis | the problem, the users, and the scope are right |
| Each spec (`pulse approve`) | this gets built: planning, build, and the gates follow in ramp order |
| A PLAN, only when something holds it (`pulse approve-plan`) | a risky PLAN is right: a risk flag or `effort: L` in the spec, `needs:` in the PLAN, or `plan_approval = "manual"` |
| The merge of each feature's pull request | the feature goes into the base branch after tests, review, and audit passed |

`pulse rank`, or the map's move mode (`m` in an item's view, the arrows move it, `Enter` puts it down), steers the order at any time and stops nothing. Between the stops nobody hands work over by hand: an approved BA flows into requirements, an approved spec into planning, and a planned feature through build, tests, review, audit, and fix rounds into its pull request. The rules that every session and every subagent gets name these stops, so an agent does not stop to ask anywhere else.

## The traceability chain

Every artifact traces back to the one that produced it:

```
BA (why?)
  -> Epic (what, strategic?)
    -> Feature (what, concrete?)
      -> PLAN (how? tasks, files, decisions)
        -> Decision record (why this way, for later changes)
          -> Spec tests, then code (does it do what the spec says?)
            -> Review (is it lean, in scope, true to the decisions?)
              -> Security audit (is it safe?)
```

The links are plain: the item's record names the spec, the spec names its BA, the PLAN names its item and its decision records, the pull request closes the item. Open any line of code and you can walk back to the business reason.

## Writeback

The chain also runs backwards. When `/pulse-build` finds that a decision no longer matches the code, the record is updated before the build goes on. When a success criterion cannot be met as written, the feature spec changes and says why. A bug fix carries its regression test and closes its item through the pull request. Documents stay true because the phase that learns something writes it down where it belongs.

## The V is iterative

The diagram shows a straight walk. Real projects learn mid-flight, and four triggers route that learning back:

- **Bug found during the build.** A new fix item with "Discovered in #n", then the fix path; the current item goes on or waits, depending on the blast radius.
- **Design no longer fits.** The build pauses, the decision record changes, then the build continues.
- **Requirement gap during planning.** Planning stops and hands the gap back to `/pulse-re`.
- **Missing capability.** The build needs something the plan never had (a library, a service, a pattern). It goes back through planning as a decision first.

The forward walk stays the default. Iteration is an option, not a detour.

## Scope adaptation

The same V runs for:

- **Simple test or feature** (hours to 1-2 days): short exploration, no validation, focus on the Definition of Done
- **Proof of concept** (1-4 weeks): shorter exploration, full ideation, hypothesis-driven validation
- **Minimum viable product** (2-6 months): full exploration, full ideation, full market validation

The phases stay the same; the depth adapts.

## See also

- [/pulse](../guides/pulse): where things stand and what comes next
- [A full V-Model run](../tutorials/full-v-model-run): end-to-end walkthrough
- [Parallel work](./parallel-work): how the build runs for several items at once
- [Verification gates](./verification-gates): what counts as done
