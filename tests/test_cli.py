"""CLI smoke tests; output compared against goldens captured from the pre-refactor code."""

from pathlib import Path

import pytest
from conftest import GOLDEN

from stock_evaluator.cli import detect_file_type, main


def _golden(name: str) -> str:
    """Golden stdout; the captured file ends with the exit code on its own line, which is dropped."""
    text = (GOLDEN / name).read_text()
    return text[: text.rindex("0\n")]


def _run(capsys, argv):
    code = main(argv)
    return code, capsys.readouterr().out


@pytest.mark.parametrize("fixture,args,golden", [
    ("generic_csv", ["evaluate", "--report"], "generic_evaluate.txt"),
    ("generic_csv", ["gainers", "--top", "3"], "generic_gainers.txt"),
    ("generic_csv", ["actions"], "generic_actions.txt"),
    ("indmoney_csv", ["evaluate", "--report"], "indmoney_evaluate.txt"),
    ("indmoney_csv", ["actions"], "indmoney_actions.txt"),
])
def test_cli_matches_golden(request, capsys, fixture, args, golden):
    path = request.getfixturevalue(fixture)
    code, out = _run(capsys, [args[0], str(path), *args[1:]])
    assert code == 0
    assert out == _golden(golden)


def test_missing_file(capsys):
    code, out = _run(capsys, ["evaluate", "/definitely/not/here.csv"])
    assert code == 1 and "File not found" in out


def test_no_command_prints_help(capsys):
    code, out = _run(capsys, [])
    assert code == 1 and "usage" in out.lower()


def test_output_flag_writes_report(generic_csv, tmp_path, capsys):
    out_file = tmp_path / "r.txt"
    assert main(["evaluate", str(generic_csv), "--output", str(out_file)]) == 0
    assert out_file.read_text().startswith("=" * 80)


@pytest.mark.parametrize("name,expected", [
    ("indmoney_report.csv", "indmoney"), ("my_pnl.xlsx", "indmoney"),
    ("p.csv", "csv"), ("p.XLSX", "excel"), ("p.xls", "excel"), ("p.txt", "csv"),
])
def test_detect_file_type(name, expected):
    assert detect_file_type(Path(name)) == expected


def test_detect_file_type_explicit_wins():
    assert detect_file_type(Path("p.csv"), "excel") == "excel"
