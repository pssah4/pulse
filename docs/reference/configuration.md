---
title: Configuration
description: Every setting in .pulse/config.toml.
---

# Configuration

`/pulse-setup` writes `.pulse/config.toml`. Hand edits are welcome; `pulse setup` changes only the keys it sets and leaves the rest of the file alone.

```toml
mode = "on"                 # on | off
parallel = "items"          # off | items | max
cap = 4                     # parallel slots for pulse go
agent = "claude"            # which [agents] templates pulse go starts, e.g. "claude:2,codex:2"
agent_timeout = 60          # minutes before a hung agent is stopped
# review_agent = "codex"    # another [agents] template for the review and the audit; default: agent
plan_approval = "auto"      # auto | manual: who approves a PLAN before it is built
base_branch = "main"
verify = "npm test"         # pulse go needs it: the RED check, the tests gate, the integration check
# repo = "owner/name"       # only when the repo has several GitHub remotes

[agents]                    # optional; these are the built-in templates, see below
claude = "claude -p --allowedTools {allow} --output-format json --permission-mode acceptEdits {prompt}"
codex = "codex exec --json --sandbox workspace-write --add-dir {gitdir} {prompt}"

[audit.supply_chain]        # read by /pulse-audit
build_command = "npm run build"
artifacts = ["dist/app.js"]
```

| Key | Default | Meaning |
|---|---|---|
| `mode` | none (not active) | `on` injects the rules, records presence, and keeps a [sign of life](#signs-of-life) on the items a session holds; `off` silences every hook but keeps the files |
| `parallel` | `items` | how far work runs at once, see [Parallel work](../concepts/parallel-work) |
| `cap` | `4` | items that run at once for you; a teammate's work takes none of your slots |
| `agent` | `claude` | the headless agents `pulse go` starts; several with their own slots as `claude:2,codex:2` (a bare name gets `cap`), see [/pulse-go](../guides/pulse-go#two-agents-at-once) |
| `review_agent` | the value of `agent` | the [agents] template the review and the audit sessions start; another model checks what one built, see [Review](../guides/pulse-review) |
| `agent_timeout` | `60` | minutes per phase, `verify` included; a phase that runs longer is stopped with its child processes. A plan or build that timed out gives its claim back; after the build the item keeps its claim, and [the chain after the build](../concepts/verification-gates#the-chain-after-the-build) says what a timeout means for each step |
| `base_branch` | origin's default branch, else `main` | where branches start and PRs point |
| `verify` | none | the command that runs the project's tests. `pulse go` needs it and does not start without it: it checks with it that the spec tests fail before the code exists, runs it as the tests gate, the first of the three gates on every feature branch, and at the end of a run runs it on the ready branches merged together. It also sets what a Claude agent may run, see [Agent templates](#agent-templates). `pulse setup --verify "<cmd>"` sets it |
| `plan_approval` | `auto` | `auto` approves every PLAN that passes P1 to P5 unless a risk flag or `effort: L` in its spec or `needs:` in the PLAN holds it; `manual` waits for `pulse approve-plan` on every PLAN |
| `map_autostart` | `true` | `pulse go` as it starts, `pulse claim`, and `pulse new --draft` open the [live map](../guides/pulse-map#when-it-opens-by-itself) where you work when no map of this clone runs; `false` turns that off, as `PULSE_MAP=off` in the environment does for one shell |
| `repo` | from `gh repo set-default`, else the single GitHub remote | the GitHub repository for work state |
| `[agents]` | the built-in templates above | how `pulse go` starts a headless agent, see [Agent templates](#agent-templates) |
| `stack`, `reachability_check` | none | per-stack reachability tooling for `/pulse-build`, see [Reachability by stack](./reachability-by-stack) |

Pulse ignores top-level keys it does not know, such as one an older version wrote. Before Python 3.11, or when the file is not valid TOML, Pulse reads it line by line and skips a line of the top level or of `[agents]` that it does not understand, with a warning that names the line. A project without `.pulse/config.toml` reads `.dia/config.toml`, the settings file of the predecessor plugin (Digital Innovation Agents), so a project that switched that plugin off stays silent until it migrates.

## Agent templates

`pulse go` starts one agent without a chat window per item, from a template in `[agents]` named by `agent`. A template is a command line: `{prompt}` becomes the instructions, and Pulse fills in two more placeholders.

- **`{allow}`** (Claude Code) lists what the agent may run without asking, since nobody is there to answer: `verify` up to its first option or path, and `git add`, `git commit`, `git status`, `git diff`, `git log`. For the planning, build, and fix phases of an item, a command under the `verify:` of its PLAN joins the list, cut the same way, but only as a test command: it must start with a program of `verify` or with a script of the repository, such as `bin/pulse check`. A shell or interpreter given code, a download, a package runner or installer (`npx`, `pip install`), `env`, or `sudo` never joins; the item log and the pull request name each line left out, and the tests gate still runs `verify`. The review and audit sessions get the list from `verify` alone. With `--permission-mode acceptEdits` its edits go through; a command outside the list is refused unless your own permission rules allow it. `python3 -m pytest -q` gives `Bash(python3 -m pytest:*)`, `npm test` gives `Bash(npm test:*)`, `go test ./...` gives `Bash(go test:*)`. A `verify` that chains commands (`npm run lint && npm test`) gets a rule for its start only, and the agent is refused the rest: wrap such a chain in one command, such as an npm script. `--allowedTools` takes every word up to the next option, so in a template of your own an option must follow `{allow}`.
- **`{gitdir}`** (Codex) is the git directory all worktrees share. The Codex sandbox keeps it read-only, so without `--add-dir {gitdir}` Codex cannot commit in its worktree. With it, Codex could also change the shared `config` and `hooks`, and a hook it left would later run outside every sandbox. So after every agent phase `pulse go` compares the shared `config` and `hooks`, and the files that point the worktree at its git directory, with their state before the phase. If a phase changed one, the item stops there: nothing is pushed, no further phase runs, the claim stays, and the run names the changed paths. A person looks and decides.

::: warning Templates from an older Pulse
A template in `[agents]` replaces the built-in one of the same name. A line copied from an older Pulse lacks `--allowedTools {allow}` or `--add-dir {gitdir}`, and its agents lose these rights: Claude is refused the tests and git unless your own permission rules allow them, and Codex cannot commit. Delete such lines, or add the two placeholders as in the templates above.
:::

## Signs of life

A claim on the board carries the phase of the session that holds the item and the time of its last sign of life, so every clone's map can tell running work from silent work ([what the team sees](../concepts/where-things-live#what-the-team-sees-and-when)). Nothing needs configuring:

- **`pulse go`** writes the phase and the time on the item's claim at every phase start (`plan`, `build`, `spec tests`, `tests`, `review`, `audit`, `fix`), and every 10 minutes while a phase runs.
- **The hook** does it for an interactive Claude Code or Codex session with `mode = "on"`: on a tool call, at most every 10 minutes per session, it writes the phase `working` and the time on the claims this session holds, and a draft keeps its phase (`analysis` or `spec`). The sessions `pulse go` starts are left to `pulse go`. A failed write costs one sign of life, and the next try comes 10 minutes later.
- **Skills** run `pulse beat <n> <phase>`.

After 30 minutes without a sign of life, a teammate's map shows `no sign of life`.

## What lives in the git directory

The shared git directory (the same for every worktree) holds Pulse's local state, never committed:

| File | Holds |
|---|---|
| `.git/pulse/issues.json` | the local copy of the item records: checked for changes every two seconds (free while nothing moved), reloaded on a change or every 30 seconds |
| `.git/pulse/fetched` | when this clone last fetched every branch from origin (the file's time); Pulse fetches at most once every 30 seconds, whichever command asks (`pulse status`, `pulse go`, the map, and others). It holds `offline` when origin did not answer |
| `.git/pulse/me` | your GitHub login |
| `.git/pulse/presence.jsonl` | hook events for the live map, trimmed as it grows |
| `.git/pulse/map.pid` | one line per live map of this clone, its process id; a map adds its line as it starts and removes it as it ends, and the file goes with the last map. No further map of this clone opens by itself while one of them lives |
| `.git/pulse/map.command` | the script a map that Pulse opened runs; for 15 seconds after Pulse writes it, that map counts as starting and no second one opens |
| `.git/pulse/go/<n>.log` | the log of each item `pulse go` ran, one section per phase |
| `.git/pulse/go/report.json` | the results of the last `pulse go` run, written after every event; `pulse status` reads it |
| `.git/pulse/go/discovered.md` | the new work the agents of `pulse go` wrote down, across runs |
| `.git/pulse/go/run.log` | the output of `pulse go --detach`, one section per start |
| `.git/pulse/usage.jsonl` | one line per agent phase of `pulse go`: agent, model, tokens, cost, seconds |
| `.git/pulse/beats/` | one stamp per session: when its hook last wrote a sign of life |
| `.git/pulse/reviews/<n>.md`, `.git/pulse/audits/<n>.md` | the review and audit verdict kept for an item's pull request, stamped with the commit it looked at |
| `.git/pulse/go.pid` | set while `pulse go` runs |
