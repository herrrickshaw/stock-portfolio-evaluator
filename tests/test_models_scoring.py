"""Score bands and recommendation thresholds of StockEvaluator.recommend (hand-computed)."""

import pytest

from stock_evaluator.models import NewsvendorModel, Recommendation, StockEvaluator

R = Recommendation


def rec(price, sector="Unknown", beta=1.0, qty=10, purchase=100.0):
    return StockEvaluator().recommend("X", price, purchase, qty, sector=sector, beta=beta)


# (price vs purchase 100, sector, beta, expected score, expected recommendation)
# score = return band + gain-potential band + cost penalty; derivations in the comments.
CASES = [
    # -40% (+25); gain 3+8+6+3.6=20.6% (+25); cost ratio .0825/.206 > .3 (-15)
    (60, "Technology", 1.2, 35, R.STRONG_BUY),
    # -20% (+15); gain 3+8+2+3=16% (+25); -15
    (80, "Unknown", 1.0, 25, R.BUY),
    # -8% (+5); gain 3+5+2+2.7=12.7% (+15); -15
    (92, "Financials", 0.9, 5, R.HOLD),
    # -3% (0); gain 6.1% (+5); -15
    (97, "Utilities", 0.7, -10, R.HOLD),
    # +5% (-5); gain 6.1% (+5); -15  -> exactly -15 is still HOLD
    (105, "Utilities", 0.7, -15, R.HOLD),
    # +25% (-10); gain 3-5+1+2.1=1.1% (0); -15
    (125, "Utilities", 0.7, -25, R.SELL),
    # +100% (-25); gain 1.1% (0); -15
    (200, "Utilities", 0.7, -40, R.STRONG_SELL),
    # +5% (-5); gain -2% (-10); -15  -> exactly -30 is still SELL
    (105, "Utilities", -2.0, -30, R.SELL),
    # +25% (-10); gain 3-5+1-6=-7% (-10); -15
    (125, "Utilities", -2.0, -35, R.STRONG_SELL),
    # 0% (-5); gain 3+4+30=37% (+25); ratio .223 -> -5  -> exactly 15 is BUY
    (100, "Energy", 10.0, 15, R.BUY),
    # 0% (-5); gain 97% (+25); ratio .085 -> 0
    (100, "Energy", 30.0, 20, R.BUY),
    # -7% (+5); gain 3+5+4+90=102% (+25); ratio .08 -> 0  -> exactly 30 is STRONG_BUY
    (93, "Energy", 30.0, 30, R.STRONG_BUY),
]


@pytest.mark.parametrize("price,sector,beta,score,expected", CASES)
def test_score_and_recommendation(price, sector, beta, score, expected):
    r, a = rec(price, sector, beta)
    assert a["recommendation_score"] == score
    assert r == expected


# Each return band with Unknown sector, beta 1 (momentum changes the gain band too):
# score = return band + gain band - 15
BANDS = [
    (-35, 35), (-30, 25), (-15, 25), (-10, 5), (-7, 5), (-5, -10), (-2, -10),
    (0, -15), (5, -15), (10, -20), (20, -20), (25, -25), (30, -40), (40, -40),
]


@pytest.mark.parametrize("ret,score", BANDS)
def test_return_bands(ret, score):
    _, a = rec(100 + ret)
    assert a["recommendation_score"] == score


def test_zero_quantity_has_no_cost_penalty():
    # 0%: -5; gain 7% (+5); no inventory cost -> no penalty
    r, a = rec(100, "Utilities", 1.0, qty=0)
    assert a["recommendation_score"] == 0
    assert a["total_inventory_cost"] == 0
    assert r == R.HOLD


def test_analysis_fields():
    r, a = rec(60, "Technology", 1.2)
    assert a["current_price"] == 60
    assert a["purchase_price"] == 100
    assert a["current_return_pct"] == pytest.approx(-40.0)
    assert a["annualized_return_pct"] == pytest.approx(-40.0)
    assert a["gain_potential_3m_pct"] == pytest.approx(20.6)
    # 10 shares * 60 * 3 months: holding 8%/4, shortage 25%/4
    assert a["holding_cost"] == pytest.approx(10 * 60 * 0.02)
    assert a["shortage_cost"] == pytest.approx(10 * 60 * 0.0625)
    assert a["total_inventory_cost"] == pytest.approx(10 * 60 * 0.0825)
    assert isinstance(a["optimal_quantity"], int)


def test_annualized_return_uses_days_held():
    _, a = StockEvaluator().recommend("X", 110, 100, 1, days_held=730)
    assert a["annualized_return_pct"] == pytest.approx(5.0)


def test_gain_potential_momentum_bands():
    ev = StockEvaluator()
    g = lambda r: ev.estimate_3month_gain_potential("Unknown", r, 1.0)  # noqa: E731
    assert g(-10.0001) == pytest.approx(0.16)
    assert g(-10) == pytest.approx(0.13)
    assert g(-5.0001) == pytest.approx(0.13)
    assert g(-5) == pytest.approx(0.08)
    assert g(0) == pytest.approx(0.08)
    assert g(20) == pytest.approx(0.08)
    assert g(20.0001) == pytest.approx(0.03)


@pytest.mark.parametrize("sector,boost", [
    ("Energy", .04), ("Financials", .02), ("Technology", .06), ("Healthcare", .03),
    ("Utilities", .01), ("Industrials", .03), ("Renewable", .05), ("Mystery", .02),
])
def test_sector_boosts(sector, boost):
    assert StockEvaluator().estimate_3month_gain_potential(sector, 0, 1.0) == pytest.approx(0.03 + boost + 0.03)


def test_beta_scales_market_component():
    ev = StockEvaluator()
    a = ev.estimate_3month_gain_potential("Unknown", 0, 0.0)
    b = ev.estimate_3month_gain_potential("Unknown", 0, 2.0)
    assert b - a == pytest.approx(0.06)
    # default beta is 1.0
    assert ev.estimate_3month_gain_potential("Unknown", 0) == pytest.approx(0.08)


def test_expected_return_floor_on_years():
    # days_held 0 is floored at 0.01 years
    assert StockEvaluator().calculate_expected_return(110, 100, 0) == pytest.approx(0.1 / 0.01)
    assert StockEvaluator().calculate_expected_return(110, -5, 10) == 0


def test_defaults_and_custom_rates():
    ev = StockEvaluator()
    assert (ev.risk_free_rate, ev.market_return) == (0.06, 0.12)
    nv = NewsvendorModel()
    assert (nv.holding_cost_rate, nv.shortage_cost_rate) == (0.08, 0.25)
    assert NewsvendorModel(0.5, 0.5).critical_ratio() == 0.5


def test_optimal_quantity_clamped_to_current_holding():
    nv = NewsvendorModel().evaluate_holding(100.0, 1000, 3.0, price_volatility=0.9)
    assert nv.optimal_quantity == 1000


def test_holding_period_scales_costs():
    one = NewsvendorModel().evaluate_holding(100.0, 10, 0.0, holding_period_months=12)
    assert one.holding_cost == pytest.approx(10 * 100 * 0.08)
    assert one.shortage_cost == pytest.approx(10 * 100 * 0.25)
