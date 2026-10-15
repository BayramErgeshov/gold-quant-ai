"""Integration tests for the local web UI's FastAPI routes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.app import _get_db, app
from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.system_log_repository import SystemLogRepository
from src.repositories.trade_repository import TradeRepository


@pytest.fixture
def client(session: AsyncSession) -> Iterator[TestClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[_get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_dashboard_page_renders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "GOLD QUANT AI" in response.text
    assert "Нет открытых позиций" in response.text


async def test_dashboard_page_renders_no_trade_card_on_a_wait_decision(
    client: TestClient, session: AsyncSession
) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="market_scan_snapshot",
        event="scan_completed",
        context={
            "market": "XAUUSD",
            "state": "WAIT",
            "trade_quality_score": 63.0,
            "confidence_pct": 58.0,
            "no_trade_reasons": ["Уверенность ниже порога"],
            "next_scan_minutes": 2.0,
        },
    )
    await session.commit()

    response = client.get("/")

    assert response.status_code == 200
    assert "Нет сделки" in response.text
    assert "63/100" in response.text
    assert "Уверенность ниже порога" in response.text


async def test_dashboard_page_renders_the_trade_explanation_for_an_open_position(
    client: TestClient, session: AsyncSession
) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await TradeRepository(session).add(
        Trade(
            symbol_id=symbol.id,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=42,
            broker_ticket="9800",
            quality_score=75.0,
            confidence_pct=82.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
            reasons=["bullish_probability_exceeds_bearish"],
            scenario_plan={"primary_scenario": "Price continues higher."},
        )
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "trade-explanation" in response.text
    assert "Price continues higher." in response.text
    assert "✅ Технический анализ" in response.text


def test_dashboard_page_renders_a_card_for_every_strategy(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Скальпинг" in response.text
    assert "Свинг" in response.text
    assert "Intraday" in response.text
    assert "Classic M5 Strategy" in response.text
    assert "Микро-скальп" in response.text
    # Every strategy searches by default until its own snapshot exists.
    assert response.text.count("Поиск...") == 5


async def test_dashboard_page_collapses_a_disabled_strategy_into_the_summary_line(
    client: TestClient, session: AsyncSession
) -> None:
    settings_repository = RuntimeSettingsRepository(session)
    runtime_settings = await settings_repository.get_or_create_default()
    runtime_settings.scalping_enabled = False
    await settings_repository.add(runtime_settings)
    await session.commit()

    response = client.get("/")

    assert response.status_code == 200
    # Per the decluttering request: a disabled strategy no longer gets a
    # full status card -- it collapses into one compact summary line.
    assert "Отключены:" in response.text
    assert "Скальпинг" in response.text
    assert response.text.count("Поиск...") == 4


def test_strategy_builder_page_renders(client: TestClient) -> None:
    response = client.get("/strategy-builder")

    assert response.status_code == 200
    assert "Strategy Builder" in response.text
    assert "Пока нет сохранённых профилей" in response.text


def test_strategy_builder_page_lists_a_saved_profile(client: TestClient) -> None:
    client.post(
        "/api/strategy-profiles",
        json={"name": "Conservative", "modules": [{"module_name": "trend", "weight": 1.5}]},
    )

    response = client.get("/strategy-builder")

    assert response.status_code == 200
    assert "Conservative" in response.text


def test_settings_page_renders(client: TestClient) -> None:
    response = client.get("/settings")

    assert response.status_code == 200
    assert "Risk mode" in response.text.lower() or "risk-mode" in response.text


def test_books_page_renders(client: TestClient) -> None:
    response = client.get("/books")

    assert response.status_code == 200
    assert "Книги" in response.text
    assert "Подтверждённых гипотез пока нет" in response.text


def test_chart_page_renders_without_a_seeded_symbol(client: TestClient) -> None:
    response = client.get("/chart")

    assert response.status_code == 200
    assert "График" in response.text
    assert "Пока нет сохранённых свечей" in response.text


def test_api_chart_returns_empty_json_without_a_seeded_symbol(client: TestClient) -> None:
    response = client.get("/api/chart")

    assert response.status_code == 200
    body = response.json()
    assert body["candles"] == []
    assert body["zones"] == []


def test_api_books_returns_json(client: TestClient) -> None:
    response = client.get("/api/books")

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 0
    assert body["claim_counts"] == {
        "pending": 0,
        "accepted": 0,
        "rejected": 0,
        "unknown": 0,
    }


def test_api_performance_returns_empty_report_without_closed_trades(client: TestClient) -> None:
    response = client.get("/api/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["trade_count"] == 0
    assert body["department_performance"]["technical"]["total_calls"] == 0


def test_api_performance_by_strategy_returns_all_five_strategies_by_default(
    client: TestClient,
) -> None:
    response = client.get("/api/performance/by-strategy")

    assert response.status_code == 200
    body = response.json()
    assert [s["strategy"] for s in body["strategies"]] == [
        "Intraday",
        "Scalping",
        "Swing",
        "Shakky",
        "MicroScalping",
    ]
    assert all(s["report"]["trade_count"] == 0 for s in body["strategies"])
    assert body["ranking"] == []


def test_api_weight_recommendations_returns_empty_lists_by_default(client: TestClient) -> None:
    response = client.get("/api/weight-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["pending"] == []
    assert body["recent"] == []


def test_api_approve_weight_recommendation_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.post(
        "/api/weight-recommendations/00000000-0000-0000-0000-000000000000/approve"
    )

    assert response.status_code == 404


def test_api_reject_weight_recommendation_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.post(
        "/api/weight-recommendations/00000000-0000-0000-0000-000000000000/reject"
    )

    assert response.status_code == 404


def test_api_strategy_profiles_returns_empty_list_by_default(client: TestClient) -> None:
    response = client.get("/api/strategy-profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles"] == []
    assert body["assignments"] == {"intraday": None, "scalping": None, "swing": None}
    assert "trend" in body["module_names"]


def test_api_save_strategy_profile_then_list_round_trips(client: TestClient) -> None:
    response = client.post(
        "/api/strategy-profiles",
        json={
            "name": "Conservative",
            "modules": [
                {"module_name": "trend", "enabled": True, "weight": 1.5},
                {"module_name": "news", "enabled": False, "min_confidence": 0.7},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Conservative"
    modules_by_name = {module["module_name"]: module for module in body["modules"]}
    assert modules_by_name["trend"]["weight"] == 1.5
    assert modules_by_name["news"]["enabled"] is False

    listed = client.get("/api/strategy-profiles").json()
    assert [profile["name"] for profile in listed["profiles"]] == ["Conservative"]


def test_api_save_strategy_profile_rejects_an_unknown_module(client: TestClient) -> None:
    response = client.post(
        "/api/strategy-profiles",
        json={"name": "Broken", "modules": [{"module_name": "not_a_real_module"}]},
    )

    assert response.status_code == 400


def test_api_delete_strategy_profile_returns_404_for_unknown_name(client: TestClient) -> None:
    response = client.delete("/api/strategy-profiles/Nonexistent")

    assert response.status_code == 404


def test_api_delete_strategy_profile_removes_a_saved_profile(client: TestClient) -> None:
    client.post("/api/strategy-profiles", json={"name": "Aggressive", "modules": []})

    response = client.delete("/api/strategy-profiles/Aggressive")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert client.get("/api/strategy-profiles").json()["profiles"] == []


def test_api_assign_strategy_profile_rejects_an_unknown_strategy(client: TestClient) -> None:
    response = client.post("/api/strategy-profiles/assign", json={"strategy": "not_a_strategy"})

    assert response.status_code == 400


def test_api_assign_strategy_profile_returns_404_for_an_unknown_profile(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/strategy-profiles/assign",
        json={"strategy": "scalping", "profile_name": "Nonexistent"},
    )

    assert response.status_code == 404


def test_api_assign_strategy_profile_persists_the_assignment(client: TestClient) -> None:
    client.post("/api/strategy-profiles", json={"name": "Swing Only", "modules": []})

    response = client.post(
        "/api/strategy-profiles/assign",
        json={"strategy": "swing", "profile_name": "Swing Only"},
    )

    assert response.status_code == 200
    assert response.json()["assignments"]["swing"] == "Swing Only"


def test_api_replay_start_returns_400_with_too_little_history(client: TestClient) -> None:
    response = client.post(
        "/api/replay/start",
        json={
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "start": "2020-01-01T00:00:00Z",
            "end": "2020-01-02T00:00:00Z",
            "window_size": 20,
        },
    )

    assert response.status_code == 400


def test_api_replay_get_returns_404_for_unknown_session(client: TestClient) -> None:
    response = client.get("/api/replay/does-not-exist")

    assert response.status_code == 404


def test_api_replay_step_returns_404_for_unknown_session(client: TestClient) -> None:
    response = client.post("/api/replay/does-not-exist/step", json={"direction": "forward"})

    assert response.status_code == 404


def test_api_replay_step_rejects_an_invalid_direction(client: TestClient) -> None:
    response = client.post("/api/replay/does-not-exist/step", json={"direction": "sideways"})

    assert response.status_code == 400


def test_api_replay_candidates_news_returns_empty_list_by_default(client: TestClient) -> None:
    response = client.get("/api/replay/candidates/news")

    assert response.status_code == 200
    assert response.json() == []


def test_api_replay_candidates_regime_returns_empty_list_for_unseeded_symbol(
    client: TestClient,
) -> None:
    response = client.get("/api/replay/candidates/regime", params={"regime_type": "bull_trend"})

    assert response.status_code == 200
    assert response.json() == []


def test_api_status_returns_json(client: TestClient) -> None:
    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["market"] == "XAUUSD"
    assert body["open_positions"] == []


def test_api_get_settings_returns_defaults(client: TestClient) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["auto_trading_enabled"] is True
    assert body["risk_mode"] == "normal"


def test_api_update_settings_persists_changes(client: TestClient) -> None:
    response = client.post(
        "/api/settings",
        json={"auto_trading_enabled": False, "risk_mode": "conservative"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["auto_trading_enabled"] is False
    assert body["risk_mode"] == "conservative"

    reread = client.get("/api/settings")
    assert reread.json()["auto_trading_enabled"] is False


def test_api_update_settings_rejects_invalid_risk_mode(client: TestClient) -> None:
    response = client.post("/api/settings", json={"risk_mode": "extreme"})

    assert response.status_code == 400


def test_api_control_status_reports_not_running_by_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.interfaces.web.app.is_live_loop_running", lambda: False)

    response = client.get("/api/control/status")

    assert response.status_code == 200
    assert response.json() == {"running": False, "paused": False}


def test_api_control_start_delegates_to_process_control(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.interfaces.web.app.start_live_loop", lambda: True)

    response = client.post("/api/control/start")

    assert response.status_code == 200
    assert response.json() == {"started": True}


def test_api_control_stop_delegates_to_process_control(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.interfaces.web.app.stop_live_loop", lambda: True)

    response = client.post("/api/control/stop")

    assert response.status_code == 200
    assert response.json() == {"stopped": True}


def test_api_control_restart_reports_running_after_restart(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.interfaces.web.app.restart_live_loop", lambda: None)
    monkeypatch.setattr("src.interfaces.web.app.is_live_loop_running", lambda: True)

    response = client.post("/api/control/restart")

    assert response.status_code == 200
    assert response.json() == {"running": True}


def test_api_control_pause_toggles_the_paused_flag(client: TestClient) -> None:
    first = client.post("/api/control/pause")
    assert first.status_code == 200
    assert first.json()["paused"] is True

    second = client.post("/api/control/pause")
    assert second.json()["paused"] is False


def test_api_control_emergency_close_returns_the_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.interfaces.web.emergency_close import EmergencyCloseResult

    async def _fake_emergency_close(session: object, mt5: object) -> EmergencyCloseResult:
        return EmergencyCloseResult(mt5_connected=True, closed_tickets=["1"], failed_tickets=[])

    monkeypatch.setattr(
        "src.interfaces.web.app.emergency_close_all_positions", _fake_emergency_close
    )

    response = client.post("/api/control/emergency-close")

    assert response.status_code == 200
    body = response.json()
    assert body["mt5_connected"] is True
    assert body["closed_tickets"] == ["1"]
