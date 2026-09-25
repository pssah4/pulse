---
title: Troubleshooting
description: Common problems when installing and running Pulse, and how to fix them.
---

# Troubleshooting

## Installation

### `/plugin isn't available in this environment` in VS Code

`/plugin` is the plugin panel of the Claude Code CLI. In the VS Code extension, type `/plugins` to open **Manage plugins**, or run the `claude plugin` commands in a terminal ([Installation](../tutorials/installation)). A plugin installed one way shows up in the other.

### `Host key verification failed` when adding the marketplace

Claude Code clones the short form `owner/repo` over SSH, and your machine does not trust GitHub's SSH host key yet. Use the HTTPS URL:

```bash
claude plugin marketplace add https://github.com/pssah4/pulse.git
```

### `claude: command not found`

Install the CLI (`curl -fsSL https://claude.ai/install.sh | bash`, or Homebrew), open a new shell, and check `claude --version`. The VS Code extension brings its own copy for its chat panel but puts no `claude` on your PATH.

### `pulse: command not found`

Run `pulse setup --cli` from the installed plugin (the command for your agent is in [Installation](../tutorials/installation)); in VS Code, run it in the integrated terminal. Then check that `~/.local/bin` is on your PATH: add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` (zsh) or to `~/.bash_profile` (bash; `~/.bashrc` on Linux) and open a new terminal. If `pulse` says "no installed Pulse found", the plugin is gone: install it again, or take the command out with `rm ~/.local/bin/pulse`. A terminal panel "Pulse map" that says `command not found: pulse` each time VS Code opens the folder comes from the task `/pulse-setup` wrote to `.vscode/tasks.json`: put the command on your PATH, or delete the task.

Installed from a clone ([Codex without the plugin](../tutorials/installation#codex-without-the-plugin)): `~/.local/bin/pulse` is a link into the clone, and `pulse setup --cli` keeps it and reports `kept: not written by pulse setup`. Check the link with `ls -l ~/.local/bin/pulse`, which must point to `~/.codex/pulse/bin/pulse`, and that `~/.local/bin` is on your PATH.

### The `/pulse` commands do not show up

1. `claude plugin list` in a terminal, or **Manage plugins** (`/plugins`) in the VS Code extension, shows `pulse@pssah4-skills`?
2. Start a new session; skills load at session start.
3. Still the old commands (`/dia-guide`, `/coding`)? The predecessor plugin is still installed: see [Coming from the Digital Innovation Agents plugin](../tutorials/installation#coming-from-the-digital-innovation-agents-plugin).

### An update does not arrive

Claude Code does not update the `pssah4-skills` marketplace on its own. Run `claude plugin marketplace update pssah4-skills`, then `claude plugin update pulse@pssah4-skills`, and restart. In Codex, `codex plugin marketplace upgrade pssah4-skills` and then `codex plugin add pulse@pssah4-skills` again, and restart Codex or start a new chat in the extension.

### Codex does not find the skills

With the plugin, in the CLI and the IDE extension alike: `codex plugin list` shows `pulse@pssah4-skills` (without the CLI, first run the `codex()` line from [Installation](../tutorials/installation#codex-cli-and-ide-extension), which runs the extension's newest binary), then restart Codex or start a new chat in the extension. Installed from a clone, the fallback without the plugin: `ls ~/.agents/skills/pulse` must list the skill folders. With both, every skill shows up twice: remove one. Codex names the skills `pulse:pulse-ba` and so on: type `$pulse:pulse-ba` for `/pulse-ba`, in the CLI and the IDE extension alike. The Codex CLI also lists them under `/skills` > **List skills**, or as soon as you type `$`, by the names `pulse-ba (pulse)` and so on; in the IDE extension, type `/` in the prompt box and pick one from the **Skills** group.

## Running Pulse

### `pulse` says "not inside a git repository" or names several remotes

Pulse needs to know which GitHub repository holds the item records. It takes, in this order, `repo` from `.pulse/config.toml`, the repository set with `gh repo set-default`, or the only GitHub remote. With several remotes it does not guess:

```bash
gh repo set-default owner/name
```

### `pulse setup` complains about `gh`

Pulse needs `gh` 2.94 or newer for parent links and "blocked by" links. Update it (`brew upgrade gh`, or see [cli.github.com](https://cli.github.com)) and run `gh auth status`.

### `pulse new` refuses: push the spec first

A record links a spec that every clone must be able to read, so `pulse new --spec` checks the file before it writes anything, and stops when the check fails (exit 2):

```text
pulse new: _devprocess/requirements/features/FEAT-01-02-login.md is not on origin as committed here; commit it, then: git push -u origin docs/12-login
```

Commit the spec, run the push the message names, and run the same `pulse new` again. A spec you changed after the push needs another commit and push. `write the spec first, <path> does not exist in the repository` means the path is wrong or the spec is not written yet. For work whose spec does not exist yet, register a draft instead: `pulse new <type> "<title>" --draft`.

### `pulse approve` refuses: merge the spec first

```text
#12 not approved: R1 spec missing on the base branch (origin/main); merge its spec there first
```

Agents plan from the spec as the base branch on origin has it, so an approval waits for that merge (rule R1). Merge the pull request that carries the spec, the one `/pulse-re` opened, then run `pulse approve <n>` again. The `a` key on the map refuses in the same way. `R1 issue: ... in the spec, item is #12` means the spec on the base branch names another item or none: commit the `issue:` line that `pulse new` wrote into the spec, push, and merge it as well. A draft has no spec yet and cannot be approved.

`pulse approve` also refuses while the spec of a feature, improvement, or fix on the base branch breaks one of R2 to R6 (an epic needs R1 only), and names the rule; the `a` key on the map does the same. Fix the spec with [`/pulse-re`](../guides/pulse-re), merge it, and approve again.

### The map does not start `pulse go`

Its footer says why, once. The map starts a run only while Pulse is on, `go_autostart` is not `false`, `PULSE_GO` is not `off`, the board answered, and no run of this clone lives. It holds back items the last run did not finish, and after a run you stopped or one that ended before its report it waits until `pulse go` runs by hand (`pulse go --detach`). It also waits while `.pulse/config.toml` differs from the one on origin's default branch, or on the base branch that one names: commit and merge the change, or start `pulse go` by hand. [/pulse-map](../guides/pulse-map#it-starts-pulse-go) has the rules.

### The map shows "no agent active" although an agent works

The lights come from the Pulse hooks, which record only when `mode = "on"` in `.pulse/config.toml`. Check the mode. A Codex session, in the CLI or the IDE extension, records only after you trusted the plugin's hooks, all of them, with `/hooks` in the CLI or one by one on the Hooks page of the extension's settings; a new chat picks them up. Until then `pulse claim`, `pulse new --draft`, and `pulse go` print `pulse: this Codex session reaches no Pulse hook` on the way; with [Codex without the plugin](../tutorials/installation#codex-without-the-plugin) there are no hooks to trust, so that line stays, and the rules come through `AGENTS.md`. Sessions without the hooks, such as Codex installed from a clone, get no light; the items they hold still show up. An agent that `pulse go` started counts as working while its phase runs, with or without hooks, and an agent silent for five minutes turns grey.

### `pulse map` prints one frame and ends

It does that without a terminal: in a pipe, a file, or an agent's shell tool. Run it in a terminal of its own; [/pulse-map](../guides/pulse-map#open-it-from-the-chat) says where for each chat. A working light that does not breathe is no fault: terminals with 16 colors show steady lights.

### The agent ignores the rules

Check `.pulse/config.toml`: `mode = "off"` silences every hook. In Claude Code, `claude plugin list` in a terminal, or **Manage plugins** (`/plugins`) in the VS Code extension, should show `pulse` as enabled. In Codex, the plugin's hooks bring the rules once you trusted them; Codex installed from a clone reads them from its global `AGENTS.md`, in `$CODEX_HOME` when you set it, else in `~/.codex` (see [Codex without the plugin](../tutorials/installation#codex-without-the-plugin)).

### `pulse check` reports findings

Each finding names the file, the line, and the rule (C1 to C10, or R1 to R6 for an approved item's spec, see [Commands](./commands#pulse-check)). Fix the document, or for a cap, add a `## Reasoned exception` section (the heading in any case). An epic's `## Items` list, which `pulse new` writes, does not count toward its cap.

A C10 finding names a spec whose file name lacks the ID of its place in the tree: it has none yet, it moved to another parent, or another branch took the same ID. `pulse number --apply` renames it, rewrites the paths to it, and moves its record along; commit the result. An open record keeps its old path until the rename is on the base branch: after the merge, run `pulse number --apply` once more.

An R finding is about the spec as the base branch on origin has it. A fix on your branch clears it only once it is merged, and until then the git hook refuses every commit, the fix commit included. The way out:

1. `pulse approve --undo <n>` takes the approval back. `pulse check` reads only the specs of approved items, so the git hook lets your commits through again, and no session or `pulse go` run claims the item meanwhile. Without the git hook, the approval can stay: skip this step and step 3.
2. Fix the spec on a branch, with [`/pulse-re`](../guides/pulse-re) or by hand, push it, and merge its pull request.
3. `pulse approve <n>` again. It reads the base branch on origin and refuses while the spec there still breaks one of R1 to R6.

To keep the approval, or if the hook still refuses the fix commit (the spec of another approved item may break a rule too), commit the fix once with `git commit --no-verify`. The hook reads origin as of your last fetch: after the merge, pull the base branch, and it lets commits through again.

### `pulse claim` says an item is held

Every claim leaves a mark on the issue that names the session holding it: a Claude Code session, a Codex thread, a `pulse go` run, or a terminal. Another session is refused, even under your login, so two agents never build the same item. The refusal names the holder, since when, and the command that frees the item:

```text
#12 is held by alice since 2026-09-24 09:12 UTC; to hand it over: pulse release 12 --take
```

- **Another person holds it:** agree with them first. `pulse release <n> --take` then hands the item over: their assignee and claim marks go, and a comment on the issue names who did it. Claim it as usual afterwards. An agent runs this only after you said yes.
- **Another session of yours holds it and has ended:** `pulse claim <n> --take` takes it over.

`release` and `done` refuse a claim that is not yours in the same way. `pulse done <n> --take` closes an item whoever holds it.

### The map says `spec in progress by <login>`

The item is a draft: a `/pulse-ba`, `/pulse-re`, or `/pulse-realign` session of that person registered it with `pulse new ... --draft` and holds it while it writes. A draft has no spec on the board yet, cannot be approved, and no agent builds it. Talk to that person before you write about the same topic. The draft ends when its spec is pushed and attached with `pulse new <type> "<title>" --spec <path> --issue <n>`. A draft that a session of your own held before it ended: `pulse claim <n> --take` in the new session.

### `pulse new --draft` says `is the draft ... already`

An open draft of the same type carries the same title, for example a realign (`Realign: <owner/repo>`) or a Project-BA that another session started. The line names its number and who holds it, and nothing new is created. A draft another person holds stays theirs: talk to them. One nobody holds, or one of yours, goes on with the same command plus `--issue <n>`; a session of your own that has ended hands it over with `pulse claim <n> --take`.

### The map says `no sign of life`

A teammate holds the item, and the session that holds it has not reported for 30 minutes or more. `pulse go` reports each phase it starts and every 10 minutes while one runs, an interactive session reports `working` at most every 10 minutes while it holds an item, and the skills run `pulse beat <n> <phase>`. Silence means the session ended, lost its network, or waits for its person. `pulse show <n>` prints `claimed_phase` and `claimed_beat`, the time of the last report in UTC.

Ask the holder. Once they agree, `pulse release <n> --take` hands the item over; claim it, then continue on the item branch they pushed (`pulse go` starts from it on its own, `/pulse-build <n>` continues on it). What they did not push stays on their machine.

### The ramp says `last run: ...`

A `pulse go` run gave the item back and left a note on it, or a session did with `pulse release <n> --note`: why it stopped (for a run a failure, a usage limit, or a stop) and which branch holds its work. The map shows the first line; `pulse show <n>` prints the whole note. Nobody holds the item, so claim it as usual. `pulse go` starts its worktree from the pushed item branch; in a session, `/pulse-build <n>` continues on that branch. Changes of a phase the run stopped halfway stay in that run's worktree, beside the repository of the machine that ran it.

### A command says "only a person does this"

`approve`, `approve-plan`, `rank`, `done`, and `release --take` refuse to run inside an agent that `pulse go` started (it carries `PULSE_HOLDER`). These decisions belong to a person: run the command in your own terminal or chat session.

### An item was approved by mistake

`pulse approve --undo <n>` takes the approval back. Until someone approves it again, no session and no `pulse go` run claims it.

### An agent of `pulse go` is refused a command

A headless agent cannot answer a permission prompt, so it runs only what its template allows. The built-in Claude template allows `verify` up to its first option or path and five git commands; the Codex template lets Codex write the shared git directory so it can commit. A template in `[agents]` copied from an older Pulse lacks both rights. See [Agent templates](./configuration#agent-templates) for what the rule covers and how to fix a template.

### `pulse go` leaves an item as failed

Its claim goes back to the ramp and its worktree stays for a look; the log is in `.git/pulse/go/<n>.log`. Fix the cause, then run `pulse go` again.

## Versions

`claude plugin list` and `codex plugin list` show the installed version; the [changelog](https://github.com/pssah4/pulse/blob/main/CHANGELOG.md) says what each version brought. After an update, restart the agent: a running Claude Code session keeps the version it started with, while the Codex update deletes the old version folder that a running Codex session still points at.

## Still stuck?

Open an issue on [GitHub](https://github.com/pssah4/pulse/issues) with your platform, `pulse --help` output, and what you tried.
