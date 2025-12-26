#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-gh}"          # local | gh
PORT="${2:-8001}"
CSV="${3:-IndexOfPublished_revised.csv}"

ROOT="$(cd "$(dirname "$0")" && pwd)"

die() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$ROOT/build.sh" ] || die "build.sh not found in repo root"
[ -f "$ROOT/generate_from_csv.py" ] || die "generate_from_csv.py not found in repo root"
[ -f "$ROOT/$CSV" ] || die "CSV not found: $CSV"

build_local() {
  echo "==> Building LOCAL (BASEURL unset)"
  unset BASEURL
  python3 "$ROOT/generate_from_csv.py" "$ROOT/$CSV"
  "$ROOT/build.sh"
}

build_gh() {
  echo "==> Building GH mimic (BASEURL=/writings)"
  export BASEURL="/writings"
  python3 "$ROOT/generate_from_csv.py" "$ROOT/$CSV"
  "$ROOT/build.sh"
}

serve_local_root() {
  echo
  echo "==> Serving from: $ROOT/site"
  echo "    URL: http://localhost:$PORT/"
  echo
  cd "$ROOT/site"
  python3 -m http.server "$PORT"
}

serve_gh_root() {
  echo
  echo "==> Serving from: $ROOT (repo root), with /writings -> site symlink"
  echo "    URL: http://localhost:$PORT/writings/"
  echo
  cd "$ROOT"
  rm -f "$ROOT/writings"
  ln -s "site" "$ROOT/writings"
#  python3 -m http.server "$PORT"
}

case "$MODE" in
  local)
    build_local
    serve_local_root
    ;;
  gh|github|pages)
    build_gh
    serve_gh_root
    ;;
  both)
    echo "==> Building BOTH modes"
    build_local
    build_gh
    echo
    echo "Built both. Now serving GH mimic by default."
    serve_gh_root
    ;;
  *)
    die "Unknown mode: $MODE. Use: local | gh | both"
    ;;
esac

