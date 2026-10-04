---
title: Upgrading Pulse
description: Move an older Pulse project to the current published-result workflow and final integration approval.
---

# Upgrading Pulse

The current workflow publishes specs, Plans and checked results on one item branch and integrates regular checked results automatically by default. Manual final approval is an explicit option. Update Pulse in each agent first ([Update](../tutorials/installation#update)), then work through this page once per project. The [changelog](https://github.com/pssah4/pulse/blob/main/CHANGELOG.md) lists every change. In Codex, type `$pulse:<name>` for `/<name>`.

## From 0.3.7 to 0.3.8

Update the plugin in Claude Code and Codex. Then check these points in each project:

- `pulse go` interprets your goal text again. If the interpretation fails, the goal pauses with its reason instead of working the whole queue; go on with `pulse go --resume` or change it with `--steer`. Item numbers such as `#580` in the text limit the run until the interpretation decides; `--item` and `--epic` always win over the text and over every steer.
- Headless agents of `pulse go` may now run every command of your `verify`. Put the checks your pre-push hook runs into `verify`, for example `npm run test:run && npm run typecheck && npm run lint`, so an agent can run them before a push; a hook refusal gets its own fix round.
- Pulse pushes its state branch `pulse-state` without your project's pre-push hooks (ADR-14); code branches always go through them. A failure that could not be pushed stays local and is sent again.
- The guard refuses an agent's `git commit`, `merge`, `rebase`, `cherry-pick`, `revert`, `am` and a `pull` of another branch on your base or default branch. Agents work on their item branch; your own terminal is not affected.
- The live map shows a run's sessions under their item with its branch, no longer counts headless agents as needing you, shows the item `pulse go` works on once, and keeps its text signet in a Herdr pane.

## From 0.3.6 to 0.3.7

Update the plugin in Claude Code and Codex. Nothing to change in a project. Two Pulse commands that use the local action outbox at once, such as two sessions claiming work, both go through.

## From 0.3.5 to 0.3.6

Update the plugin in Claude Code and Codex. Nothing to change in a project. `pulse go` no longer halts with "Probe cleanup failed" before planning, and `pulse new` and `pulse go` list a fix under an improvement in the improvement's own Items, where `pulse check` finds it.

## From 0.3.4 to 0.3.5

Update the plugin in Claude Code and Codex. Nothing to change in a project. On Linux, two hooks of a session that come due at once no longer both post a sign of life.

## From 0.3.3 to 0.3.4

Update the plugin in Claude Code and Codex. Nothing to change in a project. A Project-BA now works on `docs/<n>-<slug>` with its draft's number; an older one on an unnumbered docs branch goes on with `git switch -c docs/<n>-<slug>` from its head. `pulse new --spec` names an open record that already links the spec instead of opening a second one. A project with its own `spec_branch` pattern gets the push reminder too. In a terminal that confirms the Kitty graphics protocol the Map shows its signet as an image; everywhere else it keeps the text signet.

## From 0.3.2 to 0.3.3

Update the plugin in Claude Code and Codex and start new sessions; Codex asks for its normal review of changed hooks. Nothing to change in a project. `/pulse-go` (in Codex `$pulse:pulse-go`) starts and steers `pulse go` from the chat. A session that holds an item by hand leaves its sign of life as one `pulse:beat` comment on the item, so the Map and `pulse status` name holder, phase and age, and a stale item shows the next step.

Lever grants are new and off until you give one: in an attended Claude Code session, `pulse levers allow run`, `session` or `always` makes Claude Code ask you, and `l` on a session line in the Map grants or revokes. `pulse levers off` ends every grant. See [Let an attended session pull your levers](./pulse#let-an-attended-session-pull-your-levers).

## From 0.3.1 to 0.3.2

Update the plugin in Claude Code and Codex. Nothing to change in a project. A result whose item branch moved since its check is checked again on the new head, an idle `pulse go` names what it waits for, a push waits up to 30 minutes for the project's pre-push hook, and the Map's Herdr pane stays open unless you end the Map.

## From 0.3.0 to 0.3.1

Update the plugin in Claude Code and Codex and start new sessions: the Pulse rules a session gets now fit the context Claude Code passes on whole, and an attended Claude Code session can start `pulse go` from the chat again. Codex asks for its normal review of changed hooks.

`pulse go` now starts the workers of the session that starts it: claude workers from Claude Code, codex workers from Codex, those of `agent` from a terminal. A project that needs one kind of worker for every start, for example because it relies on the Codex sandbox, sets `workers = "fixed"` in `.pulse/config.toml`, or in the Map's settings (`s`).

A project hook that refuses a commit of `pulse go` now holds only its item. Earlier reports still show their old hook pause as an earlier event; the next run checks it again. The Map takes clicks and the mouse wheel and opens specs, Plans, decisions and check output in its reader.

## From 0.2.6 to 0.3.0

Update every participating clone's Claude Code and Codex plugin, refresh Codex rules with `pulse setup --codex-rules`, and start new agent sessions. Codex asks for its normal review of changed hooks. Keep existing item branches and worktrees; Pulse resumes retained work rather than replacing it.

This release removes the PR dependency and early spec and Plan approvals. Regular checked results integrate automatically by default. For a project that needs manual final approval, a person with repository write access selects `pulse auto merge off` before starting the runner. Old approval labels, auto switches and PR checks confer no current integration authority.

Run `pulse setup --check-plan` once per existing project to check the actual commit gates with a valid Plan. Resolve any compatibility or legacy-state finding shown by Pulse. Keep real Git hooks enabled. A repository rule that requires PRs on the target branch must be reconciled with the PR-free integration policy by its administrator; Pulse cannot bypass it.

The Map shows local actions as queued, syncing, confirmed, conflict or error. `pulse go` processes the queue; free text adds an objective, and explicit `only` / `nur` or `--epic` / `--item` selectors restrict its scope. Press `?` in the Map for the workflow and command guide.

## From 0.1.6 and older: command changes

| Gone | Use instead |
|---|---|
| `pulse done <n>` | `pulse go` closes what it merged; close a dropped item or a draft on GitHub |
| `pulse approve-plan <n>`, the label `pulse:plan-ok`, the map's `p` | a valid published Plan proceeds to the authorized build; `pulse approve <n>` now approves only a final result and base |
| the commands review and audit of `pulse`, and the review skill | `pulse go` and `/pulse-build` run review and audit themselves; `/pulse-audit` by hand for a chosen scope |
| `pulse show <n>` | `pulse status <n>` |
| `pulse rank`, the `Rank:` line | priority and dependencies order the ramp; the Map's `m` previews a shared manual order |
| `pulse block` | `pulse new --blocked-by`, or the link in GitHub |
| `pulse beat` | nothing: `pulse go` writes its own signs of life |
| `pulse arch` and the architecture map | the system map stays for navigation |
| `pulse go --detach`, `--agent`, `--cap`, `--json`, `--dry-run` | `pulse go` in a terminal or as an explicitly requested managed start without a TTY; `cap` and `agent` in `.pulse/config.toml`; `pulse status` shows what the next run takes |
| starting `pulse go` from the map (`g`, the autostart) | explicitly request `pulse go` in your terminal or through the Pulse skill |
| `pulse map --once`, `--demo`, `--color`, `--no-color` | `pulse status` prints one frame |
| `claim --files`, `release --note`, `release --drop-unpushed`, `approve --undo`, `approve --claim` | publish before ordinary release; use `pulse revoke <n>` to withdraw final approval |
| `pulse setup --parallel`, `--plan-approval`, `--git-hook` | `cap` for parallelism, `pulse check --plan` for structural validation and final approval after result verification |
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

8. **Plan compatibility.** Run `pulse setup --check-plan` before the planning handoff. Resolve findings in the tracked project validation without disabling real hooks.
9. **Legacy state.** Old approval labels, Plan comments, auto settings and PR state grant no final integration authority. Read and resolve any migration finding rather than manually editing Pulse's shared state.

## What behaves differently

- **One final approval policy.** Valid published specs and Plans proceed without early approval stops. After tests, review and audit, Pulse authorizes the exact result head and base automatically by default. A chosen manual policy waits for personal approval. Changed head or base requires revalidation and new approval.
- **Local actions first.** Approval, defer, resume, revoke and handoff are durably queued before network work. The Map shows queued, syncing, confirmed, conflict or error. Only confirmed shared approval authorizes integration; defer and revoke block locally while pending.
- **One check session.** Review and audit run in one fresh session, also for `risk: [security]`. One fix round addresses blocking findings. Failed work and evidence remain available for repair; `pulse resume <n>` requests a retry through the local outbox.
- **Choose manual approval when needed.** `pulse auto` shows the current policy. A person with repository write access can select manual approval with `pulse auto merge off`, or restore automatic approval with `pulse auto merge on`. Historical switches grant no authority. Agents cannot change this policy or operate a person's Map actions.
- **Explicit managed starts.** In a terminal `pulse go` remains in the foreground. Without a TTY it starts or reuses a Pulse-owned process and returns its receipt, report and log. It survives the caller and, under a manual policy, waits for confirmed final approval. `pulse go --stop` requests a controlled stop; nested runner agents remain refused.
- **Claims cover active work.** Published results and later retries stay visible without idle claims. Handoff requests stop and preserve the current writer, including across accounts. Unpublished work stays in its original worktree.
- **Claim continuity.** Separate `pulse claim` and `pulse release` processes in the same session and clone share a durable local acquisition receipt. Pulse saves it before publishing the claim and reuses it after a lost response. Registered worktrees share the receipt; another clone or a replacement claim does not. Legacy migration preserves file reservations and authenticates the original writer before transferring an own claim.
- **The Map and status.** They display progress and decisions. They start no backlog runner and close no item; the runner records completion after proven remote integration.

## Known limits

The current limits of the guard and spec tests are listed under [Known limits](../reference/troubleshooting#known-limits).
