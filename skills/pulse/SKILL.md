---
name: pulse
description: >
  Pulse entry point: where the work stands, what comes next, and which
  Pulse command fits, and how a person sets Pulse up, starts pulse go,
  and works the live map. Execute an explicitly requested pulse go start.
  Use when the user types /pulse, asks "where do
  I start", "what's next", "who is working on what", "activate Pulse",
  "build everything that is ready", "show the map", or starts new work
  without saying what kind it is.
---

# Pulse

Pulse runs the V-Model method (the Digital Innovation Agents), keeps
the specs in the repository and a record per item on the board, and
spreads agents over everything that is ready. This command reads the situation
and recommends one next step, or executes an explicitly requested runner start
as [Start pulse go](#start-pulse-go) says.
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
| A published spec or Plan has structural findings | fix its R1-R6 or P1-P6 findings with `/pulse-re` or the pulse-plan skill; no person approval is needed to continue authorized preparation |
| Published items need a Plan, or valid Plans are ready to build | offer `pulse go`; execute it when explicitly requested. `/pulse-build <n>` handles one item in this session |
| A checked published result waits for integration approval | show its diff, head and base, tests, review and audit; tell the person `pulse approve <n>` in their terminal or `a` in the Map |
| A result has red gates or stale head/base evidence | preserve its work, show the findings and next repair or revalidation step; approval cannot bypass them |
| A local action says queued or syncing | report that state; only confirmed shared approval authorizes integration |
| A local action says conflict or error | show its reason and refresh the item before proposing the next action |

| Release pending | `/pulse-audit` |

## New work without a kind

For an explicit `pulse go` request, pass the complete objective directly
as [Start pulse go](#start-pulse-go) says; do not require a kind first.
For other new-work requests, ask exactly one question: "Is this a new
feature, an improvement on an existing feature, or a fix for a bug?" A new feature with an unclear
problem goes to `/pulse-ba`, with a clear one to `/pulse-re`. An
improvement or a fix goes to `/pulse-build`.

## The V is a decision graph

Phases run forward by default, but work loops back when it learns
something:

1. **Bug found while building:** stop, record a fix item
   ("Discovered in #n"), find the root cause, then fix it test-first.
2. **Design proves wrong while building:** stop, amend the decision or
   the Plan, then continue.
3. **Requirement gap while planning or building:** route it back to the
   spec, re-check the Plan covers every success criterion, continue.

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

When the person explicitly asks to start `pulse go`, execute that command
with the session markers intact. Pulse runs in the foreground when the
tool provides a TTY; without one it owns a managed process and returns a
receipt with its run ID, PID, report and log. A second managed start finds
the existing run. No Herdr, extra coordinator or shell detachment is
required. Never use `nohup` or erase markers to force a start.

Pass any free-text objective directly as the positional words after `pulse go`.
Preserve the whole request, including combined instructions such as finishing
Epic 4 and investigating a UI problem. Flags are optional shortcuts. Without
an objective, process the queue; with one, process the queue plus that objective.
Only an explicit restriction bounds the run. Do not replace a compound request
with an epic flag that would drop the other instruction. The runner records
new work as visible ordinary items and applies the same DIA workflow.
Use `pulse go --pause`, `--resume` or `--steer "<additional direction>"`
when requested. A saved control is pending until the runner applies it.

Before replying, read the receipt and a fresh `pulse status` or run report.
Name the current operation during preparation; there are no active agents
until one actually starts. Report a finished or failed run truthfully,
with its cause and next step. Use `pulse go --stop` when the person asks
to stop it. Run outside the sandbox when network access or shared Git
writes require it. A person can also start it in their own terminal.
Never start `pulse go` automatically or from runner agents or child
sessions; an unrequested status check starts nothing.

The runner prepares published specs and valid Plans, builds test-first,
and runs tests, review and audit. It needs `verify` and `[spec_tests]`
on the fetched base; report missing configuration and prepare the change.
Startup reads the fetched base and its configuration; full `verify` belongs to the
completed result. It publishes on the item's branch, releases inactive
claims and obtains final approval of exact result head and base. Automatic
completion is the default; a person may choose manual final approval.
Both use the same checks. A managed runner keeps waiting without a
terminal and continues only after confirmed approval. Starting it grants no approval
and changes no approval policy. The report remains after it ends.
Details: <https://pssah4.github.io/pulse/guides/pulse-go>.

## Work the map

The person runs the live map in a terminal of its own: `pulse map`, or
the task "Pulse map" in VS Code; in Herdr it opens beside each session by
itself; `q` ends it. `pulse map --ensure`
opens it beside you in Herdr or tmux or prints the line that says how, which you
pass on (in Codex run it outside the sandbox; no output means
`PULSE_MAP=off`, then ask the person to run `pulse map`); never run `pulse map` without `--ensure` in your shell or
paste a frame. In the map `↑` `↓` pick a line, `Enter` opens an item,
`Esc` goes back, `?` shows the help; an item's view offers only what
its stage allows: read spec (`o`), read Plan, inspect the result and checks,
and approve integration (`a`) for a current verified result. The preview
names the exact head and base; `Enter` confirms. Approval, defer, resume,
revoke and handoff enter a durable local queue immediately. Show queued,
syncing, confirmed, conflict or error honestly. A background synchronizer
continues after the Map closes; a queued approval never permits a merge.
Tell the person to press `a` on the result or use `pulse approve <n>`
in their own terminal. These actions belong to the person. Never send text or keys into the
Map's pane or another terminal to operate them. `pulse auto` displays the
final integration approval policy. The person can configure it with `3`
in the Map or `pulse auto merge on|off`; `--for 8h` limits an enabled setting.
Settings enter the same durable local queue. Historical plan/build/merge
switches do not authorize work. `pulse retry <operation>` retries a saved
sync error without changing its binding. Details:
<https://pssah4.github.io/pulse/guides/pulse-map>.

## Commands

To pause open work as-is, tell the person to run `pulse defer <n>` in
their terminal. `pulse resume <n>` explicitly continues it. Approvals,
notes, code, specs, branches and evidence remain. An unreachable holder keeps
the stop pending; uncommitted work stays in its worktree.
`pulse discard <n>` closes without rollback. `pulse delete <n>` instead
requires a reviewed removal of code, specs and references before deleting
the issue and comments. It requires typed confirmation and a separate
final integration approval. Never run these person-only commands for them,
unless the person granted their levers: `pulse levers allow
run|session|always`, run on its own, makes Claude Code ask them, and
`pulse levers` shows the grants and their uses.

In the map, `m`, arrow keys and `Enter` save a shared order; prerequisites
still come first. `Esc` cancels. The picker also reaches epics in the board.

| Command | Does |
|---|---|
| `/pulse-ba` | business analysis: problem, users, scope |
| `/pulse-re` | epic, features, success criteria, registered items |
| `/pulse-build` | one item test-first (planned first when it has no Plan), bugs, tests for existing code |
| `/pulse-audit` | security audit |
| `/pulse-realign` | take over an existing codebase or a DIA project |
| `/pulse-go` | start or steer `pulse go` with the person's goal |
