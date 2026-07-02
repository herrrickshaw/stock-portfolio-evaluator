#!/usr/bin/env python3
"""Example: Analyze stock portfolio using newsvendor model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_evaluator import TaxReportIngestor, PortfolioEvaluator


def main():
    """Analyze portfolio and generate recommendations."""
    report_file = "path/to/your/IndmoneyAnnualTaxPnlReport.csv"

    if not Path(report_file).exists():
        print(f"Error: Report file not found at {report_file}")
        print("\nUsage: python sample_analysis.py <report_file>")
        print("Or update the report_file variable in this script")
        return 1

    print("=" * 100)
    print("STOCK PORTFOLIO ANALYZER - NEWSVENDOR MODEL EVALUATION")
    print("=" * 100)
    print()

    print(f"Loading portfolio from: {Path(report_file).name}")
    portfolio = TaxReportIngestor.from_indmoney_report(report_file)
    print(f"Loaded {len(portfolio.positions)} stock positions")
    print()

    evaluator = PortfolioEvaluator()

    print("=" * 100)
    print("PORTFOLIO SUMMARY")
    print("=" * 100)
    print(f"Total Cost Basis: ₹{portfolio.total_cost_basis:,.2f}")
    print(f"Current Value: ₹{portfolio.total_current_value:,.2f}")
    print(f"Unrealized P&L: ₹{portfolio.total_unrealized_gain_loss:,.2f}")
    print(f"Portfolio Return: {portfolio.portfolio_return_percent:.2f}%")
    print()

    print("=" * 100)
    print("DETAILED EVALUATION REPORT")
    print("=" * 100)
    report = evaluator.generate_report(portfolio)
    print(report)

    return 0


if __name__ == '__main__':
    sys.exit(main())
