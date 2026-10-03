"""The settings of a project as the map shows and changes them (#182): each setting with where it comes from and what
it does, per harness the last session start the Pulse hooks proved in this clone, and a change of a setting as a
commit of its own on a pushed branch from the freshly fetched base, never in the working tree."""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import tempfile
import time
from pathlib import Path

from pulse import auto, config, ready, setup, state

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "pulse_hook.py"     # what a session start injects
LIMIT = 10000                   # characters of hook context Claude Code takes whole
HARNESSES = {"claude": "Claude Code", "codex": "Codex"}
WAY = {"claude": "start a Claude Code session in this clone with the Pulse plugin",
       "codex": "start a Codex session in this clone with the Pulse plugin and trust its hooks (/hooks in the CLI, "
                "the Hooks page in the IDE extension)"}
LABEL = {"mode": "mode", "cap": "slots", "workers": "workers", "agent": "agent"}      # what the map changes
BRANCH = "chore/pulse-settings-"
WAIT = 300                      # seconds a local git step of a change may take, the project's hooks included
EFFECT = {"mode": {"on": "every session here gets the Pulse rules and checks",
                   "off": "no session here gets the Pulse rules; the files stay"},
          "repository": "the GitHub repository whose board Pulse reads",
          "base": "where work starts and checked results go",
          "slots": "how many items pulse go works on at once",
          "workers": {"session": "Claude Code starts claude workers, Codex codex workers, a terminal those of agent",
                      "fixed": "every start of pulse go runs the workers of agent"},
          "agent": {"session": "the workers of a terminal start and their share of the slots, as claude:2,codex:2",
                    "fixed": "the workers of every start and their share of the slots, as claude:2,codex:2"},
          "verify": "runs the tests of every result",
          "spec tests": "which runner runs which spec test files"}


def _effect(label: str, value) -> str:
    said = EFFECT[label]
    return said.get(value, "Pulse is not set up here") if isinstance(said, dict) else said


def delivered(root: Path, harness: str, size: int) -> None:
    """Evidence that a session started here with the Pulse rules: one file per harness, replaced whole."""
    if harness not in HARNESSES:
        return
    folder = config.pulse_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".rules-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "size": int(size)}, out)
        os.replace(name, folder / f"rules-{harness}.json")
    finally:
        Path(name).unlink(missing_ok=True)


def _record(root: Path, harness: str):
    try:
        seen = json.loads((config.pulse_dir(root) / f"rules-{harness}.json").read_text(encoding="utf-8"))
        when = datetime.datetime.fromisoformat(seen["at"].replace("Z", "+00:00")).astimezone()
        return when.strftime("%d.%m. %H:%M"), int(seen["size"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, state.StateError):
        return None


def _within(size: int) -> str:
    return f"{size:,} characters, {'within' if size <= LIMIT else 'over'} the {LIMIT:,} Claude Code takes from a hook"


def _size_now(root: Path) -> int:
    """The rules a session start would get now, as the hook builds them."""
    spec = importlib.util.spec_from_file_location("pulse_hook_now", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return len(module.context("SessionStart", root, config.clone_config(root), dict(os.environ)))


def _rules(root: Path, mode) -> list:
    rows = []
    for harness, name in HARNESSES.items():
        seen = _record(root, harness)
        if not seen:                        # no state claimed, only the way to evidence
            rows.append(f"{name}: not proven: no session start with the Pulse hooks is recorded in this clone; " +
                        WAY[harness])
            continue
        size = _within(seen[1]) if harness == "claude" else f"{seen[1]:,} characters"
        rows.append(f"{name}: last session start {seen[0]}, {size}")
    if mode != "on":
        return rows + ["Rules now: none, mode is off" if mode == "off" else "Rules now: none, Pulse is not set up here"]
    try:
        return rows + ["Rules now: " + _within(_size_now(root))]
    except Exception as error:          # the hook of this checkout may not load; the view still shows
        return rows + [f"Rules now: could not be measured ({type(error).__name__})"]


def read(root: Path, repo: str = "") -> dict:
    """{"rows": (label, value, where, effect), "rules": lines, "offers": (action, words, note)} of the view."""
    cfg = config.load(root)
    base = cfg["base_branch"] or config.default_branch(root)
    ref = config.base_ref(root, base)
    try:
        trusted = config.load(root, ref=ref)
        unread = ""
    except state.StateError as error:
        trusted, unread = {"verify": None, "spec_tests": None}, f"unreadable: {error}"
    tests = trusted["spec_tests"] if isinstance(trusted["spec_tests"], dict) else {}
    runs = ", ".join(f"{pattern}: {entry.get('run')}" for pattern, entry in tests.items() if isinstance(entry, dict))
    here = "working tree"
    rows = [("mode", cfg["mode"] or "not set", here, _effect("mode", cfg["mode"])),
            ("repository", cfg["repo"] or repo or "unknown", here, _effect("repository", None)),
            ("base", base, here, _effect("base", None)),
            ("slots", str(cfg["cap"]), here, _effect("slots", None)),
            ("workers", cfg["workers"], here, _effect("workers", cfg["workers"])),
            ("agent", cfg["agent"], here, _effect("agent", cfg["workers"])),
            ("verify", unread or trusted["verify"] or "none", ref, _effect("verify", None)),
            ("spec tests", unread or runs or "none", ref, _effect("spec tests", None))]
    cap, mode = cfg["cap"], "off" if cfg["mode"] == "on" else "on"
    offers = [(f"setting:mode={mode}", f"mode {mode}", _effect("mode", mode)),
              ("setting:cap", "slots", f"{cap} now; type another number")]
    other = "fixed" if cfg["workers"] == "session" else "session"
    offers.append((f"setting:workers={other}", f"workers {other}", _effect("workers", other)))
    # ponytail: one even split besides claude and codex; offer every split when people ask for 3:1
    for spec in ("claude", "codex") + ((f"claude:{cap // 2},codex:{cap - cap // 2}",) if cap > 1 else ()):
        if spec != cfg["agent"]:
            offers.append((f"setting:agent={spec}", f"agent {spec}", "workers of " +
                           ("every start" if cfg["workers"] == "fixed" else "a terminal start")))
    try:
        policy = "as key 3: " + auto.line(auto.read(root))
    except (OSError, state.StateError):
        policy = "as key 3"
    offers.append(("auto", "approval", policy))
    return {"rows": rows, "rules": _rules(root, cfg["mode"]), "offers": offers}


def _checked(root: Path, key: str, value: str, ref: str = None) -> tuple:
    """(value as the config takes it, base branch, ref, config text there, its value there); a StateError says why
    a change cannot be made."""
    if not auto.person(os.environ, True):
        raise state.StateError("only a person changes settings, in their own terminal or map")
    if key not in LABEL:
        raise state.StateError(f"{key} is no setting the map changes: it changes mode, slots, workers and agent; "
                               f"{key} changes in a reviewed commit")
    cfg = config.load(root)
    base = cfg["base_branch"] or config.default_branch(root)
    ref = ref or config.base_ref(root, base)
    try:
        trusted = config.load(root, ref=ref)
    except state.StateError as error:
        raise state.StateError(f"the settings on {base} cannot be read: {error}") from None
    if key == "mode" and value not in ("on", "off"):
        raise state.StateError("mode is on or off")
    if key == "workers" and value not in ("session", "fixed"):
        raise state.StateError("workers is session or fixed")
    if key == "cap":
        if not value.isdigit() or int(value) < 1:
            raise state.StateError("slots must be a positive number")
        value = int(value)
    if key == "agent":
        try:
            names = config.agent_slots(value, cfg["cap"])
        except ValueError as error:
            raise state.StateError(str(error)) from None
        if not names:
            raise state.StateError("agent names no worker: claude, codex, or a split as claude:2,codex:2")
        gone = [name for name in names if not str(trusted["agents"].get(name) or "").strip()]
        if gone:
            raise state.StateError(f"no agent template {gone[0]!r} in [agents] on {base}")
    text = config.at(root, ref)
    now = config._parse(text).get(key, config.DEFAULTS[key])
    if now == value:
        raise state.StateError(f"{LABEL[key]} is {value} on {base} already; nothing to change")
    return value, base, ref, text, now


def preview(root: Path, key: str, value: str) -> tuple:
    """(lines, intent): what Enter would write and what it does; intent None with the reason when it cannot."""
    try:
        value, base, ref, text, now = _checked(root, key, value)
    except state.StateError as error:
        return [ready.printable(str(error))], None
    label = LABEL[key]
    files = ".pulse/config.toml" + (" and the Pulse block of AGENTS.md" if key == "mode" else "")
    effect = {"mode": _effect("mode", value), "workers": _effect("workers", value),
              "cap": _effect("slots", None), "agent": _effect("agent", config.load(root)["workers"])}[key]
    lines = [f"Set {label} to {value} ({now} on {base}): {effect}.",
             f"Enter commits {files} on a new branch {BRANCH}<date> from {ref} and pushes it.",
             f"It counts for the team once that branch is integrated into {base}; your working tree stays."]
    return [ready.printable(line) for line in lines], {"key": key, "value": value, "expected": text}


def _git(cwd, *args, check=True) -> str:
    """git without the map's terminal: no prompt, stdin closed, its own session, at most WAIT seconds, so a hook, an
    LFS credential ask or a pinentry can neither hang the map nor read its keys; a timeout reads as a failure."""
    out = ready.net_git(cwd, *args, timeout=WAIT)
    if check and out.returncode:
        raise state.StateError(f"git {args[0]}: {ready.git_error(out.stderr) or 'failed'}; nothing written")
    return out.stdout.strip()


def _branch(root: Path) -> str:
    """chore/pulse-settings-<date>, -2, -3 when a branch here or on origin has the name (as migrate names its own)."""
    name = f"{BRANCH}{datetime.date.today():%Y%m%d}"
    listed = ready.net_git(root, "ls-remote", "--heads", "origin").stdout
    taken = {line.partition("refs/heads/")[2] for line in listed.splitlines()} | \
        set(_git(root, "for-each-ref", "--format=%(refname:strip=2)", f"refs/heads/{name}*").split())
    k, candidate = 1, name
    while candidate in taken:
        k += 1
        candidate = f"{name}-{k}"
    return candidate


def change(root: Path, key: str, value, expected: str) -> str:
    """Write what preview showed: a branch from the freshly fetched base with this one change, committed with the
    project's hooks and pushed; the working tree and the base stay. A StateError says why nothing was written."""
    from pulse import go                 # go reaches far; the hook imports this module for delivered() only
    if not auto.person(os.environ, True):
        raise state.StateError("only a person changes settings, in their own terminal or map")
    base = config.load(root)["base_branch"] or config.default_branch(root)
    sha, said = go._fetch_base(root, base)
    if not sha:
        raise state.StateError(f"origin/{base} could not be fetched ({said}); nothing written")
    if config.at(root, sha) != expected:
        raise state.StateError(f"the settings on {base} changed since the preview; open it again")
    value = _checked(root, key, str(value), sha)[0]
    branch = _branch(root)
    existed = _git(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False)
    created = ""
    with tempfile.TemporaryDirectory(prefix="pulse-settings-") as folder:
        tree = Path(folder) / "tree"
        try:                   # a checkout hook or an LFS smudge may fail the add after git made the branch
            _git(root, "worktree", "add", "-q", "-b", branch, str(tree), sha)
            config.write(tree, **{key: value})
            if key == "mode":
                setup.anchors(tree, value)
            _git(tree, "add", "-A")
            _git(tree, "commit", "-q", "-m", f"chore: set Pulse {key} to {value}")
            created = _git(tree, "rev-parse", "HEAD")
            ref = f"refs/heads/{branch}"         # pinned: no remote.origin.push mapping sends it elsewhere
            pushed = ready.net_git(tree, "push", "-q", "-u", "origin", f"{ref}:{ref}", timeout=WAIT)
            if pushed.returncode:
                raise state.StateError(f"the push of {branch} failed ({ready.git_error(pushed.stderr)}); "
                                       "nothing written")
        except BaseException:
            _git(root, "worktree", "remove", "--force", str(tree), check=False)
            _git(root, "worktree", "prune", check=False)
            tip = _git(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False)
            if not existed and tip and tip in (sha, created):    # only the branch this change made
                _git(root, "branch", "-D", branch, check=False)
            raise
        _git(root, "worktree", "remove", "--force", str(tree), check=False)
    return ready.printable(f"{LABEL[key]} {value} is committed on {branch} and pushed; it counts for the team once "
                           f"{branch} is integrated into {base}")
