---
title: Parallel work
description: How Pulse decides what runs at the same time, and how parallel results merge without surprises.
---

# Parallel work

When a coding agent ships a feature in an afternoon, the bottleneck moves from writing code to deciding what can run at the same time without colliding. Pulse makes that decision with a script, not with a prompt, so an agent cannot forget to parallelize and cannot start two things that will conflict.

## Two hard constraints

1. **Blockers first.** An item is built only when every item that blocks it is done, or when its one open blocker has a ready pull request (see stacking below). Planning does not wait for blockers. The records on the board hold these links ("blocked by"), and the ramp reads them.
2. **Disjoint files.** Two items run at the same time only if their PLANs touch different files. Every PLAN lists its files at the top; the ramp compares them with everything that is already running.

The second rule catches merge conflicts and duplicate work in one criterion. It is conservative on purpose, and it needs a PLAN: an item without one waits at `needs a plan` until `pulse go` has planned it, so no build ever starts with unknown files.

## The ramp

Every open item nobody works on lines up like pallets at a loading dock, in the team's order, and agents pick up ready work from the front. The ramp is the ordered backlog: each item appears once, with what it waits for.

- **Order:** the team decides it. Move an item on the [map](../guides/pulse-map#moving) (`Enter` opens it, `m` moves it, the arrows pick its place, `Enter` places it), or with `pulse rank <n> --before <m>` (or `--after <m>`, `--top`, `--bottom`), and its record gets a rank. A move writes the rank of the moved item and no other, so two people sorting at the same time end in an order one of them chose; only items above it that have no rank yet get one too. A blocker carries the best rank of what waits for it, so moving an item above its blocker pulls the blocker along (the ramp says `for #n`), and no order can put an item before its blocker. Items without a rank follow the critical path, which is Pulse's proposal: the item that unblocks the most remaining work first.
- **What each line waits for:** `not approved`, `spec: <rule>`, `needs a plan`, `plan: <rule>`, `plan waits for you`, `waits for #n`, `locked: <file> in use by #n`, then `queued` and `starts next`. `pulse go` plans what needs a plan and builds from the top.
- **Slots:** `cap` in `.pulse/config.toml` sets how many items run at once for you. Your own running items take slots; a teammate's running item takes none of yours, but its files are held for everyone. When Alice works on #12, Sebastian keeps all four of his slots, and the files of #12 stay off limits for his agents until Alice is done.
- **Locked:** a ready item whose files another running item holds waits, and the ramp names the file and the holder: `#18 ui: settings panel   locked: token.ts in use by #11`. `pulse claim` refuses such an item with the same file and holder, so a build started by hand waits too.
- **Waits:** an item with an open blocker waits until the blocker is done, or, when it has only that one, until the blocker's pull request is ready: `#13 ui: token banner   waits for #11`.

`pulse status` prints it once; the [map](../guides/pulse-map) draws it live.

## How far it goes: the parallel level

| `parallel` | What runs at once |
|---|---|
| `off` | one item at a time |
| `items` (default) | every ready item with disjoint files, up to `cap` |
| `max` | as `items`, plus parallel task waves inside an item; when ready work waits and a slot is free and no `pulse go` runs, a new session is told so at its start |

## Planning so that more can run at once

- **Contract first.** If item B needs item A only for an interface (a type, an endpoint signature, a schema), that interface becomes its own small item that blocks B. A's implementation no longer blocks B, and B starts as soon as the contract's pull request is ready (see stacking).
- **Stacking.** A feature with exactly one open blocker A whose pull request is open and ready (no draft) does not wait for A's merge. It starts on A's branch, and its own pull request targets A's branch. This holds at every parallel level, and the PLAN declares nothing for it. After A is merged, the next `pulse go` run moves the stacked pull request to the base branch.
- **Waves.** Inside a PLAN, tasks carry a wave number. Tasks of one wave touch disjoint files and do not need each other's output, so at `max` they run as parallel subagents; the wave's checks pass before the next wave starts. `pulse check` keeps the files of a wave disjoint.

## Merging parallel results

Every feature gets its own branch, `<type>/<n>-<slug>`, and exactly one pull request back to the base branch. On that branch `pulse go` runs three gates in order: the project's tests (`verify`), a review, and a security audit, the last two in fresh sessions. A red gate gets a fix round, at most two per gate, and after every fix the gates start again at the tests. The pull request is ready only when all three passed; otherwise it stays a draft that names what is open, and the item keeps its claim, so no later run builds it again. You merge each ready pull request. GitHub closes an item on its own only when the merge goes into the default branch; for another base branch, such as `develop`, the next `pulse status` or `pulse go` closes it.

Disjoint files make independent pull requests merge cleanly against the base branch. Dependencies merge in order: a blocker before the items it blocks, a stack base before what is stacked on it. At the end of a `pulse go` run with two or more ready pull requests open, the integration check merges their branches in that order in a scratch worktree and runs the project's `verify` command there, before anyone merges. A textual conflict names the branch that does not merge after the ones before it, and a red `verify` prints the end of its output, so a semantic conflict between two parallel results shows up before it reaches the base branch.

## Who starts the agents

[`pulse go`](../guides/pulse-go) does. It plans every approved item that has no PLAN yet, claims the next items to build, and creates one worktree per item beside the repository (a second checkout in its own folder, on the item's branch). In each it starts one agent without a chat window (Claude Code or Codex, from a template in the config), refills a slot the moment it frees up, runs the tests, the review, and the security audit on each finished item, opens its pull request with the results, and gives a failed item back to the ramp. The [map](../guides/pulse-map) lists each feature under its person with the step of its chain or the state of its pull request, and `on #n` when it is stacked. Headless agents keep your permission rules: Pulse never bypasses an approval.

One `pulse go` run can drive Claude Code and Codex together, each with its own slots, and hands an item on when one of them hits its usage limit.

## Claims and handover

A claim belongs to one session: a Claude Code session, a Codex thread, a `pulse go` run, or your terminal. All of them act under your GitHub login, so each claim also leaves a mark on the issue that names its session. A second session is refused, and of two claims at the same moment the older mark wins. The refusal names the holder, since when, and the command that frees the item, and the [map](../guides/pulse-map) shows the phase of a teammate's claim and its last sign of life ([What others see](#what-others-see)).

- **Hand over another person's claim:** `pulse release --take <n>`, after that person agreed. Their assignee and claim marks go, a comment on the issue names who did it, and the new session claims as usual. An agent runs it only on your yes.
- **Take over from a session of your own that has ended:** `pulse claim --take <n>`.
- **Take an approval back:** `pulse approve --undo <n>`; until someone approves the item again, nothing claims it.

`release` and `done` refuse a claim that is not yours; `pulse done --take <n>` closes an item whoever holds it. The levers that belong to a person (`approve`, `approve-plan`, `rank`, `done`, and `release --take`) refuse to run inside an agent that `pulse go` started, which carries `PULSE_HOLDER`. Such an agent holds as its run, so it claims, gives back, and blocks only its own item, which `PULSE_ITEM` names.

## What others see

Your teammates see your work through the board and the pushed branches ([Where things live](./where-things-live#what-the-team-sees-and-when) lists what reaches them when). The [map](../guides/pulse-map) and `pulse status` draw it per item:

| The map says | What it means | What to do |
|---|---|---|
| `spec in progress by alice, 20 min` | Alice's BA or spec session registered the item as a draft and holds it | talk to her before you write about the same thing; `/pulse-ba` and `/pulse-re` show overlapping drafts before they write |
| `building, 4 min ago` | a teammate holds the item: the phase of the holding session and the age of its last sign of life | nothing; the item's files are held for everyone |
| `no sign of life for 2 h` | the holding session has been silent for 30 minutes or more: it ended, lost its network, or waits for its person | ask the holder, then take over as below |
| `last run: <note>` | nobody holds the item; its last holder gave it back with a note that says why and which branch holds its work: a `pulse go` run after a failure, a usage limit, or a stop, or a session with `pulse release <n> --note` | claim it as usual and go on from that branch |

The phase comes from the session that holds the item. `pulse go` reports each phase it starts (`planning`, `building`, `tests running`, and so on) and every 10 minutes while one runs, an interactive session reports `working` at most every 10 minutes while it holds an item, and the skills report with `pulse beat <n> <phase>`. `pulse show <n>` prints the same as fields, the whole note included.

### Taking over

The work travels on the item branch: `pulse go` pushes it after every agent phase that committed, so whoever holds the item next starts from there. A free item with a `last run` note is claimed as usual; `pulse go` starts its worktree from the pushed branch on its own, and in a session `/pulse-build <n>` continues on that branch. An item someone still holds is freed first with the [handover commands](#claims-and-handover): `pulse release --take <n>` once the other person agreed, `pulse claim --take <n>` for a session of your own that ended. The new holder then continues on the branch the last one pushed.

What the last holder did not push stays in their clone; a phase that `pulse go` stopped halfway leaves its changes in that run's worktree. `pulse go` runs once per clone. Runs in other clones, your own or a teammate's, split the work through the claims.
