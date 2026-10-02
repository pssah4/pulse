---
layout: home
title: Pulse
titleTemplate: Coding agents across developers and machines
description: Coordinate your team's Claude Code and Codex agents across developers and machines, with a shared GitHub board and a workflow from specs to checked integration.

hero:
  name: "One team. One pulse."
  text: Coordinate coding agents across developers and machines.
  tagline: "Each developer runs Claude Code or Codex in their own clone. Pulse coordinates work through shared claims, dependencies and planned files, then takes each item through tests, review and security audit to integration. Regular checked results complete automatically; manual final approval is an option."
  actions:
    - theme: brand
      text: Get started
      link: /tutorials/installation
    - theme: alt
      text: A full run, start to finish
      link: /tutorials/full-v-model-run
---

<div class="landing-features">
  <a class="tile" href="/pulse/tutorials/first-business-analysis">
    <h3>Starting from a raw idea?</h3>
    <p>The agent walks you through structured discovery: who the users are, what job they need done, which assumptions could sink the idea. 34 innovation methods are at hand before a single line of code.</p>
    <span class="arrow">Run your first business analysis →</span>
  </a>
  <a class="tile" href="/pulse/guides/pulse-realign">
    <h3>Starting with existing code?</h3>
    <p>Pulse reads the code and writes down what it finds: the decisions already made, the features already there, each with its source. Projects on the Digital Innovation Agents plugin, the predecessor of Pulse, move over the same way.</p>
    <span class="arrow">Run /pulse-realign →</span>
  </a>
</div>

## Your agents run locally. The team shares the work.

Alice starts `pulse go` on her laptop. Bob starts it in his clone on another machine. Both runners use the same board: they claim items, start agents in separate worktrees, and compare planned files with the work the team already holds. Each person has their own agent slots, permissions, and subscriptions.

Work becomes visible during scoping: `/pulse-ba` and `/pulse-re` register drafts before implementation starts. Specs and Plans live on item branches. GitHub hosts the item board and a shared Git branch for confirmed claims and progress. Local actions are saved before background synchronization, with no additional coordination service for your team to operate.

The map shows each person's items, runner phases, and last heartbeat. Detailed tool activity stays in the local clone. Shared revisions serialize competing claims. Planned file reservations reduce overlap, but actual changes can still conflict. [Parallel work](./concepts/parallel-work) explains those boundaries and how to hand work over.

## Three parts

| Part | What it gives you |
|---|---|
| [Operating model](./operating-model) | A rhythm for teams where each person works with several agents: three tempos (hourly, daily, every two weeks), a conscious filter that decides what becomes work, roles as hats. |
| [Collaboration](./concepts/parallel-work) | A shared board across people and machines, an ordered queue, `pulse go` to run local agents against it, and `pulse map` to see the team's work. |
| [Digital Innovation Agents](./concepts/v-model) | The method: one command per step from a raw idea to reviewed code. Business analysis, requirements, plan, build with the spec tests first, review, security audit. |

## Quick start

Pulse runs in Claude Code and Codex, in the terminal and in the VS Code extension; support for GitHub Copilot will follow. You need Python 3.9 or newer, the GitHub CLI `gh` 2.94 or newer, and a GitHub repository. In Claude Code:

```bash
claude plugin marketplace add https://github.com/pssah4/pulse.git
claude plugin install pulse@pssah4-skills
```

In the Codex CLI:

```bash
codex plugin marketplace add pssah4/pulse
codex plugin add pulse@pssah4-skills
```

Then run `/pulse` in your project (in Codex, trust the Pulse hooks when Codex asks at its first start, under `/hooks` in the CLI or one by one on the Hooks page of the IDE extension's settings, and call it `$pulse:pulse`): it sets Pulse up where it is missing and says what comes next. The VS Code extensions, updates, and removal: [Installation](./tutorials/installation).

## Where the work lives

Business analyses, epics, features and Plans are Markdown files versioned with the code. Each item keeps its spec, Plan and implementation on one published branch. Valid specs permit planning; valid Plans permit building when dependencies and file reservations allow it. Existing Plans and unfinished work are preserved when a run resumes.

<div class="pulse-diagram">
<!--@include: ./diagrams/where-the-work-lives.svg-->
</div>

The `pulse` commands manage the shared state; nobody edits it by hand. `pulse status --json` reads a local view. GitHub holds the item catalog and relationships; a shared Git branch holds claims, results and integration state. Local actions enter a durable outbox and gain team authority only after synchronization confirms them. Pulse closes an item after proving its result reached the shared base. [Where things live](./concepts/where-things-live) has the details.

## What Pulse coordinates

Pulse uses GitHub for item types and relationships. Shared Pulse state coordinates who may write and what may integrate when several people each run several agents on one repository.

| Step | What happens |
|---|---|
| Register | Draft records expose analysis and specification work before code is written |
| Select | The ordered queue considers published specs and Plans, dependencies and files already reserved by the team |
| Execute | Each person's runner claims items and starts Claude Code or Codex in local worktrees |
| Verify | The runner executes project tests, review and security audit, then publishes the checked result |
| Integrate | Final approval binds the exact result and base, automatically by default or under a chosen manual policy; Pulse merges with project hooks |

Pulse fits teams that want this workflow across their own machines and are willing to maintain specs and plans. For one person working on one item at a time, issues and branches may be enough. For messaging, shared infrastructure leases, or a configurable skill pipeline, other tools may fit better. [Choosing a coordination tool](./concepts/choosing-a-coordination-tool) compares those uses with sources and a review date.

## The method, one command per step

<div class="pulse-diagram">
<!--@include: ./diagrams/method-steps.svg-->
</div>

The steps run forward within the authorized task and loop back when the work teaches something new. A red gate gets one fix round, followed by tests. Green review or audit evidence may carry to a new commit only when its Git tree is identical; changed contents require both checks again. [`pulse go`](./guides/pulse-go) processes the queue. Add a free-text objective directly, such as `pulse go finish Epic 4 and investigate the UI problem`, to add that work through the same visible item workflow. Explicit scope restrictions bound the run. A start without a terminal uses a managed process. Regular checked results integrate automatically by default; a person may select manual final approval of the exact head and base. Each command has a [guide](./guides/pulse); `/pulse` tells you where you stand and what comes next.

## What Pulse keeps out of your way

- **No status in documents.** Specs describe the work. Its state (claimed, held, waiting, done) sits on the shared board, and agents ask `pulse status` instead of reading a backlog file.
- **No rules that only work when someone types a command.** The rules reach every agent session and every subagent automatically.
- **No bookkeeping by prompt.** Claims, dependencies, the ramp, and the checks are scripts, so no model has to remember them.
