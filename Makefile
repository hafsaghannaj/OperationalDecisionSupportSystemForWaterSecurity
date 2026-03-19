SHELL := /bin/zsh
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup setup-full dev down api worker web test lint migrate migrate-local seed seed-local real-seed real-seed-local train train-local

setup:
	python3 -m venv $(VENV)
	$(PIP) install -e '.[dev]'
	cd services/web && npm install

setup-full:
	python3 -m venv $(VENV)
	$(PIP) install -e '.[dev,geo,ml]'
	cd services/web && npm install

dev:
	docker compose up --build

down:
	docker compose down --remove-orphans

api:
	$(PYTHON) -m uvicorn services.api.app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	$(PYTHON) -m services.worker.app.main

web:
	cd services/web && npm run dev

migrate:
	docker compose exec api alembic upgrade head

migrate-local:
	$(PYTHON) -m alembic upgrade head

seed:
	docker compose exec api python -m services.worker.app.bootstrap

seed-local:
	$(PYTHON) -m services.worker.app.bootstrap

real-seed: ## Fetch real GeoBoundaries + OCHA + DHS data and bootstrap
	docker compose exec api python -m services.worker.app.bootstrap_real

real-seed-local: ## Fetch real data and bootstrap (host, no Docker)
	AQUAINTEL_DATABASE_URL=postgresql+psycopg://aquaintel:aquaintel@localhost:5432/aquaintel \
	python -m services.worker.app.bootstrap_real

train:
	docker compose exec api python -m pipelines.training.baseline

train-local:
	$(PYTHON) -m pipelines.training.baseline

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
