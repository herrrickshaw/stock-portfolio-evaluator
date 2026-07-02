# Stock Portfolio Evaluator

A comprehensive stock portfolio analysis tool using the **Newsvendor Model** for inventory optimization applied to stock holdings.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

### 📊 **Portfolio Ingestion**
- Load from Excel/CSV files
- Parse INDmoney tax P&L reports
- Support for custom stock data formats

### 🎯 **Stock Evaluation**
- **Buy/Hold/Sell Recommendations** based on multiple factors
- **3-Month Gain Potential** estimation using momentum and sector analysis
- **Newsvendor Model** for holding cost vs opportunity cost analysis
- **Sector Classification** with beta-adjusted expectations

### 📈 **Newsvendor Model Analysis**
The newsvendor model optimizes inventory by balancing:
- **Holding Cost**: Opportunity cost of capital tied up (default: 8% annually)
- **Shortage Cost**: Regret cost if stock appreciates without holding (default: 25%)
- **Critical Ratio**: 76% threshold for optimal decision-making

## Installation

### Via pip (from GitHub)
```bash
pip install git+https://github.com/herrrickshaw/stock-portfolio-evaluator.git
```

### Local installation
```bash
git clone https://github.com/herrrickshaw/stock-portfolio-evaluator.git
cd stock-portfolio-evaluator
pip install -e .
```

## Quick Start

### Command Line
```bash
stock-eval evaluate your_portfolio.csv --report
stock-eval gainers your_portfolio.csv --top 10
stock-eval actions your_portfolio.csv
```

### Python API
```python
from stock_evaluator import TaxReportIngestor, PortfolioEvaluator

portfolio = TaxReportIngestor.from_indmoney_report("tax_report.csv")
evaluator = PortfolioEvaluator()
print(evaluator.generate_report(portfolio))
```

## Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for detailed usage, configuration, and examples.

## License

MIT License - see LICENSE file for details
