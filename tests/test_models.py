"""Characterisation tests for scoring helpers and the newsvendor model."""

import pytest

from stock_evaluator.models import (
    NewsvendorModel,
    Recommendation,
    StockEvaluator,
    _classify,
    _score_from_cost_ratio,
    _score_from_gain_potential,
    _score_from_return,
)


@pytest.mark.parametrize("ret,pts", [
    (-31, 25), (-30, 15), (-11, 15), (-10, 5), (-6, 5), (-5, 0), (-0.1, 0),
    (0, -5), (9.9, -5), (10, -10), (29.9, -10), (30, -25), (100, -25),
])
def test_score_from_return_bands(ret, pts):
    assert _score_from_return(ret) == pts


@pytest.mark.parametrize("gain,pts", [
    (16, 25), (15, 15), (11, 15), (10, 5), (6, 5), (5, 0), (0.1, 0), (0, -10), (-3, -10),
])
def test_score_from_gain_bands(gain, pts):
    assert _score_from_gain_potential(gain) == pts


@pytest.mark.parametrize("ratio,pts", [(0.31, -15), (0.3, -5), (0.16, -5), (0.15, 0), (0.0, 0)])
def test_score_from_cost_ratio(ratio, pts):
    assert _score_from_cost_ratio(ratio) == pts


@pytest.mark.parametrize("score,rec", [
    (50, Recommendation.STRONG_BUY), (30, Recommendation.STRONG_BUY), (29, Recommendation.BUY),
    (15, Recommendation.BUY), (14, Recommendation.HOLD), (-15, Recommendation.HOLD),
    (-16, Recommendation.SELL), (-30, Recommendation.SELL), (-31, Recommendation.STRONG_SELL),
])
def test_classify_thresholds(score, rec):
    assert _classify(score) is rec


def test_critical_ratio_default():
    assert NewsvendorModel().critical_ratio() == pytest.approx(0.25 / 0.33)


def test_evaluate_holding_quarter():
    a = NewsvendorModel().evaluate_holding(100.0, 10, 0.1)
    assert a.cost_of_overage == pytest.approx(10 * 100 * 0.08 * 0.25)
    assert a.cost_of_underage == pytest.approx(10 * 100 * 0.25 * 0.25)
    assert a.total_inventory_cost == pytest.approx(a.cost_of_overage + a.cost_of_underage)
    assert a.optimal_quantity == 8  # int(10 * min(1, 0.7576 + 0.1))


def test_gain_potential_known_sector_and_momentum():
    ev = StockEvaluator()
    # base .03 + deep-loss .08 + Energy .04 + beta 1.1*.03
    assert ev.estimate_3month_gain_potential("Energy", -40, 1.1) == pytest.approx(0.183)
    # overheated: -.05; unknown sector default .02
    assert ev.estimate_3month_gain_potential("Nope", 25, 1.0) == pytest.approx(0.03 - 0.05 + 0.02 + 0.03)


def test_expected_return_guards():
    ev = StockEvaluator()
    assert ev.calculate_expected_return(10, 0, 365) == 0
    assert ev.calculate_expected_return(120, 100, 365) == pytest.approx(0.2)


def test_recommend_deep_loss_is_strong_buy():
    rec, analysis = StockEvaluator().recommend("X", 60, 100, 7, sector="Weird")
    assert rec is Recommendation.STRONG_BUY
    assert analysis["recommendation_score"] == 35
    assert analysis["gain_potential_3m_pct"] == pytest.approx(16.0)
