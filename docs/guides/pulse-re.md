---
title: Requirements Engineering
description: Turn a validated Business Analysis into Epics, Features, and tech-agnostic Success Criteria. The bridge between the Why and the How.
---

# Requirements Engineering

`/pulse-re` (in Codex `$pulse:pulse-re`) is the bridge between [Business Analysis](./pulse-ba) (the Why) and [Planning](./pulse-plan) (the How). It transforms the validated business analysis into structured, measurable, tech-agnostic requirements that a human or AI architect can actually design against.

**Input:** `_devprocess/analysis/BA-{PROJECT}.md` (Project-BA, if any)
plus the matching Item-BA in `_devprocess/analysis/`, where one exists.
For the first epic of a new project, the Project-BA is the source and
`/pulse-re` opens the epic without an Item-BA; a later epic or feature
comes from its own Item-BA. The Project-BA supplies personas, value
dimensions, and KPIs by ID.

**Output:** an epic, features, and `architect-handoff.md` as files in
the repository, and one record on the board per item so everyone sees its
state. Every spec carries `issue:` (the item number) and `ba-ref:` in
its front matter; the Item-BA stays in `analysis/` as audit trail.

## Why this phase exists

Most teams skip Requirements Engineering. The BA produces "what we want to build," someone writes a Notion page, and the next day engineers are picking a framework. Two failure modes follow from that shortcut.

Tech bleeds into the problem statement. "We need OAuth" gets written instead of "users must prove identity." Now the requirement is coupled to a technology before anyone has decided whether that technology fits.

Success becomes unmeasurable. Features ship with Definition-of-Done lines like "users love it" that no test, gate, or agent can ever verify. The result is a backlog full of items nobody can say are finished.

Requirements Engineering exists to catch both, systematically, before they contaminate the architecture.

## The translation chain

Every output of RE descends from something in the BA. The skill enforces traceability. If a user story has no BA source, the skill flags it and sends you back to `/pulse-ba` rather than inventing new requirements on the fly.

```
BA element                    →  RE element
──────────────────────────────────────────────────────
HMW question                  →  Epic Hypothesis Statement
Insights                      →  Benefits Hypothesis per feature
Functional needs              →  User Stories (functional)
Emotional needs               →  User Stories (emotional)
Social needs                  →  User Stories (social)
Jobs to be Done per level     →  User Story motivation
Critical Hypotheses           →  Feature Validation section
Idea Potential axes           →  Priority label P0 / P1 / P2
Value Proposition             →  Definition of Done context
```

RE does not create new requirements out of thin air. It structures what the BA already surfaced.

## Epic Hypothesis Statement

The Epic is the strategic container. It is not a "big feature." It is a hypothesis about value, written as full prose. The skill rejects fill-in-the-blank templates because they reduce a strategic decision to a Mad Libs exercise.

```markdown
---
title: AI agent core
issue: 12
ba-ref: ../../analysis/BA-agent-core.md
---

# Epic: AI agent core

## Hypothesis

For solo founders running a B2B SaaS support inbox, who currently
spend two to four hours each day triaging tickets that mostly say
"how do I reset my password?", the AI agent core is a context-aware
ticket triage layer that auto-resolves the top ten password and
billing scenarios so the founder gets back at least an hour a day.
Unlike Zendesk macros, which the founder has to author and maintain
by hand, the agent core learns from the founder's resolution
history without configuration.
```

The hypothesis is one paragraph of prose, not a six-line template.
The skill rejects formats like `For {x} who {y} the {z} is a ...`
because they hide thin reasoning behind structure. A real
hypothesis explains the user, the problem, the solution category,
the primary value, the current alternative, and the unfair
advantage in actual sentences.

**Identity.** The item number is the ID. The file is
`_devprocess/requirements/epics/{slug}.md`; the record on the board links
it. Status lives in the record, never in the file.

## Feature structure

Under each epic, features are the units that get implemented. A
feature is what a team can ship in one coherent increment. Each one is a
spec file in `_devprocess/requirements/features/{slug}.md`, and its
record on the board hangs under the epic's. When one feature needs another
first, that is a "blocked by" link between the records, never prose.

```markdown
---
title: Auto-resolve password reset tickets
issue: 14
parent: ../epics/agent-core.md
ba-ref: ../../analysis/BA-agent-core.md
subtype: user-facing
priority: P1
effort: M
risk: []
---

# Feature: Auto-resolve password reset tickets

## Feature description
{Goal: what changes for whom, and why}

## Scope
- In: {what this feature does}
- Out: {what it deliberately does not do}

## User stories
| Role | Want | So that | Job type |

## Requirements
- FR-01: WHEN {trigger} THE SYSTEM SHALL {response}.
- FR-02 (unchanged): THE SYSTEM SHALL {keep what works today}.

## Success criteria
| ID | Criterion (tech-free) | Target | Measurement |

## Non-functional requirements
| Category | Target (with a number) | Notes |

## Architecturally Significant Requirements
| ID | Classification | Constraint | Quality attribute |

## Assumptions and dependencies
- {an assumption, or a skipped gap with the default we build on}

## Open questions
- [CLARIFY: only what the team keeps open on purpose]

## Activation Path
- Type: command | route | UI-element | endpoint | scheduled-job | tool | hotkey | public-API
- Identifier: `<command name | route path | URL | symbol name>`

## Definition of Done
- [ ] Every FR has a green test named after its id
```

**Requirements in EARS.** Each requirement is one numbered sentence with an uppercase SHALL: `WHEN <trigger> THE SYSTEM SHALL <response>`, `IF <unwanted condition> THEN THE SYSTEM SHALL <response>`, `WHILE <state> THE SYSTEM SHALL <response>`, or `THE SYSTEM SHALL <what always holds>`. Edge cases and error behavior are requirements of their own; what must keep working is marked `(unchanged)`. One line per requirement keeps it testable: each FR becomes one test, named after its id, written before the code. Given/When/Then stays available for a multi-step flow.

**The tree lives in the repository.** `parent:` links the feature to its epic, and the epic lists its features (with their fixes and improvements) under `## Items`. `pulse new --parent` sets `issue:` and `parent:` in the spec and adds its line to `## Items`; `pulse check` (C9) keeps them in step. A spec written from the template names its parent before it is registered: C9 lets a spec without an issue number do that, so the git hook takes the first commit of the specs.

**Risk flags.** `risk: [auth, security, data-migration, public-api, new-dependency]` marks a feature whose PLAN a person approves before anything is built.

**Frontmatter rule.** Status, claim, and dependencies do **not** live
in the frontmatter; the record carries them. The frontmatter holds
identity (`title`, `issue`), document links (`parent`, `ba-ref`),
planning inputs (`priority`, `effort`, `risk`), and the activation
contract (`subtype: user-facing | library`, default `user-facing`).
`pulse new` writes `issue:` and `parent:`. See
[Where things live](../concepts/where-things-live).

**Feature subtype.** Two values:

- `user-facing` (default) -- anything an end user reaches: UI, CLI
  command, API endpoint, scheduled job, agent tool, plugin command,
  hotkey. Definition of Done MUST list a documented trigger.
- `library` -- public API consumed by other code (function, class,
  module, package). No direct end-user trigger. Definition of Done
  MUST list the exported symbol(s) and the documentation entry.

A FEATURE that builds a backend module without any caller is not a
FEATURE -- it is infrastructure, and belongs as an IMP, not a FEAT
with status Done. The Activation Path entry forces the question "how
does anyone reach this code?" before the FEATURE moves out of
specification.

[`/pulse-build`](./pulse-build) verifies both the reachability and
the activation path before an item may close.

**Fixes and improvements** hang under their feature. Their spec is a
short file in `_devprocess/requirements/fixes/` or `improvements/`:
symptom, root cause as a causal chain, and regression test for a fix;
description, reason, and success criteria for an improvement.

### User stories across three levels of need

Human needs stack in three layers. The skill writes user stories on all three layers where the need exists, because a feature that serves only the functional layer is dramatically less sticky than one that serves the emotional and social layers too. The method that surfaces these three layers is the [Jobs to be done](../reference/methods-ideation#jobs-to-be-done) card.

Functional is what the user is trying to do. Emotional is how they want to feel while doing it. Social is how they want to be seen while doing it.

For a shared-expense app inside a roommate household:

- Functional. "As a roommate I want to record a shared purchase so that the split math is automatic."
- Emotional. "As a roommate I want the split to feel fair without awkward conversations so that the shared flat stays calm."
- Social. "As a roommate I want other flatmates to see I always pay my share so that my reputation stays intact."

The third line is where retention comes from. The agent probes explicitly for the emotional and social layer when it drafts user stories from BA needs. If the BA did not capture those layers, the agent sends you back to the [Jobs to be Done](../reference/methods-ideation#jobs-to-be-done) method card to fill them.

### Tech-agnostic Success Criteria

This is the rule the skill is most aggressive about. Success Criteria must be free of technology vocabulary.

Bad:

- "User authenticates via OAuth 2.0."
- "Data is stored in PostgreSQL with 24h retention."
- "REST endpoint returns 200 OK within 300ms."
- "React component loads in under 2s."

Good:

- "A user can prove identity without entering a password more than once a week on the same device."
- "Data a user deletes becomes irrecoverable within 24 hours."
- "A user receives a visible response within 300ms of any list interaction."
- "The first list view becomes interactive within 2s on a mid-range phone on 3G."

Why the rule matters: Success Criteria are the contract between the user and the team. If the contract references OAuth, you cannot swap it for a magic-link flow without renegotiating. If the contract references React, you have locked the stack before the architect has seen the problem.

Technical details live in the Technical NFRs section of the same Feature, clearly separated, and in the ADRs that follow in planning. See [Tech-agnostic Requirements](../concepts/tech-agnostic-requirements) for the full ruleset.

### ASRs: Architecturally Significant Requirements

An ASR is a requirement whose realisation shapes the architecture. You cannot satisfy it by editing one module in isolation. Common examples:

- Performance targets (latency, throughput, percentile budgets)
- Security constraints (data classification, auth model)
- Compliance constraints (GDPR, HIPAA, SOC2)
- Availability and recovery targets (SLA, RPO, RTO)
- Scale targets (concurrent users, data volume)
- Integration constraints (must talk to system X, must not talk to Y)

The skill labels every ASR as Critical, Moderate, or Low. A Critical ASR maps one-to-one to an ADR in planning, and the architecture quality gate will refuse to hand off if any Critical ASR has no matching ADR. This is the single most important traceability link in the whole V-Model.

### Benefits Hypothesis, not "description"

Teams love to write feature descriptions. The skill forces a stricter form: a Benefits Hypothesis, shaped like the test cards from validation.

> We believe this feature creates value because {insight from BA}.
> We will know we were right if {measurable signal}.

The form does three things. It forces the feature to trace back to an Exploration insight. It forces a success signal that is testable. It makes it obvious which features are based on evidence and which are still unvalidated bets. The second category is not forbidden, but the distinction has to be explicit on the feature card.

## The clarifying interview

The skill asks until the spec is one an agent can plan from without asking back: goal, scope with what is out, every requirement, edge cases, unchanged behavior, the signal for done, the four NFR categories, and constraints. There is no question budget. One question per turn, with options and a recommendation. A thin answer gets a sharper question first (a concrete example, the future without the problem, the opposite); the same question never comes back in other words.

When you do not know an answer, the skill proposes the method that finds it (below) and helps you prepare it. You can always skip: the gap goes into the spec as an assumption with the default the skill recommends, marked `(skipped)`, and the spec stays plannable. Only a question you want to keep open stays as `[CLARIFY: ...]`, and that holds the spec back until someone answers it.

## How the agent proposes methods in the dialog

Like the BA, this skill spots gaps in your input and suggests the method that will close them. You run the method, you come back with data, the skill continues. Common triggers and the matching cards:

- **Epic Hypothesis missing the current alternative.** [User journey](../reference/methods-discovery#user-journey) focused on the "before" phase, so you can see how the user solves the problem today without your product.
- **Feature has only functional user stories.** [Jobs to be done](../reference/methods-ideation#jobs-to-be-done) to surface the emotional and social layers so the stories stop feeling hollow.
- **Benefits Hypothesis has no Exploration source.** [Qualitative interview](../reference/methods-discovery#qualitative-interview) or [User motivation analysis](../reference/methods-discovery#user-motivation-analysis) to anchor the hypothesis in real evidence.
- **Technical NFR reads "fast" or "secure" without a number.** [Expert conversations](../reference/methods-discovery#expert-conversations) with the engineering or operations team to get a concrete target.
- **ASR is suspected but unverified.** [Expert review](../reference/methods-validation#expert-review) so you can confirm feasibility before writing the ADR.
- **Success Criterion cannot be made measurable.** [Test grid](../reference/methods-validation#test-grid) or [Value proposition quantification](../reference/methods-validation#value-proposition-quantification) for a baseline you can test against.
- **Critical Hypothesis from BA has no test plan.** Pick the cheapest falsifier: [Wireframes, storyboards, and paper prototypes](../reference/methods-validation#wireframes-storyboards-and-paper-prototypes), [Wizard of Oz](../reference/methods-validation#wizard-of-oz), or [Appearance prototype](../reference/methods-validation#appearance-prototype).
- **Risk blind spots before commit.** [Pre-mortem](../reference/methods-validation#pre-mortem) before the team locks resources.

## Priority: from Idea Potential to P0 / P1 / P2

The BA scored Idea Potential on three axes: User Value, Transferability (Scalability), and Feasibility. Requirements Engineering collapses those three scores into a single priority label per feature.

| Priority | Criteria | Meaning |
|---|---|---|
| P0 | High User Value and High Feasibility | Must ship in v1 |
| P1 | Moderate across axes, or high value with risk | Should ship in v1 if time allows |
| P2 | Low value or blocked feasibility | Backlog or follow-up |

The label is visible on every Feature card so the architect knows immediately which features are load-bearing for the MVP.

## Quality gates

Once an item is approved, `pulse check` reads its spec as the base branch has it and applies six rules. They are the mechanical half of "can an agent plan from this". Before that, `pulse check --spec <path> ...` applies them to specs in your working tree (one `--spec` takes several paths, and a repeated `--spec` adds its paths), and `/pulse-re` runs it before its pull request (see below):

| Rule | Checks |
|---|---|
| R1 | the spec exists on the base branch and names its item (`issue:`) |
| R2 | every mandatory section of its type is there and not empty |
| R3 | no placeholder, no open `[CLARIFY]`, no TODO outside the sections filled at the end |
| R4 | at least one requirement, each a list line that starts with its id, such as `- FR-01: WHEN ... THE SYSTEM SHALL ...` (the id plain, bold, or in backticks), in EARS form with SHALL |
| R5 | success criteria without technology terms, every NFR with a number |
| R6 | priority P0 to P2 and effort XS to L (split XL first) |

Before its pull request, once `pulse new` has numbered the specs, the skill runs `pulse check --spec <path> ...` on every spec it wrote and fixes what it reports. It applies the same rules to the files as they are, R1 only for an epic, and asks no board, so a merged spec is one `pulse approve` takes.

The judgment half stays with the interview and the approval: every prioritized need has a story, emotional and social layers were probed, success criteria measure an outcome for the user.

See [Verification Gates](../concepts/verification-gates) for the full gate mechanic.

## The architect handoff

The final artifact is `architect-handoff.md`, a single document that planning will consume. It contains the Epic Hypothesis, the Feature summary table with priorities, the full list of Critical ASRs, the Technical NFRs with numbers, the open questions for the architect, and the Critical Hypotheses from the BA that are still unvalidated.

Every item is on the board from the moment the skill names it, as a draft (`pulse new feat "<title>" --draft`), so the team sees a spec in progress and who writes it; an issue you name becomes the draft instead (`--issue <n>`). Before it writes, the skill checks the open drafts and items for overlap and asks you when one covers the same goal.

The skill validates (forbidden-terms grep, NFRs with numbers, ASRs classified, an Activation Path per feature), commits the specs on the docs branch (`docs(re): <epic>`), and pushes it. Then it attaches each spec to its draft, epic first: `pulse new epic "<title>" --spec <path> --issue <n>`, then `pulse new feat "<title>" --parent <epic> --spec <path> --issue <n>` per feature, with `--blocked-by` where one needs another. `pulse new` takes a spec only once its commit is on origin. It writes each item number into its spec as `issue:`, links the spec to its parent (`parent:`), and lists it in the epic's Items. The skill runs `pulse check --spec <path> ...` on the numbered specs and fixes what it reports, commits these lines and the fixes, pushes again, opens a pull request into the base branch, and puts each spec up for approval. When the team wants an item built, a person merges that pull request, because agents plan from the spec as the base branch has it, and then runs `pulse approve <n>`, so [`/pulse-go`](./pulse-go) can pick it up. `pulse approve` refuses while the spec is not on the base branch (R1), and for a feature while the spec there breaks one of R2 to R6; an epic needs R1 only.

Your agent asks before these steps unless its permission settings allow them: Claude Code in its default mode, in the terminal and the VS Code extension alike, before every shell command outside a small read-only set such as `git status`, so before `pulse status`, `pulse check`, `git add`, the commits, the pushes, `pulse new`, and `gh pr create` ([the rules that stop these prompts](../tutorials/installation#fewer-prompts-in-claude-code)), and Codex, whose sandbox keeps `.git` read-only and has no network (with the Codex rules from `/pulse-setup`, it runs `pulse new` without asking). Allow them when asked.

## Read the skill file

[`skills/pulse-re/SKILL.md`](https://github.com/pssah4/pulse/blob/main/skills/pulse-re/SKILL.md) on GitHub.

## Further reading

- [Tech-agnostic Requirements](../concepts/tech-agnostic-requirements). Full ruleset for keeping technology out of requirements.
- [Planning](./pulse-plan). The next phase, where ASRs become ADRs.
- [Discovery methods](../reference/methods-discovery), [Ideation methods](../reference/methods-ideation), [Validation methods](../reference/methods-validation). Method cards the agent references when you have gaps in the BA.
