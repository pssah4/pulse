---
title: /pulse
description: The entry point. Where the work stands, what comes next, and which command fits.
---

# /pulse

`/pulse` reads the situation and recommends one next step. You decide.

## Where things stand

It runs `pulse status` and sums up in a few lines: what is ready, what is in progress and who holds it, what waits for you, what is failing, and what is blocked by what. If Pulse is not active in the repository, it says so and sets it up with you ([below](#set-up-go-and-the-map)).

## What comes next

The commands are spelled as in Claude Code, on this page and on the map. In Codex, type `$pulse:<name>` for `/<name>`, so `$pulse:pulse-ba` for `/pulse-ba`.

| Situation | Recommendation |
|---|---|
| Something waits for you (an open question, a red test) | that first |
| No method artifacts, an empty or new repository | [`/pulse-ba`](./pulse-ba) for the project BA |
| Code exists but no BA and no specs, or a project from the predecessor plugin | [`/pulse-realign`](./pulse-realign) |
| The project BA is a draft | `/pulse-ba` in Validation Mode |
| A new epic or feature is wanted | `/pulse-ba` for its item BA |
| A validated project BA or an item BA exists, no epics or features yet | [`/pulse-re`](./pulse-re): reserve each item's draft number, commit and push its spec on `<type>/<n>-<slug>`, then attach it with `pulse new --spec <path> --issue <n>` |
| A published spec or Plan has structural findings | fix its R1-R6 or P1-P6 findings with `/pulse-re` or planning |
| Published items need Plans, or valid Plans are ready to build | explicitly start [`pulse go`](./pulse-go) for ready work in parallel, or [`/pulse-build <n>`](./pulse-build) for one item |
| A verified published result waits for you | read its diff, tests, review, audit and findings, then `pulse approve <n>` in your terminal or `a` in the Map approves the exact head and base |
| A result has a red gate or stale evidence | preserve and repair or revalidate it; `pulse resume <n>` requests retry of failed work, while final approval cannot bypass findings |
| A local action is queued, syncing, conflicted or failed | read its state and reason; only confirmed shared approval authorizes integration |

| A release is coming | [`/pulse-audit`](./pulse-audit) |

## New work without a kind

For an explicit `pulse go` request, pass the complete objective directly after the command; the runner resolves and registers the work. For other new-work requests, `/pulse` asks one question: a new feature, an improvement on an existing feature, or a fix? A new feature with an unclear problem goes to `/pulse-ba`, with a clear one to `/pulse-re`. Improvements and fixes go to `/pulse-build`.

## The V is a decision graph

Phases run forward by default and loop back when the work learns something: a bug found while building becomes a fix item ("Discovered in #n"), a design that proves wrong updates the decision or the Plan, a requirement gap goes back to the spec. A loop back never re-runs later phases on its own; the item's spec records what was decided.

<a id="three-gates"></a>

## Final integration approval

Preparation proceeds through spec, Plan, tests and implementation under your task authorization. There is no routine approval between these phases. After tests, review and audit pass, Pulse publishes the result and releases inactive claims. Regular checked results integrate automatically by default. With manual final approval selected, you approve the exact head and base commits with `pulse approve <n>` or `a` in the Map.

The action is saved locally before synchronization. `queued` and `syncing` are pending; `confirmed` means shared state accepted it; `conflict` or `error` names what must be resolved. Defer and revoke block locally at once. A background synchronizer continues after the Map closes. The runner rechecks approval, permissions, head, base and evidence before integrating with normal Git hooks. A changed result or base needs revalidation and a new approval. See [Final approval](./pulse-go#final-integration-approval).

## Set up, go, and the map

`/pulse` helps configure [`pulse setup`](./pulse-setup), execute an explicitly requested [`pulse go`](./pulse-go), and open the [Map](./pulse-map). In a terminal the runner stays in the foreground; without a TTY Pulse starts or reuses its managed process and returns a confirmed receipt with report and log. The skill reads its actual state before reporting success. `pulse go --stop` requests a controlled stop. Runner agents cannot start a nested runner.

The Map shows progress and offers final integration approval, defer, resume, revoke and handoff. These actions belong to you; the agent names the command for your terminal and never types keys into the Map for you, unless you granted it your levers (below). `pulse auto` displays the final approval policy. A person can choose manual approval with `pulse auto merge off` or restore automatic approval with `pulse auto merge on`.

## Let an attended session pull your levers

When an attended Claude Code session should carry the workflow through by itself, you can grant it your levers once. The session runs `pulse levers allow run`, `session` or `always` on its own; Claude Code then shows you its own permission dialog, which neither the model nor the auto mode classifier answers. Only your confirmation makes the grant. In the Map, `l` on a session line opens the settings, where you grant a session `run` or `session`, every attended session `always`, or revoke them.

| Scope | Holds |
|---|---|
| `run` | until the `pulse go` run that runs at the grant ends; without a run until your next message to that session |
| `session` | for that Claude Code session and its subagents |
| `always` | for every attended Claude Code session in this clone, until you revoke it |

Under a grant the session pulls approve, defer, resume, revoke, handoff, retry, discard, delete, `pulse auto merge on|off`, `claim --take` and `release --take` itself, as well as `gh pr ready|merge`, pushes to the base branch and `git push --force-with-lease` on an item branch. Force pushes, `--force-with-lease` on the base, `--no-verify`, disabled hooks and removed session markers stay closed under every grant; tests, review, audit and the binding of an integration to head and base still apply. Every use is logged: `pulse levers` and the Map's settings show the grants and the latest uses, and a lever on an item leaves a comment there that names the session and the grant. `pulse levers off` in your terminal, or revoke in the Map, ends every grant at once.

Grants live in Pulse's local store outside the repository, never in a file, the config or the environment. Unattended sessions (`claude -p`), agents of `pulse go` and child sessions get none. Codex gets none either: it has no dialog the model cannot answer and does not tell an attended session apart, so its levers stay yours.

## Commands

| Command | Does |
|---|---|
| `/pulse-ba` | business analysis: problem, users, scope |
| `/pulse-re` | epic, features, success criteria, registered items |
| `/pulse-build` | implementation, test first (planned first when it has no Plan), bugs, tests for existing code |
| `/pulse-audit` | security audit: the third gate of every feature, or by hand with a chosen scope |
| `/pulse-realign` | take over existing code, or move a project from the predecessor plugin |
| [`/pulse-go`](./pulse-go) | start or steer `pulse go` from the chat, with your whole text as its goal |
| [`/pulse-off`, `/pulse-on`](./pulse-setup#your-own-switch) | turn Pulse off or on for you in this project, or with `--host` on your computer, without changing your team's configuration |

[Planning](./pulse-plan) runs as a step inside `/pulse-re`, for each ready feature, improvement, or fix in its session (an epic gets no Plan), and inside `/pulse-build` and `pulse go`; review and audit run inside `/pulse-build` and `pulse go`.

The `pulse` command line behind these commands is documented in [Commands](../reference/commands).
