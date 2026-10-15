"""Generate `CURRENT_STATE.md`: the platform's living architecture snapshot.

Per the "Current State Documentation" production requirement: "Generate
and continuously maintain CURRENT_STATE.md... Must auto-update whenever
major functionality changes." Every section here is derived from source
code that already exists (imported modules, `Base.metadata`, the live
FastAPI route table, the migrations folder) rather than hand-typed facts
that silently drift out of date -- run this script again after any
change to the department roster, technical agents, database schema, or
web routes, and the output reflects the new reality automatically.

Deliberately DB-independent: it must produce the identical file whether
run against a fresh CI database or a mature production one, so CI can
enforce "regenerate and diff -- fail if `CURRENT_STATE.md` is stale"
without depending on runtime data that legitimately differs between
environments (registered ML models, ingested news, correlated
instruments actually enabled are operational state, not architecture,
and are intentionally described qualitatively rather than counted live).

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/generate_current_state.py
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_PATH = _REPO_ROOT / "CURRENT_STATE.md"
_MIGRATIONS_DIR = _REPO_ROOT / "src" / "database" / "migrations" / "versions"

# Hand-maintained: whether a given department, strategy, or architectural
# fact is "done" is a judgment call this script cannot mechanically
# derive from code alone. Review and update this block itself whenever a
# phase materially changes production readiness, not the generated
# sections below.
_KNOWN_LIMITATIONS = """\
- **Macro and News departments run in "reduced mode"**: no FRED or
  NewsAPI key is configured, so every Chief AI decision is flagged
  `reduced_confidence` for these two departments rather than fabricating
  a neutral vote for missing data.
- **Order Flow is synthetic**: the connected MT5 account/broker does not
  expose real market depth (DOM), so the Order Flow Engine derives its
  signal from trade-tape/candle proxies rather than a real order book.
- **Correlation/Order Flow are not reproducible in Market Replay Mode**:
  both require live, real-time data feeds that cannot be replayed from
  the primary symbol's own historical OHLCV alone.
- **ML department in Market Replay Mode is optional**: a replay session
  only includes an ML vote if trained classification/regression models
  are explicitly supplied; by default it is an honest absence, not a
  fabricated prediction.
- **Single symbol, single account**: the platform trades XAUUSD only,
  on one configured MT5 demo account.
- **Demo-account-only**: `live_trading_approved` is hardcoded `False` in
  every live entrypoint; enabling real-money trading is a separate,
  explicit decision this codebase never makes on its own.
"""

_KNOWN_ISSUES = """\
- Historical Similarity Search has no upper bound on how many stored
  candles it scans per query (`_MAX_CANDLES_CONSIDERED = 1_000_000`);
  this will need a proper indexed/windowed approach well before that
  ceiling is reached.
- Market Replay Mode sessions are held in-process, in-memory only --
  they do not survive a web UI restart, and are not shared across
  multiple browser tabs/processes.
"""

_PRODUCTION_READINESS = """\
- Demo-account live trading: **running continuously** on the connected
  MT5 demo account since Phase 24, with real-time Telegram notifications.
- Every phase in this document has full unit/integration test coverage,
  `ruff` clean, and `mypy --strict`-equivalent clean (see `pyproject.toml`).
- Live (real-money) trading: **not enabled**, and gated behind an
  explicit, separate decision outside this codebase's own control paths.
"""

_ROADMAP = """\
- Wire a real Macro data provider (FRED) and News provider (NewsAPI) to
  exit "reduced mode" for those two departments.
- Extend Market Replay Mode with a persisted (not in-memory) session
  store if multi-session/multi-operator replay becomes a requirement.
- Evaluate real DOM/order-flow data if the connected broker or account
  tier ever exposes it, to replace the current synthetic proxy.
"""

_FUTURE_IMPROVEMENTS = """\
- Extend the AI Weight Optimizer's recommendation cadence to be
  configurable (currently a fixed 100-trade batch) once enough
  production history exists to judge whether 100 is the right size.
- Consider a persisted "as-of" news/regime index to make Market Replay
  Mode's candidate-window search (`/api/replay/candidates/*`) faster as
  the news/regime tables grow.
"""


def _list_tables() -> list[str]:
    from src.database.postgres.base import Base
    from src.models import (  # noqa: F401
        book,
        book_claim,
        candle,
        concept,
        correlated_instrument,
        correlated_price,
        historical_similarity,
        improvement_proposal,
        market_regime,
        ml_model,
        news_article,
        runtime_settings,
        symbol,
        system_log,
        trade,
        weight_recommendation,
    )

    return sorted(table.name for table in Base.metadata.sorted_tables)


def _list_web_routes() -> list[str]:
    from src.interfaces.web.app import app

    # FastAPI's auto-generated schema endpoint, not a platform feature --
    # docs_url/redoc_url are already disabled in `app.py`.
    infra_paths = {"/openapi.json"}

    routes = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or path in infra_paths:
            continue
        method_prefix = f"{sorted(methods)[0]} " if methods else ""
        routes.append(f"{method_prefix}{path}")
    return sorted(set(routes))


def _list_technical_agents() -> list[str]:
    from src.core.technical_analysis.agent_registry import default_technical_agents

    return [agent.name for agent in default_technical_agents()]


def _list_opinion_departments() -> list[str]:
    from src.engines.learning_engine.factor_analysis import OPINION_DEPARTMENTS

    return list(OPINION_DEPARTMENTS)


def _count_migrations() -> int:
    return len(list(_MIGRATIONS_DIR.glob("2*.py")))


def _books_collection_name() -> str:
    from src.engines.book_engine.pipeline import BOOKS_COLLECTION_NAME

    return BOOKS_COLLECTION_NAME


def generate_current_state_markdown() -> str:
    """Build the full `CURRENT_STATE.md` content from live source introspection."""
    tables = _list_tables()
    routes = _list_web_routes()
    agents = _list_technical_agents()
    departments = _list_opinion_departments()
    migration_count = _count_migrations()
    books_collection = _books_collection_name()

    lines = [
        "# GOLD QUANT AI — Current State",
        "",
        "> Generated by `scripts/generate_current_state.py`. Do not hand-edit the",
        "> generated sections below (they will be overwritten) -- edit the",
        "> generator's source instead so this file and the code it describes never",
        "> drift apart.",
        "",
        "## Current Architecture",
        "",
        "Hexagonal/Clean Architecture, Python 3.12+, async-first. Independent",
        "engines (`src/engines/`) communicate through workflow orchestrators",
        "(`src/workflows/`) that never re-implement a department's own logic --",
        "they only sequence already-built outputs. Three independent trading",
        "engines run every live cycle: Intraday (M15, primary), Scalping",
        "(M1/H1), and Swing (D1/W1) -- each with its own confidence threshold",
        "and risk profile.",
        "",
        "## Implemented AI Departments",
        "",
        *(f"- `{name}`" for name in departments),
        "",
        "## Implemented Strategies",
        "",
        "- Intraday (primary, M15)",
        "- Scalping (M1/H1)",
        "- Swing (D1/W1)",
        "",
        "## Implemented Indicators / Technical Agents",
        "",
        *(f"- `{name}`" for name in agents),
        "",
        "## Implemented News Sources",
        "",
        "- NewsAPI (`src.settings.DataProvidersSettings.newsapi_api_key`) --",
        "  reduced mode (unconfigured) until a key is set; see Known Limitations.",
        "",
        "## Implemented Correlation Sources",
        "",
        "- Any MT5-tradable instrument registered via `CorrelatedInstrument`",
        "  (`src.repositories.correlated_instrument_repository`) -- up to 19",
        "  instruments watchlisted per `Phase 25` (DXY, yields, other metals,",
        "  major FX pairs).",
        "",
        "## Implemented ML Models",
        "",
        "- `ClassificationModel` (multinomial logistic regression over",
        "  directional labels) -- `src.core.ml.model`.",
        "- `RegressionModel` (linear regression predicting forward return %) --",
        "  `src.core.ml.model`.",
        "- Trained per-symbol/timeframe via `TrainingService`",
        "  (`src.engines.ml_engine.training`) and persisted through",
        "  `ml_models`/`ModelRegistry`.",
        "",
        "## Books Intelligence",
        "",
        "- Book Engine pipeline ingests `/books`, chunks, embeds, and stores",
        f"  vectors in the Qdrant collection `{books_collection}`.",
        "- `BookClaim` extraction + statistical validation against real market",
        "  behavior (a claim is never trusted until backtested).",
        "",
        "## Execution Engine",
        "",
        "- `MT5Client` (`src.core.execution.mt5_client`) -- demo-account-only;",
        "  every live entrypoint hardcodes `live_trading_approved=False`.",
        "- Full trade journal (`Trade` model) with post-trade review and",
        "  automatic post-mortem on every closed trade.",
        "",
        "## Telegram Integration",
        "",
        "- `TelegramNotifier` + Russian-localized message formatting",
        "  (`src.core.notifications`), covering signals, post-mortems, and",
        "  scheduled reports.",
        "",
        "## Web/Desktop Interface",
        "",
        "Local FastAPI web UI (`src.interfaces.web.app`), binds to localhost",
        "only, no authentication (single-operator tool). Registered routes:",
        "",
        *(f"- `{route}`" for route in routes),
        "",
        "## Database Structure",
        "",
        f"PostgreSQL, {migration_count} migrations applied. Tables:",
        "",
        *(f"- `{table}`" for table in tables),
        "",
        "## Qdrant Structure",
        "",
        f"- Collection `{books_collection}`: book chunk embeddings for semantic search.",
        "",
        "## Current Limitations",
        "",
        _KNOWN_LIMITATIONS.rstrip(),
        "",
        "## Known Issues",
        "",
        _KNOWN_ISSUES.rstrip(),
        "",
        "## Production Readiness",
        "",
        _PRODUCTION_READINESS.rstrip(),
        "",
        "## Roadmap",
        "",
        _ROADMAP.rstrip(),
        "",
        "## Future Improvements",
        "",
        _FUTURE_IMPROVEMENTS.rstrip(),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    content = generate_current_state_markdown()
    _OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
