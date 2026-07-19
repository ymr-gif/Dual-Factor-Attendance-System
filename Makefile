# nfc-scan — common commands (Step 10). `make setup` then `make up`.
.DEFAULT_GOAL := help
PY ?= python3
VENV := .venv
VPY := $(VENV)/bin/python
COMPOSE := docker compose

.PHONY: help setup up down logs dev enroll calibrate preview fmt lint health \
        web-install web-dev web-build purge digest doctor \
        appliance preflight backup restore update

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv, install deps, fetch models, seed .env
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install --upgrade pip
	$(VPY) -m pip install -r requirements.txt
	$(VPY) -m backend.fetch_liveness_models
	@test -f .env || cp .env.example .env
	@echo "Setup done. Edit .env, then 'make up' (docker) or 'make dev' (local)."

up:  ## Start the stack (Postgres + backend) via docker-compose
	$(COMPOSE) up -d --build

down:  ## Stop the stack (keeps the pgdata volume)
	$(COMPOSE) down

logs:  ## Tail backend + db logs
	$(COMPOSE) logs -f

dev:  ## Run the backend locally with autoreload (needs a reachable Postgres)
	$(VPY) -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload

health:  ## Curl the health endpoint
	@curl -fsS http://localhost:8001/health && echo

enroll:  ## Enroll a student: make enroll ARGS="S001 --images a.jpg b.jpg"
	$(VPY) -m backend.enroll $(ARGS)

calibrate:  ## Print score distribution / tune thresholds: make calibrate ARGS="--metric liveness"
	$(VPY) -m backend.calibrate $(ARGS)

preview:  ## Live camera diagnostic window: make preview ARGS="--match S001"
	$(VPY) -m backend.preview $(ARGS)

purge:  ## Apply data-retention windows (Step 20): delete/anonymize old logs
	$(VPY) -m backend.privacy

digest:  ## Send guardian attendance digest for yesterday
	$(VPY) -m backend.digest $(ARGS)

doctor:  ## Run system health check
	$(VPY) -m backend.doctor

web-install:  ## Install frontend deps (npm)
	cd frontend && npm install

web-dev:  ## Run the Vite dev server (proxies /api + /ws to :8001)
	cd frontend && npm run dev

web-build:  ## Build the SPA to frontend/dist (served by the backend at /app)
	cd frontend && npm run build

appliance:  ## Provision this box as an auto-start appliance (Step 40)
	bash deploy/install.sh

preflight:  ## Check GPU / camera / serial / deps (warn-only, Step 40)
	bash deploy/preflight.sh

backup:  ## Dump roster + attendance to backups/ (Step 43)
	bash deploy/backup.sh

restore:  ## Restore a backup: make restore FILE=backups/attendance-*.sql (Step 43)
	bash deploy/restore.sh $(FILE)

update:  ## Pull latest, migrate, rebuild, restart — data preserved (Step 43)
	bash deploy/update.sh

fmt:  ## Format backend code (black if available)
	@$(VPY) -m black backend 2>/dev/null || echo "black not installed — 'pip install black'"

lint:  ## Lint backend code (ruff if available)
	@$(VPY) -m ruff check backend 2>/dev/null || echo "ruff not installed — 'pip install ruff'"
