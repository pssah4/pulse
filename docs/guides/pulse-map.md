---
title: pulse map
description: The live map in a terminal. Who works on what, a light per item, the board, what needs you next, and the ramp of ready work.
---

# pulse map

One view of the whole team: who works on what right now, what waits for you, and what goes out next. It runs in a terminal:

```bash
pulse map
```

It reads the board every two seconds and redraws its lights twice a second, until you press `q` on the map. In a pipe, a file, or an agent's shell, where there is no terminal, `pulse map` prints one frame without color and ends. `pulse status` prints the same frame once.

The map is as wide as its terminal, from 44 to 160 columns, so it fits a pane beside a chat, and every frame asks the terminal again: resize it, and the next frame fits the new width. Below 60 columns the header leaves out the signet and keeps its words. Without a terminal (`pulse status` or `pulse map` in a pipe, a file, or an agent's shell) the map takes the width in `COLUMNS`, else 80 columns.

The signet is four rows high and at most eight columns wide. The four lines beside it show repository/person/time, activity, warnings, and auto mode, with no blank line above them. Changed rows are cleared before their text is written, so clearing a full-width row does not erase the last letter of `done` or `active`.

## Open it from the chat

A chat cannot show a live view, so an agent you ask for the map brings you to a terminal, as `/pulse` (in Codex `$pulse:pulse`) says. It runs `pulse map --ensure`, the same call that opens the map when work starts ([below](#when-it-opens-by-itself)): it opens the map where you work unless a map runs there already, and passes on the one line that says what it did. In Herdr that is a pane to the right of the chat's pane, and inside tmux a pane beside the chat; `q` closes it. In any other terminal no window opens, and the line says to run `pulse map` in a second terminal and names the command. In VS Code, with Claude Code or Codex, nothing opens: the line names the task "Pulse map" (Terminal > Run Task) where the project has it, else that `pulse setup` adds it ([pulse setup](./pulse-setup)), and the command for the terminal panel. Codex runs the call outside its sandbox, which cannot open a terminal: with the Codex rules of `pulse setup --codex-rules`, or after you approve it. With the map switched off (`PULSE_MAP=off`), the agent asks you to run `pulse map` in a terminal of your own.

The chat never runs the map itself in its own shell and never pastes a frame instead: a frame is stale the moment it prints. There is no browser page and no sidebar; the map is the terminal. If the terminal says `pulse: command not found`, run the `setup --cli` line for your agent from [Installation](../tutorials/installation) once per machine: it calls the installed plugin by its path.

### When it opens by itself

In Herdr, every chat that starts, resumes, or forks opens the map beside itself: the Pulse hook runs `pulse map --ensure` apart and does not wait for it. Herdr gets one map per tab and repository, in a new pane to the right of the chat's pane, labelled `pulse map <owner/name>`, and the focus stays in the chat; a second chat in the same tab finds that map and opens none, and two chats that start at the same moment open one. `q` ends the map and takes its label off, so the next chat that starts opens it again; `/clear` and `/compact` do not, and neither do the agents of `pulse go`, subagents, or `claude -p`. After Herdr restarts, the old pane of the map comes back as an empty shell, and the next start runs the map there again. A key in Herdr opens it too: `pulse setup` names the lines for Herdr's `config.toml`, with the full path of `pulse`, since a key command runs with the PATH of the Herdr server:

```toml
[[keys.command]]
key = "prefix+m"
type = "shell"
command = "/Users/you/.local/bin/pulse map --ensure"
```

Outside Herdr, `pulse go` as it starts, `pulse claim`, and `pulse new --draft` open the map when no map of this clone runs or is starting; `pulse map --ensure` does the same on request. Each says in one line what it did. Where the map opens:

| Where you work | What opens |
|---|---|
| a pane of Herdr | a pane to the right, one per tab and repository, the focus stays in the chat |
| a terminal inside tmux | a pane beside, the focus stays where it was |
| VS Code, with Claude Code or Codex | nothing; the task "Pulse map" starts the map in a terminal panel of its own when the folder opens, and the line names the command and, where the project has it, the task. `pulse setup` adds the task ([pulse setup](./pulse-setup)); VS Code asks you once to allow automatic tasks |
| anywhere else: Terminal, iTerm, a Linux or Windows terminal | nothing; the line says to run `pulse map` in a second terminal and names the command. There the map shows the same and takes the same keys |

The agents that `pulse go` starts never open a map. To turn it off, set `PULSE_MAP=off` in the environment.

### Starting work

The map starts no `pulse go`, neither by itself nor on a key. You start `pulse go` in a terminal of your own, where it runs in the foreground and its output stays in sight ([pulse go](./pulse-go#start-a-run)). While approved work waits, [Next](#next) says `pulse go builds it` or `pulse go writes its plan`.

Deleting an item has a separate, explicitly confirmed check step. That step
uses the same runner to execute the removal's configured tests and a fresh
review/audit session. It does not start the regular backlog run.

## What you see

```text
▀▀▀▀▀▜▄   pulse  acme/shop  Sebastian                                      09:28
▟▀▀▀▀ ▐▌  ● 4 working   ● 3 need you   ● 1 failing
▐▛▟▀▀▀▘
▐▌▘       auto you  1 plan off  2 build on  3 merge off

auto @alice  3 merge on until 18:00 (their items)

BOARD ──────────────────────────────────────────────────────────────────────────
 ready to start ██████░░░░░░░░░░░░░░░░░░   3
 in progress    ███████████░░░░░░░░░░░░░   6
 in review      ██████░░░░░░░░░░░░░░░░░░   3
 blocked        ░░░░░░░░░░░░░░░░░░░░░░░░   0
 not ready yet  ██░░░░░░░░░░░░░░░░░░░░░░   1

 #10 sign-in that lasts                                  █░░░░░░░░░ 1 of 14 done

WHO IS DOING WHAT ──────────────────────────────────────────────────────────────
● Sebastian                                   4 of 4 slots busy, 4 agents active
├ ● #19 fix: token expiry                                               building
├ ● #17 docs: auth flow                                                fix round
├ ● #20 api: pagination cursor                                          building
├ ● #21 ui: empty states                                                building
└ ● #14 fix: typo in login                              PR #114, waits for merge
● Alice                                                                  2 items
├ ● #12 api: rate limiting                            PR #112, needs your review
└ ● #23 api: error envelope                                            no PR yet
● Bob                                                                    2 items
├ ● #16 perf: query cache                                PR #116, checks failing
└ ● #24 ui: keyboard shortcuts                                         no PR yet

NEXT ───────────────────────────────────────────────────────────────────────────
 your review                                            review PR #112 on GitHub
 waits for merge                                         merge PR #114 on GitHub
 not approved                      pulse approve 15, or approve spec in its view
 queued                                                    waits for a free slot

RAMP all open work, in the order it goes out ───────────────────────────────────
  #13 ui: token banner                                                    queued
  #15 ui: dark mode                                                 not approved
  #18 ui: settings panel                                                  queued
  #22 db: session index                                                   queued
```

Each line holds a title on the left and its state on the right. The state takes the room it needs; when a long title needs the room too, the state gets about 45 percent of the line and the title the rest, cut short with `…`. A list of blockers fills the state's room and ends with how many more (`+3`). The key line and any message at the bottom wrap to the next line instead of being cut.

### Auto mode

The fourth line of the header shows your own auto mode per gate, as `pulse auto` switched it: `auto you  1 plan off  2 build on  3 merge off`, with `on until 18:00` for a switch that runs out and `off (expired 02:10)` for one that ran out. Below the header stands everyone else whose switch is on, one line per login: `auto @alice  3 merge on until 18:00 (their items)`. Their switches act only in their own `pulse go` and only on their own items, never on yours. When two open issues have the label `pulse:auto`, no switch counts for anyone, and the line says so in red: `auto off: two auto issues #12 #40, close one`. `1`, `2`, and `3` switch your own (see [Keys](#keys)).

### GitHub rate limits

`GitHub rate limit (graphql); retry after ... UTC; showing last known state, cache age ...` means GitHub's API allowance is exhausted, not that your coding agent has run out of tokens. The map shows the last cached board with its age; without a usable cache it says `no cached state`. In a narrow pane the full warning wraps in the footer when no action message is displayed.

Pulse waits until the reported retry time, or uses bounded backoff when GitHub supplies no reliable deadline. The warning remains after that time if the refresh fails and clears only after a successful fresh board read. A stale display is not permission to approve or mutate unverified work. Ordinary connection failures still say `offline`.

### Lights

| Light | Means |
|---|---|
| green | an agent works: a phase of `pulse go` on the item |
| yellow | something waits for you: a pull request asks for your review, your pull request waits for your merge, an item waits for approval, or a plan waits for you |
| red | something failed: a pull request's checks, a draft pull request with a red gate, or an item the last `pulse go` run failed |
| grey | idle: an item you hold without a running phase, a teammate's item without news, a ramp row that only waits |

The worst light rolls up to its feature and to the person, so the top row of each person is enough at a glance.

A working light breathes: its brightness rises and falls in a cycle of about three seconds, while the character and its size stay the same. Nothing blinks. How it looks depends on the terminal:

- **Truecolor** (`COLORTERM` is `truecolor` or `24bit`) and **256 colors** (`TERM` contains `256color`): the green light breathes.
- **16 colors:** every light is steady.
- **No terminal** (a pipe, a file): no color and no motion.

### Counts

- **Header:** how many lights on the map are green (`working`), yellow (`need you`), and red (`failing`).
- **Board:** every open feature, improvement, and fix, and every draft, once: ready to start, in progress (held, no pull request yet, a draft whose spec someone writes included), in review (held, with a pull request), blocked by an open item, and not ready yet (a draft nobody holds, not approved, a spec or plan that is not ready, a file in use). An epic with its spec attached counts in no group; with children it gets a line of its own below.
- **Epics:** one line per open epic with children, how far it is: its children closed as completed or merged, of those and its open children (`1 of 14 done`). A child closed as not planned counts in neither. The map reads the closed children at most every 30 seconds, and only while an epic is open.
- **Your row:** your slots (items you hold without a pull request, out of `cap` in `.pulse/config.toml`) and the agents `pulse go` runs for you. A teammate's work takes none of your slots.

Exactly one blank line separates the activity bars from the epic progress rows. Epic bars and their count columns align across the board, even when counts have different lengths. Long epic titles end in `…`; their numbers remain visible. Move the picker up into the board and press `Enter` or `→` to read an epic's full title and goal or open its spec. Returning keeps that epic selected. Epics without children have no progress row, and approving an epic does not approve its features.

### Who is doing what

You come first, with the features you hold and the drafts whose spec you write. Each feature line says where it stands: while `pulse go` runs it, the step of its chain (`planning`, `building`, `RED check running`, `tests running`, `review and audit running` (one session), `review running`, `audit running`, `fix round`); once its pull request exists, `draft PR #n, a gate is red`, `PR #n, waits for merge`, `PR #n from a fork, merged on GitHub`, or what the merge would still need (`PR #n has no passing review and audit of its last commit`); `PR #n targets <branch>` when it goes into another branch than the base, as an older Pulse stacked it. A merged feature leaves the map at once, also when it merged into a branch other than the default one: GitHub closes nothing there, and the next `pulse go` closes the item before it starts anything; until then, an item it blocks still waits for it. A pull request that changes only files under `_devprocess/`, such as the spec, counts for no feature by its branch name, open or merged: the feature shows no "waits for merge" for it, and it stays on the map after that merge. A pull request from a fork counts for a feature only through its `Closes #<n>`, since the fork's owner picks its branch name, and GitHub links `Closes #<n>` only in a pull request into the default branch: merged into another base branch, it closes nothing, and you close the feature on GitHub.

Teammates follow, each with the items they hold and where each pull request stands. Until the pull request exists, the line tells how their work goes: from the sign of life `pulse go` writes into its claim, or, for a session's claim, which nothing renews, how long it is held:

| Line | Means |
|---|---|
| `building, 4 min ago` | their `pulse go` run: the phase of its last sign of life, and its age (`<phase>, <age> ago`) |
| `no sign of life for 45 min` | their `pulse go` run has not reported for 30 minutes or more: ask them |
| `no PR yet, held 3 h` | a session of theirs holds it: only the age of the claim, which says nothing about whether it still works; ask them |
| `spec in progress by bob, 20 min` | a draft: their `/pulse-ba` or `/pulse-re` session writes its spec, last seen 20 minutes ago (else the age of the claim); a held draft stands here only, not on the ramp |
| `plan waits for bob` | the plan of an item bob holds waits for a person: `pulse approve <n>`, or approve plan in its view; `pulse status <n>` says the same |

Their lights come from GitHub: yellow when a pull request asks for your review, red when its checks fail or it is a draft that names a red gate, grey otherwise. Whether an agent runs on their machine stays there, so their items never turn green.

### Next

One line per kind of thing that waits, the most urgent first, each with the step that moves its first item. An item that waits for an open blocker is left out, and so is its light in the header: its blocker moves first.

| Line | Step it names |
|---|---|
| `failing` | `/pulse-build <n>` takes it on in a session; for a draft pull request with a red gate, `/pulse-build <n>` fixes it in a session, or fix it, then `pulse release <n>`: the next `pulse go` runs its gates |
| `your review` | review the pull request on GitHub |
| `waits for merge` | approve gate 3 for `pulse go`, or merge the pull request on GitHub; one into another branch than the base says `retarget PR #n to <base> on GitHub` |
| `plan waits for you` | `pulse approve <n>`, or approve plan in its view; the item's line says `plan changed since plan ok` or `spec changed since plan ok` when the plan or its spec changed after an approval, which then counts no more |
| `not approved` | `pulse approve <n>`, or approve spec in its view: it writes the approval, and `pulse go` merges the docs PR of a spec not yet on the base branch first |
| `docs PR changed` | `pulse approve <n>`, or approve spec in its view: the docs PR moved after gate 1, and `pulse go` merges only the commit someone approved |
| `spec rule` | `/pulse-re` on the item's spec on the base branch; `pulse approve <n>`, or approve spec in its view, names the rule it breaks, and for an approved item the ramp row names it too |
| `spec waits` | what the approval cannot move yet, grey and counted nowhere: `/pulse-re pushes the spec of #n` when the spec is neither on the base branch nor in an open pull request, `/pulse-re writes the spec of #n` when it has none |
| `last run` | `/pulse-build <n>` goes on from where the last run stopped |
| `needs a plan` | `pulse go` writes its plan, once you start it |
| `starts next` | `pulse go` builds it, once you start it |
| `queued` | waits for a free slot: every slot of yours is busy |
| `spec in progress` | `<login> writes the spec of #n`: the holder of the draft, or `/pulse-re` when nobody holds it |
| `nothing open` | `/pulse-ba` explores, `/pulse-re` writes specs |

The steps spell the commands as Claude Code does. In Codex, type `$pulse:<name>` for `/<name>`, so `$pulse:pulse-build` where the map says `/pulse-build`.

### Ramp

Every open item and every draft that nobody holds, once, in order ([Parallel work](../concepts/parallel-work#the-ramp)), each with what it waits for: `not approved`, `spec in PR #m: pulse go merges it` (approved, its spec only in its docs PR), `spec not on <base>` (approved, its spec neither on the base branch nor in an open pull request: nothing plans it), a spec or plan rule, `needs a plan`, `plan waits for you`, `waits for #n`, a file in use, or `queued`. The row marked `▲` starts next and takes your next free slot. A blocked row names its blockers (`needs a plan, waits for #11`); when they do not fit, the list ends with how many more (`waits for #11, #12 +3`). A row the last `pulse go` run failed says `failed:` and why, in red.

Two more states come from the board:

- `spec in progress`: a draft nobody holds. `/pulse-re` writes its spec; it takes no slot and never starts. Once someone holds it, it moves under them in [Who is doing what](#who-is-doing-what).
- `last run: <why>`: a run of `pulse go` gave the item back and left a note; its branch holds the work. The note comes after what the item waits for, so `not approved, last run: ...` still shows the approval first.

### Move waiting work

Pick an unclaimed ramp item, press `m`, then use `↑` and `↓` to preview its new position. `Enter` saves the shared order; `Esc` or back cancels without writing. Epics and claimed items cannot be moved. Moving an item changes neither its priority labels nor its dependencies: it must remain behind every open prerequisite.

The map, `pulse status`, and `pulse go` use the same order. Other clones see a saved move on their next full board read. Without a manual order, dependencies, effective priority, and item number determine the order; new items without a manual position follow the manually ordered part, still respecting dependencies. An invalid move, a changed claim or dependency, or a stale preview writes nothing and requires a fresh selection. A resize that loses the target context also cancels the move. The old `pulse rank` command and `Rank:` body lines do not control this order.

## Keys

No key but `?` needs Shift for navigation. The last line lists the main
keys of the level you are on; `?` shows the full help. Typed confirmations
use the exact characters of the repository, item number and commit shown.
It starts no `pulse go`.

The map is a tree: the board and work items, an item's details, and its actions. The footer lists the main keys; `?` shows the help. Navigation only reads. Confirmed actions can write approvals, auto switches, manual order, and lifecycle changes. Deletion has a separate reviewed removal-PR flow and an irreversible final confirmation. The map starts no `pulse go`; you start the runner in your own terminal. Creating items and claiming work by hand remain CLI actions.

The map runs as you, so no agent may press its keys: the [Pulse guard](../concepts/parallel-work#levers-belong-to-a-person) refuses text and keys that an agent sends into the map's pane (`herdr pane run`, `send-text`, `send-keys`, `herdr agent send-keys` and `prompt`, `herdr agent start --pane`), and `pulse map` typed into another terminal. It finds the pane locally: a pane that `.git/pulse/map-pane` names, and while a map of yours runs, any pane whose processes hold one, as Herdr (in the session the command names) or tmux and `ps` report them, in whatever tab or repository and after the pane moved. While a map runs, the guard is strict: a pane it cannot resolve counts as a map, and so does a command that names more than four panes or that another machine or a `HERDR_*` setting would answer; tmux passes only reads (`list-*`, `show-*`, `capture-pane`, `display-message`, `has-session`) and `send-keys` or `paste-buffer` into an absolute `%N` pane without a map; no script types keys (`keystroke`, `key code`). With no map running, every pane is open to agents as before and nothing is asked.

The map reads the board beside its keys, so a key never waits for GitHub. A write names itself in the footer while it runs (`approving #6…`), and the next frame shows the board as the write left it; keys typed while it runs are dropped, so none of them acts on the new board.

In a terminal lower than the map, the header stays on top and the last line keeps the keys; between them the map shows the part around the picked row and says how many lines it hides. The help stands under the header too. A terminal too low for header, one row, and keys gives header lines up first, so the map does not scroll while the terminal keeps its size. The map writes every row at its own place: a line with characters your terminal draws wider than the map counts them can cover the start of the row below until the map writes that row again, but it moves no row and never covers a confirmation, which the map writes again on every frame.

| Level | Key | Does |
|---|---|---|
| map | `↑` `↓` (or `k` `j`) | pick a visible board epic, an item in the tree, or a ramp row; `›` marks it |
| map | `Enter`, `→` | open the picked item |
| map | `g` | enter an issue number and press `Enter` to open it, including a closed feature, improvement, or fix; `Esc` cancels |
| map | `m` | preview a move of the picked, unclaimed ramp item |
| move | `↑` `↓`, `Enter` | change the target position, then save if the preview is still valid |
| map | `a` | the approval the picked item waits for, after a confirmation that names the gate, what it lets happen, and the account you act as (`approve spec #15 ui: dark mode as Sebastian (@seb): gate 1: agents may plan it`); `Enter` confirms, the map writes it, and `pulse go` acts on it. An item that waits for nobody says why in the last line |
| map | `1`, `2`, `3` | switch your own auto mode of gate 1 plan, 2 build, or 3 merge, after a short confirmation that names the gate, what then happens without asking you, and your login (`3 merge on: pulse go merges your green PRs, as @seb?`); `Enter` confirms, not within a second of opening, and `esc` cancels. It writes the same comment as `pulse auto <gate> on` or `off`, without an end: `pulse auto <gate> on --for 8h` sets one. In a map an agent started, the keys write nothing |
| map | `?` | show the help |
| map | `q` | quit; `q` quits only here, and `Esc`, `←`, `Backspace` only say so |
| item | `↑` `↓` (or `k` `j`) | pick one of the things the item offers |
| item | `Enter` | do the picked one |
| item | `a`, `o` | approve (the approval the item waits for), read spec, without picking |
| item | `PgUp`, `PgDn` | scroll long details; the arrow keys return to action selection |
| item | `?` | show the help; going back returns to the item |
| any but the map | `Esc`, `q`, `←`, `Backspace` | go back one level and drop what is not written yet: an approval not confirmed |
| any | `Ctrl-C` | quit the map |

### The item view

`Enter` opens the picked item in place of the map, and it stays live:

```text
#15 ui: dark mode ──────────────────────────────────────────────────────────────

 goal        The app follows the system's dark mode.
 stage       not approved
 approvals   none
 holder      nobody
 blocked by  nothing
 PR          none
 spec        _devprocess/requirements/features/FEAT-01-02-dark-mode.md
 plan        none yet

   approve spec  gate 1: agents may plan it
 › read spec     open it in a window
```

Long titles and goals wrap in the detail view; `PgUp` and `PgDn` let you read them in a low terminal. The goal is the first line of its spec, found on the base branch or through the same lookup as Read spec. The stage says what the map says on the item's line. Approvals names each approval the item got, one per row, with the GitHub account that gave it and when (`gate 1 by @ann, 27.09. 16:40`): the map reads the item's comments once as the view opens, and counts only a comment that `pulse approve` writes, from an account that may push; the name inside a comment counts for nothing. A long list of blockers ends with how many more, as on the ramp. The holder names who holds it, with the phase and age of the last sign of life. The plan line says where the plan is: in your working tree, or `on origin/<branch>` when it lies on a pushed item branch.

Below the facts stands what you can do with the item now, each with what it does. The view opens on a reading entry, so an `Enter` too many opens a window and writes nothing. Only what its stage allows is offered, and when that changes while you look, the cursor stays on the thing it was on:

| Offered | When | Does |
|---|---|---|
| `approve spec` | it is not approved | gate 1: agents may plan it. It writes the approval and nothing else; `pulse go` merges its docs PR into the base branch first. When it cannot be approved yet, the line says why in its place: it has no spec yet, its spec is still being written, its spec is neither on the base branch nor in an open pull request, or the spec breaks a rule |
| `approve plan` | its plan waits for a person, also once the plan or its spec changed since an approval | gate 2: agents may build it as this plan says, as origin has it |
| `try again` | `pulse go` gave up on it (`pulse:failed`) | takes the label off: the next `pulse go` tries it again |
| `read plan` | it has a plan | opens the plan in a window; one that lies only on its item branch opens as a copy to read |
| `read spec` | its spec is on the base branch, on a branch of origin, or in your working tree | opens the spec in a window, as the base branch has it: agents plan from that one. A spec that is not there yet, such as one on its branch of origin, opens as a copy to read from the newest branch on origin that has it, and the status line names that branch. A spec only in your working tree opens there; a spec path that leads out of the repository, or one that is no Markdown file, opens nothing |
| `read PR` | it has a pull request | opens it in your browser: its diff, the gates, and what departs from the plan |

### Defer, resume, discard, or delete

These are separate item actions for features, improvements, and fixes. They do not cascade through an epic. The preview names your login, the selected repository/item, affected records, and consequences. Cancel before confirmation to write nothing; if the state changes after the preview, inspect and confirm it again. `g` opens a closed item by number without reopening it or adding it to the active-work counts.

| Action | Result |
|---|---|
| `defer` | stop open work cooperatively and return it as-is to the open, paused backlog. Code, specs, uncommitted work, branches, PRs, approvals, notes, and evidence remain |
| `resume` | explicitly resume a completed defer pause. Existing approval/content/SHA checks still apply; unrelated holds remain |
| `discard` | stop work, then close the issue as not planned. Files, PRs, approval comments, and Git history remain; no code rollback occurs |
| `delete` | remove the item's code, specs, and active references through a reviewed removal PR, then permanently delete its GitHub issue and all comments after separate confirmation |

Defer keeps the item paused even with auto mode on, across restarts and clones. It blocks new starts, merges, and automatic completion until an explicit resume. The holder must acknowledge stopping and secure the work before a claim can be released. An unreachable holder or work that cannot safely be handed over leaves the operation pending or retains the claim for local resume; Pulse does not steal the claim or delete the worktree. Defer does not reopen completed work or invalidate all earlier approvals. A paused child remains open; discarded and deleted children do not count as completed work.

The same actions are available in your terminal. Choose the command for the action you intend:

```bash
pulse defer 15
pulse resume 15
pulse discard 15
pulse delete 15
```

#### Deletion is a staged removal

1. Read the warning and inventory: implementation changes, specs, active references, open work, dependent items, and the permanent loss of every issue comment. Confirm the exact `owner/repo#n` to request the controlled stop and prepare the reviewed removal scope when it is safe.
2. Review the separate removal PR. Its changes must remove the selected implementation, specs, and active references while preserving unrelated features and later independent work. Ambiguous ownership, conflicts, or dependencies stop the process for clarification. A clean revert or green tests alone do not prove complete removal.
3. Run `pulse delete <n>` again, or choose delete again in the map, to confirm `check owner/repo#n@<head>`. Pulse runs the removal's own tests, review and audit through its runner. After they pass, give a separate human merge approval bound to that head: `owner/repo#n@<head>`. A changed head requires a new preview and approval. Merging this PR does not delete the issue.
4. Once removal is integrated and verified, confirm final issue/comment deletion separately with `delete owner/repo#n@<head>`. Until then, the issue remains. Progress and completion are recorded in the removal PR so a failed step can be inspected and resumed after the original issue is gone.

If an independent base change arrives before merge, Pulse offers a confirmed
rebind followed by fresh gates and approval. A conflicting change stops for
scope review. If GitHub acknowledges deletion but the completion comment
fails, the original clone can repair that comment from its protected receipt;
a missing issue alone never proves successful deletion.

Removal uses new commits. Original branches, worktrees, and Git history remain; there is no force-push, history rewrite, or reset of the whole repository. Issue comments are permanently lost at the final step. An agent may prepare and check an authorized removal PR, but the merge approval and final deletion belong to a person with the required repository permissions.

### Approvals

`a` never writes on the first press. It shows the approval it writes and what that binds, and `Enter` confirms; any other key cancels. Every confirmation of the map takes no `Enter` within a second of opening: such an `Enter` came before you could read it, so it confirms nothing, the confirmation closes, and the footer says `enter came within a second of opening it`; what you typed before the confirmation showed is dropped. A confirmation shows a goal on one row and opens only when the terminal can show all it confirms; otherwise the map says to make the terminal larger. It stays open only as long: make the terminal smaller until part of it no longer shows, and the map closes it with the same message, and an `Enter` typed as the terminal changed confirms nothing. A resize that still shows all of it draws it anew, and its second starts again.

`a` does what `pulse approve` does, and nothing else. At gate 1 it adds `pulse:approved` and a comment that names your login; for a spec in a docs PR the comment reads `gate 1 ok at <head> <spec path>`, the commit the PR stands at and the spec, so a PR pushed to afterwards waits again (`docs PR changed since approval`). At gate 2 it writes the line `Plan-ok: <plan blob> <spec blob>` and the comment `plan ok at <plan blob> <spec blob>`: the ids git gives the plan as origin has it and the spec on the base branch, which the confirmation names, so a plan or spec changed afterwards waits again. At gate 3, on a ready pull request, it writes the comment `merge ok at <head>` for the head the confirmation names, which the next `pulse go` merges. After `pulse:failed` it takes the label off. It merges nothing: `pulse go` merges the docs PR of a spec not yet on the base branch before it plans the item, and only when every spec in that PR passes R1 to R6, the PR changes nothing outside `_devprocess/`, and its checks pass. `pulse go` counts an approval only from someone who may push to the repository. `a` refuses, and says why, a spec neither on the base branch nor in an open pull request (rule R1), for a feature, improvement, or fix a spec on the base branch that breaks one of R2 to R6, which `pulse check` reports for every approved item (an epic needs R1 only), and a plan that fails P1 to P6 or is not pushed yet. If the plan or spec changed between showing and `Enter`, the map says so and approves nothing. The approval of a plan is offered on any item whose plan waits for a person, also on one you hold: `/pulse-build` keeps its claim while the plan waits. On an item that waits for no approval, `a` says so and writes nothing.

### Merging

For ordinary work, a ready pull request says `waits for merge`: approve its merge with `a` (gate 3), and the next `pulse go` merges it, or merge it on GitHub; `read PR` opens it with its diff, its gates, and what departs from the plan. A pull request into another branch than the base gets retargeted on GitHub first. A merged item leaves the map at once unless a lifecycle pause prevents automatic completion. The separate [deletion flow](#deletion-is-a-staged-removal) requires its own removal-PR head approval and a later final issue-deletion confirmation.

### Links

With color, every `#n` on the map and in the item view is a link to its issue on GitHub: a click opens it in a terminal that knows links (OSC 8), such as VS Code or iTerm. Other terminals show the plain number, and tmux passes links on only with `terminal-features` set to `hyperlinks`.

### Opening the spec

Read spec and read plan never take the terminal. They open the file with the first of these that exists:

1. the command in `PULSE_EDITOR`, which gets the file's path (for example `PULSE_EDITOR="subl -n"`). Name a program that opens a window and returns; a terminal editor gets no terminal here.
2. in the terminal of VS Code or Cursor (`TERM_PROGRAM` is `vscode`): that editor's window, through `code -r` or `cursor -r`.
3. the system's app for the file: `open` on macOS, `xdg-open` on Linux.

Without any of them, the map shows the path to open yourself. The goal line of the item view reads the spec the same way, so a spec on a branch shows its goal before it is merged.

What someone else changes reaches your map within seconds: the map asks GitHub every two seconds whether anything moved, with a request that costs nothing while nothing changed, and reloads only then (and every 30 seconds, for pull request checks).

## Two maps at once

Run as many as you like, in one clone or in several: each map reads the board on its own and ends on its own. Their green lights breathe in step, because every frame follows the clock. A key pressed in one map shows in the others at their next read.

## After an update

The map keeps up with Pulse by itself. Once a minute it checks which Pulse the `pulse` command starts; when that one is newer than its own, for example after a plugin update, the map restores the terminal and starts again with the newer Pulse, in the same terminal. Once a day it asks the Pulse repository for the newest release and, when that is newer, names it once in its footer with the update commands for Claude Code and Codex. Without a network answer it says nothing. A map started from a clone of the repository stays with that clone.

## How it ends

`q` on the map, Ctrl-C, closing the terminal, and `kill` all end it the same way: the cursor comes back, and nothing stays behind. The map runs no server and opens no port, so there is nothing to stop or clean up.

## Where the data comes from

The map shows claims: what each person holds, from the board on GitHub, yours and your teammates' alike. The auto switches come from the comments of the issue "Pulse auto mode", read at most every 30 seconds. No hook records what a session does, so the map shows no chat and no agent's current tool; a phase of `pulse go` counts as working.
