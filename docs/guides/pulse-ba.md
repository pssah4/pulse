---
title: Business Analysis
description: The first phase of the V-Model. Understand the problem before you design the solution. The agent runs the dialog, you run the field work.
---

# Business Analysis

`/pulse-ba` (in Codex `$pulse:pulse-ba`) is the first phase of the V-Model. It exists to stop the single most common failure mode of AI-assisted software projects: jumping straight to code before the problem is understood. A modern AI coding agent will happily build the wrong thing, fast, if nobody slowed it down to ask who the user is and what they actually struggle with.

This skill is the slowdown. It runs an innovation interview with you, spots the gaps in your understanding of the user and the problem, and tells you which research method will close each gap fastest. The actual field work stays with you. No agent can replace a real conversation with a real user.

**The value is the dialog, not the document.** The BA record is a short template that condenses the interview into five questions: the observed problem, who has it, the solution hypothesis and its strongest assumption, the scope, and the success signal with the top risk. The skill writes only what was actually said or evidenced. It never invents personas, percentages, or baselines to fill a table; "unknown" is a valid value. Long-form sections (personas table, market context, competitor analysis) live in an optional BA-EXTENDED document that is cap-exempt, written only on request for a stakeholder audience, and never a gate.

## What the skill actually does

The session walks through three internal phases:

1. **Exploration** to understand the problem space. Users, needs, insights, touchpoints, trends, competitors.
2. **Ideation** to design a response. Idea description, value proposition, Wow feature, high-level concept, critical hypotheses.
3. **Validation** to test whether the idea is worth building. VP score, assessment radar, pricing, channels, revenue streams.

Every persona, insight, need, and touchpoint is proposed as a draft and confirmed by you before it becomes part of the artifact. The agent does not invent users in the background. It proposes, cites the source, and waits for your confirmation.

## On the board

Before the first question, the skill makes the analysis visible to the team, so nobody starts the same one twice. It looks for open drafts and items on the topic (`pulse status --json`) and asks whether this BA continues one of them. An issue you name, an idea from the backlog for example, becomes the draft: `pulse new <type> "<title>" --draft --phase analysis --issue <n>`. Otherwise the skill registers a new one, for an epic `pulse new epic "<title>" --draft --phase analysis`. Either way the board and the [map](./pulse-map) show a BA in progress and who writes it, the number goes into the BA as `issue:`, and the BA is written on the branch `docs/<n>-<slug>`. A Project-BA is no item: it skips the lookup and the draft, so its first question comes without `pulse status`, and its branch is `docs/<slug>`, named after the project.

## Scope adaptation

The skill asks at the start which tier applies. The rest of the session scales to match.

| Scope | Exploration | Ideation | Validation | Typical duration |
|---|---|---|---|---|
| Simple Test | Minimal: user and problem | Describe the solution | Skip | Hours to 1 or 2 days |
| Proof of Concept | Shortened: user, needs, HMW | Full | Hypotheses and feasibility | 1 to 4 weeks |
| MVP | Full 10-section Exploration board | Full | Full market assessment | 2 to 6 months |

A Simple Test does not need a stakeholder map. An MVP does not get away without one. Match depth to scope.

## How the agent proposes methods in the dialog

The core behaviour of this skill is method matchmaking. During the interview, the agent notices where your answers go thin, where you sound certain without evidence, or where entire sections of the Exploration board are empty. When that happens, it stops asking questions and suggests a method instead.

Example moment inside a real session:

> **Agent:** Who exactly is affected by this problem?
>
> **You:** Probably our B2B customers. Maybe also their end users.
>
> **Agent:** That's a guess, not evidence. Before we draft a persona, we need a few real conversations. The fastest way at this stage is [explorative interviews](../reference/methods-discovery#explorative-interviews): seven to ten short conversations, 20 to 30 minutes each, to map the problem space. If you already suspect the real pain is with power users or non-users, [extreme users](../reference/methods-discovery#extreme-users) is a better fit. Which one do you want me to prep a question list for?

The agent then helps you build the question list or the stakeholder map or the interview guide, you run the method in the field, and you come back with notes. The session continues from where you paused.

The full set of methods the agent can suggest is documented as method cards on three reference pages:

- [Discovery methods](../reference/methods-discovery) for user research, observation, synthesis, and mapping
- [Ideation methods](../reference/methods-ideation) for generating and sharpening ideas
- [Validation methods](../reference/methods-validation) for prototyping, testing, and business viability

Each card has the same structure: what the method produces, when the agent brings it up, how to run it, team and time, things that go wrong in practice, and what to bring back to the session.

## Where the methods fit into the session

The BA session walks through Exploration, Ideation, and Validation. Each phase has a natural set of methods the agent reaches for when your answers go thin. The mapping below is the practical answer to "what should I actually do next if I am stuck on this step".

**Exploration, understanding users and the problem.**

- Fuzzy user group: [Explorative interviews](../reference/methods-discovery#explorative-interviews), [Qualitative interview](../reference/methods-discovery#qualitative-interview), [Extreme users](../reference/methods-discovery#extreme-users).
- Users describe the ideal instead of the real: [Fly on the wall](../reference/methods-discovery#fly-on-the-wall), [Self-test](../reference/methods-discovery#self-test).
- Notes exist but no pattern: [User motivation analysis](../reference/methods-discovery#user-motivation-analysis), [Persona synthesis cluster](../reference/methods-discovery#persona-synthesis-cluster), [Persona](../reference/methods-discovery#persona).
- Political or multi-department project: [Stakeholder map](../reference/methods-discovery#stakeholder-map).
- B2B with several intermediaries: [Value proposition chain](../reference/methods-discovery#value-proposition-chain).
- Broad fuzzy problem: [Research mind map](../reference/methods-discovery#research-mind-map).
- Unknown market or competitors: [Market and trend analysis](../reference/methods-discovery#market-and-trend-analysis).
- Experience spans several touchpoints: [User journey](../reference/methods-discovery#user-journey).
- Private or self-censored behaviour: [Cultural probes](../reference/methods-discovery#cultural-probes).

**Ideation, designing a response.**

- Empty solution space: [Brainstorming](../reference/methods-ideation#brainstorming), [Brainwriting](../reference/methods-ideation#brainwriting).
- Seed idea too thin to prototype: [Idea tower](../reference/methods-ideation#idea-tower).
- Repeating the same variants: [Inspiration cards](../reference/methods-ideation#inspiration-cards).
- Cannot explain why users would switch: [Jobs to be done](../reference/methods-ideation#jobs-to-be-done).
- Team too close to the product: [Kill your company](../reference/methods-ideation#kill-your-company).
- Too many ideas, no shortlist: [Idea clustering and selection](../reference/methods-ideation#idea-clustering-and-selection).
- Genuine technical contradiction: [TRIZ](../reference/methods-ideation#triz).

**Validation, testing whether it is worth building.**

- A risky flow needs user feedback: [Wireframes, storyboards, and paper prototypes](../reference/methods-validation#wireframes-storyboards-and-paper-prototypes).
- Expensive feature, unclear demand: [Wizard of Oz](../reference/methods-validation#wizard-of-oz).
- Visual direction unclear: [Appearance prototype](../reference/methods-validation#appearance-prototype).
- Environment matters more than the product: [Context and system prototypes](../reference/methods-validation#context-and-system-prototypes).
- Feasibility question: [Expert review](../reference/methods-validation#expert-review).
- Business model unclear: [Business plan](../reference/methods-validation#business-plan).
- Multiple competing VPs: [Value proposition quantification](../reference/methods-validation#value-proposition-quantification).
- Team too optimistic: [Pre-mortem](../reference/methods-validation#pre-mortem).
- Menu or taxonomy confuses users: [Card sorting](../reference/methods-validation#card-sorting).

## The interview discipline

A few rules that the skill follows consistently across every session.

### Co-creation, not autonomous generation

The agent proposes drafts and you confirm. A typical exchange:

> "Here is a persona sketch based on what you just told me: [draft]. Does this fit your real users, or does it need adjustment?"

If you wanted autonomous generation, you would get a plausible BA that reads well and fails silently. Co-creation is the point.

### Ask before you ask

Before asking you about users, markets, or competitors, the agent checks whether you already have that data. Existing interviews, customer support logs, CRM exports, prior research. If you have it, the agent ingests it. If not, the agent proposes a method and you go into the field.

### Probing when answers get thin

When your answers become generic, the agent reaches for a handful of probing techniques.

- 5-Why. Ask "why is that a problem" until you hit something surprising.
- Concretisation. "Give me a concrete example." "When did this last happen?"
- Future projection. "Imagine the problem was solved tomorrow. What changes?"
- Perspective shift. "What would your customer or your boss say?"
- Emotional level. "How did that feel?"
- Analogy trigger. "Do you know something similar from another domain?"

These are the same probes the field methods use. They work in both directions: you use them on the users during field work, the agent uses them on you during the session.

## The bridge out of Exploration: Point of View and HMW

Once Exploration fills up, the agent synthesises a **Point of View** statement. The canonical form:

> [User, descriptive] needs/wants/has to [verb describing the need] because/but [insight that reframes the problem].

Example:

> Harriet, a mother of three rushing through the airport, needs a way to entertain her children because she feels uncomfortable when they disturb other passengers.

A good POV is specific about the user, verb-driven in the need, and insightful in the because. You spend more time on this one sentence than you expect, and it earns the time back in Ideation.

The POV then becomes a **How Might We** question that opens a solution space. The agent drafts three or four HMW variants from the same POV, each steering ideation in a different direction. You pick one and Ideation starts from there.

## The bridge out of Ideation: Value Proposition and Critical Hypotheses

Ideation closes with a Value Proposition and a set of Critical Hypotheses. Every hypothesis is written in the test-card form:

> We believe that [assumption]. To verify that, we will [method]. We will measure [indicator]. We are right if [threshold].

These hypotheses become the validation agenda. The agent prioritises them by risk, not by ease. The hypothesis that would kill the idea if wrong gets tested first.

## Quality gates

Before the skill hands off to Requirements Engineering, it checks quality gates adapted to scope.

| Scope | Gate threshold |
|---|---|
| Simple Test | At least 3 of 4 criteria (problem, user, functionality, DoD) |
| PoC | At least 6 of 8 criteria (HMW, hypothesis, persona, risks and more) |
| MVP | At least 10 of 13 criteria (full Exploration board, two or more personas, and so on) |

If a gate fails, the skill returns to the relevant section instead of handing off a half-finished BA. See [Verification Gates](../concepts/verification-gates) for the full mechanic.

## BA layers: Project-BA and Item-BA

A real project does not collapse into one business analysis. The BA is a
two-layer artifact that lives entirely in `_devprocess/analysis/`.
Item-BAs feed the epic or feature spec through a `ba-ref:` in the spec's
frontmatter.

- **Project-BA** (`BA-{PROJECT}.md`) is the singleton product layer:
  personas with stable IDs, value dimensions, nordstern, project-wide
  constraints and KPIs. Created once, referenced by every Item-BA.
- **Item-BA** (`BA-{slug}.md`) is one BA per new work item that needs
  discovery depth. Its `issue:` is the draft the skill registered when
  it started, or the issue it adopted.

  | Item | Template | Required? |
  |------|----------|-----------|
  | Epic | `BA-TEMPLATE.md` | yes, before `/pulse-re` opens the epic, except the first epic of a new project: the Project-BA hands it straight to `/pulse-re` |
  | Feature | `BA-TEMPLATE.md` (reduced) | yes, unless the BA of its epic covers it |
  | Improvement or fix | `BA-MINI-TEMPLATE.md` | optional, when value or root cause is unclear |

**Inheritance.** Item-BA frontmatter carries `project-ba-ref:` pointing
at the Project-BA (or `null` for single-item projects). Personas are
referenced by ID, never redefined. KPIs map upward via
`project-kpi-ref:`; unmapped KPIs are named in the handoff report.

**Templates:**

- Core discovery (Project-BA, epic and feature Item-BAs):
  `templates/BA-TEMPLATE.md` (five questions; [line caps](../reference/artifacts#line-caps):
  Project-BA 200 lines, epic BA 120, feature BA 60)
- Mini discovery (improvement and fix Item-BAs, cap 40 lines):
  `templates/BA-MINI-TEMPLATE.md`
- Optional long form for stakeholder audiences:
  `templates/BA-EXTENDED-TEMPLATE.md` (cap-exempt, on request only)

**Scope mapping per item type:**

| BA type | Default scope | Sections used |
|---------|---------------|---------------|
| Project-BA | PoC or MVP | full template |
| Epic BA | PoC or MVP | full template |
| Feature BA | Simple Test or PoC | reduced |
| Improvement or fix BA | Simple Test | mini template |

Long research raw material lives in `BA-{PROJECT}-v{N}-full.md`
archives, not in the active Project-BA.

## Handoff

The skill commits the BA on its docs branch (`docs(ba): <title>`, with `Refs: #<n>` for its draft; a Project-BA has no `Refs:` line) and asks you to approve it, the first gate of the Pulse flow. A correction goes into the BA, and the question comes again. Once you approve, the BA gets `validity: Validated`, and the skill pushes the docs branch so the team can read it. Then [`/pulse-re`](./pulse-re) starts in the same session, on the same branch, with the draft number. RE turns the HMW into the epic hypothesis, the critical hypotheses into feature validation, needs and jobs to be done into user stories, and the idea potential into priorities, and attaches each spec to its draft once the spec is pushed. State never goes into the BA file; the item's record carries it.

## Phase 6: Post-Release Review (BA as living document)

A BA validated by reasoning alone becomes historical fiction once real users arrive. After a release, `/pulse-ba` on a validated BA walks each critical hypothesis and asks what evidence came in: **Confirmed by usage**, **Contradicted by usage**, or **Inconclusive**. Every answer is appended as an evidence block with date and source; nothing is deleted. A contradiction becomes a new item under the epic. When every hypothesis is confirmed, the BA's validity becomes `Confirmed by usage`.

## Validation Mode for brownfield projects

When `/pulse-ba` detects a BA draft created by [`/pulse-realign`](./pulse-realign), it enters Validation Mode. Instead of starting a new interview from scratch, it walks through each section of the existing draft, confirms the evidence-backed claims with you, and fills the `[NEEDS USER INPUT]` placeholders through the normal interview cycle. Each section gets promoted from `Draft` to `Validated` as you confirm it.

This is how the backward walk through the V joins the forward walk. Same file, same path, same downstream phases.

## Read the skill file

Want to see the exact instructions the agent follows? [`skills/pulse-ba/SKILL.md`](https://github.com/pssah4/pulse/blob/main/skills/pulse-ba/SKILL.md) on GitHub. The method catalog the agent draws from lives at [`skills/pulse-ba/references/methods.md`](https://github.com/pssah4/pulse/blob/main/skills/pulse-ba/references/methods.md).

## Further reading

- [Discovery methods](../reference/methods-discovery), [Ideation methods](../reference/methods-ideation), [Validation methods](../reference/methods-validation). The full method cards the agent references during the dialog.
- [Your first Business Analysis tutorial](../tutorials/first-business-analysis).
- [Requirements Engineering](./pulse-re). The next phase.
- [Tech-agnostic Requirements](../concepts/tech-agnostic-requirements). Why the BA must stay free of technology vocabulary.
