"""The ramp: what goes out next, without two agents stepping on each other.

Pulse orchestrates; the map shows it and writes only the order and
approvals (ADR-06). Two hard constraints decide:
  1. every blocker is closed (GitHub knows the blocked-by edges), or the item
     stacks on its one blocker whose PR is ready
  2. items that run at the same time touch disjoint files (their PLANs
     list them under `files:`)
The order is the team's rank; a blocker carries the rank of what waits
for it, and unranked items follow the critical path. Files of anyone's
running item are held; only my own running items take my bays (the `cap`
in .pulse/config.toml).

An item goes out only when nothing gates it (ready.gates): approved, its
spec ready, a PLAN that passes P1 to P5 and is approved. Without a PLAN it
waits at "needs a plan" until pulse go has planned it.

The parallel level (.pulse/config.toml) sets how far this goes: `off` runs
one item at a time, `items` runs independent items side by side, `max`
also runs the task waves inside an item as parallel subagents. At every
level a dependent stacks on its one open blocker once that blocker's PR is
ready (it passed tests, review, and audit).
"""
from __future__ import annotations

import posixpath
from pathlib import Path

from pulse import ready, state


def plan_files(root: Path, found: dict = None) -> dict:
    """{issue number: [files]} from the frontmatter of every PLAN, each spelled one way (`./a.py`
    is `a.py`, `docs/` is `docs`)."""
    return {n: [posixpath.normpath(f) for f in ready.listed(p["text"], "files")]
            for n, p in (ready.plans(root) if found is None else found).items()}


INF = float("inf")


def effective(items: list) -> dict:
    """{n: (rank, via)}: the best rank of the item and of everything it unblocks, and whose it is.
    A blocker carries the rank of what waits for it, so the order never puts it second."""
    by = {i["number"]: i for i in items}
    memo: dict = {}

    def walk(n, seen):
        if n in memo:
            return memo[n]
        own = by[n].get("rank")
        best = (own if own is not None else INF, None)
        for m in by[n].get("blocking", []):
            if m in by and m not in seen:
                r, via = walk(m, seen | {n})
                if r < best[0]:
                    best = (r, via or m)
        memo[n] = best
        return best

    return {n: walk(n, frozenset()) for n in by}


def order(items: list) -> list:
    """The team order: effective rank, then the critical path, then the number."""
    eff, crit = effective(items), state.critical_path(items)
    return sorted(items, key=lambda i: (eff[i["number"]][0], -crit[i["number"]], i["number"]))


def _row(i: dict) -> bool:
    """A ramp row: a work item or a draft of any kind, epics too, that nobody holds (D-43). A held
    draft is in progress and stands under its holder only (#55)."""
    return not i["assignees"] and (bool(i.get("draft")) or i["type"] in state.WORK)


def place(items: list, n: int, before=None, after=None, top=False, bottom=False) -> list:
    """[(number, rank)] to write so that n stands where it was put: one record per move, the first
    sort too, so two people sorting at once end in an order one of them chose (F9.01). Only a move
    into the unranked part ranks the unranked items up to n. The rows are the ramp's: free items
    and free drafts; ValueError for anything else, as for a neighbour that is none."""
    rows = [i for i in order(items) if _row(i)]
    own = {i["number"]: i.get("rank") for i in rows}
    if n not in own:
        raise ValueError(f"#{n} is no ramp row")
    eff = effective(items)
    nums = [m for m in own if m != n]
    at = 0 if top else len(nums) if bottom else nums.index(before) if before is not None else nums.index(after) + 1
    nums.insert(at, n)
    prev = eff[nums[at - 1]][0] if at > 0 else None
    nxt = eff[nums[at + 1]][0] if at + 1 < len(nums) else None
    if prev is None:
        return [(n, 10 if nxt in (None, INF) else nxt - 10)]
    if prev not in (None, INF) and nxt in (None, INF):
        return [(n, prev + 10)]
    if prev not in (None, INF) and nxt not in (None, INF) and nxt - prev > 1e-6:
        return [(n, (prev + nxt) / 2)]
    if prev == INF:                           # into the unranked part: rank it up to n
        last = max([r for r in own.values() if r is not None], default=0)
        out = []
        for m in nums[:at + 1]:
            if own[m] is None or m == n:
                last += 10
                out.append((m, last))
        return out
    return [(m, 10 * (k + 1)) for k, m in enumerate(nums) if own[m] != 10 * (k + 1)]   # no gap left


def view(root: Path, items: list, cfg: dict, me: str, cap: int = None) -> dict:
    """The ramp as a person sees it: gates and PLANs on item branches. A claim changes no PLAN,
    so claimed items get their gate too (plan_waits)."""
    found = ready.plans(root)
    return ramp(items, plan_files(root, found), cap or cfg["cap"], me, level=cfg["parallel"],
                gates=ready.gates(root, [dict(i, assignees=[]) for i in items], cfg, found))


def _stackable(items: list) -> list:
    """A dependent whose one open blocker has a ready PR (its gates passed) builds on that
    blocker's branch, and its PR targets it; after the blocker's merge pulse go moves it on."""
    by = {i["number"]: i for i in items}
    out = []
    for i in items:
        if not (i["type"] in state.WORK and i["approved"] and not i["assignees"] and len(i["blocked_by"]) == 1):
            continue
        base = by.get(i["blocked_by"][0]) or {}
        pr = base.get("pr") or {}
        if pr and not pr.get("draft"):
            out.append({**i, "base": pr["branch"], "stacked_on": base["number"]})
    return out


def held(items: list, files: dict) -> dict:
    """{file: item} of the running items: the files of their PLANs here and the files their claims
    name, which hold even where a PLAN is unpushed or there is none."""
    return {f: i["number"] for i in items if i["type"] in state.WORK and i["assignees"] and not i.get("draft")
            for f in files.get(i["number"], []) + (i.get("claimed_files") or [])}


def clash(mine: list, held: dict, skip=None):
    """(file, holder) for the first of mine another item holds, else None. A held directory holds
    what is in it; skip, the item this one stacks on, holds nothing for it."""
    return next(((f, n) for f in mine for h, n in held.items() if n != skip
                 and (f == h or f.startswith(h + "/") or h.startswith(f + "/"))), None)


def ramp(items: list, files: dict, cap: int, me: str, level: str = "items", gates=None) -> dict:
    """gates: {issue: why it waits} from ready.gates; a gated item never goes out. A draft nobody
    holds (its spec is to be written, D-43) is a row, never goes out, and takes no bay."""
    cap = 1 if level == "off" else cap
    running = [i for i in items if i["type"] in state.WORK and i["assignees"] and not i.get("draft")]
    taken = held(items, files)
    busy = [i for i in running if me in i["assignees"] and not i.get("pr")]   # in review: no slot
    free = max(0, cap - len(busy))
    pos = {i["number"]: k for k, i in enumerate(order(items))}
    gates = gates or {}
    pool = [i for i in state.ready(items) + _stackable(items)
            if i["number"] not in gates and not i.get("draft")]
    pool.sort(key=lambda i: pos[i["number"]])
    nxt, wait, locked = [], [], []
    for i in pool:
        mine = files.get(i["number"], [])
        hit = clash(mine, taken, i.get("stacked_on"))
        if hit:
            locked.append({**i, "file": hit[0], "holder": hit[1]})
        elif len(nxt) < free:
            nxt.append(i)
            taken.update({f: i["number"] for f in mine})
        else:
            wait.append(i)
    pooled = {i["number"] for i in pool}
    stage = {i["number"]: "starts next" for i in nxt}
    stage.update({i["number"]: "queued" for i in wait})
    stage.update({i["number"]: f"locked: {Path(i['file']).name} in use by #{i['holder']}" for i in locked})
    eff, rows = effective(items), []
    for i in order(items):
        if not _row(i):
            continue
        n = i["number"]
        s = ("spec in progress" if i.get("draft") else None) or \
            stage.get(n) or gates.get(n) or ("not approved" if not i["approved"] else None) or \
            ("waits for " + ", ".join(f"#{b}" for b in i["blocked_by"]) if i["blocked_by"] else "ready")
        rows.append({**i, "stage": s, "via": eff[n][1]})     # via: the item whose rank it carries
    return {"cap": cap, "free": free, "busy": busy, "next": nxt, "wait": wait, "locked": locked,
            "level": level, "rows": rows,
            "plan_waits": [i["number"] for i in running if gates.get(i["number"], "").startswith("plan waits")],
            "after": [i for i in state.blocked(items) if i["type"] in state.WORK and i["number"] not in pooled]}
