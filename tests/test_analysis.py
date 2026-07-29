"""Behavioural tests for the analysis layer using synthetic, offline StockData."""

from __future__ import annotations

import pytest

from stock_analysis_mcp.analysis import fundamental, risk, synthesis, technical
from stock_analysis_mcp.errors import InsufficientHistoryError
from stock_analysis_mcp.models import MarketContext


def test_technical_uptrend_is_bullish(uptrend_data):
    ta = technical.analyze(uptrend_data)
    assert ta.signal == "bullish"
    assert ta.score > 20
    assert ta.trend in ("up", "strong_up")
    assert ta.last_close is not None
    assert ta.support < ta.resistance


def test_technical_downtrend_is_bearish(downtrend_data):
    ta = technical.analyze(downtrend_data)
    assert ta.signal == "bearish"
    assert ta.score < -20
    assert ta.trend in ("down", "strong_down")


def test_technical_requires_history():
    import pandas as pd

    from stock_analysis_mcp.data.provider import StockData

    tiny = StockData(resolved_symbol="X.NS", history=pd.DataFrame())
    with pytest.raises(InsufficientHistoryError):
        technical.analyze(tiny)


def test_fundamental_strong_company(uptrend_data):
    fa = fundamental.analyze(uptrend_data)
    assert fa.score > 15
    assert fa.verdict in ("strong", "healthy")
    assert fa.roe == pytest.approx(21.0, abs=0.1)


def test_fundamental_weak_company(downtrend_data):
    fa = fundamental.analyze(downtrend_data)
    assert fa.score < 0
    assert fa.verdict in ("weak", "mixed")


def test_risk_metrics_present(uptrend_data):
    ra = risk.analyze(uptrend_data)
    assert ra.annualised_volatility is not None
    assert ra.max_drawdown is not None and ra.max_drawdown <= 0
    assert ra.value_at_risk_95 is not None
    assert ra.risk_level in ("low", "moderate", "high", "very_high")


def test_outlook_blends_and_disclaims(uptrend_data):
    ta = technical.analyze(uptrend_data)
    fa = fundamental.analyze(uptrend_data)
    ra = risk.analyze(uptrend_data)
    mc = MarketContext(sentiment="neutral")
    outlook = synthesis.build_outlook(ta, fa, ra, mc)

    assert -100 <= outlook.composite_score <= 100
    assert outlook.bias in (
        "bullish",
        "cautiously_bullish",
        "neutral",
        "cautiously_bearish",
        "bearish",
    )
    assert outlook.disclaimer
    assert len(outlook.scenarios) == 3


def test_quote_builds_from_history(uptrend_data):
    q = synthesis.build_quote(uptrend_data)
    assert q.symbol == "TEST.NS"
    assert q.currency == "INR"
    assert q.price is not None


def _recommend(data):
    ta = technical.analyze(data)
    fa = fundamental.analyze(data)
    ra = risk.analyze(data)
    mc = MarketContext(sentiment="neutral")
    outlook = synthesis.build_outlook(ta, fa, ra, mc)
    return synthesis.build_recommendation(outlook, ta, fa, ra), ta, fa, ra


def test_recommendation_positive_for_uptrend(uptrend_data):
    rec, *_ = _recommend(uptrend_data)
    assert rec.rating in ("STRONG_BUY", "BUY", "HOLD")
    assert rec.stance in ("positive", "neutral")
    assert rec.confidence in ("high", "medium", "low")
    assert rec.rationale
    assert rec.disclaimer


def test_recommendation_negative_for_downtrend(downtrend_data):
    rec, *_ = _recommend(downtrend_data)
    assert rec.rating in ("SELL", "REDUCE", "HOLD")
    assert rec.stance in ("negative", "cautious", "neutral")


def test_recommendation_valid_rating_values(uptrend_data):
    rec, *_ = _recommend(uptrend_data)
    assert rec.rating in ("STRONG_BUY", "BUY", "HOLD", "REDUCE", "SELL")
