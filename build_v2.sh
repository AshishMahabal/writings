#!/usr/bin/env bash
set -euo pipefail

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
  pandoc "$md"     --standalone     --template="$TEMPLATE"     -M title="$title" -M lang="$lang" -M year="$(date +%Y)"     -o "$out"
}

# Render root index.md if present
if [ -f "$ROOT/index.md" ]; then
  render_one "$ROOT/index.md" "$SITE/index.html" "Writings" "en"
fi

# Render all markdown files under these sections, preserving structure.
for md in $(find "$ROOT/fiction" "$ROOT/nonfiction" "$ROOT/publications" -name "*.md" -type f 2>/dev/null); do
  rel="${md#$ROOT/}"              # e.g. fiction/mr/XYZ.md
  out="$SITE/${rel%.md}.html"     # e.g. site/fiction/mr/XYZ.html

  # Infer lang from path segment (mr/hi/en), default en
  lang="en"
  if echo "$rel" | grep -q "/mr/"; then lang="mr"; fi
  if echo "$rel" | grep -q "/hi/"; then lang="hi"; fi
  if echo "$rel" | grep -q "/en/"; then lang="en"; fi

  title="$(basename "${rel%.md}")"
  render_one "$md" "$out" "$title" "$lang"
done

echo "Built HTML into: $SITE"
