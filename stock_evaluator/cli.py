"""Command-line interface for stock portfolio evaluation."""

import sys
import argparse
from pathlib import Path
from .ingest import TaxReportIngestor
from .evaluator import PortfolioEvaluator


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Stock Portfolio Evaluator - Analyze holdings with newsvendor model"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    eval_parser = subparsers.add_parser('evaluate', help='Evaluate portfolio')
    eval_parser.add_argument('file', help='Portfolio file (CSV/Excel) or INDmoney tax report')
    eval_parser.add_argument('--type', choices=['auto', 'indmoney', 'csv', 'excel'], default='auto')
    eval_parser.add_argument('--report', action='store_true', help='Generate text report')
    eval_parser.add_argument('--output', help='Output file for report')

    gainers_parser = subparsers.add_parser('gainers', help='Show top potential gainers')
    gainers_parser.add_argument('file', help='Portfolio file')
    gainers_parser.add_argument('--top', type=int, default=5)
    gainers_parser.add_argument('--type', choices=['auto', 'indmoney', 'csv', 'excel'], default='auto')

    action_parser = subparsers.add_parser('actions', help='Show hold/sell recommendations')
    action_parser.add_argument('file', help='Portfolio file')
    action_parser.add_argument('--type', choices=['auto', 'indmoney', 'csv', 'excel'], default='auto')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    try:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            return 1

        file_type = args.type
        if file_type == 'auto':
            if 'indmoney' in filepath.name.lower() or 'pnl' in filepath.name.lower():
                file_type = 'indmoney'
            elif filepath.suffix.lower() == '.csv':
                file_type = 'csv'
            elif filepath.suffix.lower() in ['.xlsx', '.xls']:
                file_type = 'excel'
            else:
                file_type = 'csv'

        if file_type == 'indmoney':
            portfolio = TaxReportIngestor.from_indmoney_report(str(filepath))
        elif file_type == 'csv':
            portfolio = TaxReportIngestor.from_generic_csv(str(filepath))
        else:
            portfolio = TaxReportIngestor.from_generic_excel(str(filepath))

        print(f"Loaded {len(portfolio.positions)} positions from {filepath.name}")
        print()

        evaluator = PortfolioEvaluator()

        if args.command == 'evaluate':
            report = evaluator.generate_report(portfolio)
            print(report)
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(report)
                print(f"\nReport saved to {args.output}")

        elif args.command == 'gainers':
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

        elif args.command == 'actions':
            hold_list, sell_list = evaluator.get_hold_sell_list(portfolio)
            print("STOCKS TO HOLD/BUY")
            print("=" * 100)
            if hold_list:
                for stock in hold_list[:15]:
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
                for stock in sell_list[:15]:
                    print(
                        f"• {stock['symbol']:<20} [{stock['recommendation']:<12}] "
                        f"Return: {stock['current_return_pct']:>7.2f}% | "
                        f"Holding Cost: ₹{stock['holding_cost']:>8.2f} | "
                        f"Value: ₹{stock['value']:>12,.0f}"
                    )
            else:
                print("No stocks to sell")
            print()

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
