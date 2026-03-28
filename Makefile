.PHONY: init_local_env ensure_frontend_deps reinstall reinstall_frontend update_env run_api run_frontend run_dashboard run_dashboard_cpu run_dashboard_gpu stop_dashboard triton_shell run_demo run_observer clear_local_env update_and_run test coverage typecheck lint validate check check_explicit_any chat_agent build_windows_installer build_macos_pkg build_macos_app build_macos_dmg docker_build docker_up docker_down docker_logs docker_pull docker_watch

FRONTEND_DIR := frontend
FRONTEND_NEXT := $(FRONTEND_DIR)/node_modules/.bin/next
DASHBOARD_STATE_DIR := .cache/todoist-assistant/dashboard
DASHBOARD_PID_DIR := $(DASHBOARD_STATE_DIR)/pids
TRITON_MODEL_ID := Qwen/Qwen2.5-0.5B-Instruct
TRITON_MODEL_NAME := todoist_llm
TRITON_URL := http://127.0.0.1:8003

init_local_env: # syncs history, fetches activity
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.init_env.automation --config-dir configs --config-name automations

update_env: # updates history, fetches activity, do templates
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env.automation --config-dir configs --config-name automations

ensure_frontend_deps: # installs frontend deps if missing
	@needs_install=0; \
	if [ ! -x "$(FRONTEND_NEXT)" ]; then \
		needs_install=1; \
	else \
		desired="$$(node -e "const pkg=require('./$(FRONTEND_DIR)/package.json'); const deps=pkg.dependencies||{}; const dev=pkg.devDependencies||{}; console.log(deps.next || dev.next || '');")"; \
		installed="$$(node -e "try{const pkg=require('./$(FRONTEND_DIR)/node_modules/next/package.json'); console.log(pkg.version || '');}catch(e){console.log('');}")"; \
		if [ -z \"$$desired\" ] || [ -z \"$$installed\" ] || [ \"$$desired\" != \"$$installed\" ]; then \
			needs_install=1; \
		fi; \
	fi; \
	if [ $$needs_install -eq 1 ]; then \
		echo \"Frontend dependencies missing or out of date; installing...\"; \
		npm --prefix $(FRONTEND_DIR) install; \
	fi

reinstall_frontend: # force reinstall frontend deps (clean node_modules)
	rm -rf $(FRONTEND_DIR)/node_modules
	npm --prefix $(FRONTEND_DIR) install

reinstall: reinstall_frontend # convenience alias

run_api:
	@TODOIST_AGENT_TRITON_MODEL_ID="$(TRITON_MODEL_ID)" \
	TODOIST_AGENT_TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TODOIST_AGENT_TRITON_URL="$(TRITON_URL)" \
	uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000

run_frontend: ensure_frontend_deps
	npm --prefix $(FRONTEND_DIR) run dev -- --port 3000

run_dashboard: run_dashboard_cpu

run_dashboard_cpu: ensure_frontend_deps
	@TRITON_MODEL_ID="$(TRITON_MODEL_ID)" \
	TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TRITON_URL="$(TRITON_URL)" \
	DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh start cpu

run_dashboard_gpu: ensure_frontend_deps
	@TRITON_MODEL_ID="$(TRITON_MODEL_ID)" \
	TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TRITON_URL="$(TRITON_URL)" \
	DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh start gpu

stop_dashboard:
	@DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh stop

triton_shell:
	@DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh triton-shell

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
	@HYDRA_FULL_ERROR=1 TODOIST_AGENT_TRITON_MODEL_ID="$(TRITON_MODEL_ID)" \
	TODOIST_AGENT_TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TODOIST_AGENT_TRITON_URL="$(TRITON_URL)" \
	uv run python3 -m todoist.run_observer --config-dir configs --config-name automations

clear_local_env:
	@cache_dir="$${TODOIST_CACHE_DIR:-.cache/todoist-assistant}"; \
	data_dir="$${TODOIST_DATA_DIR:-.}"; \
	echo "Clearing cache dir: $$cache_dir"; \
	rm -rf "$$cache_dir"; \
	rm -rf .cache-migration-backup; \
	rm -rf "$$data_dir/cache" "$$data_dir/.cache-migration-backup"; \
	rm -f automation.log \
		activity.joblib \
		observer_state.joblib \
		integration_launches.joblib \
		automation_launches.joblib \
		processed_gmail_messages.joblib \
		dashboard_state.joblib \
		llm_breakdown_progress.joblib \
		llm_breakdown_queue.joblib \
		llm_chat_queue.joblib \
		llm_chat_conversations.joblib

update_and_run: # updates history, fetches activity, do templates, and runs the dashboard
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env.automation --config-dir configs --config-name automations && \
	make run_dashboard

test: ## Run unit tests with pytest
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run python3 -m pytest -v --tb=short tests/

coverage: ## Run full pytest coverage report
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run --with coverage python -m coverage run -m pytest tests/
	PYTHONPATH=. uv run --with coverage python -m coverage report

check_explicit_any: ## Reject `: Any =` variable annotations used as typecheck escape hatches
	PYTHONPATH=. uv run python3 -m scripts.check_explicit_any

typecheck: check_explicit_any ## Run pyright type checks
	PYTHONPATH=. uv run pyright --warnings

lint: ## Run pylint
	PYTHONPATH=. uv run pylint -j 0 todoist tests

validate: typecheck lint ## Run typecheck + lint

check: validate test ## Run validate + tests

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
