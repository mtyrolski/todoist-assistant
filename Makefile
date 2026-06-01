.PHONY: init_local_env ensure_frontend_deps reinstall reinstall_frontend update_env run_api run_frontend run_dashboard run_dashboard_cpu run_dashboard_gpu stop_dashboard status triton_shell download_models run_demo run_observer clear_local_env update_and_run test coverage pyright pylint ruff ruff_format pyright_all pylint_all ruff_all typecheck lint validate check_fast check test_all check_explicit_any chat_agent build_windows_installer build_macos_pkg build_macos_app build_macos_dmg docker_build docker_up docker_down docker_logs docker_pull docker_watch

FRONTEND_DIR := frontend
FRONTEND_NEXT := $(FRONTEND_DIR)/node_modules/.bin/next
PY_SOURCE_SCRIPTS := scripts/build_windows.py scripts/check_explicit_any.py scripts/check_llm_activity_prompt.py scripts/check_versions.py scripts/clear_local_env.py scripts/create_task_tree.py scripts/download_models.py scripts/get_version.py scripts/resolve_llm_backend.py scripts/run_make_checks.py scripts/status.py
PY_SOURCE_PATHS := todoist $(PY_SOURCE_SCRIPTS)
PY_CHECK_PATHS := todoist tests $(PY_SOURCE_SCRIPTS)
DASHBOARD_STATE_DIR := .cache/todoist-assistant/dashboard
DASHBOARD_PID_DIR := $(DASHBOARD_STATE_DIR)/pids
MODEL_ID ?=
TRITON_MODEL_NAME ?=
TRITON_URL ?=
BACKEND ?= raw
BACKEND_AI ?=

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
	@TODOIST_AGENT_MODEL_ID="$(MODEL_ID)" \
	TODOIST_AGENT_TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TODOIST_AGENT_TRITON_URL="$(TRITON_URL)" \
	uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000

run_frontend: ensure_frontend_deps
	npm --prefix $(FRONTEND_DIR) run dev -- --port 3000

run_dashboard: ensure_frontend_deps
	@backend="$(BACKEND)"; \
	if [ -n "$(BACKEND_AI)" ]; then backend="$(BACKEND_AI)"; fi; \
	case "$$backend" in \
		raw|none|disabled) stack_backend="raw" ;; \
		codex) stack_backend="codex" ;; \
		triton|triton_local) stack_backend="triton" ;; \
		*) echo "Unsupported dashboard backend: $$backend (use raw, codex, or triton)"; exit 2 ;; \
	esac; \
	MODEL_ID="$(MODEL_ID)" \
	TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TRITON_URL="$(TRITON_URL)" \
	DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh start "$$stack_backend" cpu

run_dashboard_cpu: ensure_frontend_deps
	@MODEL_ID="$(MODEL_ID)" \
	TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TRITON_URL="$(TRITON_URL)" \
	DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh start triton cpu

run_dashboard_gpu: ensure_frontend_deps
	@MODEL_ID="$(MODEL_ID)" \
	TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TRITON_URL="$(TRITON_URL)" \
	DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh start triton gpu

stop_dashboard:
	@DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh stop

status: ## Show local dashboard/API/frontend runtime status
	@python3 scripts/status.py

triton_shell:
	@DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh triton-shell

download_models: ## Download configured Hugging Face local/Triton models with progress
	PYTHONPATH=. uv run python3 -m scripts.download_models $(DOWNLOAD_MODELS_ARGS)

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
	@HYDRA_FULL_ERROR=1 TODOIST_AGENT_MODEL_ID="$(MODEL_ID)" \
	TODOIST_AGENT_TRITON_MODEL_NAME="$(TRITON_MODEL_NAME)" \
	TODOIST_AGENT_TRITON_URL="$(TRITON_URL)" \
	uv run python3 -m todoist.run_observer --config-dir configs --config-name automations

clear_local_env:
	@PYTHONPATH=. uv run python3 -m scripts.clear_local_env $(CLEAR_LOCAL_ENV_ARGS)

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

pyright: ## Run Pyright type checks
	PYTHONPATH=. uv run pyright --warnings $(PY_SOURCE_PATHS)

pylint: ## Run pylint
	PYTHONPATH=. uv run pylint -j 0 $(PY_SOURCE_PATHS)

ruff: ## Run Ruff lint checks
	PYTHONPATH=. uv run ruff check $(PY_SOURCE_PATHS)

ruff_format: ## Check Ruff formatting
	PYTHONPATH=. uv run ruff format --check $(PY_SOURCE_PATHS)

pyright_all: ## Run Pyright on source, tests, and scripts
	PYTHONPATH=. uv run pyright --warnings $(PY_CHECK_PATHS)

pylint_all: ## Run pylint on source, tests, and scripts
	PYTHONPATH=. uv run pylint -j 0 $(PY_CHECK_PATHS)

ruff_all: ## Run Ruff on source, tests, and scripts
	PYTHONPATH=. uv run ruff check $(PY_CHECK_PATHS)

typecheck: check_explicit_any pyright ## Run explicit-Any and Pyright checks

lint: pylint ruff ruff_format ## Run pylint and Ruff checks

check_fast: ## Run quick source-only checks with verbose progress
	+@PYTHONPATH=. uv run python3 -m scripts.run_make_checks \
		--title check_fast \
		check_explicit_any=explicit-any \
		ruff=ruff

check: ## Run all static quality checks in parallel with verbose progress
	+@PYTHONPATH=. uv run python3 -m scripts.run_make_checks \
		--title check \
		check_explicit_any=explicit-any \
		pyright=pyright \
		pylint=pylint \
		ruff=ruff

validate: check ## Alias for make check

test_all: ## Run static checks and tests in parallel with verbose progress
	+@PYTHONPATH=. uv run python3 -m scripts.run_make_checks \
		--title test_all \
		check_explicit_any=explicit-any \
		pyright_all=pyright-all \
		pylint_all=pylint-all \
		ruff_all=ruff-all \
		test=pytest

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
