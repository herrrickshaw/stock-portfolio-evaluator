"""Portfolio loading/aggregation edge cases not covered by test_evaluator."""

import pandas as pd
import pytest

from stock_evaluator import Portfolio, StockPosition, TaxReportIngestor


def _df():
    return pd.DataFrame({
        "symbol": ["tcs", "infy"],
        "quantity": [10, 4],
        "purchase_price": [3500.0, 1000.0],
        "current_price": [4200.0, 900.0],
        "sector": ["Technology", None],
    })


def test_from_excel_roundtrip(tmp_path):
    p = tmp_path / "p.xlsx"
    _df().to_excel(p, index=False)
    pf = Portfolio.from_excel(str(p))
    assert [x.symbol for x in pf.positions] == ["TCS", "INFY"]
    assert pf.positions[0].quantity == 10
    assert pf.positions[0].sector == "Technology"
    assert pf.positions[1].sector is None


def test_from_excel_missing_columns_raises(tmp_path):
    p = tmp_path / "p.xlsx"
    pd.DataFrame({"symbol": ["A"], "quantity": [1]}).to_excel(p, index=False)
    with pytest.raises(ValueError) as exc:
        Portfolio.from_excel(str(p))
    msg = str(exc.value)
    assert msg.startswith("Missing required columns:")
    assert "purchase_price" in msg and "current_price" in msg


def test_from_csv_missing_columns_raises(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("symbol,quantity,purchase_price\nA,1,2\n")
    with pytest.raises(ValueError, match="current_price"):
        Portfolio.from_csv(str(p))


def test_from_csv_uppercases_and_coerces_types(tmp_path):
    p = tmp_path / "p.csv"
    _df().to_csv(p, index=False)
    pf = Portfolio.from_csv(str(p))
    first = pf.positions[0]
    assert first.symbol == "TCS"
    assert isinstance(first.quantity, int)
    assert isinstance(first.purchase_price, float)


def test_blank_sector_cell_is_none_but_whitespace_is_trimmed(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("symbol,quantity,purchase_price,current_price,sector\n"
                 "A,1,1,1,  Energy \nB,1,1,1,   \n")
    pf = Portfolio.from_csv(str(p))
    assert pf.positions[0].sector == "Energy"
    assert pf.positions[1].sector is None


def test_get_position_case_insensitive_and_missing():
    pf = Portfolio()
    pf.add_position(StockPosition("TCS", 1, 1, 1))
    assert pf.get_position("tcs").symbol == "TCS"
    assert pf.get_position("INFY") is None


def test_get_position_returns_first_match():
    pf = Portfolio()
    pf.add_position(StockPosition("TCS", 1, 1, 1))
    pf.add_position(StockPosition("TCS", 99, 1, 1))
    assert pf.get_position("TCS").quantity == 1


def test_zero_cost_position_and_empty_portfolio_return_zero_percent():
    assert StockPosition("A", 0, 100, 100).return_percent == 0.0
    pf = Portfolio()
    assert pf.total_cost_basis == 0
    assert pf.portfolio_return_percent == 0.0
    pf.add_position(StockPosition("A", 0, 100, 100))
    assert pf.portfolio_return_percent == 0.0


def test_portfolio_aggregates():
    pf = Portfolio()
    pf.add_position(StockPosition("A", 10, 100, 120))   # +200
    pf.add_position(StockPosition("B", 5, 200, 100))    # -500
    assert pf.total_cost_basis == 2000
    assert pf.total_current_value == 1700
    assert pf.total_unrealized_gain_loss == -300
    assert pf.portfolio_return_percent == pytest.approx(-15.0)


def test_loss_position_return_percent_negative():
    assert StockPosition("A", 10, 100, 80).return_percent == pytest.approx(-20.0)
    assert StockPosition("A", 10, 100, 80).unrealized_gain_loss == -200


def test_to_dataframe_columns_and_na_sector():
    pf = Portfolio()
    pf.add_position(StockPosition("A", 10, 100, 120, sector="Energy"))
    pf.add_position(StockPosition("B", 5, 200, 100))
    df = pf.to_dataframe()
    assert list(df.columns) == ["Symbol", "Quantity", "Purchase Price", "Current Price",
                                "Total Cost", "Current Value", "Gain/Loss $", "Return %", "Sector"]
    assert df["Sector"].tolist() == ["Energy", "N/A"]
    assert df["Total Cost"].tolist() == [1000, 1000]
    assert df["Current Value"].tolist() == [1200, 500]
    assert df["Gain/Loss $"].tolist() == [200, -500]
    assert df["Return %"].tolist() == pytest.approx([20.0, -50.0])


def test_to_dataframe_empty():
    assert len(Portfolio().to_dataframe()) == 0


# ---- ingest -----------------------------------------------------------------

def _ind(rows):
    head = "Report,,,,,,\nUNREALIZED P/L,,,,,,\nName,ISIN,Qty,x,Buy,y,PL\n"
    return head + "".join(rows)


def test_indmoney_loads_prices(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(_ind(["tata  ,I,10,0,1000,0,500\n"]))
    pf = TaxReportIngestor.from_indmoney_report(str(p))
    pos = pf.positions[0]
    assert pos.symbol == "TATA"
    assert pos.quantity == 10
    assert pos.purchase_price == pytest.approx(100.0)
    assert pos.current_price == pytest.approx(150.0)


def test_indmoney_missing_section_raises(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("a,b,c\n1,2,3\n")
    with pytest.raises(ValueError, match="UNREALIZED P/L"):
        TaxReportIngestor.from_indmoney_report(str(p))


def test_indmoney_section_header_is_case_insensitive(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(_ind(["A,I,1,0,100,0,10\n"]).replace("UNREALIZED P/L", "Unrealized p/l"))
    assert len(TaxReportIngestor.from_indmoney_report(str(p)).positions) == 1


def test_indmoney_skips_bad_rows_and_stops_at_blank(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(_ind([
        "ZERO,I,0,0,100,0,10\n",      # qty 0 skipped
        "NEG,I,-3,0,100,0,10\n",      # qty < 0 skipped
        "FREE,I,5,0,0,0,10\n",        # cost 0 skipped
        "NEGCOST,I,5,0,-5,0,10\n",    # cost < 0 skipped
        "JUNK,I,abc,0,100,0,10\n",    # non-numeric skipped
        "GOOD,I,2,0,100,0,10\n",
        ",,,,,,\n",                   # blank first cell ends the section
        "AFTER,I,2,0,100,0,10\n",
    ]))
    pf = TaxReportIngestor.from_indmoney_report(str(p))
    assert [x.symbol for x in pf.positions] == ["GOOD"]


def test_indmoney_total_loss_clamps_current_price_at_zero(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(_ind(["WIPED,I,10,0,1000,0,-1500\n"]))
    assert TaxReportIngestor.from_indmoney_report(str(p)).positions[0].current_price == 0.0


def test_indmoney_fractional_quantity_truncates(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(_ind(["FRAC,I,2.9,0,100,0,0\n"]))
    assert TaxReportIngestor.from_indmoney_report(str(p)).positions[0].quantity == 2


def test_indmoney_short_row_is_skipped(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(_ind(["SHORT,I,5\n", "OK,I,2,0,100,0,0\n"]))
    assert [x.symbol for x in TaxReportIngestor.from_indmoney_report(str(p)).positions] == ["OK"]


def test_generic_loaders_delegate(tmp_path):
    c = tmp_path / "p.csv"
    x = tmp_path / "p.xlsx"
    _df().to_csv(c, index=False)
    _df().to_excel(x, index=False)
    assert len(TaxReportIngestor.from_generic_csv(str(c)).positions) == 2
    assert len(TaxReportIngestor.from_generic_excel(str(x)).positions) == 2
