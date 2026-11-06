.PHONY: sync sync_history ensure_frontend_deps reinstall_frontend run_api run_frontend dashboard stop_dashboard status run_demo clear_local_env test coverage lint ci ci-python ci-frontend build_windows_installer build_macos_pkg build_macos_app build_macos_dmg

FRONTEND_DIR := frontend
FRONTEND_NEXT := $(FRONTEND_DIR)/node_modules/.bin/next
DASHBOARD_STATE_DIR := .cache/todoist-assistant/dashboard
DASHBOARD_PID_DIR := $(DASHBOARD_STATE_DIR)/pids

sync: ## Refresh recent Todoist activity
	uv run python3 -m todoist.sync

sync_history: ## Fetch recent and older Todoist activity
	uv run python3 -m todoist.sync --history

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

run_api:
	@uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000

run_frontend: ensure_frontend_deps
	npm --prefix $(FRONTEND_DIR) run dev -- --port 3000

dashboard: ensure_frontend_deps ## Start API and frontend
	@DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh start

stop_dashboard:
	@DASHBOARD_STATE_DIR="$(DASHBOARD_STATE_DIR)" \
	DASHBOARD_PID_DIR="$(DASHBOARD_PID_DIR)" \
	bash ./scripts/dashboard_stack.sh stop

status: ## Show local dashboard/API/frontend runtime status
	@PYTHONPATH=. uv run python3 -m scripts.status

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

clear_local_env:
	@PYTHONPATH=. uv run python3 -m scripts.clear_local_env $(CLEAR_LOCAL_ENV_ARGS)

test: ## Run unit tests with pytest
	PYTHONPATH=. API_KEY=dummy_ci_key uv run python3 -m pytest -q tests/

coverage: ## Run full pytest coverage report
	PYTHONPATH=. uv run --with coverage python -m coverage run -m pytest tests/
	PYTHONPATH=. uv run --with coverage python -m coverage report

lint: ## Check Python imports and undefined names
	PYTHONPATH=. uv run ruff check --select F todoist tests scripts

ci-python: lint test ## Run Python CI checks
	uv run python3 -m scripts.check_architecture
	uv run python3 -m scripts.check_versions

ci-frontend: ## Run frontend CI checks (requires installed dependencies and Playwright Chromium)
	npm --prefix $(FRONTEND_DIR) run lint
	npm --prefix $(FRONTEND_DIR) test
	npm --prefix $(FRONTEND_DIR) run build
	npm --prefix $(FRONTEND_DIR) run test:e2e

ci: ci-python ci-frontend ## Run the Python and frontend CI checks

build_windows_installer: ## Build Windows MSI (requires Windows + WiX + Node if dashboard is included)
	uv run python3 -m scripts.build_windows

build_macos_pkg: ## Build macOS pkg installer (requires macOS + pkgbuild/productbuild)
	./scripts/build_macos_pkg.sh

build_macos_app: ## Build macOS app bundle (requires macOS + PyInstaller)
	./scripts/build_macos_app.sh

build_macos_dmg: ## Build macOS DMG from the app bundle
	./scripts/build_macos_dmg.sh

.PHONY: build_android build_android_preview build_android_bundle
build_android: ## Build an installable Android APK and run Android tests/lint
	bash scripts/build_android.sh

build_android_preview: ## Build a signed, optimized APK alongside the debug app
	bash scripts/build_android.sh preview

build_android_bundle: ## Build an optimized Android App Bundle for Google Play
	bash scripts/build_android.sh bundle
