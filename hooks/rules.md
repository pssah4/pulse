# Pulse rules

Always on, in every session and every subagent of a project that runs
Pulse. Where the project's own AGENTS.md or CLAUDE.md says otherwise,
the project wins, except for branch names: an item's branch is
`<type>/<n>-<slug>` (`feat`, `imp`, `fix`), because `pulse` finds its
Plan and published result by that name.

## Start

Defer, resume, revoke, handoff, discard and delete are person's levers.
An agent never invokes them or confirms them through the Map. Defer
preserves work and evidence until an explicit resume. An authorized
removal may be prepared by an agent; integration approval and irreversible
issue deletion remain the person's. Never replace these commands with
direct record edits, force pushes or history resets.

1. Read the code first: trace the flow, its callers, and its tests.
2. Read the one decision that applies: `_devprocess/decisions/README.md`
   routes by "Read When". Read the nearest path-specific AGENTS.md
   before you write into its area.
3. Reuse what exists (helper, pattern, dependency) before writing new code.
4. Make the smallest complete change.
5. Run the smallest check that can disprove it.

## Triage

Before changing code, docs, or specs, know what the work is: a new
feature, an improvement on an existing feature, or a fix. If the prompt
does not say, ask exactly one short question. Read-only work needs no
triage. New features start at `/pulse-ba` or `/pulse-re`; improvements
and fixes can go straight to `/pulse-build`. In Codex the commands are
skills: name them to the user as `$pulse:pulse-ba`, `$pulse:pulse-re`,
`$pulse:pulse-build`, and so on.

## Verify before you claim

No completion claim without fresh evidence from this turn.

| Claim | Evidence |
|---|---|
| Tests pass, build works | the output of the test runner itself, its exit code 0 (never that of a pipe around it, such as `\| tail` or `\| sed`), 0 failures |
| Bug fixed | a test that reproduced the bug now passes |
| Feature done | its Activation Path is reachable in code |
| Subagent done | the diff shows the expected change |

Never say "should work", "probably okay", "looks good", "tests should
be green now", or "this should fix it" without having run the check.

After each step, run the tests that step affects, not the whole suite;
use targeted checks while building. Under `pulse go`, the supervisor runs
the full `verify` once on the completed result; its agents run targeted
checks and additional Plan checks that `verify` does not cover. In an
interactive build, run `verify` once before review and audit. Repeat it
only after a relevant change. Startup reads the current base SHA and
project configuration without running a full local test suite before planning.

## Tests first

No production code without a failing test written first. RED: state
the expected failure, run it, quote the actual output. GREEN: the
minimal code that passes. REFACTOR with the tests green. A bug fix
starts with a test that reproduces the bug. Exceptions only with the
user's explicit OK: throwaway prototypes, generated code, configuration.

Fix root causes, not symptoms. After three failed fixes, stop and
re-read the flow before trying a fourth.

## Work state

Every epic, feature, improvement, and fix is a spec in the repository.
The board identifies the item; Pulse's shared state records its claim,
hold, published result and final approval. Only Pulse writes that state.
Use `pulse new ... --draft` or `--spec <path>`, `claim` and `release`.

Approval authorizes integration of a reviewed result at its exact head
and base commits. Regular checked results complete automatically by default.
A person with repository write access may choose manual final approval.
Destructive removal requires its own confirmation. Settings belong to the person,
in their terminal or the Map. Tell the person the command for their own terminal: `pulse approve`,
`revoke`, `done`, `claim --take`, `release --take`, `setup --remove`, or
`setup --mode off`. Agent sessions cannot operate these commands or the
Map's person-only actions.
Queued local actions are not shared authority: only a confirmed action
can authorize integration. Defer and revoke block locally at once while
synchronization proceeds. The Map and CLI show queued, syncing,
confirmed, conflict or error; a conflict requires a fresh preview.

An interactive session may execute an explicitly requested `pulse go`
with its source markers intact. In a terminal it runs in the foreground;
without a TTY Pulse starts or reuses its managed process. Read its receipt
and current report before describing it as running. `pulse go --stop`
requests a controlled stop of the current run. Runner agents and child
sessions never start another runner. Starting it grants no approval.

Work is visible to the team: drafts show their author, runner phases carry
a heartbeat, and a note records preserved work after a stop. A stopped
`pulse go` leaves its work on the item branch or in its retained worktree.
A claim belongs to its session and reserves only the files actually
claimed. Another holder means pick other work. Push after every commit on the item's branch; agents of `pulse go` leave pushes to their
supervisor. Before an ordinary release, publish committed work. Never
remove dirty or unpublished work to make a release succeed. Waiting for
final approval, a dependency or a later retry does not need an idle claim.
Keep the branch, worktree, note and evidence; use the safe release or
stopped-work handoff Pulse provides. A person can request a cross-account
handoff with `pulse release --take <n>`; it stops the current writer and
preserves its work before ownership changes. It grants no integration
approval. Agents never take another session's claim themselves.

Work starts from origin, never from the local base branch: continue the
published item branch, else use the fetched
`refs/remotes/origin/<base>` start point that `pulse claim` names.
Specs, Plan and implementation continue on that one branch. A session
told it no longer holds the item stops, pushes nothing and reports it.
A project hook that rejects a commit, merge or push is a finding: keep
real hooks enabled, fix the cause or report it. Never use `--no-verify`,
an empty `core.hooksPath`, force-push or history resets to get past it.
If Codex says "blocked by policy" or the Pulse guard denies a person's
lever ("Gate levers belong to a person"), name the command
for the person's terminal and do not seek another route. A plain
`claim` or `release` refused by old Codex rules needs
`pulse setup --codex-rules` in the person's terminal.

Ask, do not read: `pulse status`
(all open work in the order it goes out, what each item waits for, and what
starts next; `pulse status <n>` for one item; `--json` for the same as
data). Specs
carry `issue:`, `parent:`, and links to other documents, never state.
A spec's file name starts with its ID (`EPIC-04`, `FEAT-04-02`,
`FIX-04-02-01`): write it under its slug with `parent:` set, and
`pulse number --apply` names it. Never pick a number by hand.
Commits name their item: `Refs: #<n>`.

## Flow

Pulse prepares the authorized work through analysis, spec, Plan, build
and checks without routine approval stops between those phases. Ask only
for missing decisions that the current request does not settle. The sole
integration approval comes after a published result has passed its gates
and is automatic by default. Show its diff, tests, review, audit and
remaining findings. With an explicit manual final approval policy, name
`pulse approve <n>` or `a` in the Map for the person. The approval binds
both result head and base. A changed head or base needs revalidation and a new approval;
old spec approvals, Plan approvals and PR state authorize nothing.

A published spec that passes R1 to R6 can be planned directly from its
item branch. Before handing over a Plan, run `pulse check --plan <path>`
and resolve all P1-P6 findings. A valid published Plan permits building
when dependencies, files and project checks allow it. Bounded planning
repairs preserve the Plan's risks. GitHub CI status does not gate planning
or building. Pulse verifies the completed result before integration.

Record consequential choices (a new dependency, a changed schema,
persisted format or public interface, compatibility and destructive
operations) under `risk:`. The existing task authorization determines
what may be implemented; a risk flag adds no routine Plan approval.
An irreversible action outside that authorization still needs the
person's decision. Work that must come first belongs under `needs:` in
the Plan or `_devprocess/plans/{n}-needs.md`; the runner records blockers
and draft items for it. A headless agent never asks: it preserves work
and reports a decision it cannot resolve within the task.

The item's only Plan is `_devprocess/plans/{n}-{slug}.md`, committed on
its branch. Plan mode displays that file and keeps no separate plan.
One feature, one branch, one traceable integration. Build the Plan's
tasks test-first, then run tests, review and security audit. Review and
audit run in one fresh session, also with `risk: [security]`. There is
one fix round per item; after a relevant fix run tests and the gates
that need fresh evidence. Green review or audit evidence may carry to a
new commit only when its Git tree is identical. If contents change, rerun
both review and audit. A red gate preserves the work and findings
and cannot receive integration approval. Record deviations in the Plan
change log and the result's review evidence.

Pulse publishes the result and evidence and releases inactive claims.
It obtains final approval under the current policy, automatically by default.
Integration serializes the shared base update,
checks the exact approved head and base again, and uses regular Git
merge and push with the project's hooks. A withdrawal or changed state
prevents publication. Completion follows proof that the result reached
the remote base; restarting after that proof does not merge it twice.
Dependencies wait for completed integration, never build on a blocker's
branch. Cut features so each integration can be reviewed on its own.

## Asking the user

One question per turn. A choice between alternatives goes through a
structured question where the tool has one (AskUserQuestion in Claude
Code), else a numbered list; every option shows `+ Pro:` and `- Con:`,
the recommended option comes first, labelled "(Recommended)".

## Artifacts

Write artifacts under `_devprocess/` in the language the user chats in;
ask once if unclear. Code, identifiers, and commit messages stay
English. Keep them short: tables and bullets over prose, a section only
when it has substance, no invented numbers. Active voice, sentence case
headings, real umlauts in German. No em or en dashes, no filler, no
AI vocabulary (landscape, delve, leverage, crucial, robust, seamless,
holistic).

## Opting out

Pulse is advisory. When the user says stop, asks something unrelated,
or opts out, answer directly and do not push back.
