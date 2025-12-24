#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate/update Markdown stubs and index pages from an appearance-centric CSV.

Model:
- One row in CSV = one appearance/publication instance.
- Same work_id across rows = same work.

Safe behavior:
- Work .md pages: update ONLY YAML front matter; preserve body exactly.
- Index pages (root/index.md, fiction/index.md, fiction/<lang>/index.md, nonfiction/...,
  publications/index.md): regenerated each run.

Expected CSV columns (from your revised file):
work_id, Title, Pubtype, Venue, Kind, Subtype, Translation, Language, Year, Month
(Extra columns are ignored.)

Usage (run from your site repo root; the folder that contains build.sh):
    python3 generate_from_csv.py IndexOfPublished_revised.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import pandas as pd
import yaml
import re


# ----------------------------- Normalization -----------------------------

LANG_MAP = {"Marathi": "mr", "Hindi": "hi", "English": "en", "mr": "mr", "hi": "hi", "en": "en"}
KIND_MAP = {"कथा": "fiction", "लेख": "nonfiction", "poem": "poem", "fiction": "fiction", "nonfiction": "nonfiction"}


def norm_lang(x: object) -> str:
    s = str(x).strip()
    return LANG_MAP.get(s, s.lower()[:2] if s else "und")


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


# ----------------------------- Markdown IO -----------------------------

FM_BOUNDARY = re.compile(r"^---\s*$", flags=re.M)


def split_front_matter(text: str) -> Tuple[Optional[str], str]:
    matches = list(FM_BOUNDARY.finditer(text))
    if len(matches) >= 2 and matches[0].start() == 0:
        fm = text[matches[0].end() : matches[1].start()].strip("\n")
        body = text[matches[1].end() :].lstrip("\n")
        return fm, body
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
        new_text = dump_front_matter(front_matter) + "\n" + body
        path.write_text(new_text, encoding="utf-8")
    else:
        new_text = dump_front_matter(front_matter) + "\n" + body_if_new.strip() + "\n"
        path.write_text(new_text, encoding="utf-8")


def write_md_overwrite(path: Path, front_matter: Dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dump_front_matter(front_matter) + "\n" + body.strip() + "\n"
    path.write_text(text, encoding="utf-8")


# ----------------------------- Paths -----------------------------

def work_output_path(kind: str, lang: str, work_id: str) -> Path:
    return Path(kind) / lang / f"{work_id}.md"


# ----------------------------- Page bodies -----------------------------

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


# ----------------------------- Generators -----------------------------

def require_site_root() -> None:
    if not Path("build.sh").exists():
        raise SystemExit("Please run from the site repo root (where build.sh is).")


def generate_work_pages(df: pd.DataFrame) -> None:
    for work_id, g in df.groupby("work_id", sort=True):
        title = clean_str(g["Title"].iloc[0])
        lang = norm_lang(g["Language"].iloc[0])
        kind = norm_kind(g["Kind"].iloc[0])
        subtype = clean_str(g["Subtype"].iloc[0]) if "Subtype" in g.columns else ""
        translation = clean_str(g["Translation"].iloc[0]) if "Translation" in g.columns else ""

        fm: Dict[str, object] = {
            "id": work_id,
            "title": title,
            "language": lang,
            "kind": kind,
        }
        if subtype:
            fm["subtype"] = subtype
        if translation:
            fm["translation"] = translation

        out_path = work_output_path(kind, lang, work_id)
        write_md_preserve_body(out_path, fm, work_stub_body(title))


def generate_kind_indexes(df: pd.DataFrame, kind: str) -> None:
    items = df[df["kind_norm"] == kind].drop_duplicates("work_id").copy()
    items = items.sort_values(["language_norm", "Title"], kind="mergesort")

    lines: List[str] = [f"# {kind.title()}", ""]
    lines.append("Browse by language:")
    langs = sorted(items["language_norm"].unique().tolist())
    lines.append("")
    for L in langs:
        lines.append(f"- [{L.upper()}](/%s/%s/index.html)" % (kind, L))
    lines.append("")
    lines.append("## All")
    lines.append("")

    for _, r in items.iterrows():
        wid = r["work_id"]
        lang = r["language_norm"]
        title = r["Title"]
        lines.append(f"- [{title}](/%s/%s/{wid}.html)" % (kind, lang))
    lines.append("")

    write_md_overwrite(Path(kind) / "index.md", {"title": kind.title(), "language": "en"}, "\n".join(lines))

    for L in langs:
        sub = items[items["language_norm"] == L].copy()
        sub = sub.sort_values(["Title"], kind="mergesort")
        body_lines = [f"# {kind.title()} ({L.upper()})", ""]
        for _, r in sub.iterrows():
            wid = r["work_id"]
            title = r["Title"]
            body_lines.append(f"- [{title}](/%s/%s/{wid}.html)" % (kind, L))
        body_lines.append("")
        write_md_overwrite(Path(kind) / L / "index.md", {"title": f"{kind.title()} {L.upper()}", "language": L}, "\n".join(body_lines))


def generate_publications_index(df: pd.DataFrame) -> None:
    d = df.copy()
    d["Pubtype"] = d["Pubtype"].astype("string").str.strip()
    d["Venue"] = d["Venue"].astype("string").str.strip()
    d["Year"] = pd.to_numeric(d["Year"], errors="coerce")

    lines: List[str] = ["# Publications", "", "Grouped by publication type and venue.", ""]

    for pubtype, g1 in d.groupby("Pubtype", sort=True):
        lines += [f"## {pubtype}", ""]
        for venue, g2 in g1.groupby("Venue", sort=True):
            lines += [f"### {venue}", ""]
            g2 = g2.sort_values(["Year", "Month", "Title"], kind="mergesort")
            for _, r in g2.iterrows():
                title = r["Title"]
                wid = r["work_id"]
                lang = r["language_norm"]
                kind = r["kind_norm"]

                when_parts: List[str] = []
                m = clean_str(r["Month"])
                if m:
                    when_parts.append(m)
                if pd.notna(r["Year"]):
                    when_parts.append(str(int(r["Year"])))
                when = " ".join(when_parts).strip()
                when = f" ({when})" if when else ""

                lines.append(f"- [{title}](/%s/%s/{wid}.html){when}" % (kind, lang))
            lines.append("")

    write_md_overwrite(Path("publications") / "index.md", {"title": "Publications", "language": "en"}, "\n".join(lines))


def generate_root_index() -> None:
    write_md_overwrite(Path("index.md"), {"title": "Writings", "language": "en"}, root_index_body())


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
    df["language_norm"] = df["Language"].apply(norm_lang)
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

    print("Done.")
    print("Generated/updated: index.md, work pages, and index pages under fiction/, nonfiction/, publications/.")
    print("Next: run ./build.sh to render HTML into site/.")


if __name__ == "__main__":
    main()
