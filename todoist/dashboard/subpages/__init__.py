from todoist.dashboard.subpages import home, projects, tasks, control_panel, log_viewer, overview

render_home_page = home.render_home_page
render_overview_page = overview.render_overview_page
render_project_insights_page = projects.render_project_insights_page
render_task_analysis_page = tasks.render_task_analysis_page
render_control_panel_page = control_panel.render_control_panel_page
render_log_viewer_page = log_viewer.render_log_viewer_page

___all__ = [
    'render_home_page', 'render_overview_page', 'render_project_insights_page', 'render_task_analysis_page', 'render_control_panel_page', 'render_log_viewer_page'
]
