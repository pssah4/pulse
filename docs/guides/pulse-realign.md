---
title: /pulse-realign
description: Take over a repository that predates Pulse. Walk existing code backwards into sourced drafts, or move a project from the predecessor plugin over.
---

# /pulse-realign

Two entry points, one command.

Pulse grew out of an earlier plugin, the Digital Innovation Agents (DIA for short, versions up to 4). A DIA project keeps its settings in `.dia/config.toml` and its work list in a `BACKLOG.md` file. `/pulse-realign` (in Codex `$pulse:pulse-realign`) starts with `pulse migrate`, which only reads: the DIA settings, the DIA blocks in the agent files, the backlog rows (open and done), and whether Pulse is already set up.

- A DIA project: **Mode B**, the migration.
- Code without DIA artifacts: **Mode A**, the reverse walk.
- Both: the migration first, then the reverse walk for the gaps.

## On the board

A realign writes all over `_devprocess/`, so only one runs at a time, and the team sees it from its first step. Before the first artifact, the skill looks for a realign in progress (`pulse status --json`). One that another person or session holds stays theirs: the skill stops, names who holds it, and takes it over only on your yes. Otherwise it registers the realign as a draft this session holds: `pulse new epic "Realign: <owner/repo>" --draft --phase analysis`. A second draft with the same title is refused, and the refusal names the first. From then on the board and every [map](./pulse-map) show the realign in progress and who runs it; the skill writes a heartbeat at the start of each step and closes the draft with `pulse done` once the work lives in its own records. The board needs Pulse set up with its labels: the reverse walk runs [`/pulse-setup`](./pulse-setup) first where Pulse is missing, the migration registers its draft right after it brought the settings over.

## Mode A: the reverse walk

Code tells you what exists, not whether it solves the right problem. The reverse walk writes sourced drafts, never guesses:

- **Every claim is sourced**, `path:line` for code, `doc:section` for documentation. No source means a placeholder: `[NEEDS USER INPUT. No evidence found in {sources}.]`
- **No persona from code structure**, and no How-Might-We question without an explicit problem statement in the existing docs.
- **Every file is marked** with its provenance and a validity (`Observed`, `Inferred from codebase`, `Anticipated`, `Draft (reverse-engineered)`) until [`/pulse-ba`](./pulse-ba) validates it.

The walk, scaled to Simple Test, PoC, or MVP:

1. **Codebase map:** manifests, entry points, tests, CI, existing docs. Count the entry points: every registration the stack uses, the config keys and env vars, stored data, and external services, counted per kind. This inventory is the source pool for everything after and what the gate checks the specs against.
2. **Navigation:** a system map with fast paths into the code, proposals for path-local AGENTS.md files.
3. **Decisions:** only visible, consequential, non-obvious ones, each with a read-when; the arc42 reference at MVP scope.
4. **Epics and features:** anticipated epics grouping observed capabilities, one feature spec per capability. Each observed behavior is a requirement with its source and its test (or `none`): every operation, every error a caller sees, every limit, every data contract a rebuild must keep. Operations such as install, start, and logging are features too. A success criterion carries the observed target; only a business target waits for the BA. A rerun completes the specs of an earlier realign in place. Every feature names its epic in `parent:`, every epic lists all its features under `## Items`, and `pulse number --apply` starts each file name with its ID (`EPIC-04`, `FEAT-04-02`), so a folder listing shows which features belong to which epic.
5. **BA draft:** from README, docs, and changelogs only; the header counts what came from sources and what still needs you.
6. **Findings:** TODOs, skipped tests, requirements without a test (one improvement per feature), outdated dependencies; each checked against the code before it counts.
7. **Records:** after the verification gate, every epic, every feature, and every verified finding gets a record, each pointing at its spec; a rerun skips a spec that has one. The epics and features describe code that exists: after one question, one `pulse done` call closes their records, so the board holds only open work and each epic counts its features as done. An epic with an open fix or improvement stays open. Nothing is approved before `/pulse-ba` and [`/pulse-re`](./pulse-re) validated it.
8. **Cleanup:** method files from earlier tools go once their content moved (see [below](#nothing-of-the-old-structure-stays)).

**Verification gate.** Before any record exists, three checks run:

- **Spec to code:** every feature spec and decision is checked against the code: source paths exist, sampled criteria are evidenced, drift is named. Drift beyond a one-line doc edit becomes an item of its own.
- **Code to spec:** every entry of the inventory points at a feature, or the report names it as internal, with the reason.
- **Rebuild reading:** fresh subagents read each spec without the code first and note every place where a rebuild would have to guess; then they read the code. What the code decides becomes a requirement.

### What you can rebuild from

The specs, the decisions, and the system map are the blueprint; the board carries only open work. The handoff reports in numbers: inventory entries covered and internal, requirements with and without a test, places the rebuild reading found and closed, and the open BA points. It says the product is rebuildable only when no inventory entry and no place of the rebuild reading stays open, and otherwise names what is missing. A rebuild from the specs gives today's product without the open fixes.

## Mode B: moving a DIA project to Pulse

```bash
pulse migrate
```

It only reads: what was found, which records would be created, what goes or stays. After you agree with it:

```bash
pulse migrate --local
pulse migrate --issues
pulse check
```

`--local` and `--issues` make one commit each:

| Step | Changes |
|---|---|
| `--local` | `.dia/config.toml` becomes `.pulse/config.toml`; a DIA mode `off` stays `off`, supply-chain settings are carried over. DIA anchor blocks are replaced in place. Work state leaves the frontmatter (a BA's `status` becomes `validity`). Then the tracked files in `.dia` and the git hooks DIA installed in this clone go; untracked files and a hooks folder other clones share stay and are named. `BACKLOG.md` stays until `--issues`. |
| `--issues` | Every open backlog item gets a record on the board, or reuses the GitHub issue DIA already created for it (titles like `FEAT-01-02: ...` or `[EPIC-01] ...`). Epics become parents, fixes and improvements hang under their feature, `depends-on` becomes "blocked by". Specs get `issue:` and keep their old ID as `legacy-id:`. An issue counts as one an earlier run made only with the ID in its body and its `pulse:` type label, and as DIA's only with a DIA-style title; either way only when its author is you or has write access to the repository; the preview shows every reuse and every claim it passes over, so a rerun creates nothing twice. `BACKLOG.md` goes only when every row got a record or is done and git tracks the file; otherwise the result says why it stays. |

Done items stay history and are not migrated. Both steps need a clean working tree and move to their own `chore/pulse-migrate-<date>` branch when started on a base branch. Old commit trailers and tags stay in the git history.

The rest of the DIA layout moves in the cleanup below:

| DIA path | Content goes to |
|---|---|
| `_devprocess/context/`: `BACKLOG.md` when `--issues` kept it, `BACKLOG-HISTORY.md`, `HANDOFFS.md`, `METRICS.md`, backups such as `BACKLOG.md.preMigration` | git history; open work in them becomes a spec and a record first |
| `_devprocess/architecture/`, `_devprocess/adr/` | `_devprocess/decisions/` with a router row; `arc42*.md` into `_devprocess/` |
| `_devprocess/implementation/plans/` | an open item's PLAN into `_devprocess/plans/`; done ones are history |
| `_devprocess/requirements/handoff/plan-context.md` | the PLAN or the system map |
| `_devprocess/rules/`, `src/ARCHITECTURE.map` | the agent guide or a path-local AGENTS.md; fast paths into `_devprocess/SYSTEM-MAP.md` |
| `dia.config.json`, `dia-migration.yml`, scripts only DIA used | not needed |

After the migration: uninstall the Digital Innovation Agents plugin, install Pulse ([Installation](../tutorials/installation)), and run [`/pulse`](./pulse). Teammates delete the git hooks DIA installed in their own clones (`.git/hooks/pre-commit` and `pre-merge-commit` with a DIA header, `.git/hooks-data/`).

## Nothing of the old structure stays

Both modes end with a cleanup. The old structure is the method and process files of the predecessor or an earlier layout: specs, backlogs, TODO lists, plans, decision notes, the predecessor's settings and folders, generated state. Your product code and user-facing docs (README, user and API docs) stay, unless their content moved into a new artifact and you agree.

- **Integrate, then delete.** Each old file's content goes to its new home first: a spec, the BA, a decision record, the system map, `.pulse/config.toml`, a record on the board. Once it is there, the old file goes with `git rm`. No archive copies: git history is the archive.
- **Tests too.** Tests of code that no longer exists, duplicates, one-off checks, and tests of the predecessor's tooling go. Tests of live code stay and still pass.
- **You decide once.** Before anything is deleted, you see one list: each old path and where its content lives now, or why it is not needed. A path git does not track is marked as gone for good and goes only if you name it. The deletions get a commit of their own.
- **Sweep.** A final search over the old paths and names, empty folders, and files nothing points at comes back empty, and the handoff shows it.
