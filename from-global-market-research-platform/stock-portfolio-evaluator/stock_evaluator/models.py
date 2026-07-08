"""NewsvendorModel — stop-loss/target-band sizing borrowed from the newsvendor
inventory problem, and StockEvaluator, which applies it to one ticker's price history.

Newsvendor mapping
-------------------
The classic newsvendor problem picks an order quantity balancing:
  Cu = underage cost  (profit lost by under-ordering / exiting a position too early)
  Co = overage cost   (loss incurred by over-ordering / holding a losing position too long)
Its optimal quantile is the critical fractile CF = Cu / (Cu + Co).

Here Cu is the caller's reward:risk appetite (`reward_risk_ratio`, default 2.0 — i.e.
"I want to let winners run about 2x as far as I'm willing to let losers run") and
Co is a normalizing risk unit (`overage_cost`, default 1.0). Those two costs directly
scale the stop-loss/target distances from an *anchor price* — the position's entry
cost when known, otherwise the price `horizon_days` ago — in units of the stock's own
historical volatility (its "demand uncertainty"):

    target_price    = anchor * exp(mu_h + Cu * sigma_h)
    stop_loss_price = anchor * exp(mu_h - Co * sigma_h)

where mu_h/sigma_h are the mean/stdev of log returns projected over the holding horizon.
The band is deliberately anchored away from the live price being evaluated — anchoring
a band to the same price it's tested against would make it tautologically un-breachable.
CF is also reported as an interpretability metric alongside the resulting band.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

try:
    from scipy.stats import norm
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@dataclass
class Band:
    anchor_price: float
    target_price: float
    stop_loss_price: float
    critical_fractile: float
    horizon_days: int
    mu_daily: float
    sigma_daily: float
    prob_target_before_stop: Optional[float] = None


class NewsvendorModel:
    def __init__(self, reward_risk_ratio: float = 2.0, overage_cost: float = 1.0,
                 horizon_days: int = 20, min_history: int = 30):
        if reward_risk_ratio <= 0 or overage_cost <= 0:
            raise ValueError("reward_risk_ratio and overage_cost must be positive")
        self.cu = reward_risk_ratio
        self.co = overage_cost
        self.horizon_days = horizon_days
        self.min_history = min_history
        self.mu_: Optional[float] = None
        self.sigma_: Optional[float] = None

    @property
    def critical_fractile(self) -> float:
        return self.cu / (self.cu + self.co)

    def fit(self, closes: pd.Series) -> "NewsvendorModel":
        closes = closes.dropna()
        if len(closes) < self.min_history:
            raise ValueError(
                f"Need at least {self.min_history} price points to fit, got {len(closes)}"
            )
        log_returns = np.log(closes / closes.shift(1)).dropna()
        self.mu_ = float(log_returns.mean())
        self.sigma_ = float(log_returns.std(ddof=1))
        return self

    def band(self, anchor_price: float, horizon_days: Optional[int] = None) -> Band:
        """Compute the stop/target band relative to anchor_price (entry cost, or a
        past price) — NOT the live price you intend to compare it against."""
        if self.mu_ is None or self.sigma_ is None:
            raise RuntimeError("Call fit() before band()")
        h = horizon_days or self.horizon_days
        mu_h = self.mu_ * h
        sigma_h = self.sigma_ * (h ** 0.5)

        target_return = mu_h + self.cu * sigma_h
        stop_return = mu_h - self.co * sigma_h

        target_price = anchor_price * float(np.exp(target_return))
        stop_loss_price = anchor_price * float(np.exp(stop_return))

        prob = None
        if HAS_SCIPY and sigma_h > 0:
            # crude but informative: prob of finishing above target vs below stop
            # at the *horizon* under the fitted normal-return assumption.
            p_above_target = 1 - norm.cdf((target_return - mu_h) / sigma_h)
            p_below_stop = norm.cdf((stop_return - mu_h) / sigma_h)
            denom = p_above_target + p_below_stop
            prob = p_above_target / denom if denom > 0 else None

        return Band(
            anchor_price=anchor_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            critical_fractile=self.critical_fractile,
            horizon_days=h,
            mu_daily=self.mu_,
            sigma_daily=self.sigma_,
            prob_target_before_stop=prob,
        )


@dataclass
class EvaluationResult:
    ticker: str
    market: str
    cmp: Optional[float]
    band: Optional[Band]
    avg_cost: Optional[float]
    unrealized_pnl_pct: Optional[float]
    signal: str
    reason: str


class StockEvaluator:
    """Fetches a ticker's data via a data_source and scores it against a NewsvendorModel band."""

    def __init__(self, data_source, model_kwargs: Optional[dict] = None):
        self.data_source = data_source
        self.model_kwargs = model_kwargs or {}

    def evaluate(self, ticker: str, market: Optional[str] = None,
                 avg_cost: Optional[float] = None) -> EvaluationResult:
        from .ingest import market_from_ticker
        market = market or market_from_ticker(ticker)

        quote = self.data_source.get_quote(ticker, market)
        cmp_ = quote.get("cmp")

        history = self.data_source.get_price_history(ticker, market)
        band: Optional[Band] = None
        signal, reason = "NO_DATA", "insufficient data to evaluate"

        if cmp_ is None and not history.empty:
            cmp_ = float(history["close"].iloc[-1])

        if cmp_ is not None and not history.empty:
            try:
                model = NewsvendorModel(**self.model_kwargs)
                closes = history["close"]
                model.fit(closes)
                horizon = self.model_kwargs.get("horizon_days", model.horizon_days)
                if avg_cost:
                    anchor_price = avg_cost
                elif len(closes) > horizon:
                    anchor_price = float(closes.iloc[-(horizon + 1)])
                else:
                    anchor_price = float(closes.iloc[0])
                band = model.band(anchor_price, horizon_days=horizon)
                if cmp_ <= band.stop_loss_price:
                    signal, reason = "EXIT", "price at or below newsvendor stop-loss band"
                elif cmp_ >= band.target_price:
                    signal, reason = "TRIM", "price at or above newsvendor target band"
                else:
                    signal, reason = "HOLD", "price within stop/target band"
            except ValueError as exc:
                signal, reason = "NO_DATA", str(exc)
        elif cmp_ is not None:
            signal, reason = "NO_DATA", "no price history available to fit band"

        unrealized_pnl_pct = None
        if cmp_ is not None and avg_cost:
            unrealized_pnl_pct = (cmp_ - avg_cost) / avg_cost * 100

        return EvaluationResult(
            ticker=ticker, market=market, cmp=cmp_, band=band,
            avg_cost=avg_cost, unrealized_pnl_pct=unrealized_pnl_pct,
            signal=signal, reason=reason,
        )
