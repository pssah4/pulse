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
claude = "claude -p --output-format json --settings {settings} {prompt}"
codex = "codex exec --json {prompt}"

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
| `item_flow` | `goal` | how `pulse go` hands an item to a worker. `goal`: a worker whose program is `claude` gets the whole item as one `/goal` session (plan, spec tests, build, `verify`, reference, `Pulse-Task` per task, at most 20 turns), and each fix round as a new goal; Codex, which offers `/goal` only in its terminal UI, builds in phases. `phases`: separate plan, build and fix sessions for every worker. Pulse's own gates decide either way. Another value warns and counts as `phases`, see [pulse go](../guides/pulse-go#what-a-run-does) |
| `agent_timeout` | `60` | minutes per phase, `verify` included; a phase that runs longer is stopped with its child processes. A plan or build that timed out gives its claim back; stopped work is preserved for recovery, and [the chain after the build](../concepts/verification-gates#the-chain-after-the-build) says what a timeout means for each step |
| `base_branch` | origin's default branch, else `main` | the shared base from which item branches start and into which approved results integrate |
| `spec_branch` | `docs/{n}-{slug}` | legacy spec-branch lookup for existing projects. New work reserves a draft number first and keeps spec, Plan and implementation on `<type>/<n>-<slug>`; it needs no separate docs branch or PR |

| `verify` | none | the command that runs the project's tests. `pulse go` needs it and does not start without it: it runs it in the tests gate, the first of the three gates on every feature branch, after the built result. The [base check](../guides/pulse-go#the-base-check) fetches the current base without running this command; CI status does not gate the workflow. `pulse setup --verify "<cmd>"` sets it |
| `setup` | none | the command that makes a fresh checkout ready for the tests, such as `npm ci`. `pulse go` runs it as its own process, in each worktree it makes, again after a lockfile in it changed (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`), so its agents find their dependencies installed. A setup that fails in an item's worktree fails the item with `pulse:failed` |
| `setup_timeout` | `20` | minutes for one `setup`; one that runs longer is stopped with its child processes and counts as failed |
| `repo` | from `gh repo set-default`, else the single GitHub remote | the GitHub repository that holds the board |
| `ids_since` | none | a commit from which the project numbers its specs anew, for example a new major version on the history of the old one: `pulse number` then counts only the IDs in file names after that commit, on branches and in worktrees that contain it, see [File names and IDs](./artifacts#file-names-and-ids) |
| `[spec_tests]` | none | which runner runs a spec test file: a glob pattern (`*` and `?` within a directory, `**/` any number of them) to `run`, a command whose `{files}` becomes the frozen files it matches, each quoted by `pulse go`, so `{files}` stands bare in `run`, never inside quotes (a name that starts with `-` comes as `./<name>`), and optional `localhost = true` metadata for a runner that needs a local server. This does not select an agent; the native harness decides whether the worker can reach it. The first pattern a file matches counts. `pulse go` does not start without the section. It runs the runners at the commit that froze the spec tests, where they must fail (the RED check), and in the tests gate, one runner at a time per machine under `~/.cache/pulse/spec-tests.lock` and with `CI=1`, so parallel items never share a port. P6 of a Plan asks for a pattern for every spec test file of wave 1. A frozen file no pattern matches (a helper) runs with none |
| `[agents]` | the built-in templates above | how `pulse go` starts a headless agent, see [Agent templates](#agent-templates) |
| `stack`, `reachability_check` | none | per-stack reachability tooling for `/pulse-build`, see [Reachability by stack](./reachability-by-stack) |

**What runs a program counts as merged.** `pulse go` takes `setup`, `setup_timeout`, `verify`, `protected`, `item_flow`, `[spec_tests]`, and `[agents]` from `.pulse/config.toml` on the base branch as origin has it, never from your working tree, which a checked-out branch or an agent may have changed: a change to them counts once it is merged and pushed. A run refuses to start when `base_branch` in your working tree names another base than the file there, and, where Python has `tomllib`, when that file is no valid TOML; without `tomllib` (Python 3.9 and 3.10), when a line of it is one the built-in reader does not understand (a multi-line string or array, `[[...]]`, a dotted key) or names a key or a table twice. The other keys come from the working tree.

Pulse ignores top-level keys it does not know, such as one an older version wrote. Before Python 3.11, or when the file is not valid TOML, Pulse reads it line by line and skips a line of the top level or of `[agents]` that it does not understand, with a warning that names the line. A project without `.pulse/config.toml` reads `.dia/config.toml`, the settings file of the predecessor plugin (Digital Innovation Agents), so a project that switched that plugin off stays silent until it migrates.

Final integration approval is required for every concrete result head and base. `pulse auto` reports that policy; historical plan/build/merge switches grant no authority. A valid published spec proceeds to planning and a valid published Plan to the authorized build, subject to dependencies, active file claims and base checks. Risk flags stay visible for review without adding an early approval stop.

Before publication, `pulse check --plan <path>` checks P1 to P6 together against the current local base, without fetching or running a test suite. Under `pulse go`, agents run targeted checks and additional Plan checks outside `verify`; the supervisor runs the full command once after the build, then repeats it only after a relevant change.

## Agent templates

`pulse go` starts a native CLI for each item from a template in `[agents]`. It splits the command without a shell and inserts `{prompt}` as one argument. The built-in commands are shown above. The `{settings}` in the standard Claude template is reserved for Pulse's `PreToolUse` hook JSON; it contains no general permissions or sandbox policy.

Codex and Claude read their own user, project and organization settings and use their native authentication. Pulse leaves their configuration paths and authentication environment intact, except for the worker's GitHub isolation below. It does not copy settings from the launching clone, choose a permission mode, or set network and write permissions. Native custom templates pass through unchanged; choose their options in the harness's own configuration.

Build workers start in the item's worktree. Review and audit start in a separate session directory beside their checkout. Those directories determine which project settings the native CLI finds. An untracked local settings file in the original clone is not copied into them. Temporary permissions of the chat that started Pulse are not transferred to a new CLI.

Workers run with closed stdin and have no channel for answering permission prompts in the calling chat. A concrete native runtime, login, permission or required-hook failure stops that attempt without repeating it unchanged. The report names the phase, cause, preserved branch and worktree, and next action. Configure the native prerequisite before retrying. A successful response that merely quotes an earlier error is not treated as a new failure.

Pulse keeps its process rules: claims, personal levers, base and state pushes, worker markers, required hooks and the running Pulse copy. The default Claude start supplies the Pulse hook without overriding `disableAllHooks`; a missing installation hook is a configuration error. Native hook restrictions must be resolved in the harness. Codex needs its installed Pulse hooks trusted in Codex. The guard protects cooperative workflow use; the native harness and operating system provide the general security boundary.

No worker process receives `GH_TOKEN`, `GITHUB_TOKEN` or their enterprise counterparts. `GH_CONFIG_DIR` points at an empty folder under `.git/pulse/`. Pulse owns board updates and network publication. This separation does not change how the harness authenticates to its own model provider.

After each agent phase Pulse still compares the Git configuration, shared attributes, hooks and worktree links with their earlier state. Only `branch.*` configuration is exempt. A changed protected value stops further phases and publication, preserves the work and claim, and names the paths for a person to inspect. Pulse does not restore those files automatically. See also [evidence outside the Git directory](#what-pulse-go-keeps-outside-the-git-directory).

### Migrating old permission settings

- Remove `worker_permissions = "person"`; it now warns and uses native settings. An omitted key uses native settings without a warning.
- `worker_permissions = "narrow"` or an unknown value stops before the first claim. Configure the intended restrictions in the native harness, then remove the key.
- An exact built-in template from an older Pulse is recognized and mapped to the native default with a notice. Remove that redundant `[agents]` entry to use the current default.
- A custom old template containing `{allow}`, `{mode}`, `{settings}` or `{gitdir}` stops with a migration finding. Replace it with a native template. Only the exact standard Claude template uses the reserved hook placeholder; Pulse cannot infer a custom template's intended policy.

Publish executable configuration changes on the base branch before starting a run. Pulse neither edits the stored harness settings nor starts a fallback sandbox.

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

Gate and integration evidence lives separately from the worktrees and shared Git directory: in `$XDG_CACHE_HOME/pulse/<clone>/`, by default `~/.cache/pulse/<clone>/`, where `<clone>` is 16 hex characters of the hash of the Git directory's path. Pulse writes it as the supervisor. Files an agent leaves under `.git/pulse/` in their old evidence locations count for nothing.

Keep the cache outside the workspace, Git directory and native worker write paths. The action outbox checks ownership, permissions and path components and rejects unsafe locations. Its stop requests and pending actions use that storage. Protection from a worker still depends on the filesystem boundary configured in its native harness and operating system; Pulse does not create that boundary.

| File | Holds |
|---|---|
| `gates/<sha>` | what each gate of `pulse go` said at this commit. Local evidence beside the commit statuses `pulse/tests`, `pulse/review`, and `pulse/audit`, which anyone with write access to the repository can set. Final integration checks this evidence independently of externally writable statuses. A base commit with the tree of a commit whose tests gate passed here is green without a run, the tree read from that commit |
| `reviews/<n>.md`, `audits/<n>.md` | the review and audit verdict kept for an item's published result, stamped with the commit it looked at |
| `base.json` | this clone's evaluated base SHA, current CI and saved evidence, state, and bounded diagnostics; older saved results remain readable |
| `audit-context.json` | the last audit that counted: its date, commit, and manifests |
| `actions/outbox.sqlite` | durable local intents and synchronization receipts, including queued, syncing, confirmed, conflict and error |
| `actions/runner-<run-id>.log`, `actions/runner-stop-<run-id>` | managed process output and a stop request bound to one run |
| `compatibility/` | isolated Plan-commit probe logs and temporary checkout; successful evidence is bound to base and configuration |
