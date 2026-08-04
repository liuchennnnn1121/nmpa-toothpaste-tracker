#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE="${PUBLISH_REMOTE:-origin}"
BRANCH="${PUBLISH_BRANCH:-main}"
PYTHON_BIN="${PYTHON:-python3}"
COMMIT_MESSAGE=""
SHOULD_PUSH=1

usage() {
  cat <<'USAGE'
Usage: scripts/publish_site.sh [--message "commit message"] [--no-push]

Rebuilds the dashboard, syncs output assets into docs/, commits publishable
changes, and pushes the current HEAD to origin/main for GitHub Pages.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message)
      COMMIT_MESSAGE="${2:-}"
      if [[ -z "$COMMIT_MESSAGE" ]]; then
        echo "Missing value for $1" >&2
        exit 2
      fi
      shift 2
      ;;
    --no-push)
      SHOULD_PUSH=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$COMMIT_MESSAGE" ]]; then
  COMMIT_MESSAGE="Update dashboard $(date '+%Y-%m-%d %H:%M')"
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "This script must run inside the git repository." >&2
  exit 1
fi

echo "Rebuilding dashboard..."
"$PYTHON_BIN" toothpaste_tracker_pipeline.py rebuild-panel

echo "Syncing GitHub Pages files..."
mkdir -p docs
cp output/brand_dashboard.html docs/index.html
cp output/brand_dashboard.html docs/brand_dashboard.html
for panel in output/*_brand_panel.html; do
  [[ -e "$panel" ]] || continue
  cp "$panel" "docs/$(basename "$panel")"
done

if [[ -d output/package_images ]]; then
  mkdir -p docs/package_images
  rsync -a --delete output/package_images/ docs/package_images/
else
  echo "No output/package_images directory found; keeping existing docs/package_images." >&2
fi

touch docs/.nojekyll

echo "Staging publishable changes..."
git add -A -- .gitignore README.md scripts/publish_site.sh docs output/*.html output/monthly output/progress

if git diff --cached --quiet; then
  echo "No publishable changes to commit."
else
  git commit -m "$COMMIT_MESSAGE"
fi

if [[ "$SHOULD_PUSH" -eq 1 ]]; then
  echo "Pushing to $REMOTE/$BRANCH..."
  git push "$REMOTE" HEAD:"$BRANCH"
else
  echo "Skipping push because --no-push was provided."
fi

echo "Published site source is in docs/."
