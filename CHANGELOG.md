# Changelog

All notable changes to GOLD QUANT AI are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Phase 1 — Project Initialization

- Project directory structure established per `PROJECT_STRUCTURE.md`.
- Poetry-based dependency management (`pyproject.toml`).
- Configuration system (`src/settings.py`, `config/*.yaml`).
- Structured JSON logging (`src/common/logging`).
- Docker + Docker Compose infrastructure (Postgres, Redis, Qdrant, Prometheus, Grafana).
- CI pipeline (lint, type-check, test) via GitHub Actions.
- Pytest framework with coverage gates.
- Startup diagnostics (`src/bootstrap.py`).
- Baseline monitoring/metrics scaffold.

### Phase 2 — Database

- Async SQLAlchemy engine/session management (`src/database/postgres`).
- ORM models (`src/models`): `Symbol`, `SystemLog`.
- Repository pattern: generic `BaseRepository` + domain repositories (`src/repositories`).
- Alembic migrations (`src/database/migrations`), initial schema applied via CI.
- Redis async client (`src/database/redis`).
- Qdrant async client + collection bootstrap (`src/database/qdrant`).
- PostgreSQL backup/restore via `pg_dump`/`pg_restore` (`src/database/backup`, `src/database/restore`).
- Migration/schema integrity check (`src/database/postgres/integrity.py`).
- Idempotent seed data for the primary symbol (`src/database/seed`).

### Phase 3 — Data Collection Engine (framework)

- Provider abstraction (`src/core/data_collection/provider.py`), quality scoring
  (`validation.py`), Redis-backed cache (`cache.py`), and tiered fallback chain
  (`fallback.py`) per `DATA_COLLECTION_ENGINE.md` / `DATA_QUALITY_STANDARD.md`.
- Reference provider adapters proving the pattern end-to-end: FRED (economic data),
  NewsAPI (news), TwelveData (market data) — each gracefully reports
  "not configured" until its API key is added to `.env`, rather than faking data.
- Additional providers (Bloomberg/Reuters, TradingEconomics, Polygon, ...) follow
  the same `DataProvider` interface and are added incrementally per source.

### Phase 4 — Book Engine

- Configurable embedding provider (`src/core/embeddings`): local sentence-transformers
  by default (BAAI/bge-m3 -> BAAI/bge-large-en-v1.5 -> all-MiniLM-L6-v2 fallback
  chain, no API key required), switchable to OpenAI via `config/books.yaml`
  (`embedding.provider`) alone — no code changes needed to switch.
- ORM models + migration: `Book`, `BookChunk`, `Concept`, `ConceptRelationship`,
  `BookClaim` (`src/models`, `src/database/migrations/versions/202607060002_*`).
- Text extraction (`pypdf`) with OCR fallback (`pytesseract`/`pdf2image`, gracefully
  degrading when Tesseract isn't installed), language detection (`langdetect`),
  cleaning, and word-window chunking with overlap (`src/engines/book_engine`).
- Explainable v1 topic classification and entity extraction (keyword/pattern-based;
  BOOK_RAG.md's taxonomy), pending a trained ML classifier in a later phase.
- Full ingestion pipeline (`pipeline.py`): dimension-aware Qdrant collection
  bootstrap, per-chunk embedding/topic/entity extraction, knowledge graph
  co-occurrence linking, Qdrant upsert — persisted books are never re-ingested.
- Semantic search (`search.py`) over ingested books, tracking chunk usage counts.

### Phase 5 — Historical Research Engine

- ORM models + migration: `Candle`, `MarketRegime`, `HistoricalSimilarity`
  (`src/models`, `src/database/migrations/versions/202607060003_*`).
- Data validation (`src/engines/historical_engine/validation.py`): OHLC integrity,
  in-batch duplicate detection, gap detection per timeframe — invalid candles are
  reported and excluded, never silently "fixed" (DATA_QUALITY_STANDARD.md).
- Historical ingestion service reusing Phase 3's `FallbackChain`/`TwelveDataMarketProvider`
  (`ingestion.py`) — activates once `TWELVEDATA_API_KEY` is set; an MT5-backed Tier 1
  source can be added later without changing the service.
- Explainable rule-based regime classifier (`regime_detection.py`): bull/bear trend,
  range, high/low volatility, transition, from trend-slope/volatility/range-width
  features — pending ML Engine augmentation in a later phase.
- Similarity engine (`similarity.py`, `similarity_service.py`): ranks historical
  windows by feature-vector similarity to the current window and aggregates
  forward-return outcome statistics (win rate, average/median/max/min return).

### Phase 6 — Technical Engine

- Shared `TechnicalAgent`/`AgentReport` interface (`src/core/technical_analysis`) and
  fractal swing-point detection (`swings.py`), reused by every agent below.
- Seven independent Technical Department agents (`src/agents/technical`), each
  producing bias/confidence/evidence per AGENT_SYSTEM.md: Market Structure
  (HH/HL/LH/LL, BOS/CHoCH), Trend (slope/age/acceleration), Liquidity (equal
  highs/lows, sweeps), Smart Money (order blocks, displacement, FVG,
  premium/discount), Volatility (ATR expansion/compression), Support/Resistance
  (clustered swing levels), Price Action (doji/hammer/marubozu/engulfing/inside-
  outside bar).
- `TechnicalConfluence` aggregator combining every agent's report into one final
  Technical Report (bullish/bearish/neutral probability, confidence, quality
  grade), optionally blending in Phase 5's historical outcome statistics.
- ICT, Wyckoff, Elliott, Volume Profile, Order Flow, VWAP and Fibonacci agents
  follow the same `TechnicalAgent` interface and are added incrementally.

### Phase 7 — Macro Engine

- Shared agent primitives extracted to `src/core/agents` (`report.py`, `confluence.py`)
  so the Technical and Macro Departments' report format and voting/weighting/grading
  algorithm are defined once, not duplicated (`TechnicalConfluence` refactored
  onto the shared implementation with no behavior change).
- `MacroAgent`/`MacroObservation` interface (`src/core/macro_analysis`) for agents
  that analyze scalar economic time series rather than OHLCV candles.
- FRED-backed macro series ingestion (`src/engines/macro_engine/ingestion.py`),
  reusing Phase 3's `FallbackChain`/`FredEconomicProvider` — activates once
  `FRED_API_KEY` is set; missing FRED observations (".") are excluded, never
  fabricated.
- Five Macro Department agents (`src/agents/macro`) sharing one trend-to-gold-bias
  helper (`trend_mapping.py`) per the standard, documented directional
  relationships: Interest Rate and Bond Yield (rising = bearish, opportunity
  cost), Inflation (rising = bullish, inflation hedge), Employment (rising
  unemployment = bullish, safe haven), Dollar Index (strengthening = bearish,
  inverse USD pricing) — every report includes an explicit caveat disclosing
  the heuristic's limitations (AGENT_SYSTEM.md: "Agents never hide uncertainty").
- `MacroConfluence` aggregator combining every macro agent's report into one
  final Macro Report, mirroring `TechnicalConfluence`.

### Phase 8 — News Engine

- Shared keyword-classification utility (`src/utils/keyword_classifier.py`) extracted
  from the Book Engine's topic classifier per `CODING_STANDARDS.md` ("Never duplicate
  functionality"); `src/engines/book_engine/topic_classification.py` refactored onto it
  with no behavior change (verified by its existing test suite).
- `NewsArticle` ORM model + migration (`src/models/news_article.py`,
  `202607060004_news_engine_schema.py`) with a unique constraint on `content_hash` for
  deduplication and a check constraint on `expected_volatility`.
- `NewsArticleRepository` (`get_by_content_hash`, `list_by_category`).
- Keyword-based event classification against a `NEWS_ENGINE.md`-derived taxonomy
  (`src/engines/news_engine/classification.py`) — explainable v1, pending a trained
  classifier from the future Machine Learning Engine.
- Content-hash deduplication (`deduplication.py`): normalized title+source+date hashed
  with SHA-256, so republished/duplicate articles are never re-analyzed.
- Importance/expected-volatility scoring (`scoring.py`) blending category impact,
  source reliability and entity richness (reusing the Book Engine's
  `extract_entities`); `processing.py` orchestrates all of the above into one step.
- NewsAPI-backed news ingestion pipeline (`src/engines/news_engine/ingestion.py`),
  reusing Phase 3's `FallbackChain`/`NewsApiProvider` — activates once
  `NEWSAPI_API_KEY` is set; incomplete provider records (missing title/source/date)
  are skipped and reported, never fabricated.
- Article text cleaning (`cleaning.py`): strips NewsAPI's truncation marker
  (`"... [+N chars]"`) and normalizes whitespace before classification/storage.
- Historical linking v1 (`linking.py`): finds prior articles in the same event
  category as evidence for the Chief AI's "Historical Similarity" field; measuring
  each linked article's actual price reaction is deferred to a future cross-engine
  integration with the Historical Research Engine's similarity service.

### Phase 9 — Machine Learning Engine

- Added `scikit-learn` dependency: linear/logistic models chosen over black-box
  ensembles so every prediction stays exactly decomposable per
  MACHINE_LEARNING_ENGINE.md "Core Principles" ("No black-box decisions... every
  prediction must be explainable").
- Feature engineering (`src/core/ml/features.py`): momentum, trend, volatility,
  range-width and volume-trend features per rolling candle window, reusing the
  Historical Research Engine's regime features rather than recomputing them.
- Label generation (`src/core/ml/labels.py`): forward-return thresholds classify
  each sample into `strong_bearish`/`bearish`/`neutral`/`bullish`/`strong_bullish`.
- Dataset builder (`src/engines/ml_engine/dataset.py`): builds leakage-free,
  chronologically ordered samples from stored candles, plus a non-shuffled
  train/validation/test split (out-of-sample by construction).
- `ClassificationModel`/`RegressionModel` (`src/core/ml/model.py`): thin wrappers
  around `LogisticRegression`/`LinearRegression` tracking `feature_names`,
  `trained_at` and `n_samples`.
- Calibration diagnostics (`calibration.py`): Brier score and probability-bucket
  reliability curves.
- Explainability (`explainability.py`): exact per-feature contribution
  (`coefficient * value`) decomposition for both model types.
- Feature importance (`feature_importance.py`): permutation importance via
  `sklearn.inspection.permutation_importance` — a ranking, not SHAP/Gain/Mutual
  Information, which are reserved for future tree/ensemble model types.
- Model Registry: `MLModel` ORM + migration (`202607070001_ml_model_registry_schema.py`)
  + `MLModelRepository` (`get_latest`, `get_production`, `list_versions`,
  `next_version`) tracking version, training date, features, hyperparameters,
  metrics and lifecycle status (`training`/`candidate`/`production`/`retired`).
- Training orchestration (`src/engines/ml_engine/training.py`): builds the
  dataset, fits both models, computes validation metrics (accuracy/precision/
  recall/F1 for classification; MAE/R2 for regression), and registers each new
  version with status `"training"` — promotion to `"candidate"`/`"production"`
  remains a separate, explicit decision per IMPLEMENTATION_ROADMAP.md ("No
  production strategy may change automatically"). Raises
  `InsufficientTrainingDataError` rather than training on a fabricated or
  undersized dataset.

### Phase 10 — Statistics Engine

- Cross-department probability aggregation (`src/engines/statistics_engine/probability.py`):
  combines every department's `CombinedVote` (Technical, Macro, News, Historical,
  ML) into one overall bull/bear/neutral distribution, per DECISION_ENGINE.md
  "Consensus" — one level up from `combine_agent_reports`, which combines agents
  *within* one department.
- Cross-department confidence aggregation (`confidence.py`): historical-
  reliability-weighted average confidence across named inputs, per
  DECISION_ENGINE.md "Confidence Calculation"; reliability weighting is a
  pluggable input pending the Self-Learning Engine's measured track record.
- Performance metrics (`performance.py`): win rate, profit factor, expectancy,
  annualized Sharpe/Sortino, max drawdown — computed over realized trade/period
  returns once real trades exist (Phase 13 Execution Engine, Phase 15
  Backtesting Engine), never fabricated from no data.
- Expected value (`expected_value.py`): the standard
  `p_win * avg_win - p_loss * avg_loss` institutional formula.
- Risk metrics (`risk_metrics.py`): historical-simulation Value at Risk and
  R-multiple statistics — pure measurement, no trade-gating logic (that
  belongs to the dedicated Risk Engine, Phase 11).
- Similarity Engine (Phase 5's `historical_engine/similarity.py` +
  `similarity_service.py`) and Feature Importance (Phase 9's
  `core/ml/feature_importance.py`) already satisfy the corresponding
  roadmap checklist items — reused as-is, not duplicated.

### Phase 11 — Risk Engine

- Dynamic position sizing (`src/engines/risk_engine/position_sizing.py`): sizes
  every trade from account equity and the distance to its invalidation level
  (never a fixed size), scaled down by a drawdown factor per RISK_ENGINE.md
  "Risk Philosophy" ("Never increase risk after losses").
- Exposure limits (`exposure.py`): checks a proposed trade against configurable
  total/instrument/correlated/session/daily exposure caps
  (RISK_ENGINE.md "Exposure Control").
- Correlation concentration control (`correlation.py`): correlation-weighted
  exposure across related instruments (Gold, Silver, DXY, US10Y, VIX, indices,
  Oil, Copper), flagging excessive concentration even when no single
  instrument's own exposure looks high.
- Trade approval pipeline (`approval.py`): `classify_confidence_level` implements
  RISK_ENGINE.md's exact "Confidence Levels" table (0-40 reject, 41-60
  observation-only, 61-75 possible-setup, 76-85 high-quality/execution-allowed,
  86-100 institutional-grade); `evaluate_trade` runs every "Trade Rejection
  Rules" check (spread, session, historical edge, critical news, data
  completeness, system health, exposure) and reports every failing reason —
  "No trade may bypass the Risk Engine" even when every other department
  agrees. Live open-position aggregation and broker-fed spread/session data
  feed into this pipeline once the Execution Engine (Phase 13) is connected;
  these functions accept them as explicit inputs rather than sourcing them
  internally, so they are fully testable today.

### Phase 12 — Chief AI

- Decision pipeline (`src/engines/chief_ai/decision.py`): implements
  DECISION_ENGINE.md's "Decision Pipeline" end to end — missing required
  reports force WAIT ("Required Inputs"), department votes are combined via
  Phase 10's `combine_department_votes` (Consensus Engine), confidence via
  Phase 10's `compute_overall_confidence` (Confidence Aggregation), conflicting
  near-tied departments and unknown regimes raise uncertainty and force WAIT
  (Conflict Resolution), and a Risk Engine rejection always overrides an
  otherwise-favorable vote — "No trade may bypass the Risk Engine." "The
  default decision is always WAIT" holds structurally: every non-WAIT path
  requires passing every prior check.
- Explanation engine (`explanation.py`): builds DECISION_ENGINE.md's required
  "Why now / Why this direction / Why not opposite / What confirms / What
  invalidates" fields entirely from the decision's own recorded evidence — no
  freeform text generation.
- Alternative scenarios (`scenarios.py`): primary/alternative scenario framing
  and invalidation condition per decision direction; Maximum Risk/Expected
  Duration/Historical Analogue are left for the caller to attach from Phase 11
  position sizing and Phase 5 historical similarity once wired to a specific
  candidate trade, rather than guessed here.
- Research requests (`research_requests.py`): turns addressable uncertainty
  factors (unknown regime, conflicting departments) into structured
  Question/Motivation/Priority requests per RESEARCH_FRAMEWORK.md "Hypothesis
  Generation", rather than silently absorbing every uncertainty into a bare WAIT.

### Phase 13 — Execution Engine (MT5)

- Trade journal (`src/models/trade.py` + `202607070002_trade_journal_schema.py`
  + `TradeRepository`): tracks every order/position from submission through
  close (MT5_ENGINE.md "Order Parameters" / "Execution Log"), independent of
  which gateway (demo, paper, future live) placed it.
- `MT5Client` gateway interface (`src/core/execution/mt5_client.py`) plus
  `RealMT5Client`, which wraps the official `MetaTrader5` Python package for
  connect/account-info/place-order/modify/close/cancel. No MT5 terminal or
  broker account was available while building this, so `RealMT5Client` is
  exercised in tests against a fake `MetaTrader5` module (the same
  sys.modules-injection technique used for other external SDKs), not a real
  broker; it activates automatically once `MT5_LOGIN`/`MT5_PASSWORD`/
  `MT5_SERVER` are set in `.env`, but MT5_ENGINE.md's "Initial Mode: Demo
  Mode" rule means it must be validated against a real demo account before
  any live use — a genuine requirement for MT5 account credentials, which
  were not available in this environment.
- Pre-execution safety gate (`order_validation.py`): implements MT5_ENGINE.md
  "Account Safety" / "Execution Validation" — account type/number checks,
  live-trading approval, symbol match, terminal connection, market session,
  Risk Engine and Chief AI approval — every failure reported explicitly.
- Deterministic magic numbers (`magic_number.py`): stable per strategy
  name/version pair so the same strategy's orders are consistently tagged
  across restarts (MT5_ENGINE.md "Magic Number").
- Live position monitoring, trailing/break-even/partial-close management and
  the Telegram/emergency-mode integrations described in MT5_ENGINE.md require
  a running connection to iterate against and are deferred to when real MT5
  credentials make that live loop meaningful to build and test.

### Phase 14 — Self Learning Engine

- Post-trade review (`src/engines/learning_engine/trade_review.py`): derives
  realized return, planned-risk percentage and R-multiple from a closed
  `Trade`'s own recorded fields. Maximum Favorable/Adverse Excursion
  (SELF_LEARNING_ENGINE.md "Every Closed Trade") require tick-level price
  history during the trade's lifetime, which no engine collects yet — a
  genuine gap, not approximated here.
- Mistake/win factor analysis (`factor_analysis.py`): implements
  SELF_LEARNING_ENGINE.md "Error Analysis"/"Win Analysis" as concrete,
  reproducible checks (confidence vs. threshold, historical edge vs.
  minimum, regime known/unknown, news imminent, stop distance vs. expected
  volatility) against the trade's own recorded decision context — never a
  narrative guess.
- Hypothesis generator (`hypothesis.py`): promotes factors that recur across
  at least 3 reviewed trades into structured hypotheses (Question,
  Motivation, Supporting Evidence, Expected Outcome, Validation Plan,
  Success/Failure Criteria, Priority) per RESEARCH_FRAMEWORK.md — a single
  occurrence stays an anecdote, never a hypothesis.
- Improvement proposal system: `ImprovementProposal` ORM + migration
  (`202607070003_improvement_proposal_schema.py`) + `ImprovementProposalRepository`
  (`list_pending`), and a `build_proposal_from_hypothesis` builder
  (`proposal.py`). Every proposal starts `status="pending"` — per
  SELF_LEARNING_ENGINE.md "User Approval", nothing in this codebase
  transitions a proposal to `approved` automatically; that is always an
  explicit, external user action.

### Phase 15 — Backtesting Engine

- Historical replay simulator (`src/engines/backtesting_engine/simulator.py`):
  deterministic bar-by-bar ("Bar Replay") execution — a signal is always
  computed from candles strictly before the bar it acts on
  (BACKTESTING_ENGINE.md "No future information may leak into the past");
  entries/exits price at the acting bar's open, stop/target checks use that
  bar's high/low (stop checked first when both could trigger in the same
  bar, since intrabar order is unknowable without tick data), and
  `ExecutionCosts` (spread/slippage/commission) are applied on both entry
  and exit. Computed stop/target levels are rounded to eliminate binary
  floating-point noise (e.g. `100 * 1.1` is `110.00000000000001` in IEEE-754)
  that would otherwise cause an exact-touch bar to miss its own target.
- Report builder (`report.py`): assembles BACKTESTING_ENGINE.md's "Report"
  quantitative fields (win rate, profit factor, Sharpe, Sortino, drawdown,
  expectancy) by reusing Phase 10's `statistics_engine.performance`;
  qualitative fields (Strengths, Weaknesses, Failure Conditions) are
  caller-supplied, not fabricated.
- Walk-forward validation (`walk_forward.py`): splits candles into
  consecutive out-of-sample windows and backtests each independently;
  `passed` requires every window to clear the win-rate/profit-factor
  minimums — "Only strategies passing every stage continue."
- Monte Carlo (`monte_carlo.py`): resamples a completed backtest's trade
  returns with replacement to build a distribution of possible equity/
  drawdown outcomes (5th/50th/95th percentiles), rather than trusting the
  single realized trade order; seedable for reproducibility.
- Parameter grid search (`optimization.py`): backtests every stop-loss/
  take-profit combination and ranks by a robustness score (profit factor
  penalized by drawdown, falling back to expectancy when profit factor is
  infinite) — "Never optimize only for maximum profit. Optimize for
  robustness."
- Stress testing reuses the simulator's own `ExecutionCosts` (elevated
  spread/slippage) rather than a separate module, and live tick-level
  data requirements (Tick Replay, real spread/liquidity stress from
  MT5_ENGINE.md market data) remain a gap pending that data source.

### Phase 16 — Telegram

- Added `python-telegram-bot` dependency. Renamed the Phase 1 scaffold
  directory `src/telegram/` to `src/telegram_integration/`: the package
  name `telegram` is claimed by the third-party SDK itself, and
  `mypy_path = "src"` made `src/telegram/__init__.py` resolve to the same
  module name as the installed `telegram` package, a hard collision
  (`mypy`: "Source file found twice under different module names"). The
  scaffold had no imports anywhere yet, so the rename was zero-risk; this
  keeps `import telegram` (the real SDK) and the platform's own Telegram
  code unambiguous going forward.
- `TelegramNotifier` gateway interface (`src/core/notifications/telegram_client.py`)
  plus `RealTelegramNotifier`, wrapping `telegram.Bot.send_message`. No
  Telegram bot token was available while building this, so it is
  exercised in tests against a fake `telegram.Bot` (the same
  sys.modules-injection technique used for `MetaTrader5`); it activates
  automatically once `TELEGRAM_BOT_TOKEN` is set in `.env`.
- Message formatters (`formatting.py`) for the structurally concrete
  TELEGRAM.md message types backed by data this platform already
  produces: Signal Message, Trade Closed Message, Daily Report, News
  Alert, Error Report, Approval Request (from Phase 14's
  `ImprovementProposal`) — every field comes from an existing dataclass
  or ORM model, nothing freeform.
- Anti-spam/priority rules (`rules.py`): content-hash-based duplicate
  suppression with a "critical bypasses dedup" override, per TELEGRAM.md
  "Message Rules" ("Never spam... Critical messages bypass silent mode").
- Command registry (`commands.py`): dispatch table for every
  TELEGRAM.md "Admin Command" (`/dashboard`, `/status`, `/signals`, ...).
  Wiring this to a live, polling `telegram.ext.Application` — along with
  the remaining message types (Open Trade Update, Trailing/Break-Even/
  Partial-Close messages, Market Analysis Report, System Status, the
  full Main Menu/Interactive Buttons UI) — requires an actual bot
  connection to iterate against and is deferred until a real
  `TELEGRAM_BOT_TOKEN` is available.

### Phase 17 — Monitoring

- Health check aggregation (`src/core/monitoring/health.py`): combines every
  `src.core.diagnostics` `CheckResult` into one `HealthReport` for the
  OBSERVABILITY_AND_MONITORING.md "Observability API" (`/health`) —
  unhealthy only if a *critical* check failed, matching FAILSAFE_PROTOCOL.md's
  degraded-but-observable operation rather than an all-or-nothing outage.
- Per-agent health tracking (`agent_health.py`): `AgentHealthRegistry.track()`
  wraps any agent call, recording latency/success/failure into both an
  in-memory rolling status and new Prometheus metrics
  (`gold_quant_ai_agent_last_run_healthy`, `..._agent_run_duration_seconds`,
  `..._agent_run_failures_total`) — failures are recorded then re-raised,
  never swallowed.
- System resource metrics (`system_metrics.py`): CPU/memory/disk utilization
  via `psutil`, recorded into new gauges
  (`gold_quant_ai_cpu_usage_percent`, `..._memory_usage_percent`,
  `..._disk_usage_percent`). GPU/temperature/network/swap are intentionally
  not duplicated here — the Phase 1 Docker Compose stack's Node
  Exporter/cAdvisor already cover container/host-level metrics
  (OBSERVABILITY_AND_MONITORING.md "Prometheus Exporters").
- The full per-engine metric catalogue (Chief AI/Risk/Execution/Learning/ML/
  News/Historical/Security metrics), Grafana dashboards/panels, alerting
  levels, self-healing automation and audit reports in
  OBSERVABILITY_AND_MONITORING.md are extensive enough to warrant
  building out incrementally alongside the engines and a live deployment
  they instrument, rather than speculatively in one pass.

### Phase 18 — System Testing

- Signal workflow (`src/workflows/trade/pipeline.py`): the first true
  end-to-end integration, wiring WORKFLOW_ENGINE.md's "Signal Workflow"
  (Chief AI -> Risk/Execution Validation -> Telegram Preview -> MT5
  Execution -> Journal) across Phases 11-16 exactly as specified — a
  non-BUY/SELL decision or a failed execution-validation check never
  reaches MT5 or Telegram; a rejected MT5 order is still journaled
  (`status="rejected"`) rather than silently dropped; a filled order is
  journaled `status="open"` with its broker ticket before the Telegram
  preview is sent. Verified against fake `MT5Client`/`TelegramNotifier`
  implementations and a real (SQLite-backed) `TradeRepository`.
- Full-repository verification: complete alembic migration chain
  (`202607060001` -> `202607070003`, 8 migrations) applies cleanly in one
  pass; `ruff check`, `mypy --strict`, and the full pytest suite all pass
  with zero warnings; no `TODO`/`FIXME`/placeholder markers or
  unjustified `NotImplementedError` remain anywhere in `src/`; coverage
  holds at 100% across all ~300 source modules.
- Renamed `src/telegram/` -> `src/telegram_integration/` (Phase 16) is the
  one architectural fix this pass surfaced; everything else built through
  Phase 17 was already internally consistent.

### Phase 19 — Optimization

- `CandleRepository.insert_new`: replaced a per-candle `session.add()` loop
  with a single `session.add_all()` call — fewer Python-level calls into
  SQLAlchemy's unit-of-work for the same effect, most noticeable on large
  historical backfills.
- Qdrant collections now created with an explicit `HnswConfigDiff`
  (`m=16`, `ef_construct=200` — Qdrant's own recommended balanced-recall
  defaults), exposed as a parameter on `ensure_collection_for_dimension`
  rather than hardcoded, so index quality can be deliberately re-tuned
  once real query latency/recall data exists
  (OBSERVABILITY_AND_MONITORING.md "Qdrant Metrics").
- Already in place from earlier phases and reconfirmed rather than
  duplicated: PostgreSQL connection pooling with `pool_pre_ping` and
  `expire_on_commit=False` (`src/database/postgres/session.py`), the
  Redis-backed fallback cache for every external data provider (Phase 3),
  and per-table indexes on every foreign key/status/lookup column used by
  a repository query (audited across all 8 migrations — no missing-index
  query pattern found).
- This pass's full-suite re-run caught a real regression from the Qdrant
  HNSW change: `tests/integration/book_engine/_fakes.py`'s `FakeQdrantClient.
  create_collection` didn't accept the new `hnsw_config` keyword, breaking
  6 Book Engine tests. Fixed by accepting `**kwargs`. Exactly the kind of
  cross-module breakage the full pytest run (rather than per-phase test
  subsets) is meant to catch — a concrete justification for Phase 18's
  "test every module/integration" full-repository pass.
- Further optimization (query plan analysis, embedding batch-size tuning,
  GPU inference, execution-path latency budgets) requires production
  query volume and real embedding/inference workloads to profile against
  and is deferred until a live deployment provides that data.

### Phase 20 — Demo Deployment (in progress)

- Startup diagnostics extended with `check_mt5`/`check_telegram`
  (`src/core/diagnostics.py`), closing the gap the module's own docstring
  had flagged since Phase 1. Both report a clear "not configured" detail
  instead of a confusing low-level error when credentials are unset, and
  are now part of `run_startup_diagnostics`'s concurrent check set.
- `RealTelegramNotifier.verify_connection()` added (`getMe`-based token
  validation), reused by `check_telegram`.
- **Telegram: verified live.** Bot token confirmed via `getMe`
  (`@xauusd_bybob_bot`) and a real `sendMessage` was delivered to the
  configured group ("trade", chat id `-5127336869`). Values are ready to
  add to `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_IDS` or a
  dedicated trading-group setting) — this assistant's `.env` write access
  is permission-blocked, so the user adds them.
- **MT5: cannot be verified from this session.** `MetaTrader5.initialize()`
  communicates with the terminal via local IPC (named pipes/shared
  memory), which only works within the same Windows logon session as the
  running terminal. This assistant's execution environment is an isolated
  session even though nominally Windows, so `initialize()` reliably
  returns `IPC timeout` here regardless of whether the terminal is open
  on the user's own desktop. `MT5_LOGIN=109345080`,
  `MT5_SERVER=MetaQuotes_Demo` were confirmed well-formed for a MetaQuotes
  demo account; genuine connectivity can only be confirmed by running
  `check_mt5`/the platform directly on the machine where the terminal runs.
- Remaining Phase 20 work (Historical Learning bootstrap, Paper
  Validation, Forward Testing, Demo Trading loop, Continuous Improvement
  scheduling) builds on `SignalWorkflow` (Phase 18) once both gateways are
  confirmed live end-to-end in that same local session.
