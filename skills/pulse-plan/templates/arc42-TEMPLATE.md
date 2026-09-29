<!-- Written only when a person asks for it, for auditors or customers who
     need a formal architecture document. Agents plan from the code, the
     system map, and the decision records; this file may lag behind them
     and says so. Cap-exempt. Project file: _devprocess/arc42.md. Keep all
     12 sections; one line "Nothing to say yet." is enough where a section
     has no substance. -->

# arc42: {project}

> Written on request. The code, `_devprocess/SYSTEM-MAP.md`, and the
> decision records are the current sources; this document may lag
> behind them.

## 1. Introduction and goals

{What the system does and for whom, in three sentences.}

| Priority | Quality goal | Concrete scenario |
|----------|--------------|-------------------|
| 1 | {goal} | {stimulus -> expected response} |

## 2. Constraints

| Type | Constraint | Background |
|------|------------|------------|
| Technical | {constraint} | {reason} |
| Organizational | {constraint} | {reason} |

## 3. Context and scope

{C4 context: system, external actors, technical interfaces.}

| Interface | Protocol | Purpose |
|-----------|----------|---------|
| {interface} | {REST / events / ...} | {purpose} |

## 4. Solution strategy

| Decision | Technology | Decision record |
|----------|------------|-----------------|
| {decision} | {technology} | ADR-{nn} |

## 5. Building block view

{Level 1 building blocks; deeper levels only when they carry a decision.
The directory tree itself is not repeated here.}

## 6. Runtime view

{Only the flows an auditor must understand; one sequence per flow.}

## 7. Deployment view

{Environments, pipeline, artifact flow.}

## 8. Crosscutting concepts

{Security, persistence, error handling, logging: one paragraph each that
applies.}

## 9. Architecture decisions

| Decision record | Title | Decision |
|-----------------|-------|----------|
| ADR-{nn} | {title} | {one-line summary} |

## 10. Quality requirements

| Scenario | Stimulus | Response measure |
|----------|----------|------------------|
| {scenario} | {stimulus} | {measurable response} |

## 11. Risks and technical debt

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| {risk} | H/M/L | H/M/L | {mitigation} |

## 12. Glossary

| Term | Meaning |
|------|---------|
| {term} | {meaning} |
