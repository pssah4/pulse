---
title: /pulse-go
description: Plan and build every ready item in parallel. One worktree and one headless agent per item, refilled as slots free up, with the gates run by a script.
---

# /pulse-go

`/pulse-go` (in Codex `$pulse:pulse-go`) runs `pulse go`, a script that plans and builds everything that can run, in parallel, until the ramp is empty. The model does not decide how much runs at once, so it cannot forget to parallelize. The rules behind the decision are on [Parallel work](../concepts/parallel-work).

[`/pulse-build`](./pulse-build) is how one item gets built; `pulse go` starts that same discipline for every ready item at once, one headless agent per item in its own worktree, checks itself that the spec tests failed before the code, and runs three gates after each build: tests, review, and security audit. Nobody hands items over by hand: what the ramp has released, `pulse go` picks up in ramp order.

## Before the first run

`pulse go` needs `verify` in `.pulse/config.toml`, the command that runs the project's tests: the RED check, the tests gate, and the integration check at the end run it. Without it `pulse go` claims nothing and exits with 2 (`pulse setup --verify "<cmd>"` sets it).

It also checks the agents of the run before it claims anything. An agent that is not installed (neither on `PATH` nor bundled in a VS Code extension of Claude Code or Codex) claims nothing in this run, and the start says so. When no agent is left to build, or the `review_agent` is missing, the run does not start.

## Start a run

| Command | Does |
|---|---|
| `pulse go --dry-run` | shows which items would start, in which phase, on which branch, in which worktree |
| `pulse go` | starts the run in this terminal |
| `pulse go --detach` | starts the run in a session of its own, for the night |

`--agent claude:2,codex:2` and `--cap N` change the agents and the slots for one run; `--json` prints the report as JSON at the end. `--dry-run` claims nothing and starts nothing; it prints `would plan`, `would build`, and `would take up` lines.

`--detach` starts the run apart from this terminal or chat and waits until it holds the clone's run lock and has read the board, at most 10 seconds. Then it prints the pid, the log `.git/pulse/go/run.log`, and the report `.git/pulse/go/report.json`, and returns; `pulse status` shows how far the run got, and `kill <pid>` stops it as Ctrl-C would. A run that refuses to start (no `verify`, a run already in this clone, no agent to build with, a board it cannot read) prints its reason, and `--detach` exits with its code. `/pulse-go` starts the run this way, so it outlives the chat and the shell tool's time limit, and reads the report afterwards. Inside Codex, whose sandbox keeps the network and `.git` closed, `/pulse-go` gives you the command for a terminal instead.

## What a run does

1. **Reads the ramp**: ready items in the team order (`pulse rank`, unranked items by critical path), files disjoint from running work, up to the free slots. Before each round it fetches from origin, at most every 30 seconds, so it sees the PLANs and branches other clones pushed. A draft to take up comes first, then the builds, then the planning jobs.
2. **Plans an item without a PLAN.** An approved item with a ready spec but no PLAN takes a free slot for a planning job, even while its blockers are open. The agent writes the PLAN on the item's branch. A PLAN that fails P1 to P5 goes back to the agent with the findings, for up to two fix rounds; after that the item fails and the PLAN waits on its branch for a person. A PLAN that passes is built in the next round on the same claim when the ramp lets it (with `plan_approval = "auto"`), else the claim goes back until a later round; a risk flag or `effort: L` in the spec, `needs:` in the PLAN, or `plan_approval = "manual"` holds it at `plan waits for you` and gives the claim back.
3. **Claims each item** for this run: it assigns you on GitHub and puts the run's mark on the item, with the files of the item's PLAN, so every clone's ramp keeps other items off them. Of two concurrent claims the older mark wins, and no other session of yours can take the item meanwhile. A claim lost this round is tried again in the next.
4. **Creates a worktree** beside the repository, `<repo>-<n>-<slug>`, on the item's branch. An item that already has a branch, here or pushed from any clone, keeps it; a new one gets `<type>/<n>-<slug>`, started from the base branch as origin has it, or from the blocker's branch for a stacked item. A branch pushed from elsewhere is caught up first. Before a build, the branch merges in its base; when that does not merge, the item fails and names the worktree to resolve it in.
5. **Starts one headless agent per item** with the build instructions, the PLAN, and the spec. The agent writes the spec tests of the PLAN's first wave first (one per requirement), runs them once, and commits them alone as `test: spec tests for #<n>`; from then on they are frozen. Then it works through the PLAN's tasks test-first, commits, writes new work it finds into `DISCOVERED.md`, and touches nothing on GitHub.
6. **Checks RED and runs the gates.** `pulse go` runs `verify` at the commit that froze the spec tests: before the code exists, they must fail. Then the three gates run in order: `tests` (`verify` in the worktree), `review` in a fresh session ([review](./pulse-review), scope branch), and `audit` in another fresh session ([/pulse-audit](./pulse-audit), scope branch against the base). A red gate sends its findings to a fix agent in the same worktree, at most two fix rounds per gate, and after every fix the chain starts again at `tests`. A fix round that fails or times out ends the chain: no further gate runs, and the pull request is a draft that says so. The details are in [the chain after the build](../concepts/verification-gates#the-chain-after-the-build).
7. **Opens one pull request** per item, against the base branch, or against the blocker's branch when it is stacked. Its body has `Closes #<n>`, a `| Gate | Result |` table, the commit the gates ran at, the RED note, the files outside the PLAN, what the agent discovered, and the review and audit reports. It is ready for review only when all three gates passed; otherwise it is a draft that names what is open. Right after, `pulse go` puts the review and audit verdicts on it as comments ([verdicts on the pull request](./pulse-review#verdicts-on-the-pull-request)). The item keeps its claim until the merge, so no later run builds it again. The slot stays busy until the pull request exists; then the run reads the board again and fills it.
8. **Repeats** until nothing is ready and nothing runs. Each item gets at most one planning job and one build per run, so nothing loops.

A build fails when its agent exits with an error, runs longer than `agent_timeout`, or leaves no code commit on the branch (a PLAN alone is none). A failed item gives its claim back with a note, and its worktree stays for a look. One item's failure never stops the others.

You merge each feature's pull request; that merge is the last stop.

**Stacking.** At every parallel level, a feature with exactly one open blocker whose pull request is open and not a draft does not wait for the merge: it starts on the blocker's branch, and its PR targets that branch. After the blocker is merged, the next run moves the stacked PR to the base branch (`gh pr edit --base`). At its start, a run also closes items whose PR was merged into a base branch other than the repository's default, because GitHub closes issues on its own only for the default branch ("closed #n: its pull request was merged"), and removes the clean worktree of every closed item it made; one with changes stays, and the run names it.

## What the team sees while it runs

The board and origin carry the run's progress, so every clone's map shows it ([what the team sees, and when](../concepts/where-things-live#what-the-team-sees-and-when)).

- **A sign of life per phase.** Each phase start (`plan`, `build`, `spec tests`, `tests`, `review`, `audit`, `fix`) puts the phase and the time on the item's claim mark, and a phase that runs long renews them every 10 minutes. A teammate's map shows `building, 4 min ago`; after 30 minutes without one, `no sign of life`. A mark that cannot be written costs a line in the item's log, never the item.
- **A push after every phase.** After an agent phase (plan, build, fix) that ended cleanly, `pulse go` commits what the agent left uncommitted (never `DISCOVERED.md` or `_devprocess/temp/`). Whenever a phase added commits, it pushes the item branch, a fast-forward only. Whoever holds the item next, in any clone, builds on that work. A rejected push stops the item: it fails and gives its claim back.
- **A note on hand-back.** An item the run gives back after a failure, a usage limit, or a stop keeps a note on the board: the phase, the reason, and the branch that carries the work pushed so far. A PLAN that still fails P1 to P5 after its fix rounds leaves one too. The map shows its first line as `last run: ...`, and `pulse show <n>` prints the whole note.

## One run per clone

A second `pulse go` in the same clone refuses to start while one runs (exit 2), so every agent of the clone belongs in one run. A run stopped with Ctrl-C, `kill`, or by closing the terminal stops its agents, gives the claims of the items still running back with a note, and prints the report so far; a second signal does not cut that short.

A run that ended without its cleanup (SIGKILL, a crash, the power) leaves its agents and claims. The next start in the same clone ends those agents, gives the claims of that run back to the ramp, and prints "took over #n from a stopped run"; the loop then claims them anew. An item with a pull request keeps its claim until the merge, and an item held for a person (below) keeps it too.

Runs of your login in other clones share the ramp through claims. When another run of your login has shown a sign of life in the last 30 minutes, the start warns and names its items and their phases; this run starts all the same, and the claims decide who builds what.

## The hold

After every phase, `pulse go` compares the shared git directory's `config`, the files in its `hooks` folder, and the files that tie the worktree to it with their state before the phase. An agent that can write there (Codex with `--add-dir`) could leave a hook that later runs outside every sandbox and shows in no diff. When one of these files changed, the item stops: nothing is pushed, no further phase runs, and the claim stays, even across a hard stop of the run. The report, `pulse status`, and a note on the item name the changed paths. A draft that was taken up gets the same text at the top of its pull request, starting with "Held by `pulse go`". Look at the named paths first. Then `pulse release <n> --take` frees an item without a pull request; a draft keeps its claim, and you take the hold note out of its text.

## A draft taken up

A draft of `pulse go` stays with its claim. Fix its findings on its branch, test first, in the item's worktree or pushed from any clone. The next run sees commits newer than the commit its gates ran at, takes the draft up (`taking up #n`), and runs the gates again from `tests`. It writes the pull request text anew and marks it ready once all three gates pass. Without a new commit, no run touches a draft. A run takes up only a draft that a run under your login holds; while a session of yours works on it, the run keeps out. A fix that changed a frozen spec test runs no gate: the pull request stays draft, and its `spec tests` line names the files.

## Integration at the end

When the run ends and two or more ready pull requests are open (drafts do not count), `pulse go` fetches their branches, merges them into the base branch in dependency order in a scratch worktree, and runs `verify` on the result. A conflict names the branch that does not merge after the ones before it; a red `verify` prints the end of its output. Either one makes the run exit with 1, so a clash between two parallel results shows up before anyone merges.

## The report

The output names each start (`planning #n`, `building #n`, `taking up #n`, with the agent, branch, base, and worktree) and ends with the results:

- **planned**: each PLAN written in this run and its gate: `ready`, or `plan waits for you` with the reason.
- **done**: each finished item with its PR, the result of each gate, the fix rounds, and whether it waits for your merge or stays a draft. With it, the tokens, cost, and time its agents reported as JSON (the built-in templates do).
- **failed**: the reason (an exit code, timed out, no commits, a push that failed, a branch that does not merge with its base, a PLAN that still fails a P rule, a hold, a GitHub error), the worktree, and the log `.git/pulse/go/<n>.log`, one section per phase.
- **limit**: an agent hit its usage limit. It gets no new item in this run, and its item goes to another agent of the run, which continues in the same worktree, or back to the ramp with a note when every agent is spent.
- **skipped**: an item someone else claimed first, a PLAN that fails a P rule and waits for a person, or a held draft.
- **stopped**: an item that was in a phase when the run was stopped.
- **closed**, **took over**, and the kept worktrees of closed items, as above.
- **discovered**: the first line of what each agent wrote into `DISCOVERED.md`. The whole text goes into `.git/pulse/go/discovered.md`, and for a build into its pull request. After you agree, write a spec for each, push it, and register it with `pulse new`.
- **integration**: the branches merged at the end, the first conflict, and the `verify` result.

`.git/pulse/go/report.json` holds the same results. The run writes it after every event, so it keeps what finished even when the run is killed. `run` has the pid, the start, the end, and the signal that stopped the run; `items` has one entry per item with `result` (`planned`, `done`, `failed`, `limited`, `skipped`, `stopped`), `why`, `pr`, `log`, and `at`; `discovered`, `took`, `unclean`, `integration`, and `elsewhere` (the other run's items from the start warning) follow. `pulse status` ends with one line on the last run and one line per failed item. Every agent phase also leaves a line in `.git/pulse/usage.jsonl`, to compare agents and models across runs.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | the run ended and nothing failed |
| `1` | an item failed, a PLAN fails P1 to P5 and waits for a person, or the integration check found a conflict, a red `verify`, or could not run |
| `2` | the run did not start, and the message says why: no `verify`, a run already in this clone, an agent missing from `[agents]`, no installed agent to build or review with, or the board could not be read |
| `128` + signal | the run was stopped: `130` for Ctrl-C, `143` for SIGTERM, `129` for a closed terminal |

`pulse go --detach` returns `0` once the run holds its lock and has read the board; the run's own result is in `report.json` and in `pulse status`. A run that ended before that returns its own code, `2` when it did not start.

## Agents and permissions

The agent command is a template under `[agents]` in `.pulse/config.toml`; `{prompt}` becomes the instructions. Without an `[agents]` table these are the templates:

```toml
agent = "claude"
agent_timeout = 60        # minutes; a hung agent is stopped with its child processes

[agents]
claude = "claude -p --allowedTools {allow} --output-format json --permission-mode acceptEdits {prompt}"
codex = "codex exec --json --sandbox workspace-write --add-dir {gitdir} {prompt}"
```

A headless agent cannot answer a permission prompt, so it runs only what its template allows. `{allow}` lets Claude Code run `verify`, the `verify:` commands of the item's PLAN, and five git commands; `{gitdir}` lets Codex commit from its worktree. [Agent templates](../reference/configuration#agent-templates) says what each covers and how to fix a template copied from an older Pulse. A `verify:` command of the PLAN is allowed only when it starts with a program of `verify` or with a script of the repository, such as `bin/pulse check`; a shell or interpreter given code, a download, `npx`, `env`, or `sudo` never is, and the item log and the pull request name each command left out. An agent missing on `PATH` runs from the newest VS Code extension that bundles it. The review and audit sessions start from `review_agent`, else from the agent that built the item. Pulse never bypasses an approval.

### Two agents at once

With two subscriptions, one run keeps both busy:

```toml
agent = "claude:2,codex:2"    # or: pulse go --agent claude:2,codex:2
```

Each agent gets its own slots; a bare name gets `cap` slots, and `cap` stays the ceiling for the run. Each item goes to the agent with the most free slots. When an agent hits its usage limit, it gets no new item for the rest of the run, and the item it was building goes to another agent, which continues in the same worktree.

## Without headless agents

The same ramp drives in-session subagents: `pulse status --json`, claim each row whose `stage` is `starts next`, start one subagent per item in its own worktree, and run `pulse status --json` again after each finishes. The session that started them claims, pushes, and opens the PRs; subagents never touch GitHub.
