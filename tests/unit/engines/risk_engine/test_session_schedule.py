"""Unit tests for trading-session close scheduling."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.engines.risk_engine.session_schedule import (
    SessionSchedule,
    has_pre_close_report_already_run_today,
    is_weekend_approaching,
    is_within_pre_close_window,
    parse_session_schedule,
)

pytestmark = pytest.mark.unit


def _schedule(**overrides: object) -> SessionSchedule:
    defaults: dict[str, object] = {
        "daily_close_utc": "21:00",
        "weekly_close_weekday": "friday",
        "pre_close_warning_minutes": 30,
    }
    defaults.update(overrides)
    return parse_session_schedule(**defaults)  # type: ignore[arg-type]


def test_parse_session_schedule_resolves_fields() -> None:
    schedule = _schedule()

    assert schedule.daily_close.hour == 21
    assert schedule.daily_close.minute == 0
    assert schedule.weekly_close_weekday == 4  # Friday
    assert schedule.pre_close_warning_minutes == 30


def test_parse_session_schedule_rejects_unknown_weekday() -> None:
    with pytest.raises(ValueError, match="not in tuple"):
        _schedule(weekly_close_weekday="funday")


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (20, 29, False),  # just before the window opens
        (20, 30, True),  # window opens
        (20, 59, True),  # inside the window
        (21, 0, False),  # close instant itself, no longer "before"
        (21, 1, False),  # after close
    ],
)
def test_is_within_pre_close_window(hour: int, minute: int, expected: bool) -> None:
    schedule = _schedule()
    now = datetime(2026, 7, 10, hour, minute, tzinfo=UTC)  # a Friday

    assert is_within_pre_close_window(now, schedule) is expected


def test_is_weekend_approaching_true_on_configured_weekday() -> None:
    schedule = _schedule()
    friday = datetime(2026, 7, 10, 20, 45, tzinfo=UTC)

    assert is_weekend_approaching(friday, schedule) is True


def test_is_weekend_approaching_false_on_other_weekdays() -> None:
    schedule = _schedule()
    monday = datetime(2026, 7, 6, 20, 45, tzinfo=UTC)

    assert is_weekend_approaching(monday, schedule) is False


def test_has_pre_close_report_already_run_today_true_when_dates_match() -> None:
    now = datetime(2026, 7, 10, 20, 45, tzinfo=UTC)

    assert has_pre_close_report_already_run_today(now.date(), now) is True


def test_has_pre_close_report_already_run_today_false_when_never_run() -> None:
    now = datetime(2026, 7, 10, 20, 45, tzinfo=UTC)

    assert has_pre_close_report_already_run_today(None, now) is False


def test_has_pre_close_report_already_run_today_false_on_a_new_day() -> None:
    now = datetime(2026, 7, 10, 20, 45, tzinfo=UTC)

    assert has_pre_close_report_already_run_today(datetime(2026, 7, 9).date(), now) is False
