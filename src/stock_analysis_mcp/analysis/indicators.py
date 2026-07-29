"""Pure technical-indicator functions over pandas Series/DataFrames.

Implemented from first principles (no pandas-ta dependency) so the math is transparent,
auditable, and free of third-party version churn. Every function is total: given a
Series it returns a Series of the same index, using NaN where a value is undefined.

Conventions:
- ``close`` etc. are pandas Series indexed by date, ascending.
- RSI/ADX use Wilder's smoothing (the standard for these indicators).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing == EMA with alpha = 1/window.
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When there are no losses at all, RSI is defined as 100.
    out = out.where(avg_loss != 0.0, 100.0)
    return out


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Return MACD line, signal line, and histogram."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands: middle (SMA), upper, lower, and %B position."""
    middle = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = upper - lower
    percent_b = (close - lower) / width.replace(0.0, np.nan)
    return pd.DataFrame(
        {"middle": middle, "upper": upper, "lower": lower, "percent_b": percent_b}
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
) -> pd.DataFrame:
    """Average Directional Index with +DI / -DI (trend-strength indicator)."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )

    tr = true_range(high, low, close)
    atr_ = tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    plus_di = 100.0 * (
        plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        / atr_.replace(0.0, np.nan)
    )
    minus_di = 100.0 * (
        minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        / atr_.replace(0.0, np.nan)
    )

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_ = dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    return pd.DataFrame({"adx": adx_, "plus_di": plus_di, "minus_di": minus_di})


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_window: int = 14,
    d_window: int = 3,
) -> pd.DataFrame:
    """Stochastic oscillator (%K and %D)."""
    lowest = low.rolling(window=k_window, min_periods=k_window).min()
    highest = high.rolling(window=k_window, min_periods=k_window).max()
    percent_k = 100.0 * (close - lowest) / (highest - lowest).replace(0.0, np.nan)
    percent_d = percent_k.rolling(window=d_window, min_periods=d_window).mean()
    return pd.DataFrame({"percent_k": percent_k, "percent_d": percent_d})


def support_resistance(
    high: pd.Series,
    low: pd.Series,
    lookback: int = 60,
) -> tuple[float, float]:
    """Naive support/resistance from recent swing low/high over ``lookback`` days."""
    window_low = low.tail(lookback)
    window_high = high.tail(lookback)
    support = float(window_low.min()) if not window_low.empty else float("nan")
    resistance = float(window_high.max()) if not window_high.empty else float("nan")
    return support, resistance


def daily_returns(close: pd.Series) -> pd.Series:
    return close.pct_change()
