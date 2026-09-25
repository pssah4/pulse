---
title: Installation
description: Install, update, and remove Pulse with your coding agent's own plugin commands, then switch it on per project.
---

# Installation

Pulse installs from its GitHub repository, [pssah4/pulse](https://github.com/pssah4/pulse), with the plugin commands of your coding agent; the same commands update and remove it. Pulse supports Claude Code and Codex, each in the terminal and in the VS Code extension. Support for GitHub Copilot, Cursor, Gemini CLI, and OpenCode will follow.

**You need** Python 3.9 or newer, the GitHub CLI [`gh`](https://cli.github.com) 2.94 or newer (logged in with `gh auth login`), and a GitHub repository for your project. Pulse keeps its board there, one small record per item; everything else stays in your repository.

## Step by step

These steps take you from nothing to Pulse in your first project, for Claude Code and Codex, in the terminal and in the VS Code extension. Skip the tool you do not use. The sections further down explain each step, with removal; [a script](#or-let-a-script-do-steps-3-to-5) can do steps 3 to 5 for you, and [Update](#update) brings a newer Pulse.

**1. Check what you need.** Python 3.9 or newer, `gh` 2.94 or newer, logged in:

```bash
python3 --version
gh --version
gh auth status
```

**2. Optional: remove the Digital Innovation Agents plugin.** If you used it, it holds the marketplace name `pssah4-skills` that Pulse takes over. Remove it first as [Coming from the Digital Innovation Agents plugin](#coming-from-the-digital-innovation-agents-plugin) shows.

**3. Claude Code.** One install serves the terminal and the VS Code extension:

```bash
claude plugin marketplace add https://github.com/pssah4/pulse.git
claude plugin install pulse@pssah4-skills
```

Without the `claude` command, install it from the extension instead: type `/plugins` in its prompt box ([VS Code extension](#vs-code-extension)). Check: in a new session, typing `/pulse` lists the Pulse commands.

**4. Codex.** Install with the Codex CLI, also if you work only in the IDE extension; both share the install. If you have only the extension, first give every terminal a `codex` command that runs the newest binary the extension brings, then reload your profile:

```bash
echo 'codex() { "$(ls ~/.vscode/extensions/openai.chatgpt-*/bin/*/codex | sort -V | tail -1)" "$@"; }' >> ~/.zshrc
source ~/.zshrc
```

For bash, use `~/.bash_profile` on macOS and `~/.bashrc` on Linux. Then install Pulse:

```bash
codex plugin marketplace add pssah4/pulse
codex plugin add pulse@pssah4-skills
```

Check: in a new Codex chat, `$pulse:pulse` answers.

**5. The `pulse` command**, once per machine. It runs the newest Pulse you installed, so an update needs no new step:

```bash
P="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/cache/pssah4-skills/pulse"
"$P/$(ls "$P" | sort -V | tail -1)/bin/pulse" setup --cli
```

With Codex only, the first line reads `P="${CODEX_HOME:-$HOME/.codex}/plugins/cache/pssah4-skills/pulse"`. If the report says `"on_path": false`, add `~/.local/bin` to your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

Open a new terminal. Check: `pulse --help` lists the commands.

**6. Codex: trust the Pulse hooks.** Start `codex` in your project and pick **Trust all and continue**; later, `/hooks` in the CLI shows the list. In the IDE extension, click **Trust** on each Pulse hook on the Hooks page of its settings. Optional: `pulse setup --codex-rules` lets Codex run `pulse` without asking ([details](#codex-cli-and-ide-extension)).

**7. Restart.** Start a new Claude Code session, or reload the VS Code window (**Developer: Reload Window**), and restart Codex. A session that was running before the install does not see Pulse. After a change to your PATH, quit VS Code and open it again.

**8. In each project.** Type `/pulse-setup` in Claude Code, `$pulse:pulse-setup` in Codex. It asks a few questions and writes `.pulse/config.toml`; commit it on a branch as [Switch it on in your project](#switch-it-on-in-your-project) shows. From then on, `/pulse` (in Codex `$pulse:pulse`) says where the work stands and what comes next.

### Or let a script do steps 3 to 5

```bash
curl -fsSL https://pssah4.github.io/pulse/install.py | python3 -
```

The script finds `claude` and `codex`, also the binaries the VS Code extensions bring. It installs or updates Pulse in each, writes the `pulse` command, and asks before it adds a line to your shell profile or writes the Codex rules. It shows every command before it runs it and removes nothing: a marketplace `pssah4-skills` from another source stays as it is, and the script points you to step 2. `--dry-run` shows what it would run, and `--yes` answers yes to every question (`curl -fsSL https://pssah4.github.io/pulse/install.py | python3 - --dry-run`). Steps 6 to 8 stay with you; the script lists them at the end. Read it before you run it: [install.py](https://pssah4.github.io/pulse/install.py).

## Update

Pulse does not update itself, and neither Claude Code nor Codex refreshes its marketplace on its own. Update every tool you installed Pulse in:

| Where | Update |
|---|---|
| Claude Code, terminal | `claude plugin marketplace update pssah4-skills`, then `claude plugin update pulse@pssah4-skills` |
| Claude Code, VS Code extension | type `/plugins`, refresh `pssah4-skills` in the **Marketplaces** tab, then click the update icon on the Pulse row in the **Plugins** tab |
| Codex, CLI and IDE extension | `codex plugin marketplace upgrade pssah4-skills`, then `codex plugin add pulse@pssah4-skills` |
| Codex without the plugin | `git -C ~/.codex/pulse pull` |

The install script does the same for every install it finds:

```bash
curl -fsSL https://pssah4.github.io/pulse/install.py | python3 -
```

Then restart: start a new Claude Code session, or reload the VS Code window (**Developer: Reload Window**), and restart Codex or start a new chat in its IDE extension. A session that was running keeps the old version, and a Codex session still points at the folder the update deleted.

Nothing else needs doing. The `pulse` command runs the newest version you installed, and your projects keep their `.pulse/config.toml`. `claude plugin list` and `codex plugin list` show the version. When a release needs a step in your projects, its notes say so under **Upgrading**, in the [changelog](https://github.com/pssah4/pulse/blob/main/CHANGELOG.md) and on the [release page](https://github.com/pssah4/pulse/releases).

## Claude Code

One installation serves the terminal and the VS Code extension: a plugin you add in one shows up in the other.

### Terminal

Check that the Claude Code CLI is there with `claude --version`. If not, install it on macOS, Linux, or WSL:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Or with Homebrew:

```bash
brew install --cask claude-code
```

Install Pulse:

```bash
claude plugin marketplace add https://github.com/pssah4/pulse.git
claude plugin install pulse@pssah4-skills
```

Start a new session and type `/pulse`: autocomplete lists the Pulse commands.

Then put the `pulse` command on your PATH, once per machine:

```bash
P="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/cache/pssah4-skills/pulse"
"$P/$(ls "$P" | sort -V | tail -1)/bin/pulse" setup --cli
```

Claude Code keeps older version folders after an update, so the line picks the newest. The cache lies under `CLAUDE_CONFIG_DIR` when you set it, else under `~/.claude`. `/pulse-setup` in a Claude Code session offers the same step.

This writes `~/.local/bin/pulse`, a short script that runs the newest Pulse of the agent that calls it: a Codex session its Codex copy, a Claude Code session its Claude Code copy, and your own terminal the newest of both. An update needs no new setup, and neither agent needs the other. If its report says `"on_path": false`, add `export PATH="$HOME/.local/bin:$PATH"` to your shell profile: `~/.zshrc` for zsh, the macOS default; for bash, `~/.bash_profile` on macOS and `~/.bashrc` on Linux. The change reaches only shells started after it, so open a new terminal (restart VS Code if you work there) and check with `pulse --help`. Until then, `~/.local/bin/pulse` runs it by its full path.

Update (Claude Code does not update this marketplace on its own), then restart Claude Code:

```bash
claude plugin marketplace update pssah4-skills
claude plugin update pulse@pssah4-skills
```

Uninstall. First [take Pulse out of each project](#take-it-out-of-a-project) that uses it. Then the first line below, because the `pulse` command runs through the installed plugin; skip it if Pulse stays installed in Codex:

```bash
pulse setup --remove --cli
claude plugin uninstall pulse@pssah4-skills
claude plugin marketplace remove pssah4-skills
```

On Windows, run Claude Code and Pulse inside WSL.

### VS Code extension

The extension brings its own copy of Claude Code, so it needs no CLI for plugins. Type `/plugins` in the prompt box to open **Manage plugins**:

1. In the **Marketplaces** tab, add `https://github.com/pssah4/pulse.git`.
2. In the **Plugins** tab, click **Install** on `pulse` and choose **Install for you**.

The install reaches the sessions open in that window at once: type `/pulse` in the prompt box, and autocomplete lists the Pulse commands. If a session cannot reload its plugins, the dialog offers to try again or to restart Claude in that session.

To update, refresh `pssah4-skills` in the **Marketplaces** tab, then click the update icon on the Pulse row in the **Plugins** tab, and reload the window (**Developer: Reload Window**): a running session keeps the version it started with.

For the `pulse` command, run the `setup --cli` line from the terminal steps above in VS Code's integrated terminal, or let [`/pulse-setup`](#switch-it-on-in-your-project) do it.

To uninstall, first [take Pulse out of each project](#take-it-out-of-a-project), then run `pulse setup --remove --cli` in VS Code's integrated terminal (skip it if Pulse stays installed in Codex): the `pulse` command runs through the installed plugin. Then click the uninstall icon on the Pulse row in the **Plugins** tab, and remove the marketplace with its trash icon.

## Codex

One installation serves the Codex CLI and the IDE extension: Pulse as a plugin with hooks, so the rules reach every session and sessions show up on the live map. You install it and trust its hooks once, and the extension picks it up in a new chat. OpenAI documents plugins as unsupported in the IDE extension and does not promise this; current versions load the plugin anyway, and a Pulse test checks that they still do. [Codex without the plugin](#codex-without-the-plugin) is the fallback, without hooks. Take one of the two: with both, every skill shows up twice.

### Codex CLI and IDE extension

Check that the Codex CLI is there with `codex --version`. If not, install it on macOS or Linux with OpenAI's installer:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

Or with Homebrew (`npm install -g @openai/codex` works too):

```bash
brew install --cask codex
```

Install Pulse with the Codex CLI, also if you work in the IDE extension. If you work only in the IDE extension and do not install the CLI, run this line first: it makes `codex` in this shell the newest binary the extension brings (the extension puts none on your PATH), and the lines below then work as written.

```bash
codex() { "$(ls ~/.vscode/extensions/openai.chatgpt-*/bin/*/codex | sort -V | tail -1)" "$@"; }
```

The function lives only in this shell. To have `codex` in every new terminal, for the update and the uninstall too, add the line to your shell profile (`~/.zshrc` for zsh; for bash, see the [Claude Code terminal steps](#terminal)).

```bash
codex plugin marketplace add pssah4/pulse
codex plugin add pulse@pssah4-skills
```

Trust the hooks: start `codex` in your project. If you are not signed in yet, Codex asks you to sign in first; the CLI and the IDE extension share one sign-in. Then, in a folder it has not seen, it asks **Trust this folder?**; then it shows **Hooks need review**: pick **Trust all and continue**, or **Review hooks** to read each one (their source is `Plugin - pulse@pssah4-skills`). Later, `/hooks` in the CLI shows the same list, and `t` trusts all. The IDE extension has no `/hooks`: open its settings, go to the Hooks page, and under **From Plugins** click **Trust** on each hook of `pulse@pssah4-skills`; the page trusts one hook per click, and Pulse needs them all. Codex runs a plugin's hooks only after this review and asks again when an update changes them.

Then put the `pulse` command on your PATH (see the [Claude Code terminal steps](#terminal) for what it writes and for the shell profile when its report says `"on_path": false`); like there, the first two lines pick the newest version folder in the cache. The last line is optional and runs the new command by its full path, so it works before your PATH has it. Codex runs commands in a sandbox without network access, so every `pulse` command that reads or writes the board on GitHub asks you first; the line writes `~/.codex/rules/pulse.rules` (under `$CODEX_HOME` when you set it), which lets Codex run `pulse` outside its sandbox without asking. A rule matches a plain `pulse ...` command: a pipeline or a redirection, such as `pulse status --json | head`, runs inside the sandbox, where `.git` is read-only and GitHub is out of reach. Codex still asks before `approve`, `approve-plan`, `rank`, and `done`, which a person decides, and before every `release` and `claim`: a rule sees only how a command starts, so it cannot tell a handover with `--take` from the rest.

```bash
P="${CODEX_HOME:-$HOME/.codex}/plugins/cache/pssah4-skills/pulse"
"$P/$(ls "$P" | sort -V | tail -1)/bin/pulse" setup --cli
~/.local/bin/pulse setup --codex-rules
```

Restart Codex, or start a new chat in the IDE extension. If you just added `~/.local/bin` to your PATH, quit VS Code and open it again instead: a new chat keeps the PATH VS Code started with, and without `pulse` on it the Pulse hooks point the agent at the full path of the plugin copy, which the Codex rules do not match, so Codex asks before every `pulse` command.

The skills are called `pulse:pulse`, `pulse:pulse-ba`, and so on: type `$pulse:pulse-ba` in the prompt box, in the CLI and the IDE extension alike. The Codex CLI also lists them under `/skills` > **List skills**, or as soon as you type `$`, by the names `pulse-ba (pulse)` and so on; in the IDE extension, type `/` in the prompt box and pick one from the **Skills** group.

The rules cover `pulse` only. The skills also create branches, commit, and push; the sandbox keeps `.git` read-only and has no network, so Codex asks before each of these git commands. Approve them when it asks.

Update, then restart Codex, or start a new chat in the IDE extension: the update deletes the old version folder, and a running session still points its skills and hooks there.

```bash
codex plugin marketplace upgrade pssah4-skills
codex plugin add pulse@pssah4-skills
```

Uninstall: [take Pulse out of each project](#take-it-out-of-a-project) first, then the `pulse` command and the Codex rules (skip `--cli` if Pulse stays installed in Claude Code):

```bash
pulse setup --remove --cli --codex-rules
codex plugin remove pulse@pssah4-skills
codex plugin marketplace remove pssah4-skills
```

Codex keeps your trust of the Pulse hooks in `~/.codex/config.toml` (`$CODEX_HOME/config.toml` when you set `CODEX_HOME`), as tables named `[hooks.state."pulse@pssah4-skills:..."]`. Delete them if a later install should ask you again.

### Codex without the plugin

The fallback, for instance if an update of the IDE extension stops loading the plugin. Uninstall the plugin first. Clone Pulse, link its skills and its `pulse` command, and load its rules through your global `AGENTS.md`:

```bash
git clone https://github.com/pssah4/pulse.git ~/.codex/pulse
mkdir -p ~/.agents/skills ~/.local/bin
ln -s ~/.codex/pulse/skills ~/.agents/skills/pulse
ln -s ~/.codex/pulse/bin/pulse ~/.local/bin/pulse
ln -s ~/.codex/pulse/hooks/rules.md "${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
```

The last line puts the link where Codex reads its global `AGENTS.md`: in `$CODEX_HOME` when you set it, else in `~/.codex`. If you already have a global `AGENTS.md` there, leave out the last line and add this line to it instead: `Follow the Pulse rules in ~/.codex/pulse/hooks/rules.md.` Then restart Codex. Without hooks, these sessions have no light on the live map.

Check the command with `pulse --help`. The skills run `pulse` from your PATH, and without hooks nothing else tells Codex where it is: on `command not found`, put `~/.local/bin` on your PATH as in the [Claude Code terminal steps](#terminal). The Codex rules from the plugin steps work here too, with the same effect: `pulse setup --codex-rules`.

Update:

```bash
git -C ~/.codex/pulse pull
```

Uninstall: [take Pulse out of each project](#take-it-out-of-a-project) first, and remove the Codex rules while the clone is still there (the first line; it reports `unchanged` if you never wrote them). The last two lines delete the global `AGENTS.md` only if it is the link from above; if you added the Pulse line to your own `AGENTS.md`, take that line out by hand:

```bash
pulse setup --remove --codex-rules
rm ~/.agents/skills/pulse ~/.local/bin/pulse
rm -rf ~/.codex/pulse
A="${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
[ "$(readlink "$A")" = "$HOME/.codex/pulse/hooks/rules.md" ] && rm "$A"
```

Afterwards no `pulse` command is left in `~/.local/bin`: if Pulse stays installed in Claude Code, run the `setup --cli` line from the [terminal steps](#terminal) again.

## Switch it on in your project

In a session in your project, run `/pulse-setup` (in Codex, `$pulse:pulse-setup`). It writes `.pulse/config.toml`, creates the `pulse:` labels on GitHub once you agree, adds a short Pulse block to the agent files you have (CLAUDE.md, AGENTS.md, and others), and offers the `pulse` command if it is not on your PATH yet. It also offers a git hook: it refuses commits on `main`, `master`, `develop`, and `dev` (or the branches in `git config pulse.protected-branches`) and runs `pulse check` before each commit; `git commit --no-verify` bypasses it once. Details: [/pulse-setup](../guides/pulse-setup) and [Configuration](../reference/configuration).

Check the command with `pulse --help`.

Commit `.pulse/config.toml` and the agent files setup changed or created, so every clone of your team runs with the same settings; a clone without the file has Pulse switched off. With the git hook, commit them on a branch and merge it like any other change:

```bash
git switch -c chore/pulse-setup
git add .pulse/config.toml $(git ls-files --modified --others --exclude-standard -- CLAUDE.md AGENTS.md)
git commit -m "chore: switch on Pulse"
git push -u origin chore/pulse-setup
```

The `git add` line takes CLAUDE.md and AGENTS.md when setup changed or created them; add any other agent file setup changed or created by name. Then open a pull request for `chore/pulse-setup` and merge it.

After the merge, switch back to the base branch and pull, so the next branch starts with the settings: `git switch main && git pull` (your base branch in place of `main`).

In VS Code, `/pulse-setup` may also have written the task "Pulse map" to `.vscode/tasks.json`. It runs `pulse` from each person's PATH, so commit it only when the whole team has the `pulse` command and wants the map to start with the folder; otherwise leave it untracked, and it works for you alone. Claude Code protects `.vscode/`: it asks before it writes there, even in a mode that accepts edits (in auto mode its classifier decides): allow it, or add the task by hand as [/pulse-setup](../guides/pulse-setup#by-hand) shows.

### Fewer prompts in Claude Code

In its default mode, Claude Code asks before each file it writes, until you allow edits for the rest of the session, and before every shell command outside a small read-only set such as `git status`. In the Pulse flow that means `pulse status` (in `/pulse`, in `/pulse-re`, and before the first question of every `/pulse-ba` for the whole project, an epic, a feature, an improvement, or a fix), the new branch, `mkdir`, `git add`, `pulse check`, each commit and push, `pulse new`, and `gh pr create`. These rules in your project's `.claude/settings.local.json` let it run these steps without asking. It still asks before `approve`, `approve-plan`, `rank`, and `done`, which a person decides, before a handover with `--take`, and before `pulse -- <command>`:

```json
{
  "permissions": {
    "allow": [
      "Bash(pulse *)",
      "Bash(git switch -c *)",
      "Bash(git checkout -b *)",
      "Bash(git add *)",
      "Bash(git commit *)",
      "Bash(git push *)",
      "Bash(gh pr create *)",
      "Bash(mkdir -p _devprocess/*)"
    ],
    "ask": [
      "Bash(pulse approve *)",
      "Bash(pulse approve-plan *)",
      "Bash(pulse rank *)",
      "Bash(pulse done *)",
      "Bash(pulse claim *--take*)",
      "Bash(pulse release *--take*)",
      "Bash(pulse -- *)"
    ]
  }
}
```

If the file exists, add the rules to its `permissions`. They hold for you alone; in `.claude/settings.json` they hold for everyone who clones the project, once each person trusts the folder. Claude Code keeps `.claude/settings.local.json` out of git only when it creates the file itself. If you create it by hand, `git status` lists it as untracked and a `git add -A` would commit it: add the line `.claude/settings.local.json` to your `.gitignore`. `/permissions` lists the rules in effect.

A rule matches the command as the agent writes it: with `pulse` off your PATH, the Pulse hooks point the agent at the full path of the plugin copy, and `Bash(pulse *)` does not match it. Claude Code also asks before a command its own checks flag, even when a rule allows it, such as a `gh pr create` whose body has a Markdown heading inside quotes, or a `mkdir` with braces (`{epics,features}`). Allow it when asked.

### Take it out of a project

`pulse setup --mode off` silences the Pulse hooks, the git hook included, and keeps the files. `pulse setup --remove` takes the Pulse blocks out of the agent files and the git hook out of `.git/hooks`, and puts back a hook of yours that setup had kept as `pre-commit.bak`. It deletes an agent file that held nothing but the Pulse block, such as an AGENTS.md that setup created. Run it in each project before you uninstall Pulse: afterwards there is no `pulse` to run it with, and the git hook stays until you delete `.git/hooks/pre-commit` by hand.

Both leave the rest in place:

- `.pulse/config.toml`. After `--remove` it still says `mode = "on"`, so a clone that has it keeps Pulse on wherever the plugin is installed. Commit the agent files that `--remove` changed or deleted; if the team stops using Pulse, delete the config in the same commit.
- The task "Pulse map" in `.vscode/tasks.json`, if setup added it. Delete that entry, or VS Code runs `pulse map` each time the folder opens, and after the uninstall that terminal says `command not found: pulse`.
- The `pulse:` labels on GitHub and the records, which stay as plain issues. If the project leaves Pulse for good, delete the labels on GitHub (`gh label delete pulse:feat`, and so on).
- The local cache in the git directory, which is never committed: `rm -rf "$(git rev-parse --git-common-dir)/pulse"` deletes it.

## Coming from the Digital Innovation Agents plugin

Pulse replaces the Digital Innovation Agents plugin (DIA, last release 4.0.2), its predecessor, and keeps the marketplace name `pssah4-skills`. Remove the old marketplace, which also uninstalls DIA, then install Pulse as above:

```bash
claude plugin marketplace remove pssah4-skills
```

A project whose `.claude/settings.json` enables the old plugin switches to Pulse on its own. In Codex, remove the old plugin and marketplace first:

```bash
codex plugin remove digital-innovation-agents@pssah4-skills
codex plugin marketplace remove pssah4-skills
```

With the old manual Codex install, remove its clone, its link in `~/.agents/skills`, and its rules in `AGENTS.md`. Then run [`/pulse-realign`](../guides/pulse-realign) once in each project: it moves the settings and turns the old backlog file into records on the board.

## What's next

- [Your first business analysis](./first-business-analysis): `/pulse-ba` from a raw idea
- [A full V-Model run](./full-v-model-run): from idea to merged code
- [/pulse](../guides/pulse): where you stand and what comes next
