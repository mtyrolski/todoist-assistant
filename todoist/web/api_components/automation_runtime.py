"""Compatibility wrappers for automation runtime helpers exposed by web.api."""

from dataclasses import dataclass
from typing import Any

_COMPONENT_EXPORTS = (
    "_serialize_dt",
    "_run_automation_sync",
    "_run_all_automations_sync",
    "_load_automations",
    "_available_automation_keys",
    "_automation_ref",
    "_automation_requires_auth",
    "_default_enabled_automation_keys",
    "_configured_enabled_automation_keys",
    "_enabled_automation_keys",
    "_clear_gmail_auth_session",
    "_current_gmail_auth_session",
    "_write_gmail_token",
    "_allow_insecure_oauth_transport",
    "_start_gmail_manual_auth_session",
    "_gmail_automation_status",
    "_automation_metadata_for_key",
    "_load_automation_inventory",
    "_save_enabled_automations",
    "_set_automation_enabled",
    "_restart_dashboard_observer_if_managed",
    "_automation_run_signal_metadata",
    "_automation_launch_metadata",
    "_load_observer_state",
    "_serialize_observer_state",
    "_build_observer",
)
_PATH_ALIASES = {
    "_AUTOMATIONS_PATH": "AUTOMATIONS_PATH",
    "_DASHBOARD_CONFIG_PATH": "DASHBOARD_CONFIG_PATH",
}


@dataclass
class _PendingGmailAuthSession:
    state: str
    auth_url: str
    redirect_uri: str
    started_at: str
    completed: bool = False
    error: str | None = None


def _service_module():
    from todoist.web.services import admin_automations

    return admin_automations


def _sync_api_globals() -> None:
    from todoist.web import api as web_api

    service = _service_module()
    for name, value in vars(web_api).items():
        if getattr(value, "_component_wrapper_for", None) == name:
            continue
        target = _PATH_ALIASES.get(name, name)
        if hasattr(service, target):
            setattr(service, target, value)


def _service_call(name: str, *args: Any, **kwargs: Any) -> Any:
    _sync_api_globals()
    return getattr(_service_module(), name)(*args, **kwargs)


def _make_wrapper(name: str):
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return _service_call(name, *args, **kwargs)

    _wrapper.__name__ = name
    setattr(_wrapper, "_component_wrapper_for", name)
    return _wrapper


for _name in _COMPONENT_EXPORTS:
    globals()[_name] = _make_wrapper(_name)
