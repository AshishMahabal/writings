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
TEMPLATE="$ASSETS_SRC/template.html"
if [ ! -f "$TEMPLATE" ]; then
  echo "Missing assets/template.html"
  exit 1
fi

rm -rf "$SITE"
mkdir -p "$SITE"
cp -R "$ASSETS_SRC" "$SITE"

render_one() {
  local md="$1"
  local out="$2"
  local title="$3"
  local lang="$4"
  local page_section="$5"   # home | fiction | nonfiction | publications | "" (none)
  local book_key="$6"       # ghost_writer | isot | "" (none)

  mkdir -p "$(dirname "$out")"

  local active_home=""
  local active_fiction=""
  local active_nonfiction=""
  local active_publications=""
  local active_ghost_writer=""
  local active_isot=""

  case "$page_section" in
    home) active_home="1" ;;
    fiction) active_fiction="1" ;;
    nonfiction) active_nonfiction="1" ;;
    publications) active_publications="1" ;;
  esac

  case "$book_key" in
    ghost_writer) active_ghost_writer="1" ;;
    isot) active_isot="1" ;;
  esac

  pandoc "$md" \
    --standalone \
    --template="$TEMPLATE" \
    -M title="$title" \
    -M lang="$lang" \
    -M baseurl="$BASEURL_META" \
    -M year="$(date +%Y)" \
    -M active_home="$active_home" \
    -M active_fiction="$active_fiction" \
    -M active_nonfiction="$active_nonfiction" \
    -M active_publications="$active_publications" \
    -M active_ghost_writer="$active_ghost_writer" \
    -M active_isot="$active_isot" \
    -o "$out"
}

# Build site root index.md -> site/index.html (Home)
if [ -f "$ROOT/index.md" ]; then
  render_one "$ROOT/index.md" "$SITE/index.html" "Writings" "en" "home" ""
fi

# Build all content pages
while IFS= read -r -d '' md; do
  rel="${md#$ROOT/}"
  out="$SITE/${rel%.md}.html"
  title="$(basename "${rel%.md}")"

  # Infer language from path segment (full names). Default to English.
  lang="en"
  if echo "$rel" | grep -q "/Marathi/"; then lang="mr"; fi
  if echo "$rel" | grep -q "/Hindi/"; then lang="hi"; fi
  if echo "$rel" | grep -q "/English/"; then lang="en"; fi

  # Infer section (and book key) from path
  page_section="home"
  book_key=""

  case "$rel" in
    fiction/*)
      page_section="fiction"
      ;;
    nonfiction/*)
      page_section="nonfiction"
      ;;
    publications/venues/venue-54714bad4d/*)
      page_section=""          # don't highlight Home or Publications; highlight book link instead
      book_key="ghost_writer"
      ;;
    publications/venues/inner-space-and-outer-thoughts/*)
      page_section=""          # same idea
      book_key="isot"
      ;;
    publications/venues/*)
      page_section=""          # other venue pages: no section highlight for now
      ;;
    publications/*)
      page_section="publications"
      ;;
  esac

  render_one "$md" "$out" "$title" "$lang" "$page_section" "$book_key"
done < <(find "$ROOT/fiction" "$ROOT/nonfiction" "$ROOT/publications" -name "*.md" -type f -print0 2>/dev/null)

echo "Built HTML into: $SITE"

