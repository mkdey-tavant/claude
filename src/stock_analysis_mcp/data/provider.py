"""yfinance provider wrapper: resolution, retries, caching, and normalisation.

All raw network access lives here so the analysis layer stays pure and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import yfinance as yf
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..cache import get_or_set
from ..config import get_settings
from ..errors import DataUnavailableError, SymbolNotFoundError
from ..logging_config import get_logger
from . import tickers

log = get_logger(__name__)
_settings = get_settings()

# Minimum rows of daily history we consider "usable" for even light analysis.
_MIN_USABLE_ROWS = 30


@dataclass
class StockData:
    """Normalised bundle of everything the analysis layer needs for one stock."""

    resolved_symbol: str
    history: pd.DataFrame  # daily OHLCV, ascending by date
    info: dict[str, Any] = field(default_factory=dict)
    fast_info: dict[str, Any] = field(default_factory=dict)
    news: list[dict[str, Any]] = field(default_factory=list)

    @property
    def currency(self) -> str:
        return self.info.get("currency") or self.fast_info.get("currency") or "INR"

    @property
    def long_name(self) -> str:
        return self.info.get("longName") or self.info.get("shortName") or self.resolved_symbol


class _NetworkError(Exception):
    """Internal marker so tenacity only retries genuine transient failures."""


@retry(
    retry=retry_if_exception_type(_NetworkError),
    stop=stop_after_attempt(_settings.max_retries),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=6),
    reraise=True,
)
def _download_history(symbol: str, days: int) -> pd.DataFrame:
    """Download daily OHLCV for ``symbol`` over the trailing ``days`` window."""
    try:
        ticker = yf.Ticker(symbol)
        # ``period`` in days keeps the request small and index-consistent.
        hist = ticker.history(period=f"{days}d", interval="1d", auto_adjust=True)
    except Exception as exc:  # noqa: BLE001 - yfinance raises a variety of types
        raise _NetworkError(str(exc)) from exc

    if hist is None or hist.empty:
        return pd.DataFrame()

    hist = hist.rename(columns=str.title)  # Open/High/Low/Close/Volume
    hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
    hist.index = pd.to_datetime(hist.index)
    return hist.sort_index()


def _fetch_meta(symbol: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Fetch ``info``, ``fast_info`` and recent news, tolerating partial failures."""
    ticker = yf.Ticker(symbol)

    info: dict[str, Any] = {}
    try:
        info = dict(ticker.info or {})
    except Exception as exc:  # noqa: BLE001
        log.warning("info() failed for %s: %s", symbol, exc)

    fast: dict[str, Any] = {}
    try:
        fi = ticker.fast_info
        fast = {k: fi[k] for k in list(fi.keys())} if hasattr(fi, "keys") else dict(fi)
    except Exception as exc:  # noqa: BLE001
        log.warning("fast_info failed for %s: %s", symbol, exc)

    news: list[dict[str, Any]] = []
    try:
        news = list(ticker.news or [])[:8]
    except Exception as exc:  # noqa: BLE001
        log.debug("news() failed for %s: %s", symbol, exc)

    return info, fast, news


def _looks_valid(hist: pd.DataFrame, info: dict[str, Any]) -> bool:
    """Heuristic: does this candidate actually correspond to a live listing?"""
    if hist is not None and not hist.empty and len(hist) >= _MIN_USABLE_ROWS:
        return True
    # Some thinly-traded names have sparse history but valid metadata.
    return bool(info.get("regularMarketPrice") or info.get("currentPrice"))


def _load_uncached(raw_symbol: str, preferred_market: str | None, days: int) -> StockData:
    candidates = tickers.candidate_tickers(raw_symbol, preferred_market)
    log.info("Resolving %r -> candidates %s", raw_symbol, candidates)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            hist = _download_history(candidate, days)
        except _NetworkError as exc:
            last_error = exc
            log.warning("History download failed for %s: %s", candidate, exc)
            continue

        info, fast, news = _fetch_meta(candidate)
        if _looks_valid(hist, info):
            log.info("Resolved %r -> %s (%d rows)", raw_symbol, candidate, len(hist))
            return StockData(
                resolved_symbol=candidate,
                history=hist,
                info=info,
                fast_info=fast,
                news=news,
            )

    if last_error is not None:
        raise DataUnavailableError(
            f"Could not retrieve data for {raw_symbol!r}; the data provider may be "
            f"temporarily unavailable. Last error: {last_error}"
        )
    raise SymbolNotFoundError(
        f"No NSE/BSE listing found for {raw_symbol!r}. "
        f"Tried: {', '.join(candidates)}. Check the symbol and try again."
    )


def load_stock(
    raw_symbol: str,
    preferred_market: str | None = None,
    days: int | None = None,
) -> StockData:
    """Resolve and load a stock, using the shared TTL cache.

    Raises :class:`SymbolNotFoundError` or :class:`DataUnavailableError` on failure.
    """
    days = days or _settings.history_days
    market = (preferred_market or _settings.default_market).upper()
    key = f"stock:{tickers.normalise_base(raw_symbol)}:{market}:{days}"
    return get_or_set(key, lambda: _load_uncached(raw_symbol, market, days))
