"""Technical analysis: compute indicators and distil them into a trend, signal, and score.

The scoring model is a transparent, weighted rules engine (not a black box). Each rule
contributes points to a running score in [-100, +100]; the sign and magnitude reflect how
bullish/bearish the configuration is. This is intentionally explainable so callers can see
*why* a verdict was reached via the ``signals`` list.
"""

from __future__ import annotations

from ..data.provider import StockData
from ..errors import InsufficientHistoryError
from ..models import TechnicalAnalysis
from ..utils import clamp, round_opt, safe_float
from . import indicators as ind

_MIN_ROWS = 60


def _trend_label(score: float) -> str:
    if score >= 50:
        return "strong_up"
    if score >= 15:
        return "up"
    if score <= -50:
        return "strong_down"
    if score <= -15:
        return "down"
    return "sideways"


def _signal_label(score: float) -> str:
    if score >= 20:
        return "bullish"
    if score <= -20:
        return "bearish"
    return "neutral"


def analyze(data: StockData) -> TechnicalAnalysis:
    hist = data.history
    if hist is None or len(hist) < _MIN_ROWS:
        raise InsufficientHistoryError(
            f"Need at least {_MIN_ROWS} trading days of history for {data.resolved_symbol}; "
            f"got {0 if hist is None else len(hist)}."
        )

    close = hist["Close"]
    high, low = hist["High"], hist["Low"]
    last = float(close.iloc[-1])

    sma20 = ind.sma(close, 20)
    sma50 = ind.sma(close, 50)
    sma200 = ind.sma(close, 200)
    ema20 = ind.ema(close, 20)
    rsi14 = ind.rsi(close, 14)
    macd_df = ind.macd(close)
    bb = ind.bollinger_bands(close, 20)
    adx_df = ind.adx(high, low, close, 14)
    stoch = ind.stochastic(high, low, close)
    atr14 = ind.atr(high, low, close, 14)
    support, resistance = ind.support_resistance(high, low, lookback=60)

    def last_val(series) -> float | None:
        v = series.iloc[-1] if len(series.dropna()) else None
        return safe_float(v)

    v_sma20, v_sma50, v_sma200 = last_val(sma20), last_val(sma50), last_val(sma200)
    v_ema20 = last_val(ema20)
    v_rsi = last_val(rsi14)
    v_macd = last_val(macd_df["macd"])
    v_macd_sig = last_val(macd_df["signal"])
    v_macd_hist = last_val(macd_df["hist"])
    v_bb_b = last_val(bb["percent_b"])
    v_adx = last_val(adx_df["adx"])
    v_pdi = last_val(adx_df["plus_di"])
    v_mdi = last_val(adx_df["minus_di"])
    v_stoch_k = last_val(stoch["percent_k"])
    v_atr = last_val(atr14)

    score = 0.0
    signals: list[str] = []

    # 1) Price vs moving averages (trend structure).
    if v_sma50 is not None:
        if last > v_sma50:
            score += 12
            signals.append("Price is above the 50-day SMA (medium-term uptrend).")
        else:
            score -= 12
            signals.append("Price is below the 50-day SMA (medium-term weakness).")
    if v_sma200 is not None:
        if last > v_sma200:
            score += 15
            signals.append("Price is above the 200-day SMA (long-term uptrend).")
        else:
            score -= 15
            signals.append("Price is below the 200-day SMA (long-term downtrend).")

    # 2) Golden/death cross between 50 and 200.
    if v_sma50 is not None and v_sma200 is not None:
        if v_sma50 > v_sma200:
            score += 10
            signals.append("50-day SMA is above the 200-day SMA (golden-cross regime).")
        else:
            score -= 10
            signals.append("50-day SMA is below the 200-day SMA (death-cross regime).")

    # 3) RSI momentum / mean reversion.
    if v_rsi is not None:
        if v_rsi >= 70:
            score -= 8
            signals.append(f"RSI is {v_rsi:.0f} (overbought; pullback risk).")
        elif v_rsi <= 30:
            score += 8
            signals.append(f"RSI is {v_rsi:.0f} (oversold; possible bounce).")
        elif v_rsi >= 55:
            score += 6
            signals.append(f"RSI is {v_rsi:.0f} (positive momentum).")
        elif v_rsi <= 45:
            score -= 6
            signals.append(f"RSI is {v_rsi:.0f} (weak momentum).")

    # 4) MACD.
    if v_macd is not None and v_macd_sig is not None:
        if v_macd > v_macd_sig:
            score += 10
            signals.append("MACD is above its signal line (bullish momentum).")
        else:
            score -= 10
            signals.append("MACD is below its signal line (bearish momentum).")

    # 5) ADX-confirmed directional trend.
    if v_adx is not None and v_pdi is not None and v_mdi is not None:
        if v_adx >= 25:
            if v_pdi > v_mdi:
                score += 12
                signals.append(f"ADX {v_adx:.0f} with +DI>-DI (strong uptrend).")
            else:
                score -= 12
                signals.append(f"ADX {v_adx:.0f} with -DI>+DI (strong downtrend).")
        else:
            signals.append(f"ADX {v_adx:.0f} (weak/undefined trend).")

    # 6) Bollinger position.
    if v_bb_b is not None:
        if v_bb_b >= 1.0:
            score -= 5
            signals.append("Price at/above the upper Bollinger Band (stretched).")
        elif v_bb_b <= 0.0:
            score += 5
            signals.append("Price at/below the lower Bollinger Band (stretched down).")

    # 7) Stochastic extremes.
    if v_stoch_k is not None:
        if v_stoch_k >= 80:
            score -= 4
        elif v_stoch_k <= 20:
            score += 4

    score = clamp(score, -100.0, 100.0)

    return TechnicalAnalysis(
        symbol=data.resolved_symbol,
        trend=_trend_label(score),
        signal=_signal_label(score),
        score=round(score, 1),
        last_close=round_opt(last),
        sma_20=round_opt(v_sma20),
        sma_50=round_opt(v_sma50),
        sma_200=round_opt(v_sma200),
        ema_20=round_opt(v_ema20),
        rsi_14=round_opt(v_rsi),
        macd=round_opt(v_macd, 3),
        macd_signal=round_opt(v_macd_sig, 3),
        macd_hist=round_opt(v_macd_hist, 3),
        bollinger_percent_b=round_opt(v_bb_b, 3),
        adx_14=round_opt(v_adx),
        plus_di=round_opt(v_pdi),
        minus_di=round_opt(v_mdi),
        stochastic_k=round_opt(v_stoch_k),
        atr_14=round_opt(v_atr),
        support=round_opt(support),
        resistance=round_opt(resistance),
        signals=signals,
    )
