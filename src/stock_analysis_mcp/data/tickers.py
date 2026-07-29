"""Resolve user-supplied stock names/symbols to Yahoo Finance tickers.

Yahoo suffixes Indian listings with ``.NS`` (NSE) and ``.BO`` (BSE). Users, however,
type things like ``reliance``, ``RELIANCE``, ``TCS.NS`` or ``INFY``. This module
normalises all of those into candidate Yahoo tickers, trying the preferred market first.

Note: this is deliberately a *heuristic* resolver, not an exhaustive listing database.
It normalises formatting and appends the right exchange suffix; the provider then
validates each candidate against Yahoo and returns the first that yields real data.
"""

from __future__ import annotations

import re

from ..config import get_settings

_NSE_SUFFIX = ".NS"
_BSE_SUFFIX = ".BO"
_KNOWN_SUFFIXES = (_NSE_SUFFIX, _BSE_SUFFIX)

# A small alias table for common informal names. Extend as needed; unknown names still
# fall through to the generic normalisation path.
_ALIASES: dict[str, str] = {
    "RELIANCE": "RELIANCE",
    "RIL": "RELIANCE",
    "TCS": "TCS",
    "INFOSYS": "INFY",
    "INFY": "INFY",
    "HDFC BANK": "HDFCBANK",
    "HDFCBANK": "HDFCBANK",
    "ICICI BANK": "ICICIBANK",
    "ICICIBANK": "ICICIBANK",
    "SBI": "SBIN",
    "STATE BANK": "SBIN",
    "SBIN": "SBIN",
    "ITC": "ITC",
    "LT": "LT",
    "LARSEN": "LT",
    "L&T": "LT",
    "WIPRO": "WIPRO",
    "BHARTI AIRTEL": "BHARTIARTL",
    "AIRTEL": "BHARTIARTL",
    "MARUTI": "MARUTI",
    "TATA MOTORS": "TATAMOTORS",
    "TATAMOTORS": "TATAMOTORS",
    "ADANI ENTERPRISES": "ADANIENT",
}


def _clean(raw: str) -> str:
    """Uppercase, trim, and collapse internal whitespace."""
    return re.sub(r"\s+", " ", raw.strip()).upper()


def normalise_base(raw: str) -> str:
    """Return the exchange-agnostic base symbol (no ``.NS``/``.BO`` suffix)."""
    cleaned = _clean(raw)
    for suffix in _KNOWN_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break

    if cleaned in _ALIASES:
        return _ALIASES[cleaned]

    # Strip characters Yahoo never uses in NSE/BSE symbols (keep A-Z, 0-9, & and -).
    return re.sub(r"[^A-Z0-9&-]", "", cleaned)


def _explicit_suffix(raw: str) -> str | None:
    cleaned = _clean(raw)
    for suffix in _KNOWN_SUFFIXES:
        if cleaned.endswith(suffix):
            return suffix
    return None


def candidate_tickers(raw: str, preferred_market: str | None = None) -> list[str]:
    """Return an ordered list of Yahoo ticker candidates to try.

    - If the user already provided a ``.NS``/``.BO`` suffix, that candidate is tried first.
    - Otherwise the preferred market (arg → settings default) is tried first, then the other.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty symbol provided.")

    base = normalise_base(raw)
    if not base:
        raise ValueError(f"Could not derive a valid symbol from {raw!r}.")

    ordered: list[str] = []

    explicit = _explicit_suffix(raw)
    if explicit:
        ordered.append(f"{base}{explicit}")

    market = (preferred_market or get_settings().default_market).upper()
    primary, secondary = (
        (_BSE_SUFFIX, _NSE_SUFFIX) if market == "BSE" else (_NSE_SUFFIX, _BSE_SUFFIX)
    )
    for suffix in (primary, secondary):
        candidate = f"{base}{suffix}"
        if candidate not in ordered:
            ordered.append(candidate)

    return ordered
