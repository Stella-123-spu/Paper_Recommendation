#!/bin/bash
# Daily-papers pipeline runner.
#
# Invoked by launchd at 9am daily. Self-throttles to a true ~3-day cadence
# by checking `last-run` and skipping unless MIN_INTERVAL_SEC - SLACK_SEC
# has elapsed. Mirrors state into the Cowork-readable .status/ folder so the
# Paper Pipeline Monitor artifact can read it.
#
# Override paths by exporting env vars before launchd loads this:
#   PAPER_REC_PATH   default: $HOME/Documents/Paper_Recommendation
#   OBSIDIAN_VAULT   default: $HOME/Documents/Obsidian/Research
#   CLAUDE_BIN       default: /opt/homebrew/bin/claude
set -u

# ---- paths -----------------------------------------------------------------
CLAUDE_BIN="${CLAUDE_BIN:-/opt/homebrew/bin/claude}"
PAPER_REC_PATH="${PAPER_REC_PATH:-$HOME/Documents/Paper_Recommendation}"
OBSIDIAN_VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/Obsidian/Research}"

STATE_DIR="$HOME/Library/Application Support/daily-papers"
LAST_RUN_FILE="$STATE_DIR/last-run"
LOG_FILE="$STATE_DIR/runner.log"
STATUS_DIR="$PAPER_REC_PATH/.status"

# ---- schedule --------------------------------------------------------------
MIN_INTERVAL_SEC=$((3 * 24 * 60 * 60))   # 3 days nominal cadence
SLACK_SEC=$((6 * 60 * 60))               # fire up to 6h early (drift absorption)

WORK_DIR="$OBSIDIAN_VAULT"
PROMPT="paper recommendations from the last 3 days"

# ---- Cowork status mirror --------------------------------------------------
# Runs on every exit path (skip, fatal, normal) so the monitor never misses
# state changes. Without `trap`, a `skip` exit would bypass the mirror.
mirror_status() {
  mkdir -p "$STATUS_DIR" 2>/dev/null || return 0
  [ -f "$LAST_RUN_FILE" ] && cp -f "$LAST_RUN_FILE" "$STATUS_DIR/last-run"   2>/dev/null
  [ -f "$LOG_FILE"      ] && cp -f "$LOG_FILE"      "$STATUS_DIR/runner.log" 2>/dev/null
  return 0
}
trap mirror_status EXIT

# ---- main ------------------------------------------------------------------
mkdir -p "$STATE_DIR"
now=$(date +%s)
ts() { date "+%Y-%m-%d %H:%M:%S"; }

if [ -f "$LAST_RUN_FILE" ]; then
  last=$(cat "$LAST_RUN_FILE" 2>/dev/null || echo 0)
  diff=$((now - last))
  threshold=$((MIN_INTERVAL_SEC - SLACK_SEC))
  if [ "$diff" -lt "$threshold" ]; then
    hours=$((diff / 3600))
    echo "[$(ts)] skip: ${hours}h since last run (need >=$((threshold/3600))h)" >> "$LOG_FILE"
    exit 0
  fi
fi

echo "[$(ts)] start: cwd=$WORK_DIR prompt=\"$PROMPT\"" >> "$LOG_FILE"

cd "$WORK_DIR" || { echo "[$(ts)] fatal: cd $WORK_DIR failed" >> "$LOG_FILE"; exit 1; }

if [ ! -x "$CLAUDE_BIN" ]; then
  echo "[$(ts)] fatal: $CLAUDE_BIN not executable" >> "$LOG_FILE"
  exit 1
fi

"$CLAUDE_BIN" -p --dangerously-skip-permissions "$PROMPT" >> "$LOG_FILE" 2>&1
rc=$?
echo "[$(ts)] end: rc=$rc" >> "$LOG_FILE"

if [ "$rc" -eq 0 ]; then
  echo "$now" > "$LAST_RUN_FILE"
else
  echo "[$(ts)] not updating last-run because rc=$rc" >> "$LOG_FILE"
fi

exit $rc
