# Pulse rules

Always on, in every session and subagent of a project that runs Pulse.
Where the project's own AGENTS.md or CLAUDE.md says otherwise, the
project wins, except for branch names: an item's branch is
`<type>/<n>-<slug>` (`feat`, `imp`, `fix`), because `pulse` finds the
item by that name.

## Start

Defer, resume, revoke, handoff, discard and delete are the person's
levers, as are settings: an agent pulls them only under the person's
`pulse levers` grant, never in the Map or through record edits, force
pushes or history resets. Tell the
person the command for their own terminal: `pulse approve`, `revoke`,
`done`, `claim --take`, `release --take`, `setup --remove`, or
`setup --mode off`. An agent may prepare an authorized removal.

Read the code first (the flow, its callers, its tests), the one
decision that applies (`_devprocess/decisions/README.md` routes by
"Read When") and the nearest path-specific AGENTS.md before writing
into its area. Reuse what exists, make the smallest complete change,
and run the smallest check that can disprove it.

## Triage

Before changing code, docs, or specs, know whether the work is a new
feature, an improvement, or a fix; if the prompt does not say, ask one
short question. Read-only work needs no triage. New features start at
`/pulse-ba` or `/pulse-re`; improvements and fixes can go straight to
`/pulse-build`. In Codex these are skills: `$pulse:pulse-ba`,
`$pulse:pulse-re`, `$pulse:pulse-build`.

## Verify before you claim

No completion claim without fresh evidence from this turn: the test
runner's own exit code 0 and 0 failures (never a pipe's, such as
`| tail`), the passing test that reproduced a bug, a feature's
Activation Path reachable in code, a subagent's diff. Never say "should
work" or "looks good" without running the check.

After each step, run the tests that step affects, not the whole suite.
Under `pulse go`, the supervisor runs the full `verify` once on the
completed result and its agents run targeted checks; in an interactive
build, run `verify` once before review and audit, again only after a
relevant change.

## Tests first

No production code without a failing test written first. RED: state
the expected failure, run it, quote the actual output. GREEN: the
minimal code that passes. REFACTOR with the tests green. A bug fix
starts with a test that reproduces the bug. Exceptions only with the
user's explicit OK: throwaway prototypes, generated code, configuration.
Fix the root cause; after three failed fixes, stop and re-read the
flow.

## Work state

Every epic, feature, improvement, and fix is a spec in the repository.
The board identifies the item; Pulse's shared state records its claim,
hold, published result and final approval. Only Pulse writes that state.
Use `pulse new ... --draft` or `--spec <path>`, `claim` and `release`.

An interactive session starts `pulse go` only on explicit request,
source markers intact, and reads its receipt before calling it running;
runner agents and child sessions never start another runner.

Work is visible to the team: drafts show their author, runner phases
carry a heartbeat, and a note records preserved work after a stop. A
stopped `pulse go` leaves its work on the item branch or in its retained
worktree. A claim belongs to its session and reserves only its files;
another holder means pick other work. Commit and merge only on the
item's branch, never on the base or default branch. Push after every
commit (agents of `pulse go` leave that to their supervisor).
Never remove dirty or unpublished work to make a release succeed. A
person can request a handoff with `pulse release --take <n>`. Agents
never take another session's claim themselves.

Work starts from origin, never from the local base branch: continue the
published item branch, else the fetched `refs/remotes/origin/<base>`
start point that `pulse claim` names. Specs, Plan and implementation
continue on that one branch. A session told it no longer holds the item
stops, pushes nothing and reports it. A project hook that rejects a
commit, merge or push is a finding: fix the cause or report it, never
bypass it (`--no-verify`, empty `core.hooksPath`, force-push, history
resets). If Codex says "blocked by policy" or the Pulse guard denies a
person's lever ("Gate levers belong to a person"), name the command for
the person's terminal and do not seek another route.

Ask `pulse status` what is open and what each item waits for. Specs
carry `issue:`, `parent:` and links, never state. Write a new spec under
its slug with `parent:` set; `pulse number --apply` adds its ID. Never
pick a number by hand. Commits name their item: `Refs: #<n>`.

## Flow

Pulse prepares the authorized work through analysis, spec, Plan, build
and checks without routine approval stops; ask only for decisions the
request leaves open. The one integration approval comes after the gates
and is automatic by default; show the result's diff, tests, review,
audit and open findings. Under a manual final approval policy, name
`pulse approve <n>` or `a` in the Map for the person. A changed head or
base needs revalidation and a new approval; old approvals and PR state
authorize nothing.

A published spec that passes R1 to R6 can be planned directly from its
item branch. Before handing over a Plan, run `pulse check --plan <path>`
and resolve all P1-P6 findings. A valid published Plan permits building
when dependencies, files and project checks allow it. GitHub CI status
does not gate planning or building.

Record consequential choices (a new dependency, a changed schema,
format or public interface, destructive operations) under `risk:`. A
risk flag adds no routine Plan approval to the task's authorization; an
irreversible action outside that authorization needs the person's
decision. Work that must come first goes under `needs:` in the Plan or
`_devprocess/plans/{n}-needs.md`. A headless agent never asks: it
preserves work and reports what it cannot decide.

The item's only Plan is `_devprocess/plans/{n}-{slug}.md`, committed on
its branch. Plan mode displays that file and keeps no separate plan.
Build the tasks test-first, then run tests, review and security audit.
Review and audit run in one fresh session, also with `risk: [security]`.
There is one fix round per item; after it, rerun what needs fresh
evidence. Gate evidence carries to a new commit only with an identical
Git tree. A red gate preserves the work and findings and cannot receive
integration approval. Record deviations in the Plan change log and the
result's review evidence.

Completion follows proof that the result reached the remote base.
Dependencies wait for completed integration, never build on a blocker's
branch.

## Asking the user

One question per turn. Offer alternatives as a structured question
where the tool has one (AskUserQuestion in Claude Code), else a
numbered list; each option with `+ Pro:` and `- Con:`, the
recommended one first as "(Recommended)".

## Artifacts

Write artifacts under `_devprocess/` in the language the user chats in;
ask once if unclear. Code, identifiers, and commit messages stay
English. Keep them short, tables over prose, no invented numbers.
Active voice, sentence case headings, real umlauts in German.
No em or en dashes, no filler, no AI vocabulary (landscape, delve,
leverage, crucial, robust, seamless, holistic).

## Opting out

Pulse is advisory. When the user says stop, asks something unrelated,
or opts out, answer directly without pushback.
