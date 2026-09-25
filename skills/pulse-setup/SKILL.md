---
name: pulse-setup
description: >
  Activates, reconfigures, or deactivates Pulse in a project: writes
  .pulse/config.toml, the anchor block in agent files, and the GitHub
  labels Pulse uses. Use for "activate Pulse", "Pulse setup", "Pulse
  settings", "turn Pulse off", "change the number of parallel agents".
---

# Pulse setup

Everything deterministic runs through `pulse setup`; this skill asks the
questions and reports.

## 1. Check the ground

- Inside a git repository with a GitHub remote.
- `gh --version` at 2.94 or newer and `gh auth status` green. Work state
  lives in GitHub issues; older `gh` lacks parent, sub-issue, and blocker
  support. If it is older, name the upgrade (`brew upgrade gh` on macOS)
  and carry on: config and anchors work without it.

## 2. Ask, one question per turn

1. Mode: `on` (Recommended) or `off`. Off keeps the files but silences
   every hook.
2. How far to parallelize (`parallel`): `items` (Recommended: every ready
   item with disjoint files runs at once, and a dependent stacks on its
   blocker's branch once the blocker's PR is ready), `max` (also parallel
   task waves inside an item; the hooks push ready work out), or `off`
   (one thing at a time).
3. Parallel slots for `/pulse-go` (`cap`): 4 is the default. More slots
   finish the ramp sooner but raise merge and review load.
4. Which agents `pulse go` starts headless (`agent`): `claude`, `codex`,
   or both with their own slots, e.g. `claude:2,codex:2` (two
   subscriptions at once). The command templates live under `[agents]`.
5. The test command for the tests gate (`verify`): the one command that
   runs the project's tests, e.g. `npm test` or `python3 -m pytest -q`.
   Detect it from the project and confirm it. `pulse go` needs it:
   without one it stops before the first claim (exit 2) and says to set
   `verify` in `.pulse/config.toml`. A project without tests leaves
   `verify` empty: run setup without `--verify` and tell the person that
   `pulse go` starts once `pulse setup --verify "<command>"` sets a real
   test command. Never propose a command that always passes, such as
   `echo`, `true`, or `exit 0`: it would pass every tests gate.
6. PLAN approval (`plan_approval`): `auto` (Recommended: a PLAN nothing
   holds is built; a risk flag or effort L in the spec, or `needs:` in
   the PLAN, still waits for a person) or `manual` (every PLAN waits for
   `pulse approve-plan`).
7. Base branch: confirm the detected one (`pulse setup --dry-run` shows
   it as `base_branch` under `config`).
8. Agent files for the anchor block: by default every one that exists
   (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules,
   .github/copilot-instructions.md, .windsurfrules).

## 3. Write

```bash
# show what would change
pulse setup --dry-run
pulse setup --mode on --parallel items --cap 4 --agent claude --verify "<test command>" --plan-approval auto --base-branch <branch> [--files CLAUDE.md AGENTS.md]
```

A flag changes only what it names: without `--mode` the mode stays as it
is (`on` for a first setup).

Creating labels writes to the GitHub repository; ask first, then:

```bash
# pulse:epic, pulse:feat, pulse:imp, pulse:fix, pulse:approved, pulse:plan-ok, pulse:draft
pulse setup --labels
```

Offer the local git hook: it refuses commits on `main`, `master`,
`develop`, and `dev` (or those in `git config pulse.protected-branches`)
and commits with `pulse check` findings; `git commit --no-verify`
bypasses it once. `pulse check` reads the board on GitHub; when it cannot
(offline, no `gh` login) it reports `R1-R6 skipped: no board` and lets
the commit through. The hook runs `pulse` from PATH, else the plugin
that wrote it; with neither, it still refuses commits on those branches
and skips only `pulse check`, and says so. With `mode = "off"` it lets
every commit through. Only on a yes:

```bash
pulse setup --git-hook
```

Offer the `pulse` command for the terminal, once per machine: people run
`pulse status`, `approve`, and `go` there, and the git hook finds it on
PATH. Only on a yes:

```bash
# writes ~/.local/bin/pulse
pulse setup --cli
```

It is a short script that runs, at each call, the Pulse in `$PULSE_HOME`
when set, else the agent's own: in a Codex session the newest in the
Codex cache, in a Claude Code session the newest in the Claude Code
plugin cache, so neither agent needs the other. A terminal of its own
runs the newest of both. A plugin update needs no new setup.
When the report says `"on_path": false`, tell the person to add
`~/.local/bin` to PATH in their shell profile:
`export PATH="$HOME/.local/bin:$PATH"`. A status
`kept` means a `pulse` that setup did not write is in the way; name it
and leave it.

In Codex, also offer rules that let Codex run `pulse` without asking;
it still asks before `approve`, `approve-plan`, `rank`, and `done`,
which a person decides, and before every `release` and `claim`, because
a rule sees only how a command starts and cannot tell a handover with
`--take` from the rest. Only on a
yes, then restart Codex:

```bash
# writes pulse.rules in $CODEX_HOME/rules, by default ~/.codex/rules
pulse setup --codex-rules
```

Both write to the home directory, outside the project, which the Codex
sandbox blocks: ask the person to approve running them outside it.

In Codex, the Pulse hooks run only once the person trusted them: `/hooks`
in the CLI (`t` trusts them all), or Trust on each hook on the Hooks
page of the IDE extension's settings, then a new chat. Until then the session gets no rules, no
light on the map, and no heartbeat, and `pulse claim` and
`pulse new --draft` say so. Codex keeps the trust in
`$CODEX_HOME/config.toml` (by default `~/.codex/config.toml`) as tables
named `[hooks.state."pulse@...`; without one, ask the person to trust
the hooks. Never write those tables yourself: the trust is the
person's decision.

In VS Code (the Claude Code or Codex extension, or `TERM_PROGRAM` is
`vscode`), offer the task "Pulse map": it starts the live map by itself
in a terminal panel of its own each time the folder opens, and
Terminal > Run Task > Pulse map starts it by hand. There `pulse go`,
`pulse claim`, and `pulse new --draft` open no window and name this
task instead. The task runs `pulse` from PATH: without it, offer
`pulse setup --cli` first. Only on a yes, write it to
`.vscode/tasks.json`:

```json
{"label": "Pulse map", "type": "shell", "command": "pulse map",
 "runOptions": {"runOn": "folderOpen"},
 "problemMatcher": [], "presentation": {"panel": "dedicated"}}
```

- No `.vscode/tasks.json`: create it with `"version": "2.0.0"` and this
  task as the one entry of `tasks`.
- A `tasks.json` you can parse (JSON, comments allowed): add the task to
  `tasks`, or replace the one labelled "Pulse map", and leave every other
  task, setting, and comment as it is.
- A `tasks.json` you cannot parse, or one without a `tasks` list: leave
  it alone. Tell the person why and show them the task to add.

Tell the person that VS Code asks once whether this folder may run
automatic tasks, and only in a trusted workspace; the map starts with
the folder after they allow it (Tasks: Manage Automatic Tasks changes
the answer later).

Claude Code protects `.vscode/`: it asks before it writes there, even in a
mode that accepts edits (in auto mode its classifier decides). If the write is refused,
show the person the path and the task above, and carry on with the
report.

## 4. Report

Config path, anchor changes per file, `gh` status, labels created, git hook,
the terminal command, the map task, the Codex rules and whether the Codex
hooks are trusted, and the result of `pulse check`, which is clean right
after setup.

Then offer to commit `.pulse/config.toml` and the agent files setup
changed or created on a branch such as `chore/pulse-setup` and push
it, for a pull request into the base branch: a clone without the
config has Pulse switched off.
Never commit them on the base branch; the git hook, once written,
refuses that.

## Legacy DIA projects

Pulse reads `.dia/config.toml` as a fallback, so `mode = "off"` stays off.
The anchor block replaces an old DIA block in place, never twice. Moving
the old BACKLOG.md into issues is `/pulse-realign`, not this skill.

## Deactivate

`pulse setup --mode off` silences the hooks, the git hook included.
`pulse setup --remove` takes the anchor blocks out of the agent files
and the git hook out of `.git/hooks`, and puts back a hook of the
person's own that setup kept as `pre-commit.bak`. It deletes an agent
file that held only the anchor block; offer to commit the changed and
deleted agent files. Neither touches
the task "Pulse map" in `.vscode/tasks.json`: when Pulse leaves the
project, offer to delete it, or VS Code runs `pulse map` each time the
folder opens, and after an uninstall that says `command not found: pulse`.
`pulse setup --remove --cli --codex-rules` takes the terminal command
and the Codex rules off this machine, for every project on it.
