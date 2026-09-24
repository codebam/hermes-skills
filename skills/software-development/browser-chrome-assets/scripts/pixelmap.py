#!/usr/bin/env python3
"""Print a screenshot region as a hex grid plus a luminance summary.

Usage: pixelmap.py <png> <x> <y> <w> <h> [label]

Screenshots are read through ImageMagick (`magick ... txt:-`), so any format works and the
sampled pixels are the real ones (no box-filter blur). Use it to answer "is this glyph lighter
or darker than the surface it sits on" for favicons, tab strips and other browser chrome.
"""
import re
import subprocess
import sys


def pixelmap(png, x, y, w, h, label=""):
    out = subprocess.run(
        ["magick", png, "-crop", f"{w}x{h}+{x}+{y}", "+repage", "txt:-"],
        capture_output=True, text=True,
    ).stdout
    rows = {}
    for line in out.splitlines():
        m = re.match(r"(\d+),(\d+):.*?(#[0-9A-Fa-f]{6})", line)
        if m:
            rows.setdefault(int(m.group(2)), {})[int(m.group(1))] = m.group(3).lstrip("#").upper()
    if not rows:
        print(f"no pixels read from {png} ({w}x{h}+{x}+{y}) — check the crop")
        return 1

    print(f"--- {label or png} ({w}x{h}+{x}+{y}) ---")
    for row in sorted(rows):
        print(f"{row:2d} " + " ".join(rows[row][col][:2] for col in sorted(rows[row])))

    lum = lambda v: (int(v[0:2], 16) + int(v[2:4], 16) + int(v[4:6], 16)) / 3
    values = [lum(v) for r in rows.values() for v in r.values()]
    # the surface the glyph sits on is the most common value in the crop
    background = max(set(values), key=values.count)
    brighter = sum(1 for v in values if v > background + 20)
    darker = sum(1 for v in values if v < background - 20)
    print(f"  background={background:.0f}  pixels brighter={brighter}  darker={darker}")
    print("  (a light-on-dark glyph shows brighter>0, darker=0; the inverse shows the opposite)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 6:
        print(__doc__)
        sys.exit(2)
    png = sys.argv[1]
    x, y, w, h = (int(v) for v in sys.argv[2:6])
    sys.exit(pixelmap(png, x, y, w, h, " ".join(sys.argv[6:])))
