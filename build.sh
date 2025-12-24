#!/usr/bin/env bash
set -euo pipefail

BASEURL_META="${BASEURL:-}"
# normalize: "" or "/writings" (no trailing slash)
BASEURL_META="/${BASEURL_META#/}"
BASEURL_META="${BASEURL_META%/}"
if [ "$BASEURL_META" = "/" ]; then BASEURL_META=""; fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
SITE="$ROOT/site"
ASSETS_SRC="$ROOT/assets"

rm -rf "$SITE"
mkdir -p "$SITE/assets"

# Copy assets
if [ -f "$ASSETS_SRC/style.css" ]; then
  cp "$ASSETS_SRC/style.css" "$SITE/assets/style.css"
fi

TEMPLATE="$ASSETS_SRC/template.html"
if [ ! -f "$TEMPLATE" ]; then
  echo "Missing assets/template.html"
  exit 1
fi

render_one() {
  local md="$1"
  local out="$2"
  local title="$3"
  local lang="$4"
  mkdir -p "$(dirname "$out")"
  pandoc "$md"     --standalone     --template="$TEMPLATE"     -M title="$title" -M lang="$lang" -M baseurl="$BASEURL_META" -M year="$(date +%Y)"     -o "$out"
}

# Render root index.md
if [ -f "$ROOT/index.md" ]; then
  render_one "$ROOT/index.md" "$SITE/index.html" "Writings" "en"
fi

# Render all markdown files under sections.
while IFS= read -r -d '' md; do
  rel="${md#$ROOT/}"
  out="$SITE/${rel%.md}.html"
  title="$(basename "${rel%.md}")"

  # Infer language from path segment (full names). Default to English.
  lang="en"
  if echo "$rel" | grep -q "/Marathi/"; then lang="mr"; fi
  if echo "$rel" | grep -q "/Hindi/"; then lang="hi"; fi
  if echo "$rel" | grep -q "/English/"; then lang="en"; fi

  render_one "$md" "$out" "$title" "$lang"
done < <(find "$ROOT/fiction" "$ROOT/nonfiction" "$ROOT/publications" -name "*.md" -type f -print0 2>/dev/null)

echo "Built HTML into: $SITE"
