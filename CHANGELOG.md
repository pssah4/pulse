# Changelog

All notable changes to Pulse are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
