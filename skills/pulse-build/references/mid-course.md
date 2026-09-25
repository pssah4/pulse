# Mid-course triggers (binding)

Work learns things. When it does, pause the code edit, route the finding
to the right artifact, append a PLAN change-log line, and only then
resume. The commit names every item it touched.

**A held PLAN.** When the PLAN waited for a person (a risk flag, effort
L, `needs:`, or `manual`) and a trigger below changes its tasks, the
changed PLAN goes back to that person: show what changed and wait for
`pulse approve-plan <n>` before building on. Headless (an agent
`pulse go` started), keep the tasks as approved and write the finding
into `DISCOVERED.md` at the worktree root instead.

## 1. Bug discovery (trigger=bug)

A NEW bug surfaces while implementing the current item. Do not fix it
silently:

1. STOP the code edit.
2. Triage: bug in shipped code -> fix; missing requirement -> new
   feature (`/pulse-re`); design gap -> amend the decision or the PLAN.
3. Record it BEFORE any change: write the fix spec
   `_devprocess/requirements/fixes/{slug}.md` from `templates/FIX-TEMPLATE.md`,
   with "Discovered in #<current>" and the root cause in 3 to 10 lines,
   and `parent:` set; `pulse number --apply` names it
   `FIX-{ee}-{ff}-{nn}-{slug}.md`. Commit it on this branch and push, then register it:
   `pulse new fix "<symptom>" --parent <feature> --spec <path>`.
   Headless (an agent started by `pulse go`): do not call `pulse new`;
   write one line into `DISCOVERED.md` at the worktree root instead,
   with the symptom and the root cause. The orchestrator records it
   once the user agrees.
4. PLAN change log: `trigger=bug #<new>: <one line>`.
5. Fix it test-first. Commit names both items: `Refs: #<current>, #<new>`.

## 2. Design discovery (trigger=design)

A decision no longer matches reality. Do not deviate silently:

1. STOP the code edit.
2. Triage: small correction -> update the record with a dated section;
   wrong at the root -> update it to the actual decision and name what
   became history (supersede only on full reversal); wording only ->
   edit in place.
3. PLAN change log: `trigger=design`. If the pivot invalidates the
   remaining tasks, rewrite them and re-run the coverage gate.
4. Resume. The commit names the record: `Refs: #<n>, ADR-<nn> (updated)`.

## 3. Requirements discovery (trigger=requirement)

The spec is ambiguous, incomplete, or contradicts the code. Do not
reinterpret silently:

1. STOP the code edit.
2. Triage:
   - Ambiguous criterion -> rewrite, keep its number, add a reason.
   - Missing criterion -> add one with the next number.
   - Wrong criterion -> amend, or mark "Removed: {reason}" (never
     delete the line).
   - Scope wrong at the root -> ask the user; do not reshape the
     feature graph alone.
3. Re-run the coverage gate: every amended criterion maps to a task or
   is deferred. PLAN change log: `trigger=requirement`.
4. Resume. The commit names the change: `Refs: #<n> (SC-03 amended)`.

## 4. Capability discovery (trigger=capability)

The code is about to add a NEW user-facing capability no spec describes.

**Signals (any one):** a new route, handler, or command no spec names;
a new sidebar entry, settings tab, or top-level UI surface; a new CLI
flag or public endpoint that changes the user contract. Tech-only
changes do NOT trigger this (helpers, refactors, private utilities,
bug fixes, docs, tests).

1. STOP the code edit. Headless: do not ask and do not build it; write
   one line into `DISCOVERED.md` and go on with the PLAN.
2. Ask, one question at a time; never invent persona, job, or outcome:
   - A: A real new user-facing capability, or a technical byproduct?
     (byproduct -> code on)
   - B: For which persona? (from the Project-BA, or "Other" plus a
     short description)
   - C: Which job to be done does it solve?
   - D: Which measurable outcome do we expect? (if deferred, write
     `[AWAITING BA]`)
3. Write the feature spec draft now, not after the code, from
   `skills/pulse-re/templates/FEATURE-TEMPLATE.md`, and record the
   persona, job, and outcome in the Item-BA (a stub from
   `BA-MINI-TEMPLATE.md` is enough). Never edit validated BA sections
   silently.
4. Commit the spec on this branch and push, then
   `pulse new feat "<title>" --parent <epic> --spec <path>`. When all
   four answers came in, ask the user whether to approve it. Its spec
   must be merged into the base branch first; after that merge,
   `pulse approve <n>` only on the user's yes.
5. Resume. The commit names the new item.

**Bypass.** If the user says "scratch change, no feature yet", the commit
carries `[no-capture: scratch]`. A deliberate bypass is a recorded
action, not a hidden one.
