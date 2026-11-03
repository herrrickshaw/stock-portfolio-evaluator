"""Tunable constants for the evaluator (rates, sector tables, scoring thresholds)."""

from __future__ import annotations

from typing import Dict, Tuple

# --- Newsvendor model -------------------------------------------------------
DEFAULT_HOLDING_COST_RATE = 0.08    # annual opportunity cost of capital (fraction)
DEFAULT_SHORTAGE_COST_RATE = 0.25   # regret factor if the stock rises un-held (fraction)
DEFAULT_PRICE_VOLATILITY = 0.25     # annual volatility (fraction); accepted but unused
DEFAULT_HOLDING_PERIOD_MONTHS = 3

# --- StockEvaluator ---------------------------------------------------------
DEFAULT_RISK_FREE_RATE = 0.06
DEFAULT_MARKET_RETURN = 0.12
BASE_QUARTERLY_GAIN = 0.03
MARKET_QUARTERLY_RETURN = 0.03
DEFAULT_SECTOR_BOOST = 0.02
DEFAULT_SECTOR = "Technology"

# (upper bound exclusive, momentum boost) for current_return_pct below zero.
MOMENTUM_DEEP_LOSS = (-10, 0.08)
MOMENTUM_MILD_LOSS = (-5, 0.05)
MOMENTUM_OVERHEATED = (20, -0.05)   # boost applied when return_pct > threshold

SECTOR_GAIN_FACTORS: Dict[str, float] = {
    "Energy": 0.04,
    "Financials": 0.02,
    "Technology": 0.06,
    "Healthcare": 0.03,
    "Utilities": 0.01,
    "Industrials": 0.03,
    "Renewable": 0.05,
}

SECTOR_BETA: Dict[str, float] = {
    "Energy": 1.1, "Technology": 1.2, "Financials": 0.9,
    "Healthcare": 0.8, "Utilities": 0.7, "Industrials": 1.0,
    "Automobile": 1.1, "Materials": 1.0, "Retail": 1.0,
    "Consumer": 0.9,
}
DEFAULT_BETA = 1.0
ASSUMED_DAYS_HELD = 365  # purchase dates are not used; every holding is treated as 1 year old

# Score bands, checked in order: (return_pct < bound -> points).
RETURN_SCORE_BANDS: Tuple[Tuple[float, int], ...] = (
    (-30, 25), (-10, 15), (-5, 5), (0, 0), (10, -5), (30, -10),
)
RETURN_SCORE_ABOVE_ALL = -25
# Gain-potential bands, checked in order: (gain_pct > bound -> points).
GAIN_SCORE_BANDS: Tuple[Tuple[float, int], ...] = ((15, 25), (10, 15), (5, 5), (0, 0))
GAIN_SCORE_NONPOSITIVE = -10
# Cost-to-gain ratio penalties, checked in order: (ratio > bound -> points).
COST_RATIO_PENALTIES: Tuple[Tuple[float, int], ...] = ((0.3, -15), (0.15, -5))

# Recommendation thresholds on the total score: (score >= bound -> label).
RECOMMENDATION_THRESHOLDS: Tuple[Tuple[int, str], ...] = (
    (30, "STRONG_BUY"), (15, "BUY"), (-15, "HOLD"), (-30, "SELL"),
)

# --- PortfolioEvaluator -----------------------------------------------------
# Substring match against the upper-cased symbol; first hit in insertion order wins.
SYMBOL_SECTOR_MAP: Dict[str, str] = {
    'TCS': 'Technology', 'INFY': 'Technology', 'WIPRO': 'Technology',
    'HDFC': 'Financials', 'ICICI': 'Financials', 'AXIS': 'Financials',
    'RELIANCE': 'Energy', 'VEDANTA': 'Energy', 'ADANIPOWER': 'Energy',
    'BHARTIARTL': 'Technology', 'TITAN': 'Consumer', 'LT': 'Industrials',
    'MARUTI': 'Automobile', 'TATASTEEL': 'Materials', 'JSWSTEEL': 'Materials',
    'DEEPAKFERT': 'Chemicals', 'BAJAJFINSV': 'Financials',
    'ONGC': 'Energy', 'NTPC': 'Energy', 'JSWENERGY': 'Energy',
    'SUNPHARMA': 'Healthcare', 'DMART': 'Retail',
    'BAJAJ': 'Automobile', 'HDFCBANK': 'Financials',
    'HDFCLIFE': 'Financials', 'SBILIFE': 'Financials',
    'GLENMARK': 'Healthcare', 'COALINDIA': 'Materials',
    'POWERGRID': 'Utilities', 'GAIL': 'Energy',
    'TECHM': 'Technology', 'MINDTREE': 'Technology',
    'LIC': 'Financials', 'IRCTC': 'Transport', 'NATIONALUM': 'Materials',
}
