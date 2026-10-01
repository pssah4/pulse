---
title: Parallel work
description: How Pulse decides what runs at the same time, and how parallel results merge without surprises.
---

# Parallel work

When a coding agent ships a feature in an afternoon, the bottleneck moves from writing code to deciding what can run at the same time without colliding. Pulse makes that decision with a script, not with a prompt, so an agent cannot forget to parallelize and cannot start two things that will conflict.

## Two hard constraints

1. **Blockers first.** An item is built only when every item that blocks it is done: merged, even when its pull request was ready long before. Planning does not wait for blockers. The records on the board hold these links ("blocked by"), and the ramp reads them.
2. **Disjoint files.** Two items run at the same time only if their PLANs touch different files. Every PLAN lists its files at the top; the ramp compares them with everything that is already running.

The second rule catches merge conflicts and duplicate work in one criterion. It is conservative on purpose, and it needs a PLAN: an item without one waits at `needs a plan` until it has one, planned in the `/pulse-re` session that approved it, by `/pulse-build`, or by `pulse go`, so no build ever starts with unknown files.

## The ramp

Every open item nobody works on lines up like pallets at a loading dock, in order, and agents pick up ready work from the front. The ramp is the ordered backlog: each item appears once, with what it waits for.

- **Order:** no item before an open blocker; among the rest, the best `P0` to `P2` label of the item and of everything it unblocks, then the lower number. So a `P2` item that blocks a `P0` item comes before a `P1` item.
- **What each line waits for:** `not approved`, `spec: <rule>`, `needs a plan`, `plan: <rule>`, `plan waits for you`, `waits for #n`, `locked: <file> in use by #n`, then `queued` and `starts next`. `pulse go` plans what needs a plan and builds from the top.
- **Slots:** `cap` in `.pulse/config.toml` sets how many items run at once for you. Your own running items take slots; a teammate's running item takes none of yours, but its files are held for everyone. When Alice works on #12, Sebastian keeps all four of his slots, and the files of #12 stay off limits for his agents until Alice is done.
- **Locked:** a ready item whose files another running item holds waits, and the ramp names the file and the holder: `#18 ui: settings panel   locked: token.ts in use by #11`. `pulse claim` refuses such an item with the same file and holder, so a build started by hand waits too.
- **Reserved:** an item selected to start next reserves its files before its agent starts. A conflicting row says `reserved: test_text.py for #3 (starts next)`. A direct `pulse claim` gives the same reason and asks you to start #3 first. Only items selected for a free slot reserve files; a gated or merely queued item creates no reservation.
- **Waits:** an item with an open blocker waits until the blocker is done: `#13 ui: token banner   waits for #11`.

`pulse status` prints it once; the [map](../guides/pulse-map) draws it live.

## Planning so that more can run at once

Manual order is shared by the map and the runner. Use `m`, arrows, then Enter on an unclaimed work item in the map. Open dependencies always come first. New items without a manual position follow the manually ordered part using the normal priority rules. Claims and dependencies that change during a move invalidate its preview. Esc cancels without writing. Epics can be selected to read, but are not movable work items. Old `Rank:` body lines stay ignored; there is no `pulse rank` command.

- **Contract first.** If item B needs item A only for an interface (a type, an endpoint signature, a schema), that interface becomes its own small item that blocks B. A's implementation no longer blocks B, and B starts as soon as the contract is merged. Nothing builds on a blocker's branch.
- **Waves.** Inside a PLAN, tasks carry a wave number. Tasks of one wave touch disjoint files and do not need each other's output; the wave's checks pass before the next wave starts. `pulse check` keeps the files of a wave disjoint.

## Merging parallel results

Every feature gets its own branch, `<type>/<n>-<slug>`, and exactly one pull request back to the base branch. On that branch `pulse go` runs three gates in order: the project's tests (`verify`), a review, and a security audit, the last two in one fresh session. A red gate gets a fix round, one per item, and after it the tests run again and only the gates that were red. The pull request is ready only when all three passed; otherwise it stays a draft that names what is open, and the item keeps its claim, so no later run builds it again. You approve the merge of each ready pull request (gate 3), and `pulse go` merges it and closes the item, on any base branch. A pull request merged on GitHub closes at the start of the next run.

Disjoint files make independent pull requests merge cleanly against the base branch. Dependencies merge in order: a blocker before the items it blocks, and a dependent starts only after that merge. Before it starts anything on a new commit of the base branch, `pulse go` checks that commit with the project's CI, `setup`, and `verify`, and on a red base it starts nothing but the fix marked `pulse:base` ([the base check](../guides/pulse-go#the-base-check)).

## Who starts the agents

[`pulse go`](../guides/pulse-go) does. It plans every approved item that has no PLAN yet, claims the next items to build, and creates one worktree per item in the repository under `.worktrees/` (a second checkout in its own folder, on the item's branch). In each it starts one agent without a chat window (Claude Code or Codex, from a template in the config), refills a slot the moment it frees up, runs the tests, the review, and the security audit on each finished item, opens its pull request with the results, and gives a failed item back to the ramp. The [map](../guides/pulse-map) lists each feature under its person with the step of its chain or the state of its pull request. Headless agents keep your permission rules: Pulse never bypasses an approval.

One `pulse go` run can drive Claude Code and Codex together, each with its own slots, and hands an item on when one of them hits its usage limit.

## Claims and handover

A claim belongs to one session: a Claude Code session, a Codex thread, a `pulse go` run, or your terminal. All of them act under your GitHub login, so each claim also leaves a mark on the item's record that names its session. A second session is refused, and of two claims at the same moment the older mark wins. The refusal names the holder, since when, and the command that frees the item, and the [map](../guides/pulse-map) shows the phase of a teammate's claim and its last sign of life ([What others see](#what-others-see)).

- **Hand over another person's claim:** `pulse release --take <n>`, after that person agreed. Their assignee and claim marks go, a comment on the record names who did it, and the new session claims as usual. An agent never runs it: it names the command for your own terminal.
- **Take over from a session of your own that has ended:** `pulse claim --take <n>`.
- **Take an approval back:** remove the `pulse:approved` label in GitHub (the map writes approvals only); until someone approves the item again, nothing claims it.

`release` refuses a claim that is not yours. An item closes when `pulse go` merges its pull request; one you drop, you close on GitHub. The levers that belong to a person refuse to run in any agent session ([Levers belong to a person](#levers-belong-to-a-person)). An agent that `pulse go` started holds as its run, so it claims and gives back only its own item, which `PULSE_ITEM` names.

## Levers belong to a person

Approving a spec or a PLAN, taking over a claim, closing an item, and marking a pull request ready or merging it are a person's decisions. Agents never pull these levers, and three layers stop an agent that pulls one in the open:

- **The command line.** `pulse approve`, `auto` with `on` or `off`, `claim --take`, and `release --take` refuse to run when an agent marker is set (`PULSE_HOLDER`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, `CODEX_THREAD_ID`) or stdin is not a terminal, and so do `setup --remove` and `setup --mode off`, which would switch the guard off. Run them in your own terminal, or use the map.
- **The Pulse guard.** A hook checks every shell, Monitor, and MCP call of a Claude Code or Codex session and its subagents before it runs, and denies it with "Gate levers belong to a person or to their own auto switch". It acts in a session whose working directory lies in a project where Pulse is on, or whose project Claude Code names in `CLAUDE_PROJECT_DIR`: it reads that project's `.pulse/config.toml`, and a session outside such a project has no guard. It reads through `env`, `command`, full paths, the program name in any case, the `-c` of `bash`, `sh`, `zsh`, `dash`, `ksh`, and `fish` (with any options before it), `pwsh -Command`, a shell that reads its commands from stdin, `$(...)` and backticks outside single quotes, `$'...'`, line continuations, comments, redirections, chains with `;`, `&&`, `||`, `|`, and `-R` or `--repo` anywhere.
- **The Codex rules.** With `pulse setup --codex-rules`, Codex refuses the same levers in every mode ("blocked by policy"). A prefix rule sees only how a command starts, so `gh -R o/r pr merge 5`, `env gh pr merge 5`, or a full path pass it; there the guard holds.

The guard denies:

- `pulse approve`, `auto` with `on` or `off` (`pulse auto build on`, `pulse auto --for 8h merge on`), `claim --take`, `release --take`, `setup --remove`, and `setup --mode off`, also as quoted text anywhere in the command
- `gh pr merge`, `gh pr ready`, `gh pr review --approve`, and `gh pr create` without `--draft`
- `gh issue close`, `reopen`, `edit`, `pin`, `unpin`, `delete`, `transfer`, and `lock`; `gh label create`, `edit`, and `delete`; `gh repo edit`; `gh issue create` with a `pulse:` label or the title "Pulse auto mode"
- a `gh` command that writes while its line holds `<!-- pulse:`, `Plan-ok`, `plan ok at`, or `merge ok at`, also in a heredoc, a here-string, or a pipe; a comment, issue, or pull request whose `--body-file` holds one, is no regular file the guard can read (the first 64 KB), or is named twice in the line; a body from stdin that no heredoc, here-string, `echo`, or `printf` of the line feeds; and `$(...)` or backticks in `--body` or `--body-file`
- `gh api` with a method other than GET, or with `-f`, `-F`, `--field`, `--raw-field`, or `--input`; `gh auth token` and `gh auth status --show-token`
- `git push` with `--force`, `-f`, `--force-with-lease`, `--mirror`, `--no-verify`, `-n` (also as a start git takes, such as `--force-w`), a `+` refspec, or a refspec with `*`, or onto the base or default branch; `git commit` with `--no-verify` or `-n`. A push that names no branch, or `HEAD` or `@`, or one the push computes (`"$(git branch --show-current)"`), counts the branch the chain pushes from: after its last `cd` or `pushd`, or the branch a `checkout` or `switch` names. Where the guard cannot tell (another repository through `GIT_DIR` or `--git-dir`, a directory it cannot name, a checkout of a file, git that does not answer) it denies the push; so does a commit or push with `-c core.hooksPath`
- a command that unsets or blanks an agent marker (`unset CODEX_THREAD_ID`, `env -u CLAUDE_CODE_SESSION_ID`, `env -i`, `CLAUDE_CODE_SESSION_ID=`), since the command line would then take the agent for you
- `claude` with `--bare`, or with `--settings` that switch every hook off (`"disableAllHooks"` set) or the Pulse plugin (`enabledPlugins` with a `pulse@` key set false), as JSON in the command or in the file it names; a settings value that is neither JSON nor a regular file the guard can read (a fifo, a variable it cannot expand), or a file the command also names elsewhere, since it may write that file first; and `opencode run`: each starts an agent without the guard
- a change to `.pulse/config.toml` or its directory by shell, also through `./`, `..`, a symlink, a glob in a word that names `.pulse/`, or after `cd .pulse`: `rm`, `truncate`, `ex`, `ed`, `sed -i`, and `perl -i` at all; and `tee`, `>`, or `>>` that leaves `mode` other than `on`. The guard judges only the words of the writing command and its heredoc or here-string: a `mode = ...` (quoted key too) with another value, or a whole new file without `mode`, is denied, and so is content that comes through a pipe or from a file (`<`). `cp` or `mv` over the file, content a program reads from a file of its own, and an edit through the agent's own file tools pass
- the GitHub tools of an MCP server, except those that read (`get`, `list`, `search`, `..._read`); a `command` or `cmd` of any MCP tool is checked as a command

Text that goes into another terminal gets the same check: `herdr pane run`, `send-text`, and `send-keys`, `herdr agent prompt`, `tmux send-keys`, `new-window`, `split-window`, `new-session`, `run-shell`, `respawn-pane`, `respawn-window`, and `display-popup`, and `osascript`, with `-e` or fed by a heredoc. A pane that an agent opens has no agent marker and a terminal, so a command typed there would count as yours. For the same reason the guard lets no agent without it start in a pane: `herdr agent start` with a kind other than `claude` or `codex`, `claude --bare`, and text for another terminal that starts `opencode`, `gemini`, `pi`, `aider`, `amp`, `goose`, `cursor-agent`, `qwen`, `crush`, or another kind Herdr knows (`copilot`, `cursor`, `devin`, `cline`, `droid`, `kimi`, `kiro`, `grok`, `kilo`, `qodercli`, `letta`, `hermes`). Nothing at all goes into the pane of a live map, which runs as you and would take a typed `a` as your approval: the guard knows that pane from `.git/pulse/map-pane`, and while a map of yours runs it asks Herdr or tmux which processes the target pane runs (`ps`, one lookup per pane, four panes and 3 s at most); a pane it cannot resolve counts as a map, tmux takes only reads and input into an absolute `%N` pane, and no script types keys. It refuses `pulse map` typed into another terminal too. Everything else in Herdr stays open to agents: opening and splitting panes, running commands in them, starting Claude and Codex agents and prompting them, reading their output. A command the guard cannot take apart is denied when it names `pulse`, `gh`, `herdr`, `tmux`, `osascript`, or `git push`, and let through otherwise.

A heredoc body is data, a commit message or a pull request text through `cat` too, unless a shell, `eval`, `osascript`, or `tmux load-buffer` reads it, or `$(cat <<EOF ...)` hands it to a pane, a shell's `-c`, or `eval`. The pulse lever text rule reads every body. The quoted-text rule is strict on purpose: an agent that searches for the phrase, such as `grep -r "pulse approve" docs/`, is denied too. It can search for `pulse.approve` instead.

In Codex the guard works only after you trust the Pulse hooks (`/hooks` in the CLI, the Hooks page in the settings of the IDE extension); until then the command line and the Codex rules hold. No layer stops a script file, a program of the agent's own, or a token read out of `gh`: the layers stop a lever pulled in the open, not an agent that looks for a way around them. An interactive Pulse skill may execute an explicitly requested `pulse go` in its persistent foreground TTY, retaining all session markers. Runner agents and child sessions cannot start another runner. Starting one writes no approval and changes no auto switch.

## What others see

Your teammates see your work through the board and the pushed branches ([Where things live](./where-things-live#what-the-team-sees-and-when) lists what reaches them when). The [map](../guides/pulse-map) and `pulse status` draw it per item:

| The map says | What it means | What to do |
|---|---|---|
| `spec in progress by alice, 20 min` | Alice's BA or spec session registered the item as a draft and holds it | talk to her before you write about the same thing; `/pulse-ba` and `/pulse-re` show overlapping drafts before they write |
| `building, 4 min ago` | a teammate's `pulse go` run holds the item: the phase it runs and the age of its last sign of life | nothing; the item's files are held for everyone |
| `no sign of life for 2 h` | the `pulse go` run that holds the item has not reported for 30 minutes or more: it was stopped, or its machine is off the network | ask the holder |
| `no PR yet, held 2 h` | a teammate's session holds the item; nothing reports a session's progress, so the line shows how long it is held | ask the holder |
| `last run: <note>` | nobody holds the item; a `pulse go` run gave it back after a failure, a usage limit, or a stop, with a note that says why and which branch holds its work | claim it as usual and go on from that branch |

The phase and the sign of life come from `pulse go`, which reports each phase it starts (`planning`, `building`, `tests running`, and so on) and every 10 minutes while one runs. A session's claim keeps the time it was made, so its age never says whether the session still works. `pulse status <n>` prints the same as fields, the whole note included.

### Taking over

The work travels on the item branch: `pulse go` pushes it after every agent phase that committed, so whoever holds the item next starts from there. A free item with a `last run` note is claimed as usual; `pulse go` starts its worktree from the pushed branch on its own, and in a session `/pulse-build <n>` continues on that branch. An item someone still holds is freed first with the [handover commands](#claims-and-handover): `pulse release --take <n>` once the other person agreed, `pulse claim --take <n>` for a session of your own that ended. The new holder then continues on the branch the last one pushed.

What the last holder did not push stays in their clone; a phase that `pulse go` stopped halfway leaves its changes in that run's worktree. `pulse go` runs once per clone. Runs in other clones, your own or a teammate's, split the work through the claims.
