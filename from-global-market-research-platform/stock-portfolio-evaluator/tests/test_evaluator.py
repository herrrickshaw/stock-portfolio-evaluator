"""Unit tests for stock_evaluator. Pure synthetic data — no network calls."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from stock_evaluator.evaluator import PortfolioEvaluator
from stock_evaluator.ingest import (
    BrokerReportIngestor, TaxReportIngestor, _postgres_china_history, _sqlite_india_history,
)
from stock_evaluator.models import NewsvendorModel, StockEvaluator
from stock_evaluator.portfolio import Holding, Portfolio


def _price_series(n: int, drift: float = 0.0, vol: float = 0.01, seed: int = 7,
                   start: float = 100.0) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, vol, n)
    prices = start * np.exp(np.cumsum(log_returns))
    return pd.Series(prices)


class StubDataSource:
    """Returns canned quote/history data; no network access."""

    def __init__(self, prices: pd.Series, cmp_override: float | None = None):
        self._prices = prices
        self._cmp = cmp_override if cmp_override is not None else float(prices.iloc[-1])

    def get_quote(self, ticker, market=None):
        return {"cmp": self._cmp}

    def get_price_history(self, ticker, market=None, lookback_days=252):
        return pd.DataFrame({"close": self._prices.tail(lookback_days)})


class NewsvendorModelTests(unittest.TestCase):
    def test_critical_fractile(self):
        model = NewsvendorModel(reward_risk_ratio=2.0, overage_cost=1.0)
        self.assertAlmostEqual(model.critical_fractile, 2 / 3)

    def test_band_brackets_current_price(self):
        prices = _price_series(300, drift=0.0, vol=0.015)
        model = NewsvendorModel(reward_risk_ratio=2.0, overage_cost=1.0, horizon_days=20)
        model.fit(prices)
        band = model.band(anchor_price=float(prices.iloc[-1]))
        self.assertGreater(band.target_price, band.anchor_price)
        self.assertLess(band.stop_loss_price, band.anchor_price)
        self.assertEqual(band.horizon_days, 20)

    def test_fit_requires_min_history(self):
        model = NewsvendorModel(min_history=30)
        with self.assertRaises(ValueError):
            model.fit(pd.Series([100.0, 101.0, 99.0]))

    def test_higher_reward_risk_widens_target_more_than_stop(self):
        prices = _price_series(300, drift=0.0, vol=0.02)
        cmp_ = float(prices.iloc[-1])
        conservative = NewsvendorModel(reward_risk_ratio=1.0, overage_cost=1.0).fit(prices).band(cmp_)
        aggressive = NewsvendorModel(reward_risk_ratio=3.0, overage_cost=1.0).fit(prices).band(cmp_)
        target_gap_conservative = conservative.target_price - cmp_
        target_gap_aggressive = aggressive.target_price - cmp_
        self.assertGreater(target_gap_aggressive, target_gap_conservative)
        # stop distance is unaffected by reward_risk_ratio (only overage_cost moves it)
        self.assertAlmostEqual(conservative.stop_loss_price, aggressive.stop_loss_price, places=6)


class StockEvaluatorTests(unittest.TestCase):
    def test_uptrend_triggers_trim(self):
        history = _price_series(260, drift=0.0, vol=0.01, start=100.0)
        source = StubDataSource(history, cmp_override=float(history.iloc[-1]) * 1.5)
        evaluator = StockEvaluator(source, model_kwargs={"reward_risk_ratio": 2.0, "horizon_days": 20})
        result = evaluator.evaluate("TEST", market="india")
        self.assertEqual(result.signal, "TRIM")

    def test_downtrend_triggers_exit(self):
        history = _price_series(260, drift=0.0, vol=0.01, start=100.0)
        source = StubDataSource(history, cmp_override=float(history.iloc[-1]) * 0.5)
        evaluator = StockEvaluator(source, model_kwargs={"reward_risk_ratio": 2.0, "horizon_days": 20})
        result = evaluator.evaluate("TEST", market="india")
        self.assertEqual(result.signal, "EXIT")

    def test_stable_price_holds(self):
        history = _price_series(260, drift=0.0, vol=0.01, start=100.0)
        source = StubDataSource(history, cmp_override=float(history.iloc[-1]))
        evaluator = StockEvaluator(source, model_kwargs={"reward_risk_ratio": 2.0, "horizon_days": 20})
        result = evaluator.evaluate("TEST", market="india")
        self.assertEqual(result.signal, "HOLD")

    def test_unrealized_pnl_pct(self):
        history = _price_series(260, drift=0.0, vol=0.01, start=100.0)
        cmp_ = float(history.iloc[-1])
        source = StubDataSource(history, cmp_override=cmp_)
        evaluator = StockEvaluator(source)
        result = evaluator.evaluate("TEST", market="india", avg_cost=cmp_ / 1.1)
        self.assertAlmostEqual(result.unrealized_pnl_pct, 10.0, places=3)


class PortfolioTests(unittest.TestCase):
    def test_weights_sum_to_one(self):
        portfolio = Portfolio(holdings=[
            Holding(ticker="A", quantity=10),
            Holding(ticker="B", quantity=5),
        ])
        weights = portfolio.weights({"A": 100.0, "B": 200.0})
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["A"], 1000 / 2000)
        self.assertAlmostEqual(weights["B"], 1000 / 2000)

    def test_target_weights_equal_split_default(self):
        portfolio = Portfolio(holdings=[Holding(ticker="A"), Holding(ticker="B"), Holding(ticker="C")])
        targets = portfolio.target_weights()
        self.assertAlmostEqual(sum(targets.values()), 1.0)
        for t in targets.values():
            self.assertAlmostEqual(t, 1 / 3)

    def test_target_weights_explicit_overrides(self):
        portfolio = Portfolio(holdings=[
            Holding(ticker="A", target_weight=0.6),
            Holding(ticker="B"),
        ])
        targets = portfolio.target_weights()
        self.assertAlmostEqual(targets["A"], 0.6)
        self.assertAlmostEqual(targets["B"], 0.4)

    def test_from_csv_flexible_columns(self):
        csv_body = "symbol,qty,buy_price,market\nRELIANCE,10,2400,india\nAAPL,5,150,us\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.csv"
            path.write_text(csv_body)
            portfolio = Portfolio.from_csv(path)
        self.assertEqual(len(portfolio.holdings), 2)
        self.assertEqual(portfolio.holdings[0].ticker, "RELIANCE")
        self.assertEqual(portfolio.holdings[0].quantity, 10)
        self.assertEqual(portfolio.holdings[0].avg_cost, 2400)

    def test_save_and_load_roundtrip(self):
        portfolio = Portfolio(name="p1", holdings=[Holding(ticker="A", quantity=3, avg_cost=50.0)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "portfolio.json"
            portfolio.save(path)
            loaded = Portfolio.load(path)
        self.assertEqual(loaded.name, "p1")
        self.assertEqual(loaded.holdings[0].ticker, "A")
        self.assertEqual(loaded.holdings[0].quantity, 3)


class TaxReportIngestorTests(unittest.TestCase):
    def test_realized_gains_infers_term_from_dates(self):
        csv_body = (
            "ticker,quantity,buy_date,sell_date,gain\n"
            "RELIANCE,10,2023-01-01,2024-06-01,5000\n"  # >365 days -> LTCG
            "TCS,5,2024-01-01,2024-03-01,1200\n"          # <=365 days -> STCG
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gains.csv"
            path.write_text(csv_body)
            records = TaxReportIngestor.realized_gains_from_csv(path)
        by_ticker = {r["ticker"]: r for r in records}
        self.assertEqual(by_ticker["RELIANCE"]["term"], "LTCG")
        self.assertEqual(by_ticker["TCS"]["term"], "STCG")


class PortfolioEvaluatorTests(unittest.TestCase):
    def test_underweight_holding_flagged_add(self):
        portfolio = Portfolio(holdings=[
            Holding(ticker="A", quantity=100, target_weight=0.5),
            Holding(ticker="B", quantity=1, target_weight=0.5),
        ])

        class MultiStubSource:
            def __init__(self):
                self._history = _price_series(260, drift=0.0, vol=0.01, start=100.0)
                # cmp == last close, which falls inside its own newsvendor band (verified
                # for this seed), so the band signal stays HOLD and only weight drift decides.
                self._cmp = float(self._history.iloc[-1])

            def get_quote(self, ticker, market=None):
                return {"cmp": self._cmp}

            def get_price_history(self, ticker, market=None, lookback_days=252):
                return pd.DataFrame({"close": self._history.tail(lookback_days)})

        evaluator = PortfolioEvaluator(portfolio, data_source=MultiStubSource(), drift_threshold=0.05)
        report = evaluator.run()
        by_ticker = {h.ticker: h for h in report.holdings}
        self.assertEqual(by_ticker["A"].action, "TRIM")  # 100 * 100 = 10000, way overweight
        self.assertEqual(by_ticker["B"].action, "ADD")    # 1 * 100 = 100, way underweight

    def test_exit_signal_overrides_drift_add(self):
        portfolio = Portfolio(holdings=[Holding(ticker="A", quantity=1, target_weight=1.0)])

        class CrashingStubSource:
            def __init__(self):
                self._history = _price_series(260, drift=0.0, vol=0.01, start=100.0)

            def get_quote(self, ticker, market=None):
                return {"cmp": float(self._history.iloc[-1]) * 0.5}  # crashed -> below stop-loss

            def get_price_history(self, ticker, market=None, lookback_days=252):
                return pd.DataFrame({"close": self._history.tail(lookback_days)})

        evaluator = PortfolioEvaluator(portfolio, data_source=CrashingStubSource())
        report = evaluator.run()
        self.assertEqual(report.holdings[0].action, "EXIT")


class PostgresChinaHistoryTests(unittest.TestCase):
    """Mocks psycopg2 entirely — no real DB connection made."""

    def test_maps_suffixed_ticker_to_bare_float_and_parses_rows(self):
        # psycopg2 hands back Postgres `numeric` columns as Decimal, not float —
        # use Decimal here so a regression (np.log() choking on Decimal) fails loudly.
        mock_cursor = mock.MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("2024-01-02", Decimal("10.5")), ("2024-01-03", Decimal("10.7")),
        ]
        mock_conn = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with mock.patch("stock_evaluator.ingest.psycopg2.connect", return_value=mock_conn) as connect:
            df = _postgres_china_history("600519.SS", lookback_days=10)

        connect.assert_called_once()
        query_params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(query_params[0], "600519.0")  # tries the '.0'-suffixed form first
        self.assertEqual(query_params[1], "600519")    # and the bare form as fallback
        self.assertEqual(list(df["close"]), [10.5, 10.7])
        self.assertEqual(df["close"].dtype, np.float64)
        np.log(df["close"])  # must not raise — this is what broke before the astype(float) fix

    def test_non_numeric_ticker_skips_query_entirely(self):
        with mock.patch("stock_evaluator.ingest.psycopg2.connect") as connect:
            df = _postgres_china_history("AAPL", lookback_days=10)
        connect.assert_not_called()
        self.assertTrue(df.empty)

    def test_connection_failure_returns_empty_frame(self):
        with mock.patch("stock_evaluator.ingest.psycopg2.connect", side_effect=Exception("no db")):
            df = _postgres_china_history("600519.SS", lookback_days=10)
        self.assertTrue(df.empty)


class SqliteIndiaHistoryTests(unittest.TestCase):
    """Uses a real temp SQLite file with the nse_bhav_cache.db schema — no mocking needed."""

    def _make_bhav_db(self, rows):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute(
            "CREATE TABLE prices(symbol TEXT, d TEXT, open REAL, high REAL, low REAL, "
            "close REAL, volume INTEGER, PRIMARY KEY(symbol, d))"
        )
        conn.executemany("INSERT INTO prices(symbol, d, close) VALUES (?, ?, ?)", rows)
        conn.commit()
        conn.close()
        return tmp.name

    def test_bare_symbol_lookup_strips_suffix(self):
        db_path = self._make_bhav_db([
            ("RELIANCE", "2026-07-01", 1300.0),
            ("RELIANCE", "2026-07-02", 1310.0),
            ("TCS", "2026-07-01", 3900.0),
        ])
        with mock.patch.dict("os.environ", {"STOCK_EVALUATOR_INDIA_SQLITE": db_path}):
            df = _sqlite_india_history("RELIANCE.NS", lookback_days=10)
        self.assertEqual(list(df["close"]), [1300.0, 1310.0])

    def test_missing_db_file_returns_empty(self):
        with mock.patch.dict("os.environ", {"STOCK_EVALUATOR_INDIA_SQLITE": "/no/such/file.db"}):
            df = _sqlite_india_history("RELIANCE.NS", lookback_days=10)
        self.assertTrue(df.empty)


class BrokerReportIngestorTests(unittest.TestCase):
    """Synthetic fixtures shaped like INDmoney's real export layout (header row
    preceded by account-summary rows, data terminated by a blank/footer row) —
    not the user's actual files."""

    def _write_xlsx(self, rows):
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        pd.DataFrame(rows).to_excel(tmp.name, header=False, index=False)
        return tmp.name

    def test_us_holdings_stops_at_blank_row(self):
        path = self._write_xlsx([
            ["Account Details", None, None, None, None],
            ["Broker Name", "Alpaca", None, None, None],
            [None, None, None, None, None],
            ["Stock Symbol", "Holding Since", "Quantity", "Avg. Price ($)", "Total Value ($)"],
            ["AAPL", "01 Jan 2026", 0.5, 170.0, 85.0],
            ["MSFT", "02 Jan 2026", 0.25, 330.0, 82.5],
            [None, None, None, None, None],
            ["Disclaimer:-", None, None, None, None],
        ])
        holdings = BrokerReportIngestor.us_holdings_from_xls(path)
        self.assertEqual(len(holdings), 2)
        self.assertEqual(holdings[0].ticker, "AAPL")
        self.assertEqual(holdings[0].market, "us")
        self.assertAlmostEqual(holdings[0].quantity, 0.5)
        self.assertAlmostEqual(holdings[0].avg_cost, 170.0)

    def test_india_holdings_resolves_via_isin_map_and_flags_unresolved(self):
        path = self._write_xlsx([
            ["Holdings report as on 06-07-2026", None, None, None, None],
            ["Stock Name", "ISIN", "Quantity", "Average buy price", "Buy Value"],
            ["Reliance Industries Ltd", "INE002A01018", 1, 1300.0, 1300.0],
            ["Externally Purchased holding with ISIN INE999Z99999", "INE999Z99999", 5, 0, 0],
        ])
        fake_isin_map = {"INE002A01018": "RELIANCE"}
        holdings, unresolved = BrokerReportIngestor.india_holdings_from_xlsx(path, isin_map=fake_isin_map)

        self.assertEqual(len(holdings), 2)
        self.assertEqual(holdings[0].ticker, "RELIANCE")
        self.assertEqual(holdings[0].market, "india")
        self.assertAlmostEqual(holdings[0].avg_cost, 1300.0)
        # unresolved ISIN: kept as the ticker (position not silently dropped), zero avg_cost -> None
        self.assertEqual(holdings[1].ticker, "INE999Z99999")
        self.assertIsNone(holdings[1].avg_cost)

        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["isin"], "INE999Z99999")

    def test_merge_combines_quantity_and_reaverages_cost(self):
        us = [Holding(ticker="AAPL", market="us", quantity=2, avg_cost=100.0)]
        india = [Holding(ticker="AAPL", market="us", quantity=2, avg_cost=200.0)]  # duplicate on purpose
        portfolio = BrokerReportIngestor.merge(us, india, name="test")
        self.assertEqual(len(portfolio.holdings), 1)
        merged = portfolio.holdings[0]
        self.assertEqual(merged.quantity, 4)
        self.assertAlmostEqual(merged.avg_cost, 150.0)  # (2*100 + 2*200) / 4


if __name__ == "__main__":
    unittest.main()
