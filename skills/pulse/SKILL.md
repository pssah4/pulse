---
name: pulse
description: >
  Pulse entry point: where the work stands, what comes next, and which
  Pulse command fits, and how a person sets Pulse up, starts pulse go,
  and works the live map. Use when the user types /pulse, asks "where do
  I start", "what's next", "who is working on what", "activate Pulse",
  "build everything that is ready", "show the map", or starts new work
  without saying what kind it is.
---

# Pulse

Pulse runs the V-Model method (the Digital Innovation Agents), keeps
the specs in the repository and a record per item on the board, and
spreads agents over everything that is ready. This command reads the situation and recommends one next step.
The user decides.

## Where things stand

Run `pulse status`. If Pulse is not active here (no `.pulse/config.toml`),
say so in one line and set it up as [Set Pulse up](#set-pulse-up)
says. Otherwise summarize in at most five lines: ready
items, work in progress and who holds it, what waits on the user, what
is failing, what is blocked and on what.

## What comes next

Take the first row that applies. In Codex, name each command as
`$pulse:<name>`, so `$pulse:pulse-ba` for `/pulse-ba`.

| Situation | Recommend |
|---|---|
| Something waits on the user (an open question, a red test) | name it first |
| No method artifacts, empty or greenfield repo | `/pulse-ba` for the Project-BA |
| Code exists but no BA and no specs, or legacy DIA artifacts | `/pulse-realign` |
| Project-BA is a Draft | `/pulse-ba` in Validation Mode |
| A new epic or feature is wanted | `/pulse-ba` for its Item-BA |
| A validated Project-BA or an Item-BA exists, no epics or features registered yet | `/pulse-re` |
| Specs wait for approval (`pulse status`: "not approved") | show each spec's goal, scope, and success criteria, then tell the person how they approve it, which means build it: `pulse approve <n>` in their own terminal, or `a` in the map; it writes the approval and nothing else, and `pulse go` merges a spec not yet on the base branch there first: the docs PR that `pulse new` opened, once every spec in it passes R1 to R6, it changes only `_devprocess/`, and its checks pass. It refuses a spec neither on the base branch nor in an open pull request (R1: `/pulse-re` pushes it) and, for a feature, improvement, or fix, a spec on the base branch that breaks R2 to R6: then `/pulse-re` on that spec (an epic needs R1 only) |
| An approved spec waits for `pulse go` (`pulse status`: "spec in PR #m: pulse go merges it") | tell the person: `pulse go` in their own terminal merges the docs PR, then plans; when the run names why it did not merge it (a spec that breaks a rule, a file outside `_devprocess/`, checks that have not passed), fix that on the docs branch and push |
| Items are approved but their spec does not pass R1 to R6 (`pulse check`) | `/pulse-re` on that spec |
| A PLAN waits for a person (`pulse status`: "plan waits for you", or "plan changed since plan ok", "spec changed since plan ok") | show its goal, decisions, and risks, and tell the person how they approve it: `pulse approve <n>` in their own terminal, which binds the PLAN as origin has it and the spec on the base |
| Approved items with a ready spec, or ready items, and free slots | tell the person: `pulse go` in their own terminal plans what has no PLAN, then builds all in parallel ([Start pulse go](#start-pulse-go)); or `/pulse-build <n>` for one in this session (it plans first when there is no PLAN) |
| A feature PR is ready (tests, review, and audit passed) | name it: it waits for the person's `pulse approve <n>`, or `a` in the map, which approves its merge at its head (gate 3); the next `pulse go` merges it and closes the item |
| A draft feature PR names a red gate | fix the findings on its branch test-first, push them, and give the item back with `pulse release <n>`; the next `pulse go` runs the gates on it and marks it ready once all three pass |
| A PR whose last commit has no review or no audit | run the missing gates on a yes, in a fresh subagent, as in Done of `/pulse-build`, and put the reports into the PR |
| Release pending | `/pulse-audit` |

## New work without a kind

Ask exactly one question: "Is this a new feature, an improvement on an
existing feature, or a fix for a bug?" A new feature with an unclear
problem goes to `/pulse-ba`, with a clear one to `/pulse-re`. An
improvement or a fix goes to `/pulse-build`.

## The V is a decision graph

Phases run forward by default, but work loops back when it learns
something:

1. **Bug found while building:** stop, record a fix item
   ("Discovered in #n"), find the root cause, then fix it test-first.
2. **Design proves wrong while building:** stop, amend the decision or
   the PLAN, then continue.
3. **Requirement gap while planning or building:** route it back to the
   spec, re-check the PLAN covers every success criterion, continue.

A loop back does not re-run later phases on its own. The user decides,
and the item's spec records the decision.

## Set Pulse up

`pulse setup` switches Pulse on in a git repository with a GitHub
remote (`gh` 2.94 or newer): it writes `.pulse/config.toml` and the
anchor block in `AGENTS.md`; a `CLAUDE.md` gets the line `@AGENTS.md`
that imports it. Ask one question per turn for what
`pulse setup --dry-run` shows and for `--verify "<command>"`, the tests
`pulse go` runs (none where the project has no tests, never a command
that always passes), run `pulse setup` with the answers, and `--labels`
once the person agrees. Once per machine, on a yes: `--cli` puts
`pulse` in `~/.local/bin`, and in Codex `--codex-rules` lets Codex run
`pulse` without asking but never a person's lever; both write outside
the project, so Codex asks the person first. Codex runs the Pulse hooks
once the person trusts them (`/hooks` in the CLI); never write that
trust yourself. Outside Herdr `pulse setup` adds the task "Pulse map"
below to `.vscode/tasks.json` itself; only where its report says it kept
the file (no plain JSON), offer the task "Pulse map" below for `tasks` in
`.vscode/tasks.json`, keeping the rest. Offer to commit the config and the agent files on a branch
from `refs/remotes/origin/<base>` after `git fetch origin`. Off (`--mode off`) and
out (`--remove`; `--remove --cli --codex-rules` instead takes the
command and the Codex rules off this machine) are the person's, in
their own terminal. Details:
<https://pssah4.github.io/pulse/guides/pulse-setup>.

```json
{"label": "Pulse map", "type": "shell", "command": "pulse map",
 "runOptions": {"runOn": "folderOpen"},
 "problemMatcher": [], "presentation": {"panel": "dedicated"}}
```

## Start pulse go

`pulse go` is the person's: it refuses an agent session and a start
without a terminal, so never start `pulse go` yourself; tell the person
to type `pulse go` in their own terminal, where it runs in the
foreground. It plans and builds every
approved item in parallel, a worktree and a headless agent each (an
item without a PLAN is planned first), runs the RED check and three
gates (tests, review, audit), and opens a pull request per feature:
ready when all three passed, else a draft that names what is open, for
the person to merge. It needs `verify` and ends when
the ramp is empty or on Ctrl-C; `.git/pulse/go/report.json` holds each
item's result. Details: <https://pssah4.github.io/pulse/guides/pulse-go>.

## Work the map

The person runs the live map in a terminal of its own: `pulse map`, or
the task "Pulse map" in VS Code; in Herdr it opens beside each session by
itself; `q` ends it. `pulse map --ensure`
opens it beside you in Herdr or tmux or prints the line that says how, which you
pass on (in Codex run it outside the sandbox; no output means
`PULSE_MAP=off`, then ask the person to run `pulse map`); never run `pulse map` without `--ensure` in your shell or
paste a frame. In the map `↑` `↓` pick a line, `Enter` opens an item,
`Esc` goes back, `?` shows the help; an item's view offers only what
its stage allows: the approval it waits for (`a`: approve spec, approve
plan, approve merge, or try again), read spec (`o`), read plan or PR, each done with
`Enter`; `pulse go` merges a ready pull request once a person approved its merge. These are the person's levers: tell the person
to press `a` on the item in the Pulse map, or to run `pulse approve <n>`
in their own terminal. The auto mode per gate is theirs as well: when the person
asks how `pulse go` could pass a gate without asking them, name
`pulse auto <plan|build|merge> on [--for 8h]` in their own terminal, or
`1` `2` `3` in the map; never switch it yourself. Never send text or keys into the map's pane, nor
`pulse map` into another terminal: the map runs as the person, and the
guard refuses it. Details:
<https://pssah4.github.io/pulse/guides/pulse-map>.

## Commands

| Command | Does |
|---|---|
| `/pulse-ba` | business analysis: problem, users, scope |
| `/pulse-re` | epic, features, success criteria, registered items |
| `/pulse-build` | one item test-first (planned first when it has no PLAN), bugs, tests for existing code |
| `/pulse-audit` | security audit |
| `/pulse-realign` | take over an existing codebase or a DIA project |
