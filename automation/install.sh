#!/bin/bash
# Install / uninstall the daily-papers launchd automation + monitor.
#
# Usage:
#   ./install.sh              install (idempotent — safe to re-run)
#   ./install.sh --uninstall  remove plists from launchd, leave state alone
#   ./install.sh --uninstall --purge   also delete state files and .status mirror
#   ./install.sh --dry-run    show what would happen, do nothing
#
# Assumes:
#   - macOS with launchd
#   - This script lives in <repo>/automation/ and runs from there
#   - Obsidian vault is at $HOME/Documents/Obsidian/Research (override via env)
#   - Paper_Recommendation repo is at $HOME/Documents/Paper_Recommendation (override via env)
set -euo pipefail

# ---- paths ----
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
LAUNCHD_SRC="$HERE/launchd"
MONITOR_SRC="$HERE/monitor"

STATE_DIR="$HOME/Library/Application Support/daily-papers"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"
PAPER_REC_PATH="${PAPER_REC_PATH:-$HOME/Documents/Paper_Recommendation}"
STATUS_DIR="$PAPER_REC_PATH/.status"

# ---- args ----
MODE="install"
PURGE=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --uninstall) MODE="uninstall" ;;
    --purge) PURGE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg"; exit 2 ;;
  esac
done

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] $*"
  else
    eval "$*"
  fi
}

say() { printf "  %s\n" "$*"; }
hdr() { printf "\n== %s ==\n" "$*"; }

# ---- discover jobs to install (one per .plist in launchd/) ----
shopt -s nullglob
PLISTS=("$LAUNCHD_SRC"/*.plist)
if [ "${#PLISTS[@]}" -eq 0 ]; then
  echo "no .plist files found under $LAUNCHD_SRC"; exit 1
fi

label_of() {
  # Extract <key>Label</key> value from a plist (best-effort, no plistbuddy dep)
  awk '/<key>Label<\/key>/{getline; gsub(/^[ \t]*<string>|<\/string>[ \t]*$/,""); print; exit}' "$1"
}

# ============================================================================
# UNINSTALL
# ============================================================================
if [ "$MODE" = "uninstall" ]; then
  hdr "Uninstalling launchd jobs"
  for plist_src in "${PLISTS[@]}"; do
    label="$(label_of "$plist_src")"
    deployed="$LAUNCHAGENTS_DIR/$(basename "$plist_src")"
    say "→ $label"
    run "launchctl bootout gui/$(id -u) '$deployed' 2>/dev/null || true"
    if [ -f "$deployed" ]; then
      run "rm '$deployed'"
    fi
  done

  if [ "$PURGE" -eq 1 ]; then
    hdr "Purging state"
    say "→ $STATE_DIR"
    run "rm -rf '$STATE_DIR'"
    say "→ $STATUS_DIR"
    run "rm -rf '$STATUS_DIR'"
  else
    say ""
    say "State preserved at:"
    say "  $STATE_DIR"
    say "  $STATUS_DIR"
    say "Pass --purge to also remove these."
  fi
  echo
  echo "Uninstall complete."
  exit 0
fi

# ============================================================================
# INSTALL
# ============================================================================

hdr "Preflight"
say "REPO_ROOT       = $REPO_ROOT"
say "STATE_DIR       = $STATE_DIR"
say "PAPER_REC_PATH  = $PAPER_REC_PATH"
say "STATUS_DIR      = $STATUS_DIR"
[ -d "$REPO_ROOT/skills" ] || { echo "WARNING: $REPO_ROOT/skills not found — is this really the Paper_Recommendation repo?"; }
[ -d "$HOME/Documents/Obsidian/Research" ] || say "NOTE: Obsidian vault at default path not found. Override with OBSIDIAN_VAULT=... in the plist EnvironmentVariables if needed."
command -v launchctl >/dev/null || { echo "launchctl missing — is this macOS?"; exit 1; }

hdr "Creating directories"
run "mkdir -p '$STATE_DIR'"
run "mkdir -p '$STATUS_DIR'"
run "mkdir -p '$LAUNCHAGENTS_DIR'"

hdr "Deploying runner scripts"
for src in "$LAUNCHD_SRC"/*.sh; do
  dst="$STATE_DIR/$(basename "$src")"
  say "→ $(basename "$src")"
  run "cp '$src' '$dst'"
  run "chmod +x '$dst'"
done

hdr "Deploying launchd plists (substituting __HOME__)"
for src in "${PLISTS[@]}"; do
  base="$(basename "$src")"
  dst="$LAUNCHAGENTS_DIR/$base"
  say "→ $base"
  # Substitute __HOME__ → $HOME and write out
  run "sed 's|__HOME__|$HOME|g' '$src' > '$dst'"
  # Validate
  if [ "$DRY_RUN" -eq 0 ]; then
    plutil -lint "$dst" >/dev/null || { echo "plist invalid: $dst"; exit 1; }
  fi
done

hdr "Reloading launchd"
for src in "${PLISTS[@]}"; do
  label="$(label_of "$src")"
  dst="$LAUNCHAGENTS_DIR/$(basename "$src")"
  say "→ $label"
  # bootout then bootstrap = idempotent reload
  run "launchctl bootout gui/$(id -u) '$dst' 2>/dev/null || true"
  run "launchctl bootstrap gui/$(id -u) '$dst'"
done

hdr "Seeding last-run (if absent)"
for src in "$LAUNCHD_SRC"/*.sh; do
  name="$(basename "$src" .sh)"   # 'runner' or 'backfill-runner'
  if [ "$name" = "runner" ]; then
    seed_file="$STATE_DIR/last-run"
  else
    seed_file="$STATE_DIR/$(echo "$name" | sed 's/-runner//')-last-run"
  fi
  if [ -f "$seed_file" ]; then
    say "✓ $seed_file already seeded"
  else
    say "→ seeding $seed_file = $(date +%s) (now)"
    run "date +%s > '$seed_file'"
  fi
done

hdr "Deploying monitor (substituting __HOME__)"
MONITOR_OUT="$STATE_DIR/paper-pipeline-monitor.html"
if [ -f "$MONITOR_SRC/paper-pipeline-monitor.html" ]; then
  say "→ $MONITOR_OUT"
  run "sed 's|__HOME__|$HOME|g' '$MONITOR_SRC/paper-pipeline-monitor.html' > '$MONITOR_OUT'"
else
  say "skip — no monitor source found"
fi

hdr "Bootstrapping .status mirror"
# Touch the runner once so the trap mirror_status copies current state.
if [ -x "$STATE_DIR/runner.sh" ]; then
  say "→ running runner.sh once (will skip due to seed, but mirrors state)"
  run "'$STATE_DIR/runner.sh' >/dev/null 2>&1 || true"
fi

hdr "Done"
cat <<EOF

Installed jobs:
$(for src in "${PLISTS[@]}"; do echo "  - $(label_of "$src")"; done)

Verify:
  launchctl list | grep sitongliu
  tail "$STATE_DIR/runner.log"
  ls -la "$STATUS_DIR"

Create Cowork monitor artifact:
  Open Cowork, ask Claude:
    "Create a Cowork artifact from $MONITOR_OUT, id 'paper-pipeline-monitor'."
  (or update an existing one with that id)

EOF
