.PHONY: init_local_env run_dashboard clear_local_env

init_local_env: # syncs history, fetches activity
	uv run python3 -m todoist.automations.init_env --config-dir configs --config-name automations

run_dashboard:
	PYTHONPATH=. uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False

run_demo:
	PYTHONPATH=. uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False demo

clear_local_env:
	rm -f activity.joblib
