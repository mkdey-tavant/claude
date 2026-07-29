"""Cross-cut synthesis: build the quote snapshot and the blended forward outlook.

The outlook deliberately produces a *bias and scenarios*, never a price target or a
"will go up" prediction. It blends the technical and fundamental scores, then tempers the
language using the risk level and market sentiment. The heavy lifting of turning this into
prose is left to the calling LLM — this gives it honest, structured raw material.
"""

from __future__ import annotations

from ..data.provider import StockData
from ..models import (
    FundamentalAnalysis,
    MarketContext,
    Outlook,
    Quote,
    Recommendation,
    RiskAnalysis,
    TechnicalAnalysis,
)
from ..utils import DISCLAIMER, round_opt, safe_float


def build_quote(data: StockData) -> Quote:
    info = data.info
    hist = data.history

    price = safe_float(info.get("currentPrice")) or safe_float(info.get("regularMarketPrice"))
    prev_close = safe_float(info.get("previousClose"))

    as_of = None
    if hist is not None and not hist.empty:
        if price is None:
            price = float(hist["Close"].iloc[-1])
        if prev_close is None and len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
        as_of = hist.index[-1].date().isoformat()

    change_pct = None
    if price is not None and prev_close:
        change_pct = round((price - prev_close) / prev_close * 100.0, 2)

    return Quote(
        symbol=data.resolved_symbol,
        name=data.long_name,
        currency=data.currency,
        price=round_opt(price),
        previous_close=round_opt(prev_close),
        change_pct=change_pct,
        day_high=round_opt(safe_float(info.get("dayHigh"))),
        day_low=round_opt(safe_float(info.get("dayLow"))),
        volume=safe_float(info.get("volume")),
        market_cap=safe_float(info.get("marketCap")),
        as_of=as_of,
    )


def _bias_label(score: float) -> str:
    if score >= 40:
        return "bullish"
    if score >= 15:
        return "cautiously_bullish"
    if score <= -40:
        return "bearish"
    if score <= -15:
        return "cautiously_bearish"
    return "neutral"


def build_outlook(
    technical: TechnicalAnalysis,
    fundamental: FundamentalAnalysis,
    risk: RiskAnalysis,
    market: MarketContext,
) -> Outlook:
    # Blend: technicals drive short-term bias, fundamentals anchor the medium term.
    composite = 0.55 * technical.score + 0.45 * fundamental.score

    # Temper for macro backdrop.
    if market.sentiment == "risk_off":
        composite -= 8
    elif market.sentiment == "risk_on":
        composite += 5

    composite = max(-100.0, min(100.0, composite))
    bias = _bias_label(composite)

    positives: list[str] = []
    risks: list[str] = []

    if technical.signal == "bullish":
        positives.append("Technical structure is constructive (trend + momentum aligned).")
    elif technical.signal == "bearish":
        risks.append("Technical structure is weak (trend + momentum against the stock).")

    if fundamental.verdict in ("strong", "healthy"):
        positives.append(f"Fundamentals look {fundamental.verdict}.")
    elif fundamental.verdict == "weak":
        risks.append("Fundamentals look weak.")

    if risk.risk_level in ("high", "very_high"):
        risks.append(f"Elevated risk profile ({risk.risk_level.replace('_', ' ')}).")
    if risk.max_drawdown is not None and risk.max_drawdown <= -0.4:
        risks.append("History shows large drawdowns — position sizing matters.")
    if market.sentiment == "risk_off":
        risks.append("Broad market is risk-off, a headwind for most equities.")
    elif market.sentiment == "risk_on":
        positives.append("Supportive risk-on market backdrop.")

    # Pull a couple of the most salient per-pillar notes forward.
    if technical.signal == "bullish":
        positives.extend(technical.signals[:1])
    if fundamental.verdict in ("strong", "healthy"):
        positives.extend(fundamental.observations[:1])

    scenarios = [
        f"Base case: if the {market.sentiment.replace('_', ' ')} backdrop holds, the stock likely "
        f"tracks its current {technical.trend.replace('_', ' ')} tendency near-term.",
        f"Bull case: a break above resistance (~{technical.resistance}) with volume would "
        f"strengthen the {bias.replace('_', ' ')} case.",
        f"Bear case: a breakdown below support (~{technical.support}) would invalidate the "
        f"setup and raise downside risk.",
    ]

    return Outlook(
        composite_score=round(composite, 1),
        bias=bias,
        time_horizon="short-to-medium term (weeks to a few months)",
        key_positives=positives or ["No standout positives from the current data."],
        key_risks=risks or ["No standout risks flagged, but all equity holdings carry risk."],
        scenarios=scenarios,
        disclaimer=DISCLAIMER,
    )


# Rating tiers, ordered from most negative (0) to most positive (4). Indexing by tier lets
# us cleanly "downgrade" a rating by a notch when risk is elevated.
_RATING_TIERS = ["SELL", "REDUCE", "HOLD", "BUY", "STRONG_BUY"]
_STANCE_BY_RATING = {
    "STRONG_BUY": "positive",
    "BUY": "positive",
    "HOLD": "neutral",
    "REDUCE": "cautious",
    "SELL": "negative",
}


def _tier_from_composite(composite: float) -> int:
    if composite >= 50:
        return 4  # STRONG_BUY
    if composite >= 20:
        return 3  # BUY
    if composite > -20:
        return 2  # HOLD
    if composite > -50:
        return 1  # REDUCE
    return 0  # SELL


def _confidence(technical: TechnicalAnalysis, fundamental: FundamentalAnalysis) -> str:
    """High when the two pillars agree strongly; low when they pull in opposite directions."""
    t, f = technical.score, fundamental.score
    same_direction = (t >= 0) == (f >= 0)
    strong = abs(t) >= 20 and abs(f) >= 20
    if same_direction and strong:
        return "high"
    if not same_direction and abs(t - f) >= 40:
        return "low"
    return "medium"


def build_recommendation(
    outlook: Outlook,
    technical: TechnicalAnalysis,
    fundamental: FundamentalAnalysis,
    risk: RiskAnalysis,
) -> Recommendation:
    """Map the blended composite onto a conventional rating scale.

    This is an *algorithmic, non-personalised* signal. It starts from the outlook's
    composite score, then applies a risk-aware safety adjustment: a very-high-risk name is
    downgraded one notch (never below SELL) so the rating never reads more aggressive than
    the risk justifies.
    """
    composite = outlook.composite_score
    tier = _tier_from_composite(composite)

    rationale: list[str] = [
        f"Composite score {composite:+.1f} (technical {technical.score:+.0f}, "
        f"fundamental {fundamental.score:+.0f})."
    ]

    # Risk-aware downgrade: don't hand out a bullish rating on a very risky name.
    if risk.risk_level == "very_high" and tier > 0:
        tier -= 1
        rationale.append("Downgraded one notch due to very high risk (volatility/drawdown).")
    elif risk.risk_level == "high" and tier == 4:
        tier -= 1
        rationale.append("Trimmed from Strong Buy to Buy given the elevated risk profile.")

    rating = _RATING_TIERS[tier]
    confidence = _confidence(technical, fundamental)

    if confidence == "low":
        rationale.append(
            "Low confidence: technical and fundamental signals disagree — treat with caution."
        )
    elif confidence == "high":
        rationale.append("High confidence: technical and fundamental signals align.")

    # Surface the single most relevant driver from each pillar.
    if technical.signals:
        rationale.append(f"Technical: {technical.signals[0]}")
    if fundamental.observations:
        rationale.append(f"Fundamental: {fundamental.observations[0]}")

    return Recommendation(
        rating=rating,
        stance=_STANCE_BY_RATING[rating],
        confidence=confidence,
        composite_score=composite,
        rationale=rationale,
        disclaimer=DISCLAIMER,
    )
