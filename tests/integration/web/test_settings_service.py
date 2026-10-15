"""Integration tests for the web UI's settings data assembly."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.settings_service import (
    SettingsUpdate,
    get_current_settings,
    update_settings,
)


async def test_get_current_settings_returns_defaults(session: AsyncSession) -> None:
    view = await get_current_settings(session)

    assert view.fixed_lot_size is None
    assert view.auto_trading_enabled is True
    assert view.confidence_threshold is None
    assert view.intraday_enabled is True
    assert view.scalping_enabled is True
    assert view.swing_enabled is True
    assert view.scalping_confidence_threshold is None
    assert view.swing_confidence_threshold is None
    assert view.risk_mode == "normal"
    assert view.max_positions is None
    assert view.books_folder is None
    assert view.correlated_instruments_enabled == 0


async def test_update_settings_sets_fixed_lot_size(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(fixed_lot_size=0.5))

    assert view.fixed_lot_size == 0.5


async def test_update_settings_clears_fixed_lot_size(session: AsyncSession) -> None:
    await update_settings(session, SettingsUpdate(fixed_lot_size=0.5))

    view = await update_settings(session, SettingsUpdate(clear_fixed_lot_size=True))

    assert view.fixed_lot_size is None


async def test_update_settings_toggles_auto_trading(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(auto_trading_enabled=False))

    assert view.auto_trading_enabled is False


async def test_update_settings_sets_confidence_threshold(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(confidence_threshold=85.0))

    assert view.confidence_threshold == 85.0


async def test_update_settings_clears_confidence_threshold(session: AsyncSession) -> None:
    await update_settings(session, SettingsUpdate(confidence_threshold=85.0))

    view = await update_settings(session, SettingsUpdate(clear_confidence_threshold=True))

    assert view.confidence_threshold is None


async def test_update_settings_toggles_scalping(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(scalping_enabled=False))

    assert view.scalping_enabled is False


async def test_update_settings_toggles_swing(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(swing_enabled=False))

    assert view.swing_enabled is False


async def test_update_settings_toggles_intraday(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(intraday_enabled=False))

    assert view.intraday_enabled is False


async def test_update_settings_sets_scalping_confidence_threshold(
    session: AsyncSession,
) -> None:
    view = await update_settings(session, SettingsUpdate(scalping_confidence_threshold=72.0))

    assert view.scalping_confidence_threshold == 72.0


async def test_update_settings_clears_scalping_confidence_threshold(
    session: AsyncSession,
) -> None:
    await update_settings(session, SettingsUpdate(scalping_confidence_threshold=72.0))

    view = await update_settings(session, SettingsUpdate(clear_scalping_confidence_threshold=True))

    assert view.scalping_confidence_threshold is None


async def test_update_settings_sets_swing_confidence_threshold(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(swing_confidence_threshold=88.0))

    assert view.swing_confidence_threshold == 88.0


async def test_update_settings_clears_swing_confidence_threshold(session: AsyncSession) -> None:
    await update_settings(session, SettingsUpdate(swing_confidence_threshold=88.0))

    view = await update_settings(session, SettingsUpdate(clear_swing_confidence_threshold=True))

    assert view.swing_confidence_threshold is None


async def test_independent_strategy_thresholds_do_not_affect_each_other(
    session: AsyncSession,
) -> None:
    await update_settings(session, SettingsUpdate(confidence_threshold=82.0))
    await update_settings(session, SettingsUpdate(scalping_confidence_threshold=72.0))

    view = await update_settings(session, SettingsUpdate(swing_confidence_threshold=88.0))

    assert view.confidence_threshold == 82.0
    assert view.scalping_confidence_threshold == 72.0
    assert view.swing_confidence_threshold == 88.0


async def test_update_settings_sets_risk_mode(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(risk_mode="aggressive"))

    assert view.risk_mode == "aggressive"


async def test_update_settings_rejects_unknown_risk_mode(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="risk_mode must be one of"):
        await update_settings(session, SettingsUpdate(risk_mode="extreme"))


async def test_partial_update_leaves_other_fields_unchanged(session: AsyncSession) -> None:
    await update_settings(session, SettingsUpdate(fixed_lot_size=0.3, risk_mode="conservative"))

    view = await update_settings(session, SettingsUpdate(auto_trading_enabled=False))

    assert view.fixed_lot_size == 0.3
    assert view.risk_mode == "conservative"
    assert view.auto_trading_enabled is False


async def test_update_settings_sets_max_positions(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(max_positions=3))

    assert view.max_positions == 3


async def test_update_settings_clears_max_positions(session: AsyncSession) -> None:
    await update_settings(session, SettingsUpdate(max_positions=3))

    view = await update_settings(session, SettingsUpdate(clear_max_positions=True))

    assert view.max_positions is None


async def test_update_settings_rejects_max_positions_below_one(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="max_positions must be at least 1"):
        await update_settings(session, SettingsUpdate(max_positions=0))


async def test_update_settings_rejects_an_unreachable_confidence_threshold(
    session: AsyncSession,
) -> None:
    # Regression test: `scalping_confidence_threshold` was once found set
    # to 100.0 in production, silently making Scalping reject every
    # signal for weeks -- this must be rejected outright now.
    with pytest.raises(ValueError, match="scalping_confidence_threshold must be in"):
        await update_settings(session, SettingsUpdate(scalping_confidence_threshold=100.0))


async def test_update_settings_rejects_unreachable_thresholds_for_every_engine(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="confidence_threshold must be in"):
        await update_settings(session, SettingsUpdate(confidence_threshold=96.0))
    with pytest.raises(ValueError, match="swing_confidence_threshold must be in"):
        await update_settings(session, SettingsUpdate(swing_confidence_threshold=99.0))


async def test_update_settings_accepts_a_confidence_threshold_at_the_sane_boundary(
    session: AsyncSession,
) -> None:
    view = await update_settings(session, SettingsUpdate(scalping_confidence_threshold=95.0))

    assert view.scalping_confidence_threshold == 95.0


async def test_update_settings_sets_books_folder(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(books_folder="/custom/books"))

    assert view.books_folder == "/custom/books"


async def test_update_settings_clears_books_folder(session: AsyncSession) -> None:
    await update_settings(session, SettingsUpdate(books_folder="/custom/books"))

    view = await update_settings(session, SettingsUpdate(clear_books_folder=True))

    assert view.books_folder is None


async def test_get_current_settings_defaults_to_not_paused(session: AsyncSession) -> None:
    view = await get_current_settings(session)

    assert view.paused is False


async def test_update_settings_toggles_paused(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(paused=True))

    assert view.paused is True

    view = await update_settings(session, SettingsUpdate(paused=False))

    assert view.paused is False


async def test_get_current_settings_defaults_micro_scalping(session: AsyncSession) -> None:
    view = await get_current_settings(session)

    assert view.micro_scalping_enabled is True
    assert view.micro_scalping_min_confidence is None
    assert view.micro_scalping_max_holding_minutes is None
    assert view.micro_scalping_dynamic_profit_target_enabled is True
    assert view.micro_scalping_trailing_stop_enabled is True
    assert view.micro_scalping_lot_mode == "manual"
    assert view.micro_scalping_fixed_lot_size is None


async def test_update_settings_toggles_micro_scalping(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(micro_scalping_enabled=False))

    assert view.micro_scalping_enabled is False


async def test_update_settings_sets_and_clears_micro_scalping_min_confidence(
    session: AsyncSession,
) -> None:
    view = await update_settings(session, SettingsUpdate(micro_scalping_min_confidence=70.0))

    assert view.micro_scalping_min_confidence == 70.0

    view = await update_settings(session, SettingsUpdate(clear_micro_scalping_min_confidence=True))

    assert view.micro_scalping_min_confidence is None


async def test_update_settings_rejects_an_unreachable_micro_scalping_min_confidence(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="micro_scalping_min_confidence must be in"):
        await update_settings(session, SettingsUpdate(micro_scalping_min_confidence=100.0))


async def test_update_settings_sets_and_clears_micro_scalping_max_holding_minutes(
    session: AsyncSession,
) -> None:
    view = await update_settings(session, SettingsUpdate(micro_scalping_max_holding_minutes=15.0))

    assert view.micro_scalping_max_holding_minutes == 15.0

    view = await update_settings(
        session, SettingsUpdate(clear_micro_scalping_max_holding_minutes=True)
    )

    assert view.micro_scalping_max_holding_minutes is None


async def test_update_settings_rejects_a_non_positive_max_holding_minutes(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="micro_scalping_max_holding_minutes must be positive"):
        await update_settings(session, SettingsUpdate(micro_scalping_max_holding_minutes=0.0))


async def test_update_settings_toggles_micro_scalping_dynamic_profit_target_and_trailing(
    session: AsyncSession,
) -> None:
    view = await update_settings(
        session,
        SettingsUpdate(
            micro_scalping_dynamic_profit_target_enabled=False,
            micro_scalping_trailing_stop_enabled=False,
        ),
    )

    assert view.micro_scalping_dynamic_profit_target_enabled is False
    assert view.micro_scalping_trailing_stop_enabled is False


async def test_update_settings_sets_micro_scalping_lot_mode(session: AsyncSession) -> None:
    view = await update_settings(session, SettingsUpdate(micro_scalping_lot_mode="auto"))

    assert view.micro_scalping_lot_mode == "auto"


async def test_update_settings_rejects_an_invalid_micro_scalping_lot_mode(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="micro_scalping_lot_mode must be"):
        await update_settings(session, SettingsUpdate(micro_scalping_lot_mode="bogus"))


async def test_update_settings_sets_and_clears_micro_scalping_fixed_lot_size(
    session: AsyncSession,
) -> None:
    view = await update_settings(session, SettingsUpdate(micro_scalping_fixed_lot_size=0.1))

    assert view.micro_scalping_fixed_lot_size == 0.1

    view = await update_settings(session, SettingsUpdate(clear_micro_scalping_fixed_lot_size=True))

    assert view.micro_scalping_fixed_lot_size is None


async def test_update_settings_rejects_a_non_positive_fixed_lot_size(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="micro_scalping_fixed_lot_size must be positive"):
        await update_settings(session, SettingsUpdate(micro_scalping_fixed_lot_size=0.0))


async def test_get_current_settings_defaults_micro_scalping_max_spread_points(
    session: AsyncSession,
) -> None:
    view = await get_current_settings(session)

    assert view.micro_scalping_max_spread_points is None


async def test_update_settings_sets_and_clears_micro_scalping_max_spread_points(
    session: AsyncSession,
) -> None:
    view = await update_settings(session, SettingsUpdate(micro_scalping_max_spread_points=80.0))

    assert view.micro_scalping_max_spread_points == 80.0

    view = await update_settings(
        session, SettingsUpdate(clear_micro_scalping_max_spread_points=True)
    )

    assert view.micro_scalping_max_spread_points is None


async def test_update_settings_rejects_a_non_positive_max_spread_points(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="micro_scalping_max_spread_points must be positive"):
        await update_settings(session, SettingsUpdate(micro_scalping_max_spread_points=0.0))
