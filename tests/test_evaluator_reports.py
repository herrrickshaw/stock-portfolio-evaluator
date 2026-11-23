"""PortfolioEvaluator: position evaluation, aggregation, ordering and the text report."""

import pytest

from stock_evaluator import Portfolio, PortfolioEvaluator, StockPosition


def pf(*rows):
    p = Portfolio()
    for sym, qty, buy, cur, *sector in rows:
        p.add_position(StockPosition(sym, qty, buy, cur, sector=sector[0] if sector else None))
    return p


MIXED = pf(
    ("TCS", 10, 100, 60, "Technology"),     # -40%, STRONG_BUY
    ("UTIL", 10, 100, 125, "Utilities"),    # +25%, SELL
    ("FLAT", 10, 100, 100, "Financials"),   # 0%, HOLD
    ("BIG", 10, 100, 200, "Utilities"),     # +100%, STRONG_SELL
)


def test_evaluate_position_uses_explicit_price_over_position_price():
    ev = PortfolioEvaluator()
    p = StockPosition("TCS", 10, 100, 120, sector="Technology")
    assert ev.evaluate_position(p)["current_price"] == 120
    assert ev.evaluate_position(p, current_price=60)["current_price"] == 60
    # a zero override is falsy and falls back to the position's price
    assert ev.evaluate_position(p, current_price=0)["current_price"] == 120


def test_evaluate_position_sector_precedence():
    ev = PortfolioEvaluator()
    given = ev.evaluate_position(StockPosition("TCS", 1, 100, 100, sector="Energy"))
    inferred = ev.evaluate_position(StockPosition("TCS", 1, 100, 100))
    unknown = ev.evaluate_position(StockPosition("ZZZZ", 1, 100, 100))
    assert given["sector"] == "Energy"
    assert inferred["sector"] == "Technology"
    assert unknown["sector"] == "Unknown"


def test_evaluate_position_keys_and_values():
    out = PortfolioEvaluator().evaluate_position(StockPosition("TCS", 10, 100, 60, sector="Technology"))
    assert set(out) == {"symbol", "sector", "quantity", "purchase_price", "current_price",
                        "recommendation", "analysis"}
    assert out["recommendation"] == "STRONG_BUY"
    assert out["quantity"] == 10 and out["purchase_price"] == 100


def test_beta_by_sector_changes_gain_potential():
    ev = PortfolioEvaluator()
    tech = ev.evaluate_position(StockPosition("A", 1, 100, 100, sector="Technology"))
    util = ev.evaluate_position(StockPosition("A", 1, 100, 100, sector="Utilities"))
    other = ev.evaluate_position(StockPosition("A", 1, 100, 100, sector="Mystery"))
    # base 3 + sector + 3*beta, flat return so momentum 0
    assert tech["analysis"]["gain_potential_3m_pct"] == pytest.approx(3 + 6 + 3.6)
    assert util["analysis"]["gain_potential_3m_pct"] == pytest.approx(3 + 1 + 2.1)
    assert other["analysis"]["gain_potential_3m_pct"] == pytest.approx(3 + 2 + 3.0)


def test_get_sector_normalisation_and_substring_rules():
    ev = PortfolioEvaluator()
    assert ev.get_sector("tcs") == "Technology"
    assert ev.get_sector("Bharti-Artl") == "Technology"  # hyphen/space stripped before lookup
    assert ev.get_sector("bhartiartl") == "Technology"
    assert ev.get_sector("HDFC BANK LTD") == "Financials"
    assert ev.get_sector("L T") == "Industrials"      # exact after spaces removed
    assert ev.get_sector("LTD") == "Unknown"          # 2-letter key never matches as a substring
    assert ev.get_sector("") == "Unknown"


def test_evaluate_portfolio_summary_and_groups():
    res = PortfolioEvaluator().evaluate_portfolio(MIXED)
    s = res["portfolio_summary"]
    assert s["total_positions"] == 4
    assert s["total_cost_basis"] == 4000
    assert s["total_current_value"] == 10 * (60 + 125 + 100 + 200)
    assert s["total_unrealized_pnl"] == 850
    assert s["portfolio_return_pct"] == pytest.approx(21.25)
    assert [p["symbol"] for p in res["positions"]] == ["TCS", "UTIL", "FLAT", "BIG"]
    groups = res["summary_by_recommendation"]
    assert set(groups) == {"STRONG_BUY", "SELL", "HOLD", "STRONG_SELL"}
    assert groups["SELL"]["count"] == 1 and groups["SELL"]["stocks"] == ["UTIL"]
    assert groups["SELL"]["total_value"] == 1250
    assert groups["SELL"]["avg_gain_potential"] == pytest.approx(1.1)
    assert res["timestamp"][:2] == "20"


def test_group_average_gain_potential_is_mean():
    p = pf(("A", 1, 100, 100, "Utilities"), ("B", 3, 100, 100, "Technology"))
    groups = PortfolioEvaluator().evaluate_portfolio(p)["summary_by_recommendation"]
    assert groups["HOLD"]["count"] == 2
    assert groups["HOLD"]["total_value"] == 400
    assert groups["HOLD"]["avg_gain_potential"] == pytest.approx((6.1 + 12.6) / 2)


def test_evaluate_empty_portfolio():
    res = PortfolioEvaluator().evaluate_portfolio(Portfolio())
    assert res["portfolio_summary"]["total_positions"] == 0
    assert res["positions"] == [] and res["summary_by_recommendation"] == {}


def test_gainers_sorted_desc_and_limited():
    ev = PortfolioEvaluator()
    g = ev.get_gainers_list(MIXED, top_n=2)
    assert [x["symbol"] for x in g] == ["TCS", "FLAT"]
    assert g[0]["gain_potential_3m_pct"] >= g[1]["gain_potential_3m_pct"]
    assert g[0]["value"] == 600
    assert g[0]["current_return_pct"] == pytest.approx(-40.0)
    assert set(g[0]) == {"symbol", "sector", "gain_potential_3m_pct", "current_return_pct",
                         "current_price", "quantity", "value", "analysis"}
    assert len(ev.get_gainers_list(MIXED)) == 4          # default top_n=5 > 4 holdings
    assert len(ev.get_gainers_list(MIXED, top_n=0)) == 0


def test_default_top_n_is_five():
    p = pf(*[(f"S{i}", 1, 100, 100, "Financials") for i in range(8)])
    assert len(PortfolioEvaluator().get_gainers_list(p)) == 5


def test_hold_sell_split_and_ordering():
    hold, sell = PortfolioEvaluator().get_hold_sell_list(MIXED)
    assert [h["symbol"] for h in hold] == ["TCS", "FLAT"]
    assert [h["recommendation"] for h in hold] == ["STRONG_BUY", "HOLD"]
    # sell list is ordered by current return ascending (worst first)
    assert [s["symbol"] for s in sell] == ["UTIL", "BIG"]
    assert [s["recommendation"] for s in sell] == ["SELL", "STRONG_SELL"]
    assert hold[0]["gain_potential_3m_pct"] >= hold[1]["gain_potential_3m_pct"]
    assert sell[0]["current_return_pct"] <= sell[1]["current_return_pct"]
    assert set(hold[0]) == {"symbol", "sector", "quantity", "current_price", "value", "recommendation",
                            "current_return_pct", "gain_potential_3m_pct", "holding_cost"}


def test_buy_is_in_hold_bucket():
    hold, sell = PortfolioEvaluator().get_hold_sell_list(pf(("A", 10, 100, 80, "Unknown")))
    assert hold[0]["recommendation"] == "BUY" and sell == []


def test_report_sections_and_numbers():
    text = PortfolioEvaluator().generate_report(MIXED)
    lines = text.split("\n")
    assert lines[0] == "=" * 80 and lines[-1] == "=" * 80
    assert lines[1] == "STOCK PORTFOLIO EVALUATION REPORT"
    for needle in ("PORTFOLIO SUMMARY", "TOP 5 POTENTIAL GAINERS (Next 3 Months)",
                   "STOCKS TO HOLD/BUY", "STOCKS TO SELL", "RECOMMENDATION DISTRIBUTION"):
        assert needle in lines
    assert "Total Positions: 4" in lines
    assert "Total Cost Basis: ₹4,000.00" in lines
    assert "Total Current Value: ₹4,850.00" in lines
    assert "Unrealized P&L: ₹850.00" in lines
    assert "Portfolio Return: 21.25%" in lines
    assert any(ln.startswith("1. TCS (Technology) - Gain Potential: 20.60%") for ln in lines)
    assert "STRONG_BUY: 1 stocks | Total Value: ₹600 | Avg Gain Potential: 20.60%" in lines
    dist = lines[lines.index("RECOMMENDATION DISTRIBUTION") + 2:]
    order = [ln.split(":")[0] for ln in dist if ": " in ln and "stocks" in ln]
    assert order == ["STRONG_BUY", "HOLD", "SELL", "STRONG_SELL"]


def test_report_sell_line_shows_holding_cost():
    text = PortfolioEvaluator().generate_report(MIXED)
    sell_line = next(ln for ln in text.split("\n") if ln.startswith("* UTIL (SELL)"))
    assert "Current Return: 25.00%" in sell_line
    assert "Value: ₹1,250" in sell_line
    assert "Holding Cost: ₹25.00" in sell_line


def test_report_empty_buckets_messages():
    only_winner = pf(("BIG", 10, 100, 200, "Utilities"))
    text = PortfolioEvaluator().generate_report(only_winner)
    assert "No stocks recommended to hold/buy" in text
    assert "No stocks recommended to sell" not in text
    only_hold = pf(("A", 10, 100, 100, "Financials"))
    text = PortfolioEvaluator().generate_report(only_hold)
    assert "No stocks recommended to sell" in text
    assert "No stocks recommended to hold/buy" not in text


def test_report_limits_lists_to_ten():
    p = pf(*[(f"S{i}", 1, 100, 100, "Financials") for i in range(14)])
    text = PortfolioEvaluator().generate_report(p)
    assert len([ln for ln in text.split("\n") if ln.startswith("* ")]) == 10
    assert len([ln for ln in text.split("\n") if ln[:2] in ("1.", "2.", "3.", "4.", "5.", "6.")]) == 5
