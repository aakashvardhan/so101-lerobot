"""Generate a printable A4 template for the ACT eval cube positions.

Reads the 50 Random-tab (x, y) coordinates from ACT_eval_scoresheet.xlsx and
renders them as numbered dots on a true-scale 1 cm grid. Output is an SVG in an
HTML page sized in physical mm: open it in a browser and print at 100% /
"Actual size" on A4. Includes a 10 cm scale-check bar.

Usage:
    python scripts/make_position_template.py
    -> writes eval_position_template.html at the repo root
    python scripts/make_position_template.py --minimal
    -> writes eval_position_grid.html: full-page 1 cm graph-paper grid with the
       numbered dots and a red center cross only (no titles or instructions)
"""

import argparse
import re
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

XLSX = "ACT_eval_scoresheet.xlsx"
OUT = "eval_position_template.html"
FIRST_TRIAL_ROW, LAST_TRIAL_ROW = 15, 64

# All SVG coordinates below are in mm. The page is 210 x 275 so the content
# fits on ONE sheet of either A4 (210x297) or US Letter (215.9x279.4).
PAGE_W, PAGE_H = 210.0, 275.0
CX, CY = 105.0, 140.0  # grid origin (workspace center) on the page


def read_positions():
    """Return [(trial, x_cm, y_cm)] parsed from the Random sheet's column B."""
    with zipfile.ZipFile(XLSX) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root:
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        names = [s.get("name") for s in wb.iter(NS + "sheet")]
        sheet_files = sorted(
            n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)
        )
        root = ET.fromstring(z.read(sheet_files[names.index("Random")]))
        cells = {}
        for c in root.iter(NS + "c"):
            v = c.find(NS + "v")
            if v is None or v.text is None:
                continue
            cells[c.get("r")] = shared[int(v.text)] if c.get("t") == "s" else v.text

    positions = []
    for row in range(FIRST_TRIAL_ROW, LAST_TRIAL_ROW + 1):
        m = re.match(r"\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)", cells.get(f"B{row}", ""))
        if not m:
            raise ValueError(f"Cannot parse position in Random!B{row}")
        positions.append((row - FIRST_TRIAL_ROW + 1, float(m.group(1)), float(m.group(2))))
    return positions


def label_offsets(positions):
    """Pick a label direction per dot so labels in tight clusters don't overlap.

    Default is upper-right; within any pair closer than 6 mm, alternate the
    later dot to another corner.
    """
    dirs = {}
    corners = [(1, 1), (-1, -1), (1, -1), (-1, 1)]
    order = sorted(positions, key=lambda p: (p[1], p[2]))
    for i, (t, x, y) in enumerate(order):
        taken = {dirs[t2] for t2, x2, y2 in order[:i]
                 if abs(x - x2) < 0.6 and abs(y - y2) < 0.6}
        dirs[t] = next(c for c in corners if c not in taken)
    return dirs


def pt(x_cm, y_cm):
    """cm in workspace coords (+y away from robot = up the page) -> page mm."""
    return CX + 10 * x_cm, CY - 10 * y_cm


def render_minimal(positions, dirs, out):
    """Full-page 1 cm graph-paper grid with numbered dots, axes and a center cross."""
    # Grid from (10, 10) to (200, 260) -> 19 x 25 cm of whole squares.
    # The workspace center MUST sit on a grid intersection: (100, 140) is one.
    cx, cy = 100.0, 140.0
    s = []
    for x in range(10, 201, 10):
        s.append(f'<line x1="{x}" y1="10" x2="{x}" y2="260" stroke="#2b8fd4" stroke-width="0.25"/>')
    for y in range(10, 261, 10):
        s.append(f'<line x1="10" y1="{y}" x2="200" y2="{y}" stroke="#2b8fd4" stroke-width="0.25"/>')

    # x / y axes through the center, darker and heavier than the grid.
    s.append(f'<line x1="10" y1="{cy}" x2="200" y2="{cy}" stroke="#155a8a" stroke-width="0.6"/>')
    s.append(f'<line x1="{cx}" y1="10" x2="{cx}" y2="260" stroke="#155a8a" stroke-width="0.6"/>')
    # Arrowheads + axis names at the grid edges.
    s.append(f'<path d="M 200 {cy} l -3 -1.5 v 3 z" fill="#155a8a"/>')
    s.append(f'<text x="203" y="{cy + 1.2}" font-size="4" fill="#155a8a">+x</text>')
    s.append(f'<path d="M {cx} 10 l -1.5 3 h 3 z" fill="#155a8a"/>')
    s.append(f'<text x="{cx}" y="7" font-size="4" fill="#155a8a" text-anchor="middle">+y</text>')
    # cm tick labels every cm from -5..5 along both axes (skip 0).
    for v in range(-5, 6):
        if v == 0:
            continue
        s.append(f'<text x="{cx + 10 * v}" y="{cy + 4}" font-size="2.4" fill="#155a8a" '
                 f'text-anchor="middle">{v}</text>')
        s.append(f'<text x="{cx - 1.5}" y="{cy - 10 * v + 1}" font-size="2.4" fill="#155a8a" '
                 f'text-anchor="end">{v}</text>')

    # Red cross on the workspace center (on a grid intersection).
    s.append(f'<line x1="{cx - 4}" y1="{cy}" x2="{cx + 4}" y2="{cy}" stroke="red" stroke-width="0.6"/>')
    s.append(f'<line x1="{cx}" y1="{cy - 4}" x2="{cx}" y2="{cy + 4}" stroke="red" stroke-width="0.6"/>')

    for t, xc, yc in positions:
        x, y = cx + 10 * xc, cy - 10 * yc
        dx, dy = dirs[t]
        s.append(f'<circle cx="{x}" cy="{y}" r="0.8" fill="black"/>')
        anchor = "start" if dx > 0 else "end"
        ly = y - 1.2 if dy > 0 else y + 2.8
        s.append(f'<text x="{x + 1.5 * dx}" y="{ly}" font-size="2.6" fill="#1040c0" text-anchor="{anchor}">{t}</text>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}mm" height="{PAGE_H}mm" '
           f'viewBox="0 0 {PAGE_W} {PAGE_H}" font-family="Helvetica, Arial, sans-serif">'
           + "".join(s) + "</svg>")
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>ACT eval position grid</title>"
            "<style>@page{margin:0}body{margin:0}</style></head><body>" + svg + "</body></html>")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out} ({len(positions)} positions)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minimal", action="store_true",
                    help="Bare graph-paper grid + dots only, no titles/instructions.")
    args = ap.parse_args()

    positions = read_positions()
    dirs = label_offsets(positions)
    if args.minimal:
        render_minimal(positions, dirs, "eval_position_grid.html")
        return
    s = []

    # 1 cm grid over the +/-5 cm zone, heavier lines on the axes.
    for v in range(-5, 6):
        lw = 0.5 if v == 0 else 0.15
        (x1, y1), (x2, y2) = pt(v, -5), pt(v, 5)
        s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#999" stroke-width="{lw}"/>')
        (x1, y1), (x2, y2) = pt(-5, v), pt(5, v)
        s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#999" stroke-width="{lw}"/>')
        if v != 0:
            x, y = pt(v, -5.4)
            s.append(f'<text x="{x}" y="{y}" font-size="2.4" fill="#666" text-anchor="middle">{v}</text>')
            x, y = pt(-5.5, v)
            s.append(f'<text x="{x}" y="{y + 0.8}" font-size="2.4" fill="#666" text-anchor="end">{v}</text>')

    # Zone border.
    x0, y0 = pt(-5, 5)
    s.append(f'<rect x="{x0}" y="{y0}" width="100" height="100" fill="none" stroke="#222" stroke-width="0.4"/>')

    # Origin cross (workspace center).
    (x1, y1), (x2, y2) = pt(-0.4, 0), pt(0.4, 0)
    s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="red" stroke-width="0.5"/>')
    (x1, y1), (x2, y2) = pt(0, -0.4), pt(0, 0.4)
    s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="red" stroke-width="0.5"/>')
    x, y = pt(0.2, 0.4)
    s.append(f'<text x="{x}" y="{y}" font-size="2.4" fill="red">center</text>')

    # Axis direction arrows.
    (x1, y1), (x2, y2) = pt(5.4, 0), pt(6.4, 0)
    s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="black" stroke-width="0.4"/>')
    s.append(f'<path d="M {x2} {y2} l -1.5 -1 v 2 z" fill="black"/>')
    s.append(f'<text x="{x2 + 2}" y="{y2 + 1.2}" font-size="3.5">+x</text>')
    (x1, y1), (x2, y2) = pt(0, 5.4), pt(0, 6.4)
    s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="black" stroke-width="0.4"/>')
    s.append(f'<path d="M {x2} {y2} l -1 1.5 h 2 z" fill="black"/>')
    s.append(f'<text x="{x2}" y="{y2 - 2}" font-size="3.5" text-anchor="middle">+y</text>')

    x, y = pt(0, -6.5)
    s.append(f'<text x="{x}" y="{y}" font-size="5" font-weight="bold" text-anchor="middle">ROBOT BASE THIS SIDE</text>')

    # Numbered trial dots (place the CUBE CENTER on the dot).
    for t, xc, yc in positions:
        x, y = pt(xc, yc)
        dx, dy = dirs[t]
        s.append(f'<circle cx="{x}" cy="{y}" r="0.8" fill="black"/>')
        anchor = "start" if dx > 0 else "end"
        ly = y - 1.2 if dy > 0 else y + 2.8
        s.append(f'<text x="{x + 1.5 * dx}" y="{ly}" font-size="2.6" fill="#1040c0" text-anchor="{anchor}">{t}</text>')

    # Title and instructions.
    s.append('<text x="105" y="22" font-size="6" font-weight="bold" text-anchor="middle">'
             'ACT Eval — Random Cube Positions (50 trials)</text>')
    s.append('<text x="105" y="30" font-size="3.8" fill="red" text-anchor="middle">'
             'Print at 100% / &quot;Actual size&quot; — do NOT use &quot;Fit to page&quot;</text>')
    s.append('<text x="105" y="37" font-size="3.2" text-anchor="middle">'
             'Align red cross with workspace center, +y pointing away from the robot base.</text>')
    s.append('<text x="105" y="42" font-size="3.2" text-anchor="middle">'
             'Place the cube CENTER on the numbered dot for each trial.</text>')

    # Scale-check bar: exactly 100 mm.
    bx, by = 55, 245
    s.append(f'<line x1="{bx}" y1="{by}" x2="{bx + 100}" y2="{by}" stroke="black" stroke-width="0.5"/>')
    for tick in (0, 100):
        s.append(f'<line x1="{bx + tick}" y1="{by - 2}" x2="{bx + tick}" y2="{by + 2}" stroke="black" stroke-width="0.5"/>')
    s.append(f'<text x="105" y="{by + 6}" font-size="3.2" text-anchor="middle">'
             'scale check: this bar must measure exactly 10 cm</text>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}mm" height="{PAGE_H}mm" '
           f'viewBox="0 0 {PAGE_W} {PAGE_H}" font-family="Helvetica, Arial, sans-serif">'
           + "".join(s) + "</svg>")
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>ACT eval position template</title>"
            "<style>@page{margin:0}"
            "body{margin:0}</style></head><body>" + svg + "</body></html>")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT} ({len(positions)} positions)")


if __name__ == "__main__":
    main()
