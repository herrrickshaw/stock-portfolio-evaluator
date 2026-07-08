"""Command-line interface for stock_evaluator.

    stock-evaluator ingest holdings.csv -o portfolio.json
    stock-evaluator ingest-broker --us us_holdings.xls --india india_holdings.xlsx -o portfolio.json
    stock-evaluator evaluate portfolio.json -o report.md
    stock-evaluator evaluate portfolio.json --format json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .evaluator import PortfolioEvaluator
from .ingest import BrokerReportIngestor, TaxReportIngestor
from .portfolio import Portfolio


def _cmd_ingest(args: argparse.Namespace) -> int:
    portfolio = TaxReportIngestor.holdings_from_csv(args.input, name=args.name)
    portfolio.save(args.output)
    print(f"Wrote {len(portfolio.holdings)} holdings to {args.output}")
    return 0


def _cmd_ingest_broker(args: argparse.Namespace) -> int:
    if not args.us and not args.india:
        print("Provide at least one of --us / --india", file=sys.stderr)
        return 2

    holding_lists = []
    if args.us:
        us_holdings = BrokerReportIngestor.us_holdings_from_xls(args.us)
        print(f"Parsed {len(us_holdings)} US holdings from {args.us}")
        holding_lists.append(us_holdings)
    if args.india:
        india_holdings, unresolved = BrokerReportIngestor.india_holdings_from_xlsx(args.india)
        print(f"Parsed {len(india_holdings)} India holdings from {args.india}")
        if unresolved:
            print(f"WARNING: {len(unresolved)} India holdings could not be resolved to an NSE "
                  f"ticker (ISIN not in the local nse_equity_list.csv — likely BSE-only or an "
                  f"ETF/fund); kept under their raw ISIN as the ticker, so quantities are still "
                  f"counted but won't get real price quotes until remapped manually:")
            for u in unresolved:
                print(f"  {u['isin']}  qty={u['quantity']:g}  {u['name']}")
        holding_lists.append(india_holdings)

    portfolio = BrokerReportIngestor.merge(*holding_lists, name=args.name)
    portfolio.save(args.output)
    print(f"Wrote {len(portfolio.holdings)} combined holdings to {args.output}")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    portfolio = Portfolio.load(args.portfolio)
    evaluator = PortfolioEvaluator(
        portfolio,
        model_kwargs={
            "reward_risk_ratio": args.reward_risk,
            "horizon_days": args.horizon_days,
        },
        drift_threshold=args.drift_threshold,
    )
    report = evaluator.run()

    output = report.to_json() if args.format == "json" else report.to_markdown()
    if args.output:
        Path(args.output).write_text(output)
        print(f"Wrote report to {args.output}")
    else:
        print(output)

    if args.fail_on_action:
        flagged = [h for h in report.holdings if h.action in ("EXIT", "TRIM", "ADD")]
        if flagged:
            return 1
    return 0


def _cmd_realized_gains(args: argparse.Namespace) -> int:
    records = TaxReportIngestor.realized_gains_from_csv(args.input)
    ltcg = sum(r["gain"] for r in records if r["term"] == "LTCG")
    stcg = sum(r["gain"] for r in records if r["term"] == "STCG")
    print(f"{len(records)} realized-gain records: LTCG={ltcg:,.2f}  STCG={stcg:,.2f}")
    if args.output:
        import json
        Path(args.output).write_text(json.dumps(records, indent=2))
        print(f"Wrote records to {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-evaluator", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Build a portfolio.json from a broker/holdings CSV")
    p_ingest.add_argument("input", help="Path to holdings CSV")
    p_ingest.add_argument("-o", "--output", default="portfolio.json")
    p_ingest.add_argument("--name", default=None)
    p_ingest.set_defaults(func=_cmd_ingest)

    p_broker = sub.add_parser("ingest-broker",
                               help="Build a portfolio.json from INDmoney's US (Alpaca) and/or India Excel exports")
    p_broker.add_argument("--us", default=None, help="Path to the INDmoney US holdings .xls export")
    p_broker.add_argument("--india", default=None, help="Path to the INDmoney India holdings .xlsx export")
    p_broker.add_argument("-o", "--output", default="portfolio.json")
    p_broker.add_argument("--name", default="combined")
    p_broker.set_defaults(func=_cmd_ingest_broker)

    p_eval = sub.add_parser("evaluate", help="Run a rebalance check on a portfolio.json")
    p_eval.add_argument("portfolio", help="Path to portfolio.json")
    p_eval.add_argument("-o", "--output", default=None, help="Write report to this path instead of stdout")
    p_eval.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_eval.add_argument("--reward-risk", type=float, default=2.0,
                         help="Newsvendor reward:risk ratio (Cu), default 2.0")
    p_eval.add_argument("--horizon-days", type=int, default=20,
                         help="Holding horizon in trading days for the stop/target band")
    p_eval.add_argument("--drift-threshold", type=float, default=0.05,
                         help="Absolute weight drift vs target that triggers ADD/TRIM, default 0.05")
    p_eval.add_argument("--fail-on-action", action="store_true",
                         help="Exit 1 if any holding needs EXIT/TRIM/ADD (useful for cron/CI)")
    p_eval.set_defaults(func=_cmd_evaluate)

    p_gains = sub.add_parser("realized-gains", help="Parse a broker tax P&L CSV into LTCG/STCG records")
    p_gains.add_argument("input", help="Path to tax P&L CSV")
    p_gains.add_argument("-o", "--output", default=None)
    p_gains.set_defaults(func=_cmd_realized_gains)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
