"""Tests for stock portfolio evaluator."""

import unittest
from stock_evaluator import Portfolio, StockPosition, PortfolioEvaluator


class TestPortfolio(unittest.TestCase):
    """Test portfolio management."""

    def setUp(self):
        """Set up test fixtures."""
        self.portfolio = Portfolio()

    def test_add_position(self):
        """Test adding a position to portfolio."""
        position = StockPosition(
            symbol="TCS",
            quantity=10,
            purchase_price=3500,
            current_price=4200
        )
        self.portfolio.add_position(position)
        self.assertEqual(len(self.portfolio.positions), 1)

    def test_portfolio_metrics(self):
        """Test portfolio calculation metrics."""
        position = StockPosition(
            symbol="HDFC",
            quantity=5,
            purchase_price=1500,
            current_price=1800
        )
        self.portfolio.add_position(position)

        self.assertEqual(self.portfolio.total_cost_basis, 7500)
        self.assertEqual(self.portfolio.total_current_value, 9000)
        self.assertEqual(self.portfolio.total_unrealized_gain_loss, 1500)

    def test_stock_position_return(self):
        """Test stock position return calculation."""
        position = StockPosition(
            symbol="INFY",
            quantity=20,
            purchase_price=2000,
            current_price=2500
        )
        self.assertEqual(position.return_percent, 25.0)


class TestEvaluator(unittest.TestCase):
    """Test portfolio evaluator."""

    def setUp(self):
        """Set up test fixtures."""
        self.portfolio = Portfolio()
        self.evaluator = PortfolioEvaluator()

        self.portfolio.add_position(StockPosition(
            symbol="TCS",
            quantity=10,
            purchase_price=3500,
            current_price=4200,
            sector="Technology"
        ))
        self.portfolio.add_position(StockPosition(
            symbol="HDFC",
            quantity=5,
            purchase_price=1500,
            current_price=1800,
            sector="Financials"
        ))

    def test_evaluate_portfolio(self):
        """Test portfolio evaluation."""
        results = self.evaluator.evaluate_portfolio(self.portfolio)
        self.assertIn('portfolio_summary', results)
        self.assertEqual(results['portfolio_summary']['total_positions'], 2)

    def test_gainers_list(self):
        """Test getting gainers list."""
        gainers = self.evaluator.get_gainers_list(self.portfolio, top_n=2)
        self.assertEqual(len(gainers), 2)
        self.assertIn('gain_potential_3m_pct', gainers[0])

    def test_hold_sell_list(self):
        """Test hold/sell classification."""
        hold_list, sell_list = self.evaluator.get_hold_sell_list(self.portfolio)
        self.assertEqual(len(hold_list) + len(sell_list), 2)


if __name__ == '__main__':
    unittest.main()
