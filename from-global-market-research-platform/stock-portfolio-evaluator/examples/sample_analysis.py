"""End-to-end demo: build a small multi-market portfolio, run a rebalance check,
and print the report. Pulls live prices via yfinance/Cassandra if reachable;
falls back gracefully to whatever holdings return data for.

Run from the package root:  python examples/sample_analysis.py
"""
from stock_evaluator.evaluator import PortfolioEvaluator
from stock_evaluator.portfolio import Holding, Portfolio


def main() -> None:
    portfolio = Portfolio(
        name="sample",
        holdings=[
            Holding(ticker="RELIANCE", market="india", quantity=10, avg_cost=2400.0, target_weight=0.30),
            Holding(ticker="TCS", market="india", quantity=5, avg_cost=3500.0, target_weight=0.25),
            Holding(ticker="AAPL", market="us", quantity=8, avg_cost=170.0, target_weight=0.25),
            Holding(ticker="MSFT", market="us", quantity=4, avg_cost=330.0, target_weight=0.20),
        ],
    )

    evaluator = PortfolioEvaluator(
        portfolio,
        model_kwargs={"reward_risk_ratio": 2.0, "horizon_days": 20},
        drift_threshold=0.05,
    )
    report = evaluator.run()
    print(report.to_markdown())


if __name__ == "__main__":
    main()
