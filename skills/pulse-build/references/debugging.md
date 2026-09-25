# Debugging protocol

When a test fails unexpectedly during implementation, or behavior is
incorrect, or a fix does not work, follow this 4-phase protocol.

**The rule:** No fixes without root-cause investigation.

## Phase A: Root cause (BEFORE any fix attempt)

1. Read the error message completely: stack trace, line numbers, codes
2. Check reproducibility: does it happen every time?
3. Check recent changes: `git diff`, last commits, new dependencies
4. In multi-component systems: add logging at every component boundary
5. Trace the data flow backwards: where does the bad value originate?

## Phase B: Pattern analysis

1. Find working examples in the codebase
2. Read the reference implementation completely (do not skim)
3. List every difference, even ones that seem irrelevant
4. Check dependencies and config assumptions

## Phase C: Hypothesis

1. State one hypothesis: "Root cause is X because Y"
2. Make the smallest possible change to test it
3. One variable at a time
4. If the hypothesis is wrong: form a new one, do not pile fixes

## Phase D: Implementation

1. Write a failing test that reproduces the bug
2. Apply exactly one fix that addresses the root cause
3. Verify: test passes, no regressions elsewhere
4. Record the bug as a fix item unless the item you are on already
   is that fix: write the fix spec `_devprocess/requirements/fixes/{slug}.md`
   from `templates/FIX-TEMPLATE.md` (symptom, root cause as a causal
   chain, fix, regression test) with `parent:` set, run
   `pulse number --apply` (it names the file `FIX-{ee}-{ff}-{nn}-{slug}.md`),
   commit it on this branch and push, then
   register it: `pulse new fix "<symptom>" --parent <feature> --spec <path>`.
   The fix's commit names it: `Refs: #<n>`.

## Phase D.5: Architecture alarm (after 3+ failed fix attempts)

If three or more fix attempts fail to resolve the situation, this is
an architecture problem, not a bug:

- Each fix reveals a new problem in a different place?
- Fixes require massive refactoring?
- Each fix creates new symptoms?

Then STOP. No fourth attempt. Question the pattern fundamentally and
discuss with the user before any more fixes. This is a wrong
architecture, not a failed hypothesis.

**Every bug found gets an issue**, even when the fix is trivial. The
issue carries both state and substance: symptom, root cause as a causal
chain, fix, regression test.
