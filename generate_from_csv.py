#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate/update Markdown stubs, indices, venue pages, and per-work publication history
from an appearance-centric CSV.

v6:
- Robust year formatting everywhere (no int(NaN) failures).
- Internal links work locally and on GitHub Pages project sites via BASEURL.
  - Local: BASEURL="" (default)  -> /fiction/...
  - GitHub Pages: BASEURL="/writings" -> /writings/fiction/...

Required CSV columns:
work_id, Title, Pubtype, Venue, Kind, Subtype, Language, Year, Month
Optional: Translation
All other columns ignored.

Usage:
  python3 generate_from_csv.py IndexOfPublished_revised.csv
  ./build.sh

CI example:
  BASEURL="/writings" python3 generate_from_csv.py IndexOfPublished_revised.csv
  ./build.sh
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

LANG_CANON = {"Marathi": "Marathi", "Hindi": "Hindi", "English": "English"}
KIND_MAP = {
    "कथा": "fiction",
    "लेख": "nonfiction",
    "poem": "poem",
    "fiction": "fiction",
    "nonfiction": "nonfiction",
}

AUTO_START = "<!-- AUTO:PUBLICATION_HISTORY:START -->"
AUTO_END = "<!-- AUTO:PUBLICATION_HISTORY:END -->"

WORK_HERO_START = "<!-- AUTO:WORK_HERO:START -->"
WORK_HERO_END = "<!-- AUTO:WORK_HERO:END -->"

# Optional: display-time context suffix for venues (keeps canonical venue identity unchanged)
# If your CSV has a column VenueContext, that will override these defaults per-row.
VENUE_CONTEXT_SUFFIX: Dict[str, str] = {
    "Aisi Akshare": "Diwali Special",
    "Maayboli": "Diwali Issue",
    "MMLA": "Diwali Ank",
}

WORK_META_START = "<!-- AUTO:WORK_META:START -->"
WORK_META_END = "<!-- AUTO:WORK_META:END -->"


FM_BOUNDARY = re.compile(r"^---\s*$", flags=re.M)


def norm_lang_full(x: object) -> str:
    s = str(x).strip()
    return LANG_CANON.get(s, s if s else "Unknown")


def norm_kind(x: object) -> str:
    s = str(x).strip()
    return KIND_MAP.get(s, s)


def clean_str(x: object) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in ("none", "nan"):
        return ""
    return s


def is_nan(x: object) -> bool:
    try:
        return x != x  # NaN is the only value not equal to itself
    except Exception:
        return False


def year_int(x: object) -> Optional[int]:
    """Best-effort int year for sorting/grouping; returns None if missing."""
    if x is None or is_nan(x):
        return None
    try:
        return int(float(x))
    except Exception:
        s = clean_str(x)
        if not s:
            return None
        m = re.search(r"(\d{4})", s)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        return None


def year_str(x: object) -> str:
    """Safe display year string; returns "" if missing/invalid."""
    y = year_int(x)
    return str(y) if y is not None else ""


def month_key(x: object) -> int:
    s = clean_str(x)
    if not s:
        return 99
    try:
        return int(float(s))
    except Exception:
        pass
    s2 = s.lower()
    names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    for i, n in enumerate(names, start=1):
        if s2.startswith(n):
            return i
    return 98


def require_site_root() -> None:
    if not Path("build.sh").exists():
        raise SystemExit("Please run from the site repo root (where build.sh is).")


def split_front_matter(text: str) -> Tuple[Optional[str], str]:
    matches = list(FM_BOUNDARY.finditer(text))
    if len(matches) >= 2 and matches[0].start() == 0:
        body = text[matches[1].end() :].lstrip("\n")
        return text[matches[0].end() : matches[1].start()].strip("\n"), body
    return None, text


def dump_front_matter(data: Dict) -> str:
    y = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        width=1000,
        default_flow_style=False,
    ).strip()
    return f"---\n{y}\n---\n"

def ensure_auto_block(body: str, start_marker: str, end_marker: str, heading: str = "") -> str:
    """Ensure an auto-update block exists; if missing, append it at the end."""
    if start_marker in body and end_marker in body:
        return body
    extra = ""
    if heading:
        extra += f"\n\n{heading}\n\n"
    extra += f"{start_marker}\n(auto)\n{end_marker}\n"
    return body.rstrip() + extra


def replace_auto_block(body: str, start_marker: str, end_marker: str, new_block_md: str, heading: str = "") -> str:
    """Replace only the contents between start_marker and end_marker."""
    body2 = ensure_auto_block(body, start_marker, end_marker, heading=heading)
    s = body2.find(start_marker)
    e = body2.find(end_marker)
    if s == -1 or e == -1 or e < s:
        return body2
    before = body2[: s + len(start_marker)]
    after = body2[e:]
    mid = "\n" + new_block_md.strip() + "\n"
    return before + mid + after


def write_md_update_block_only(
    path: Path,
    front_matter: Dict,
    start_marker: str,
    end_marker: str,
    new_block_md: str,
    heading: str = "",
) -> None:
    """
    If file exists: keep human-authored body except the auto block.
    If file does not exist: create it with just front matter + the auto block.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        _, body = split_front_matter(existing)
        body = replace_auto_block(body, start_marker, end_marker, new_block_md, heading=heading)
        path.write_text(dump_front_matter(front_matter) + "\n" + body, encoding="utf-8")
    else:
        body = replace_auto_block("", start_marker, end_marker, new_block_md, heading=heading)
        path.write_text(dump_front_matter(front_matter) + "\n" + body.strip() + "\n", encoding="utf-8")


def ensure_pubhistory_block(body: str) -> str:
    if AUTO_START in body and AUTO_END in body:
        return body
    extra = (
        "\n\n## Publication history\n\n"
        + AUTO_START
        + "\n*(auto-generated)*\n"
        + AUTO_END
        + "\n"
    )
    return body.rstrip() + extra


def replace_pubhistory_block(body: str, new_block_md: str) -> str:
    body2 = ensure_pubhistory_block(body)
    start = body2.find(AUTO_START)
    end = body2.find(AUTO_END)
    if start == -1 or end == -1 or end < start:
        return body2
    before = body2[: start + len(AUTO_START)]
    after = body2[end:]
    mid = "\n" + new_block_md.strip() + "\n"
    return before + mid + after



def ensure_workhero_block(body: str) -> str:
    """Ensure hero marker block exists at top of body (after H1), if not present."""
    if WORK_HERO_START in body and WORK_HERO_END in body:
        return body
    lines = body.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("# "):
            insert_at = i + 1
            if insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            break
    block = [WORK_HERO_START, "", WORK_HERO_END, ""]
    lines[insert_at:insert_at] = block
    return "\n".join(lines)

def replace_workhero_block(body: str, new_block_md: str) -> str:
    body2 = ensure_workhero_block(body)
    start = body2.find(WORK_HERO_START)
    end = body2.find(WORK_HERO_END)
    if start == -1 or end == -1 or end < start:
        return body2
    before = body2[: start + len(WORK_HERO_START)]
    after = body2[end:]
    mid = "\n" + new_block_md.strip() + "\n" if new_block_md.strip() else "\n"
    return before + mid + after


def ensure_workmeta_block(body: str) -> str:
    """Ensure work meta marker block exists just after the hero block (or after H1)."""
    if WORK_META_START in body and WORK_META_END in body:
        return body
    lines = body.splitlines()

    # Prefer inserting after the WORK_HERO block if present
    insert_at = 0
    if WORK_HERO_END in body:
        for i, line in enumerate(lines):
            if line.strip() == WORK_HERO_END:
                insert_at = i + 1
                if insert_at < len(lines) and lines[insert_at].strip() == "":
                    insert_at += 1
                break
    else:
        # Fallback: after H1
        for i, line in enumerate(lines):
            if line.lstrip().startswith("# "):
                insert_at = i + 1
                if insert_at < len(lines) and lines[insert_at].strip() == "":
                    insert_at += 1
                break

    block = [WORK_META_START, "", WORK_META_END, ""]
    lines[insert_at:insert_at] = block
    return "\n".join(lines)


def replace_workmeta_block(body: str, new_block_md: str) -> str:
    body2 = ensure_workmeta_block(body)
    start = body2.find(WORK_META_START)
    end = body2.find(WORK_META_END)
    if start == -1 or end == -1 or end < start:
        return body2
    before = body2[: start + len(WORK_META_START)]
    after = body2[end:]
    mid = "\n" + new_block_md.strip() + "\n" if new_block_md.strip() else "\n"
    return before + mid + after


def workmeta_md_for_work(g: pd.DataFrame) -> str:
    """Auto meta block: co-authors and pen name."""
    coauthors = ""
    penname = ""

    if "Coauthors" in g.columns:
        for x in g["Coauthors"].tolist():
            x = clean_str(x)
            if x:
                coauthors = x
                break

    if "Penname" in g.columns:
        for x in g["Penname"].tolist():
            x = clean_str(x)
            if x:
                penname = x
                break

    lines: List[str] = []
    if coauthors:
        lines.append(f"*Co-authored with:* {coauthors}  ")
    if penname:
        lines.append(f"*Published under the pen name:* {penname}  ")

    return "\n".join(lines).strip()

def find_workhero_image(work_id: str) -> str:
    """Return the site-relative src path if an image exists for this work_id, else ""."""
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    rel_dir = Path("assets") / "images" / "stories"
    for ext in exts:
        rel = rel_dir / f"{work_id}-page1{ext}"
        if rel.exists():
            return link(rel.as_posix())
    return ""

def pick_preferred_appearance_for_hero(g: pd.DataFrame) -> Tuple[str, str]:
    """
    Choose which appearance to cite in the hero caption.
    Prefers Book > Anthology > Magazine > Online Magazine > others, then earliest by date.
    Returns (venue, year_str).
    """
    gg = g.copy()
    gg["YearNum"] = gg["Year"].apply(year_int)
    gg["MonthKey"] = gg["Month"].apply(month_key)
    gg["PubtypeClean"] = gg["Pubtype"].apply(lambda x: clean_str(x).lower())
    rank = {"book": 0, "anthology": 1, "magazine": 2, "online magazine": 3}
    gg["PubRank"] = gg["PubtypeClean"].map(lambda s: rank.get(s, 9))
    gg = gg.sort_values(["PubRank", "YearNum", "MonthKey", "Venue"], kind="mergesort")
    if len(gg) == 0:
        return ("", "")
    venue = clean_str(gg["Venue"].iloc[0])
    y_txt = year_str(gg["Year"].iloc[0])
    return (venue, y_txt)

def workhero_md_for_work(g: pd.DataFrame, venue_slug_map: Dict[str, str], work_id: str, title: str) -> str:
    """If a hero image exists for work_id, return the HTML+caption block; else ""."""
    src = find_workhero_image(work_id)
    if not src:
        return ""
    venue, y_txt = pick_preferred_appearance_for_hero(g)
    if venue:
        vslug = venue_slug_map.get(venue, slugify(venue))
        vlink = link(f"publications/venues/{vslug}/index.html")
        vmd = f"[{venue}]({vlink})"
    else:
        vmd = "(venue unknown)"
    when = f" ({y_txt})" if y_txt else ""
    return "\n".join(
        [
            '<div class="work-hero">',
            f'<img src="{src}" alt="Opening of {title}">',
            "</div>",
            "",
            f"First half of page 1. Appeared in {vmd}{when}.",
        ]
    )

def write_work_md(path: Path, front_matter: Dict, body_if_new: str, pubhistory_md: str, workhero_md: str = "", workmeta_md: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        _, body = split_front_matter(existing)
        body = replace_pubhistory_block(body, pubhistory_md)
        if workhero_md.strip():
            # Avoid duplicating if the same image was already manually inserted outside the auto block
            m = re.search(r'<img\s+[^>]*src="([^"]+)"', workhero_md)
            src = m.group(1) if m else ""
            if (not src) or (src not in body):
                body = replace_workhero_block(body, workhero_md)
        if workmeta_md.strip():
            body = replace_workmeta_block(body, workmeta_md)
        path.write_text(dump_front_matter(front_matter) + "\n" + body, encoding="utf-8")
    else:
        body = replace_pubhistory_block(body_if_new, pubhistory_md)
        if workhero_md.strip():
            body = replace_workhero_block(body, workhero_md)
        if workmeta_md.strip():
            body = replace_workmeta_block(body, workmeta_md)
        path.write_text(dump_front_matter(front_matter) + "\n" + body.strip() + "\n", encoding="utf-8")


def write_md_overwrite(path: Path, front_matter: Dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_front_matter(front_matter) + "\n" + body.strip() + "\n", encoding="utf-8")


def slugify(s: str) -> str:
    s = clean_str(s)
    if not s:
        return "venue-unknown"
    normalized = unicodedata.normalize("NFKD", s)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    if ascii_only:
        return ascii_only
    h = hashlib.md5(s.encode("utf-8")).hexdigest()[:10]
    return f"venue-{h}"


def work_output_path(kind: str, lang_full: str, work_id: str) -> Path:
    return Path(kind) / lang_full / f"{work_id}.md"


def work_stub_body(title: str) -> str:
    return f"""# {title}

*(Text to be added here.)*
"""


def get_baseurl() -> str:
    b = os.environ.get("BASEURL", "").strip()
    if b in ("", "/"):
        return ""
    return "/" + b.strip("/")


def link(path: str) -> str:
    base = get_baseurl()
    p = "/" + path.lstrip("/")
    return f"{base}{p}"


def venue_display(venue: str, row: Optional[pd.Series] = None) -> str:
    """Return display name for venue, optionally with a context suffix."""
    v = clean_str(venue)
    if not v:
        return ""
    ctx = ""
    if row is not None:
        ctx = clean_str(row.get("VenueContext", ""))
    if not ctx:
        ctx = VENUE_CONTEXT_SUFFIX.get(v, "")
    return f"{v} ({ctx})" if ctx else v

def link_unused(path: str) -> str:
    return path.lstrip("/")

def root_index_body() -> str:
    return "\n".join(
        [
            "# Writings",
            "",
            "Science fiction (primarily Marathi) and non-fiction (astronomy, rationalism, essays).",
            "",
            f"- [Fiction]({link('fiction/index.html')})",
            f"- [Non-Fiction]({link('nonfiction/index.html')})",
            f"- [Publications]({link('publications/index.html')})",
            "",
        ]
    )


def pubhistory_md_for_work(g: pd.DataFrame, venue_slug_map: Dict[str, str]) -> str:
    gg = g.copy()
    gg["YearNum"] = gg["Year"].apply(year_int)
    gg["MonthKey"] = gg["Month"].apply(month_key)
    gg = gg.sort_values(["YearNum", "MonthKey", "Venue", "Pubtype"], kind="mergesort")

    lines: List[str] = []
    for _, r in gg.iterrows():
        venue = clean_str(r.get("Venue", ""))
        pubtype = clean_str(r.get("Pubtype", ""))
        y_txt = year_str(r.get("Year", None))
        m = clean_str(r.get("Month", ""))

        vslug = venue_slug_map.get(venue, slugify(venue))
        vlink = link(f"publications/venues/{vslug}/index.html")
        vdisp = venue_display(venue, r)
        venue_md = f"[{vdisp}]({vlink})" if vdisp else "(venue unknown)"

        year_md = f"[{y_txt}]({link(f'publications/years/{y_txt}/index.html')})" if y_txt else ""

        when_parts: List[str] = []
        if m:
            when_parts.append(m)
        if y_txt:
            when_parts.append(y_txt)
        when = " ".join(when_parts).strip() or "(date unknown)"

        mid = f"{pubtype}: " if pubtype else ""
        tail = f" — {year_md}" if year_md else ""
        lines.append(f"- {when} — {mid}{venue_md}{tail}")

    return "\n".join(lines) if lines else "*(No publication data yet.)*"


def earliest_pub_hint(g: pd.DataFrame) -> str:
    gg = g.copy()
    gg["YearNum"] = gg["Year"].apply(year_int)
    gg["MonthKey"] = gg["Month"].apply(month_key)
    gg = gg.sort_values(["YearNum", "MonthKey", "Venue"], kind="mergesort")
    if not len(gg):
        return ""
    venue = clean_str(gg["Venue"].iloc[0])
    y_txt = year_str(gg["Year"].iloc[0])
    if venue and y_txt:
        return f"[{venue}, {y_txt}]"
    if venue:
        return f"[{venue}]"
    if y_txt:
        return f"[{y_txt}]"
    return ""


def generate_root_index() -> None:
#    write_md_overwrite(Path("index.md"), {"title": "Writings", "language": "English"}, root_index_body())
    start_marker = "<!-- AUTO:HOME_NAV:START -->"
    end_marker = "<!-- AUTO:HOME_NAV:END -->"

    block = "\n".join(
        [
            "## Sections",
            "",
            f"- [Fiction]({link('fiction/index.html')})",
            f"- [Non-Fiction]({link('nonfiction/index.html')})",
            f"- [Publications]({link('publications/index.html')})",
            "",
        ]
    )

    write_md_update_block_only(
        Path("index.md"),
        {"title": "Writings", "language": "English"},
        start_marker,
        end_marker,
        block,
    )


def generate_work_pages(df: pd.DataFrame, venue_slug_map: Dict[str, str]) -> None:
    for work_id, g in df.groupby("work_id", sort=True):
        title = clean_str(g["Title"].iloc[0])
        lang_full = norm_lang_full(g["Language"].iloc[0])
        kind = norm_kind(g["Kind"].iloc[0])
        subtype = clean_str(g["Subtype"].iloc[0]) if "Subtype" in g.columns else ""
        translation = clean_str(g["Translation"].iloc[0]) if "Translation" in g.columns else ""

        fm: Dict[str, object] = {"id": work_id, "title": title, "language": lang_full, "kind": kind}
        if subtype:
            fm["subtype"] = subtype
        if translation:
            fm["translation"] = translation

        pub_md = pubhistory_md_for_work(g, venue_slug_map)
        hero_md = workhero_md_for_work(g, venue_slug_map, work_id, title)
        meta_md = workmeta_md_for_work(g)
        write_work_md(work_output_path(kind, lang_full, work_id), fm, work_stub_body(title), pub_md, workhero_md=hero_md, workmeta_md=meta_md)


def generate_kind_indexes(df: pd.DataFrame, kind: str) -> None:
    items = df[df["kind_norm"] == kind].drop_duplicates("work_id").copy()

    hint_map: Dict[str, str] = {}
    for wid, g in df[df["kind_norm"] == kind].groupby("work_id", sort=False):
        hint_map[wid] = earliest_pub_hint(g)

    items = items.sort_values(["language_full", "Title"], kind="mergesort")
    langs = sorted(items["language_full"].unique().tolist())

    # --- Build only the auto-updated block for the top index page ---
    block_lines: List[str] = []
    block_lines.append("## By language")
    block_lines.append("")
    block_lines.append(" | ")
    for L in langs:
        block_lines.append(f"[{L}]({link(f'{kind}/{L}/index.html')})")
        block_lines.append(" | ")
    block_lines.append("")
    block_lines.append("## All")
    block_lines.append("")
    for _, r in items.iterrows():
        wid = r["work_id"]
        L = r["language_full"]
        title = r["Title"]
        hint = hint_map.get(wid, "")
        block_lines.append(f"- [{title}]({link(f'{kind}/{L}/{wid}.html')}) {hint}")
    block_lines.append("")

    start_marker = f"<!-- AUTO:{kind.upper()}_LIST:START -->"
    end_marker = f"<!-- AUTO:{kind.upper()}_LIST:END -->"

    write_md_update_block_only(
        Path(kind) / "index.md",
        {"title": kind.title(), "language": "English"},
        start_marker,
        end_marker,
        "\n".join(block_lines),
    )

    # --- Keep language-specific pages fully generated (overwrite is fine) ---
    for L in langs:
        sub = items[items["language_full"] == L].copy().sort_values(["Title"], kind="mergesort")
        body_lines = [f"# {kind.title()} ({L})", ""]
        for _, r in sub.iterrows():
            wid = r["work_id"]
            title = r["Title"]
            hint = hint_map.get(wid, "")
            body_lines.append(f"- [{title}]({link(f'{kind}/{L}/{wid}.html')}) {hint}")
        body_lines.append("")
        write_md_overwrite(
            Path(kind) / L / "index.md",
            {"title": f"{kind.title()} {L}", "language": L},
            "\n".join(body_lines),
        )


def generate_publications_index(df: pd.DataFrame, venue_slug_map: Dict[str, str]) -> None:
    d = df.copy()
    d["Pubtype"] = d["Pubtype"].astype("string").str.strip()
    d["Venue"] = d["Venue"].astype("string").str.strip()
    d["YearNum"] = d["Year"].apply(year_int)
    d["MonthKey"] = d["Month"].apply(month_key)

    # Build ONLY the auto-updated block (no "# Publications" here)
    block: List[str] = []
    block.append("## Browse")
    block.append("")
#    block.append(f"|")
#    block.append(f"|[By year]({link('publications/years/index.html')})")
#    block.append(" | ")
#    block.append(f"[By venue]({link('publications/venues/index.html')})")
#    block.append(" |")
    block.append(
        f"[By year]({link('publications/years/index.html')}) · "
        f"[By venue]({link('publications/venues/index.html')})"
    )
    block.append("")

    for pubtype, g1 in d.groupby("Pubtype", sort=True):
        block += [f"## {pubtype}", ""]
        for venue, g2 in g1.groupby("Venue", sort=True):
            vslug = venue_slug_map.get(venue, slugify(venue))
            vlink = link(f"publications/venues/{vslug}/index.html")
            block += [f"### [{venue}]({vlink})", ""]
            g2 = g2.sort_values(["YearNum", "MonthKey", "Title"], kind="mergesort")
            for _, r in g2.iterrows():
                title = r["Title"]
                wid = r["work_id"]
                k = r["kind_norm"]
                L = r["language_full"]

                when_parts: List[str] = []
                m = clean_str(r.get("Month", ""))
                if m:
                    when_parts.append(m)
                y_txt = year_str(r.get("Year", None))
                if y_txt:
                    when_parts.append(y_txt)
                when = " ".join(when_parts).strip()
                when = f" ({when})" if when else ""

                block.append(f"- [{title}]({link(f'{k}/{L}/{wid}.html')}){when}")
            block.append("")

    start_marker = "<!-- AUTO:PUBLICATIONS_INDEX:START -->"
    end_marker = "<!-- AUTO:PUBLICATIONS_INDEX:END -->"

    write_md_update_block_only(
        Path("publications") / "index.md",
        {"title": "Publications", "language": "English"},
        start_marker,
        end_marker,
        "\n".join(block),
    )


def generate_publications_year_indexes(df: pd.DataFrame) -> None:
    d = df.copy()
    d["YearNum"] = d["Year"].apply(year_int)
    d = d[d["YearNum"].notna()].copy()
    d["YearNum"] = d["YearNum"].astype(int)
    d["MonthKey"] = d["Month"].apply(month_key)

    # Precompute badge labels per row (kind + subtypes)
    d["_kind_label"] = d["kind_norm"].apply(kind_display)
    d["_subtype_labels"] = d.get("Subtype", "").apply(lambda x: parse_subtypes(clean_str(x)))

    years = sorted(d["YearNum"].unique().tolist())
    base = Path("publications") / "years"
    base.mkdir(parents=True, exist_ok=True)

    # Year index with counts + unique badges per year
    lines: List[str] = ["# Publications by year", ""]
    for y in years:
        suby = d[d["YearNum"] == y].copy()
        n = int(len(suby))

        kind_badges = sorted({clean_str(x) for x in suby["_kind_label"].tolist() if clean_str(x)})
        subtype_badges = sorted({lbl for labels in suby["_subtype_labels"].tolist() for lbl in (labels or []) if clean_str(lbl)})

        badges_html = ""
        if kind_badges or subtype_badges:
            parts: List[str] = []
            # subtypes first (usually the more "content" signal)
            parts += [badge_html(lbl, "subtype") for lbl in subtype_badges]
            parts += [badge_html(lbl, "kind") for lbl in kind_badges]
            badges_html = f' <span class="year-item__badges">{" ".join(parts)}</span>'

        lines.append(
            f'- <span class="year-item"><a href="{link(f"publications/years/{y}/index.html")}">{y}</a>'
            f' <span class="year-item__count">({n})</span>{badges_html}</span>'
        )
    lines.append("")
    write_md_overwrite(base / "index.md", {"title": "Publications by year", "language": "English"}, "\n".join(lines))

    # Individual year pages (fully generated)
    for y in years:
        sub = d[d["YearNum"] == y].copy()
        sub["Venue"] = sub["Venue"].astype("string").str.strip()
        sub = sub.sort_values(["Pubtype", "Venue", "MonthKey", "Title"], kind="mergesort")
        ydir = base / str(y)
        ydir.mkdir(parents=True, exist_ok=True)

        body: List[str] = [
            f"# Publications in {y}",
            "",
            f"- [Back to years]({link('publications/years/index.html')})",
            "",
        ]
        for pubtype, g1 in sub.groupby("Pubtype", sort=True):
            body += [f"## {pubtype}", ""]
            for venue, g2 in g1.groupby("Venue", sort=True):
                body += [f"### {venue_display(venue)}", ""]
                for _, r in g2.iterrows():
                    title = r["Title"]
                    wid = r["work_id"]
                    k = r["kind_norm"]
                    L = r["language_full"]
                    mtxt = clean_str(r.get("Month", ""))
                    mtxt = f"{mtxt} " if mtxt else ""
                    # Put badges at end of the row (consistent with your preference)
                    kind_label = kind_display(k)
                    sub_labels = parse_subtypes(clean_str(r.get("Subtype", "")))
                    badges = []
                    if kind_label:
                        badges.append(badge_html(kind_label, "kind"))
                    for sl in (sub_labels or []):
                        badges.append(badge_html(sl, "subtype"))
                    translation_val = clean_str(r.get("Translation", ""))
                    if translation_val:
                        badges.append(badge_html("Translation", "meta"))
                    badges_html = f' <span class="row-badges">{" ".join(badges)}</span>' if badges else ""
                    body.append(f"- [{title}]({link(f'{k}/{L}/{wid}.html')}) ({mtxt}{y}){badges_html}")
                body.append("")
        write_md_overwrite(ydir / "index.md", {"title": f"Publications {y}", "language": "English"}, "\n".join(body))


def kind_display(kind_norm: str) -> str:
    k = clean_str(kind_norm).lower()
    if k == "fiction":
        return "Fiction"
    if k == "nonfiction":
        return "Non-Fiction"
    if k == "poem":
        return "Poem"
    return k.title() if k else "Work"



# ---- Subtype badges (Marathi -> English) ----
SUBTYPE_MAP = {
    "बुद्धिप्रामाण्यवाद": "Rationalism",
    "विज्ञानकथा": "Sci-Fi",
    "कला": "Arts",
    "ललित": "Belles-lettres",
    "विज्ञान": "Science",
    "भाषा": "Language",
    "प्रवास": "Travel",
    "सामाजिक": "Social",
    "गणित": "Math",
    "साहित्य": "Literature",
}

_BADGE_CLEAN_RE = re.compile(r"[^\w\s-]", flags=re.UNICODE)
_BADGE_WS_RE = re.compile(r"\s+")

def slug_class(s: str) -> str:
    s = clean_str(s).lower()
    s = _BADGE_CLEAN_RE.sub("", s)
    s = _BADGE_WS_RE.sub("-", s).strip("-")
    return s or "tag"

def parse_subtypes(raw: str) -> List[str]:
    """Parse comma-separated subtype string; map Marathi tokens to English labels."""
    raw = clean_str(raw)
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]
    return [SUBTYPE_MAP.get(p, p) for p in parts]

def badge_html(label: str, kind: str) -> str:
    """kind: 'kind', 'subtype', or 'meta' (affects CSS class namespace)."""
    cls = slug_class(label)
    return f'<span class="badge badge--{kind} badge--{kind}-{cls}">{label}</span>'

def generate_venue_pages(df: pd.DataFrame, venue_slug_map: Dict[str, str]) -> None:
    base = Path("publications") / "venues"
    base.mkdir(parents=True, exist_ok=True)

    venues = sorted({clean_str(v) for v in df["Venue"].tolist() if clean_str(v)})

    # Venues index (still fully generated; you can convert later the same way)
    lines = [
        "# Venues",
        "",
        "Where the pieces appeared (magazines, newsletters, books, anthologies, etc.).",
        "",
    ]
    # Precompute for speed
    d_index = df.copy()
    d_index["YearNum"] = d_index["Year"].apply(year_int)
    d_index["_kind_label"] = d_index["kind_norm"].apply(kind_display)
    d_index["_subtype_labels"] = d_index.get("Subtype", "").apply(lambda x: parse_subtypes(clean_str(x)))
    d_index["Venue"] = d_index["Venue"].astype("string").str.strip()

    for v in venues:
        slug = venue_slug_map[v]
        sub = d_index[d_index["Venue"] == v].copy()
        n = int(len(sub))

        # year range (ignore unknowns)
        yrs = [int(y) for y in sub["YearNum"].dropna().tolist()]
        yr_span = ""
        if yrs:
            y0, y1 = min(yrs), max(yrs)
            yr_span = f" [{y0}–{y1}]" if y0 != y1 else f" [{y0}]"

        kind_badges = sorted({clean_str(x) for x in sub["_kind_label"].tolist() if clean_str(x)})
        subtype_badges = sorted({lbl for labels in sub["_subtype_labels"].tolist() for lbl in (labels or []) if clean_str(lbl)})

        badges_html = ""
        if kind_badges or subtype_badges:
            parts: List[str] = []
            parts += [badge_html(lbl, "subtype") for lbl in subtype_badges]
            parts += [badge_html(lbl, "kind") for lbl in kind_badges]
            badges_html = f' <span class="venue-index__badges">{" ".join(parts)}</span>'

        lines.append(
            f'- <span class="venue-index__item"><a href="{link(f"publications/venues/{slug}/index.html")}">{v}</a> '
            f'<span class="venue-index__meta">({n}){yr_span}</span>{badges_html}</span>'
        )
    lines.append("")
    write_md_overwrite(base / "index.md", {"title": "Venues", "language": "English"}, "\n".join(lines))

    d = df.copy()
    d["YearNum"] = d["Year"].apply(year_int)
    d["MonthKey"] = d["Month"].apply(month_key)
    d["Venue"] = d["Venue"].astype("string").str.strip()
    d["Pubtype"] = d["Pubtype"].astype("string").str.strip()

    start_marker = "<!-- AUTO:VENUE_ENTRIES:START -->"
    end_marker = "<!-- AUTO:VENUE_ENTRIES:END -->"

    for v in venues:
        slug = venue_slug_map[v]
        sub = d[d["Venue"] == v].copy()
        sub = sub.sort_values(["YearNum", "MonthKey", "Title"], kind="mergesort")

        # Venue type once at top (if mixed types, show "Mixed")
        pubtypes = [
            clean_str(x)
            for x in sub["Pubtype"].dropna().astype(str).tolist()
            if clean_str(x)
        ]
        unique_pubtypes = sorted(set(pubtypes))
        if len(unique_pubtypes) == 1:
            venue_type = unique_pubtypes[0]
        elif len(unique_pubtypes) == 0:
            venue_type = ""
        else:
            venue_type = "Mixed"

        h1 = f"# {venue_display(v)} ({venue_type})" if venue_type else f"# {venue_display(v)}"

        heading_text = "\n".join(
            [
                h1,
                "",
                f"- [Back to venues]({link('publications/venues/index.html')})",
                "",
            ]
        )

        # Rendering mode: compact for Book; grouped-by-year for others
        compact = clean_str(venue_type).lower() == "book"

        def _entry_li(r: pd.Series, y_display: str, show_when: bool) -> str:
            title = r["Title"]
            wid = r["work_id"]
            k_norm = clean_str(r.get("kind_norm", ""))
            L = clean_str(r.get("language_full", ""))
            k = clean_str(r.get("kind_norm", ""))

            k_label = kind_display(k_norm)  # Fiction / Non-fiction / etc.

            m = clean_str(r.get("Month", ""))
            when_parts = [p for p in [m, (y_display if y_display != "(year unknown)" else "")] if p]
            when_txt = " ".join(when_parts).strip()
            when_html = f'<span class="venue-item__when"> ({when_txt})</span>' if (show_when and when_txt) else ""

            # Internal work link
            url = link(f"{k}/{L}/{wid}.html")

            # Optional external/online link. Column name in your sheet: 'Link'
            external = clean_str(r.get("Link", "")) or clean_str(r.get("ExternalURL", "")) or clean_str(r.get("OnlineURL", ""))
            is_online_pub = "online" in clean_str(r.get("Pubtype", "")).lower()
            online_html = f' <a class="venue-item__online" href="{external}">Online</a>' if (external and is_online_pub) else ""

            # Subtype badges (comma-separated supported)
            subtype_raw = clean_str(r.get("Subtype", ""))
            subtype_labels = parse_subtypes(subtype_raw)
            subtype_badges = " ".join(badge_html(lbl, "subtype") for lbl in subtype_labels)

            # Kind badge at end
            kind_badge = badge_html(k_label, "kind") if k_label else ""

            translation_val = clean_str(r.get("Translation", ""))
            translation_badge = badge_html("Translation", "meta") if translation_val else ""

            badges = " ".join([b for b in [subtype_badges, kind_badge, translation_badge] if b]).strip()
            badges_html = f' <span class="venue-item__badges">{badges}</span>' if badges else ""

            item_classes = ["venue-item"]
            if k_label:
                item_classes.append(f"venue-item--{slug_class(k_label)}")

            return (
                f'<li class="{" ".join(item_classes)}">'
                f'<a class="venue-item__title" href="{url}">{title}</a>'
                f'{when_html}{online_html}{badges_html}'
                f"</li>"
            )

        block_lines: List[str] = []

        if compact:
            block_lines.append(f'<ul class="venue-list venue-list--book">')
            for _, r in sub.iterrows():
                block_lines.append(_entry_li(r, y_display="", show_when=False))
            block_lines.append("</ul>")
            block_lines.append("")
        else:
            for y_val, g1 in sub.groupby(sub["YearNum"], sort=True):
                y_display = str(int(y_val)) if pd.notna(y_val) else "(year unknown)"
                block_lines += [f"## {y_display}", ""]
                block_lines.append(f'<ul class="venue-list venue-list--{slug_class(venue_type or "venue")}">')
                for _, r in g1.iterrows():
                    block_lines.append(_entry_li(r, y_display=y_display, show_when=True))
                block_lines.append("</ul>")
                block_lines.append("")

        write_md_update_block_only(
            base / slug / "index.md",
            {"title": v, "language": "English"},
            start_marker,
            end_marker,
            "\n".join(block_lines).rstrip(),
            heading=heading_text,
        )


def generate_badge_summary(df: pd.DataFrame) -> None:
    """Generate a lightweight tag/badge summary page (handy for you; safe to expose publicly too)."""
    d = df.copy()
    d["_kind_label"] = d["kind_norm"].apply(kind_display)
    d["_subtype_labels"] = d.get("Subtype", "").apply(lambda x: parse_subtypes(clean_str(x)))

    total_rows = int(len(d))
    total_works = int(d["work_id"].nunique())

    # Kind counts (by appearances/rows)
    kind_counts: Dict[str, int] = {}
    for k in d["_kind_label"].tolist():
        k = clean_str(k)
        if not k:
            continue
        kind_counts[k] = kind_counts.get(k, 0) + 1

    # Subtype counts (by appearances/rows; multi-subtype rows contribute to each)
    subtype_counts: Dict[str, int] = {}
    for labels in d["_subtype_labels"].tolist():
        for lbl in (labels or []):
            lbl = clean_str(lbl)
            if not lbl:
                continue
            subtype_counts[lbl] = subtype_counts.get(lbl, 0) + 1

    base = Path("publications") / "tags"
    base.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines += [
        "# Badges / tags summary",
        "",
        f"Pieces (rows): **{total_rows}** · Unique works: **{total_works}**",
        "",
        "## Kind",
        "",
    ]
    for lbl in sorted(kind_counts.keys()):
        lines.append(f'- {badge_html(lbl, "kind")} <span class="tag-item__count">({kind_counts[lbl]})</span>')
    lines += ["", "## Subtype", ""]
    for lbl in sorted(subtype_counts.keys()):
        lines.append(f'- {badge_html(lbl, "subtype")} <span class="tag-item__count">({subtype_counts[lbl]})</span>')
    lines.append("")

    write_md_overwrite(base / "index.md", {"title": "Badges summary", "language": "English"}, "\n".join(lines))



def main() -> None:
    require_site_root()
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=str, help="Path to appearance-centric CSV (revised).")
    args = ap.parse_args()

    df = pd.read_csv(Path(args.csv))
    required = {"work_id", "Title", "Pubtype", "Venue", "Kind", "Subtype", "Language", "Year", "Month"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"CSV missing required columns: {sorted(missing)}")

    df = df.copy()
    df["language_full"] = df["Language"].apply(norm_lang_full)
    df["kind_norm"] = df["Kind"].apply(norm_kind)

    venues = sorted({clean_str(v) for v in df["Venue"].tolist() if clean_str(v)})
    venue_slug_map: Dict[str, str] = {v: slugify(v) for v in venues}

    for d in ["fiction", "nonfiction", "poem", "publications"]:
        Path(d).mkdir(exist_ok=True)

    generate_root_index()
    generate_work_pages(df, venue_slug_map)

    for k in sorted(df["kind_norm"].dropna().unique().tolist()):
        if k in ("fiction", "nonfiction", "poem"):
            generate_kind_indexes(df, k)

    generate_publications_index(df, venue_slug_map)
    generate_publications_year_indexes(df)
    generate_badge_summary(df)
    generate_venue_pages(df, venue_slug_map)

    print("Done (v6). Next: run ./build.sh")


if __name__ == "__main__":
    main()
