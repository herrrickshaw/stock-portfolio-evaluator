"""Portfolio evaluation and recommendation engine."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from . import config
from .models import StockEvaluator
from .portfolio import Portfolio, StockPosition

REC_ORDER = ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']
HOLD_RECOMMENDATIONS = frozenset({'STRONG_BUY', 'BUY', 'HOLD'})
RULE = "=" * 80
THIN_RULE = "-" * 80


class PortfolioEvaluator:
    """Evaluate portfolio holdings and generate recommendations."""

    def __init__(self,
                 evaluator: Optional[StockEvaluator] = None,
                 sector_map: Optional[Dict[str, str]] = None):
        """Create an evaluator; both collaborators are injectable (defaults come from config)."""
        self.evaluator = evaluator if evaluator is not None else StockEvaluator()
        self.sector_map = dict(sector_map if sector_map is not None else config.SYMBOL_SECTOR_MAP)

    def get_sector(self, symbol: str) -> str:
        """Get sector for a stock symbol."""
        sym_upper = symbol.upper().replace(' ', '').replace('-', '')
        for key, sector in self.sector_map.items():
            if key in sym_upper:
                return sector
        return config.DEFAULT_SECTOR

    def evaluate_position(self, position: StockPosition, current_price: Optional[float] = None) -> Dict:
        """Evaluate a single position."""
        price = current_price or position.current_price
        sector = position.sector or self.get_sector(position.symbol)
        days_held = config.ASSUMED_DAYS_HELD
        beta = config.SECTOR_BETA.get(sector, config.DEFAULT_BETA)

        recommendation, analysis = self.evaluator.recommend(
            symbol=position.symbol,
            current_price=price,
            purchase_price=position.purchase_price,
            quantity=position.quantity,
            sector=sector,
            days_held=days_held,
            beta=beta
        )

        return {
            'symbol': position.symbol,
            'sector': sector,
            'quantity': position.quantity,
            'purchase_price': position.purchase_price,
            'current_price': price,
            'recommendation': recommendation.value,
            'analysis': analysis,
        }

    def evaluate_portfolio(self, portfolio: Portfolio) -> Dict:
        """Evaluate entire portfolio and generate recommendations."""
        results = {
            'timestamp': datetime.now().isoformat(),
            'portfolio_summary': {
                'total_positions': len(portfolio.positions),
                'total_cost_basis': portfolio.total_cost_basis,
                'total_current_value': portfolio.total_current_value,
                'total_unrealized_pnl': portfolio.total_unrealized_gain_loss,
                'portfolio_return_pct': portfolio.portfolio_return_percent,
            },
            'positions': [],
            'summary_by_recommendation': {},
        }

        for position in portfolio.positions:
            eval_result = self.evaluate_position(position)
            results['positions'].append(eval_result)

        rec_summary = {}
        for pos_eval in results['positions']:
            rec = pos_eval['recommendation']
            if rec not in rec_summary:
                rec_summary[rec] = {'count': 0, 'stocks': [], 'total_value': 0, 'avg_gain_potential': 0}
            rec_summary[rec]['count'] += 1
            rec_summary[rec]['stocks'].append(pos_eval['symbol'])
            rec_summary[rec]['total_value'] += pos_eval['quantity'] * pos_eval['current_price']
            rec_summary[rec]['avg_gain_potential'] += pos_eval['analysis'].get('gain_potential_3m_pct', 0)

        for rec in rec_summary:
            if rec_summary[rec]['count'] > 0:
                rec_summary[rec]['avg_gain_potential'] /= rec_summary[rec]['count']

        results['summary_by_recommendation'] = rec_summary
        return results

    def get_gainers_list(self, portfolio: Portfolio, top_n: int = 5) -> List[Dict]:
        """Get top potential gainers for next 3 months."""
        evaluations = []

        for position in portfolio.positions:
            eval_result = self.evaluate_position(position)
            gain_potential = eval_result['analysis'].get('gain_potential_3m_pct', 0)
            evaluations.append({
                'symbol': eval_result['symbol'],
                'sector': eval_result['sector'],
                'gain_potential_3m_pct': gain_potential,
                'current_return_pct': eval_result['analysis']['current_return_pct'],
                'current_price': eval_result['current_price'],
                'quantity': eval_result['quantity'],
                'value': eval_result['quantity'] * eval_result['current_price'],
                'analysis': eval_result['analysis'],
            })

        evaluations.sort(key=lambda x: x['gain_potential_3m_pct'], reverse=True)
        return evaluations[:top_n]

    def get_hold_sell_list(self, portfolio: Portfolio) -> Tuple[List[Dict], List[Dict]]:
        """Get stocks to hold vs sell."""
        hold_list = []
        sell_list = []

        for position in portfolio.positions:
            eval_result = self.evaluate_position(position)
            rec = eval_result['recommendation']

            eval_with_rec = {
                'symbol': eval_result['symbol'],
                'sector': eval_result['sector'],
                'quantity': eval_result['quantity'],
                'current_price': eval_result['current_price'],
                'value': eval_result['quantity'] * eval_result['current_price'],
                'recommendation': rec,
                'current_return_pct': eval_result['analysis']['current_return_pct'],
                'gain_potential_3m_pct': eval_result['analysis']['gain_potential_3m_pct'],
                'holding_cost': eval_result['analysis']['holding_cost'],
            }

            if rec in HOLD_RECOMMENDATIONS:
                hold_list.append(eval_with_rec)
            else:
                sell_list.append(eval_with_rec)

        hold_list.sort(key=lambda x: x['gain_potential_3m_pct'], reverse=True)
        sell_list.sort(key=lambda x: x['current_return_pct'])
        return hold_list, sell_list

    def generate_report(self, portfolio: Portfolio) -> str:
        """Generate a text report of portfolio evaluation."""
        eval_results = self.evaluate_portfolio(portfolio)
        gainers = self.get_gainers_list(portfolio, top_n=5)
        hold_list, sell_list = self.get_hold_sell_list(portfolio)

        lines: List[str] = [RULE, "STOCK PORTFOLIO EVALUATION REPORT", RULE, ""]
        lines += _summary_section(eval_results['portfolio_summary'])
        lines += _gainers_section(gainers)
        lines += _hold_section(hold_list)
        lines += _sell_section(sell_list)
        lines += _distribution_section(eval_results['summary_by_recommendation'])
        lines += ["", RULE]
        return "\n".join(lines)


def _summary_section(summary: Dict) -> List[str]:
    """Portfolio summary block (currency in INR)."""
    return [
        "PORTFOLIO SUMMARY",
        THIN_RULE,
        f"Total Positions: {summary['total_positions']}",
        f"Total Cost Basis: ₹{summary['total_cost_basis']:,.2f}",
        f"Total Current Value: ₹{summary['total_current_value']:,.2f}",
        f"Unrealized P&L: ₹{summary['total_unrealized_pnl']:,.2f}",
        f"Portfolio Return: {summary['portfolio_return_pct']:.2f}%",
        "",
    ]


def _gainers_section(gainers: List[Dict]) -> List[str]:
    """Top potential gainers block."""
    lines = ["TOP 5 POTENTIAL GAINERS (Next 3 Months)", THIN_RULE]
    for i, gainer in enumerate(gainers, 1):
        lines.append(
            f"{i}. {gainer['symbol']} ({gainer['sector']}) - "
            f"Gain Potential: {gainer['gain_potential_3m_pct']:.2f}% | "
            f"Current Return: {gainer['current_return_pct']:.2f}% | "
            f"Qty: {gainer['quantity']} @ ₹{gainer['current_price']:.2f}"
        )
    lines.append("")
    return lines


def _hold_section(hold_list: List[Dict]) -> List[str]:
    """Hold/buy block (first 10 entries)."""
    lines = ["STOCKS TO HOLD/BUY", THIN_RULE]
    if hold_list:
        for stock in hold_list[:10]:
            lines.append(
                f"* {stock['symbol']} ({stock['recommendation']}) - "
                f"Gain Potential: {stock['gain_potential_3m_pct']:.2f}% | "
                f"Return: {stock['current_return_pct']:.2f}% | "
                f"Value: ₹{stock['value']:,.0f}"
            )
    else:
        lines.append("No stocks recommended to hold/buy")
    lines.append("")
    return lines


def _sell_section(sell_list: List[Dict]) -> List[str]:
    """Sell block (first 10 entries)."""
    lines = ["STOCKS TO SELL", THIN_RULE]
    if sell_list:
        for stock in sell_list[:10]:
            lines.append(
                f"* {stock['symbol']} ({stock['recommendation']}) - "
                f"Current Return: {stock['current_return_pct']:.2f}% | "
                f"Value: ₹{stock['value']:,.0f} | "
                f"Holding Cost: ₹{stock['holding_cost']:.2f}"
            )
    else:
        lines.append("No stocks recommended to sell")
    lines.append("")
    return lines


def _distribution_section(rec_summary: Dict) -> List[str]:
    """Per-recommendation counts, value and mean gain potential."""
    lines = ["RECOMMENDATION DISTRIBUTION", THIN_RULE]
    for rec in REC_ORDER:
        if rec in rec_summary:
            data = rec_summary[rec]
            lines.append(
                f"{rec}: {data['count']} stocks | "
                f"Total Value: ₹{data['total_value']:,.0f} | "
                f"Avg Gain Potential: {data['avg_gain_potential']:.2f}%"
            )
    return lines
