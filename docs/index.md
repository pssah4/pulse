---
layout: home
title: Pulse
titleTemplate: Parallel, method-driven development with AI coding agents

hero:
  text: |
    Many people. Many agents.
    One repo. No collisions.
  tagline: "Coding agents are fast alone and chaotic together. Pulse plans the dependencies between tasks, starts them in the right order, gives each to one agent, and never runs two at once that touch the same files. Features start as specs, from business analysis to requirements engineering, and a pull request is ready only after tests, review, and a security audit pass."
  actions:
    - theme: brand
      text: Get started
      link: /tutorials/installation
    - theme: alt
      text: A full run, start to finish
      link: /tutorials/full-v-model-run
---

<div class="pulse-live">
  <iframe src="/pulse/map-demo.html" title="The Pulse map: a morning at acme/shop in time-lapse" loading="lazy"></iframe>
  <p>A morning at a small shop project, in time-lapse. Sebastian runs five agents at once; Alice and Bob work on several items in parallel. <span class="k ok"></span> working <span class="k hold"></span> waiting for you <span class="k bad"></span> a check failed. The same view runs in your terminal: <code>pulse map</code>.</p>
</div>

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

## Three parts

| Part | What it gives you |
|---|---|
| [Operating model](./operating-model) | A rhythm for teams where each person works with several agents: three tempos (hourly, daily, every two weeks), a conscious filter that decides what becomes work, roles as hats. |
| [Collaboration](./concepts/parallel-work) | One shared board for people and agents, a ramp that hands out ready work in the right order, `pulse go` to build all of it in parallel, and the live map above. |
| [Digital Innovation Agents](./concepts/v-model) | The method: one command per step from a raw idea to reviewed code. Business analysis, requirements, plan, build with the spec tests first, review, security audit. |

## Quick start

Pulse runs in Claude Code and Codex, in the terminal and in the VS Code extension; support for GitHub Copilot, Cursor, Gemini CLI, and OpenCode will follow. You need Python 3.9 or newer, the GitHub CLI `gh` 2.94 or newer, and a GitHub repository. In Claude Code:

```bash
claude plugin marketplace add https://github.com/pssah4/pulse.git
claude plugin install pulse@pssah4-skills
```

In the Codex CLI:

```bash
codex plugin marketplace add pssah4/pulse
codex plugin add pulse@pssah4-skills
```

Then run `/pulse-setup` in your project (in Codex, trust the Pulse hooks when Codex asks at its first start, under `/hooks` in the CLI or one by one on the Hooks page of the IDE extension's settings, and call it `$pulse:pulse-setup`), and `/pulse` from there on. The VS Code extensions, updates, and removal: [Installation](./tutorials/installation).

## Where the work lives

You never write tickets on GitHub. Epics, features, and plans are Markdown files in your repository, written by the agents together with you and reviewed in pull requests like code. GitHub only keeps the board, one small record per item, so that everyone sees the same state.

<div class="pulse-diagram">
<!--@include: ./diagrams/where-the-work-lives.svg-->
</div>

The `pulse` commands write these records; nobody edits them by hand. Agents ask questions instead of reading files: `pulse status --json` answers "what can I start?" from a local copy. Under the hood the records are GitHub issues with a `pulse:` label, so pull requests close them and GitHub shows dependencies for free. [Where things live](./concepts/where-things-live) has the details.

## Why not just GitHub?

Pulse keeps its records in GitHub issues on purpose: types, sub-issues, dependencies, assignees, and pull requests that close issues all come from GitHub. What GitHub leaves open is the moment several people each run several agents on one repository. GitHub records what exists and who has it; it does not decide what may start now.

| GitHub gives you | Pulse adds |
|---|---|
| Dependencies between issues, shown as "blocked" | One ordered ramp: an item starts only when it is approved, its spec passes the rules, its PLAN exists, and its blockers are done |
| One branch per agent; conflicts show up when the branches merge | The ramp holds back an item whose PLAN touches files another running item holds, before the first line of code |
| An assignee per issue; nothing stops a second agent from taking it too | A claim per session: a second session is refused, the map shows each claim's phase and last sign of life, and a stalled item can be handed over |
| A view of the agent sessions GitHub runs, and of Copilot's own clients | Claude Code and Codex on your own machines and subscriptions, on one live map with your teammates' work |
| Checks and reviews on the pull request | Spec tests first, then tests, review, and security audit in fresh sessions, with fix rounds; the pull request leaves draft only when all three pass, and parallel results are merged and tested together before anyone merges |
| Spec Kit: spec, plan, tasks, implement | The step before the spec (a business analysis with 34 methods), tech-agnostic success criteria, and checks that keep specs and PLANs to their rules |

When one person works with one agent at a time, GitHub and a spec template may be all you need. Pulse pays off once several people and their agents build on the same repository at once.

## The method, one command per step

<div class="pulse-diagram">
<!--@include: ./diagrams/method-steps.svg-->
</div>

The steps run forward on their own and stop for you only where the diagram says so; they loop back when the work teaches something new. A red gate (tests, review, or audit) gets a fix round, and the gates start again at the tests. [`/pulse-go`](./guides/pulse-go) runs planning, build, and the three gates for every approved item in parallel, each feature on its own branch with one pull request back to the base branch. Each command has a [guide](./guides/pulse); `/pulse` tells you where you stand and what comes next.

## What Pulse keeps out of your way

- **No status in documents.** Specs describe the work. Its state (approved, taken, blocked, done) sits on the shared board, and agents ask `pulse status` instead of reading a backlog file.
- **No rules that only work when someone types a command.** The rules reach every agent session and every subagent automatically.
- **No bookkeeping by prompt.** Claims, dependencies, the ramp, and the checks are scripts, so no model has to remember them.
