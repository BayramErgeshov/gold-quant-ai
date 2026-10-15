"""Trading-session close scheduling for the "Before Market Close" report.

Per the production requirement: "30 minutes before market close, analyze
every open position... Before weekends, add weekend gap analysis." Session
times are broker-dependent and configured explicitly
(`src.core.config.platform_config.SessionScheduleConfig`) rather than
guessed from a fixed trading-hours assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

_WEEKDAY_NAMES: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@dataclass(frozen=True, slots=True)
class SessionSchedule:
    """Resolved, ready-to-evaluate session close schedule.

    Attributes:
        daily_close: The connected broker's daily session close time (UTC).
        weekly_close_weekday: `datetime.weekday()` index (Monday=0) whose
            daily close is also the weekly close.
        pre_close_warning_minutes: How long before `daily_close` the
            report window opens.
    """

    daily_close: time
    weekly_close_weekday: int
    pre_close_warning_minutes: int


def parse_session_schedule(
    *, daily_close_utc: str, weekly_close_weekday: str, pre_close_warning_minutes: int
) -> SessionSchedule:
    """Build a `SessionSchedule` from the raw YAML-sourced config values.

    Args:
        daily_close_utc: "HH:MM" in UTC.
        weekly_close_weekday: A lowercase weekday name, e.g. "friday".
        pre_close_warning_minutes: Minutes before close the report window opens.

    Returns:
        The resolved `SessionSchedule`.

    Raises:
        ValueError: If `daily_close_utc` is not "HH:MM", or
            `weekly_close_weekday` is not a recognized weekday name.
    """
    hour_str, _, minute_str = daily_close_utc.partition(":")
    daily_close = time(hour=int(hour_str), minute=int(minute_str))
    return SessionSchedule(
        daily_close=daily_close,
        weekly_close_weekday=_WEEKDAY_NAMES.index(weekly_close_weekday.lower()),
        pre_close_warning_minutes=pre_close_warning_minutes,
    )


def is_within_pre_close_window(now: datetime, schedule: SessionSchedule) -> bool:
    """Check whether `now` falls in the pre-close reporting window for today.

    Args:
        now: Current time (UTC).
        schedule: The resolved session schedule.

    Returns:
        True if `now` is within `pre_close_warning_minutes` before today's
        `daily_close`, exclusive of the close instant itself.
    """
    close_today = datetime.combine(now.date(), schedule.daily_close, tzinfo=now.tzinfo)
    window_start = close_today - timedelta(minutes=schedule.pre_close_warning_minutes)
    return window_start <= now < close_today


def is_weekend_approaching(now: datetime, schedule: SessionSchedule) -> bool:
    """Check whether today's close is also the weekly (pre-weekend) close.

    Args:
        now: Current time (UTC).
        schedule: The resolved session schedule.

    Returns:
        True if `now`'s weekday matches `schedule.weekly_close_weekday`.
    """
    return now.weekday() == schedule.weekly_close_weekday


def has_pre_close_report_already_run_today(last_run_date: date | None, now: datetime) -> bool:
    """Check whether today's pre-close report has already been sent.

    Args:
        last_run_date: The date the report last ran, if ever.
        now: Current time (UTC).

    Returns:
        True if `last_run_date` is today's date.
    """
    return last_run_date == now.date()
