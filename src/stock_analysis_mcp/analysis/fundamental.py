"""Fundamental analysis from provider metadata, distilled into a quality score.

yfinance's ``info`` dict is inconsistent across listings (some Indian names lack certain
fields), so every read is defensive and every rule is skipped when its inputs are missing.
The score reflects only the metrics that were actually available.
"""

from __future__ import annotations

from ..data.provider import StockData
from ..models import FundamentalAnalysis
from ..utils import clamp, pct, round_opt, safe_float


def _verdict(score: float) -> str:
    if score >= 45:
        return "strong"
    if score >= 15:
        return "healthy"
    if score >= -15:
        return "mixed"
    return "weak"


def analyze(data: StockData) -> FundamentalAnalysis:
    info = data.info
    g = lambda k: safe_float(info.get(k))  # noqa: E731 - terse local reader

    market_cap = g("marketCap")
    pe = g("trailingPE")
    fwd_pe = g("forwardPE")
    peg = g("pegRatio") or g("trailingPegRatio")
    pb = g("priceToBook")
    div_yield = g("dividendYield")
    roe = g("returnOnEquity")
    profit_margin = g("profitMargins")
    op_margin = g("operatingMargins")
    dte = g("debtToEquity")
    current_ratio = g("currentRatio")
    rev_growth = g("revenueGrowth")
    earn_growth = g("earningsGrowth") or g("earningsQuarterlyGrowth")
    wk_high = g("fiftyTwoWeekHigh")
    wk_low = g("fiftyTwoWeekLow")

    score = 0.0
    obs: list[str] = []

    # Valuation (lower is cheaper — but negative P/E means losses).
    if pe is not None:
        if pe <= 0:
            score -= 10
            obs.append("Negative trailing P/E (company is loss-making on a TTM basis).")
        elif pe < 15:
            score += 10
            obs.append(f"Low P/E of {pe:.1f} (attractively valued vs. broad market).")
        elif pe < 30:
            score += 3
            obs.append(f"Moderate P/E of {pe:.1f}.")
        else:
            score -= 6
            obs.append(f"High P/E of {pe:.1f} (rich valuation; priced for growth).")

    if peg is not None and peg > 0:
        if peg < 1:
            score += 8
            obs.append(f"PEG of {peg:.2f} (<1 suggests growth is under-priced).")
        elif peg > 2:
            score -= 5
            obs.append(f"PEG of {peg:.2f} (>2 suggests growth may be over-priced).")

    if pb is not None and pb > 0:
        if pb < 3:
            score += 4
        elif pb > 8:
            score -= 4
            obs.append(f"High price-to-book of {pb:.1f}.")

    # Profitability.
    if roe is not None:
        if roe >= 0.18:
            score += 12
            obs.append(f"Strong ROE of {roe * 100:.1f}% (efficient use of equity).")
        elif roe >= 0.10:
            score += 5
        elif roe < 0:
            score -= 10
            obs.append("Negative ROE (destroying shareholder equity).")

    if profit_margin is not None:
        if profit_margin >= 0.15:
            score += 8
            obs.append(f"Healthy net margin of {profit_margin * 100:.1f}%.")
        elif profit_margin < 0:
            score -= 8
            obs.append("Negative net margin (unprofitable).")

    # Leverage / solvency. yfinance reports debtToEquity as a percentage (e.g. 45 == 0.45x).
    if dte is not None:
        dte_ratio = dte / 100.0 if dte > 5 else dte
        if dte_ratio <= 0.5:
            score += 8
            obs.append(f"Conservative leverage (D/E ~ {dte_ratio:.2f}).")
        elif dte_ratio <= 1.0:
            score += 2
        elif dte_ratio > 2.0:
            score -= 10
            obs.append(f"High leverage (D/E ~ {dte_ratio:.2f}); balance-sheet risk.")

    if current_ratio is not None:
        if current_ratio >= 1.5:
            score += 4
        elif current_ratio < 1.0:
            score -= 6
            obs.append(f"Current ratio {current_ratio:.2f} (<1; short-term liquidity strain).")

    # Growth.
    if rev_growth is not None:
        if rev_growth >= 0.15:
            score += 8
            obs.append(f"Revenue growing {rev_growth * 100:.1f}% YoY.")
        elif rev_growth < 0:
            score -= 6
            obs.append(f"Revenue contracting {rev_growth * 100:.1f}% YoY.")

    if earn_growth is not None:
        if earn_growth >= 0.15:
            score += 8
            obs.append(f"Earnings growing {earn_growth * 100:.1f}% YoY.")
        elif earn_growth < 0:
            score -= 6
            obs.append(f"Earnings contracting {earn_growth * 100:.1f}% YoY.")

    if not obs:
        obs.append("Limited fundamental data available for this listing from the provider.")

    score = clamp(score, -100.0, 100.0)

    return FundamentalAnalysis(
        symbol=data.resolved_symbol,
        name=data.long_name,
        sector=info.get("sector"),
        industry=info.get("industry"),
        score=round(score, 1),
        verdict=_verdict(score),
        market_cap=market_cap,
        pe_ratio=round_opt(pe),
        forward_pe=round_opt(fwd_pe),
        peg_ratio=round_opt(peg, 3),
        price_to_book=round_opt(pb),
        dividend_yield=pct(div_yield) if div_yield and div_yield < 1 else round_opt(div_yield),
        roe=pct(roe),
        profit_margin=pct(profit_margin),
        operating_margin=pct(op_margin),
        debt_to_equity=round_opt(dte),
        current_ratio=round_opt(current_ratio),
        revenue_growth=pct(rev_growth),
        earnings_growth=pct(earn_growth),
        fifty_two_week_high=round_opt(wk_high),
        fifty_two_week_low=round_opt(wk_low),
        observations=obs,
    )
