# stock-portfolio-evaluator

Newsvendor-based stop-loss/target banding and rebalance checking for a stock
portfolio, built to sit alongside this repo's multi-market Cassandra data
(India/US/Europe/Japan/Korea).

## Why "newsvendor"

The [newsvendor problem](https://en.wikipedia.org/wiki/Newsvendor_model) picks
an order quantity that balances the cost of ordering too little (`Cu`,
underage) against the cost of ordering too much (`Co`, overage); the optimal
quantile is the *critical fractile* `Cu / (Cu + Co)`.

Here that same asymmetric-cost idea sizes a stop-loss/target band around a
position's entry price (or the price `horizon_days` ago, if there's no cost
basis), scaled by the stock's own historical volatility:

```
target_price    = anchor_price * exp(mu_h + Cu * sigma_h)
stop_loss_price = anchor_price * exp(mu_h - Co * sigma_h)
```

`Cu` is your reward:risk appetite (`--reward-risk`, default 2.0 — let winners
run ~2x as far as you'll let losers run). `mu_h`/`sigma_h` are the mean/stdev
of the stock's log returns projected over the holding horizon.

## Data sources

`CompositeDataSource` (`stock_evaluator/ingest.py`) tries, in order:

1. This repo's `backend/db` Cassandra quote cache, if `backend/` is present
   next to this package and Cassandra is reachable — reuses already-computed
   RSI/EMA/fundamentals instead of re-fetching.
2. For `india` tickers: `market_data_consolidated/india/nse_bhav_cache.db`, a
   local SQLite NSE Bhavcopy cache — ~2,740 symbols (close to the full NSE
   universe), daily-updated through the current date, bare symbols (no
   `.NS`/`.BO` suffix). Path is overridable via `STOCK_EVALUATOR_INDIA_SQLITE`.
   Several smaller/older India OHLCV SQLite files also exist on this machine
   (`global_expansion_screener_framework/*.db`, ~60 curated large-caps back to
   2011) but aren't wired in — `nse_bhav_cache.db` already covers those same
   tickers more currently within the model's default lookback window, so
   adding the older files would only add redundant, staler rows.
3. For `china` tickers only: the local `market_data` Postgres database
   (`psql -d market_data`, connects as the local user, no password). That DB's
   `stocks`/`fundamentals` tables are empty metadata stubs for every market
   except china, but its `ohlcv_history` table has real, daily-updated price
   history for 291 China A-shares — so it's used for exactly that slice, and
   nothing else routes through it. Its `ticker` column is a varchar with no
   `.SS`/`.SZ` suffix, and (a known quirk of that table) the same stock can
   appear as both `'600519.0'` and `'600519'` from different load runs, only
   one of which has OHLCV attached; `ingest.py` tries both at the query
   boundary rather than assuming a single format.
4. `yfinance`, for price history and as a quote fallback (the only price
   source for US and every other market — see below).

None of these are hard dependencies: if Cassandra isn't running, `backend/`
isn't importable, the SQLite file is missing, or Postgres/`psycopg2` isn't
reachable, everything falls through to the next source, down to `yfinance`
alone. `psycopg2-binary` is an optional extra (`pip install -e .[postgres]`)
— not required unless you want the China history path; `sqlite3` is stdlib.

### Investigated and deliberately *not* wired in

- `Downloads/data/us_screener_output/screener.db` — no OHLCV time series at
  all, just a single stale scan snapshot (`last_price` is empty for most
  rows, `scanned_at` is a single fixed date). There is currently no local US
  price source beyond yfinance.
- `global-market-scanners/dvm_global.db` and `viability.db` — do cover other
  markets (e.g. Europe, individual European exchanges), but they're
  point-in-time technical-indicator/strategy-summary snapshots, not price
  history, so they can't feed `NewsvendorModel`'s return-volatility fit.
- `global-market-scanners/edgar_facts.db` — SEC XBRL fundamentals (US), not
  price data.
- `market_data_consolidated/{japan,uk,...}/*.parquet` — per-ticker parquet
  caches, but spot-checking them found tickers misfiled under the wrong
  market folder (e.g. Indian `.NS`/`.BO` tickers sitting under `japan/` and
  `uk/`, apparently from a substring-matching bug in whatever built that
  tree) — not trustworthy enough to route through without a real audit.

## `BrokerReportIngestor` (INDmoney Excel exports)

`india_holdings_from_xlsx()` resolves each row's ISIN to an NSE symbol via a
local `nse_equity_list.csv` copy (`_load_nse_isin_map()`), since INDmoney's
own "Stock Name" column is a placeholder (`"Externally Purchased holding with
ISIN ..."`) for any holding it never priced itself. That list only covers
NSE-listed equities as of whenever it was last refreshed — BSE-only listings
and fund/ETF ISINs (often `INF`-prefixed) are frequently missing. Unresolved
rows are **not dropped**: the raw ISIN is kept as the ticker so quantity/value
accounting stays complete, and `ingest-broker` prints the full unresolved list
so they can be remapped by hand. In one real run this was ~30% of rows (21/73).

## Known limitation: yfinance rate limiting on large portfolios

A single `evaluate` call makes up to 2 yfinance requests per holding (quote +
history), plus one per *unresolved* ISIN placeholder (which always 404s, since
it's not a real ticker) before falling back. On a 90-holding portfolio this
was observed to occasionally trip Yahoo's rate limiting mid-run, which fails
*fast* rather than slow — every US holding after the trip silently reported
`NO_DATA` (0.0% weight) in about 7 seconds total, instead of the ~60-90s a
clean run actually takes. There's no retry/backoff yet. If a report looks
suspiciously fast and full of `NO_DATA`/`-` rows, re-run it — that's the
signal something upstream failed, not that those holdings have no data.

## Install

```bash
cd stock-portfolio-evaluator
pip install -e .
```

## CLI

```bash
# Build portfolio.json from a broker holdings export (flexible column names:
# ticker/symbol, quantity/qty, avg_cost/buy_price, market, target_weight)
stock-evaluator ingest holdings.csv -o portfolio.json

# Build portfolio.json from INDmoney's US (Alpaca-routed) and/or India Excel exports
# — merges both into one portfolio, summing quantity for any ticker in both
stock-evaluator ingest-broker --us us_holdings.xls --india india_holdings.xlsx -o portfolio.json

# Run a rebalance check
stock-evaluator evaluate portfolio.json --format markdown -o report.md
stock-evaluator evaluate portfolio.json --reward-risk 2.5 --horizon-days 30 --drift-threshold 0.03

# Exit 1 if any holding needs EXIT/TRIM/ADD (useful for cron alerting)
stock-evaluator evaluate portfolio.json --fail-on-action

# Parse a broker tax P&L export into LTCG/STCG-tagged records
stock-evaluator realized-gains capital_gains.csv -o gains.json
```

## Library

```python
from stock_evaluator import Portfolio, Holding, PortfolioEvaluator

portfolio = Portfolio(holdings=[
    Holding(ticker="RELIANCE", market="india", quantity=10, avg_cost=2400.0, target_weight=0.5),
    Holding(ticker="TCS", market="india", quantity=5, avg_cost=3500.0, target_weight=0.5),
])
report = PortfolioEvaluator(portfolio).run()
print(report.to_markdown())
```

See `examples/sample_analysis.py` for a fuller walkthrough.

## Regular rebalance checks

`scripts/install_schedule.sh` registers a standalone weekly launchd job (on
its own cadence, independent of this repo's existing daily 08:30 mailer) that
runs `stock-evaluator evaluate` against a portfolio file and writes the report
out. See that script for configuration.

## Tests

```bash
python -m pytest tests/ -v
```

All tests run against synthetic price series — no network calls.
