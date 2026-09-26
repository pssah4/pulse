---
name: pulse-go
description: >
  Plans and builds every approved item in parallel: one worktree and one
  headless agent (Claude Code or Codex) per item, refilled as slots free up;
  an item without a PLAN is planned first; each built feature goes through
  tests, review, and security audit before its PR is ready. Use for
  /pulse-go, "work on everything in parallel", "start all unblocked
  items", "parallelize the backlog".
---

# Pulse go

`pulse go` is a script, not a suggestion: it reads the ramp, claims items,
creates worktrees, and starts the agents itself. A model cannot forget to
parallelize because it does not decide.

`/pulse-build` is how one item gets built; `pulse go` runs that same
discipline for every ready item at once, one headless agent per item, and
runs the gates after each build: tests, review, security audit. Build one
item with the user watching: `/pulse-build <n>`. Build everything the
ramp releases: `pulse go`.

## How far it goes: the parallel level

`.pulse/config.toml`, set by `/pulse-setup`:

| `parallel` | What runs at once |
|---|---|
| `off` | one item at a time |
| `items` (default) | every ready item with files disjoint from running work, up to `cap` |
| `max` | as `items`; inside an item, task waves run as parallel subagents |

Two constraints hold at every level: blockers first (GitHub knows the
edges), and nothing runs at the same time as another item that touches
one of its files (the PLANs' `files:` lists). The order is the team's rank
(`pulse rank`, or dragging in the map); unranked items follow the
critical path.

A feature with exactly one open blocker whose pull request is ready (all
gates passed) does not wait for the merge: it stacks on the blocker's
branch and its pull request targets that branch. When the blocker is
merged, the next run moves the stacked pull request to the base branch.

## Plan first, then build

An item is built only when it is ready: approved, its spec passes R1 to R6,
its PLAN passes P1 to P5 and is approved, no blocker open. An approved item
with a ready spec and no PLAN gets a planning job first (free slots only,
in ramp order): the agent writes the PLAN on the item's branch, Pulse pushes
it and gives the claim back. With `plan_approval = "auto"` (default) the
next round builds it on the same branch; a risk flag or effort L in the
spec, `needs:` in the PLAN, or `plan_approval = "manual"` leaves it on
"plan waits for you" until `pulse approve-plan <n>`. Planning does not
wait for blockers, building does.

## Run it

`pulse go` needs `verify` in `.pulse/config.toml`, the command that runs
the project's tests: the tests gate and the RED check run it. Without it
`pulse go` claims nothing and says so (`pulse setup --verify "<cmd>"`).

While a live map runs, it starts `pulse go` itself when approved work
waits and no run of this clone lives (`go_autostart`); `pulse go`
refuses a second run in the clone, so check `pulse status` first.

1. `pulse go --dry-run`: which items would start, on which branch, from
   which base, in which worktree. Say it to the user before the real run:
   `pulse go` claims those items, pushes their branches, and opens one
   pull request per feature against the base branch (or against its
   blocker's branch when it is stacked).
2. Start it detached, so it outlives this chat and the shell tool's time
   limit: `pulse go --detach` (with `--agent codex`, `--agent
   claude:2,codex:2`, or `--cap N` for this run). It waits until the run
   holds the clone's run lock, at most 10 seconds, then prints the pid,
   the log `.git/pulse/go/run.log`, and the report, and returns 0. A run
   that ends before that (no `verify`, a run already in this clone, no
   agent to build with) prints what it wrote, and `--detach` exits with
   the run's code. In Codex, whose sandbox keeps the network and `.git`
   closed, do not start it: give the user the command for a terminal,
   `pulse go --detach`. The run keeps
   going until the ramp is empty and every agent has finished. Per
   feature, on its own branch: plan (when there is no PLAN), build (spec
   tests first, then frozen, then the PLAN's tasks), the RED check
   (`verify` must fail at the commit that froze the spec tests), then
   the gates in order: `tests` (`verify`), `review` in a fresh session
   (the pulse-review skill, scope branch), `audit` in a fresh session
   (`/pulse-audit`, scope branch against the base). When the scan of
   the audit fails, no audit session starts: the `audit` gate says
   `none` with the reason, and the PR stays draft. A red gate gets a
   fix round, at most two per gate, and after every fix the chain starts
   again at `tests`. Logs, one section per phase:
   `.git/pulse/go/<n>.log`. What an agent leaves uncommitted, `pulse go`
   commits before the next gate, so tests, review, and audit judge the
   same commits. After every agent phase that committed, it pushes the
   item's branch, a fast-forward only, so whoever holds the item next
   builds on the work; a rejected push stops the item. The claim mark
   names the phase, and for a build the PLAN's `files:`, so every
   clone's ramp holds those files at once; each later phase start puts
   the phase and the time on the mark, and a phase that runs long
   renews them every 10 minutes (the heartbeat, as `pulse beat` does),
   so the map in every clone shows the phase and the age of the last
   sign of life. The output names each start: `planning #n`,
   `building #n`, or `taking up #n` (a draft).
3. Read `.git/pulse/go/report.json`: it is written after every result,
   so it holds what finished even when the run was stopped. `run` has
   the pid, the start, the end, and the signal that stopped it; `items`
   has one entry per item with `result`, `why`, `pr`, `log`, and `at`;
   `pulse status` names the last run in one line. The results:
   - **done:** the PR exists with a table of the three gates and the
     review and audit reports, and the review and audit verdicts as
     comments, so a session that takes the item over finds them. Ready
     when all three passed: it waits for the user's merge. Draft when a
     gate stayed red: the PR names what is open, and the item keeps its
     claim, so no later run builds it again.
   - **planned:** the PLAN's path and its gate: `ready`, `plan waits for
     you` (with the reason), or the P rule it fails.
   - **failed:** the claim went back, the worktree stays for a look. Work
     already committed on the branch is on origin too and goes into the
     gates on the next run, in any clone. A PLAN that still breaks a P
     rule after its two fix rounds ends here too; it is on the branch
     for the user to fix. When a phase changed `.git/config`, a file in
     `.git/hooks`, or where a worktree finds its git dir, nothing was
     pushed and the claim stays, even when the run is killed later: the
     user looks at the named paths before anything runs again. A draft
     held this way starts its PR text with "Held by `pulse go`"; no run
     takes it up again until the user takes that note out.
   - **limited:** an agent hit its usage limit; its item went back with
     a note, and another agent with a free slot takes it in this run.
     When no other agent is left, the item waits on the ramp for a
     later run, and its note names the branch with the work.
   - **stopped:** the run was stopped (Ctrl-C, SIGTERM) while the item
     was in a phase; its claim went back.
   - **skipped:** its claim went to someone else, its PLAN fails a P
     rule and waits for a person, or its draft is held.

   Each item `pulse go` gives back or holds keeps a note with the
   phase, the reason, and the branch that carries the work: after a
   failed phase, a PLAN that still fails, a usage limit, a stop, and a
   hold for the user. The map shows the first line of a free item's
   note, and whoever takes the item next builds on that branch. Two
   hand-backs leave no note: a planned item that waits (its PLAN for
   the user, or its build for a blocker, a file another item holds, or
   a free slot; the ramp says which), and the claims of a killed run
   that the next start gives back to the ramp.

   The other keys:
   - `took`: items a killed run held; this run ended that run's agents
     and gave the claims back to the ramp.
   - `discovered`: new work the agents wrote down, also in
     `.git/pulse/go/discovered.md` and in the PR. The output gives one
     line per item: the first line of its notes and the path of
     `discovered.md`. After the user agrees, write a spec for each,
     commit and push it, and only then register it with `pulse new
     <kind> "<title>" --spec <path>`: the record needs the spec on
     origin.
   - `integration`: with two ready PRs or more (drafts do not count) the
     run ends by merging their branches in dependency order in a scratch
     worktree and running `verify` there; a conflict names the branch
     that does not merge after the ones before it, a red verify prints
     the end of its output.
   - `unclean`: the worktree of a closed item that holds changes; a
     clean one is removed after its PR was merged.
   - `elsewhere`: items another `pulse go` run of the same login holds
     with a sign of life in the last 30 minutes, a run in another clone.
     An item with a pull request does not count: its claim stays until
     the merge, with no run on it. The start names them in one line and
     runs all the same; the claims decide who builds what.

   The output says more than the report: `closed #n` for an item whose
   pull request was merged since the last run (GitHub closes an item
   only when its PR goes into the default branch; the run closes the
   rest), and per item the tokens, cost, and time its agents reported
   (Claude Code does with `--output-format json`, the default template).
   Every agent phase leaves one line in `.git/pulse/usage.jsonl`.
4. The user merges each ready feature PR (the last stop). Out of a
   draft: fix the named findings on the branch (test first), in the
   item's worktree or pushed from anywhere. The next `pulse go` sees the
   new commits, runs the gates again, renews the PR text, and marks the
   PR ready once all three pass. A fix that changed a frozen spec test
   runs no gate: the PR stays draft and its `spec tests` line names the
   file.

## Agents

Templates live under `[agents]` in `.pulse/config.toml`; `{prompt}` is
replaced by the build instructions for the item:

```toml
agent = "claude"
[agents]
claude = "claude -p --allowedTools {allow} --output-format json --permission-mode acceptEdits {prompt}"
codex = "codex exec --json --sandbox workspace-write --add-dir {gitdir} {prompt}"
```

These are the templates Pulse uses when `[agents]` names none. `{allow}`
becomes the `verify` command without its trailing flags plus `git add`,
`commit`, `status`, `diff`, and `log`; for an item with a PLAN, each
command under the PLAN's `verify:` joins, cut the same way. `{gitdir}`
becomes the shared git directory, so Codex can commit from its
worktree.

Several agents in one run, each with its own slots, keep two
subscriptions busy at once:

```toml
agent = "claude:2,codex:2"      # a bare name gets `cap` slots; `cap` stays the ceiling
```

Each item goes to the agent with the most free slots. An agent that hits
its usage limit gets no new item for the rest of the run, and the item it
was building goes to another agent in the same worktree. One run per
clone: a second `pulse go` refuses to start while one runs, a stopped
run gives its claims back, and after a run that was killed (SIGKILL, a
crash) the next `pulse go` ends its agents and gives its claims back
itself, except an item held for the user after a phase changed
`.git/config` or `.git/hooks`. Further runs of the same login in other
clones share the ramp through claims. The agents claim as the run, so an
agent's own `pulse claim` of its item succeeds; `PULSE_ITEM` names that
item, and a claim, release, or block of any other one exits 1. Codex's sandbox keeps
`.git` read-only; `pulse go` commits what an agent leaves uncommitted.

Headless agents keep the user's permission rules: edits inside their
worktree go through, and shell commands only as far as the template
allows them (`{allow}` for Claude). A project's `.claude/settings.json`
does not reach them, because every worktree is a new folder nobody
trusted. Pulse never bypasses a permission. After every phase `pulse go`
checks `.git/config`, `.git/hooks`, and the files that point a worktree
at its git directory; a change holds the item for the user.
`agent_timeout` (minutes, default 60) stops an agent that hangs, with
its child processes.

## Inside a session instead

Where a headless run is not wanted, the same ramp drives in-session
subagents: `pulse status --json`, claim each row whose `stage` is
`starts next`, start one subagent per item in its own worktree, and
after each finishes run `pulse status --json` again. Subagents never
touch GitHub; the session that started them claims, pushes, and opens
the PRs.
