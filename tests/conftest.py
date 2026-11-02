"""Shared fixtures: small portfolios written to tmp_path (no network, no real data)."""

from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden"

GENERIC_CSV = """symbol,quantity,purchase_price,current_price,sector
tcs,10,3500,4200,Technology
HDFCBANK,5,1500,1800,
ONGC,100,200,120,Energy
WIPRO,50,500,300,
SUNPHARMA,20,1000,1010,
FOO,7,100,60,Weird
"""

INDMONEY_CSV = """Header,x,,,,,
UNREALIZED P/L,,,,,,
Stock,ISIN,BuyQty,BuyPrice,BuyAmount,x,UnrealizedPL
Infosys,A,10,1,10000,,2500
Reliance,B,5,1,20000,,-12000
Broken,C,0,1,0,,0
Wiped,D,10,1,1000,,-1500
,,,,,,
After,E,1,1,1,,1
"""


@pytest.fixture
def generic_csv(tmp_path: Path) -> Path:
    path = tmp_path / "portfolio.csv"
    path.write_text(GENERIC_CSV)
    return path


@pytest.fixture
def indmoney_csv(tmp_path: Path) -> Path:
    path = tmp_path / "indmoney_pnl.csv"
    path.write_text(INDMONEY_CSV)
    return path
