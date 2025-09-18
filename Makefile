.PHONY: init_local_env run_dashboard run_chainlit clear_local_env

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

run_chainlit: # runs the new Chainlit chat interface
	cd todoist/chainlit_app && PYTHONPATH=../.. chainlit run app.py

update_and_run: # updates history, fetches activity, do templates, and runs the dashboard
	uv run python3 -m todoist.automations.update_env --config-dir configs --config-name automations && \
	PYTHONPATH=. uv run streamlit run todoist/dashboard/app.py --client.showErrorDetails=False
