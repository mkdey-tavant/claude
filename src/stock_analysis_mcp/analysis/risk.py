"""Risk analysis: volatility, beta, drawdown, Sharpe, and historical VaR.

All metrics are derived from the daily return series. ``beta`` is computed against a
benchmark return series when one is supplied (typically NIFTY 50), otherwise it falls
back to the provider-reported beta if present.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import get_settings
from ..data.provider import StockData
from ..errors import InsufficientHistoryError
from ..models import RiskAnalysis
from ..utils import round_opt, safe_float

_TRADING_DAYS = 252
_MIN_ROWS = 60


def _max_drawdown(close: pd.Series) -> float | None:
    if close.empty:
        return None
    running_max = close.cummax()
    drawdown = (close - running_max) / running_max
    return float(drawdown.min())


def _historical_var(returns: pd.Series, confidence: float = 0.95) -> float | None:
    clean = returns.dropna()
    if len(clean) < 30:
        return None
    # 95% VaR = the 5th percentile of the return distribution (a negative number).
    return float(np.percentile(clean, (1 - confidence) * 100))


def _beta_from_series(stock_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    joined = pd.concat([stock_ret, bench_ret], axis=1, join="inner").dropna()
    if len(joined) < 30:
        return None
    s = joined.iloc[:, 0]
    b = joined.iloc[:, 1]
    var_b = float(b.var(ddof=0))
    if var_b == 0:
        return None
    cov = float(np.cov(s, b, ddof=0)[0, 1])
    return cov / var_b


def _risk_level(vol: float | None, mdd: float | None) -> str:
    """Bucket by annualised volatility, nudged by drawdown severity."""
    if vol is None:
        return "moderate"
    if vol >= 0.60 or (mdd is not None and mdd <= -0.60):
        return "very_high"
    if vol >= 0.40:
        return "high"
    if vol >= 0.22:
        return "moderate"
    return "low"


def analyze(data: StockData, benchmark_returns: pd.Series | None = None) -> RiskAnalysis:
    hist = data.history
    if hist is None or len(hist) < _MIN_ROWS:
        raise InsufficientHistoryError(
            f"Need at least {_MIN_ROWS} trading days for risk metrics on {data.resolved_symbol}."
        )

    settings = get_settings()
    close = hist["Close"]
    returns = close.pct_change().dropna()

    ann_vol = float(returns.std(ddof=0) * np.sqrt(_TRADING_DAYS)) if len(returns) else None

    mean_daily = float(returns.mean()) if len(returns) else 0.0
    ann_return = mean_daily * _TRADING_DAYS
    sharpe = None
    if ann_vol and ann_vol > 0:
        sharpe = (ann_return - settings.risk_free_rate) / ann_vol

    mdd = _max_drawdown(close)
    var95 = _historical_var(returns)

    downside = returns[returns < 0]
    downside_dev = float(downside.std(ddof=0) * np.sqrt(_TRADING_DAYS)) if len(downside) else None

    beta = None
    if benchmark_returns is not None:
        beta = _beta_from_series(returns, benchmark_returns)
    if beta is None:
        beta = safe_float(data.info.get("beta"))

    # Liquidity heuristic from average traded value.
    liquidity_note = None
    if "Volume" in hist and "Close" in hist:
        avg_turnover = float((hist["Volume"] * hist["Close"]).tail(30).mean())
        if avg_turnover < 5e6:  # < ~₹50 lakh/day
            liquidity_note = "Thin liquidity — wide spreads and slippage risk on larger orders."
        elif avg_turnover < 5e7:
            liquidity_note = "Moderate liquidity."
        else:
            liquidity_note = "Ample liquidity."

    level = _risk_level(ann_vol, mdd)

    obs: list[str] = []
    if ann_vol is not None:
        obs.append(f"Annualised volatility ~{ann_vol * 100:.1f}%.")
    if beta is not None:
        rel = "more" if beta > 1 else "less"
        obs.append(f"Beta ~{beta:.2f} ({rel} volatile than the benchmark).")
    if mdd is not None:
        obs.append(f"Worst historical drawdown in-window: {mdd * 100:.1f}%.")
    if var95 is not None:
        obs.append(
            f"On a typical bad day (95% VaR), a ~{abs(var95) * 100:.1f}% single-day loss "
            f"is within historical norms."
        )
    if sharpe is not None:
        quality = "attractive" if sharpe > 1 else "modest" if sharpe > 0 else "poor"
        obs.append(f"Sharpe ratio ~{sharpe:.2f} ({quality} risk-adjusted return).")
    if liquidity_note:
        obs.append(liquidity_note)

    return RiskAnalysis(
        symbol=data.resolved_symbol,
        risk_level=level,
        annualised_volatility=round_opt(ann_vol, 4),
        beta=round_opt(beta, 3),
        max_drawdown=round_opt(mdd, 4),
        sharpe_ratio=round_opt(sharpe, 3),
        value_at_risk_95=round_opt(var95, 4),
        downside_deviation=round_opt(downside_dev, 4),
        liquidity_note=liquidity_note,
        observations=obs,
    )
