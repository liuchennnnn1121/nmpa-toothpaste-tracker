#!/bin/sh
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 - <<'PY'
from datetime import date
import sys

today = date.today()
if today.weekday() >= 5:
    sys.exit(0)

for day in range(1, today.day):
    candidate = date(today.year, today.month, day)
    if candidate.weekday() < 5:
        sys.exit(0)
PY

MONTH="$(python3 - <<'PY'
from datetime import date, timedelta
today = date.today()
first = today.replace(day=1)
prev = first - timedelta(days=1)
print(prev.strftime("%Y-%m"))
PY
)"

python3 toothpaste_tracker_pipeline.py run-month --month "$MONTH"
