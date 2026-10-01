#!/usr/bin/env python3
"""Export the current terminal map as an animated SVG for the docs hero.

Run before VitePress builds or starts: Python 3.9+, standard library only.
The public mirror includes docs/ and pulse/, so it can build this too.
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pulse import map as pmap  # noqa: E402

CELL, ROW, PAD = 9, 18, 16
COLORS = {31: "#ff5c5c", 32: "#2ee59d", 33: "#ffc857", 35: "#c58af9",
          36: "#58b4ff", 90: "#6e7b8b"}
SGR = re.compile(r"\033\[([0-9;]*)m")


def line_svg(line: str) -> str:
    """Keep terminal columns and colors, escaping all fixture text as XML."""
    line = re.sub(r"\033\]8;;[^\033]*\033\\", "", line).rstrip()
    spans, column, start, color, bold = [], 0, 0, "#d6dde6", False
    for match in [*SGR.finditer(line), None]:
        end = match.start() if match else len(line)
        text = line[start:end]
        if text:
            weight = ' font-weight="700"' if bold else ""
            spans.append(f'<tspan x="{PAD + column * CELL}" fill="{color}"{weight}>{escape(text)}</tspan>')
            column += sum(pmap._cols(c) for c in text)
        if match is None:
            break
        codes = [int(c or 0) for c in match.group(1).split(";")]
        index = 0
        while index < len(codes):
            code = codes[index]
            if code == 0:
                color, bold = "#d6dde6", False
            elif code == 1:
                bold = True
            elif code == 22:
                bold = False
            elif code == 39:
                color = "#d6dde6"
            elif code in COLORS:
                color = COLORS[code]
            elif code == 38 and codes[index + 1:index + 2] == [2]:
                color = "#%02x%02x%02x" % tuple(codes[index + 2:index + 5])
                index += 4
            else:
                raise ValueError(f"Unsupported map color: {codes}")
            index += 1
        start = match.end()
    return "".join(spans)


def render_svg() -> str:
    frames = [pmap.render(pmap.demo(step), frame=phase, color=pmap.TRUE, width=pmap.WIDTH)
              for step in range(len(pmap.SCRIPT)) for phase in range(len(pmap.BREATH))]
    width, height = pmap.WIDTH * CELL + 2 * PAD, max(map(len, frames)) * ROW + 2 * PAD
    duration = len(frames) * pmap.TICK
    lines, groups = {}, []
    for index, frame in enumerate(frames):
        rows = []
        for row, line in enumerate(frame):
            if line not in lines:
                lines[line] = f"line-{len(lines)}"
            rows.append(f'<use href="#{lines[line]}" y="{PAD + 14 + row * ROW}"/>')
        step, phase = divmod(index, len(pmap.BREATH))
        groups.append(f'<g class="frame frame-{index}" data-step="{step}" data-phase="{phase}" '
                      f'style="animation-delay:{index * pmap.TICK:g}s">' + "".join(rows) + "</g>")
    definitions = "\n".join(f'<text id="{name}">{line_svg(line)}</text>' for line, name in lines.items())
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<title>The Pulse map: a morning at acme/shop in time-lapse</title>
<style>
text {{ font: 15px Menlo, Consolas, "DejaVu Sans Mono", monospace; white-space: pre; font-variant-ligatures: none; }}
.frame {{ visibility: hidden; animation: map-frame {duration:g}s step-end infinite; }}
.frame-0 {{ visibility: visible; }}
@keyframes map-frame {{
  0% {{ visibility: visible; }}
  {100 / len(frames):.8f}%, 100% {{ visibility: hidden; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .frame {{ animation: none; visibility: hidden; }}
  .frame-0 {{ visibility: visible; }}
}}
</style>
<rect width="{width}" height="{height}" rx="14" fill="#0d1117"/>
<defs>
{definitions}
</defs>
''' + "\n".join(groups) + "\n</svg>\n"


if __name__ == "__main__":
    output = ROOT / "docs/public/assets/pulse-map-demo.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(), encoding="utf-8")
    print(f"Map demo: {output.stat().st_size // 1024} KB, {len(pmap.SCRIPT)} steps")
