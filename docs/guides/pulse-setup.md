---
title: /pulse-setup
description: Activate, configure, or deactivate Pulse in a project.
---

# /pulse-setup

`/pulse-setup` (in Codex `$pulse:pulse-setup`) asks a few questions, one at a time, and runs `pulse setup`. It writes:

- **`.pulse/config.toml`**: the settings, see [Configuration](../reference/configuration).
- **An anchor block** in the agent files that exist (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, .github/copilot-instructions.md, .windsurfrules): a short pointer for agents without hook support, and the rule that an item's plan is its PLAN file, which a plan mode only shows. The project's own files win over the rules the hooks bring, so this rule stands in them. When a later Pulse changes the block, a new session has its agent run `pulse setup --anchors`, which rewrites only the block of each file that has one and changes nothing else; the change goes into the next commit. A block left by the predecessor plugin (Digital Innovation Agents) is replaced in place, never duplicated.
- **Seven GitHub labels** (`pulse:epic`, `pulse:feat`, `pulse:imp`, `pulse:fix`, `pulse:approved`, `pulse:plan-ok`, `pulse:draft`), only after you agree, because that writes to the repository.

On your yes it also adds:

- **A git hook** (`.git/hooks/pre-commit`): it refuses commits on `main`, `master`, `develop`, and `dev` (or the branches in `git config pulse.protected-branches`) and commits with `pulse check` findings. `git commit --no-verify` bypasses it once. A pre-commit hook of your own is kept as `pre-commit.bak`.
- **The `pulse` command** in `~/.local/bin`, once per machine, see [Installation](../tutorials/installation).
- **Codex rules** in `~/.codex/rules/pulse.rules` (`$CODEX_HOME/rules` when you set `CODEX_HOME`), in Codex: Codex runs `pulse` outside its sandbox without asking, and still asks before `approve`, `approve-plan`, `rank`, and `done`, before a handover with `release --take` or `claim --take`, and before `pulse -- <command>`. `pulse` takes `--take` only right after the command, where a rule sees it, so every other `claim` and `release` runs without asking. In Full access, where Codex never asks, it refuses these commands instead: run them in your own terminal, or switch Codex to a mode that asks. A rule matches a plain `pulse ...` command: a pipeline or a redirection, such as `pulse status --json | head`, runs inside the sandbox, where `.git` is read-only and GitHub is out of reach. The rules do not change with a Pulse update; when the changelog names a change to them, update Pulse in Codex too, then run `pulse setup --codex-rules` again. It writes no rules while Codex runs an older Pulse than the copy that writes them.
- **The task "Pulse map"** in `.vscode/tasks.json`, in VS Code: it starts the [live map](./pulse-map) in a terminal panel of its own each time the folder opens (`runOn: folderOpen`), and Terminal > Run Task > Pulse map starts it by hand. VS Code asks once whether the folder may run automatic tasks, and only in a trusted workspace. Other tasks in the file stay as they are. Claude Code protects `.vscode/`: it asks before it writes there, even in a mode that accepts edits (in auto mode its classifier decides): allow it, or add the task [by hand](#by-hand).

Commit `.pulse/config.toml` and the agent files it changed or created on a branch and merge it like any other change, so every clone of the team runs with the same settings; the git hook refuses commits on the base branch. Add `.vscode/tasks.json` to that commit only if the whole team has the `pulse` command and wants the map to start with the folder. After the merge, switch back to the base branch and pull (`git switch main && git pull`), so the next branch starts with the settings.

## Prerequisites

- A git repository with a GitHub remote. With several GitHub remotes, set `repo = "owner/name"` in the config or run `gh repo set-default`; Pulse never guesses.
- `gh` 2.94 or newer and `gh auth status` green. Older versions cannot set parents and "blocked by" links on the records.
- Python 3.9 or newer (the macOS system Python works).

## The questions

1. **Mode:** `on`, or `off` to keep the files but silence every hook.
2. **Parallel level:** `items` (every ready item with disjoint files runs at once), `max` (also parallel task waves inside an item; the hooks push idle ready work out), or `off`. At every level, a dependent stacks on its blocker's branch once the blocker's pull request is ready. See [Parallel work](../concepts/parallel-work).
3. **Slots (`cap`):** how many items run at once, 4 by default.
4. **Agent:** which headless agents `pulse go` starts, `claude`, `codex`, or both with their own slots (`claude:2,codex:2`).
5. **Test command (`verify`):** the one command that runs the project's tests, for example `npm test` or `python3 -m pytest -q`, detected from the project and confirmed by you. It is the tests gate of every feature; without one `pulse go` does not start: it stops before the first claim with exit 2 and asks for `pulse setup --verify "<command>"`. A new project without tests leaves it out: setup runs without `--verify` and writes no `verify`, and `pulse setup --verify "<command>"` adds it before the first `pulse go`. Never a command that always passes, such as `echo tests pass` or `true`: it would pass every tests gate.
6. **PLAN approval:** `auto` (default) builds a PLAN that nothing holds; a risk flag or `effort: L` in the spec, or `needs:` in the PLAN, still waits for you. `manual` makes every PLAN wait for `pulse approve-plan`.
7. **Base branch:** detected from the remote; confirm it. `pulse setup --dry-run` shows it as `base_branch` among the values it would write.
8. **Agent files:** which agent files get the anchor block, by default every one that exists (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, .github/copilot-instructions.md, .windsurfrules); `pulse setup --files` names them, and a file it names that does not exist yet is created.

## By hand

`pulse setup --dry-run` shows the files it would change and the values, base branch included. Then:

```bash
pulse setup --mode on --parallel items --cap 4 --agent claude --verify "npm test" --plan-approval auto --base-branch main
```

| Command | Does |
|---|---|
| `pulse setup --labels` | creates the labels on GitHub |
| `pulse setup --anchors` | rewrites only the Pulse block in the agent files that have one; config and labels stay |
| `pulse setup --git-hook` | writes the pre-commit hook: protected branches and `pulse check` |
| `pulse setup --mode off` | silences the hooks, the git hook included |
| `pulse setup --remove` | takes the anchor blocks and the git hook out again, and deletes an agent file that held only the block |

The task "Pulse map" has no flag. In VS Code, add it to `tasks` in `.vscode/tasks.json`; a new file gets `"version": "2.0.0"` and this task as the one entry of `tasks`:

```json
{"label": "Pulse map", "type": "shell", "command": "pulse map",
 "runOptions": {"runOn": "folderOpen"},
 "problemMatcher": [], "presentation": {"panel": "dedicated"}}
```

In Codex, the Pulse hooks run only once you trusted them: `/hooks` in the CLI (`t` trusts them all), or **Trust** on each hook on the Hooks page of the IDE extension's settings, then a new chat. Until then the session gets no rules, no light on the [map](./pulse-map), and no heartbeat on the board; `pulse claim` and `pulse new --draft` say so in one line. The setup report says whether they are trusted.

`--mode off` and `--remove` keep `.pulse/config.toml`, the labels, the local cache in `.git/pulse/`, and the task "Pulse map" in `.vscode/tasks.json`. [Take it out of a project](../tutorials/installation#take-it-out-of-a-project) says what to delete by hand, and when.

Moving a project from the predecessor plugin over is [`/pulse-realign`](./pulse-realign), not setup: it also turns the old backlog file into records on the board.
