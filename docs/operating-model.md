---
title: Operating model
description: How a team of people and coding agents works together in Pulse. Three tempos, a conscious filter, roles as hats.
---

# Operating model

> **A team operating model for AI-native development.**

Pulse has three parts:

```
Pulse
|- Operating model              rhythm: three tempos, conscious filter, roles as hats (this page)
|- Collaboration                presence, ramp, pulse go, the live map
`- Digital Innovation Agents    the V-Model method: BA, RE, plan, build, test, audit
```

The V-Model gives one person and their agents a structured walk from
problem to release. The operating model is what happens when several
people work the same product at the same time: it turns the walk into a
rhythm the whole team moves to. The collaboration tools make that
rhythm visible and run the parallel part. On this page, a *pair* is one
person working with their coding agents.

Not a process. A pulse. Regular, lightweight, essential.

## Why Pulse exists

Single-player AI development is a productivity question. One person,
one agent, optimise the prompts and the toolchain and ship.

Multiplayer AI development is a coordination question. Multiple people,
each with their own agent, working on the same codebase, each fast
enough to ship a feature in an afternoon. Agile frameworks like Scrum
or Kanban were built for human cycle times. None of them fit a team
where the bottleneck is no longer implementation and fast parallel
delivery, it is alignment.

Pulse exists because teams need something that does not slow the pairs
down but keeps them coherent.

## The shift

When a pair ships a feature in hours, three things change at once:

- **The plan becomes the product.** Writing code is cheap. Deciding
  what should exist is the expensive work.
- **Speed amplifies whatever is already there.** A team without
  structure ships incoherent features faster. A team with structure
  ships coherent ones faster.
- **The ability to say "no" matters more than the ability to say "yes".**
  Implementation cost no longer filters ideas. Something else has to.

The principles of product development have not changed. The cycle
time has. That changes how teams coordinate, not what they coordinate
on.

## The four values

In the spirit of the original Agile Manifesto, which worked because
it stated values and not procedures, Pulse values:

> **Shared artifacts** over status meetings.

> **Team coherence** over individual speed.

> **Conscious filters** over unlimited backlogs.

> **Structural governance** over approval gates.

**Shared artifacts over status meetings.** A coding agent has no memory
between sessions. A teammate does not know what you built yesterday.
Written artifacts are the only synchronisation that works for both
audiences. A spec, a decision record, a pull request. Not a standup,
not a Teams message.

**Team coherence over individual speed.** Each pair is fast. Speed
without direction is drift. A team that ships five coherent features
beats a team where three pairs each ship five uncoordinated ones.

**Conscious filters over unlimited backlogs.** When implementation is
cheap, every idea feels worth building. Pulse prevents ideas from
becoming work without passing through a deliberate filter. That filter
separates a product team from a feature factory.

**Structural governance over approval gates.** Nobody wants to wait
for someone to sign off a PR at 11pm. People decide what gets built
and whether the result goes in. Everything in between runs on
structure: tests, fitness functions, a reviewer agent in a fresh
session, conventions that agents and humans follow equally. The rules
live in the code and the specs, not in someone's calendar.

## Three layers, three tempos

This is the part that distinguishes Pulse from Scrum, Kanban, or
Shape Up. Instead of one cadence for everything, three tempos run at
the same time.

| Layer | Cadence | What it produces |
|---|---|---|
| Execution | Hourly | Working features, PRs, updated artifacts |
| Coordination | Daily | Shared situational awareness, blocker resolution |
| Product | Weekly to bi-weekly | Direction, learning, roadmap fit |

### Execution layer (hourly)

Each person works with one or more agents. The next item comes from the
ramp (approved, specified, planned, not blocked, not taken), and
`pulse go` plans, builds, reviews, and lands it. In hours, not weeks. One
constraint:
nobody works on something that has not passed the filter. Spontaneous
ideas go to the Ideas channel, not directly into code.

The V-Model walk runs inside this layer: [`/pulse`](/guides/pulse)
says where things stand and what comes next, the phase skills
([`/pulse-ba`](/guides/pulse-ba), [`/pulse-re`](/guides/pulse-re),
[`/pulse-build`](/guides/pulse-build) with its [planning](/guides/pulse-plan)
and [review](/guides/pulse-review) steps,
[`/pulse-audit`](/guides/pulse-audit)) cover partial cycles, and
[`/pulse-go`](/guides/pulse-go) plans and builds every approved item at
once, each in its own worktree ([Parallel work](/concepts/parallel-work)).
Pulse stops for a person only [where a person decides](/concepts/v-model#where-pulse-stops-for-you):
the BA, each spec (`pulse approve` means build it), a PLAN that something
holds, and the merge. Between those points the phases hand over without
asking; nobody passes approved work on by hand, and the order in the ramp
(`pulse rank`) decides what an agent takes next.

### Coordination layer (daily)

The team synchronises through three lightweight rituals:

- **Async status (daily, 2 min writing).** What is done, what is next,
  any blockers. Structured, not prose. `pulse status` and the
  [live map](/guides/pulse-map) already show who holds what, in which
  phase, what waits, and which BAs and specs are being written, so the
  status only adds what the board cannot know.
- **Sync call (twice a week, 30 min).** Not "what did you do", that is
  in the async status. Resolve blockers, review ideas from the Ideas
  channel, adjust priorities.
- **Merge (continuous, async).** Before a PR reaches a person, a
  reviewer agent in a fresh session has checked it against its spec,
  PLAN, and decisions ([review](/guides/pulse-review)) and put the
  verdict into the PR. The person reads the PR at feature level (does
  it deliver what the spec promised?) and merges. Architecture
  conformance, duplicates, dead code, and syntax are the agents' job.

Total meeting overhead: under 2.5 hours per week.

### Product layer (weekly to bi-weekly)

Direction, not tickets.

- **Direction session (every two weeks, 90 min).** Replaces sprint
  planning, sprint review, and retrospective in one. Focus: what 3 to
  5 outcomes do we want in the next two weeks? What did we learn?
  What needs to change?
- **Repository review (every two weeks, before the direction
  session).** [`/pulse`](/guides/pulse) offers it when the last one is
  older than two weeks. It looks for drift no single PR shows:
  hotspots, duplicates, dead code, decisions the code stopped
  following. Its findings feed the direction session.
- **Roadmap review (monthly, 60 min).** Does the roadmap still match
  the Business Analysis?

The three layers are nested. The execution layer runs continuously
inside the coordination layer, which runs inside the product layer.
A pair might ship three features in a single day while the product
direction stays stable for two weeks.

## The shared context layer

This is where Pulse lives or dies. Coding agents have no memory
between sessions. Teammates do not know each other's context. Shared
artifacts are the only synchronisation that works, and each fact has
one home ([Where things live](/concepts/where-things-live)):

- The board on GitHub: one record per item, written by the `pulse`
  commands. Draft (a BA or spec is being written), ready, taken
  (assignee, with the phase and last sign of life of the holding
  session), blocked (waits for another item), in review (open pull
  request), done (closed). Epics and features form the hierarchy
  through parent links.
- [`BA-{PROJECT}.md` plus an Item-BA per epic or feature the Project-BA does not cover](/guides/pulse-ba):
  the product north star and the item-level discovery. It lives across
  releases through the
  [Post-Release Review](/guides/pulse-ba#phase-8-post-release-review-ba-as-living-document).
- [Epic and feature specs](/guides/pulse-re) in `_devprocess/requirements/`:
  the unit of work, written tech-agnostic so anyone, person or agent,
  can pick them up.
- [PLANs and decision records](/guides/pulse-plan): how an item gets
  built, and the decisions that constrain later changes, found through
  the "Read When" column of `decisions/README.md`.
- `architect-handoff.md`: the bridge from requirements to the plan.
  Questions a person cannot answer alone travel as pull request
  comments or come up in the sync call.
- Pull requests and commits: every commit names its item
  (`Refs: #<n>`), every pull request closes one.
- `AGENTS.md`, `CLAUDE.md`, and the Pulse rules: institutional memory
  and working rules, loaded into every session and every subagent.

Every artifact serves two audiences: humans who need alignment, and
agents who need context. If a teammate can read it, an agent can read
it. If an agent needs it, a teammate needs it too.

## Seeing each other's work

Nobody has to ask what a teammate is doing. Work reaches the board the
moment a `pulse` command writes it, and the [map](/guides/pulse-map)
shows each item a teammate holds or writes:

- `spec in progress by alice, 20 min`: Alice's BA or spec session
  registered the item as a draft. Talk to her before you write about
  the same thing.
- `building, 4 min ago`: the phase of the session that holds the item
  and the age of its last sign of life. `pulse go` reports each phase
  it starts, and every 10 minutes while one runs; an interactive
  session reports `working` at most every 10 minutes.
- `no sign of life for 2 h`: the holding session has been silent for
  30 minutes or more. It may have ended.
- `last run: <note>` on a free item: a `pulse go` run gave it back
  after a failure, a usage limit, or a stop, or a session with
  `pulse release <n> --note`, and says why and which branch holds its
  work.

Work moves with the item branch, which `pulse go` pushes after every
agent phase that committed. A free item with a note is claimed like
any other, and the next holder builds on that branch. An item another
person holds stays theirs until they agree; then
`pulse release <n> --take` hands it over, and the new holder continues
on the branch they pushed. What stays in each clone, and when the rest
reaches the team, is in
[Where things live](/concepts/where-things-live#what-the-team-sees-and-when);
[Parallel work](/concepts/parallel-work#what-others-see) has the
details.

## The conscious filter

The most important part of Pulse is what it prevents.

When implementation is cheap, the temptation is to turn every idea
into a feature immediately. Pulse creates a deliberate pipeline:

```
Ideas channel  ->  Sync call filter  ->  Approved  ->  Ramp  ->  Work
   (free flow)    (10 min review,      (pulse       (order:    (pulse go:
                  matches against BA   approve,     pulse      plan, build,
                  and roadmap)         label        rank)      review, land)
                                       pulse:approved)
```

The filter is lightweight. It happens in 10 minutes during the sync
call. But it exists. Its existence keeps the product coherent.

Nobody works on anything that has not passed the filter. Discoveries
made mid-implementation become new items ("Discovered in #n") and go
through the same filter via the
[cross-phase feedback triggers](/concepts/v-model#the-v-is-iterative),
not through ad-hoc code changes.

## Communication channels

Four channels, in any tool the team uses (Teams, Slack, Discord):

| Channel | Purpose | Example |
|---|---|---|
| Ideas | Free-flowing impulses | "Could we add a CSV export?" |
| Async status | Daily structured updates | "Done X, next Y, blocked on Z" |
| Pull requests | Collecting PRs waiting for a merge, questions at feature level | "PR-42 lands the CSV export, ready to merge" |
| Direction | Bi-weekly outcome decisions | Direction session notes |

If something is in Ideas, it is an impulse. Only when it passes the
sync call filter and gets approved (`pulse approve`) does it become work.

## Roles as hats

In a 3 to 4 person team, these are hats, not dedicated positions:

| Hat | Responsibility |
|---|---|
| Product direction | Owns the BA, runs the direction session, calls the filter decisions |
| Architecture | Owns the decision records the reviewer agent checks every PR against |
| Quality | Owns testing strategy, security findings, and the checks |

The person wearing the product direction hat still builds and ships
features. These are responsibilities, not full-time jobs.
The hats move. Whoever is closest to a decision wears the hat for it.

## The operating model and the method

The operating model defines how a team works together. The Digital
Innovation Agents define what happens inside one item: the walk from
business analysis through requirements, plan, build, and test to the
security audit. The walk is not strictly linear. The
[V is a decision graph](/concepts/v-model#the-v-is-iterative) with four
cross-phase triggers (bug, design, requirements gap, missing
capability) that close the iteration loop.

The team tempos consume what the walk produces. The sync call reads
`pulse status` and the live map. The direction session reads closed
items and merged pull requests against the BA. The conscious filter
reads against the BA. Nothing in the operating model asks anyone to
produce extra artifacts.

## What Pulse is not

- **Not anti-planning.** The Direction Session is planning. It is
  compressed and focused on outcomes, not estimation.
- **Not anti-meeting.** It defines fewer meetings, sharper meetings,
  and more written async work.
- **Not a complete framework.** It is a starting point. Teams adapt
  the cadences and the filter to their reality, the same way teams
  adapt Scrum.
- **Not Scrum's replacement on principle.** Scrum solved a real
  problem. The problem has changed. Teams that already work well with
  Scrum can keep what fits and pull in what closes their gaps.

## Adoption notes

To run Pulse you need:

1. The Pulse plugin installed ([Installation](/tutorials/installation))
2. A GitHub repository (Pulse keeps its records there) and the GitHub CLI `gh` 2.94 or newer
3. `/pulse-setup` once per project (in Codex `$pulse:pulse-setup`):
   config, labels, the anchor block in the agent files

Once that runs, the rituals layer on top. Start with the async status
and the sync call. Add the direction session at the first natural
rhythm break. The roadmap review can wait until the first month is in.

## Open conversations

Pulse is not finished. The article that introduced it
([LinkedIn, April 2026](https://www.linkedin.com/in/sebastian-hanke-product/))
attracted dozens of substantive challenges. The ones that shaped the
workflow are recorded here, with the answer as it stands today. Each is a real critique
with a real reply. The replies that prompted code changes link to the
feature that closed the gap.

### "The V looks like waterfall"

Helder A. (Agile Coach):

> While PULSE seems to espouse some constructs aimed at building
> shared understanding, it relies heavily on handoffs in a linear
> workflow. Shared understanding comes from interaction, not docs.

Reply. The V-Model phases are sequential. That is true. The
difference to waterfall: in waterfall, each phase runs once and gets
thrown over the fence to a different team. In Pulse, the same pair
runs through all phases in hours. The handoffs are not between
people, they bridge agent sessions that have zero memory. Without
`architect-handoff.md`, the next agent session does not know what the
previous one decided.

The artifacts do not replace conversation. They make conversation
productive. Sync calls, pull request threads, and the Ideas channel
are the interaction loops. The docs ensure those conversations are not
wasted on "wait, what did you build yesterday?".

What changed:
[the V is iterative](/concepts/v-model#the-v-is-iterative) makes
explicit that the V is a decision graph with cross-phase triggers. The
forward walk is the default, iteration is a first-class option.

### "Architecture decisions get made implicitly"

A mobile engineering lead asked:

> ADRs record decisions, but architecture emerges the moment the
> first code lands in the repo, before any decision is named. With
> five parallel pairs the first merge holds de facto authority. How
> does PULSE catch these implicit commitments before the next
> Direction Session can react?

Reply. Two mechanisms close this gap.
[`/pulse-realign`](/guides/pulse-realign) discovers
implicit and explicit design decisions that already exist in the
codebase and records them as decision records marked `Inferred from
codebase`, so the next person adapts to a named decision instead of an
unnamed pattern.
[`/pulse-build`](/guides/pulse-build) runs a critical review against the real
codebase before any new feature implementation begins. If the
existing code conflicts with a planned decision, the record is
amended before the implementation, not after.

What changed: the
[design trigger](/concepts/v-model#the-v-is-iterative) formalises the
second pattern. Code that proves a design wrong amends the decision
record first, in the same flow as the bug trigger. With parallel
builds, the first merge no longer holds silent authority either: the
ramp keeps items that touch the same files apart, and the integration
check at the end of a `pulse go` run merges the ready branches in
dependency order and runs the tests on the result.

### "The reading budget per person is not in the model"

Mark Zimmermann (second comment):

> When a pair generates 60 pages of context in two days, nobody
> absorbs it all and consensus shifts to whoever summarises loudest.
> PULSE names three tempos, but the reading budget per person is not
> in the model. Have you found a compression layer for this?

Reply. Partly. The constraint is real. The method is built so the
agents read the artifacts in full and the humans read the shape. The
sync call reads `pulse status` and the live map, not the specs: who
holds what, what waits on whom, what goes out next. That covers
"who does what". A narrator that condenses the content of the latest
artifacts is still open. Until then, the asymmetry holds: agents
absorb depth, humans absorb shape.

### "Where does the Verifier role live?"

Mark Zimmermann (third comment):

> The InfoWorld piece framed it as a coordination-layer failure. DORA
> 2025 finds AI is negatively correlated with delivery stability when
> control systems lag behind change volume. Three tempos buy you the
> control surface. Open question: where in PULSE does the Verifier
> role live, with the pair, the reviewer, or the artifact itself?

Reply. The verifier lives in the artifact and the workflow, not the
person. The [verification gate](/concepts/verification-gates) arrives
through the Pulse hooks in every session and every subagent, so no
completion claim goes out without fresh evidence. The
[Security Audit](/guides/pulse-audit) phase runs OWASP, OWASP LLM,
SAST, SCA, and Zero Trust checks before release. A reviewer agent in a
fresh session checks every item against its spec, PLAN, and decisions
before its PR leaves draft. The person who merges judges whether the
feature does what its spec promised.

The Digital Innovation Agents are part of Pulse. Every team can adapt
and add skills for their own needs. Treat Pulse as a starting point,
not a process manual.

### "The signal layer is missing"

Martin König (Senior Atlassian Architect):

> Good operating model. I am missing the signal layer for
> observability. Without it, you do not really see if the system is
> pulsing in the right direction or just moving fast somewhere else.

Reply. This was the most actionable critique. The predecessor of Pulse
answered it with a hand-kept `METRICS.md`; Pulse drops that file, because a file the
agents must remember to update drifts. The signal now comes from where
the work already happens: the live map shows the pulse of the moment
(who works, who waits, what is red), and the timestamps of item records and pull requests
timestamps carry cycle time, blocked time, and throughput. A report on
top of those timestamps is still open. BA hypotheses keep their
validation status in the BA, where the direction session reads it.

### "Kanban has rhythm"

Björn Schotte (Mayflower GmbH):

> Kanban itself is based on rhythm, and you set your rituals at a
> pace the system needs. "Kanban has no rhythm" is wrong.

Vlad Georgescu (Optimistic Tech Leader):

> Why would Kanban not work with delivering full epics or full
> components multiple times per day? In a two-week sprint, instead of
> 20 stories, we might deliver 20 epics, each with 20 stories.

Reply. Both are correct that Kanban can carry a rhythm. Pure Kanban
is a pull system without prescribed cadences. With STATIK or
replenishment meetings, it gains the cadences explicitly.

Pulse is essentially Kanban with three explicit cadences bolted on.
The execution layer is a pull system. The coordination and product
layers add the rhythm that the team found missing when they tried
pure Kanban with agents working asynchronously at wildly different
speeds.

The broader point stands: bad planning was always bad planning,
agents or not. Pulse is not anti-planning, it is anti-ceremony. The
Direction Session is planning, just compressed and focused on
outcomes.

### "Decision provenance"

Yauheni Kurbayeu (Provenance Manifesto):

> The natural next step is decision provenance: preserving not only
> the artifacts but the decision lineage behind them, so teams and
> agents inherit the why, not just the latest file.

Reply. Provenance is exactly the design intent of the artifact set.
[Writeback](/concepts/v-model#writeback) keeps decision records and
specs in sync with the code. Decision records in MADR format carry
context, decision, alternatives, and consequences. Every commit names
its item, every pull request closes one, every item's record links its spec.
The [traceability chain](/concepts/v-model#the-traceability-chain)
means any line of code traces back to a business motivation in the BA.

### "Speed asymmetry is the real problem"

Ben Gusberg (AI for Partnerships, ex-Stanford):

> When anyone can ship a feature in an afternoon, the bottleneck
> moves to coordination and vision alignment almost overnight. Most
> teams are not ready for that shift.

Mattias Tronje (Transformation Lead):

> You are describing at team-scale what keeps breaking at org-scale.
> Three devs with three agents building three implementations is the
> micro version of three functions deploying three AI tools that
> cannot talk to each other.

Sami Niemelä (Head of Design, In Parallel):

> Where many current processes fail to output sufficient quality is
> exactly that design is only a box in the process instead of
> horizontal capability throughout.

Reply (collected). All three are pointing at the same edge: Pulse was
designed for a single-team, single-codebase setting. Cross-team flows
need a layer above Pulse that Pulse does not yet describe. Design as
a horizontal capability is similarly a gap, not a position.

These are open. The repo is open source for exactly this reason:
teams that stretch Pulse past its current scope will find the
breakpoints first, and contributions back are the way the framework
matures.

## References

- [LinkedIn article: Introducing PULSE](https://www.linkedin.com/in/sebastian-hanke-product/) (April 2026)
- [The V-Model](/concepts/v-model)
- [Parallel work](/concepts/parallel-work)
- [Where things live](/concepts/where-things-live)
- [Verification gates](/concepts/verification-gates)
- [Artifacts reference](/reference/artifacts)
- [GitHub repository](https://github.com/pssah4/pulse)
