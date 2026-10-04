---
title: A full V-Model run
description: From a raw idea to merged code with Pulse, every step and every artifact, for a team of three.
---

# A full V-Model run

This walkthrough takes one idea through every step: business analysis, requirements, plan, a parallel build, tests, and the security audit. Sebastian, Alice, and Bob build a small tool that helps teams run better retrospectives. You see what each step asks, what it writes, and how the three of them share the work.

Reading time about 20 minutes; running it for a proof of concept takes an afternoon.

## The setup

In the repository, ask Pulse where to start:

```
/pulse

We want to build a tool that helps teams run better retrospectives.
```

This walkthrough spells the commands as Claude Code does. In Codex, type `$pulse:<name>` for `/<name>`, so `$pulse:pulse` here.

Pulse is not set up yet, so `/pulse` sets it up first: it asks for the settings one at a time and runs [`pulse setup`](../guides/pulse-setup). Nothing else exists yet, so it recommends `/pulse-ba`.

## Step 1: Business analysis (`/pulse-ba`)

The [first business analysis tutorial](./first-business-analysis) shows this step in detail. The agent interviews Sebastian one question at a time: who runs retrospectives, what goes wrong today, which job the tool must do. It writes:

- `_devprocess/analysis/BA-retrospectives.md`: the Project-BA with personas, the How-Might-We question, the value proposition, and the critical hypotheses
- `_devprocess/analysis/EXPLORE-retrospectives.md`: the Exploration Board, for a proof of concept or an MVP
- no Item-BA yet: the first epic of a new project comes straight from the Project-BA; a later epic gets an Item-BA of its own, which inherits the personas by reference

The skill pushes the Project-BA's discovery branch after each commit, so Alice and Bob can read it while it grows. It records validated claims when the evidence supports them, asks Sebastian to close the completed discovery draft, and continues authorized requirements work in the same session.

::: tip Methods the BA agent will propose
During this phase the agent stops the interview whenever a gap appears
and points you at the matching field method. Most common entry points:

- [Explorative interviews](../reference/methods-discovery#explorative-interviews)
  and [Qualitative interview](../reference/methods-discovery#qualitative-interview)
  when the user is still abstract.
- [Fly on the wall](../reference/methods-discovery#fly-on-the-wall)
  and [Self-test](../reference/methods-discovery#self-test) when
  interviews keep producing the ideal workflow instead of the real one.
- [Persona synthesis cluster](../reference/methods-discovery#persona-synthesis-cluster)
  and [Persona](../reference/methods-discovery#persona) to turn
  notes into a usable persona.
- [Brainstorming](../reference/methods-ideation#brainstorming),
  [Brainwriting](../reference/methods-ideation#brainwriting), or
  [Jobs to be done](../reference/methods-ideation#jobs-to-be-done)
  during Ideation.
- [Wireframes, storyboards, and paper prototypes](../reference/methods-validation#wireframes-storyboards-and-paper-prototypes)
  and [Pre-mortem](../reference/methods-validation#pre-mortem)
  during Validation.

Full catalog under [Discovery methods](../reference/methods-discovery),
[Ideation methods](../reference/methods-ideation), and
[Validation methods](../reference/methods-validation).
:::

## Step 2: Requirements (`/pulse-re`)

The BA becomes an epic and its features, each a file in the repository:

- `requirements/epics/EPIC-01-retro-board.md`: the epic hypothesis in plain prose, business outcomes with baseline and target
- `requirements/features/FEAT-01-01-anonymous-cards.md`, `FEAT-01-02-vote-and-rank.md`, `FEAT-01-03-action-items.md`: user stories, success criteria without technology ("a participant adds a card in under 10 seconds"), and an Activation Path that names how a user reaches the feature
- `requirements/handoff/architect-handoff.md`: what the plan must respect

Each item is visible from the moment `/pulse-re` reserves its draft: `pulse new feat "Vote and rank" --draft` returns #3. The skill creates `feat/3-vote-and-rank` from the fetched base, writes and validates its spec, assigns its logical ID with `pulse number --apply`, then commits and pushes. Spec, Plan and build stay on that branch. It attaches each published spec to the reserved draft, parents first, on that item's branch:

```bash
pulse new epic "Retro board" --spec _devprocess/requirements/epics/EPIC-01-retro-board.md --issue 1
pulse new feat "Anonymous cards" --parent 1 --spec _devprocess/requirements/features/FEAT-01-01-anonymous-cards.md --issue 2
pulse new feat "Vote and rank" --parent 1 --spec _devprocess/requirements/features/FEAT-01-02-vote-and-rank.md --issue 3
pulse new feat "Action items" --parent 1 --blocked-by 3 --spec _devprocess/requirements/features/FEAT-01-03-action-items.md --issue 4
```

The numbers are examples: the Project-BA's draft from step 1 took a number too, so on your board they differ.

Commit and push the metadata registration writes on the same item branch. Keep each parent's spec available so relative links resolve. Each feature produces one traceable integration. Action items need ranking first, so #4 names #3 as a blocker. Valid published specs can be planned immediately; no spec merge or approval separates them from planning.

## Step 3: Plan

Planning runs inside `/pulse-re`, `/pulse-build` and `pulse go`. Here `/pulse-re` plans the published features while their requirements are fresh; an epic gets no implementation Plan. One Plan per feature in `_devprocess/plans/` records tasks, files and decisions, including rejected alternatives. Disjoint tasks share a wave. A constraint future changes must respect, such as "cards are stored without author", becomes a decision record behind `_devprocess/decisions/README.md`.

The files lists matter beyond the item: the backlog compares them to keep parallel work apart.

Each Plan passes `pulse check --plan <path>`, is committed alone as `docs(plan): #<n>`, and is pushed on its item branch. A valid Plan permits the authorized build when prerequisites, file reservations and base checks allow it. #4 can be planned while #3 is open, but cannot build until #3 is integrated.

## Step 4: Build in parallel (`pulse go`)

```bash
pulse status
```

The backlog starts with #2 and #3, because their files do not overlap. #4 waits for #3. Alice wants #2 herself and claims it from her machine (`pulse claim 2`, then `/pulse-build 2`), so Sebastian's run takes #3; #4 waits for the merge of #3:

```bash
pulse go
```

Pulse prepares #3's worktree under `.worktrees/`, reusing its published `feat/3-vote-and-rank` branch. It checks the frozen spec tests fail before implementation, runs the build, then verifies the result and requests review and security audit in one fresh session. The Map shows preparation, actual agent phases and result evidence.

After publication, Pulse rechecks the exact head, base and evidence, integrates with normal hooks and a fast-forward push, and records completion. Only then may #4 build from the updated base. Its result receives its own checks and integrates automatically when they pass.

A person who wants manual final approval first selects it with `pulse auto merge off`. They can then review a result and approve its exact head and base with `a` in the Map or `pulse approve 3` in their terminal. The action is queued locally and becomes authoritative after synchronization. Destructive removal always keeps its separate confirmations. Without a terminal, an explicit `pulse go` starts or reuses a managed process; `pulse go --stop` requests a controlled stop.

Each build follows [`/pulse-build`](../guides/pulse-build): read the code first, write a failing test, make it pass, and prove the Activation Path exists before the item may close. A bug found on the way gets its own fix spec and record ("Discovered in #3") before anyone fixes it.

## Step 5: Test gaps (`/pulse-build`)

Each build already proved its own requirements: one spec test per requirement, written first and frozen. Asked to "write tests", `/pulse-build` covers what lies outside: integration tests across the features and unit tests where coverage still has gaps. Failing tests start a fix loop with four options: fix all, approve each fix, adjust a test because the spec changed (only with a reason on record), or stop and look first. Every round runs the tests again before anything counts as fixed.

## Step 6: Security audit (`/pulse-audit`)

Every feature branch already passed an audit of its own changes before its result became eligible for final approval. Before the release, `/pulse-audit` looks at the whole codebase: OWASP Top 10, the OWASP Top 10 for LLM applications where it applies, static analysis, dependencies, supply chain, and Zero Trust. The report lands in `_devprocess/analysis/AUDIT-retrospectives-<date>.md`. Findings the team does not fix now become fix items that point at the report; nothing stays in a silent "later" state.

## Integrate and release

Each integration updates the shared base. Pulse fetches its current commit and reads the configuration there before starting further work. CI status is not a start or integration gate. Startup does not repeat the full local suite; the supervisor verifies each completed result before integration. Release steps such as versioning, tagging and publishing belong to the project.

## What you end up with

```
_devprocess/
  analysis/       BA-retrospectives.md, EXPLORE-retrospectives.md, Item-BAs, AUDIT-*.md
  requirements/   epics/, features/, fixes/, handoff/architect-handoff.md
  plans/          one Plan per feature
  decisions/      README.md (router) and the records it routes to
```

On the board: one record per feature (#2 to #4, plus any fixes), completed once its result reaches the shared base. `pulse go` closes the epic #1 with the last of them it merges. Every line of code traces back through the checked result, commit (`Refs: #3`), Plan and spec to the BA. A publication that succeeded before an interrupted closure is recovered without integrating twice.

## Pausing and resuming

Say "stop" at any time; `pulse go --stop` stops a managed run cooperatively. Branches, uncommitted work, specs and evidence remain. To pause one item, use `pulse defer <n>` and later `pulse resume <n>` in your terminal or the Map. Waiting work needs no idle claim. `/pulse` reads the retained state and names the next step.