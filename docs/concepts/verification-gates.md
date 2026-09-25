---
title: Verification gates
description: The "no completion without fresh evidence" rule that keeps AI agents from claiming success they did not check, and the chain of gates every item passes before its pull request is ready.
---

# Verification gates

The most common failure mode of AI coding sessions is hallucinating
success. The agent says "tests are green", "the build works", "the
bug is fixed", without actually having run the verification command
in that message. Pulse puts a verification gate into every session and
every subagent, and `/pulse-build` adds the reachability steps.

## The rule

> No completion claims without fresh verification evidence.
>
> If the agent has not run the verification command in this message,
> it cannot claim the task is successful.

The Pulse hooks inject this rule at session start and into every
subagent, so it holds without any skill loaded. When a turn edited code
but ran no test or build command, the Stop hook reminds the agent once
before it hands back.

## The gate function

Seven steps, all mandatory. Steps 1 to 5 verify the claim ("tests
pass", "build works", "bug fixed"). Steps 6 and 7 verify that the new
code is reachable and that a user or caller can actually trigger the
FEATURE.

1. **Identify** which command proves the claim
   - "Tests pass" -> a concrete test command with path
   - "Build works" -> a concrete build command
   - "Bug fixed" -> the test reproducing the original symptom
2. **Run** the command fully, not cached, not partial
3. **Read** the complete output, check the exit code, count failures
4. **Verify** the output actually confirms the claim
5. **Claim** the status only now, with the evidence
6. **Reachability check** (subtype-aware): every new
   top-level symbol introduced this session has a caller outside its
   definition file and outside test files, OR is exported as a public
   API entry point for `subtype: library` FEATUREs. A class that
   compiles but is never called fails this step.
7. **Activation-path check**: the `Type` and
   `Identifier` claimed in the FEATURE's `## Activation Path` section
   actually exist in the code (route registered, command registered,
   public symbol exported, etc.). The activation path string is a grep
   target, not a promise.

Skipping any step is lying, not verifying.

Steps 6 and 7 close a drift mode where backend modules existed as
syntactic classes without callers, while the FEATURE was marked Done
because tests and build passed. `/pulse-re` makes every feature name
its Activation Path, `pulse check` rule C6 flags a feature spec without
one, and `/pulse-build` proves it before the feature closes.

The reachability tooling that step 6 uses is per-language. The
[reachability-by-stack reference](../reference/reachability-by-stack)
lists concrete commands for TypeScript, JavaScript, Python, Go, Rust,
React, R, plus an Obsidian-plugin TypeScript sub-profile.

## Forbidden language

Before fresh verification, these phrases are forbidden:

- "should work"
- "probably okay"
- "looks good"
- "tests should be green now"
- "the change should fix the bug"
- any statement that implies success without evidence

## Common failures: what is not enough

| Claim | What is not sufficient | What is sufficient |
|---|---|---|
| Tests pass | "Looks like tests should pass" | Test command output with 0 failures |
| Linter clean | "Linter passed earlier" | Linter output with 0 errors |
| Build works | "Linter passed" | Build command with exit code 0 |
| Bug fixed | "Code changed, assumed fixed" | Test reproducing the original symptom passes |
| Subagent done | "Subagent reported success" | VCS diff shows the expected changes |
| Requirements met | "Tests pass, phase complete" | Line-by-line checklist against the plan |

## Regression test cycle

For bug fixes, a stricter variant applies: the 6-step regression
cycle.

1. Write the regression test reproducing the bug behavior
2. **Run 1**: test MUST pass (because the fix is already in)
3. Temporarily revert the fix (`git stash` or code revert)
4. **Run 2**: test MUST FAIL. This proves the test actually catches the bug.
5. Restore the fix
6. **Run 3**: test MUST pass again

Only when all three runs produce the expected result is the bug
marked as resolved and the regression test marked as valid. The fix
spec's "Regression test" section notes the date of the cycle, and the
pull request that closes the item carries the test.

Without this cycle, a regression test might always pass regardless of
the fix. You would never know it is not actually catching the bug.

## Why this matters

AI agents are helpful by default. They want to report success. They
try to make the user happy. That helpfulness is valuable, but it makes
agents bad at verification. They will round up a "probably works" into
"done" if you let them.

Verification gates force the agent to be honest by default. You
cannot claim success without evidence. The command has to run, the
output has to be read, the verification has to succeed. No shortcuts.

## The chain after the build

Fresh evidence proves that the code does what the builder claims. It
does not prove that the tests came first, that the code should look the
way it does, or that it is safe. So every item passes a chain of gates
before its pull request leaves draft. `pulse go` runs the chain as a
script, so no agent can skip a step or declare one passed; `/pulse-build`
follows the same order in your session ([/pulse-build](../guides/pulse-build#done)).
`pulse go` does not start without a `verify` command in
`.pulse/config.toml`: the RED check and the tests gate need it.

1. **Plan gate.** An item without a PLAN gets a planning agent first. The
   PLAN must pass P1 to P5: the frontmatter names issue, spec, files, and
   verify; every requirement and success criterion has a task, and every
   requirement its spec test in the first wave; every task names its
   files and a check; the tasks of one wave touch different files; no
   placeholder is left. A PLAN that fails goes back to the planner with
   the findings, for up to two fix rounds; after that the item fails and
   the PLAN waits on its branch for a person. A PLAN that passes goes on
   to the build, unless something holds it for `pulse approve-plan`: a
   risk flag or `effort: L` in the spec, `needs:` in the PLAN, or
   `plan_approval = "manual"`.
2. **Spec tests, frozen.** The builder writes the spec tests of the
   PLAN's first wave, one per requirement, and commits them alone as
   `test: spec tests for #<n>`. From that commit on they are frozen.
   After the build and after every fix round, `pulse go` checks them
   line by line: every run of lines the freeze commit added must still
   stand at HEAD, unchanged and in one piece. An older test in the same
   file may go or change. A frozen line that changed gets a fix round
   ("restore them and change the code instead"); once the rounds are
   spent, the pull request opens as a draft that names the files, and no
   gate runs, because bent tests prove nothing.
3. **RED check.** After the build, `pulse go` checks out the freeze
   commit in a scratch worktree and runs `verify` there, whatever the
   agent reported: before the code exists, the tests must fail. When they
   fail, the pull request says "RED evidenced". When they pass, the
   builder gets up to two fix rounds ("spec tests must fail first"),
   shared with the rounds for changed spec tests, and the RED check runs
   again after each; when they still pass, or the check timed out, the
   pull request says "RED not evidenced". Without a freeze
   commit it says "No spec-test commit, RED not evidenced". A missing
   RED is a note for the person who merges and makes no draft on its
   own: the gates follow. They do not when a fix round itself fails or
   times out. Then no gate runs, and the item ends as a draft pull
   request that says "The fix round for spec tests ended early" with
   the reason.
4. **Leftovers committed.** Before any gate judges the branch, `pulse go`
   commits what the agent left uncommitted (never `DISCOVERED.md` or
   `_devprocess/temp/`), so the tests, the review, and the audit all
   judge the same commit. A phase that committed pushes the item branch
   at once, so whoever holds the item next builds on the work.
5. **Tests.** The `verify` command runs in the item's worktree.
6. **Review.** A fresh session that did not build the item checks the
   changes against the spec, the PLAN, and the decisions
   ([review](../guides/pulse-review)). Its brief says the tests passed
   at HEAD, so it does not run them again.
7. **Security audit.** Pulse runs the scanner itself, with dependency
   advisories live from OSV, and a fresh session triages the result
   ([/pulse-audit](../guides/pulse-audit)). A report without a
   `Coverage:` line, without a scan of the commit it judges, or with a
   pass while the OSV lookup failed or left a lockfile unread
   (`partial`) and the Coverage line does not say `SCA unavailable`
   gives no verdict
   ([the Coverage rule](../guides/pulse-audit#the-coverage-rule)).

**Fix rounds.** Red tests, a blocking review, and a blocking audit each
get up to two fix rounds. A fix agent gets the blocking findings (for
the tests, the end of their output), works test first, and commits;
then the chain starts again with the frozen-test check and the tests,
so a fresh review and a fresh audit look again. A fix round that fails
or times out ends the chain the same way as under the RED check: no
further gate, a draft that names the round. A session that gives no
verdict (it failed, timed out, changed the branch, or wrote no verdict
line) gets no fix round.

**The pull request.** One per item, `Closes #<n>`, against the base
branch, or against the blocker's branch when the item is stacked on it.
It is ready when every gate passed, and a draft otherwise. Its text
gives the reasons: a table of the gates with their results and the fix
rounds spent, the commit the gates ran at, the RED note, the files that
depart from the PLAN, the work the agent discovered, and the review and
audit reports. The test output stays in the local log
(`.git/pulse/go/<n>.log`), because a test may print what a pull request
must not. Once the pull request exists, `pulse go` puts the review and
audit verdicts for its last commit on it as comments, one per gate, so
whoever holds the item next, in another clone, finds them
([verdicts on the pull request](../guides/pulse-review#verdicts-on-the-pull-request)).
When GitHub refuses them, the pull request stays as it is and the item's
log says so. The item keeps its claim until the merge.

**A draft taken up.** When a draft of `pulse go` gets new commits after
its gates ran (you fixed it, in this clone or pushed from another), the
next run takes it up: the frozen-test check, then the gates from the
tests. The text is written anew, and the pull request turns ready once
every gate passes. Without a new commit, no run touches a draft. A run
takes up only a draft that a run under your login holds; while a session
of yours works on it, the run keeps out.

**The hold.** After every phase, `pulse go` compares the shared git
directory's `config`, the files in its `hooks` folder, and the files
that tie the worktree to it (`commondir`, `config.worktree`, the
worktree's `.git`) with their state before the phase. An agent that can
write there (Codex with `--add-dir`) could leave a hook that runs later
outside every sandbox and shows in no diff. When one of these files
changed, the item stops: nothing is pushed, no further phase runs, the
claim stays, and the run's report and `pulse status` name the changed
paths. A draft that was taken up gets the same note at the top of its
text, and no run takes it up again until a person has looked and
removed that note.

**Integration at the end.** When a run ends, and two or more ready pull
requests are open, `pulse go` merges their branches into the base branch
in dependency order, in a scratch worktree, and runs `verify` on the
result. A conflict or a red `verify` between parallel work shows up
before anyone merges: the run's output and its report name the branches
merged, the first conflict, and the end of the test output, and the run
exits with 1.

## Where the rule is enforced

- **Every session and every subagent**: the rule arrives with the
  Pulse hooks; the Stop hook catches a turn that edited code without a
  check
- **`/pulse-build`**: applied to every task completion, plus the
  reachability and Activation Path steps before a feature closes
- **The chain** in `/pulse-build` and `pulse go`: the spec tests
  frozen and RED checked, then the tests, a review, and a security
  audit on the last commit before the PR leaves draft
- **The test fix-loop of `/pulse-build`** (tests for existing code):
  each iteration verifies that previously failing tests now pass, with
  fresh command output
- **`/pulse-audit` fix-loop**: each iteration re-runs the audit
  phase for the affected category, with fresh output
- **The end of a `pulse go` run**: with two or more ready pull
  requests open, their branches merged in dependency order and the
  project's `verify` command run on the combined result

## See also

- [/pulse-build](../guides/pulse-build): the build loop around the gate
- [The V-Model](./v-model)
- [Reachability by stack](../reference/reachability-by-stack)
