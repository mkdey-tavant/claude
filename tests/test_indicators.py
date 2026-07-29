"""Unit tests for the pure indicator math against known-good expectations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_analysis_mcp.analysis import indicators as ind


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ind.sma(s, 2)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 1.5
    assert out.iloc[4] == 4.5


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1, 40, dtype=float))  # strictly increasing
    out = ind.rsi(s, 14)
    assert out.dropna().iloc[-1] == 100.0


def test_rsi_all_losses_is_zero():
    s = pd.Series(np.arange(40, 1, -1, dtype=float))  # strictly decreasing
    out = ind.rsi(s, 14)
    assert out.dropna().iloc[-1] == 0.0


def test_rsi_in_range():
    rng = np.random.default_rng(42)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    out = ind.rsi(s, 14).dropna()
    assert (out >= 0).all() and (out <= 100).all()


def test_macd_hist_is_difference():
    s = pd.Series(100 + np.cumsum(np.ones(100)))
    df = ind.macd(s)
    diff = (df["macd"] - df["signal"]).dropna()
    assert np.allclose(diff.values, df["hist"].dropna().values)


def test_bollinger_percent_b_bounds_on_trend():
    s = pd.Series(np.linspace(100, 200, 100))
    bb = ind.bollinger_bands(s, 20).dropna()  # drop warm-up rows before comparing
    assert (bb["upper"] >= bb["middle"]).all()
    assert (bb["lower"] <= bb["middle"]).all()


def test_atr_positive():
    n = 100
    close = pd.Series(np.linspace(100, 150, n))
    high, low = close * 1.02, close * 0.98
    out = ind.atr(high, low, close, 14).dropna()
    assert (out > 0).all()


def test_support_resistance_orders():
    n = 100
    close = pd.Series(np.linspace(100, 150, n))
    high, low = close * 1.01, close * 0.99
    support, resistance = ind.support_resistance(high, low, 60)
    assert support < resistance


def test_adx_columns_and_range():
    n = 120
    close = pd.Series(np.linspace(100, 200, n))
    high, low = close * 1.02, close * 0.98
    df = ind.adx(high, low, close, 14).dropna()
    assert {"adx", "plus_di", "minus_di"}.issubset(df.columns)
    assert (df["adx"] >= 0).all() and (df["adx"] <= 100).all()
