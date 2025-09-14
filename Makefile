.PHONY: init_local_env run_dashboard clear_local_env test format-check lint format lint-fix ci-check

init_local_env: # syncs history, fetches activity
	uv run python3 -m todoist.automations.init_env --config-dir configs --config-name automations

update_env: # updates history, fetches activity, do templates
	uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations

run_dashboard:
	PYTHONPATH=. uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False

run_demo:
	PYTHONPATH=. uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False demo

clear_local_env:
	rm -f activity.joblib

update_and_run: # updates history, fetches activity, do templates, and runs the dashboard
	uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations && \
	PYTHONPATH=. uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False

# Development and CI targets
test: # run tests with pytest
	uv run python3 -m pytest tests/ -v

format-check: # check code formatting with yapf
	uv run yapf --diff --recursive todoist/ tests/

lint: # check code with ruff linter
	uv run ruff check todoist/ tests/

format: # auto-fix formatting with yapf
	uv run yapf --in-place --recursive todoist/ tests/

lint-fix: # auto-fix linting issues with ruff
	uv run ruff check --fix todoist/ tests/

ci-check: test format-check lint # run all CI checks locally
