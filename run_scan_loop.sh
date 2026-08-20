#!/usr/bin/env bash
# Runs the multi-timeframe scan repeatedly. Meant for a persistent session
# (e.g. inside `tmux` on Termux) so it survives for days.
#
# Usage: ./run_scan_loop.sh [interval_seconds] [balance]
set -euo pipefail
cd "$(dirname "$0")"

INTERVAL="${1:-300}"   # default: every 5 minutes, matching the shortest scanned timeframe
BALANCE="${2:-10000}"

mkdir -p logs

while true; do
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') ===" >> logs/scan.log
  python -m bot.analyze --timeframes 5min,15min,30min --balance "$BALANCE" >> logs/scan.log 2>&1 || true
  sleep "$INTERVAL"
done
