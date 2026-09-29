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
| Tests pass, build works | the output of the test runner itself, its exit code 0 (never that of a pipe around it, such as `\| tail` or `\| sed`), 0 failures |
| Bug fixed | a test that reproduced the bug now passes |
| Feature done | its Activation Path is reachable in code |
| Subagent done | the diff shows the expected change |

Never say "should work", "probably okay", "looks good", "tests should
be green now", or "this should fix it" without having run the check.

After each step, run the tests that step affects, not the whole suite;
run `verify` once, before the gates, and again only after a change.

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
`--spec <path>`, `claim`, `release`, `approve`.
Approving
says the team wants an item built; only a person decides that, in their
own terminal or the map: an agent session never runs `pulse approve`,
`done`, `claim --take`, `release --take`, `pulse go`,
`setup --remove`, or `setup --mode off`, nor `gh pr merge` or `gh pr ready`, and the command
line and the Pulse guard refuse them.
Where one waits, tell the person which gate waits and how they pull the
lever. Content
never goes into the record, and nobody edits it with `gh` directly.
Work on the board is visible to the team: drafts show a BA or spec in
progress and who writes it, a claim carries its phase and, while
`pulse go` runs it, a heartbeat, and a note stays on an item after a
stopped run. A claim belongs to the session that made it: another session, even under
the same login, gets exit 1 and picks other work; the refusal names the
command that frees the item. A stopped `pulse go` leaves its work on the
item branch and a note on the item; whoever goes on builds on that
branch. Push after every commit, on an item branch and a docs branch
alike: work only this clone has is invisible to the team and lost to
whoever takes over, and the stop hook names a missing push (an agent of
`pulse go` leaves the push to its run). A project hook that refuses a
commit or push is a finding: never skip it with `--no-verify`; fix the
cause or tell the person. A session told that it no longer
holds its item (`pulse claim` or `pulse release` names another holder)
stops the work on it, pushes nothing of it, and tells the person.
`pulse release <n>` refuses while the item's branch has commits only
this clone has: push them first. `pulse release --take <n>`
hands a claim over, another person's or one of an ended session of
yours: their assignee and marks go, and a comment names who did it.
`pulse claim --take <n>` takes over from a session of your own that has
ended and holds the item for the terminal it is typed in. Both are
a person's: tell the person the command for their own terminal, then
claim as usual. Work starts from origin, never from the local
base branch, which may lag behind what others pushed: `pulse claim`
fetches and names the start point, and a docs branch starts from
`refs/remotes/origin/<base>` after `git fetch origin`. When Codex refuses a command
with "blocked by policy", or the Pulse guard denies one ("Gate levers
belong to a person"), it is a person's lever: tell the person which gate
waits and the command for their own terminal, and look for no other
way. A plain `claim` or `release` that Codex refuses or asks about means
the Codex rules are older than this Pulse: the person runs
`pulse setup --codex-rules` again.
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

Pulse stops for a person at these points and runs on everywhere else:
the business analysis is approved; a person reads the spec and approves
it (`pulse approve`, or `a` in the map, which means build it: a spec
approved in the `/pulse-re` session is planned there at once, any other
in ramp order; approving writes the approval and nothing else, and a spec
not yet on the base branch is merged into the base branch first by
`pulse go`, where agents plan from it: its open docs pull request, once
every spec in it passes R1 to R6 and its checks pass); a person reads
each PLAN once it is pushed and approves it (`pulse approve <n>` again,
or `a` in the map: the approval binds the PLAN and the spec as origin
has them, and a PLAN or spec changed since waits again; `risk:` in the
spec or the PLAN asks for a closer look); an item `pulse go` gave up on (the label
`pulse:failed`, with a comment that says why): no run takes it until the
person takes the label off with `pulse approve <n>` in their own terminal;
the merge of each feature's pull request into the base branch. Between these
points, do not ask whether to go on: finish the phase and start the
next one.

Steps that would need a person's OK (a new dependency, a changed
schema, persisted format, or public interface, broken backward
compatibility, a departure from a current decision, anything destructive
such as deleting data, force-push, or rewriting history) belong in the
PLAN under `risk:`, which asks the person who approves the PLAN for a closer look, and an approved PLAN covers them. Work that has to be built first goes under `needs:`,
in the PLAN or, found while building, in `_devprocess/plans/{n}-needs.md`:
`pulse go` makes each entry a blocker and a new title a draft item, and
never holds a PLAN for it. When the build meets a step the PLAN does not
cover, ask the user. A session without a person (an agent `pulse go`
started) never asks: it leaves that step undone and names it in its
summary.

An item's plan is its PLAN file `_devprocess/plans/{n}-{slug}.md`,
committed on the item's branch. A plan mode, where the agent has one, only shows that
PLAN for approval and keeps no plan of its own: a plan outside the
repository does not count.

One feature, one branch, one pull request. On its branch the build works
through the PLAN's tasks; then three gates run in order: the project's
tests (`verify` in `.pulse/config.toml`; `pulse go` does not start
without it), a review, and a security audit of the branch, the last
two in one fresh session, also with `risk: [security]`. A red gate gets
one fix round per item, and after it the tests run again and only the
gates that were red. A session opens the pull request as a draft; when all three
passed (each on the commit its gate table names: a gate that stayed green
after a fix did not run again), `pulse go` marks its own ready, and in a
session you tell the person, who marks it ready and merges it. A red
gate keeps it draft, and its body names what is open.
A departure from the PLAN does not: it goes into the pull request under
`## Deviations from the PLAN`, for the person who merges. A feature
whose blocker is not merged yet waits for that merge; nothing builds on
a blocker's branch.

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
