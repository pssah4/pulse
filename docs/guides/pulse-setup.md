---
title: pulse setup
description: Activate, configure, or deactivate Pulse in a project.
---

# pulse setup

`pulse setup` switches Pulse on in a project. In a chat, `/pulse` (in Codex `$pulse:pulse`) asks you the questions below, one at a time, and runs it with your answers. It writes:

- **`.pulse/config.toml`**: the settings, see [Configuration](../reference/configuration).
- **An anchor block** in AGENTS.md, which Codex and Claude Code read, and in .github/copilot-instructions.md where it exists: a short pointer for agents without hook support, and the rule that the repository Plan file is the item's only plan, also in plan mode. The project's own files win over the rules the hooks bring, so this rule stands in them. A CLAUDE.md gets no block of its own but the line `@AGENTS.md <!-- pulse -->`, unless it imports AGENTS.md already: Claude Code reads AGENTS.md by itself only where no CLAUDE.md is, and the import brings the block in with every setting. Setup creates AGENTS.md next to a CLAUDE.md, and never creates a CLAUDE.md. Where CLAUDE.md and AGENTS.md are one file, linked either way, that file carries the block once. When a later Pulse changes the block, a new session has its agent run `pulse setup --anchors`, which rewrites only the block of each file that has one and changes nothing else, except that a block an older Pulse wrote into CLAUDE.md moves to AGENTS.md; the change goes into the next commit. A block left by the predecessor plugin (Digital Innovation Agents) is replaced in place, never duplicated.
- **The task "Pulse map"** in `.vscode/tasks.json`, outside Herdr: it starts the [live map](./pulse-map) in a terminal panel of its own each time VS Code opens the folder (`runOn: folderOpen`), and Terminal > Run Task > Pulse map starts it by hand. VS Code asks once whether the folder may run automatic tasks, and only in a trusted workspace. Other tasks in the file stay as they are, and a file with comments or trailing commas stays untouched: the report (`vscode_task`) then carries the task to add [by hand](#by-hand). In Herdr the map opens beside each chat by itself, so setup writes no task there. In both, the report names the lines for a key in Herdr's `config.toml` that opens the map (`herdr_key`); setup never writes them.
- **GitHub labels**, when requested, identify item types, priorities, drafts, holds and failures. Historical approval and auto labels may remain for compatibility; they authorize no integration. `pulse:base` identifies a repair for a red base. Final approval belongs to the reviewed result at its exact head and base, in Pulse's shared state. Setup never grants it.

On your yes it also adds:

- **The `pulse` command** in `~/.local/bin`, once per machine, see [Installation](../tutorials/installation).
- **Codex rules** in `~/.codex/rules/pulse.rules` (`$CODEX_HOME/rules` when you set `CODEX_HOME`), in Codex: Codex runs `pulse` outside its sandbox without asking. In every mode, Full access included, Codex refuses the levers of a person ("blocked by policy"): `approve`, `revoke`, lifecycle actions and a handover with `release --take` or `claim --take`, `pulse -- <command>`, `gh pr merge` and `gh pr ready`, and `gh issue edit`, `close`, and `reopen`: run them in your own terminal. A prefix rule sees only how a command starts, so `gh -R o/r pr merge 5`, `env gh pr merge 5`, or a full path pass it; the [Pulse guard](../concepts/parallel-work#levers-belong-to-a-person) catches those once you trust the Pulse hooks. `pulse` takes `--take` only right after the command, where a rule sees it, so every other `claim` and `release` runs without asking. A rule matches a plain `pulse ...` command: a pipeline or a redirection, such as `pulse status --json | head`, runs inside the sandbox, where `.git` is read-only and GitHub is out of reach. The rules do not change with a Pulse update; when the changelog names a change to them, update Pulse in Codex too, then run `pulse setup --codex-rules` again. It writes no rules while Codex runs an older Pulse than the copy that writes them.

Commit `.pulse/config.toml` and the agent files it changed or created on a branch and merge it like any other change, so every clone of the team runs with the same settings. Add `.vscode/tasks.json` to that commit only if the whole team has the `pulse` command and wants the map to start with the folder. After the merge, switch back to the base branch and pull (`git switch main && git pull`), so the next branch starts with the settings.

Setup writes neither `[spec_tests]` nor `setup`. `pulse go` needs `[spec_tests]`, the runner of each spec test file, and runs `setup` (`npm ci`, say) in each worktree it makes: add both to `.pulse/config.toml` by hand ([Configuration](../reference/configuration)) and commit them with the rest. `pulse go` reads them, `verify`, and `[agents]` only from the base branch as origin has it, so a change counts once it is merged.

## Check Plan compatibility

After configuring the project and before planning, run:

```bash
pulse setup --check-plan
```

The probe uses the fetched base and its actual setup and commit gates in an isolated checkout. Its valid Plan names future implementation and test files without creating them. It reports `compatible`, `incompatible` or `unchecked`, the base SHA, the failing step when relevant, and the log. It claims no item, publishes nothing and grants no approval. Matching successful evidence can be reused; changed hooks, settings or base require a fresh check.

Fix an incompatible validation rule in the tracked project settings. Keep real hooks enabled, including inherited hooks; never point `core.hooksPath` at an empty directory, set hook-skipping environment variables or use `--no-verify` to make the probe green. Missing dependencies, a timeout or an unsafe external hook setup mean compatibility is unproven. Both realign modes perform this check before handing work to planning.

## Prerequisites

- A Git repository with a GitHub remote. With several remotes, set `repo = "owner/name"` or run `gh repo set-default`; Pulse never guesses.
- `gh` 2.94 or newer and a working login with the needed repository permissions.
- Python 3.9 or newer.
- A shared remote supporting atomic publication of the base and Pulse state for integration. A refused push remains blocked; Pulse does not fall back to an unsafe update.

## The questions

1. **Mode:** `on`, or `off` to keep the files but silence every hook.
2. **Slots (`cap`):** how many agents `pulse go` runs at once, 4 by default. See [Parallel work](../concepts/parallel-work).
3. **Agent:** which headless agents `pulse go` starts, `claude`, `codex`, or both with their own slots (`claude:2,codex:2`).
4. **Test command (`verify`):** the one command that runs the project's tests, for example `npm test` or `python3 -m pytest -q`, detected from the project and confirmed by you. It is the tests gate of every feature; without one `pulse go` does not start: it stops before the first claim with exit 2 and asks for `pulse setup --verify "<command>"`. A new project without tests leaves it out: setup runs without `--verify` and writes no `verify`, and `pulse setup --verify "<command>"` adds it before the first `pulse go`. Never a command that always passes, such as `echo tests pass` or `true`: it would pass every tests gate.
5. **Base branch:** detected from the remote; confirm it. `pulse setup --dry-run` shows it as `base_branch` among the values it would write.
6. **Agent files:** which agent files setup writes, by default every one that exists (CLAUDE.md, AGENTS.md, .github/copilot-instructions.md), with AGENTS.md for the block a CLAUDE.md imports; `pulse setup --files` names them, and a file it names that does not exist yet is created.

## By hand

`pulse setup --dry-run` shows the files it would change and the values, base branch included. Then:

```bash
pulse setup --mode on --cap 4 --agent claude --verify "npm test" --base-branch main
```

| Command | Does |
|---|---|
| `pulse setup --labels` | creates the labels on GitHub |
| `pulse setup --check-plan` | check a valid Plan-only commit with future files against the fetched base's setup and real project hooks; report compatibility and a log without publishing or claiming work |
| `pulse setup --anchors` | rewrites only the Pulse block in the agent files that have one, and moves a block an older Pulse wrote into CLAUDE.md to AGENTS.md, leaving CLAUDE.md the line that imports it; config and labels stay |
| `pulse setup --mode off` | silences the hooks |
| `pulse setup --remove` | takes the anchor blocks out again (also from CLAUDE.md, GEMINI.md, .cursorrules, and .windsurfrules, where an older Pulse wrote them), the `@AGENTS.md <!-- pulse -->` line from CLAUDE.md (a line of your own stays), and a git hook an older Pulse installed, and deletes an agent file that held only the block |

The task "Pulse map" has no flag. Where setup kept your `.vscode/tasks.json`, add it to `tasks` there; a new file gets `"version": "2.0.0"` and this task as the one entry of `tasks`. Claude Code protects `.vscode/`: it asks before its agent writes there, even in a mode that accepts edits (in auto mode its classifier decides): allow it, or add the task yourself.

```json
{"label": "Pulse map", "type": "shell", "command": "pulse map",
 "runOptions": {"runOn": "folderOpen"},
 "problemMatcher": [], "presentation": {"panel": "dedicated"}}
```

In Codex, the Pulse hooks run only once you trusted them: `/hooks` in the CLI (`t` trusts them all), or **Trust** on each hook on the Hooks page of the IDE extension's settings, then a new chat. Until then the session gets no rules and no stop check. The setup report says whether they are trusted.

`--mode off` and `--remove` keep `.pulse/config.toml`, the labels, the local cache in `.git/pulse/`, and the task "Pulse map" in `.vscode/tasks.json`. [Take it out of a project](../tutorials/installation#take-it-out-of-a-project) says what to delete by hand, and when.

Moving a project from the predecessor plugin over is [`/pulse-realign`](./pulse-realign), not setup: it also turns the old backlog file into records on the board.
