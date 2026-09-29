"""The lever guard (FEAT-03-01): whether a command of an agent session pulls a person's lever.

The PreToolUse hook asks verdict() before every shell, Monitor, and MCP call of a session and its
subagents. It reads the command only, without network; the hook passes the base and default branch
and the command's directory, and only a push that names no branch costs a git call. Text sent into
another terminal (Herdr, tmux, osascript) is checked like a command, and no agent without this guard
starts in a pane. Nothing goes into the pane of a live map, which runs as the person, and no pulse map
goes into another terminal (FR-10 of #121): a pane that map-pane names, and while a map of this user
runs, any pane whose processes hold one, asked of Herdr or tmux and ps; a pane it cannot resolve then
counts as a map. Nowhere starts a claude with every hook or the Pulse plugin off or an opencode run, and no shell
write, rm, or truncate takes mode in .pulse/config.toml away from on, read from the command's text (#112). It
stops a lever pulled in the open; a script file, a program of the agent's own, or a token read out of gh passes
(Analysis 5.8).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import stat
import subprocess
import time

REASON = ("Gate levers belong to a person or to their own auto switch. Tell the person which gate waits: "
          "a in the Pulse map, or pulse approve in their terminal.")
PULSE = re.compile(r"\bpulse[ \t]+(?:--[ \t]+)?(?:approve|go|done|auto(?:[ \t]+[\w=.:-]+){0,4}?[ \t]+(?:on|off)|"
                   r"claim[ \t]+--take|release[ \t]+--take)(?![\w.])")      # quoted too, in comments and bodies
RISKY = re.compile(r"\b(?:pulse|gh|herdr|tmux|osascript)\b|\bgit\s+push\b")   # what an unreadable command may not name
MARKS = re.compile(r"<!-- pulse:|Plan-ok|plan ok at|merge ok at")
MARKERS = {"PULSE_HOLDER", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"}
QUOTED = re.compile(r"'([^']*)'|\"((?:[^\"\\]|\\.)*)\"")
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?[ \t]*(?:'([^'\n]+)'|\"([^\"\n]+)\"|\\?([\w.-]+))")
CAT = re.compile(r"\$\([ \t]*cat[ \t]+<<-?[ \t]*(['\"]?)([\w.-]+)\1[ \t]*\n(.*?)\n[ \t]*\2[ \t]*\n?[ \t]*\)", re.S)
TMUX_SEP = "\x1e"                                       # a ; for tmux, which the shell leaves in the words
SEP = set(";&|()\n")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
WRAPPERS = {"env", "command", "sudo", "xargs", "exec", "nohup", "time", "timeout", "builtin", "nice"}
ISSUE = {"close", "reopen", "edit", "pin", "unpin", "delete", "transfer", "lock"}
READS = {"view", "list", "status", "diff", "checks", "watch", "download"}
BODIES = {("issue", "comment"), ("issue", "create"), ("pr", "create"), ("pr", "comment"), ("pr", "edit"),
          ("pr", "review")}                           # the gh writes that take --body and --body-file
SUBST = re.compile(r"\$\(|`")                        # a command substitution: text the guard cannot see
ENTER = {"Enter", "C-m", "KPEnter"}
HOOKS_OFF = re.compile(r"disableAllHooks\W*(?!false)\w")          # settings that are no JSON: by their text
MODE = re.compile(r"[\"']?\bmode[\"']?\s*=\s*[\"']?([\w-]*)")         # mode = "on", also a quoted key
CONFIG = re.compile(r"(?:^|[\\/])\.pulse(?:[\\/]config\.toml)?$", re.I)    # the config, or the directory it is in
IN_PULSE = re.compile(r"(?:^|[\\/])\.pulse(?:[\\/]|$)", re.I)
GLOB = re.compile(r"[*?[{]")
# ponytail: agent CLIs without the Pulse guard, by the name they start with (Herdr's kinds among them); a
# renamed binary, a package runner (npx), or a new agent passes until it is named here
AGENTS = {"opencode", "gemini", "pi", "aider", "amp", "goose", "cursor-agent", "qwen", "crush", "copilot", "cursor",
          "devin", "cline", "droid", "kimi", "kiro", "grok", "kilo", "qodercli", "letta", "hermes"}
TMUX = {"send-keys": "tNc", "send": "tNc", "new-window": "ceFnt", "neww": "ceFnt", "split-window": "ceFlpt",
        "splitw": "ceFlpt", "new-session": "cefFnstxy", "new": "cefFnstxy", "run-shell": "cdt", "run": "cdt",
        "respawn-pane": "cet", "respawnp": "cet", "respawn-window": "cet", "respawnw": "cet",
        "display-popup": "bcdehsStTwxy", "popup": "bcdehsStTwxy"}         # the letters that take a value


class _Ctx:
    """What a command line runs in: the base branches, its directory (a path, a function that finds it,
    None when nobody knows, False when another guarded agent runs it), whether the chain moved git to
    another repository (GIT_DIR, GIT_WORK_TREE), the branch a checkout or switch of the chain goes to
    ("" none, None one it cannot name, ("check", name) a word that may be a branch), text for another
    terminal, the panes live maps run in, and the text and heredoc bodies of the current level."""

    def __init__(self, bases, cwd, pane=False, maps=frozenset(), seen=None, said=None):
        self.bases, self._cwd, self.pane, self.maps, self.raw, self.bodies = bases, cwd, pane, maps, "", []
        self.moved, self.branch = False, ""
        self.feed = []                                  # what the current command reads: its heredocs, None unknown
        self.seen = {} if seen is None else seen        # lookups, once per verdict at every level
        self.said = [] if said is None else said        # why a map pane was refused, for the verdict

    def into(self, cwd=None, pane=True):
        """The context of text sent into another terminal (cwd None) or to another guarded agent (False)."""
        return _Ctx(self.bases, cwd, pane, self.maps, self.seen, self.said)

    def lookup(self, ask, *where):
        """ask(*where), once per verdict: a line of pushes costs one git call per directory."""
        if (ask, where) not in self.seen:
            self.seen[ask, where] = ask(*where)
        return self.seen[ask, where]

    def where(self):
        if callable(self._cwd):
            self._cwd = self._cwd()
        return self._cwd

    def chdir(self, args, prog):
        args = [a for a in args if a not in ("-L", "-P", "-e", "-@", "--")]
        target = os.path.expanduser(args[0] if args else "~")
        if prog == "popd" or target.startswith(("-", "+")) or "$" in target or "`" in target:
            self._cwd = None                            # a directory the guard cannot name
        elif os.path.isabs(target):
            self._cwd = target
        else:
            base = self.where()
            self._cwd = os.path.join(base, target) if base else None
        if self.branch != "":
            self.branch = None                          # a checkout before, in which repository?


PWSH_JOIN = re.compile(r"`\r?\n")                 # PowerShell joins a line that ends in a backtick


def verdict(tool, tool_input, base, default, cwd=".", maps=()) -> str:
    """REASON when the call pulls a person's lever, else "". cwd is the command's directory, or a function
    that finds it, None when it is not known; maps are the panes live maps run in (.git/pulse/map-pane). A
    command it cannot take apart, or a check that fails, is denied when it names a lever's tool (FR-08)."""
    try:
        command = tool_input.get("command")             # Bash, PowerShell, Monitor
        if tool.startswith("mcp__"):                    # GitHub tools of an MCP server: only reads
            words = re.split(r"[_-]", tool.split("__")[-1].lower())
            if "github" in tool.lower() and words[0] not in ("get", "list", "search") and words[-1] != "read":
                return REASON
            command = next((tool_input[k] for k in ("command", "cmd") if isinstance(tool_input.get(k), str)), "")
        if not isinstance(command, str):
            raise TypeError("no command")
        if tool == "PowerShell":                        # its line continuation: a backtick at the end of a line
            command = PWSH_JOIN.sub("", command)
        ctx = _Ctx({base, default} - {None, ""}, cwd, maps=frozenset(maps))
        ctx.seen["until"] = time.monotonic() + LOOKUPS      # every lookup of a live map's pane, within the hook's 5 s
        ctx.seen["whole"] = command                     # the line a write of gh stands in (#124)
        return (ctx.said[0] if ctx.said else REASON) if _denied(command, ctx, 0, True) else ""
    except Exception:
        raw = next((tool_input[k] for k in ("command", "cmd") if k in tool_input), tool_input) \
            if isinstance(tool_input, dict) else tool_input
        text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
        return REASON if RISKY.search(text) else ""


def _denied(text, ctx, depth, strict):
    """Whether text, a command line, pulls a lever. strict: text the guard cannot take apart raises; else
    (text for a pane, a prompt) it splits at blanks."""
    if depth > 5:
        raise ValueError("nested too deep")
    text = _prepare(text)
    raw, bodies, feed = ctx.raw, ctx.bodies, ctx.feed
    main, docs = _heredocs(text)
    ctx.raw, ctx.bodies = text, [body for _, body in docs]
    try:
        if PULSE.search(text) or any(_feeds(head, body, ctx, depth) for head, body in docs):
            return True
        main, subs = _scan(main)
        if any(_denied(sub, ctx, depth + 1, False) for sub in subs):
            return True
        io = []
        for cmd in _commands(main, strict, io):
            ctx.feed = _stdin(io, ctx.bodies)
            if _redirected(cmd, io, ctx):
                return True
            n = next((i for i, w in enumerate(cmd) if not re.match(r"\w+=", w)), len(cmd))
            prog = _name(cmd[n]) if n < len(cmd) else ""
            if any(re.fullmatch(r"(\w+)=", w) and w[:-1] in MARKERS for w in cmd) or ctx.pane and prog in AGENTS:
                return True                             # a blanked marker; an agent without the guard in a pane
            if prog in ("cd", "pushd", "popd"):
                ctx.chdir(cmd[n + 1:], prog)
            if any(w.startswith(("GIT_DIR=", "GIT_WORK_TREE=")) for w in cmd):
                ctx.moved = True
            progs, names, ends, last = _programs(cmd, n), [_name(w) for w in cmd], [0] * len(cmd), {}
            for i in reversed(range(len(cmd))):         # a program's words end where its name comes again:
                ends[i], last[names[i]] = last.get(names[i], len(cmd)), i      # linear, however long the line
            for i, name in enumerate(names):            # env, command, sudo, xargs, a path: the program anywhere
                check, args = CHECKS.get(name), cmd[i + 1:ends[i]]
                if check and (check(args, ctx, depth, i in progs) if name in SHELLS else check(args, ctx, depth)):
                    return True
        return False
    finally:
        ctx.raw, ctx.bodies, ctx.feed = raw, bodies, feed


def _name(word):
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _programs(cmd, n):
    """Where cmd names its program: at n, and after a wrapper such as env, sudo, xargs, or timeout."""
    out, i = {n}, n
    while i < len(cmd) and _name(cmd[i]) in WRAPPERS:
        wrapper, i = _name(cmd[i]), i + 1
        while i < len(cmd) and (cmd[i].startswith("-") or re.match(r"\w+=", cmd[i])):
            i += 1
        i += wrapper == "timeout" and i < len(cmd)      # its duration
        out.add(i)
    return out


def _prepare(text):
    """The text as the shell reads it: line continuations joined, $'...' decoded, a ; for tmux kept as a word
    of its own, and each `$(cat <<EOF ... EOF)` replaced by its body, the text it hands on."""
    text = re.sub(r"\\\r?\n", "", text)
    text = re.sub(r"\$'((?:[^'\\]|\\.)*)'", lambda m: "'" + re.sub(
        r"\\(.)", lambda e: {"n": "\n", "t": "\t", "'": "'\\''"}.get(e.group(1), e.group(1)), m.group(1)) + "'", text)
    text = re.sub(r"\\;|';'|\";\"", f" {TMUX_SEP} ", text)

    def body(m):
        inside = re.sub(r'([\\"$`])', r"\\\1", m.group(3))
        return inside if _quote_at(text, m.start()) == '"' else f'"{inside}"'
    return CAT.sub(body, text)


def _quote_at(text, pos):
    """The quote the shell is in at pos: "'", '"', or ""."""
    quote, i = "", 0
    while i < pos:
        c = text[i]
        if c == "\\" and quote != "'":
            i += 1
        elif c in "'\"" and quote in ("", c):
            quote = "" if quote else c
        i += 1
    return quote


def _heredocs(text):
    """text with every heredoc body cut out, and each body with the command before its <<."""
    out, docs, pos = [], [], 0
    for m in HEREDOC.finditer(text):
        eol = text.find("\n", m.end())
        if m.start() < pos or eol < 0:
            continue
        delim = m.group(1) or m.group(2) or m.group(3)
        end = re.compile(rf"^[ \t]*{re.escape(delim)}[ \t]*$", re.M).search(text, eol + 1)
        if not end:
            continue
        out.append(text[pos:eol + 1])
        docs.append((text[max(text.rfind(c, 0, m.start()) for c in "\n;|&(") + 1:m.start()],
                     text[eol + 1:end.start()]))
        pos = end.start()
    return "".join(out) + text[pos:], docs


def _feeds(head, body, ctx, depth):
    """Whether a heredoc body pulls a lever where it goes: a shell or eval runs it, osascript types its
    strings into a terminal, tmux load-buffer pastes it into one. Any other body is data, for PULSE only."""
    words = head.split()
    prog = _name(next((w for w in words if not re.match(r"\w+=", w)), ""))
    pane = ctx.into()
    if prog in SHELLS or prog == "eval":
        return _denied(body, ctx, depth + 1, False)
    if prog == "osascript":
        return _keys_typed(body, ctx) or any(_denied(a or b, pane, depth + 1, False) for a, b in QUOTED.findall(body))
    return prog == "tmux" and "load-buffer" in words and _denied(body, pane, depth + 1, False)


def _scan(text):
    """text without its comments, and its command substitutions: $(...) and `...` outside single quotes."""
    out, subs, i, n, quote = [], [], 0, len(text), ""
    while i < n:
        c = text[i]
        if c == "\\" and quote != "'":
            out.append(text[i:i + 2])
            i += 2
            continue
        if not quote and c == "#" and (i == 0 or text[i - 1] in " \t\n;&|("):
            j = text.find("\n", i)                      # a comment, up to its line end
            i = n if j < 0 else j
            continue
        if quote != "'" and (text.startswith("$(", i) or c == "`"):
            if c == "`":
                j = text.find("`", i + 1)
                j = n if j < 0 else j + 1
                subs.append(text[i + 1:j - 1])
            else:
                level, j = 1, i + 2
                while j < n and level:
                    level += {"(": 1, ")": -1}.get(text[j], 0)
                    j += 1
                subs.append(text[i + 2:j - 1])
            out.append(text[i:j])
            i = j
            continue
        if c in "'\"" and quote in ("", c):
            quote = "" if quote else c
        out.append(c)
        i += 1
    return "".join(out), subs


def _commands(text, strict, io):
    """The simple commands of text, cut at ; & | ( ) and line ends, each as its words, without redirections:
    an operator of < > &, the fd number before it, and its target. io holds the current command's redirections as
    (operator, target), a heredoc as ("<<", its number in the text), and ("|", "") when a pipe feeds it."""
    try:
        lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>\n")
        lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
        words = list(lex)
    except ValueError:
        if strict:
            raise
        words = re.findall(r"[;&|()<>\n]+|[^\s;&|()<>]+", text)
    cmd, target, heredocs = [], "", 0
    io.clear()
    for w in words:
        if w and set(w) <= SEP:
            if cmd or io:
                yield cmd
            cmd, target = [], ""
            io[:] = [("|", "")] if "|" in w and "||" not in w or w == "(" and ("|", "") in io else []
        elif target:
            io.append((target, heredocs if target == "<<" else w))
            heredocs += target == "<<"
            target = ""
        elif w and set(w) <= set("<>&|") and set(w) & set("<>"):
            if cmd and cmd[-1].isdigit():
                cmd.pop()
            target = w
        else:
            cmd.append(w)
    if cmd or io:
        yield cmd


def _flag(args, longs, shorts, takes="", opt="", long_takes=(), prefix=False):
    """Whether a flag is set in args, the last spelling winning: a long name (--draft, --draft=false; with
    prefix also a start of it, as git takes --force-w) or a letter of a short cluster (-d, -fd, -d=false). A
    cluster stops at a letter of takes, whose value is the rest of the word or the next word, or of opt,
    whose value can only follow in the word; a long option of long_takes has its value in the next word."""
    on, skip = False, False
    for a in args:
        if skip:
            skip = False
        elif a.startswith("--"):
            name, eq, value = a.partition("=")
            if name in long_takes and not eq:
                skip = True
            elif name in longs or prefix and len(name) > 3 and any(long.startswith(name) for long in longs):
                on = not eq or value.lower() not in ("false", "0")
        elif a.startswith("-") and a[1:2].isalpha():   # "- a list item" is a value, no cluster
            for j, c in enumerate(a[1:], 2):
                if c in shorts:
                    on = a[j:j + 1] != "=" or a[j + 1:].lower() not in ("false", "0")
                    if a[j:j + 1] == "=":
                        break
                elif c in takes:
                    skip = j == len(a)
                    break
                elif c in opt:
                    break
    return on


def _values(args, long, short=""):
    """The values of an option in each spelling: --label x, --label=x, and with a short name -l x, -lx."""
    out = []
    for i, a in enumerate(args):
        if a == long or short and a == "-" + short:
            out.append(args[i + 1] if i + 1 < len(args) else "")
        elif a.startswith(long + "="):
            out.append(a.split("=", 1)[1])
        elif short and a.startswith("-" + short) and not a.startswith("--"):
            out.append(a[2:].lstrip("="))
    return out


def _getopt(args, takes):
    """{letter: value} of the options before the first word, as getopt reads them: -lt %3, -t%3, -t %3."""
    got, i = {}, 0
    while i < len(args) and args[i].startswith("-") and args[i] != "-":
        a, i = args[i], i + 1
        if a == "--":
            break
        for j, c in enumerate(a[1:], 2):
            if c in takes:
                got[c] = a[j:] if j < len(a) else (args[i] if i < len(args) else "")
                i += j == len(a)
                break
            got[c] = ""
    return got


def _words(args, takes):
    """The words after the options, as getopt reads them; a letter of takes has a value."""
    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] != "-":
        a, i = args[i], i + 1
        if a == "--":
            break
        for j, c in enumerate(a[1:], 2):
            if c in takes:
                i += j == len(a)
                break
    return args[i:]


def _gh(args, ctx, depth):
    kept, skip = [], False                              # -R and --repo stand anywhere (Analysis 5.8)
    for a in args:
        if skip:
            skip = False
        elif a in ("-R", "--repo"):
            skip = True
        elif not a.startswith(("--repo=", "-R")):
            kept.append(a)
    words = [a for a in kept if not a.startswith("-")] + ["", ""]
    group, verb = words[0], words[1]
    verb = "create" if verb == "new" else verb          # gh's alias of create
    if group == "api":
        return _api_writes(kept[kept.index("api") + 1:])
    if group == "auth":                                 # a token read out, or shown
        return verb == "token" or verb == "status" and _flag(kept, ("--show-token",), "t", "h")
    if (group, verb) in (("pr", "merge"), ("pr", "ready"), ("repo", "edit")) or \
            group == "issue" and verb in ISSUE or group == "label" and verb in ("create", "edit", "delete", "clone"):
        return True
    if (group, verb) == ("pr", "review") and _flag(kept, ("--approve",), "a", "bF", long_takes=("--body", "--body-file")):
        return True
    if (group, verb) == ("pr", "create") and not _flag(
            kept, ("--draft",), "d", "aBbFHlmprtT", long_takes=(
                "--title", "--body", "--base", "--head", "--label", "--assignee", "--reviewer", "--milestone",
                "--project", "--body-file", "--template", "--recover")):
        return True
    if (group, verb) == ("issue", "create") and (
            any(v.strip().lower().startswith("pulse:") for val in _values(kept, "--label", "l") for v in val.split(","))
            or any(v.strip().lower() == "pulse auto mode" for v in _values(kept, "--title", "t"))):
        return True
    if verb in READS or group in ("search", "browse", "status"):
        return False
    # a mark anywhere in the line: a heredoc, a here-string, or a pipe may hand it on as the body (#124)
    if any(MARKS.search(text) for text in (ctx.raw, ctx.seen.get("whole", ""), *ctx.bodies)):
        return True
    return (group, verb) in BODIES and _hidden(kept, ctx)


def _hidden(args, ctx):
    """Whether the body of a write of gh may hold a mark the guard cannot see (#124 fix round 1): a command
    substitution in --body; a --body-file with one, that the line names twice (it may write it first), that is no
    regular file the guard can read, or that holds a mark; stdin that no heredoc, here-string, echo, or printf
    of the line feeds, or with a command substitution in the line or in a heredoc the shell expands.
    ponytail: a variable ($B) set from a file earlier in the line passes; the substitution that set it does not
    reach the body."""
    whole, line = ctx.seen.get("whole", ctx.raw), _heredocs(ctx.raw)[0]
    subs = [s for s in _scan(line)[1] if s.strip()]      # outside single quotes: backticks there are text
    if any(s in v for v in _values(args, "--body", "b") for s in subs):
        return True
    for word in _values(args, "--body-file", "F"):
        if word == "-":
            fed = ctx.bodies or "<<<" in line or re.search(r"\b(?:echo|printf)\b[^|;&\n]*\|", line)
            bare = any(m.group(3) and "\\" not in m.group(0) for m in HEREDOC.finditer(ctx.raw))
            if not fed or subs or bare and any(SUBST.search(b) for b in ctx.bodies):
                return True
            continue
        path = None if any(s in word for s in subs) or whole.count(word) > 1 else _path(word, ctx)
        text = _read(path) if path else None
        if text is None or MARKS.search(text):
            return True
    return False


def _api_writes(args):
    """gh api with a method other than GET, or with a field or an input, which makes it a POST."""
    i = 0
    while i < len(args):
        a, i = args[i], i + 1
        if a.startswith("--"):
            name, eq, value = a.partition("=")
            if name in ("--field", "--raw-field", "--input"):
                return True
            if name == "--method":
                if not eq:
                    value, i = (args[i] if i < len(args) else ""), i + 1
                if value.upper() != "GET":
                    return True
        elif a.startswith("-"):
            for j, c in enumerate(a[1:], 2):
                if c in "fF":
                    return True
                if c in "XHqtp":                        # a value: the rest of the word, else the next word
                    value = a[j:].lstrip("=")
                    if not value:
                        value, i = (args[i] if i < len(args) else ""), i + 1
                    if c == "X" and value.upper() != "GET":
                        return True
                    break
    return False


def _git(args, ctx, depth):
    i, where, moved, hooks_off = 0, [], ctx.moved, False
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        value = args[i + 1] if i + 1 < len(args) and a in ("-c", "--config-env") else a[2:] if a.startswith("-c") else ""
        hooks_off = hooks_off or value.lower().startswith("core.hookspath")      # the hooks of --no-verify
        if a == "-C" and i + 1 < len(args):
            where.append(args[i + 1])
        moved = moved or a.startswith(("--git-dir", "--work-tree"))
        i += 2 if a in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env") else 1
    sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
    if sub in ("checkout", "switch"):                   # the chain goes on in another branch
        ctx.branch = _target(sub, rest, ctx.bases)
    if hooks_off and sub in ("commit", "push"):
        return True
    if sub == "commit":
        return _flag(rest, ("--no-verify",), "n", "mFCct", "Su", prefix=True, long_takes=(
            "--message", "--file", "--author", "--date", "--reuse-message", "--reedit-message", "--fixup", "--squash",
            "--template", "--cleanup", "--trailer", "--pathspec-from-file"))
    if sub != "push":
        return False
    if _flag(rest, ("--force", "--force-with-lease", "--mirror", "--no-verify", "--all", "--branches"), "fn", "o",
             long_takes=("--repo", "--receive-pack", "--exec", "--push-option"), prefix=True):
        return True
    words, skip = [], False
    for a in rest:
        if skip:
            skip = False
        elif a in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            skip = True
        elif not a.startswith("-"):
            words.append(a)
    dsts = []
    for spec in words[1:]:                              # words[0] is the remote
        dst = spec.split(":")[-1]
        dst = dst[11:] if dst.startswith("refs/heads/") else dst
        if spec.startswith("+") or "*" in dst or dst in ctx.bases:
            return True                                 # forced, every branch (as --all), or the base
        dsts.append("HEAD" if "$" in dst or "`" in dst else dst)       # a name the push computes
    if dsts and not set(dsts) & {"HEAD", "@"}:
        return False
    place = ctx.where()                                 # git push, git push origin HEAD: the checked-out branch
    if place is False:
        return False                                    # another guarded agent runs it and judges it there
    if moved or place is None or ctx.branch is None:
        return True                                     # another repository, a directory or a branch unknown
    here = os.path.join(place, *where)
    if isinstance(ctx.branch, tuple):                   # a checkout of a word: a branch, or a file or a commit
        ctx.branch = ctx.branch[1] if ctx.lookup(_is_branch, here, ctx.branch[1]) else None
        if ctx.branch is None:
            return True
    branch = ctx.branch or ctx.lookup(_branch, here)
    return not branch or branch in ctx.bases            # a branch git cannot name: denied (FR-08)


def _target(sub, rest, bases):
    """The branch a checkout or switch goes to: a name, ("check", name) for a checkout's word that may also be
    a file or a commit, or None when it names none. --track names the remote branch: its name counts."""
    made = ("-c", "-C", "--create", "--force-create") if sub == "switch" else ("-b", "-B", "--orphan")
    for i, a in enumerate(rest[:-1]):
        if a in made:
            return rest[i + 1]
    words = [a for a in rest if not a.startswith("-")]
    if not words or "--" in rest or sub == "switch" and {"--detach", "-d"} & set(rest):
        return None
    name = words[0].split("/", 1)[-1] if {"--track", "-t"} & set(rest) else words[0]
    return name if sub == "switch" or name in bases else ("check", name)


def _branch(where):
    """The checked-out branch in the directory where, else "" (git failed, or took too long)."""
    try:
        out = subprocess.run(["git", "-C", where, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                             text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _is_branch(where, name):
    """Whether name is a branch in the repository at where, here or on a remote (a checkout makes it one)."""
    try:
        out = subprocess.run(["git", "-C", where, "for-each-ref", "--format=%(refname)", f"refs/heads/{name}",
                              f"refs/remotes/*/{name}"], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(r == f"refs/heads/{name}" or r.startswith("refs/remotes/") and r.split("/", 3)[-1] == name
               for r in out.stdout.split())


MAP_REASON = "The Pulse map runs as a person: no agent sends it text or keys. Tell the person what to press."
LOCKED = ("The guard refuses it: a Pulse map is open: tmux input only to an absolute %N pane (send-keys or "
          "paste-buffer -t %N); list, show, capture, and display read freely. Tell the person what to press.")
MAP_CMD = re.compile(r"(?:run_module\('pulse'.*|(?:^|[\s/'\"])pulse['\"]?)\smap(?:\s|$)")
TYPES_KEYS = re.compile(r"keystroke|key\s*code", re.I)       # AppleScript and JXA, any application
PANE_ID = re.compile(r"%\d+")
HERDR_PANE = re.compile(r"w\d+:p\d+")
TMUX_ENV = re.compile(r"(?<![\w$])TMUX(?:_PANE)?=")
HERDR_ENV = re.compile(r"(?<![\w$])HERDR_\w*=")
LOOKUPS, TARGETS = 3.0, 4          # seconds for all lookups of one verdict, and panes it may ask about, while a map runs
INTO = {"send-keys": "tNc", "send": "tNc", "paste-buffer": "bst", "pasteb": "bst"}   # tmux commands that type
TMUX_READS = {"ls", "lsw", "lsp", "lsc", "lsb", "lsk", "lscm", "capture-pane", "capturep", "show", "showw", "showenv",
              "showb", "showmsgs", "showphist", "has-session", "has"}          # besides list-* and show-*


def _is_map(command):
    """Whether a command line of ps is a live map: pulse map, not pulse map --ensure."""
    return bool(MAP_CMD.search(command)) and "--ensure" not in command


def _procs():
    """{pid: (parent pid, uid, command)} of every process, from one ps; None when ps does not answer in time."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,uid=,command="], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=1).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    table = {}
    for line in out.splitlines():
        w = line.split(None, 3)
        if len(w) >= 3 and w[0].isdigit() and w[1].isdigit():
            table[int(w[0])] = (int(w[1]), w[2], w[3] if len(w) > 3 else "")
    return table


def _found(value, key=""):
    """(every number under a key that names a pid, every string under a key that names a pane), anywhere in an
    answer of Herdr."""
    if isinstance(value, dict):
        got = [_found(v, k) for k, v in value.items()]
    elif isinstance(value, list):
        got = [_found(v, key) for v in value]
    else:
        key = key.lower()
        return ([value] if isinstance(value, int) and not isinstance(value, bool) and "pid" in key else [],
                [value] if isinstance(value, str) and "pane" in key and HERDR_PANE.fullmatch(value) else [])
    return [p for g in got for p in g[0]], [p for g in got for p in g[1]]


def _herdr_json(*args, session=None, timeout=1.0):
    """What a herdr command answers as JSON, in session when one is named; None when it does not answer."""
    try:
        out = subprocess.run([os.environ.get("HERDR_BIN_PATH") or "herdr", *(["--session", session] if session else []),
                              *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _herdr_pids(target, session=None, timeout=1.0, agent=False):
    """The pids Herdr names for the processes of pane target, or of the pane an agent of that name runs in; None
    when it cannot say."""
    if agent:
        pids, panes = _found(_herdr_json("agent", "get", target, session=session, timeout=timeout / 2))
        if pids or not panes:
            return pids or None
        target, timeout = panes[0], timeout / 2
    return _found(_herdr_json("pane", "process-info", "--pane", target, session=session, timeout=timeout))[0] or None


def _tmux_pids(target, session=None, timeout=1.0, agent=False):
    """[the pid of the shell of tmux pane target, an absolute %N]; None when tmux cannot say."""
    try:
        out = subprocess.run(["tmux", "display-message", "-p", "-t", target, "#{pane_pid}"], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=timeout)
        return [int(out.stdout.strip())] if out.returncode == 0 and out.stdout.strip().isdigit() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _map_runs(ctx):
    """The process table while a live map of this user runs, else None: then no pane holds one. ps failing counts
    as a map (FR-08)."""
    table = ctx.lookup(_procs)
    if table is None:
        return {}
    me = str(os.getuid())
    return table if any(uid == me and _is_map(cmd) for _, uid, cmd in table.values()) else None


def _cannot_tell(target, ctx, why=""):
    ctx.said.append(f"The guard cannot tell whether {target} is a Pulse map{why}, and a map runs: no agent sends it "
                    "text or keys. Tell the person what to press.")
    return True


def _into_map(kind, target, ctx, session=None, agent=False, blind=False):
    """Whether input goes into the pane of a live map (FR-10): target in map-pane, or its label; else, while a map
    of this user runs, a pane whose processes hold one, or one the guard cannot resolve: blind (another machine, an
    environment the command sets), more than TARGETS panes in one verdict, none of LOOKUPS seconds left, or no
    answer. Without a live map nothing is asked."""
    if target and _map(target, ctx):
        ctx.said.append(MAP_REASON)
        return True
    table = _map_runs(ctx)
    if table is None:
        return False
    if blind or not table:
        return _cannot_tell(target, ctx)
    key = ("pane", kind, target, session)
    if key not in ctx.seen:
        asked = ctx.seen.setdefault("targets", set())
        asked.add(key)
        if len(asked) > TARGETS:
            ctx.said.append(f"The guard asks about {TARGETS} panes at most while a Pulse map runs, and this command "
                            f"names more than {TARGETS}: split it. Tell the person what to press into the map.")
            return True
        left = ctx.seen["until"] - time.monotonic()
        if left <= 0.05:
            return _cannot_tell(target, ctx, f" within {LOOKUPS:g} s")
        ctx.seen[key] = (_herdr_pids if kind == "herdr" else _tmux_pids)(target, session, min(1.0, left), agent)
    pids = ctx.seen[key]
    if not pids:
        return _cannot_tell(target, ctx)
    kids, me, todo, seen = {}, str(os.getuid()), list(pids), set()
    for pid, (parent, _, _) in table.items():
        kids.setdefault(parent, []).append(pid)
    while todo:                                          # the pane's processes and all they started
        pid = todo.pop()
        if pid in seen:
            continue
        seen.add(pid)
        uid, cmd = (table.get(pid) or (0, "", ""))[1:]
        if uid == me and _is_map(cmd):
            ctx.said.append(MAP_REASON)
            return True
        todo += kids.get(pid, [])
    return False


def _map(target, ctx):
    """Whether target names the pane of a live map without asking anyone: an id in map-pane, a tmux target that
    ends in one, or the label pulse map <repo> (FR-10)."""
    return target.startswith("pulse map") or any(target == m or target.endswith(("." + m, ":" + m)) for m in ctx.maps)


def _herdr(args, ctx, depth):
    """Herdr: text into a pane is checked like a command; nothing goes into a live map (FR-10); only agents with this
    guard start in a pane. --session goes to the lookup; another machine, or HERDR_* set in the command, blinds it."""
    i, session, blind = 0, None, bool(HERDR_ENV.search(ctx.raw))
    while i < len(args) and args[i].startswith("-"):   # --session, --machine, --remote: each with a value
        name, eq, value = args[i].partition("=")
        value = value if eq else (args[i + 1] if i + 1 < len(args) else "")
        session = value if name == "--session" else session
        blind = blind or name in ("--machine", "--remote")
        i += 1 if eq else 2
    group, verb = (args[i:i + 2] + ["", ""])[:2]
    rest = args[i + 2:]
    typed = (group, verb) in (("pane", "run"), ("pane", "send-text"), ("pane", "send-keys"))
    told = (group, verb) in (("agent", "prompt"), ("agent", "send-keys"))
    words = [w for w in rest if not w.startswith("-")]
    target = (words or ["?"])[0]
    if (typed or told) and _into_map("herdr", target, ctx, session, told and not HERDR_PANE.fullmatch(target), blind):
        return True                                     # the map runs as the person: a would approve
    if (group, verb) == ("agent", "start") and any(_into_map("herdr", p, ctx, session, False, blind)
                                                   for p in _values(rest, "--pane")):
        return True
    if typed:                                           # keys by name, spaces between: text for PULSE
        return _denied(" ".join(rest[1:]), ctx.into(), depth + 1, False)
    if told:                                            # to an agent that runs this guard itself
        return _denied(" ".join(w for w in rest[1:] if not w.startswith("--")), ctx.into(False, False), depth + 1,
                       False)
    if (group, verb) == ("agent", "start"):             # only agents that run this guard
        kinds = _values(rest, "--kind")
        return "--bare" in rest or not kinds or not set(kinds) <= {"claude", "codex"}
    return False


def _tmux_reads(name, opts):
    """Whether a tmux command only reads: list-*, show-*, capture-pane, has-session, and display-message without -I
    (which types into a pane) and with -t an absolute %N at most; none with a format that runs a shell (#())."""
    if any("#(" in o for o in opts):
        return False
    if name in ("display-message", "display"):
        o = _getopt(opts, "cdtF")
        return "I" not in o and (not o.get("t") or bool(PANE_ID.fullmatch(o["t"])))
    return name.startswith(("list-", "show-")) or name in TMUX_READS


def _tmux(args, ctx, depth):
    """tmux: text a command types is checked like a command; nothing goes into a live map (FR-10). While a map of
    this user runs only reads pass, and input into an absolute %N pane that holds no map; everything else is refused
    (LOCKED): other servers, other targets, hooks, bindings, aliases, shells, and TMUX set in the command."""
    pane, lead, i = ctx.into(), [], 0
    while i < len(args) and args[i].startswith("-"):
        lead.append(args[i])
        if args[i] == "-c":                             # tmux -c runs a shell command
            break
        i += 2 if args[i] in ("-L", "-S", "-f", "-T") else 1
    cmds, cmd = [], []
    for a in args[i:] if "-c" not in lead else []:     # tmux runs commands apart at a ; word
        if a in (";", TMUX_SEP):
            cmds, cmd = cmds + [cmd], []
        else:
            cmd.append(a)
    cmds = [c for c in cmds + [cmd] if c]
    for name, *opts in cmds:                            # the id map-pane names: no ps needed
        if name in INTO and _map(_getopt(opts, INTO[name]).get("t") or "", ctx):
            ctx.said.append(MAP_REASON)
            return True
    reads = not lead and not TMUX_ENV.search(ctx.raw) and all(_tmux_reads(name, opts) for name, *opts in cmds)
    if not reads and _map_runs(ctx) is not None:
        for name, *opts in cmds:
            o = _getopt(opts, INTO.get(name, ""))
            if lead or TMUX_ENV.search(ctx.raw) or not (_tmux_reads(name, opts) or name in INTO and "K" not in o
                                                        and PANE_ID.fullmatch(o.get("t", ""))):
                ctx.said.append(LOCKED)
                return True
        if not cmds and lead:
            ctx.said.append(LOCKED)
            return True
        if any(_into_map("tmux", _getopt(opts, INTO[name])["t"], ctx) for name, *opts in cmds if name in INTO):
            return True
    if "-c" in lead:
        return i + 1 < len(args) and _denied(args[i + 1], pane, depth + 1, False)
    for name, *opts in cmds:
        if name not in TMUX:
            continue
        words = _words(opts, TMUX[name])
        text = " ".join("\n" if k in ENTER else k for k in words) if name.startswith("send") else " ".join(words)
        if _denied(text, pane, depth + 1, False):
            return True
    return False


def _osascript(args, ctx, depth):
    """Each -e statement and each string in it (`do script "..."` types it into a terminal); without -e (a
    heredoc, a pipe) each string of the whole command. Keys a script types go to the window in front, which may be
    a live map: none while one runs, whatever application it names."""
    pane = ctx.into()
    scripts = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "-e"]
    strings = [a or b for s in scripts or [ctx.raw] for a, b in QUOTED.findall(s)]
    return _keys_typed(" ".join(scripts or [ctx.raw]), ctx) or any(_denied(s, pane, depth + 1, False)
                                                                   for s in scripts + strings)


def _keys_typed(script, ctx):
    """Whether a script types keys (keystroke, key code, keyCode) while a live map of this user runs."""
    if not TYPES_KEYS.search(script) or _map_runs(ctx) is None:
        return False
    ctx.said.append(MAP_REASON)
    return True


def _shell(args, ctx, depth, program=True):
    """bash -c, sh -c, zsh -c, and the like, with any options before (-euo pipefail, --rcfile f, --): its text
    is a command line of its own. A shell that is the program of its command and has no command or script
    reads its commands from stdin: the strings and heredocs of the chain."""
    i, run, stdin = 0, False, False
    while i < len(args) and args[i].startswith(("-", "+")) and args[i] not in ("-", "--"):
        a, i = args[i], i + 1
        if a.startswith("--"):
            i += a in ("--rcfile", "--init-file")
            continue
        run, stdin = run or "c" in a[1:], stdin or "s" in a[1:]
        i += sum(ch in "oO" for ch in a[1:])            # each o names an option
    i += i < len(args) and args[i] == "--"
    if run:
        return i < len(args) and _denied(args[i], ctx, depth + 1, True)
    return program and (stdin or i >= len(args) or args[i] == "-") and _fed(ctx, depth)


def _fed(ctx, depth):
    return any(_denied(t, ctx, depth + 1, False) for t in ctx.bodies + [a or b for a, b in QUOTED.findall(ctx.raw)])


def _pwsh(args, ctx, depth):
    """pwsh and powershell with -Command (-c, or any start of it): the rest is the command."""
    i = next((i for i, a in enumerate(args) if len(a) > 1 and "-command".startswith(a.lower())), None)
    return i is not None and _denied(PWSH_JOIN.sub("", " ".join(args[i + 1:])), ctx, depth + 1, True)


def _pulse(args, ctx, depth):
    """The command line of pulse itself, in any quoting or case, with the starts of options argparse takes: a
    person's levers."""
    args = [a.lower() for a in (args[1:] if args[:1] == ["--"] else args)] + ["", ""]
    sub, nxt = args[0], args[1]
    if ctx.pane and sub == "map":                       # a map in a terminal an agent types into (FR-10)
        return True
    if sub == "setup":                                  # Pulse off or out, and the guard with it
        for k, a in enumerate(args):
            name, eq, value = a.partition("=")
            if len(name) >= 4 and ("--remove".startswith(name) or "--mode".startswith(name) and
                                   (value if eq else args[k + 1]) == "off"):
                return True
    return sub in ("approve", "approve-plan", "go", "done") or sub == "auto" and bool({"on", "off"} & set(args)) or \
        (sub, nxt) in (("claim", "--take"), ("release", "--take"))


def _env(args, ctx, depth):
    """env that unsets a marker or clears the environment: the command line would take an agent for a person."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a, i = args[i], i + 1
        if a in ("-i", "--ignore-environment", "-"):
            return True
        if a in ("-u", "--unset"):
            name, i = (args[i] if i < len(args) else ""), i + 1
        elif a.startswith(("--unset=", "-u")):
            name = a.split("=", 1)[1] if a.startswith("--") else a[2:]
        else:
            i += a in ("-C", "--chdir", "-S", "--split-string", "-P")      # an option with its value
            continue
        if name in MARKERS:
            return True
    return False


def _path(word, ctx):
    """The path word names from the command's directory; None when that is unknown and word is relative."""
    word, place = os.path.expanduser(word), ctx.where()
    return os.path.join(place, word) if isinstance(place, str) else word if os.path.isabs(word) else None


def _read(path):
    """The first 64 KB of a regular file, else None: opened without blocking, so a fifo cannot hold the hook."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except (OSError, ValueError):
        return None
    try:
        return os.read(fd, 1 << 16).decode("utf-8", "replace") if stat.S_ISREG(os.fstat(fd).st_mode) else None
    finally:
        os.close(fd)


def _off(text):
    """Whether settings switch every hook or the Pulse plugin off; settings that are no JSON, by their text."""
    try:
        data = json.loads(text)
    except ValueError:
        return bool(HOOKS_OFF.search(text))
    plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
    return isinstance(data, dict) and (bool(data.get("disableAllHooks")) or isinstance(plugins, dict) and any(
        str(k).startswith("pulse@") and not v for k, v in plugins.items()))


def _claude(args, ctx, depth):
    """claude without this guard: --bare, or --settings that switch every hook or the Pulse plugin off, as JSON or
    in the file it names (FR-01 of #112). A file the guard cannot read, a value it cannot name ($, `), and a file the
    command names twice (it may write it first) are denied; a plain path that does not exist passes, claude refuses
    it. ponytail: --setting-sources without the source that enables the plugin passes, a known limit."""
    if "--bare" in args:
        return True
    for value in _values(args, "--settings"):
        text = value if value.lstrip().startswith("{") else None
        if text is None:
            word = os.path.expandvars(value)
            path = _path(word, ctx)
            if not path or "$" in word or "`" in word or ctx.raw.count(value) > 1:
                return True
            text = _read(path)
            if text is None and os.path.lexists(path):
                return True
        if text is not None and _off(text):
            return True
    return False


def _config(word, ctx):
    """Whether word names .pulse/config.toml or its directory: normalized, from the directory a cd of the chain went
    to, through a symlink where that directory is known; a glob in a word that names .pulse counts."""
    path = _path(word, ctx)
    for p in {word, path or word, os.path.realpath(path) if path and os.path.isabs(path) else word}:
        p = os.path.normpath(p)
        if CONFIG.search(p) or GLOB.search(word) and IN_PULSE.search(p):
            return True
    return False


def _written(text, whole):
    """Whether a command that writes .pulse/config.toml, whole or appended, leaves mode other than on, read from its
    words and heredocs only: it sets mode to another value, or writes a whole file without mode (FR-02 of #112)."""
    sets = MODE.findall(text)
    return any(v != "on" for v in sets) or whole and not sets


def _stdin(io, bodies):
    """What a command reads: its heredocs and here-strings; None when a pipe or a file (<) feeds it instead."""
    feed = [b for op, k in io if op == "<<" for b in bodies[k:k + 1]] + [w for op, w in io if op == "<<<"]
    return feed or (None if any(op in ("|", "<") for op, _ in io) else [])


def _redirected(cmd, io, ctx):
    """Whether a redirection of cmd writes .pulse/config.toml and leaves mode other than on, judged by the command's
    words and heredocs; what a pipe or a file feeds it is unknown."""
    return any(">" in op and _config(w, ctx) and (
        ctx.feed is None or _written(" ".join(cmd + ctx.feed), ">>" not in op)) for op, w in io)


def _touches(args, ctx):
    return any(_config(a, ctx) for a in args)


def _perl(args, ctx, depth):
    """perl -i on .pulse/config.toml, in any cluster: -pi, -i.bak, -0pi (-0 takes the digits after it)."""
    args = ["-" + a[1:].lstrip("0123456789") if re.match(r"-\d", a) else a for a in args]
    return _flag(args, (), "i", "eE") and _touches(args, ctx)


CHECKS = {"gh": _gh, "git": _git, "herdr": _herdr, "tmux": _tmux, "osascript": _osascript, "pulse": _pulse,
          **{shell: _shell for shell in SHELLS}, "pwsh": _pwsh, "powershell": _pwsh, "env": _env,
          "unset": lambda args, ctx, depth: bool(MARKERS & set(args)),
          "eval": lambda args, ctx, depth: _denied(" ".join(args), ctx, depth + 1, True),
          "claude": _claude, "opencode": lambda args, ctx, depth: "run" in args,
          "sed": lambda args, ctx, depth: _flag(args, ("--in-place",), "i", "efl", prefix=True) and _touches(args, ctx),
          "perl": _perl, **dict.fromkeys(("ex", "ed", "rm", "truncate"), lambda args, ctx, depth: _touches(args, ctx)),
          "tee": lambda args, ctx, depth: _touches(args, ctx) and (      # stdin from a pipe or a file: unknown
              not ctx.feed or _written(" ".join(ctx.feed), not _flag(args, ("--append",), "a")))}
