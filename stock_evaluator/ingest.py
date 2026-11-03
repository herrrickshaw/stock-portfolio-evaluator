"""Data ingestion for tax reports and portfolio files."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .portfolio import Portfolio, StockPosition

UNREALIZED_MARKER = "UNREALIZED P/L"
WIPED_OUT_PRICE_FACTOR = 0.5   # current price assumed as this fraction of cost when value <= 0
MIN_CURRENT_PRICE = 0.01


def _find_unrealized_section(df: pd.DataFrame) -> Optional[int]:
    """Return the row index of the UNREALIZED P/L marker, or None."""
    for idx, row in df.iterrows():
        if isinstance(row[0], str) and UNREALIZED_MARKER in row[0].upper():
            return idx
    return None


def _parse_indmoney_row(row: pd.Series) -> Optional[StockPosition]:
    """Parse one holdings row (col 0 name, 2 qty, 4 buy amount, 6 unrealised P/L); None if unusable."""
    try:
        stock_name = str(row[0]).strip()
        buy_qty = int(float(row[2]))
        buy_amount_total = float(row[4])
        unrealized_pl = float(row[6])

        if buy_qty <= 0 or pd.isna(buy_amount_total) or buy_amount_total <= 0:
            return None

        purchase_price = buy_amount_total / buy_qty
        current_value = buy_amount_total + unrealized_pl

        if current_value <= 0:
            current_price = purchase_price * WIPED_OUT_PRICE_FACTOR
        else:
            current_price = max(current_value / buy_qty, MIN_CURRENT_PRICE)

        return StockPosition(
            symbol=stock_name.upper(),
            quantity=buy_qty,
            purchase_price=purchase_price,
            current_price=current_price,
        )
    except (ValueError, IndexError, TypeError):
        return None


class TaxReportIngestor:
    """Ingest stock portfolio from tax P&L reports."""

    @staticmethod
    def from_indmoney_report(filepath: str) -> Portfolio:
        """
        Load portfolio from INDmoney tax P&L report CSV.

        Extracts unrealized holdings from the UNREALIZED P/L section.

        Args:
            filepath: Path to CSV file

        Returns:
            Portfolio object with all holdings
        """
        portfolio = Portfolio()
        df = pd.read_csv(filepath, header=None)

        unrealized_idx = _find_unrealized_section(df)
        if unrealized_idx is None:
            raise ValueError("Could not find 'UNREALIZED P/L' section in CSV")

        # Row after the marker is the column header; data starts one row later.
        for idx in range(unrealized_idx + 2, len(df)):
            row = df.iloc[idx]

            if pd.isna(row[0]) or row[0] == '':
                break

            position = _parse_indmoney_row(row)
            if position is not None:
                portfolio.add_position(position)

        return portfolio

    @staticmethod
    def from_generic_csv(filepath: str) -> Portfolio:
        """
        Load portfolio from generic CSV with columns:
        symbol, quantity, purchase_price, current_price, [sector]

        Args:
            filepath: Path to CSV file

        Returns:
            Portfolio object
        """
        return Portfolio.from_csv(filepath)

    @staticmethod
    def from_generic_excel(filepath: str) -> Portfolio:
        """
        Load portfolio from generic Excel with columns:
        symbol, quantity, purchase_price, current_price, [sector]

        Args:
            filepath: Path to Excel file

        Returns:
            Portfolio object
        """
        return Portfolio.from_excel(filepath)
