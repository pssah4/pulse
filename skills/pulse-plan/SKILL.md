---
name: pulse-plan
user-invocable: false
description: >
  Turns a ready spec into a PLAN (tasks, files, decisions with rejected
  alternatives, coverage of every success criterion) and keeps the few
  decisions worth a record. Use for "plan", "architecture", "ADR",
  "decision record", "arc42", "system map", "solution design", or before
  building a feature.
---

# Planner and architect

You turn a ready spec into a PLAN the builder can execute, after checking
the design against the real code. Decisions live in the PLAN. A separate
decision record exists only for what constrains future changes.

## 1. Read, code first

1. `pulse show <n>`: the item, its spec, its parent.
2. Claim it, as the planning job of `pulse go` does, so that no second
   session plans the same item: `pulse claim <n>`, unless `pulse go` or
   `/pulse-build` already holds it for this session. Exit 1 prints why
   (`/pulse-build` lists the reasons); plan nothing you could not claim.
3. The spec and, for a new epic, `_devprocess/requirements/handoff/architect-handoff.md`.
4. `_devprocess/decisions/README.md`: read the records whose "Read When"
   matches this change.
5. The code the spec touches: flow, callers, tests, existing patterns.

**Critical review.** Before planning, check the design against the code:
do the decisions match the real architecture, do existing patterns
contradict them, which modules are affected but unnamed, which
dependencies or constraints are missing. Report only divergences, gaps,
and risks; silence means "matches the code". Write corrections back to
the spec or the decision record before planning on top of them.

**Handoff dialog.** The architect handoff carries a `## Dialog` section
between RE and you. It is not a blocker: only the dependent item waits.
Answer open questions from the artifacts and the code first. Ask
everything still open in ONE question per session. Append-only; answered
entries get `Status: Resolved`.

**Spec gap.** If the design reveals a gap, contradiction, or impossible
constraint in the spec, stop planning that item and route it back to
`/pulse-re`. Planning around a broken spec carries the fault into the
code. Other items continue.

## 2. Write the PLAN

`templates/PLAN-TEMPLATE.md`, saved as `_devprocess/plans/{n}-{slug}.md`
with `issue:`, `spec:`, `files:`, and `verify:` in the frontmatter. The
PLAN is self-contained: an agent that never saw the repository builds from
it without asking. It carries:

- **Goal:** what is different afterwards, observable.
- **Context:** the modules and files involved, patterns to reuse, terms.
- **Decisions:** each open question with the chosen option AND the
  rejected ones with their reason. The code will only ever show the
  winner; the rejected options are what a later agent cannot recover.
- **Interfaces:** signatures, types, schemas this item creates or changes.
- **Tasks:** each covers requirement or criterion ids (`Covers`), names
  concrete files (create, modify, test), a rough diff budget, and the
  check that proves it. A task that ends up more than twice its budget
  gets one change-log line saying why.
- **Spec tests first.** Wave 1 holds the spec tests: one test per FR,
  named after its id, written from the EARS line and its examples at the
  boundary the Activation Path names. The builder runs them once (they
  fail), commits them alone, and never changes them afterwards. Inside,
  the build is test-first as always.
- **files:** the union of every file the tasks touch. `/pulse-go` keeps
  plans with overlapping files from running at the same time.
- **verify:** the build and test commands that prove the item. The
  agents of `pulse go` run a line only when it starts with a program of
  the configured `verify` or with a script of the repository (`bin/pulse
  check`); a shell or interpreter given code, a download, `npx`, `env`,
  or `sudo` is left out, and the item log names it.
- **Wave** per task: tasks with the same wave number touch disjoint files
  and do not need each other's output, so they can run at once. A task
  that needs another one's result goes into a later wave.
- **Stop conditions:** what makes the builder stop and report instead of
  guessing.
- **needs:** work that has to come first and is not yet an item, or a
  step that needs a person's OK (a new dependency, a changed schema or
  public interface, a breaking or destructive change). An entry holds
  the PLAN for a person, and the approval covers the step. An entry that
  starts with `#M` holds only while #M is open and no blocker of this
  item: the board already waits for a blocker, and a closed item is done.

## Plan for parallel work

Pulse builds in parallel as far as `.pulse/config.toml` allows (`parallel`:
`off`, `items`, `max`). Plan so that as much as possible can run at once,
and so that parallel results merge cleanly:

- **Disjoint files.** Two items that change the same file cannot run at
  the same time. If a shared file is avoidable (a new module instead of
  growing an old one, a registry entry in its own file), avoid it.
- **Contract first.** When item B depends on item A only for an
  interface (a type, an endpoint signature, a schema), split that
  interface into its own small item that blocks B, and let A's
  implementation stop blocking B. B then starts as soon as the contract
  lands, in parallel with the rest of A.
- **Unmerged code stacks by itself.** A dependent that needs A's code
  (not only its interface) keeps A as its one blocker. As soon as A's PR
  is ready, the dependent starts on A's branch and its PR targets A's
  branch; no line in the PLAN is needed. Merge order is then A before B,
  which the integration check at the end of a `pulse go` run tests
  before anyone merges.
- **One feature, one traceable merge.** A PLAN whose tasks would make a
  merge nobody can follow in one reading is two features. Say so and
  split the spec with `/pulse-re` before planning on.
- **Waves inside a PLAN.** Order tasks into waves by their data flow;
  each wave ends with its checks passing before the next begins.

**Coverage gate** (before any code, re-run whenever the spec or a
decision changes). `pulse go` and the ramp check P1 to P5 mechanically:

1. P1: the frontmatter names `issue`, `spec`, `files`, and `verify`,
   and the file is UTF-8.
2. P2: every FR and SC id of the spec appears in a task's `Covers` or in a
   `Deferred: SC-nn {reason}` line; every task covers an id; every FR has
   its spec test in wave 1, except an FR the spec marks `(unchanged)`,
   which an existing test may prove.
3. P3: every task names a file and a check; `files` is exactly the union
   of the task files. "Clean up state management" fails.
4. P4: tasks in one wave touch disjoint files.
5. P5: no placeholder outside the change log; braces in code blocks and
   inline code are code.
6. By judgment: every decision the plan relies on has a task that puts it
   into effect.

## Where the PLAN lives, and who approves it

Once the PLAN is saved, run `pulse claim <n>` again (this session holds
the item already): the claim then carries the PLAN's `files:`, and every
ramp keeps other items off those files without a fetch. Commit the PLAN
alone as `docs(plan): #<n>` on the item's branch (`<type>/<n>-<slug>`)
and push it: the ramp and every teammate see it there, and the build
continues on that branch. `pulse go` plans approved items with a ready
spec by itself, in ramp order, as the first phase of their job.

With `plan_approval = "auto"` (the default) a PLAN that passes P1 to P5 is
approved at once, unless something holds it: a risk flag in the spec
(`risk:`) or an entry under `needs:`. With `manual`, or when something
holds it, the ramp shows "plan waits for you" until a person approves it
(`pulse approve-plan <n>`, or the action in the ramp).

## 3. Decision records: only with a read-when

Write a record in `_devprocess/decisions/` (`templates/ADR-TEMPLATE.md`,
router row in `README.md` from `templates/DECISIONS-README-TEMPLATE.md`)
only if you can formulate a `read-when` that an agent in six months will
actually hit. "Changing how sessions persist" qualifies; "we split the
migration into three steps" does not and stays in the PLAN.

It qualifies almost always when the reversal cost is high: data model,
persistence, external contracts, authentication, anything with a
migration path. A Critical ASR usually lands here.

- **`constraint`:** known before the code (compliance, platform, a hard
  limit). Full MADR, Considered Options with real alternatives required.
- **`post-hoc`:** the normal case. After the item merges, sweep the
  PLAN's decisions and record the ones that pass the read-when test:
  Context, Decision, Consequences, Sources (code paths allowed there).
- **`choice`:** a real pre-code choice between alternatives; rare.

One decision per record. Before adding one, check whether an existing
record should be extended. When a decision changes, update the record
with a dated section naming what became history; supersede only on full
reversal. Core sections (Context, Decision drivers, Considered Options,
Decision, Consequences) carry no code paths, file names, or signatures.

Stable project rules (stack, conventions, domain terms) belong in the
project's AGENTS.md or a path-local AGENTS.md, not in `_devprocess/`.

## 4. On request

- **arc42 constraints** (`templates/arc42-CONSTRAINTS-TEMPLATE.md`, cap
  40): quality goals, constraints, quality scenarios, risks. Before code.
- **arc42 reference** (`templates/arc42-REFERENCE-TEMPLATE.md`): the full
  document for auditors or customers, after code, allowed to lag.
- **System map** (`templates/SYSTEM-MAP-TEMPLATE.md`, cap 120): system
  shape, data ownership, security invariants, fast paths into the code.

## 5. Handoff

Commit the PLAN (`docs(plan): <title>`, `Refs: #<n>`) and any records,
push the branch, then give the claim back: `pulse release <n>`. Keep it
only when this session goes on to build the item (`/pulse-build <n>`).
Set new blockers with `pulse block <n> --by <m>` or
`pulse new ... --blocked-by`.

An approved item goes straight on, unless its PLAN waits for a person
(a risk flag, `needs:`, or `plan_approval = "manual"`): then show the
user the goal, the decisions, the risks, and the files, and wait for
`pulse approve-plan <n>`. Otherwise `/pulse-build <n>` in this session,
or `pulse go` when several are ready; `pulse go` builds in ramp order
without asking. An item that is not approved yet waits for the person
who approves its spec. When the plan reveals an order the team should
know, name it: `pulse status` shows the current one, and `pulse rank`
moves an item.
