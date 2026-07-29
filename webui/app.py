"""A tiny local web UI for manually testing the stock-analysis tools in a browser.

This is a **test harness**, not part of the MCP server itself. It imports the same
analysis functions the MCP tools call, so what you see here is exactly what an MCP
client would receive. Run it with:

    cd stock-analysis-mcp && source .venv/bin/activate
    pip install flask            # one-time (or: pip install -e ".[ui]")
    python webui/app.py

Then open http://127.0.0.1:5001
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template_string, request

from stock_analysis_mcp.logging_config import configure_logging
from stock_analysis_mcp.server import analyze_stock

configure_logging("INFO")
log = logging.getLogger("webui")

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stock Analysis — Test UI</title>
<style>
  :root {
    --bg: #0f1420; --panel: #1a2130; --panel2: #222b3d; --text: #e6ecf5;
    --muted: #93a1bd; --line: #2c374d; --accent: #4f8cff;
    --green: #34d399; --red: #f87171; --amber: #fbbf24;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #f4f6fb; --panel: #ffffff; --panel2: #f0f3fa; --text: #1a2233;
      --muted: #5c6b8a; --line: #e2e8f2; --accent: #2563eb;
      --green: #059669; --red: #dc2626; --amber: #d97706;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  header { padding: 24px 20px; border-bottom: 1px solid var(--line); }
  h1 { margin: 0 0 4px; font-size: 20px; }
  .sub { color: var(--muted); font-size: 13px; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 20px; }
  form { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 20px 0; }
  input, select, button {
    font: inherit; padding: 10px 14px; border-radius: 10px;
    border: 1px solid var(--line); background: var(--panel); color: var(--text); }
  input { flex: 1; min-width: 220px; }
  button { background: var(--accent); color: #fff; border: none; cursor: pointer; font-weight: 600; }
  button:disabled { opacity: .6; cursor: wait; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px; }
  .card h2 { margin: 0 0 12px; font-size: 13px; text-transform: uppercase;
    letter-spacing: .06em; color: var(--muted); }
  .row { display: flex; justify-content: space-between; padding: 5px 0;
    border-bottom: 1px dashed var(--line); font-size: 14px; }
  .row:last-child { border-bottom: none; }
  .row .k { color: var(--muted); }
  .row .v { font-weight: 600; font-variant-numeric: tabular-nums; }
  .quote { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
  .price { font-size: 34px; font-weight: 700; }
  .pill { display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
  .bull, .up, .strong_up, .risk_on, .strong, .healthy, .bullish, .cautiously_bullish, .low,
  .strong_buy, .buy, .positive
    { background: color-mix(in srgb, var(--green) 22%, transparent); color: var(--green); }
  .bear, .down, .strong_down, .risk_off, .weak, .bearish, .cautiously_bearish, .very_high, .high,
  .sell, .reduce, .negative, .cautious
    { background: color-mix(in srgb, var(--red) 22%, transparent); color: var(--red); }
  .neutral, .sideways, .mixed, .moderate, .hold
    { background: color-mix(in srgb, var(--amber) 22%, transparent); color: var(--amber); }
  .bar { height: 8px; border-radius: 6px; background: var(--panel2); overflow: hidden; margin: 8px 0 14px; position: relative; }
  .bar i { position: absolute; top: 0; bottom: 0; width: 2px; left: 50%; background: var(--line); }
  .bar span { position: absolute; top: 0; bottom: 0; }
  ul.notes { margin: 8px 0 0; padding-left: 18px; color: var(--muted); font-size: 13px; }
  ul.notes li { margin: 3px 0; }
  .news a { color: var(--accent); text-decoration: none; font-size: 14px; }
  .news .src { color: var(--muted); font-size: 12px; }
  .full { grid-column: 1 / -1; }
  .err { background: color-mix(in srgb, var(--red) 15%, transparent); color: var(--red);
    padding: 14px; border-radius: 10px; }
  .disc { color: var(--muted); font-size: 12px; margin-top: 20px; line-height: 1.6; }
  .muted { color: var(--muted); }
  .spinner { display: none; }
  .loading .spinner { display: inline; }
</style>
</head>
<body>
<header><div class="wrap" style="padding:0">
  <h1>📈 Stock Analysis — Test UI</h1>
  <div class="sub">Local harness for the NSE/BSE MCP tools · informational only, not investment advice</div>
</div></header>
<div class="wrap">
  <form id="f">
    <input id="symbol" placeholder="Enter a stock: RELIANCE, TCS, INFY, HDFC Bank…" autofocus>
    <select id="market">
      <option value="NSE">NSE</option>
      <option value="BSE">BSE</option>
    </select>
    <button id="btn" type="submit">Analyze <span class="spinner">…</span></button>
  </form>
  <div id="out"></div>
</div>

<script>
const $ = (s) => document.querySelector(s);
const fmt = (v, s='') => (v===null||v===undefined) ? '<span class="muted">—</span>' : v+s;
const pill = (v) => `<span class="pill ${v}">${String(v).replace(/_/g,' ')}</span>`;

function scoreBar(score) {
  // score in [-100, 100] -> position from center
  const pct = Math.max(-100, Math.min(100, score));
  const color = pct >= 15 ? 'var(--green)' : pct <= -15 ? 'var(--red)' : 'var(--amber)';
  if (pct >= 0) return `<div class="bar"><i></i><span style="left:50%;width:${pct/2}%;background:${color}"></span></div>`;
  return `<div class="bar"><i></i><span style="right:50%;width:${-pct/2}%;background:${color}"></span></div>`;
}
const rows = (pairs) => pairs.map(([k,v]) => `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');
const notes = (arr) => arr && arr.length ? `<ul class="notes">${arr.map(n=>`<li>${n}</li>`).join('')}</ul>` : '';

function render(d) {
  const q=d.quote, t=d.technical, f=d.fundamental, r=d.risk, m=d.market_context, o=d.outlook, rec=d.recommendation;
  const chg = q.change_pct;
  const chgColor = chg>=0 ? 'var(--green)' : 'var(--red)';
  const cur = q.currency==='INR' ? '₹' : (q.currency+' ');
  const ratingCls = rec.rating.toLowerCase();
  const confCls = {high:'positive', medium:'neutral', low:'cautious'}[rec.confidence] || 'neutral';
  const confPill = `<span class="pill ${confCls}">${rec.confidence}</span>`;
  return `
  <div class="quote card full">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;width:100%">
      <div>
        <div style="font-size:13px;color:var(--muted)">${q.symbol} · ${q.name||''}</div>
        <div class="quote">
          <span class="price">${cur}${fmt(q.price)}</span>
          <span style="color:${chgColor};font-weight:700">${chg>=0?'▲':'▼'} ${fmt(chg,'%')}</span>
          <span class="muted">as of ${fmt(q.as_of)}</span>
        </div>
      </div>
      <div style="text-align:right">
        <div class="muted" style="font-size:12px">RATING</div>
        <span class="pill ${ratingCls}" style="font-size:16px;padding:6px 14px">${rec.rating.replace(/_/g,' ')}</span>
        <div class="muted" style="font-size:12px;margin-top:4px">${rec.confidence} confidence</div>
      </div>
    </div>
  </div>
  <div class="grid" style="margin-top:16px">
    <div class="card">
      <h2>Technical · ${pill(t.signal)}</h2>
      <div class="muted" style="font-size:13px">Score ${t.score} · trend ${pill(t.trend)}</div>
      ${scoreBar(t.score)}
      ${rows([['Last close',fmt(t.last_close)],['RSI (14)',fmt(t.rsi_14)],['SMA 50 / 200',fmt(t.sma_50)+' / '+fmt(t.sma_200)],['MACD / signal',fmt(t.macd)+' / '+fmt(t.macd_signal)],['ADX (14)',fmt(t.adx_14)],['Support / Resistance',fmt(t.support)+' / '+fmt(t.resistance)]])}
      ${notes(t.signals)}
    </div>
    <div class="card">
      <h2>Fundamental · ${pill(f.verdict)}</h2>
      <div class="muted" style="font-size:13px">Score ${f.score} · ${fmt(f.sector)}</div>
      ${scoreBar(f.score)}
      ${rows([['P/E (fwd)',fmt(f.pe_ratio)+' ('+fmt(f.forward_pe)+')'],['P/B',fmt(f.price_to_book)],['ROE',fmt(f.roe,'%')],['Net margin',fmt(f.profit_margin,'%')],['Debt/Equity',fmt(f.debt_to_equity)],['Rev / Earn growth',fmt(f.revenue_growth,'%')+' / '+fmt(f.earnings_growth,'%')]])}
      ${notes(f.observations)}
    </div>
    <div class="card">
      <h2>Risk · ${pill(r.risk_level)}</h2>
      ${rows([['Annualised vol',fmt(r.annualised_volatility!=null?(r.annualised_volatility*100).toFixed(1):null,'%')],['Beta (vs NIFTY)',fmt(r.beta)],['Max drawdown',fmt(r.max_drawdown!=null?(r.max_drawdown*100).toFixed(1):null,'%')],['Sharpe',fmt(r.sharpe_ratio)],['1-day VaR 95%',fmt(r.value_at_risk_95!=null?(r.value_at_risk_95*100).toFixed(1):null,'%')]])}
      ${notes(r.observations)}
    </div>
    <div class="card">
      <h2>Market context · ${pill(m.sentiment)}</h2>
      ${rows([['India VIX',fmt(m.india_vix)],['NIFTY 50',fmt(m.nifty_50_change_pct,'%')],['SENSEX',fmt(m.sensex_change_pct,'%')],['USD/INR',fmt(m.usd_inr)],['S&P 500',fmt(m.sp500_change_pct,'%')],['Crude / Gold',fmt(m.crude_oil_change_pct,'%')+' / '+fmt(m.gold_change_pct,'%')]])}
      ${notes(m.observations)}
    </div>
    <div class="card full">
      <h2>Outlook · ${pill(o.bias)}</h2>
      <div class="muted" style="font-size:13px">Composite ${o.composite_score} · ${o.time_horizon}</div>
      ${scoreBar(o.composite_score)}
      <div class="grid">
        <div><strong style="color:var(--green)">Positives</strong>${notes(o.key_positives)}</div>
        <div><strong style="color:var(--red)">Risks</strong>${notes(o.key_risks)}</div>
      </div>
      <div style="margin-top:10px"><strong>Scenarios</strong>${notes(o.scenarios)}</div>
    </div>
    <div class="card full">
      <h2>Recommendation · ${pill(rec.rating.toLowerCase())}</h2>
      <div class="muted" style="font-size:13px">
        Stance ${pill(rec.stance)} · ${confPill} confidence · composite ${rec.composite_score}
      </div>
      <div style="margin-top:10px"><strong>Why</strong>${notes(rec.rationale)}</div>
      <div style="margin-top:10px;color:var(--amber);font-size:13px">
        ⚠ This is an automated, rule-based signal — the same for every user — not personalised investment advice.
      </div>
    </div>
    ${d.news && d.news.length ? `<div class="card full news"><h2>Recent news</h2>${d.news.map(n=>`<div class="row"><a href="${n.link||'#'}" target="_blank" rel="noopener">${n.title}</a><span class="src">${n.publisher||''}</span></div>`).join('')}</div>` : ''}
  </div>
  <div class="disc">⚠️ ${d.disclaimer}</div>`;
}

$('#f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const symbol = $('#symbol').value.trim();
  if (!symbol) return;
  const market = $('#market').value;
  $('#btn').disabled = true; $('#btn').classList.add('loading');
  $('#out').innerHTML = '<p class="muted">Fetching live data & running analysis…</p>';
  try {
    const res = await fetch(`/api/analyze?symbol=${encodeURIComponent(symbol)}&market=${market}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    $('#out').innerHTML = render(data);
  } catch (err) {
    $('#out').innerHTML = `<div class="err">❌ ${err.message}</div>`;
  } finally {
    $('#btn').disabled = false; $('#btn').classList.remove('loading');
  }
});
</script>
</body>
</html>"""


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.get("/api/analyze")
def api_analyze():
    symbol = (request.args.get("symbol") or "").strip()
    market = (request.args.get("market") or "NSE").strip().upper()
    if not symbol:
        return jsonify({"error": "Please provide a symbol."}), 400
    try:
        result = analyze_stock(symbol, market=market)
        return jsonify(result.model_dump())
    except Exception as exc:  # noqa: BLE001 - surface a clean message to the browser
        log.warning("Analysis failed for %s: %s", symbol, exc)
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Stock Analysis web test UI.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SAM_WEBUI_PORT", "5001")),
        help="Port to serve on (default: 5001, or $SAM_WEBUI_PORT).",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SAM_WEBUI_HOST", "127.0.0.1"),
        help="Host to bind (default: 127.0.0.1).",
    )
    cli_args = parser.parse_args()

    try:
        print(f" * Stock Analysis UI → http://{cli_args.host}:{cli_args.port}")
        app.run(host=cli_args.host, port=cli_args.port, debug=False)
    except OSError as exc:
        if getattr(exc, "errno", None) in (48, 98) or "address already in use" in str(exc).lower():
            raise SystemExit(
                f"Port {cli_args.port} is already in use. "
                f"Start on a different port, e.g.:\n"
                f"    python webui/app.py --port 5002"
            ) from exc
        raise
