.PHONY: init_local_env ensure_frontend_deps update_env run_api run_frontend run_dashboard run_demo run_observer clear_local_env update_and_run test typecheck lint validate check chat_agent build_windows_installer build_macos_pkg build_macos_app build_macos_dmg docker_build docker_up docker_down docker_logs docker_pull docker_watch

FRONTEND_DIR := frontend
FRONTEND_NEXT := $(FRONTEND_DIR)/node_modules/.bin/next

init_local_env: # syncs history, fetches activity
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.init_env.automation --config-dir configs --config-name automations

update_env: # updates history, fetches activity, do templates
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env.automation --config-dir configs --config-name automations

ensure_frontend_deps: # installs frontend deps if missing
	@if [ ! -x "$(FRONTEND_NEXT)" ]; then \
		echo "Frontend dependencies missing; installing..."; \
		npm --prefix $(FRONTEND_DIR) install; \
	fi

run_api:
	uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000

run_frontend: ensure_frontend_deps
	npm --prefix $(FRONTEND_DIR) run dev -- --port 3000

# New meaning: run the "pretty" web dashboard stack (API + frontend)
run_dashboard: ensure_frontend_deps
	@bash -c '\
		set -euo pipefail; \
		pids=""; api_pid=""; fe_pid=""; \
		wait_for_api() { \
			local tries=0; \
			echo "Waiting for API to be ready..."; \
			if command -v curl >/dev/null 2>&1; then \
				until curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; do \
					tries=$$((tries+1)); \
					[ $$tries -ge 60 ] && break; \
					sleep 0.5; \
				done; \
			else \
				sleep 2; \
			fi; \
		}; \
		cleanup() { \
			echo "Stopping dashboard servers..."; \
			[ -n "$$pids" ] && kill $$pids 2>/dev/null || true; \
			wait 2>/dev/null || true; \
		}; \
		trap cleanup INT TERM EXIT; \
		uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000 & api_pid="$$!"; pids="$$pids $$api_pid"; \
		wait_for_api; \
		npm --prefix frontend run dev -- --port 3000 & fe_pid="$$!"; pids="$$pids $$fe_pid"; \
		echo "Dashboard running:"; \
		echo "  API:      http://127.0.0.1:8000"; \
		echo "  Frontend: http://127.0.0.1:3000"; \
		wait -n $$api_pid $$fe_pid; \
	'

run_demo: ensure_frontend_deps
	@bash -c '\
		set -euo pipefail; \
		pids=""; api_pid=""; fe_pid=""; \
		wait_for_api() { \
			local tries=0; \
			echo "Waiting for API to be ready..."; \
			if command -v curl >/dev/null 2>&1; then \
				until curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; do \
					tries=$$((tries+1)); \
					[ $$tries -ge 60 ] && break; \
					sleep 0.5; \
				done; \
			else \
				sleep 2; \
			fi; \
		}; \
		cleanup() { \
			echo "Stopping demo dashboard servers..."; \
			[ -n "$$pids" ] && kill $$pids 2>/dev/null || true; \
			wait 2>/dev/null || true; \
		}; \
		trap cleanup INT TERM EXIT; \
		TODOIST_DASHBOARD_DEMO=1 uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000 & api_pid="$$!"; pids="$$pids $$api_pid"; \
		wait_for_api; \
		TODOIST_DASHBOARD_DEMO=1 npm --prefix frontend run dev -- --port 3000 & fe_pid="$$!"; pids="$$pids $$fe_pid"; \
		echo "Demo dashboard running (anonymized):"; \
		echo "  API:      http://127.0.0.1:8000"; \
		echo "  Frontend: http://127.0.0.1:3000"; \
		wait -n $$api_pid $$fe_pid; \
	'

run_observer:
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.run_observer --config-dir configs --config-name automations

clear_local_env:
	rm -f activity.joblib

update_and_run: # updates history, fetches activity, do templates, and runs the dashboard
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env.automation --config-dir configs --config-name automations && \
	make run_dashboard

test: ## Run unit tests with pytest
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run python3 -m pytest -v --tb=short tests/

typecheck: ## Run pyright type checks
	PYTHONPATH=. uv run python3 -m pyright --warnings

lint: ## Run pylint
	PYTHONPATH=. uv run pylint -j 0 todoist tests

validate: typecheck lint ## Run typecheck + lint

check: validate test ## Run validate + tests

TODOIST_AGENT_MODEL_ID ?= mistralai/Ministral-3-3B-Instruct-2512
override TODOIST_AGENT_DEVICE := cpu
TODOIST_AGENT_ARGS ?=

chat_agent: ## Chat with local agent (Transformers; read-only)
	@echo "Starting agent with TODOIST_AGENT_MODEL_ID=$(TODOIST_AGENT_MODEL_ID)"
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run python -m todoist.agent.chat --model-id "$(TODOIST_AGENT_MODEL_ID)" $(TODOIST_AGENT_ARGS) --device "$(TODOIST_AGENT_DEVICE)"

build_windows_installer: ## Build Windows MSI (requires Windows + WiX + Node if dashboard is included)
	uv run python3 -m scripts.build_windows

build_macos_pkg: ## Build macOS pkg installer (requires macOS + pkgbuild/productbuild)
	./scripts/build_macos_pkg.sh

build_macos_app: ## Build macOS app bundle (requires macOS + PyInstaller)
	./scripts/build_macos_app.sh

build_macos_dmg: ## Build macOS DMG from the app bundle
	./scripts/build_macos_dmg.sh

docker_build: ## Build API + frontend Docker images
	docker compose build

docker_up: ## Run API + frontend with Docker Compose
	docker compose up

docker_down: ## Stop Docker Compose services
	docker compose down

docker_logs: ## Tail Docker Compose logs
	docker compose logs -f

docker_pull: ## Pull published Docker images
	docker compose pull

docker_watch: ## Live-reload with Docker Compose watch (Compose 2.22+)
	docker compose watch
