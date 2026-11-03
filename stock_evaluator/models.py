"""Stock evaluation models including newsvendor inventory optimization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from . import config


class Recommendation(Enum):
    """Stock action recommendation."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class NewsvendorAnalysis:
    """Newsvendor model analysis for stock holding costs."""
    optimal_quantity: float
    holding_cost: float
    shortage_cost: float
    total_inventory_cost: float
    cost_of_underage: float
    cost_of_overage: float
    critical_ratio: float


class NewsvendorModel:
    """
    Newsvendor model for inventory optimization applied to stock holdings.

    In stock context:
    - Holding cost: opportunity cost of capital tied up (% annual)
    - Shortage cost: regret cost if stock rises without holding (% potential gain)
    - Demand: future price movement probability
    """

    def __init__(self,
                 holding_cost_rate: float = config.DEFAULT_HOLDING_COST_RATE,
                 shortage_cost_rate: float = config.DEFAULT_SHORTAGE_COST_RATE):
        """
        Initialize newsvendor model.

        Args:
            holding_cost_rate: Annual opportunity cost of holding stock (default 8%)
            shortage_cost_rate: Regret cost factor if stock rises (default 25%)
        """
        self.holding_cost_rate = holding_cost_rate
        self.shortage_cost_rate = shortage_cost_rate

    def critical_ratio(self) -> float:
        """Calculate critical ratio for optimal order quantity."""
        return self.shortage_cost_rate / (self.holding_cost_rate + self.shortage_cost_rate)

    def evaluate_holding(self,
                         stock_price: float,
                         current_quantity: int,
                         expected_price_change: float,
                         price_volatility: float = config.DEFAULT_PRICE_VOLATILITY,
                         holding_period_months: int = config.DEFAULT_HOLDING_PERIOD_MONTHS
                         ) -> NewsvendorAnalysis:
        """
        Evaluate if current holding quantity is optimal using newsvendor model.

        Args:
            stock_price: Current stock price
            current_quantity: Current quantity held
            expected_price_change: Expected price change % (e.g., 0.15 for 15%)
            price_volatility: Annual volatility (default 25%)
            holding_period_months: Holding period in months (default 3)

        Returns:
            NewsvendorAnalysis with holding cost breakdown
        """
        period_fraction = holding_period_months / 12
        period_holding_cost = self.holding_cost_rate * period_fraction
        holding_cost_per_share = stock_price * period_holding_cost
        shortage_cost_per_share = stock_price * self.shortage_cost_rate * period_fraction

        total_cost = (current_quantity * holding_cost_per_share) + \
                    (current_quantity * shortage_cost_per_share)

        underage_cost = current_quantity * shortage_cost_per_share
        overage_cost = current_quantity * holding_cost_per_share

        optimal_fraction = max(0, min(1, self.critical_ratio() + expected_price_change))
        optimal_quantity = int(current_quantity * optimal_fraction)

        return NewsvendorAnalysis(
            optimal_quantity=optimal_quantity,
            holding_cost=overage_cost,
            shortage_cost=underage_cost,
            total_inventory_cost=total_cost,
            cost_of_underage=underage_cost,
            cost_of_overage=overage_cost,
            critical_ratio=self.critical_ratio()
        )


def _score_from_return(current_return_pct: float) -> int:
    """Score unrealised return (percent): deep losses score high (contrarian), big gains score low."""
    for bound, points in config.RETURN_SCORE_BANDS:
        if current_return_pct < bound:
            return points
    return config.RETURN_SCORE_ABOVE_ALL


def _score_from_gain_potential(gain_potential_pct: float) -> int:
    """Score the estimated 3-month gain potential (percent)."""
    for bound, points in config.GAIN_SCORE_BANDS:
        if gain_potential_pct > bound:
            return points
    return config.GAIN_SCORE_NONPOSITIVE


def _score_from_cost_ratio(cost_to_gain_ratio: float) -> int:
    """Penalty for newsvendor carrying cost relative to expected gain (ratio, unitless)."""
    for bound, points in config.COST_RATIO_PENALTIES:
        if cost_to_gain_ratio > bound:
            return points
    return 0


def _classify(score: int) -> Recommendation:
    """Map a total score onto a Recommendation."""
    for bound, label in config.RECOMMENDATION_THRESHOLDS:
        if score >= bound:
            return Recommendation(label)
    return Recommendation.STRONG_SELL


class StockEvaluator:
    """Comprehensive stock evaluation engine."""

    def __init__(self,
                 risk_free_rate: float = config.DEFAULT_RISK_FREE_RATE,
                 market_return: float = config.DEFAULT_MARKET_RETURN):
        """
        Initialize evaluator.

        Args:
            risk_free_rate: Risk-free rate for CAPM (default 6%)
            market_return: Expected market return (default 12%)
        """
        self.risk_free_rate = risk_free_rate
        self.market_return = market_return
        self.newsvendor = NewsvendorModel()

    def calculate_expected_return(self,
                                   current_price: float,
                                   purchase_price: float,
                                   days_held: int) -> float:
        """Calculate annualized return on investment."""
        if purchase_price <= 0:
            return 0
        return_pct = (current_price - purchase_price) / purchase_price
        years = max(days_held / 365, 0.01)
        return return_pct / years

    def estimate_3month_gain_potential(self,
                                        sector: str,
                                        current_return_pct: float,
                                        beta: float = 1.0) -> float:
        """
        Estimate potential 3-month gain using sector momentum and fundamental factors.

        Args:
            sector: Stock sector
            current_return_pct: Current unrealized return %
            beta: Stock beta relative to market (default 1.0)

        Returns:
            Estimated 3-month gain percentage
        """
        momentum_boost = 0
        if current_return_pct < config.MOMENTUM_DEEP_LOSS[0]:
            momentum_boost = config.MOMENTUM_DEEP_LOSS[1]
        elif current_return_pct < config.MOMENTUM_MILD_LOSS[0]:
            momentum_boost = config.MOMENTUM_MILD_LOSS[1]
        elif current_return_pct > config.MOMENTUM_OVERHEATED[0]:
            momentum_boost = config.MOMENTUM_OVERHEATED[1]

        sector_boost = config.SECTOR_GAIN_FACTORS.get(sector, config.DEFAULT_SECTOR_BOOST)
        beta_adjusted = config.MARKET_QUARTERLY_RETURN * beta

        return config.BASE_QUARTERLY_GAIN + momentum_boost + sector_boost + beta_adjusted

    def recommend(self,
                  symbol: str,
                  current_price: float,
                  purchase_price: float,
                  quantity: int,
                  sector: str = config.DEFAULT_SECTOR,
                  days_held: int = config.ASSUMED_DAYS_HELD,
                  beta: float = config.DEFAULT_BETA) -> Tuple[Recommendation, dict]:
        """
        Generate buy/hold/sell recommendation using multiple factors.

        Returns:
            (Recommendation, analysis_dict)
        """
        analysis: Dict[str, float] = {}

        current_return = (current_price - purchase_price) / purchase_price
        current_return_pct = current_return * 100
        annualized_return = self.calculate_expected_return(
            current_price, purchase_price, days_held
        )

        gain_potential = self.estimate_3month_gain_potential(
            sector, current_return_pct, beta
        )
        gain_potential_pct = gain_potential * 100

        nv_analysis = self.newsvendor.evaluate_holding(
            current_price, quantity, gain_potential
        )

        analysis.update({
            'current_price': current_price,
            'purchase_price': purchase_price,
            'current_return_pct': current_return_pct,
            'annualized_return_pct': annualized_return * 100,
            'gain_potential_3m_pct': gain_potential_pct,
            'holding_cost': nv_analysis.holding_cost,
            'shortage_cost': nv_analysis.shortage_cost,
            'total_inventory_cost': nv_analysis.total_inventory_cost,
            'optimal_quantity': nv_analysis.optimal_quantity,
        })

        score = _score_from_return(current_return_pct) + _score_from_gain_potential(gain_potential_pct)

        if nv_analysis.total_inventory_cost > 0:
            cost_to_gain_ratio = nv_analysis.total_inventory_cost / max(
                quantity * current_price * gain_potential, 1
            )
            score += _score_from_cost_ratio(cost_to_gain_ratio)

        analysis['recommendation_score'] = score

        return _classify(score), analysis
