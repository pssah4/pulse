<!-- See skills/pulse-re/SKILL.md for how to fill -->

# Architect Handoff for {PROJECT}

**Author:** {Requirements Engineer} | **Target release:** {release or sprint}

## 1. Scope

- Scope: {Simple Test / PoC / MVP}
- Main goal: {from BA Executive Summary}
- Source BA: {path to BA-{PROJECT}.md}

## 2. Architecturally Significant Requirements

| ID | Source feature | Classification | Constraint | Notes |
|---|---|---|---|---|
| ASR-001 | #12 | Critical | {constraint} | {note} |
| ASR-002 | #13 | Moderate | {constraint} | |

## 3. NFR summary

| Category | Target | Source features |
|---|---|---|
| Performance (response time p95) | {ms} | #11 |
| Availability | {uptime %} | #13 |
| Scalability (concurrent users) | {N} | #12 |
| Security (authN, authZ, data class) | {list} | all |
| Compliance | {standard} | {features} |

## 4. Constraints

- Stack: {allowed languages, frameworks, prohibited choices}
- Integration: {existing systems, APIs to consume or expose}
- Operational: {deployment target, SRE owner, on-call rotation}
- Team: {skills available, out-of-scope}

## 5. Open Questions

- {open question 1}
- {open question 2}

## 6. Dialog

### Questions from Architect to RE

| ID | Date | Question | Addressed by | Status |
|---|---|---|---|---|
| Q-001 | YYYY-MM-DD | {question} | #N SC-NN | Pending |

### Answers from RE

| ID | Date | Answer | Affected artifacts | Status |
|---|---|---|---|---|
| A-001 | YYYY-MM-DD | {answer} | #N (SC-NN updated) | Resolved |

## 7. Ready-to-design checklist

- [ ] All Critical ASRs have quantified constraints
- [ ] NFR table has numbers, not adjectives
- [ ] Every feature listed in section 2 or 3
- [ ] Open questions categorized (blocker vs. async)
