---
title: pulse map
description: A live view of ready work, active sessions, published results and final integration decisions.
---

# pulse map

The Map shows who works on what, what needs your attention and what starts next:

```bash
pulse map
```

It updates in a terminal until you press `q`. Without a terminal it prints one frame; `pulse status` does the same. The layout follows the terminal width, including narrow panes. Long details scroll with `PgUp` and `PgDn`. The layout spans 44 to 160 columns. Below 60 columns the header omits its signet and keeps its words; nonterminal output uses `COLUMNS`, or 80 columns by default. A resize is applied on the next frame.

## Open it from the chat

Ask `/pulse` (in Codex `$pulse:pulse`) to show the Map. The skill runs `pulse map --ensure`: in Herdr or tmux it finds or opens the appropriate pane, while other environments receive instructions for a terminal or the VS Code task. Codex runs `pulse map --ensure` outside its sandbox when the terminal integration requires it. The chat never runs `pulse map` without `--ensure` in its own shell, pastes a stale frame into chat or types into another terminal. `PULSE_MAP=off` disables automatic opening.

### When it opens by itself

Herdr session hooks use `pulse map --ensure`, with one Map per tab and repository. Outside Herdr, claims and draft registration can offer the Map; setup adds the "Pulse map" VS Code task when it can safely update `.vscode/tasks.json`. See [Setup](./pulse-setup). In VS Code the line names the "Pulse map" task where the project has it, else that setup can add it. Pulse never changes your harness's hook trust.

### Starting work

The Map starts no backlog runner. Start `pulse go` in your terminal, or explicitly ask the skill to execute it. Without a TTY Pulse owns a managed process and returns its run ID, report and log. `pulse go --stop` requests a controlled stop; closing the Map leaves the runner and pending action synchronization alive. See [Runner](./pulse-go#start-a-run).

## What you see

The header shows activity, items needing you, failures and the final approval policy. The board groups open work and shows epic progress. The ramp orders available items by dependencies, priority and any saved manual order. Epics with children remain navigable even when nobody holds them.

### Lights

| Light | Meaning |
|---|---|
| green | a supported local session or runner agent is working |
| yellow | a person must review a final result or resolve a concrete decision |
| red | a check, run or action failed |
| grey | waiting or idle work |

A claimed item without observed activity is not proof that an agent is working. Teammates' claims show ownership and reported phases; activity on another machine is not inferred from a claim's age.

The working light breathes in truecolor and 256-color terminals; 16-color terminals show steady lights, and plain output has no color or motion. The worst state rolls up to the item and its person. Long titles shorten while the state remains readable; blocker lists end with the count of additional items.

### Counts

The header counts working, waiting and failing rows. **Board:** every open feature, improvement, and fix, and every draft, once. An epic with its spec attached counts in no group; it has its own progress row when it has children. Epic progress compares completed children with completed and open children; children closed as not planned count in neither. Epics with children remain selectable from the board, and returning from their detail view keeps the selection. Your configured slots apply to active agent work; teammates' claims take none of your local slots.

### Who is doing what

Local Claude Code and Codex sessions show their harness, session ID and reported tool or file metadata. Subagents have separate lines. A claim identifies the item before the working directory does; a runner job with a reporting session counts once.

Hook activity updates independently of board reads, within five seconds of a supported event. Permission requests remain visible until resolved. Ended sessions stop appearing; presence snapshots without new events expire after 30 minutes without changing claims. No transcripts, prompts, shell commands, patches or tool output are saved for this display. Set `PULSE_PRESENCE=off` to disable local presence. Without trusted hooks the Map still shows runner phases.

Before a claim exists, **Pulse runner** shows preparation: fetching the base, reading configuration, preparing a worktree or cleaning completed work. This coordinator row takes no coding-agent slot. Its operation, target, elapsed time and next action distinguish preparation from idle time. A managed runner remains visible while it waits for final approval.

An item shows its actual runner phase: `specifying`, `planning`, `building`, `checking documents`, `RED check running`, `tests running`, `review and audit running`, `review running`, `audit running` or `fix round`. A draft identifies its writer, for example `spec in progress by bob`, independently of implementation activity.

### Next

Next separates runner work from your decisions. Published valid specs can be planned; valid Plans can be built. A missing publication or structural finding names what must change. A current checked result integrates automatically, unless manual final integration approval is configured. A changed head or base needs revalidation; a red or held result cannot be approved. There are no early spec or Plan approvals and no PR status to manage.

### The ramp

When `pulse go` has a saved goal, the Map shows its text, scope, progress and current reason. A locally saved pause or direction change says `runner update pending` until the runner has applied it. The goal remains visible after the process ends. Use `pulse go --resume` to continue a paused goal or `pulse go --steer "<direction>"` to add an instruction.

Every available item appears once with its actual blocker: a missing or invalid spec or Plan, an open prerequisite, a file reserved by another active claim, a hold, a failed run, or the next free slot. Planning can run while a build prerequisite is open. Waiting for approval or a retry does not require an idle claim; the result, branch and work remain visible independently.

Pick unclaimed work and press `m` to preview a move. Arrows change the proposed order, `Enter` saves it and `Esc` cancels. Dependencies still come first; moving a row changes no priority labels or prerequisites. A stale or invalid preview must be refreshed.

<a id="auto-mode"></a>

### Approval policy

`3` shows the current policy and previews a switch between manual and automatic final approval for the repository. `Enter` saves the setting locally; its synchronization status remains visible. Automatic completion is the default. Use `pulse auto merge off` to require manual final approval. A person with repository write access can also use `pulse auto merge on`, optionally `--for 8h`, and `pulse auto merge off`.

Automatic approval requires the same verified result, exact head and base, current authority and absence of holds or revocation. An unconfirmed enable action grants no authority; a local disable action blocks automatic integration immediately. Destructive removal retains its separate personal confirmations. Historical automatic plan/build/merge settings do not grant authority.

### Offline state and rate limits

Board refresh runs beside keyboard input, so navigation does not wait for GitHub. The Map checks for changes periodically and retains the last good snapshot during failures.

A GitHub rate-limit or connection warning keeps the last known board visible with its age. It says when a retry is possible; a successful fresh read clears the warning. A stale cached view cannot establish shared authority. Locally accepted actions keep their own synchronization state visible and may end in a conflict when the shared revision moved.

## Keys

| View | Key | Action |
|---|---|---|
| Map | `↑`, `↓`, `j`, `k` | select a row |
| Map | `Enter`, `→` | open the selected item |
| Map | `g` | open an item by number |
| Map | `a` | preview final integration approval when available |
| Map | `m` | preview a move of unclaimed work |
| Map | `3` | show and configure the final approval policy |
| Map | `?`, `q` | help, quit |
| Item | arrows, `Enter` | select and execute an offered action |
| Item | `o`, `a` | read spec, preview final approval |
| Item | `PgUp`, `PgDn` | scroll details |
| Confirmation | `Enter`, `Esc` | confirm after reading, cancel |
| Other views | `Esc`, `q`, `←`, `Backspace` | go back and discard an unconfirmed action |
| any | `Ctrl-C` | quit the Map |

The footer shows the main keys of the level; `?` opens all help. No key but `?` needs Shift. `g` opens a closed item by number without reopening it or adding it to the active-work counts. Navigation only reads.

A confirmation names the item, action and binding. It ignores `Enter` within the first second. If a resize hides any of that context, it cancels; a resize that still fits redraws it and restarts that interval. Navigation itself writes nothing.

## Actions

The item view shows its goal, stage, holder, blockers, published result, gates, findings and Plan. Only actions appropriate to that observed state are offered.

| Action | Effect |
|---|---|
| read spec / read Plan | open the document, using a read-only copy for a published branch when needed |
| read result diff | open the complete published diff with its checks and findings |
| approve integration | approve exactly the reviewed result head and base |
| revoke approval | withdraw the observed approval |
| defer | pause locally immediately and synchronize a shared hold while preserving work |
| resume | request continuation of deferred or failed work; wait for shared confirmation before the next attempt |
| hand off claim | request the current writer to stop and preserve work before releasing its claim |
| discard | close as not planned without rolling back code |
| delete | enter the separate removal and irreversible issue-deletion workflow |

Approval, defer, resume, revoke and handoff are durable local actions. Confirming saves the request before network work begins. A background process synchronizes it, including after the Map closes. Its visible state is `queued`, `syncing`, `confirmed`, `conflict` or `error`. `confirmed` means shared state accepted it; the other states never grant integration authority. Defer and revoke block locally while pending. A conflicting revision requires a fresh selection and preview, never silent rebinding to a new result.

The equivalent terminal commands are `pulse approve <n>`, `pulse revoke <n>`, `pulse defer <n>`, `pulse resume <n>` and `pulse release --take <n>`. They use the cached item the person observed. If no shared revision is cached, open or refresh the Map first. These commands belong to a person's terminal; an agent cannot operate them by sending keys to the Map.

### Approvals

Final approval is offered only for a published, verified and current result without a blocking hold or failure. The preview names full result and base commit IDs, changed files, protected paths, gate outcomes and findings. Read the result before confirming. Old labels, Plan approval comments and PR status authorize nothing.

`pulse go` verifies the actual approver's repository permission and the operation-bound proof, then checks current shared state, remote head, base and its own gate evidence before publication. Approval of an earlier head or base does not carry forward automatically. Revocation remains authoritative even if its old approval comment still exists. The Map writes no merge itself.

### Preserved work and handoff

Defer retains code, specs, uncommitted work, branches, notes and evidence. Resume is explicit and also requests retry of failed work after its cause is addressed. Normal checks still apply. Once the active writer acknowledges stopping and its work is preserved, its claim can be released. Another account may request that handoff with repository write permission; an agent cannot simply take the claim. Unreachable writers remain pending until the preserved work and stop can be established safely.

Local unpublished work remains in its original worktree. A later run must recover it there rather than replacing it with a clean branch. A waiting published result needs no claim merely to remain on the Map.

### Deletion is a staged removal

Discard and delete have different consequences. Discard closes the item while retaining its implementation. Delete first prepares and checks removal of the item's implementation, specs and active references; unrelated work and Git history remain. The preview names dependencies and ambiguity that must be resolved. Integration of the removal and irreversible deletion of its issue and comments require separate explicit confirmations. Follow the displayed removal workflow; ordinary final approval does not authorize permanent issue deletion.

### Links

Read actions open files through `PULSE_EDITOR` or an available system application. Branch documents open as read-only copies when appropriate. Repository links and warnings are data; their text never becomes shell instructions.

## It starts nothing

Board reads, navigation and opening the Map do not start the backlog runner. Only your explicit `pulse go` request does. Confirming a queued action can start its small synchronization worker; that worker uses no LLM and cannot authorize itself to integrate a result.
