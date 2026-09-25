---
title: Your first Business Analysis
description: Walk through a concrete business analysis with the /pulse-ba skill, from scoping to handoff.
---

# Your first Business Analysis

Let's run a real business analysis. We take an idea, scope it, explore
the problem, design a solution, and end with a Business Analysis document
that hands off cleanly to Requirements Engineering.

## The example idea

> "I want to build a tool that helps distributed teams run better
> async retrospectives."

This is a typical starting point: a rough idea, no clear user, no
hypothesis, no scope. Exactly where `/pulse-ba` is most useful.

::: info Methods you will see referenced below
The agent's main job is to notice gaps in your understanding and propose
the right research or prototyping method to close them. The callouts
through this tutorial link straight to the method cards under
[Discovery methods](../reference/methods-discovery),
[Ideation methods](../reference/methods-ideation), and
[Validation methods](../reference/methods-validation). You can read
them now or wait until the tutorial walks you into the spot where one
becomes relevant.
:::

## Step 1: Invoke the skill

Pulse runs in Claude Code and Codex; support for other coding agents will follow. Type the skill and your idea, in Claude Code `/pulse-ba`, in Codex `$pulse:pulse-ba`, in the CLI and the IDE extension alike (the Codex CLI also lists the skills under `/skills` > **List skills**, or as soon as you type `$`, by the names `pulse-ba (pulse)` and so on, the IDE extension under **Skills** when you type `/`):

```
/pulse-ba

I want to build a tool that helps distributed teams run better async
retrospectives.
```

In Codex, every other command in this tutorial goes the same way:
`$pulse:pulse-re` for `/pulse-re`, and so on.

A new project gets a Project-BA. It is no item, but while it is
written it holds a draft on the board, so nobody starts a second one:
the skill looks for one (`pulse status`), registers
`pulse new epic "Project BA: <product>" --draft --phase analysis`, and
writes the BA on a docs branch it names after the project, here
`docs/retrospectives`. The name comes from your idea, so your agent may
pick another one, such as `docs/async-retro`. A BA for a new
epic or feature in a running project starts on the board as well, as a
draft whose number goes into the BA as `issue:`, on the branch
`docs/<n>-<slug>` (see
[Business Analysis](../guides/pulse-ba#on-the-board)).

## Step 2: Determine the project scope

If the skill cannot tell what the BA is for, it first asks: the whole
project, a new epic, a new feature, or a smaller improvement or fix.
Answer "the whole project". Then comes the scope question, in words like these:

```
Before we go into detail: what is your project purpose?

A) Simple Test / Feature
   -> Timeframe: hours to 1-2 days

B) Proof of Concept (PoC)
   -> Prove technical feasibility, 1-4 weeks

C) Minimum Viable Product (MVP)
   -> Functional product, 2-6 months
```

Pick the proof of concept (**B) PoC** above) for this walkthrough, however the agent words the question. The skill now adapts the depth
of the analysis: shortened Exploration, full Ideation, hypothesis-based
Validation.

## Step 3: Exploration phase

The skill asks targeted questions, one at a time. For a PoC, expect
8 to 12 questions covering:

- **Users and personas**: who is affected? Who pays? Who blocks?
- **Needs**: what functional, emotional, and social needs exist?
- **Insights**: what did you learn from real user statements?
- **Trends and technology**: what is happening in the space?
- **How-Might-We**: the synthesis question that bridges problem and solution

Important: the skill co-creates artifacts with you. It proposes a
draft persona and asks you to confirm or correct. It cites which user
statement an insight comes from. Nothing is invented in the background.

::: tip If you cannot answer "who is the user"
Before drafting a persona, the agent will likely propose a field method
so you can come back with real evidence:

- [Explorative interviews](../reference/methods-discovery#explorative-interviews).
  7 to 10 short conversations, 20 to 30 minutes each, to map the problem
  space when you do not yet know which segment matters.
- [Qualitative interview](../reference/methods-discovery#qualitative-interview).
  One deep conversation, 60 to 90 minutes, when you already know who
  to talk to and need depth.
- [Stakeholder map](../reference/methods-discovery#stakeholder-map)
  when several departments or external parties are in the picture and
  you do not know who to interview first.
- [Extreme users](../reference/methods-discovery#extreme-users) when
  average-user interviews produce generic answers and the real driver
  has not surfaced yet.
:::

::: tip If you have interview notes but no pattern
The agent will help you move from raw notes to a usable persona:

- [User motivation analysis](../reference/methods-discovery#user-motivation-analysis)
  to pull functional needs, emotional needs, and obstacles out of a
  pile of transcripts.
- [Persona synthesis cluster](../reference/methods-discovery#persona-synthesis-cluster)
  to turn clusters of insights into persona seeds.
- [Persona](../reference/methods-discovery#persona) to finish each
  seed into a one-page reference everyone on the team can check
  decisions against.
:::

::: tip If users describe an ideal workflow instead of the real one
Interviews alone will not get you past this. Two observational
methods fit:

- [Fly on the wall](../reference/methods-discovery#fly-on-the-wall).
  Silent observation in the real context. You learn what users do,
  not what they say they do.
- [Self-test](../reference/methods-discovery#self-test). Walk the
  user's process yourself. Uncomfortable but fast.
:::

::: tip If you cannot name the competitors or the market context
- [Market and trend analysis](../reference/methods-discovery#market-and-trend-analysis).
  One day of desk research, two hours of clustering, four to six
  themes with one potential field each.
- [User journey](../reference/methods-discovery#user-journey) when
  the friction is really about the user's experience over time, not
  the market around it.
:::

At the end of Exploration, you get a How-Might-We question like:

> How might we help distributed product teams run retros that surface
> root causes, so action items actually ship?

## Step 4: Ideation phase

The skill now shifts from understanding the problem to designing a
solution. For a PoC, expect 8 to 10 questions:

- Solution description and object model
- **Idea potential** on three axes (Value, Transferability, Feasibility), scored 0 to 10
- **The Wow**: which feature would you want the press to celebrate?
- **Critical hypotheses**: what must be true for this to work?
- **Value proposition**: the formal statement

::: tip If the solution space feels empty or keeps repeating itself
The agent will suggest a short ideation exercise. Which one depends on
your team and the shape of the blockage:

- [Brainstorming](../reference/methods-ideation#brainstorming). A
  15 to 20 minute group session once you have a sharp HMW. Best when
  the team is willing to defer judgement and fast-talkers can be kept
  in check.
- [Brainwriting](../reference/methods-ideation#brainwriting). The
  silent 6-3-5 variant, useful when previous brainstorms were dominated
  by one or two voices.
- [Inspiration cards](../reference/methods-ideation#inspiration-cards)
  when the team keeps reproducing the same three or four variants and
  you need a jolt from outside the domain.
- [Idea tower](../reference/methods-ideation#idea-tower) when a seed
  idea is promising but too thin to prototype. Additive only, no
  removals, until the concept is coherent enough to sketch.
:::

::: tip If you cannot explain why users would switch
- [Jobs to be done](../reference/methods-ideation#jobs-to-be-done).
  Name the functional job, the emotional job, and the social job for
  the target user, along with hiring and firing criteria. This is
  also the method the RE skill will rely on when it drafts user
  stories for the functional, emotional, and social layer.
- [Kill your company](../reference/methods-ideation#kill-your-company)
  for the inverse lens. Pretend a startup is attacking you. The
  weaknesses they would target become the value proposition you
  need to defend.
:::

::: tip If you have too many ideas and no shortlist
- [Idea clustering and selection](../reference/methods-ideation#idea-clustering-and-selection).
  Cluster by theme first, then score the clusters against four
  criteria (User Value, Feasibility, Transferability, Risk), and
  pick the top three with evidence you can defend.
:::

Example output of Idea Potential:

```
Value/Urgency:    8/10 (retros are a well-known pain point)
Transferability: 9/10 (applies to any distributed team)
Feasibility:     6/10 (async UX is tricky)
```

## Step 5: Validation phase

For PoC scope, Validation is shortened to hypothesis prioritization and
feasibility. You list the critical hypotheses, prioritize them, and
define test methods.

::: tip If a critical hypothesis needs a test plan
The agent matches the hypothesis to the cheapest method that would
actually falsify it:

- [Wireframes, storyboards, and paper prototypes](../reference/methods-validation#wireframes-storyboards-and-paper-prototypes).
  Low-fidelity sketches of the risky flow. Best as a first test when
  the flow itself is the hypothesis.
- [Wizard of Oz](../reference/methods-validation#wizard-of-oz) when
  the feature is expensive to build (AI, automation, complex backend)
  and you want to see if users would even use it.
- [Appearance prototype](../reference/methods-validation#appearance-prototype)
  when the flow is clear and you are testing brand or visual trust.
- [Expert review](../reference/methods-validation#expert-review)
  when the question is "can this even exist" (regulation, technical
  feasibility, safety) rather than "do users want this".
:::

::: tip If you are unsure about the business side
- [Business plan](../reference/methods-validation#business-plan).
  A one-page Business Model Canvas with one sentence per cell and a
  number in every revenue and cost cell. Mark unsupported assumptions
  as the next hypotheses.
- [Value proposition quantification](../reference/methods-validation#value-proposition-quantification)
  to compare two or three candidate value propositions against
  evidence instead of gut feeling.
- [Pre-mortem](../reference/methods-validation#pre-mortem) before
  committing resources. "It is six months from now and the project
  has failed. Write down why." Five minutes silent per person, then
  cluster the reasons and assign owners to preventive actions.
:::

## Step 6: Produce the documents

The skill now creates two artifacts:

- `_devprocess/analysis/BA-<project>.md`, here `BA-retrospectives.md`: the BA record, five short answers from the dialog (the observed problem, who has it, the solution hypothesis with its strongest assumption, the scope, and the success signal with the top risk). A long form comes only on request.
- `_devprocess/analysis/EXPLORE-<project>.md`, here `EXPLORE-retrospectives.md`: the Exploration Board

The skill names both files after the project (`BA-<project>.md`, `EXPLORE-<project>.md`) and the branch after the topic (`docs/<slug>`), so the two names need not match.

Both follow the templates of the Pulse plugin,
[skills/pulse-ba/templates](https://github.com/pssah4/pulse/tree/main/skills/pulse-ba/templates)
on GitHub; a plugin install keeps them in its own folder, not in your
project.

## Step 7: Hand over

`/pulse-ba` lists the files it wrote and the HMW question, and commits the BA on its docs branch (`docs(ba): <title>`) with the scope, the HMW, the critical hypotheses, and the open questions in the commit body. Then it asks you to approve the BA, the first gate of the flow: in at most eight lines the problem, who has it, the solution hypothesis and its strongest assumption, the scope, the success signal, and the top risk, and then "Is this BA approved? Then I push the docs branch so the team can read it. Or what should change?"

Name what should change, and it goes into the BA before the question comes again. Until you approve, the branch stays on your machine. Approve it, and the BA becomes `validity: Validated`, the skill pushes the branch (`git push -u origin docs/<slug>`, here `docs/retrospectives`) so your team can read it, closes the Project-BA's draft with `pulse done`, and continues with [`/pulse-re`](../guides/pulse-re) in the same session without asking again.

`/pulse-re` opens the first epic of a new project straight from this Project-BA, without an Item-BA. A later epic starts with an Item-BA of its own: run `/pulse-ba` again and answer "a new epic" (or "a new feature" for a feature the BA of its epic does not cover).

Your agent asks before it runs these steps, unless its permission settings allow them. Claude Code, in the terminal and the VS Code extension alike, asks in its default mode before each file it writes, until you allow edits for the rest of the session, and before every shell command outside a small read-only set such as `git status`: here the new branch, `mkdir`, `git add`, each `git commit`, and the `git push`, and in `/pulse-re` also `pulse status`, `pulse check`, `pulse new`, and `gh pr create`. Every BA, this Project-BA included, runs `pulse status` and `pulse new` before its first question, and the Project-BA `pulse done` after the push. [Fewer prompts in Claude Code](./installation#fewer-prompts-in-claude-code) names the rules that let it run these without asking. Codex asks before the branch, the commit, and the push: its sandbox keeps `.git` read-only and has no network. Allow them when asked.

## What's next

- The BA document is the input for [`/pulse-re`](../guides/pulse-re),
  which turns it into Epics, Features, and tech-agnostic Success Criteria.
- Or let [`/pulse`](../guides/pulse) recommend the next step.
  See the next tutorial: [A full V-Model run](./full-v-model-run).
- The full set of method cards lives under
  [Discovery methods](../reference/methods-discovery),
  [Ideation methods](../reference/methods-ideation), and
  [Validation methods](../reference/methods-validation).
