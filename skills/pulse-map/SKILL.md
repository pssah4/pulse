---
name: pulse-map
description: >
  Starts the live Pulse map: who works on what (person, branch, feature)
  with a status light per agent, the board, and the ramp of
  ready work. Use for /pulse-map, "show the map", "who is working on what",
  "what is everyone doing", "open the dashboard".
---

# Pulse map

`pulse map` is the live map in a terminal of its own: it redraws every
two seconds and takes keys, none with Shift, and its last line lists the
keys of the level it is on. On the map `↑` `↓` (or `j` `k`) pick an item,
`Enter` opens it, `?` shows the help, `q` quits. In the item view (goal,
stage, holder with phase and last sign of life, blockers, PR, PLAN) `a`
approves it, `p` approves its PLAN (both show what they bind first,
`Enter` confirms), `o` opens its spec in a window while the map runs on
(`PULSE_EDITOR`, else VS Code or Cursor, else the system's app, else the
path), and `m` moves it on the ramp (arrows, `Enter` places it). `Esc`,
`←`, or Backspace go back one level and never end the map. `a` refuses
what `pulse approve` refuses: a spec that is not on `origin/<base>` (R1)
and, for a feature, improvement, or fix, one there that breaks R2 to R6;
an epic needs R1 only.
`pulse map --demo` plays a time-lapse of a sample project without a
repository.

## Open it

Run `pulse map --ensure` and pass on the one line it prints. It opens
the live map where the person works, unless a map of this clone runs or
is starting, in the places listed below: a tmux pane beside the chat or
a new terminal window (say that `q` closes it). In VS Code it opens
nothing; its line names the task "Pulse map" (Terminal > Run Task)
where the project has it, else that `/pulse-setup` adds it, and the
command for the terminal panel.
In Codex, run it outside the sandbox, which cannot open a terminal: the
Codex rules of `/pulse-setup` allow that, otherwise ask the person to
approve it. When it prints nothing, the map is switched off
(`map_autostart = false`, `PULSE_MAP=off`): ask the person to run
`pulse map` in a terminal of their own.

Never run `pulse map` without `--ensure` in your shell tool, which has
no terminal, and never paste a frame in its place: it is stale the
moment it prints. And no browser.

## When it opens by itself

`pulse go` as it starts, `pulse claim`, and `pulse new --draft` open the
map as `pulse map --ensure` does. Each says in one line what it did:

- inside tmux: a pane beside the chat;
- in a terminal on macOS: a new window of Terminal, or of iTerm when
  the command runs in iTerm;
- on Linux with a display: a window of the first terminal emulator
  found (`x-terminal-emulator`, `gnome-terminal`, `konsole`, `xterm`);
- in VS Code (Claude Code or Codex): nothing opens.
  The task "Pulse map" that `/pulse-setup` adds starts the map in a
  terminal panel of its own when the folder opens; the line names the
  command and, where the project has it, the task;
- anywhere else: the line names the command for a terminal of its own.

The agents `pulse go` starts never open one. `map_autostart = false` in
`.pulse/config.toml` turns it off for the project, `PULSE_MAP=off` in
the environment for one shell.

## It starts pulse go

Each time the live map reads the board and finds approved work (an item
that starts next, or an approved item nobody holds that needs a PLAN)
while no run of this clone lives, it starts `pulse go` apart from itself
and names the items and the log in its footer once. A run ends when the
ramp is empty; the next approval starts one again, at most once a
minute. It starts nothing, and names why, for an item the last run did
not finish (failed, usage limit, stopped, claim refused), after a run a
person stopped or one that ended before its report (until
`pulse go` runs by hand), when `.pulse/config.toml` differs from the one
on origin's default branch or the base it names (a checked-out branch never runs its
own commands), and without `verify`. `go_autostart = false` turns it
off for the project, `PULSE_GO=off` for one shell.

## Reading it

- **Lights:** green breathes = working, yellow = waits for you (a question,
  a permission prompt, or a teammate's pull request asking for your
  review), red = the last test or build failed, or a pull request's checks
  fail, grey = idle. Nothing blinks. The worst light rolls up to the
  feature and the person; the header counts all lights.
- **Board:** ready to start, in progress, in review, blocked, not ready yet
  (drafts count here);
  then each open epic with its children closed as completed, of those
  and its open children (`1 of 14 done`); one closed as not planned
  counts in neither.
- **Who is doing what:** me with busy slots and working agents in total;
  one line per feature I hold, with the step of its chain while `pulse
  go` runs it (`planning`, `building`, `RED check running`, `tests
  running`, `review running`, `audit running`, `fix round`) or
  its pull request (draft with a red gate, waits for merge), and `on #n`
  when it is stacked; below it what its agent does right now (the one
  that needs me or failed first). An agent outside any feature gets a
  line with its branch. Each teammate gets one line per item they hold,
  lit from GitHub (needs your review, checks failing, otherwise grey);
  without a pull request the line says `<phase>, <age> ago` from their
  last sign of life, `no sign of life for <age>` after 30 minutes, or
  `merged, closes on the next pulse status` when the pull request merged
  into a branch other than the default one. A draft stands under its
  holder, me or a teammate, with its ramp words:
  `spec in progress by <login>, <age>`, the age of its last sign of life,
  else of the claim.
- **Next:** one line per kind of thing that waits for a person, the most
  urgent first, with the step that moves it; items that wait for an open
  blocker are left out. For a draft it is `spec in progress` with
  `<login> writes the spec of #n`.
- **Ramp:** every open item nobody holds and every draft, in the team's
  order, each with what it waits for (not approved, spec or plan rule, plan waits for
  you, waits for #n with `+n` for more than fit, locked by a file,
  queued, `spec in progress by <login>, <age>` for a draft); `last run: <why>`
  follows when a run of `pulse go`, or a session with `pulse release
  <n> --note`, gave the item back. `starts next`
  takes a free slot, the busy ones stand on my row above. The order
  changes with `m` in the item view of `pulse map` or with
  `pulse rank <n> --before <m>`; only a person decides it, an agent moves
  nothing unless asked.

Live agent detail comes from this machine's sessions. Teammates appear
through the board: what they hold, and their pull requests.

## When it shows nothing

- "command not found": `pulse` is not on the terminal's PATH;
  `pulse setup --cli` puts it there, once per machine.
- "no repo" or an error line: `pulse setup`, or set `repo` in
  `.pulse/config.toml` when the repo has several GitHub remotes.
- "no agent active" while an agent works: Pulse is not active here
  (`/pulse-setup`), or the session records nothing: Codex records once
  its plugin's hooks are trusted (`/hooks` in the CLI, or the Hooks page of the
  IDE extension).
