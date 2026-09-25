---
title: {short title}
issue: {N}
parent: ../epics/{epic}.md
ba-ref: ../../analysis/BA-{slug}.md
subtype: user-facing  # user-facing | library
priority: P2          # P0 | P1 | P2
effort: M             # XS | S | M | L; split XL into smaller items first
risk: []              # auth, security, data-migration, public-api, new-dependency: a person approves the PLAN
---

<!-- See skills/pulse-re/SKILL.md for how to fill. Leave issue as it is:
     `pulse new --parent <epic>` sets issue and parent and lists the feature in
     the epic's Items. Until then pulse check (C9) lets a spec without an issue
     number name its parent. Once the item is approved, pulse check reads this
     spec from the base branch (rules R1 to R6): no placeholder and no open
     [CLARIFY] may remain. -->

# Feature: {Name}

## Feature description

{Goal: what changes for whom, and why. Two or three sentences.}

## Scope

- In: {what this feature does}
- Out: {what it deliberately does not do}

## User stories

| Role | Want | So that | Job type |
|------|------|---------|----------|
| {role} | {capability} | {outcome} | functional |
| {role} | {capability} | I experience {desired feeling} | emotional |
| {role} | {capability} | I am perceived as {external perception} | social |

## Requirements

<!-- One line each, numbered FR-nn, EARS form with an uppercase SHALL:
     WHEN <trigger> THE SYSTEM SHALL <response>.
     IF <unwanted condition> THEN THE SYSTEM SHALL <response>.
     WHILE <state> THE SYSTEM SHALL <response>.
     THE SYSTEM SHALL <what always holds>.
     Mark behavior that must not change with (unchanged). Add a small example
     table below a requirement when inputs and outputs matter. Each FR gets a
     test named after its id, written first. -->

- FR-01: WHEN {trigger} THE SYSTEM SHALL {response}.
- FR-02 (unchanged): THE SYSTEM SHALL {keep what works today}.

## Success criteria

<!-- Tech-agnostic: no technology terms, see skills/pulse-re/references/tech-agnostic-rules.md -->

| ID    | Criterion           | Target          | Measurement       |
|-------|---------------------|-----------------|-------------------|
| SC-01 | {user outcome}      | {target value}  | {how to measure}  |
| SC-02 | {behavior}          | {target value}  | {how to measure}  |

## Non-functional requirements

Populated rows only, every target with a number. Omit the section if nothing is binding.

| Category     | Target                       | Notes              |
|--------------|------------------------------|--------------------|
| Performance  | {response time, throughput}  | {context}          |
| Security     | {authn/authz, encryption}    | {context}          |
| Scalability  | {concurrent users, volume}   | {context}          |
| Availability | {uptime, RTO, RPO}           | {context}          |

## Architecturally Significant Requirements

| ID     | Classification     | Constraint            | Quality attribute |
|--------|--------------------|-----------------------|-------------------|
| ASR-01 | CRITICAL | MODERATE | {what must hold}      | {attribute}       |

## Assumptions and dependencies

- {an assumption, or a gap the user skipped, with the default we build on}
- {a dependency on another item; also recorded with --blocked-by}

## Open questions

<!-- Only questions the user wants to keep open, each as [CLARIFY: question].
     The spec is not ready while one is open. Answers go into the text above. -->

## Activation Path

- Type: command | route | UI-element | endpoint | scheduled-job | tool | hotkey | public-API
- Identifier: `{command name | route path | URL | symbol name}`
- Where it lives: {file or section pointer}
- How a user (or caller) reaches it: {one sentence}

## Definition of Done

- [ ] All user stories implemented and success criteria verified
- [ ] Every FR has a green test named after its id
- [ ] Activation Path trigger or symbol exists in code
- [ ] Issue closed by the merging PR
- [ ] Navigation (SYSTEM-MAP or path-local AGENTS.md) updated if a new entry point landed
