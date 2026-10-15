"""Synthetic order flow analysis, for symbols/brokers without real DOM.

Per this platform's operating instructions: "If real DOM is unavailable:
Automatically switch to synthetic order flow analysis using: Tick Volume,
Volume Profile, Market Profile, VWAP, Delta approximations, Footprint
approximations, High Volume Nodes, Low Volume Nodes, Fair Value Gaps,
Liquidity Pools... Never assume certainty." Every measurement here is an
*approximation* derived from OHLCV bars — there is no real bid/ask
transaction tape to work from — and confidence is capped well below what
`real_order_flow` can claim from an actual book, precisely because of that.

Reuses `src.agents.technical.smart_money.find_fair_value_gaps` and
`src.agents.technical.liquidity.find_liquidity_pools` rather than
duplicating that detection logic (CODING_STANDARDS.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agents.technical.liquidity import LiquidityPool, find_liquidity_pools
from src.agents.technical.smart_money import FairValueGap, find_fair_value_gaps
from src.core.technical_analysis.swings import find_swing_points
from src.models.candle import Candle

_MIN_CANDLES = 10
_DEFAULT_VOLUME_PROFILE_BINS = 20
_VALUE_AREA_PCT = 0.70
_HVN_PERCENTILE = 0.80
_LVN_PERCENTILE = 0.20
_DEFAULT_SWING_LOOKAROUND = 2
_DEFAULT_POOL_TOLERANCE_PCT = 0.15
# Synthetic signals are inherently approximate (no real trade tape), so
# their ceiling confidence is deliberately below what a genuine DOM read
# could support — never presented as equivalent certainty.
_MAX_SYNTHETIC_CONFIDENCE = 0.6


@dataclass(frozen=True, slots=True)
class VolumeProfileBin:
    """One price bin of an approximated Volume Profile.

    Attributes:
        price_low: Bin's lower price bound.
        price_high: Bin's upper price bound.
        volume: Total tick volume attributed to this bin.
    """

    price_low: float
    price_high: float
    volume: float

    @property
    def midpoint(self) -> float:
        return (self.price_low + self.price_high) / 2


@dataclass(frozen=True, slots=True)
class VolumeProfile:
    """An approximated Volume Profile over a window of candles.

    Attributes:
        bins: Every price bin, ordered by price ascending.
        point_of_control: The bin with the most volume (the approximated POC).
        value_area: Bins comprising ~70% of total volume around the POC.
        high_volume_nodes: Bins at or above the 80th volume percentile.
        low_volume_nodes: Bins at or below the 20th volume percentile
            (excluding empty bins, which carry no information).
    """

    bins: list[VolumeProfileBin]
    point_of_control: VolumeProfileBin | None
    value_area: list[VolumeProfileBin]
    high_volume_nodes: list[VolumeProfileBin]
    low_volume_nodes: list[VolumeProfileBin]


def compute_volume_profile(
    candles: list[Candle], *, bin_count: int = _DEFAULT_VOLUME_PROFILE_BINS
) -> VolumeProfile:
    """Approximate a Volume Profile / Market Profile from OHLCV bars.

    Each candle's volume is attributed to the bin containing its typical
    price `(high + low + close) / 3` — a standard approximation when only
    bar-level (not trade-level) data is available.

    Args:
        candles: Candles ordered by timestamp ascending.
        bin_count: Number of equal-width price bins to split the window's
            range into.

    Returns:
        A `VolumeProfile`. Empty (no POC, no bins) if `candles` is empty
        or every candle has the same price (zero range) — never a
        fabricated profile.
    """
    if not candles:
        return VolumeProfile(
            bins=[], point_of_control=None, value_area=[], high_volume_nodes=[], low_volume_nodes=[]
        )

    price_low = min(candle.low for candle in candles)
    price_high = max(candle.high for candle in candles)
    if price_high <= price_low:
        return VolumeProfile(
            bins=[], point_of_control=None, value_area=[], high_volume_nodes=[], low_volume_nodes=[]
        )

    bin_width = (price_high - price_low) / bin_count
    volumes = [0.0] * bin_count
    for candle in candles:
        typical_price = (candle.high + candle.low + candle.close) / 3
        bin_index = min(int((typical_price - price_low) / bin_width), bin_count - 1)
        volumes[bin_index] += candle.volume or 0.0

    bins = [
        VolumeProfileBin(
            price_low=price_low + index * bin_width,
            price_high=price_low + (index + 1) * bin_width,
            volume=volumes[index],
        )
        for index in range(bin_count)
    ]

    total_volume = sum(bin_.volume for bin_ in bins)
    if total_volume <= 0:
        return VolumeProfile(
            bins=bins,
            point_of_control=None,
            value_area=[],
            high_volume_nodes=[],
            low_volume_nodes=[],
        )

    poc = max(bins, key=lambda bin_: bin_.volume)
    value_area = _compute_value_area(bins, poc, total_volume)

    sorted_volumes = sorted(bin_.volume for bin_ in bins if bin_.volume > 0)
    hvn_threshold = _percentile(sorted_volumes, _HVN_PERCENTILE)
    lvn_threshold = _percentile(sorted_volumes, _LVN_PERCENTILE)
    high_volume_nodes = [bin_ for bin_ in bins if bin_.volume >= hvn_threshold and bin_.volume > 0]
    low_volume_nodes = [bin_ for bin_ in bins if 0 < bin_.volume <= lvn_threshold]

    return VolumeProfile(
        bins=bins,
        point_of_control=poc,
        value_area=value_area,
        high_volume_nodes=high_volume_nodes,
        low_volume_nodes=low_volume_nodes,
    )


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:  # pragma: no cover - defensive: callers only
        # pass bins already filtered to `volume > 0`, and `compute_volume_profile`
        # only reaches this call after confirming `total_volume > 0`.
        return 0.0
    index = min(len(sorted_values) - 1, int(len(sorted_values) * fraction))
    return sorted_values[index]


def _compute_value_area(
    bins: list[VolumeProfileBin], poc: VolumeProfileBin, total_volume: float
) -> list[VolumeProfileBin]:
    """Expand outward from the POC until ~70% of volume is included."""
    poc_index = bins.index(poc)
    included = {poc_index}
    accumulated = poc.volume
    low, high = poc_index - 1, poc_index + 1

    while accumulated < total_volume * _VALUE_AREA_PCT and (low >= 0 or high < len(bins)):
        low_volume = bins[low].volume if low >= 0 else -1.0
        high_volume = bins[high].volume if high < len(bins) else -1.0
        if high_volume >= low_volume and high < len(bins):
            included.add(high)
            accumulated += high_volume
            high += 1
        elif low >= 0:
            included.add(low)
            accumulated += low_volume
            low -= 1
        else:  # pragma: no cover - unreachable: the while condition above
            # already guarantees `low >= 0 or high < len(bins)`, so one of
            # the two branches above always fires first.
            break

    return [bins[index] for index in sorted(included)]


def compute_vwap(candles: list[Candle]) -> float | None:
    """Compute the Volume-Weighted Average Price over a window of candles.

    Args:
        candles: Candles ordered by timestamp ascending.

    Returns:
        The VWAP, or None if there is no volume data to weight by.
    """
    total_volume = sum(candle.volume or 0.0 for candle in candles)
    if total_volume <= 0:
        return None
    weighted_sum = sum(
        ((candle.high + candle.low + candle.close) / 3) * (candle.volume or 0.0)
        for candle in candles
    )
    return weighted_sum / total_volume


@dataclass(frozen=True, slots=True)
class DeltaApproximation:
    """Approximated buy/sell volume split per candle.

    Per-candle direction (close vs open) stands in for the real trade-by-
    trade buy/sell tape this platform does not have access to — a
    documented approximation, not a claim of measuring actual executed
    aggressor side.

    Attributes:
        per_candle_delta: One signed value per candle: `+volume` if it
            closed up, `-volume` if it closed down, `0` if flat or no
            volume — the "footprint approximation".
        net_delta: Sum of `per_candle_delta` across the whole window.
    """

    per_candle_delta: list[float]
    net_delta: float


def compute_delta_approximation(candles: list[Candle]) -> DeltaApproximation:
    """Approximate buy/sell volume delta from candle direction.

    Args:
        candles: Candles ordered by timestamp ascending.

    Returns:
        A `DeltaApproximation`.
    """
    per_candle: list[float] = []
    for candle in candles:
        volume = candle.volume or 0.0
        if candle.close > candle.open:
            per_candle.append(volume)
        elif candle.close < candle.open:
            per_candle.append(-volume)
        else:
            per_candle.append(0.0)
    return DeltaApproximation(per_candle_delta=per_candle, net_delta=sum(per_candle))


@dataclass(frozen=True, slots=True)
class SyntheticOrderFlowReport:
    """Every synthetic order-flow measurement for one analysis window.

    Attributes:
        volume_profile: Approximated Volume Profile.
        vwap: Volume-weighted average price, if computable.
        delta: Approximated buy/sell delta.
        fair_value_gaps: Unfilled three-candle imbalances.
        liquidity_pools: Estimated resting liquidity (equal highs/lows).
        bullish_probability: Confidence-weighted lean toward higher prices.
        bearish_probability: Confidence-weighted lean toward lower prices.
        confidence: Overall confidence in [0.0, `_MAX_SYNTHETIC_CONFIDENCE`].
        supporting_evidence: Facts supporting the directional lean.
        opposing_evidence: Facts against it.
    """

    volume_profile: VolumeProfile
    vwap: float | None
    delta: DeltaApproximation
    fair_value_gaps: list[FairValueGap]
    liquidity_pools: list[LiquidityPool]
    bullish_probability: float
    bearish_probability: float
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)


def analyze_synthetic_order_flow(candles: list[Candle]) -> SyntheticOrderFlowReport:
    """Run every synthetic order-flow measurement over a window of candles.

    Args:
        candles: Candles ordered by timestamp ascending.

    Returns:
        A `SyntheticOrderFlowReport`. Confidence is `0.0` (fully neutral)
        if there are too few candles to measure anything meaningfully.
    """
    if len(candles) < _MIN_CANDLES:
        return SyntheticOrderFlowReport(
            volume_profile=compute_volume_profile([]),
            vwap=None,
            delta=DeltaApproximation(per_candle_delta=[], net_delta=0.0),
            fair_value_gaps=[],
            liquidity_pools=[],
            bullish_probability=0.0,
            bearish_probability=0.0,
            confidence=0.0,
            opposing_evidence=["Not enough candles for synthetic order flow analysis."],
        )

    volume_profile = compute_volume_profile(candles)
    vwap = compute_vwap(candles)
    delta = compute_delta_approximation(candles)
    fvgs = find_fair_value_gaps(candles)

    swings = find_swing_points(candles, lookaround=_DEFAULT_SWING_LOOKAROUND)
    highs = [swing.candle.high for swing in swings if swing.kind == "high"]
    lows = [swing.candle.low for swing in swings if swing.kind == "low"]
    liquidity_pools = find_liquidity_pools(
        highs, tolerance_pct=_DEFAULT_POOL_TOLERANCE_PCT, kind="buy_side"
    ) + find_liquidity_pools(lows, tolerance_pct=_DEFAULT_POOL_TOLERANCE_PCT, kind="sell_side")

    supporting: list[str] = []
    opposing: list[str] = []
    signals: list[float] = []  # each in [-1, 1]; averaged into a directional score

    last_close = candles[-1].close
    if vwap is not None and vwap > 0:
        vwap_signal = 1.0 if last_close > vwap else -1.0
        signals.append(vwap_signal)
        (supporting if vwap_signal > 0 else opposing).append(
            f"Price is {'above' if vwap_signal > 0 else 'below'} VWAP ({vwap:.2f})"
        )

    total_volume = sum(abs(value) for value in delta.per_candle_delta)
    if total_volume > 0:
        delta_signal = delta.net_delta / total_volume
        signals.append(delta_signal)
        (supporting if delta_signal > 0 else opposing).append(
            f"Net delta approximation is {'positive' if delta_signal > 0 else 'negative'} "
            f"({delta.net_delta:+.1f})"
        )

    if fvgs:
        last_gap = fvgs[-1]
        gap_signal = 1.0 if last_gap.direction == "bullish" else -1.0
        signals.append(gap_signal * 0.5)  # half-weight: a single FVG is weaker evidence
        supporting.append(f"Most recent fair value gap is {last_gap.direction}")

    directional_score = sum(signals) / len(signals) if signals else 0.0
    confidence = min(_MAX_SYNTHETIC_CONFIDENCE, abs(directional_score) * len(signals) / 3)
    bullish_probability = max(0.0, directional_score)
    bearish_probability = max(0.0, -directional_score)

    return SyntheticOrderFlowReport(
        volume_profile=volume_profile,
        vwap=vwap,
        delta=delta,
        fair_value_gaps=fvgs,
        liquidity_pools=liquidity_pools,
        bullish_probability=bullish_probability,
        bearish_probability=bearish_probability,
        confidence=confidence,
        supporting_evidence=supporting,
        opposing_evidence=opposing,
    )
