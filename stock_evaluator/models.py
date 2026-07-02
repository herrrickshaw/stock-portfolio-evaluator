"""Stock evaluation models including newsvendor inventory optimization."""

import numpy as np
from dataclasses import dataclass
from typing import Tuple
from enum import Enum


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
                 holding_cost_rate: float = 0.08,
                 shortage_cost_rate: float = 0.25):
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
                         price_volatility: float = 0.25,
                         holding_period_months: int = 3) -> NewsvendorAnalysis:
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


class StockEvaluator:
    """Comprehensive stock evaluation engine."""

    def __init__(self,
                 risk_free_rate: float = 0.06,
                 market_return: float = 0.12):
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
        base_quarterly = 0.03

        momentum_boost = 0
        if current_return_pct < -10:
            momentum_boost = 0.08
        elif current_return_pct < -5:
            momentum_boost = 0.05
        elif current_return_pct > 20:
            momentum_boost = -0.05

        sector_factors = {
            'Energy': 0.04,
            'Financials': 0.02,
            'Technology': 0.06,
            'Healthcare': 0.03,
            'Utilities': 0.01,
            'Industrials': 0.03,
            'Renewable': 0.05,
        }
        sector_boost = sector_factors.get(sector, 0.02)

        market_quarterly = 0.03
        beta_adjusted = market_quarterly * beta

        total_estimate = base_quarterly + momentum_boost + sector_boost + beta_adjusted
        return total_estimate

    def recommend(self,
                  symbol: str,
                  current_price: float,
                  purchase_price: float,
                  quantity: int,
                  sector: str = "Technology",
                  days_held: int = 365,
                  beta: float = 1.0) -> Tuple[Recommendation, dict]:
        """
        Generate buy/hold/sell recommendation using multiple factors.

        Returns:
            (Recommendation, analysis_dict)
        """
        analysis = {}

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

        score = 0

        if current_return_pct < -30:
            score += 25
        elif current_return_pct < -10:
            score += 15
        elif current_return_pct < -5:
            score += 5
        elif current_return_pct < 0:
            score += 0
        elif current_return_pct < 10:
            score -= 5
        elif current_return_pct < 30:
            score -= 10
        else:
            score -= 25

        if gain_potential_pct > 15:
            score += 25
        elif gain_potential_pct > 10:
            score += 15
        elif gain_potential_pct > 5:
            score += 5
        elif gain_potential_pct > 0:
            score += 0
        else:
            score -= 10

        if nv_analysis.total_inventory_cost > 0:
            cost_to_gain_ratio = nv_analysis.total_inventory_cost / max(
                quantity * current_price * gain_potential, 1
            )
            if cost_to_gain_ratio > 0.3:
                score -= 15
            elif cost_to_gain_ratio > 0.15:
                score -= 5

        if score >= 30:
            recommendation = Recommendation.STRONG_BUY
        elif score >= 15:
            recommendation = Recommendation.BUY
        elif score >= -15:
            recommendation = Recommendation.HOLD
        elif score >= -30:
            recommendation = Recommendation.SELL
        else:
            recommendation = Recommendation.STRONG_SELL

        analysis['recommendation_score'] = score

        return recommendation, analysis
