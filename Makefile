.PHONY: init_local_env run_dashboard clear_local_env test

init_local_env: # syncs history, fetches activity
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.init_env --config-dir configs --config-name automations

update_env: # updates history, fetches activity, do templates
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations

run_dashboard:
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False

run_demo:
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False demo

clear_local_env:
	rm -f activity.joblib

update_and_run: # updates history, fetches activity, do templates, and runs the dashboard
	HYDRA_FULL_ERROR=1 uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations && \
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False

test: ## Run unit tests with pytest
	PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run pytest -v --tb=short tests/
