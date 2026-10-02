# Parent BA validity at handoff

Before committing the RE handoff, record whether the parent BA's claims
have been validated by the dialog and cited evidence. This is an evidence
assessment, not a separate approval gate.

## Find the parent

1. `ba-ref:` in the epic or feature spec.
2. `Source BA:` in `_devprocess/requirements/handoff/architect-handoff.md`.
3. The Item-BA whose `issue:` matches the item.
4. The sole Project-BA `_devprocess/analysis/BA-{PROJECT}.md`.

If none can be located unambiguously, report `Parent BA: not located,
status promotion skipped`. Registration can continue where its own
requirements are settled.

## Record the evidence

A Draft becomes Validated only when its claims have support and required
input is complete. Creating derived specs alone does not prove this.
Ask about a missing fact or conflicting assumption when needed; do not
ask a routine "approve BA" question. A user request to keep Draft wins.

For a supported transition, update:

```yaml
validity: Validated
validated-by: /pulse-re on {YYYY-MM-DD}
validated-via: handoff (epic + features + architect handoff)
```

Append a Validation Log row naming the date, dialog or sources that
settled the claims, and the resulting handoff. Preserve `created-by:`
and `reverse-engineering-provenance:`. Commit the update with the specs.
An already validated BA needs no new marker. If input remains open,
keep Draft and name that input; only dependent work waits.

## Report

State the BA path and one outcome: validated with its evidence, kept at
Draft with the unresolved input or user request, already valid, or not
located. This assessment authorizes no integration. The final checked
result needs its own head/base approval later.
