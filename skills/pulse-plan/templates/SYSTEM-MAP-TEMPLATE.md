<!-- Navigation map for agents. Every planner reads it before a Plan; a
     planning session with a person, or /pulse-realign, creates it on a docs
     branch into the base, never an item branch; a build updates an
     existing one as its last task when the item changes an entry point,
     data ownership, an invariant, or a quality goal. Names stable boundaries and first
     code entry points; it is NOT a full module inventory and is never
     auto-loaded. Cap: 150 lines. Project file: _devprocess/SYSTEM-MAP.md. -->

# System map: {project}

## System shape

{Three to four sentences: processes, boundaries, what talks to what.}

Core boundaries:

- {boundary}: `{src/entry-point}`
- {boundary}: `{src/entry-point}`

## Data ownership

- {store (DB, config, state)}: owned by `{module}`; nobody else writes

## Security invariants

- {invariant, e.g. "renderer never gets raw credentials"}
- {invariant; changing one of these requires a decision record BEFORE
  implementation}

## Quality goals, constraints, risks

- Quality goal: {goal, e.g. "a stopped run loses no work"}
- Constraint: {constraint and its reason}
- Risk: {risk and what keeps it small}

## Fast paths

When changing {topic}: start in `{file1}`, `{file2}`, `{file3}`.

When changing {topic}: start in `{file1}`, `{file2}`.

## Decision hooks

Before changing a listed area, check `decisions/README.md` (or the
`applies-to`/`read-when` frontmatter of the ADRs) for a binding
decision. If a change would violate one, stop and ask.
