#!/bin/bash
# Weekly wiki backfill runner.
#
# Invoked by launchd on Sundays at 9am. Self-throttles by checking
# calendar-day diff against MIN_CALENDAR_DAYS (default 6) — this is robust
# against Mac sleep/wake jitter that would skew an hour-based check.
#
# Even when the backfill itself is throttled, the cheap wiki index refresh
# still runs so deletions / manual edits are reflected without a week's lag.
#
# Mirrors state into Paper_Recommendation/.status/ for the Cowork monitor.
#
# Override paths by exporting before launchd loads this:
#   PAPER_REC_PATH   default: $HOME/Documents/Paper_Recommendation
#   CLAUDE_BIN       default: /opt/homebrew/bin/claude
set -u

# ---- paths -----------------------------------------------------------------
CLAUDE_BIN="${CLAUDE_BIN:-/opt/homebrew/bin/claude}"
PAPER_REC_PATH="${PAPER_REC_PATH:-$HOME/Documents/Paper_Recommendation}"

STATE_DIR="$HOME/Library/Application Support/daily-papers"
LAST_RUN_FILE="$STATE_DIR/backfill-last-run"
LOG_FILE="$STATE_DIR/backfill.log"
STATUS_DIR="$PAPER_REC_PATH/.status"

SCRIPT="$PAPER_REC_PATH/skills/_shared/backfill_empty_stubs.py"
INDEX_SCRIPT="$PAPER_REC_PATH/skills/_shared/generate_wiki_index.py"

# ---- schedule --------------------------------------------------------------
MIN_CALENDAR_DAYS=6   # require >=6 calendar days since last run

# ---- Cowork status mirror --------------------------------------------------
mirror_status() {
  mkdir -p "$STATUS_DIR" 2>/dev/null || return 0
  [ -f "$LAST_RUN_FILE" ] && cp -f "$LAST_RUN_FILE" "$STATUS_DIR/backfill-last-run" 2>/dev/null
  [ -f "$LOG_FILE"      ] && cp -f "$LOG_FILE"      "$STATUS_DIR/backfill.log"      2>/dev/null
  return 0
}
trap mirror_status EXIT

# ---- main ------------------------------------------------------------------
mkdir -p "$STATE_DIR"
now=$(date +%s)
ts() { date "+%Y-%m-%d %H:%M:%S"; }

# Calendar-day diff (time-of-day irrelevant, only the date matters).
if [ -f "$LAST_RUN_FILE" ]; then
  last=$(cat "$LAST_RUN_FILE" 2>/dev/null || echo 0)
  if [ "$last" != "0" ]; then
    days_since=$(python3 -c "
from datetime import date, datetime
last_d = datetime.fromtimestamp($last).date()
today  = date.today()
print((today - last_d).days)
")
    if [ "$days_since" -lt "$MIN_CALENDAR_DAYS" ]; then
      echo "[$(ts)] skip: only ${days_since} calendar day(s) since last run (need >=${MIN_CALENDAR_DAYS})" >> "$LOG_FILE"
      # Even when backfill is throttled, do the cheap weekly index refresh
      # so deletions / manual edits get reflected without waiting another week.
      if [ -f "$INDEX_SCRIPT" ]; then
        python3 "$INDEX_SCRIPT" >> "$LOG_FILE" 2>&1 || echo "[$(ts)] warn: index refresh failed" >> "$LOG_FILE"
      fi
      exit 0
    fi
  fi
fi

echo "[$(ts)] start: backfill empty concept stubs" >> "$LOG_FILE"

if [ ! -x "$CLAUDE_BIN" ]; then
  echo "[$(ts)] fatal: $CLAUDE_BIN not executable (claude CLI missing)" >> "$LOG_FILE"
  exit 1
fi

if [ ! -f "$SCRIPT" ]; then
  echo "[$(ts)] fatal: $SCRIPT not found" >> "$LOG_FILE"
  exit 1
fi

python3 "$SCRIPT" >> "$LOG_FILE" 2>&1
rc=$?
echo "[$(ts)] end: rc=$rc" >> "$LOG_FILE"

# Always refresh the wiki index after a real run too (catches deletions /
# manual edits made during the week, even when no stubs were backfilled).
if [ -f "$INDEX_SCRIPT" ]; then
  python3 "$INDEX_SCRIPT" >> "$LOG_FILE" 2>&1 || echo "[$(ts)] warn: index refresh failed" >> "$LOG_FILE"
fi

if [ "$rc" -eq 0 ]; then
  echo "$now" > "$LAST_RUN_FILE"
else
  echo "[$(ts)] not updating last-run because rc=$rc" >> "$LOG_FILE"
fi

exit $rc
