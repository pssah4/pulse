# Changelog

All notable changes to Pulse are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
