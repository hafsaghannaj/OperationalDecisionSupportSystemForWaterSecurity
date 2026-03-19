SHELL := /bin/zsh
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup setup-full dev down api worker web test lint migrate migrate-local seed seed-local real-seed real-seed-local train train-local demo-local real-manifest-local preview-up preview-down preview-db-prepare preview-bootstrap preview-real-bootstrap preview-smoke

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

preview-up:
	docker compose -f docker-compose.yml -f docker-compose.preview.yml up --build -d

preview-down:
	docker compose -f docker-compose.yml -f docker-compose.preview.yml down --remove-orphans

preview-db-prepare:
	zsh scripts/preview_db_prepare.sh

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

preview-bootstrap:
	$(MAKE) preview-db-prepare
	docker compose -f docker-compose.yml -f docker-compose.preview.yml exec api alembic upgrade head
	docker compose -f docker-compose.yml -f docker-compose.preview.yml exec api python -m services.worker.app.bootstrap

seed-local:
	$(PYTHON) -m services.worker.app.bootstrap

real-seed: ## Fetch real GeoBoundaries + OCHA + DHS data and bootstrap
	docker compose exec api python -m services.worker.app.bootstrap_real

preview-real-bootstrap:
	$(MAKE) preview-db-prepare
	docker compose -f docker-compose.yml -f docker-compose.preview.yml exec api alembic upgrade head
	docker compose -f docker-compose.yml -f docker-compose.preview.yml exec api python -m services.worker.app.bootstrap_real

real-seed-local: ## Fetch real data and bootstrap (host, no Docker)
	ODSSWS_DATABASE_URL=postgresql+psycopg://odssws:odssws@localhost:5432/odssws \
	python -m services.worker.app.bootstrap_real

train:
	docker compose exec api python -m pipelines.training.baseline

train-local:
	$(PYTHON) -m pipelines.training.baseline

demo-local:
	PYTHONPATH=src $(PYTHON) -m outbreaks.demo

real-manifest-local:
	PYTHONPATH=. $(PYTHON) -c "from libs.pilot import write_real_data_manifest; print(write_real_data_manifest())"

preview-smoke:
	$(PYTHON) scripts/preview_smoke_test.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
