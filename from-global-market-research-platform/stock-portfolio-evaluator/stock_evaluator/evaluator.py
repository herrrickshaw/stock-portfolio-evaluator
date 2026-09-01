"""PortfolioEvaluator — runs a full rebalance check across a Portfolio.

Combines two independent signals per holding:
  1. Newsvendor stop/target band (StockEvaluator) — is this specific stock's
     price outside the band the model thinks it should trade in?
  2. Weight drift — has this holding's share of the portfolio moved too far
     from its target weight (equal-split by default, or explicit per-holding
     target_weight)?

The stronger signal wins when the two disagree (EXIT beats everything; a
target-band TRIM beats a drift-only TRIM/ADD).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional

from .ingest import CompositeDataSource
from .models import StockEvaluator, EvaluationResult
from .portfolio import Portfolio

_ACTION_PRIORITY = {"EXIT": 4, "TRIM": 3, "ADD": 2, "HOLD": 1, "NO_DATA": 0}


@dataclass
class HoldingReport:
    ticker: str
    market: str
    cmp: Optional[float]
    quantity: float
    current_weight: float
    target_weight: float
    weight_drift: float
    band_signal: str
    band_reason: str
    stop_loss_price: Optional[float]
    target_price: Optional[float]
    unrealized_pnl_pct: Optional[float]
    action: str
    action_reason: str


@dataclass
class RebalanceReport:
    portfolio_name: str
    total_value: float
    drift_threshold: float
    holdings: list[HoldingReport]

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for h in self.holdings:
            counts[h.action] = counts.get(h.action, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "portfolio_name": self.portfolio_name,
            "total_value": self.total_value,
            "drift_threshold": self.drift_threshold,
            "summary": self.summary(),
            "holdings": [asdict(h) for h in self.holdings],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        lines = [
            f"# Rebalance report — {self.portfolio_name}",
            "",
            f"Total value: {self.total_value:,.2f} | Drift threshold: {self.drift_threshold:.1%}",
            "",
            "| Ticker | CMP | Weight | Target | Drift | Band signal | Action | Reason |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for h in self.holdings:
            cmp_str = f"{h.cmp:.2f}" if h.cmp is not None else "-"
            lines.append(
                f"| {h.ticker} | {cmp_str} | {h.current_weight:.1%} | {h.target_weight:.1%} "
                f"| {h.weight_drift:+.1%} | {h.band_signal} | **{h.action}** | {h.action_reason} |"
            )
        counts = self.summary()
        lines += ["", "**Summary:** " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
        return "\n".join(lines)


class PortfolioEvaluator:
    def __init__(self, portfolio: Portfolio, data_source: Optional[CompositeDataSource] = None,
                 model_kwargs: Optional[dict] = None, drift_threshold: float = 0.05):
        self.portfolio = portfolio
        self.data_source = data_source or CompositeDataSource()
        self.stock_evaluator = StockEvaluator(self.data_source, model_kwargs=model_kwargs)
        self.drift_threshold = drift_threshold

    def _decide_action(self, eval_result: EvaluationResult, drift: float) -> tuple[str, str]:
        band_action = eval_result.signal if eval_result.signal in _ACTION_PRIORITY else "NO_DATA"

        drift_action, drift_reason = "HOLD", "within target weight band"
        if drift > self.drift_threshold:
            drift_action, drift_reason = "TRIM", f"overweight by {drift:+.1%} vs target"
        elif drift < -self.drift_threshold:
            drift_action, drift_reason = "ADD", f"underweight by {drift:+.1%} vs target"

        if _ACTION_PRIORITY[band_action] >= _ACTION_PRIORITY[drift_action]:
            if band_action == "HOLD" and drift_action != "HOLD":
                return drift_action, drift_reason
            return band_action, eval_result.reason
        return drift_action, drift_reason

    def run(self) -> RebalanceReport:
        price_map = {}
        evals: dict[str, EvaluationResult] = {}
        for h in self.portfolio.holdings:
            result = self.stock_evaluator.evaluate(h.ticker, h.market, avg_cost=h.avg_cost)
            evals[h.ticker] = result
            if result.cmp is not None:
                price_map[h.ticker] = result.cmp

        current_weights = self.portfolio.weights(price_map)
        target_weights = self.portfolio.target_weights()
        total_value = self.portfolio.total_value(price_map)

        reports = []
        for h in self.portfolio.holdings:
            result = evals[h.ticker]
            cw = current_weights.get(h.ticker, 0.0)
            tw = target_weights.get(h.ticker, 0.0)
            drift = cw - tw
            action, action_reason = self._decide_action(result, drift)
            reports.append(HoldingReport(
                ticker=h.ticker, market=h.market, cmp=result.cmp, quantity=h.quantity,
                current_weight=cw, target_weight=tw, weight_drift=drift,
                band_signal=result.signal, band_reason=result.reason,
                stop_loss_price=result.band.stop_loss_price if result.band else None,
                target_price=result.band.target_price if result.band else None,
                unrealized_pnl_pct=result.unrealized_pnl_pct,
                action=action, action_reason=action_reason,
            ))

        return RebalanceReport(
            portfolio_name=self.portfolio.name,
            total_value=total_value,
            drift_threshold=self.drift_threshold,
            holdings=reports,
        )
