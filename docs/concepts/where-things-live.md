---
title: Where things live
description: Content in the repository, state on a shared board on GitHub, rules in hooks, truth in the code. Each fact has one home.
---

# Where things live

Most drift between documents and code comes from one fact living in two places. Pulse gives every kind of fact exactly one home and never copies it.

| Fact | Home | How agents reach it |
|---|---|---|
| What an item is and why: business analysis, epics, features | Markdown in `_devprocess/`, in your repository | the spec path in the item's record; for the active item the hooks hand it over |
| How an item gets built: tasks, files, decisions | the PLAN in `_devprocess/plans/` | `pulse show <n>`; the ramp reads the files list |
| The state of each item: draft, approved, taken, blocked, in review, done | the board on GitHub, one small record per item | `pulse status`, `pulse show <n>`, from a local cache |
| Who works on an item, in which phase | the record's assignee and the claim mark of the session that holds it | `pulse claim <n>`, `pulse beat <n> <phase>` |
| Order and dependencies | parent and "blocked by" links between records | the same queries |
| Decisions that constrain later changes | `_devprocess/decisions/`, behind a router | the "Read When" column of `decisions/README.md` |
| Rules for every session | the Pulse hooks | injected at session start and into every subagent |
| Rules for one area of the code | a path-local `AGENTS.md` | loads when an agent reads a file in that area |
| What the system does | the code and its tests | always read first |
| History and authorship | git and pull requests | `git log` |

## The board on GitHub

The board is where the state of every item lives: one small record per item, and nothing else. Nobody writes tickets there, and only the `pulse` command changes it. The content of an item (what it is, why, how it gets built) stays in its spec and PLAN in the repository.

### Why state does not live in the repository

With parallel work, every agent builds in its own worktree on its own branch. A backlog file in the repository exists once per branch: a claim written in one worktree stays invisible to the others until someone merges, so two agents can take the same item, and every merge collides in the same table. State has to live outside the branches, in one place that every worktree and every teammate sees at the same moment. That place is the board, and a claim on it is visible to everyone at once.

### What a record holds

An item gets its record the moment someone starts writing about it. `/pulse-ba` and `/pulse-re` register it as a draft (`pulse new feat "<title>" --draft`), which returns its number and holds the item for the session that writes. Once the spec is written and pushed, `/pulse-re` attaches it with `pulse new feat "<title>" --spec <path> --issue <n>`, and the draft ends. Without a draft, `pulse new feat "<title>" --spec <path>` creates the record and the link in one step. The spec keeps the number as `issue:` in its front matter. From then on the item is known everywhere as `#<n>`, and its branch is named after it (`feat/<n>-<slug>`).

A record holds only what everyone needs to see at a glance:

| Field | Meaning |
|---|---|
| title, type | `epic`, `feat` (feature), `imp` (improvement), `fix` |
| draft | a BA or spec is being written for it; a draft cannot be approved, and no agent builds it |
| approved | the team wants it built (`pulse approve`); whether an agent can start also depends on its spec and PLAN |
| plan approved | a person approved its PLAN (`pulse approve-plan`); with `plan_approval = "auto"` Pulse approves a PLAN nothing holds without writing this |
| assignee | who works on it; one person per item |
| claim mark | a comment that names the session holding the item, its phase, and the time of its last sign of life |
| note | a comment left when the item goes back, by a `pulse go` run or by `pulse release <n> --note`: why, and the branch with its work |
| parent | the epic or feature it belongs to; the spec names it too (`parent:`), so the tree survives in the repository |
| blocked by | items that have to be done first |
| open or closed | closed means done; a merged pull request with `Closes #<n>` closes it (merged into a base branch other than the default, the next `pulse status` or `pulse go` closes it) |
| spec | the path of the Markdown file in the repository, on origin |

The `pulse` commands write these records; nobody edits them by hand, and the content of an item never goes there. Technically each record is a GitHub issue with a `pulse:` label, which brings sub-issues, dependencies, assignees, and the link to pull requests without an extra server. You can look at them on GitHub. You do not need to.

## What the team sees, and when

Your work reaches the team in three places. The board shows state the moment a `pulse` command writes it. The remote (`origin`) shows files and commits once they are pushed. Everything else stays in your clone.

| What | Where it lives | Others see it from |
|---|---|---|
| A BA in progress | board: a draft, held by your session in the phase `analysis`; the BA itself in your clone, on `docs/<n>-<slug>` | the draft: when `/pulse-ba` starts (`pulse new <type> "<title>" --draft --phase analysis`). The BA text: once you approve the BA and the skill pushes the docs branch |
| A spec in progress | board: a draft in the phase `spec`, with a heartbeat each time the session runs `pulse beat <n> spec`; the spec in your clone, on the docs branch | the draft: when `/pulse-re` names the item (`pulse new <type> "<title>" --draft`). The spec text: the push of the docs branch |
| A registered spec | origin: the spec on the pushed docs branch; board: the record links its path | `pulse new ... --spec <path>`, with `--issue <n>` for a draft, which ends the draft. It refuses until the commit with the spec is on origin |
| Approval | board: the `pulse:approved` label | `pulse approve <n>`, or `a` on the map. Both refuse until the spec is merged into the base branch on origin (R1), and for a feature, improvement, or fix while that spec breaks R2 to R6 |
| A claim | board: the assignee and a claim mark with the session, its phase, and the time of its last heartbeat | at once. `pulse go` reports each phase it starts, and every 10 minutes while one runs; an interactive session reports `working` at most every 10 minutes while it holds an item; a skill runs `pulse beat <n> <phase>` |
| The files an item holds | board: the claim carries the `files:` of the item's PLAN, pushed or not, or the files a hotfix names | at once: every ramp keeps other items off those files without a fetch |
| The work: PLAN and commits | your clone until pushed, then origin, on the item branch `<type>/<n>-<slug>` | the push. `pulse go` pushes after every agent phase that committed; in a session, planning pushes the PLAN and `/pulse-build` pushes after every commit |
| A note on hand-back | board: a comment on the item that says why the work stopped and which branch holds it | when `pulse go` gives the item back after a failure, a usage limit, or a stop, or a session gives it back with `pulse release <n> --note "<why>"` (`/pulse-build` does so when it stops before the item is done) |
| Pull request and verdicts | origin: the pull request, with the gate results and the review and audit reports in its text, and the verdicts as comments with one hidden marker per gate and commit; the verdicts `pulse go` or `--publish` put on at once share one comment (`pulse review <n> --publish`) | the pull request |
| Lights, logs, kept verdicts | your clone, under `.git/pulse/`: the board cache, the agents' lights, the logs and report of `pulse go`, the kept review and audit verdicts | never; verdicts and reports reach the team on the pull request. The worktrees of one clone share all of it |

The [map](../guides/pulse-map) turns this into one line per item. A teammate's item without a pull request shows the phase and the age of the last heartbeat (`building, 4 min ago`), and after 30 minutes without one, `no sign of life for 45 min`. A draft shows `spec in progress by <login>`, and a free item given back with a note shows `last run:` and the first line of that note. [Parallel work](./parallel-work#what-others-see) says what to do about each.

## What that rules out

- **No status in documents.** A spec carries `issue:` and links to other documents, nothing about progress. `pulse check` flags `status`, `phase`, or `claim` in any `_devprocess` front matter.
- **No backlog file.** `pulse status` and the [map](../guides/pulse-map) render the board from the records.
- **No code paths in decisions.** A decision record explains a choice; the files that embody it go into its Sources appendix, which may go stale.
- **No re-documenting.** What code, tests, git, pull requests, or the records already carry is not written down again.

## What reading costs

The board saves reading where an agent needs to find its way, not where it does the work. Without it, the questions "what can I start, what waits for what, who has what" mean reading a backlog file that grows with every item, or opening several specs. With it, `pulse status` answers in a few lines from a local cache: a free check every two seconds asks GitHub whether anything moved, and only a change (or 30 seconds) reloads the cache in the shared git directory; `status` and `show` answer from it in milliseconds, and offline with the last known state. Every write goes straight to GitHub and drops the cache.

The work itself costs the same. An agent reads the spec and the PLAN of the item it builds, in full, because that is what it builds from. What it no longer reads is everyone else's. With ten items the difference is small; with a hundred items and five agents it adds up.
