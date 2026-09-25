"""pulse: the command line behind the Pulse skills. Stdlib only.

Exit codes: 0 done, 1 refused (e.g. a claim someone else holds),
2 cannot act here (no repo, ambiguous remotes, gh failed).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from pulse import check, config, dispatch, go, mapstart, migrate, ready, review, setup, spec, state
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
    """The map frame once, or its view model; first, items whose PR was merged are closed
    (GitHub closes only on the default branch). The map itself only reads (ADR-06)."""
    root = config.find_root()
    if root is not None and config.load(root)["mode"] is None:      # asks GitHub nothing
        note = ("Pulse is not active here (no .pulse/config.toml): /pulse-setup (in Codex $pulse:pulse-setup), "
                "or pulse setup, activates it.")
        print(json.dumps({"active": False, "note": note}) if args.json else note)
        return 0
    root, repo, run = _ctx()
    note = ""
    try:
        state.sync_merged(root, repo, state.load(root, repo, run=run, fresh=args.fresh), run=run)
    except state.StateError as e:
        note = f"merged pull requests not checked: {e}"
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
    return "\n" + "\n".join(lines)


def _fetch(root):
    """ready.fetch, and one line when origin did not answer or no fetch could run; on stderr, so
    --json stays JSON."""
    got = ready.fetch(root)
    if not got:
        why = "offline: origin did not answer" if got is False else "no fetch: .git is read-only here"
        print(why + "; the PLANs are those this clone fetched last", file=sys.stderr)


def cmd_show(args):
    root, repo, run = _ctx()
    items = state.load(root, repo, run=run, fresh=args.fresh)
    i = next((i for i in items if i["number"] == args.n), None)
    if i is None:
        print(f"#{args.n} is not an open issue")
        return 1
    _fetch(root)               # as pulse status: the PLAN another clone pushed counts
    cfg = config.load(root)
    r = dispatch.view(root, items, cfg, state.me(root, run=run))
    p = ready.plans(root).get(args.n) or {}
    row = next((x for x in r["rows"] if x["number"] == args.n), {})
    stage = row.get("stage", "in progress" if i["assignees"] else "")
    if i["assignees"] and ready.approvable(root, items, cfg, args.n)[0]:
        stage = "plan waits for you"       # a claim changes no PLAN; /pulse-build waits for approve-plan
    i = {**i, "stage": stage, "plan": p.get("path"), "plan_ref": p.get("ref")}
    print(json.dumps(i, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in i.items()))
    return 0


def cmd_rank(args):
    if _go_agent("rank"):
        return 1
    root, repo, run = _ctx()
    items = state.load(root, repo, run=run, fresh=True)
    try:
        writes = dispatch.place(items, args.n, before=args.before, after=args.after,
                                top=args.top, bottom=args.bottom)
    except ValueError:
        print(f"pulse rank: #{args.n} and the item it goes next to must both be open and free")
        return 1
    for n, value in writes:
        state.set_rank(root, repo, n, value, run=run)
    print(f"#{args.n} moved; {len(writes)} record{'s' if len(writes) != 1 else ''} written")
    return 0


def cmd_go(args):
    root = _root()
    # the live map where the user works, before a detached run starts (D-48), for a run its start
    # checks let through: go.run refuses without verify and beside a run of this clone
    if not (args.dry_run or args.json or (go.last_run(root) or {}).get("run", {}).get("running")) \
            and config.load(root)["verify"]:
        mapstart.ensure(root)
    if args.detach:
        return _detach(root, args)
    rep = go.run(root, cap=args.cap, agent=args.agent, dry_run=args.dry_run)
    stopped, mix = rep.get("run", {}).get("stopped"), rep.get("integration") or {}
    clash = mix.get("error") or mix.get("conflict") or not (mix.get("verify") or {}).get("ok", True)
    # a PLAN that still fails P1 to P5 waits for a person, so the run is not clean; neither is a clash
    rc = 128 + signal.Signals[stopped] if stopped else \
        1 if rep["failed"] or clash or any(j["why"].startswith("plan: ") for j in rep["skipped"]) else 0
    if args.json:
        print(json.dumps(rep, indent=2))
        return rc
    verbs = {"plan": "would plan", "build": "would build", "resume": "would take up"} if args.dry_run else \
        {"plan": "planning", "build": "building", "resume": "taking up"}
    print(f"pulse go: parallel {rep['level']}, agents {rep['agent']}")
    for n in rep.get("took", []):
        print(f"  took over #{n} from a stopped run")
    for j in rep["started"]:
        print(f"  {verbs[j['phase']]} #{j['number']} with {j['agent']} on {j['branch']} (from {j['base']}) "
              f"in {j['worktree']}")
    for j in rep.get("planned", []):
        print(f"  planned #{j['number']} -> {j['plan']} ({j['gate']}{_spent(j)})")
    for j in rep["done"]:
        rounds = f" after {j['rounds']} fix round{'s' if j['rounds'] != 1 else ''}" if j["rounds"] else ""
        gates = ", ".join(f"{g} {j[g].split(':')[0]}" for g in go.GATES)
        state_ = "waits for your merge" if all(j[g].startswith("pass") for g in go.GATES) \
            else "draft, a gate is red"
        print(f"  done   #{j['number']} -> {j['pr']} ({gates}{rounds}, {state_}{_spent(j)})")
    for j in rep["failed"]:
        print(f"  failed #{j['number']}: {j['why']} (worktree {j['worktree']}, log {j['log']})")
    for j in rep["limited"]:
        print(f"  limit  {j['agent']} hit its usage limit on #{j['number']}; #{j['number']} went back "
              f"to the ramp (log {j['log']})")
    for j in rep["skipped"]:
        print(f"  skipped #{j['number']}: {j['why']}")
    for n in rep.get("merged", []):
        print(f"  closed #{n}: its pull request was merged")
    if rep.get("sync_error"):
        print(f"  merged pull requests not checked: {rep['sync_error']}")
    found = {}                 # an agent may write a whole page: its first line here, all of it in discovered.md
    for d in rep["discovered"]:
        found.setdefault(d["from"], []).append(d["item"])
    for n, lines in found.items():
        more = f"and {len(lines) - 1} more line{'s' if len(lines) > 2 else ''} " if len(lines) > 1 else ""
        print(f"  discovered while building #{n}: {lines[0]} ({more}in "
              f"{Path(rep['report']).with_name('discovered.md')})")
    for j in rep.get("stopped", []):
        print(f"  stopped #{j['number']} in {j['phase']} ({j['why']})")
    for u in rep.get("unclean", []):
        print(f"  kept the worktree of closed #{u['number']}, it has changes: {u['worktree']}")
    if mix.get("error"):
        print(f"  integration not checked: {mix['error']}")
    elif mix:
        print(f"  integration on {mix['base']}: merged " + (", ".join(mix["merged"]) or "nothing"))
        if mix["conflict"]:
            print(f"  CONFLICT: {mix['conflict']['branch']} does not merge after the branches above")
        if mix["verify"]:
            print(f"  verify `{mix['verify']['command']}`: {'ok' if mix['verify']['ok'] else 'FAILED'}")
            print("\n".join("    " + l for l in mix["verify"]["tail"]))
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
    if root is None or args.demo or args.once or not sys.stdout.isatty():
        return pmap.main(args)
    with mapstart.noted(root):
        return pmap.main(args)


def _detach(root, args):
    """pulse go apart from this terminal or chat session: a session of its own, its output in
    run.log, its results in report.json (F2.07). It waits up to 10 s for the run to hold its lock
    (go.pid names it) and for a board read since its start (the cache); a run that ended before,
    e.g. refused without verify or unable to read the board, prints what it wrote and returns its
    exit code."""
    common = config.pulse_dir(root)
    log = common / "go" / "run.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    argv = [str(setup.PULSE_BIN), "go"] + (["--agent", args.agent] if args.agent else []) + \
        (["--cap", str(args.cap)] if args.cap else [])
    with open(log, "a", encoding="utf-8") as out:
        out.write(f"--- pulse go --detach, {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        out.flush()
        since, started = out.tell(), time.time()
        p = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             start_new_session=True)
    end = time.time() + 10
    while p.poll() is None and time.time() < end:
        try:           # the board read after the lock is where gh fails: offline, no login (f9-docs)
            if (common / "go.pid").read_text().strip() == str(p.pid) and \
                    json.loads(state.cache_path(root).read_text(encoding="utf-8"))["fetched_at"] >= started:
                break
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    if p.returncode is not None:
        with open(log, encoding="utf-8") as f:
            f.seek(since)
            print(f.read(), end="")
        return p.returncode
    print(f"pulse go runs detached, pid {p.pid}: log {log}, report {log.with_name('report.json')}; "
          f"pulse status shows how far it got, kill {p.pid} stops it")
    return 0


def cmd_review(args):
    """pulse review / pulse audit: a fresh session over an item's branch or any scope."""
    root = _root()
    scope = args.scope or ("branch" if args.n is not None else "working")
    if scope == "range" and not args.rng:
        raise state.StateError("--scope range needs --range A..B")
    if (args.record or args.publish) and args.n is None:
        raise state.StateError("--record and --publish keep the verdict of an item: give its number")
    if args.publish:
        done = review.publish(root, args.n, state.gh)
        print(json.dumps({"number": args.n, "published": done}, indent=2) if args.json else
              f"#{args.n}: " + (f"published on the PR: {', '.join(done)}" if done else
                                "nothing new for an open PR of this branch"))
        return 0
    item = {}
    if args.n is not None:
        item = next((i for i in state.cached(root) if i["number"] == args.n), None)
    if item is None:           # not in the cache: ask the board once, work without it offline
        try:
            item = next((i for i in state.load(root, state.repo(root)) if i["number"] == args.n), {})
        except state.StateError:
            item = {}
    title, spec_path = item.get("title", ""), item.get("spec")
    if not (args.run or args.record):
        b = review.brief(root, args.n, title, spec_path, args.base, scope, args.rng) if args.kind == "review" \
            else review.audit_brief(root, args.n, title, args.base, scope, args.rng)
        print(json.dumps(b, indent=2) if args.json else b["prompt"])
        return 0
    rec = review.run(root, args.n, title, spec_path, args.base, args.agent, args.kind, scope, args.rng) \
        if args.run else review.record(root, args.n, args.kind)
    if args.n is not None and rec["verdict"]:
        try:                   # on top of the kept verdict: GitHub's answer changes nothing kept here
            rec["published"] = review.publish(root, args.n, state.gh)
        except (state.StateError, OSError) as e:
            rec["unpublished"] = str(e)
    if args.json:
        print(json.dumps(rec, indent=2))
    else:
        where = f" ({rec['path']})" if rec.get("path") else ""
        print(f"{f'#{args.n}' if args.n is not None else scope}: " +
              (f"{rec['verdict']}{where}" if rec["verdict"] else f"no verdict, {rec['why']}"))
        if args.n is None and rec.get("report"):
            print(rec["report"])
        if rec.get("published"):
            print(f"published on the PR: {', '.join(rec['published'])}")
        if rec.get("unpublished"):
            print(f"not published on the PR: {rec['unpublished']}")
    return {"pass": 0, "block": 1}.get(rec["verdict"], 2)


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
            how = f"reuse #{a['match']}" if a["match"] else "new issue"
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
    --issue makes an issue that links no spec that record or that draft (D-43)."""
    root, repo, run = _ctx()
    if not args.draft:
        if not (root / args.spec).is_file():
            print(f"pulse new: write the spec first, {args.spec} does not exist in the repository")
            return 2
        branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                                capture_output=True, text=True).stdout.strip()
        ready.net_git(root, "fetch", "-q", "origin", branch)
        here = spec.on_base(root, args.spec, "HEAD")
        if here is None or here != spec.on_base(root, args.spec, f"origin/{branch}"):
            print(f"pulse new: {args.spec} is not on origin as committed here; "
                  f"commit it, then: git push -u origin {branch}")
            return 2
    rel = {"parent": args.parent, "blocked_by": args.blocked_by or []}
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


def link(root, repo, n, args, run):
    """Write issue and parent into the new spec; list it in the epic's Items (under its feature)."""
    path = root / args.spec
    if not spec.split(path.read_text(encoding="utf-8"))[0]:
        return
    spec.set_front(path, "issue", str(n))
    up = state.spec_of(repo, args.parent, run) if args.parent else None     # a done feature is a parent too
    if not up or not (root / up).is_file():
        return
    spec.set_front(path, "parent", os.path.relpath(root / up, path.parent))
    feature, epic = None, root / up
    grand = spec.front(epic.read_text(encoding="utf-8")).get("parent")
    if grand:
        feature, epic = epic, (epic.parent / grand).resolve()
    rel = lambda p: os.path.relpath(p, epic.parent)
    spec.add_item(epic, n, args.title, rel(path), under=rel(feature) if feature else None)


def _refs(numbers):
    return ", ".join(f"#{n}" for n in numbers)


def cmd_block(args):
    root, repo, run = _ctx()
    state.block(root, repo, args.n, args.by, run=run)
    print(f"#{args.n} waits for {_refs(args.by)}")
    return 0


def _go_agent(lever):
    """Gate levers are a person's: an agent that pulse go started carries PULSE_HOLDER (D-21)."""
    if not os.environ.get("PULSE_HOLDER"):
        return False
    print(f"pulse {lever}: only a person does this, not an agent that pulse go started")
    return True


def cmd_approve(args):
    if _go_agent("approve"):
        return 1
    root, repo, run = _ctx()
    if args.undo:
        state.approve(root, repo, args.n, run=run, undo=True)
        print(f"approval taken back from {_refs(args.n)}")
        return 0
    items = {i["number"]: i for i in state.load(root, repo, run=run)}
    branch = config.load(root)["base_branch"] or config.default_branch(root)
    ready.net_git(root, "fetch", "-q", "origin", branch)
    base = config.base_ref(root, branch)
    refused = {}
    for n in args.n:           # agents plan from the base branch, so the spec is merged first (R1, D-19);
        i = items.get(n) or {}  # there pulse check holds a work item's spec to R2 to R6 too, in every commit
        why = spec.refusal(spec.on_base(root, i["spec"], base) if i.get("spec") else None, i.get("type"), n, base)
        if why:
            refused[n] = why
    good = [n for n in args.n if n not in refused]
    if good:
        state.approve(root, repo, good, run=run)
        print(f"approved {_refs(good)}: the team wants {'it' if len(good) == 1 else 'them'} built")
    for n, why in refused.items():
        print(f"#{n} not approved: {why}")
    return 1 if refused else 0


def cmd_approve_plan(args):
    """Only a PLAN that waits for a person and passes P1 to P5, and only the PLAN as it is now:
    the pushed one when the item's branch on origin moved past the copy here (ready.plans)."""
    if _go_agent("approve-plan"):
        return 1
    root, repo, run = _ctx()
    _fetch(root)
    items, cfg, code = state.load(root, repo, run=run, fresh=True), config.load(root), 0
    for n in args.n:
        d, why = ready.approvable(root, items, cfg, n)
        if not d:
            print(why)
            code = 1
            continue
        state.approve_plan(root, repo, n, d, run=run)
        p = ready.plans(root).get(n)
        goal = spec.sections(p["text"]).get("goal", "").strip().split("\n")[0] if p else ""
        where = f" on {p['ref']}" if p and p["ref"] else ""
        print(f"PLAN of #{n} approved as it is now{where} ({d})" + (f": {goal}" if goal else ""))
    return code


def _spent(j):
    u = j.get("usage")
    return f"; {u['tokens']} tokens, ${u['cost_usd']:.2f}, {u['seconds']} s" if u else ""


def _said(result):
    ok, why = result
    print(why)
    return 0 if ok else 1


def cmd_beat(args):
    """A sign of life for skills: this session's claim mark on n names the phase and the time now."""
    root, repo, run = _ctx()
    wrote = state.beat(root, repo, args.n, args.phase, run=run)
    print(f"#{args.n}: {args.phase}" if wrote else
          f"#{args.n}: this session holds no claim on it, nothing written")
    return 0


def cmd_claim(args):
    """The claim carries the files the work changes, so every ramp holds them without a fetch (WP-56):
    those of the PLAN this clone has, or --files for work without one (hotfix lane)."""
    root, repo, run = _ctx()
    files = args.files or dispatch.plan_files(root).get(args.n)
    rc = _said(state.claim(root, repo, args.n, run=run, take=args.take, files=files))
    if rc == 0:
        mapstart.ensure(root)
    return rc


def cmd_release(args):
    """--take also hands over another person's claim (D-13)."""
    if args.take and _go_agent("release --take"):
        return 1
    root, repo, run = _ctx()
    return _said(state.release(root, repo, args.n, run=run, take=args.take, take_person=args.take, note=args.note))


def cmd_done(args):
    if _go_agent("done"):
        return 1
    root, repo, run = _ctx()
    return _said(state.done(root, repo, args.n, run=run, take=args.take))


def cmd_setup(args):
    """--cli and --codex-rules set up this machine, from anywhere; the rest sets up this project."""
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

    c = add("status", cmd_status, "where things stand: the map, once; --json gives its data")
    c.add_argument("--json", action="store_true")
    c.add_argument("--fresh", action="store_true", help="skip the cache")
    c = add("show", cmd_show, "one open item")
    c.add_argument("n", type=int)
    c.add_argument("--json", action="store_true")
    c.add_argument("--fresh", action="store_true")
    c = add("approve", cmd_approve, "the team wants these items built")
    c.add_argument("n", type=int, nargs="+")
    c.add_argument("--undo", action="store_true", help="take the approval back")
    c = add("approve-plan", cmd_approve_plan, "a person approves these items' PLANs")
    c.add_argument("n", type=int, nargs="+")
    c = add("rank", cmd_rank, "put an item in the team order: before or after another, top or bottom")
    c.add_argument("n", type=int)
    where = c.add_mutually_exclusive_group(required=True)
    where.add_argument("--before", type=int)
    where.add_argument("--after", type=int)
    where.add_argument("--top", action="store_true")
    where.add_argument("--bottom", action="store_true")

    c = add("go", cmd_go, "build every ready item in parallel: worktree + headless agent each")
    c.add_argument("--agent", help="agents from [agents] with their slots, e.g. claude:2,codex:2 "
                                   "(default: config 'agent')")
    c.add_argument("--cap", type=int, help="parallel slots for this run (default: config 'cap')")
    how = c.add_mutually_exclusive_group()
    how.add_argument("--dry-run", action="store_true", help="show what would start, change nothing")
    how.add_argument("--detach", action="store_true",
                     help="run apart from this terminal or chat, overnight: log and report in .git/pulse/go")
    c.add_argument("--json", action="store_true")

    c = add("map", cmd_map, "live map in the terminal: who does what, what goes out next")
    c.add_argument("--once", action="store_true", help="print one frame and exit")
    c.add_argument("--ensure", action="store_true", help="open a live map where you work unless this clone "
                   "has one; map_autostart = false in .pulse/config.toml or PULSE_MAP=off turns it off")
    c.add_argument("--demo", action="store_true", help="sample data, no repo needed")
    c.add_argument("--no-color", action="store_true")
    c.add_argument("--color", action="store_true", help="force color when piping")

    s = add("setup", cmd_setup, "activate Pulse here: config, anchor blocks, labels; "
                                "--cli and --codex-rules set up this machine")
    s.add_argument("--mode", choices=["on", "off"], help="default: keep the current mode, else on")
    s.add_argument("--cap", type=int, help="parallel slots for /pulse-go (default: keep, else 4)")
    s.add_argument("--base-branch", help="default: keep, else the DIA source branch, else origin's default")
    s.add_argument("--files", nargs="*", help="agent files for the anchor block (default: those that exist)")
    s.add_argument("--labels", action="store_true", help="create the pulse:* labels on GitHub")
    s.add_argument("--remove", action="store_true",
                   help="remove the anchor blocks and the git hook; "
                        "with --cli or --codex-rules, those files instead")
    s.add_argument("--parallel", choices=["off", "items", "max"], help="how far pulse go parallelizes")
    s.add_argument("--agent", help="agents pulse go starts headless: claude, codex, or claude:2,codex:2")
    s.add_argument("--verify", help="the command that runs the project's tests; pulse go runs it before review")
    s.add_argument("--plan-approval", choices=["auto", "manual"],
                   help="auto builds a PLAN nothing holds; manual waits for pulse approve-plan")
    s.add_argument("--git-hook", action="store_true",
                   help="install a pre-commit hook: protected branches + pulse check")
    s.add_argument("--cli", action="store_true",
                   help="the pulse command in ~/.local/bin; it runs the Pulse in $PULSE_HOME, else the newest "
                        "in the Claude Code plugin cache, else the newest in the Codex cache")
    s.add_argument("--codex-rules", action="store_true",
                   help="Codex runs pulse without asking, except approve, approve-plan, rank, done, "
                        "release, claim, and pulse -- <command>")
    s.add_argument("--dry-run", action="store_true")

    for name, fn, text, take in (
            ("release", cmd_release, "give an item back",
             "also from another session of mine, or hand another person's claim over (with a comment)"),
            ("done", cmd_done, "close an item", "close it whoever holds it"),
            ("claim", cmd_claim, "hold an item for this session; exit 1 when another person or session has it",
             "take over from a session of mine that has ended")):
        c = add(name, fn, text, plumb=name == "claim")
        c.add_argument("n", type=int)
        c.add_argument("--take", action="store_true", help=take)
        if name == "release":
            c.add_argument("--note", default="", help="why, and where the work is, for whoever takes it next")
        if name == "claim":
            c.add_argument("--files", nargs="+", metavar="PATH", help="the files the work changes, "
                           "for work without a PLAN (hotfix lane); default: those of its PLAN here")

    c = add("new", cmd_new, "create an issue for a spec, or a draft without one; print its number", plumb=True)
    c.add_argument("type", choices=state.TYPES)
    c.add_argument("title")
    c.add_argument("--parent", type=int)
    c.add_argument("--blocked-by", type=_numbers, help="comma-separated issue numbers")
    what = c.add_mutually_exclusive_group(required=True)
    what.add_argument("--spec", help="the spec file in the repository, committed and pushed; "
                                     "the record on the board only links it")
    what.add_argument("--draft", action="store_true", help="no spec yet: a record claimed for the work on it")
    c.add_argument("--phase", choices=["analysis", "spec"], default="spec",
                   help="with --draft: the work (default: spec)")
    c.add_argument("--issue", type=int,
                   help="an open issue without a spec (a draft, an issue from the BA) instead of a new one: "
                        "with --spec it links the spec and takes <title> as its title, "
                        "with --draft it becomes the draft")
    c = add("beat", cmd_beat, "a sign of life: this session's claim on n names its phase and time", plumb=True)
    c.add_argument("n", type=int)
    c.add_argument("phase")
    c = add("block", cmd_block, "item n waits until the given items are done", plumb=True)
    c.add_argument("n", type=int)
    c.add_argument("--by", type=_numbers, required=True, help="comma-separated item numbers")
    for kind, what, report in (("review", "a fresh session reviews", "REVIEW.md"),
                               ("audit", "a fresh session audits the security of", "AUDIT.md")):
        c = add(kind, cmd_review, f"{what} an item's branch or any scope", plumb=True)
        c.add_argument("n", type=int, nargs="?", help="the item; its verdict is kept for its PR")
        c.add_argument("--scope", choices=review.SCOPES,
                       help="default: branch with an item, else working (the current work)")
        c.add_argument("--base", help="the branch scope measures against this ref (default: the base branch)")
        c.add_argument("--range", dest="rng", help="A..B for --scope range")
        how = c.add_mutually_exclusive_group()
        how.add_argument("--run", action="store_true", help="start the session headless and read its verdict")
        how.add_argument("--record", action="store_true", help=f"keep the {report} a subagent wrote")
        how.add_argument("--publish", action="store_true",
                         help="put the kept review and audit verdicts for HEAD on the open PR of this branch")
        c.add_argument("--agent", help="agent template from [agents] (default: review_agent, else agent)")
        c.add_argument("--json", action="store_true")
        c.set_defaults(kind=kind)
    c = add("check", check.main, "drift a script can see: links, paths, state, caps, stubs", plumb=True)
    c.add_argument("--spec", nargs="+", action="extend", metavar="PATH", help="only R1 to R6, on these spec "
                   "files as they are here: what pulse approve refuses once they are merged; asks GitHub nothing")
    c = add("migrate", cmd_migrate, "DIA project -> Pulse: preview, then --local, then --issues", plumb=True)
    step = c.add_mutually_exclusive_group()
    step.add_argument("--local", action="store_true",
                      help="config, anchors, frontmatter; removes .dia's tracked files and DIA's git hooks")
    step.add_argument("--issues", action="store_true",
                      help="open backlog items -> GitHub issues; the backlog goes once every row is carried over")
    c.add_argument("--offline", action="store_true", help="preview without matching existing issues")
    c.add_argument("--json", action="store_true")
    p.epilog = "plumbing, for skills, hooks, and pulse go:\n" + "\n".join(plumbing)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except state.StateError as e:
        print(f"pulse: {e}")
        return 2
