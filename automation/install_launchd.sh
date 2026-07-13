#!/bin/sh
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$ROOT_DIR/automation/com.codex.nmpa-toothpaste-tracker.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DST="$LAUNCH_AGENTS_DIR/com.codex.nmpa-toothpaste-tracker.plist"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$ROOT_DIR/output/logs"

cp "$PLIST_SRC" "$PLIST_DST"
chmod 644 "$PLIST_DST"
chmod +x "$ROOT_DIR/automation/run_monthly_tracker.sh"

launchctl unload "$PLIST_DST" >/dev/null 2>&1 || true
launchctl load "$PLIST_DST"
launchctl list | grep 'com.codex.nmpa-toothpaste-tracker' || true

echo "$PLIST_DST"
