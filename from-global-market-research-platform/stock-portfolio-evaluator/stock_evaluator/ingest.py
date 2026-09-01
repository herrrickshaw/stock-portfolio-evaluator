"""Data sourcing and portfolio/tax-report ingestion.

CompositeDataSource tries every source it can find, in order of freshness/cost:
  1. This machine's Cassandra quote cache (backend/db), if the backend package
     and a running Cassandra are both reachable — cheap, already-computed RSI/EMA/fundamentals.
  2. For india tickers: the local `nse_bhav_cache.db` SQLite file — a genuine, daily
     -updated NSE Bhavcopy cache covering ~2,740 symbols back to mid-2025 (bare NSE
     symbols, no .NS/.BO suffix). This is the broadest and freshest local India price
     source found on this machine — several smaller/older India OHLCV SQLite files
     also exist (`global_expansion_screener_framework/*.db`, ~60 curated large-caps
     back to 2011) but aren't wired in here since bhav_cache already covers those same
     tickers more currently, within the model's default lookback window.
  3. For china tickers only: the local `market_data` Postgres database, which has a
     real, daily-updated OHLCV history for 291 China A-shares (everything else in
     that DB — other markets, fundamentals, and most `stocks` rows for china itself —
     is an empty/duplicate metadata stub, so it's not used for anything but china
     price history).
  4. yfinance, for price history and as a fundamentals/quote fallback.

None of these sources are required at import time: if a dependency isn't importable,
or its service/file isn't reachable, the corresponding methods just return None/empty
and callers fall back to the next source.

Not wired in (investigated and rejected — see stock-portfolio-evaluator README):
`Downloads/data/us_screener_output/screener.db` has no OHLCV time series at all (a
single stale scan snapshot with an empty `last_price` column), so there is currently
no local US price source beyond yfinance. `global-market-scanners/dvm_global.db` and
`viability.db` cover other markets (e.g. Europe) but are point-in-time technical/
summary snapshots, not price history, so they can't feed NewsvendorModel's return-
volatility fit either.
"""
from __future__ import annotations

import csv
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from .portfolio import Holding, Portfolio

log = logging.getLogger(__name__)

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# Local Postgres `market_data` DB — trust/peer auth, no password needed.
_PG_CONN_KWARGS = dict(dbname="market_data", user="umashankar", host="localhost", port=5432)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_INDIA_SQLITE = _REPO_ROOT / "market_data_consolidated" / "india" / "nse_bhav_cache.db"


# ── ticker <-> market helpers (mirrors backend/fetchers/history.py conventions) ──

_SUFFIX_MAP = {
    "NS": "india", "BO": "india",
    "T": "japan",
    "KS": "korea", "KQ": "korea",
    "SS": "china", "SZ": "china",
    "HK": "hong_kong",
    "TO": "canada", "V": "canada",
}
_EUROPE_SUFFIXES = {"PA", "AS", "BR", "LS", "MI", "IR", "OL", "DE", "F",
                     "ST", "HE", "CO", "MC", "SW", "WA", "AT", "VI", "L"}
_MARKET_SUFFIX = {"india": ".NS"}  # only India needs a suffix appended for yfinance


def market_from_ticker(ticker: str) -> str:
    sfx = ticker.rsplit(".", 1)[-1].upper() if "." in ticker else ""
    if sfx in _SUFFIX_MAP:
        return _SUFFIX_MAP[sfx]
    if sfx in _EUROPE_SUFFIXES:
        return "europe"
    return "us"


def yf_symbol(ticker: str, market: str) -> str:
    """Map a bare/Cassandra-style ticker to the symbol yfinance expects."""
    suffix = _MARKET_SUFFIX.get(market, "")
    if not suffix:
        return ticker
    return ticker if ticker.upper().endswith(suffix.upper()) else f"{ticker}{suffix}"


def bare_ticker(ticker: str) -> str:
    for sfx in (".NS", ".BO", ".T", ".KS", ".KQ", ".SS", ".SZ", ".HK", ".TO", ".V"):
        if ticker.upper().endswith(sfx):
            return ticker[: -len(sfx)]
    return ticker


# ── Cassandra access (optional, best-effort) ─────────────────────────────────

def _find_backend_quotes(market: str, tickers: list[str]) -> dict[str, dict]:
    """Best-effort read from this repo's backend/db Cassandra cache. Returns {} if unavailable."""
    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"
    if not backend_dir.is_dir():
        return {}
    added = False
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
        added = True
    try:
        from db import cassandra_client as cass  # type: ignore
        from db.quote_updater import get_quotes  # type: ignore

        if cass.session() is None:
            return {}
        return get_quotes(market, tickers)
    except Exception as exc:
        log.debug("Cassandra quote lookup unavailable: %s", exc)
        return {}
    finally:
        if added:
            sys.path.remove(str(backend_dir))


# ── SQLite nse_bhav_cache access (india OHLCV only, best-effort) ─────────────

def _sqlite_india_history(ticker: str, lookback_days: int) -> pd.DataFrame:
    """Read India OHLCV from the local NSE Bhavcopy SQLite cache.

    Symbols there are bare NSE tickers (no .NS/.BO suffix), matching Cassandra's
    India convention. Path is overridable via STOCK_EVALUATOR_INDIA_SQLITE for
    machines where market_data_consolidated/ lives somewhere else.
    """
    db_path = Path(os.environ["STOCK_EVALUATOR_INDIA_SQLITE"]) if os.environ.get(
        "STOCK_EVALUATOR_INDIA_SQLITE") else _DEFAULT_INDIA_SQLITE
    if not db_path.is_file():
        return pd.DataFrame(columns=["close"])
    bare = bare_ticker(ticker)
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
    except Exception as exc:
        log.debug("nse_bhav_cache.db open failed: %s", exc)
        return pd.DataFrame(columns=["close"])
    try:
        rows = conn.execute(
            "SELECT d, close FROM prices WHERE symbol = ? ORDER BY d DESC LIMIT ?",
            (bare, lookback_days),
        ).fetchall()
    except Exception as exc:
        log.debug("nse_bhav_cache.db query failed for %s: %s", ticker, exc)
        return pd.DataFrame(columns=["close"])
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=["close"])
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


# ── Postgres market_data access (china OHLCV only, best-effort) ──────────────

def _postgres_china_history(ticker: str, lookback_days: int) -> pd.DataFrame:
    """Read China A-share OHLCV from the local market_data Postgres DB.

    `stocks.ticker` is a varchar with no .SS/.SZ suffix, and — a known data-quality
    quirk of this table — the same underlying ticker can appear as both '600006.0'
    and '600006' (two separate stock_id rows from different load runs); only the
    '.0'-suffixed row actually has OHLCV attached, so both forms are tried and
    whichever matches wins.
    """
    if not HAS_PSYCOPG2:
        return pd.DataFrame(columns=["close"])
    bare = bare_ticker(ticker)
    if not bare.isdigit():
        return pd.DataFrame(columns=["close"])
    try:
        conn = psycopg2.connect(connect_timeout=3, **_PG_CONN_KWARGS)
    except Exception as exc:
        log.debug("Postgres market_data connection failed: %s", exc)
        return pd.DataFrame(columns=["close"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT h.date, h.close_price
                FROM ohlcv_history h
                JOIN stocks s ON h.stock_id = s.stock_id
                JOIN markets m ON s.market_id = m.market_id
                WHERE m.market_name = 'china' AND s.ticker IN (%s, %s)
                ORDER BY h.date DESC
                LIMIT %s
                """,
                (f"{bare}.0", bare, lookback_days),
            )
            rows = cur.fetchall()
    except Exception as exc:
        log.debug("Postgres china history query failed for %s: %s", ticker, exc)
        return pd.DataFrame(columns=["close"])
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=["close"])
    # close_price is Postgres `numeric`, which psycopg2 hands back as Decimal —
    # cast to float or np.log()/std() blow up downstream.
    df = pd.DataFrame(rows, columns=["date", "close"]).set_index("date").sort_index()
    df["close"] = df["close"].astype(float)
    return df


# ── unified data source ───────────────────────────────────────────────────────

class CompositeDataSource:
    """Fetches quotes/history from whatever backing source is actually reachable."""

    def __init__(self, cache: bool = True):
        self._cache = cache
        self._history_cache: dict[str, pd.DataFrame] = {}
        self._quote_cache: dict[str, dict] = {}

    def get_quote(self, ticker: str, market: Optional[str] = None) -> dict:
        """Return {'cmp', 'rsi', 'ema_50', ...} for one ticker, or {} if nothing found."""
        market = market or market_from_ticker(ticker)
        key = f"{market}:{ticker}"
        if self._cache and key in self._quote_cache:
            return self._quote_cache[key]

        bare = bare_ticker(ticker)
        cass_hit = _find_backend_quotes(market, [bare, ticker])
        result = cass_hit.get(bare) or cass_hit.get(ticker) or {}

        if not result.get("cmp") and HAS_YF:
            try:
                sym = yf_symbol(ticker, market)
                fast = yf.Ticker(sym).fast_info
                cmp_ = getattr(fast, "last_price", None)
                if cmp_:
                    result = {**result, "cmp": float(cmp_), "source": result.get("source", "yfinance")}
            except Exception as exc:
                log.debug("yfinance quote fallback failed for %s: %s", ticker, exc)

        if self._cache:
            self._quote_cache[key] = result
        return result

    def get_price_history(self, ticker: str, market: Optional[str] = None,
                           lookback_days: int = 252) -> pd.DataFrame:
        """Daily close-price history as a DataFrame indexed by date, columns=['close']."""
        market = market or market_from_ticker(ticker)
        key = f"{market}:{ticker}:{lookback_days}"
        if self._cache and key in self._history_cache:
            return self._history_cache[key]

        df = pd.DataFrame(columns=["close"])
        if market == "india":
            df = _sqlite_india_history(ticker, lookback_days)
        elif market == "china":
            df = _postgres_china_history(ticker, lookback_days)

        if df.empty and HAS_YF:
            try:
                sym = yf_symbol(ticker, market)
                period = f"{max(lookback_days, 30) + 30}d"
                hist = yf.Ticker(sym).history(period=period, interval="1d")
                if not hist.empty:
                    df = hist[["Close"]].rename(columns={"Close": "close"}).tail(lookback_days)
            except Exception as exc:
                log.debug("yfinance history fetch failed for %s: %s", ticker, exc)

        if self._cache:
            self._history_cache[key] = df
        return df


class TaxReportIngestor:
    """Parses broker holdings / tax P&L exports into a Portfolio plus realized-gain records."""

    @staticmethod
    def holdings_from_csv(path: str | Path, name: Optional[str] = None) -> Portfolio:
        return Portfolio.from_csv(path, name=name)

    @staticmethod
    def realized_gains_from_csv(path: str | Path) -> list[dict]:
        """Parse a broker tax-P&L export (e.g. Zerodha/Screener capital-gains CSV) into records:
        [{'ticker', 'quantity', 'buy_date', 'sell_date', 'gain', 'term'}, ...]

        'term' is 'LTCG' or 'STCG', inferred from holding period when the source
        file doesn't say so explicitly (>365 days for India-style equity rules).
        """
        rows = list(csv.DictReader(Path(path).open(newline="")))
        if not rows:
            return []
        header = list(rows[0].keys())
        lowered = {h.lower().strip(): h for h in header}

        def col(*aliases: str) -> Optional[str]:
            for a in aliases:
                if a in lowered:
                    return lowered[a]
            return None

        c_ticker = col("ticker", "symbol", "scrip")
        c_qty = col("quantity", "qty")
        c_buy = col("buy_date", "purchase_date")
        c_sell = col("sell_date", "sale_date")
        c_gain = col("gain", "profit", "realized_gain", "pnl")
        c_term = col("term", "gain_type")
        if c_ticker is None or c_gain is None:
            raise ValueError(f"Could not find ticker/gain columns in {path}; header was {header}")

        records = []
        for row in rows:
            ticker = (row.get(c_ticker) or "").strip()
            if not ticker:
                continue
            gain_raw = row.get(c_gain)
            gain = float(gain_raw) if gain_raw not in (None, "") else 0.0
            term = (row.get(c_term) or "").strip().upper() if c_term else ""
            buy_date = row.get(c_buy) if c_buy else None
            sell_date = row.get(c_sell) if c_sell else None
            if term not in ("LTCG", "STCG") and buy_date and sell_date:
                try:
                    days = (pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days
                    term = "LTCG" if days > 365 else "STCG"
                except Exception:
                    term = term or "UNKNOWN"
            records.append({
                "ticker": ticker,
                "quantity": float(row.get(c_qty) or 0) if c_qty else None,
                "buy_date": buy_date,
                "sell_date": sell_date,
                "gain": gain,
                "term": term or "UNKNOWN",
            })
        return records


# ── ISIN -> NSE symbol resolution (local, offline) ────────────────────────────

_NSE_ISIN_CSV_CANDIDATES = [
    _REPO_ROOT / "data" / "nse_equity_list.csv",
    _REPO_ROOT / "herrrickshaw" / "data" / "nse_equity_list.csv",
    _REPO_ROOT / "market_data_consolidated" / "india" / "nse_equity_list.csv",
]


def _load_nse_isin_map() -> dict[str, str]:
    """ISIN -> bare NSE symbol, from whichever local nse_equity_list.csv copy exists.

    Covers NSE-listed equities only — BSE-only listings and mutual-fund/ETF ISINs
    (typically INF-prefixed) are frequently missing, so callers must handle
    unresolved ISINs explicitly rather than assuming full coverage.
    """
    for path in _NSE_ISIN_CSV_CANDIDATES:
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path)
            df.columns = [c.strip() for c in df.columns]
            return dict(zip(df["ISIN NUMBER"], df["SYMBOL"]))
        except Exception as exc:
            log.debug("Failed to load NSE ISIN map from %s: %s", path, exc)
    return {}


class BrokerReportIngestor:
    """Parses INDmoney's holdings-report Excel exports: an India (NSE demat) sheet
    keyed by ISIN, and a US sheet (INDmoney routes US investing through Alpaca)
    keyed directly by ticker. Both are `.xls`/`.xlsx` — needs xlrd/openpyxl.
    """

    @staticmethod
    def _find_header_row(df: pd.DataFrame, marker: str) -> int:
        for i, val in df[0].items():
            if isinstance(val, str) and val.strip() == marker:
                return i
        raise ValueError(f"Could not find a row starting with {marker!r} in this sheet")

    @staticmethod
    def us_holdings_from_xls(path: str | Path) -> list[Holding]:
        """'Stock Symbol' header row, fractional-share quantities, market='us'."""
        df = pd.read_excel(path, sheet_name=0, header=None)
        start = BrokerReportIngestor._find_header_row(df, "Stock Symbol") + 1
        holdings = []
        for _, row in df.iloc[start:].iterrows():
            symbol = row[0]
            if not isinstance(symbol, str) or not symbol.strip():
                break  # end of data block (blank row / footer disclaimer text)
            avg_cost = float(row[3]) if pd.notna(row[3]) else None
            holdings.append(Holding(
                ticker=symbol.strip(), market="us",
                quantity=float(row[2]), avg_cost=avg_cost or None,
            ))
        return holdings

    @staticmethod
    def india_holdings_from_xlsx(path: str | Path,
                                  isin_map: Optional[dict[str, str]] = None
                                  ) -> tuple[list[Holding], list[dict]]:
        """'Stock Name' header row, keyed by ISIN — the 'Stock Name' column is a
        placeholder ('Externally Purchased holding with ISIN ...') for holdings
        INDmoney never priced, so ISIN is the only reliable join key.

        Returns (holdings, unresolved): unresolved entries still get a Holding
        (ticker set to the raw ISIN, so quantity/value accounting isn't lost) but
        won't fetch real quotes until manually remapped to an actual ticker.
        """
        isin_map = isin_map if isin_map is not None else _load_nse_isin_map()
        df = pd.read_excel(path, sheet_name=0, header=None)
        start = BrokerReportIngestor._find_header_row(df, "Stock Name") + 1
        holdings: list[Holding] = []
        unresolved: list[dict] = []
        for _, row in df.iloc[start:].iterrows():
            isin = row[1]
            if not isinstance(isin, str) or not isin.strip():
                break
            name, qty = row[0], float(row[2])
            avg_price = float(row[3]) if pd.notna(row[3]) else 0.0
            symbol = isin_map.get(isin.strip())
            if symbol is None:
                unresolved.append({"name": name, "isin": isin.strip(), "quantity": qty, "avg_price": avg_price})
                symbol = isin.strip()
            holdings.append(Holding(
                ticker=symbol, market="india", quantity=qty, avg_cost=avg_price or None,
            ))
        return holdings, unresolved

    @staticmethod
    def merge(*holding_lists: list[Holding], name: str = "combined") -> Portfolio:
        """Merge holdings from multiple broker exports into one Portfolio, summing
        quantity (and re-averaging cost) for any (market, ticker) seen more than once."""
        merged: dict[tuple[str, str], Holding] = {}
        for holdings in holding_lists:
            for h in holdings:
                key = (h.market, h.ticker)
                if key not in merged:
                    merged[key] = Holding(ticker=h.ticker, market=h.market, quantity=h.quantity,
                                           avg_cost=h.avg_cost, buy_date=h.buy_date)
                    continue
                existing = merged[key]
                total_qty = existing.quantity + h.quantity
                if existing.avg_cost is not None and h.avg_cost is not None and total_qty:
                    existing.avg_cost = (
                        existing.avg_cost * existing.quantity + h.avg_cost * h.quantity
                    ) / total_qty
                existing.quantity = total_qty
        return Portfolio(name=name, holdings=list(merged.values()))
