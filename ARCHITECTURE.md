# Architecture — Stock Analysis Tool (End to End)

This document explains **how the whole system is built and how data flows through it**,
from the moment you type a stock name to the moment a report appears. It also explains
**how data freshness / "daily refresh" actually works**, and how to turn it into a true
scheduled job if you want that.

> Audience: developers and technically-curious users. No prior context needed.

---

## 1. The big picture in one paragraph

You give the tool a **stock symbol** (e.g. `RELIANCE`). It resolves that to a Yahoo
Finance ticker, downloads the last ~400 days of daily prices plus company fundamentals
and news, runs four independent **analysis engines** (technical, fundamental, risk,
market context) written in plain Python, blends the technical + fundamental scores into a
forward **outlook**, and returns one structured report. That report can be delivered three
ways — a **command-line tool**, a **local web dashboard**, or an **MCP server** — all
sharing the exact same engine. No AI service is involved; the only external dependency is
the free Yahoo Finance data feed.

---

## 2. High-level component diagram

```
        ┌──────────────────────────────────────────────────────────────┐
        │                   HOW YOU INTERACT (pick one)                  │
        │                                                                │
        │   CLI              Web dashboard          MCP server           │
        │   stock-analysis   webui/app.py (Flask)   stock-analysis-mcp   │
        │   cli.py           browser @ :5001        server.py (FastMCP)  │
        └───────────────┬───────────────┬───────────────┬──────────────┘
                        │               │               │
                        └───────────────┼───────────────┘
                                        │  (all three call the same functions)
                                        ▼
        ┌──────────────────────────────────────────────────────────────┐
        │                     ANALYSIS LAYER (pure Python)               │
        │                                                                │
        │  technical.py   fundamental.py   risk.py   market.py           │
        │        └──────────────┬───────────────┘        │              │
        │                indicators.py                synthesis.py       │
        │         (RSI, MACD, SMA, ADX…)      (quote + outlook + rating) │
        └──────────────────────────────┬───────────────────────────────┘
                                        │  needs data
                                        ▼
        ┌──────────────────────────────────────────────────────────────┐
        │                        DATA LAYER                              │
        │                                                                │
        │   tickers.py            provider.py            cache.py        │
        │   (name → .NS/.BO)      (yfinance + retries)   (15-min TTL)    │
        └──────────────────────────────┬───────────────────────────────┘
                                        │  network
                                        ▼
                        ┌───────────────────────────────┐
                        │   Yahoo Finance (free feed)    │
                        │   prices · fundamentals · news │
                        └───────────────────────────────┘

        Cross-cutting (used everywhere): config.py · logging_config.py ·
                                         models.py · errors.py · utils.py
```

**Key architectural rule:** *all network access lives in the data layer.* The analysis
layer is pure — it takes data in and returns numbers out — which is why it can be fully
unit-tested offline.

---

## 3. Technology stack

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3.10+** | Best ecosystem for financial data & math. |
| Market data | **yfinance** | Free, no API key, covers NSE/BSE. |
| Numerical math | **pandas + numpy** | Fast, standard for time-series & indicators. |
| MCP protocol | **`mcp` SDK (FastMCP)** | Official way to expose tools to MCP clients. |
| Data validation / output contract | **Pydantic v2** | Typed, self-documenting, auto-serialises to JSON. |
| Configuration | **pydantic-settings** | 12-factor config via `SAM_*` environment variables. |
| Caching | **cachetools (TTLCache)** | Simple, thread-safe, time-based expiry. |
| Retries | **tenacity** | Exponential backoff for flaky network calls. |
| Web dashboard | **Flask** | Tiny, dependency-light local test UI. |
| Tests / lint | **pytest + ruff** | Fast tests, consistent style. |

---

## 4. The three layers explained

The codebase is deliberately split into three layers with a one-way dependency direction:
**presentation → analysis → data**. Lower layers never import higher ones.

### 4.1 Data layer (`src/stock_analysis_mcp/data/`)

This is the **only** place that touches the network.

- **`tickers.py` — ticker resolution.**
  Turns a human input (`reliance`, `TCS`, `HDFC Bank`, `INFY.NS`) into an ordered list of
  Yahoo candidates. Yahoo suffixes Indian listings with `.NS` (NSE) and `.BO` (BSE), so
  `TCS` on NSE becomes `TCS.NS`. It uppercases, strips junk characters, applies a small
  alias table (e.g. `infosys → INFY`, `SBI → SBIN`), and orders candidates by your
  preferred exchange. It's a *heuristic resolver*, not a full listings database — the
  provider then validates each candidate against real data.

- **`provider.py` — the yfinance wrapper.** The workhorse. It:
  1. Asks `tickers.py` for candidate symbols.
  2. Downloads ~400 days of daily OHLCV (`interval="1d"`, `auto_adjust=True`) — wrapped in
     **tenacity** retries with exponential backoff so a transient network blip doesn't fail
     the whole request.
  3. Fetches company metadata (`info`), quick stats (`fast_info`), and recent `news` —
     each in its own try/except so a partial failure degrades gracefully instead of
     crashing.
  4. Validates the candidate actually corresponds to a live listing.
  5. Packages everything into a single normalised **`StockData`** dataclass.
  6. Wraps the whole thing in the cache (see §6).

- **`cache.py` — the TTL cache.**
  A thread-safe wrapper around `cachetools.TTLCache`. Its `get_or_set(key, producer)`
  returns a cached value or computes it once. Because it computes *while holding a lock*,
  concurrent requests for the same stock won't all hammer Yahoo (no "cache stampede").

### 4.2 Analysis layer (`src/stock_analysis_mcp/analysis/`)

Pure functions: `StockData` in → a typed result model out. No I/O, no globals, no surprises.

- **`indicators.py` — the math primitives.**
  Every technical indicator implemented from first principles (no `pandas-ta` dependency):
  SMA, EMA, RSI (Wilder's smoothing), MACD, Bollinger Bands, ATR, ADX/+DI/−DI, Stochastic,
  support/resistance. Each is a total function returning a Series with `NaN` where a value
  is undefined (e.g. the first 199 days have no 200-day average).

- **`technical.py` — trend & momentum scoring.**
  Runs the indicators and applies a **transparent weighted rules engine**: each rule adds
  or subtracts points to a score clamped to −100…+100, and records a plain-English reason.
  Produces `signal` (bullish/neutral/bearish), `trend`, the score, and the `signals` list.

- **`fundamental.py` — business-quality scoring.**
  Same rules-engine style over valuation (P/E, PEG, P/B), profitability (ROE, margins),
  leverage (debt/equity, current ratio), and growth. Every rule is skipped if its input is
  missing (common for some Indian listings), so the score reflects only available data.
  Produces `verdict` (strong/healthy/mixed/weak) + observations.

- **`risk.py` — risk metrics.**
  Computes annualised volatility, **beta vs NIFTY 50**, max drawdown, Sharpe ratio, and
  historical 1-day 95% Value-at-Risk from the daily return series, plus a liquidity read
  from traded value. Buckets into low/moderate/high/very_high. Risk is *descriptive* — it
  does not feed the composite score, but it tempers the outlook's language.

- **`market.py` — macro backdrop.**
  Fetches index/FX/commodity tickers (India VIX, NIFTY, SENSEX, USD/INR, S&P 500, crude,
  gold) and derives a `risk_on / neutral / risk_off` sentiment. Also exposes
  `benchmark_returns()` — the NIFTY 50 return series used for beta. (This layer *does* fetch
  data, but only via the same cached mechanism.)

- **`synthesis.py` — the blend & the rating.**
  `build_quote()` assembles the price snapshot. `build_outlook()` combines the pillars:
  ```
  composite = 0.55 × technical_score + 0.45 × fundamental_score
  then nudged by market sentiment (risk_off −8, risk_on +5)
  ```
  and maps the result to a `bias` plus base/bull/bear **scenarios** — a *lean*, never a
  price target.
  `build_recommendation()` then turns that composite into an **algorithmic rating**
  (`STRONG_BUY` / `BUY` / `HOLD` / `REDUCE` / `SELL`) with a `confidence` level (how much
  the two pillars agree) and a risk-aware downgrade (a very-high-risk name drops a notch).
  This is a transparent, *non-personalised* signal — the same for every user — **not**
  investment advice.

### 4.3 Presentation layer (three interchangeable front-ends)

All three call the same analysis functions and return/serialise the same Pydantic models.

- **`cli.py`** — the `stock-analysis` command. Formats a coloured terminal report (with the
  rating as a headline), or emits raw JSON (`--json`), or a single section
  (`--section risk`, `--section recommendation`, …).
- **`webui/app.py`** — a Flask app serving a single-page dashboard (default
  `http://127.0.0.1:5001`; override with `--port` or `SAM_WEBUI_PORT`). The browser calls
  `/api/analyze`, which runs the same pipeline and returns JSON that the page renders into
  cards, with the rating shown as a badge in the header.
- **`server.py`** — the FastMCP server (`stock-analysis-mcp`) exposing six tools over stdio
  for any MCP client (Claude Desktop, MCP Inspector, etc.).

### 4.4 Cross-cutting modules

- **`config.py`** — all settings, overridable via `SAM_*` env vars (cache TTL, history
  window, default market, risk-free rate, retries…).
- **`logging_config.py`** — logs to **stderr only** (critical for the MCP server, whose
  stdout carries the protocol).
- **`models.py`** — the Pydantic response contract (`Quote`, `TechnicalAnalysis`,
  `Recommendation`, …, `FullAnalysis`). This is the stable, typed shape everything returns.
- **`errors.py`** — domain exceptions (`SymbolNotFoundError`, `DataUnavailableError`,
  `InsufficientHistoryError`) turned into clean messages at the edges.
- **`utils.py`** — safe numeric coercion, rounding, and the shared **disclaimer** text.

---

## 5. End-to-end request lifecycle

What actually happens when you run `stock-analysis RELIANCE`:

```
1. cli.py parses args  → symbol="RELIANCE", market="NSE"
2. provider.load_stock("RELIANCE", "NSE")
     a. cache key = "stock:RELIANCE:NSE:400"
     b. cache HIT?  → return cached StockData (skip to step 3)
        cache MISS? ↓
     c. tickers.candidate_tickers → ["RELIANCE.NS", "RELIANCE.BO"]
     d. for each candidate:
          - download 400d daily OHLCV   (tenacity retries on failure)
          - fetch info / fast_info / news
          - valid?  → build StockData, store in cache, stop
3. synthesis.build_quote(data)          → price snapshot
4. technical.analyze(data)              → indicators + score  (uses indicators.py)
5. fundamental.analyze(data)            → quality score
6. market.benchmark_returns()           → NIFTY returns (cached)
   risk.analyze(data, benchmark)        → vol, beta, drawdown, VaR, Sharpe
7. market.get_context()                 → VIX, NIFTY, USD/INR… (cached)
8. server._parse_news(data.news)        → cleaned headlines
9.  synthesis.build_outlook(...)        → composite score + bias + scenarios
10. synthesis.build_recommendation(...) → rating (STRONG_BUY…SELL) + confidence
11. assemble FullAnalysis (Pydantic)
12. cli.py renders it (coloured text, or JSON)
```

The web UI and MCP server follow the identical steps 2–11; only step 1 (input) and step 12
(output format) differ.

---

## 6. Data freshness & "daily refresh" — how it really works

This is the part most people misunderstand, so here it is in detail.

### There is no background scheduler
The app does **not** wake itself up. It has no cron job, no timer, no daemon. Data is
pulled **on demand** — the moment you run the CLI, click Analyze in the browser, or an MCP
client calls a tool.

### Where "daily" comes from
1. **The data is daily-granularity.** The provider requests `interval="1d"`, so Yahoo
   returns one price bar per trading day. Each new trading day, Yahoo publishes a new bar,
   and the tool picks it up the next time it fetches.
2. **The latest bar updates through the day.** During market hours the current day's bar
   and `currentPrice` update (Yahoo data is typically delayed ~15 minutes); after close it
   settles to the end-of-day value.

### The 15-minute cache
To be kind to the free feed, results are cached in memory for **`SAM_CACHE_TTL_SECONDS`
(default 900s = 15 min)**:

```
First request for RELIANCE      → fetch from Yahoo, store in cache        (slow, ~1–2s)
Same request within 15 minutes  → served from cache                       (instant)
Same request after 15 minutes   → cache expired → fetch fresh again       (slow again)
```

The cache is **process-local** — it lives only while the CLI command runs, or while the web
/ MCP server process is alive. Restarting the process empties it.

### So, in practice
- Run it once in the morning and once in the evening → you get that day's latest data each
  time (fresh fetch, because >15 min apart).
- Spam the same stock 10 times in a minute → only the first hits Yahoo; the rest are cached.
- Want it to *literally run itself every day*? → add a scheduler (next section).

### Turning it into a **true automated daily refresh**
The tool is a clean building block for this — just have your OS run it on a schedule.

**Option A — `cron` (macOS/Linux):** run every weekday at 9:30 AM and save a report:
```bash
# crontab -e   →  add this line
30 9 * * 1-5  cd /path/to/stock-analysis-mcp && ./.venv/bin/stock-analysis RELIANCE --json > ~/reports/reliance-$(date +\%F).json
```

**Option B — a small watchlist script + cron**, to refresh several stocks and email/store
them. (This is a natural extension — ask and it can be added as a `refresh` command.)

**Option C — macOS `launchd`** or **Windows Task Scheduler** for a GUI-managed schedule.

The important point: **scheduling is an orchestration concern layered *on top of* the tool**,
not baked into it — which keeps the tool simple and lets you choose any scheduler.

---

## 7. Resilience & error handling

- **Retries with backoff** (tenacity) around every price download — transient network
  failures are retried up to `SAM_MAX_RETRIES` (default 3) times.
- **Graceful degradation** — if `info`, `fast_info`, or `news` fail, those fields come back
  empty rather than failing the whole request; rules simply skip missing inputs.
- **Candidate fallback** — if `.NS` yields nothing, it tries `.BO` before giving up.
- **Typed domain errors** — `SymbolNotFoundError` / `DataUnavailableError` /
  `InsufficientHistoryError` become clean, user-readable messages at the CLI/web/MCP edge.
- **Cache stampede protection** — concurrent identical requests share one fetch.

---

## 8. Extensibility

Because the layers are decoupled, common changes are localised:

| I want to… | Change only… |
|---|---|
| Swap the free feed for a paid provider (FMP, Polygon) | `data/provider.py` (analysis untouched) |
| Add/adjust a scoring rule or weight | the relevant `analysis/*.py` file |
| Add a new indicator | `analysis/indicators.py` + one rule |
| Add a new output field | `models.py` + the producer |
| Add a new front-end (e.g. a REST API) | a new presentation module calling the same functions |
| Support another market | extend `data/tickers.py` suffix logic |

---

## 9. Testing

- **`tests/test_indicators.py`** — verifies the indicator math against known-good cases
  (e.g. RSI = 100 on a pure uptrend, MACD histogram = macd − signal).
- **`tests/test_tickers.py`** — resolution and candidate ordering.
- **`tests/test_analysis.py`** — feeds **synthetic** uptrend/downtrend `StockData` (no
  network) and asserts the engine returns bullish/bearish, computes risk, blends the
  outlook. This works precisely *because* the analysis layer is pure.

Run: `pytest` (23 tests, all offline).

---

## 10. Limitations (be honest about these)

- **Data source is free & unofficial.** yfinance can rate-limit or break; for SLA-backed
  production, swap in a paid provider (localised to `provider.py`).
- **Scores are heuristic**, not backtested-and-calibrated. They're sensible defaults, not
  proven alpha.
- **Cache is in-memory & per-process.** For a multi-worker deployment, back it with Redis.
- **Not investment advice.** The `recommendation` is a transparent, rule-based rating
  computed from the stock's own metrics — the same for every user, *not* personalised to
  anyone's finances or goals. The tool is not a licensed adviser; every response carries a
  disclaimer.

---

## 11. File map (quick reference)

```
stock-analysis-mcp/
├── pyproject.toml              # deps, console scripts (stock-analysis, stock-analysis-mcp)
├── README.md                   # developer overview
├── USAGE.md                    # end-user, no-context guide
├── ARCHITECTURE.md             # this file
├── .env.example                # configurable SAM_* settings
├── src/stock_analysis_mcp/
│   ├── server.py               # MCP tools (FastMCP)  ── presentation
│   ├── cli.py                  # terminal command      ── presentation
│   ├── config.py               # settings              ── cross-cutting
│   ├── logging_config.py       # stderr logging        ── cross-cutting
│   ├── models.py               # Pydantic contract     ── cross-cutting
│   ├── errors.py               # domain exceptions     ── cross-cutting
│   ├── utils.py                # helpers + disclaimer   ── cross-cutting
│   ├── cache.py                # TTL cache             ── data
│   ├── data/
│   │   ├── tickers.py          # name → Yahoo ticker    ── data
│   │   └── provider.py         # yfinance wrapper       ── data
│   └── analysis/
│       ├── indicators.py       # pure indicator math    ── analysis
│       ├── technical.py        # trend/momentum score   ── analysis
│       ├── fundamental.py      # quality score          ── analysis
│       ├── risk.py             # risk metrics           ── analysis
│       ├── market.py           # macro context + benchmark ── analysis
│       └── synthesis.py        # quote + outlook + rating ── analysis
├── webui/app.py                # Flask dashboard        ── presentation
└── tests/                      # offline unit tests
```
