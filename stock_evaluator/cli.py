"""Command-line interface for stock portfolio evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .evaluator import PortfolioEvaluator
from .ingest import TaxReportIngestor
from .portfolio import Portfolio

FILE_TYPES = ['auto', 'indmoney', 'csv', 'excel']
EXCEL_SUFFIXES = ('.xlsx', '.xls')
MAX_ACTION_ROWS = 15


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (subcommands: evaluate, gainers, actions)."""
    parser = argparse.ArgumentParser(
        description="Stock Portfolio Evaluator - Analyze holdings with newsvendor model"
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    eval_parser = subparsers.add_parser('evaluate', help='Evaluate portfolio')
    eval_parser.add_argument('file', help='Portfolio file (CSV/Excel) or INDmoney tax report')
    eval_parser.add_argument('--type', choices=FILE_TYPES, default='auto')
    eval_parser.add_argument('--report', action='store_true', help='Generate text report')
    eval_parser.add_argument('--output', help='Output file for report')

    gainers_parser = subparsers.add_parser('gainers', help='Show top potential gainers')
    gainers_parser.add_argument('file', help='Portfolio file')
    gainers_parser.add_argument('--top', type=int, default=5)
    gainers_parser.add_argument('--type', choices=FILE_TYPES, default='auto')

    action_parser = subparsers.add_parser('actions', help='Show hold/sell recommendations')
    action_parser.add_argument('file', help='Portfolio file')
    action_parser.add_argument('--type', choices=FILE_TYPES, default='auto')
    return parser


def detect_file_type(filepath: Path, requested: str = 'auto') -> str:
    """Resolve 'auto' to indmoney/csv/excel from the file name and suffix."""
    if requested != 'auto':
        return requested
    name = filepath.name.lower()
    suffix = filepath.suffix.lower()
    if 'indmoney' in name or 'pnl' in name:
        return 'indmoney'
    if suffix in EXCEL_SUFFIXES:
        return 'excel'
    return 'csv'


def load_portfolio(filepath: Path, file_type: str) -> Portfolio:
    """Load a portfolio of the given resolved file type."""
    if file_type == 'indmoney':
        return TaxReportIngestor.from_indmoney_report(str(filepath))
    if file_type == 'csv':
        return TaxReportIngestor.from_generic_csv(str(filepath))
    return TaxReportIngestor.from_generic_excel(str(filepath))


def _cmd_evaluate(args: argparse.Namespace, evaluator: PortfolioEvaluator, portfolio: Portfolio) -> None:
    report = evaluator.generate_report(portfolio)
    print(report)
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"\nReport saved to {args.output}")


def _cmd_gainers(args: argparse.Namespace, evaluator: PortfolioEvaluator, portfolio: Portfolio) -> None:
    gainers = evaluator.get_gainers_list(portfolio, top_n=args.top)
    print(f"TOP {args.top} POTENTIAL GAINERS (Next 3 Months)")
    print("=" * 100)
    for i, gainer in enumerate(gainers, 1):
        print(
            f"{i}. {gainer['symbol']:<20} {gainer['sector']:<12} "
            f"Gain Potential: {gainer['gain_potential_3m_pct']:>6.2f}% | "
            f"Current Return: {gainer['current_return_pct']:>7.2f}% | "
            f"Qty: {gainer['quantity']:>5} @ ₹{gainer['current_price']:>8.2f} = "
            f"₹{gainer['value']:>12,.0f}"
        )
    print()


def _cmd_actions(args: argparse.Namespace, evaluator: PortfolioEvaluator, portfolio: Portfolio) -> None:
    hold_list, sell_list = evaluator.get_hold_sell_list(portfolio)
    print("STOCKS TO HOLD/BUY")
    print("=" * 100)
    if hold_list:
        for stock in hold_list[:MAX_ACTION_ROWS]:
            print(
                f"• {stock['symbol']:<20} [{stock['recommendation']:<12}] "
                f"Return: {stock['current_return_pct']:>7.2f}% | "
                f"Gain Pot: {stock['gain_potential_3m_pct']:>6.2f}% | "
                f"Value: ₹{stock['value']:>12,.0f}"
            )
    else:
        print("No stocks to hold")
    print()

    print("STOCKS TO SELL")
    print("=" * 100)
    if sell_list:
        for stock in sell_list[:MAX_ACTION_ROWS]:
            print(
                f"• {stock['symbol']:<20} [{stock['recommendation']:<12}] "
                f"Return: {stock['current_return_pct']:>7.2f}% | "
                f"Holding Cost: ₹{stock['holding_cost']:>8.2f} | "
                f"Value: ₹{stock['value']:>12,.0f}"
            )
    else:
        print("No stocks to sell")
    print()


COMMANDS = {'evaluate': _cmd_evaluate, 'gainers': _cmd_gainers, 'actions': _cmd_actions}


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    # Top-level boundary: any failure becomes a one-line error and exit code 1.
    try:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            return 1

        portfolio = load_portfolio(filepath, detect_file_type(filepath, args.type))
        print(f"Loaded {len(portfolio.positions)} positions from {filepath.name}")
        print()

        COMMANDS[args.command](args, PortfolioEvaluator(), portfolio)
        return 0

    except Exception as e:  # noqa: BLE001 - deliberate CLI boundary
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
