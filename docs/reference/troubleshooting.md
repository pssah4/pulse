---
title: Troubleshooting
description: Common problems when installing and running Pulse, and how to fix them.
---

# Troubleshooting

## Installation

### `/plugin isn't available in this environment` in VS Code

`/plugin` is the plugin panel of the Claude Code CLI. In the VS Code extension, type `/plugins` to open **Manage plugins**, or run the `claude plugin` commands in a terminal ([Installation](../tutorials/installation)). A plugin installed one way shows up in the other.

### `Host key verification failed` when adding the marketplace

Claude Code clones the short form `owner/repo` over SSH, and your machine does not trust GitHub's SSH host key yet. Use the HTTPS URL:

```bash
claude plugin marketplace add https://github.com/pssah4/pulse.git
```

### `claude: command not found`

Install the CLI (`curl -fsSL https://claude.ai/install.sh | bash`, or Homebrew), open a new shell, and check `claude --version`. The VS Code extension brings its own copy for its chat panel but puts no `claude` on your PATH.

### `pulse: command not found`

Run `pulse setup --cli` from the installed plugin (the command for your agent is in [Installation](../tutorials/installation)); in VS Code, run it in the integrated terminal. Then check that `~/.local/bin` is on your PATH: add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` (zsh) or to `~/.bash_profile` (bash; `~/.bashrc` on Linux) and open a new terminal. If `pulse` says "no installed Pulse found", the plugin is gone: install it again, or take the command out with `rm ~/.local/bin/pulse`. A terminal panel "Pulse map" that says `command not found: pulse` each time VS Code opens the folder comes from the task that `pulse setup` wrote to `.vscode/tasks.json`: put the command on your PATH, or delete the task.

Installed from a clone ([Codex without the plugin](../tutorials/installation#codex-without-the-plugin)): `~/.local/bin/pulse` is a link into the clone, and `pulse setup --cli` keeps it and reports `kept: not written by pulse setup`. Check the link with `ls -l ~/.local/bin/pulse`, which must point to `~/.codex/pulse/bin/pulse`, and that `~/.local/bin` is on your PATH.

### The `/pulse` commands do not show up

1. `claude plugin list` in a terminal, or **Manage plugins** (`/plugins`) in the VS Code extension, shows `pulse@pssah4-skills`?
2. Start a new session; skills load at session start.
3. Still the old commands (`/dia-guide`, `/coding`)? The predecessor plugin is still installed: see [Coming from the Digital Innovation Agents plugin](../tutorials/installation#coming-from-the-digital-innovation-agents-plugin).

### An update does not arrive

Claude Code does not update the `pssah4-skills` marketplace on its own. Run `claude plugin marketplace update pssah4-skills`, then `claude plugin update pulse@pssah4-skills`, and restart. In Codex, `codex plugin marketplace upgrade pssah4-skills` and then `codex plugin add pulse@pssah4-skills` again, and restart Codex or start a new chat in the extension.

### Codex does not find the skills

With the plugin, in the CLI and the IDE extension alike: `codex plugin list` shows `pulse@pssah4-skills` (without the CLI, first run the `codex()` line from [Installation](../tutorials/installation#codex-cli-and-ide-extension), which runs the extension's newest binary), then restart Codex or start a new chat in the extension. Installed from a clone, the fallback without the plugin: `ls ~/.agents/skills/pulse` must list the skill folders. With both, every skill shows up twice: remove one. Codex names the skills `pulse:pulse-ba` and so on: type `$pulse:pulse-ba` for `/pulse-ba`, in the CLI and the IDE extension alike. The Codex CLI also lists them under `/skills` > **List skills**, or as soon as you type `$`, by the names `pulse-ba (pulse)` and so on; in the IDE extension, type `/` in the prompt box and pick one from the **Skills** group.

## Running Pulse

### GitHub API rate limit

This is GitHub's request budget, not the agent's token allowance. Pulse pauses requests until GitHub's reset or Retry-After deadline, and uses bounded backoff when no deadline is available. The map names the limit and marks its cached board as stale. Its counts may no longer match GitHub. It clears the warning after a successful fresh read; restarting the map does not bypass the shared cooldown.

Do not rotate credentials or remove the cooldown to force retries. Keep only the maps and runners you need open. Requests from other tools can consume the same account's budget. A stale board never authorizes a write; wait for a fresh read before approving work.

### A deferred item does not resume automatically

That is intentional. In your own terminal, `pulse resume <n>` resumes work explicitly. Defer preserves its approvals and PRs; normal content and commit checks still apply. A stop request with an unreachable holder remains pending. If uncommitted work needs its original worktree, use that clone for the handover instead of deleting the worktree or taking its claim blindly.

### `pulse` says "not inside a git repository" or names several remotes

Pulse needs to know which GitHub repository holds the item records. It takes, in this order, `repo` from `.pulse/config.toml`, the repository set with `gh repo set-default`, or the only GitHub remote. With several remotes it does not guess:

```bash
gh repo set-default owner/name
```

### `pulse setup` complains about `gh`

Pulse needs `gh` 2.94 or newer for parent links and "blocked by" links. Update it (`brew upgrade gh`, or see [cli.github.com](https://cli.github.com)) and run `gh auth status`.

### `pulse new` refuses: push the spec first

A record links a spec that every clone must be able to read and an agent can plan from, so `pulse new --spec` checks the file as committed before it writes anything. A spec that breaks one of R2 to R6 is refused with its findings (exit 1), as `pulse check --spec` names them; only its `issue:` line is left out, since `pulse new` writes it. On a docs branch (a branch other than the base that changes nothing outside `_devprocess/` and is no item's build branch `<type>/<n>-<slug>`), `pulse new` pushes the branch and opens its docs PR into the base branch, or uses the open one; when origin refuses the push, it stops with `git push said: ...` (exit 2). On the base branch or a build branch it pushes nothing and stops while the committed spec is not on origin (exit 2):

```text
pulse new: _devprocess/requirements/features/FEAT-01-02-login.md is not on origin as committed here; commit it, then: git push -u origin docs/12-login
```

Commit the spec, run the push the message names, and run the same `pulse new` again. A spec you changed after the push needs another commit and push. `write the spec first, <path> does not exist in the repository` means the path is wrong or the spec is not written yet. For work whose spec does not exist yet, register a draft instead: `pulse new <type> "<title>" --draft`. `could not add label: 'P1' not found` means the project set up its labels before the priority labels existed: run `pulse setup --labels` once, then the same `pulse new` again. With `--issue`, `pulse new` wrote nothing to the record yet, so the rerun goes through.

### `pulse new`, `pulse number`, or `pulse claim` says `git fetch said`

`pulse new --spec`, `pulse number --apply`, and `pulse claim` fetch every branch from origin, then ask origin which commit each branch is on (`git ls-remote`) and hold that against the refs git lists here. After a fetch that failed while origin answered, they print git's error; after one that went through but left a listed ref on another commit than origin names, they print `the fetch went through, but refs here differ from origin:` and the refs. Only when something they need is not as origin has it do `pulse new` and `pulse number` refuse (exit 2) and `pulse claim` name no start point (it still exits 0, the claim made):

```text
pulse number: git fetch said: error: cannot lock ref 'refs/remotes/origin/docs/login': Unable to create '/home/ana/shop/.git/refs/remotes/origin/docs/login.lock': File exists. Another git process seems to be running in this repository, or the lock file may be stale
```

- `pulse new --spec` on the base branch or a build branch needs the branch you are on as origin has it, and refuses when origin no longer has that branch; on a docs branch it pushes and fetches nothing.
- `pulse number --apply` needs the history of every branch on origin. A branch whose ref git could not update, or wrote on another commit, counts through the commit origin names; when that commit or its history did not arrive (a fetch cut short), the refusal names the branch. Of two specs with the same ID, the one on the base branch as origin has it keeps the ID.
- `pulse claim` names no start point while the ref it lists for the base branch or a branch of the item is not as origin has it (`start point not checked: ...`); otherwise it names the start point.

When they go on, the line goes to stderr. `pulse status`, also for one item, and `pulse approve` print the same `git fetch said: ...` until a fetch goes through. A timeout says `no answer within 60 s`; Pulse ends Git and its transport processes, keeps that cause, and skips the second remote query. `offline: origin did not answer` means no more specific cause was available. Two common causes:

- A lock file that a git process left when it stopped (`File exists`): when no other git runs in the clone, delete the `.lock` file the message names.
- Two branches whose names differ only in case (on origin, or a local branch beside one on origin), on a file system that ignores case (macOS, Windows, where git sets `core.ignorecase`): the clone keeps one ref file for both, loose or in `packed-refs`, and a fetch may even exit without an error. Pulse then says `branch names that differ only in case share one ref file here:` and the names. `pulse new` registers nothing, `pulse claim` names no start point, `pulse number` counts through the commits origin names, `pulse go` starts nothing from the base or the item's branch, and the hint of `pulse claim` and `pulse release` on where another holder's work is says `where the work is stays unnamed`. With `core.ignorecase` set and origin not answering, `pulse go` starts nothing either. Delete or rename one of the two branches on origin, or move the clone to the reftable format with `git refs migrate --ref-format=reftable` (git 2.46 or newer).

`git fetch --prune origin` shows git's whole message. When origin does not answer at all, `pulse new` and `pulse number` refuse with `origin did not answer` and hand out nothing; `pulse claim` makes the claim and says `start point not checked: origin did not answer`.

Pulse's Git network calls also disable terminal, SSH Askpass and Git Credential Manager prompts, including during checks of preserved work and feature removal. Existing credentials and SSH configuration still apply. If authentication needs your attention, run `git fetch origin` in your own terminal, resolve the reported login or host-key issue there, then retry Pulse. A transport that does not respond stops after 60 seconds.

### `pulse approve` refuses: the spec is neither on the base branch nor in a pull request

```text
#12 not approved: R1 spec not on origin/main and in no open pull request; /pulse-re pushes it
```

Agents plan from the spec as the base branch on origin has it (rule R1). `pulse approve` writes the approval and nothing else; [`pulse go`](../guides/pulse-go) merges the spec into the base branch first, through the docs PR that `pulse new` opened. Here the base branch lacks the spec and no open pull request carries it: push the spec on its docs branch, or let `/pulse-re` do it (its `pulse new` opens the docs PR), then approve again. `R1 issue: ... in the spec, item is #12` means the spec names another item or none: commit the `issue:` line that `pulse new` wrote into the spec and push. For a feature, improvement, or fix, `pulse approve` also refuses a spec on the base branch that breaks one of R2 to R6; an epic needs R1 only.

### `pulse go` does not merge a docs PR

The run's report names why, and the ramp keeps `spec in PR #m: pulse go merges it` meanwhile:

- A spec in the pull request breaks one of R1 to R6: fix it with `/pulse-re` on the docs branch and push.
- The merge would change a file outside `_devprocess/`, or add a link or a submodule there. A spec committed on a build branch reaches the base branch with that branch's pull request. Pulse judges the merge as git makes it, so a moved file or a history that merges back and forth counts with every path the merge writes.
- It waits for its checks: `pulse go` set the status `pulse/tests` ("docs only: R1-R6") at the head it checked and merges once the whole rollup of that head passed, in a later run.
- It does not merge cleanly (`PR #8 does not merge cleanly into main here ...`), most often because a second feature of the same epic merged first: each `pulse new` adds its line at the end of the epic's `## Items`. The way on: merge `refs/remotes/origin/<base>` into the docs branch (`git fetch origin`, then `git merge refs/remotes/origin/main` on the docs branch), keep both lines where they conflict, commit, and push the branch; the next run merges it.
- The approval came from an account that may not push to the repository: someone who may approves the item again.

`pulse go` merges only the head it checked. When GitHub only queues the merge, the spec reaches the base branch later, and a later run plans the item.

### The map does not start `pulse go`

It never does. Start `pulse go` in your own terminal or explicitly ask the Pulse skill to start it in a foreground TTY. Ctrl-C stops a terminal run; ask the skill to stop its run ([pulse go](../guides/pulse-go#start-a-run)).

### The map shows "no agent active" although an agent works

The map shows claims, not sessions: no hook records what a session does. An item a session holds shows up under its holder with how long it is held (`held 2 h`); an item a `pulse go` run holds, with the phase and the age of the run's last sign of life. An agent that `pulse go` started counts as working while its phase runs.

### `pulse map` prints one frame and ends

It does that without a terminal: in a pipe, a file, or an agent's shell tool. Run it in a terminal of its own; [pulse map](../guides/pulse-map#open-it-from-the-chat) says where for each chat. A working light that does not breathe is no fault: terminals with 16 colors show steady lights.

### The agent ignores the rules

Check `.pulse/config.toml`: `mode = "off"` silences every hook. In Claude Code, `claude plugin list` in a terminal, or **Manage plugins** (`/plugins`) in the VS Code extension, should show `pulse` as enabled. In Codex, the plugin's hooks bring the rules once you trusted them; Codex installed from a clone reads them from its global `AGENTS.md`, in `$CODEX_HOME` when you set it, else in `~/.codex` (see [Codex without the plugin](../tutorials/installation#codex-without-the-plugin)).

### `pulse check` reports findings

Each finding names the file, the line, and the rule (C1 to C10, or R1 to R6 for an approved item's spec, see [Commands](./commands#pulse-check)). Fix the document, or for a cap, add a `## Reasoned exception` section (the heading in any case). An epic's `## Items` list, which `pulse new` writes, does not count toward its cap.

A C10 finding names a spec whose file name lacks the ID of its place in the tree: it has none yet, it moved to another parent, or another branch took the same ID. `pulse number --apply` renames it, rewrites the paths to it, and moves its record along; commit the result. An open record keeps its old path until the rename is on the base branch: after the merge, run `pulse number --apply` once more.

An R finding is about the spec as the base branch on origin has it. A fix on your branch clears it only once it is merged. The way out:

1. Take the approval back, so no session or `pulse go` run claims the item meanwhile: remove the `pulse:approved` label in GitHub. When nothing would claim it, the approval can stay: skip this step and step 3.
2. Fix the spec on a branch, with [`/pulse-re`](../guides/pulse-re) or by hand, push it, and merge it into the base branch.
3. `pulse approve <n>` again. It reads the base branch on origin and refuses while the spec there still breaks one of R1 to R6.

`pulse check` reads origin as of your last fetch: after the merge, pull the base branch, and the finding is gone.

### `pulse claim` says an item is held

Every claim leaves a mark on the item's record that names the session holding it: a Claude Code session, a Codex thread, a `pulse go` run, or a terminal. Another session is refused, even under your login, so two agents never build the same item. The refusal names the holder, since when, and the command that frees the item:

```text
#12 is held by alice since 2026-09-24 09:12 UTC; to hand it over: pulse release --take 12
```

- **Another person holds it:** agree with them first. `pulse release --take <n>` then hands the item over: their assignee and claim marks go, and a comment on the record names who did it. Claim it as usual afterwards. An agent runs this only after you said yes. For a draft, the refusal and the hand-over name its docs branch on origin as where the work is (`; the work is on origin/docs/12-mode`), and the claim starts from it.
- **Another session of yours holds it and has ended:** `pulse claim --take <n>` takes it over.

`release` refuses a claim that is not yours in the same way.

### The map says `spec in progress by <login>`

The item is a draft: a `/pulse-ba`, `/pulse-re`, or `/pulse-realign` session of that person registered it with `pulse new ... --draft` and holds it while it writes. A draft has no spec on the board yet, cannot be approved, and no agent builds it. Talk to that person before you write about the same topic. The draft ends when its spec is pushed and attached with `pulse new <type> "<title>" --spec <path> --issue <n>`. A draft that a session of your own held before it ended: `pulse claim --take <n>` in the new session.

### `pulse new --draft` says `is the draft ... already`

An open draft of the same type carries the same title, for example a realign (`Realign: <owner/repo>`) or a Project-BA that another session started. The line names its number and who holds it, and nothing new is created. A draft another person holds stays theirs: talk to them. One nobody holds, or one of yours, goes on with the same command plus `--issue <n>`; a session of your own that has ended hands it over with `pulse claim --take <n>`.

### The map says `no sign of life`

A teammate's `pulse go` run holds the item and has not reported for 30 minutes or more. `pulse go` reports each phase it starts and every 10 minutes while one runs, so silence means the run was stopped, or its machine is off the network. `pulse status <n>` prints `claimed_phase` and `claimed_beat`, the time of the last report in UTC. A session's claim never says this: nothing renews its time, so the map shows how long it is held (`held 2 h`), which says nothing about whether the session still works.

Ask the holder. Once they agree, `pulse release --take <n>` hands the item over; claim it, then continue on the item branch they pushed (`pulse go` starts from it on its own, `/pulse-build <n>` continues on it). What they did not push stays on their machine. A session of theirs that still runs learns of the hand-over from its next `pulse claim` or `pulse release`, which names who has the item now: it stops the work on the item and pushes nothing more of it. Its stop hook asks for no push of the item, since it reads who holds the item from the board at every stop, and a new session on the item's branch hears who holds it. Its `pulse release <n>` answers that the item was handed over and there is nothing to give back.

### The ramp says `last run: ...`

A `pulse go` run gave the item back and left a note on it: why it stopped (a failure or a stop) and which branch holds its work. The map shows the first line; `pulse status <n>` prints the whole note. Nobody holds the item, so claim it as usual. `pulse go` starts its worktree from the pushed item branch; in a session, `/pulse-build <n>` continues on that branch. Changes of a phase the run stopped halfway stay in that run's worktree, under `.worktrees/` in the repository of the machine that ran it.

### A command says "only a person does this"

`approve`, `auto` with `on` or `off`, `claim --take`, and `release --take` refuse to run in an agent session, which carries `PULSE_HOLDER`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, or `CODEX_THREAD_ID`, and when stdin is not a terminal. These decisions belong to a person: run the command in your own terminal. An explicit `pulse go` request can run through the interactive Pulse skill with a persistent TTY; nested runners and starts without a TTY are refused. So do `setup --remove` and `setup --mode off`, which would switch the guard off. `CLAUDECODE` alone does not count, since IDE extensions set it in their terminals too. Such an agent also claims and gives back only the item it was started for (`PULSE_ITEM`); `pulse claim` or `pulse release` of another item ends with "claims and releases only its own item".

### An agent's command is denied: "Gate levers belong to a person"

The [Pulse guard](../concepts/parallel-work#levers-belong-to-a-person) denied a command that pulls a person's lever, or that sends one into another terminal. The agent should name the gate that waits; run the command in your own terminal when you want it. The guard also denies a search for such a phrase, such as `grep -r "pulse approve" docs/`: it reads quoted text too. Search for `pulse.approve` instead, or run the search yourself.

### The map names another account

Pulse acts as the account `gh` uses in that terminal: `gh auth status` shows it, and a `GH_TOKEN` in the environment wins over the login. Switch with `gh auth switch`, or unset `GH_TOKEN`; the map shows the new account at once, since Pulse keeps the login per gh config and token. A map that another program started, such as a Herdr pane or a VS Code task, has that program's environment. Every approval names its account in a comment on the item, such as `gate 1 approved by Sebastian Hanke (@pssah4)`.

### `Codex hooks not trusted: run /hooks in Codex`

The agents of this project include Codex (`agent` in `.pulse/config.toml`), and Codex has not trusted the Pulse hooks yet: its sessions get no rules, and the lever guard does not run there. Start `codex` in the project and trust them with `/hooks` in the CLI, or click **Trust** on each Pulse hook on the Hooks page of the IDE extension's settings. Pulse reads the trust from `$CODEX_HOME/config.toml` (else `~/.codex/config.toml`), where Codex keeps it as tables named `[hooks.state."pulse@pssah4-skills:..."]`.

### `pulse go` skips an item: `on hold (pulse:hold)`

A person set the label `pulse:hold` on the item in GitHub. `pulse go` neither plans nor builds it. Remove the label, and the next run goes on with it.

### `pulse go` starts nothing: `base red: <check>`

The current project CI failed that check. Read the cause, next action and run link in the map or `.git/pulse/go/report.json`, then repair the failing project check. An item marked `pulse:base` may repair the base through its normal approvals. Startup reads current CI and matching existing evidence; it no longer runs local `setup` or the full `verify` before planning. Proven GitHub Dependabot update searches are excluded, but a project check with the same name still counts. A newer CI result at the same commit takes precedence over an older Pulse result. Without project CI or matching successful evidence, Pulse starts without inventing a green status; full verification applies to the implemented result.

### `pulse go` pauses: `hook rejected: <hook> at #n`

A project hook refused a commit or push of `pulse go` for item #n. The run starts nothing new until the base branch moves or you start it again, and the item gives its claim back without failing; its worktree keeps the work. `pulse go` never skips a hook: run the hook's check in the worktree, fix the cause, then start `pulse go` again.

### `pulse go` does not start: `no [spec_tests]`

`pulse go` runs each spec test with its own runner and reads the runners from `[spec_tests]` in `.pulse/config.toml` on the base branch as origin has it, like `verify`, `setup`, and `[agents]`. Add the section ([Configuration](./configuration)), commit it, and merge it into the base branch; a change only in your working tree counts for nothing.

### `pulse go` skips an item: `needs a Claude agent (localhost spec tests)`

A spec test of the item's first wave matches a pattern of `[spec_tests]` with `localhost = true`, and Codex runs without network, so it cannot reach that server. Add `claude` to `agent` in `.pulse/config.toml` (`claude:2,codex:2`, say), or build the item in a Claude Code session with `/pulse-build <n>`.

### `pulse go` skips an item: `failed (pulse:failed)`

A run of `pulse go` gave up on the item: it set the label `pulse:failed` and left a comment `pulse go: failed at <base>: <reason>`. No run plans or builds it again on its own. Read the reason and the log `.git/pulse/go/<n>.log`, fix what it names, then run `pulse approve <n>` in your own terminal: it takes the label off, and the next run tries again.

### An item was approved by mistake

Remove the `pulse:approved` label in GitHub: the map writes approvals only. Until someone approves it again, no session and no `pulse go` run claims it.

### An agent of `pulse go` is refused a command

A headless agent cannot answer a permission prompt, so it runs only what its template allows. The built-in Claude template allows `verify` up to its first option or path, five git commands, and the runners of `[spec_tests]`, and never `gh`: `pulse go` does everything on GitHub itself; the Codex template lets Codex write the shared git directory so it can commit. A template in `[agents]` copied from an older Pulse lacks both rights. See [Agent templates](./configuration#agent-templates) for what the rule covers and how to fix a template.

### `pulse go` leaves an item as failed

Its claim goes back to the ramp and its worktree stays for a look; the log is in `.git/pulse/go/<n>.log`. Fix the cause, then run `pulse go` again.

### `pulse go` refuses a branch with a foreign upstream

A local branch left by `gh pr checkout` may follow a fork or an origin
`refs/pull/...` ref. Pulse skips it when finding an item's branch and,
if its generated branch name would reuse it, stops before setup with
`has a foreign upstream`. Keep the reviewed fork on a different branch
name, then retry. An own branch without an upstream, or one tracking a
branch on origin or in this clone, still works. Change its tracking
configuration only after checking that the commits belong to your work.

## Known limits

- **The guard reads commands, not files.** It checks shell, Monitor, and MCP calls. An agent that writes `.pulse/config.toml` or `.claude/settings.json` with its own file tools, or runs a script file, passes it ([Levers belong to a person](../concepts/parallel-work#levers-belong-to-a-person)). While a map runs, it refuses more tmux commands than it needs to.
- **The guard reads quoted text too.** A commit message or a search that contains a lever, such as `pulse auto build on`, is denied.
- **Auto mode.** Two first `pulse auto ... on` at the same moment make two issues "Pulse auto mode", and every switch is off until you close one. A switch comment you delete brings back the one before it; one you edit turns that gate off for its login.
- **Spec tests.** A runner that waits for the lock of another item's spec tests spends that time from `agent_timeout`. The PLAN rule P6 looks only at files whose names read as tests.
- **Herdr.** The pane beside the chat and the notifications are tested against a stand-in for Herdr; tell us when yours behaves differently.

## Versions

`claude plugin list` and `codex plugin list` show the installed version; the [changelog](https://github.com/pssah4/pulse/blob/main/CHANGELOG.md) says what each version brought. After an update, restart the agent: a running Claude Code session keeps the version it started with, while the Codex update deletes the old version folder that a running Codex session still points at.

## Still stuck?

Open an issue on [GitHub](https://github.com/pssah4/pulse/issues) with your platform, `pulse --help` output, and what you tried.
