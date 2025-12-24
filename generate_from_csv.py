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


def write_work_md(path: Path, front_matter: Dict, body_if_new: str, pubhistory_md: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        _, body = split_front_matter(existing)
        body = replace_pubhistory_block(body, pubhistory_md)
        path.write_text(dump_front_matter(front_matter) + "\n" + body, encoding="utf-8")
    else:
        body = replace_pubhistory_block(body_if_new, pubhistory_md)
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
        venue_md = f"[{venue}]({vlink})" if venue else "(venue unknown)"

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
    write_md_overwrite(Path("index.md"), {"title": "Writings", "language": "English"}, root_index_body())


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
        write_work_md(work_output_path(kind, lang_full, work_id), fm, work_stub_body(title), pub_md)


def generate_kind_indexes(df: pd.DataFrame, kind: str) -> None:
    items = df[df["kind_norm"] == kind].drop_duplicates("work_id").copy()

    hint_map: Dict[str, str] = {}
    for wid, g in df[df["kind_norm"] == kind].groupby("work_id", sort=False):
        hint_map[wid] = earliest_pub_hint(g)

    items = items.sort_values(["language_full", "Title"], kind="mergesort")
    langs = sorted(items["language_full"].unique().tolist())

    lines: List[str] = [f"# {kind.title()}", ""]
    lines.append("Browse by language:")
    lines.append("")
    for L in langs:
        lines.append(f"- [{L}]({link(f'{kind}/{L}/index.html')})")
    lines.append("")
    lines.append("## All")
    lines.append("")
    for _, r in items.iterrows():
        wid = r["work_id"]
        L = r["language_full"]
        title = r["Title"]
        hint = hint_map.get(wid, "")
        lines.append(f"- [{title}]({link(f'{kind}/{L}/{wid}.html')}) {hint}")
    lines.append("")
    write_md_overwrite(Path(kind) / "index.md", {"title": kind.title(), "language": "English"}, "\n".join(lines))

    for L in langs:
        sub = items[items["language_full"] == L].copy().sort_values(["Title"], kind="mergesort")
        body_lines = [f"# {kind.title()} ({L})", ""]
        for _, r in sub.iterrows():
            wid = r["work_id"]
            title = r["Title"]
            hint = hint_map.get(wid, "")
            body_lines.append(f"- [{title}]({link(f'{kind}/{L}/{wid}.html')}) {hint}")
        body_lines.append("")
        write_md_overwrite(Path(kind) / L / "index.md", {"title": f"{kind.title()} {L}", "language": L}, "\n".join(body_lines))


def generate_publications_index(df: pd.DataFrame, venue_slug_map: Dict[str, str]) -> None:
    d = df.copy()
    d["Pubtype"] = d["Pubtype"].astype("string").str.strip()
    d["Venue"] = d["Venue"].astype("string").str.strip()
    d["YearNum"] = d["Year"].apply(year_int)
    d["MonthKey"] = d["Month"].apply(month_key)

    lines: List[str] = ["# Publications", "", "Grouped by publication type and venue.", ""]
    lines.append(f"- [Browse by year]({link('publications/years/index.html')})")
    lines.append(f"- [Browse by venue]({link('publications/venues/index.html')})")
    lines.append("")

    for pubtype, g1 in d.groupby("Pubtype", sort=True):
        lines += [f"## {pubtype}", ""]
        for venue, g2 in g1.groupby("Venue", sort=True):
            vslug = venue_slug_map.get(venue, slugify(venue))
            vlink = link(f"publications/venues/{vslug}/index.html")
            lines += [f"### [{venue}]({vlink})", ""]
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

                lines.append(f"- [{title}]({link(f'{k}/{L}/{wid}.html')}){when}")
            lines.append("")
    write_md_overwrite(Path("publications") / "index.md", {"title": "Publications", "language": "English"}, "\n".join(lines))


def generate_publications_year_indexes(df: pd.DataFrame) -> None:
    d = df.copy()
    d["YearNum"] = d["Year"].apply(year_int)
    d = d[d["YearNum"].notna()].copy()
    d["YearNum"] = d["YearNum"].astype(int)
    d["MonthKey"] = d["Month"].apply(month_key)

    years = sorted(d["YearNum"].unique().tolist())
    base = Path("publications") / "years"
    base.mkdir(parents=True, exist_ok=True)

    lines = ["# Publications by year", ""]
    for y in years:
        lines.append(f"- [{y}]({link(f'publications/years/{y}/index.html')})")
    lines.append("")
    write_md_overwrite(base / "index.md", {"title": "Publications by year", "language": "English"}, "\n".join(lines))

    for y in years:
        sub = d[d["YearNum"] == y].copy()
        sub["Venue"] = sub["Venue"].astype("string").str.strip()
        sub = sub.sort_values(["Pubtype", "Venue", "MonthKey", "Title"], kind="mergesort")
        ydir = base / str(y)
        ydir.mkdir(parents=True, exist_ok=True)

        body: List[str] = [f"# Publications in {y}", "", f"- [Back to years]({link('publications/years/index.html')})", ""]
        for pubtype, g1 in sub.groupby("Pubtype", sort=True):
            body += [f"## {pubtype}", ""]
            for venue, g2 in g1.groupby("Venue", sort=True):
                body += [f"### {venue}", ""]
                for _, r in g2.iterrows():
                    title = r["Title"]
                    wid = r["work_id"]
                    k = r["kind_norm"]
                    L = r["language_full"]
                    m = clean_str(r.get("Month", ""))
                    m = f"{m} " if m else ""
                    body.append(f"- [{title}]({link(f'{k}/{L}/{wid}.html')}) ({m}{y})")
                body.append("")
        write_md_overwrite(ydir / "index.md", {"title": f"Publications {y}", "language": "English"}, "\n".join(body))


def generate_venue_pages(df: pd.DataFrame, venue_slug_map: Dict[str, str]) -> None:
    base = Path("publications") / "venues"
    base.mkdir(parents=True, exist_ok=True)

    venues = sorted({clean_str(v) for v in df["Venue"].tolist() if clean_str(v)})
    lines = ["# Venues", "", "Where the pieces appeared (magazines, newsletters, books, anthologies, etc.).", ""]
    for v in venues:
        slug = venue_slug_map[v]
        lines.append(f"- [{v}]({link(f'publications/venues/{slug}/index.html')})")
    lines.append("")
    write_md_overwrite(base / "index.md", {"title": "Venues", "language": "English"}, "\n".join(lines))

    d = df.copy()
    d["YearNum"] = d["Year"].apply(year_int)
    d["MonthKey"] = d["Month"].apply(month_key)
    d["Venue"] = d["Venue"].astype("string").str.strip()

    for v in venues:
        slug = venue_slug_map[v]
        sub = d[d["Venue"] == v].copy()
        sub = sub.sort_values(["YearNum", "MonthKey", "Title"], kind="mergesort")

        body: List[str] = [f"# {v}", "", f"- [Back to venues]({link('publications/venues/index.html')})", ""]
        for y_val, g1 in sub.groupby(sub["YearNum"], sort=True):
            # y_val can be NaN; avoid int(y_val) entirely.
            y_display = str(int(y_val)) if pd.notna(y_val) else "(year unknown)"
            body += [f"## {y_display}", ""]
            for _, r in g1.iterrows():
                title = r["Title"]
                wid = r["work_id"]
                k = r["kind_norm"]
                L = r["language_full"]
                pubtype = clean_str(r.get("Pubtype", ""))
                m = clean_str(r.get("Month", ""))
                when_parts = [p for p in [m, (y_display if y_display != "(year unknown)" else "")] if p]
                when = " ".join(when_parts).strip()
                when = f" ({when})" if when else ""
                pubtype_md = f"{pubtype}: " if pubtype else ""
                body.append(f"- {pubtype_md}[{title}]({link(f'{k}/{L}/{wid}.html')}){when}")
            body.append("")
        write_md_overwrite(base / slug / "index.md", {"title": v, "language": "English"}, "\n".join(body))


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
    generate_venue_pages(df, venue_slug_map)

    print("Done (v6). Next: run ./build.sh")


if __name__ == "__main__":
    main()
