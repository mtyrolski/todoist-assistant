.PHONY: init_local_env install_app ensure_frontend_deps update_env run_api run_frontend run_dashboard run_demo run_observer clear_local_env update_and_run test typecheck lint validate check chat_agent

FRONTEND_DIR := frontend
FRONTEND_NEXT := $(FRONTEND_DIR)/node_modules/.bin/next

init_local_env: # syncs history, fetches activity
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.init_env --config-dir configs --config-name automations

update_env: # updates history, fetches activity, do templates
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations

install_app: # installs frontend dependencies
	npm --prefix $(FRONTEND_DIR) install

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
		cleanup() { \
			echo "Stopping dashboard servers..."; \
			[ -n "$$pids" ] && kill $$pids 2>/dev/null || true; \
			wait 2>/dev/null || true; \
		}; \
		trap cleanup INT TERM EXIT; \
		uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000 & api_pid="$$!"; pids="$$pids $$api_pid"; \
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
		cleanup() { \
			echo "Stopping demo dashboard servers..."; \
			[ -n "$$pids" ] && kill $$pids 2>/dev/null || true; \
			wait 2>/dev/null || true; \
		}; \
		trap cleanup INT TERM EXIT; \
		TODOIST_DASHBOARD_DEMO=1 uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000 & api_pid="$$!"; pids="$$pids $$api_pid"; \
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
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations && \
	make run_dashboard

test: ## Run unit tests with pytest
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run pytest -v --tb=short tests/

typecheck: ## Run pyright type checks
	PYTHONPATH=. uv run pyright --warnings

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
