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
import argparse
import base64
import functools
import json
import html
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

# Reuse the site's own date/venue parsing rather than duplicating it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generate_from_csv import clean_str, month_key, venue_display, year_int  # noqa: E402

W, H = 1200, 630
HERE = Path(__file__).resolve().parent
OG_DIR = HERE / "og"          # per-work cards live here
MANIFEST = OG_DIR / "manifest.json"

# Bump whenever the card DESIGN changes. Card content alone cannot detect a layout
# change, so without this a redesign would silently leave every card stale.
LAYOUT_VERSION = 4
CSV = HERE.parent / "IndexOfPublished_revised.csv"

INK = "#111111"
MUTED = "#6e6e69"
BG = "#fafaf8"
RULE = "#c8c8c3"
DEVA = "Devanagari Sangam MN"
SERIF = "Georgia"
# Titles are Marathi, Hindi or English. Georgia first so Latin titles match the
# name below; fontconfig falls back per glyph to the Devanagari face otherwise.
TITLE_FAMILY = f"{SERIF}, {DEVA}"

URL_TEXT = "ashishmahabal.github.io/writings"
URL_SIZE = 30
LOGO_X, LOGO_Y, LOGO_SIZE = 80, 48, 150
RULE_Y = 505

# Cover box, anchored bottom-right. The rule stops at the URL's width, so a cover
# may drop past RULE_Y to sit level with the URL baseline.
BOX_RIGHT, BOX_BOTTOM, BOX_MAX_W, BOX_MAX_H, BOX_GAP = 1120, 572, 300, 345, 14

# Venue -> cover image. Filenames follow no convention, so this map is manual:
# a new book or anthology means adding a line here.
COVERS = {
    "घोस्ट रायटर आणि इतर विज्ञानकथा": "images/books/ghost_writer_book_01.jpg",
    "Inner Space and Outer Thoughts": "images/anthologies/inner_space_and_outer_thoughts_anthology_english_01.jpg",
    "मन्वंतर": "images/anthologies/manvantar_anthology_01.jpg",
    "विज्ञानिनी भाग २": "images/anthologies/vidnyanini2_anthology_02.jpg",
    "पूर्वसंचित गोफ नात्यांचा": "images/anthologies/poorvasanchit_goph_natyacha_anthology_03.jpg",
    "तर्किष्ट": "images/anthologies/Tarkishta.jpg",
    "तर्कटपंजरी": "images/anthologies/TarkatPanjari.jpg",
}

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" fill="#fafaf8"/>
  <image x="80" y="78" width="150" height="150" href="data:image/png;base64,{logo}"/>
  <text x="80" y="332" font-family="Georgia" font-weight="bold" font-size="76" fill="#111111">Ashish Mahabal</text>
  <text x="80" y="416" font-family="Devanagari Sangam MN" font-size="58" fill="#111111">आशिष महाबळ</text>
  <line x1="80" y1="505" x2="{rule_end}" y2="505" stroke="#c8c8c3" stroke-width="2"/>
  <text x="80" y="562" font-family="Georgia" font-size="30" fill="#6e6e69">ashishmahabal.github.io/writings</text>
</svg>
"""


def _svg_doc(body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="{BG}"/>'
            f'{body}</svg>')


def _rasterize(svg: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".svg", encoding="utf-8") as f:
        f.write(svg)
        f.flush()
        subprocess.run(
            ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(out), f.name],
            check=True,
        )


@functools.lru_cache(maxsize=None)
def ink_width(text: str, family: str, size: int, bold: bool = False) -> int:
    """Rendered width of a string, measured by rasterizing and finding the ink box.

    SVG has no automatic wrapping, so titles must be wrapped by hand, and Pillow's
    font metrics cannot be trusted for Devanagari here (no HarfBuzz => no shaping,
    so conjuncts are mis-measured). Measuring what rsvg actually draws is exact.
    """
    if not text.strip():
        return 0
    w = max(400, int(len(text) * size * 1.6) + 200)
    h = int(size * 3)
    weight = ' font-weight="bold"' if bold else ""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
           f'<rect width="{w}" height="{h}" fill="#fff"/>'
           f'<text x="10" y="{int(size * 1.9)}" font-family="{family}" font-size="{size}"'
           f'{weight} fill="#000">{html.escape(text)}</text></svg>')
    with tempfile.NamedTemporaryFile("w", suffix=".svg", encoding="utf-8") as f:
        f.write(svg)
        f.flush()
        out = Path(f.name + ".png")
        subprocess.run(["rsvg-convert", "-o", str(out), f.name], check=True)
    bbox = ImageOps.invert(Image.open(out).convert("L")).getbbox()
    out.unlink()
    return (bbox[2] - 10) if bbox else 0


def wrap(text: str, family: str, size: int, max_w: int) -> list:
    """Greedy word wrap against measured widths."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and ink_width(trial, family, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


# Vertical band the title may occupy: from the top of the logo down to clear
# space above the name block.
TITLE_TOP, TITLE_BOTTOM = LOGO_Y, 240
LINE_RATIO = 1.34


def fit_title(text: str, family: str, max_w: int, max_lines: int = 3) -> tuple:
    """Largest size from a ladder that fits the title in both width and height.

    Line count alone is not enough: three lines at 72px are 288px tall, which
    overruns the top of the canvas and collides with the name below.
    """
    budget = TITLE_BOTTOM - TITLE_TOP
    for size in (72, 64, 56, 52, 48, 42, 36):
        lines = wrap(text, family, size, max_w)
        if len(lines) <= max_lines and len(lines) * int(size * LINE_RATIO) <= budget:
            return size, lines
    return 32, wrap(text, family, 32, max_w)



def work_rows_sorted(rows):
    g = rows.copy()
    g["_y"] = g["Year"].apply(year_int)
    g["_m"] = g["Month"].apply(month_key)
    return g.sort_values(["_y", "_m"], kind="mergesort")


def work_credit(rows) -> str:
    """Every venue this work appeared in, oldest first, on one line.

    Showing the whole publication history means there is no rule to pick between
    "first appeared in" and "collected in", and every book contributes its cover.
    """
    parts = []
    for _, r in work_rows_sorted(rows).iterrows():
        venue = venue_display(clean_str(r.get("Venue", "")), r)
        y = year_int(r.get("Year"))
        when = " ".join(x for x in (clean_str(r.get("Month", "")), str(y) if y else "") if x)
        part = " \u00b7 ".join(x for x in (venue, when) if x)
        if part and part not in parts:
            parts.append(part)
    # "Venue - date" keeps the middot, so the 78 single-venue cards read exactly as
    # before; a heavier separator divides venues when there is more than one.
    return "  |  ".join(parts)


def work_covers(rows) -> list:
    """Cover images for the books/anthologies this work appeared in, oldest first."""
    out = []
    for _, r in work_rows_sorted(rows).iterrows():
        rel = COVERS.get(clean_str(r.get("Venue", "")))
        if rel and rel not in out and (HERE / rel).exists():
            out.append(rel)
    return out


def card_state(df) -> dict:
    """work_id -> the content that determines its card. Cheap: no rendering."""
    state = {}
    for wid, rows in df.groupby("work_id", sort=True):
        state[str(wid)] = {
            "title": clean_str(rows.iloc[0]["Title"]),
            "credit": work_credit(rows),
            "covers": work_covers(rows),
        }
    return state


def card_path(work_id: str):
    """The rendered card for a work, whichever extension it uses."""
    for ext in (".jpg", ".png"):
        f = OG_DIR / f"{work_id}{ext}"
        if f.exists():
            return f
    return None


def read_manifest() -> tuple:
    if not MANIFEST.exists():
        return None, {}
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return data.get("layout"), data.get("cards", {})
    except (json.JSONDecodeError, OSError):
        return None, {}


def plan(df) -> tuple:
    """Return (state, todo, orphans). todo = work_ids needing a render."""
    state = card_state(df)
    layout, cards = read_manifest()

    if layout != LAYOUT_VERSION:
        # Design changed: every card is stale regardless of content.
        return state, sorted(state), _orphans(state)

    todo = [
        wid for wid, want in state.items()
        if cards.get(wid) != want or not card_path(wid)
    ]
    return state, sorted(todo), _orphans(state)


def _orphans(state: dict) -> list:
    """PNGs with no matching row. Reported, never deleted."""
    if not OG_DIR.exists():
        return []
    found = list(OG_DIR.glob("*.png")) + list(OG_DIR.glob("*.jpg"))
    return sorted({f.stem for f in found if f.stem not in state})


def write_manifest(state: dict) -> None:
    OG_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"layout": LAYOUT_VERSION, "cards": state},
                   ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _cover_svg(covers: list, credit_bottom: float) -> str:
    """Covers laid out side by side, bottom-right, fitted inside the box.

    Covers are portrait (cover scans) or landscape (photos of the book), so the
    aspect ratio cannot be assumed; each is fitted rather than cropped.
    """
    if not covers:
        return ""
    n = len(covers)
    slot_w = (BOX_MAX_W - BOX_GAP * (n - 1)) / n
    avail_h = min(BOX_MAX_H, BOX_BOTTOM - (credit_bottom + 26))

    boxes = []
    for rel in covers:
        iw, ih = Image.open(HERE / rel).size
        ratio = iw / ih
        h = avail_h
        w = h * ratio
        if w > slot_w:
            w = slot_w
            h = w / ratio
        boxes.append((rel, w, h))

    x = BOX_RIGHT - (sum(b[1] for b in boxes) + BOX_GAP * (n - 1))
    out = ""
    for rel, w, h in boxes:
        y = BOX_BOTTOM - h
        data = base64.b64encode((HERE / rel).read_bytes()).decode("ascii")
        out += (f'<image x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
                f'href="data:image/jpeg;base64,{data}"/>'
                f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
                f'fill="none" stroke="{RULE}" stroke-width="1"/>')
        x += w + BOX_GAP
    return out


def make_work_card(work_id: str, title: str, out_stem: Path, credit: str = "",
                   covers: list = ()) -> tuple:
    """Per-work card. Writes .jpg when it carries cover art, else .png.

    Cover art is photographic and roughly triples the card's area, which pushes a
    PNG towards 250 KB -- close to the size where WhatsApp stops showing a
    preview. JPEG lands near 80 KB with no visible difference.
    """
    logo = base64.b64encode((HERE / "favicon-192.png").read_bytes()).decode("ascii")

    title_x, title_right = 270, W - 80
    max_w = title_right - title_x
    size, lines = fit_title(title, TITLE_FAMILY, max_w)
    lh = int(size * LINE_RATIO)

    block_h = len(lines) * lh
    top = max(TITLE_TOP, LOGO_Y + LOGO_SIZE / 2 - block_h / 2)
    top = min(top, TITLE_BOTTOM - block_h)
    centre = top + block_h / 2
    first_baseline = centre - (len(lines) - 1) * lh / 2 + size * 0.34

    tspans = "".join(
        f'<tspan x="{title_right}" y="{first_baseline + i * lh:.0f}">{html.escape(ln)}</tspan>'
        for i, ln in enumerate(lines)
    )

    # Credit: shrink to fit, then wrap right-justified if still too wide.
    credit_size = 28
    credit_lines = []
    if credit:
        while credit_size > 18 and ink_width(credit, TITLE_FAMILY, credit_size) > max_w:
            credit_size -= 2
        credit_lines = wrap(credit, TITLE_FAMILY, credit_size, max_w)
    credit_y = min(top + block_h + 38, TITLE_BOTTOM + 50)
    clh = int(credit_size * 1.35)
    credit_svg = ""
    if credit_lines:
        ctspans = "".join(
            f'<tspan x="{title_right}" y="{credit_y + i * clh:.0f}">{html.escape(ln)}</tspan>'
            for i, ln in enumerate(credit_lines)
        )
        credit_svg = (f'<text text-anchor="end" font-family="{TITLE_FAMILY}" '
                      f'font-size="{credit_size}" fill="{MUTED}">{ctspans}</text>')
    credit_bottom = credit_y + (len(credit_lines) - 1) * clh if credit_lines else credit_y

    # The rule underlines the URL rather than dividing the card, which frees the
    # bottom-right corner for the cover.
    rule_end = 80 + ink_width(URL_TEXT, SERIF, URL_SIZE)

    body = f"""
  <image x="{LOGO_X}" y="{LOGO_Y}" width="{LOGO_SIZE}" height="{LOGO_SIZE}" href="data:image/png;base64,{logo}"/>
  <text text-anchor="end" font-family="{TITLE_FAMILY}" font-size="{size}" fill="{INK}">{tspans}</text>
  {credit_svg}
  {_cover_svg(list(covers), credit_bottom)}
  <text x="80" y="420" font-family="{SERIF}" font-weight="bold" font-size="44" fill="{INK}">Ashish Mahabal</text>
  <text x="80" y="470" font-family="{DEVA}" font-size="34" fill="{INK}">आशिष महाबळ</text>
  <line x1="80" y1="{RULE_Y}" x2="{rule_end}" y2="{RULE_Y}" stroke="{RULE}" stroke-width="2"/>
  <text x="80" y="562" font-family="{SERIF}" font-size="{URL_SIZE}" fill="{MUTED}">{URL_TEXT}</text>
"""
    png = out_stem.with_suffix(".png")
    jpg = out_stem.with_suffix(".jpg")
    _rasterize(_svg_doc(body), png)
    if covers:
        Image.open(png).convert("RGB").save(jpg, "JPEG", quality=85, optimize=True)
        png.unlink()
        out = jpg
    else:
        jpg.unlink(missing_ok=True)      # a work can lose its cover
        out = png
    return size, len(lines), credit_size, out


def main() -> None:
    ap = argparse.ArgumentParser(description="Render social-share cards.")
    ap.add_argument("work_id", nargs="?", help="render this work's card into assets/og/ "
                                               "instead of the default card")
    ap.add_argument("--all", action="store_true", help="render a card for every work in the CSV")
    ap.add_argument("--sync", action="store_true",
                    help="render only cards that are missing or out of date, then "
                         "update the manifest")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any card is missing or stale; renders "
                         "nothing, so it is safe to run in CI")
    args = ap.parse_args()

    if args.work_id or args.all or args.sync or args.check:
        import pandas as pd
        df = pd.read_csv(CSV)
        df["work_id"] = df["work_id"].astype(str)

        if args.check:
            state, todo, orphans = plan(df)
            for wid in orphans:
                print(f"orphan: assets/og/{wid}.png has no row in {CSV.name}")
            if todo:
                print(f"{len(todo)} card(s) missing or stale: {', '.join(todo)}")
                print("Run: python3 assets/make_og_card.py --sync")
                raise SystemExit(1)
            print(f"cards up to date ({len(state)} works, layout v{LAYOUT_VERSION})")
            return

        if args.sync:
            state, todo, orphans = plan(df)
            for wid in orphans:
                print(f"orphan: assets/og/{wid}.png has no row in {CSV.name}")
            for wid in todo:
                rows = df[df["work_id"] == wid]
                _, _, _, out = make_work_card(
                    wid, clean_str(rows.iloc[0]["Title"]), OG_DIR / wid,
                    work_credit(rows), work_covers(rows))
                cov = f"  [{len(state[wid]['covers'])} cover]" if state[wid]["covers"] else ""
                print(f"  rendered {out.name}{cov}  {state[wid]['credit']}")
            write_manifest(state)
            print(f"cards: {len(todo)} rendered, {len(state) - len(todo)} unchanged, "
                  f"{len(orphans)} orphan(s)")
            return

        if args.all:
            ids = sorted(df["work_id"].dropna().unique())
        else:
            ids = [args.work_id]
            if args.work_id not in set(df["work_id"]):
                raise SystemExit(f"{args.work_id} not found in {CSV.name}")

        for wid in ids:
            rows = df[df["work_id"] == wid]
            title = clean_str(rows.iloc[0]["Title"])
            credit = work_credit(rows)
            covers = work_covers(rows)
            size, n, csize, out = make_work_card(wid, title, OG_DIR / wid, credit, covers)
            flags = []
            if size <= 42:
                flags.append(f"SMALL TITLE {size}px")
            if n >= 3:
                flags.append(f"{n} LINES")
            if csize < 28:
                flags.append(f"credit shrunk to {csize}px")
            if covers:
                flags.append(f"{len(covers)} cover(s)")
            print(f"{wid:<14} {size:>3}px/{n}L  {credit}" + ("   <-- " + ", ".join(flags) if flags else ""))
        if args.all:
            write_manifest(card_state(df))
        return

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
