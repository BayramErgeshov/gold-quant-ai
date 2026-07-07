.PHONY: install lint format typecheck test test-unit test-integration security run docker-up docker-down migrate

install:
	poetry install

lint:
	poetry run ruff check src tests

format:
	poetry run ruff format src tests

typecheck:
	poetry run mypy src

test:
	poetry run pytest

test-unit:
	poetry run pytest -m unit

test-integration:
	poetry run pytest -m integration

security:
	poetry run bandit -r src -q

run:
	poetry run python -m src.bootstrap

docker-up:
	docker compose up -d

docker-down:
	docker compose down

migrate:
	poetry run alembic upgrade head

ci: lint typecheck security test
