"""Characterisation tests for loading portfolios (CSV, Excel, INDmoney report)."""

import pandas as pd
import pytest

from stock_evaluator import Portfolio, TaxReportIngestor
from stock_evaluator.evaluator import PortfolioEvaluator


def test_from_csv_uppercases_symbols_and_reads_rows(generic_csv):
    p = Portfolio.from_csv(str(generic_csv))
    assert [x.symbol for x in p.positions][:2] == ["TCS", "HDFCBANK"]
    assert len(p.positions) == 6
    assert p.get_position("tcs").quantity == 10


def test_from_csv_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("symbol,quantity\nA,1\n")
    with pytest.raises(ValueError, match="Missing required columns"):
        Portfolio.from_csv(str(path))


def test_from_excel_matches_csv(generic_csv, tmp_path):
    xlsx = tmp_path / "p.xlsx"
    pd.read_csv(generic_csv).to_excel(xlsx, index=False)
    a = Portfolio.from_csv(str(generic_csv)).to_dataframe()
    b = Portfolio.from_excel(str(xlsx)).to_dataframe()
    pd.testing.assert_frame_equal(a, b)


def test_indmoney_report_parsing(indmoney_csv):
    p = TaxReportIngestor.from_indmoney_report(str(indmoney_csv))
    # zero-quantity row skipped; blank row ends the section
    assert [x.symbol for x in p.positions] == ["INFOSYS", "RELIANCE", "WIPED"]
    infy, rel, wiped = p.positions
    assert infy.purchase_price == pytest.approx(1000) and infy.current_price == pytest.approx(1250)
    assert rel.current_price == pytest.approx(1600)
    assert wiped.current_price == pytest.approx(50)  # value <= 0 -> half of cost


def test_indmoney_report_without_marker(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="UNREALIZED"):
        TaxReportIngestor.from_indmoney_report(str(path))


def test_sector_lookup_substring_first_match():
    ev = PortfolioEvaluator()
    assert ev.get_sector("hdfc-bank") == "Financials"
    assert ev.get_sector("ONGC") == "Energy"
    # known quirk (preserved): "LT" matches inside "ONGCLTD" before ONGC is reached
    assert ev.get_sector("ONGC LTD") == "Industrials"
    assert ev.get_sector("UNKNOWNCO") == "Technology"


def test_injected_sector_map():
    assert PortfolioEvaluator(sector_map={"ABC": "Utilities"}).get_sector("abc") == "Utilities"
