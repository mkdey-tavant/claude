"""Global & domestic market context, plus the benchmark series used for beta.

Fetches a handful of index/FX/commodity tickers to describe the macro backdrop the stock
is trading in. Every fetch is best-effort: a failure on one instrument degrades gracefully
to ``None`` rather than failing the whole analysis.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from ..cache import get_or_set
from ..logging_config import get_logger
from ..models import MarketContext
from ..utils import round_opt

log = get_logger(__name__)

# Yahoo tickers for the macro dashboard.
_NIFTY = "^NSEI"
_SENSEX = "^BSESN"
_INDIA_VIX = "^INDIAVIX"
_USDINR = "USDINR=X"
_SP500 = "^GSPC"
_CRUDE = "CL=F"
_GOLD = "GC=F"


def _fetch_series(symbol: str, days: int = 90) -> pd.Series | None:
    """Return a cached daily close series for ``symbol`` (or ``None`` on failure)."""

    def _load() -> pd.Series | None:
        try:
            hist = yf.Ticker(symbol).history(period=f"{days}d", interval="1d", auto_adjust=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("Market fetch failed for %s: %s", symbol, exc)
            return None
        if hist is None or hist.empty or "Close" not in hist:
            return None
        return hist["Close"].dropna()

    return get_or_set(f"market:{symbol}:{days}", _load)


def _last_change_pct(series: pd.Series | None) -> float | None:
    if series is None or len(series) < 2:
        return None
    prev, last = float(series.iloc[-2]), float(series.iloc[-1])
    if prev == 0:
        return None
    return round((last - prev) / prev * 100.0, 2)


def _last_value(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    return float(series.iloc[-1])


def benchmark_returns() -> pd.Series | None:
    """Daily returns of NIFTY 50, used as the beta benchmark. Cached."""
    series = _fetch_series(_NIFTY, days=400)
    if series is None:
        return None
    return series.pct_change().dropna()


def get_context() -> MarketContext:
    nifty = _fetch_series(_NIFTY)
    sensex = _fetch_series(_SENSEX)
    vix = _fetch_series(_INDIA_VIX)
    usdinr = _fetch_series(_USDINR)
    sp500 = _fetch_series(_SP500)
    crude = _fetch_series(_CRUDE)
    gold = _fetch_series(_GOLD)

    nifty_chg = _last_change_pct(nifty)
    sensex_chg = _last_change_pct(sensex)
    sp500_chg = _last_change_pct(sp500)
    vix_level = _last_value(vix)

    # Simple risk-on/off read: VIX level dominates, tie-broken by NIFTY direction.
    sentiment = "neutral"
    obs: list[str] = []
    if vix_level is not None:
        if vix_level >= 20:
            sentiment = "risk_off"
            obs.append(f"India VIX elevated at {vix_level:.1f} (fear/volatility high).")
        elif vix_level <= 13:
            sentiment = "risk_on"
            obs.append(f"India VIX low at {vix_level:.1f} (calm/complacent market).")
        else:
            obs.append(f"India VIX moderate at {vix_level:.1f}.")

    if sentiment == "neutral" and nifty_chg is not None:
        if nifty_chg >= 0.75:
            sentiment = "risk_on"
        elif nifty_chg <= -0.75:
            sentiment = "risk_off"

    if nifty_chg is not None:
        obs.append(f"NIFTY 50 {'+' if nifty_chg >= 0 else ''}{nifty_chg:.2f}% on the last session.")
    if sp500_chg is not None:
        obs.append(f"S&P 500 {'+' if sp500_chg >= 0 else ''}{sp500_chg:.2f}% (global cue).")
    usdinr_val = _last_value(usdinr)
    if usdinr_val is not None:
        obs.append(f"USD/INR at {usdinr_val:.2f}.")

    as_of = None
    for s in (nifty, sensex, sp500):
        if s is not None and not s.empty:
            as_of = s.index[-1].date().isoformat()
            break

    return MarketContext(
        as_of=as_of,
        sentiment=sentiment,
        india_vix=round_opt(vix_level),
        nifty_50_change_pct=nifty_chg,
        sensex_change_pct=sensex_chg,
        usd_inr=round_opt(usdinr_val),
        sp500_change_pct=sp500_chg,
        crude_oil_change_pct=_last_change_pct(crude),
        gold_change_pct=_last_change_pct(gold),
        observations=obs,
    )
