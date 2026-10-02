---
title: Where things live
description: Published item branches, a shared Git state branch, durable local actions and GitHub item relationships.
---

# Where things live

Pulse separates item content, confirmed team state and local intent. The Map combines them, while keeping a pending action distinct from a confirmed result.

| Fact | Authoritative home | How to read it |
|---|---|---|
| What an item is and why: BA, epic, feature, improvement or fix | Markdown in `_devprocess/` on the published item branch | the spec path in the item record |
| How it gets built: tasks, files and checks | the Plan in `_devprocess/plans/`, on the same branch | `pulse status <n>` and the Plan itself |
| Item identity, parent, dependencies and findings | GitHub issue records and authenticated comments | `pulse status`, the Map or the issue |
| Claims, file reservations, holds, results, approvals and integration | the dedicated `pulse-state` branch on `origin` | Pulse's shared-state reader, surfaced in status and the Map |
| An action accepted locally but not yet confirmed | the protected SQLite outbox for this clone | the action's `queued`, `syncing`, `confirmed`, `conflict` or `error` status |
| A run's objective, scope, criteria and progress | the protected local goal record in the same database | `pulse go`, status and the Map |
| A run's applied goal, process and activity | its persistent local runner report | status and the Map; a newer local goal is shown as pending until applied |
| Decisions that constrain later changes | `_devprocess/decisions/` | the router's “Read When” column |
| Rules for sessions and areas of the code | Pulse hooks and path-local `AGENTS.md` files | session startup and file reads |
| Behavior, history and authorship | code, tests and Git commits | read the implementation, run checks and use `git log` |

## The board on GitHub

Each epic, feature, improvement and fix has one small GitHub issue record. Pulse writes its type, spec link, parent and blockers, and publishes findings there. The item description and implementation Plan remain versioned documents. No pull request is needed to register, build, review or integrate an item.

<a id="why-state-does-not-live-in-the-repository"></a>

### Shared state outside item branches

A claim written on a feature branch would remain invisible until that branch was merged. Pulse instead publishes shared state to `origin/pulse-state`, independently of the checked-out branch and index. Updates carry the item revision they observed. Competing or stale operations can conflict instead of silently replacing a newer claim or approval.

A confirmed claim identifies its current holder and reserved files. Only that holder may publish the associated work. Integration also reserves a shared slot and checks current state before publishing the base update. These checks coordinate participating Pulse processes; they do not promise that arbitrary external edits or undeclared file changes cannot conflict.

### What a record holds

Reserve a draft before writing its spec:

```bash
pulse new feat "<title>" --draft
```

Use its number in the item branch, such as `feat/<n>-<slug>`, and work in that branch's worktree. Commit and push the spec, then attach it to the existing draft:

```bash
pulse new feat "<title>" --spec <path> --issue <n>
```

Commit and push any registration metadata on that same branch. A spec carries `issue:` and document links such as `parent:`. A valid published spec can be planned without a separate merge to the base. A valid published Plan permits building when dependencies and reservations allow it; there is no early approval label or Plan approval to obtain.

| Field or state | Meaning |
|---|---|
| title, type, spec | the visible identity and published document path |
| draft | specification work is still needed before planning or building |
| parent, blocked by | hierarchy and work that must finish first |
| claim and files | the confirmed holder and current file reservations; a waiting result needs no coding-agent claim |
| hold or stop request | work must stop or remain paused; the writer preserves its work before acknowledging a handoff |
| failed | a failed phase and its recovery information; inspect the preserved work and use `pulse resume <n>` to continue |
| result | the published branch, exact head and base, with tests, review and audit outcomes |
| approval | authority for that exact result head and base, under the current final approval policy |
| done | confirmed integration into the remote base; issue closure alone does not prove this |

Legacy spec approvals, Plan approvals and PR status grant no integration authority. Pulse can display older records during migration, but current operations use confirmed shared state.

## Which account acts

The supervisor uses the GitHub account configured for `gh` and names the acting account in the UI. Agent workers receive neither a GitHub token nor the supervisor's `gh` login. Permission checks for approval and integration remain separate from a comment's display name or an issue assignee.

Regular checked results complete automatically by default. A person with repository write access can choose manual final approval. Both modes bind the result head and base and respect holds and revocations. A person can also request a claim handoff across accounts with `pulse release --take <n>`; the writer must stop and preserve its work before the handoff is confirmed. See [pulse go](../guides/pulse-go).

## What the team sees, and when

Each teammate runs local agents against the same board and shared Git state. Pushed commits make work available to other clones. Detailed tool activity, logs and unpushed edits stay local; moving a claim does not transfer that unpublished work.

| What | Local state | When it becomes shared |
|---|---|---|
| Draft registration | the session prepares the item | GitHub confirms the record; a writer also needs a confirmed claim |
| Spec, Plan and implementation | the item worktree and its branch | their commits are pushed to `origin`; the runner publishes completed agent phases |
| Approve, defer, resume, revoke or handoff | a durable outbox entry, bound to the displayed item revision | synchronization returns `confirmed`; a queued action alone grants no team authority |
| Claim and reserved files | the caller awaits its shared receipt | the shared-state push succeeds; other clients observe it on their next read |
| Gate evidence | protected local records bound to the checked commit | the result is published to shared state, with review and audit reports on the item |
| Integration and closure | an isolated normal merge with the project's hooks | the base and state publish together; Pulse proves ancestry before completing closure |
| Run logs and goal progress | the clone's local report, logs and protected goal database | visible to this clone's sessions; they are not a team coordination service |

Local defer intent blocks this clone immediately while synchronization is pending. A local revoke also prevents this clone from integrating, including a merge already in progress. Resume grants no permission until it is confirmed. A confirmed revoke withdraws the shared approval. Closing the Map does not discard the outbox: a background synchronizer can continue without an LLM session. A conflict or error remains visible for inspection and retry.

The board cache and runner logs live under `pulse/` in the clone's shared Git directory, commonly `.git/pulse/`. Trusted gate evidence and the SQLite outbox live in the user's cache, outside the agent worktree and shared Git directory. Linked worktrees of one clone share these records; another clone has its own local cache and outbox and reads the same remote state branch.

The [Map](../guides/pulse-map) shows preparation, current phase, holds, failures, results and local action status. A claim is not kept merely to show that work exists. Published work, preserved worktrees and recovery notes remain available after a claim is released. [Parallel work](./parallel-work#what-others-see) explains the collaboration view.

## What that rules out

- **No workflow status in specs.** A spec carries `issue:` and document links. Claims, holds and completion belong to shared state.
- **No hand-maintained backlog table.** Status and the Map derive their view from the records and current shared state.
- **No early approval gates.** Spec and Plan validation determine readiness; final integration approval binds a checked result.
- **No PR dependency.** Item branches, authenticated evidence and confirmed state carry the workflow.
- **No duplicated implementation description.** Decisions explain choices; their Sources appendix can point to code that may later move.

## What reading costs

Status and the Map reuse local caches. The Map refreshes its data in the background and distinguishes last-known state from pending local actions. Accepting an outbox action does not wait for a full GitHub board read; it binds the revision already shown. If there is no cached item, open or refresh the Map first.

Before publishing or integrating, the supervisor reads the state and remote commits needed to authorize that operation. Cached UI state alone cannot grant permission. Agents still read their own spec, Plan and relevant decisions in full; the board saves them from scanning every other item's documents to find available work.
