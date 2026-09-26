# Pulse rules

Always on, in every session and every subagent of a project that runs
Pulse. Where the project's own AGENTS.md or CLAUDE.md says otherwise,
the project wins, except for branch names: an item's branch is
`<type>/<n>-<slug>` (`feat`, `imp`, `fix`), because `pulse` finds its
PLAN and pull request by that name.

## Start

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
| Tests pass, build works | the command's output, exit code 0, 0 failures |
| Bug fixed | a test that reproduced the bug now passes |
| Feature done | its Activation Path is reachable in code |
| Subagent done | the diff shows the expected change |

Never say "should work", "probably okay", "looks good", "tests should
be green now", or "this should fix it" without having run the check.

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
Its state (draft, approved, taken, blocked, done) is a small record on
the board on GitHub that only `pulse` writes: `pulse new ... --draft` or
`--spec <path>`, `claim`, `beat`, `release`, `done`, `block`, `approve`,
`approve-plan`, `rank`. Approving
says the team wants an item built; only a person decides that, and an
agent approves nothing on its own, neither an item nor a PLAN. Content
never goes into the record, and nobody edits it with `gh` directly.
Work on the board is visible to the team: drafts show a BA or spec in
progress and who writes it, a claim carries its phase and a heartbeat
(`pulse beat`), and a note stays on an item after a stopped run. A
claim belongs to the session that made it: another session, even under
the same login, gets exit 1 and picks other work; the refusal names the
command that frees the item. A stopped `pulse go` leaves its work on the
item branch and a note on the item; whoever goes on builds on that
branch. `pulse release --take <n>` hands another
person's claim over: their assignee and marks go, and a comment names
who did it; then claim as usual. `pulse claim --take <n>` takes over
from a session of your own that has ended. An agent runs either only
after the user says yes. When Codex refuses a `pulse` command with
"approval required by policy", the session runs in Full access and
cannot ask: give the person the command for their own terminal, or ask
them to switch Codex to a mode that asks, and look for no other way. A
claim made there belongs to that terminal: in place of `claim --take`,
the person runs `pulse release --take <n>`, then you claim as usual. A
refused plain `claim` or `release` means the Codex rules are older than
this Pulse: the person runs `pulse setup --codex-rules` again.
Ask, do not read: `pulse status`
(all open work in the team order, what each item waits for, and what
starts next; `--json` for the same as data), `pulse show <n>`. Specs
carry `issue:`, `parent:`, and links to other documents, never state.
A spec's file name starts with its ID (`EPIC-04`, `FEAT-04-02`,
`FIX-04-02-01`): write it under its slug with `parent:` set, and
`pulse number --apply` names it. Never pick a number by hand.
Commits name their item: `Refs: #<n>`.

## Flow

Pulse stops for a person at these points and runs on everywhere else:
the business analysis is approved; a person reads the spec and approves
it (the person merges its pull request into the base branch, where
agents plan from it, then runs `pulse approve`, which means build it:
planning and the build follow in ramp order); a PLAN only when something
holds it (a risk flag or effort L in the spec, `needs:` in the PLAN, or
`plan_approval = "manual"`; then `pulse approve-plan <n>`); the merge of
each feature's pull request into the base branch. `pulse rank` steers
the order at any time and stops nothing. Between these points, do not
ask whether to go on: finish the phase and start the next one.

Steps that would need a person's OK (a new dependency, a changed
schema, persisted format, or public interface, broken backward
compatibility, a departure from a current decision, anything destructive
such as deleting data, force-push, or rewriting history) belong in the
PLAN: a risk flag in the spec or an entry under `needs:` holds the PLAN
for a person, and an approved PLAN covers them. When the build meets
one the PLAN does not cover, ask the user. A session without a person
(an agent `pulse go` started) never asks: it leaves that step undone and
writes it into DISCOVERED.md at the worktree root.

An item's plan is its PLAN file `_devprocess/plans/{n}-{slug}.md`,
committed on the item's branch. A plan mode, where the agent has one, only shows that
PLAN for approval and keeps no plan of its own: a plan outside the
repository does not count.

One feature, one branch, one pull request. On its branch the build works
through the PLAN's tasks; then three gates run in order: the project's
tests (`verify` in `.pulse/config.toml`; `pulse go` does not start
without it), a review, and a security audit of the branch, the last
two in fresh sessions (`pulse review <n>`, `pulse audit <n>`). A red
gate gets a fix round, and after every fix the gates start again at the
tests. The pull request is ready when all three passed on its last
commit; only a red gate keeps it draft, and its body names what is open.
A departure from the PLAN does not: it goes into the pull request under
`## Deviations from the PLAN`, for the person who merges. A feature
whose one blocker has a ready pull request builds on that branch and
targets it; after the blocker's merge it moves to the base branch.

Cut features so that each merge reads well on its own: one feature, one
traceable merge, never a monolith.

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
