# Installing Pulse for Codex

Pulse comes to Codex as a plugin from `pssah4/pulse`, the same marketplace Claude Code uses. The plugin brings the skills and the Pulse hooks: the rules reach every session at its start and in each subagent, and the synchronous lever guard checks each shell, Monitor, and MCP call before it runs.

The plugin serves the Codex CLI and the Codex IDE extension alike: both read `~/.codex` (or `$CODEX_HOME` when you set it), so you install it and trust its hooks once, and the extension picks it up in a new chat. OpenAI documents plugins as unsupported in the IDE extension and does not promise this; current versions load the plugin anyway, and a Pulse test checks that they still do. The manual path is the fallback, without hooks. Take one path: with both, every skill shows up twice, so uninstall one before you switch to the other.

## Prerequisites

After upgrading, run `pulse setup --codex-rules` in your own terminal to refresh the machine rules. `pulse defer`, `resume`, `discard`, and `delete` are person-only commands, like the approval levers. Agents may prepare an explicitly requested removal PR, but cannot approve its merge or delete its issue.

- Git, Python 3.9 or newer, and the GitHub CLI `gh` 2.94 or newer
- For the plugin, the Codex CLI, also if you work in the IDE extension. Without it, run this line first: it makes `codex` in this shell the newest binary the extension brings (the extension puts none on your PATH), and the steps below then work as written.
  ```bash
  codex() { "$(ls ~/.vscode/extensions/openai.chatgpt-*/bin/*/codex | sort -V | tail -1)" "$@"; }
  ```
  The function lives only in this shell. To have `codex` in every new terminal, for the update and the uninstall too, add the line to your shell profile (`~/.zshrc` for zsh; for bash, `~/.bash_profile` on macOS and `~/.bashrc` on Linux).

## Plugin (Codex CLI and IDE extension)

1. Add the marketplace and install Pulse:
   ```bash
   codex plugin marketplace add pssah4/pulse
   codex plugin add pulse@pssah4-skills
   ```

2. Trust the hooks. Codex runs a plugin's hooks only after you have reviewed them: start `codex` in your project. If you are not signed in yet, Codex asks you to sign in first; the CLI and the IDE extension share one sign-in. In a folder it has not seen, it then asks "Trust this folder?"; then it shows "Hooks need review": pick "Trust all and continue", or "Review hooks" to read each one (their source is `Plugin - pulse@pssah4-skills`). Later, `/hooks` shows the same list, and `t` trusts all. The IDE extension has no `/hooks`: open its settings, go to the Hooks page, and under **From Plugins** click **Trust** on each hook of `pulse@pssah4-skills`; the page trusts one hook per click, and Pulse needs them all. Codex asks again only when an update changes them. Until you trust them, `pulse status`, the map, and `pulse go` say `Codex hooks not trusted: run /hooks in Codex` in a project whose agents include Codex.

3. Put the `pulse` command on your PATH:
   ```bash
   P=${CODEX_HOME:-~/.codex}/plugins/cache/pssah4-skills/pulse
   "$P/$(ls "$P" | sort -V | tail -1)/bin/pulse" setup --cli
   ```
   The second line runs the newest version folder in the cache. This writes `~/.local/bin/pulse`, a short script that runs the Pulse of the agent that calls it: a Codex session its Codex copy, a Claude Code session its Claude Code copy, and your own terminal the newest of both. An update needs no new setup. If its report says `"on_path": false`, add `export PATH="$HOME/.local/bin:$PATH"` to your shell profile (`~/.zshrc` for zsh; for bash, `~/.bash_profile` on macOS and `~/.bashrc` on Linux) and open a new terminal.

4. Optional: let Codex run `pulse` outside its sandbox without asking. The sandbox has no network access, so otherwise every `pulse` command that reads or writes the board on GitHub asks you first. In every mode, Full access included, Codex refuses the levers of a person ("blocked by policy"): `approve` and `auto` with a gate, a handover with `release --take` or `claim --take`, `pulse -- <command>`, `gh pr merge` and `gh pr ready`, and `gh issue edit`, `close`, and `reopen`: run them in your own terminal. A prefix rule sees only how a command starts, so `gh -R o/r pr merge 5`, `env gh pr merge 5`, or a full path pass it; the Pulse guard catches those once you trust the Pulse hooks. `pulse` takes `--take` only right after the command, where a rule sees it, so every other `claim` and `release` runs without asking. The rules do not change with a Pulse update; when the changelog names a change to them, update Pulse in Codex too, then run `pulse setup --codex-rules` again. It writes no rules while Codex runs an older Pulse than the copy that writes them. A rule matches a plain `pulse ...` command: a pipeline or a redirection, such as `pulse status --json | head`, runs inside the sandbox, where `.git` is read-only and GitHub is out of reach. The full path works before your PATH has the command:
   ```bash
   ~/.local/bin/pulse setup --codex-rules
   ```

5. Restart Codex. In the IDE extension, start a new chat; if you just added `~/.local/bin` to your PATH, quit VS Code and open it again instead: a new chat keeps the PATH VS Code started with, and without `pulse` on it the Pulse hooks point the agent at the full path of the plugin copy, which the rules of step 4 do not match, so Codex asks before every `pulse` command.

Update with the two lines below, then start a new chat in the IDE extension or restart Codex: the update deletes the old version folder, and a running session still points its skills and hooks there. When Codex asks, trust the Pulse hooks again: it asks after an update that changes them. A running live map restarts itself with the new Pulse. `pulse setup --anchors` refreshes the Pulse block of a project whose text changed, and moves a block an older Pulse wrote into `CLAUDE.md` to `AGENTS.md`.

```bash
codex plugin marketplace upgrade pssah4-skills
codex plugin add pulse@pssah4-skills
```

Uninstall. First run `pulse setup --remove` in each project that uses Pulse: it takes out the anchor blocks and the `@AGENTS.md` line it set in `CLAUDE.md`, which nothing removes afterwards, and a git hook an older Pulse installed. In VS Code, also delete the task "Pulse map" from the project's `.vscode/tasks.json` if setup added it; it runs `pulse map` each time the folder opens. Then the lines below (skip `--cli` if Pulse stays installed in Claude Code):

```bash
pulse setup --remove --cli --codex-rules
codex plugin remove pulse@pssah4-skills
codex plugin marketplace remove pssah4-skills
```

Codex keeps your trust of the Pulse hooks in `~/.codex/config.toml` (`$CODEX_HOME/config.toml` when you set `CODEX_HOME`), as tables named `[hooks.state."pulse@pssah4-skills:..."]`. Delete them if a later install should ask you again.

## Manual (Codex without the plugin)

If the plugin is installed, run its uninstall steps first. Without the plugin there are no hooks: the rules come from your global `AGENTS.md`.

1. Clone Pulse:
   ```bash
   git clone https://github.com/pssah4/pulse.git ~/.codex/pulse
   ```

2. Link the skills:
   ```bash
   mkdir -p ~/.agents/skills
   ln -s ~/.codex/pulse/skills ~/.agents/skills/pulse
   ```

3. Put the `pulse` command on your PATH:
   ```bash
   mkdir -p ~/.local/bin
   ln -s ~/.codex/pulse/bin/pulse ~/.local/bin/pulse
   ```

4. Load the rules in every session. Codex reads its global `AGENTS.md` in `$CODEX_HOME` when you set it, else in `~/.codex`. Without one yet:
   ```bash
   ln -s ~/.codex/pulse/hooks/rules.md "${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
   ```
   With one, add a line to it: `Follow the Pulse rules in ~/.codex/pulse/hooks/rules.md.`

5. Restart Codex, and check the command with `pulse --help`: the skills run `pulse` from your PATH. On `command not found`, put `~/.local/bin` on your PATH as in step 3 of the plugin. Step 4 of the plugin works here too.

Update:

```bash
git -C ~/.codex/pulse pull
```

Uninstall. First run `pulse setup --remove` in each project that uses Pulse, and remove the Codex rules while the clone is still there. The last two lines delete the global `AGENTS.md` only if it is the link from step 4; if you added the Pulse line to your own `AGENTS.md`, take that line out by hand:

```bash
pulse setup --remove --codex-rules
rm ~/.agents/skills/pulse ~/.local/bin/pulse
rm -rf ~/.codex/pulse
A="${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
[ "$(readlink "$A")" = "$HOME/.codex/pulse/hooks/rules.md" ] && rm "$A"
```

Afterwards no `pulse` command is left in `~/.local/bin`: if Pulse stays installed in Claude Code, run the `setup --cli` line of its [installation](https://pssah4.github.io/pulse/tutorials/installation#terminal) again.

## Verify

```bash
pulse --help
```

In a new Codex session, ask "where does the work stand?". The `pulse` skill answers, names the next step, and lists the Pulse commands. Codex names the skills `pulse:pulse`, `pulse:pulse-ba`, and so on: call one as `$pulse:pulse-ba`, or pick it from a list: `/skills` > **List skills** in the CLI, or as soon as you type `$`, by the names `pulse-ba (pulse)` and so on; in the IDE extension, type `/` in the prompt box and look in the **Skills** group.

## What differs from Claude Code

- `pulse go` runs Codex headless when `agent` in `.pulse/config.toml` names it (`codex`, or `claude:2,codex:2`), one agent per ready item, the same way it runs Claude Code. Codex runs there without network, so an item whose spec tests need a server on localhost goes to Claude. `pulse go` commits what Codex leaves uncommitted.
- A claim belongs to the Codex thread that made it; another Codex or Claude Code session is refused for that item.
- Board commands such as `pulse status` and `claim` talk to GitHub, which the Codex sandbox blocks: approve them when Codex asks, or run `pulse setup --codex-rules` once (`pulse setup --remove --codex-rules` takes it back). With the rules, Codex refuses `approve`, `auto` with a gate, `release --take`, `claim --take`, `gh pr merge`, and `gh pr ready` in every mode: a person runs them in their own terminal. A rule sees only how a command starts, so `gh -R o/r pr merge 5` or `env gh ...` pass it; the Pulse guard catches those once the hooks are trusted.
- Besides the levers above, the rules cover `pulse` only. The skills also create branches, commit, and push; the sandbox keeps `.git` read-only and has no network, so Codex asks before each of these git commands. Approve them when it asks.
