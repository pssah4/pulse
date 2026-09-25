---
type: ba
target-type: improvement | fix
issue: {N, once the item has a GitHub issue}
project-ba-ref: {path to BA-PROJECT.md, or null}
personas: []
project-kpi-ref: []
scope: simple-test
created: YYYY-MM-DD
---

<!-- See skills/pulse-ba/SKILL.md for how to fill. The parent feature is the GitHub parent issue, not a frontmatter field. Cap: 40 lines. -->

# Mini-BA: {Item title}

## 1. Observed behaviour

{FIX: what the user sees today that is wrong. IMP: what works but is unsatisfying. One sentence.}

## 2. Root cause hypothesis

{Best current hypothesis. Mark unverified assumptions with `Assumption:`. One sentence.}

## 3. Impact

| Dimension | Value |
|-----------|-------|
| Affected personas | {P1, P3 from Project-BA, or empty} |
| Frequency | {daily / weekly / per-release / one-off} |
| Severity | {blocker / major / minor / cosmetic} |
| Business impact | {one sentence: retention, revenue, support load} |

## 4. Acceptance

- [ ] {observable acceptance criterion 1}
- [ ] {observable acceptance criterion 2; FIX includes regression test, IMP includes the proving signal}

## 5. Risk and assumptions

- Risk: {one sentence on what could go wrong if we change this}
- Assumption: {strongest assumption that, if wrong, invalidates the BA}
- Project-BA refs touched: {persona IDs / KPIs affected, or empty}
