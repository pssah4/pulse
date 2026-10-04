---
title: pulse map
description: A live view of ready work, active sessions, published results and final integration decisions.
---

# pulse map

The Map shows who works on what, what needs your attention and what starts next:

```bash
pulse map
```

It updates in a terminal until you press `q`. Without a terminal it prints one frame; `pulse status` does the same. In a terminal you can also click rows and scroll with the mouse wheel; see [Mouse](#mouse). The layout follows the terminal width, including narrow panes. A Map taller than its pane scrolls as a whole: `PgUp`, `PgDn`, `Home` and `End` move the window, a line above the keys names the lines shown (`lines 21 to 40 of 96`), and the window follows the selected row just far enough to keep it in sight. Every section heading can be selected; `Enter` or a click folds the section into one line with its count, such as `BACKLOG (12)`, and opens it again. The folds stay with the clone (`.git/pulse/map-folds`) and come back when the Map starts again. Long details scroll with `PgUp` and `PgDn`. The layout spans 44 to 160 columns. Below 60 columns the header omits its signet and keeps its words. A terminal that confirms the Kitty graphics protocol, such as Kitty, Ghostty or WezTerm, shows the signet as an image in the same 8 columns and 4 rows; the Map asks once and keeps the text signet in terminals that do not answer. Inside tmux, GNU screen or a Herdr pane the Map does not ask and keeps the text signet; nonterminal output uses `COLUMNS`, or 80 columns by default. A resize is applied on the next frame.

## Open it from the chat

Ask `/pulse` (in Codex `$pulse:pulse`) to show the Map. The skill runs `pulse map --ensure`: in Herdr or tmux it finds or opens the appropriate pane, while other environments receive instructions for a terminal or the VS Code task. Codex runs `pulse map --ensure` outside its sandbox when the terminal integration requires it. The chat never runs `pulse map` without `--ensure` in its own shell, pastes a stale frame into chat or types into another terminal. `PULSE_MAP=off` disables automatic opening.

### When it opens by itself

Herdr session hooks use `pulse map --ensure`, with one Map per tab and repository. Outside Herdr, claims and draft registration can offer the Map; setup adds the "Pulse map" VS Code task when it can safely update `.vscode/tasks.json`. See [Setup](./pulse-setup). In VS Code the line names the "Pulse map" task where the project has it, else that setup can add it. Pulse never changes your harness's hook trust.

In Herdr the Map's pane closes when the Map ends with exit code 0: `q`, `Ctrl-C`, or SIGTERM or SIGHUP. If the Map ends any other way, the pane stays open with its last output and the command that starts it again, and the next `pulse map --ensure` starts the Map in that pane. `pulse map --ensure` reports "opened beside" only once the Map runs; otherwise it says that the Map did not start and quotes the last lines of its pane. A clone or pulse path with a backslash or a control character gets no pane; the line says why. An error while the Map reads the board or draws a view does not end it: the status line names the error and the Map reads again. An error while it builds the item view still ends the Map, and the pane stays open with the message.

### Starting work

The Map starts no backlog runner. Start `pulse go` in your terminal, or explicitly ask the skill to execute it. Without a TTY Pulse owns a managed process and returns its run ID, report and log. `pulse go --stop` requests a controlled stop; closing the Map leaves the runner and pending action synchronization alive. See [Runner](./pulse-go#start-a-run).

## What you see

The header shows activity, items needing you, failures and the final approval policy. The board groups open work and shows epic progress. The backlog orders available items by dependencies, priority and any saved manual order. Epics with children remain navigable even when nobody holds them.

### Lights

| Light | Meaning |
|---|---|
| green | a supported local session or runner agent is working |
| yellow | a person must review a final result or resolve a concrete decision |
| red | a check, run or action failed |
| grey | waiting or idle work |

A claimed item without observed activity is not proof that an agent is working. An item a session holds by hand, without a run of `pulse go`, names its holder, the session, its phase and the age of its last sign of life, for example `held by ann, claude session b3dcb386: building, 5 min ago`. The session leaves that sign of life as one comment on the item's issue when it claims the item or changes phase, and its hook renews the comment at most every ten minutes while the session works, from any clone and without a commit. Only a comment by the claim's own account for the claim's session counts. After 30 minutes without one the row turns yellow: `no sign of life for 40 min; ask ann or take it over: pulse release --take 12`. The Map, `pulse status <n>` and an idle `pulse go` use the same words, and none of them changes the claim.

The working light breathes in truecolor and 256-color terminals; 16-color terminals show steady lights, and plain output has no color or motion. The worst state rolls up to the item and its person. Long titles shorten while the state remains readable; blocker lists end with the count of additional items.

### Counts

The header counts working, waiting and failing rows. **Board:** every open feature, improvement, and fix, and every draft, once. An epic with its spec attached counts in no group; it has its own progress row when it has children. Epic progress compares completed children with completed and open children; children closed as not planned count in neither. Epics with children remain selectable from the board, and returning from their detail view keeps the selection. Your configured slots apply to active agent work; teammates' claims take none of your local slots.

### Who is doing what

The section reads as a tree. Your row names you and sums up your items and sessions; while your `pulse go` runs it adds `pulse go: k of n slots`, the run's jobs and its slots, never items you hold by hand. Below it each of your items, without repeating you as its holder, and its ladder of stages. Its sessions start folded behind one row such as `▸ 2 sessions`: `Enter`, `→` or a click on that row unfolds them, and the Map keeps which items are unfolded in this clone, as it keeps folded sections. An unfolded session shows its harness and short ID, its place (the branch, else the folder), what it does now and for how long, such as `claude a1b2c3d4 · imp/580-tree   editing a.py 2 min`, and below it each subagent still running, with its type, what it was started for and how long it runs: `↳ Explore: find the callers   1 min`. A finished subagent disappears. Claude Code and Codex report subagents through their hooks; the description comes from the call of the agent tool that started it. A session that needs you stands in Needs you even while its item is folded. Sessions on a branch without an item fold the same way under their branch. `pulse status` prints no fold row: it names the count on the item's or branch's row, such as `2 sessions, building`. A session of `pulse go` stands under the item the run gave it, also its review and goal sessions in their detached folders; otherwise a claim identifies the item before the working directory does, and a runner job with a reporting session counts once. Each item names its branch on a grey line below it. A session without an item stands under its branch, or under `detached`.

Hook activity updates independently of board reads, within five seconds of a supported event. Permission requests of your sessions remain visible until the call returns or you write to the session; a session nobody attends also stops waiting when it starts another tool call without an answer. A permission request carries no call ID, so the result of another call of the same tool in the same turn ends it too. An agent of `pulse go` runs headless and nobody can answer it: its row shows `permission denied: <tool>`, and it never counts as needing you. Ended sessions stop appearing; presence snapshots without new events expire after 30 minutes without changing claims. No transcripts, prompts, shell commands, patches or tool output are saved for this display. Set `PULSE_PRESENCE=off` to disable local presence. Without trusted hooks the Map still shows runner phases.

Session and subagent lines can be selected like items. When the Map runs in Herdr, `Enter` or a click on such a line focuses the Herdr pane that runs the session now, also in another tab or workspace. The Map asks Herdr at that moment and matches only the session ID that Herdr reports for a pane, so it finds a moved pane and never takes a pane by its directory, name or title. The jump only moves the focus: the agent receives no input. A subagent without a pane of its own leads to its parent session, and the status line says so. Without a jump the status line names the reason: the Map does not run in Herdr, Herdr does not answer, Herdr reports no single pane with the session's ID, or the session has ended or another session replaced it.

The **Pulse runner** row is the runner's place. Before a claim exists it shows preparation: fetching the base, reading configuration, preparing a worktree or cleaning completed work, and below it what the runner does next (`then: start the build agent`). Once the run has read its configuration, the row also names its workers and why, for example `workers codex (started from Codex)`. This coordinator row takes no coding-agent slot. A managed runner remains visible while it waits for final approval. When `pulse go` has a saved goal, the row carries it: the goal in one line with its state, its scope with `k of n done`, what holds it, and `resume: pulse go --resume` while it is paused. A locally saved pause or direction change says `runner update pending` until the runner has applied it. The goal and the row remain after the process ends (`not running`). Use `pulse go --steer "<direction>"` to add an instruction. What the run does about a hook's refusal stands here too: a fix round, the item it waits for and how that one stands, or in grey an earlier refusal that the next run checks again. `r` reads the report of the last run.

Each of your own jobs shows a ladder of its stages below its row: `✓ spec  ✓ plan  ✓ build  ✓ tests  ▸ review/audit 4 min  · fix  · integrate`, done, active with its duration, or open. A published result waits at `integrate`. Below the ladder, `Plan 2/5: the parser` says how many tasks of the job's Plan are done and which comes next: agents of `pulse go` and `/pulse-build` close each task with a commit that carries the trailer `Pulse-Task: <n>`, the task's number in the Plan, and the Map counts them on the item's branch, here and as fetched from origin, each task once. A Plan without tasks or a branch without such a commit shows only the ladder. The count is display only; the gates never read it. A local action on the item, such as `handoff: conflict`, stands below the ladder until the shared state confirms it, and two minutes longer. Someone else's items show only the item and its branch, and what is yours on them: your sessions and your local actions; their item view still names the holder, the phase and the age. An item in the backlog that a spec writer or the runner moves next names that under its row, such as `/pulse-re on the spec of #6`. The row of an item shows its actual runner phase: `specifying`, `planning`, `building`, `checking documents`, `RED check running`, `tests running`, `review and audit running`, `review running`, `audit running` or `fix round`. A draft of yours identifies its writer, for example `spec in progress by seb`.

### Needs you

Needs you stands on top, and only when you must act: a result that waits for your final approval (`a approves`), a failed item to decide on, a plan to review or publish, an integration to resolve, a decision about a hook's refusal or the Plan commit gates, the base's remedy when the base holds the run, and a permission request or question of a session you attend (`enter jumps`). Each entry names the item or session, why, and the key; `Enter` or a click opens the item. `a approves` appears only where the step is the final approval itself; a result that needs revalidation opens its item instead. `pulse status` prints the command in place of the key, such as `pulse approve 7` or `pulse status 7`. Without such an entry the section does not appear. Published valid specs are planned and valid Plans are built without you; a current checked result integrates automatically, unless manual final integration approval is configured. A changed head or base needs revalidation; a red or held result cannot be approved. There are no early spec or Plan approvals and no PR status to manage.

A project hook that refused the runner holds only its item. The header warns about it only while it holds at the current base, for example `! #567 waits for #569: pre-commit (repo:hygiene) refused its plan`. Once the items it waits for are closed, it waits for the base to move; the item view's `effect` says what releases it.

### Backlog

The item the local `pulse go` prepares or runs a job on leaves the backlog at once and stands under Who is doing what with its stage, such as `preparing build`, even before the board shows its claim. `▲` marks only rows that start next and have not failed. Every available item appears once with its actual blocker: a missing or invalid spec or Plan, an open prerequisite, a file reserved by another active claim, a hold, a failed run, or the next free slot. Planning can run while a build prerequisite is open. Waiting for approval or a retry does not require an idle claim; the result, branch and work remain visible independently.

Pick unclaimed work and press `m` to preview a move. Arrows change the proposed order, `Enter` saves it and `Esc` cancels. Dependencies still come first; moving a row changes no priority labels or prerequisites. A stale or invalid preview must be refreshed.

### Done

Below the backlog, Done lists the items Pulse integrated into the base in the last 7 days, newest first, each with its title, who integrated it and when, such as `#580 upstream sync   Sebastian Hanke, 03.10. 23:20`. Who is the name git records for the merge commit, the person whose clone integrated the item. The Map reads this from the fetched base and takes missing titles from the closed issues it already reads for the epic bars. The section is open by default and folds like every other section; `Enter` on a row opens the item with its merge commit. `pulse status` shows the same section.

<a id="auto-mode"></a>

### Approval policy

`3` shows the current policy and previews a switch between manual and automatic final approval for the repository. `Enter` saves the setting locally; its synchronization status remains visible. Automatic completion is the default. Use `pulse auto merge off` to require manual final approval. A person with repository write access can also use `pulse auto merge on`, optionally `--for 8h`, and `pulse auto merge off`.

Automatic approval requires the same verified result, exact head and base, current authority and absence of holds or revocation. An unconfirmed enable action grants no authority; a local disable action blocks automatic integration immediately. Destructive removal retains its separate personal confirmations. Historical automatic plan/build/merge settings do not grant authority.

### Settings

`s`, or a click on the approval line in the header, opens the settings of the project. Each setting shows its value, where it comes from and what it does: `mode`, the repository, the base branch, the slots (`cap`), `workers`, `agent` with its split of the slots, `verify` and the spec test runners. `verify` and `[spec_tests]` come from `.pulse/config.toml` on the base branch of origin, as `pulse go` reads them; the others come from your working tree.

Rules shows, per harness, when a session in this clone last started with the Pulse rules and how large they were, against the 10,000 characters Claude Code takes from a hook. The session-start hook records this in `.git/pulse/rules-claude.json` and `.git/pulse/rules-codex.json` while `mode` is `on`. Without a record the line says "not proven" and names the way to one; for Codex that includes trusting its hooks: `/hooks` in the Codex CLI, the Hooks page of its settings in the IDE extension. "Rules now" measures what a session start would get today.

The entries change `mode`, the slots, `workers` and `agent`; the approval entry takes the way of `3`. `Enter` on an entry previews the change and its effect; the slots ask for a number first. `Enter` on the preview fetches the base and commits the change on a branch of its own, `chore/pulse-settings-<YYYYMMDD>` (`-2`, `-3` when the name is taken), made from `origin/<base>` in a throwaway worktree: `.pulse/config.toml`, for `mode` also the Pulse block of `AGENTS.md`, committed with your project's hooks and pushed. Your working tree and the base stay as they are. The status line names the branch; the change counts for the team once that branch is integrated into the base.

LEVERS lists the [lever grants](./pulse#let-an-attended-session-pull-your-levers) that hold, with scope, who granted and until when, and their latest uses. Its entries grant an attended Claude Code session `run` or `session`, every attended session `always`, or revoke every grant; `Enter` previews, a second `Enter` saves it in the local store at once. `l` on a session line opens this view.

Only a person changes settings. A value that does not hold, a configuration on the base that cannot be read, or a base that cannot be fetched gives the reason and writes nothing. The Map never changes what runs a program (`verify`, `setup`, `[agents]`, `[spec_tests]`); those change in a reviewed commit.

### Offline state and rate limits

Board refresh runs beside keyboard input, so navigation does not wait for GitHub. The Map checks for changes periodically and retains the last good snapshot during failures.

A GitHub rate-limit or connection warning keeps the last known board visible with its age. It says when a retry is possible; a successful fresh read clears the warning. A stale cached view cannot establish shared authority. Locally accepted actions keep their own synchronization state visible and may end in a conflict when the shared revision moved.

## Keys

| View | Key | Action |
|---|---|---|
| Map | `↑`, `↓`, `j`, `k` | select a row; the first `↓` selects the first item, `↑` reaches the section headings |
| Map | `PgUp`, `PgDn`, `Home`, `End` | scroll the Map |
| Map | `Enter`, `→` on a section heading | fold or open the section |
| Map | `Enter`, `→` | open the selected item |
| Map | `Enter` on a session line | focus its Herdr pane |
| Map | `l` on a session line | open the settings with your [lever grants](./pulse#let-an-attended-session-pull-your-levers) |
| Map | `g` | open an item by number |
| Map | `a` | preview final integration approval when available |
| Map | `m` | preview a move of unclaimed work |
| Map | `3` | show and configure the final approval policy |
| Map | `s`, a click on the approval line | open the [settings](#settings) |
| Map | `r` | read the report of the last run |
| Map | `?`, `q` | help, quit |
| Item | arrows, `Enter` | select and execute an offered action |
| Item | `o`, `a` | read spec, preview final approval |
| Item | `PgUp`, `PgDn` | scroll details |
| Settings | arrows, `Enter` | select an entry, preview its change |
| Settings | `PgUp`, `PgDn` | scroll the view |
| Reader | arrows, `PgUp`, `PgDn`, wheel | scroll the text |
| Reader | `Esc`, `q`, `←`, a click on `‹ back` | return to the view and entry it opened from |
| Confirmation | `Enter`, `Esc` | confirm after reading, cancel |
| Other views | `Esc`, `q`, `←`, `Backspace` | go back and discard an unconfirmed action |
| any | `Ctrl-C` | quit the Map |

The footer shows the main keys of the level below a line that separates them from the status; `?` opens all help. No key but `?` needs Shift. `g` opens a closed item by number without reopening it or adding it to the active-work counts. Navigation only reads.

A confirmation names the item, action and binding. It ignores `Enter` within the first second. If a resize hides any of that context, it cancels; a resize that still fits redraws it and restarts that interval. Navigation itself writes nothing.

## Mouse

A click on an item row opens that item, as selecting it and pressing `Enter` does. A click on a session line focuses its Herdr pane, as `Enter` does there. A click on a section heading folds or opens the section. A click on the approval line in the header opens the [settings](#settings), as `s` does. In the item view a click on an entry selects it and acts as `Enter`: a write still opens its confirmation first, and only `Enter` confirms. A click never confirms anything. A click on the spec, plan or checks line opens that text in the reader; a click on "run report" in Next opens the report of the last run. The wheel moves the selection on the Map, which scrolls along with it, and scrolls the item view, the help and the reader three lines per notch.

While the Map runs, the terminal sends it the clicks, so a plain drag no longer selects text. Hold `Shift` (`Option` or `Alt` in some terminals) to select text or to open a terminal link. The Map turns mouse reporting off whenever it ends: `q`, `Ctrl-C`, a closed terminal or a restart on a newer Pulse. On Windows the Map uses keys only. Every mouse action has a key.

## Actions

The item view shows its goal, stage, holder, blockers, published result, gates, findings and Plan. After a hook refusal it adds what the hook refused and when (`refused`), what that does now (`effect`) and the last lines of the output. Only actions appropriate to that observed state are offered.

| Action | Effect |
|---|---|
| read spec / read Plan | show the document in the reader, as the base or a branch of origin has it when the working tree differs |
| read parent spec / read ADR-nn | show the spec this item's spec names as parent, or a decision record its Plan names |
| read run log | show the gate and hook output of the item's last run |
| read result diff | show the complete published diff with its checks and findings |
| read check output | show the whole output of the check a project hook refused, in any phase |
| approve integration | approve exactly the reviewed result head and base |
| revoke approval | withdraw the observed approval |
| defer | pause locally immediately and synchronize a shared hold while preserving work |
| resume | request continuation of deferred or failed work; wait for shared confirmation before the next attempt |
| hand off claim | request the current writer to stop and preserve work before releasing its claim |
| discard | close as not planned without rolling back code |
| delete | enter the separate removal and irreversible issue-deletion workflow |

### The reader

Read actions show their text in a reader inside the Map, below its header, which keeps updating. A line names the source: the file, the path and the branch of origin it came from, or the run's file. Lines wrap at the terminal width. The reader reads at most 256 KiB, the start of a document or the end of a log, and a `cut:` line says so. It removes terminal control sequences and shows any other control character as `?`, so nothing in the text acts. It reads only files of the repository, of a branch of origin or of this clone's Pulse directory. When a file is missing, empty, unreadable or outside the repository, the status line names the reason instead. `r` on the Map shows the report of the last `pulse go` run: how it ended, a halt, the base and, per item, its result, time, phase, reason and log.

Approval, defer, resume, revoke and handoff are durable local actions. Confirming saves the request before network work begins. A background process synchronizes it, including after the Map closes. Its state stands at its item and in its item view: `queued`, `syncing`, `confirmed`, `conflict` or `error`; a change of the approval policy stands on the approval line of the header. `confirmed` means shared state accepted it; it leaves the Map two minutes later. The other states never grant integration authority. Defer and revoke block locally while pending. An `error` offers `retry sync` in the item view. A conflicting revision requires a fresh selection and preview, never silent rebinding to a new result: the item view offers `redo <action>`, which reads the board anew and opens the confirmation again.

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

Read actions show files in the reader and write no copies. With color, each `#n` is a terminal link to its issue that your terminal opens. Repository links and warnings are data; their text never becomes shell instructions.

## It starts nothing

Board reads, navigation and opening the Map do not start the backlog runner. Only your explicit `pulse go` request does. Confirming a queued action can start its small synchronization worker; that worker uses no LLM and cannot authorize itself to integrate a result.
