---
title: Configuration
description: Every setting in .pulse/config.toml.
---

# Configuration

`pulse setup` writes `.pulse/config.toml`. Hand edits are welcome; `pulse setup` changes only the keys it sets and leaves the rest of the file alone.

```toml
mode = "on"                 # on | off
cap = 4                     # agents pulse go runs at once, in every phase and across all agents
agent = "claude"            # which [agents] templates pulse go starts, e.g. "claude:2,codex:2"
workers = "session"         # session: Claude Code starts claude, Codex codex, a terminal agent | fixed: always agent
worker_permissions = "person"   # person: Claude workers run in your permission mode with your rules | narrow: Pulse's list
item_flow = "goal"          # goal: a Claude worker gets each item as one /goal session | phases: plan, build, fix apart
agent_timeout = 60          # minutes before a hung agent is stopped
base_branch = "main"
verify = "npm test"         # pulse go needs it: the tests gate after the build
setup = "npm ci"            # pulse go runs it in each item worktree it makes
setup_timeout = 20          # minutes for one setup
# repo = "owner/name"       # only when the repo has several GitHub remotes
# parallel, map_autostart, go_autostart, plan_approval: gone; an older file keeps them, and Pulse reads past them

[spec_tests]                # pulse go needs it: the runner of each spec test file, {files} filled in
"tests/**/test_*.py" = { run = "python3 -m pytest {files}" }
"e2e/**/*.spec.ts" = { run = "npx playwright test {files}", localhost = true }

[agents]                    # optional; these are the built-in templates, see below
claude = "claude -p --allowedTools {allow} --output-format json --permission-mode {mode} --settings {settings} {prompt}"
codex = "codex exec --json --sandbox workspace-write --add-dir {gitdir} {prompt}"

[audit.supply_chain]        # read by /pulse-audit
build_command = "npm run build"
artifacts = ["dist/app.js"]
```

| Key | Default | Meaning |
|---|---|---|
| `mode` | none (not active) | `on` injects the rules at a session start and in each subagent, and runs the stop check; `off` silences every hook but keeps the files |
| `cap` | `4` | agents `pulse go` runs at once for you, see [Parallel work](../concepts/parallel-work); a teammate's work takes none of your slots |
| `agent` | `claude` | the headless agents `pulse go` starts from a terminal, or from anywhere with `workers = "fixed"`; several as `claude:2,codex:2`, where a number caps that agent and a bare name gets `cap`, while `cap` counts all of them together, see [pulse go](../guides/pulse-go#two-agents-at-once) |
| `workers` | `session` | who picks the workers of a run. `session`: a start from Claude Code runs `claude` workers, a start from Codex `codex` workers, each with all slots, and a terminal start runs `agent`; an empty template for that harness in `[agents]` falls back to `agent`. `fixed`: every start runs `agent`. Another value warns and counts as `session`, see [pulse go](../guides/pulse-go#which-workers-a-run-starts) |
| `worker_permissions` | `person` | the rights of a Claude worker of `pulse go`. `person`: your permission mode (`auto` when your Claude Code settings set `permissions.defaultMode = "auto"`, else `acceptEdits`), your local rules, subagents, and the Pulse guard as a hook; `narrow`: Pulse's list of `verify`, the spec test runners, git, and `pulse check` in `acceptEdits`. Another value warns and counts as `narrow`, see [Agent templates](#agent-templates) |
| `item_flow` | `goal` | how `pulse go` hands an item to a worker. `goal`: a worker whose program is `claude` gets the whole item as one `/goal` session (plan, spec tests, build, `verify`, reference, `Pulse-Task` per task, at most 20 turns), and each fix round as a new goal; Codex, which offers `/goal` only in its terminal UI, builds in phases. `phases`: separate plan, build and fix sessions for every worker. Pulse's own gates decide either way. Another value warns and counts as `phases`, see [pulse go](../guides/pulse-go#what-a-run-does) |
| `agent_timeout` | `60` | minutes per phase, `verify` included; a phase that runs longer is stopped with its child processes. A plan or build that timed out gives its claim back; stopped work is preserved for recovery, and [the chain after the build](../concepts/verification-gates#the-chain-after-the-build) says what a timeout means for each step |
| `base_branch` | origin's default branch, else `main` | the shared base from which item branches start and into which approved results integrate |
| `spec_branch` | `docs/{n}-{slug}` | legacy spec-branch lookup for existing projects. New work reserves a draft number first and keeps spec, Plan and implementation on `<type>/<n>-<slug>`; it needs no separate docs branch or PR |

| `verify` | none | the command that runs the project's tests. `pulse go` needs it and does not start without it: it runs it in the tests gate, the first of the three gates on every feature branch, after the built result. The [base check](../guides/pulse-go#the-base-check) fetches the current base without running this command; CI status does not gate the workflow. It also sets what a Claude agent may run, see [Agent templates](#agent-templates). `pulse setup --verify "<cmd>"` sets it |
| `setup` | none | the command that makes a fresh checkout ready for the tests, such as `npm ci`. `pulse go` runs it itself, outside every agent sandbox, in each worktree it makes, again after a lockfile in it changed (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`), so its agents find their dependencies installed. A setup that fails in an item's worktree fails the item with `pulse:failed` |
| `setup_timeout` | `20` | minutes for one `setup`; one that runs longer is stopped with its child processes and counts as failed |
| `repo` | from `gh repo set-default`, else the single GitHub remote | the GitHub repository that holds the board |
| `ids_since` | none | a commit from which the project numbers its specs anew, for example a new major version on the history of the old one: `pulse number` then counts only the IDs in file names after that commit, on branches and in worktrees that contain it, see [File names and IDs](./artifacts#file-names-and-ids) |
| `[spec_tests]` | none | which runner runs a spec test file: a glob pattern (`*` and `?` within a directory, `**/` any number of them) to `run`, a command whose `{files}` becomes the frozen files it matches, each quoted by `pulse go`, so `{files}` stands bare in `run`, never inside quotes (a name that starts with `-` comes as `./<name>`), and `localhost = true` for a runner that needs a server on localhost: an item whose wave-1 spec test matches such a pattern is built by no agent whose program is `codex`, since a Codex worker may run without network: Claude builds it, or an agent of your own. The first pattern a file matches counts. `pulse go` does not start without the section. It runs the runners at the commit that froze the spec tests, where they must fail (the RED check), and in the tests gate, one runner at a time per machine under `~/.cache/pulse/spec-tests.lock` and with `CI=1`, so parallel items never share a port. P6 of a Plan asks for a pattern for every spec test file of wave 1. A frozen file no pattern matches (a helper) runs with none |
| `[agents]` | the built-in templates above | how `pulse go` starts a headless agent, see [Agent templates](#agent-templates) |
| `stack`, `reachability_check` | none | per-stack reachability tooling for `/pulse-build`, see [Reachability by stack](./reachability-by-stack) |

**What runs a program counts as merged.** `pulse go` takes `setup`, `setup_timeout`, `verify`, `protected`, `worker_permissions`, `item_flow`, `[spec_tests]`, and `[agents]` from `.pulse/config.toml` on the base branch as origin has it, never from your working tree, which a checked-out branch or an agent may have changed: a change to them counts once it is merged and pushed. A run refuses to start when `base_branch` in your working tree names another base than the file there, and, where Python has `tomllib`, when that file is no valid TOML; without `tomllib` (Python 3.9 and 3.10), when a line of it is one the built-in reader does not understand (a multi-line string or array, `[[...]]`, a dotted key) or names a key or a table twice. The other keys come from the working tree.

Pulse ignores top-level keys it does not know, such as one an older version wrote. Before Python 3.11, or when the file is not valid TOML, Pulse reads it line by line and skips a line of the top level or of `[agents]` that it does not understand, with a warning that names the line. A project without `.pulse/config.toml` reads `.dia/config.toml`, the settings file of the predecessor plugin (Digital Innovation Agents), so a project that switched that plugin off stays silent until it migrates.

Final integration approval is required for every concrete result head and base. `pulse auto` reports that policy; historical plan/build/merge switches grant no authority. A valid published spec proceeds to planning and a valid published Plan to the authorized build, subject to dependencies, active file claims and base checks. Risk flags stay visible for review without adding an early approval stop.

Before publication, `pulse check --plan <path>` checks P1 to P6 together against the current local base, without fetching or running a test suite. Under `pulse go`, agents run targeted checks and additional Plan checks outside `verify`; the supervisor runs the full command once after the build, then repeats it only after a relevant change.

## Agent templates

`pulse go` starts one agent without a chat window per item, from a template in `[agents]` named by `agent`. A template is a command line: `{prompt}` becomes the instructions, and Pulse fills in the other placeholders.

Whatever the template and your own settings say, `pulse go` limits two programs itself, by the program the template runs, not by its name in `[agents]`: the first word that is no option, no `VAR=value`, and not `env` or `npx`, by its base name without `.exe` (`npx -y @openai/codex` runs `codex`). `codex` gets the network and the review of approvals you set for your own Codex sessions, right after that word: `-c sandbox_workspace_write.network_access=true` only where the top level of `$CODEX_HOME/config.toml` (by default `~/.codex/config.toml`) sets `network_access = true` under `[sandbox_workspace_write]`, else `false`, so no command it runs reaches the network; an `approval_policy` you set there goes along as `-c` too, and `approvals_reviewer` and `sandbox_workspace_write.writable_roots` always do, with your value or Codex's default (`user`, none): Codex reads `.codex/config.toml` from a worktree of a trusted repository, and a branch could widen the review or the sandbox there. Nothing you did not set explicitly, no profile (Codex keeps those in `<name>.config.toml`, chosen by `--profile`, which `pulse go` never passes), and `pulse go` reads these once when a run starts. With `approvals_reviewer = "auto_review"`, Codex's own automatic review can approve an escalation that then runs outside the sandbox, exactly as in your own Codex session; `pulse go` follows your setting and never sets it itself. Its template must name the workspace sandbox (`--sandbox workspace-write`, `-s workspace-write`, or `--full-auto`), and may name nothing that could open the sandbox or its network: `danger-full-access`, `--dangerously-bypass-approvals-and-sandbox`, `--yolo`, a setting with `network_access` or `sandbox_mode`, or a profile (`-p`, `--profile`), which `$CODEX_HOME/config.toml` (by default `~/.codex/config.toml`) fills; otherwise `pulse go` stops before it claims anything. `claude` gets `--disallowedTools Bash(gh:*)` right after its word. That list takes the words up to the next option, so in a template of your own an option must follow the program, as `-p` does. Another program gets neither. No agent process gets `GH_TOKEN` or `GITHUB_TOKEN`, and `GH_CONFIG_DIR` points at an empty folder under `.git/pulse/`, so `gh` in an agent finds no login: agents never touch GitHub, `pulse go` does.

- **`{allow}`** (Claude Code) lists what the agent may run without asking, since nobody is there to answer: each command of `verify` up to its first option, path, or number (a chain such as `npm test && npm run typecheck` gives a rule for each), `git add`, `git commit`, `git status`, `git diff`, `git log`, `pulse check`, which only reads, and the `run` of each pattern in `[spec_tests]`, cut the same way and before `{files}` (`npx playwright test {files}` gives `Bash(npx playwright test:*)`). A command of `verify` or a runner whose rule would end at a shell or an interpreter (`node --test` cut to `node`, `python3 scripts/check.py` cut to `python3`), names `env`, `gh`, or `pulse`, or is `git` without a subcommand joins no list, since it would run any code or reach past the item: the agent is refused it, and the tests gate still runs it. Name a script (`scripts/check.sh`) or a package command instead. For the planning, build, and fix phases of an item, a command under the `verify:` of its Plan runs only when the config on the base names it too, cut the same way: `verify` and the runners are on the list already, and a command of `setup` joins it unless it downloads, installs, or runs any code (`npx`, `pip install`, `env`, `sudo`, a shell or interpreter). The item log and the result name each line left out, and the tests gate still runs `verify`. A check your hooks run before a push, such as a typecheck or a lint, belongs in `verify`: then the agents can run it, and the tests gate checks what the push checks. The review and audit sessions of `pulse go` get the list from `verify` alone, plus `git -C tree diff`, `log`, `show`, and `status`: they start beside their checkout `tree/`, and a headless Claude refuses `cd tree && git ...` in one command. Its edits go through; a command outside the list is refused unless your permission mode or your own permission rules allow it. `python3 -m pytest -q` gives `Bash(python3 -m pytest:*)`, `npm test` gives `Bash(npm test:*)`, `go test ./...` gives `Bash(go test:*)`. `--allowedTools` takes every word up to the next option, so in a template of your own an option must follow `{allow}`.
- **`{mode}`** and **`{settings}`** (Claude Code) give a worker the rights you give your own sessions in the project. With `worker_permissions = "person"`, the default, `{mode}` is `auto` when `permissions.defaultMode` is `auto` in your Claude Code settings, read in Claude Code's order from `.claude/settings.local.json` of your clone, `.claude/settings.json` on the base branch as origin has it, and `settings.json` in `$CLAUDE_CONFIG_DIR` or `~/.claude`; any other mode gives `acceptEdits`, since a worker edits its worktree. `bypassPermissions` holds where your user settings set it, never from a project's or a local file, as in Claude Code: such a worker asks nothing and has no classifier, and the Pulse guard is its only fence. The guard stops a lever a worker pulls in the open, in a command; a script the worker writes and runs, or settings it edits, may get past it. Choose `auto` or `narrow` where that is too much. `{settings}` carries the `allow`, `ask`, and `deny` rules of your `.claude/settings.local.json`, which a worktree does not have, the Pulse guard as a hook, and `disableAllHooks: false`, which outranks your own and the project's settings, so a worker can never pull your levers (merge or push to the base, approvals, takeovers), whatever plugins it loads. Your user and project rules Claude Code reads itself. `{allow}` adds `Agent`, `Read`, `Grep`, and `Glob`: a worker starts subagents and reads as an attended session does. When your organization's managed settings set `allowManagedHooksOnly` or `disableAllHooks`, the guard cannot hold, and every worker starts narrow and fenced. Pulse reads your settings once when a run starts, so no worker widens the ones after it. Every agent of a run, review and audit sessions included, carries the clone in `PULSE_CLONE`, and the guard of a worker reads the project from there, whatever mode its own folder or worktree names. A phase whose worktree holds a `.claude/settings.json` that differs from the base, or a `.claude/settings.local.json`, starts narrow too, reads your user settings only (`--setting-sources user`), none of the worktree's, and runs the Pulse guard as its own hook; the item's notes say so. A worker never starts another agent past its permission checks or sandbox (`--dangerously-skip-permissions`, `bypassPermissions`, `--yolo`): the guard denies it. With `worker_permissions = "narrow"` (another value warns and counts as `narrow`), `{mode}` is `acceptEdits`, `{settings}` is empty, and `{allow}` holds Pulse's list alone, as before. A call a worker's mode does not allow without asking is refused, since nobody answers a worker, and the run report names it with its tool and input under the item's notes.
- **`{gitdir}`** (Codex) is the git directory all worktrees share. The Codex sandbox keeps it read-only, so without `--add-dir {gitdir}` Codex cannot commit in its worktree. With it, Codex could also change the shared `config` and `hooks`, and a hook it left would later run outside every sandbox. So after every agent phase `pulse go` compares the whole git config the worktree reads, except `branch.*`, the shared `info/attributes`, the hooks, in the shared `hooks` folder and where `core.hooksPath` points for the worktree (husky: `.husky/_` in it), and the files that tie the worktree to the git directory with their state before the phase. If a phase changed one, the item stops there: nothing is pushed, nothing is thrown away, no further phase runs, the claim stays, and the run names what changed. A person looks and decides. Settings under `branch.*`, such as the merge base VS Code notes per branch, stop nothing; any other change to the config does, since `gpg.program`, `credential.helper`, or a remote's URL can run a program as you. The gates' evidence and the kept verdicts are not in the git directory, see [what `pulse go` keeps outside it](#what-pulse-go-keeps-outside-the-git-directory).

::: warning Templates from an older Pulse
A template in `[agents]` replaces the built-in one of the same name. A line copied from an older Pulse lacks `--allowedTools {allow}`, `--permission-mode {mode} --settings {settings}`, or `--add-dir {gitdir}`, and its agents lose these rights: Claude is refused the tests and git unless your own permission rules allow them, runs in the mode the line names without the guard as a hook of its own, and Codex cannot commit. Delete such lines, or add the placeholders as in the templates above.
:::

## Signs of life

The claim of a `pulse go` run carries the phase it runs and the time of its last sign of life, so every clone's map can tell running work from silent work ([what the team sees](../concepts/where-things-live#what-the-team-sees-and-when)). Nothing needs configuring:

- **`pulse go`** writes the phase and the time on the item's claim at every phase start (`plan`, `build`, `spec tests`, `tests`, `review`, `audit`, `fix`), and every 10 minutes while a phase runs.

After 30 minutes without a sign of life, a teammate's map shows `no sign of life`. Nothing renews the time on a session's claim: the map shows how long it is held (`held 2 h`).

## Shared workflow state

The remote `pulse-state` branch carries canonical claims, holds, results, final approvals and the integration reservation. Its updates compare the observed revision; stale actions conflict rather than overwriting newer work. Issue metadata identifies and describes the item. A local outbox entry becomes shared authority only after confirmation. Do not edit this state by hand.

Pulse pushes an update that changes only `pulse-state` without the project's pre-push hooks: they judge a branch's code, and this branch carries only Pulse's state. A push that also carries an item branch, such as the publication of a result, always runs them, and agents never skip a hook. When origin does not take the failure of an item, this clone's outbox keeps it and sends it again, also at the start of the next `pulse go` run. Until the board has it, the map shows the item as failed and "not on the board yet".

## What lives in the git directory

The shared git directory (the same for every worktree) holds Pulse's local state, never committed:

| File | Holds |
|---|---|
| `.git/pulse/issues.json` | the local copy of the item records: checked for changes every two seconds (free while nothing moved), reloaded on a change or every 30 seconds |
| `.git/pulse/fetched` | when this clone last fetched every branch from origin (the file's time); Pulse fetches at most once every 30 seconds, whichever command asks (`pulse status`, `pulse go`, the map, and others); `pulse claim`, `pulse number --apply`, and `pulse new --spec` check the published source before authorizing their update. After a fetch that failed it holds `offline` and what git said, which `pulse status`, also for one item, prints until the next fetch |
| `.git/pulse/me` | your GitHub login |
| `.git/pulse/map.pid` | one line per live map of this clone, its process id; a map adds its line as it starts and removes it as it ends, and the file goes with the last map. No further map of this clone opens by itself while one of them lives |
| `.git/pulse/map.command` | the script a map that Pulse opened runs; for 15 seconds after Pulse writes it, that map counts as starting and no second one opens |
| `.git/pulse/go/<n>.log` | the log of each item `pulse go` ran, one section per phase |
| `.git/pulse/go/report.json` | the unique run ID, managed/foreground mode, PID, start/end, results, current runner `activity`, and evaluated `base` state, written before preparation calls and after every event; the map and `pulse status` read them |
| `.git/pulse/go/base.log` | base-check diagnostics; startup does not run `setup` or `verify` on the base |
| `.git/pulse/usage.jsonl` | one line per agent phase of `pulse go`: agent, model, tokens, cost, seconds |
| `.git/pulse/go.pid` | set while `pulse go` runs |

## What `pulse go` keeps outside the git directory

A Codex agent of `pulse go` can write the shared git directory (`--add-dir {gitdir}`), so what decides whether a gate passed lives elsewhere: in `$XDG_CACHE_HOME/pulse/<clone>/`, by default `~/.cache/pulse/<clone>/`, where `<clone>` is 16 hex characters of the hash of the git directory's path. `pulse go` writes there outside the agent sandbox. Files an agent leaves under `.git/pulse/` in their old places count for nothing, and those from before this version are no longer read.

Keep the cache outside the workspace, Git directory and agent write paths. The action outbox checks ownership, permissions and path components and rejects unsafe locations. Its stop requests and pending actions are protected with that storage. Other evidence still depends on the configured sandbox boundary; a custom cache path is not a substitute for it.

| File | Holds |
|---|---|
| `gates/<sha>` | what each gate of `pulse go` said at this commit. Local evidence beside the commit statuses `pulse/tests`, `pulse/review`, and `pulse/audit`, which anyone with write access to the repository can set. Final integration checks this evidence independently of externally writable statuses. A base commit with the tree of a commit whose tests gate passed here is green without a run, the tree read from that commit |
| `reviews/<n>.md`, `audits/<n>.md` | the review and audit verdict kept for an item's published result, stamped with the commit it looked at |
| `base.json` | this clone's evaluated base SHA, current CI and saved evidence, state, and bounded diagnostics; older saved results remain readable |
| `audit-context.json` | the last audit that counted: its date, commit, and manifests |
| `actions/outbox.sqlite` | durable local intents and synchronization receipts, including queued, syncing, confirmed, conflict and error |
| `actions/runner-<run-id>.log`, `actions/runner-stop-<run-id>` | managed process output and a stop request bound to one run |
| `compatibility/` | isolated Plan-commit probe logs and temporary checkout; successful evidence is bound to base and configuration |

The Claude Code template runs without a sandbox: its agent can run the tests it wrote and `git diff --output=<file>`, and so can write any file you can, this folder too. Where that matters, let `pulse go` run Codex.
