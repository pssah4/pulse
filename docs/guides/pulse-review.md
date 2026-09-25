---
title: Review
description: A second look in a fresh session before a pull request leaves draft, and a repository review every two weeks against drift.
---

# Review

A coding agent that reviews its own diff reads it with everything it knew while writing it, and misses what a stranger would see. The review gives every item a reviewer that did not build it: a fresh session that sees only the spec, the PLAN, the decisions that apply, and the diff. It runs before the pull request leaves draft, so the person who reviews the PR spends their time on direction and architecture, not on duplicates and dead code.

`/pulse-build` (in Codex `$pulse:pulse-build`) and `pulse go` start the review on their own, as the second gate after the tests, and never ask. The review runs as a step of these commands: the `pulse-review` skill carries `user-invocable: false` and stays out of the command menu (Codex does not read that field and still lists it). For an item built outside Pulse, for any other set of changes, or for the repository review, ask the agent for a review, or run `pulse review` below.

## Scope

Started by hand, the reviewer first asks what to review. `pulse review [<n>] --scope <scope>` prints the brief for that scope:

| Scope | What |
|---|---|
| `full` | the whole repository: repository mode below |
| `branch` | the branch against its base (`--base REF`, default the base branch) |
| `commit` | the last commit |
| `working` | the current work, uncommitted and untracked |
| `staged` | staged changes only |
| `range` | a free `A..B` (`--range A..B`) |

The default is `branch` with an item number and `working` without one. Only a review with an item number keeps its verdict for that item's pull request.

## Item mode

| Command | Does |
|---|---|
| `pulse review 12` | prints the brief for a fresh session, plus what the script already found |
| `pulse review 12 --run` | starts the reviewer headless and keeps its verdict |
| `pulse review 12 --record` | keeps the REVIEW.md a subagent wrote |
| `pulse review 12 --publish` | puts the kept verdicts for HEAD on the branch's open pull request |

The brief names the spec, the PLAN, and the base branch, and lists what a script can see without judgment: files the diff touches that the PLAN does not list (a directory in the PLAN covers what is in it; changes under `_devprocess/` are writeback and never count). It also says whether Pulse ran the project's tests at HEAD: in `pulse go` it did, so the reviewer does not run them again; by hand it says `tests: skipped`. The reviewer goes through the checks and writes `REVIEW.md`:

| Check | Blocks when |
|---|---|
| Scope | a file outside the PLAN without a line in its change log, or behaviour the spec does not ask for |
| Decisions and rules | a decision record or a path-local `AGENTS.md` rule is broken |
| Criteria | a success criterion has no test, or its test never checks what the user sees |
| Lean | a duplicate, dead code, an abstraction with one use, a new dependency nobody approved |
| Tests | a test that asserts nothing, or mocks the unit it claims to test |
| Security | an obvious hole; the reviewer then recommends [`/pulse-audit`](./pulse-audit) with branch scope |

Naming, long functions, and comments that restate the code are notes: they never block, so the report stays short enough to be read.

```
Verdict: block
- [block] src/api.py:40 scope: src/cache.py is outside the PLAN and the change log says nothing
- [note] src/api.py:77 maintainable: `tmp2` says nothing
```

With an item number, `--run` and `--record` keep the report in `.git/pulse/reviews/<n>.md`, stamped with the commit the reviewer saw; `--record` and `--publish` need one, and only one of `--run`, `--record`, and `--publish` goes in a call. `--agent` picks another template from `[agents]` (default: `review_agent`, else `agent`), `--json` prints the result as JSON. The exit code is 0 for pass, 1 for block, 2 when the reviewer gave no verdict or the call was wrong.

## What happens with the verdict

- **pass**: the chain goes on to the security audit ([/pulse-audit](./pulse-audit)). The pull request is ready for review only when the tests, the review, and the audit all passed on its last commit.
- **block**: the builder fixes the blocking findings test-first and commits, and the chain starts again at the tests, so a fresh review looks again. After two fix rounds the pull request stays draft and its body says what is still open.
- **no verdict**: the session failed, timed out, changed the branch, or wrote no `Verdict:` line. No fix round starts; the pull request stays draft and says why.

When a pull request's last commit has no review or no audit, or the agent just opened one without them, the Pulse Stop hook asks the agent to run what is missing before it hands back. A reviewer that changes the branch itself, by a commit or an edit, gets no verdict. The reviewer can be a different model than the builder: set `review_agent` in `.pulse/config.toml` to another template under `[agents]` ([configuration](../reference/configuration)).

A check the reviewer writes to confirm a finding, such as a reproduction or a probe, goes under `_devprocess/temp/testing/` with a name no test runner collects, and is deleted before the report. The verdict's before-and-after comparison leaves that folder out. When the folder is not ignored, the reviewer adds it to `.git/info/exclude`, which changes no file of the branch and keeps a forgotten probe out of an agent's `git add -A`.

## Verdicts on the pull request

A kept verdict lives in the clone that ran the review. Once the item's branch has an open pull request, `--run` and `--record` also put the verdict on it as a comment, `Pulse review: pass for <commit>.` with a hidden marker, one per gate and commit. `--publish` does the same for the review and audit verdicts kept for HEAD before the pull request existed, all in one comment, on the pull request of the branch checked out where you run it; `/pulse-build` runs it right after it opens the pull request, and `pulse go` does the same step after its own. When GitHub does not answer, `--run` and `--record` still keep the verdict, add `not published on the PR` with GitHub's error, and exit by the verdict; `--publish` stops with `pulse:` and GitHub's error and exit code 2. The kept verdict stays as it is either way, so `--publish` can run again later. With nothing to put on a pull request (no verdict kept for HEAD, no open pull request, or every verdict already on it), `--publish` says `nothing new for an open PR of this branch` and exits with 0.

Whoever holds the item next, in another clone, finds the verdicts there: without a kept verdict of its own, Pulse reads the newest marker on the item's open pull request. Only markers from people who can push to the repository count (owner, member, collaborator), since anyone may comment on a pull request.

## Repository mode

The brief for a fresh session over the whole repository:

```bash
pulse review --scope full
```

A single diff never shows drift: the same helper written a third time in another module, a decision the code quietly stopped following, a file that grows every week. Every two weeks, before the direction session of the [operating model](../operating-model), the repository review looks for exactly that:

1. `pulse check` for what a script sees.
2. Hotspots: the files that change most often and grow fastest.
3. Duplicates, dead code, abstractions with one use, dependencies used in one place.
4. Drift: for each decision record, does the code still do what it says?

The result is `_devprocess/analysis/REVIEW-<date>.md` with at most ten findings, ordered by harm. You decide which ones become improvement items. [`/pulse`](./pulse) recommends the next repository review when the last one is older than two weeks.

## See also

- [/pulse-build](./pulse-build): where the item review sits in the build
- [/pulse-go](./pulse-go): the review gate of a parallel run
- [/pulse-audit](./pulse-audit): the gate after the review
- [Verification gates](../concepts/verification-gates): what counts as done
