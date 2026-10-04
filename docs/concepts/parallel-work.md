---
title: Parallel work
description: How Pulse coordinates work across developers and machines using dependencies, planned files, and shared claims, and where those safeguards end.
---

# Parallel work

Several people can run Claude Code and Codex in their own clones of the same repository. Each person's `pulse go` starts agents locally and uses the shared board to select work alongside the team's other items. The scheduler checks dependencies and planned files before starting a build.

`/pulse-ba` and `/pulse-re` register drafts during scoping, so the team can see work before implementation starts. The same board carries that work through planning, build, verification and integration. [Where things live](./where-things-live#what-the-team-sees-and-when) explains what becomes visible at each step.

## What the scheduler checks

1. **Blockers first.** An item is built only when every item that blocks it is done: its result has reached the shared base. Planning does not wait for blockers. The records on the board hold these links ("blocked by"), and the ramp reads them.
2. **Disjoint planned files.** The scheduler selects concurrent builds only when their Plans declare different files. Every Plan lists its files at the top; the ramp compares them with the exact files reserved by active claims.

The second rule holds back work with overlapping planned files. It needs a Plan: an item without one waits at `needs a plan` until it has one, planned in `/pulse-re`, by `/pulse-build`, or by `pulse go`.

## Coordination boundaries

The scheduler compares the files declared in the Plan with shared claim records. An edit outside that list, a dependency missing from the spec, or work done outside Pulse can still cause a conflict. Keep Plans current and review the resulting changes.

Shared Git revisions serialize competing claims. A stale update cannot replace a newer holder; the runner checks ownership again before publishing its results. These checks coordinate participating Pulse processes, while unplanned or external edits remain outside those reservations.

Each clone runs its own agents. The Map combines shared ownership, phases, planned files and heartbeats. Detailed tool activity and unpushed edits stay local. Moving a claim to another machine does not transfer those local edits. Follow [Claims and handover](#claims-and-handover) before continuing someone else's item.

## The ramp

Every open item nobody works on lines up like pallets at a loading dock, in order, and agents pick up ready work from the front. The ramp is the ordered backlog: each item appears once, with what it waits for.

- **Order:** no item before an open blocker; among the rest, the best `P0` to `P2` label of the item and of everything it unblocks, then the lower number. So a `P2` item that blocks a `P0` item comes before a `P1` item.
- **What each line waits for:** a missing publication, `spec: <rule>`, `needs a plan`, `plan: <rule>`, final result approval, `waits for #n`, `locked: <file> in use by #n`, then `queued` and `starts next`. `pulse go` plans what needs a plan and builds from the top.
- **Slots:** `cap` in `.pulse/config.toml` sets how many items run at once for you. Your own running items take slots; a teammate's running item takes none of yours, but its files are held for everyone. When Alice works on #12, Sebastian keeps all four of his slots, and the files of #12 stay off limits for his agents until Alice is done.
- **Locked:** a ready item whose files another running item holds waits, and the ramp names the file and the holder: `#18 ui: settings panel   locked: token.ts in use by #11`. `pulse claim` refuses such an item with the same file and holder, so a build started by hand waits too.
- **Reservations:** an actual claim reserves its files before the writer starts. A merely queued row or a result waiting for approval holds no files. A dependency or later retry does not justify retaining an idle claim.

- **Waits:** an item with an open blocker waits until the blocker is done: `#13 ui: token banner   waits for #11`.

`pulse status` prints it once; the [map](../guides/pulse-map) draws it live.

## Planning so that more can run at once

Manual order is shared by the map and the runner. Use `m`, arrows, then Enter on an unclaimed work item in the map. Open dependencies always come first. New items without a manual position follow the manually ordered part using the normal priority rules. Claims and dependencies that change during a move invalidate its preview. Esc cancels without writing. Epics can be selected to read, but are not movable work items. Old `Rank:` body lines stay ignored; there is no `pulse rank` command.

- **Contract first.** If item B needs item A only for an interface (a type, an endpoint signature, a schema), that interface becomes its own small item that blocks B. A's implementation no longer blocks B, and B starts as soon as the contract is merged. Nothing builds on a blocker's branch.
- **Waves.** Inside a Plan, tasks carry a wave number. Tasks of one wave touch disjoint files and do not need each other's output; the wave's checks pass before the next wave starts. `pulse check` keeps the files of a wave disjoint.

## Merging parallel results

Every item has one branch, `<type>/<n>-<slug>`, from spec through Plan and implementation. Tests, review and security audit establish result evidence; the latter two share one fresh session. One fix round addresses blocking findings. Pulse publishes the result and releases inactive claims. Checked results integrate automatically by default; a chosen manual policy waits for personal approval of exact head and base.

Integration is serialized across clones. Pulse reserves the shared slot, checks current approval, remote commits and evidence, then performs a regular merge and normal fast-forward push with project hooks. The shared state and base publication are atomic: a concurrent withdrawal or changed state prevents publication. If the base moved, the result needs revalidation and new approval. A successful remote integration followed by interrupted closure is resumed without merging twice.

Disjoint files reduce conflicts; they do not make an approval valid for a different base. Dependencies integrate in order. The [base check](../guides/pulse-go#the-base-check) fetches the current base without a full startup suite. CI status grants no start or integration authority; Pulse verifies the completed result.

## Who starts the agents

[`pulse go`](../guides/pulse-go) prepares published specs, builds valid Plans and verifies their results. It uses one worktree per item under `.worktrees/`, reuses retained work, and fills free agent slots according to configuration. The [Map](../guides/pulse-map) shows preparation, active phases, findings and final approval waits. An explicit start without a TTY uses Pulse's managed process, which survives its caller and can wait for confirmed approval under a manual policy. `pulse go --stop` requests a controlled stop. Agent permissions and source markers remain intact.

One `pulse go` run can drive Claude Code and Codex together, each with its own slots, and hands an item on when one of them hits its usage limit.

## Claims and handover

A claim belongs to a session and generation: a Claude Code session, Codex thread, runner or terminal. Shared revisions serialize competing claims; a stale update cannot take over a newer holder. Only the files actually claimed are reserved. The Map shows the holder and current reported phase.

- **Hand off a claim:** a person with repository write access requests `pulse release --take <n>` in their own terminal, including across accounts. Pulse asks the writer to stop and preserve work before releasing ownership. An unreachable writer remains pending until its stop and preserved work can be established safely.
- **Take over an ended session of your own:** use the person-only `pulse claim --take <n>` recovery path and inspect the named retained work before proceeding.
- **Withdraw final approval:** use `pulse revoke <n>` or the Map. The local block applies immediately; its status shows when shared state confirms it. Removing a historical label changes no canonical approval.

Ordinary `pulse release <n>` releases only your claim after safe publication. Never remove dirty or unpublished work to make it succeed. A later owner continues the published branch or the original retained worktree. Waiting results and failed work stay visible without an idle claim. A runner agent remains limited to the item in `PULSE_ITEM`.

## Levers belong to a person

Manual final integration approval, policy changes, revocation, lifecycle decisions and claim handoff belong to a person. Agents never pull these levers, and three layers stop an agent that pulls one in the open:

- **The command line.** `pulse approve`, `revoke`, lifecycle actions, `claim --take`, and `release --take` refuse to run when an agent marker is set (`PULSE_HOLDER`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, `CODEX_THREAD_ID`) or stdin is not a terminal, and so do `setup --remove` and `setup --mode off`, which would switch the guard off. Run them in your own terminal, or use the map.
- **The Pulse guard.** A hook checks every shell, Monitor, and MCP call of a Claude Code or Codex session and its subagents before it runs, and denies it with "Gate levers belong to a person or to their own auto switch". It acts in a session whose working directory lies in a project where Pulse is on, or whose project Claude Code names in `CLAUDE_PROJECT_DIR`: it reads that project's `.pulse/config.toml`, and a session outside such a project has no guard. It reads through `env`, `command`, full paths, the program name in any case, the `-c` of `bash`, `sh`, `zsh`, `dash`, `ksh`, and `fish` (with any options before it), `pwsh -Command`, a shell that reads its commands from stdin, `$(...)` and backticks outside single quotes, `$'...'`, line continuations, comments, redirections, chains with `;`, `&&`, `||`, `|`, and `-R` or `--repo` anywhere.
- **The Codex rules.** With `pulse setup --codex-rules`, Codex refuses the same levers in every mode ("blocked by policy"). A prefix rule sees only how a command starts, so `gh -R o/r pr merge 5`, `env gh pr merge 5`, or a full path pass it; there the guard holds.

The guard denies:

- `pulse approve`, `auto` with `on` or `off` (`pulse auto build on`, `pulse auto --for 8h merge on`), `claim --take`, `release --take`, `setup --remove`, and `setup --mode off`, also as quoted text anywhere in the command
- `gh pr merge`, `gh pr ready`, `gh pr review --approve`, and `gh pr create` without `--draft`
- `gh issue close`, `reopen`, `edit`, `pin`, `unpin`, `delete`, `transfer`, and `lock`; `gh label create`, `edit`, and `delete`; `gh repo edit`; `gh issue create` with a `pulse:` label or the title "Pulse auto mode"
- a `gh` command that writes while its line holds `<!-- pulse:`, `Plan-ok`, `plan ok at`, or `merge ok at`, also in a heredoc, a here-string, or a pipe; a comment, issue, or pull request whose `--body-file` holds one, is no regular file the guard can read (the first 64 KB), or is named twice in the line; a body from stdin that no heredoc, here-string, `echo`, or `printf` of the line feeds; and `$(...)` or backticks in `--body` or `--body-file`
- `gh api` with a method other than GET, or with `-f`, `-F`, `--field`, `--raw-field`, or `--input`; `gh auth token` and `gh auth status --show-token`
- `git push` with `--force`, `-f`, `--force-with-lease`, `--mirror`, `--no-verify`, `-n` (also as a start git takes, such as `--force-w`), a `+` refspec, or a refspec with `*`, or onto the base or default branch; `git commit` with `--no-verify` or `-n`; and `git commit`, `merge`, `cherry-pick`, `revert`, `am`, `rebase`, and a `pull` of another branch while the working directory is on the base or default branch, judged after the chain's `cd`, `pushd`, `-C`, `checkout`, or `switch`, and denied where the guard cannot tell the branch. Aborting, a detached HEAD, and catching up with the branch's own origin branch stay open, and the reason points to the item branch. A push that names no branch, or `HEAD` or `@`, or one the push computes (`"$(git branch --show-current)"`), counts the branch the chain pushes from: after its last `cd` or `pushd`, or the branch a `checkout` or `switch` names. Where the guard cannot tell (another repository through `GIT_DIR` or `--git-dir`, a directory it cannot name, a checkout of a file, git that does not answer) it denies the push; so does a commit or push with `-c core.hooksPath`
- a command that unsets or blanks an agent marker (`unset CODEX_THREAD_ID`, `env -u CLAUDE_CODE_SESSION_ID`, `env -i`, `CLAUDE_CODE_SESSION_ID=`), since the command line would then take the agent for you
- `claude` with `--bare`, or with `--settings` that switch every hook off (`"disableAllHooks"` set) or the Pulse plugin (`enabledPlugins` with a `pulse@` key set false), as JSON in the command or in the file it names; a settings value that is neither JSON nor a regular file the guard can read (a fifo, a variable it cannot expand), or a file the command also names elsewhere, since it may write that file first; and `opencode run`: each starts an agent without the guard
- a change to `.pulse/config.toml` or its directory by shell, also through `./`, `..`, a symlink, a glob in a word that names `.pulse/`, or after `cd .pulse`: `rm`, `truncate`, `ex`, `ed`, `sed -i`, and `perl -i` at all; and `tee`, `>`, or `>>` that leaves `mode` other than `on`. The guard judges only the words of the writing command and its heredoc or here-string: a `mode = ...` (quoted key too) with another value, or a whole new file without `mode`, is denied, and so is content that comes through a pipe or from a file (`<`). `cp` or `mv` over the file, content a program reads from a file of its own, and an edit through the agent's own file tools pass
- the GitHub tools of an MCP server, except those that read (`get`, `list`, `search`, `..._read`); a `command` or `cmd` of any MCP tool is checked as a command

Text that goes into another terminal gets the same check: `herdr pane run`, `send-text`, and `send-keys`, `herdr agent prompt`, `tmux send-keys`, `new-window`, `split-window`, `new-session`, `run-shell`, `respawn-pane`, `respawn-window`, and `display-popup`, and `osascript`, with `-e` or fed by a heredoc. A pane that an agent opens has no agent marker and a terminal, so a command typed there would count as yours. For the same reason the guard lets no agent without it start in a pane: `herdr agent start` with a kind other than `claude` or `codex`, `claude --bare`, and text for another terminal that starts `opencode`, `gemini`, `pi`, `aider`, `amp`, `goose`, `cursor-agent`, `qwen`, `crush`, or another kind Herdr knows (`copilot`, `cursor`, `devin`, `cline`, `droid`, `kimi`, `kiro`, `grok`, `kilo`, `qodercli`, `letta`, `hermes`). Nothing at all goes into the pane of a live map, which runs as you and would take a typed `a` as your approval: the guard knows that pane from `.git/pulse/map-pane`, and while a map of yours runs it asks Herdr or tmux which processes the target pane runs (`ps`, one lookup per pane, four panes and 3 s at most); a pane it cannot resolve counts as a map, tmux takes only reads and input into an absolute `%N` pane, and no script types keys. It refuses `pulse map` typed into another terminal too. Everything else in Herdr stays open to agents: opening and splitting panes, running commands in them, starting Claude and Codex agents and prompting them, reading their output. A command the guard cannot take apart is denied when it names `pulse`, `gh`, `herdr`, `tmux`, `osascript`, or `git push`, and let through otherwise.

A heredoc body is data, a commit message or a pull request text through `cat` too, unless a shell, `eval`, `osascript`, or `tmux load-buffer` reads it, or `$(cat <<EOF ...)` hands it to a pane, a shell's `-c`, or `eval`. The pulse lever text rule reads every body. The quoted-text rule is strict on purpose: an agent that searches for the phrase, such as `grep -r "pulse approve" docs/`, is denied too. It can search for `pulse.approve` instead.

In Codex the guard works only after you trust the Pulse hooks (`/hooks` in the CLI, the Hooks page in the settings of the IDE extension); until then the command line and the Codex rules hold. No layer stops a script file, a program of the agent's own, or a token read out of `gh`: the layers stop a lever pulled in the open, not an agent that looks for a way around them. An interactive Pulse skill may execute an explicitly requested `pulse go`, retaining all session markers. Without a TTY Pulse owns a managed process; with one the runner stays in the foreground. Runner agents and child sessions cannot start another runner. Starting one writes no approval and changes no auto switch.

## What others see

Your teammates see your work through the board and the pushed branches ([Where things live](./where-things-live#what-the-team-sees-and-when) lists what reaches them when). The [map](../guides/pulse-map) and `pulse status` draw it per item:

| The map says | What it means | What to do |
|---|---|---|
| `spec in progress by alice, 20 min` | Alice's BA or spec session registered the item as a draft and holds it | talk to her before you write about the same thing; `/pulse-ba` and `/pulse-re` show overlapping drafts before they write |
| `building, 4 min ago` | a teammate's `pulse go` run holds the item: the phase it runs and the age of its last sign of life | nothing; the item's files are held for everyone |
| `no sign of life for 2 h` | the `pulse go` run that holds the item has not reported for 30 minutes or more: it was stopped, or its machine is off the network | ask the holder |
| `held 2 h` | a teammate's session holds the item; nothing reports a session's progress, so the line shows how long it is held | ask the holder |
| `last run: <note>` | nobody holds the item; a `pulse go` run gave it back after a failure, a usage limit, or a stop, with a note that says why and which branch holds its work | claim it as usual and go on from that branch |

The phase and the sign of life come from `pulse go`, which reports each phase it starts (`planning`, `building`, `tests running`, and so on) and every 10 minutes while one runs. A session's claim keeps the time it was made, so its age never says whether the session still works. `pulse status <n>` prints the same as fields, the whole note included.

### Taking over

The work travels on the item branch: `pulse go` pushes it after every agent phase that committed, so whoever holds the item next starts from there. A free item with a `last run` note is claimed as usual; `pulse go` starts its worktree from the pushed branch on its own, and in a session `/pulse-build <n>` continues on that branch. An item someone still holds is freed first with the [handover commands](#claims-and-handover): `pulse release --take <n>` requests a safe handoff, and `pulse claim --take <n>` recovers an ended session of your own. Continue only after ownership is confirmed, using its published branch or recorded retained worktree.

What the last holder did not push stays in their clone; a phase that `pulse go` stopped halfway leaves its changes in that run's worktree. `pulse go` runs once per clone. Runs in other clones, your own or a teammate's, split the work through the claims.
