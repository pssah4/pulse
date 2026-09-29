---
title: Where things live
description: Content in the repository, state on a shared board on GitHub, rules in hooks, truth in the code. Each fact has one home.
---

# Where things live

Most drift between documents and code comes from one fact living in two places. Pulse gives every kind of fact exactly one home and never copies it.

| Fact | Home | How agents reach it |
|---|---|---|
| What an item is and why: business analysis, epics, features | Markdown in `_devprocess/`, in your repository | the spec path in the item's record; for the active item the hooks hand it over |
| How an item gets built: tasks, files, decisions | the PLAN in `_devprocess/plans/` | `pulse status <n>`; the ramp reads the files list |
| The state of each item: draft, approved, taken, blocked, in review, done | the board on GitHub, one small record per item | `pulse status`, for one item `pulse status <n>`, from a local cache |
| Who works on an item, in which phase | the record's assignee and the claim mark of the session that holds it | `pulse claim <n>`, `pulse status <n>` |
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
| approved | the team wants it built (`pulse approve`), the label `pulse:approved` with a comment `gate 1 approved by <name> (@<login>)`; `pulse go` counts it only when whoever added the label may push. Whether an agent can start also depends on its spec and PLAN |
| plan approved | a person approved its PLAN (`pulse approve <n>` once the PLAN waits): the line `Plan-ok: <plan blob> <spec blob>` in the issue, the ids git gives the PLAN on origin and the spec on the base branch, and the comment `plan ok at <plan blob> <spec blob>: gate 2 approved by <name> (@<login>)`. It counts only with that comment from someone who may push, and only for that PLAN and spec: a change of either waits for a new approval. The line alone counts for nothing |
| hold | a person set the label `pulse:hold` in GitHub: `pulse go` neither plans nor builds the item until the label is gone |
| failed | `pulse go` gave up on the item: the label `pulse:failed` and a comment `pulse go: failed at <base>: <reason>`; no run plans or builds it until `pulse approve <n>` takes the label off |
| assignee | who works on it; one person per item |
| claim mark | a comment that names the session holding the item, its phase, and the time of its last sign of life |
| note | a comment a `pulse go` run leaves when it gives the item back: why, and the branch with its work |
| parent | the epic or feature it belongs to; the spec names it too (`parent:`), so the tree survives in the repository |
| blocked by | items that have to be done first |
| open or closed | closed means done; GitHub closes it when a pull request with `Closes #<n>` merges into the default branch. Into another base branch, `pulse go` closes the item after it merged its pull request, and at its next start after someone else merged one on GitHub; `pulse status` only reads. An item you drop, you close on GitHub |
| spec | the path of the Markdown file in the repository, on origin |

The `pulse` commands write these records; nobody edits them by hand, and the content of an item never goes there. Technically each record is a GitHub issue with a `pulse:` label, which brings sub-issues, dependencies, assignees, and the link to pull requests without an extra server. You can look at them on GitHub. You do not need to.

## Which account acts

Pulse writes to GitHub as the account `gh` uses in your terminal. The map's header and your own row under WHO IS DOING WHAT, `pulse status`, the first line of `pulse go`, the context each agent session starts with, every confirmation on the map, and the output of `pulse approve` name it as `<name> (@<login>)`: the name from `git config user.name`, the login from GitHub. Pulse asks GitHub for the login at most once a minute and keeps it per gh config and token: another token in `GH_TOKEN` shows its account at once, and so does `gh auth switch`, which rewrites gh's hosts file; any other change shows within a minute. The hooks never ask GitHub; they name the login the last `pulse` command with the same token saw, else the name alone. The account is shown, and nothing is locked by it.

## What the team sees, and when

Your work reaches the team in three places. The board shows state the moment a `pulse` command writes it. The remote (`origin`) shows files and commits once they are pushed. Everything else stays in your clone.

| What | Where it lives | Others see it from |
|---|---|---|
| A BA in progress | board: a draft, held by your session in the phase `analysis`; the BA itself in your clone, on `docs/<n>-<slug>` | the draft: when `/pulse-ba` starts (`pulse new <type> "<title>" --draft --phase analysis`). The BA text: from its first commit, which the skill pushes; your approval then marks it `Validated` |
| A spec in progress | board: a draft in the phase `spec`; the spec in your clone, on the docs branch | the draft: when `/pulse-re` names the item (`pulse new <type> "<title>" --draft`). The spec text: from its first commit, which the skill pushes |
| A registered spec | origin: the spec on the pushed docs branch and in its docs PR; board: the record links its path and the docs PR, with the label `P0` to `P2` | `pulse new ... --spec <path>`, with `--issue <n>` for a draft, which ends the draft. It refuses a spec that breaks R2 to R6, pushes the docs branch, and opens its docs PR or uses the open one |
| Approval | board: the `pulse:approved` label | `pulse approve <n>`, or `a` on the map, which write the approval and nothing else; `pulse go` merges a spec not yet on the base branch through its docs PR first. Both refuse a spec neither on the base branch nor in an open pull request (R1), and for a feature, improvement, or fix one that breaks R2 to R6 |
| A claim | board: the assignee and a claim mark with the session, its phase, and the time of its last heartbeat | at once. `pulse go` reports each phase it starts, and every 10 minutes while one runs |
| The files an item holds | board: the claim carries the `files:` of the item's PLAN, pushed or not | at once: every ramp keeps other items off those files without a fetch |
| The work: PLAN and commits | your clone until pushed, then origin, on the item branch `<type>/<n>-<slug>` | the push. `pulse go` pushes after every agent phase that committed; in a session, planning pushes the PLAN and `/pulse-build` pushes after every commit |
| A note on hand-back | board: a comment on the item that says why the work stopped and which branch holds it | when `pulse go` gives the item back after a failure, a usage limit, or a stop |
| Pull request and verdicts | origin: the pull request, with the gate results and the review and audit reports in its text, and the verdicts as comments with one hidden marker per gate and commit; the verdicts `pulse go` puts on at once share one comment | the pull request |
| Logs, kept verdicts | your clone, under `.git/pulse/`: the board cache, the logs and report of `pulse go`, the kept review and audit verdicts | never; verdicts and reports reach the team on the pull request. The worktrees of one clone share all of it |

The [map](../guides/pulse-map) turns this into one line per item. A teammate's item without a pull request that a `pulse go` run holds shows the phase and the age of the run's last heartbeat (`building, 4 min ago`), and after 30 minutes without one, `no sign of life for 45 min`; one a session holds shows how long it is held (`no PR yet, held 2 h`). A draft shows `spec in progress by <login>`, and a free item given back with a note shows `last run:` and the first line of that note. [Parallel work](./parallel-work#what-others-see) says what to do about each.

## What that rules out

- **No status in documents.** A spec carries `issue:` and links to other documents, nothing about progress. `pulse check` flags `status`, `phase`, or `claim` in any `_devprocess` front matter.
- **No backlog file.** `pulse status` and the [map](../guides/pulse-map) render the board from the records.
- **No code paths in decisions.** A decision record explains a choice; the files that embody it go into its Sources appendix, which may go stale.
- **No re-documenting.** What code, tests, git, pull requests, or the records already carry is not written down again.

## What reading costs

The board saves reading where an agent needs to find its way, not where it does the work. Without it, the questions "what can I start, what waits for what, who has what" mean reading a backlog file that grows with every item, or opening several specs. With it, `pulse status` answers in a few lines from a local cache: a free check every two seconds asks GitHub whether anything moved, and only a change (or 30 seconds) reloads the cache in the shared git directory; `status` answers from it in milliseconds, for the board and for one item, and offline with the last known state. Every write goes straight to GitHub and drops the cache.

The work itself costs the same. An agent reads the spec and the PLAN of the item it builds, in full, because that is what it builds from. What it no longer reads is everyone else's. With ten items the difference is small; with a hundred items and five agents it adds up.
