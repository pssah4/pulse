---
title: The V-Model
description: "The Pulse workflow from idea to release: who works, why, which artifacts they produce, and how people and agents hand the work on."
---

# The V-Model

The Digital Innovation Agents follow the V-Model, a sequential process that bends in the middle. The left side is design (what do we build and why?), the bottom is the build, and the right side is verification (does it work, is it safe?). Each design phase has a verification phase that checks it.

## Why the V-Model?

A plain AI coding session looks like this:

```
User idea -> Agent writes code -> Result
```

That skips what matters for real projects: understanding the problem, fixing the scope, deciding the architecture on purpose, verifying the result. Small changes survive the shortcut. Anything bigger does not.

The V-Model sets a deliberate path:

1. Understand the problem before designing the solution
2. Define requirements before deciding the architecture
3. Plan before building
4. Write the tests that prove the requirements before the code, and review before anything merges
5. Audit before anything merges, and again before releasing

Each phase leaves an artifact the next one reads, so nothing lives only in an agent's context. The artifacts sit in `_devprocess/` in the repository; the board combines the GitHub item catalog with confirmed shared Pulse state ([Where things live](./where-things-live)).

## The phases

Specs, Plans, frozen tests and implementation travel on one published item branch. The Map shows both active work and waiting results. Regular checked results integrate automatically by default. A person may choose manual final approval after the result is available to review.

`pulse go` plans ready specs and builds valid Plans in parallel where dependencies and file reservations allow. Each item has its own worktree. The project's test command verifies the result; review and audit run in one fresh session that did not build it, also for `risk: [security]`. One fix round addresses blocking findings. A current result is ready for approval only after the gates pass.

People and agents share that work as follows:

1. The runner claims eligible work from the backlog; one claim owns its current writing phase and files.
2. The agent prepares its Plan and builds test-first on the same branch as its spec.
3. The runner publishes the branch and result evidence, releases inactive claims and integrates checked results with exact head and base binding. An explicitly chosen manual policy waits for personal approval.
4. Confirmed approval permits a fresh integration check. A serialized merge and normal push integrate the result; completion follows proof of remote ancestry. Changed head or base requires revalidation and new approval.

The board identifies items and dependencies. Shared Pulse state holds claims, holds, results, approvals and integration ownership. Workers commit locally; the supervisor publishes their branch and evidence. With in-session subagents, the parent owns that handoff. [Parallel work](./parallel-work) explains the coordination.

**Business analysis (`/pulse-ba`).** Exploration, ideation and validation produce a Project-BA and, where needed, an Item-BA. Resolve missing product input through the dialog and record the evidence; a separate BA approval is not a routine stop.

**Requirements engineering (`/pulse-re`).** Turn that input into epics, features, requirements, success criteria and the architect handoff. Register drafts to obtain item numbers, publish specs on their item branches and attach them to the records. A spec that passes its structural checks is ready for planning without a separate spec merge.

**Plan (inside `/pulse-re`, `/pulse-build`, and `pulse go`).** A Plan per feature, improvement or fix names tasks, files, waves, frozen spec tests and choices. An epic gets no implementation Plan. `pulse check --plan <path>` reports P1-P6 findings offline; a valid published Plan permits the authorized build when prerequisites are met. Repair attempts preserve risk information. Choices that constrain future work get decision records. Missing authorization for a particular consequential action is resolved explicitly, rather than adding a routine Plan approval.

**Build (`/pulse-build`).** The spec tests come first, one per requirement, red, then frozen: from there the code changes, never those tests. Unit tests where logic branches, the smallest change, and done only when the feature's Activation Path exists in the code. `/pulse-build` also writes tests for code that has none yet.

**Review (inside `/pulse-build` and `pulse go`).** The second gate, in one fresh session with the audit, after the project's tests (`verify`) passed on the branch. A reviewer in a fresh session, one that did not build the item, checks the changes against the spec, the Plan, and the decisions: scope, tests that prove the criteria, duplicates, dead code, abstractions with one use, and whether the system map still says what the change touches.

**Security audit (`/pulse-audit`).** The third gate: Pulse runs the scanner itself, with dependency advisories live from OSV, and a fresh session audits the feature branch against the base on that scan. It blocks while a Critical or High finding is open, and a report that does not say what it covered gives no verdict. Before a release, and regularly in between, it audits the whole codebase: OWASP Top 10, OWASP LLM Top 10, static analysis, dependencies, supply chain, Zero Trust. The release itself (version, tag, publish) belongs to the project; after it, `/pulse-ba` looks back at the hypotheses.

**Publication and integration.** Each item keeps its spec, Plan and implementation on `<type>/<n>-<slug>`. Pulse publishes the checked result and review evidence. The configured final approval policy binds its exact head and base; shared approval and current evidence are checked again before the normal merge and push. A red, stale or held result cannot be approved. No pull request is part of this chain.

## Where Pulse stops for you

Ask for missing product decisions when evidence and the current task do not settle them. Preparation otherwise continues. With manual final approval selected, review the diff, tests, review, audit, risks and findings, then confirm the exact result and base in Pulse. Regular checked results otherwise integrate automatically. Destructive removal keeps its separate explicit confirmations.

Local action status remains visible: queued, syncing, confirmed, conflict or error. Only confirmed shared approval authorizes integration; defer and revoke block locally while their synchronization is pending. Under a manual policy, a managed runner can wait without a terminal and continue when approval is confirmed. Historical automatic settings grant no final approval. Claude Code and Codex use the same workflow and checks.

## The traceability chain

Every artifact traces back to the one that produced it:

```
BA (why?)
  -> Epic (what, strategic?)
    -> Feature (what, concrete?)
      -> Plan (how? tasks, files, decisions)
        -> Decision record (why this way, for later changes)
          -> Spec tests, then code (does it do what the spec says?)
            -> Review (is it lean, in scope, true to the decisions?)
              -> Security audit (is it safe?)
```

The links are plain: the item's record names the spec, the spec names its BA, the Plan names its item and its decision records, the integrated result completes the item. Open any line of code and you can walk back to the business reason.

## Writeback

The chain also runs backwards. When `/pulse-build` finds that a decision no longer matches the code, the record is updated before the build goes on. When a success criterion cannot be met as written, the feature spec changes and says why. A bug fix carries its regression test and completes its item after integration is verified. Documents stay true because the phase that learns something writes it down where it belongs.

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
