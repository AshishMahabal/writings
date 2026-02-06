## Local preview and GitHub Pages testing

### Normal local:

`./serve_local.sh local`

### Mimic for GitHub:

`./serve_local.sh gh`

### Use different port:

`./serve_local.sh gh 8081`

### Use different CSV:

`./serve_local.sh gh 8000 MyIndex.csv`

## Prerequisites

- Python 3.9+
- Pandoc (for Markdown → HTML)
- Python packages: `pandas`, `pyyaml`

Example install:

`python3 -m pip install pandas pyyaml`

## Build (manual)

Generate Markdown from the CSV, then render HTML:

`python3 generate_from_csv.py IndexOfPublished_revised.csv`

`./build.sh`

## Environment variables

- `BASEURL` — used for GitHub Pages project site paths. Example: `/writings`.
- `SITE_URL` — absolute site root for feed links (e.g., `https://ashishmahabal.github.io`).
- `SITE_TITLE`, `SITE_SUBTITLE` — Atom feed metadata.

Examples:

`BASEURL="/writings" python3 generate_from_csv.py IndexOfPublished_revised.csv`

`SITE_URL="https://ashishmahabal.github.io" ./build.sh`

## CSV schema

Required columns:

`work_id, Title, Pubtype, Venue, Kind, Subtype, Language, Year, Month`

Optional columns used:

`Translation, Link, ExternalURL, OnlineURL, Audio link, Coauthors, Penname, VenueContext`

