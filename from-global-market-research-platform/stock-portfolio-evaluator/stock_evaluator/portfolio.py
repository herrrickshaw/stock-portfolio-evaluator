"""Portfolio and Holding — in-memory representation of a set of stock positions."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Holding:
    ticker: str
    market: str = "india"
    quantity: float = 0.0
    avg_cost: Optional[float] = None
    buy_date: Optional[str] = None
    target_weight: Optional[float] = None

    def cost_basis(self) -> Optional[float]:
        if self.avg_cost is None:
            return None
        return self.avg_cost * self.quantity


_COLUMN_ALIASES = {
    "ticker": {"ticker", "symbol", "yf_ticker", "instrument"},
    "market": {"market", "exchange_market", "country"},
    "quantity": {"quantity", "qty", "shares", "units"},
    "avg_cost": {"avg_cost", "average_cost", "buy_price", "avg_price", "cost_price"},
    "buy_date": {"buy_date", "purchase_date", "trade_date", "date"},
    "target_weight": {"target_weight", "target_pct", "target_allocation"},
}


def _match_column(header: list[str], field_name: str) -> Optional[str]:
    lowered = {h.lower().strip(): h for h in header}
    for alias in _COLUMN_ALIASES[field_name]:
        if alias in lowered:
            return lowered[alias]
    return None


@dataclass
class Portfolio:
    name: str = "default"
    holdings: list[Holding] = field(default_factory=list)

    def add_holding(self, holding: Holding) -> None:
        self.holdings.append(holding)

    def tickers(self) -> list[str]:
        return [h.ticker for h in self.holdings]

    def weights(self, price_map: dict[str, float]) -> dict[str, float]:
        """Current market-value weight of each holding, given a ticker -> cmp map."""
        values = {h.ticker: (price_map.get(h.ticker) or 0.0) * h.quantity for h in self.holdings}
        total = sum(values.values())
        if total <= 0:
            return {t: 0.0 for t in values}
        return {t: v / total for t, v in values.items()}

    def total_value(self, price_map: dict[str, float]) -> float:
        return sum((price_map.get(h.ticker) or 0.0) * h.quantity for h in self.holdings)

    def target_weights(self) -> dict[str, float]:
        """Target weight per ticker, defaulting to an equal split among holdings that don't specify one."""
        explicit = {h.ticker: h.target_weight for h in self.holdings if h.target_weight is not None}
        remaining = [h.ticker for h in self.holdings if h.target_weight is None]
        leftover = max(0.0, 1.0 - sum(explicit.values()))
        equal_share = leftover / len(remaining) if remaining else 0.0
        return {**{t: equal_share for t in remaining}, **explicit}

    def to_dict(self) -> dict:
        return {"name": self.name, "holdings": [asdict(h) for h in self.holdings]}

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        holdings = [Holding(**h) for h in data.get("holdings", [])]
        return cls(name=data.get("name", "default"), holdings=holdings)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "Portfolio":
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def from_csv(cls, path: str | Path, name: Optional[str] = None) -> "Portfolio":
        """Build a Portfolio from a broker/holdings CSV with flexible column naming."""
        rows = list(csv.DictReader(Path(path).open(newline="")))
        if not rows:
            return cls(name=name or Path(path).stem)
        header = list(rows[0].keys())
        cols = {f: _match_column(header, f) for f in _COLUMN_ALIASES}
        if cols["ticker"] is None:
            raise ValueError(f"Could not find a ticker/symbol column in {path}; header was {header}")

        holdings: list[Holding] = []
        for row in rows:
            ticker = (row.get(cols["ticker"]) or "").strip()
            if not ticker:
                continue
            quantity = float(row.get(cols["quantity"]) or 0) if cols["quantity"] else 0.0
            avg_cost_raw = row.get(cols["avg_cost"]) if cols["avg_cost"] else None
            avg_cost = float(avg_cost_raw) if avg_cost_raw not in (None, "") else None
            market = (row.get(cols["market"]) or "india").strip().lower() if cols["market"] else "india"
            buy_date = row.get(cols["buy_date"]) if cols["buy_date"] else None
            target_weight_raw = row.get(cols["target_weight"]) if cols["target_weight"] else None
            target_weight = float(target_weight_raw) if target_weight_raw not in (None, "") else None
            holdings.append(Holding(
                ticker=ticker, market=market, quantity=quantity,
                avg_cost=avg_cost, buy_date=buy_date, target_weight=target_weight,
            ))
        return cls(name=name or Path(path).stem, holdings=holdings)
