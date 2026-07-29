"""FastMCP server exposing stock-analysis tools.

Tools are thin orchestration wrappers over the analysis layer. They translate domain
exceptions into clean MCP tool errors and return typed pydantic models, which FastMCP
serialises to structured JSON for the calling model.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .analysis import fundamental as fundamental_mod
from .analysis import market as market_mod
from .analysis import risk as risk_mod
from .analysis import synthesis
from .analysis import technical as technical_mod
from .config import get_settings
from .data import provider
from .errors import StockAnalysisError
from .logging_config import configure_logging, get_logger
from .models import (
    FullAnalysis,
    FundamentalAnalysis,
    MarketContext,
    NewsItem,
    Quote,
    RiskAnalysis,
    TechnicalAnalysis,
)
from .utils import DISCLAIMER

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger(__name__)

mcp = FastMCP(
    name="stock-analysis",
    instructions=(
        "Tools for fundamental, technical, and risk analysis of Indian (NSE/BSE) stocks, "
        "with market context and a structured forward outlook. Pass a symbol like "
        "'RELIANCE', 'TCS', 'INFY', or a Yahoo-style ticker ('RELIANCE.NS', 'TCS.BO'). "
        "Optionally pass market='NSE' or 'BSE'. All output is informational only and is "
        "NOT investment advice — always surface the returned disclaimer to the end user. "
        "For a forward view, use the 'outlook' block from analyze_stock as raw material and "
        "add your own reasoning; never present it as a guaranteed prediction."
    ),
)


def _parse_news(raw_items: list[dict[str, Any]]) -> list[NewsItem]:
    """Normalise yfinance news entries (schema varies across versions)."""
    items: list[NewsItem] = []
    for it in raw_items:
        content = it.get("content", it) if isinstance(it, dict) else {}
        title = content.get("title") or it.get("title")
        if not title:
            continue
        publisher = None
        provider_field = content.get("provider") or it.get("publisher")
        if isinstance(provider_field, dict):
            publisher = provider_field.get("displayName")
        elif isinstance(provider_field, str):
            publisher = provider_field
        link = None
        url_field = content.get("canonicalUrl") or content.get("clickThroughUrl")
        if isinstance(url_field, dict):
            link = url_field.get("url")
        link = link or it.get("link")
        published = content.get("pubDate") or content.get("displayTime")
        items.append(NewsItem(title=title, publisher=publisher, link=link, published=published))
    return items[:6]


def _fail(exc: Exception) -> Exception:
    """Convert internal errors to a clean message; unexpected ones are logged fully."""
    if isinstance(exc, StockAnalysisError):
        return ValueError(str(exc))
    log.exception("Unexpected error during analysis")
    return RuntimeError(f"Analysis failed unexpectedly: {exc}")


@mcp.tool()
def get_quote(symbol: str, market: str | None = None) -> Quote:
    """Return a current price snapshot for an NSE/BSE stock.

    Args:
        symbol: Stock name or ticker, e.g. 'RELIANCE', 'INFY', 'TCS.NS'.
        market: Optional 'NSE' or 'BSE' to disambiguate dual-listed names.
    """
    try:
        data = provider.load_stock(symbol, preferred_market=market)
        return synthesis.build_quote(data)
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from exc


@mcp.tool()
def get_technical_analysis(symbol: str, market: str | None = None) -> TechnicalAnalysis:
    """Compute technical indicators (SMA/EMA, RSI, MACD, Bollinger, ADX, Stochastic, ATR)
    and a transparent, explainable trend/momentum score for an NSE/BSE stock.
    """
    try:
        data = provider.load_stock(symbol, preferred_market=market)
        return technical_mod.analyze(data)
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from exc


@mcp.tool()
def get_fundamental_analysis(symbol: str, market: str | None = None) -> FundamentalAnalysis:
    """Analyse valuation, profitability, leverage, and growth fundamentals, returning a
    quality score and observations for an NSE/BSE stock.
    """
    try:
        data = provider.load_stock(symbol, preferred_market=market)
        return fundamental_mod.analyze(data)
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from exc


@mcp.tool()
def get_risk_analysis(symbol: str, market: str | None = None) -> RiskAnalysis:
    """Compute risk metrics — annualised volatility, beta (vs NIFTY 50), max drawdown,
    Sharpe ratio, historical VaR, and a liquidity read — for an NSE/BSE stock.
    """
    try:
        data = provider.load_stock(symbol, preferred_market=market)
        bench = market_mod.benchmark_returns()
        return risk_mod.analyze(data, benchmark_returns=bench)
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from exc


@mcp.tool()
def get_market_context() -> MarketContext:
    """Return the current domestic and global market backdrop: India VIX, NIFTY 50 and
    SENSEX moves, USD/INR, S&P 500, crude oil, and gold, with a risk-on/off read.
    """
    try:
        return market_mod.get_context()
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from exc


@mcp.tool()
def analyze_stock(symbol: str, market: str | None = None) -> FullAnalysis:
    """Run the full analysis pipeline for an NSE/BSE stock and return one consolidated
    report: quote, technical, fundamental, risk, market context, recent news, and a
    structured forward *outlook* (bias + scenarios, not a prediction).

    This is the primary tool. Use the returned 'outlook' as raw material for a forecast
    and always present the 'disclaimer' to the user.

    Args:
        symbol: Stock name or ticker, e.g. 'RELIANCE', 'TCS', 'INFY.NS'.
        market: Optional 'NSE' or 'BSE'.
    """
    try:
        data = provider.load_stock(symbol, preferred_market=market)

        quote = synthesis.build_quote(data)
        technical = technical_mod.analyze(data)
        fundamental = fundamental_mod.analyze(data)
        bench = market_mod.benchmark_returns()
        risk = risk_mod.analyze(data, benchmark_returns=bench)
        context = market_mod.get_context()
        news = _parse_news(data.news)
        outlook = synthesis.build_outlook(technical, fundamental, risk, context)
        recommendation = synthesis.build_recommendation(outlook, technical, fundamental, risk)

        return FullAnalysis(
            quote=quote,
            technical=technical,
            fundamental=fundamental,
            risk=risk,
            market_context=context,
            news=news,
            outlook=outlook,
            recommendation=recommendation,
            disclaimer=DISCLAIMER,
        )
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from exc


def main() -> None:
    """Console-script entry point. Serves over stdio (the standard MCP transport)."""
    log.info("Starting stock-analysis MCP server (stdio transport)")
    mcp.run()


if __name__ == "__main__":
    main()
