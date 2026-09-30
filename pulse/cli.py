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

from pulse import auto, check, config, go, lifecycle, mapstart, merge, migrate, ready, setup, spec, state
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
    root = config.find_root()
    if root is not None and config.load(root)["mode"] is None:      # asks GitHub nothing
        note = ("Pulse is not active here (no .pulse/config.toml): /pulse (in Codex $pulse:pulse) sets it up, "
                "or pulse setup activates it.")
        print(json.dumps({"active": False, "note": note}) if args.json else note)
        return 0
    if args.n is not None:
        return _item(args)
    root, repo, run = _ctx()
    note = ""
    try:
        state.load(root, repo, run=run, fresh=args.fresh)
    except state.StateError as e:
        note = f"the board could not be read: {e}"
    _fetch(root)               # waits, with a time limit: the ramp below counts every clone's PLANs
    vm = pmap.gather(root)
    vm["error"] = vm["error"] or note
    vm["last_run"] = go.last_run(root)
    print(json.dumps(vm, indent=2) if args.json else pmap.once(vm, sys.stdout.isatty()) + _last_run(vm["last_run"]))
    return 2 if vm["error"] and not state.cache_path(root).is_file() else 0   # nothing known: no board to show


def _last_run(rep) -> str:
    """How the last pulse go run went: when it ended, its results per kind, and what failed and why."""
    if not rep:
        return ""
    run, items = rep["run"], rep.get("items") or {}
    counts = collections.Counter(i.get("result") for i in items.values())
    when = (f"runs since {run.get('started')} (pid {run.get('pid')})" if run["running"] else
            f"ended {run['ended']}" + (f", stopped by {run['stopped']}" if run.get("stopped") else "")
            if run.get("ended") else "ended without its cleanup; the next pulse go takes over what it held")
    lines = [f"last pulse go run: {when}: " + (", ".join(f"{c} {k}" for k, c in counts.items()) or "no results")]
    lines += [f"  #{n} failed: {i.get('why')}" for n, i in items.items() if i.get("result") == "failed"]
    return "\n" + "\n".join(map(ready.printable, lines))     # a why quotes foreign text (#56)


def _fetch(root, now=False):
    """ready.fetch, and one line when the last fetch failed or none could run: what git said, as every
    command names it (#85), or that origin did not answer, where git said nothing; on stderr, so --json
    stays JSON."""
    got = ready.fetch(root, now=True) if now else ready.fetch(root)
    if not got:
        said = ready.fetch_said(root) if got is False else ""
        why = f"git fetch said: {said}" if said else \
            "offline: origin did not answer" if got is False else "no fetch: .git is read-only here"
        print(why + "; the PLANs are those this clone fetched last", file=sys.stderr)


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
    behind = ready.behind(root) if got or said else None
    if behind is None:
        return "origin did not answer", None
    twin, rest = ready.conflict(behind), [b for b in behind if b not in ready.twins(behind)]     # #97
    if said:
        return "; ".join(filter(None, (f"git fetch said: {said}", twin))), behind
    return "; ".join(filter(None, (twin, rest and "the fetch went through, but refs here differ from origin: " +
                                   ", ".join(ready.printable(f"origin/{b}") for b in rest)))), behind


def _item(args):
    """pulse status <n>: one open item, its stage in the words of the map, its PLAN, claim, and blockers."""
    root, repo, run = _ctx()
    items = state.load(root, repo, run=run, fresh=args.fresh)
    i = next((i for i in items if i["number"] == args.n), None)
    if i is None:
        print(f"#{args.n} is not an open issue")
        return 1
    _fetch(root)               # as the board: the PLAN another clone pushed counts
    stages = {}                # the stage in the words of the map (#99 FR-14), without the board lines it never prints
    pmap.render(pmap.gather(root, board=False), color=0, stages=stages)
    p = ready.plans(root).get(args.n) or {}
    i = {**i, "stage": stages.get(args.n, ""), "plan": p.get("path"), "plan_ref": p.get("ref")}
    # a title or note is foreign text (#56): each line of a value through printable, as on the board, and its
    # later lines indented, so none reads as a field
    text = "\n".join("  " * (j > 0) + ready.printable(line)
                     for k, v in i.items() for j, line in enumerate(f"{k}: {v}".splitlines()))
    print(json.dumps(i, indent=2) if args.json else text)
    return 0


def cmd_go(args):
    """pulse go in the foreground of this terminal: its output is the person's, Ctrl-C stops it."""
    if _person_only("go"):
        return 1
    root = _root()
    cfg = config.load(root)
    if cfg["verify"]:          # go.run refuses without it, before its first line
        if not (go.last_run(root) or {}).get("run", {}).get("running"):
            mapstart.ensure(root)          # the live map where the user works (D-48), beside no run of this clone
        who = state.who(root, run=state.gh)          # the account the run acts as (#111)
        warn = setup.untrusted(cfg["agent"])
        print(f"pulse go: {'as ' + who + ', ' if who else ''}cap {cfg['cap']}, agents {cfg['agent']}; "
              f"Ctrl-C stops it{'; ' + warn if warn else ''}", flush=True)
    rep = go.run(root)
    stopped = rep.get("run", {}).get("stopped")
    # a PLAN that still fails P1 to P5 waits for a person, so the run is not clean
    rc = 128 + signal.Signals[stopped] if stopped else \
        1 if rep["failed"] or rep.get("halt") or any(j["why"].startswith("plan: ") for j in rep["skipped"]) else 0
    verbs = {"plan": "planning", "build": "building", "merge": "merging the base into"}
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
        state_ = "waits for your merge" if all(j[g].startswith("pass") for g in go.GATES) \
            else "draft, a gate is red"
        print(f"  done   #{j['number']} -> {j['pr']} ({gates}{rounds}, {state_}{_spent(j)})")
    for j in rep["failed"]:
        print(ready.printable(f"  failed #{j['number']}: {j['why']} (worktree {j['worktree']}, log {j['log']})"))
    for j in rep["limited"]:
        print(ready.printable(f"  limit  #{j['number']}: {j['why']} (log {j['log']})"))
    for j in rep["skipped"]:
        print(ready.printable(f"  skipped #{j['number']}: {j['why']}"))
    for n in rep.get("merged", []):
        print(f"  closed #{n}: its pull request was merged")
    for j in rep.get("stopped", []):
        print(ready.printable(f"  stopped #{j['number']} in {j['phase']} ({j['why']})"))
    for u in rep.get("unclean", []):
        print(ready.printable(f"  kept the worktree of closed #{u['number']}, it has changes: {u['worktree']}"))
    if rep.get("halt"):
        print(ready.printable(f"  held: {rep['halt']}"))     # a hook's name and git's words (L-4)
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
    with mapstart.noted(root):
        return pmap.main(args)


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
    from is refused; on a spec branch the spec goes to origin and into the branch's docs PR (#116)."""
    root, repo, run = _ctx()
    args.title = spec.with_id(args.spec, args.title)          # FEAT-04-02 Speech input, on the board too
    pr, labels = None, []
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
            pr = state.docs_pr(root, repo, branch, base, f"docs: {args.title}", run=run)
        else:                  # the base branch, or a build branch: its own PR brings the spec along
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
    if args.draft and not args.issue:      # one draft per type and title: two people start the same realign or BA
        same = next((i for i in state.load(root, repo, run=run, fresh=True) if i.get("draft")
                     and i["type"] == args.type and i["title"].casefold() == args.title.casefold()), None)
        if same:
            print(f"pulse new: #{same['number']} is the draft \"{same['title']}\" already, held by "
                  f"{same.get('claimed_by') or 'nobody'}; a free one or one of yours goes on with "
                  f"--issue {same['number']}, one another person holds stays theirs")
            return 1
    rel = {"parent": args.parent, "blocked_by": args.blocked_by or [], "pr": pr, "labels": labels}
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
    all of it under _devprocess/, and no item's build branch. Only such a branch is pushed and gets a docs PR
    (#116); a build branch reaches the base with its own PR, after its gates, even while it holds only its PLAN."""
    if branch in ("", base):
        return False
    n = state.item_of(branch)
    if n and not config.is_spec_branch(config.load(root), branch, n):     # feat/42-theme-spec is a spec branch
        return False
    changed = ready._git(root, "diff", "--name-only", "-z", f"{config.base_ref(root, base)}...HEAD").split("\0")
    return any(changed) and all(c.startswith("_devprocess/") for c in changed if c)


def link(root, repo, n, args, run):
    """Write issue and parent into the new spec; list it in the epic's Items (under its feature)."""
    path = root / args.spec
    if not spec.split(path.read_text(encoding="utf-8"))[0]:
        return
    spec.set_front(path, "issue", str(n))
    # the spec that names the parent here, else the one its record links (a done feature is a parent too)
    up = (spec.registered(root).get(args.parent) or state.spec_of(repo, args.parent, run)) if args.parent else None
    if not up or not (root / up).is_file():
        return
    spec.set_front(path, "parent", os.path.relpath(root / up, path.parent))
    feature, epic = None, root / up
    grand = spec.front(epic.read_text(encoding="utf-8")).get("parent")
    if grand:
        feature, epic = epic, (epic.parent / grand).resolve()
    rel = lambda p: os.path.relpath(p, epic.parent)
    spec.add_item(epic, n, args.title, rel(path), under=rel(feature) if feature else None)


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
    records = json.loads(run(["issue", "list", "--repo", repo, "--state", "all", "--limit", "1000",
                              "--json", "number,title,body"]))
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


def _person_only(lever):
    """Gate levers are a person's (D-21, FEAT-03-01): auto.person, no agent marker and a terminal. It holds direct
    calls only; the lever guard checks what goes into a pane."""
    if auto.person(os.environ, _tty()):
        return False
    print("pulse go: only a person does this: start it in your own terminal" if lever == "go" else
          f"pulse {lever}: only a person does this, in their own terminal or the Pulse map; tell the person "
          "which gate waits")
    return True


def _other_item(cmd, n):
    """An agent of pulse go holds as its run, which holds the run's other items too: it claims and gives back
    only the item pulse go started it for (PULSE_ITEM, #65); a session without one, none."""
    if not os.environ.get("PULSE_HOLDER") or os.environ.get("PULSE_ITEM") == str(n):
        return False
    print(f"pulse {cmd} #{n}: an agent of pulse go claims and releases only its own item")
    return True


def cmd_lifecycle(args):
    if _person_only(args.cmd):
        return 1
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
    """Write the approval each item waits for, and nothing else (#115): gate 1, gate 2 for its PLAN as origin has
    it, gate 3 for the head of its ready PR (#118), or a new try after pulse:failed. pulse go acts on it: it merges
    the docs PR, plans, builds, merges the PR."""
    if _person_only("approve"):
        return 1
    root, repo, run = _ctx()
    _fetch(root, now=True)     # the spec and PLAN as origin has them now: what a Plan-ok binds
    items = {i["number"]: i for i in state.load(root, repo, run=run, fresh=True)}
    who, code = state.who(root, run=run), 0    # the account, as the comment on each item names it (#111)
    as_ = f" as {who}" if who else ""
    for n in args.n:
        gate, blobs, why = ready.waiting(root, items[n]) if n in items else (None, (), f"#{n} is not an open item")
        if gate is None:
            print(ready.printable(why))
            code = 1
            continue
        if gate == 3:          # what waits for a person in it, named before the approval is written (L-2 of #118)
            print(merge.seen(root, repo, items[n]["pr"]["number"], run, f"#{n}"))
        state.approve(root, repo, n, gate, blobs, run=run)
        print([f"#{n}: pulse:failed is off{as_}: the next pulse go tries it again",
               f"approved #{n}{as_}" + (f" at {blobs[0][:12]} for {blobs[1]}" if gate == 1 and blobs else "") +
               ": gate 1, the team wants it built",
               f"approved the plan of #{n}{as_} at {' '.join(b[:12] for b in blobs)}: gate 2, agents may build it",
               f"approved the merge of #{n}{as_} at {' '.join(b[:12] for b in blobs)}: gate 3, pulse go merges it"][gate])
    return code


def cmd_auto(args):
    """Your auto mode per gate (#124): without a gate, every login's switches; on says what then happens without
    asking and asks once, off asks nothing. Only a person switches, in their own terminal or the Pulse map."""
    if bool(args.gate) != bool(args.switch) or args.span and args.switch != "on":
        print("pulse auto: <plan|build|merge> on [--for 8h|2d], or <gate> off; alone it shows the switches")
        return 2
    if args.switch and _person_only(f"auto {args.gate} {args.switch}"):
        return 1
    root, repo, run = _ctx()
    if not args.switch:
        print(auto.show(root, repo, run))
        return 0
    until = auto.stamp(time.time() + args.span) if args.span else None
    if args.switch == "on":
        login = state.me(root, run=run)
        print(auto.explain(args.gate, login, config.load(root)["base_branch"] or config.default_branch(root), until))
        try:
            yes = input(f"Switch on as {state.who(root, login)}? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            yes = False
        if not yes:
            print("nothing switched")
            return 1
    print(auto.toggle(root, repo, args.gate, args.switch == "on", until, run))
    return 0


def _spent(j):
    u = j.get("usage")
    return f"; {u['tokens']} tokens, ${u['cost_usd']:.2f}, {u['seconds']} s" if u else ""


def _said(result):
    ok, why = result
    print(why)
    return 0 if ok else 1


def cmd_claim(args):
    """The claim carries the files of the PLAN this clone has, so every ramp holds them without a fetch
    (WP-56). A file another running item holds refuses it, as the ramp locks it (#46)."""
    if args.take and _person_only("claim --take") or _other_item("claim", args.n):
        return 1
    root, repo, run = _ctx()
    plans = ready.plan_files(root)
    files = plans.get(args.n)
    if files:
        # ponytail: read, then claim; two claims on different items that share a file in the same
        # seconds can both win, and the ramp shows both. A read after the claim would close it.
        others = [i for i in state.load(root, repo, run=run, fresh=True) if i["number"] != args.n]
        hit = ready.clash([posixpath.normpath(f) for f in files], ready.held(others, plans))
        if hit:
            return _said((False, f"#{args.n}: {hit[0]} is in use by #{hit[1]}; start #{args.n} once #{hit[1]} is done"))
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
    if args.take and _person_only("release --take") or _other_item("release", args.n):
        return 1
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


def cmd_setup(args):
    """--cli and --codex-rules set up this machine, from anywhere; the rest sets up this project. Switching
    Pulse off or out takes the lever guard along: a person's (#106)."""
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

    def add(name, fn, text, plumb=False):
        """A command; plumbing (for skills, hooks, and pulse go) is listed apart in the help."""
        if plumb:
            plumbing.append(f"  {name:<14}{text}")
        c = sub.add_parser(name, description=text, **({} if plumb else {"help": text}))   # help= lists it
        c.set_defaults(func=fn)
        return c

    c = add("status", cmd_status, "where things stand: the map, once, or one open item with its stage, spec, PLAN, "
                                   "claim, and blockers; --json gives its data")
    c.add_argument("n", type=int, nargs="?")
    c.add_argument("--json", action="store_true")
    c.add_argument("--fresh", action="store_true", help="skip the cache")
    c = add("approve", cmd_approve, "write the approval each item waits for: gate 1 (agents may plan it), gate 2 "
                                     "(its pushed PLAN: agents may build it), or a new try after pulse:failed; "
                                     "pulse go acts on it")
    c.add_argument("n", type=int, nargs="+")

    for name, description in (
            ("defer", "stop an open item and put its unchanged work in the paused backlog"),
            ("resume", "explicitly resume an item deferred to the backlog, retaining its approvals"),
            ("discard", "stop an item and close it as not planned, without removing code or specs"),
            ("delete", "remove an item's code and specs through a reviewed PR, then delete its issue and comments")):
        command = add(name, cmd_lifecycle, description)
        command.add_argument("n", type=int)

    c = add("auto", cmd_auto, "your auto mode per gate: alone it shows every person's switches; <gate> on lets "
                              "your own pulse go pass that gate for your items without asking you, off takes it back")
    c.add_argument("gate", nargs="?", choices=auto.GATES, help="plan (gate 1), build (gate 2), merge (gate 3)")
    c.add_argument("switch", nargs="?", choices=["on", "off"])
    c.add_argument("--for", dest="span", type=auto.span, metavar="8h|2d",
                   help="with on: for so many hours or days, then off by itself")

    add("go", cmd_go, "plan and build every approved item in parallel, in the foreground of this terminal: "
                      "worktree + headless agent each, at most cap of them, agents from agent (.pulse/config.toml)")

    c = add("map", cmd_map, "live map in the terminal: who does what, what goes out next")
    c.add_argument("--ensure", action="store_true", help="open a live map where you work unless this clone "
                   "has one; PULSE_MAP=off turns it off")

    s = add("setup", cmd_setup, "activate Pulse here: config, anchor blocks, labels; "
                                "--cli and --codex-rules set up this machine")
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
                        "go, done, claim --take, release --take, pulse -- <command>, "
                        "gh pr merge and ready, gh issue edit, close, and reopen")
    s.add_argument("--dry-run", action="store_true")

    for name, fn, text, take in (
            ("release", cmd_release, "give an item back",
             "also from another session of mine, or hand another person's claim over (with a comment)"),
            ("claim", cmd_claim, "hold an item for this session; exit 1 names why: closed, not approved, "
                                 "blocked, a file another item holds, or held by another person or session",
             "take over from a session of mine that has ended")):
        c = add(name, fn, text, plumb=name == "claim")
        c.add_argument("n", type=int)
        c.add_argument("--take", action="store_true", help=f"right after {name}: {take}")

    c = add("new", cmd_new, "create the record of an item on the board (a GitHub issue) for a spec, "
                            "or a draft without one; print its number", plumb=True)
    c.add_argument("type", choices=state.TYPES)
    c.add_argument("title")
    c.add_argument("--parent", type=int)
    c.add_argument("--blocked-by", type=_numbers, help="comma-separated issue numbers")
    what = c.add_mutually_exclusive_group(required=True)
    what.add_argument("--spec", help="the spec file in the repository, committed and ready (R2 to R6); on a spec "
                                     "branch pulse new pushes it and opens the branch's docs PR, or uses the open "
                                     "one; the record on the board links spec and PR and carries its priority")
    what.add_argument("--draft", action="store_true", help="no spec yet: a record claimed for the work on it")
    c.add_argument("--phase", choices=["analysis", "spec"], default="spec",
                   help="with --draft: the work (default: spec)")
    c.add_argument("--issue", type=int,
                   help="an open issue without a spec (a draft, an issue from the BA) instead of a new one: "
                        "with --spec it links the spec and takes <title> as its title, "
                        "with --draft it becomes the draft")
    c = add("check", check.main, "drift a script can see: links, paths, state, caps, stubs", plumb=True)
    c.add_argument("--spec", nargs="+", action="extend", metavar="PATH", help="only R1 to R6, on these spec "
                   "files as they are here: what pulse go refuses before it merges them; asks GitHub nothing")
    c = add("number", cmd_number, "start each spec's file name with its ID (EPIC-04, FEAT-04-02): shows the moves, --apply makes them")
    c.add_argument("--apply", action="store_true", help="rename them, rewrite the paths to them, "
                                                        "and move their records along")
    c = add("migrate", cmd_migrate, "DIA project -> Pulse: preview, then --local, then --issues", plumb=True)
    step = c.add_mutually_exclusive_group()
    step.add_argument("--local", action="store_true",
                      help="config, anchors, frontmatter; removes .dia's tracked files and DIA's git hooks")
    step.add_argument("--issues", action="store_true",
                      help="open backlog items -> records on the board; the backlog goes once every row is "
                           "carried over")
    c.add_argument("--offline", action="store_true", help="preview without matching existing issues")
    c.add_argument("--json", action="store_true")
    p.epilog = "plumbing, for skills, hooks, and pulse go:\n" + "\n".join(plumbing)
    return p


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = parser()
    args = p.parse_args(argv)
    if getattr(args, "take", False) and argv[:2] != [args.cmd, "--take"]:
        # a Codex rule sees only how a command starts (setup.CODEX_RULES): elsewhere it would run unasked
        p.error(f"--take goes right after the command: pulse {args.cmd} --take <n>")
    try:
        return args.func(args)
    except state.StateError as e:
        print(f"pulse: {e}")
        return 2
