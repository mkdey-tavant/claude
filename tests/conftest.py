"""Shared fixtures: synthetic StockData so the whole analysis layer is testable offline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_analysis_mcp.data.provider import StockData


def _make_history(prices: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range(end="2026-07-24", periods=len(prices), freq="B")
    close = pd.Series(prices, index=idx)
    high = close * 1.01
    low = close * 0.99
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(np.full(len(prices), 2_000_000.0), index=idx)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})


@pytest.fixture
def uptrend_data() -> StockData:
    # Smooth 3x rise over ~300 sessions with mild noise.
    n = 300
    base = np.linspace(100, 300, n)
    noise = np.sin(np.linspace(0, 12, n)) * 3
    prices = base + noise
    return StockData(
        resolved_symbol="TEST.NS",
        history=_make_history(prices),
        info={
            "longName": "Test Uptrend Ltd",
            "currency": "INR",
            "trailingPE": 22.0,
            "returnOnEquity": 0.21,
            "profitMargins": 0.18,
            "debtToEquity": 30.0,
            "revenueGrowth": 0.20,
            "earningsGrowth": 0.25,
            "currentRatio": 2.1,
            "marketCap": 5_00_00_00_00_000,
            "sector": "Technology",
        },
    )


@pytest.fixture
def downtrend_data() -> StockData:
    n = 300
    base = np.linspace(300, 100, n)
    noise = np.sin(np.linspace(0, 12, n)) * 3
    prices = base + noise
    return StockData(
        resolved_symbol="FALL.NS",
        history=_make_history(prices),
        info={
            "longName": "Test Downtrend Ltd",
            "currency": "INR",
            "trailingPE": -5.0,
            "returnOnEquity": -0.08,
            "profitMargins": -0.05,
            "debtToEquity": 250.0,
            "revenueGrowth": -0.12,
            "currentRatio": 0.8,
        },
    )
