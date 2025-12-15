.PHONY: init_local_env install_app update_env run_api run_frontend run_dashboard run_dashboard_streamlit run_demo run_observer clear_local_env update_and_run test

init_local_env: # syncs history, fetches activity
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.init_env --config-dir configs --config-name automations

update_env: # updates history, fetches activity, do templates
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations

install_app: # installs frontend dependencies
	npm --prefix frontend install

run_api:
	uv run uvicorn todoist.web.api:app --reload --host 127.0.0.1 --port 8000

run_frontend:
	npm --prefix frontend run dev -- --port 3000

# New meaning: run the "pretty" web dashboard stack (API + frontend)
run_dashboard:
	@bash -lc '\
		set -euo pipefail; \
		pids=""; \
		cleanup() { \
			echo "Stopping dashboard servers..."; \
			[ -n "$$pids" ] && kill $$pids 2>/dev/null || true; \
			wait 2>/dev/null || true; \
		}; \
		trap cleanup INT TERM EXIT; \
		$(MAKE) run_api & pids="$$pids $$!"; \
		$(MAKE) run_frontend & pids="$$pids $$!"; \
		echo "Dashboard running:"; \
		echo "  API:      http://127.0.0.1:8000"; \
		echo "  Frontend: http://127.0.0.1:3000"; \
		wait; \
	'

# Preserve old Streamlit dashboard under a new target
run_dashboard_streamlit:
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False

run_demo:
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False demo

run_observer:
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.run_observer --config-dir configs --config-name automations

clear_local_env:
	rm -f activity.joblib

update_and_run: # updates history, fetches activity, do templates, and runs the dashboard
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations && \
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False

test: ## Run unit tests with pytest
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run pytest -v --tb=short tests/
