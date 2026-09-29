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
agent_timeout = 60          # minutes before a hung agent is stopped
base_branch = "main"
verify = "npm test"         # pulse go needs it: the tests gate, the base check
setup = "npm ci"            # pulse go runs it in each worktree it makes and in the base check
setup_timeout = 20          # minutes for one setup
# repo = "owner/name"       # only when the repo has several GitHub remotes
# parallel, map_autostart, go_autostart, plan_approval: gone; an older file keeps them, and Pulse reads past them

[spec_tests]                # pulse go needs it: the runner of each spec test file, {files} filled in
"tests/**/test_*.py" = { run = "python3 -m pytest {files}" }
"e2e/**/*.spec.ts" = { run = "npx playwright test {files}", localhost = true }

[agents]                    # optional; these are the built-in templates, see below
claude = "claude -p --allowedTools {allow} --output-format json --permission-mode acceptEdits {prompt}"
codex = "codex exec --json --sandbox workspace-write --add-dir {gitdir} {prompt}"

[audit.supply_chain]        # read by /pulse-audit
build_command = "npm run build"
artifacts = ["dist/app.js"]
```

| Key | Default | Meaning |
|---|---|---|
| `mode` | none (not active) | `on` injects the rules at a session start and in each subagent, and runs the stop check; `off` silences every hook but keeps the files |
| `cap` | `4` | agents `pulse go` runs at once for you, see [Parallel work](../concepts/parallel-work); a teammate's work takes none of your slots |
| `agent` | `claude` | the headless agents `pulse go` starts; several as `claude:2,codex:2`, where a number caps that agent and a bare name gets `cap`, while `cap` counts all of them together, see [pulse go](../guides/pulse-go#two-agents-at-once) |
| `agent_timeout` | `60` | minutes per phase, `verify` included; a phase that runs longer is stopped with its child processes. A plan or build that timed out gives its claim back; after the build the item keeps its claim, and [the chain after the build](../concepts/verification-gates#the-chain-after-the-build) says what a timeout means for each step |
| `base_branch` | origin's default branch, else `main` | where branches start and PRs point |
| `spec_branch` | `docs/{n}-{slug}` | the name of the docs branch that carries an item's BA and specs: `{n}` is the item's number, `{slug}` its short name, `{type}` its type (`epic`, `feat`, `imp`, `fix`). `/pulse-ba` and `/pulse-re` write there, `pulse new --spec` opens its docs PR. A project whose branch rule refuses `docs/` branches sets its own, for example `{type}/{n}-{slug}-spec`. A pattern without `{n}`, or one a build branch `{type}/{n}-{slug}` would match, is refused with a warning, and the default applies |
| `verify` | none | the command that runs the project's tests. `pulse go` needs it and does not start without it: it runs it in the tests gate, the first of the three gates on every feature branch, and in the [base check](../guides/pulse-go#the-base-check). It also sets what a Claude agent may run, see [Agent templates](#agent-templates). `pulse setup --verify "<cmd>"` sets it |
| `setup` | none | the command that makes a fresh checkout ready for the tests, such as `npm ci`. `pulse go` runs it itself, outside every agent sandbox, in each worktree it makes, again after a lockfile in it changed (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`), and in the base check, so its agents find their dependencies installed. A setup that fails in an item's worktree fails the item with `pulse:failed`; on the base it makes the base red |
| `setup_timeout` | `20` | minutes for one `setup`; one that runs longer is stopped with its child processes and counts as failed |
| `repo` | from `gh repo set-default`, else the single GitHub remote | the GitHub repository that holds the board |
| `ids_since` | none | a commit from which the project numbers its specs anew, for example a new major version on the history of the old one: `pulse number` then counts only the IDs in file names after that commit, on branches and in worktrees that contain it, see [File names and IDs](./artifacts#file-names-and-ids) |
| `[spec_tests]` | none | which runner runs a spec test file: a glob pattern (`*` and `?` within a directory, `**/` any number of them) to `run`, a command whose `{files}` becomes the frozen files it matches, each quoted by `pulse go`, so `{files}` stands bare in `run`, never inside quotes (a name that starts with `-` comes as `./<name>`), and `localhost = true` for a runner that needs a server on localhost: an item whose wave-1 spec test matches such a pattern is built by no agent whose program is `codex`, since Codex runs without network: Claude builds it, or an agent of your own. The first pattern a file matches counts. `pulse go` does not start without the section. It runs the runners at the commit that froze the spec tests, where they must fail (the RED check), and in the tests gate, one runner at a time per machine under `~/.cache/pulse/spec-tests.lock` and with `CI=1`, so parallel items never share a port. P6 of a PLAN asks for a pattern for every spec test file of wave 1. A frozen file no pattern matches (a helper) runs with none |
| `[agents]` | the built-in templates above | how `pulse go` starts a headless agent, see [Agent templates](#agent-templates) |
| `stack`, `reachability_check` | none | per-stack reachability tooling for `/pulse-build`, see [Reachability by stack](./reachability-by-stack) |

**What runs a program counts as merged.** `pulse go` takes `setup`, `setup_timeout`, `verify`, `protected`, `[spec_tests]`, and `[agents]` from `.pulse/config.toml` on the base branch as origin has it, never from your working tree, which a checked-out branch or an agent may have changed: a change to them counts once it is merged and pushed. A run refuses to start when `base_branch` in your working tree names another base than the file there, and, where Python has `tomllib`, when that file is no valid TOML; without `tomllib` (Python 3.9 and 3.10), when a line of it is one the built-in reader does not understand (a multi-line string or array, `[[...]]`, a dotted key) or names a key or a table twice. The other keys come from the working tree.

Pulse ignores top-level keys it does not know, such as one an older version wrote. Before Python 3.11, or when the file is not valid TOML, Pulse reads it line by line and skips a line of the top level or of `[agents]` that it does not understand, with a warning that names the line. A project without `.pulse/config.toml` reads `.dia/config.toml`, the settings file of the predecessor plugin (Digital Innovation Agents), so a project that switched that plugin off stays silent until it migrates.

## Agent templates

`pulse go` starts one agent without a chat window per item, from a template in `[agents]` named by `agent`. A template is a command line: `{prompt}` becomes the instructions, and Pulse fills in two more placeholders.

Whatever the template and your own settings say, `pulse go` limits two programs itself, by the program the template runs, not by its name in `[agents]`: the first word that is no option, no `VAR=value`, and not `env` or `npx`, by its base name without `.exe` (`npx -y @openai/codex` runs `codex`). `codex` gets `-c sandbox_workspace_write.network_access=false` right after that word, so no command it runs reaches the network. Its template must name the workspace sandbox (`--sandbox workspace-write`, `-s workspace-write`, or `--full-auto`), and may name nothing that could open the sandbox or its network: `danger-full-access`, `--dangerously-bypass-approvals-and-sandbox`, `--yolo`, a setting with `network_access` or `sandbox_mode`, or a profile (`-p`, `--profile`), which `$CODEX_HOME/config.toml` (by default `~/.codex/config.toml`) fills; otherwise `pulse go` stops before it claims anything. `claude` gets `--disallowedTools Bash(gh:*)` right after its word. That list takes the words up to the next option, so in a template of your own an option must follow the program, as `-p` does. Another program gets neither. No agent process gets `GH_TOKEN` or `GITHUB_TOKEN`, and `GH_CONFIG_DIR` points at an empty folder under `.git/pulse/`, so `gh` in an agent finds no login: agents never touch GitHub, `pulse go` does.

- **`{allow}`** (Claude Code) lists what the agent may run without asking, since nobody is there to answer: `verify` up to its first option or path, `git add`, `git commit`, `git status`, `git diff`, `git log`, and the `run` of each pattern in `[spec_tests]`, cut the same way and before `{files}` (`npx playwright test {files}` gives `Bash(npx playwright test:*)`). A runner whose rule would end at a shell or an interpreter (`node --test` cut to `node`, `sh e2e/run.sh` cut to `sh`) or names `env` joins no list, since it would run any code: the agent is refused it, and the tests gate still runs it. A `verify` cut that way does join, and lets the agent run any code with it; name a script or a package command instead. For the planning, build, and fix phases of an item, a command under the `verify:` of its PLAN joins the list, cut the same way, but only as a test command: it must start with a program of `verify` or with a script of the repository, such as `bin/pulse check`. A shell or interpreter given code, a download, a package runner or installer (`npx`, `pip install`), `env`, or `sudo` never joins; the item log and the pull request name each line left out, and the tests gate still runs `verify`. The review and audit sessions of `pulse go` get the list from `verify` alone, plus `git -C tree diff`, `log`, `show`, and `status`: they start beside their checkout `tree/`, and a headless Claude refuses `cd tree && git ...` in one command. With `--permission-mode acceptEdits` its edits go through; a command outside the list is refused unless your own permission rules allow it. `python3 -m pytest -q` gives `Bash(python3 -m pytest:*)`, `npm test` gives `Bash(npm test:*)`, `go test ./...` gives `Bash(go test:*)`. A `verify` that chains commands (`npm run lint && npm test`) gets a rule for its start only, and the agent is refused the rest: wrap such a chain in one command, such as an npm script. `--allowedTools` takes every word up to the next option, so in a template of your own an option must follow `{allow}`.
- **`{gitdir}`** (Codex) is the git directory all worktrees share. The Codex sandbox keeps it read-only, so without `--add-dir {gitdir}` Codex cannot commit in its worktree. With it, Codex could also change the shared `config` and `hooks`, and a hook it left would later run outside every sandbox. So after every agent phase `pulse go` compares the whole git config the worktree reads, except `branch.*`, the shared `info/attributes`, the hooks, in the shared `hooks` folder and where `core.hooksPath` points for the worktree (husky: `.husky/_` in it), and the files that tie the worktree to the git directory with their state before the phase. If a phase changed one, the item stops there: nothing is pushed, nothing is thrown away, no further phase runs, the claim stays, and the run names what changed. A person looks and decides. Settings under `branch.*`, such as the merge base VS Code notes per branch, stop nothing; any other change to the config does, since `gpg.program`, `credential.helper`, or a remote's URL can run a program as you. The gates' evidence and the kept verdicts are not in the git directory, see [what `pulse go` keeps outside it](#what-pulse-go-keeps-outside-the-git-directory).

::: warning Templates from an older Pulse
A template in `[agents]` replaces the built-in one of the same name. A line copied from an older Pulse lacks `--allowedTools {allow}` or `--add-dir {gitdir}`, and its agents lose these rights: Claude is refused the tests and git unless your own permission rules allow them, and Codex cannot commit. Delete such lines, or add the two placeholders as in the templates above.
:::

## Signs of life

The claim of a `pulse go` run carries the phase it runs and the time of its last sign of life, so every clone's map can tell running work from silent work ([what the team sees](../concepts/where-things-live#what-the-team-sees-and-when)). Nothing needs configuring:

- **`pulse go`** writes the phase and the time on the item's claim at every phase start (`plan`, `build`, `spec tests`, `tests`, `review`, `audit`, `fix`), and every 10 minutes while a phase runs.

After 30 minutes without a sign of life, a teammate's map shows `no sign of life`. Nothing renews the time on a session's claim: the map shows how long it is held (`held 2 h`).

## What lives in the git directory

The shared git directory (the same for every worktree) holds Pulse's local state, never committed:

| File | Holds |
|---|---|
| `.git/pulse/issues.json` | the local copy of the item records: checked for changes every two seconds (free while nothing moved), reloaded on a change or every 30 seconds |
| `.git/pulse/fetched` | when this clone last fetched every branch from origin (the file's time); Pulse fetches at most once every 30 seconds, whichever command asks (`pulse status`, `pulse go`, the map, and others); `pulse claim`, `pulse number --apply`, and `pulse new --spec` off a docs branch fetch every time. After a fetch that failed it holds `offline` and what git said, which `pulse status`, also for one item, and `pulse approve` print until the next fetch |
| `.git/pulse/me` | your GitHub login |
| `.git/pulse/map.pid` | one line per live map of this clone, its process id; a map adds its line as it starts and removes it as it ends, and the file goes with the last map. No further map of this clone opens by itself while one of them lives |
| `.git/pulse/map.command` | the script a map that Pulse opened runs; for 15 seconds after Pulse writes it, that map counts as starting and no second one opens |
| `.git/pulse/go/<n>.log` | the log of each item `pulse go` ran, one section per phase |
| `.git/pulse/go/report.json` | the results of the last `pulse go` run, written after every event; `pulse status` reads it |
| `.git/pulse/go/base.log` | the output of `setup` and `verify` in the base check |
| `.git/pulse/usage.jsonl` | one line per agent phase of `pulse go`: agent, model, tokens, cost, seconds |
| `.git/pulse/go.pid` | set while `pulse go` runs |

## What `pulse go` keeps outside the git directory

A Codex agent of `pulse go` can write the shared git directory (`--add-dir {gitdir}`), so what decides whether a gate passed lives elsewhere: in `$XDG_CACHE_HOME/pulse/<clone>/`, by default `~/.cache/pulse/<clone>/`, where `<clone>` is 16 hex characters of the hash of the git directory's path. `pulse go` writes there outside the agent sandbox. Files an agent leaves under `.git/pulse/` in their old places count for nothing, and those from before this version are no longer read.

The cache must stay outside the workspace, git directory, temporary folders, and any extra sandbox write paths, including through symlinks. A custom `XDG_CACHE_HOME` inside one of those paths removes this protection; Pulse does not validate that configuration. The default cache path is outside the standard Codex write paths.

| File | Holds |
|---|---|
| `gates/<sha>` | what each gate of `pulse go` said at this commit. Local evidence beside the commit statuses `pulse/tests`, `pulse/review`, and `pulse/audit`, which anyone with write access to the repository can set. Gate 3 and the auto merge read it. A base commit with the tree of a commit whose tests gate passed here is green without a run, the tree read from that commit |
| `reviews/<n>.md`, `audits/<n>.md` | the review and audit verdict kept for an item's pull request, stamped with the commit it looked at |
| `base.json` | the base check of this clone: the base commit `setup` and `verify` last ran on and how, and the last known state of the base |
| `audit-context.json` | the last audit that counted: its date, commit, and manifests |

The Claude Code template runs without a sandbox: its agent can run the tests it wrote and `git diff --output=<file>`, and so can write any file you can, this folder too. Where that matters, let `pulse go` run Codex.
