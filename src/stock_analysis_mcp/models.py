"""Pydantic response models. These define the stable, typed contract returned to callers.

Every tool returns one of these (serialised to a dict by FastMCP). Keeping the schema
explicit means the calling LLM receives predictable, well-labelled fields to reason over.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Quote(BaseModel):
    symbol: str
    name: str
    currency: str
    price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    as_of: str | None = Field(default=None, description="Date of the latest close (ISO).")


class TechnicalAnalysis(BaseModel):
    symbol: str
    trend: str = Field(description="Overall trend: strong_up | up | sideways | down | strong_down")
    signal: str = Field(description="Composite bias: bullish | neutral | bearish")
    score: float = Field(description="Technical score from -100 (bearish) to +100 (bullish).")
    last_close: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_20: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    bollinger_percent_b: float | None = None
    adx_14: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None
    stochastic_k: float | None = None
    atr_14: float | None = None
    support: float | None = None
    resistance: float | None = None
    signals: list[str] = Field(default_factory=list, description="Human-readable observations.")


class FundamentalAnalysis(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    score: float = Field(description="Fundamental quality score from -100 to +100.")
    verdict: str = Field(description="strong | healthy | mixed | weak")
    market_cap: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    observations: list[str] = Field(default_factory=list)


class RiskAnalysis(BaseModel):
    symbol: str
    risk_level: str = Field(description="low | moderate | high | very_high")
    annualised_volatility: float | None = Field(
        default=None, description="Std dev of returns, annualised."
    )
    beta: float | None = None
    max_drawdown: float | None = Field(
        default=None, description="Worst peak-to-trough decline (fraction)."
    )
    sharpe_ratio: float | None = None
    value_at_risk_95: float | None = Field(
        default=None, description="Historical 1-day 95% VaR (fraction)."
    )
    downside_deviation: float | None = None
    liquidity_note: str | None = None
    observations: list[str] = Field(default_factory=list)


class MarketContext(BaseModel):
    as_of: str | None = None
    sentiment: str = Field(description="risk_on | neutral | risk_off")
    india_vix: float | None = None
    nifty_50_change_pct: float | None = None
    sensex_change_pct: float | None = None
    usd_inr: float | None = None
    sp500_change_pct: float | None = None
    crude_oil_change_pct: float | None = None
    gold_change_pct: float | None = None
    observations: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    publisher: str | None = None
    link: str | None = None
    published: str | None = None


class Outlook(BaseModel):
    """A structured, disclaimered synthesis for the calling LLM to build a forecast on."""

    composite_score: float = Field(
        description="Blended technical+fundamental score, -100..+100."
    )
    bias: str = Field(
        description="bullish | cautiously_bullish | neutral | cautiously_bearish | bearish"
    )
    time_horizon: str = Field(
        description="Horizon the bias applies to, e.g. 'short-to-medium term'."
    )
    key_positives: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    scenarios: list[str] = Field(
        default_factory=list, description="Plausible forward scenarios, not predictions."
    )
    disclaimer: str


class Recommendation(BaseModel):
    """A transparent, rule-based rating derived from the stock's own metrics.

    This is an ALGORITHMIC SIGNAL, identical for every user — not personalised investment
    advice. It maps the blended technical+fundamental composite (tempered by risk and market
    conditions) onto a conventional rating scale, and always states its reasoning.
    """

    rating: str = Field(description="STRONG_BUY | BUY | HOLD | REDUCE | SELL")
    stance: str = Field(description="Plain-word stance: positive | neutral | cautious | negative")
    confidence: str = Field(
        description="How much the technical & fundamental pillars agree: high | medium | low"
    )
    composite_score: float = Field(
        description="The blended score the rating is based on, -100..+100."
    )
    rationale: list[str] = Field(default_factory=list, description="Why this rating was assigned.")
    disclaimer: str


class FullAnalysis(BaseModel):
    """The complete report returned by :func:`analyze_stock`."""

    quote: Quote
    technical: TechnicalAnalysis
    fundamental: FundamentalAnalysis
    risk: RiskAnalysis
    market_context: MarketContext
    news: list[NewsItem] = Field(default_factory=list)
    outlook: Outlook
    recommendation: Recommendation
    disclaimer: str
