# stock-analysis-mcp

A **production-grade MCP server** for fundamental, technical, and risk analysis of Indian
(**NSE / BSE**) stocks — with live market context and a structured, honest forward *outlook*.

Built for use inside any MCP client (Claude Desktop, Claude Code, etc.). You give it a
stock name; it returns typed, explainable analysis that an LLM can reason over and present.

> ⚠️ **Not investment advice.** Every response carries a disclaimer. This tool is for
> education and information only. Consult a SEBI-registered adviser before investing.

---

## What it does

| Tool | Purpose |
|------|---------|
| `analyze_stock` | **Primary tool.** Full report: quote + technical + fundamental + risk + market context + news + forward outlook + an algorithmic rating. |
| `get_quote` | Current price snapshot. |
| `get_technical_analysis` | SMA/EMA, RSI, MACD, Bollinger, ADX, Stochastic, ATR, support/resistance + explainable score. |
| `get_fundamental_analysis` | Valuation, profitability, leverage, growth + quality score. |
| `get_risk_analysis` | Annualised volatility, beta (vs NIFTY 50), max drawdown, Sharpe, historical VaR, liquidity. |
| `get_market_context` | India VIX, NIFTY/SENSEX, USD/INR, S&P 500, crude, gold + risk-on/off read. |

### Design principles

- **Explainable, not black-box.** Scores come from a transparent weighted rules engine;
  every verdict ships with the human-readable `signals` / `observations` that produced it.
- **Honest forecasting.** The `outlook` gives a *bias* and *scenarios* (base/bull/bear),
  never a fabricated price target. Prediction narrative is left to the calling LLM.
- **Algorithmic rating, not advice.** The `recommendation` maps the blended score onto a
  `STRONG_BUY … SELL` scale with a confidence level — a transparent, non-personalised
  signal (the same for every user), *not* investment advice.
- **Resilient data layer.** Retries with exponential backoff, TTL caching to respect
  yfinance rate limits, graceful degradation when individual fields/instruments fail.
- **Typed contract.** Every tool returns a Pydantic model → predictable structured JSON.

---

## Architecture

```
src/stock_analysis_mcp/
├── server.py            # FastMCP tools (orchestration only)   ── presentation
├── cli.py               # `stock-analysis` terminal command    ── presentation
├── config.py            # env-driven settings (SAM_* vars)
├── cache.py             # thread-safe TTL cache
├── models.py            # Pydantic response contract (incl. Recommendation)
├── data/
│   ├── tickers.py       # NSE/BSE ↔ Yahoo (.NS/.BO) resolution
│   └── provider.py      # yfinance wrapper: retries, caching, normalisation
└── analysis/
    ├── indicators.py    # pure indicator math (no pandas-ta dependency)
    ├── technical.py     # trend/momentum scoring
    ├── fundamental.py   # quality scoring
    ├── risk.py          # volatility / beta / drawdown / VaR / Sharpe
    ├── market.py        # macro dashboard + NIFTY benchmark for beta
    └── synthesis.py     # quote snapshot + blended outlook + rating
webui/app.py             # local Flask test dashboard            ── presentation
```

The layers are strictly separated: **all network access lives in `data/`**, so the entire
`analysis/` layer is pure and unit-tested offline. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full end-to-end walkthrough.

---

## Setup

Requires Python 3.10+.

```bash
cd stock-analysis-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"        # dev = tests/lint; ui = the web dashboard
```

Copy `.env.example` → `.env` to tune caching, retries, default market, etc. (all optional).

### Run the tests

```bash
pytest
```

### Run the server (stdio)

```bash
stock-analysis-mcp          # console script
# or
python -m stock_analysis_mcp.server
```

### Use the standalone CLI (no MCP client, no LLM needed)

The `stock-analysis` command runs the full pipeline from your terminal. Its only
external need is internet access for the yfinance data feed.

```bash
stock-analysis RELIANCE              # full colour report
stock-analysis TCS --market BSE      # pick the exchange
stock-analysis INFY --section risk   # just one section
stock-analysis INFY --json           # machine-readable JSON (pipe to jq)
stock-analysis --help
```

Colour auto-disables when piped or when `NO_COLOR` is set, so `--json` output stays clean.

### Run the web dashboard (local browser UI)

```bash
python webui/app.py                  # → http://127.0.0.1:5001
python webui/app.py --port 5002      # if 5001 is busy (or set SAM_WEBUI_PORT)
```

A single-page dashboard: enter a stock, pick NSE/BSE, and get the full report with the
rating shown as a badge. Runs entirely locally. See [USAGE.md](USAGE.md) for a
non-developer walkthrough.

---

## Register with an MCP client

### Claude Desktop / Claude Code

Add to your MCP config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "stock-analysis": {
      "command": "/absolute/path/to/stock-analysis-mcp/.venv/bin/stock-analysis-mcp",
      "env": {
        "SAM_DEFAULT_MARKET": "NSE",
        "SAM_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Then ask: *"Analyze RELIANCE"* or *"Give me a risk analysis of INFY."*

### Quick smoke test with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector stock-analysis-mcp
```

---

## Example (shape of `analyze_stock` output)

```jsonc
{
  "quote":      { "symbol": "RELIANCE.NS", "price": 1234.5, "change_pct": 0.8, ... },
  "technical":  { "signal": "bullish", "score": 42.0, "rsi_14": 58.3, "trend": "up", "signals": [...] },
  "fundamental":{ "verdict": "healthy", "score": 28.0, "pe_ratio": 24.1, "roe": 12.4, ... },
  "risk":       { "risk_level": "moderate", "annualised_volatility": 0.27, "beta": 1.1, ... },
  "market_context": { "sentiment": "risk_on", "india_vix": 12.4, "nifty_50_change_pct": 0.5, ... },
  "outlook":    { "bias": "cautiously_bullish", "composite_score": 36.0, "key_risks": [...], "scenarios": [...] },
  "recommendation": { "rating": "BUY", "stance": "positive", "confidence": "high", "composite_score": 36.0, "rationale": [...] },
  "disclaimer": "..."
}
```

The `recommendation` is an **algorithmic, non-personalised rating** (`STRONG_BUY` / `BUY` /
`HOLD` / `REDUCE` / `SELL`) derived from the blended score and tempered by risk — a
transparent signal, **not** investment advice.

---

## Limitations & production notes

- **Data source is yfinance** (free, unofficial). Great for an MVP; it can rate-limit or
  break without notice. For SLA-backed production, swap `data/provider.py` for a paid
  provider (Financial Modeling Prep, Polygon, etc.) — the analysis layer is unaffected.
- Fundamentals for some Indian listings are sparse in yfinance; rules skip missing inputs.
- The cache is process-local. For a multi-worker deployment, back it with Redis.
- This is **decision-support, not a signal service.** No auto-trading, no price targets.
