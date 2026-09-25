# Artifact formats for the reverse walk

Binding formats for every artifact `/pulse-realign` produces in Mode A.
The templates named here are canonical; this file only fixes how realign
fills them. The anti-hallucination rules from SKILL.md apply to every
block below.

## 1. Navigation (A2)

Template: `skills/pulse-plan/templates/SYSTEM-MAP-TEMPLATE.md`, project
file `_devprocess/SYSTEM-MAP.md`, cap 120 lines. Name the stack and point
at the manifests; versions and dependency lists stay there. One
`Sources:` line per block is enough:

```
## System shape

A Next.js app with an API layer and a Postgres database via Prisma;
tests run in Vitest and Playwright.

Sources: package.json, tsconfig.json, prisma/schema.prisma, vitest.config.ts
```

Areas with their own rules (a database layer, a plugin boundary) get a
proposed path-local AGENTS.md: three to eight lines, only rules visible
in the code of that area, each with its source.

## 2. Decision records (A3)

Template: `skills/pulse-plan/templates/ADR-TEMPLATE.md` with
`kind: post-hoc`. Required sections: Context, Decision, Consequences,
Sources. Considered Options is omitted for post-hoc; when docs or
comments name the alternatives, upgrade to `kind: choice` and cite them.
Core sections carry no code paths; the paths that embody the decision go
into `## Sources`.

```yaml
---
id: ADR-{nn}
title: {short title}
date: {YYYY-MM-DD}
kind: post-hoc
validity: Inferred from codebase
source: /pulse-realign on {date}
read-when: "{one-line trigger}"
---
```

- `Context:` what the code shows that implies the decision was made.
- `Decision:` the observable choice, one to three sentences.
- `Consequences:` only what is visible (lock-in, operational
  implications in CI config).
- `## Sources`: files, commits, or docs that support the decision.

Write only decisions that are consequential AND non-obvious from
framework defaults. Location: `_devprocess/decisions/ADR-{nn}-{slug}.md`,
numbered in discovery order, one router row each.

## 3. arc42 reference (A3, MVP scope or on request)

Template: `skills/pulse-plan/templates/arc42-REFERENCE-TEMPLATE.md`,
project file `_devprocess/arc42-REFERENCE.md`. Post-code, cap-exempt,
sections without substance omitted.

| Section | Fill from |
|---|---|
| 3 Context and scope | entry points, external integrations visible in config |
| 4 Solution strategy | the inferred decisions (one row each) |
| 5 Building block view | observable module boundaries; NEVER the raw directory tree |
| 6 Runtime view | explicit docs only; otherwise omit |
| 7 Deployment view | CI config, Dockerfile, k8s manifests |
| 9 Architecture decisions | the decision router |

Header: `validity: Inferred from codebase`, `source: /pulse-realign on {date}`.
Do NOT write the arc42 constraints document: quality goals, constraints,
and risks are pre-code content that the pulse-plan skill creates when
new work starts.

## 4. Anticipated epics (A4)

Template: `skills/pulse-re/templates/EPIC-TEMPLATE.md`, reduced. Location:
`_devprocess/requirements/epics/{slug}.md`; `pulse number --apply` renames
it to `EPIC-{nn}-{slug}.md` once every spec of the run is written.

```yaml
---
title: {thematic name}
date: {YYYY-MM-DD}
validity: Anticipated (not yet validated)
source: /pulse-realign on {date}
---

# Epic: {thematic name, e.g. "User and access management"}

> Anticipated. Derived from observed capabilities, not from a validated
> business motivation. /pulse-ba refines or replaces the hypothesis.

## Anticipated scope

{1-2 sentences: which observed capabilities this epic groups, and why}

## Evidence

- {module or directory, short description}
- {route or API surface}
- {test file describing this capability cluster}

## Items

- [{feature title}](../features/{feature slug}.md)
  - [{fix title}](../fixes/{fix slug}.md)
```

One Items line per feature this epic groups, each fix or improvement two
spaces deeper below its feature; no `#n` while the item has no record.
`pulse number --apply` puts the IDs into these lines, and `pulse new`
adds the issue number when A7 registers an item.

No obvious clusters: a single `observed-capabilities.md`, split later.
Hypothesis prose is written by `/pulse-ba`, never invented here.

## 5. Feature specs (A4)

Template: `skills/pulse-re/templates/FEATURE-TEMPLATE.md`, reduced scope.
Location: `_devprocess/requirements/features/{slug}.md`, renamed to
`FEAT-{ee}-{nn}-{slug}.md` by `pulse number --apply`. Every feature
names its epic in `parent:`, shipped or not; the epic lists it under
`## Items`. Once A7 has pushed the specs, it gives every feature its
record with
`pulse new feat "<title>" --parent <epic> --spec <this spec>`, which
writes `issue:` and adds the number to its Items line, and closes it
with the other records of code that exists.

```yaml
---
title: {short capability name}
parent: ../epics/{epic slug}.md
date: {YYYY-MM-DD}
validity: Observed (not validated)
source: /pulse-realign on {date}
---

# Feature: {short name}

## Feature description

{What the code does, 2-3 sentences.}

Source: {file paths and line ranges that implement this feature}

## User stories

[NEEDS USER INPUT]

## Requirements

- FR-01: WHEN a caller asks for the stored chats THE SYSTEM SHALL list them with id, title, and last change, newest first.
  Source: src/chats/handlers.ts:42. Test: tests/chats.test.ts:18.
- FR-02: IF the chat id is unknown THEN THE SYSTEM SHALL answer "not found" and change nothing.
  Source: src/chats/handlers.ts:61. Test: none.
- FR-03: WHEN the app stores a chat THE SYSTEM SHALL write it with these fields.
  Source: src/chats/store.ts:12. Test: tests/store.test.ts:30.

  | Field | Type | Required |
  |---|---|---|
  | id | string (UUID) | yes |
  | title | string | yes |
  | updatedAt | ISO 8601 timestamp | yes |

## Success criteria

{Observable criteria table, see section 6.}

## Non-functional requirements

{Constraints visible in code: rate limits, timeouts, retry policies,
auth requirements.}

Source: {config or middleware locations}

## Activation Path

- Type: {route | command | UI-element | endpoint | ...}
- Identifier: `{the identifier in the code}`
- Where it lives: {file}
- How a user (or caller) reaches it: {one sentence}
```

Names stay short and capability-focused ("User login", "Project
export"). One capability per feature, never lumped.

Every operation the description names has at least one FR, and every
error a caller sees has an `IF ... THEN` FR. A data contract a rebuild
must keep (stored data, a file format, an API or protocol to the
outside, config and env) is an FR with a field table (field, type,
required); a contract several features share gets a feature of its own.
Each FR stands on one line, its `Source:` and `Test:` on the next. The
Activation Path names every identifier, not only one.

## 6. Observable success criteria (A4)

One criterion per outcome a user sees; the FRs carry the detail. The
target is what the code shows: it works (yes), or the number it sets,
with `Source:`. `[AWAITING BA]` only for a business target the code
cannot show (adoption, time saved, satisfaction). The measurement
always names the test or the check.

```
| ID | Criterion (observable) | Target | Measurement |
|---|---|---|---|
| SC-01 | A user can reopen, rename, and delete a conversation | yes (Source: src/chats/handlers.ts:42-88) | tests/chats.test.ts |
| SC-02 | Startup aborts when the sandbox is not ready after 30 s | 30 s (Source: src/main/index.ts:1088) | integration test |
| SC-03 | Teams reuse conversations instead of starting over | [AWAITING BA] | pilot interview |
```

`/pulse-ba` later replaces `[AWAITING BA]` with validated targets.

## 7. BA draft (A5)

Template: `skills/pulse-ba/templates/BA-TEMPLATE.md` (five questions,
Project-BA cap 200 lines). Location: `_devprocess/analysis/BA-{PROJECT}.md`.

```yaml
---
title: {project name}
date: {YYYY-MM-DD}
target-type: project
scope: {simple-test | poc | mvp}
validity: Draft (reverse-engineered, awaiting validation)
source: /pulse-realign on {date}
filled-from-sources: {n}
needs-user-input: {m}
---
```

Per section, evidence rules:

- **1 Problem (observed):** only from README motivation or explicit
  docs. Otherwise placeholder.
- **2 Who has it:** ONLY if docs explicitly name a user type; quote the
  exact phrase. Never inferred from routes or directories.
- **3 Solution hypothesis and strongest assumption:** HMW framing only
  if the docs contain an explicit problem statement; the assumption only
  if the docs mention one. Otherwise placeholder.
- **4 Scope:** In-list from observed capabilities (cite A4 evidence);
  Out-list only from explicit "non-goals" docs.
- **5 Success signal and top risk:** only from documented metrics or
  stated risks. Otherwise placeholder.

Every non-placeholder sentence carries `Source:`. Placeholders use the
full form: `[NEEDS USER INPUT. No evidence found in {searched sources}.
/pulse-ba will fill this in.]`

## 8. Findings as specs (A6, A7)

A finding becomes a record only after the verification gate confirmed
the gap, and only with a spec of its own. Failing or skipped tests,
security findings, and wrong behavior get a fix spec from
`skills/pulse-build/templates/FIX-TEMPLATE.md` under
`_devprocess/requirements/fixes/{slug}.md`; everything else gets an
improvement spec from `skills/pulse-build/templates/IMP-TEMPLATE.md`
under `_devprocess/requirements/improvements/{slug}.md`. Its `parent:`
names the feature (or the epic) the finding belongs to, and the epic lists
it under that feature; `pulse number --apply` names it
`FIX-{ee}-{ff}-{nn}-{slug}.md` or `IMP-...`. The frontmatter
adds `validity: Observed (not validated)` and
`source: /pulse-realign on {date}`; Symptom (fix) or Reason
(improvement) carries:

```
Evidence: {path:line}
Verified against the code: {what was checked}.
```

Then register it once A7 has pushed its commit, which writes `issue:`
and `parent:` into the spec:
`pulse new fix|imp "<title>" --parent <feature or epic> --spec <that spec>`.
The record links the spec and holds nothing else. It stays open: the
finding is the open work, while the feature above it is closed.

A known defect gets an FR for the expected behavior, and the fix spec
below it says where the code departs today.
FRs without a test give one improvement spec per feature, "Spec tests
for FR-..", that names the FR ids.

Target already satisfied: no spec, one line in the realign report.
Undecidable: no spec yet; list it in the report with the open question.
Nothing is approved here.
