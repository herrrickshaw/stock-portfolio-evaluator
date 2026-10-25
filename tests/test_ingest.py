"""Tests for stock_evaluator.ingest and Portfolio file loaders (synthetic fixtures only)."""

import os
import tempfile
import unittest

from stock_evaluator.ingest import TaxReportIngestor
from stock_evaluator.portfolio import Portfolio

# Synthetic INDmoney-style tax P&L CSV: a realised section, then UNREALIZED P/L.
# Columns used by the parser: 0 name, 2 buy qty, 4 buy amount, 6 unrealised P/L.
INDMONEY_CSV = """REALIZED P/L,,,,,,
Stock,x,Qty,x,Amount,x,PL
OLDCO LTD,,5,,500,,50
,,,,,,
UNREALIZED P/L,,,,,,
Stock,x,Qty,x,Amount,x,PL
ALPHA LTD,,10,,1000,,200
BETA LTD,,4,,400,,-400
GAMMA LTD,,0,,0,,0
DELTA LTD,,abc,,100,,1
,,,,,,
AFTER BLANK,,1,,10,,1
"""


def _write(text, suffix=".csv"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


class TestIndmoneyIngest(unittest.TestCase):

    def setUp(self):
        self.path = _write(INDMONEY_CSV)
        self.pf = TaxReportIngestor.from_indmoney_report(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_reads_only_unrealized_section_until_blank_row(self):
        syms = [p.symbol for p in self.pf.positions]
        self.assertEqual(syms, ["ALPHA LTD", "BETA LTD"])

    def test_prices_derived_from_amount_and_pl(self):
        a = self.pf.get_position("ALPHA LTD")
        self.assertEqual(a.quantity, 10)
        self.assertAlmostEqual(a.purchase_price, 100.0)
        self.assertAlmostEqual(a.current_price, 120.0)
        self.assertAlmostEqual(a.return_percent, 20.0)

    def test_total_loss_is_reported_as_total_loss(self):
        # unrealised P/L == -buy amount -> position is worth 0; it must not be shown as a 50% loss
        b = self.pf.get_position("BETA LTD")
        self.assertAlmostEqual(b.current_price, 0.0)
        self.assertAlmostEqual(b.return_percent, -100.0)

    def test_missing_section_raises(self):
        p = _write("a,b,c\n1,2,3\n")
        try:
            with self.assertRaises(ValueError):
                TaxReportIngestor.from_indmoney_report(p)
        finally:
            os.remove(p)


class TestGenericCsv(unittest.TestCase):

    def test_loads_and_uppercases(self):
        p = _write("symbol,quantity,purchase_price,current_price,sector\ntcs,2,10,15,Technology\n")
        try:
            pf = TaxReportIngestor.from_generic_csv(p)
        finally:
            os.remove(p)
        self.assertEqual(pf.positions[0].symbol, "TCS")
        self.assertEqual(pf.total_cost_basis, 20)
        self.assertEqual(pf.total_current_value, 30)
        self.assertAlmostEqual(pf.portfolio_return_percent, 50.0)

    def test_missing_columns_raise(self):
        p = _write("symbol,quantity\nTCS,1\n")
        try:
            with self.assertRaises(ValueError):
                Portfolio.from_csv(p)
        finally:
            os.remove(p)

    def test_empty_portfolio_return_is_zero(self):
        self.assertEqual(Portfolio().portfolio_return_percent, 0.0)


if __name__ == "__main__":
    unittest.main()
