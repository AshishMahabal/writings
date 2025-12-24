#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate/update Markdown stubs and index pages from an appearance-centric CSV.

Changes in v3:
1) Language folders use full names: English/Hindi/Marathi (matching CSV values).
2) Adds year index pages:
   - publications/years/index.md
   - publications/years/<YYYY>/index.md (one per year with any appearances)
3) In fiction/nonfiction listings, shows a compact publication hint in brackets:
   [Venue, Year] using the earliest known appearance for that work.

Model:
- One CSV row = one appearance.
- Same work_id across rows = same work.

Safe behavior:
- Work pages: update ONLY YAML front matter, preserve body.
- Index pages are regenerated each run.

Required CSV columns:
work_id, Title, Pubtype, Venue, Kind, Subtype, Language, Year, Month
Optional: Translation
All other columns are ignored.

Usage (run from repo root where build.sh lives):
    python3 generate_from_csv.py IndexOfPublished_revised.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import pandas as pd
import yaml
import re


LANG_CANON = {"Marathi": "Marathi", "Hindi": "Hindi", "English": "English"}
KIND_MAP = {"कथा": "fiction", "लेख": "nonfiction", "poem": "poem", "fiction": "fiction", "nonfiction": "nonfiction"}


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


def year_int(x: object) -> Optional[int]:
    try:
        return int(float(x))
    except Exception:
        return None


FM_BOUNDARY = re.compile(r"^---\s*$", flags=re.M)


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


def write_md_preserve_body(path: Path, front_matter: Dict, body_if_new: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        _, body = split_front_matter(existing)
        path.write_text(dump_front_matter(front_matter) + "\n" + body, encoding="utf-8")
    else:
        path.write_text(dump_front_matter(front_matter) + "\n" + body_if_new.strip() + "\n", encoding="utf-8")


def write_md_overwrite(path: Path, front_matter: Dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_front_matter(front_matter) + "\n" + body.strip() + "\n", encoding="utf-8")


def work_output_path(kind: str, lang_full: str, work_id: str) -> Path:
    return Path(kind) / lang_full / f"{work_id}.md"


def work_stub_body(title: str) -> str:
    return f"""# {title}

*(Text to be added here.)*

## Publication history

This page is the canonical work page. Publication instances are listed via the CSV-driven Publications index.
"""


def root_index_body() -> str:
    return """# Writings

Science fiction (primarily Marathi) and non-fiction (astronomy, rationalism, essays).

- [Fiction](/fiction/index.html)
- [Non-Fiction](/nonfiction/index.html)
- [Publications](/publications/index.html)
"""


def require_site_root() -> None:
    if not Path("build.sh").exists():
        raise SystemExit("Please run from the site repo root (where build.sh is).")


def earliest_pub_hint(g: pd.DataFrame) -> str:
    gg = g.copy()
    gg["YearNum"] = gg["Year"].apply(year_int)
    gg = gg.sort_values(["YearNum", "Month", "Venue"], kind="mergesort")
    venue = clean_str(gg["Venue"].iloc[0]) if len(gg) else ""
    y = gg["YearNum"].iloc[0] if len(gg) else None
    if venue and pd.notna(y):
        return f"[{venue}, {int(y)}]"
    if venue:
        return f"[{venue}]"
    if pd.notna(y):
        return f"[{int(y)}]"
    return ""


def generate_root_index() -> None:
    write_md_overwrite(Path("index.md"), {"title": "Writings", "language": "English"}, root_index_body())


def generate_work_pages(df: pd.DataFrame) -> None:
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

        write_md_preserve_body(work_output_path(kind, lang_full, work_id), fm, work_stub_body(title))


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
        lines.append(f"- [{L}](/%s/%s/index.html)" % (kind, L))
    lines.append("")
    lines.append("## All")
    lines.append("")
    for _, r in items.iterrows():
        wid = r["work_id"]
        L = r["language_full"]
        title = r["Title"]
        hint = hint_map.get(wid, "")
        lines.append(f"- [{title}](/%s/%s/{wid}.html) {hint}" % (kind, L))
    lines.append("")
    write_md_overwrite(Path(kind) / "index.md", {"title": kind.title(), "language": "English"}, "\n".join(lines))

    for L in langs:
        sub = items[items["language_full"] == L].copy().sort_values(["Title"], kind="mergesort")
        body_lines = [f"# {kind.title()} ({L})", ""]
        for _, r in sub.iterrows():
            wid = r["work_id"]
            title = r["Title"]
            hint = hint_map.get(wid, "")
            body_lines.append(f"- [{title}](/%s/%s/{wid}.html) {hint}" % (kind, L))
        body_lines.append("")
        write_md_overwrite(Path(kind) / L / "index.md", {"title": f"{kind.title()} {L}", "language": L}, "\n".join(body_lines))


def generate_publications_index(df: pd.DataFrame) -> None:
    d = df.copy()
    d["Pubtype"] = d["Pubtype"].astype("string").str.strip()
    d["Venue"] = d["Venue"].astype("string").str.strip()
    d["YearNum"] = d["Year"].apply(year_int)

    lines: List[str] = ["# Publications", "", "Grouped by publication type and venue.", ""]
    lines.append("- [Browse by year](/publications/years/index.html)")
    lines.append("")

    for pubtype, g1 in d.groupby("Pubtype", sort=True):
        lines += [f"## {pubtype}", ""]
        for venue, g2 in g1.groupby("Venue", sort=True):
            lines += [f"### {venue}", ""]
            g2 = g2.sort_values(["YearNum", "Month", "Title"], kind="mergesort")
            for _, r in g2.iterrows():
                title = r["Title"]
                wid = r["work_id"]
                kind = r["kind_norm"]
                L = r["language_full"]
                when_parts: List[str] = []
                m = clean_str(r["Month"])
                if m:
                    when_parts.append(m)
                y = r["YearNum"]
                if pd.notna(y):
                    when_parts.append(str(int(y)))
                when = " ".join(when_parts).strip()
                when = f" ({when})" if when else ""
                lines.append(f"- [{title}](/%s/%s/{wid}.html){when}" % (kind, L))
            lines.append("")
    write_md_overwrite(Path("publications") / "index.md", {"title": "Publications", "language": "English"}, "\n".join(lines))


def generate_publications_year_indexes(df: pd.DataFrame) -> None:
    d = df.copy()
    d["YearNum"] = d["Year"].apply(year_int)
    d = d[pd.notna(d["YearNum"])].copy()
    d["YearNum"] = d["YearNum"].astype(int)

    years = sorted(d["YearNum"].unique().tolist())
    base = Path("publications") / "years"
    base.mkdir(parents=True, exist_ok=True)

    lines = ["# Publications by year", ""]
    for y in years:
        lines.append(f"- [{y}](/publications/years/{y}/index.html)")
    lines.append("")
    write_md_overwrite(base / "index.md", {"title": "Publications by year", "language": "English"}, "\n".join(lines))

    for y in years:
        sub = d[d["YearNum"] == y].copy()
        sub["Venue"] = sub["Venue"].astype("string").str.strip()
        sub = sub.sort_values(["Pubtype", "Venue", "Month", "Title"], kind="mergesort")
        ydir = base / str(y)
        ydir.mkdir(parents=True, exist_ok=True)

        body: List[str] = [f"# Publications in {y}", "", "- [Back to years](/publications/years/index.html)", ""]
        for pubtype, g1 in sub.groupby("Pubtype", sort=True):
            body += [f"## {pubtype}", ""]
            for venue, g2 in g1.groupby("Venue", sort=True):
                body += [f"### {venue}", ""]
                for _, r in g2.iterrows():
                    title = r["Title"]
                    wid = r["work_id"]
                    kind = r["kind_norm"]
                    L = r["language_full"]
                    m = clean_str(r["Month"])
                    m = f"{m} " if m else ""
                    body.append(f"- [{title}](/%s/%s/{wid}.html) ({m}{y})" % (kind, L))
                body.append("")
        write_md_overwrite(ydir / "index.md", {"title": f"Publications {y}", "language": "English"}, "\n".join(body))


def main() -> None:
    require_site_root()
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=str, help="Path to appearance-centric CSV (revised)." )
    args = ap.parse_args()

    df = pd.read_csv(Path(args.csv))
    required = {"work_id", "Title", "Pubtype", "Venue", "Kind", "Subtype", "Language", "Year", "Month"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"CSV missing required columns: {sorted(missing)}")

    df = df.copy()
    df["language_full"] = df["Language"].apply(norm_lang_full)
    df["kind_norm"] = df["Kind"].apply(norm_kind)

    Path("fiction").mkdir(exist_ok=True)
    Path("nonfiction").mkdir(exist_ok=True)
    Path("poem").mkdir(exist_ok=True)
    Path("publications").mkdir(exist_ok=True)

    generate_root_index()
    generate_work_pages(df)

    for k in sorted(df["kind_norm"].dropna().unique().tolist()):
        if k in ("fiction", "nonfiction", "poem"):
            generate_kind_indexes(df, k)

    generate_publications_index(df)
    generate_publications_year_indexes(df)

    print("Done (v3). Next: run ./build.sh")


if __name__ == "__main__":
    main()
