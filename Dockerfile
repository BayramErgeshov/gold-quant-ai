# GOLD QUANT AI — application image
# Multi-stage build: install dependencies with Poetry, ship a slim runtime image.
# See DEPLOYMENT.md: Docker First, Immutable Infrastructure, Health Checks.

FROM python:3.12-slim AS builder

ENV POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "poetry>=1.8,<2.0"

WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root --no-ansi

COPY . .
RUN poetry install --only main --no-ansi


FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 goldquant \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=goldquant:goldquant /app /app

USER goldquant

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["python", "-m", "src.bootstrap"]
