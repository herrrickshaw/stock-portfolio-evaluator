#!/usr/bin/env python3
"""Setup configuration for stock portfolio evaluator."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="stock-portfolio-evaluator",
    version="1.0.0",
    author="Umashankar Triplicane Dwarakanathan",
    author_email="umashankartd1991@gmail.com",
    description="Stock portfolio analysis tool using newsvendor model for inventory optimization",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/herrrickshaw/stock-portfolio-evaluator",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pandas>=1.3.0",
        "openpyxl>=3.0.0",
        "numpy>=1.20.0",
    ],
    entry_points={
        "console_scripts": [
            "stock-eval=stock_evaluator.cli:main",
        ],
    },
    include_package_data=True,
)
