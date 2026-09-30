# Changelog

All notable changes to Pulse are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] - 2026-09-30

### Changed

- The four-row terminal signet follows the SVG icons on a finer dot grid, with aqua and petrol gradients in truecolor and 256 colors.

## [0.2.1] - 2026-09-30

### Added

- Defer open work to the paused backlog as-is, explicitly resume it, or discard it without removing code. Existing PRs, approvals, notes and work remain preserved.
- Feature deletion through a confirmed, reviewed removal PR before irreversible issue/comment deletion; no history rewriting or implicit removal of dependent features.
- Shared manual map ordering with `m`, arrows and Enter; dependencies always precede the work they block.

### Changed

- Epic progress bars share a column below a blank separator. The picker reaches epics, and their details show the full title.
- The terminal P signet uses at most four rows beside the header text.

### Fixed

- The live map keeps the final character at the right edge of a split terminal.
- GitHub rate limits pause requests until the retry deadline and show the map's cached data as stale instead of calling the connection offline.

## [0.2.0] - 2026-09-30

### Upgrade notes

This release removes commands and changes who acts at each gate:
`pulse done`, `approve-plan`, `review`, `audit`, `rank`, `show`, `beat`,
`block`, `arch`, and `go --detach` and `--agent` are gone, `pulse approve`
only writes the approval and `pulse go` acts on it, and `pulse go` needs
`[spec_tests]` in `.pulse/config.toml` on the base branch. Once per
project, run `pulse setup --labels` and `pulse setup --anchors`, and in
Codex trust the hooks again. [Upgrading from 0.1.6](https://pssah4.github.io/pulse/guides/upgrading)
lists every step.

### Added

- `pulse go` pulls the auto lever of its own person (#125). With your
  switch of a gate on, your run writes the approval `pulse approve` would,
  naming itself (`gate 1 approved by pulse go as @you (auto plan on since
  10:12)`), and then plans, builds, or merges exactly as after yours: only
  for items you opened (or, at gates 2 and 3, whose claim it holds), from
  switches read on GitHub right before, never from someone else's switch,
  one past its time, or with two control issues. `pulse:hold`,
  `pulse:draft`, and `pulse:failed` stop every lever, `risk:` in the spec,
  the approved PLAN, or the PLAN at the head stops gates 2 and 3, and gate
  3 also waits for a person on a protected path, manifest, or lockfile (by
  old and new name), a pass carried from an earlier head, a head behind the
  base, or a rollup that has not passed. More manifests count: `setup.py`,
  `setup.cfg`, `Gemfile`, `composer.json`, `bun.lock`, `.npmrc`, and their
  lockfiles. An edited toggle turns its login's gate off. The report
  says `<gate> waits for a person: <reason>`, the pull request `Merge: auto
  (@you, until 18:00)` or `Merge: waits for a person`, and in Herdr a gate
  that waits for you sends one notification per run. `plan_approval` and
  `go_autostart` are named once as ignored.
- `pulse go` picks the agent per item and limits what it may reach
  (#119). An item whose wave-1 spec test matches a `[spec_tests]` pattern
  with `localhost = true` is built by no agent whose program is `codex`,
  so by Claude; with only Codex in `agent` it waits with `needs a Claude
  agent (localhost spec tests)`. Every `codex` start gets
  `-c sandbox_workspace_write.network_access=false`, and a template that
  opens its sandbox stops the run before its first claim; every `claude`
  start gets `--disallowedTools Bash(gh:*)`, and its allow list gains the
  runners of `[spec_tests]` that are no bare shell or interpreter. A
  Codex template must name the workspace sandbox and may name no profile
  or sandbox or network setting, also behind `env` or `npx`. No agent
  process gets a GitHub token or `gh` login. A usage limit in any agent
  phase parks the item with its claim and worktree: another agent that
  may build it runs the same phase at once, else the run waits for the
  reset time the agent named (at most 8 days), with `limit until <time>`
  on the claim; before the phase starts again the run checks that the
  item is still open, approved, and its own, and without a terminal a
  second limit gives the item back. A fix or review and audit session that crashes or times out runs
  once more. In a terminal, a run with no agent at work waits while an
  item waits at gate 2 or 3 (`go idle, waits for #n`), reads the board
  every 60 seconds with a full read at most every 5 minutes, and ends
  with `q`.
- Auto mode per person and gate (#124). `pulse auto <plan|build|merge> on
  [--for 8h|2d]` in your own terminal says what then happens without
  asking you, for which items, and as which login, and asks once; `off`
  asks nothing; `pulse auto` alone shows yours and everyone else's. The
  keys `1`, `2`, `3` in the map do the same after a short confirmation.
  Each switch is a comment in the issue "Pulse auto mode" (label
  `pulse:auto`, created and pinned by the first `on`); per login and gate
  the newest counts, its GitHub author set it, and a switch past its time
  is off. Two such issues turn every switch off. The map head, `pulse
  status` (`auto` in `--json`), and the SessionStart context show your
  switches and the others'. Only a person switches: agents meet
  `_person_only`, the lever guard, and a Codex rule. `pulse setup` switches
  nothing on; `--labels` creates `pulse:auto`.
- Gate 3 in `pulse go` (#118). `pulse approve <n>` on an item with a
  ready pull request writes only `merge ok at <head>` and names the
  protected paths it changes. The run that holds the build claim merges
  the base in, runs `setup` after a lockfile changed and the tests gate at
  the new head, and merges with `--match-head-commit` in the repository's
  merge method: only with a merge ok from someone who may push, its own
  evidence for that head, a ready and mergeable pull request, and a whole
  rollup that passed; while checks still run it waits and merges in a
  later round or run, never with `--auto` (GitHub keeps auto-merge after
  a push) or `--admin`, and it turns off an auto-merge an earlier
  version left on. It
  closes the issue and, with its last item, the epic, after its own merge
  and after an auto-merge or a merge on GitHub, on any base. A pull request
  keeps its claim until the merge, across runs (`go:<clone>:<pid>`), and an
  approved item given back with code on its branch goes straight into the
  gates.
- In Herdr the live map opens beside the chat by itself: a chat that
  starts, resumes, or forks runs `pulse map --ensure` apart, which splits
  its pane to the right, one map per tab and repository, labelled
  `pulse map <owner/name>`. `q` ends the map and takes its label off; after
  a restart of Herdr the next start runs the map in its old pane again.
  `pulse setup` names the lines for a Herdr key that opens it (#121).
- `a` on an item of the map, not only in its view, writes the approval
  it waits for after a confirmation that names the gate, what it lets
  happen, and the login (#121).
- The item view of the map names each approval with the GitHub account
  that gave it and when, and the spec (#121).
- The lever guard refuses every text and key an agent sends into the pane
  of a live map, which it finds by the map's processes wherever the pane
  moved or whichever repository it shows, keys System Events types while a
  map runs, and `pulse map` typed into another terminal; it now checks
  `herdr pane send-keys` like `send-text` (#121).
- The lever guard refuses `claude` whose `--settings` switch every hook
  or the Pulse plugin off, `opencode run`, and a shell write, `rm`, or
  `truncate` of `.pulse/config.toml` that leaves `mode` other than `on`
  (#112).
- A lever guard. Where Pulse is on, a synchronous PreToolUse hook checks
  every shell, Monitor, and MCP call of a Claude Code or Codex session
  and its subagents before it runs, and denies a person's lever:
  `pulse approve`, `approve-plan`, `go`, `done`, `auto on|off`,
  `claim --take`, `release --take`, `setup --remove`, and
  `setup --mode off` (also as quoted text),
  `gh pr merge`, `gh pr ready`,
  `gh pr review --approve`, `gh pr create` without `--draft`, edits of
  issues, labels, and the repository, `gh api` writes, `gh auth token`,
  a forced push or a push onto the base or default branch (a push that
  names no branch is judged where the chain pushes from), and a command
  that unsets an agent marker. It reads through `env`, full paths, the
  `-c` of a shell, a shell fed by stdin, chains, and `-R` anywhere,
  checks text sent into another terminal through Herdr, tmux, or
  `osascript` the same way, and starts no agent without the guard in a
  pane. Herdr stays open to agents otherwise. In Codex it works once
  the Pulse hooks are trusted (#106).
- The config key `spec_branch` names the docs branch with `{n}`, `{slug}`,
  and `{type}` (default `docs/{n}-{slug}`), for a project whose branch rule
  refuses `docs/` branches, say `{type}/{n}-{slug}-spec`. Pulse finds a
  draft's docs branch by that pattern and by the old `docs/<n>-`. A
  pattern without `{n}`, or one a build branch matches, is refused with a
  warning (#116).
- Every surface names the account that acts as `Name (@login)`: the
  map's header and your own WHO row, `pulse status`, the first line of
  `pulse go`, the context each session starts with, the map's
  confirmations, and the output of `pulse approve`, which also leaves a
  comment `gate 1 approved by ...` or `plan ok at ...: gate 2 approved
  by ...` on the item (#111, #115).
- `pulse status`, the map, and `pulse go` say
  `Codex hooks not trusted: run /hooks in Codex` when the agents
  include Codex and Codex has not trusted the Pulse hooks (#111).
- The label `pulse:hold`: `pulse go` neither plans nor builds an item
  that carries it, nor takes up its draft. `pulse setup --labels`
  creates it (#111).
- `setup` and `setup_timeout` in `.pulse/config.toml`: `pulse go` runs
  `setup` (`npm ci`, say) itself, outside every agent sandbox, in each
  worktree it makes and again after a lockfile in it changed; a setup
  that fails there fails the item with `pulse:failed` (#113).
- The base check: before `pulse go` starts anything on a new commit of
  the base branch, it checks that commit once. A status `pulse/base` on
  it counts; a tree whose tests gate passed here is green without a
  run; else the project's CI (never `pulse/*`) and `setup` and `verify`
  in a scratch worktree decide, and the result goes on the commit as
  `pulse/base` for every clone. While the CI runs, the last known state
  holds. On a red base only an item with the new label `pulse:base`
  starts, and the map head says `base red: <check>` (#113).
- A project hook that refuses a commit or push of `pulse go` pauses new
  starts until the base moves or the run starts again, fails no item,
  and shows `hook rejected: <hook> at #n`; `pulse go` never skips a
  hook (#113).
- The label `pulse:failed`: an item `pulse go` gave up on gets it, with
  a comment `pulse go: failed at <base>: <reason>`, and no run takes it
  again until `pulse approve <n>` takes the label off. A crash gets one
  more try in the run first. Run `pulse setup --labels` once to create
  the label (#114).
- `needs:` in a PLAN, and in `_devprocess/plans/<n>-needs.md` for work a
  build finds, becomes blocker edges: `pulse go` makes a new title a
  draft item with the item's parent (one per round), writes `#m` in its
  place, and makes no edge that would close a cycle. The planning prompt
  lists the open drafts that came from `needs:` (#114).
- `risk:` in the PLAN holds it for a person, as `risk:` in the spec does
  (#114).

### Changed

- `pulse go` takes plans and builds from one queue (#119): no item before
  an open blocker, then the best `P0` to `P2` label of the item and of
  everything it unblocks, then the number; the critical path is no longer
  a key. `cap` counts every running agent in every phase, across all
  agents; a number in `agent` caps one agent.
- Every item gets one fresh session for review and audit, also with
  `risk: [security]`, and one fix round for all its gates (was two
  sessions for security and two rounds). A gate still red after the
  round leaves the pull request a draft that names the open findings;
  after the round the tests and only the red gates run again, as before.
  A PLAN keeps its two fix rounds. `/pulse-build` hands the tasks of one
  wave to parallel subagents where it can start them, and runs the
  wave's check once (#126).
- The map fits from 44 columns (was 60); below 60 its header leaves out
  the signet. Outside Herdr and tmux, `pulse map --ensure` says to run
  `pulse map` in a second terminal. `pulse setup` writes the VS Code task
  "Pulse map" itself, outside Herdr, and leaves a `tasks.json` with
  comments untouched; `/pulse` no longer writes it (#121).
- `pulse approve <n>` and the map's `a` write only the approval the item
  waits for: at gate 1 the label `pulse:approved` and a comment (for a
  spec in a docs PR `gate 1 ok at <head> <spec path>`), at gate
  2 the line `Plan-ok: <plan blob> <spec blob>` in the issue and the
  comment `plan ok at <plan blob> <spec blob>`, the ids git gives the
  PLAN as origin has it and the spec on the base branch, and after
  `pulse:failed` a new try. `pulse go` acts on them: it merges an
  approved item's docs PR (only `_devprocess/`, R1 to R6 for every spec
  in it, then the status `pulse/tests` "docs only: R1-R6" and the whole
  check rollup passing at the head it checked, the merge bound to that
  head, which must be the one a person approved; a PR pushed to since
  waits as `docs PR changed since approval`), plans, and builds. It
  counts an approval only from someone who may push, and opens a pull
  request only while both approvals hold.
  Every PLAN waits for a person now; a PLAN or spec changed since its
  approval waits again (`plan changed since plan ok`), and an approved
  item whose spec is neither on the base branch nor in an open pull
  request stands as `spec not on <base>`. An old `Plan-ok` line of 12
  characters counts for the PLAN it names, through whoever added
  `pulse:plan-ok` (#115).
- The tests gate of `pulse go` runs each spec test with its own runner
  (#117). `[spec_tests]` in `.pulse/config.toml` maps file patterns to a
  runner (`run`, with `{files}`, and `localhost`); `pulse go` does not
  start without it and reads it from the base branch on origin only. P6
  of a PLAN asks for a pattern for every spec test file of wave 1. The
  RED check checks out the freeze commit in the item's own worktree and
  every runner must fail there; without a freeze commit the tests gate is
  red. The tests gate runs `verify`, each runner one at a time per
  machine under `~/.cache/pulse/spec-tests.lock` with `CI=1`, and
  `pulse check` on the branch's files. Each gate leaves the commit status
  `pulse/tests`, `pulse/review`, or `pulse/audit` on the head and an
  entry in `.git/pulse/gates/<sha>`, which replaces
  `.git/pulse/green/<tree>`. A review or audit is green only when its
  first line reads exactly `Verdict: pass` and no finding under it is
  `- [block]`, and an item gets two fix rounds for all its gates
  together. Tests that change a tracked file or move HEAD, a wave 1 test
  file of the PLAN that no freeze holds, and a change to a file a freeze
  created make the tests gate red; the review brief names runner and
  setup files changed after the freeze. Without `tomllib`, the config on
  the base refuses every line the built-in reader does not understand. On Python 3.9 the config reader
  understands tables with quoted keys, arrays, and inline tables.
- `pulse go` takes `setup`, `setup_timeout`, `verify`, and `[agents]`
  from `.pulse/config.toml` on the base branch as origin has it, never
  from the working tree (#113).
- The hold of `pulse go` compares the whole git config but `branch.*`,
  `info/attributes`, the hooks (in `.git/hooks` and where
  `core.hooksPath` points for the worktree), and the worktree's pointers
  to its git directory; an editor setting under `branch.*`, such as VS
  Code's merge base per branch, stops no build any more. A change every
  worktree runs with halts the whole run: no launch, no fetch, no push
  (#113).
- Review and audit of an item run in one fresh session of `pulse go`,
  which writes `REVIEW.md` and `AUDIT.md`, each with its own verdict; an
  item whose spec or PLAN has `risk: [security]` keeps two sessions.
  After a fix round the tests run again and only the gates that were not
  green, so a fix round repeats no green review or audit; a gate that
  spent its two fix rounds gets no third. The gate table of the pull
  request names the commit each gate saw, the risk counts as the spec on
  the base and the PLAN at the build's start say it, and a `REVIEW.md` or
  `AUDIT.md` an agent leaves is never committed. The map shows the shared
  session as `review and audit running` (#120).
- Every planner reads `_devprocess/SYSTEM-MAP.md` before a PLAN: the plan
  prompt of `pulse go` names it. Where it is missing, a planning session
  with a person, or `/pulse-realign`, creates it on a docs branch
  into the base, never on an item branch. `/pulse-build` updates an
  existing map as its last task when the item
  changes an entry point, data ownership, an invariant, or a quality
  goal, and the review blocks a diff that does so while the map stays
  silent. The system map template gains quality goals, constraints, and
  risks, cap 150 lines. arc42 is one template with all 12 sections, only
  on request, as `_devprocess/arc42.md`, which `pulse check` no longer
  caps (#120).
- Skills, rules, and the prompts of `pulse go` run the tests a step
  affects after each step, and `verify` once, before the gates; a task's
  check in a PLAN names the test files it affects (#120).
- `effort: L` and `needs:` no longer hold a PLAN. A build that changes
  only files under `_devprocess/` opens no pull request and fails as
  `nothing built` (#114).
- `pulse new --spec` refuses a spec that breaks one of R2 to R6 and names
  the findings (`issue:` aside, which it writes). On a docs branch (not
  the base, no build branch, nothing changed outside `_devprocess/`) it
  pushes the branch
  and opens its docs PR into the base branch, or uses the open one, so one
  pull request carries the specs of an RE run. The record's body says
  ``Spec: `<path>` (PR #x)``, and the record gets the label `P0`, `P1`, or
  `P2` from the spec's `priority:`. A project set up before creates these
  labels with `pulse setup --labels` (#116).
- `pulse new --spec --issue <n>` sets no parent the issue already has, so
  GitHub no longer refuses it with "duplicate sub-issue" (#116).
- The login Pulse shows is kept a minute and per gh config and token,
  so `gh auth switch` or another `GH_TOKEN` shows its account at once;
  it was kept a day for every token of the clone. The hooks read it
  from that cache only and never ask GitHub (#111).
- The session start hook runs on `fork` too (#111).
- `approve`, `approve-plan`, `go`, `done`, `claim --take`,
  `release --take`, `setup --remove`, and `setup --mode off` refuse
  to run in any
  agent session (`PULSE_HOLDER`, `CLAUDE_CODE_SESSION_ID`,
  `CLAUDE_CODE_CHILD_SESSION`, `CODEX_THREAD_ID`) and when stdin is not
  a terminal; before, only agents of `pulse go` were refused. Run them
  in your own terminal (#106).
- `pulse setup --codex-rules` writes `forbidden` instead of `prompt`
  for these levers and adds `gh pr merge`, `gh pr ready`, and
  `gh issue edit|close|reopen`: Codex refuses them in every mode. Run
  `pulse setup --codex-rules` again once Pulse in Codex is updated. The
  Claude Code rules on the installation page deny the same commands
  (#106).
- Skills and rules no longer let an agent pull a lever on your yes: they
  tell you which gate waits and the command for your own terminal.
  `/pulse-build` opens its pull request as a draft, and you mark it
  ready (#106).
- `pulse status <n>` shows one open item as `pulse show <n>` did: its
  stage in the map's words, spec, PLAN, claim, and blockers; `--json`
  works for the board and for one item (#108).
- `pulse release <n>` refuses while the item's branch has commits only
  this clone has, and names the branch, how many commits it has, and
  the push; no flag gives them up any more. `pulse release --take <n>`
  stays, a person's lever (#108).
- `pulse/dispatch.py` lives in `pulse/ready.py`: the ramp, the file locks,
  and the order sit beside the gates (#107).
- `pulse go` puts item worktrees and their gate directories under
  `.worktrees/` in the main checkout instead of beside the repository,
  so a container that mounts only the project folder sees them. Git
  ignores the folder through `.git/info/exclude`, `pulse check` skips
  it. A worktree an older Pulse made beside the repository is used
  where it lies; one a person made never is. In a `--separate-git-dir`
  clone or a submodule the folder lies in the work tree, never in the
  git directory. Clean worktrees of closed items go at both places,
  except the one `pulse go` runs in.
  vitest, jest, and ESLint need `.worktrees/` in their ignore list
  (#122).
- `pulse setup` writes the Pulse block once, into `AGENTS.md`, which
  Codex and Claude Code read. A `CLAUDE.md` gets the line
  `@AGENTS.md <!-- pulse -->` instead of a second block, so Claude Code
  reads the block with every setting of "Project instructions"; setup
  creates no `CLAUDE.md`. A `CLAUDE.md` and `AGENTS.md` that are one
  file, linked either way, carry the block once. `--remove` takes out
  the block and only the line Pulse set (#123).
- Existing projects run `pulse setup --anchors` once: it moves the block
  out of `CLAUDE.md` into `AGENTS.md` and sets the import line; commit
  the change (#123).

### Removed

- `pulse go --agent` (#119): `agent` in `.pulse/config.toml` names the
  agents of a run.
- `pulse done`, the closing of merged items in `pulse status`, and the
  draft takeup of `pulse go` (#118): `pulse status` only reads, `pulse go`
  closes what it merged, and a person closes a dropped item or a draft
  epic on GitHub.
- `pulse approve-plan`, the label `pulse:plan-ok`, `plan_approval` with
  `pulse setup --plan-approval`, the approval's own merge of a spec (its
  pull request, or its branch through a merge commit) with the correction
  branches, and the map's `p`, unapprove, and merge with the merge checks
  behind it: a ready pull request is merged on GitHub (#115).
- The integration check at the end of `pulse go`, with `integration` in
  its report and summary; the base check takes over its scratch
  worktree (#113).
- `pulse review`, `pulse audit`, and the `/pulse-review` skill. `pulse go`
  runs both gates itself; the review brief lives in
  `skills/pulse-build/references/review.md`, which `/pulse-build` hands to
  a subagent with the audit's. `/pulse-audit` by hand asks its scope and
  runs `audit_scan.py` directly. The repository review every two weeks
  stays in v0.1.6. The hotfix lane of `/pulse-build` goes too: a bug
  without a PLAN gets one first (#120).
- `DISCOVERED.md`, `.git/pulse/go/discovered.md`, and the `discovered`
  field of the report, and the reference `mid-course.md` of
  `/pulse-build`: a builder writes work that comes first into
  `_devprocess/plans/<n>-needs.md`, and the build skill routes the rest
  (#114).
- The architecture map: `pulse arch`, its page, its rebuild in the live
  map and in `pulse go`, check rule C11, the architecture map template,
  and `layer:` in specs and decision records. Nothing replaces it; the
  system map stays for navigation (#109).
- The team order by hand: `pulse rank`, the `Rank:` line in an issue
  body, and the map's `m` key and prioritize entry. The ramp orders by
  the critical path, then the item number, as it did for every item
  without a rank; a `Rank:` line an older Pulse wrote is ignored (#109).
- The demo page, the demo GIF, and the map flags `--once`, `--demo`,
  `--color`, and `--no-color`. `pulse status` prints one frame, and so
  does `pulse map` in a pipe, without color; the README shows an excerpt
  of the map (#109).
- The adapters for Cursor, OpenCode, and Gemini, with their manifests.
  Pulse ships two packages, Claude Code and Codex. `pulse setup` writes
  its block into `CLAUDE.md`, `AGENTS.md`, and the Copilot instructions
  only; `pulse setup --remove` still takes an older Pulse block out of
  `GEMINI.md`, `.cursorrules`, and `.windsurfrules`, and `pulse migrate`
  still replaces a DIA block there (#109).
- The git pre-commit hook and `pulse setup --git-hook`. Branch
  protection, where set, keeps the base branch; put `pulse check` into
  `verify` to run it in the tests gate. `pulse setup --remove` still removes a hook an older
  Pulse installed and puts back the one it kept as `pre-commit.bak`
  (#109).
- Check rule C8. The plan gate checks the waves of a PLAN as P4 (#109).
- The config key `review_agent`. The review and the audit run with the
  agent that built the item; an older config that names the key loads
  without an error (#109).
- `pulse go --detach`, `--cap`, `--json`, and `--dry-run`. `pulse go` runs
  only in the foreground of the terminal a person starts it in, names
  `cap` and the agents in its first line, and stops on Ctrl-C; `cap`
  comes from `.pulse/config.toml`, and `pulse status` shows what the next
  run takes (#107).
- The start of `pulse go` from the live map: the autostart, the `g` key,
  and the `pulse go` line in NEXT, with `go_autostart` and `PULSE_GO`.
  `pulse map --ensure` opens no Terminal, iTerm, or Linux window any
  more; in tmux it opens a pane, elsewhere it names the command (#107).
- Stacking: a dependent no longer builds on its blocker's branch once the
  blocker's pull request is ready, and no run moves a stacked pull
  request to the base branch. A dependent waits for its blocker's merge;
  `pulse go` takes up only drafts whose pull request targets the base
  branch and names the others once under skipped (#107).
- The session notes beside a session's stamp (`.held`, `.lost`) and the
  look for runs of the same login in other clones (`elsewhere` in the
  report). The note `pulse go` leaves on an item it gives back stays
  (#107).
- `pulse/presence.py` and its async hooks on UserPromptSubmit,
  PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure,
  Notification, SubagentStop, and SessionEnd. The hooks run at
  SessionStart, SubagentStart, and Stop, and only the synchronous lever
  guard runs before each shell, Monitor, or MCP call. With them go the
  hook's heartbeat and lost-item news, the notes on a stale Pulse block
  and a newer release at a session start, and the review reminder at
  Stop. The live map shows claims, no chats and no session lights; only the claim
  of a `pulse go` run shows a sign of life, a session's claim how long
  it is held (#107).
- The config keys `parallel`, `map_autostart`, and `go_autostart`, and
  `pulse setup --parallel`. `cap` alone limits how many agents run at
  once; `PULSE_MAP=off` switches the map off; an older config that names
  the keys loads without an error. The Pulse block in `CLAUDE.md` and
  `AGENTS.md` changed with it: run `pulse setup --anchors` in an existing
  project, since an older block still names `parallel` (#107).
- `pulse show`: `pulse status <n>` shows the item (#108).
- `pulse beat`: `pulse go` writes its own signs of life (#108).
- `pulse block`: a blocker comes with `pulse new --blocked-by`, or you
  add it in GitHub (#108).
- The flags `claim --files` (a claim carries the files of the item's
  PLAN), `release --note` (the note on a hand-back comes from
  `pulse go`), `release --drop-unpushed` (push first), `approve --undo`
  (`unapprove` in the map's item view, or remove the `pulse:approved`
  label in GitHub), and `approve --claim` (the `/pulse-re` session plans
  an item once you approved it). The guard and the Codex rules no longer
  name `release --drop-unpushed`; rules an older
  `pulse setup --codex-rules` wrote still forbid it, which does no harm
  (#108).
- The skills `/pulse-go`, `/pulse-map`, and `/pulse-setup`, in Claude
  Code and in Codex. `/pulse` says in one paragraph each how you set
  Pulse up, start `pulse go` in your own terminal, and work the live
  map, and names every lever as your step: press `a` in the Pulse map,
  or run `pulse approve <n>` in your own terminal. The commands
  `pulse setup`, `pulse go`, and `pulse map` stay, and so do their
  pages (#110).

### Fixed

- Handover notes and takeover comments from members or collaborators
  require confirmed push permission; read access alone no longer counts
  (#89). Agent instructions use full remote refs that tags cannot shadow
  (#91). `pulse go` refuses item branches with a foreign upstream before
  setup and shows branch names without control characters in its
  summaries and planning or fix prompts (#96).
- A confirmation in the live map stays open only while the terminal
  shows all of it: made smaller, the map closes it and says to make the
  terminal larger, and an `Enter` typed as the terminal changed confirms
  nothing. A resize that still shows it draws it anew, and its second
  starts again. A whole frame writes every row at its own place, so a
  row the terminal draws wider than the map counts moves no row below it
  (#98).
- Branch names that differ only in case no longer let Pulse work on the
  wrong commit (#97). On macOS and Windows one ref file holds both, loose
  or packed; `pulse go`, `pulse claim`, `pulse new`, `pulse number`, and
  the hint on where another holder's work is now name the two branches
  and neither build, start, register, nor point at either of them.
- `pulse check` no longer hangs on a spec, a PLAN, or another Markdown
  file under `_devprocess/` that is a symlink or a FIFO: it names the
  file (C1) and never reads it. A link or path with a part over 255
  bytes, or a `parent:` through a symlink loop, is a finding with its
  file instead of a traceback (#93).

### Security

- A sandboxed Codex agent of `pulse go` can no longer forge a verdict or a gate's
  evidence (#95). A Codex agent may write the shared git directory, so a
  review or audit verdict, `gates/<sha>`, or the base check's note it left
  under `.git/pulse/` counted as if `pulse go` had written it: a pass
  marker on the pull request, a merge at gate 3 or by the auto merge, a
  base green without a run. `pulse go` now keeps all of these in
  `~/.cache/pulse/<clone>/` (`$XDG_CACHE_HOME` when set), outside the
  standard Codex sandbox, and reads nothing of them from the git directory.
  A custom cache must stay outside every sandbox write path.
  Evidence from an earlier version no longer counts: the base check runs
  once more, and `pulse go` merges no pull request whose gates ran
  before; a person merges it. The Claude Code template still runs without a
  sandbox, and its agent can write any file you can.

## [0.1.6] - 2026-09-28

### Added

- The live map starts `pulse go` on a key: while approved work waits
  and no run of the clone lives, NEXT says `g start pulse go: #5, #7`,
  also where the map does not start a run by itself. `g`, or `Enter` on
  that line, shows the items, the agent, the test command, and why the
  map did not start the run; `Enter` starts it apart from the map.
  Without a test command the line names the command that sets it (#76).

### Changed

- Planning is a step of `/pulse-re` too. When you approve a feature,
  improvement, or fix in the RE session, the skill runs `pulse approve`
  (which brings the spec onto the base branch, see #88 below), plans the
  item right away without asking, and
  goes on into the build unless something holds the PLAN; an epic gets
  no PLAN. The guides of `/pulse`, `/pulse-re`, and planning, the
  V-Model page, the artifacts and commands references, the operating
  model, and the full V-Model tutorial say so, and the planning skill
  names effort L among the holds of a PLAN. Tests hold every hand-over
  between the stops and look through the skills and the rules for a
  question whether to go on, in the forms the skills used to ask it
  (#26).

- One name for the place where item state lives: the board. The README,
  the docs, the command reference (with the help of `pulse new` and
  `pulse migrate --issues`), and the skills and their references no
  longer put item state "on GitHub" or content into an issue: a bug's
  substance goes into its fix spec, its record holds only state. Where
  it helps, a page says that each record is technically a GitHub issue
  (#11).

- Work reaches origin as it happens. A session that holds an item and
  ends with commits on its branch, or its docs branch, that origin
  lacks is stopped once and told the push. `pulse release` keeps such
  an item unless `--drop-unpushed` gives it back without them. The
  rules and skills push after every commit; `/pulse-ba` and `/pulse-re`
  push their docs branch from the first commit on, so the BA shows
  while it is written and its approval decides whether it counts (#79).

- Pulse syncs with origin before it hands anything out. `pulse claim`
  fetches and names the start point: the item's branch on origin, else
  the base branch as origin has it now, never the local one.
  `pulse number --apply` and `pulse new --spec` fetch first and refuse when
  origin does not answer, so an ID another clone pushed is not handed
  out again and no record links a spec nobody saw on origin. Rules and skills start every branch from
  there (#78).

- A spec needs no pull request any more. When the spec of an item is
  not on the base branch and in no open spec pull request, but on
  exactly one branch of origin, `pulse approve` and approve spec in the
  map merge that branch into the base branch themselves, push the
  merge, and then approve. The checks of a spec pull request hold: the
  merge changes only plain files under `_devprocess/`, the spec at the
  branch's head passes R1 to R6 (an epic R1), and the map merges only the head its
  confirmation showed. The confirmation, and `pulse approve` afterwards,
  name every path the merge changes, with A, M, or D, and the map offers
  the merge only where `pulse approve` makes it; elsewhere it says why
  not yet. `Enter` merges nothing its confirmation did not show. The merge commit, `Merge spec of #<n>`, is made without a
  checkout under your git identity and pushed without force. Several
  branches that carry the spec, a branch that does not merge cleanly, or
  a push origin refuses merge nothing and say what to do; on a protected
  base branch, a spec pull request stays the way. `/pulse-re` and
  `/pulse-build` push a spec and open no pull request for it, and the
  rules, skills, and docs say so (#88).

- Rules, skills, templates, docs, and diagrams tell the same flow. A
  spec approved in the `/pulse-re` session is planned there at once and
  built without a stop, any other in ramp order; planning runs in `/pulse-re`,
  `/pulse-build`, and `pulse go`, and `pulse go` opens the pull request
  for a person's merge. A person's holds are stops, the gates stay tests,
  review, and audit; the place of item state is the board everywhere.
  The RE guide no longer promises a Benefits Hypothesis, an ASR level
  Low, or an architecture gate. `/pulse-build` says what a session does
  that lost its item, and every list of a person's levers names
  `release --drop-unpushed`. The map pages name the lights, keys, holds,
  and reasons as the map shows them, and say that the hold after a
  failed or stopped run holds only in its clone (#100).

### Fixed

- Of two claims on one item in the same seconds, the older one wins: a
  claim that finds a fresh mark of someone not yet assigned before its
  own waits a moment and reads again. Should both still win, a
  `pulse go` run checks its claim before each push; one that lost the item pushes nothing, opens no
  pull request, takes its claim back, and names who holds it. An
  interactive session hears it at its next sign of life, and
  `pulse beat` exits with 1 (#77).

- The review and the audit of `pulse go` start in a gate directory
  beside the worktree, with a fresh checkout of the pushed commit, and
  write their report next to that checkout, at the path the prompt
  names. They run git on that checkout as `git -C tree diff`, `log`,
  `show`, or `status`, the four forms their allow list adds, and the
  prompt names the diff, the spec, the PLAN, and the decision records
  from where the session starts. Nothing the builder left uncommitted or
  ignored reaches them, and a tracked `review.md` or `audit.md` stays
  as it is. The brief of both names changed agent instructions
  (`CLAUDE.md`, `AGENTS.md`, `.claude/`, `.codex/`, `.agents/`,
  `.mcp.json`), a report counts only after the brief of this run, a
  link or FIFO is no report, and `pulse review --run` and
  `pulse audit --run` end the process group of their session (#36).

- Codex asks before `pulse release --drop-unpushed`, as before
  `release --take`: `pulse` takes `--drop-unpushed` only right after
  `release` (`pulse release --drop-unpushed <n>`), where a Codex rule
  sees it, and exits with 2 anywhere else; `--take` and
  `--drop-unpushed` never go together, and an agent of `pulse go` may
  not drop commits. The rules change: update Pulse in Codex, then run
  `pulse setup --codex-rules` again. The Claude Code rules in the
  installation tutorial ask there too; add
  `"Bash(pulse release *--drop-unpushed*)"` to the `ask` list of
  settings you copied from it before (#87).

- `pulse go` no longer builds on a spec branch named like the item's
  branch (`feat/563-chat-activity-spec`): a branch of the item that
  changes nothing but specs against the base branch, or nothing any
  more, is none to build on; the build starts on a new branch (#73).

- The map (`pulse map`, `pulse status`) and `pulse show` no longer pass
  escape sequences from titles, notes, errors, the presence log, the
  last run's report, or a plan's goal to the terminal: every character
  that is not printable shows as `?`, and a line of the map shows the
  first line of a text. Only the map writes colors and links, and a
  warning about a config line Pulse skips shows the line the same way.
  A confirmation (approve spec, approve plan, unapprove, merge, `g`)
  opens only where the terminal can show all it confirms, counting each
  character that is not ASCII as two columns; else the map asks for a
  larger terminal. While it is open, the map writes it again on every
  frame, so no line of the map can cover it. A goal in a confirmation
  takes one row, and `pulse show` keeps the lines of a note. A title
  with `›` no longer moves the view away from the picked row, the item
  view runs the row it shows, read spec says why it opens nothing on a
  path the system refuses, and wide characters (CJK) and spacing marks
  count by the columns a terminal draws them in, so a line that holds
  them keeps its width, and messages at the bottom wrap instead of
  losing their end (#56).

- An `Enter` within a second of `g` in the live map, or of the `Enter`
  on the `pulse go` line in NEXT that opened the confirmation, no
  longer starts `pulse go`: typed for another window, or the second of
  a double `Enter`, it closes the confirmation, and the footer says
  why. An `Enter` from a second on starts the run as before (#86).

- `pulse check` reads links (C1), code names in a decision record (C3),
  the Activation Path of a feature spec (C6), and the lines it counts
  toward a cap (C5, past comments that never close) in linear time. A
  prepared file of 40,000 characters cost 1 to 8 seconds on every
  commit, now it costs milliseconds, with the same findings. A link
  whose target itself holds `[` is no longer checked as a whole; a link
  inside it is. Findings print without control characters (#41).

- `pulse claim` and `pulse release` no longer name a spec branch as
  where the work is: the hint names only a branch on origin that
  `pulse go` would build on, fetched just now and quoted as a shell
  reads it, and none when origin has only the spec branch (#83).

- `pulse number --apply`, `pulse new --spec`, and `pulse claim` hold
  the refs git lists after every fetch against the commits origin
  names: a lock file left behind no longer reads as "origin did not
  answer", and a fetch that exits without an error but leaves a listed
  ref on another commit (on macOS, two branch names on origin that
  differ only in case) no longer counts as fetched. They print git's
  error, or the refs that differ. `pulse new` and `pulse number`
  refuse, and `pulse claim` names no start point, only when something
  they need is not as origin has it: `pulse new` its own branch, also
  one origin deleted; `pulse number` the history of a branch on origin,
  so a fetch cut short hands out no ID; `pulse claim` the base branch or
  a branch of the item. `pulse number` counts a branch whose ref git
  could not update through the commit origin names, and hands out no ID
  while git cannot read the history. `pulse status`, `pulse show`, and
  `pulse approve-plan` name what git said as well, and say that origin
  did not answer only when git said nothing. Still open for a follow-up:
  a twin such as `MAIN` that arrives beside an `origin/main` in
  `packed-refs`, which `pulse claim` does not see, and `pulse go` and
  the hint on where another holder's work is, which do not check the
  refs yet (#85).

- A pull request from a fork counts for an item only through its
  `Closes #n`, which GitHub links only in a pull request into the
  default branch. Merged from a branch named `feat/12-typo`, it no
  longer closes #12 at the next `pulse status` or `pulse go`, drops the
  claim of whoever builds it, or takes it off the map; merged into
  another base branch, it closes nothing, and `pulse done 12` closes
  the item. Nothing is built on a fork's branch: no feature stacks on
  it, `pulse go` takes up no fork's draft and leaves it out of the
  integration check, and no verdict goes onto it. A stack base comes
  from origin only, never from a local branch, tag, or commit of the
  same name. The integration check fetches each branch on its own and
  names one origin lacks instead of calling it a conflict. Branch names
  reach the start line of `pulse claim`, the build prompt, the branch
  lines of the run summary, and handover notes with control characters
  shown as `?` (#63).

- A session whose item a person took with `pulse release --take`
  hears it at its next sign of life, the heartbeat or `pulse beat`
  (which exits with 1), with who has the item now, also when it
  claimed the item, or registered it as a draft, and has waited
  since. It stops the work on the item and pushes nothing more of
  it, and the stop hook asks for no push of it. A session that gave
  its item back or never held it hears nothing, and a hand-over
  between two sessions of one person stays silent (#84).

- A review or audit verdict on a pull request counts only from someone
  who may push: the repository's owner, or a member or collaborator
  whose permission GitHub names write or admin, Enterprise Managed
  Users included. GitHub calls people with read access members and
  collaborators too, so a reader's marker could end the Stop hook's
  question for the gates, merge a pull request from the map or keep it
  from merging, and keep `pulse review --publish` from putting the real
  verdict on the pull request. When GitHub gives no answer (its rate
  limit, or the 403 for a login that cannot push), such a verdict
  counts for nothing, and while it is the newest of its gate, no older
  verdict counts in its place: the Stop hook names GitHub's reason and
  sends you to `gh auth status` and `gh auth switch` first, and the
  map merges nothing and shows the reason. A marker counts
  only on a line of its own, outside quotes and code blocks, and only
  in a comment of the owner, a member, or a collaborator, read in
  linear time; the Stop hook asks about each author once, and
  `--publish` never posts a verdict of your own login twice (#74).

- Handover, approval, and the map say and do the same (#99, with #90).
  After a take, the old session's stop hook asks for no push and no
  review or audit, since it reads who holds the item from the board at
  every stop; `pulse beat` reports a loss once and clears its notes,
  and names `pulse release <n>` after a lost race; `pulse release <n>`
  after a take says there is nothing to give back; a new session on
  another login's item hears who holds it; a draft names its docs
  branch as where the work is and where the next holder starts.
  `pulse approve` takes a later correction of a spec on the base branch
  along when one branch of origin changed it, and
  `pulse approve --claim` claims a feature, improvement, or fix for
  planning before it approves it, blockers aside, so no live map starts
  a run for the item the `/pulse-re` session plans. On the map every
  confirmation takes no `Enter` within a second of opening it and says
  `enter came within a second of opening it` (#90), and the item view
  opens on a reading entry. `merge` is offered only where it goes
  through: never for a fork's pull request, nor for one whose last
  commit lacks passing review and audit, where the line and NEXT name
  the missing runs; its confirmation says when `Enter` makes the pull
  request a draft again. What `pulse approve` cannot move is grey and
  counts nowhere, a row that waits for a slot says `queued`, read spec
  is offered only where the spec is, and an epic's approval says that
  its features are approved one by one. `pulse status` names
  `pulse go --detach` where the live map has `g`, `pulse show` prints
  the stage in the map's words, a teammate's waiting plan names whose
  it is, and the help names `j k`, Ctrl-C, and `?` as the one key with
  Shift. The help of `pulse beat`, `pulse claim`, `pulse go`, and
  `pulse check --spec`, and the preview of `pulse migrate` say what they
  do; the fake `gh` of the E2E scripts takes `pr ready --undo`.

## [0.1.5] - 2026-09-27

### Added

- The item view of the live map merges an item's finished pull request:
  merge is offered once the pull request is ready and targets the base
  branch, shows what it merges, and merges with Enter. The map reads the
  pull request again first and merges only one of this repository at
  the head the confirmation showed, without failing checks, whose gates
  passed on that head and none blocked it. A pull request with commits
  after the gates of pulse go is set back to draft, so the next pulse go
  runs its gates again. The action read PR opens the pull request in the
  browser, and NEXT sends a waiting merge to the item view instead of
  GitHub (#70).

### Changed

- The git hook refuses commits on the base branch too, the one
  `base_branch` in `.pulse/config.toml` names (without one, origin's
  default branch), beside `main`, `master`, `develop`, `dev`, or the
  list in `pulse.protected-branches`. A clone gets it with the next
  `pulse setup --git-hook` (#75).
- Approving a spec merges its spec pull request: `pulse approve <n>`
  and approve spec in the live map merge the one open pull request that
  carries the item's spec into the base branch, then approve the item.
  Nobody merges a spec pull request on GitHub any more. Pulse reads the
  pull request again first and merges only one of this repository
  whose merge into the freshly fetched base branch changes nothing but
  plain files under `_devprocess/`, and only the head whose spec passed
  R1 to R6 and that the map showed; a draft becomes ready first, and the
  item is approved once the spec is on the base branch. The confirmation
  in the map names the pull request and the other specs it brings along,
  which stay unapproved (#69).

### Fixed

- An open pull request that changes only files under `_devprocess/`,
  such as a spec, no longer counts as the pull request of the item its
  branch name names: the map shows no "waits for merge" for it, and
  `pulse go` stacks nothing on it (#62).
- The item view of the live map reads a spec that lies only on a branch
  of origin, such as one in an open spec pull request: its goal shows,
  and read spec opens a copy to read and names the branch. A spec in
  the working tree that differs from the base branch opens as the base
  branch has it. A spec path that leads out of the repository, or one
  that is no Markdown file, opens nothing (#68).

## [0.1.4] - 2026-09-26

### Added

- `pulse arch` builds an architecture map: every feature and decision
  record in its layer, and a page per feature, decision, and epic.
  `pulse arch --open` opens it. Pulse rebuilds it from the base branch
  after every merge while a live map or `pulse go` runs; it lives in
  `.git/pulse/` and is never committed. The layers come from
  `_devprocess/architecture-map.md`, each spec names its place with
  `layer:`, and `pulse check` (C11) reports a place the layers lack.
  Without layers the map groups the features by epic.

### Changed

- `--take` goes right after the command: `pulse claim --take <n>`,
  `pulse release --take <n>`, `pulse done --take <n>`. Anywhere else it
  exits 2 and names this spelling.

### Fixed

- Codex in Full access claims and gives items back again. The Codex
  rules ask only before `claim --take` and `release --take`, next to
  `approve`, `approve-plan`, `rank`, `done`, and `pulse -- <command>`.
  Update Pulse in Codex too, then run `pulse setup --codex-rules` again
  to rewrite them; it writes no rules while Codex runs an older Pulse.
  Where Codex refuses a command in Full access, the agent names it for
  your own terminal.
- An agent of `pulse go` claims, gives back, and blocks only the item it
  was started for (`PULSE_ITEM`); before, it could give back any item its
  run held.
- A claim or note mark counts only at the start of a comment, where
  Pulse writes it: a note or comment that carries one in its text no
  longer holds an item or its files.
- The header of the live map stays on top in a terminal lower than the
  map, wherever the cursor is, and the help stands under it too.
- An item whose pull request merged leaves the map at once, also when it
  merged into a branch other than the default one, and its epic counts it
  done; `pulse status` still closes it.
- The live map names each chat that waits for you. Under an item where
  several chats stand it counts the ones that ask and says what a working
  agent does there, and NEXT gives each asking chat a line of its own with
  agent, title, and how long it waits, the longest first. `Enter` on that
  line, or a click on it or on `need you`, opens the chat in VS Code; a
  chat in a terminal, the Codex app, Cursor, or VS Code Insiders says
  where it runs.
- A merged pull request that changes only files under `_devprocess/`,
  such as a spec, no longer counts as the build of the item its branch is
  named after: `pulse status` and `pulse go` leave that item open and the
  map keeps it. An item whose whole work lies under `_devprocess/` closes
  with `pulse done <n>`.

## [0.1.3] - 2026-09-25

### Changed

- A live map restarts itself with a newer Pulse within a minute of an
  update, in its own terminal. Once a day it asks for the newest release
  and names a newer one in its footer with the update commands for
  Claude Code and Codex; the next session names it too.
- A session in a project whose Pulse block is out of date has its agent
  run `pulse setup --anchors`, which rewrites only the block.
- The live map reads the board beside its keys, so a key never waits for
  GitHub. A write names itself in the footer while it runs, and the map
  then shows the board as the write left it.
- A draft someone writes stands only under its holder and counts as in
  progress; the ramp keeps the drafts nobody holds.
- The item view offers only what the item's stage allows, each with what
  it does: approve or unapprove, approve plan, read plan, prioritize (top
  of the ramp), and read spec. `q`, `Esc`, `←`, and Backspace go back on
  every level below the map, `→` opens an item, and `Esc` on the map says
  that `q` quits. Unapprove asks for `Enter` as the approvals do, and keys
  typed while a write runs are dropped. The map writes "plan" in lower case.
- A plan on a pushed item branch counts only as a Markdown file in the
  plans folder itself, as in the working tree.
- The installation page walks through an update step by step, for Claude
  Code and for Codex: getting the new version, loading it
  (`/reload-plugins` or a new chat), trusting the Codex hooks again when
  Codex asks, and what happens by itself. Claude Code users turn on
  auto-update for `pssah4-skills` once.
- The install script sets up the `pulse` command with the newest copy of
  both tools and names only the steps that are still open: the Codex
  hook trust only while Codex has none, auto-update once for Claude Code.

### Fixed

- The map shows an agent under the item its session holds, also when the
  session's directory has another item's branch checked out, and a Codex
  agent on the branch where its last command ran. Codex tells the hooks
  only its session's directory, so its work in another worktree showed
  under the wrong item.

## [0.1.2] - 2026-09-25

### Changed

- An item's plan is its PLAN file `_devprocess/plans/{n}-{slug}.md`. The
  anchor block `pulse setup` writes into the agent files says so, and so
  do the rules: a plan mode only shows the PLAN for approval, and a plan
  outside the repository does not count. The PLAN template gains the
  sections Not touched and Verification.
- A new session names each agent file whose Pulse block is out of date,
  and `/pulse-setup` writes it anew.
- `/pulse-realign` gives every epic and feature spec a record and, after
  one question, closes the records of code that exists in one `pulse
  done` call: the board holds only open work, and each epic counts its
  features as done. `pulse done` takes several numbers, and `pulse new
  --spec` creates nothing for a spec that has its record, so a stopped
  run goes on without duplicates.
- `/pulse-realign` delivers a basis to rebuild the product from: A1
  counts the entry points per kind, every observed behavior becomes a
  requirement with its source and its test, a success criterion carries
  the observed target, and the verification gate also checks code to
  spec and runs a rebuild reading with fresh subagents. The handoff
  reports in numbers and says "rebuildable" only when no inventory entry
  and no place of the rebuild reading stays open.
- On the map, `m` moves the picked ramp row and the map stays; its
  footer names the key. With color, each `#n` links to its issue in a
  terminal that knows links (VS Code, iTerm).

### Fixed

- The `pulse` command runs the Pulse of the agent that calls it: a Codex
  session its Codex copy, a Claude Code session its Claude Code copy, and
  a terminal of its own the newest of both. An older Pulse in Claude Code
  no longer stands in for a newer one in Codex, so each works without the
  other.

### Upgrading

- Run `pulse setup --cli` once more: it rewrites `~/.local/bin/pulse`.
- Run `/pulse-setup` once in each project: the anchor block now says that
  an item's plan is its PLAN file.

## [0.1.1] - 2026-09-25

### Added

- Logical IDs for specs. A spec's file name starts with its type, the
  numbers of its parent, and its own counter: `EPIC-04`, `FEAT-04-02`,
  `FIX-04-02-01`, `IMP-04-02-01`. A folder listing groups the features of
  an epic, and every ID names its epic and feature. The issue number
  stays the ID of the record.
- `pulse number` shows every spec whose file name lacks the ID of its
  place in the tree; `--apply` renames them, rewrites every path to them,
  puts the IDs into the epics' `## Items` lines, and moves the records
  along (an open record once the base branch has the new path). A new ID
  never repeats one that any branch, the history, or a worktree has used.
- `pulse check` rule C10 reports a spec without the ID of its place.
- `ids_since` in `.pulse/config.toml` lets a project number its specs
  anew from a commit, for example version 2 on the history of version 1.
- The installation page starts with one numbered sequence, from the
  prerequisites to `/pulse-setup` in a project, for Claude Code and
  Codex in the terminal and the VS Code extension; the README's quick
  start follows it.
- An optional install script:
  `curl -fsSL https://pssah4.github.io/pulse/install.py | python3 -`
  installs or updates Pulse with every tool it finds, also the binaries
  the VS Code extensions bring, writes the `pulse` command, asks before
  it changes your shell profile or writes the Codex rules, and removes
  nothing. `--dry-run` shows what it would run.
- The live map starts `pulse go` apart from itself when approved work
  waits and no run of this clone lives, so an approval, yours or a
  teammate's, starts the build without anyone typing `pulse go`. It
  starts only with the `.pulse/config.toml` that origin holds, never with
  the one of a checked-out branch, and what the last run did not finish
  waits for a person. `go_autostart = false` in `.pulse/config.toml` or
  `PULSE_GO=off` turns it off.

### Changed

- The new logo: the wordmark in the navigation of the documentation
  site and at the top of the README, the app icon as the favicon, petrol
  as the brand color, and a petrol-tinted dark mode. The landing page
  says what Pulse adds to GitHub, and its two diagrams follow the theme.
- The map shows the Pulse signet beside its header: in 256 colors as
  drawn, cyan in a terminal with 16 colors, plain without color.
- The installation page has one Update section: the commands for every
  tool, the install script, what to restart, and where a release names
  a step for your projects.
- The operating model and the review skill: a reviewer agent in a fresh
  session checks every pull request against its spec, PLAN, and
  decisions, and the person reads it at feature level and merges.
- `pulse new` puts the spec's ID in front of the record's title and its
  `## Items` line. An `## Items` line may stand without an issue number,
  for a shipped feature that has no record.
- `/pulse-realign` names the epic of every feature, shipped or not, and
  lists all features in their epic's `## Items`.
- A `pulse go` run reads `.pulse/config.toml` once, at its start: a
  branch checked out while it runs changes neither its `verify` nor its
  base branch.
- `/pulse-realign` and a Project-BA start with a draft on the board, as an
  Item-BA and `/pulse-re` do: the team and every map see the work from its
  first step, a heartbeat keeps it alive, and the draft closes once the
  work lives in its own records or the pushed BA.
- `pulse new --draft` refuses a title that an open draft of the same type
  has already and names that draft and who holds it, so two people
  cannot start the same realign or Project-BA.
- A Codex session whose Pulse hooks never ran hears so the first time it
  claims work: `/hooks` in the CLI, or the Hooks page of the IDE
  extension's settings, trusts them, and a new chat picks them up.
  `/pulse-setup` reports whether they are trusted.

### Fixed

- `pulse claim` refuses an item whose files another running item holds,
  as the ramp does, and names the file and the holder: a build started
  by hand with an item number no longer works on the same file as
  another item.

### Upgrading

- Run `pulse number --apply` once and commit the result; until then
  `pulse check` reports C10 for every spec. After the merge, run it once
  more so the open records link the new paths.

## [0.1.0] - 2026-09-25

The first public release. Pulse replaces the Digital Innovation Agents
plugin (DIA), whose last release was 4.0.2: the method stays, the
mechanics are rebuilt. The history of DIA stays with DIA.

### Added

- Pulse in three parts: an operating model for teams where each person
  works with several agents, collaboration on one shared board, and the
  Digital Innovation Agents as the method from a raw idea to reviewed code.
- Installation from the GitHub repository `pssah4/pulse` with each
  agent's own plugin commands, no npm package: Claude Code (terminal and
  VS Code extension) and the Codex CLI install the plugin with its hooks
  from the marketplace `pssah4-skills` (Codex asks once to trust the
  hooks in `/hooks`). The Codex IDE extension uses the plugin the Codex
  CLI installed; OpenAI does not promise this, so a test guards it and a
  clone without hooks stays the fallback. The same commands update and
  remove it. GitHub Copilot, Cursor,
  Gemini CLI, and OpenCode load the same skills and rules, untested end
  to end.
- `pulse setup --cli` puts a `pulse` command into `~/.local/bin` that runs
  the newest installed Pulse, so a plugin update needs no new setup.
  `pulse setup --codex-rules` lets Codex run `pulse` outside its sandbox
  and still asks before `approve`, `approve-plan`, `rank`, `done`,
  `release`, and `claim`. `--remove` takes both back.
- Slash commands: `/pulse` (where things stand, what comes next),
  `/pulse-ba`, `/pulse-re`, `/pulse-build` (test first, also tests for
  existing code and a red suite), `/pulse-audit`, `/pulse-go`,
  `/pulse-map`, `/pulse-setup`, and `/pulse-realign`. Planning and review
  run as steps inside the flow.
- The `pulse` command line (Python 3.9 or newer, standard library only):
  `status` prints where things stand once (`--json` gives its data),
  `show`, `approve`, `approve-plan`, `rank`, `go`, `map`, `setup`,
  `release`, and `done`. The commands for skills and hooks (`claim`,
  `new`, `beat`, `block`, `review`, `audit`, `check`, `migrate`) have
  their own group in `pulse --help`.
- Specs in the repository, state on the board: every epic, feature,
  improvement, and fix is a Markdown spec in `_devprocess/`; its state
  (approved, taken, blocked, done) is a small record on GitHub that only
  `pulse` writes, read from a local cache. `pulse new --spec` records an
  item only once its spec is committed and pushed, and `pulse approve`
  refuses while the spec is not on the base branch.
- Specs an agent can plan from: scope with what is out, numbered
  requirements in EARS form, assumptions, open questions, and risk flags.
  `pulse check` applies the rules R1 to R6 to every approved item's spec
  and C1 to C9 to the documents; offline it says R1 to R6 were not
  checked and blocks nothing.
- `pulse go` plans and builds every approved item in parallel, one
  worktree and one headless agent (Claude Code or Codex) each, in the
  team's order from `pulse rank`; two items that touch the same files do
  not run at the same time. An item without a PLAN is planned first, and
  a PLAN that fails the plan gate (P1 to P5) gets up to two fix rounds.
  With `plan_approval = "auto"` a PLAN nothing holds is built; a risk
  flag, effort L, `needs:`, or `manual` waits for `pulse approve-plan`.
  `pulse go` does not start without a `verify` command. `--detach` runs
  it apart from the terminal, for example overnight;
  `.git/pulse/go/report.json` keeps every result as it happens, and
  `pulse status` names the last run.
- Spec tests first: one test per requirement, committed alone and frozen
  before the build. `pulse go` checks the frozen lines after every build
  and fix round, and checks RED itself: the tests must fail at the commit
  that froze them, or the pull request says so.
- Three gates after every build: the project's tests (`verify`), a
  review, and a security audit, the last two in fresh sessions. What an
  agent left uncommitted is committed before the gates, so all three
  judge the same commit. A red gate gets up to two fix rounds. One pull
  request per feature, ready when all three passed and a draft with the
  reasons otherwise; a feature whose blocker has a ready pull request
  stacks on the blocker's branch. A draft of `pulse go` that gets a new
  commit is taken up by the next run. At the end of a run with two or
  more ready pull requests, their branches are merged in dependency
  order in a scratch worktree and `verify` runs on the result.
- The security audit in the chain stands on a scan that Pulse runs
  itself. Dependency advisories come live from the OSV API, the only
  source for npm, PyPI, Go, and crates.io; without network the scan says
  `offline` instead of a clean result. An audit report without a
  `Coverage:` line, without a scan of its commit, or with a pass while
  the OSV lookup failed and the report does not say so gives no verdict.
  The bundled references carry an `as-of` date, and the brief and the
  report warn once one is 90 days old or has no date.
- Gate verdicts travel with the pull request: `pulse review` and
  `pulse audit` put them on the item's open pull request (`--publish` for
  the ones kept before it existed), so whoever takes the item over in
  another clone need not run the gates again.
- After every phase, `pulse go` compares the git config, the git hooks,
  and the files that tie a worktree to its repository with their state
  before. An agent that changed one of them stops its item: nothing is
  pushed, the claim stays, and the report names the files for a person
  to look at.
- Running and early work visible through the board: a claim names its
  phase and the time of its last sign of life, from `pulse go` at every
  phase and from an interactive session every ten minutes at most
  (`pulse beat` for skills); after 30 minutes without one the map says
  "no sign of life". `/pulse-ba` and `/pulse-re` work on a draft record
  (`pulse new <kind> <title> --draft`, label `pulse:draft`) that shows as
  "spec in progress by <login>"; `/pulse-re` checks the open drafts and
  items for overlap first, and `pulse new --spec <path> --issue <n>`
  attaches the spec to the draft.
- Work changes hands with its code: `pulse go` pushes the item branch
  after every agent phase that committed, and a run that fails, hits a
  usage limit, or stops gives the item back with a note (reason and
  branch) that the map shows; the next holder builds on that branch.
  `pulse release <n> --take` hands over another person's claim,
  `pulse claim <n> --take` takes over from an ended session of your own,
  and `pulse approve --undo` takes an approval back.
- Pulse stops for a person only at the business analysis, each spec
  (`pulse approve` means build it), a PLAN that something holds, and the
  merge of each feature's pull request.
- An item belongs to the session that claimed it; another session is
  refused, also under the same GitHub login.
- The live map in the terminal, `pulse map` (`pulse status` prints one
  frame): who works on which item and in which phase, what goes out
  next, what failed, and what waits for you; a working agent's light
  breathes. Arrows or `j`/`k` select, `Enter` opens an item with its
  goal, stage, holder, blockers, pull request, and PLAN; there `a`
  approves it, `p` approves its PLAN after showing what that binds, `o`
  opens the spec in your editor, and `m` moves it in the team order
  (arrows, then `Enter`). `Esc` goes back, `?` shows the keys, `q` quits.
  `/pulse-map` opens it in a tmux pane beside the chat or names the
  command for a second terminal, and `/pulse-setup` offers a VS Code and
  Cursor task for it.
- Hooks in every session and subagent: the rules and the active item at
  the start, one reminder when code changed without a check, one when a
  pull request's last commit has no review or audit (Claude Code), and
  presence events for the map from Claude Code and the Codex CLI.
- An optional git hook refuses commits on protected branches and commits
  with `pulse check` findings.
- `/pulse-realign` and `pulse migrate` take over a DIA project: settings,
  anchor blocks, frontmatter, and the old `BACKLOG.md` as records on the
  board. A project that enabled the DIA plugin switches to Pulse when it
  is installed.

### Changed from DIA 4.0.2

- Skills renamed: `business-analysis` to `pulse-ba`,
  `requirements-engineering` to `pulse-re`, `architecture` to
  `pulse-plan`, `coding` and `testing` to `pulse-build`,
  `security-audit` to `pulse-audit`, `dia-setup` to `pulse-setup`,
  `dia-realign` to `pulse-realign`, `dia-guide` to `pulse`.
- Settings move from `.dia/config.toml` to `.pulse/config.toml`
  (`mode = "on" | "off"`); the old file is still read as a fallback.

### Removed from DIA 4.0.2

- `BACKLOG.md` as the state store, commit trailers, phase tags, and the
  three modes.
- The skills `consistency-check` (now `pulse check`), `dia-bootstrap`,
  `project-conventions`, and `humanizer`, and the Copilot agent files
  under `.github/`.
