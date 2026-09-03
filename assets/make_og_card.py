#!/usr/bin/env python3
"""Generate the default social-share card (assets/og-default.png, 1200x630).

Run locally when the card design changes, then commit the resulting PNG.
CI does not run this, so the workflow needs no extra dependencies.

    python3 assets/make_og_card.py

Requires `rsvg-convert` (librsvg), which shapes text through Pango/HarfBuzz.

Do NOT go back to drawing the text with Pillow: this machine's Pillow reports
`PIL.features.check("raqm") == False`, so it silently falls back to
Layout.BASIC, which paints codepoints in logical order with no shaping. That
gives no matra reordering and no conjuncts -- आशिष came out as आशषि.
"""
import base64
import subprocess
import tempfile
from pathlib import Path

W, H = 1200, 630
HERE = Path(__file__).resolve().parent

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" fill="#fafaf8"/>
  <image x="80" y="78" width="150" height="150" href="data:image/png;base64,{logo}"/>
  <text x="80" y="332" font-family="Georgia" font-weight="bold" font-size="76" fill="#111111">Ashish Mahabal</text>
  <text x="80" y="416" font-family="Devanagari Sangam MN" font-size="58" fill="#111111">आशिष महाबळ</text>
  <line x1="80" y1="505" x2="{rule_end}" y2="505" stroke="#c8c8c3" stroke-width="2"/>
  <text x="80" y="562" font-family="Georgia" font-size="30" fill="#6e6e69">ashishmahabal.github.io/writings</text>
</svg>
"""


def main() -> None:
    logo = base64.b64encode((HERE / "favicon-192.png").read_bytes()).decode("ascii")
    svg = SVG.format(w=W, h=H, rule_end=W - 80, logo=logo)

    out = HERE / "og-default.png"
    # The SVG is scratch, not a source file -- build.sh copies assets/ wholesale
    # into site/, so leaving it here would publish it.
    with tempfile.NamedTemporaryFile("w", suffix=".svg", encoding="utf-8") as src:
        src.write(svg)
        src.flush()
        subprocess.run(
            ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(out), src.name],
            check=True,
        )
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
