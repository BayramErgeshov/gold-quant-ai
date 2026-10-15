"""Trade outcome factor analysis for the Self Learning Engine.

Per SELF_LEARNING_ENGINE.md "Error Analysis" / "Win Analysis": for every
closed trade, determine which measurable factors contributed to its
outcome. Each check is a concrete, reproducible comparison against the
trade's own recorded decision context — never a fabricated narrative
explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.trade import Trade

_STOP_TO_VOLATILITY_RATIO_THRESHOLD = 0.5

# Every independent opinion department this platform can record a vote
# for on `Trade.department_votes` (excludes pipeline stages like
# "statistics"/"risk"/"execution", which never carry a bias). Kept
# separate from `src.engines.chief_ai.decision.REQUIRED_REPORTS` since
# that tuple also includes those non-opinion stages.
OPINION_DEPARTMENTS: tuple[str, ...] = (
    "technical",
    "historical",
    "ml",
    "macro",
    "news",
    "correlation",
    "order_flow",
    "scalping_engine",
    "swing_engine",
    "shakky_engine",
)


@dataclass(frozen=True, slots=True)
class TradeContext:
    """Recorded decision context for a closed trade, beyond the `Trade` row itself.

    Attributes:
        confidence_pct: The Chief AI decision confidence at entry.
        confidence_threshold: The threshold that was required to execute.
        historical_edge_pct: The historical edge measured for the setup.
        min_historical_edge_pct: The minimum edge that was required.
        market_regime: Classified regime at entry, if known.
        news_imminent_at_entry: Whether high-impact news was imminent at entry.
        expected_volatility_pct: Expected volatility (e.g. ATR-based), if known.
    """

    confidence_pct: float
    confidence_threshold: float
    historical_edge_pct: float
    min_historical_edge_pct: float
    market_regime: str | None
    news_imminent_at_entry: bool
    expected_volatility_pct: float | None


@dataclass(frozen=True, slots=True)
class TradeFactor:
    """One measurable factor identified for a closed trade's outcome."""

    name: str
    detail: str


def _stop_was_too_close(trade: Trade, context: TradeContext) -> bool:
    if (
        context.expected_volatility_pct is None
        or trade.entry_price is None
        or trade.entry_price == 0
    ):
        return False
    stop_distance_pct = abs(trade.entry_price - trade.stop_loss) / trade.entry_price * 100
    return stop_distance_pct < context.expected_volatility_pct * _STOP_TO_VOLATILITY_RATIO_THRESHOLD


def analyze_losing_trade(trade: Trade, context: TradeContext) -> list[TradeFactor]:
    """Apply SELF_LEARNING_ENGINE.md "Error Analysis" checks to a losing trade.

    Args:
        trade: The closed, losing `Trade`.
        context: Recorded decision context at entry.

    Returns:
        Every measurable mistake factor identified. Empty if none of the
        checkable conditions applied — never a fabricated cause.
    """
    factors: list[TradeFactor] = []

    if context.confidence_pct < context.confidence_threshold:
        factors.append(
            TradeFactor(
                name="confidence_below_threshold",
                detail=(
                    f"Entry confidence {context.confidence_pct:.1f}% was below the "
                    f"required threshold {context.confidence_threshold:.1f}%."
                ),
            )
        )
    if context.historical_edge_pct < context.min_historical_edge_pct:
        factors.append(
            TradeFactor(
                name="weak_historical_edge",
                detail=(
                    f"Historical edge {context.historical_edge_pct:.2f}% was below the "
                    f"required minimum {context.min_historical_edge_pct:.2f}%."
                ),
            )
        )
    if context.market_regime is None:
        factors.append(
            TradeFactor(
                name="unknown_market_regime", detail="Market regime was unclassified at entry."
            )
        )
    if context.news_imminent_at_entry:
        factors.append(
            TradeFactor(name="news_ignored", detail="High-impact news was imminent at entry.")
        )
    if _stop_was_too_close(trade, context):
        factors.append(
            TradeFactor(
                name="stop_too_close",
                detail=(
                    f"Stop distance was small relative to expected volatility "
                    f"({context.expected_volatility_pct:.2f}%)."
                ),
            )
        )
    return factors


def analyze_winning_trade(trade: Trade, context: TradeContext) -> list[TradeFactor]:
    """Apply SELF_LEARNING_ENGINE.md "Win Analysis" checks to a winning trade.

    Args:
        trade: The closed, winning `Trade`. Unused directly today (kept for
            symmetry with `analyze_losing_trade` and future MFE/MAE-based checks).
        context: Recorded decision context at entry.

    Returns:
        Every measurable success factor identified. Empty if none of the
        checkable conditions applied.
    """
    factors: list[TradeFactor] = []

    if context.confidence_pct >= context.confidence_threshold:
        factors.append(
            TradeFactor(
                name="confidence_above_threshold",
                detail=(
                    f"Entry confidence {context.confidence_pct:.1f}% met the required "
                    f"threshold {context.confidence_threshold:.1f}%."
                ),
            )
        )
    if context.historical_edge_pct >= context.min_historical_edge_pct:
        factors.append(
            TradeFactor(
                name="strong_historical_edge",
                detail=(
                    f"Historical edge {context.historical_edge_pct:.2f}% met the required "
                    f"minimum {context.min_historical_edge_pct:.2f}%."
                ),
            )
        )
    if context.market_regime is not None:
        factors.append(
            TradeFactor(
                name="known_market_regime",
                detail=f"Market regime was classified as {context.market_regime!r} at entry.",
            )
        )
    return factors


def disagreeing_departments(trade: Trade) -> list[str]:
    """Identify which departments' recorded vote opposed this trade's own direction.

    Uses `Trade.department_votes` — a snapshot taken at signal time
    (`src.workflows.trade.pipeline.SignalWorkflow`), the only decision-time
    evidence actually persisted per trade. Per the "Post Trade Learning"
    production requirement: "which AI agents disagreed."

    Args:
        trade: The closed trade to review.

    Returns:
        Department names whose recorded `bias` opposed `trade.direction`.
        Empty if no department votes were recorded, or none disagreed.
    """
    if not trade.department_votes:
        return []
    opposing_bias = "bearish" if trade.direction == "buy" else "bullish"
    return [
        name for name, vote in trade.department_votes.items() if vote.get("bias") == opposing_bias
    ]


def missing_departments(trade: Trade) -> list[str]:
    """Identify which known opinion departments had no recorded vote for this trade.

    Per the "Post Trade Learning" production requirement: "what external
    information was missing." A missing department here most often means
    an unconfigured data source at signal time (e.g. Macro/News before
    FRED/NewsAPI keys were set) rather than a bug — this only reports the
    fact, never why.

    Args:
        trade: The closed trade to review.

    Returns:
        Names from `OPINION_DEPARTMENTS` absent from
        `trade.department_votes`. Empty if every known department voted,
        or `department_votes` predates this platform's snapshotting
        (in which case every name is reported, honestly, as missing).
    """
    present = set(trade.department_votes) if trade.department_votes else set()
    return [name for name in OPINION_DEPARTMENTS if name not in present]


def outcome_direction(trade: Trade) -> int | None:
    """The direction price actually moved: +1 up, -1 down, None if unknown.

    Shared by `department_performance.compute_department_reliability`
    (aggregate, across many trades) and `department_correctness` below
    (a single trade) — the same definition of "which way did it actually
    go," never computed two different ways.
    """
    if trade.realized_pnl is None:
        return None
    trade_direction = 1 if trade.direction == "buy" else -1
    won = trade.realized_pnl > 0
    return trade_direction if won else -trade_direction


def department_direction(bias: object) -> int | None:
    """A recorded `bias` string as a direction: +1 bullish, -1 bearish, None otherwise."""
    if bias == "bullish":
        return 1
    if bias == "bearish":
        return -1
    return None  # neutral or unrecognized: not a directional call


def department_correctness(trade: Trade) -> dict[str, bool]:
    """Identify which departments' recorded vote matched what actually happened.

    Distinct from `disagreeing_departments` (which compares each
    department's vote against the trade's own ENTRY direction, known at
    signal time): this compares against the REALIZED outcome, known only
    in hindsight — "which AI agents were actually right or wrong," per
    the "Post Trade Learning" production requirement.

    Args:
        trade: The closed trade to review.

    Returns:
        `{department_name: was_correct}` for every department that both
        cast a directional (non-neutral) vote and has a known outcome.
        Empty if the outcome is unknown (`realized_pnl` unset) or no
        department cast a directional vote.
    """
    outcome = outcome_direction(trade)
    if outcome is None or not trade.department_votes:
        return {}
    correctness: dict[str, bool] = {}
    for name, vote in trade.department_votes.items():
        direction = department_direction(vote.get("bias"))
        if direction is None:
            continue
        correctness[name] = direction == outcome
    return correctness


def analyze_department_disagreement(trade: Trade) -> list[TradeFactor]:
    """Build one `TradeFactor` per department that disagreed with this trade's direction.

    Each factor's `name` embeds the specific department (e.g.
    `"department_disagreed:macro"`) rather than a single shared name —
    otherwise multiple departments disagreeing within *one* trade would
    look like a recurring pattern to `generate_hypotheses_from_factors`
    after just one post-mortem, instead of the same department disagreeing
    across *multiple* trades.
    """
    votes = trade.department_votes or {}
    return [
        TradeFactor(
            name=f"department_disagreed:{name}",
            detail=(
                f"{name!r} voted against the {trade.direction} entry "
                f"(confidence {float(votes[name].get('confidence', 0.0)):.0%})."
            ),
        )
        for name in disagreeing_departments(trade)
    ]
