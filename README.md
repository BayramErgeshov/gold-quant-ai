# GOLD QUANT AI

Institutional-grade, multi-agent AI research and trading platform for XAUUSD.

This is a research platform, not a signal bot. It coordinates independent research
departments (technical, macro, news, historical, machine learning, statistics, risk)
behind a Chief AI decision layer, and only acts on evidence that has passed
historical validation. See the project specification files in the repository root
(`PROJECT_VISION.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_ROADMAP.md`, etc.) for the
full institutional requirements this codebase implements.

## Status

Under active build-out, following `IMPLEMENTATION_ROADMAP.md` phase by phase.
Current phase: **Phase 1 — Project Initialization**.

## Requirements

- Python 3.12+
- Poetry
- Docker + Docker Compose
- MetaTrader 5 terminal (Windows) for live/demo execution

## Getting Started

```bash
cp .env.example .env       # fill in local credentials
poetry install
docker compose up -d       # postgres, redis, qdrant, prometheus, grafana
poetry run python -m src.bootstrap   # runs startup diagnostics
```

## Development

```bash
make lint       # ruff + mypy
make test       # pytest with coverage
make format     # ruff format
```

## Project Structure

See [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) for the authoritative layout.
Architecture consistency has higher priority than development speed — do not add
files outside the defined structure.

## Documentation

Institutional specifications live as Markdown files in the repository root and are
treated as mandatory requirements, not suggestions. Module-level documentation lives
under [`docs/`](docs/).

## Safety

The platform starts in **demo mode only**. Live trading requires explicit user
approval and separate credentials — see `FAILSAFE_PROTOCOL.md` and `MT5_ENGINE.md`.
