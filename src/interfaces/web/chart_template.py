"""HTML rendering for the local web UI's chart page.

Per the "Chart" production requirement: "Embed TradingView (or equivalent
if licensing requires another solution)... Only if rendering performance
remains smooth." Uses TradingView's free, self-hosted Lightweight Charts
library (Apache-2.0, no account/licensing needed) rather than the full
TradingView Charting Library, which requires a separate paid agreement
this platform does not have. Split out from `templates.py` to keep that
file under the project's 500-line limit.
"""

from __future__ import annotations

import json

from src.interfaces.web.chart_service import ChartData
from src.interfaces.web.templates import _page

_LIGHTWEIGHT_CHARTS_CDN_URL = (
    "https://unpkg.com/lightweight-charts@4/dist/lightweight-charts.standalone.production.js"
)

# Zone kinds rendered as a single dashed price line (a level, not a range).
_SINGLE_LEVEL_ZONE_KINDS = frozenset(
    {"support", "resistance", "liquidity_buy_side", "liquidity_sell_side"}
)

_ZONE_COLORS: dict[str, str] = {
    "order_block": "#d9a441",
    "fvg_bullish": "#26a69a",
    "fvg_bearish": "#ef5350",
    "support": "#26a69a",
    "resistance": "#ef5350",
    "liquidity_buy_side": "#4d8dff",
    "liquidity_sell_side": "#4d8dff",
}


def render_chart_html(data: ChartData, *, market: str) -> str:
    """Render the chart page.

    Args:
        data: The current `ChartData`.
        market: Symbol name, e.g. "XAUUSD".

    Returns:
        A complete HTML document.
    """
    payload = json.dumps(
        {
            "candles": [
                {
                    "time": candle.time,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                }
                for candle in data.candles
            ],
            "tradeMarkers": [
                {"time": m.time, "price": m.price, "kind": m.kind, "label": m.label}
                for m in data.trade_markers
            ],
            "swingMarkers": [
                {"time": m.time, "price": m.price, "kind": m.kind} for m in data.swing_markers
            ],
            "zones": [
                {
                    "kind": z.kind,
                    "priceLow": z.price_low,
                    "priceHigh": z.price_high,
                    "label": z.label,
                    "single": z.kind in _SINGLE_LEVEL_ZONE_KINDS,
                    "color": _ZONE_COLORS.get(z.kind, "#8b94a7"),
                }
                for z in data.zones
            ],
        }
    )
    empty_notice = (
        '<p class="muted">Пока нет сохранённых свечей для этого символа.</p>'
        if not data.candles
        else ""
    )
    structure_note = f'<p class="muted">{data.structure_note}</p>' if data.structure_note else ""

    return _page(
        "График",
        f"""
<h1>График — {market}</h1>
<div class="nav"><a href="/">← Панель</a> · <a href="/settings">Настройки →</a></div>

<div class="card">
  <h2>Свечи и структура</h2>
  {structure_note}
  {empty_notice}
  <div id="chart" style="height: 520px;"></div>
  <p class="muted">
    <span class="tag">Order Block</span>
    <span class="tag">FVG</span>
    <span class="tag">Support/Resistance</span>
    <span class="tag">Liquidity</span>
    <span class="tag">Swing High/Low</span>
    <span class="tag">Входы/выходы</span>
  </p>
</div>

<script src="{_LIGHTWEIGHT_CHARTS_CDN_URL}"></script>
<script>
const chartData = {payload};
const container = document.getElementById("chart");
if (chartData.candles.length > 0 && window.LightweightCharts) {{
  const chart = LightweightCharts.createChart(container, {{
    layout: {{ background: {{ color: "transparent" }}, textColor: "#e6e9ef" }},
    grid: {{
      vertLines: {{ color: "rgba(255,255,255,0.05)" }},
      horzLines: {{ color: "rgba(255,255,255,0.05)" }},
    }},
    timeScale: {{ timeVisible: true, secondsVisible: false }},
  }});
  const series = chart.addCandlestickSeries({{
    upColor: "#26a69a", downColor: "#ef5350",
    borderVisible: false, wickUpColor: "#26a69a", wickDownColor: "#ef5350",
  }});
  series.setData(chartData.candles);

  const markers = [];
  for (const m of chartData.tradeMarkers) {{
    if (m.kind === "entry_buy") {{
      markers.push({{ time: m.time, position: "belowBar", color: "#26a69a",
        shape: "arrowUp", text: m.label }});
    }} else if (m.kind === "entry_sell") {{
      markers.push({{ time: m.time, position: "aboveBar", color: "#ef5350",
        shape: "arrowDown", text: m.label }});
    }} else {{
      markers.push({{ time: m.time, position: "inBar", color: "#d9a441",
        shape: "circle", text: m.label }});
    }}
  }}
  for (const s of chartData.swingMarkers) {{
    markers.push({{
      time: s.time,
      position: s.kind === "swing_high" ? "aboveBar" : "belowBar",
      color: "#8b94a7",
      shape: s.kind === "swing_high" ? "arrowDown" : "arrowUp",
      text: s.kind === "swing_high" ? "SH" : "SL",
    }});
  }}
  markers.sort((a, b) => a.time - b.time);
  series.setMarkers(markers);

  for (const zone of chartData.zones) {{
    series.createPriceLine({{
      price: zone.priceLow, color: zone.color, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true,
      title: zone.label,
    }});
    if (!zone.single && zone.priceHigh !== zone.priceLow) {{
      series.createPriceLine({{
        price: zone.priceHigh, color: zone.color, lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true,
        title: zone.label,
      }});
    }}
  }}

  chart.timeScale().fitContent();
  new ResizeObserver(entries => {{
    chart.applyOptions({{ width: entries[0].contentRect.width }});
  }}).observe(container);
}}
</script>
""",
    )
