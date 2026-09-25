# Hotfix lane (fix now, record right after)

Trivial bugs may be fixed first and recorded right after, when ALL FIVE
hold: at most 3 files; no new feature or dependency; no breaking change
to a public interface; under 15 minutes; an existing feature is the
parent. Any miss sends the bug through the normal flow.

When allowed:

1. Put it on the board before the first edit. An item `/pulse-build`
   sent here is claimed and on its branch already. Otherwise register a
   draft: `pulse new fix "<symptom>" --parent <feature> --draft` prints
   the number and holds the item for this session; branch
   `fix/<n>-<slug>` from the base branch. Either way,
   `pulse claim <n> --files <path>...` adds the files the fix touches to
   this session's claim, so every ramp keeps other work off them.
2. Fix it test-first; the regression-test cycle still runs and the
   15 minutes include it.
3. Record it. An item from `/pulse-build` has its spec: note the date in
   its "Regression test" section. A draft gets its spec now: write
   `_devprocess/requirements/fixes/{slug}.md` from
   `templates/FIX-TEMPLATE.md`. Commit fix and spec as `fix: <title>`
   with `Refs: #<n>` and push: `git push -u origin fix/<n>-<slug>`.
   A draft then gets its spec attached:
   `pulse new fix "<symptom>" --parent <feature> --spec <path> --issue <n>`;
   it ends the draft and gives the claim back. Commit what it wrote and
   push again. Open the PR; it closes the item.
4. Tell the user: files touched, item number, PR.

The safety nets that keep the lane honest:

- **Spec and record** exist for every hotfix, even retroactively.
- **Commit** names the item.
- **Stubs** left behind carry `FIXME(stub): <reason> -- see #<n>`;
  `pulse check` finds stubs without an open item.
- **Regression test** reproduced the bug before the fix.

Misuse signal: when hotfixes exceed 30% of an iteration's items, the
lane has become a process bypass. Register an improvement item for
the quality debt (`templates/IMP-TEMPLATE.md`).
