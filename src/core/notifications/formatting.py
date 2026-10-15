"""Telegram message formatting.

Per the "Telegram" production requirement: "Messages must be short.
Russian language. Simple words. Use emojis." Every formatter here builds
plain text purely from already-computed data -- never inventing a field
the caller did not supply. Upstream English/internal reason codes (e.g.
`PositionPreCloseAssessment.reasons`, department vote keys) are treated
as internal data, translated to short Russian phrases only here, at the
display boundary -- their own modules and tests stay untouched.

Deliberately plain text, not Telegram's legacy Markdown mode: dynamic
fields here (news headlines, error messages) can legitimately contain
`*`/`_`/`` ` ``/`[` characters, and legacy Markdown parses the whole
message as one document -- one stray special character anywhere makes
Telegram reject the entire message
(`src.core.notifications.telegram_client.RealTelegramNotifier.send_message`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.historical_engine.similarity import SimilarityDisplayStats
from src.engines.learning_engine.post_mortem import PostMortemReport
from src.models.improvement_proposal import ImprovementProposal
from src.models.news_article import NewsArticle
from src.models.trade import Trade
from src.workflows.reporting.pre_close_report import PositionPreCloseAssessment

# Shared department-key -> short Russian label mapping, used both for the
# signal message's "reason" bullets and the post-mortem's disagreeing/
# missing department lists. Keys match `department_votes` dict keys
# actually produced by `src.workflows.market_update.pipeline` and
# `src.services.scheduler.live_loop._scalping_decision` -- an unknown key
# falls back to itself rather than crashing, since new departments are
# occasionally added.
_RU_DEPARTMENT_NAMES: dict[str, str] = {
    "technical": "Технический анализ",
    "historical": "История",
    "ml": "ML-модель",
    "correlation": "Корреляция",
    "order_flow": "Order Flow",
    "scalping_engine": "Скальпинг",
    "swing_engine": "Свинг",
    "macro": "Макро",
    "news": "Новости",
}


def _ru_department_label(name: str) -> str:
    return _RU_DEPARTMENT_NAMES.get(name, name)


# Maps a `strategy_name`'s own suffix (see `_SCALPING_STRATEGY_SUFFIX`/
# `_SWING_STRATEGY_SUFFIX` in `src.services.scheduler.live_loop`) to a
# short Russian strategy label for the Telegram signal message's
# "Стратегия" line -- no suffix means the primary (Intraday) engine.
_STRATEGY_SUFFIX_LABELS_RU: tuple[tuple[str, str], ...] = (
    ("_scalp", "Скальпинг"),
    ("_swing", "Свинг"),
)


def _strategy_label_ru(strategy_name: str) -> str:
    for suffix, label in _STRATEGY_SUFFIX_LABELS_RU:
        if strategy_name.endswith(suffix):
            return label
    return "Intraday"


def build_reason_tags_ru(votes: dict[str, dict[str, float | str]]) -> list[str]:
    """Build short Russian "reason" bullets from a cycle's department votes.

    Args:
        votes: `{department_name: {"bias": ..., "confidence": ...}}`, the
            same snapshot persisted on `Trade.department_votes`.

    Returns:
        One short `"{department} {arrow}"` tag per non-neutral
        department, e.g. `["Тренд ↑", "Корреляция ↓"]`. Neutral
        departments contribute nothing meaningful to a short reason list,
        so they are omitted, never a fabricated tag.
    """
    tags: list[str] = []
    for name, vote in votes.items():
        bias = vote.get("bias")
        if bias == "bullish":
            tags.append(f"{_ru_department_label(name)} ↑")
        elif bias == "bearish":
            tags.append(f"{_ru_department_label(name)} ↓")
    return tags


def build_reason_tags_ru_for_direction(
    votes: dict[str, dict[str, float | str]], direction: Literal["BUY", "SELL"]
) -> list[str]:
    """Build ✅/❌ "reason" bullets relative to the trade's own direction.

    Per the "Telegram" production requirement's exact example format:
    "✅ DXY падает... ❌ Сильное сопротивление рядом" -- a department that
    agrees with the executed direction gets ✅, one that opposed it (but
    did not block the trade, e.g. a minority vote) gets ❌. Distinct from
    `build_reason_tags_ru`'s direction-agnostic bullish/bearish arrows,
    which existing callers (post-mortem) still use unchanged.

    Args:
        votes: `{department_name: {"bias": ..., "confidence": ...}}`.
        direction: The executed trade's own direction.

    Returns:
        One `"✅/❌ {department}"` tag per non-neutral department. Neutral
        departments are omitted, never a fabricated tag.
    """
    supporting_bias = "bullish" if direction == "BUY" else "bearish"
    opposing_bias = "bearish" if direction == "BUY" else "bullish"
    tags: list[str] = []
    for name, vote in votes.items():
        bias = vote.get("bias")
        if bias == supporting_bias:
            tags.append(f"✅ {_ru_department_label(name)}")
        elif bias == opposing_bias:
            tags.append(f"❌ {_ru_department_label(name)}")
    return tags


@dataclass(frozen=True, slots=True)
class SignalMessageData:
    """Fields for a Telegram "Signal Message".

    Attributes:
        trade_id: Journal reference for this signal.
        market: Symbol name, e.g. "XAUUSD".
        direction: "BUY" or "SELL".
        strategy_name: The executing engine's own `strategy_name` (with
            its `_scalp`/`_swing` suffix, if any) -- mapped to a short
            Russian label via `_strategy_label_ru`.
        entry_price: Planned entry price.
        stop_loss: Protective stop price.
        take_profit: Target price, if any.
        confidence_pct: Overall decision confidence, 0-100.
        quality_score: The Trade Quality Engine's 0-100 score
            (`src.engines.chief_ai.trade_quality`).
        reason_tags: Short Russian ✅/❌ evidence bullets, e.g.
            `["✅ Тренд", "❌ Корреляция"]` (see
            `build_reason_tags_ru_for_direction`).
        similarity_summary: Per the "Trade Similarity Engine" production
            requirement: "Display this information before every trade" --
            None omits the block entirely (Shakky trades never have one,
            per that engine's own spec).
    """

    trade_id: str
    market: str
    direction: Literal["BUY", "SELL"]
    strategy_name: str
    entry_price: float
    stop_loss: float
    take_profit: float | None
    confidence_pct: float
    quality_score: float
    reason_tags: list[str] = field(default_factory=list)
    similarity_summary: SimilarityDisplayStats | None = None


def _format_similarity_block_ru(stats: SimilarityDisplayStats) -> str:
    """Format the Trade Similarity Engine's "before every trade" block.

    Per the "Trade Similarity Engine" production requirement: "Return:
    How many similar situations were found. How many became profitable.
    How many failed. Average RR. Average holding time. Average drawdown."
    """
    lines = [f"🔍 Похожие ситуации: {stats.found_count}"]
    if stats.win_rate_pct is not None:
        lines.append(
            f"Прибыльных: {stats.profitable_count} | "
            f"Провал: {stats.failed_count} ({stats.win_rate_pct:.0f}%)"
        )
    if stats.average_rr is not None:
        lines.append(f"Средний RR: {stats.average_rr:.1f}")
    if stats.average_drawdown_pct is not None:
        lines.append(f"Ср. просадка: {stats.average_drawdown_pct:.2f}%")
    lines.append(f"Ожид. время: {stats.average_holding_time_minutes:.0f} мин")
    return "\n".join(lines)


def format_signal_message(data: SignalMessageData) -> str:
    """Format a Telegram "Signal Message".

    Per the "Telegram" production requirement's own exact example format
    (short, Russian, one value per labeled line, blank line between
    fields).

    Args:
        data: The signal's fields.

    Returns:
        Short Russian text with emoji, e.g.:
        "🟢 BUY XAUUSD\\n\\n📈 Стратегия:\\nSwing\\n\\n⭐ Качество:\\n91/100\\n..."
    """
    direction_emoji = "🟢" if data.direction == "BUY" else "🔴"
    verdict = "Покупка подтверждена." if data.direction == "BUY" else "Продажа подтверждена."
    blocks = [
        f"{direction_emoji} {data.direction} {data.market}",
        f"📈 Стратегия:\n{_strategy_label_ru(data.strategy_name)}",
        f"⭐ Качество:\n{data.quality_score:.0f}/100",
        f"📊 Уверенность:\n{data.confidence_pct:.0f}%",
        f"💰 Вход:\n{data.entry_price:.2f}",
        f"🛑 SL:\n{data.stop_loss:.2f}",
    ]
    if data.take_profit is not None:
        blocks.append(f"🎯 TP:\n{data.take_profit:.2f}")
    if data.reason_tags:
        blocks.append("📌 Причины:\n" + "\n".join(data.reason_tags))
    if data.similarity_summary is not None and data.similarity_summary.found_count > 0:
        blocks.append(_format_similarity_block_ru(data.similarity_summary))
    blocks.append(f"🧠 Chief AI:\n{verdict}")
    blocks.append(f"Журнал: {data.trade_id}")
    return "\n\n".join(blocks)


_POSITION_EVENT_LABELS: dict[str, str] = {
    "sl_moved": "🔧 Стоп подвинут",
    "breakeven": "⚖️ Безубыток",
    "partial_close": "✂️ Частичное закрытие",
    "scale_in": "➕ Добавили объём",
    "scale_out": "➖ Уменьшили объём",
}


@dataclass(frozen=True, slots=True)
class PositionEventData:
    """Fields for an in-trade Telegram event notification.

    Per the spec: "During the trade send: SL moved, Break-even, Partial
    close, Scale in, Scale out."

    Attributes:
        event: One of `_POSITION_EVENT_LABELS`' keys.
        trade_id: Journal reference.
        market: Symbol name, e.g. "XAUUSD".
        reason: Why this action was taken, short Russian text (never a
            bare label -- always the actual driving factor).
        new_stop_loss: The position's stop after this event, if changed.
        volume_change: Signed change in position size (positive for scale
            in/add, negative for partial close/scale out), if applicable.
        current_price: The price at the moment of this event.
    """

    event: str
    trade_id: str
    market: str
    reason: str
    new_stop_loss: float | None = None
    volume_change: float | None = None
    current_price: float | None = None


def format_position_event_message(data: PositionEventData) -> str:
    """Format an in-trade Telegram event notification.

    Args:
        data: The event's fields.

    Returns:
        Short Russian text with emoji.

    Raises:
        KeyError: If `data.event` is not one of `_POSITION_EVENT_LABELS`.
    """
    label = _POSITION_EVENT_LABELS[data.event]
    lines = [f"{label} — {data.market}"]
    if data.current_price is not None:
        lines.append(f"Цена: {data.current_price:.2f}")
    if data.new_stop_loss is not None:
        lines.append(f"Новый стоп: {data.new_stop_loss:.2f}")
    if data.volume_change is not None:
        lines.append(f"Изменение объёма: {data.volume_change:+.4f}")
    lines.append(data.reason)
    lines.append(f"Журнал: {data.trade_id}")
    return "\n".join(lines)


# Tolerance (in price points) used to decide whether a closed trade's
# exit price was close enough to its stop/target to honestly call it
# "stopped out"/"target hit" rather than an approximate, uncertain
# closure (broker reconciliation, manual close) -- matches this
# platform's XAUUSD point-size conventions used elsewhere
# (`src.workflows.market_update.pipeline._POINT_SIZE`-scale reasoning).
_CLOSE_REASON_PROXIMITY_TOLERANCE = 0.5


def _infer_close_reason_ru(
    *, exit_price: float, stop_loss: float, take_profit: float | None
) -> str:
    """Infer a short, honest Russian reason for why a trade closed.

    Never claims certainty beyond what `exit_price`'s proximity to the
    recorded stop/target actually supports -- falls back to a neutral
    label rather than a fabricated one.
    """
    if (
        take_profit is not None
        and abs(exit_price - take_profit) <= _CLOSE_REASON_PROXIMITY_TOLERANCE
    ):
        return "Тейк-профит достигнут"
    if abs(exit_price - stop_loss) <= _CLOSE_REASON_PROXIMITY_TOLERANCE:
        return "Сработал стоп-лосс"
    return "Закрыта по рыночному сигналу"


def format_trade_closed_message(trade: Trade, *, prediction_accuracy: str | None = None) -> str:
    """Format a Telegram "Trade Closed Message".

    Args:
        trade: The closed `Trade`.
        prediction_accuracy: Optional caller-supplied prediction-accuracy note.

    Returns:
        Short Russian text with emoji, e.g. "✅ Профит +18.00$\\n...".

    Raises:
        ValueError: If `trade.entry_price` or `trade.exit_price` is missing.
    """
    if trade.entry_price is None or trade.exit_price is None:
        raise ValueError("A closed trade must have both entry_price and exit_price recorded")

    is_profit = (trade.realized_pnl or 0.0) >= 0
    pnl_emoji = "✅" if is_profit else "❌"
    pnl_label = "Профит" if is_profit else "Убыток"
    pnl_text = f"{trade.realized_pnl:+.2f}$" if trade.realized_pnl is not None else "неизвестно"
    close_reason = _infer_close_reason_ru(
        exit_price=trade.exit_price, stop_loss=trade.stop_loss, take_profit=trade.take_profit
    )
    lines = [
        f"{pnl_emoji} {pnl_label} {pnl_text}",
        f"{trade.direction.upper()} {close_reason}",
    ]
    if prediction_accuracy is not None:
        lines.append(prediction_accuracy)
    lines.append(f"Журнал: {trade.id}")
    return "\n".join(lines)


def format_post_mortem_message(report: PostMortemReport, *, market: str) -> str:
    """Format a Telegram "Post Trade Analysis" notification for a closed trade.

    Per the "Post Trade Analysis" production requirement: every closed
    trade -- win or loss -- automatically answers "Would Chief AI open
    this trade again, knowing the outcome?" (`report.would_repeat`), with
    supporting detail on which departments disagreed or were missing.
    Never proposes a strategy change itself -- a recurring pattern across
    losing trades separately raises a pending `ImprovementProposal`
    requiring explicit user approval.

    Args:
        report: The generated `PostMortemReport`.
        market: Symbol name, e.g. "XAUUSD".

    Returns:
        Short Russian text with emoji.
    """
    verdict_ru = "ДА" if report.would_repeat else "НЕТ"
    lines = [
        f"🔍 Разбор сделки — {market}",
        f"Результат: {report.review.r_multiple:+.2f}R ({report.review.realized_return_pct:+.2f}%)",
        f"Открыли бы снова: {verdict_ru}",
    ]
    if report.disagreeing_departments:
        disagreeing = ", ".join(
            _ru_department_label(name) for name in report.disagreeing_departments
        )
        lines.append(f"Были против: {disagreeing}")
    if report.missing_departments:
        missing = ", ".join(_ru_department_label(name) for name in report.missing_departments)
        lines.append(f"Не хватало данных: {missing}")
    correct = [name for name, ok in report.department_correctness.items() if ok]
    wrong = [name for name, ok in report.department_correctness.items() if not ok]
    if correct:
        lines.append(
            f"Оказались правы: {', '.join(_ru_department_label(name) for name in correct)}"
        )
    if wrong:
        lines.append(f"Ошиблись: {', '.join(_ru_department_label(name) for name in wrong)}")
    lines.append(f"Журнал: {report.trade_id}")
    return "\n".join(lines)


# Internal English reason tags produced by
# `src.workflows.reporting.pre_close_report.assess_position_before_close`
# (kept in English there since its own tests assert on the exact tag
# text) translated to short Russian phrases for display only.
_KNOWN_PRE_CLOSE_REASON_TRANSLATIONS: dict[str, str] = {
    "no_strong_directional_signal_this_cycle": "Нет сильного сигнала",
    "position_in_profit": "Позиция в плюсе",
    "position_in_loss": "Позиция в минусе",
}


def _translate_pre_close_reason_ru(tag: str) -> str:
    if tag.startswith("current_decision_agrees:"):
        direction, _, pct = tag.removeprefix("current_decision_agrees:").partition("@")
        return f"Сигнал подтверждает {direction} {pct}"
    if tag.startswith("current_decision_opposes:"):
        direction, _, pct = tag.removeprefix("current_decision_opposes:").partition("@")
        return f"Сигнал против, за {direction} {pct}"
    return _KNOWN_PRE_CLOSE_REASON_TRANSLATIONS.get(tag, tag)


def format_pre_close_report_message(assessment: PositionPreCloseAssessment) -> str:
    """Format a Telegram "Before Market Close" position report.

    Per the "Before Market Close" production requirement: 30 minutes
    before the session close, every open position gets a report with a
    recommendation, confidence, reasons, and (on the day the weekly close
    approaches) a weekend gap risk note.

    Args:
        assessment: The generated `PositionPreCloseAssessment`.

    Returns:
        Short Russian text with emoji.
    """
    recommendation_ru = "ДЕРЖАТЬ" if assessment.recommendation == "keep" else "ЗАКРЫТЬ"
    reasons_ru = "; ".join(_translate_pre_close_reason_ru(tag) for tag in assessment.reasons)
    lines = [
        f"🌙 Перед закрытием рынка — {assessment.market}",
        f"Рекомендация: {recommendation_ru}",
        f"Уверенность: {assessment.confidence_pct:.0f}%",
        f"Причина: {reasons_ru}",
    ]
    if assessment.weekend_risk is not None:
        weekend_note = (
            "⚠️ Повышенный риск гэпа на выходных"
            if assessment.weekend_risk.startswith("Elevated")
            else "Риск гэпа на выходных: низкий"
        )
        lines.append(weekend_note)
    lines.append(f"Журнал: {assessment.trade_id}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class DailyReportData:
    """Fields for a Telegram "Daily Report".

    Attributes:
        report_date: The date this report covers.
        total_signals: Number of signals generated.
        executed_trades: Number of trades actually executed.
        winning_trades: Number of winning trades.
        losing_trades: Number of losing trades.
        win_rate: Fraction of executed trades that won.
        profit_factor: Gross profit / gross loss.
        net_result_pct: Net result, in percent.
        system_health: Short system-health note.
    """

    report_date: str
    total_signals: int
    executed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    net_result_pct: float
    system_health: str = "OK"


def format_daily_report(data: DailyReportData) -> str:
    """Format a Telegram "Daily Report".

    Args:
        data: The report's fields.

    Returns:
        Short Russian text with emoji.
    """
    return (
        f"📅 Итоги дня — {data.report_date}\n"
        f"Сигналов: {data.total_signals} | Сделок: {data.executed_trades}\n"
        f"Побед: {data.winning_trades} | Убытков: {data.losing_trades} "
        f"(винрейт {data.win_rate:.0%})\n"
        f"Profit factor: {data.profit_factor:.2f} | Итог: {data.net_result_pct:+.2f}%\n"
        f"Система: {data.system_health}"
    )


def format_news_alert(article: NewsArticle) -> str:
    """Format a Telegram "News Alert".

    Args:
        article: The classified, scored `NewsArticle`.

    Returns:
        Short Russian text with emoji.
    """
    return (
        f"📰 Новость — {article.title}\n"
        f"Источник: {article.source} | Важность: {article.importance_score:.2f}\n"
        f"Ожидаемая волатильность: {article.expected_volatility}\n"
        f"Категория: {article.category or 'не определена'}"
    )


@dataclass(frozen=True, slots=True)
class ErrorReportData:
    """Fields for a Telegram "Error Report".

    Attributes:
        timestamp: When the error occurred.
        module: The module/component that raised it.
        error: A short error description.
        severity: One of "low", "medium", "high", "critical".
        automatic_recovery: Whether the system recovered automatically.
        manual_action_required: Whether a human must intervene.
        status: Current status, e.g. "resolved", "monitoring".
    """

    timestamp: datetime
    module: str
    error: str
    severity: str
    automatic_recovery: bool
    manual_action_required: bool
    status: str


def format_error_report(data: ErrorReportData) -> str:
    """Format a Telegram "Error Report".

    Args:
        data: The report's fields.

    Returns:
        Short Russian text with emoji.
    """
    return (
        f"⚠️ Ошибка [{data.severity.upper()}] — {data.module}\n"
        f"{data.error}\n"
        f"Восстановлено автоматически: {'да' if data.automatic_recovery else 'нет'} | "
        f"Нужно вмешательство: {'да' if data.manual_action_required else 'нет'}\n"
        f"Статус: {data.status}"
    )


def format_approval_request(proposal: ImprovementProposal) -> str:
    """Format a Telegram "Approval Request".

    Args:
        proposal: The pending `ImprovementProposal`.

    Returns:
        Short Russian text with emoji, ending with the Approve/Reject/
        Postpone choices the user must make.
    """
    return (
        f"✅ Нужно подтверждение — {proposal.title}\n"
        f"Проблема: {proposal.problem}\n"
        f"Доказательства: {proposal.evidence}\n"
        f"Ожидаемая польза: {proposal.expected_benefit}\n"
        f"Возможный риск: {proposal.potential_risk}\n"
        f"Сложность: {proposal.implementation_difficulty}\n"
        f"Рекомендация: {proposal.recommendation}\n"
        f"Ответ: Approve / Reject / Postpone (ref: {proposal.id})"
    )


# Every fixed (no embedded value) reason code `src.engines.chief_ai.decision.evaluate`
# and `src.engines.risk_engine.approval.evaluate_trade` can produce on a WAIT
# decision, translated to a short Russian phrase for the "No Trade" explanation.
# An unrecognized or value-embedding code (e.g. "spread_excessive: 45 > max 35")
# falls back to a prefix match in `_translate_no_trade_reason_ru` below, and
# ultimately to the raw code itself -- never a fabricated translation.
_KNOWN_NO_TRADE_REASON_TRANSLATIONS: dict[str, str] = {
    "market_closed": "Рынок закрыт",
    "critical_news_imminent": "Приближаются важные новости",
    "data_incomplete": "Неполные данные",
    "system_health_degraded": "Проблемы со здоровьем системы",
    "conflicting_departments": "Департаменты дают противоречивые сигналы",
    "unknown_market_regime": "Режим рынка не определён",
    "required_report_missing": "Не хватает обязательных данных",
}
_NO_TRADE_REASON_PREFIX_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("risk_rejected:confidence_level_not_executable", "Недостаточная уверенность для исполнения"),
    ("risk_rejected:spread_excessive", "Слишком широкий спред"),
    ("risk_rejected:historical_edge_insufficient", "Недостаточное историческое преимущество"),
    ("risk_rejected:critical_news_imminent", "Приближаются важные новости"),
    ("risk_rejected:data_incomplete", "Неполные данные"),
    ("risk_rejected:system_health_degraded", "Проблемы со здоровьем системы"),
    ("risk_rejected:market_closed", "Рынок закрыт"),
    ("confidence_below_threshold", "Уверенность ниже порога"),
    ("reduced_confidence:macro_unavailable", "Нет данных по макроэкономике"),
    ("reduced_confidence:news_unavailable", "Нет данных по новостям"),
    ("reduced_confidence:correlation_unavailable", "Нет данных по корреляции"),
    ("reduced_confidence:order_flow_unavailable", "Нет данных по Order Flow"),
    ("reduced_confidence:ml_unavailable", "Нет данных от ML-модели"),
    ("missing_report:", "Нет отчёта: "),
)


def _translate_no_trade_reason_ru(tag: str) -> str:
    if tag in _KNOWN_NO_TRADE_REASON_TRANSLATIONS:
        return _KNOWN_NO_TRADE_REASON_TRANSLATIONS[tag]
    for prefix, translation_prefix in _NO_TRADE_REASON_PREFIX_TRANSLATIONS:
        if tag.startswith(prefix):
            remainder = tag.removeprefix(prefix)
            return translation_prefix if not remainder else f"{translation_prefix}{remainder}"
    return tag


def build_no_trade_reasons_ru(
    decision: ChiefAIDecision, department_votes: dict[str, dict[str, float | str]]
) -> list[str]:
    """Build the "No Trade" explanation's reason bullets.

    Args:
        decision: The cycle's WAIT decision.
        department_votes: The cycle's department vote snapshot, e.g.
            `{"technical": {"bias": "bearish", "confidence": 0.8}}`.

    Returns:
        Translated `decision.reasons`/`reduced_confidence_factors` codes
        (deduplicated, order preserved), followed by short department
        disagreement tags -- never a reason not backed by `decision`'s
        own recorded fields.
    """
    translated = [_translate_no_trade_reason_ru(tag) for tag in decision.reasons]
    translated.extend(
        _translate_no_trade_reason_ru(tag) for tag in decision.reduced_confidence_factors
    )
    seen: set[str] = set()
    reasons: list[str] = []
    for reason in translated:
        if reason not in seen:
            seen.add(reason)
            reasons.append(reason)
    reasons.extend(build_reason_tags_ru(department_votes))
    return reasons


@dataclass(frozen=True, slots=True)
class NoTradeMessageData:
    """Fields for a Telegram "No Trade" explanation.

    Attributes:
        market: Symbol name, e.g. "XAUUSD".
        quality_score: The Trade Quality Engine's 0-100 score for this
            cycle's (non-)decision.
        confidence_pct: Overall decision confidence, 0-100.
        reasons: Short Russian reasons this cycle did not trade (see
            `_translate_no_trade_reason_ru`), plus any department
            disagreement tags -- never a fabricated reason not backed by
            `ChiefAIDecision`'s own recorded fields.
        next_scan_minutes: Minutes until the next scheduled market scan.
    """

    market: str
    quality_score: float
    confidence_pct: float
    reasons: list[str] = field(default_factory=list)
    next_scan_minutes: float = 0.0


def format_no_trade_message(data: NoTradeMessageData) -> str:
    """Format a Telegram "No Trade" explanation.

    Per the "No Trade Explanation" production requirement: whenever
    Chief AI decides not to trade, show Trade Quality, Confidence, and
    the reasons why -- e.g.:
    "❌ No Trade\\nTrade Quality: 63/100\\nConfidence: 58%\\n..."

    Args:
        data: The cycle's fields.

    Returns:
        Short Russian text with emoji.
    """
    lines = [
        f"❌ Нет сделки — {data.market}",
        f"📊 Качество: {data.quality_score:.0f}/100",
        f"⭐ Уверенность: {data.confidence_pct:.0f}%",
    ]
    if data.reasons:
        lines.append("📌 Причины:")
        lines.extend(f"• {reason}" for reason in data.reasons)
    lines.append(f"🔄 Следующее сканирование: через {data.next_scan_minutes:.0f} мин.")
    return "\n".join(lines)
