#!/bin/bash
# Registers the weekly rebalance-check launchd job. Not run automatically —
# execute this yourself when you want the schedule active:
#   bash scripts/install_schedule.sh
set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="$PKG_DIR/scripts/com.stockevaluator.rebalance.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.stockevaluator.rebalance.plist"

sed -e "s#__PKG_DIR__#$PKG_DIR#g" -e "s#__HOME__#$HOME#g" "$PLIST_SRC" > "$PLIST_DST"
echo "Wrote $PLIST_DST"

chmod +x "$PKG_DIR/scripts/run_rebalance_check.sh"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "Loaded com.stockevaluator.rebalance — runs every Monday at 08:00."
echo "Logs: $HOME/stock-evaluator-rebalance.log"
echo "To remove: launchctl unload $PLIST_DST && rm $PLIST_DST"
