from todoist.dashboard.subpages import home, projects, tasks, control_panel

render_home_page = home.render_home_page
render_project_insights_page = projects.render_project_insights_page
render_task_analysis_page = tasks.render_task_analysis_page
render_control_panel_page = control_panel.render_control_panel_page

___all__ = [
    'render_home_page',
    'render_project_insights_page',
    'render_task_analysis_page',
    'render_control_panel_page'
]