"""HTML rendering for the local web UI.

Per the "Professional User Interface" production requirement: "modern
dark theme, extremely responsive, minimalistic, fast." Plain HTML/CSS/JS,
no templating engine or frontend framework -- the whole point is speed
and simplicity; a single small stylesheet is shared by every page.
"""

from __future__ import annotations

from datetime import timedelta

from src.interfaces.web.dashboard_service import (
    ClosedTradeView,
    DashboardStatus,
    OpenPositionView,
    StrategyStatusView,
)
from src.interfaces.web.settings_service import SettingsView
from src.interfaces.web.strategy_performance_service import (
    StrategyPerformance,
    StrategyPerformanceView,
)
from src.interfaces.web.strategy_profile_service import StrategyProfilesView

_STRATEGY_LABELS_RU: dict[str, str] = {
    "intraday": "Intraday",
    "scalping": "Скальпинг",
    "swing": "Свинг",
    # Per Shakky's own production requirement: "must appear in the
    # interface as 'Classic M5 Strategy'" -- an explicit exception to
    # every other strategy's Russian label.
    "shakky": "Classic M5 Strategy",
    "micro_scalping": "Микро-скальп",
}
_STRATEGY_STATUS_LABELS_RU: dict[str, str] = {
    "waiting": "⏸ Ожидание (отключено/пауза)",
    "searching": "🔍 Поиск...",
    "trade_found": "✅ Сделка найдена",
    "trade_open": "📈 Сделка открыта",
    "no_trade": "❌ Нет сделки",
}
# Per the "Complete Strategy Builder" production requirement: "Show all
# internal confirmations inside every module" -- maps each Technical
# Department agent's own `agent_name` (`src.agents.technical.*`) to a
# short Russian label for the dashboard's sub-signal breakdown.
_TECHNICAL_AGENT_LABELS_RU: dict[str, str] = {
    "trend": "Тренд",
    "momentum": "Моментум",
    "volatility": "Волатильность",
    "support_resistance": "Поддержка/Сопротивление",
    "liquidity": "Ликвидность",
    "smart_money": "Smart Money",
    "market_structure": "Структура рынка",
    "price_action": "Price Action",
}

# A professional trading-terminal dark palette (TradingView/MT5-style
# near-black blue-grey background, not a pure #000 -- easier on the eyes
# for a screen left open all day).
_STYLE = """
:root {
  --bg: #0e1117; --panel: #161b24; --border: #262d3a;
  --text: #e6e9ef; --muted: #8b94a7;
  --green: #26a69a; --red: #ef5350; --blue: #4d8dff; --amber: #d9a441;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
  background: var(--bg); color: var(--text);
  max-width: 960px; margin: 0 auto; padding: 1rem 1.25rem 3rem;
  font-size: 14px;
}
h1 { font-size: 1.1rem; font-weight: 600; margin: 0 0 1rem; letter-spacing: 0.02em; }
h2 { font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--muted); margin: 0 0 0.6rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0.75rem; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 0.9rem 1rem; margin-bottom: 0.75rem;
}
.row { display: flex; justify-content: space-between; align-items: center; padding: 0.3rem 0;
  border-bottom: 1px solid rgba(255,255,255,0.03); }
.row:last-child { border-bottom: none; }
.label { color: var(--muted); }
.value { font-weight: 600; }
.pos { color: var(--green); }
.neg { color: var(--red); }
.buy { color: var(--green); }
.sell { color: var(--red); }
.pill {
  display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px;
  font-size: 0.75rem; font-weight: 600; letter-spacing: 0.03em;
}
.pill-healthy { background: rgba(38,166,154,0.15); color: var(--green); }
.pill-stalled { background: rgba(239,83,80,0.15); color: var(--red); }
.pill-unknown { background: rgba(139,148,167,0.15); color: var(--muted); }
.pill-buy { background: rgba(38,166,154,0.15); color: var(--green); }
.pill-sell { background: rgba(239,83,80,0.15); color: var(--red); }
.pill-neutral { background: rgba(217,164,65,0.15); color: var(--amber); }
a { color: var(--blue); text-decoration: none; font-size: 0.85rem; }
a:hover { text-decoration: underline; }
.tag {
  display: inline-block; background: rgba(77,141,255,0.12); color: var(--blue);
  border-radius: 6px; padding: 0.1rem 0.5rem; margin: 0.15rem 0.25rem 0.15rem 0;
  font-size: 0.75rem;
}
.muted { color: var(--muted); font-size: 0.85rem; }
.nav { margin-bottom: 1rem; }
.trade-explanation { margin: 0.3rem 0 0.6rem; font-size: 0.85rem; }
.trade-explanation summary { cursor: pointer; color: var(--muted); }
.trade-explanation summary:hover { color: var(--text); }
.trade-explanation ul { margin: 0.3rem 0 0; padding-left: 1.1rem; color: var(--muted); }
input, select {
  background: var(--bg); color: var(--text); border: 1px solid var(--border);
  border-radius: 6px; padding: 0.5rem; margin: 0.25rem 0; width: 100%;
}
label { font-size: 0.85rem; color: var(--muted); display: block; margin-top: 0.6rem; }
button {
  background: var(--blue); color: #fff; border: none; border-radius: 6px;
  padding: 0.55rem 1.1rem; margin-top: 0.75rem; cursor: pointer; font-weight: 600;
}
button:hover { opacity: 0.9; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
td, th { text-align: left; padding: 0.3rem 0.4rem;
  border-bottom: 1px solid rgba(255,255,255,0.03); }
th { color: var(--muted); font-weight: 500; }
"""

_HEALTH_LABELS_RU = {"healthy": "работает", "stalled": "завис", "unknown": "нет данных"}
_BIAS_LABELS_RU = {"bullish": "рост", "bearish": "падение", "neutral": "нейтрально"}


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — GOLD QUANT AI</title>
<style>{_STYLE}</style>
</head>
<body>
{body}
</body>
</html>"""


def _health_pill(health: str) -> str:
    label = _HEALTH_LABELS_RU.get(health, health)
    return f'<span class="pill pill-{health}">{label}</span>'


def _bias_pill(bias: str | None) -> str:
    if bias is None:
        return '<span class="muted">нет данных</span>'
    css_class = {"bullish": "buy", "bearish": "sell"}.get(bias, "neutral")
    label = _BIAS_LABELS_RU.get(bias, bias)
    return f'<span class="pill pill-{css_class}">{label}</span>'


def _trade_explanation_html(
    view: OpenPositionView | ClosedTradeView, *, would_repeat: bool | None = None
) -> str:
    """Render one trade's "Strategy Explanation" details (collapsed by default).

    Per the "Strategy Explanation" production requirement: Strategy, Trade
    Quality, Confidence, Risk Score, Expected Holding Time, Expected
    Scenario, Reasons, positive/negative confirmations, all in one place
    per trade -- a `<details>` block keeps the surrounding table/list
    compact (per the "extremely minimalistic" requirement) while still
    making every field genuinely available, not merely computed and discarded.
    """
    strategy_label = _STRATEGY_LABELS_RU.get(view.strategy.lower(), view.strategy)
    quality_text = f"{view.quality_score:.0f}/100" if view.quality_score is not None else "—"
    confidence_text = f"{view.confidence_pct:.0f}%" if view.confidence_pct is not None else "—"
    risk_text = f"{view.risk_score:.0f}/100" if view.risk_score is not None else "—"
    holding_text = (
        f"{view.expected_holding_time_minutes:.0f} мин"
        if view.expected_holding_time_minutes is not None
        else "—"
    )
    scenario_text = view.expected_scenario or "—"
    reasons_html = (
        "".join(f"<li>{reason}</li>" for reason in view.reasons)
        or '<li class="muted">нет данных</li>'
    )
    tags_html = (
        "".join(
            f'<span class="tag">{tag}</span>'
            for tag in [*view.positive_confirmations, *view.negative_confirmations]
        )
        or '<span class="muted">нет данных</span>'
    )
    repeat_row = ""
    if would_repeat is not None:
        repeat_text = "ДА" if would_repeat else "НЕТ"
        repeat_row = (
            f'<div class="row"><span class="label">Открыли бы снова</span>'
            f'<span class="value">{repeat_text}</span></div>'
        )
    similarity_row = ""
    if view.similarity_summary is not None:
        similarity_row = (
            f'<div class="row"><span class="label">🔍 Похожие ситуации</span>'
            f'<span class="value">{view.similarity_summary}</span></div>'
        )
    return f"""
<details class="trade-explanation">
  <summary>{strategy_label} · Качество {quality_text} · Уверенность {confidence_text}</summary>
  <div class="row"><span class="label">Риск</span><span class="value">{risk_text}</span></div>
  <div class="row"><span class="label">Ожидаемое время удержания</span>
    <span class="value">{holding_text}</span></div>
  <div class="row"><span class="label">Ожидаемый сценарий</span>
    <span class="value">{scenario_text}</span></div>
  {repeat_row}
  {similarity_row}
  <div>{tags_html}</div>
  <ul>{reasons_html}</ul>
</details>
"""


def _sub_signals_html(technical_sub_signals: dict[str, list[str]]) -> str:
    """Render each Technical Department agent's own internal confirmations.

    Per the "Complete Strategy Builder" production requirement: "Show all
    internal confirmations inside every module," e.g. Trend -> "✅ EMA20",
    "❌ EMA200". Agents with no evidence this cycle are omitted rather
    than shown as an empty, misleading block.
    """
    blocks = []
    for agent_name, tags in technical_sub_signals.items():
        if not tags:
            continue
        label = _TECHNICAL_AGENT_LABELS_RU.get(agent_name, agent_name)
        tags_html = "".join(f'<span class="tag">{tag}</span>' for tag in tags)
        blocks.append(
            f'<div class="row"><span class="label">{label}</span></div><div>{tags_html}</div>'
        )
    if not blocks:
        return '<span class="muted">Нет данных за этот цикл</span>'
    return "".join(blocks)


def _closed_trade_row(trade: ClosedTradeView) -> str:
    pnl_class = "pos" if (trade.realized_pnl or 0.0) >= 0 else "neg"
    pnl_text = f"{trade.realized_pnl:+.2f}$" if trade.realized_pnl is not None else "?"
    closed_text = trade.closed_at.strftime("%d.%m %H:%M") if trade.closed_at else "-"
    direction_class = "buy" if trade.direction == "buy" else "sell"
    explanation_html = _trade_explanation_html(trade, would_repeat=trade.would_repeat)
    return (
        f'<tr><td class="{direction_class}">{trade.direction.upper()}</td>'
        f'<td class="{pnl_class}">{pnl_text}</td>'
        f'<td class="muted">{closed_text}</td></tr>'
        f'<tr><td colspan="3">{explanation_html}</td></tr>'
    )


def _default_strategy_view(status: DashboardStatus, strategy_key: str) -> StrategyStatusView:
    return status.strategies.get(strategy_key, StrategyStatusView(status="searching"))


_ALL_STRATEGY_KEYS = ("intraday", "scalping", "swing", "shakky", "micro_scalping")


def _enabled_strategy_cards(status: DashboardStatus) -> str:
    """Render a full card only for each currently-enabled strategy.

    Per the user's own explicit request to declutter the dashboard: a
    disabled engine contributes no signal and never will until
    re-enabled in Settings, so it does not need a full status card
    competing for attention with the engines that actually trade.
    """
    views = [(key, _default_strategy_view(status, key)) for key in _ALL_STRATEGY_KEYS]
    enabled = [(key, view) for key, view in views if view.enabled]
    return "".join(_strategy_card(key, view) for key, view in enabled)


def _disabled_strategies_summary(status: DashboardStatus) -> str:
    """Collapse every disabled strategy into one compact line instead of full cards."""
    disabled_labels = [
        _STRATEGY_LABELS_RU.get(key, key)
        for key in _ALL_STRATEGY_KEYS
        if not _default_strategy_view(status, key).enabled
    ]
    if not disabled_labels:
        return ""
    return (
        '<div class="row muted" style="margin-top: 8px;">'
        f'<span class="label">Отключены:</span> <span>{", ".join(disabled_labels)}</span>'
        "</div>"
    )


def _strategy_card(strategy_key: str, view: StrategyStatusView) -> str:
    """Render one strategy's own independent status card.

    Per the "User Interface" production requirement: every strategy
    shows its own Searching/Waiting/Trade Found/Trade Open/No Trade
    status, Trade Quality, Confidence and reasoning -- independently of
    the other two strategies.
    """
    label = _STRATEGY_LABELS_RU.get(strategy_key, strategy_key)
    status_label = _STRATEGY_STATUS_LABELS_RU.get(view.status, view.status)
    quality_text = f"{view.quality_score:.0f}/100" if view.quality_score is not None else "—"
    confidence_text = f"{view.confidence_pct:.0f}%" if view.confidence_pct is not None else "—"
    reasons_html = (
        "".join(f'<div class="row"><span class="label">• {r}</span></div>' for r in view.reasons)
        if view.reasons
        else ""
    )
    daily_stats_html = ""
    if view.trades_per_day is not None:
        best_hour = (
            f"{view.best_trading_hour_utc:02d}:00 UTC"
            if view.best_trading_hour_utc is not None
            else "—"
        )
        worst_hour = (
            f"{view.worst_trading_hour_utc:02d}:00 UTC"
            if view.worst_trading_hour_utc is not None
            else "—"
        )
        daily_stats_html = f"""
  <div class="row"><span class="label">Сделок в день</span>
    <span class="value">{view.trades_per_day:.1f}</span></div>
  <div class="row"><span class="label">Прибыль за сегодня</span>
    <span class="value">{(view.today_total_profit_usd or 0.0):+.2f}$</span></div>
  <div class="row"><span class="label">Лучший час</span>
    <span class="value">{best_hour}</span></div>
  <div class="row"><span class="label">Худший час</span>
    <span class="value">{worst_hour}</span></div>
"""
    return f"""
<div class="card">
  <h2>{label}</h2>
  <div class="row"><span class="label">Статус</span>
    <span class="value">{status_label}</span></div>
  <div class="row"><span class="label">Качество</span>
    <span class="value">{quality_text}</span></div>
  <div class="row"><span class="label">Уверенность</span>
    <span class="value">{confidence_text}</span></div>
  {reasons_html}
  {daily_stats_html}
</div>
"""


def render_dashboard_html(status: DashboardStatus) -> str:
    """Render the main dashboard page.

    Args:
        status: The current `DashboardStatus`.

    Returns:
        A complete HTML document.
    """
    decision_class = "buy" if status.state == "BUY" else "sell" if status.state == "SELL" else ""
    confidence_text = f"{status.confidence_pct:.0f}%" if status.confidence_pct is not None else "—"
    quality_text = (
        f"{status.trade_quality_score:.0f}/100" if status.trade_quality_score is not None else "—"
    )
    risk_score_text = f"{status.risk_score:.0f}/100" if status.risk_score is not None else "—"
    mt5_status_ru = {"connected": "подключён", "disconnected": "нет связи", "unknown": "нет данных"}
    mt5_pill_class = {"connected": "healthy", "disconnected": "stalled", "unknown": "unknown"}
    telegram_status_text = "подключён" if status.telegram_configured else "не настроен"
    news_status_text = "подключён" if status.news_configured else "не настроен"

    positions_rows = (
        "".join(
            f'<div class="row"><span class="{"buy" if p.direction == "buy" else "sell"}">'
            f"{p.direction.upper()} {p.volume:g} @ "
            f"{p.entry_price if p.entry_price is not None else '?'}</span>"
            f'<span class="label">Стоп {p.stop_loss}</span></div>'
            f"{_trade_explanation_html(p)}"
            for p in status.open_positions
        )
        or '<div class="muted">Нет открытых позиций</div>'
    )

    closed_rows = (
        "".join(_closed_trade_row(t) for t in status.closed_trades)
        or '<tr><td class="muted" colspan="3">Пока нет закрытых сделок</td></tr>'
    )

    department_tags = (
        "".join(f'<span class="tag">{name}</span>' for name in status.active_departments)
        or '<span class="muted">Нет данных за этот цикл</span>'
    )

    today_pnl_class = "pos" if status.today_pnl >= 0 else "neg"
    win_rate_text = f"{status.win_rate_pct:.0f}%" if status.win_rate_pct is not None else "—"
    profit_factor_text = f"{status.profit_factor:.2f}" if status.profit_factor is not None else "—"

    no_trade_block = ""
    if status.state == "WAIT":
        next_scan_text = (
            f"{status.next_scan_minutes:.0f} мин." if status.next_scan_minutes is not None else "—"
        )
        reasons_rows = (
            "".join(
                f'<div class="row"><span class="label">• {r}</span></div>'
                for r in status.no_trade_reasons
            )
            or '<div class="muted">Причины не зафиксированы</div>'
        )
        no_trade_block = f"""
<div class="card">
  <h2>❌ Нет сделки</h2>
  <div class="row"><span class="label">Качество</span>
    <span class="value">{quality_text}</span></div>
  <div class="row"><span class="label">Уверенность</span>
    <span class="value">{confidence_text}</span></div>
  <div class="row"><span class="label">Причины</span></div>
  {reasons_rows}
  <div class="row"><span class="label">Следующее сканирование</span>
    <span class="value">{next_scan_text}</span></div>
</div>
"""

    week_total = status.trades_opened_this_week
    week_goal_class = "pos" if 3 <= week_total <= 5 else "muted" if week_total in (1, 2) else "neg"
    week_goal_status = (
        "в цели (3-5)" if 3 <= week_total <= 5 else "ниже цели" if week_total < 3 else "выше цели"
    )

    return _page(
        "Панель",
        f"""
<h1>GOLD QUANT AI</h1>
<div class="nav"><a href="/settings">Настройки →</a> · <a href="/books">Книги →</a> ·
  <a href="/chart">График →</a> · <a href="/strategy-builder">Strategy Builder →</a> ·
  <a href="/strategy-comparison">Сравнение стратегий →</a></div>

<div class="card">
  <h2>🎯 Цель на неделю: 3-5 качественных сделок</h2>
  <div class="row"><span class="label">Сделок за 7 дней</span>
    <span class="value {week_goal_class}">{week_total} ({week_goal_status})</span></div>
  <div class="row"><span class="label">Прибыльных / убыточных за 7 дней</span>
    <span class="value">{status.wins_this_week} / {status.losses_this_week}</span></div>
  <div class="row"><span class="label">Минимум в неделю</span>
    <span class="value muted">1 сделка</span></div>
</div>

<div class="card">
  <h2>Управление</h2>
  <div class="row"><span class="label">Процесс</span>
    <span class="value" id="control-status">проверка...</span></div>
  <button onclick="controlAction('start')">START</button>
  <button onclick="controlAction('stop')">STOP</button>
  <button onclick="controlAction('pause')" id="pause-button">PAUSE</button>
  <button onclick="controlAction('restart')">RESTART</button>
  <button onclick="emergencyClose()" style="background: var(--red);">EMERGENCY CLOSE</button>
  <p id="control-message" class="muted"></p>
</div>

<div class="grid">
  {_enabled_strategy_cards(status)}
</div>
{_disabled_strategies_summary(status)}

<div class="grid">
  <div class="card">
    <h2>Рынок и решение</h2>
    <div class="row"><span class="label">Инструмент</span>
      <span class="value">{status.market}</span></div>
    <div class="row"><span class="label">Решение Chief AI</span>
      <span class="value {decision_class}">{status.state or "—"}</span></div>
    <div class="row"><span class="label">Уверенность</span>
      <span class="value">{confidence_text}</span></div>
    <div class="row"><span class="label">Режим рынка</span>
      <span class="value">{status.market_regime or "—"}</span></div>
    <div class="row"><span class="label">Стратегия</span>
      <span class="value">{status.active_strategy or "—"}</span></div>
    <div class="row"><span class="label">Тренд</span>{_bias_pill(status.current_trend)}</div>
    <div class="row"><span class="label">Качество сделки</span>
      <span class="value">{quality_text}</span></div>
    <div class="row"><span class="label">Риск-скор</span>
      <span class="value">{risk_score_text}</span></div>
    <div class="row"><span class="label">Статус системы</span>
      {_health_pill(status.system_health)}</div>
  </div>

  <div class="card">
    <h2>Департаменты и сводки</h2>
    <div>{department_tags}</div>
    <div class="row"><span class="label">Корреляция</span>
      <span class="value">{status.correlation_summary or "—"}</span></div>
    <div class="row"><span class="label">Order Flow</span>
      <span class="value">{status.order_flow_summary or "—"}</span></div>
    <div class="row"><span class="label">Новости</span>
      <span class="value muted">{status.news_summary or "—"}</span></div>
    <details class="trade-explanation">
      <summary>Под-сигналы модулей</summary>
      {_sub_signals_html(status.technical_sub_signals)}
    </details>
  </div>

  <div class="card">
    <h2>Подключения</h2>
    <div class="row"><span class="label">MT5</span>
      <span class="pill pill-{mt5_pill_class[status.mt5_status]}">
        {mt5_status_ru[status.mt5_status]}</span></div>
    <div class="row"><span class="label">Telegram</span>
      <span class="value">{telegram_status_text}</span></div>
    <div class="row"><span class="label">Новости (NewsAPI)</span>
      <span class="value muted">{news_status_text}</span></div>
  </div>

  <div class="card">
    <h2>Результаты</h2>
    <div class="row"><span class="label">PnL сегодня</span>
      <span class="value {today_pnl_class}">{status.today_pnl:+.2f}$</span></div>
    <div class="row"><span class="label">Win rate</span>
      <span class="value">{win_rate_text}</span></div>
    <div class="row"><span class="label">Profit factor</span>
      <span class="value">{profit_factor_text}</span></div>
    <div class="row"><span class="label">Просадка</span>
      <span class="value neg">{status.current_drawdown_usd:.2f}$</span></div>
  </div>

  <div class="card">
    <h2>Обучение и книги</h2>
    <div class="row"><span class="label">Книги обработаны</span>
      <span class="value">{status.books_summary.processed} /
      {status.books_summary.discovered}</span></div>
    <div class="row"><span class="label">Гипотезы: ожидают</span>
      <span class="value">{status.learning_progress.pending}</span></div>
    <div class="row"><span class="label">Подтверждено</span>
      <span class="value pos">{status.learning_progress.approved}</span></div>
    <div class="row"><span class="label">Отклонено</span>
      <span class="value neg">{status.learning_progress.rejected}</span></div>
  </div>
</div>

<div class="card">
  <h2>Открытые позиции</h2>
  {positions_rows}
</div>

<div class="card">
  <h2>Сигналы</h2>
  <div class="row"><span class="label">Ожидают исполнения</span>
    <span class="value">{status.pending_signals}</span></div>
</div>

<div class="card">
  <h2>Последние закрытые сделки</h2>
  <table><tr><th>Направление</th><th>P/L</th><th>Закрыта</th></tr>{closed_rows}</table>
</div>

<div class="card">
  <h2>Объяснение</h2>
  <p class="muted">{status.ai_explanation or "Пока нет анализа."}</p>
</div>
{no_trade_block}

<script>
function refreshControlStatus() {{
  fetch("/api/control/status").then(r => r.json()).then(data => {{
    let text = data.running ? "запущен" : "остановлен";
    if (data.paused) {{ text += " (на паузе)"; }}
    document.getElementById("control-status").textContent = text;
    document.getElementById("pause-button").textContent = data.paused ? "RESUME" : "PAUSE";
  }});
}}
function controlAction(action) {{
  fetch("/api/control/" + action, {{ method: "POST" }})
    .then(r => r.json())
    .then(() => {{
      document.getElementById("control-message").textContent = "Готово.";
      refreshControlStatus();
    }})
    .catch(() => {{
      document.getElementById("control-message").textContent = "Ошибка.";
    }});
}}
function emergencyClose() {{
  if (!confirm("Закрыть ВСЕ открытые позиции немедленно?")) {{ return; }}
  fetch("/api/control/emergency-close", {{ method: "POST" }})
    .then(r => r.json())
    .then(data => {{
      document.getElementById("control-message").textContent =
        "Закрыто: " + data.closed_tickets.length + ", ошибок: " + data.failed_tickets.length;
    }});
}}
refreshControlStatus();
setInterval(() => location.reload(), 15000);
</script>
""",
    )


def render_settings_html(view: SettingsView) -> str:
    """Render the settings page.

    Args:
        view: The current `SettingsView`.

    Returns:
        A complete HTML document.
    """
    telegram_status = "подключён" if view.telegram_configured else "не настроен"
    news_status = "подключён" if view.news_configured else "не настроен"
    macro_status = "подключён" if view.macro_configured else "не настроен"
    lot_size_value = view.fixed_lot_size if view.fixed_lot_size is not None else ""
    confidence_value = view.confidence_threshold if view.confidence_threshold is not None else ""
    scalping_confidence_value = (
        view.scalping_confidence_threshold if view.scalping_confidence_threshold is not None else ""
    )
    swing_confidence_value = (
        view.swing_confidence_threshold if view.swing_confidence_threshold is not None else ""
    )
    max_positions_value = view.max_positions if view.max_positions is not None else ""
    min_trade_quality_value = (
        view.min_trade_quality_score if view.min_trade_quality_score is not None else ""
    )
    books_folder_value = view.books_folder or ""
    auto_trading_checked = "checked" if view.auto_trading_enabled else ""
    intraday_checked = "checked" if view.intraday_enabled else ""
    scalping_checked = "checked" if view.scalping_enabled else ""
    swing_checked = "checked" if view.swing_enabled else ""
    shakky_checked = "checked" if view.shakky_enabled else ""
    shakky_dynamic_tp_checked = "checked" if view.shakky_dynamic_tp_enabled else ""
    shakky_scaling_checked = "checked" if view.shakky_scaling_enabled else ""
    demo_learning_checked = "checked" if view.demo_learning_mode_enabled else ""
    micro_scalping_checked = "checked" if view.micro_scalping_enabled else ""
    micro_scalping_min_confidence_value = (
        view.micro_scalping_min_confidence if view.micro_scalping_min_confidence is not None else ""
    )
    micro_scalping_max_holding_value = (
        view.micro_scalping_max_holding_minutes
        if view.micro_scalping_max_holding_minutes is not None
        else ""
    )
    micro_scalping_dynamic_profit_target_checked = (
        "checked" if view.micro_scalping_dynamic_profit_target_enabled else ""
    )
    micro_scalping_trailing_stop_checked = (
        "checked" if view.micro_scalping_trailing_stop_enabled else ""
    )
    micro_scalping_fixed_lot_value = (
        view.micro_scalping_fixed_lot_size if view.micro_scalping_fixed_lot_size is not None else ""
    )
    micro_scalping_max_spread_value = (
        view.micro_scalping_max_spread_points
        if view.micro_scalping_max_spread_points is not None
        else ""
    )

    def _option(value: str, label: str, selected: str) -> str:
        is_selected = " selected" if value == selected else ""
        return f'<option value="{value}"{is_selected}>{label}</option>'

    return _page(
        "Настройки",
        f"""
<h1>Настройки</h1>
<div class="nav"><a href="/">← Панель</a> · <a href="/books">Книги →</a></div>

<div class="card">
  <h2>Торговля</h2>
  <label>Размер лота (пусто = авто-лот по Risk Engine)</label>
  <input id="lot-size" type="number" step="0.01" value="{lot_size_value}">

  <label><input id="auto-trading" type="checkbox" {auto_trading_checked}> Авто-торговля</label>

  <label>Макс. одновременных позиций (пусто = без лимита по количеству)</label>
  <input id="max-positions" type="number" step="1" min="1" value="{max_positions_value}">

  <label>Режим риска</label>
  <select id="risk-mode">
    {_option("conservative", "Консервативный", view.risk_mode)}
    {_option("normal", "Обычный", view.risk_mode)}
    {_option("aggressive", "Агрессивный", view.risk_mode)}
  </select>

  <label>Минимальный Trade Quality Score, 0-100 (пусто = по умолчанию)</label>
  <input id="min-trade-quality" type="number" step="1" min="0" max="100"
    value="{min_trade_quality_value}">

  <label><input id="demo-learning-mode" type="checkbox" {demo_learning_checked}>
    Demo Learning Mode (снимает лимит числа позиций и смягчает пороги уверенности
    ради максимума статистики)</label>

  <button onclick="save()">Сохранить</button>
  <p id="save-status" class="muted"></p>
</div>

<div class="card">
  <h2>Стратегии</h2>
  <label><input id="intraday-enabled" type="checkbox" {intraday_checked}> Intraday-движок</label>
  <label>Порог уверенности Intraday, % (пусто = по умолчанию)</label>
  <input id="confidence-threshold" type="number" step="1" value="{confidence_value}">

  <label><input id="scalping-enabled" type="checkbox" {scalping_checked}> Скальпинг-движок</label>
  <label>Порог уверенности Скальпинг, % (пусто = по умолчанию)</label>
  <input id="scalping-confidence-threshold" type="number" step="1"
    value="{scalping_confidence_value}">

  <label><input id="swing-enabled" type="checkbox" {swing_checked}> Свинг-движок</label>
  <label>Порог уверенности Свинг, % (пусто = по умолчанию)</label>
  <input id="swing-confidence-threshold" type="number" step="1" value="{swing_confidence_value}">

  <label><input id="shakky-enabled" type="checkbox" {shakky_checked}> Classic M5 Strategy
    (Shakky) -- независимый rule-based движок, без AI-порога уверенности</label>
  <label><input id="shakky-dynamic-tp-enabled" type="checkbox" {shakky_dynamic_tp_checked}>
    Shakky: Dynamic Take Profit (даёт прибыльной сделке дойти дальше при сильном тренде)</label>
  <label><input id="shakky-scaling-enabled" type="checkbox" {shakky_scaling_checked}>
    Shakky: Position Scaling (добавляет объём только в прибыльную позицию при росте тренда)</label>

  <button onclick="save()">Сохранить</button>
</div>

<div class="card">
  <h2>Микро-скальп</h2>
  <label><input id="micro-scalping-enabled" type="checkbox" {micro_scalping_checked}>
    Микро-скальп -- отдельный движок, использующий подтверждения Shakky, закрывающий
    сделки за секунды-минуты при небольшой цели по прибыли</label>

  <label>Минимальная уверенность (Trend Confidence), % (пусто = по умолчанию)</label>
  <input id="micro-scalping-min-confidence" type="number" step="1"
    value="{micro_scalping_min_confidence_value}">

  <label>Максимальное время удержания, мин (пусто = по умолчанию)</label>
  <input id="micro-scalping-max-holding" type="number" step="1" min="1"
    value="{micro_scalping_max_holding_value}">

  <label><input id="micro-scalping-dynamic-profit-target-enabled" type="checkbox"
    {micro_scalping_dynamic_profit_target_checked}>
    Динамическая цель по прибыли (позволяет продлить сделку при сильном импульсе)</label>

  <label><input id="micro-scalping-trailing-stop-enabled" type="checkbox"
    {micro_scalping_trailing_stop_checked}>
    Трейлинг-стоп (вместо немедленного закрытия при сильном импульсе)</label>

  <label>Режим размера лота</label>
  <select id="micro-scalping-lot-mode">
    {_option("manual", "Ручной (фиксированный лот)", view.micro_scalping_lot_mode)}
    {_option("auto", "Авто (по риску)", view.micro_scalping_lot_mode)}
  </select>

  <label>Фиксированный лот (используется в ручном режиме, пусто = по умолчанию)</label>
  <input id="micro-scalping-fixed-lot" type="number" step="0.01"
    value="{micro_scalping_fixed_lot_value}">

  <label>Максимальный спред, пункты (пусто = по умолчанию)</label>
  <input id="micro-scalping-max-spread" type="number" step="1" min="1"
    value="{micro_scalping_max_spread_value}">

  <button onclick="save()">Сохранить</button>
</div>

<div class="card">
  <h2>Книги</h2>
  <label>Папка книг (пусто = папка по умолчанию)</label>
  <input id="books-folder" type="text" value="{books_folder_value}" placeholder="books">
  <button onclick="save()">Сохранить</button>
</div>

<div class="card">
  <h2>Подключения (только чтение)</h2>
  <div class="row"><span class="label">Telegram</span>
    <span class="value">{telegram_status}</span></div>
  <div class="row"><span class="label">Новости (NewsAPI)</span>
    <span class="value muted">{news_status}</span></div>
  <div class="row"><span class="label">Макро (FRED)</span>
    <span class="value muted">{macro_status}</span></div>
  <div class="row"><span class="label">Коррелированные инструменты</span>
    <span class="value">{view.correlated_instruments_enabled} активно</span></div>
</div>

<script>
function save() {{
  const lotSize = document.getElementById("lot-size").value;
  const confidence = document.getElementById("confidence-threshold").value;
  const scalpingConfidence = document.getElementById("scalping-confidence-threshold").value;
  const swingConfidence = document.getElementById("swing-confidence-threshold").value;
  const maxPositions = document.getElementById("max-positions").value;
  const minTradeQuality = document.getElementById("min-trade-quality").value;
  const booksFolder = document.getElementById("books-folder").value;
  const microScalpingMinConfidence =
    document.getElementById("micro-scalping-min-confidence").value;
  const microScalpingMaxHolding = document.getElementById("micro-scalping-max-holding").value;
  const microScalpingFixedLot = document.getElementById("micro-scalping-fixed-lot").value;
  const microScalpingMaxSpread = document.getElementById("micro-scalping-max-spread").value;
  const payload = {{
    auto_trading_enabled: document.getElementById("auto-trading").checked,
    intraday_enabled: document.getElementById("intraday-enabled").checked,
    scalping_enabled: document.getElementById("scalping-enabled").checked,
    swing_enabled: document.getElementById("swing-enabled").checked,
    shakky_enabled: document.getElementById("shakky-enabled").checked,
    shakky_dynamic_tp_enabled: document.getElementById("shakky-dynamic-tp-enabled").checked,
    shakky_scaling_enabled: document.getElementById("shakky-scaling-enabled").checked,
    demo_learning_mode_enabled: document.getElementById("demo-learning-mode").checked,
    micro_scalping_enabled: document.getElementById("micro-scalping-enabled").checked,
    micro_scalping_min_confidence:
      microScalpingMinConfidence === "" ? null : parseFloat(microScalpingMinConfidence),
    clear_micro_scalping_min_confidence: microScalpingMinConfidence === "",
    micro_scalping_max_holding_minutes:
      microScalpingMaxHolding === "" ? null : parseFloat(microScalpingMaxHolding),
    clear_micro_scalping_max_holding_minutes: microScalpingMaxHolding === "",
    micro_scalping_dynamic_profit_target_enabled: document.getElementById(
      "micro-scalping-dynamic-profit-target-enabled"
    ).checked,
    micro_scalping_trailing_stop_enabled: document.getElementById(
      "micro-scalping-trailing-stop-enabled"
    ).checked,
    micro_scalping_lot_mode: document.getElementById("micro-scalping-lot-mode").value,
    micro_scalping_fixed_lot_size:
      microScalpingFixedLot === "" ? null : parseFloat(microScalpingFixedLot),
    clear_micro_scalping_fixed_lot_size: microScalpingFixedLot === "",
    micro_scalping_max_spread_points:
      microScalpingMaxSpread === "" ? null : parseFloat(microScalpingMaxSpread),
    clear_micro_scalping_max_spread_points: microScalpingMaxSpread === "",
    risk_mode: document.getElementById("risk-mode").value,
    fixed_lot_size: lotSize === "" ? null : parseFloat(lotSize),
    clear_fixed_lot_size: lotSize === "",
    confidence_threshold: confidence === "" ? null : parseFloat(confidence),
    clear_confidence_threshold: confidence === "",
    scalping_confidence_threshold:
      scalpingConfidence === "" ? null : parseFloat(scalpingConfidence),
    clear_scalping_confidence_threshold: scalpingConfidence === "",
    swing_confidence_threshold: swingConfidence === "" ? null : parseFloat(swingConfidence),
    clear_swing_confidence_threshold: swingConfidence === "",
    max_positions: maxPositions === "" ? null : parseInt(maxPositions, 10),
    clear_max_positions: maxPositions === "",
    min_trade_quality_score: minTradeQuality === "" ? null : parseFloat(minTradeQuality),
    clear_min_trade_quality_score: minTradeQuality === "",
    books_folder: booksFolder === "" ? null : booksFolder,
    clear_books_folder: booksFolder === "",
  }};
  fetch("/api/settings", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(payload),
  }}).then(r => {{
    document.getElementById("save-status").textContent = r.ok ? "Сохранено." : "Ошибка сохранения.";
  }});
}}
</script>
""",
    )


def render_strategy_builder_html(view: StrategyProfilesView) -> str:
    """Render the Strategy Builder page.

    Per the "Complete Strategy Builder" production requirement: enable/
    disable and weight every analysis module independently, save/load
    named profiles, and assign a saved profile to each of the three
    independent strategies.

    Args:
        view: The current `StrategyProfilesView`.

    Returns:
        A complete HTML document.
    """

    def _option(value: str, label: str, selected: str | None) -> str:
        is_selected = " selected" if value == (selected or "") else ""
        return f'<option value="{value}"{is_selected}>{label}</option>'

    module_rows = "".join(
        f"""<div class="row"><span class="label">
      <input type="checkbox" class="module-enabled" data-module="{name}" checked> {name}</span>
      <input type="number" class="module-weight" data-module="{name}" value="1.0"
        step="0.1" min="0" style="width:5rem;"></div>"""
        for name in view.module_names
    )

    def _assignment_select(key: str, label: str) -> str:
        assigned = view.assignments.get(key)
        options = "".join(_option(p.name, p.name, assigned) for p in view.profiles)
        return f"""<div class="row"><span class="label">{label}</span>
      <select id="assign-{key}" style="width:auto;min-width:10rem;">
        {_option("", "— нет —", assigned)}
        {options}
      </select></div>"""

    assignment_selects = "".join(
        _assignment_select(key, label)
        for key, label in (("intraday", "Intraday"), ("scalping", "Скальпинг"), ("swing", "Свинг"))
    )

    profile_list = (
        "".join(
            f'<div class="row"><span class="label">{profile.name}</span>'
            f"<button onclick=\"deleteProfile('{profile.name}')\" "
            f'style="margin-top:0;background:var(--red);">Удалить</button></div>'
            for profile in view.profiles
        )
        or '<div class="muted">Пока нет сохранённых профилей</div>'
    )

    return _page(
        "Strategy Builder",
        f"""
<h1>Strategy Builder</h1>
<div class="nav"><a href="/">← Панель</a> · <a href="/settings">Настройки →</a></div>

<div class="card">
  <h2>Назначение профилей стратегиям</h2>
  {assignment_selects}
  <button onclick="assignAll()">Применить назначения</button>
  <p id="assign-status" class="muted"></p>
</div>

<div class="card">
  <h2>Сохранённые профили</h2>
  {profile_list}
</div>

<div class="card">
  <h2>Новый профиль</h2>
  <label>Название профиля</label>
  <input id="profile-name" type="text" placeholder="Conservative">
  <p class="muted">Отметьте нужные модули и укажите вес. Отключённый модуль не участвует
    в решении. Модули, оставленные без изменений, сохраняют поведение по умолчанию.</p>
  {module_rows}
  <button onclick="saveProfile()">Сохранить профиль</button>
  <p id="save-status" class="muted"></p>
</div>

<script>
function saveProfile() {{
  const name = document.getElementById("profile-name").value;
  if (!name) {{ document.getElementById("save-status").textContent = "Укажите название."; return; }}
  const modules = [];
  document.querySelectorAll(".module-enabled").forEach(checkbox => {{
    const moduleName = checkbox.dataset.module;
    const weightInput = document.querySelector(
      '.module-weight[data-module="' + moduleName + '"]');
    modules.push({{
      module_name: moduleName,
      enabled: checkbox.checked,
      weight: parseFloat(weightInput.value) || 1.0,
    }});
  }});
  fetch("/api/strategy-profiles", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{name: name, modules: modules}}),
  }}).then(r => {{
    document.getElementById("save-status").textContent = r.ok ? "Сохранено." : "Ошибка сохранения.";
    if (r.ok) {{ setTimeout(() => location.reload(), 800); }}
  }});
}}
function deleteProfile(name) {{
  if (!confirm("Удалить профиль " + name + "?")) {{ return; }}
  fetch("/api/strategy-profiles/" + encodeURIComponent(name), {{ method: "DELETE" }})
    .then(() => location.reload());
}}
function assignAll() {{
  const strategies = ["intraday", "scalping", "swing"];
  Promise.all(strategies.map(strategy => {{
    const value = document.getElementById("assign-" + strategy).value;
    return fetch("/api/strategy-profiles/assign", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{strategy: strategy, profile_name: value === "" ? null : value}}),
    }});
  }})).then(() => {{
    document.getElementById("assign-status").textContent = "Применено.";
  }});
}}
</script>
""",
    )


def _format_pct(value: float | None, *, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%" if value is not None else "—"


def _format_ratio(value: float) -> str:
    return "∞" if value == float("inf") else f"{value:.2f}"


def _format_price_distance(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"


def _format_holding_time(value: timedelta | None) -> str:
    if value is None:
        return "—"
    total_hours = value.total_seconds() / 3600
    if total_hours < 24:
        return f"{total_hours:.1f} ч"
    return f"{total_hours / 24:.1f} дн"


def _strategy_comparison_row_html(perf: StrategyPerformance) -> str:
    report = perf.report
    label = _STRATEGY_LABELS_RU.get(perf.strategy.lower(), perf.strategy)
    if report.trade_count == 0:
        return (
            f"""<tr><td>{label}</td><td colspan="8" class="muted">Нет закрытых сделок</td></tr>"""
        )
    return f"""<tr>
  <td>{label}</td>
  <td>{report.trade_count}</td>
  <td>{_format_pct(report.win_rate * 100)}</td>
  <td>{_format_ratio(report.profit_factor)}</td>
  <td>{_format_pct(report.average_win_pct)}</td>
  <td>{_format_pct(report.average_loss_pct)}</td>
  <td>{_format_holding_time(report.average_holding_time)}</td>
  <td>{_format_price_distance(perf.average_mfe)}</td>
  <td>{_format_price_distance(perf.average_mae)}</td>
  <td>{_format_pct(perf.average_quality_score, decimals=0)}</td>
</tr>"""


def render_strategy_comparison_html(view: StrategyPerformanceView) -> str:
    """Render the "Сравнение стратегий" page.

    Per the user's own "Strategy Comparison" requirement: compares
    Shakky against every other strategy on Win Rate, Profit Factor,
    Average Win/Loss, Average Holding Time, Maximum Favorable/Adverse
    Excursion, and Trade Quality -- one row per strategy, always all
    four (an empty track record is shown honestly, never omitted).
    """
    rows_html = "\n".join(_strategy_comparison_row_html(perf) for perf in view.strategies)
    ranking_html = (
        "".join(
            f'<div class="row"><span class="label">'
            f"{rank.rank}. {_STRATEGY_LABELS_RU.get(rank.strategy.lower(), rank.strategy)}</span>"
            f'<span class="value">{_format_ratio(rank.profit_factor)}</span></div>'
            for rank in view.ranking
        )
        if view.ranking
        else '<p class="muted">Пока нет стратегий с закрытыми сделками для ранжирования.</p>'
    )

    return _page(
        "Сравнение стратегий",
        f"""
<h1>Сравнение стратегий</h1>
<div class="nav"><a href="/">← Панель</a> · <a href="/settings">Настройки →</a></div>

<div class="card">
  <h2>Показатели по стратегиям</h2>
  <div style="overflow-x: auto;">
  <table>
    <tr>
      <th>Стратегия</th><th>Сделок</th><th>Win Rate</th><th>Profit Factor</th>
      <th>Ср. прибыль</th><th>Ср. убыток</th><th>Ср. время в сделке</th>
      <th>Ср. MFE</th><th>Ср. MAE</th><th>Ср. Trade Quality</th>
    </tr>
    {rows_html}
  </table>
  </div>
</div>

<div class="card">
  <h2>Рейтинг по Profit Factor</h2>
  {ranking_html}
</div>
""",
    )
