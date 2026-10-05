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

An explicit restriction limits the run, for example `pulse go only finish the features in Epic 4`. `--epic EPIC-04` and `--item 12` restrict the run the same way; next to a text they add to it and never replace it. Item numbers in the text restrict the run until the interpretation is confirmed; it then decides whether only those items run, as in `pulse go -- '#569 and #580, leave the rest'`, or the queue goes on beside them, as in `pulse go -- 'Fix the header, #1 priority'`. Given next to a text, `--item` or `--epic` wins: it sets the scope, item numbers in the text do not widen it, and an interpretation that needs other items pauses the goal with that reason. Dependencies outside that scope remain visible as blockers. The restriction also applies to result refresh and integration.

If the interpretation fails, Pulse pauses the goal and names the reason in the output of `pulse go` and in the Map. Nothing outside a confirmed scope starts; `pulse go --resume` interprets the goal again.

The saved goal retains its objective, scope, criteria and progress across runs. Every agent that specifies, plans, builds or fixes an item reads the goal and its criteria. The Map shows the local intent separately when the runner has not yet applied it. Steering, pausing or changing the goal stops only the jobs whose item leaves its scope; the others go on, and a pause starts nothing new until you resume:

```bash
pulse go --pause
pulse go --steer "Keep the public API unchanged"
pulse go --resume
```

A goal is complete only when its assigned work and completion evidence are verified. An empty ready queue, a foreign claim or a failed refresh leaves it open with a reason that names the items holding it, such as `#580 failed: ...` or `#2 waits for #1`. The Map shows its progress (`k of n items complete`) from the interpretation on, also while jobs run.

In your terminal the runner stays in the foreground and Ctrl-C stops it. From your interactive chat, `/pulse-go` and your goal (in Codex `$pulse:pulse-go`) start it with your whole text as the goal, and `/pulse-go pause`, `resume`, `stop` or `steer <direction>` control it; an explicit request to `/pulse` (in Codex `$pulse:pulse`) works as well. Without a TTY, Pulse owns a managed process: the command returns a receipt with its run ID, PID, report and log after the child has saved its startup report. The process survives the calling tool's exit. A quick completed run reports its actual outcome; an unconfirmed start reports an error.

A second managed start reuses the existing run, including a foreground run. No shell detachment, `nohup`, Herdr or additional LLM coordinator is required. Source markers stay intact. An attended Claude Code or Codex session may start it when you ask for it in the chat; runner agents (`PULSE_HOLDER`) and unattended sessions such as `claude -p` (`CLAUDE_CODE_SESSION_ATTENDED=0`) cannot start another runner and are told to use your own terminal. Claude Code sets `CLAUDE_CODE_CHILD_SESSION=1` in every process of a session, so that variable alone decides nothing. The Map and hooks never start backlog work automatically.

```bash
pulse go --stop
```

This requests a controlled stop of the current run. A request bound to an older run cannot stop its replacement. The runner preserves work and records its end. `pulse status` and the [Map](./pulse-map) show preparation and work independently of the calling terminal. Fetching, configuration, board loading and worktree setup appear before an agent is active.

## What a run does

1. Fetch the base and read its configuration, then assess the ready work. Startup runs no full local test suite before planning.
2. Plan valid published specs, including specs on item branches. Validate each Plan with `pulse check --plan <path>`; structural findings receive bounded repair attempts. A valid published Plan permits building when prerequisites and file reservations allow it.
3. Build test-first in an item worktree. Frozen spec tests demonstrate the requirements at their public boundaries. Agents run targeted checks; the supervisor owns full verification of the completed result.
   With Claude Code workers, steps 2 and 3 are one session: `pulse go` hands the item to it as a goal (`/goal`), a condition the item branch alone proves: the Plan committed and clean under `pulse check --plan`, the spec tests first in their own commit, every requirement built, `verify` green, the spec updated as reference, each Plan task closed by a commit with `Pulse-Task: <task number>`, everything committed. The session plans, builds and checks itself with all its harness allows, subagents included, and ends after at most 20 turns or the `agent_timeout`. An item that still waits for other work gets a planning session only. `pulse go` then pushes through your hooks and runs its own gates; it never takes the goal's own verdict as done. Codex offers `/goal` only in its terminal UI, so Codex workers, and every worker with `item_flow = "phases"`, plan and build in separate sessions as before. Where Claude Code refuses `/goal` (hooks restricted by your organization, a workspace it does not trust, a version without it), the item falls back to phases and its notes say so. A session that changed its frozen spec tests gets a spec-tests fix round before any other gate, as a phased build does.
4. Run the result's tests, review and security audit. Review and audit share one fresh session. Blocking findings get one fix round per item, as a new goal for a Claude Code worker; relevant changes require fresh evidence. A red result keeps its findings and work for repair.
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

A person can request a handoff with `pulse release --take <n>`, including a claim under another account. Pulse requests the writer to stop and preserve its work before releasing the claim. A missing acknowledgement remains visible; it is not permission for two writers. A job whose publication a handoff fences acknowledges its stop before it ends. If a job of an earlier run ended without acknowledging, the next run in the same clone acknowledges its stop at the start, with the job's worktree there, and resume continues the preserved work in that clone. While a process group a run recorded for the job still runs, the stop stays open and the run report says why; an item the run before held stays open for one run. A writer of another clone or account or an attended session keeps its stop open until it acknowledges. Defer keeps work paused until `pulse resume <n>` is confirmed. See [Map actions](./pulse-map#actions).

## One run per clone

One lock covers the complete lifecycle, from the first report through cleanup. Managed launch transfers that lock to its child, so concurrent callers cannot create duplicate runners. Runs in other clones coordinate through shared claims and the integration reservation.

A controlled stop preserves branches, worktrees, findings and recovery notes. After a crash, a later run inspects the recorded work and prior processes before continuing. A stopped or waiting item does not retain a claim merely to remain visible.

## The hold

The runner checks whether an agent changed Git configuration, hook configuration or shared Git files. A changed security boundary halts affected work and preserves the checkout for inspection. Read the named paths and reason before requesting a handoff. Never clear a hold by deleting evidence, skipping hooks or resetting history.

## The base check

The runner starts from the fetched base SHA and the configuration stored there. CI status does not gate planning, building or integration. A failed fetch leaves the source unconfirmed and reports what must be resolved before work starts.

Pulse verifies the completed result before integration. The supervisor runs full `verify` once for that result; agents run targeted checks during implementation. Tests, review and audit must cover the exact result and base being integrated. A changed head or base requires revalidation. External CI results do not replace that evidence.

### A hook that refuses

A project hook that refuses a commit, push or base merge of the runner holds only that item; other items keep starting. Pulse records the item, phase, step, hook, the check npm or pnpm names in its last `> package@version script` header, the time and the base commit, with the last lines of the output. The whole output stays in `.git/pulse/go/<n>.hook.txt` of this clone.

The item then gets one fix round of its own for the refusal, whatever rounds its gates spent: a push the hook refuses after the review's fix round still gets one. The round receives the output and the open fix items on the board. When the cause lies in the item's own change, the round fixes it and the build continues. When it lies in a check the whole project shares, the round changes nothing outside the item and names the prerequisite under `needs:` in `_devprocess/plans/<n>-needs.md`: `'#m title'` for an open fix item, otherwise a short title, which becomes one draft. The item then waits for it with its work preserved and its claim released. Without a named prerequisite the item fails and names the decision: change the item so the check passes, or name what it waits for.

The record survives restarts. A restart alone starts nothing again: a waiting item stays held until every item it names is closed and the base has moved. Then the runner takes the current base into the preserved worktree, runs the hooks again and publishes the preserved plan without a new planner, once per base. `pulse publish-plan` takes the current base in before its commit as well.

When the commit gates refuse the compatibility probe's valid plan, ordinary planning waits. The hold names the hook, the check and the probe's output, and the decision which item repairs the gates. Items labelled `pulse:base` plan and build anyway; `pulse new <type> <title> --base` sets that label. Pulse never links an item to a refusal on its own and never disables a hook or substitutes an empty hook directory.

## The report

`.git/pulse/go/report.json` (under the shared Git directory for worktrees) retains the run ID, managed/foreground mode, PID, start/end, stop reason, current preparation, base assessment and per-item outcomes. `halt` and `halt_kind` (`base`, `compatibility`, `tainted`, `startup`) name what holds the whole run; `refused` keeps one record per item a hook refused, with its state: `fixing`, `waits` with the items it needs, or `decision`. `pulse status` shows the current activity or last result. Item logs record each phase; a managed start also names its persistent process log. Preparation does not count as a working coding agent.

A successful start receipt confirms process ownership. Read the current report for finished, failed, held or waiting work and the saved goal's progress. The end of `pulse go` and `pulse status` name each item a hook refusal holds, with the cause and its effect. A managed runner can wait for an explicitly configured manual approval; closing the Map does not stop it or its action synchronizer.

## Agents and permissions

Agents use the configured templates and retain their sandboxes. A Claude worker gets the rights you give your own sessions in the project: your permission mode (`auto` when your Claude Code settings set `permissions.defaultMode = "auto"`), your rules, subagents, and read tools, plus what the run needs (`verify`, the spec test runners, git in its worktree, `pulse check`). The Pulse guard runs in every worker as a hook, so no worker merges or pushes to the base, approves, or takes over; `worker_permissions = "narrow"` keeps Pulse's own list, see [Agent templates](../reference/configuration#agent-templates). A call your mode does not allow without asking is refused, since nobody answers a worker, and the run report names it. Codex workers keep their workspace sandbox, with network and the review of approvals only as the top level of your own `config.toml` in `$CODEX_HOME` (by default `~/.codex`) sets them; that review can approve an escalation that then runs outside the sandbox, as in your own Codex session, and `pulse go` never sets it itself. The plan, build and fix sessions of an item also read the last comments on its own issue by people who may push, a hint of yours among them, read when the job starts, as data after their instructions; the spec, the Plan and Pulse's instructions take precedence over them. A `/goal` session reads them from a file the context after its condition names, never inside the condition. Spec, review, audit and goal-interpretation sessions and `pulse status` show none. No worker gets a GitHub login: `pulse go` writes the board. The supervisor owns network publication and shared state. Agent processes receive no GitHub token or `gh` login; Codex has network only where your Codex settings give it. A localhost spec test requires an agent whose configured sandbox permits it. Review and audit run separately from the builder's session and leave the worktree unchanged.

### Which workers a run starts

With `workers = "session"`, the default, the session that starts `pulse go` picks its workers. Started from Claude Code, the run starts `claude` workers with all slots; started from Codex, `codex` workers; started in a terminal, the workers of `agent`. Pulse tells the harnesses apart by `CODEX_THREAD_ID` and `CLAUDE_CODE_SESSION_ID`, Codex first, so a Codex session started from a Claude Code shell counts as Codex. An empty template for that harness in `[agents]` falls back to `agent`. With `workers = "fixed"` every start runs `agent`.

The start line names the workers and the reason, for example `workers claude (started from Claude Code)`; a managed start prints the same line after its receipt. `report.json` keeps them under `workers`, and the Pulse runner row of the [Map](./pulse-map) shows them. The [settings view](./pulse-map#settings) of the Map shows which of the two holds and changes it.

Upgrading: an `agent` that named one harness for every start, such as `agent = "codex"`, now applies to terminal starts only. Set `workers = "fixed"` to keep it for starts from a session too.

### Two agents at once

```toml
agent = "claude:2,codex:2"
```

Each number caps that agent; `cap` still limits the total. Free slots go to ready work. A usage limit preserves the work and reports when another eligible agent or a later retry can continue. See [Agent templates](../reference/configuration#agent-templates).

## Without headless agents

Use `/pulse-build <n>` in an interactive session. Claim the item, continue its published branch, keep the tests frozen, and publish and release the prepared result. An explicitly requested `pulse go` can then run its gates and record the final result for approval.
