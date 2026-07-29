"""Command-line interface for stock analysis — runs fully standalone (no MCP, no LLM).

Usage:
    stock-analysis RELIANCE
    stock-analysis TCS --market BSE
    stock-analysis INFY --json
    stock-analysis NIFTY --market NSE --section technical

Only needs internet access for the yfinance data feed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .config import get_settings
from .errors import StockAnalysisError
from .logging_config import configure_logging
from .models import FullAnalysis

# ---- ANSI colour helpers (auto-disabled when output is not a TTY or NO_COLOR set) ----

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def bold(s: str) -> str:
    return _c(s, "1")


def dim(s: str) -> str:
    return _c(s, "2")


def green(s: str) -> str:
    return _c(s, "32")


def red(s: str) -> str:
    return _c(s, "31")


def yellow(s: str) -> str:
    return _c(s, "33")


def cyan(s: str) -> str:
    return _c(s, "36")


# Map a verdict/signal/rating label to a colour function (case-insensitive lookup).
_POSITIVE = {"bullish", "cautiously_bullish", "up", "strong_up", "strong", "healthy",
             "risk_on", "low", "strong_buy", "buy", "positive"}
_NEGATIVE = {"bearish", "cautiously_bearish", "down", "strong_down", "weak",
             "risk_off", "high", "very_high", "sell", "reduce", "negative", "cautious"}


def _tag(label: str) -> str:
    key = label.lower()
    pretty = label.replace("_", " ").upper()
    if key in _POSITIVE:
        return green(pretty)
    if key in _NEGATIVE:
        return red(pretty)
    return yellow(pretty)


def _conf_tag(confidence: str) -> str:
    """Confidence has its own colour scale (high = good), separate from risk levels."""
    fn = {"high": green, "medium": yellow, "low": red}.get(confidence, yellow)
    return fn(confidence.upper())


def _fmt(value, suffix: str = "", dash: str = "—") -> str:
    if value is None:
        return dim(dash)
    return f"{value}{suffix}"


def _kv(key: str, value: str, width: int = 22) -> str:
    return f"  {dim(key.ljust(width))} {value}"


def _rule(title: str) -> str:
    return bold(cyan(f"\n{title}\n" + "─" * max(len(title), 12)))


def _pct(value, digits: int = 1) -> str:
    if value is None:
        return dim("—")
    return f"{value * 100:.{digits}f}%"


def render_text(a: FullAnalysis) -> str:
    q = a.quote
    lines: list[str] = []

    cur = "₹" if q.currency == "INR" else f"{q.currency} "
    change = q.change_pct
    chg_str = dim("—")
    if change is not None:
        arrow = "▲" if change >= 0 else "▼"
        chg_str = (green if change >= 0 else red)(f"{arrow} {change:+.2f}%")
    lines.append("")
    lines.append(f"{bold(q.symbol)}  {dim('·')}  {q.name or ''}")
    lines.append(f"{bold(cur + _fmt(q.price))}   {chg_str}   {dim('as of ' + str(q.as_of))}")

    # Recommendation (headline)
    rec = a.recommendation
    lines.append("")
    lines.append(
        f"  {bold('RATING:')} {_tag(rec.rating)}   "
        f"{dim('confidence')} {_conf_tag(rec.confidence)}   "
        f"{dim('composite')} {rec.composite_score:+.1f}"
    )

    # Technical
    t = a.technical
    lines.append(_rule("TECHNICAL"))
    lines.append(_kv("Signal / Trend", f"{_tag(t.signal)}  ·  {_tag(t.trend)}  (score {t.score})"))
    lines.append(_kv("Last close", _fmt(t.last_close)))
    lines.append(_kv("RSI (14)", _fmt(t.rsi_14)))
    lines.append(_kv("SMA 50 / 200", f"{_fmt(t.sma_50)} / {_fmt(t.sma_200)}"))
    lines.append(_kv("MACD / signal", f"{_fmt(t.macd)} / {_fmt(t.macd_signal)}"))
    lines.append(_kv("ADX (14)", _fmt(t.adx_14)))
    lines.append(_kv("Support / Resistance", f"{_fmt(t.support)} / {_fmt(t.resistance)}"))
    for s in t.signals:
        lines.append(dim(f"    • {s}"))

    # Fundamental
    f = a.fundamental
    lines.append(_rule("FUNDAMENTAL"))
    lines.append(_kv("Verdict", f"{_tag(f.verdict)}  (score {f.score})  ·  {_fmt(f.sector)}"))
    lines.append(_kv("P/E (forward)", f"{_fmt(f.pe_ratio)} ({_fmt(f.forward_pe)})"))
    lines.append(_kv("Price / Book", _fmt(f.price_to_book)))
    lines.append(_kv("ROE", _fmt(f.roe, "%")))
    lines.append(_kv("Net margin", _fmt(f.profit_margin, "%")))
    lines.append(_kv("Debt / Equity", _fmt(f.debt_to_equity)))
    growth = f"{_fmt(f.revenue_growth, '%')} / {_fmt(f.earnings_growth, '%')}"
    lines.append(_kv("Rev / Earn growth", growth))
    for o in f.observations:
        lines.append(dim(f"    • {o}"))

    # Risk
    r = a.risk
    lines.append(_rule("RISK"))
    lines.append(_kv("Risk level", _tag(r.risk_level)))
    lines.append(_kv("Annualised vol", _pct(r.annualised_volatility)))
    lines.append(_kv("Beta (vs NIFTY)", _fmt(r.beta)))
    lines.append(_kv("Max drawdown", _pct(r.max_drawdown)))
    lines.append(_kv("Sharpe ratio", _fmt(r.sharpe_ratio)))
    lines.append(_kv("1-day VaR (95%)", _pct(r.value_at_risk_95)))
    for o in r.observations:
        lines.append(dim(f"    • {o}"))

    # Market context
    m = a.market_context
    lines.append(_rule("MARKET CONTEXT"))
    lines.append(_kv("Sentiment", _tag(m.sentiment)))
    lines.append(_kv("India VIX", _fmt(m.india_vix)))
    indices = f"{_fmt(m.nifty_50_change_pct, '%')} / {_fmt(m.sensex_change_pct, '%')}"
    lines.append(_kv("NIFTY 50 / SENSEX", indices))
    lines.append(_kv("USD / INR", _fmt(m.usd_inr)))
    lines.append(_kv("S&P 500", _fmt(m.sp500_change_pct, "%")))
    commodities = f"{_fmt(m.crude_oil_change_pct, '%')} / {_fmt(m.gold_change_pct, '%')}"
    lines.append(_kv("Crude / Gold", commodities))

    # Outlook
    o = a.outlook
    lines.append(_rule("OUTLOOK"))
    lines.append(_kv("Bias", f"{_tag(o.bias)}  (composite {o.composite_score})"))
    lines.append(_kv("Horizon", o.time_horizon))
    lines.append("  " + green("Positives:"))
    for p in o.key_positives:
        lines.append(dim(f"    + {p}"))
    lines.append("  " + red("Risks:"))
    for k in o.key_risks:
        lines.append(dim(f"    - {k}"))
    lines.append("  " + cyan("Scenarios:"))
    for sc in o.scenarios:
        lines.append(dim(f"    → {sc}"))

    # Recommendation (detail)
    rec = a.recommendation
    lines.append(_rule("RECOMMENDATION"))
    lines.append(_kv("Rating", f"{_tag(rec.rating)}  ·  {_tag(rec.stance)}"))
    lines.append(_kv("Confidence", _conf_tag(rec.confidence)))
    lines.append("  " + dim("Why:"))
    for reason in rec.rationale:
        lines.append(dim(f"    • {reason}"))
    lines.append("  " + yellow("This is an automated signal, not personalised advice."))

    # News
    if a.news:
        lines.append(_rule("RECENT NEWS"))
        for n in a.news:
            src = dim(f" ({n.publisher})") if n.publisher else ""
            lines.append(f"  • {n.title}{src}")

    lines.append("")
    lines.append(yellow("⚠ " + a.disclaimer))
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    p = argparse.ArgumentParser(
        prog="stock-analysis",
        description="Standalone fundamental, technical & risk analysis for NSE/BSE stocks.",
        epilog="Informational only — NOT investment advice.",
    )
    p.add_argument("symbol", help="Stock name or ticker, e.g. RELIANCE, TCS, INFY.NS")
    p.add_argument(
        "-m", "--market",
        default=settings.default_market,
        choices=["NSE", "BSE", "nse", "bse"],
        help=f"Preferred exchange (default: {settings.default_market}).",
    )
    p.add_argument(
        "-s", "--section",
        choices=["all", "technical", "fundamental", "risk", "market", "outlook",
                 "recommendation"],
        default="all",
        help="Limit output to one section (default: all). JSON output is always full.",
    )
    p.add_argument("--json", action="store_true", help="Emit raw JSON instead of a report.")
    p.add_argument("-v", "--verbose", action="store_true", help="Enable INFO logging to stderr.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _render_section(a: FullAnalysis, section: str) -> str:
    """Render only the requested section by reusing the full renderer's building blocks."""
    if section == "all":
        return render_text(a)
    # For a single section, build a focused view via the model's sub-object JSON.
    sub = {
        "technical": a.technical,
        "fundamental": a.fundamental,
        "risk": a.risk,
        "market": a.market_context,
        "outlook": a.outlook,
        "recommendation": a.recommendation,
    }[section]
    header = _rule(section.upper())
    body = "\n".join(_kv(k, str(v)) for k, v in sub.model_dump().items())
    return f"{header}\n{body}\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging("INFO" if args.verbose else "ERROR")

    # Import here so --help/--version stay instant (avoids loading pandas/yfinance).
    from .analysis import fundamental as fundamental_mod
    from .analysis import market as market_mod
    from .analysis import risk as risk_mod
    from .analysis import synthesis
    from .analysis import technical as technical_mod
    from .data import provider
    from .server import _parse_news
    from .utils import DISCLAIMER

    try:
        data = provider.load_stock(args.symbol, preferred_market=args.market.upper())

        # Build in dependency order (outlook needs the other pillars).
        quote = synthesis.build_quote(data)
        technical = technical_mod.analyze(data)
        fundamental = fundamental_mod.analyze(data)
        risk = risk_mod.analyze(data, benchmark_returns=market_mod.benchmark_returns())
        context = market_mod.get_context()
        outlook = synthesis.build_outlook(technical, fundamental, risk, context)
        recommendation = synthesis.build_recommendation(outlook, technical, fundamental, risk)
        report = FullAnalysis(
            quote=quote,
            technical=technical,
            fundamental=fundamental,
            risk=risk,
            market_context=context,
            news=_parse_news(data.news),
            outlook=outlook,
            recommendation=recommendation,
            disclaimer=DISCLAIMER,
        )
    except StockAnalysisError as exc:
        print(red(f"Error: {exc}"), file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(red(f"Unexpected error: {exc}"), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.model_dump(), indent=2, default=str))
    else:
        print(_render_section(report, args.section))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
