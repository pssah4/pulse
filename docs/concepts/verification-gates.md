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
During the build its agents run targeted tests and additional PLAN
checks outside `verify`. The supervisor runs the full command once on
the completed result; a relevant later change requires fresh evidence.

1. **Plan gate.** An item without a PLAN gets a planning agent first. A
   structurally invalid PLAN with no previous approval returns to the
   planner at its existing path, preserving its risks. The
   PLAN must pass P1 to P6: the frontmatter names issue, spec, files, and
   verify; every requirement and success criterion has a task, and every
   requirement its spec test in the first wave; every task names its
   files and a check; the tasks of one wave touch different files; no
   placeholder is left; every spec test file of the first wave matches a
   pattern in `[spec_tests]` of the config on the base branch. Before publication,
   `pulse check --plan <path>` reports all six rules' findings together,
   using the current local base without a network request or test suite.
   A PLAN that fails goes back to the planner with
   the findings, for up to two fix rounds; after that the item fails and
   the PLAN waits on its branch for a person, with all findings and a
   next action. A previously approved PLAN is preserved for a person's
   decision. Spec approval for planning is automatic by default; a valid
   PLAN waits for manual build approval with `pulse approve <n>`, which
   binds the PLAN and spec blobs. Explicit build delegation may permit
   that handoff automatically; an explicit off, expired delegation,
   `risk:` or open prerequisites keeps its existing hold.
2. **Spec tests, frozen.** The builder writes the spec tests of the
   PLAN's first wave, one per requirement, and commits them alone as
   `test: spec tests for #<n>`. From that commit on they are frozen.
   After the build and after every fix round, `pulse go` checks them
   line by line: every run of lines the freeze commit added must still
   stand at HEAD, unchanged and in one piece. An older test in the same
   file may go or change. A file the freeze commit created stays whole:
   no line of it changes, and none comes to it. A frozen line that changed gets a fix round
   ("restore them and change the code instead"); once the rounds are
   spent, the pull request opens as a draft that names the files, and no
   gate runs, because bent tests prove nothing.
3. **RED check.** After the build, `pulse go` checks out the freeze
   commit in the item's own worktree, where `setup` ran, runs the runner
   of each frozen spec test there (from `[spec_tests]` of the config on
   the base branch), and goes back to the branch, whatever the agent
   reported: before the code exists, every runner must fail. When they
   fail, the pull request says "RED evidenced". When one passes, the
   builder gets a fix round ("spec tests must fail first") out of the
   item's two, and the RED check runs again after it; when a runner still
   passes, or the check timed out, the row `spec tests` of the gate table
   says "RED not evidenced" and the pull request stays a draft. The gates
   follow either way. They do not when a fix round itself fails or
   times out. Then no gate runs, and the item ends as a draft pull
   request that says "The fix round for spec tests ended early" with
   the reason.
4. **Leftovers committed.** Before any gate judges the branch, `pulse go`
   commits what the agent left uncommitted (never
   `_devprocess/temp/`), so the tests, the review, and the audit all
   judge the same commit. A phase that committed pushes the item branch
   at once, so whoever holds the item next builds on the work.
5. **Tests.** In the item's worktree, `verify` runs, then the runner of
   each frozen spec test, one runner at a time per machine under
   `~/.cache/pulse/spec-tests.lock` and with `CI=1`, then `pulse check`
   (C1 to C10), whose findings count in the files the branch changed.
   Without a freeze commit, when no frozen file matches a pattern in
   `[spec_tests]`, or when a test file that wave 1 of the PLAN names is
   not among the frozen ones, the tests gate is red, and no fix round
   follows: no round makes spec tests fail before code that is already
   there. Tests that change a tracked file or move HEAD make it red as
   well, since what they judged is gone. A RED check git cannot check
   out, or a worktree its runners left changed, gives the row
   `spec tests` "RED not checked" with the reason; in the second case no
   gate runs and the worktree stays at the freeze commit for a person.
6. **Review and security audit.** One fresh session that did not build
   the item does both, each part with its own report and its own verdict,
   also for an item whose spec or PLAN has `risk: [security]`. The review checks the changes against the spec, the
   PLAN, the decisions, and the system map (`skills/pulse-build/references/review.md`);
   its brief says the tests passed at HEAD, so it does not run them
   again. For the audit, Pulse runs the scanner itself, with dependency
   advisories live from OSV, and the session triages the result
   ([/pulse-audit](../guides/pulse-audit)). A report without a
   `Coverage:` line, without a scan of the commit it judges, or with a
   pass while the OSV lookup failed or left a lockfile unread
   (`partial`) and the Coverage line does not say `SCA unavailable`
   gives no verdict
   ([the Coverage rule](../guides/pulse-audit#the-coverage-rule)). A
   report counts as green only when its first line reads exactly
   `Verdict: pass` and no finding below it is `- [block]`; "pass (stays
   draft)" there, or a pass further down, is none. The review brief names
   `conftest.py`, runner configs, the pytest sections of
   `pyproject.toml`, the scripts of `package.json`, and test setup files
   that changed after the spec tests were frozen.

Each gate leaves its result as the commit status `pulse/tests`,
`pulse/review`, or `pulse/audit` on the head it judged, and in
`~/.cache/pulse/<clone>/gates/<sha>` of the clone that ran it, outside
the git directory a Codex agent can write, like the kept verdicts
([what `pulse go` keeps outside the git directory](../reference/configuration#what-pulse-go-keeps-outside-the-git-directory)).
That file is local evidence, not proof: a Claude Code agent runs without
a sandbox and can write any file you can. The base check takes the tree
from the commit the file is named for, never from the file.

**Fix round.** An item gets one fix round for all its gates
together: red RED, changed spec tests, red tests, a blocking review, and
a blocking audit. One session that fixes the review and the audit is one
round. A fix agent gets the blocking findings (for
the tests, the end of their output), works test first, and commits;
then the frozen-test check and the tests run again, and only the gates
that were not green: a fresh session looks again at a blocking review
or audit, a passed one stays as it is. A fix round that fails
or times out ends the chain the same way as under the RED check: no
further gate, a draft that names the round. A session that gives no
verdict (it failed, timed out, changed the branch, or wrote no verdict
line) gets no fix round. A gate still red after the round leaves the
pull request a draft that names the open findings, for a person.

**The pull request.** One per item, `Closes #<n>`, against the base
branch. It is ready when every gate passed, and a draft otherwise. Its text
gives the reasons: a table of the gates with their results, the fix
rounds spent, and the commit each gate saw (a gate that stayed green
after a fix did not run again and keeps its own), the commit the chain
ended at, the RED note, the files that
depart from the PLAN, and the review and audit reports. The test output stays in the local log
(`.git/pulse/go/<n>.log`), because a test may print what a pull request
must not. Once the pull request exists, `pulse go` puts the review and
audit verdicts for its last commit on it as comments, one per gate, so
whoever holds the item next, in another clone, finds them: `Pulse
review: pass for <commit>.` with a hidden marker, one per gate and
commit. A marker counts only on a line of its own and only from someone
who may push to the repository (the owner, or a member or collaborator
with write or admin permission); when GitHub cannot say whether its
author may push, it counts for nothing, and no older verdict of its gate
counts in its place. When GitHub refuses them, the pull request stays as
it is and the item's log says so. The item keeps its claim until the
merge.

**Given back with code.** A draft of `pulse go` you fixed goes back with
`pulse release <n>`; the next run takes it straight into the gates: the
frozen-test check, then the gates from the tests. The text is written
anew, and the pull request turns ready once every gate passes. Gate 3,
the merge itself, waits for your `merge ok` ([pulse go](../guides/pulse-go#gate-3-the-merge)).

**The hold.** After every phase, `pulse go` compares the whole git
config the worktree reads, except `branch.*`, the shared
`info/attributes`, the hooks, in the shared `hooks` folder and where
`core.hooksPath` points for the worktree, and the files that tie the
worktree to the git directory with their state before the phase. An agent that can write
there (Codex with `--add-dir`) could leave a program that runs later
outside every sandbox and shows in no diff. When one of them changed,
the item stops: nothing is pushed or thrown away, no further phase
runs, the claim stays, and the run's report and `pulse status` name
what changed. Settings under `branch.*`, such as the merge base VS Code
notes per branch, stop nothing; any other change to the config does,
since `gpg.program`, `credential.helper`, or a remote's URL can run a
program as you.

## Where the rule is enforced

- **Every session and every subagent**: the rule arrives with the
  Pulse hooks; the Stop hook catches a turn that edited code without a
  check
- **`/pulse-build`**: applied to every task completion, plus the
  reachability and Activation Path steps before a feature closes
- **The chain** in `/pulse-build` and `pulse go`: the spec tests
  frozen and RED checked, then the tests, a review, and a security
  audit before the PR leaves draft; the PR names the commit each gate
  saw
- **The test fix-loop of `/pulse-build`** (tests for existing code):
  each iteration verifies that previously failing tests now pass, with
  fresh command output
- **`/pulse-audit` fix-loop**: each iteration re-runs the audit
  phase for the affected category, with fresh output
- **The base check of `pulse go`**: each new commit of the base branch
  is fetched and evaluated from current project CI and saved evidence.
  No full local suite runs before planning. Pending CI permits planning
  and holds ordinary builds; a current red base allows only repair items

## Removing a feature

`pulse delete <n>` is separate from completing the original feature. The
removal PR must remove its code, specs and active references while keeping
unrelated behavior. Fresh tests, review and audit bind the removal head;
old evidence from the feature does not approve its removal.

The person reviews the scope and confirms the exact removal head before
merge. Only after integration is verified can they confirm permanent
issue and comment deletion. Ambiguous ownership, dependencies, unpushed
work or a changed head stop the operation. Git history remains intact.

## Related guides

- [/pulse-build](../guides/pulse-build): the build loop around the gate
- [The V-Model](./v-model)
- [Reachability by stack](../reference/reachability-by-stack)
