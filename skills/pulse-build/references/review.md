# Review

The brief of the review gate. The builder knows why it wrote each line
and reads its own diff with that knowledge; a reviewer without it reads
what is actually there. So whoever built the item does not review it:
the review runs in a fresh session that sees only the spec, the Plan,
the decisions that apply, and the diff. `pulse go` gives that session
this file with its brief, together with the audit's in one session;
`/pulse-build` gives it to a subagent (its section Done).

1. Read the spec, the Plan with its change log, the system map as the
   base has it (`git show <base>:_devprocess/SYSTEM-MAP.md`; a change the
   branch makes to it is part of the diff), the decision records whose
   "Read When" matches (`_devprocess/decisions/README.md`), and the
   nearest path-local AGENTS.md of each changed area.
2. Read the changes of the branch against its base (`git diff
   <base>...HEAD`). Open the surrounding code where a hunk alone does not
   tell you what it does.
3. Go through the checks below. Every finding names a place, the check,
   and what is wrong. No finding without a place.
4. Write `REVIEW.md` where the brief says: in `pulse go` at the path it
   names beside the checkout, else at the worktree root. Do not change
   code, do not commit, do not touch GitHub.

**Temporary checks.** A script, probe, or fixture you write to confirm
a finding goes under `_devprocess/temp/testing/`, never into the
project's test directories or the repository root. Name it so no test
runner collects it, for example `probe_<topic>.py` (never `test_*.py`
or `*.test.ts`), and run it by path. Delete it before you write the
report. The project's tests are not temporary: leave them as they are.
The session must leave the working tree as it found it: Pulse compares
HEAD and `git status` before and after, and a changed tree voids the
verdict. The comparison leaves out `_devprocess/temp/`, so a probe there
does not void it; a file you move out of the folder does. When
`_devprocess/temp/` is not ignored, add it to `.git/info/exclude` from
the repository root before your first check, so that no agent's
`git add -A` picks up a probe someone forgot:

```bash
git check-ignore -q _devprocess/temp/testing/x || printf '\n_devprocess/temp/\n' >> "$(git rev-parse --git-path info/exclude)"
```

## Checks

| Check | Block when | Note when |
|---|---|---|
| Scope | a file outside the Plan's files without a line in its change log; behaviour the spec does not ask for | |
| Decisions and rules | a decision record or a path-local AGENTS.md rule is broken | |
| System map | the diff changes an entry point, data ownership, an invariant, or a quality goal, and `_devprocess/SYSTEM-MAP.md` does not follow | |
| Criteria | an FR has no spec test, or its spec test changed after `test: spec tests for #<n>`; a test that never checks behaviour the user sees | |
| Lean | a duplicate of code that already exists; dead code (a new symbol without a caller outside its file and tests); an abstraction with one use; a new dependency outside the authorized task | a shorter way with the same result exists |
| Maintainable | | unclear naming, a function doing several jobs, a comment that restates the code |
| Tests | a test that asserts nothing, or mocks the unit under test | slow or brittle tests |
| Security | an obvious hole: a secret in code, unchecked input into a shell, a query, or a path. Name it for the audit (`/pulse-audit`, scope branch) | |

Block only what must change before the result is approved for integration. Everything
else is a note. A review full of notes gets skimmed, and the one finding
that mattered goes with it.

## The report

```
Verdict: block
- [block] src/api.py:40 scope: src/cache.py is outside the Plan and the change log says nothing
- [block] src/api.py:12 lean: duplicate of paginate() in src/util.py
- [note] src/api.py:77 maintainable: `tmp2` says nothing
```

First line `Verdict: pass` or `Verdict: block`: block when at least one
finding blocks. Then one line per finding: `- [block|note] <file>:<line>
<check>: <what>`. `pulse go` keeps the report in the shared git dir,
stamped with the commit it looked at, and publishes the result evidence.

## After the verdict

The builder fixes blocking findings test-first and commits; then the
tests run again, and a fresh review looks again. One fix round for all
the item's gates together;
after that the result stays blocked and its evidence names what is still
open. Notes do not block. The builder may take them along, or ask the
user once whether they become improvement items (a short spec each with
`parent:` set, named by `pulse number --apply`, registered as a draft, then
published on its own `imp/<n>-<slug>` branch from
`refs/remotes/origin/<base>` after `git fetch origin`, then attached with
`pulse new imp ... --spec <path> --issue <n>`).
