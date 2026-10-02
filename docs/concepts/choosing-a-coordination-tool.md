---
title: Choosing a coordination tool
description: Compare Pulse, Commons, and agent-sync with task-pipeline for coordinating coding work across sessions and machines, with dated sources and practical tradeoffs.
---

# Choosing a coordination tool

Several tools coordinate coding work across independent sessions and machines. This page compares Pulse, [Commons](https://github.com/t54-labs/agent-commons), and [agent-sync](https://github.com/ssheleg/agent-sync) with [task-pipeline](https://github.com/ssheleg/task-pipeline) for that shared need.

**Reviewed on 2 October 2026. Maintained by the author of Pulse.** The table describes the source snapshots linked below. It covers coordination and workflow, without ranking speed, code quality, or reliability. Other tools and integrations exist; this is a focused selection.

## Features and requirements

agent-sync and task-pipeline are separate projects from the same author. They are grouped here because one provides coordination and the other provides a development workflow. Their components still need to be configured for the host project.

| Criterion | Commons | agent-sync with task-pipeline | Pulse |
|---|---|---|---|
| Shared state across machines | A private Relay stores coordination state; the team operates the service and its storage. Local mode is also available. [Setup][commons-team] | Git-backed leases coordinate ownership across machines. A shared backend such as Outline provides awareness and a board; the filesystem backend keeps that view local. [Backends][sync-backends] | GitHub hosts the item board and a Git branch for shared Pulse state. Each clone keeps a cache and local action outbox; no additional coordination service is required. [Storage](./where-things-live) |
| Starting agents | Coordinates agents already started in their own runtimes, through a CLI and skill. [Product boundary][commons-why] | The host agent or an external executor drives the pipeline. The work graph reports runnable nodes and leaves dispatch to that caller. [Work graph][pipeline-graph] | Each person's `pulse go` starts local Claude Code or Codex agents in worktrees and refills available slots. [Runner](../guides/pulse-go) |
| Work structure | Tasks, owners, blockers, plans, messages, and evidence-bearing updates. [Overview][commons-readme] | Configurable stages and gates, with a graph of dependencies and declared file touches. [Stages][pipeline-readme], [graph][pipeline-graph] | Draft registration during analysis and specification, then specs, Plans, dependencies, builds and checked integration. [Lifecycle](./where-things-live#what-the-team-sees-and-when) |
| Coordination safeguards | Named resource leases with expiry and fencing epochs. Integrations can use those epochs to reject stale holders. [Leases][commons-why] | Git-ref arbitration for cross-machine task leases; configured file guards have Claude Code hooks. [Leases and hooks][sync-backends] | Shared Git revisions serialize competing claims and reserve planned files. Unplanned edits can still overlap. [Boundaries](./parallel-work#coordination-boundaries) |
| Verification workflow | Records evidence and distinguishes reported work from independent acceptance; execution stays with the connected agents and systems. [Evidence][commons-why] | Configurable automatic, judgment, and manual gates; the example flow includes build, tests, deployment, documentation, and acceptance. [Workflow][pipeline-readme] | The runner executes project tests, review and security audit before integration. Final approval binds the exact result and base, automatically by default or under a chosen manual policy. [Gates](./verification-gates) |

## Choose by the work you need to coordinate

These recommendations follow from the boundaries above:

- **Consider Commons** when independent agents need discovery, messages, handoffs, and leases over shared resources such as a staging environment or database. Its private Relay gives the team a coordination service to operate. [Product scope][commons-why]
- **Consider agent-sync with task-pipeline** when you want task leases alongside a development process whose stages and gates you can configure. Plan for the shared backend, lease configuration, and host-agent integration. [Configuration][sync-backends], [pipeline configuration][pipeline-readme]
- **Consider Pulse** when several developers use Claude Code or Codex in their own clones and want a shared GitHub queue with local agent execution through to checked integration. Adopting it includes specs, Plans and final approval in Pulse. [Parallel work](./parallel-work)

For one person working on one item at a time, ordinary issues and branches may be enough. Running on several machines alone is not a reason to adopt any particular workflow.

## Boundaries to check before adopting

For Pulse, reservations cover the files declared in a plan. They cannot account for every actual edit or semantic interaction. Shared Git revisions serialize competing claims, but do not prevent arbitrary writes outside Pulse. The shared map shows item phases and heartbeats; detailed tool activity and unpushed work stay in the originating clone. A handover needs to account for that local work. [Coordination boundaries](./parallel-work#coordination-boundaries)

For agent-sync, cross-machine exclusion requires its Git lease backend. task-pipeline's separate execution authority in the reviewed source uses SQLite on a local filesystem; it explicitly limits its guarantee to one host. A distributed executor needs an appropriate authority adapter. [Lease configuration][sync-backends], [execution authority][pipeline-authority]

For Commons, resource leases and fencing coordinate cooperating integrations. A lease does not itself authorize a deployment or prevent arbitrary writes by a tool that ignores it. [Lease boundary][commons-why]

## Source snapshots

The links in the table pin each statement to the reviewed source. A source snapshot can include changes absent from a packaged release. In particular, the reviewed Commons README recommends version 0.4.0 for its stable installation while describing work on its 0.5 development line. Check the installation instructions for the version you will use. [Release distinction][commons-readme]

| Project | Reviewed snapshot |
|---|---|
| Commons | [6e91123](https://github.com/t54-labs/agent-commons/tree/6e911236127dc6cf0d231add87e302974151a7f4) |
| agent-sync | [637424e](https://github.com/ssheleg/agent-sync/tree/637424ee9fdfde9f8ab21c21782e9fc8f034d238) |
| task-pipeline | [c5ce69b](https://github.com/ssheleg/task-pipeline/tree/c5ce69b1735334db5219104026c9fda798319aa6) |
| Pulse | [v0.3.0](https://github.com/pssah4/pulse/tree/v0.3.0), including its [shared-state implementation](https://github.com/pssah4/pulse/blob/v0.3.0/pulse/shared.py), [claim implementation](https://github.com/pssah4/pulse/blob/v0.3.0/pulse/state.py) and [runner guide](https://github.com/pssah4/pulse/blob/v0.3.0/docs/guides/pulse-go.md) |

This is a documentation and source review. It does not establish how these systems perform in a production team. If a statement has changed, please [open an issue](https://github.com/pssah4/pulse/issues) with the relevant version and source so it can be corrected.

[commons-readme]: https://github.com/t54-labs/agent-commons/blob/6e911236127dc6cf0d231add87e302974151a7f4/README.md
[commons-why]: https://github.com/t54-labs/agent-commons/blob/6e911236127dc6cf0d231add87e302974151a7f4/docs/why-commons.md
[commons-team]: https://github.com/t54-labs/agent-commons/blob/6e911236127dc6cf0d231add87e302974151a7f4/docs/team-onboarding.md
[sync-backends]: https://github.com/ssheleg/agent-sync/blob/637424ee9fdfde9f8ab21c21782e9fc8f034d238/README.md#backends
[pipeline-readme]: https://github.com/ssheleg/task-pipeline/blob/c5ce69b1735334db5219104026c9fda798319aa6/README.md#configure-it-for-your-project
[pipeline-graph]: https://github.com/ssheleg/task-pipeline/blob/c5ce69b1735334db5219104026c9fda798319aa6/plugins/task-pipeline/skills/task-pipeline/references/work-graph.md
[pipeline-authority]: https://github.com/ssheleg/task-pipeline/blob/c5ce69b1735334db5219104026c9fda798319aa6/plugins/task-pipeline/skills/task-pipeline/scripts/execution_authority.py
