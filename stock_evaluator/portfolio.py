"""Portfolio ingestion and management from Excel files."""

import pandas as pd
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class StockPosition:
    """Represents a single stock position in a portfolio."""
    symbol: str
    quantity: int
    purchase_price: float
    current_price: float
    purchase_date: Optional[str] = None
    sector: Optional[str] = None

    @property
    def total_cost(self) -> float:
        """Total cost basis of position."""
        return self.quantity * self.purchase_price

    @property
    def current_value(self) -> float:
        """Current market value of position."""
        return self.quantity * self.current_price

    @property
    def unrealized_gain_loss(self) -> float:
        """Unrealized gain or loss in dollars."""
        return self.current_value - self.total_cost

    @property
    def return_percent(self) -> float:
        """Return percentage."""
        if self.total_cost == 0:
            return 0.0
        return (self.unrealized_gain_loss / self.total_cost) * 100


class Portfolio:
    """Portfolio management and data ingestion."""

    def __init__(self):
        """Initialize empty portfolio."""
        self.positions: List[StockPosition] = []

    @classmethod
    def from_excel(cls, filepath: str) -> "Portfolio":
        """
        Load portfolio from Excel file.

        Expected columns: symbol, quantity, purchase_price, current_price,
        [optional: purchase_date, sector]
        """
        portfolio = cls()
        df = pd.read_excel(filepath)

        required_cols = {'symbol', 'quantity', 'purchase_price', 'current_price'}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        for _, row in df.iterrows():
            position = StockPosition(
                symbol=str(row['symbol']).upper(),
                quantity=int(row['quantity']),
                purchase_price=float(row['purchase_price']),
                current_price=float(row['current_price']),
                purchase_date=row.get('purchase_date'),
                sector=row.get('sector')
            )
            portfolio.positions.append(position)

        return portfolio

    @classmethod
    def from_csv(cls, filepath: str) -> "Portfolio":
        """Load portfolio from CSV file."""
        portfolio = cls()
        df = pd.read_csv(filepath)

        required_cols = {'symbol', 'quantity', 'purchase_price', 'current_price'}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        for _, row in df.iterrows():
            position = StockPosition(
                symbol=str(row['symbol']).upper(),
                quantity=int(row['quantity']),
                purchase_price=float(row['purchase_price']),
                current_price=float(row['current_price']),
                purchase_date=row.get('purchase_date'),
                sector=row.get('sector')
            )
            portfolio.positions.append(position)

        return portfolio

    def add_position(self, position: StockPosition) -> None:
        """Add a stock position to portfolio."""
        self.positions.append(position)

    def get_position(self, symbol: str) -> Optional[StockPosition]:
        """Get a specific position by symbol."""
        for position in self.positions:
            if position.symbol == symbol.upper():
                return position
        return None

    @property
    def total_cost_basis(self) -> float:
        """Total cost basis of entire portfolio."""
        return sum(p.total_cost for p in self.positions)

    @property
    def total_current_value(self) -> float:
        """Total current market value of portfolio."""
        return sum(p.current_value for p in self.positions)

    @property
    def total_unrealized_gain_loss(self) -> float:
        """Total unrealized gain/loss across portfolio."""
        return self.total_current_value - self.total_cost_basis

    @property
    def portfolio_return_percent(self) -> float:
        """Overall portfolio return percentage."""
        if self.total_cost_basis == 0:
            return 0.0
        return (self.total_unrealized_gain_loss / self.total_cost_basis) * 100

    def to_dataframe(self) -> pd.DataFrame:
        """Convert portfolio to pandas DataFrame."""
        data = []
        for pos in self.positions:
            data.append({
                'Symbol': pos.symbol,
                'Quantity': pos.quantity,
                'Purchase Price': pos.purchase_price,
                'Current Price': pos.current_price,
                'Total Cost': pos.total_cost,
                'Current Value': pos.current_value,
                'Gain/Loss $': pos.unrealized_gain_loss,
                'Return %': pos.return_percent,
                'Sector': pos.sector or 'N/A'
            })
        return pd.DataFrame(data)
