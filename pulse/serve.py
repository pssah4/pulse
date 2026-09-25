"""The demo of the docs: the map's time-lapse as one static page, docs/public/map-demo.html.

No second renderer: the page shows the terminal's lines in truecolor (D-38), converted from
ANSI to spans, 80 columns wide (D-45), and the font scales so they always fit the pane.
write_demo_page writes the page; scripts/map_gif.py draws the GIF from frame_html and CSS.
The module keeps the name of the map server it held until D-37; nothing here serves, the
live map is `pulse map`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pulse import map as pmap

STYLE = {"1": "font-weight:700", "90": "color:var(--dim)", "31": "color:var(--bad)",
         "32": "color:var(--ok)", "33": "color:var(--hold)", "35": "color:var(--review)",
         "36": "color:var(--accent)"}
DEMO_PAGE = Path(__file__).resolve().parents[1] / "docs" / "public" / "map-demo.html"


def _rgb(n: int) -> tuple:
    """A color of the 256-color palette: the 6x6x6 cube, then the grey ramp."""
    if n >= 232:
        return (8 + 10 * (n - 232),) * 3
    return tuple((0, 95, 135, 175, 215, 255)[(n - 16) // k % 6] for k in (36, 6, 1))


def style(code: str) -> str:
    """CSS for one SGR sequence: the page's named colors, 256-color and 24-bit colors."""
    out, parts = [], code.split(";")
    while parts:
        p = parts.pop(0)
        if p == "38" and parts[:1] == ["2"]:
            out.append("color:rgb(%s,%s,%s)" % tuple(parts[1:4]))
            parts = parts[4:]
        elif p == "38" and parts[:1] == ["5"]:
            out.append("color:#%02x%02x%02x" % _rgb(int(parts[1])))
            parts = parts[2:]
        else:
            out.append(STYLE.get(p, ""))
    return ";".join(filter(None, out))


def to_html(line: str) -> str:
    out = []
    for part in re.split(r"(\033\[[0-9;]*m)", line):
        if part.startswith("\033["):
            code = part[2:-1]
            out.append("</span>" if code == "0" else f'<span style="{style(code)}">')
        else:
            out.append(part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return "".join(out)


def frame_html(vm: dict, frame: int = 0) -> str:
    """One frame as a truecolor terminal shows it (D-38): the page adds no light of its own."""
    return "\n".join(to_html(line) for line in pmap.render(vm, frame=frame, color=pmap.TRUE))


CSS = """
 :root{--bg:#0d1117;--fg:#d6dde6;--dim:#6e7b8b;--ok:#2ee59d;--bad:#ff5c5c;--hold:#ffc857;
       --review:#c58af9;--accent:#58b4ff}
 html,body{margin:0;background:var(--bg);color:var(--fg)}
 pre{margin:0;padding:14px 16px;white-space:pre;line-height:1.2;font-variant-ligatures:none;
     font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono",monospace}
"""
FIT = """
 const m=document.getElementById('m'), probe=document.createElement('span');
 probe.textContent='0'.repeat(%d); probe.style.cssText='position:absolute;visibility:hidden;font:inherit;white-space:pre';
 function fit(tall){ m.appendChild(probe); m.style.fontSize='100px';
   const w=probe.getBoundingClientRect().width, h=m.getBoundingClientRect().height;
   let px=(innerWidth-32)*100/w; if(tall) px=Math.min(px,(innerHeight-28)*100/h);
   m.style.fontSize=Math.max(6,Math.min(tall?40:14,px))+'px'; }
""" % pmap.WIDTH


def demo_page() -> str:
    """The time-lapse as one static page: every frame of every step inline, picked by the clock
    the way the terminal picks them, so every surface shows the same moment."""
    frames = [frame_html(pmap.demo(k), f).split("\n") for k in range(len(pmap.SCRIPT))
              for f in range(len(pmap.BREATH))]
    tall = max(len(f) for f in frames)
    frames = [f + [" " * pmap.WIDTH] * (tall - len(f)) for f in frames]
    lines = list(dict.fromkeys(l for f in frames for l in f))   # a breath changes a few lines: each once
    at = {l: k for k, l in enumerate(lines)}
    return ("""<!doctype html><meta charset=utf-8><title>Pulse map, a morning in time-lapse</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>""" + CSS + """ html,body{height:100%} body{display:grid;place-items:center}</style>
<pre id=m></pre>
<script>
 const L=""" + json.dumps(lines) + """;
 const F=""" + json.dumps([[at[l] for l in f] for f in frames]) + """;
 const STEP=""" + str(pmap.STEP_SECONDS) + """, TICK=""" + str(pmap.TICK) + """, B=""" + str(len(pmap.BREATH)) + \
        """;""" + FIT + """
 function show(){ const t=Date.now()/1000, f=F[Math.floor(t/STEP)%(F.length/B)*B+Math.floor(t/TICK)%B];
   m.innerHTML=f.map(k=>L[k]).join('\\n'); }
 show(); fit(true); addEventListener('resize',()=>fit(true)); setInterval(show,100);
</script>
""")


def write_demo_page(path: Path = DEMO_PAGE) -> None:
    path.write_text(demo_page(), encoding="utf-8")
