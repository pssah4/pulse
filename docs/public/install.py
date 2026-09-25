#!/usr/bin/env python3
"""Install or update Pulse for Claude Code and Codex: the steps of the installation page in one run.

    curl -fsSL https://pssah4.github.io/pulse/install.py | python3 -
    curl -fsSL https://pssah4.github.io/pulse/install.py | python3 - --yes
    curl -fsSL https://pssah4.github.io/pulse/install.py | python3 - --dry-run

It installs Pulse with every tool it finds (the claude and codex commands, or the binaries the
VS Code extensions bring) and puts the pulse command into ~/.local/bin. It asks before it adds a
line to your shell profile or writes the Codex rules (--yes answers yes, --no answers no, a run
without a terminal answers no), shows every command before it runs it, and removes nothing.
Trusting the Codex hooks, restarting your sessions, and /pulse-setup in each project stay with
you: the end of the run names them. The manual way is on the installation page.
Python 3.9 or newer, standard library only.
"""
import argparse
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

MARKET = "pssah4-skills"
PLUGIN = "pulse@pssah4-skills"
GUIDE = "https://pssah4.github.io/pulse/tutorials/installation"
OURS = re.compile(r"(^|[/:])pssah4/pulse(\.git)?/?$")        # github.com/pssah4/pulse, not pulse-dev
PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'
HOME = Path.home()


def say(text=""):
    print(text, flush=True)


def version(path):
    """Sort key of an extension or version folder: its numbers."""
    return tuple(int(n) for n in re.findall(r"\d+", str(path)))


def find(name, pattern):
    """(path, from the VS Code extension) of a tool: the command on PATH, else the newest bundled binary."""
    if shutil.which(name):
        return name, False
    bundled = sorted(glob.glob(str(HOME / pattern)), key=version)
    return (bundled[-1], True) if bundled else (None, False)


def config_dir(var, default):
    return Path(os.environ.get(var) or HOME / default)


def run(cmd, dry, capture=False):
    say("+ " + " ".join(shlex.quote(str(c)) for c in cmd))
    if dry:
        return 0, ""
    done = subprocess.run([str(c) for c in cmd], text=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE if capture else None)
    return done.returncode, done.stdout or ""


def ask(question, answer):
    """True on yes. answer: True (--yes), False (--no), None (ask on the terminal, if there is one)."""
    if answer is not None:
        say(f"{question} {'yes' if answer else 'no'}")
        return answer
    try:
        with open("/dev/tty", "r+") as tty:                  # stdin is the script when piped from curl
            tty.write(f"{question} [y/N] ")
            tty.flush()
            return tty.readline().strip().lower() in ("y", "yes", "j", "ja")
    except OSError:
        say(f"{question} no (no terminal to ask; run again with --yes to say yes)")
        return False


def conflict(tool, source):
    say(f"{tool}: the marketplace {MARKET} comes from {source}, not from Pulse. Left as it is.")
    say(f"  Remove it first (the optional step): {GUIDE}#coming-from-the-digital-innovation-agents-plugin")


def ours(source, override):
    return bool(source) and (source == override or OURS.search(source.strip()) is not None)


def claude(exe, source, override, dry):
    """Install or update Pulse in Claude Code; the CLI and the VS Code extension share it."""
    plugins = config_dir("CLAUDE_CONFIG_DIR", ".claude") / "plugins"
    try:
        entry = json.loads((plugins / "known_marketplaces.json").read_text()).get(MARKET)
    except (OSError, ValueError):
        entry = None
    if entry is None:
        steps = [["plugin", "marketplace", "add", source], ["plugin", "install", PLUGIN]]
    else:
        src = entry.get("source", {})
        where = src.get("url") or src.get("repo") or src.get("path") or ""
        if not ours(where, override):
            conflict("Claude Code", where)
            return False
        try:
            installed = PLUGIN in json.loads((plugins / "installed_plugins.json").read_text()).get("plugins", {})
        except (OSError, ValueError):
            installed = False
        steps = [["plugin", "marketplace", "update", MARKET], ["plugin", "update" if installed else "install", PLUGIN]]
    return all(run([exe, *s], dry)[0] == 0 for s in steps)


def codex(exe, source, override, dry):
    """Install or update Pulse in Codex; the CLI and the IDE extension share it."""
    try:
        text = (config_dir("CODEX_HOME", ".codex") / "config.toml").read_text()
    except OSError:
        text = ""
    block = re.search(rf"^\[marketplaces\.{MARKET}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if block is None:
        steps = [["plugin", "marketplace", "add", source], ["plugin", "add", PLUGIN]]
    else:
        where = (re.search(r'^source\s*=\s*"([^"]*)"', block.group(1), re.M) or [None, ""])[1]
        if not ours(where, override):
            conflict("Codex", where)
            return False
        git = re.search(r'^source_type\s*=\s*"git"', block.group(1), re.M)
        steps = ([["plugin", "marketplace", "upgrade", MARKET]] if git else []) + [["plugin", "add", PLUGIN]]
    return all(run([exe, *s], dry)[0] == 0 for s in steps)


def copy():
    """The newest cached Pulse: Claude Code's cache first, then Codex's, as the pulse command finds it."""
    for var, default in (("CLAUDE_CONFIG_DIR", ".claude"), ("CODEX_HOME", ".codex")):
        cache = config_dir(var, default) / "plugins/cache" / MARKET / "pulse"
        found = sorted((p for p in cache.glob("*/bin/pulse") if not (p.parents[1] / ".orphaned_at").exists()),
                       key=lambda p: version(p.parents[1].name))
        if found:
            return found[-1]
    return None


def profile():
    shell = os.path.basename(os.environ.get("SHELL", ""))
    if shell == "zsh":
        return HOME / ".zshrc"
    if shell == "bash":
        return HOME / (".bash_profile" if sys.platform == "darwin" else ".bashrc")
    return None


def add_line(line, why, answer, dry):
    """Add line to the shell profile once, on a yes; say what to do by hand otherwise."""
    rc = profile()
    if rc is None:
        say(f"Add this line to your shell profile ({why}): {line}")
        return
    if rc.exists() and line in rc.read_text():
        say(f"{rc} has the line already ({why}).")
        return
    if not ask(f"Add to {rc} ({why}): {line} ?", answer):
        say(f"  By hand: add the line to {rc}, then open a new terminal.")
        return
    say(f"+ append to {rc}: {line}")
    if not dry:
        with open(rc, "a") as f:
            f.write(f"\n# added by the Pulse installer\n{line}\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="install.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="answer yes to every question")
    p.add_argument("--no", action="store_true", help="answer no to every question")
    p.add_argument("--dry-run", action="store_true", help="show the commands, change nothing")
    args = p.parse_args(argv)
    answer = True if args.yes else False if args.no else None
    override = os.environ.get("PULSE_SOURCE", "")

    claude_exe, _ = find("claude", ".vscode*/extensions/anthropic.claude-code-*/resources/native-binary/claude")
    codex_exe, codex_bundled = find("codex", ".vscode*/extensions/openai.chatgpt-*/bin/*/codex")
    if not (claude_exe or codex_exe):
        say("Neither Claude Code nor Codex found. Install one, then run this again:")
        say("  Claude Code: curl -fsSL https://claude.ai/install.sh | bash   (or the VS Code extension)")
        say("  Codex: curl -fsSL https://chatgpt.com/codex/install.sh | sh   (or the codex VS Code extension)")
        return 1
    done = []
    if claude_exe:
        say(f"Claude Code: {claude_exe}")
        if claude(claude_exe, override or "https://github.com/pssah4/pulse.git", override, args.dry_run):
            done.append("Claude Code")
    if codex_exe:
        say(f"Codex: {codex_exe}")
        if codex(codex_exe, override or "pssah4/pulse", override, args.dry_run):
            done.append("Codex")
    if not done:
        say(f"Pulse is installed in no tool. The manual way: {GUIDE}")
        return 1

    pulse = copy()
    on_path = True
    if pulse is None and args.dry_run:
        say("+ <newest cached Pulse>/bin/pulse setup --cli")
    elif pulse is None:
        say(f"No cached Pulse found after the install; see {GUIDE}#terminal")
    else:
        rc, out = run([pulse, "setup", "--cli"], args.dry_run, capture=True)
        try:
            report = json.loads(out) if out.strip() else {}
        except ValueError:
            report = {}
        on_path = report.get("on_path", True)
        for change in report.get("changes", []):
            say(f"  {change.get('path')}: {change.get('status')}")
    if not on_path:
        add_line(PATH_LINE, "the pulse command", answer, args.dry_run)
    if "Codex" in done and codex_bundled:
        ext = Path(codex_exe).parents[3]
        root = "~/" + str(ext.relative_to(HOME)) if HOME in ext.parents else str(ext)
        add_line(f'codex() {{ "$(ls {root}/openai.chatgpt-*/bin/*/codex | sort -V | tail -1)" "$@"; }}',
                 "codex in every terminal", answer, args.dry_run)
    if "Codex" in done and pulse is not None:
        if ask("Let Codex run pulse outside its sandbox without asking (pulse setup --codex-rules)?", answer):
            run([pulse, "setup", "--codex-rules"], args.dry_run)

    say()
    tools = " and ".join(done)
    say(f"Dry run, nothing changed. Pulse would be installed in {tools}. Left for you after a real run:"
        if args.dry_run else f"Pulse is installed in {tools}. Left for you:")
    if "Codex" in done:
        say("  - Codex: trust the Pulse hooks. In the CLI, start codex in a project and pick")
        say("    Trust all and continue (later: /hooks in the CLI); in the IDE extension, click Trust")
        say("    on each Pulse hook on the Hooks page of its settings.")
    say("  - Restart: new Claude Code sessions, or reload the VS Code window (Developer: Reload Window);")
    say("    restart Codex; after a change to your PATH, quit VS Code and open it again.")
    say("  - In each project: /pulse-setup (in Codex $pulse:pulse-setup).")
    say(f"Details: {GUIDE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
