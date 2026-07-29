"""Domain-specific exceptions surfaced to MCP callers as clean error messages."""

from __future__ import annotations


class StockAnalysisError(Exception):
    """Base class for all recoverable, user-facing errors."""


class SymbolNotFoundError(StockAnalysisError):
    """The requested ticker could not be resolved to any known listing."""


class DataUnavailableError(StockAnalysisError):
    """The provider returned no usable data (delisted, suspended, or upstream outage)."""


class InsufficientHistoryError(StockAnalysisError):
    """Not enough price history to compute the requested analysis reliably."""
