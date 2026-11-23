"""Tests for stock_evaluator.cli.main (argument handling, file-type detection, output)."""

import sys

import pandas as pd
import pytest

from stock_evaluator import cli

CSV_TEXT = (
    "symbol,quantity,purchase_price,current_price,sector\n"
    "TCS,10,3500,4200,Technology\n"
    "RELIANCE,5,2000,1000,Energy\n"
    "TITAN,2,100,200,Consumer\n"
)

INDMONEY_TEXT = (
    "Account,Report,,,,,\n"
    "UNREALIZED P/L,,,,,,\n"
    "Name,ISIN,Qty,x,Buy Amount,y,PL\n"
    "TCS LTD,INE1,10,0,35000,0,7000\n"
    ",,,,,,\n"
)


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["stock-evaluator", *argv])
    return cli.main()


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "holdings.csv"
    p.write_text(CSV_TEXT)
    return p


def test_no_command_prints_help_and_returns_1(monkeypatch, capsys):
    assert run(monkeypatch) == 1
    assert "usage:" in capsys.readouterr().out


def test_missing_file_returns_1(monkeypatch, capsys, tmp_path):
    rc = run(monkeypatch, "evaluate", str(tmp_path / "nope.csv"))
    assert rc == 1
    assert capsys.readouterr().out.strip() == f"Error: File not found: {tmp_path / 'nope.csv'}"


def test_evaluate_prints_loaded_count_and_report(monkeypatch, capsys, csv_path):
    assert run(monkeypatch, "evaluate", str(csv_path)) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "Loaded 3 positions from holdings.csv"
    assert "STOCK PORTFOLIO EVALUATION REPORT" in out
    assert "Report saved" not in out


def test_evaluate_writes_report_file(monkeypatch, capsys, csv_path, tmp_path):
    dest = tmp_path / "report.txt"
    assert run(monkeypatch, "evaluate", str(csv_path), "--output", str(dest)) == 0
    text = dest.read_text()
    assert text.startswith("=" * 80)
    assert "PORTFOLIO SUMMARY" in text
    assert f"Report saved to {dest}" in capsys.readouterr().out


def test_gainers_default_top_5_and_custom_top(monkeypatch, capsys, csv_path):
    assert run(monkeypatch, "gainers", str(csv_path)) == 0
    out = capsys.readouterr().out
    assert "TOP 5 POTENTIAL GAINERS (Next 3 Months)" in out
    ranked = [ln for ln in out.splitlines() if ln[:2] in ("1.", "2.", "3.", "4.")]
    assert len(ranked) == 3  # only 3 holdings exist
    assert run(monkeypatch, "gainers", str(csv_path), "--top", "1") == 0
    out = capsys.readouterr().out
    assert "TOP 1 POTENTIAL GAINERS" in out
    assert len([ln for ln in out.splitlines() if ln.startswith(("1.", "2."))]) == 1


def test_gainers_ranked_by_gain_potential(monkeypatch, capsys, csv_path):
    run(monkeypatch, "gainers", str(csv_path), "--top", "3")
    ranked = [ln for ln in capsys.readouterr().out.splitlines() if ln[:2] in ("1.", "2.", "3.")]
    pots = [float(ln.split("Gain Potential:")[1].split("%")[0]) for ln in ranked]
    assert pots == sorted(pots, reverse=True)
    # RELIANCE (-50% return) gets the loser boost, so it leads
    assert ranked[0].split()[1] == "RELIANCE"


def test_actions_lists_hold_and_sell(monkeypatch, capsys, csv_path):
    assert run(monkeypatch, "actions", str(csv_path)) == 0
    out = capsys.readouterr().out
    assert "STOCKS TO HOLD/BUY" in out
    assert "STOCKS TO SELL" in out
    bullets = [ln for ln in out.splitlines() if ln.startswith("•")]
    assert len(bullets) == 3
    assert "No stocks to hold" not in out
    assert "No stocks to sell" not in out


def test_actions_empty_buckets(monkeypatch, capsys, tmp_path):
    p = tmp_path / "only_winner.csv"
    p.write_text("symbol,quantity,purchase_price,current_price,sector\n"
                 "TITAN,2,100,300,Consumer\n")
    assert run(monkeypatch, "actions", str(p)) == 0
    out = capsys.readouterr().out
    assert "No stocks to hold" in out
    assert "No stocks to sell" not in out


def test_actions_no_sell(monkeypatch, capsys, tmp_path):
    p = tmp_path / "flat.csv"
    p.write_text("symbol,quantity,purchase_price,current_price,sector\n"
                 "HDFC,2,100,100,Financials\n")
    assert run(monkeypatch, "actions", str(p)) == 0
    out = capsys.readouterr().out
    assert "No stocks to sell" in out
    assert "No stocks to hold" not in out


def test_actions_truncates_to_15(monkeypatch, capsys, tmp_path):
    rows = "".join(f"S{i},1,100,100,Financials\n" for i in range(20))
    p = tmp_path / "many.csv"
    p.write_text("symbol,quantity,purchase_price,current_price,sector\n" + rows)
    assert run(monkeypatch, "actions", str(p)) == 0
    out = capsys.readouterr().out
    assert len([ln for ln in out.splitlines() if ln.startswith("•")]) == 15


@pytest.mark.parametrize("name", ["my_indmoney_export.csv", "PNL_2024.csv"])
def test_auto_detects_indmoney_by_name(monkeypatch, capsys, tmp_path, name):
    p = tmp_path / name
    p.write_text(INDMONEY_TEXT)
    assert run(monkeypatch, "evaluate", str(p)) == 0
    assert capsys.readouterr().out.startswith(f"Loaded 1 positions from {name}")


def test_auto_detects_excel_by_suffix(monkeypatch, capsys, tmp_path):
    p = tmp_path / "holdings.xlsx"
    pd.read_csv(__import__("io").StringIO(CSV_TEXT)).to_excel(p, index=False)
    assert run(monkeypatch, "evaluate", str(p)) == 0
    assert capsys.readouterr().out.startswith("Loaded 3 positions from holdings.xlsx")


def test_unknown_suffix_falls_back_to_csv(monkeypatch, capsys, tmp_path):
    p = tmp_path / "holdings.dat"
    p.write_text(CSV_TEXT)
    assert run(monkeypatch, "evaluate", str(p)) == 0
    assert capsys.readouterr().out.startswith("Loaded 3 positions from holdings.dat")


def test_explicit_type_overrides_detection(monkeypatch, capsys, tmp_path):
    p = tmp_path / "holdings.txt"
    p.write_text(INDMONEY_TEXT)
    assert run(monkeypatch, "evaluate", str(p), "--type", "indmoney") == 0
    assert capsys.readouterr().out.startswith("Loaded 1 positions")


def test_explicit_excel_type_on_csv_file_fails_cleanly(monkeypatch, capsys, csv_path):
    rc = run(monkeypatch, "evaluate", str(csv_path), "--type", "excel")
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.startswith("Error: ")
    assert captured.out == ""


def test_bad_columns_return_1_with_message_on_stderr(monkeypatch, capsys, tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n")
    assert run(monkeypatch, "evaluate", str(p)) == 1
    assert "Missing required columns" in capsys.readouterr().err


def test_invalid_type_choice_exits(monkeypatch, csv_path):
    with pytest.raises(SystemExit) as exc:
        run(monkeypatch, "evaluate", str(csv_path), "--type", "pdf")
    assert exc.value.code == 2
