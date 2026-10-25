"""Tests for stock_evaluator.models (NewsvendorModel, StockEvaluator)."""

import math
import unittest
from statistics import NormalDist

from stock_evaluator.models import NewsvendorModel, Recommendation, StockEvaluator


class TestNewsvendorCriticalRatio(unittest.TestCase):

    def test_default_critical_ratio_is_cu_over_cu_plus_co(self):
        # README: "Critical Ratio: 76% threshold" -> 0.25 / (0.25 + 0.08)
        self.assertAlmostEqual(NewsvendorModel().critical_ratio(), 0.25 / 0.33)
        self.assertAlmostEqual(round(NewsvendorModel().critical_ratio(), 2), 0.76)

    def test_equal_costs_give_one_half(self):
        self.assertAlmostEqual(NewsvendorModel(0.1, 0.1).critical_ratio(), 0.5)


class TestNewsvendorCosts(unittest.TestCase):

    def test_cost_terms_hand_computed(self):
        # price 100, 10 shares, 3 months: holding 8%*0.25 = 2/share, shortage 25%*0.25 = 6.25/share
        nv = NewsvendorModel().evaluate_holding(100.0, 10, 0.0, holding_period_months=3)
        self.assertAlmostEqual(nv.holding_cost, 20.0)
        self.assertAlmostEqual(nv.shortage_cost, 62.5)
        self.assertAlmostEqual(nv.total_inventory_cost, 82.5)
        self.assertAlmostEqual(nv.cost_of_overage, 20.0)
        self.assertAlmostEqual(nv.cost_of_underage, 62.5)

    def test_zero_quantity_gives_zero_costs_and_zero_optimal(self):
        nv = NewsvendorModel().evaluate_holding(100.0, 0, 0.05)
        self.assertEqual(nv.total_inventory_cost, 0)
        self.assertEqual(nv.optimal_quantity, 0)


class TestNewsvendorCriticalFractile(unittest.TestCase):
    """The newsvendor optimum is the demand quantile F^-1(Cu/(Cu+Co)), so it must move with the
    spread of the demand distribution (here: price volatility) whenever CR != 0.5."""

    def test_optimal_quantity_depends_on_volatility(self):
        m = NewsvendorModel()  # CR ~ 0.76 > 0.5
        low = m.evaluate_holding(100.0, 1000, -0.20, price_volatility=0.10)
        high = m.evaluate_holding(100.0, 1000, -0.20, price_volatility=0.50)
        self.assertNotEqual(low.optimal_quantity, high.optimal_quantity)
        # CR > 0.5 -> z > 0 -> more volatility raises the optimal quantity
        self.assertGreater(high.optimal_quantity, low.optimal_quantity)

    def test_optimal_quantity_is_normal_critical_fractile(self):
        # demand (as a multiple of the current position) ~ N(1 + mu, sigma * sqrt(months/12))
        m = NewsvendorModel()
        mu, vol, months, q0 = -0.20, 0.25, 3, 1000
        sigma_h = vol * math.sqrt(months / 12)
        z = NormalDist().inv_cdf(m.critical_ratio())
        expected = int(q0 * min(1.0, max(0.0, 1 + mu + z * sigma_h)))
        nv = m.evaluate_holding(100.0, q0, mu, price_volatility=vol, holding_period_months=months)
        self.assertEqual(nv.optimal_quantity, expected)

    def test_symmetric_costs_optimum_is_the_mean(self):
        # CR = 0.5 -> z = 0 -> Q* = mean demand, independent of volatility
        m = NewsvendorModel(0.1, 0.1)
        nv = m.evaluate_holding(100.0, 1000, -0.30, price_volatility=0.9)
        self.assertEqual(nv.optimal_quantity, 700)

    def test_optimal_never_negative(self):
        nv = NewsvendorModel().evaluate_holding(100.0, 1000, -2.0, price_volatility=0.1)
        self.assertEqual(nv.optimal_quantity, 0)


class TestStockEvaluator(unittest.TestCase):

    def setUp(self):
        self.ev = StockEvaluator()

    def test_annualized_return(self):
        # +10% over half a year -> 20% annualised (simple)
        self.assertAlmostEqual(self.ev.calculate_expected_return(110, 100, 182.5), 0.2)

    def test_annualized_return_zero_purchase_price(self):
        self.assertEqual(self.ev.calculate_expected_return(110, 0, 100), 0)

    def test_gain_potential_hand_computed(self):
        # base 3% + loser boost 8% + Technology 6% + beta 1.2 * 3% = 20.6%
        self.assertAlmostEqual(self.ev.estimate_3month_gain_potential("Technology", -15, 1.2), 0.206)
        # winner > 20%: 3% - 5% + unknown-sector 2% + 3% = 3%
        self.assertAlmostEqual(self.ev.estimate_3month_gain_potential("Unknown", 25, 1.0), 0.03)

    def test_recommend_deep_loser_is_strong_buy(self):
        rec, a = self.ev.recommend("X", 60, 100, 10, sector="Technology", beta=1.2)
        self.assertEqual(rec, Recommendation.STRONG_BUY)
        self.assertAlmostEqual(a["current_return_pct"], -40.0)

    def test_recommend_big_winner_low_potential_is_sell_side(self):
        rec, a = self.ev.recommend("X", 200, 100, 10, sector="Utilities", beta=0.7)
        self.assertIn(rec, (Recommendation.SELL, Recommendation.STRONG_SELL))

    def test_recommend_flat_is_hold(self):
        rec, _ = self.ev.recommend("X", 100, 100, 10, sector="Financials", beta=0.9)
        self.assertEqual(rec, Recommendation.HOLD)


if __name__ == "__main__":
    unittest.main()
