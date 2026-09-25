---
name: pulse-review
user-invocable: false
description: >
  Code review in a fresh session: per item before its pull request leaves
  draft (scope against the PLAN, decisions, frozen spec tests, lean and
  maintainable code, test quality), and across the whole repository every
  two weeks against drift. Use for "review this item", "code review",
  "review the PR", "is the code clean", "repo review", "where is the
  code drifting".
---

# Reviewer

A second look before a person sees the pull request. The builder knows
why it wrote each line and reads its own diff with that knowledge; a
reviewer without it reads what is actually there. So whoever built the
item does not review it: the review runs in a fresh session that sees
only the spec, the PLAN, the decisions that apply, and the diff.

Two modes: **item mode** for one item's changes, **repo mode** for the
whole codebase.

## Scope

`pulse go` and `/pulse-build` always review one item's branch against
its base, without a question. Called by hand, ask first what to review
(a structured question where the tool has one, AskUserQuestion in Claude
Code); recommend `branch` when the current branch belongs to an item,
else `working`. The scopes are the same as `/pulse-audit`'s:

| Scope | What |
|---|---|
| `full` | the whole repository: repo mode below |
| `branch` | the branch against its base (`--base`) |
| `commit` | the last commit |
| `working` | the current work: uncommitted and untracked |
| `staged` | staged changes only |
| `range` | a free `A..B` (`--range`) |

`pulse review [<n>] --scope <scope>` prints the brief for that scope;
`--run` starts it headless. Only a review with an item number keeps its
verdict for that item's pull request.

## Item mode: one item `<n>`

**Is this session fresh?** If this session built #n, do not review it
here. Start a fresh one: a subagent that gets the brief from
`pulse review <n>` (then `pulse review <n> --record`), or
`pulse review <n> --run`, which starts one headless. `/pulse-build` and
`pulse go` do this on their own.

1. `pulse review <n>` prints the brief: spec, PLAN, base, and what the
   script already found (files outside the PLAN).
2. Read the spec, the PLAN with its change log, the decision records
   whose "Read When" matches (`_devprocess/decisions/README.md`), and the
   nearest path-local AGENTS.md of each changed area.
3. Read the changes the brief names (scope branch: `git diff
   <base>...HEAD`). Open the surrounding code where a hunk alone does
   not tell you what it does.
4. Go through the checks below. Every finding names a place, the check,
   and what is wrong. No finding without a place.
5. Write `REVIEW.md` at the worktree root. Do not change code, do not
   commit, do not touch GitHub.

**Temporary checks.** A script, probe, or fixture you write to confirm
a finding goes under `_devprocess/temp/testing/`, never into the
project's test directories or the repository root. Name it so no test
runner collects it, for example `probe_<topic>.py` (never `test_*.py`
or `*.test.ts`), and run it by path. Delete it before you write the
report (in repo mode too). The project's tests are not temporary: leave
them as they are. Here the session must leave the working tree as it
found it: `pulse review <n> --record` compares HEAD and `git status`
before and after, and a changed tree voids the verdict. The comparison
leaves out `_devprocess/temp/`, so a probe there does not void it; a file
you move out of the folder does. When `_devprocess/temp/` is not
ignored, add it to `.git/info/exclude` from the repository root before
your first check, so that no agent's `git add -A` picks up a probe
someone forgot:

```bash
git check-ignore -q _devprocess/temp/testing/x || printf '\n_devprocess/temp/\n' >> "$(git rev-parse --git-path info/exclude)"
```

### Checks

| Check | Block when | Note when |
|---|---|---|
| Scope | a file outside the PLAN's files without a line in its change log; behaviour the spec does not ask for | |
| Decisions and rules | a decision record or a path-local AGENTS.md rule is broken | |
| Criteria | an FR has no spec test, or its spec test changed after `test: spec tests for #<n>`; a test that never checks behaviour the user sees | |
| Lean | a duplicate of code that already exists; dead code (a new symbol without a caller outside its file and tests); an abstraction with one use; a new dependency without the user's approval | a shorter way with the same result exists |
| Maintainable | | unclear naming, a function doing several jobs, a comment that restates the code |
| Tests | a test that asserts nothing, or mocks the unit under test | slow or brittle tests |
| Security | an obvious hole: a secret in code, unchecked input into a shell, a query, or a path. Recommend `/pulse-audit` with branch scope | |

Block only what must change before a person reviews the PR. Everything
else is a note. A review full of notes gets skimmed, and the one finding
that mattered goes with it.

### The report

```
Verdict: block
- [block] src/api.py:40 scope: src/cache.py is outside the PLAN and the change log says nothing
- [block] src/api.py:12 lean: duplicate of paginate() in src/util.py
- [note] src/api.py:77 maintainable: `tmp2` says nothing
```

First line `Verdict: pass` or `Verdict: block`: block when at least one
finding blocks. Then one line per finding: `- [block|note] <file>:<line>
<check>: <what>`. `pulse review <n> --record` keeps the report in the
shared git dir, stamped with the commit it looked at.

### After the verdict

The builder fixes blocking findings test-first and commits, then a fresh
review looks again. At most two fix rounds; after that the pull request
stays draft and its body names what is still open. Notes do not block.
The builder may take them along, or ask the user once whether they
become improvement items (a short spec each, committed and pushed, then
`pulse new imp ... --spec`).

## Repo mode

Every two weeks, before the direction session, and whenever the code
feels like it is drifting. `/pulse` offers it when the newest
`_devprocess/analysis/REVIEW-*.md` is older than two weeks.

1. `pulse check`: what the script sees (links, paths, stubs, caps).
2. Hotspots: files that change most often and grow fastest.
   `git log --since="3 months ago" --name-only --format= | sort | uniq -c | sort -rn | head -20`
   and the largest source files. A file that is both is the first place
   to look.
3. Duplicates: logic that exists twice under different names, often in
   the hotspots.
4. Dead code: symbols without callers outside their file and tests. The
   per-language tooling is in `../pulse-build/references/reachability.md`.
5. Drift: for each decision record, does the code still do what it says?
   The Sources appendix points at the files.
6. Weight: abstractions with one use, dependencies used in one place,
   configuration nobody changes.

Write `_devprocess/analysis/REVIEW-<YYYY-MM-DD>.md`: at most ten
findings, ordered by harm, each with place, evidence, and a suggested
change. Then ask the user once which findings become improvement items;
each gets a short spec, committed on a docs branch and pushed, then
`pulse new imp "<title>" --spec <path>`.

## Keywords
Code review, review, PR review, clean code, maintainability, lean code,
duplicate, dead code, over-engineering, slop, drift, hotspots, repo review
