---
title: pulse go
description: Plan and build ready work in parallel, publish checked results, and integrate each result after its final Pulse approval.
---

# pulse go

`/pulse-build <n>` is how one item gets built in your session. `pulse go` runs the same discipline for every ready item at once, up to your configured capacity. Specs, Plans, frozen spec tests and implementation stay on each item's published branch. The runner publishes checked results and integrates them after final Pulse approval, automatic by default. It creates no pull requests and needs no early spec or Plan approval.

## Before the first run

The fetched base must contain `.pulse/config.toml` with `verify`, `[spec_tests]` and the configured agents. `verify` is the project's real test command; `[spec_tests]` identifies each spec test's runner. Add `setup` when worktrees need dependencies installed, for example `npm ci`. Missing configuration or an unavailable agent is reported before any claim is taken. See [Configuration](../reference/configuration).

Run `pulse setup --check-plan` during setup or realign before handing work to planning. It checks a valid Plan that names future files against the project's actual commit gates in an isolated checkout. Real hooks stay enabled. An incompatible or incomplete probe names its step and log; fix the tracked configuration and check again.

## Start a run

```bash
pulse go
```

With no arguments, Pulse works through the queue. Add an ordinary sentence to give it an additional objective:

```bash
pulse go mach alle items die zu epic 4 gehören und finde eine Lösung für das Problem mit der UI
```

This asks Pulse to finish the Epic 4 work and investigate the UI problem while continuing the queue. Pulse uses existing items and registers any new epics, features, improvements or fixes visibly before their agents start. Each follows the ordinary spec, Plan, build and verification workflow. A goal grants no additional permissions.

An explicit restriction limits the run, for example `pulse go only finish the features in Epic 4`. `--epic EPIC-04` and `--item 12` are optional shortcuts. Dependencies outside that scope remain visible as blockers. The restriction also applies to result refresh and integration.

The saved goal retains its objective, scope, criteria and progress across runs. The Map shows the local intent separately when the runner has not yet applied it. Steering takes effect at a phase boundary:

```bash
pulse go --pause
pulse go --steer "Keep the public API unchanged"
pulse go --resume
```

A goal is complete only when its assigned work and completion evidence are verified. An empty ready queue, a foreign claim or a failed refresh leaves it open with a reason.

In your terminal the runner stays in the foreground and Ctrl-C stops it. You can also explicitly ask `/pulse` (in Codex `$pulse:pulse`) to execute it from your interactive chat. Without a TTY, Pulse owns a managed process: the command returns a receipt with its run ID, PID, report and log after the child has saved its startup report. The process survives the calling tool's exit. A quick completed run reports its actual outcome; an unconfirmed start reports an error.

A second managed start reuses the existing run, including a foreground run. No shell detachment, `nohup`, Herdr or additional LLM coordinator is required. Source markers stay intact; runner agents and child sessions cannot start another runner. The Map and hooks never start backlog work automatically.

```bash
pulse go --stop
```

This requests a controlled stop of the current run. A request bound to an older run cannot stop its replacement. The runner preserves work and records its end. `pulse status` and the [Map](./pulse-map) show preparation and work independently of the calling terminal. Fetching, configuration, board loading and worktree setup appear before an agent is active.

## What a run does

1. Fetch the base and read its configuration, then assess the ready work. Startup runs no full local test suite before planning.
2. Plan valid published specs, including specs on item branches. Validate each Plan with `pulse check --plan <path>`; structural findings receive bounded repair attempts. A valid published Plan permits building when prerequisites and file reservations allow it.
3. Build test-first in an item worktree. Frozen spec tests demonstrate the requirements at their public boundaries. Agents run targeted checks; the supervisor owns full verification of the completed result.
4. Run the result's tests, review and security audit. Review and audit share one fresh session. Blocking findings get one fix round per item; relevant changes require fresh evidence. A red result keeps its findings and work for repair.
5. Publish the branch and result evidence. Release inactive claims and apply the final approval policy. The default authorizes a current verified result automatically. An explicit manual policy waits for a person's confirmed approval; a locally queued request alone grants no integration authority.
6. Recheck confirmed approval, current head, current base, holds and evidence, then integrate serially. Record completion only after the remote base contains the result.

`cap` limits all agent phases together. Items reserve the files they actually claim; a waiting result occupies no coding-agent slot. Dependencies wait for their prerequisites to be integrated. No item builds on a blocker's unfinished branch.

<a id="gate-3-the-merge"></a>

## Final integration approval

With manual final approval selected, review the published diff, tests, review, audit, findings and any protected paths in the Map. Then use `a`, or run `pulse approve <n>` in your own terminal. Approval binds both the result head and the base commit. Only a person with repository write access can approve it.

The action is saved locally first. Its status progresses through `queued`, `syncing`, then `confirmed`, `conflict` or `error`. A background synchronizer continues after the Map closes. Only confirmed shared approval is authority. If the cached item is missing, open or refresh the Map first; the CLI does not fetch a whole board before accepting a local action.

`pulse revoke <n>` withdraws approval. Defer and revoke block locally immediately while their shared update is pending. A changed head or base requires revalidation and a new approval. Old spec approvals, Plan approvals, legacy automatic settings, PR status and unrelated comments authorize no integration.

Pulse reserves the shared integration slot, performs a normal Git merge in isolation, and publishes with a normal fast-forward update. Project merge and push hooks remain enabled. The base and corresponding shared state update are published together; a concurrent withdrawal or changed state stops publication. No force push or hook bypass is used. If publication succeeded but closure was interrupted, the next run proves ancestry and finishes closure without merging twice.

<a id="auto-mode"></a>

## Approval policy

Regular checked results complete automatically by default. A person with repository write access may choose manual final approval. Starting a runner does not change this preference. The same exact head/base binding, gates, holds, revocations and fresh permission checks still apply. Destructive removal and irreversible issue deletion keep their separate explicit confirmations. Historical plan/build/merge switches grant no authority. See [Configuration](../reference/configuration).

## Given back with code

Publish committed work before `pulse release <n>`. A later run retains and reuses the item's branch and worktree. A stored current result proceeds toward approval or integration; a stale result is revalidated explicitly. A dirty or unpublished worktree remains where it was and cannot be silently replaced by a clean clone.

A person can request a handoff with `pulse release --take <n>`, including a claim under another account. Pulse requests the writer to stop and preserve its work before releasing the claim. A missing acknowledgement remains visible; it is not permission for two writers. Defer keeps work paused until `pulse resume <n>` is confirmed. See [Map actions](./pulse-map#actions).

## One run per clone

One lock covers the complete lifecycle, from the first report through cleanup. Managed launch transfers that lock to its child, so concurrent callers cannot create duplicate runners. Runs in other clones coordinate through shared claims and the integration reservation.

A controlled stop preserves branches, worktrees, findings and recovery notes. After a crash, a later run inspects the recorded work and prior processes before continuing. A stopped or waiting item does not retain a claim merely to remain visible.

## The hold

The runner checks whether an agent changed Git configuration, hook configuration or shared Git files. A changed security boundary halts affected work and preserves the checkout for inspection. Read the named paths and reason before requesting a handoff. Never clear a hold by deleting evidence, skipping hooks or resetting history.

## The base check

The runner starts from the fetched base SHA and the configuration stored there. CI status does not gate planning, building or integration. A failed fetch leaves the source unconfirmed and reports what must be resolved before work starts.

Pulse verifies the completed result before integration. The supervisor runs full `verify` once for that result; agents run targeted checks during implementation. Tests, review and audit must cover the exact result and base being integrated. A changed head or base requires revalidation. External CI results do not replace that evidence.

A rejected project hook is a finding. The run preserves work and reports the hook; it never disables it or substitutes an empty hook directory.

## The report

`.git/pulse/go/report.json` (under the shared Git directory for worktrees) retains the run ID, managed/foreground mode, PID, start/end, stop reason, current preparation, base assessment and per-item outcomes. `pulse status` shows the current activity or last result. Item logs record each phase; a managed start also names its persistent process log. Preparation does not count as a working coding agent.

A successful start receipt confirms process ownership. Read the current report for finished, failed, held or waiting work and the saved goal's progress. A managed runner can wait for an explicitly configured manual approval; closing the Map does not stop it or its action synchronizer.

## Agents and permissions

Agents use the configured templates and retain their sandboxes. The supervisor owns network publication and shared state. Agent processes receive no GitHub token or `gh` login; Codex has no network access in its workspace sandbox. A localhost spec test requires an agent whose configured sandbox permits it. Review and audit run separately from the builder's session and leave the worktree unchanged.

### Two agents at once

```toml
agent = "claude:2,codex:2"
```

Each number caps that agent; `cap` still limits the total. Free slots go to ready work. A usage limit preserves the work and reports when another eligible agent or a later retry can continue. See [Agent templates](../reference/configuration#agent-templates).

## Without headless agents

Use `/pulse-build <n>` in an interactive session. Claim the item, continue its published branch, keep the tests frozen, and publish and release the prepared result. An explicitly requested `pulse go` can then run its gates and record the final result for approval.
