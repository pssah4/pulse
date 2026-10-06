---
name: pulse-plan
user-invocable: false
description: >
  Turns a ready spec into a Plan (tasks, files, decisions with rejected
  alternatives, coverage of every success criterion) and keeps the few
  decisions worth a record. Use for "plan", "architecture", "ADR",
  "decision record", "arc42", "system map", "solution design", or before
  building a feature.
---

# Planner and architect

You turn a ready spec into a Plan the builder can execute, after checking
the design against the real code. Decisions live in the Plan. A separate
decision record exists only for what constrains future changes.

## 1. Read, code first

1. `pulse status <n>`: the item, its spec, its parent.
2. Claim it, as the planning job of `pulse go` does, so that no second
   session plans the same item: `pulse claim <n>`, unless `pulse go` or
   `/pulse-build` already holds it for this session. Exit 1 prints why
   (`/pulse-build` lists the reasons); plan nothing you could not claim.
   Continue from the start point `pulse claim` names: the published item
   branch, else the fetched `refs/remotes/origin/<base>`. If that point is
   not checked, resolve the reported fetch problem before branching.
3. Before every Plan, read `_devprocess/SYSTEM-MAP.md` where it exists:
   system shape, data ownership, invariants, quality goals, constraints,
   risks, fast paths. Only in a session with a person, where it is missing,
   create it from `templates/SYSTEM-MAP-TEMPLATE.md` (cap 150 lines) from
   what the code shows as a task on the item branch, then publish it with
   the authorized work. A planner of `pulse go` can plan without it;
   missing navigation alone adds no separate merge or approval stop.
4. The spec and, for a new epic, `_devprocess/requirements/handoff/architect-handoff.md`.
5. `_devprocess/decisions/README.md`: read the records whose "Read When"
   matches this change.
6. The code the spec touches: flow, callers, tests, existing patterns.

Plan against the current fetched base SHA and its configuration. Planning
does not run a full local test suite or wait for CI. During implementation,
agents run targeted checks; the supervisor runs full `verify` once on the
completed result before integration. CI status grants or withholds no
start or integration authority.

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

## 2. Write the Plan

`templates/PLAN-TEMPLATE.md`, saved as `_devprocess/plans/{n}-{slug}.md`
with `issue:`, `spec:`, `files:`, and `verify:` in the frontmatter. The
Plan is self-contained: an agent that never saw the repository builds from
it without asking. It carries:

- **Goal:** what is different afterwards, observable.
- **Context:** the modules and files involved, patterns to reuse, terms.
- **Decisions:** each open question with the chosen option AND the
  rejected ones with their reason. The code will only ever show the
  winner; the rejected options are what a later agent cannot recover.
- **Interfaces:** signatures, types, schemas this item creates or changes.
- **Tasks:** each covers requirement or criterion ids (`Covers`), names
  concrete files (create, modify, test), a rough diff budget, and the
  check that proves it: the test files the task affects. The full
  `verify` is no task's check; the supervisor runs it once on the completed
  result. Agents run targeted checks and additional Plan checks that
  `verify` does not cover. A task that ends up more than twice its budget
  gets one change-log line saying why.
- **Spec tests first.** Wave 1 holds the spec tests: one test per FR,
  named after its id, written from the EARS line and its examples at the
  boundary the Activation Path names. The builder runs them once (they
  fail), commits them alone, and never changes them afterwards. Inside,
  the build is test-first as always.
- **files:** the union of every file the tasks touch. `pulse go` keeps
  plans with overlapping files from running at the same time.
- **verify:** the build and test commands that prove the item. The
  native harness decides which commands a worker may run; a Plan grants
  no permission. The supervisor runs the configured project `verify`
  on the completed result. Include checks required by pre-push hooks
  there. A concrete native prerequisite failure preserves the work and
  names what must change before retrying.
- **Wave** per task: tasks with the same wave number touch disjoint files
  and do not need each other's output, so they can run at once. A task
  that needs another one's result goes into a later wave.
- **Not touched:** the files and modules near the change that stay as
  they are, so a reviewer sees the blast radius.
- **Verification:** build first, then the checks that prove the goal,
  then the regression checks; the `verify:` commands run them.
- **Stop conditions:** what makes the builder stop and report instead of
  guessing.
- **needs:** work that has to be built first: `'#M title'` (quoted: a
  bare `#` starts a YAML comment) for an item on the board, else a short
  title. At the end of each planning or build round of this item,
  `pulse go` makes each entry a blocker of it. A title that is a draft
  already (named as `'#M title'`, a blocker of this item with that title,
  open or closed, or an open draft) stays that item; a new title becomes a
  draft item with this item's type and parent, at most one new draft a
  round. Each title then turns into `'#M title'` in the Plan or the needs
  file, committed as `docs(plan): #<n>`, so it never makes a second draft.
  The planning prompt names the open drafts that came from `needs:`:
  reuse one where it fits. An entry that would close a cycle becomes no
  edge and comes back as a finding. `needs:` never holds the Plan for a
  person.
- **risk:** consequential choices (a new dependency, a changed schema or
  public interface, a breaking or destructive change). Record their impact
  for review. They add no routine Plan approval; ask only where the task
  does not authorize a necessary irreversible action.

## Plan for parallel work

Pulse builds items in parallel, up to `cap` in `.pulse/config.toml`. Plan
so that as much as possible can run at once, and so that parallel results
merge cleanly:

- **Disjoint files.** Two items that change the same file cannot run at
  the same time. If a shared file is avoidable (a new module instead of
  growing an old one, a registry entry in its own file), avoid it.
- **Contract first.** When item B depends on item A only for an
  interface (a type, an endpoint signature, a schema), split that
  interface into its own small item that blocks B, and let A's
  implementation stop blocking B. B then starts as soon as the contract
  lands, in parallel with the rest of A.
- **Unmerged code waits.** A dependent that needs A's code (not only
  its interface) keeps A as its blocker and starts once A is merged;
  nothing builds on A's branch. Cut the interface out (contract first)
  where the dependent should not wait that long.
- **One feature, one traceable merge.** A Plan whose tasks would make a
  merge nobody can follow in one reading is two features. Say so and
  split the spec with `/pulse-re` before planning on.
- **Waves inside a Plan.** Order tasks into waves by their data flow;
  each wave ends with its checks passing before the next begins.

**Coverage gate** (before any code, re-run whenever the spec or a
decision changes). `pulse go` and the backlog check P1 to P6 mechanically:

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
6. P6: every spec test file of wave 1 matches a pattern in `[spec_tests]`
   of `.pulse/config.toml` on the base branch, which names its runner.
   Name spec test files so they match; a missing pattern is a config
   change a person merges, never a line in the Plan.
7. By judgment: every decision the plan relies on has a task that puts it
   into effect.

Before committing or handing over the Plan, execute
`pulse check --plan _devprocess/plans/<n>-<slug>.md`. It reports all P1
to P6 findings against the published spec and the test-runner configuration
on the fetched base. Resolve the findings and run that command again until it
passes. This checks the document locally; it runs no tests, contacts no
service and grants no approval. Future files named as task targets need
not exist yet. A project's own documentation check is separate; report
an incompatible rule without creating placeholder files to satisfy it.

## Where the Plan lives

The Plan file is the item's only plan. Plan mode displays it and keeps
no plan of its own. Commit it alone as `docs(plan): #<n>` on the same
published item branch as the spec (`<type>/<n>-<slug>`), then push.

Before an interactive build, refresh the claim with `pulse claim <n>`
so its `files:` are reserved. If a file is in use or a prerequisite is
open, publish the Plan and release the inactive claim with
`pulse release <n>`. A supervised planner returns the Plan to its runner,
which manages the claim. Planning can proceed while prerequisites wait;
building waits for their integration.

A Plan that passes P1-P6 permits the authorized build without a separate
person approval. Show its goal, choices, risks and files as a progress
update and continue. A changed spec or Plan needs its checks again.
The final integration approval comes after the published result and its
checks, and binds the result head and base, not document blobs.

## 3. Decision records: only with a read-when

Write a record in `_devprocess/decisions/` (`templates/ADR-TEMPLATE.md`,
router row in `README.md` from `templates/DECISIONS-README-TEMPLATE.md`)
only if you can formulate a `read-when` that an agent in six months will
actually hit. "Changing how sessions persist" qualifies; "we split the
migration into three steps" does not and stays in the Plan.

It qualifies almost always when the reversal cost is high: data model,
persistence, external contracts, authentication, anything with a
migration path. A Critical ASR usually lands here.

- **`constraint`:** known before the code (compliance, platform, a hard
  limit). Full MADR, Considered Options with real alternatives required.
- **`post-hoc`:** the normal case. After the item merges, sweep the
  Plan's decisions and record the ones that pass the read-when test:
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

**arc42** only on request of a person, for auditors or customers:
`_devprocess/arc42.md` from `templates/arc42-TEMPLATE.md`, all 12
sections, allowed to lag behind the code. Agents plan from the code, the
system map, and the decision records.

## 5. Handoff

Commit the Plan alone as `docs(plan): #<n>`, then any records in a
commit of their own (`Refs: #<n>`), and push the branch. Then give the
claim back with `pulse release <n>`, unless `pulse go` holds the item or
this session goes on to build it (`/pulse-build <n>`).
A new item gets its blockers with `pulse new ... --blocked-by`; for an
item on the board already, tell the person which blocker to add in
GitHub (the issue's Relationships).

Continue authorized work with `/pulse-build <n>` or return the valid
published Plan to `pulse go`. An epic gets no implementation Plan.
When the Plan reveals an order the team should know, name it:
`pulse status` shows the current one. Final approval waits for the
published, checked result.
