"""The architecture map (FEAT-05): every feature and decision in its layer of the architecture, and a
page per feature, decision, and epic.

The map shows what is merged. build() reads the specs, the decisions, and the layer model from the
base branch, never the work tree, and writes one page per clone into the shared git dir: nothing
there is committed, so parallel branches never collide over it. refresh() rebuilds the page when
the base moved; the live map and pulse go call it after they fetched, so it follows every merge.

The layer model is _devprocess/architecture-map.md: `## <id>: <name>`, a paragraph, and
`- <id>: <name>` per group. A spec or decision names its place as `layer: <layer>[/<group>]`.
Without a model the map groups the features by epic. The page needs no script: its views switch
with :target, and the one script only turns file links into editor links.
"""
from __future__ import annotations

import html
import os
import posixpath
import re
import subprocess
import tempfile
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

from pulse import config, setup, spec, state

MODEL = "_devprocess/architecture-map.md"
PICTURE = "_devprocess/architecture-map.svg"
PAGE = "architecture-map.html"
TEMPLATE = Path(__file__).with_name("archmap.html")
UP = "../../"                         # from the page in <clone>/.git/pulse/ to the clone's files
STAMP = re.compile(r'<meta name="pulse-map" content="([^"]*)">')
ADR_ID = re.compile(r"^(ADR-\d+)")
CITED = re.compile(r"(?<![\w/.-])(?:[\w.-]+/)+[\w.-]*\w\.(?!md\b)[a-z]{1,5}\b")   # a source file a spec names
DESCRIBED = ("feature description", "description", "symptom", "context", "kontext", "goal")
LARGEST = 1_000_000                   # bytes of one file the map reads; a larger one shows by its name alone
SVG, XLINK = "http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink"
# the project picture keeps shapes, text, and links within the page, nothing else (audit M-1 of #67)
SHAPES = {n.lower(): n for n in ("svg", "g", "defs", "title", "desc", "rect", "circle", "ellipse", "line", "polyline",
                                 "polygon", "path", "text", "tspan", "a", "marker", "linearGradient",
                                 "radialGradient", "stop")}
LOOKS = {n.lower(): n for n in (
    "viewBox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "dx", "dy", "d",
    "points", "transform", "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity", "font-family", "font-size", "font-weight",
    "font-style", "text-anchor", "dominant-baseline", "letter-spacing", "marker-start", "marker-mid", "marker-end",
    "refX", "refY", "markerWidth", "markerHeight", "markerUnits", "orient", "offset", "stop-color", "stop-opacity",
    "gradientUnits", "preserveAspectRatio", "role", "aria-label", "id", "href")}
QUIET = {"metadata"}                  # an editor's own notes: left out without a word
PAGE_IDS = ("layer-", "feature-", "adr-", "epic-")
LINK = re.compile(r"\[([^\[\]]*)\]\(([^()\s\[\]]+)(?:\s+&quot;[^&]*&quot;)?\)")   # on escaped text; linear
KINDS = {"FEAT": "feature", "EPIC": "epic", "ADR": "adr"}        # what has a page, by the anchor it has


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _git(root, *args, **kw):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, **kw)


def files(root: Path, ref: str) -> dict:
    """{path: text} of the specs, decisions, model, and picture on ref: one ls-tree, one cat-file. cat-file
    gets object ids, never names (audit L-1); a file above LARGEST comes as "" (L-2)."""
    wanted, texts = [], {}
    for entry in _git(root, "ls-tree", "-rz", "-l", ref, "--", "_devprocess").stdout.split(b"\0"):
        meta, _, name = entry.partition(b"\t")
        mode_type_oid_size = meta.split()
        if len(mode_type_oid_size) != 4 or mode_type_oid_size[1] != b"blob":
            continue
        path, (_, _, oid, size) = name.decode("utf-8", "replace"), mode_type_oid_size
        if path in (MODEL, PICTURE) or path.endswith(".md") and _kind(path):
            if int(size) > LARGEST:
                texts[path] = ""
            else:
                wanted.append((path, oid.decode()))
    out = _git(root, "cat-file", "--batch", input="".join(f"{oid}\n" for _, oid in wanted).encode()).stdout
    at = 0
    for path, _ in wanted:
        end = out.index(b"\n", at)
        head = out[at:end].split()
        if len(head) != 3:                 # "<oid> missing": gone between the two calls
            at = end + 1
            continue
        size = int(head[2])
        texts[path] = out[end + 1:end + 1 + size].decode("utf-8", "replace")
        at = end + 2 + size
    return texts


def _kind(path: str):
    """FEAT, EPIC, IMP, FIX, or ADR for a spec or decision by its folder, else None."""
    folder, name = posixpath.split(path)
    if folder == "_devprocess/decisions":
        return "ADR" if ADR_ID.match(name) else None
    if posixpath.dirname(folder) == spec.REQUIREMENTS:
        return spec.FOLDERS.get(posixpath.basename(folder))
    return None


def model(text: str) -> list:
    """[{id, name, summary, groups: [(id, name)]}] from the layer model, top to bottom. A layer named
    twice is one layer. The patterns run on stripped lines: linear (audit M-2)."""
    layers, current, said = [], None, {}
    for line in spec.COMMENT.sub("", text or "").splitlines():
        line = line.strip()
        head = re.match(r"## +([\w.-]+): *(\S.*)", line)
        if head:
            current = next((l for l in layers if l["id"] == head.group(1)), None)
            if current is None:
                current = {"id": head.group(1), "name": head.group(2), "summary": "", "groups": []}
                layers.append(current)
                said[head.group(1)] = []
            continue
        group = re.match(r"[-*] +([\w.-]+): *(\S.*)", line) if current else None
        if group and group.group(1) not in {g for g, _ in current["groups"]}:
            current["groups"].append((group.group(1), group.group(2)))
        elif current and line and not group and not current["groups"]:
            said[current["id"]].append(line)
    for layer in layers:
        layer["summary"] = " ".join(said[layer["id"]])
    return layers


def misplaced(where: str, layers: list) -> str:
    """Why `layer: <where>` names no place in the model; "" when it does."""
    lid, _, gid = where.partition("/")
    found = next((l for l in layers if l["id"] == lid.strip()), None)
    if found is None:
        return f"layer {lid.strip()!r} is not in {MODEL}"
    if gid.strip() and gid.strip() not in {g for g, _ in found["groups"]}:
        return f"group {gid.strip()!r} is not in layer {lid.strip()!r} of {MODEL}"
    return ""


def layer_problems(root: Path) -> list:
    """[(path, why)] for each spec and decision in the work tree whose layer: names a place the
    model lacks (pulse check, C11); [] without a model."""
    try:
        layers = model((root / MODEL).read_text(encoding="utf-8"))
    except OSError:
        return []
    out = []
    for path in sorted([*(root / spec.REQUIREMENTS).glob("*/*.md"), *(root / "_devprocess/decisions").glob("ADR-*.md")]):
        rel = path.relative_to(root).as_posix()
        where = str(spec.front(path.read_text(encoding="utf-8", errors="replace")).get("layer") or "")
        why = misplaced(where, layers) if _kind(rel) in ("FEAT", "ADR") and where else ""
        if why:
            out.append((rel, why))
    return out


def _title(fm: dict, body: str, rid: str) -> str:
    title = str(fm.get("title") or "").strip().strip("\"'")
    if not title:
        m = re.search(r"^# +(.+)$", body, re.M)
        title = re.sub(r"^[\w-]+: *", "", m.group(1)) if m else rid
    return title


def records(texts: dict) -> list:
    """Every epic, feature, improvement, fix, and decision, sorted by ID."""
    out = []
    for path, text in texts.items():
        kind = _kind(path) if path not in (MODEL, PICTURE) else None
        if not kind:
            continue
        name = posixpath.basename(path)
        found = spec.id_of(name)
        rid = spec.id_text(*found) if found else ADR_ID.match(name).group(1) if kind == "ADR" else name[:-3]
        fm, raw = spec.front(text), spec.split(text)[1]
        body = re.sub(r"^\s*# .*\n?", "", raw, count=1)        # the page shows the title above it
        parent = fm.get("parent")
        sec = spec.sections(text)
        lead = next((sec[k] for k in DESCRIBED if sec.get(k, "").strip()), "")
        out.append({"id": rid, "kind": kind, "path": path, "fm": fm, "body": body,
                    "title": _title(fm, raw, rid), "layer": str(fm.get("layer") or "").strip(),
                    "parent": posixpath.normpath(posixpath.join(posixpath.dirname(path), parent))
                    if isinstance(parent, str) else None,
                    "lead": re.sub(r"\s+", " ", lead.strip().split("\n\n")[0]),
                    "cites": set(CITED.findall(spec.COMMENT.sub("", body)))})
    out.sort(key=lambda r: (r["id"], r["path"]))
    seen = set()
    for r in out:                         # nothing numbers decision records: one number twice gets its file name,
        if r["id"] in seen:               # else its path, which no other record has
            stem = posixpath.basename(r["path"])[:-3]
            r["id"] = stem if stem not in seen else r["path"][:-3]
        seen.add(r["id"])
    return out


def relate(features: list, adrs: list) -> dict:
    """{id: [(other id, via)]} for a feature and a decision the spec names or whose sources it shares."""
    out = {r["id"]: [] for r in features + adrs}
    for a in adrs:
        named = re.compile(rf"\b{re.escape(a['id'])}\b")
        for f in features:
            shared = sorted(f["cites"] & a["cites"])
            if named.search(f["body"]) or shared:
                via = "names the decision" if named.search(f["body"]) else shared[0]
                out[f["id"]].append((a["id"], via))
                out[a["id"]].append((f["id"], via))
    return out


# --- markdown: the subset specs use; the text is escaped before any markup is set ---------------

def _href(url: str, at: str, anchors: dict) -> str:
    """A link of a spec: another spec's page, a file of the clone, or a web address; "" for the rest."""
    url = html.unescape(url).strip()
    if re.match(r"(?i)(https?|mailto):", url) or url.startswith("#"):
        return url
    if re.match(r"(?i)[a-z][a-z0-9+.-]*:", url):
        return ""                             # javascript:, data:, and every other scheme
    target = posixpath.normpath(posixpath.join(posixpath.dirname(at), url.split("#")[0]))
    return anchors.get(target) or UP + target


def _emphasis(s: str) -> str:
    # each pattern stops at the next star: linear on any line (audit M-2)
    s = re.sub(r"\*\*([^*\s](?:[^*]*[^*\s])?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(?<![\w*])\*([^*\s](?:[^*]*[^*\s])?)\*(?![\w*])", r"<em>\1</em>", s)


def _inline(text: str, at: str, anchors: dict) -> str:
    out = []
    for k, part in enumerate(re.split(r"(`[^`]*`)", text)):
        if k % 2:
            out.append(f"<code>{esc(part[1:-1])}</code>")
            continue
        links = []

        def hold(m):                      # a link waits as a mark without stars: one in its address pairs with
            href, label = _href(m.group(2), at, anchors), _emphasis(m.group(1))   # none outside, a pair around it holds
            links.append(f'<a href="{esc(href)}">{label}</a>' if href else label)
            return f"\ue000{len(links) - 1}\ue001"
        held = _emphasis(LINK.sub(hold, esc(part.replace("\ue000", ""))))
        out.append(re.sub("\ue000(\\d+)\ue001", lambda m: links[int(m.group(1))], held))
    return "".join(out)


def markdown(text: str, at: str, anchors: dict) -> str:
    """Headings, paragraphs, lists, tables, quotes, and code of a spec as HTML. Nested lists come
    out flat."""
    # ponytail: a subset renderer; a spec that needs more of markdown reads fine in its file
    out, para, items, rows, fence = [], [], None, [], None
    inline = lambda s: _inline(s, at, anchors)

    def flush():
        nonlocal para, items, rows
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
        if items:
            out.append(f"<{items[0]}>" + "".join(f"<li>{inline(' '.join(i))}</li>" for i in items[1]) + f"</{items[0]}>")
        if rows:
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            body = [r for r in cells[1:] if not set("".join(r)) <= set("-: ")]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells[0]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</tbody></table>")
        para, items, rows = [], None, []

    for line in spec.COMMENT.sub("", text).splitlines():
        line = line.rstrip()
        if fence is not None:
            if line.lstrip().startswith("```"):
                out.append(f"<pre><code>{esc(chr(10).join(fence))}</code></pre>")
                fence = None
            else:
                fence.append(line)
            continue
        item = re.match(r"^\s*([-*+]|\d+[.)])\s+(.*)$", line)
        head = re.match(r"(#{1,6})\s+(\S.*)", line)
        if line.lstrip().startswith("```"):
            flush()
            fence = []
        elif head:
            flush()
            n, title = min(max(len(head.group(1)), 2), 4), head.group(2)
            bare = title.rstrip("#")
            if bare != title and bare[-1:].isspace():            # "## Title ##": the closing hashes go
                title = bare.rstrip()
            out.append(f"<h{n}>{inline(title)}</h{n}>")
        elif line.lstrip().startswith("|"):
            if not rows:
                flush()
            rows.append(line)
        elif item:
            tag = "ol" if item.group(1)[0].isdigit() else "ul"
            if not items or items[0] != tag or para:
                flush()
                items = (tag, [])
            items[1].append([item.group(2)])
        elif line.startswith(">"):
            flush()
            out.append(f"<blockquote>{inline(line.lstrip('> '))}</blockquote>")
        elif not line.strip():
            flush()
        elif items and line.startswith((" ", "\t")):
            items[1][-1].append(line.strip())          # a list item going on in the next line
        else:
            if items or rows:
                flush()
            para.append(line.strip())
    if fence is not None:
        out.append(f"<pre><code>{esc(chr(10).join(fence))}</code></pre>")
    flush()
    return "\n".join(out)


# --- the page ---------------------------------------------------------------------------------------

def _names(tag: str) -> tuple:
    """(namespace, local name) of an element or attribute ElementTree read; no namespace is SVG's."""
    ns, _, local = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
    return ns, local


def _kept(name: str, value: str):
    """The name an attribute keeps on the page, or None: a link only within the page, a url() only
    to the picture's own parts, an id no page view uses."""
    ns, local = _names(name)
    if "\\" in value:                  # a CSS escape spells url( otherwise (audit round 2 of #67)
        return None
    kept = LOOKS.get(local.lower()) if ns in ("", XLINK) else None
    if ns == XLINK and kept != "href" or kept == "href" and not value.startswith("#"):
        return None
    if "url(" in value.lower() and not re.fullmatch(r"\s*url\(\s*#[\w.-]+\s*\)\s*", value):
        return None
    if kept == "id" and (value == "map" or value.startswith(PAGE_IDS) or not re.fullmatch(r"[A-Za-z][\w.-]*", value)):
        return None
    return kept


def _shape(el, filled, dropped: set) -> str:
    """One element of the picture as markup: kept shapes and attributes, text escaped."""
    ns, local = _names(el.tag)
    tag = SHAPES.get(local.lower()) if ns in ("", SVG) else None
    if tag is None:
        if ns in ("", SVG) and local.lower() not in QUIET:
            dropped.add(local)
        return esc(filled(el.tail))
    attrs = ""
    for name, value in el.attrib.items():
        kept = _kept(name, value)
        if kept:
            attrs += f' {kept}="{esc(value)}"'
        elif _names(name)[0] in ("", XLINK):
            dropped.add(_names(name)[1])
    inner = "".join(_shape(child, filled, dropped) for child in el)
    return f"<{tag}{attrs}>{esc(filled(el.text))}{inner}</{tag}>{esc(filled(el.tail))}"


def picture(svg, count) -> str:
    """The project's own picture over the layers, its counts filled in. Only shapes, text, and links
    within the page reach the page (FR-06, audit M-1 of #67); a note names what was left out."""
    if svg is None:
        return ""
    why, root = "", None
    if not svg.strip():
        why = "it is empty or larger than 1 MB"
    elif re.search(r"<!(?:doctype|entity)", svg, re.I):
        why = "it declares a document type"
    else:
        try:
            root = ET.fromstring(svg)
        except ET.ParseError:
            root, why = None, "it is not well-formed XML"
        if root is not None and _names(root.tag)[1] != "svg":
            why = "its root is no svg element"
    if why:
        return f'<p class="note">{PICTURE} is left out: {why}.</p>'
    dropped = set()
    filled = lambda t: re.sub(r"\{\{features:([\w.-]+)\}\}", lambda m: plural(count(m.group(1)), "feature"), t or "")
    try:
        shown = _shape(root, filled, dropped)
    except RecursionError:
        return f'<p class="note">{PICTURE} is left out: it is nested too deeply.</p>'
    said = (f'<p class="note">{PICTURE}: left out {", ".join(sorted(dropped))}; the picture keeps shapes, text, '
            "and links within this page.</p>") if dropped else ""
    return f'<figure class="fig">{shown}</figure>{said}'


def boxes(recs: list, layers: list) -> list:
    """The layers of the map with what stands in them: [{id, name, summary, groups: [(gid, name,
    features)], loose, adrs}]; with a model its layers and "unplaced", without one an epic each."""
    features = [r for r in recs if r["kind"] == "FEAT"]
    adrs = [r for r in recs if r["kind"] == "ADR"]
    if not layers:
        epics = {r["path"]: r for r in recs if r["kind"] == "EPIC"}
        out = [{"id": e["id"], "name": e["title"], "summary": e["lead"], "groups": [],
                "loose": [f for f in features if f["parent"] == path], "adrs": []} for path, e in epics.items()]
        out.sort(key=lambda b: b["id"])
        rest = [f for f in features if f["parent"] not in epics]
        out += [{"id": "none", "name": "No epic", "summary": "", "groups": [], "loose": rest, "adrs": []}] if rest else []
        return out + ([{"id": "decisions", "name": "Decisions", "summary": "", "groups": [], "loose": [],
                        "adrs": adrs}] if adrs else [])
    out = [{**l, "groups": [(gid, name, []) for gid, name in l["groups"]], "loose": [], "adrs": []} for l in layers]
    by_id = {b["id"]: b for b in out}
    unplaced = {"id": "unplaced", "name": "Not placed", "groups": [], "loose": [], "adrs": [],
                "summary": f"No layer: yet, or one {MODEL} does not know. /pulse-plan places a feature when it plans it."}
    for r in features + adrs:
        box, gid = unplaced, ""
        if r["layer"] and not misplaced(r["layer"], layers):
            lid, _, gid = r["layer"].partition("/")
            box, gid = by_id[lid.strip()], gid.strip()
        if r["kind"] == "ADR":
            box["adrs"].append(r)
        elif gid:
            next(g for g in box["groups"] if g[0] == gid)[2].append(r)
        else:
            box["loose"].append(r)
    return out + ([unplaced] if unplaced["loose"] or unplaced["adrs"] else [])


def _count(box) -> int:
    return len(box["loose"]) + sum(len(g[2]) for g in box["groups"])


def render(texts: dict, ref: str, sha: str, stamp: str, project: str, issues: str) -> str:
    """The whole page from the files of the base branch."""
    recs, layers = records(texts), model(texts.get(MODEL))
    by = {r["id"]: r for r in recs}
    anchors = {r["path"]: f"#{KINDS[r['kind']]}-{r['id']}" for r in recs if r["kind"] in ("FEAT", "EPIC", "ADR")}
    rel = relate([r for r in recs if r["kind"] == "FEAT"], [r for r in recs if r["kind"] == "ADR"])
    epic = {r["path"]: r for r in recs if r["kind"] == "EPIC"}
    feature = {r["path"]: r for r in recs if r["kind"] == "FEAT"}
    items = [r for r in recs if r["kind"] in ("IMP", "FIX")]
    placed = boxes(recs, layers)
    where = {r["id"]: b for b in placed for r in b["loose"] + b["adrs"] + [f for g in b["groups"] for f in g[2]]}
    count = lambda lid: next((_count(b) for b in placed if b["id"] == lid), 0)

    def issue(r):
        n = str(r["fm"].get("issue") or "").lstrip("#")
        if not n.isdigit():
            return ""
        return f'<a href="{esc(issues + n)}">#{n}</a>' if issues else f"<span>#{n}</span>"

    def chip(r):
        cls = " adr" if r["kind"] == "ADR" else ""
        return (f'<a class="chip{cls}" href="#{KINDS[r["kind"]]}-{esc(r["id"])}">'
                f'<span class="cid">{esc(r["id"])}</span><span class="ct">{esc(r["title"])}</span></a>')

    def row(r, note=None):
        href = f'#{KINDS[r["kind"]]}-{esc(r["id"])}' if r["kind"] in ("FEAT", "EPIC", "ADR") else esc(UP + r["path"])
        return (f'<a class="row{" adr" if r["kind"] == "ADR" else ""}" href="{href}"><span class="rid">{esc(r["id"])}</span>'
                f'<span class="rt">{esc(r["title"])}</span><span class="rd">{esc(note if note is not None else r["lead"])}</span></a>')

    def block(title, rs, note=None):
        return (f'<section class="block"><h2>{title}<span class="cnt">{len(rs)}</span></h2><div class="rows">'
                + "".join(row(r, note(r) if note else None) for r in rs) + "</div></section>") if rs else ""

    def layer_box(b):
        n, a = _count(b), len(b["adrs"])
        told = " · ".join([plural(n, "feature")] * bool(n or not a) + [plural(a, "decision")] * bool(a))
        head = f'<header class="lh"><h2>{esc(b["name"])}</h2><span class="lcnt">{told}</span></header>'
        summary = f'<p class="lsub">{esc(b["summary"])}</p>' if b["summary"] else ""
        adrs = f'<div class="chips">{"".join(chip(r) for r in b["adrs"])}</div>' if b["adrs"] else ""
        groups = "".join(f'<div class="grp"><h3><span>{esc(name)}</span><span class="gcnt">{len(fs)}</span></h3>'
                         f'<div class="chips">{"".join(chip(f) for f in fs)}</div></div>' for _, name, fs in b["groups"])
        loose = f'<div class="grp"><div class="chips">{"".join(chip(f) for f in b["loose"])}</div></div>' if b["loose"] else ""
        cls = " unplaced" if b["id"] == "unplaced" else ""
        return (f'<section class="layer{cls}" id="layer-{esc(b["id"])}">{head}{summary}{adrs}'
                f'<div class="groups">{groups}{loose}</div></section>')

    def page(r, crumbs, meta, lead, facts, extra=""):
        trail = "".join(f'<a href="{h}">{esc(t)}</a><span class="sep">›</span>' for t, h in crumbs)
        dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts if v)
        return (f'<section class="view page" id="{KINDS[r["kind"]]}-{esc(r["id"])}">'
                f'<nav class="crumbs"><a href="#map">Map</a><span class="sep">›</span>{trail}<span>{esc(r["id"])}</span></nav>'
                f'<header class="page-head"><div class="meta">{"".join(m for m in meta if m)}</div><h1>{esc(r["title"])}</h1>'
                + (f'<p class="lead-text">{esc(lead)}</p>' if lead else "") + "</header>"
                f'<div class="actions"><a class="btn primary" data-editor="{esc(r["path"])}" hidden>Open in VS Code</a>'
                f'<a class="btn" href="{esc(UP + r["path"])}">Markdown file</a><code class="path">{esc(r["path"])}</code></div>'
                + (f'<dl class="facts">{dl}</dl>' if dl else "") + extra
                + f'<article class="md">{markdown(r["body"], r["path"], anchors)}</article></section>')

    def place(r):
        b = where.get(r["id"])
        if not b:
            return ""
        gid = r["layer"].partition("/")[2].strip() if layers and b["id"] != "unplaced" else ""
        group = next((name for g, name, _ in b["groups"] if g == gid), "")
        return f'<a href="#layer-{esc(b["id"])}">{esc(b["name"])}{" › " + esc(group) if group else ""}</a>'

    def links(pairs):
        return "".join(f'<span><a href="#{KINDS[by[i]["kind"]]}-{esc(i)}">{esc(i)} {esc(by[i]["title"])}</a>'
                       f'<span class="via"> via {esc(via)}</span></span>' for i, via in pairs)

    views = []
    for f in (r for r in recs if r["kind"] == "FEAT"):
        e = epic.get(f["parent"])
        kids = [i for i in items if i["parent"] == f["path"]]
        views.append(page(f, [(where[f["id"]]["name"], f'#layer-{esc(where[f["id"]]["id"])}')] if f["id"] in where else [],
                          ["<span>feature</span>", f'<a href="#epic-{esc(e["id"])}">{esc(e["id"])} {esc(e["title"])}</a>' if e else "", issue(f)],
                          f["lead"], [("Layer", place(f)), ("Decisions", links(rel[f["id"]]))],
                          block("Fixes and improvements", kids)))
    for a in (r for r in recs if r["kind"] == "ADR"):
        views.append(page(a, [(where[a["id"]]["name"], f'#layer-{esc(where[a["id"]]["id"])}')] if a["id"] in where else [],
                          ["<span>decision</span>", f'<span>{esc(a["fm"].get("kind"))}</span>' if a["fm"].get("kind") else ""],
                          f'Read when: {a["fm"]["read-when"]}' if a["fm"].get("read-when") else a["lead"],
                          [("Layer", place(a)), ("Features", links(rel[a["id"]]))]))
    for e in (r for r in recs if r["kind"] == "EPIC"):
        mine = [f for f in feature.values() if f["parent"] == e["path"]]
        mine.sort(key=lambda f: f["id"])
        note = (lambda f: where[f["id"]]["name"] if f["id"] in where else "") if layers else None
        views.append(page(e, [], ["<span>epic</span>", issue(e), f"<span>{plural(len(mine), 'feature')}</span>"], e["lead"], [],
                          block("Features", mine, note) + block("Fixes and improvements", [i for i in items if i["parent"] == e["path"]])))

    n_feat, n_adr = sum(r["kind"] == "FEAT" for r in recs), sum(r["kind"] == "ADR" for r in recs)
    how = ("Each feature and decision stands in the layer its <code>layer:</code> names; the layers come from "
           f"<code>{MODEL}</code>." if layers else
           f"No layer model yet, so the features stand under their epic. <code>{MODEL}</code> names the layers; "
           "/pulse-plan proposes it.")
    # every spec is reachable from the map (SC-02): an epic by the line of epics, a fix or improvement
    # by its feature or epic, and one with neither in a box of its own
    epics = " · ".join(f'<a href="#epic-{esc(e["id"])}">{esc(e["id"])} {esc(e["title"])}</a>' for e in epic.values())
    loose = [i for i in items if i["parent"] not in feature and i["parent"] not in epic]
    rest = (f'<section class="layer unplaced" id="layer-loose"><header class="lh"><h2>Fixes and improvements without '
            f'a feature or epic</h2><span class="lcnt">{len(loose)}</span></header><div class="rows">'
            + "".join(row(i) for i in loose) + "</div></section>") if loose else ""
    home = (f'<section class="view" id="map"><header class="head"><div class="eyebrow">Pulse · Architecture</div>'
            f'<h1>{esc(project)}: architecture map</h1><p>{how} A box leads to its features, a feature to its spec.</p>'
            f'<p class="note">Built from {esc(ref)} at {esc(sha[:7])} · {plural(n_feat, "feature")} · {plural(n_adr, "decision")}'
            " · rebuilt by Pulse after every merge.</p>" + (f'<p class="note">Epics: {epics}</p>' if epics else "") + "</header>"
            + picture(texts.get(PICTURE), count)
            + f'<div class="layers">{"".join(layer_box(b) for b in placed)}{rest}</div></section>')
    title = f"{esc(project)}: architecture map"
    return (TEMPLATE.read_text(encoding="utf-8").replace("<!--STAMP-->", esc(stamp)).replace("<!--TITLE-->", title)
            .replace("<!--VIEWS-->", "\n".join([home, *views])))


def _issues(root: Path) -> str:
    """The issue address of the repo in .pulse/config.toml, else of a GitHub origin, else ""; asks no network."""
    name = config.load(root).get("repo") or ""
    if not name:
        m = state.REMOTE.search(_git(root, "remote", "get-url", "origin", text=True).stdout.strip())
        name = m.group(1) if m else ""
    return f"https://github.com/{name}/issues/" if name else ""


def _stamp(root: Path, ref: str) -> tuple:
    sha = _git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", text=True).stdout.strip()
    if not sha:
        raise state.StateError(f"{ref} has no commit to build the architecture map from")
    try:
        version = setup._version(setup.PULSE_BIN.parents[1])
    except (OSError, ValueError, KeyError):
        version = ""
    return sha, f"{sha} {version}"


def build(root: Path) -> Path:
    """Build the page from the base branch into the clone's git dir; its path."""
    ref = config.base_ref(root)
    sha, stamp = _stamp(root, ref)
    page = config.pulse_dir(root) / PAGE
    text = render(files(root, ref), ref, sha, stamp, config.common_dir(root).parent.name, _issues(root))
    page.parent.mkdir(parents=True, exist_ok=True)
    fd, part = tempfile.mkstemp(dir=page.parent, prefix=f".{PAGE}.")   # a new file: follows no link (audit L-3)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(part, page)                 # a reload in the browser never shows half a page
    return page


def refresh(root: Path):
    """The page, rebuilt when the base branch moved or Pulse changed since it was built; None when it
    cannot be built. Never raises: the live map and pulse go call it on every round (FEAT-05 NFR)."""
    try:
        page = config.pulse_dir(root) / PAGE
        want = _stamp(root, config.base_ref(root))[1]
        try:
            with page.open(encoding="utf-8") as f:
                have = STAMP.search(f.read(2048))
        except OSError:
            have = None
        return page if have and have.group(1) == want else build(root)
    except Exception:  # ponytail: any failure means no map this round; `pulse arch` shows the error
        return None


def main(args) -> int:
    root = config.find_root()
    if root is None:
        print("pulse arch: not inside a git repository")
        return 2
    page = build(root)
    print(page)
    if args.open:
        webbrowser.open(page.as_uri())
    return 0
