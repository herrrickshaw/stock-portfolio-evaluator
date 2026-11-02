# Stock Portfolio Evaluator

A small Python library and command-line tool that reads a stock holdings file (generic CSV/Excel, or an INDmoney
tax P&L report) and produces a rule-based Buy / Hold / Sell view for each position, using a newsvendor-style
holding-cost vs regret-cost model. Output is a plain-text report or console tables, in INR. It is aimed at
Indian-equity retail portfolios.

> Status: maintained, small. Research and education only; **not investment advice**. The scoring rules are heuristic
> constants in `stock_evaluator/config.py`, not a validated forecasting model.

[How to use this repo with an AI assistant](HOW_TO_USE_WITH_AI.md) ·
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/stock-portfolio-evaluator/blob/main/notebooks/colab_test.ipynb)

## What it does
- Loads holdings from a generic CSV or Excel file (`symbol, quantity, purchase_price, current_price[, sector]`).
- Parses the `UNREALIZED P/L` section of an INDmoney annual tax P&L CSV.
- Estimates a 3-month gain potential per stock from sector, momentum (current return) and beta.
- Applies a newsvendor holding/shortage cost model (defaults: 8% holding, 25% shortage, critical ratio about 0.76).
- Scores each position and maps it to STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL.
- Prints a report, a top-N "gainers" list, or hold/sell action lists.

## Quick start
```bash
git clone https://github.com/herrrickshaw/stock-portfolio-evaluator.git
cd stock-portfolio-evaluator
python -m venv .venv && source .venv/bin/activate
pip install -e .
stock-eval evaluate your_portfolio.csv --report
```

Other commands:
```bash
stock-eval gainers your_portfolio.csv --top 10
stock-eval actions your_portfolio.csv
stock-eval evaluate report.csv --type indmoney --output report.txt
```
`--type` is `auto` (default), `indmoney`, `csv` or `excel`; auto picks `indmoney` for file names containing
"indmoney" or "pnl", `excel` for `.xlsx/.xls`, otherwise `csv`.

Python API:
```python
from stock_evaluator import TaxReportIngestor, PortfolioEvaluator

portfolio = TaxReportIngestor.from_indmoney_report("tax_report.csv")
print(PortfolioEvaluator().generate_report(portfolio))
```

## How it works
| Stage | Module | Output |
|---|---|---|
| Ingest | `ingest.py`, `portfolio.py` | `Portfolio` of `StockPosition` |
| Constants | `config.py` | rates, sector/beta tables, score bands, thresholds |
| Score | `models.py` (`NewsvendorModel`, `StockEvaluator`) | recommendation + analysis dict |
| Aggregate and render | `evaluator.py` | summary dicts, gainers, hold/sell lists, text report |
| CLI | `cli.py` | `stock-eval evaluate / gainers / actions` |

Scoring: the score is the sum of a contrarian return band (deep losses score high, big gains score low), a
gain-potential band, and a penalty when newsvendor carrying cost is large relative to expected gain. Thresholds
(30 / 15 / -15 / -30) map the score to a label. All holdings are assumed to be one year old (purchase dates are not used).

## Repository layout
| Path | Purpose |
|---|---|
| `stock_evaluator/` | the package (see table above) |
| `tests/` | pytest suite; `tests/golden/` holds CLI output captured before the 2026-11 refactor |
| `examples/sample_analysis.py` | script example (edit the report path first) |
| `notebooks/colab_test.ipynb` | Colab test notebook |
| `from-global-market-research-platform/` | imported legacy snapshot of an earlier version, kept for history; not part of the package |

## Configuration
No environment variables, no secrets, no network access. Tunables live in `stock_evaluator/config.py`;
`PortfolioEvaluator(evaluator=..., sector_map=...)` accepts overrides.

## Testing
```bash
pip install pytest ruff
pytest -q
ruff check stock_evaluator tests
```

## Limitations and known issues
- Heuristic constants, not calibrated; recommendations are mechanical outputs, not advice.
- Sector is guessed by substring match on the symbol (first hit wins), defaulting to Technology; for example
  `ONGC LTD` resolves to Industrials because `LT` matches first.
- A blank `sector` cell in a CSV is read as NaN and is displayed as `nan` instead of falling back to the symbol lookup.
- `price_volatility` and the CAPM rates are accepted but not used in scoring.
- Amounts are formatted in rupees regardless of the input currency.
- Python 3.9+ is the tested floor.

## Licence
MIT, see `LICENSE`.
