"""pulse: the command line behind the Pulse skills. Stdlib only.

Exit codes: 0 done, 1 refused (e.g. a claim someone else holds),
2 cannot act here (no repo, ambiguous remotes, gh failed).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import posixpath
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

from pulse import auto, check, config, go, lifecycle, mapstart, migrate, ready, setup, spec, state
from pulse import map as pmap


def _root():
    root = config.find_root()
    if root is None:
        raise state.StateError("not inside a git repository")
    return root


def _ctx():
    root, run = _root(), state.gh          # gh looked up per call so tests can swap it
    return root, state.repo(root, run=run), run


def cmd_status(args):
    """The map frame once, or its view model; it only reads, as the map does (ADR-06, FR-06 of #118): pulse go
    closes what it merged. With n, that item."""
    welcome = getattr(args, "welcome", False)
    help_hint = "pulse --help lists commands; pulse <command> --help explains when and how to use one."
    root = config.find_root()
    mode = config.load(root)["mode"] if root is not None else None
    if welcome and root is None:
        print("Not inside a git repository. Open your project's Git directory, then use /pulse "
              "(in Codex $pulse:pulse) for orientation or pulse setup to activate it.\n" + help_hint)
        return 0
    if root is not None and mode is None:      # asks GitHub nothing
        note = ("Pulse is not active here (no .pulse/config.toml): /pulse (in Codex $pulse:pulse) sets it up, "
                "or pulse setup activates it.")
        print(json.dumps({"active": False, "note": note}) if args.json else note)
        if welcome:
            print(help_hint)
        return 0
    if welcome and mode == "off":
        print("Pulse is off here. pulse setup --mode on activates it when you choose to continue.")
    if args.n is not None:
        return _item(args)
    root, repo, run = _ctx()
    note = ""
    try:
        state.load(root, repo, run=run, fresh=args.fresh)
    except state.StateError as e:
        note = f"the board could not be read: {e}"
    _fetch(root)               # waits, with a time limit: the ramp below counts every clone's Plans
    vm = pmap.gather(root)
    vm["error"] = vm["error"] or note
    vm["last_run"] = go.last_run(root)
    unknown = bool(vm["error"] and state.stored(root) is None)
    if welcome and unknown:
        print(ready.printable("No current board state is available; readiness is unknown. " + vm["error"]))
    else:
        print(json.dumps(vm, indent=2) if args.json else
              pmap.once(vm, sys.stdout.isatty()) + _last_run(vm["last_run"], vm.get("refusals")))
    if welcome:
        if vm["error"]:
            if not unknown:
                print(ready.printable(vm["error"]))
            print("pulse status --fresh retries the board read; resolve the reported error before starting work.")
        print("pulse map opens the live view. pulse go processes permitted queue work; "
              "add a goal, for example: pulse go Improve checkout.\n" + help_hint)
    return 2 if unknown else 0   # nothing known: no board to show


def _last_run(rep, refusals=None) -> str:
    """How the last pulse go run went: when it ended, its results per kind, what failed and why, and each item a
    hook's refusal holds, with cause and effect (FR-10 of #178)."""
    if not rep:
        return ""
    run, items = rep["run"], rep.get("items") or {}
    counts = collections.Counter(i.get("result") for i in items.values())
    when = (f"runs since {run.get('started')} (pid {run.get('pid')})" if run["running"] else
            f"ended {run['ended']}" + (f", stopped by {run['stopped']}" if run.get("stopped") else "")
            if run.get("ended") else "ended without its cleanup; the next pulse go takes over what it held")
    lines = [f"last pulse go run: {when}: " + (", ".join(f"{c} {k}" for k, c in counts.items()) or "no results")]
    lines += [f"  #{n} failed: {i.get('why')}" for n, i in items.items() if i.get("result") == "failed"]
    lines += [_held(r) for r in refusals or ()]
    return "\n" + "\n".join(map(ready.printable, lines))     # a why quotes foreign text (#56)


def _held(r: dict) -> str:
    """One line for a hook's refusal: the item, where it stands, what happened, and what that does now."""
    if r.get("legacy"):
        return f"  earlier: {r['legacy']}; {go.refusal_effect(r)}"
    return f"  #{r['number']} {go.refusal_standing(r) if r.get('current') else 'earlier'}: {go.refusal_cause(r)}; " \
        f"{go.refusal_effect(r)}"


def _goal_said(goal) -> None:
    """The goal's state and why, when something holds it: a failed interpretation pauses with its reason and the
    person's next step (#206)."""
    if (goal or {}).get("reason"):
        step = "; go on: pulse go --resume, or change it: pulse go --steer '<new text>', then pulse go --resume" \
            if goal["status"] == "paused" else ""
        print(ready.printable(f"  goal {goal['status']}: {goal['reason']}{step}"))


def _fetch(root, now=False):
    """ready.fetch, and one line when the last fetch failed or none could run: what git said, as every
    command names it (#85), or that origin did not answer, where git said nothing; on stderr, so --json
    stays JSON."""
    got = ready.fetch(root, now=True) if now else ready.fetch(root)
    if not got:
        said = ready.fetch_said(root) if got is False else ""
        why = f"git fetch said: {said}" if said else \
            "offline: origin did not answer" if got is False else "no fetch: .git is read-only here"
        print(why + "; the Plans are those this clone fetched last", file=sys.stderr)


def _unfetched(root) -> tuple:
    """(why, behind) after a fetch just now (#78), held against ready.behind after every fetch that reached
    origin (#85): ("", {}) when every branch of origin is here as origin has it; (why, None) when origin did
    not answer or no fetch could run; else what git said, the branch names that share a ref file (#97), or
    which refs differ, and behind. A fetch the time
    limit ended heard nothing, and ls-remote would wait as long again."""
    got = ready.fetch(root, now=True)
    if got is None:
        return "no fetch: .git is read-only here", None
    said = "" if got else ready.fetch_said(root)
    timed_out = said.startswith("no answer within ")
    behind = ready.behind(root) if got or said and not timed_out else None
    if behind is None:
        return "origin did not answer" + (f" ({said})" if said else ""), None
    twin, rest = ready.conflict(behind), [b for b in behind if b not in ready.twins(behind)]     # #97
    if said:
        return "; ".join(filter(None, (f"git fetch said: {said}", twin))), behind
    return "; ".join(filter(None, (twin, rest and "the fetch went through, but refs here differ from origin: " +
                                   ", ".join(ready.printable(f"origin/{b}") for b in rest)))), behind


def _item(args):
    """pulse status <n>: one open item, its stage in the words of the map, its Plan, claim, and blockers."""
    root, repo, run = _ctx()
    items = state.load(root, repo, run=run, fresh=args.fresh)
    i = next((i for i in items if i["number"] == args.n), None)
    if i is None:
        print(f"#{args.n} is not an open issue")
        return 1
    _fetch(root)               # as the board: the Plan another clone pushed counts
    stages = {}                # the stage in the words of the map (#99 FR-14), without the board lines it never prints
    pmap.render(pmap.gather(root, board=False), color=0, stages=stages)
    p = ready.plans(root).get(args.n) or {}
    i = {**i, "stage": stages.get(args.n, ""), "plan": p.get("path"), "plan_ref": p.get("ref"),
         "plan_blob": p.get("blob"), "plan_findings": ready.plan_validation(root, p["text"], i.get("spec")) if p else []}
    # a title or note is foreign text (#56): each line of a value through printable, as on the board, and its
    # later lines indented, so none reads as a field
    text = "\n".join("  " * (j > 0) + ready.printable(line)
                     for k, v in i.items() for j, line in enumerate(f"{k}: {v}".splitlines()))
    print(json.dumps(i, indent=2) if args.json else text)
    return 0


def cmd_go(args):
    """An explicit runner request, owned by the terminal or by Pulse when no TTY exists."""
    why = auto.nested(os.environ)        # an attended session may start it; its own agents never (#183)
    if why:
        print(f"pulse go: no nested runner from {why}; start it in your own terminal")
        return 1
    objective = " ".join(getattr(args, "objective", [])).strip()
    epic, item = getattr(args, "epic", None), getattr(args, "item", None)
    control = "steer" if getattr(args, "steer", None) is not None else \
        next((name for name in ("pause", "resume", "stop") if getattr(args, name, False)), None)
    if control and (objective or epic is not None or item is not None) or item is not None and item <= 0:
        print("pulse go: use one control without a goal or selector; item numbers must be positive")
        return 1
    root = _root()
    if getattr(args, "stop", False):
        from pulse import runner
        current = (go.last_run(root) or {}).get("run") or {}
        if not current.get("id") or not current.get("running"):
            print("pulse go: no active runner")
            return 0
        result = runner.stop(root, current.get("id", ""))
        print(ready.printable(f"pulse go: {result['status']}; {result.get('why', '')}"))
        return 1 if result["status"] == "conflict" else 0
    if objective or epic is not None or item is not None or control:
        from pulse import goals
        try:
            current = goals.read(root)
            expected = (current or {}).get("revision")
            if control:
                if not current:
                    raise state.StateError("no saved goal to " + control)
                saved = goals.control(root, control, expected, text=getattr(args, "steer", None))
            else:
                selector = {"epic": epic} if epic is not None else {"item": f"#{item}"} if item is not None else None
                saved = goals.submit(root, objective or None, selector=selector, expected=expected)
        except state.StateError as error:
            print(ready.printable(f"pulse go: {error}"))
            return 1
        print(f"pulse go: goal{' ' + control if control else ''} saved; runner applies it at the next transition")
        print(ready.printable(f"  objective: {saved['objective']}"))
        print(ready.printable(f"  scope: {saved['scope']['mode']}; revision: {saved['revision']}"))
        if control in {"pause", "steer"}:
            return 0
    else:
        print("pulse go: process the queue; optional goal example: pulse go Improve checkout")
    if not _tty():
        from pulse import runner
        receipt = runner.start(root)
        print(ready.printable(f"pulse go: {receipt['status']}; {receipt.get('why', '')}"))
        for key in ("pid", "run_id", "report", "log"):
            if receipt.get(key):
                print(ready.printable(f"  {key}: {receipt[key]}"))
        if receipt.get("goal"):
            print(ready.printable(f"  runner goal revision: {receipt['goal'].get('revision', '')}"))
            _goal_said(receipt["goal"])
        if receipt["status"] == "started":         # the managed run picks the same (#182)
            spec, why = go.workers(config.load(root), os.environ)
        else:                                     # a run already active or done: the workers its report names
            seen = (go.last_run(root) or {}).get("workers") if receipt["status"] in ("running", "finished") else None
            spec, why = (seen.get("spec"), seen.get("why")) if isinstance(seen, dict) else ("", "")
        if spec:
            warn = setup.untrusted(spec)
            print(ready.printable(f"  workers {spec} ({why})" + (f"; {warn}" if warn else "")))
        print("  pulse map shows progress; pulse go --stop requests a controlled stop")
        return 1 if receipt["status"] == "error" else 0
    cfg = config.load(root)
    if cfg["verify"]:          # go.run refuses without it, before its first line
        if not (go.last_run(root) or {}).get("run", {}).get("running"):
            mapstart.ensure(root)          # the live map where the user works (D-48), beside no run of this clone
        who = state.who(root, run=state.gh)          # the account the run acts as (#111)
        spec, why = go.workers(cfg, os.environ)          # the workers of the session that starts it (#182)
        warn = setup.untrusted(spec)
        print(f"pulse go: {'as ' + who + ', ' if who else ''}cap {cfg['cap']}, workers {spec} ({why}); "
              f"Ctrl-C stops it{'; ' + warn if warn else ''}", flush=True)
    rep = go.run(root)
    stopped = rep.get("run", {}).get("stopped")
    # a Plan that still fails P1 to P5 waits for a person, so the run is not clean
    rc = 128 + signal.Signals[stopped] if stopped else \
        1 if rep["failed"] or rep.get("halt") or any(j["why"].startswith("plan: ") for j in rep["skipped"]) else 0
    verbs = {"spec": "specifying", "documents": "checking documents", "plan": "planning", "build": "building", "refresh": "rechecking",
             "merge": "merging the base into"}
    for n in rep.get("took", []):
        print(f"  took over #{n} from a stopped run")
    for j in rep["started"]:           # branch names reach the terminal printable (#63)
        print(ready.printable(f"  {verbs[j['phase']]} #{j['number']} with {j['agent']} on {j['branch']} "
                              f"(from {j['base']}) in {j['worktree']}"))
    for j in rep.get("planned", []):
        print(f"  planned #{j['number']} -> {j['plan']} ({j['gate']}{_spent(j)})")
    for j in rep["done"]:
        rounds = f" after {j['rounds']} fix round{'s' if j['rounds'] != 1 else ''}" if j["rounds"] else ""
        gates = ", ".join(f"{g} {j[g].split(':')[0]}" for g in go.GATES)
        policy = auto.read(root)
        state_ = "integrated" if j["number"] in rep.get("merged", []) else \
            "published work preserved; a gate is red" if not all(j[g].startswith("pass") for g in go.GATES) else \
            "automatic integration pending" if auto.active(policy["policy"]) and not policy.get("blocked") else \
            "waits for integration approval"
        print(f"  done   #{j['number']} -> {j.get('head', '')[:12]} ({gates}{rounds}, {state_}{_spent(j)})")
    for j in rep["failed"]:
        print(ready.printable(f"  failed #{j['number']}: {j['why']} (worktree {j['worktree']}, log {j['log']})"))
    for j in rep["limited"]:
        print(ready.printable(f"  limit  #{j['number']}: {j['why']} (log {j['log']})"))
    for j in rep["skipped"]:
        print(ready.printable(f"  skipped #{j['number']}: {j['why']}"))
    for n in rep.get("merged", []):
        print(f"  closed #{n}: its approved result was integrated")
    for j in rep.get("stopped", []):
        print(ready.printable(f"  stopped #{j['number']} in {j['phase']} ({j['why']})"))
    for u in rep.get("unclean", []):
        print(ready.printable(f"  kept the worktree of closed #{u['number']}, it has changes: {u['worktree']}"))
    for r in go.refusals(root):         # each item a hook's refusal holds, with cause and effect (FR-10 of #178)
        print(ready.printable(_held(r)))
    _goal_said(rep.get("goal"))
    if rep.get("halt"):
        print(ready.printable(f"  held: {rep['halt']}"))     # a hook's name and git's words (L-4)
        kind = go.halt_kind(rep)
        probe = rep.get("compatibility") or {}
        detail = {"next": probe.get("next"), "url": probe.get("log")} if kind == "compatibility" else \
            {} if kind in go.OWN_REMEDY else rep.get("base") or {}
        for key, label in (("cause", "Cause"), ("next", "Next"), ("url", "Details")):
            if detail.get(key):
                print(ready.printable(f"  {label}: {str(detail[key])[:512]}"))
    if stopped:
        print(f"pulse go: stopped by {'Ctrl-C' if stopped == 'SIGINT' else stopped}; the report so far is above")
    if rep.get("report"):
        print(f"  report {rep['report']}")
    return rc


def cmd_map(args):
    """The live map; while it runs, map.pid tells pulse map --ensure that this clone has one (D-48)."""
    if args.ensure:
        return mapstart.ensure(_root())
    root = config.find_root()
    if root is None or not sys.stdout.isatty():
        return pmap.main(args)
    with mapstart.noted(root) as end:
        end["code"] = pmap.main(args)
    return end["code"]


def cmd_migrate(args):
    root = _root()
    try:
        if args.local:
            rep = migrate.apply_local(root)
        elif args.issues:
            run = state.gh
            rep = migrate.apply_issues(root, state.repo(root, run=run), run=run)
        else:
            existing = []
            if not args.offline:
                existing = migrate.issues(state.repo(root, run=state.gh), state.gh)
            rep = {"detect": migrate.detect(root), "plan": migrate.plan(root, existing)}
    except migrate.MigrateError as e:
        print(f"pulse migrate: {e}")
        return 2
    if args.json:
        print(json.dumps(rep, indent=2))
    elif "plan" in rep:
        d, show = rep["detect"], migrate.printable
        print(show(f"DIA mode {d['dia_mode']}, anchors {', '.join(d['anchors']) or 'none'}, "
                   f"{d['open_items']} open and {d['done_items']} done items in {d['backlog'] or 'no backlog'}"))
        for a in rep["plan"]:
            how = f"reuse #{a['match']}" if a["match"] else "new record"
            rel = (f", parent {a['parent']}" if a["parent"] else "") + \
                  (f", blocked by {', '.join(a['blocked_by'])}" if a["blocked_by"] else "")
            print(show(f"  {a['id']:<14} {a['kind']:<5} {a['status'] or '-':<12} {how:<11} {a['title']}{rel}"
                       f"{' (ready)' if a['ready'] else ''}"))
            if a["reuse"]:
                print(show(f"{'':<17}{a['reuse']}"))
        for head, lines in (("passed over, not trusted", [p for a in rep["plan"] for p in a["passed"]]),
                            ("removed once the content has moved", d["removes"]),
                            ("left in place, for you to decide", d["keeps"]),
                            ("not carried over, so the backlog stays", d["skipped"])):
            if lines:
                print(f"{head}:\n" + "\n".join(show(f"  {x}") for x in lines))
        print("next: pulse migrate --local, then pulse migrate --issues")
    else:
        print(json.dumps(rep, indent=2))
    return 0


def cmd_new(args):
    """A record for a spec every clone can read, or a draft claimed for the analysis and spec work;
    --issue makes an issue that links no spec that record or that draft (D-43). A spec an agent cannot plan
    from is refused; a spec branch is published to origin before registration."""
    root, repo, run = _ctx()
    args.title = spec.with_id(args.spec, args.title)          # FEAT-04-02 Speech input, on the board too
    labels = []
    if not args.draft:
        if not (root / args.spec).is_file():
            print(f"pulse new: write the spec first, {args.spec} does not exist in the repository")
            return 2
        had = str(spec.front((root / args.spec).read_text(encoding="utf-8")).get("issue") or "").strip()
        if had.isdigit() and not args.issue:        # a rerun, after a rate limit say: no second record
            print(f"pulse new: {args.spec} has its record #{had} already; nothing created")
            return 0
        here = spec.on_base(root, args.spec, "HEAD")          # as committed: what origin gets
        wrong = []
        if here is not None and args.type in spec.SECTIONS:  # an epic needs R1 only, as pulse check --spec says
            lines, body = spec.split(here)     # issue: is mine to write, a template's {N} there too (IMP-11 FR-04)
            wrong = spec.findings("---\n" + "\n".join(l for l in lines if not l.startswith("issue:")) +
                                  "\n---\n" + body, args.type)
        if wrong:
            print(f"pulse new: {args.spec} is not ready: {'; '.join(wrong)}; fix it, commit, and run pulse new again")
            return 1
        prio = spec.front(here or "").get("priority")
        labels = [prio] if prio in spec.PRIORITY else []
        branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                                capture_output=True, text=True).stdout.strip()
        base = config.load(root)["base_branch"] or config.default_branch(root)
        if here is not None and _spec_branch_here(root, branch, base):
            pushed = ready.net_git(root, "push", "-q", "-u", "origin", f"refs/heads/{branch}")
            if pushed.returncode:
                print(f"pulse new: git push said: {ready.git_error(pushed.stderr)}; nothing registered")
                return 2
        else:                  # the base or item branch must already be published
            why, behind = _unfetched(root)
            if behind is None or branch in behind:     # the ref that shows the spec on origin is not here
                print(f"pulse new: {why}, so nothing shows {args.spec} on origin; nothing registered")
                return 2
            if why:            # stdout carries the number a skill reads
                print(f"pulse new: {why}", file=sys.stderr)
            if here is None or here != spec.on_base(root, args.spec, f"origin/{branch}"):
                print(f"pulse new: {args.spec} is not on origin as committed here; "
                      f"commit it, then: git push -u origin {shlex.quote(branch)}")
                return 2
    if not args.draft:                     # a clone without the pulled issue: line: one open record per spec (#80)
        same = next((i for i in state.load(root, repo, run=run, fresh=True)
                     if posixpath.normpath(i.get("spec") or ".") == posixpath.normpath(args.spec)
                     and i["number"] != args.issue), None)
        if same:
            print(f"pulse new: #{same['number']} records {args.spec} already; nothing created. Pull the base to get "
                  f"its issue: line, or go on with #{same['number']}")
            return 1
    if getattr(args, "base", False):       # it repairs the base or the Plan commit gates (FR-05 of #178)
        labels.append(state.BASE)
    if args.draft and not args.issue:      # one draft per type and title: two people start the same realign or BA
        same = next((i for i in state.load(root, repo, run=run, fresh=True) if i.get("draft")
                     and i["type"] == args.type and i["title"].casefold() == args.title.casefold()), None)
        if same:
            print(f"pulse new: #{same['number']} is the draft \"{same['title']}\" already, held by "
                  f"{same.get('claimed_by') or 'nobody'}; a free one or one of yours goes on with "
                  f"--issue {same['number']}, one another person holds stays theirs")
            return 1
    rel = {"parent": args.parent, "blocked_by": args.blocked_by or [], "labels": labels}
    if args.issue:
        ok, why = state.attach(root, repo, args.issue, args.type, args.spec, run=run, title=args.title, **rel)
        if not ok:
            print(why)
            return 1
        n = args.issue
    else:
        n = state.create(root, repo, args.type, args.title, spec=args.spec, draft=args.draft, run=run, **rel)
    if args.draft:
        ok, why = state.claim(root, repo, n, run=run, phase=args.phase)
        print(n if ok else f"{n}\n{why}")
        if ok:
            mapstart.ensure(root)
        return 0 if ok else 1
    link(root, repo, n, args, run)
    print(n)
    return 0


def _spec_branch_here(root, branch, base) -> bool:
    """Whether the branch checked out is a spec branch: not the base, and against the base it changes something,
    all of it under _devprocess/, and no item's build branch. Publishing makes its spec
    available for automatic planning; final integration carries it onto the base."""
    if branch in ("", base):
        return False
    n = state.item_of(branch)
    if n and not config.is_spec_branch(config.load(root), branch, n):     # feat/42-theme-spec is a spec branch
        return False
    changed = ready._git(root, "diff", "--name-only", "-z", f"{config.base_ref(root, base)}...HEAD").split("\0")
    return any(changed) and all(c.startswith("_devprocess/") for c in changed if c)


def link(root, repo, n, args, run):
    """Write issue and parent into the new spec; list it in Items where C9 finds it (spec.add_under)."""
    path = root / args.spec
    if not spec.split(path.read_text(encoding="utf-8"))[0]:
        return
    spec.set_front(path, "issue", str(n))
    # the spec that names the parent here, else the one its record links (a done feature is a parent too)
    up = (spec.registered(root).get(args.parent) or state.spec_of(repo, args.parent, run)) if args.parent else None
    if not up or not (root / up).is_file():
        return
    spec.set_front(path, "parent", os.path.relpath(root / up, path.parent))
    spec.add_under(root / up, n, args.title, path)


def cmd_number(args):
    """Every spec's file name starts with the ID its place in the tree calls for; with --apply the specs
    move there, every path to them follows, and so do their records."""
    root = _root()
    why, behind = _unfetched(root) if args.apply else ("", {})
    lost = [ready.printable(b) for b, c in (behind or {}).items() if c and subprocess.run(
        ["git", "-C", str(root), "log", "--name-only", "--format=", "--end-of-options", c, "--",
         spec.REQUIREMENTS], capture_output=True).returncode]     # not here, or without a tree or parent
    if behind is None or lost:     # an ID another clone pushed since the last fetch would be handed out twice
        print(f"pulse number: {why}; " + (f"{', '.join(lost)} did not arrive; " if lost else "") +
              "no ID handed out, another clone may have taken it")
        return 2
    if why:                    # a ref git could not write, or wrote elsewhere, counts through its commit here
        print(f"pulse number: {why}", file=sys.stderr)
    base = config.load(root)["base_branch"] or config.default_branch(root)
    try:
        found = spec.numbering(root, revs=tuple(c for c in behind.values() if c),
                               base_rev=behind.get(base) or None)
    except subprocess.CalledProcessError as e:      # no history read is no ID (#85 audit M-1)
        print(f"pulse number: git cannot read the history here ({ready.git_error(e.stderr or '')}); "
              "no ID handed out")
        return 2
    for old, why, new in found:
        print(f"{old} -> {Path(new).name}: {why}" if new else f"{old}: {why}")
    moves = [(old, new) for old, _, new in found if new]
    done = "pulse number: every spec has its ID"
    if not args.apply:
        if moves or not found:
            print("pulse number --apply renames them" if moves else done)
        return 1 if len(moves) < len(found) else 0         # a name to change by hand
    spec.renumber(root, moves)
    try:
        _follow(root)
    except state.StateError as e:
        print(f"pulse number: {e}; the records follow on the next pulse number --apply")
    if moves or not found:
        print(f"renamed {len(moves)} spec{'s' if len(moves) != 1 else ''}: commit them" if moves else done)
    return 1 if len(moves) < len(found) else 0


def _follow(root):
    """Each record links its spec where the spec now lies and carries its ID in the title. A record moves
    once the base branch has the new path and no longer the one it links, since agents read the spec
    there: before the merge it waits, and a clone behind the base branch changes nothing."""
    local = spec.registered(root)
    if not local:
        return
    run = state.gh
    repo = state.repo(root, run=run)
    ready.fetch(root)
    base = config.base_ref(root)
    records = state.issues(repo, run, "all", "number,title,body")
    for r in sorted(records, key=lambda r: r["number"]):
        path, m = local.get(r["number"]), state.SPEC.search(r.get("body") or "")
        if not path or not m:                    # no spec of ours, or a draft
            continue
        n, now, title = r["number"], m.group(1), spec.with_id(path, r["title"])
        if now != path and (spec.on_base(root, now) is not None or spec.on_base(root, path) is None):
            print(f"#{n} keeps its record until {path} is on {base}: run pulse number --apply again after the merge")
            continue
        if now != path:
            state.set_spec(root, repo, n, path, run=run)
        if title != r["title"]:
            run(["issue", "edit", str(n), "--repo", repo, "--title", title])
        if now != path or title != r["title"]:
            print(f"#{n} links {path}")


def _tty() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _person_only(lever, n=None):
    """Gate levers are a person's (D-21, FEAT-03-01): auto.person, no agent marker and a terminal. It holds direct
    calls only; the lever guard checks what goes into a pane. A lever grant of the person lets an attended Claude
    Code session pull it (#197): logged, and named on the item's board record."""
    from pulse import levers
    if auto.person(os.environ, _tty()):
        return False
    root = config.find_root()
    grant = levers.allowed(root, os.environ) if levers.grantable(lever) else None
    if grant:
        items = [m for m in (n if isinstance(n, list) else [n]) if m]
        sid, what = levers.session(os.environ), " ".join(["pulse", lever, *map(str, items)])
        levers.use(root, grant, what, "cli", sid)
        print(ready.printable(f"pulse {lever}: under the person's lever grant ({grant['scope']}, by {grant['by']}) "
                              f"for Claude Code session {sid[:8]}"))
        for m in items:
            _lever_note(root, m, what, grant, sid)
        return False
    print(f"pulse {lever}: only a person does this, in their own terminal or the Pulse map; tell the person "
          "which gate waits" + (f"; or {levers.HINT}" if levers.session(os.environ) and levers.grantable(lever) else ""))
    return True


def _lever_note(root, n, what, grant, sid):
    """FR-08 of #197: the board record of the item names the session and the grant behind the lever."""
    stamp = time.strftime("%H:%M UTC", time.gmtime(grant["at"]))
    body = (f"`{what}` ran from Claude Code session {sid[:8]} under a lever grant ({grant['scope']}) "
            f"that {grant['by']} gave at {stamp}; the item's record shows what it changed.")
    try:
        state.gh(["issue", "comment", str(n), "--repo", state.repo(root, run=state.gh), "--body", body])
    except state.StateError as error:
        print(ready.printable(f"pulse: the board note on #{n} failed ({error}); the use is in pulse levers"))


def cmd_levers(args):
    """#197: show, ask for, or end the person's lever grants."""
    from pulse import levers
    root = _root()
    if args.action == "off":
        print(f"pulse levers: {levers.off(root)} grant(s) ended; every lever is the person's again")
        return 0
    if args.action == "allow":
        if not args.scope:
            print("pulse levers allow: name the scope, run, session or always")
            return 1
        if auto.person(os.environ, _tty()):
            if args.scope != "always":
                print("pulse levers allow: a person grants run or session to one session in the Pulse map "
                      "(l on its line); always holds for every attended session of this clone")
                return 1
            levers.grant(root, "always", "", levers.who(root))
            print("pulse levers: every attended Claude Code session of this clone may pull your levers until "
                  "pulse levers off")
            return 0
        sid = levers.session(os.environ)
        if not sid:
            print(ready.printable(f"pulse levers allow: {levers.why_not(os.environ)}"))
            return 1
        levers.request(root, sid, args.scope, levers.run_id(root) if args.scope == "run" else "")
        print(f"pulse levers: the grant ({args.scope}) holds once Claude Code reports this command done; "
              "it follows the person's confirmation in Claude Code's dialog")
        return 0
    shown = levers.listing(root)
    for g in shown["grants"]:
        print(ready.printable(f"grant {g['scope']} by {g['by']}, {g['until']}"))
    for u in shown["uses"][:10]:
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(u["at"]))
        print(ready.printable(f"used {when}: {u['lever']} by session {u['session'][:8]} ({u['scope']}, {u['source']})"))
    if not shown["grants"]:
        print("pulse levers: no grant; every lever is the person's")
    return 0


def _other_item(cmd, n):
    """An agent of pulse go holds as its run, which holds the run's other items too: it claims and gives back
    only the item pulse go started it for (PULSE_ITEM, #65); a session without one, none."""
    if not os.environ.get("PULSE_HOLDER") or os.environ.get("PULSE_ITEM") == str(n):
        return False
    print(f"pulse {cmd} #{n}: an agent of pulse go claims and releases only its own item")
    return True


def cmd_lifecycle(args):
    if _person_only(args.cmd, args.n):
        return 1
    if args.cmd in ("defer", "resume", "revoke", "handoff"):
        return _local_action(args.cmd, [args.n])
    root, repo, run = _ctx()
    if args.cmd == "delete":
        from pulse import remove
        return remove.command(root, repo, args.n, run=run)
    planned = lifecycle.preview(root, repo, args.n, args.cmd, run=run)
    for line in planned["lines"]:
        print(ready.printable(line))
    try:
        answer = input(f"Type {planned['confirmation']} to confirm, or Enter to cancel: ").strip()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer != planned["confirmation"]:
        print("cancelled; nothing changed")
        return 0
    print(ready.printable(lifecycle.apply(root, repo, planned, answer, run=run)))
    return 0


def cmd_approve(args):
    """Durably queue approval of the observed result and base; synchronization authenticates it."""
    if _person_only("approve", args.n):
        return 1
    return _local_action("approve", args.n)


def _local_action(kind, numbers):
    root, code = _root(), 0
    items = {item["number"]: item for item in state.cached(root) or []}
    for n in numbers:
        item = items.get(n)
        if item is None:
            print(f"#{n}: open or refresh the Pulse map first; no observed item is cached")
            code = 1
            continue
        try:
            intent = pmap.action_preview(root, item, kind)
        except state.StateError as error:
            print(ready.printable(str(error)))
            code = 1
            continue
        print("\n".join(intent["lines"]))
        print(pmap.queue_action(root, intent))
    return code


def cmd_auto(args):
    """Show final approval policy or durably queue an explicit person setting."""
    if bool(args.gate) != bool(args.switch) or args.span and args.switch != "on":
        print("pulse auto: show policy, or use merge on|off with optional --for 8h|2d")
        return 2
    if args.switch and _person_only(f"auto {args.gate} {args.switch}"):
        return 1
    root = _root()
    if args.switch:
        try:
            until = auto.stamp(time.time() + args.span) if args.span else None
            print(pmap.queue_policy(root, args.switch == "on", until=until))
        except state.StateError as error:
            print(ready.printable(str(error)))
            return 1
        return 0
    print(auto.show(root, config.load(root).get("repo") or ""))
    return 0


def _spent(j):
    u = j.get("usage")
    return f"; {u['tokens']} tokens, ${u['cost_usd']:.2f}, {u['seconds']} s" if u else ""


def _said(result):
    ok, why = result
    print(why)
    return 0 if ok else 1


def cmd_claim(args):
    """The claim carries the files of the Plan this clone has, so every ramp holds them without a fetch
    (WP-56). Running work and the ramp's next-item reservations refuse a conflicting claim (#46, #102)."""
    if args.take and _person_only("claim --take", args.n) or _other_item("claim", args.n):
        return 1
    root, repo, run = _ctx()
    sources = ready.plan_sources(root)
    variants = [row for row in sources.get(args.n, []) if not row.get("superseded")]
    if len({row["content"] for row in variants}) > 1:
        paths = ready.printable(", ".join(sorted({row["path"] for row in variants})))
        return _said((False, f"#{args.n}: plan versions differ; choose the preserved content in {paths}"))
    found = ready.plans(root, sources=sources)
    plans = ready.plan_files(root, found)
    files = plans.get(args.n)
    if files:
        # ponytail: read, then claim; two claims on different items that share a file in the same
        # seconds can both win, and the ramp shows both. A read after the claim would close it.
        items = ready.current(root, state.load(root, repo, run=run, fresh=True))
        others = [i for i in items if i["number"] != args.n]
        hit = ready.clash([posixpath.normpath(f) for f in files], ready.held(others, plans))
        if hit:
            return _said((False, f"#{args.n}: {hit[0]} is in use by #{hit[1]}; start #{args.n} once #{hit[1]} is done"))
        cfg = config.load(root)
        gates = ready.gates(root, [dict(i, assignees=[]) for i in items],
                            config.load(root, config.base_ref(root)), found)
        ramp = ready.ramp(items, plans, cfg["cap"], state.me(root, run=run), gates=gates)
        reserved = next((i for i in ramp["locked"] if i["number"] == args.n and i["reserved"]), None)
        if reserved:
            stage = next(i["stage"] for i in ramp["rows"] if i["number"] == args.n)
            return _said((False, f"#{args.n}: {stage}; start #{reserved['holder']} first"))
    labels = set()             # as the claim read them: a draft starts on its docs branch (#99 FR-05)
    rc = _said(state.claim(root, repo, args.n, run=run, take=args.take, files=files, labels=labels))
    if rc == 0:
        print(_start_point(root, args.n, state.DRAFT in labels))
        mapstart.ensure(root)
    return rc


def _start_point(root, n, draft=False) -> str:
    """Where the work on n starts, from origin as a fetch just now shows it: the item's branch there,
    where the last holder pushed, for a draft its docs branch (#99 FR-05), else the base branch; never the
    local base, which may lag (#78).
    A pushed name is quoted as a shell reads it: an agent may run the line (#78 audit L-1). Not checked
    while the base or a branch of n here is not where origin has it; any other ref that is not goes to
    stderr with what git said (#85)."""
    why, behind = _unfetched(root)
    cfg = config.load(root)
    base = cfg["base_branch"] or config.default_branch(root)
    if behind is None or any(b == base or state.item_of(b) == n or draft and config.is_spec_branch(cfg, b, n)
                             for b in behind):
        return f"start point not checked: {why}"
    if why:
        print(f"pulse claim: {why}", file=sys.stderr)
    b = state.docs_branch(root, n) if draft else go._branch_of(root, n, base, origin_first=True)
    if b and ready._tip(root, f"refs/remotes/origin/{b}"):
        return "start from " + ready.printable(shlex.quote(f"origin/{b}"))
    if b:
        return f"continue on {ready.printable(shlex.quote(b))}: only this clone has it, push it"
    if not ready._tip(root, f"refs/remotes/origin/{base}"):
        return f"start point not checked: origin has no {base}"
    return f"start from origin/{base} (fetched just now)"


def cmd_release(args):
    """--take also hands over another person's claim (D-13)."""
    if args.take and _person_only("release --take", args.n) or _other_item("release", args.n):
        return 1
    if args.take:
        return _local_action("handoff", [args.n])
    root, repo, run = _ctx()
    kept = [] if args.take else \
        ready.unpushed(root, args.n, config.load(root)["base_branch"] or config.default_branch(root))
    v = state._view(repo, args.n, run) if kept else {}
    if kept and not state._lead(v, state.holder())[1] and \
            state.me(root, run=run) in [a["login"] for a in v.get("assignees", [])]:
        # given back, the work would be lost to whoever takes it next (#79); a session whose item an
        # older claim holds pushes nothing of it (#77), and another person's item is theirs to name
        b, k = kept[0]
        print(f"#{args.n} keeps its claim: {ready.printable(b)} has {k} commit{'s' if k != 1 else ''} only this "
              f"clone has; push first (git push -u origin {ready.printable(shlex.quote(b))})")
        return 1
    return _said(state.release(root, repo, args.n, run=run, take=args.take, take_person=args.take))


def cmd_retry(args):
    if _person_only("retry"):
        return 1
    try:
        print(pmap.retry_action(_root(), args.operation))
    except state.StateError as e:
        print(ready.printable(str(e)))
        return 1
    return 0


def cmd_publish_plan(args):
    """Publish exactly the local Plan bytes selected by the person or interactive parent session."""
    why = auto.nested(os.environ)
    if why:
        print(f"pulse publish-plan: no nested publication from {why}; run it in your own terminal")
        return 1
    root, repo, run = _ctx()
    selection = {key: getattr(args, key) for key in ("worktree", "path", "content")}
    result = go.publish_plan(root, repo, args.n, selection, gh_run=run)
    print(ready.printable(f"pulse publish-plan: {result['status']}; {result.get('why', '')}"))
    return 0 if result["status"] == "published" else 1


def cmd_setup(args):
    """--cli and --codex-rules set up this machine, from anywhere; the rest sets up this project. Switching
    Pulse off or out takes the lever guard along: a person's (#106)."""
    if args.check_plan:
        return setup.main(args)
    if args.remove and _person_only("setup --remove") or args.mode == "off" and _person_only("setup --mode off"):
        return 1
    if args.cli or args.codex_rules:
        return setup.machine(args.cli, args.codex_rules, args.remove, args.dry_run)
    return setup.main(args)


def _numbers(text):
    return [int(x) for x in str(text).replace("#", "").split(",") if x.strip()]


def parser() -> argparse.ArgumentParser:
    """The pulse command line; scripts/gen_commands.py documents it from here."""
    p = argparse.ArgumentParser(prog="pulse", description="Pulse: work state, parallel agents, V-Model.",
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>", title="commands")
    plumbing = []

    def add(name, fn, text, plumb=False, when="", example=""):
        """A command; plumbing (for skills, hooks, and pulse go) is listed apart in the help."""
        if plumb:
            plumbing.append(f"  {name:<14}{text}")
        c = sub.add_parser(name, description=text, epilog=f"When: {when}\nExample: {example}",
                           formatter_class=argparse.RawDescriptionHelpFormatter,
                           **({} if plumb else {"help": text}))   # help= lists it
        c.set_defaults(func=fn)
        return c

    c = add("status", cmd_status, "where things stand: the map, once, or one open item with its stage, spec, Plan, "
            "claim, and blockers; --json gives its data", when="Read the current work and its next steps.",
            example="pulse status 12")
    c.add_argument("n", type=int, nargs="?")
    c.add_argument("--json", action="store_true")
    c.add_argument("--fresh", action="store_true", help="skip the cache")
    c = add("approve", cmd_approve, "queue final integration approval for the cached, reviewed result and base",
            when="Manual final policy is selected and you have reviewed the current result.", example="pulse approve 12")
    c.add_argument("n", type=int, nargs="+")

    c = add("levers", cmd_levers, "show, ask for, or end the person's lever grants for attended Claude Code "
            "sessions; Claude Code asks the person to confirm a grant",
            when="An attended session should pull approve, defer, resume, take over, merge and base pushes itself.",
            example="pulse levers allow session")
    c.add_argument("action", nargs="?", choices=("allow", "off"))
    c.add_argument("scope", nargs="?", choices=("run", "session", "always"))

    c = add("retry", cmd_retry, "retry a saved action after a synchronization error; keep its original binding",
            when="A saved action reports a synchronization error.", example="pulse retry operation-id")
    c.add_argument("operation", help="the operation ID shown in Pulse's synchronization state")

    for name, description, when in (
            ("defer", "queue a stop and pause while preserving the item's work", "Pause work you want to keep."),
            ("resume", "queue resumption of preserved work after its stop is confirmed", "Continue a deferred item."),
            ("revoke", "queue withdrawal of the item's integration approval", "Withdraw a previous final approval."),
            ("handoff", "queue an explicit claim handoff while preserving its work", "Give retained work to another writer."),
            ("discard", "stop an item and close it as not planned, without removing code or specs",
             "Abandon an item after reviewing the proposed closure."),
            ("delete", "prepare removal of an item's code and specs, then delete its issue and comments",
             "Remove an item after reviewing and confirming its removal scope.")):
        command = add(name, cmd_lifecycle, description, when=when, example=f"pulse {name} 12")
        command.add_argument("n", type=int)

    c = add("auto", cmd_auto, "show or configure final integration approval; automatic by default",
            when="Inspect the final policy, or deliberately choose automatic or manual integration.", example="pulse auto")
    c.add_argument("gate", nargs="?", choices=auto.GATES, help="merge: final approval for verified regular results")
    c.add_argument("switch", nargs="?", choices=["on", "off"])
    c.add_argument("--for", dest="span", type=auto.span, metavar="8h|2d",
                   help="expire automatic final approval after this duration")

    c = add("go", cmd_go, "process the queue, optionally with a saved goal; Pulse manages the runner without a terminal. "
            "Example: pulse go Improve checkout. Use --epic or --item to restrict the run",
            when="Start or continue permitted work through its checks and integration.", example="pulse go Improve checkout")
    c.add_argument("objective", nargs="*", metavar="goal", help="optional goal words, added to queue work")
    scope = c.add_mutually_exclusive_group()
    scope.add_argument("--epic", metavar="EPIC-04", help="restrict work to this logical epic (or #4 for its issue)")
    scope.add_argument("--item", type=int, metavar="12", help="restrict work to this item number")
    controls = c.add_mutually_exclusive_group()
    controls.add_argument("--pause", action="store_true", help="save a goal pause for the runner's next transition")
    controls.add_argument("--resume", action="store_true", help="resume the saved goal and start or reuse the runner")
    controls.add_argument("--steer", metavar="text", help="append direction to the saved goal without starting a runner")
    controls.add_argument("--stop", action="store_true", help="request a controlled stop of this clone's current run")

    c = add("publish-plan", cmd_publish_plan, "publish the selected retained Plan through normal project hooks",
            when="The item view offers publication of a retained Plan.",
            example="pulse publish-plan 12 --worktree /path/to/item --path _devprocess/plans/12-login.md --content saved-content-id")
    c.add_argument("n", type=int)
    for key in ("worktree", "path", "content"):
        c.add_argument("--" + key, required=True, help="the selected Plan's " + key)

    c = add("map", cmd_map, "live map in the terminal: who does what, what goes out next",
            when="Watch progress or inspect an item's available actions.", example="pulse map")
    c.add_argument("--ensure", action="store_true", help="open a live map where you work unless this clone "
                   "has one; PULSE_MAP=off turns it off")

    s = add("setup", cmd_setup, "activate Pulse here: config, anchor blocks, labels; "
            "--cli and --codex-rules set up this machine", when="Activate Pulse or update project settings.",
            example='pulse setup --agent codex --verify "python3 -m pytest"')
    s.add_argument("--check-plan", action="store_true",
                   help="only retry Plan commit compatibility against the current trusted base; change no setup files")
    s.add_argument("--mode", choices=["on", "off"], help="default: keep the current mode, else on")
    s.add_argument("--cap", type=int, help="agents pulse go runs at once (default: keep, else 4)")
    s.add_argument("--base-branch", help="default: keep, else the DIA source branch, else origin's default")
    s.add_argument("--files", nargs="*", help="agent files to write (default: those that exist): AGENTS.md carries the "
                                              "anchor block, CLAUDE.md gets the line @AGENTS.md that imports it")
    s.add_argument("--labels", action="store_true", help="create the pulse:* labels on GitHub")
    s.add_argument("--remove", action="store_true",
                   help="remove the anchor blocks, the @AGENTS.md line setup set in CLAUDE.md, and a git hook an "
                        "older Pulse installed; with --cli or --codex-rules, those files instead")
    s.add_argument("--agent", help="agents pulse go starts headless: claude, codex, or claude:2,codex:2")
    s.add_argument("--verify", help="the command that runs the project's tests; pulse go runs it before review")
    s.add_argument("--anchors", action="store_true",
                   help="rewrite only the Pulse block in the agent files that have one, and move one in CLAUDE.md "
                        "to AGENTS.md, leaving the import line; config and labels stay")
    s.add_argument("--cli", action="store_true",
                   help="the pulse command in ~/.local/bin; it runs the Pulse in $PULSE_HOME, else the agent's "
                        "own: a Codex session the newest in the Codex cache, a Claude Code session the newest "
                        "in the Claude Code plugin cache; a terminal the newest of both")
    s.add_argument("--codex-rules", action="store_true",
                   help="Codex runs pulse without asking and never a person's lever: approve, auto <gate>, "
                        "defer, resume, revoke, handoff, done, claim --take, release --take, pulse -- <command>, "
                        "gh pr merge and ready, gh issue edit, close, and reopen")
    s.add_argument("--dry-run", action="store_true")

    for name, fn, text, take, when in (
            ("release", cmd_release, "give an item back",
             "also from another session of mine, or hand another person's claim over (with a comment)",
             "Your session has preserved its work and will stop writing this item."),
            ("claim", cmd_claim, "hold an item for this session; exit 1 names why: closed, on hold, "
                                 "blocked, a file another item holds, or held by another person or session",
             "take over from a session of mine that has ended", "Acquire exclusive ownership before item work.")):
        c = add(name, fn, text, plumb=name == "claim", when=when, example=f"pulse {name} 12")
        c.add_argument("n", type=int)
        c.add_argument("--take", action="store_true", help=f"right after {name}: {take}")

    c = add("new", cmd_new, "create the record of an item on the board (a GitHub issue) for a spec, "
            "or a draft without one; print its number", plumb=True,
            when="Register an authorized work item before preparing its spec.",
            example='pulse new feat "Improve checkout" --draft')
    c.add_argument("type", choices=state.TYPES)
    c.add_argument("title")
    c.add_argument("--parent", type=int)
    c.add_argument("--blocked-by", type=_numbers, help="comma-separated issue numbers")
    what = c.add_mutually_exclusive_group(required=True)
    what.add_argument("--spec", help="the spec file in the repository, committed and ready (R2 to R6); on a spec "
                                     "branch pulse new publishes it; the record on the board links its spec and carries its priority")
    what.add_argument("--draft", action="store_true", help="no spec yet: a record claimed for the work on it")
    c.add_argument("--phase", choices=["analysis", "spec"], default="spec",
                   help="with --draft: the work (default: spec)")
    c.add_argument("--base", action="store_true",
                   help="label it pulse:base: it repairs the base or the Plan commit gates, and pulse go plans and "
                        "builds it while they hold other work")
    c.add_argument("--issue", type=int,
                   help="an open issue without a spec (a draft, an issue from the BA) instead of a new one: "
                        "with --spec it links the spec and takes <title> as its title, "
                        "with --draft it becomes the draft")
    c = add("check", check.main, "drift a script can see: links, paths, state, caps, stubs", plumb=True,
            when="Validate a spec or Plan, or inspect project consistency.",
            example="pulse check --plan _devprocess/plans/12-login.md")
    only = c.add_mutually_exclusive_group()
    only.add_argument("--spec", nargs="+", action="extend", metavar="PATH", help="only R1 to R6, on these spec "
                   "files as they are here: the structural checks before planning; asks GitHub nothing")
    only.add_argument("--plan", nargs="+", action="extend", metavar="PATH", help="all P1 to P6 on local Plans "
                      "against the available base spec and config; offline, runs no tests and grants no approval")
    c = add("number", cmd_number, "start each spec's file name with its ID (EPIC-04, FEAT-04-02): shows the moves, --apply makes them",
            when="Preview logical IDs and path changes before applying them.", example="pulse number")
    c.add_argument("--apply", action="store_true", help="rename them, rewrite the paths to them, "
                                                        "and move their records along")
    c = add("migrate", cmd_migrate, "DIA project -> Pulse: preview, then --local, then --issues", plumb=True,
            when="Bring an existing DIA project into Pulse while preserving its work.", example="pulse migrate --offline")
    step = c.add_mutually_exclusive_group()
    step.add_argument("--local", action="store_true",
                      help="config, anchors, frontmatter; preserves project hooks and their DIA inputs")
    step.add_argument("--issues", action="store_true",
                      help="open backlog items -> records on the board; the backlog goes once every row is "
                           "carried over")
    c.add_argument("--offline", action="store_true", help="preview without matching existing issues")
    c.add_argument("--json", action="store_true")
    p.epilog = "plumbing, for skills, hooks, and pulse go:\n" + "\n".join(plumbing)
    return p


def command_help() -> list[str]:
    """Read the active parser's reference, including commands hidden from its ordinary list."""
    sub = next(a for a in parser()._actions if isinstance(a, argparse._SubParsersAction))
    listed = {a.dest for a in sub._choices_actions}
    lines = []
    for public, title in ((True, "Commands"), (False, "Plumbing (for skills, hooks, and pulse go)")):
        lines += [title, ""]
        for name, command in sub.choices.items():
            if (name in listed) == public:
                lines += command.format_help().splitlines() + [""]
    return lines


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = parser()
    args = p.parse_args(argv if argv else ["status"])
    args.welcome = not argv
    if getattr(args, "take", False) and argv[:2] != [args.cmd, "--take"]:
        # a Codex rule sees only how a command starts (setup.CODEX_RULES): elsewhere it would run unasked
        p.error(f"--take goes right after the command: pulse {args.cmd} --take <n>")
    try:
        return args.func(args)
    except state.StateError as e:
        print(f"pulse: {e}")
        return 2
