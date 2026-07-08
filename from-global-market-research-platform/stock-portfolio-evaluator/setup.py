from setuptools import find_packages, setup

setup(
    name="stock-portfolio-evaluator",
    version="0.1.0",
    description="Newsvendor-based stop-loss/target banding and rebalance checking for a stock portfolio",
    packages=find_packages(exclude=["tests", "examples"]),
    python_requires=">=3.9",
    install_requires=[
        "pandas>=1.5",
        "numpy>=1.23",
        "scipy>=1.9",
        "yfinance>=0.2",
    ],
    extras_require={
        # only needed for China A-share history via the local market_data Postgres DB;
        # every other data path works without it.
        "postgres": ["psycopg2-binary>=2.9"],
    },
    entry_points={
        "console_scripts": [
            "stock-evaluator=stock_evaluator.cli:main",
        ],
    },
)
