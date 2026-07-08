#!/bin/bash
# Runs a rebalance check against a portfolio.json and writes a timestamped
# markdown report. Invoked by com.stockevaluator.rebalance.plist on its own
# weekly schedule (independent of this repo's existing daily 08:30 mailer).
#
# Configure via env vars before calling, or edit the defaults below:
#   PORTFOLIO_PATH   path to portfolio.json (default: ~/stock-portfolio-evaluator/portfolio.json)
#   REPORT_DIR       where dated reports are written (default: ~/stock-portfolio-evaluator/reports)
#   REWARD_RISK      newsvendor Cu, default 2.0
#   HORIZON_DAYS     holding horizon in trading days, default 20
#   DRIFT_THRESHOLD  absolute weight drift that triggers ADD/TRIM, default 0.05

set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORTFOLIO_PATH="${PORTFOLIO_PATH:-$PKG_DIR/portfolio.json}"
REPORT_DIR="${REPORT_DIR:-$PKG_DIR/reports}"
REWARD_RISK="${REWARD_RISK:-2.0}"
HORIZON_DAYS="${HORIZON_DAYS:-20}"
DRIFT_THRESHOLD="${DRIFT_THRESHOLD:-0.05}"

mkdir -p "$REPORT_DIR"

if [ ! -f "$PORTFOLIO_PATH" ]; then
    echo "No portfolio found at $PORTFOLIO_PATH — run 'stock-evaluator ingest <holdings.csv>' first." >&2
    exit 1
fi

REPORT_PATH="$REPORT_DIR/rebalance_$(date +%Y-%m-%d).md"

cd "$PKG_DIR"
python3 -m stock_evaluator.cli evaluate "$PORTFOLIO_PATH" \
    --reward-risk "$REWARD_RISK" \
    --horizon-days "$HORIZON_DAYS" \
    --drift-threshold "$DRIFT_THRESHOLD" \
    -o "$REPORT_PATH"

echo "Rebalance report written to $REPORT_PATH"
