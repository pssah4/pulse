---
title: A full V-Model run
description: From a raw idea to merged code with Pulse, every step and every artifact, for a team of three.
---

# A full V-Model run

This walkthrough takes one idea through every step: business analysis, requirements, plan, a parallel build, tests, and the security audit. Sebastian, Alice, and Bob build a small tool that helps teams run better retrospectives. You see what each step asks, what it writes, and how the three of them share the work.

Reading time about 20 minutes; running it for a proof of concept takes an afternoon.

## The setup

Once per project, in the repository:

```
/pulse-setup
```

This walkthrough spells the commands as Claude Code does. In Codex, type `$pulse:<name>` for `/<name>`, so `$pulse:pulse-setup` here.

Then ask Pulse where to start:

```
/pulse

We want to build a tool that helps teams run better retrospectives.
```

Nothing exists yet, so `/pulse` recommends `/pulse-ba`.

## Step 1: Business analysis (`/pulse-ba`)

The [first business analysis tutorial](./first-business-analysis) shows this step in detail. The agent interviews Sebastian one question at a time: who runs retrospectives, what goes wrong today, which job the tool must do. It writes:

- `_devprocess/analysis/BA-retrospectives.md`: the Project-BA with personas, the How-Might-We question, the value proposition, and the critical hypotheses
- `_devprocess/analysis/EXPLORE-retrospectives.md`: the Exploration Board, for a proof of concept or an MVP
- no Item-BA yet: the first epic of a new project comes straight from the Project-BA; a later epic gets an Item-BA of its own, which inherits the personas by reference

Sebastian approves the BA. The skill pushes it on its docs branch, so Alice and Bob can read it, and goes on with requirements in the same session.

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

- `requirements/epics/retro-board.md`: the epic hypothesis in plain prose, business outcomes with baseline and target
- `requirements/features/anonymous-cards.md`, `vote-and-rank.md`, `action-items.md`: user stories, success criteria without technology ("a participant adds a card in under 10 seconds"), and an Activation Path that names how a user reaches the feature
- `requirements/handoff/architect-handoff.md`: what the plan must respect

Each item is on the board from the moment `/pulse-re` names it, as a draft (`pulse new feat "Vote and rank" --draft` returns #3), so Alice and Bob see a spec in progress and who writes it. Once the specs pass validation, `/pulse-re` commits them on the docs branch, pushes it, and attaches each spec to its draft; before its pull request it runs `pulse check --spec` on the numbered specs:

```bash
pulse new epic "Retro board" --spec _devprocess/requirements/epics/retro-board.md --issue 1
pulse new feat "Anonymous cards" --parent 1 --spec _devprocess/requirements/features/anonymous-cards.md --issue 2
pulse new feat "Vote and rank" --parent 1 --spec _devprocess/requirements/features/vote-and-rank.md --issue 3
pulse new feat "Action items" --parent 1 --blocked-by 3 --spec _devprocess/requirements/features/action-items.md --issue 4
```

Then it commits what `pulse new` wrote into the specs, pushes again, and opens a pull request with the specs into `develop`. Each feature is cut so that its merge reads well on its own: one feature, one traceable merge. Action items need the ranking first, so #4 waits for #3. The team agrees in the sync call that all three are specified well enough. Sebastian merges the pull request, because agents plan from the specs as the base branch has them, and `pulse approve 2 3 4` puts them on the ramp.

## Step 3: Plan

Planning runs inside the build commands: `pulse go` plans each approved feature before it builds it, and `/pulse-build` plans an item it starts without a PLAN. One PLAN per feature in `_devprocess/plans/`: the tasks, the files each task touches, and the decisions made on the way with the options that lost. Tasks that touch different files share a wave and can run at once. A decision that later changes must respect ("cards are stored without author") becomes a decision record behind the router in `_devprocess/decisions/README.md`.

The files lists matter beyond the item: the ramp compares them to keep parallel work apart.

## Step 4: Build in parallel (`/pulse-go`)

```bash
pulse go --dry-run
```

The ramp starts with #2 and #3, because their files do not overlap. #4 waits for #3. Alice wants #2 herself and claims it from her machine (`pulse claim 2`, then `/pulse-build 2`), so Sebastian's run takes #3 and, once the pull request of #3 is ready, #4:

```bash
pulse go
```

It creates a second checkout for #3 beside the repository on the branch `feat/3-vote-and-rank`, starts an agent there, and runs three gates when the build is done: the project's tests, then a review and a security audit, each in a fresh session. All three pass, so #3 gets a ready pull request against the base branch (`develop` here) with `Closes #3`, the gate table, and both reports. #4 was waiting for #3; now it stacks on the branch of #3, runs the same chain, and its pull request targets that branch. `pulse map` shows all of it live: Sebastian's agents with a green light, Alice's item as in progress, #4 moving from waiting to building, `on #3`. Sebastian reads the pull request of #3 and merges it. The next `pulse go` run closes #3 (GitHub does that on its own only for the default branch) and moves the pull request of #4 to `develop`, where he merges it too.

Each build follows [`/pulse-build`](../guides/pulse-build): read the code first, write a failing test, make it pass, and prove the Activation Path exists before the item may close. A bug found on the way gets its own fix spec and record ("Discovered in #3") before anyone fixes it.

## Step 5: Test gaps (`/pulse-build`)

Each build already proved its own requirements: one spec test per requirement, written first and frozen. Asked to "write tests", `/pulse-build` covers what lies outside: integration tests across the features and unit tests where coverage still has gaps. Failing tests start a fix loop with four options: fix all, approve each fix, adjust a test because the spec changed (only with a reason on record), or stop and look first. Every round runs the tests again before anything counts as fixed.

## Step 6: Security audit (`/pulse-audit`)

Every feature branch already passed an audit of its own changes before its pull request was ready. Before the release, `/pulse-audit` looks at the whole codebase: OWASP Top 10, the OWASP Top 10 for LLM applications where it applies, static analysis, dependencies, supply chain, and Zero Trust. The report lands in `_devprocess/analysis/AUDIT-retrospectives-<date>.md`. Findings the team does not fix now become fix items that point at the report; nothing stays in a silent "later" state.

## Integrate and release

When two or more pull requests are ready, `pulse go` ends its run with an integration check: it merges their branches in dependency order in a scratch checkout and runs the project's verify command, and its summary names the branch that does not merge, or the output of a failing verify. A clash between parallel results shows up there before it reaches the base branch. The release itself (version, tag, publish) belongs to the project.

## What you end up with

```
_devprocess/
  analysis/       BA-retrospectives.md, EXPLORE-retrospectives.md, Item-BAs, AUDIT-*.md
  requirements/   epics/, features/, fixes/, handoff/architect-handoff.md
  plans/          one PLAN per feature
  decisions/      README.md (router) and the records it routes to
```

On the board: one record per item (#1 to #4, plus any fixes), closed by the pull requests that delivered them. Every line of code traces back to the BA through the spec, the PLAN, the commit (`Refs: #3`), and the pull request (`Closes #3`).

## Pausing and resuming

Say "stop" at any time. Nothing gets lost: the specs are in the repository and the state is on GitHub. Later, `/pulse` reads both and recommends the next step.
