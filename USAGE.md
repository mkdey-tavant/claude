# How to Use the Stock Analysis Tool (No Claude, No Subscription)

This guide is for **anyone** who wants to run the stock analysis tool on their own
computer. You do **not** need Claude, ChatGPT, an API key, or any paid subscription.

The tool analyses **Indian stocks (NSE / BSE)** and gives you:
- 📊 **Technical analysis** (price trends, RSI, MACD, moving averages, support/resistance)
- 💰 **Fundamental analysis** (P/E, ROE, debt, growth, profitability)
- ⚠️ **Risk analysis** (volatility, beta, max drawdown, Sharpe ratio, Value-at-Risk)
- 🌍 **Market context** (India VIX, NIFTY, SENSEX, USD/INR, global cues)
- 🔮 **A forward outlook** (a bias + base/bull/bear scenarios — *not* a buy/sell call)
- 📰 **Recent news** headlines

> ⚠️ **This is for education and information only. It is NOT investment advice.**
> Always consult a SEBI-registered investment adviser before making any decision.

The **only** thing the tool needs from the internet is stock price data (fetched free
via Yahoo Finance). Nothing is sent to any AI service.

---

## Step 1 — Install Python (one time)

You need **Python 3.10 or newer**.

- **Check if you already have it.** Open a terminal (macOS: *Terminal* app; Windows:
  *PowerShell*) and run:
  ```bash
  python3 --version
  ```
  If it prints `Python 3.10.x` or higher, you're set. Skip to Step 2.

- **If not installed or too old**, download it free from
  [python.org/downloads](https://www.python.org/downloads/) and install it.
  On Windows, tick **"Add Python to PATH"** during setup.

---

## Step 2 — Set up the tool (one time)

Open a terminal and go into the project folder:

```bash
cd path/to/stock-analysis-mcp
```

Create an isolated environment and install the tool into it:

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui]"
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[ui]"
```

That's it. The `.venv` folder keeps everything self-contained — it won't affect the rest
of your system.

> 💡 The `[ui]` part also installs the optional web dashboard. If you only want the
> command line, `pip install -e .` is enough.

---

## Step 3 — Use it (pick whichever you like)

Each time you open a **new** terminal, first "activate" the environment:

- macOS / Linux: `source .venv/bin/activate`
- Windows: `.venv\Scripts\Activate.ps1`

You'll know it worked when you see `(.venv)` at the start of your prompt.

### Option A — Command line (simplest)

Just type `stock-analysis` followed by a stock name:

```bash
stock-analysis RELIANCE
stock-analysis TCS
stock-analysis "HDFC Bank"
stock-analysis INFY
```

You can also use official ticker symbols (`RELIANCE.NS`, `TCS.BO`).

**Useful options:**

| What you want | Command |
|---|---|
| Analyse on the BSE instead of NSE | `stock-analysis TCS --market BSE` |
| See only the rating/recommendation | `stock-analysis INFY --section recommendation` |
| See only the risk section | `stock-analysis INFY --section risk` |
| See only fundamentals | `stock-analysis INFY --section fundamental` |
| Get raw data (for scripts/Excel) | `stock-analysis INFY --json` |
| See all options | `stock-analysis --help` |

Sections you can pass to `--section`: `technical`, `fundamental`, `risk`, `market`,
`outlook`, or `all` (the default).

### Option B — Web dashboard (visual, in your browser)

Start the local dashboard:

```bash
python webui/app.py
```

Then open your web browser and go to:

```
http://127.0.0.1:5001
```

Type a stock name, choose NSE or BSE, and click **Analyze**. You'll get a clean visual
report with colour-coded results. To stop the dashboard, go back to the terminal and
press **Ctrl + C**.

> **Port already in use?** If you see `Port 5001 is in use`, another program (or a
> previous run) is using it. Start on a different port instead:
> ```bash
> python webui/app.py --port 5002
> ```
> Then open `http://127.0.0.1:5002`.

> This runs entirely on your own computer. Nothing leaves your machine except the request
> for stock prices from Yahoo Finance.

### Option C — Inside your own Python script

If you want to build on top of the tool:

```python
from stock_analysis_mcp.server import analyze_stock

result = analyze_stock("RELIANCE", market="NSE")
data = result.model_dump()   # a plain dictionary

print(data["quote"]["price"])
print(data["outlook"]["bias"])
print(data["technical"]["signals"])
```

---

## How to read the results

| Section | What it tells you |
|---|---|
| **Quote** | Current price and today's move. |
| **Technical** | Short-term price behaviour. `Signal` is `bullish` / `neutral` / `bearish`; the `score` runs from −100 (very bearish) to +100 (very bullish). |
| **Fundamental** | Business quality. `Verdict` is `strong` / `healthy` / `mixed` / `weak`. |
| **Risk** | How bumpy the ride is. `Risk level` is `low` / `moderate` / `high` / `very_high`. |
| **Market context** | The overall mood of the market that day (`risk_on` / `neutral` / `risk_off`). |
| **Outlook** | A blended `bias` plus base / bull / bear **scenarios**. This is a *lean*, not a prediction. |
| **Recommendation** | An algorithmic **rating**: `STRONG_BUY` / `BUY` / `HOLD` / `REDUCE` / `SELL`, with a `confidence` level and the reasons behind it. |

Every section also lists **plain-English reasons** for its verdict, so you can see exactly
*why* — nothing is a black box.

### About the recommendation / rating

The **rating** is generated by a transparent set of rules from the stock's own numbers
(the blended technical + fundamental score, adjusted for risk). It is:

- **The same for everyone** — it is *not* tailored to your finances, goals, or holdings.
- **An automated signal, not personalised investment advice.** The tool is not a licensed
  adviser and does not know your situation.
- **`confidence`** tells you how much the technical and fundamental pictures *agree*.
  `low` confidence means they disagree — treat the rating with extra caution.

Always do your own research and consult a SEBI-registered adviser before acting.

---

## Frequently asked questions

**Do I need Claude, ChatGPT, or any AI subscription?**
No. The entire analysis is done by transparent math and rules in plain Python. No AI
service is used or contacted.

**Do I need to pay for stock data?**
No. It uses the free Yahoo Finance feed. (This is great for personal use; it's unofficial
and can occasionally be slow or rate-limited.)

**Which stocks work?**
Indian stocks listed on the NSE or BSE — for example RELIANCE, TCS, INFY, HDFCBANK,
ICICIBANK, SBIN, ITC, LT, WIPRO, and thousands more.

**Is this a buy/sell recommendation service?**
No — by design. It gives you analysis and a bias, never a "buy this now" call.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: stock-analysis` | You forgot to activate the environment. Run the activate command from Step 3. |
| `python3: command not found` | Python isn't installed or not on PATH — redo Step 1. On Windows try `python` instead of `python3`. |
| `No NSE/BSE listing found for ...` | Check the spelling, or try adding the exchange: `--market BSE`, or the full ticker like `TCS.NS`. |
| `Could not retrieve data ... provider may be temporarily unavailable` | Yahoo Finance was briefly unreachable or rate-limited. Wait a minute and try again. |
| Web page won't open at `127.0.0.1:5001` | Make sure `python webui/app.py` is still running in the terminal, then refresh. |
| Results look slightly stale | The tool caches data for ~15 minutes to be gentle on the free feed. |

---

*Built for personal, educational use. Not affiliated with NSE, BSE, or Yahoo. Not
investment advice.*
