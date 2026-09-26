---
title: /pulse-map
description: The live map in a terminal. Who works on what, a light per agent, the board, what needs you next, and the ramp of ready work.
---

# /pulse-map

One view of the whole team: who works on what right now, what waits for you, and what goes out next. It runs in a terminal:

```bash
pulse map
```

It reads the board every two seconds and redraws its lights twice a second, until you press `q` on the map. `pulse map --once` prints one frame and ends; so does `pulse map` in a pipe, a file, or an agent's shell, where there is no terminal. `pulse status` prints the same frame once.

The map is as wide as its terminal, from 60 to 160 columns, and every frame asks the terminal again: resize it, and the next frame fits the new width. Without a terminal (`pulse status` or `pulse map` in a pipe, a file, or an agent's shell) the map takes the width in `COLUMNS`, else 80 columns.

`pulse map --demo` plays a morning at a sample project in time-lapse, without a repository: agents pick up work, one asks a question, a test fails and recovers, pull requests go out, and Alice and Bob work on several items in parallel, one of them waiting for your review. The demo takes no keys; Ctrl-C ends it.

## Open it from the chat

A chat cannot show a live view, so `/pulse-map` (in Codex `$pulse:pulse-map`) brings you to a terminal. It runs `pulse map --ensure`, the same call that opens the map when work starts ([below](#when-it-opens-by-itself)): it opens the map where you work unless a map of this clone runs already, and passes on the one line that says what it did. Inside tmux that is a pane beside the chat, in a terminal on macOS or Linux a new window; `q` closes either. In VS Code, with Claude Code or Codex, nothing opens: the line names the task "Pulse map" (Terminal > Run Task) where the project has it, else that [`/pulse-setup`](./pulse-setup) (in Codex `$pulse:pulse-setup`) adds it on your yes, and the command for the terminal panel. Codex runs the call outside its sandbox, which cannot open a terminal: with the Codex rules from `/pulse-setup`, or after you approve it. With the map switched off (`map_autostart = false`, `PULSE_MAP=off`), `/pulse-map` asks you to run `pulse map` in a terminal of your own.

The chat never runs the map itself in its own shell and never pastes a frame instead: a frame is stale the moment it prints. There is no browser page and no sidebar; the map is the terminal. If the terminal says `pulse: command not found`, run the `setup --cli` line for your agent from [Installation](../tutorials/installation) once per machine: it calls the installed plugin by its path.

### When it opens by itself

`pulse go` as it starts, `pulse claim`, and `pulse new --draft` open the map when no map of this clone runs or is starting; `pulse map --ensure` and `/pulse-map` do the same on request. Each says in one line what it did. Where the map opens:

| Where you work | What opens |
|---|---|
| a terminal inside tmux | a pane beside, the focus stays where it was |
| a terminal on macOS | a new window of Terminal, or of iTerm when you work in iTerm |
| a terminal on Linux with a display | a window of the first terminal emulator found: `x-terminal-emulator`, `gnome-terminal`, `konsole`, `xterm` |
| VS Code, with Claude Code or Codex | nothing; the task "Pulse map" starts the map in a terminal panel of its own when the folder opens, and the line names the command and, where the project has it, the task. [`/pulse-setup`](./pulse-setup) adds the task on your yes; VS Code asks you once to allow automatic tasks |
| anywhere else | nothing; the line names the command for a terminal of its own |

The agents that `pulse go` starts never open a map. To turn it off, set `map_autostart = false` in `.pulse/config.toml` for the project, or `PULSE_MAP=off` in the environment for one shell ([Configuration](../reference/configuration)).

### It starts pulse go

Approving an item means building it, so nobody has to type `pulse go` afterwards. Each time the live map reads the board, it looks for approved work: an item that starts next on the ramp, or an approved item nobody holds that needs a plan. When there is some and no run of this clone lives, the map starts `pulse go` apart from itself, as `pulse go --detach` does, and its footer names the items and the log `.git/pulse/go/run.log` once. The run ends when the ramp is empty, as always, and the next approval starts one again, yours or a teammate's. A minute passes between two starts from the maps of one clone. The map starts nothing, and says why in its footer, when:

- the last run did not finish an item (it failed, hit a usage limit, was stopped, or its claim was refused): the footer names it, and it starts no run until you look at it, though a run started for other work may take it along;
- the last run the map started took none of the items that wait now: the map starts again once the ramp changes;
- you stopped the last run, or the last start ended before it wrote its report: no start until `pulse go` runs by hand;
- `.pulse/config.toml` in your working tree differs from the one on origin's default branch, or on the base branch that one names: the map never runs a `verify` or agent command that a checked-out branch brings, so on someone's pull request branch you start `pulse go` by hand; where git knows no `origin/HEAD` yet, `git remote set-head origin -a` sets it;
- `verify` is not set: the footer names the command that sets it.

Set `go_autostart = false` in `.pulse/config.toml` to turn it off for the project, or `PULSE_GO=off` (also `0`, `false`, `no`) for one shell. A run has the same rights and environment as the map that started it, and `run.log` marks each start the map made.

## What you see

```text
 ▀▀▀▀▀▀▜▄
 ▟▛▀▀▀▀▐█▌  pulse  acme/shop                                               09:28
 ▄█████▛▀   ● 5 working   ● 3 need you   ● 1 failing
▐█▗█▛▀▘
▐▛▝▘

BOARD ──────────────────────────────────────────────────────────────────────────
 ready to start ██████░░░░░░░░░░░░░░░░░░   3
 in progress    ███████████░░░░░░░░░░░░░   6
 in review      ██████░░░░░░░░░░░░░░░░░░   3
 blocked        ░░░░░░░░░░░░░░░░░░░░░░░░   0
 not ready yet  ██░░░░░░░░░░░░░░░░░░░░░░   1
 #10 sign-in that lasts                                  █░░░░░░░░░ 1 of 14 done

WHO IS DOING WHAT ──────────────────────────────────────────────────────────────
● Sebastian                                   4 of 4 slots busy, 5 agents active
├ ● develop                                                     running pulse go
├ ● #19 fix: token expiry                                               building
│ └ editing expiry.ts
├ ● #17 docs: auth flow                                                fix round
│ └ editing auth.md
├ ● #20 api: pagination cursor                                          building
│ └ reading cursor.ts
├ ● #21 ui: empty states                                                building
│ └ editing Empty.tsx
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
 not approved                           pulse approve 15, or approve in its view
 starts next                                                 /pulse-go builds it

RAMP all open work, in team order ──────────────────────────────────────────────
  #13 ui: token banner                                                    queued
  #15 ui: dark mode                                                 not approved
  #18 ui: settings panel                                                  queued
  #22 db: session index                                                   queued
```

Each line holds a title on the left and its state on the right. The state takes the room it needs; when a long title needs the room too, the state gets about 45 percent of the line and the title the rest, cut short with `…`. A list of blockers fills the state's room and ends with how many more (`+3`). The key line and any message at the bottom wrap to the next line instead of being cut.

### Lights

| Light | Means |
|---|---|
| green | an agent works: a session on this machine, or a phase of `pulse go` on the item |
| yellow | something waits for you: an agent asks a question or waits at a permission prompt, a pull request asks for your review, your pull request waits for your merge, an item waits for approval, or a plan waits for you |
| red | something failed: an agent's last test or build command, a pull request's checks, a draft pull request with a red gate, or an item the last `pulse go` run failed |
| grey | idle: an agent's turn ended or it was silent for five minutes, a teammate's item without news, a ramp row that only waits |

The worst light rolls up to its feature and to the person, so the top row of each person is enough at a glance.

A working light breathes: its brightness rises and falls in a cycle of about three seconds, while the character and its size stay the same. Nothing blinks. How it looks depends on the terminal:

- **Truecolor** (`COLORTERM` is `truecolor` or `24bit`) and **256 colors** (`TERM` contains `256color`): the green light breathes.
- **16 colors:** every light is steady.
- **`--no-color`:** no color and no motion. `--color` keeps the colors when you pipe a frame.

### Counts

- **Header:** how many lights on the map are green (`working`), yellow (`need you`), and red (`failing`). With color, `need you` is a link to the chat that has waited longest among those it can open.
- **Board:** every open feature, improvement, and fix, and every draft, once: ready to start, in progress (held, no pull request yet, a draft whose spec someone writes included), in review (held, with a pull request), blocked by an open item, and not ready yet (a draft nobody holds, not approved, a spec or plan that is not ready, a file in use). An epic with its spec attached counts in no group; with children it gets a line of its own below.
- **Epics:** one line per open epic with children, how far it is: its children closed as completed or merged, of those and its open children (`1 of 14 done`). A child closed as not planned counts in neither. The map reads the closed children at most every 30 seconds, and only while an epic is open.
- **Your row:** your slots (items you hold without a pull request, out of `cap` in `.pulse/config.toml`) and all working agents, subagents included and idle ones not. A teammate's work takes none of your slots.

### Who is doing what

You come first, with the features you hold and the drafts whose spec you write. Each feature line says where it stands: while `pulse go` runs it, the step of its chain (`planning`, `building`, `RED check running`, `tests running`, `review running`, `audit running`, `fix round`); once its pull request exists, `draft PR #n, a gate is red` or `PR #n, waits for merge`; `on #n` when it is stacked on the branch of feature #n. Below a feature with a running agent stands what the agent does, in plain words: an agent that needs you or failed comes first, otherwise the latest activity. Where several chats stand on one feature and some of them ask you, the line counts them and names what a working agent there does: `2 chats ask you, Codex: running npm run test:e2e`. Which chats they are, [Next](#next) says. An agent counts for the item its session holds, wherever its directory stands; without a claim, for the item its branch builds, and a Codex agent stands on the branch where its last command ran. An agent outside any feature, such as the session that runs `pulse go` on `develop`, gets a line with its branch. A merged feature leaves the map at once, also when it merged into a branch other than the default one: GitHub closes nothing there, and `pulse status` closes the item later. Until it does, an item it blocks still waits for it; the next `pulse go` closes it before it starts anything. A merged pull request that changes only files under `_devprocess/`, such as the spec, counts for no feature by its branch name, so the feature stays.

Teammates follow, each with the items they hold and where each pull request stands. Until the pull request exists, the line tells how their work goes, from the sign of life their session or `pulse go` writes into the claim:

| Line | Means |
|---|---|
| `building, 4 min ago` | the phase of their last sign of life, and its age (`<phase>, <age> ago`) |
| `no sign of life for 45 min` | no sign of life for 30 minutes or more: ask them, or take the item over |
| `no PR yet, held 3 h` | a claim from before signs of life existed: only its age |
| `spec in progress by bob, 20 min` | a draft: their `/pulse-ba` or `/pulse-re` session writes its spec, last seen 20 minutes ago (else the age of the claim); a held draft stands here only, not on the ramp |

Their lights come from GitHub: yellow when a pull request asks for your review, red when its checks fail, grey otherwise. Whether an agent runs on their machine stays there, so their items never turn green.

### Next

One line per kind of thing that waits, the most urgent first, each with the step that moves its first item; a chat that asks you gets a line of its own. An item that waits for an open blocker is left out, and so is its light in the header: its blocker moves first.

| Line | Step it names |
|---|---|
| `failing` | `/pulse-build <n>` takes it on in a session |
| `asks you` | answer that chat: one line per chat that waits for you, the longest waiting first, with its agent, title, and how long it waits (`answer Claude "Epic 17 layout" (35 min)`), or where it stands when it has no title (`answer Codex on #12`). A long title is cut inside its quotes, so the wait time always shows. A chat counts once, also when a subagent of it asks. `Enter` on the line opens the chat in VS Code, and so does a click with color; a chat that runs in a terminal gets no link and says `in its terminal`, a thread of the Codex app says `in the Codex app`, a chat in Cursor or VS Code Insiders names its editor |
| `your review` | review the pull request on GitHub |
| `waits for merge` | merge the pull request on GitHub |
| `plan waits for you` | `pulse approve-plan <n>`, or approve plan in its view |
| `not approved` | `pulse approve <n>`, or approve in its view; while its spec is not on the base branch, merge the spec first |
| `spec rule` | `/pulse-re` on the item's spec; `pulse approve <n>`, or approve in its view, names the rule it breaks, and for an approved item the ramp row names it too |
| `last run` | `/pulse-build <n>` goes on from where the last run stopped |
| `needs a plan` | `/pulse-go` writes its plan |
| `starts next` | `/pulse-go` builds it |
| `spec in progress` | `<login> writes the spec of #n`: the holder of the draft, or `/pulse-re` when nobody holds it |
| `nothing open` | `/pulse-ba` explores, `/pulse-re` writes specs |

The steps spell the commands as Claude Code does. In Codex, type `$pulse:<name>` for `/<name>`, so `$pulse:pulse-go` where the map says `/pulse-go`.

### Ramp

Every open item and every draft that nobody holds, once, in the team's order ([Parallel work](../concepts/parallel-work#the-ramp)), each with what it waits for: `not approved`, a spec or plan rule, `needs a plan`, `plan waits for you`, `waits for #n`, a file in use, or `queued`. The row marked `▲` starts next and takes your next free slot. A blocked row names its blockers (`needs a plan, waits for #11`); when they do not fit, the list ends with how many more (`waits for #11, #12 +3`). A row the last `pulse go` run failed says `failed:` and why, in red. `for #n` says the item carries the rank of #n, which waits for it.

Two more states come from the board:

- `spec in progress`: a draft nobody holds. `/pulse-re` writes its spec; it takes no slot and never starts. Once someone holds it, it moves under them in [Who is doing what](#who-is-doing-what).
- `last run: <why>`: a run of `pulse go`, or a session with `pulse release <n> --note`, gave the item back and left a note; its branch holds the work. The note comes after what the item waits for, so `not approved, last run: ...` still shows the approval first.

## Keys

The map is a tree: the map itself, an item, and what acts on that item. No key needs Shift, and the last line always lists the keys of the level you are on. Only the order and approvals are written from the map: the order, the approval to build an item and taking it back, and the approval of a plan. Claiming, closing, and new items stay with the commands.

The map reads the board beside its keys, so a key never waits for GitHub. A write names itself in the footer while it runs (`moving #8…`, `approving #6…`), and the next frame shows the board as the write left it; keys typed while it runs are dropped, so none of them acts on the new board.

In a terminal lower than the map, the header stays on top and the last line keeps the keys; between them the map shows the part around the picked row and says how many lines it hides. The help stands under the header too. A terminal too low for header, one row, and keys gives header lines up first, so the map never scrolls.

| Level | Key | Does |
|---|---|---|
| map | `↑` `↓` (or `k` `j`) | pick an item: a feature in the tree, a chat that asks you in [Next](#next), or a ramp row; `›` marks it |
| map | `Enter`, `→` | open the picked item, or the picked chat in VS Code |
| map | `m` | move the picked ramp row; `Enter` places it and you stay on the map |
| map | `?` | show the help |
| map | `q` | quit; `q` quits only here, and `Esc`, `←`, `Backspace` only say so |
| item | `↑` `↓` | pick one of the things the item offers |
| item | `Enter` | do the picked one |
| item | `a`, `p`, `o` | approve, approve plan, read spec, without picking |
| item | `?` | show the help; going back returns to the item |
| move | `↑` `↓` | move the item among the ramp rows |
| move | `Enter` | place it there: the only write of the move |
| any but the map | `Esc`, `q`, `←`, `Backspace` | go back one level and drop what is not written yet: a move, an approval not confirmed |

### The item view

`Enter` opens the picked item in place of the map, and it stays live:

```text
#15 ui: dark mode ──────────────────────────────────────────────────────────────

 goal        The app follows the system's dark mode.
 stage       not approved
 holder      nobody
 blocked by  nothing
 PR          none
 plan        none yet

 › approve       agents plan and build it when its turn comes
   prioritize    top of the ramp: it gets the next free slot
   read spec     open it in your editor
```

The goal is the first line of its spec on the base branch. The stage says what the map says on the item's line. A long list of blockers ends with how many more, as on the ramp. The holder names who holds it, with the phase and age of the last sign of life. The plan line says where the plan is: in your working tree, or `on origin/<branch>` when it lies on a pushed item branch.

Below the facts stands what you can do with the item now, each with what it does. Only what its stage allows is offered, and when that changes while you look, the cursor stays on the thing it was on:

| Offered | When | Does |
|---|---|---|
| `approve` | it is not approved | agents plan and build it when its turn comes. When it cannot be approved yet, the line says why in its place: its spec is still on a branch, breaks a rule, or is still being written |
| `unapprove` | it is approved and on the ramp | takes the approval back after `Enter` confirms: nobody builds it until someone approves it again |
| `approve plan` | its plan waits for a person | the agent builds it as this plan says |
| `read plan` | it has a plan | opens the plan in a window; one that lies only on its item branch opens as a copy to read |
| `prioritize` | it is on the ramp, below the top | puts it at the top of the ramp, with one write: it gets the next free slot |
| `read spec` | it has a spec | opens the spec in a window |

### Approvals

`approve`, `approve plan`, and `unapprove` never write on the first press. They show what the approval binds, and `Enter` confirms; any other key cancels. `approve` refuses what `pulse approve` refuses, and says why: a spec that is not on `origin/<base>` (rule R1), because agents plan from the base branch, and for a feature, improvement, or fix a spec there that breaks one of R2 to R6, which `pulse check` would hold against every commit; an epic needs R1 only. The map sees origin as of its last fetch, which runs beside it at most every 30 seconds. `approve plan` is offered on any item whose plan waits for a person, also on one you hold: `/pulse-build` keeps its claim while the plan waits. If the plan changed between showing and `Enter`, the map says so and approves nothing. On an item that is approved already, `a` says so and writes nothing.

### Moving

`m` works on the map, on ramp rows, a draft nobody holds included; an item someone holds has no place in the order. The arrows move the item among the other rows, and nothing is written until `Enter` places it, however far it went. Like [`pulse rank`](../reference/commands), this writes the rank of the moved item and no other, unless items above it have no rank yet: those get one too. `Esc` puts it back and writes nothing. Either way you stay on the map. To put an item first in one step, pick prioritize in its view.

With color, every `#n` on the map and in the item view is a link to its issue on GitHub: a click opens it in a terminal that knows links (OSC 8), such as VS Code or iTerm. Other terminals show the plain number, and tmux passes links on only with `terminal-features` set to `hyperlinks`.

### Opening the spec

Read spec and read plan never take the terminal. They open the file with the first of these that exists:

1. the command in `PULSE_EDITOR`, which gets the file's path (for example `PULSE_EDITOR="subl -n"`). Name a program that opens a window and returns; a terminal editor gets no terminal here.
2. in the terminal of VS Code or Cursor (`TERM_PROGRAM` is `vscode`): that editor's window, through `code -r` or `cursor -r`.
3. the system's app for the file: `open` on macOS, `xdg-open` on Linux.

Without any of them, the map shows the path to open yourself.

### Opening a chat

A chat that asks you opens through the link its extension understands: `vscode://anthropic.claude-code/open?session=<id>` for Claude Code, `vscode://openai.chatgpt/local/<id>` for Codex. The map hands the link to `open` on macOS or `xdg-open` on Linux and runs on; `PULSE_EDITOR` and `code -r` play no part, since `code -r` takes a link for a file. A subagent's line opens the chat of its session. Only a chat in VS Code whose session id is a UUID gets a link; Cursor and VS Code Insiders get none, since the link opens VS Code. For a chat in a terminal, in the Codex app, in Cursor, or in VS Code Insiders, `Enter` says in the status line where to answer it: a link would open that session a second time in VS Code. A job of `pulse go` or `pulse review --run` gets no link either, even when you started it from a VS Code chat.

What someone else changes reaches your map within seconds: the map asks GitHub every two seconds whether anything moved, with a request that costs nothing while nothing changed, and reloads only then (and every 30 seconds, for pull request checks). Two people moving different items at the same time both keep their move.

## Two maps at once

Run as many as you like, in one clone or in several: each map reads the board on its own and ends on its own. Their green lights breathe in step, because every frame follows the clock. A key pressed in one map shows in the others at their next read.

## After an update

The map keeps up with Pulse by itself. Once a minute it checks which Pulse the `pulse` command starts; when that one is newer than its own, for example after a plugin update, the map restores the terminal and starts again with the newer Pulse, in the same terminal. Once a day it asks the Pulse repository for the newest release and, when that is newer, names it once in its footer with the update commands for Claude Code and Codex; the next session in the project names it too. Without a network answer it says nothing. A map started from a clone of the repository stays with that clone.

## How it ends

`q` on the map, Ctrl-C, closing the terminal, and `kill` all end it the same way: the cursor comes back, and nothing stays behind. The map runs no server and opens no port, so there is nothing to stop or clean up.

## Where the data comes from

Live detail about agents comes from the sessions on your machine, recorded by the Pulse hooks: Claude Code with the plugin, and Codex with the plugin, in the CLI and in the IDE extension, once you trusted the plugin's hooks, all of them (with `/hooks` in the CLI or one by one on the Hooks page of the extension's settings). When a chat waits for you, the hooks also note whether it runs in VS Code and what it is called: in Claude Code its own name, else its generated title, else its last prompt; in Codex its thread name. Only printable characters reach the map, 60 at most. The log that holds them is readable by you only. Sessions without the hooks, such as [Codex without the plugin](../tutorials/installation#codex-without-the-plugin), get no light; the items they hold still show up. A phase of `pulse go` counts as working with or without hooks. What teammates do reaches the map through the board on GitHub.

The demo on the [start page](/) of these docs and the GIF in the README show the terminal's own frames at 80 columns in truecolor, converted to HTML, with no animation of their own.
