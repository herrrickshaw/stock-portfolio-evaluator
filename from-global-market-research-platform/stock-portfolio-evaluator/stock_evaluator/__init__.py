"""stock_evaluator — newsvendor-based stock/portfolio evaluation and rebalance checking."""

from .portfolio import Holding, Portfolio
from .models import NewsvendorModel, StockEvaluator, EvaluationResult
from .evaluator import PortfolioEvaluator, RebalanceReport
from .ingest import TaxReportIngestor, CompositeDataSource, BrokerReportIngestor

__version__ = "0.1.0"

__all__ = [
    "Holding",
    "Portfolio",
    "NewsvendorModel",
    "StockEvaluator",
    "EvaluationResult",
    "PortfolioEvaluator",
    "RebalanceReport",
    "TaxReportIngestor",
    "CompositeDataSource",
    "BrokerReportIngestor",
]
