# Parent BA promotion (full prompt)

The verbatim question `/pulse-re` asks when the parent BA is still a
Draft once the specs pass validation, before the commit in step 6 of its
workflow, so the promotion goes out with the specs. The SKILL.md keeps
only the summary.

## When the prompt fires

Parent BA resolution order:

1. `ba-ref:` in the new epic or feature spec (preferred, written by RE
   during this run).
2. The `Source BA:` line in
   `_devprocess/requirements/handoff/architect-handoff.md`.
3. The Item-BA in `analysis/` whose `issue:` matches the new item.
4. The Project-BA `_devprocess/analysis/BA-{PROJECT}.md` if it is the
   only BA in the project.

If no parent BA can be located unambiguously, skip silently and add one
line to the report (`Parent BA: not located, status promotion skipped`).
Do not block the registration.

## Question

Ask only when the BA frontmatter `validity:` is `Draft` or
`Draft (reverse-engineered, ...)`.

> Title: "Promote parent BA?"
> Question: "RE derived an epic, features, and an architect handoff
> from `BA-{NAME}.md`. The BA is still marked Draft. Promote it to
> Validated, in the commit with the specs?"
>
> Options (each with Pro/Con):
> 1. (Recommended) Promote to Validated
>    + Pro: BA exercised end-to-end through RE, validity reflects
>      reality, downstream readers see a content-bearing artifact.
>    - Con: marks the BA as validated even if you have not personally
>      walked every section since the co-creation dialog.
> 2. Keep Draft
>    + Pro: an explicit walkthrough via `/pulse-ba` Validation Mode
>      happens later; the change stays manual.
>    - Con: BA stays at Draft while the specs derived from it go up for
>      approval; later readers must guess the BA's reliability.
> 3. Other (free text)

## Apply on option 1

Update BA frontmatter:

```yaml
validity: Validated
validated-by: /pulse-re on {YYYY-MM-DD}
validated-via: handoff (epic + features + architect handoff)
```

Append a row to the BA's `## Validation Log` section (create the
section if it does not exist, after the first section):

```
| {YYYY-MM-DD} | /pulse-re | Validated through RE handoff: {N} epics, {M} features, architect handoff at `_devprocess/requirements/handoff/architect-handoff.md` |
```

Keep `created-by:` and `reverse-engineering-provenance:` (if set) in
place as historical record.

## Apply on option 2 or 3

Leave the BA frontmatter untouched. Note the decline in the report
(`Parent BA: kept at Draft per user request`).

## On Validated or other non-Draft

Skip silently. No prompt, no edit. Idempotent on later runs.

## Report lines

Pick one of the four:

- `Parent BA: BA-{NAME}.md, promoted Draft -> Validated`
- `Parent BA: BA-{NAME}.md, kept at {validity} per user request`
- `Parent BA: BA-{NAME}.md, already {validity} (no change)`
- `Parent BA: not located, status promotion skipped`
