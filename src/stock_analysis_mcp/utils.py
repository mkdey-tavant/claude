"""Small shared helpers for safe numeric coercion and rounding."""

from __future__ import annotations

import math
from typing import Any

DISCLAIMER = (
    "This analysis is generated from historical and publicly available data for "
    "educational and informational purposes only. It is NOT investment advice, a "
    "recommendation, or a solicitation to buy or sell any security. Markets are "
    "uncertain; past performance does not guarantee future results. Consult a "
    "SEBI-registered investment adviser before making any decision."
)


def safe_float(value: Any) -> float | None:
    """Coerce ``value`` to a finite float, or return ``None`` for missing/invalid input."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def round_opt(value: float | None, ndigits: int = 2) -> float | None:
    """Round an optional float, passing ``None`` through unchanged."""
    if value is None:
        return None
    return round(value, ndigits)


def pct(value: float | None, ndigits: int = 2) -> float | None:
    """Convert a fraction (0.0123) to a percentage (1.23), rounded."""
    if value is None:
        return None
    return round(value * 100.0, ndigits)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
