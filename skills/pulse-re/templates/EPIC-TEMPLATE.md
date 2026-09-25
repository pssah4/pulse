---
title: {Name}
issue: {N}
scope: PoC | MVP
ba-ref: ../../analysis/BA-{slug}.md
hmw-ref: ../../analysis/BA-{slug}.md#3-solution-hypothesis-and-strongest-assumption
---

<!-- See skills/pulse-re/SKILL.md for how to fill. Save it under its slug;
     `pulse number --apply` names it epics/EPIC-{nn}-{slug}.md. `pulse new
     --parent <epic>` adds each feature to Items and each fix or improvement
     indented below its feature; `pulse check` (C9) keeps Items and the
     children's parent: links in step, C10 the IDs in the file names. -->

# Epic: {Name}

## Hypothesis

<!-- One paragraph of prose: the user, the problem, the solution category,
     the primary value, the current alternative, and the unfair advantage,
     in real sentences. Never the fill-in pattern "For {target segment} who
     {need}, {product} is a {category} ..." (see "Hypothesis statements as
     full prose" in skills/pulse-re/SKILL.md). -->

{Hypothesis paragraph}

## Business outcomes

1. {Metric} from {Baseline} to {Target} within {Timeframe}
2. {Metric} from {Baseline} to {Target} within {Timeframe}

## Critical hypotheses

| BA Ref | Hypothesis | Leading indicator | Validated by | Status |
|--------|-----------|-------------------|--------------|--------|
| H-01 | {Hypothesis} | {Indicator, source} | #{N} | Open |

## Items

<!-- One line per feature as `- [#n FEAT-{nn}-01 title](../features/FEAT-{nn}-01-slug.md)`,
     its fixes and improvements two spaces deeper below it. An item without a
     record yet is listed without `#n`; `pulse new` adds the number. Priority and effort
     live in each item's spec; the order lives in the ramp. -->

## Out of scope
- {Feature X}: {Rationale}

## Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| {Risk} | H/M/L | H/M/L | {Mitigation} |
