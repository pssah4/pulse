---
title: Verification gates
description: The "no completion without fresh evidence" rule that keeps AI agents from claiming success they did not check, and the chain of gates every item passes before its result is ready for final integration approval.
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
published result carries the test and its evidence.

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
before its published result can receive final approval. `pulse go` runs the chain as a
script, so no agent can skip a step or declare one passed; `/pulse-build`
follows the same order in your session ([/pulse-build](../guides/pulse-build#done)).
`pulse go` does not start without a `verify` command in
`.pulse/config.toml`: the RED check and the tests gate need it.
During the build its agents run targeted tests and additional Plan
checks outside `verify`. The supervisor runs the full command once on
the completed result; a relevant later change requires fresh evidence.

1. **Plan validation.** A missing or structurally invalid Plan goes to
   the planner at its existing path, preserving risks and recorded
   decisions. P1-P6 check issue, spec, files and verify; requirement and
   criterion coverage; tests in wave 1; concrete tasks and checks;
   disjoint files per wave; no placeholders; and configured test runners.
   `pulse check --plan <path>` reports all findings against the published
   spec and fetched base configuration without a network call or suite.
   Bounded repairs resolve structural findings. A valid published Plan
   permits the authorized build when dependencies and active file claims
   allow it. Unresolved findings preserve the work and name the next
   action. There is no early person approval for the spec or Plan.

2. **Spec tests, frozen.** The builder writes the spec tests of the
   Plan's first wave, one per requirement, and commits them alone as
   `test: spec tests for #<n>`. From that commit on they are frozen.
   After the build and after every fix round, `pulse go` checks them
   line by line: every run of lines the freeze commit added must still
   stand at HEAD, unchanged and in one piece. An older test in the same
   file may go or change. A file the freeze commit created stays whole:
   no line of it changes, and none comes to it. A frozen line that changed gets a fix round
   ("restore them and change the code instead"); once the rounds are
   spent, the result stays blocked with the named files, and no gate runs.
   A required test correction starts with its requirement and Plan change
   log, with the exact test diff shown to the user before the edit.
3. **RED check.** After the build, `pulse go` checks out the freeze
   commit in the item's own worktree, where `setup` ran, runs the runner
   of each frozen spec test there (from `[spec_tests]` of the config on
   the base branch), and goes back to the branch, whatever the agent
   reported: before the code exists, every runner must fail. When they
   fail, the result records "RED evidenced". When one passes, the
   builder gets a fix round ("spec tests must fail first") out of the
   item's one allowed round, and the RED check runs again after it; when a runner still
   passes, or the check timed out, the row `spec tests` of the gate table
   says "RED not evidenced" and the result remains blocked. The gates
   follow either way. They do not when a fix round itself fails or
   times out. Then no gate runs, and the result says
   "The fix round for spec tests ended early" with
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
   `[spec_tests]`, or when a test file that wave 1 of the Plan names is
   not among the frozen ones, the tests gate is red, and no fix round
   follows: no round makes spec tests fail before code that is already
   there. Tests that change a tracked file or move HEAD make it red as
   well, since what they judged is gone. A RED check git cannot check
   out, or a worktree its runners left changed, gives the row
   `spec tests` "RED not checked" with the reason; in the second case no
   gate runs and the worktree stays at the freeze commit for a person.
6. **Review and security audit.** One fresh session that did not build
   the item does both, each part with its own report and its own verdict,
   also for an item whose spec or Plan has `risk: [security]`. The review checks the changes against the spec, the
   Plan, the decisions, and the system map (`skills/pulse-build/references/review.md`);
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
a sandbox and can write any file you can. For evidence reuse, Pulse reads the Git tree
from the commit the file is named for, never from the file.

**Fix round.** An item gets one fix round for all its gates
together: red RED, changed spec tests, red tests, a blocking review, and
a blocking audit. One session that fixes the review and the audit is one
round. A fix agent gets the blocking findings (for
the tests, the end of their output), works test first, and commits;
then the frozen-test check and the tests run again. If the new commit
has the same Git tree, Pulse may carry green review or audit evidence
and rerun only the red gates. Changed contents invalidate that evidence,
so review and audit both run again. A fix round that fails
or times out ends the chain the same way as under the RED check: no
further gate, preserved work with a finding naming the round. A session that gives no
verdict (it failed, timed out, changed the branch, or wrote no verdict
line) gets no fix round. A gate still red after the round leaves the
result blocked with its open findings available for repair.

**The published result.** Pulse records the branch, result head, base,
gates and findings in shared state and keeps the full review and audit
evidence available for inspection. Each verdict identifies what it
checked. Test output stays in the local log (`.git/pulse/go/<n>.log`),
since it can contain material that should not be published. External
commit statuses alone grant no authority. Inactive claims are released;
the branch, worktree, result and evidence remain visible independently.

**Final approval and integration.** Regular checked results receive
automatic approval by default. With an explicitly chosen manual policy,
a person reviews the diff, tests, review, audit, risks and findings,
then approves the exact result head and base in Pulse. The local queue exposes pending and failed actions;
only confirmed shared approval authorizes integration. A changed head
or base needs revalidation and new approval. Pulse serializes integration,
checks the current approval and evidence again, and uses a normal merge
and push with real hooks. A withdrawal before publication prevents the
base update. Remote ancestry proves completion, including recovery after
an interrupted closure.

**Given back with code.** Publish the item branch before ordinary
`pulse release <n>`. A later runner reuses its preserved work and evidence
and runs the checks still needed for its current result. It does not
build a stored current result again merely because its claim was released.
See [final approval](../guides/pulse-go#final-integration-approval).

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
  audit before final integration approval; result evidence names the
  commit each gate saw
- **The test fix-loop of `/pulse-build`** (tests for existing code):
  each iteration verifies that previously failing tests now pass, with
  fresh command output
- **`/pulse-audit` fix-loop**: each iteration re-runs the audit
  phase for the affected category, with fresh output
- **The base check of `pulse go`**: fetch the current base and read its
  configuration before starting work. CI status does not gate planning,
  building or integration. No full local suite runs before planning;
  the supervisor owns full verification of the completed result.

## Removing a feature

`pulse delete <n>` is separate from completing the original feature. The
removal must cover its code, specs and active references while keeping
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
