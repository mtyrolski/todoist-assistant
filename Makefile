.PHONY: init_local_env run_dashboard

init_local_env: # syncs history, fetches activity
	poetry run python3 -m todoist.automations.init_env --config-dir configs --config-name automations

run_dashboard:
	PYTHONPATH=. poetry run streamlit run todoist/dashboard/app.py

clear_local_env:
	rm -f activity.joblib
