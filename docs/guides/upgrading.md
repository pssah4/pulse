---
title: Upgrading from 0.1.6
description: What Pulse 0.2.0 removes, what to do once per project, and what behaves differently.
---

# Upgrading from 0.1.6

Pulse 0.2.0 has fewer commands, three gates a person opens, and `pulse go` doing the rest. Update Pulse in each agent first ([Update](../tutorials/installation#update)), then work through this page once per project. The [changelog](https://github.com/pssah4/pulse/blob/main/CHANGELOG.md) lists every change. In Codex, type `$pulse:<name>` for `/<name>`.

## What breaks

| Gone | Use instead |
|---|---|
| `pulse done <n>` | `pulse go` closes what it merged; close a dropped item or a draft on GitHub |
| `pulse approve-plan <n>`, the label `pulse:plan-ok`, the map's `p` | `pulse approve <n>`, or `a` in the map, at gate 2 |
| the commands review and audit of `pulse`, and the review skill | `pulse go` and `/pulse-build` run review and audit themselves; `/pulse-audit` by hand for a chosen scope |
| `pulse show <n>` | `pulse status <n>` |
| `pulse rank`, the `Rank:` line, the map's `m` | the priority labels `P0` to `P2` order the ramp |
| `pulse block` | `pulse new --blocked-by`, or the link in GitHub |
| `pulse beat` | nothing: `pulse go` writes its own signs of life |
| `pulse arch` and the architecture map | the system map stays for navigation |
| `pulse go --detach`, `--agent`, `--cap`, `--json`, `--dry-run` | `pulse go` in the foreground of your terminal; `cap` and `agent` in `.pulse/config.toml`; `pulse status` shows what the next run takes |
| starting `pulse go` from the map (`g`, the autostart) | `pulse go` in your own terminal |
| `pulse map --once`, `--demo`, `--color`, `--no-color` | `pulse status` prints one frame |
| `claim --files`, `release --note`, `release --drop-unpushed`, `approve --undo`, `approve --claim` | push first; remove the `pulse:approved` label on GitHub to take an approval back |
| `pulse setup --parallel`, `--plan-approval`, `--git-hook` | `cap` alone; every PLAN waits for a person; `pulse check` inside `verify` |
| the skills for `pulse go`, the map, and setup | `/pulse` explains setup, `pulse go`, and the map; the commands `pulse setup`, `pulse go`, and `pulse map` stay |
| the adapters for Cursor, OpenCode, and Gemini | Claude Code or Codex |

## Once per project

1. **Labels.** `pulse setup --labels` creates the new ones: `pulse:hold`, `pulse:failed`, `pulse:base`, `pulse:auto`, and `P0` to `P2`.
2. **The Pulse block.** `pulse setup --anchors` moves the block out of `CLAUDE.md` into `AGENTS.md` and leaves `CLAUDE.md` the line that imports it. Commit the change.
3. **Config on the base branch.** Add `[spec_tests]`, the runner of each spec test file, and `setup` if a fresh checkout needs one (`npm ci`, say), to `.pulse/config.toml`, and merge the change into the base branch. `pulse go` reads `verify`, `setup`, `[spec_tests]`, and `[agents]` only from the base branch as origin has it, and does not start without `[spec_tests]`. See [Configuration](../reference/configuration).
4. **Old keys.** `plan_approval`, `go_autostart`, `parallel`, and `map_autostart` switch nothing any more, and Pulse names the first two once as ignored. Remove them once every clone of the team runs the new release.
5. **Worktrees.** Item worktrees now live under `.worktrees/` in the repository. vitest, jest, and ESLint need `.worktrees/` in their ignore list; pytest and TypeScript skip it on their own.
6. **Codex.** Update Pulse in Codex, trust the hooks again with `/hooks` in the CLI (or **Trust** on the Hooks page of the IDE extension), and run `pulse setup --codex-rules` again. A Codex template of your own in `[agents]` must name `--sandbox workspace-write` and no profile, or `pulse go` stops before its first claim.
7. **Agents for localhost tests.** `pulse go` runs Codex without network. An item whose spec tests match a `[spec_tests]` pattern with `localhost = true` needs Claude: name it in `agent` (`claude:2,codex:2`, say), or the item waits with `needs a Claude agent (localhost spec tests)`.

## What behaves differently

- **Approve writes, go acts.** `pulse approve <n>`, or `a` in the map, writes the approval the item waits for and nothing else. `pulse go` acts on it: at gate 1 it merges the spec's docs PR and plans the item, at gate 2 it builds the approved PLAN, and at gate 3 it merges the ready pull request you gave a merge ok, then closes the issue. Every PLAN waits for a person.
- **One check session.** Review and audit run in one fresh session per item, also for `risk: [security]`, and an item gets one fix round for all its gates. A gate still red after it leaves the pull request a draft.
- **Auto mode starts off.** `pulse auto <gate> on`, or `1` `2` `3` in the map, lets your own `pulse go` pass a gate for your items. Nothing switches it on for you, and it still stops for a person on `risk:`, a protected path, and the other cases in [Auto mode](./pulse-go#auto-mode).
- **Levers stay with you.** The [Pulse guard](../concepts/parallel-work#levers-belong-to-a-person) refuses approvals, merges, `pulse go`, and `pulse auto` in every agent session, also after your yes: the agent names the command for your own terminal. `/pulse-build` opens its pull request as a draft, and you mark it ready.
- **`pulse go` runs in your terminal only.** It stays in the foreground, checks each new base commit before it builds on it, sets up each worktree with `setup`, and waits at gates 2 and 3 while nothing else runs; `q` ends it. Its agents get no GitHub token.
- **The map.** In Herdr it opens beside each chat by itself; in any other terminal, run `pulse map` in a second one. It starts nothing.
- **`pulse status` only reads.** It closes no merged item; `pulse go` does.

## Known limits

The current limits of the guard, auto mode, and the spec tests are listed under [Known limits](../reference/troubleshooting#known-limits).
