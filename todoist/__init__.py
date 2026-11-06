"""Public package exports for Telemetry for Todoist."""

from todoist.core.version import get_version

__version__ = get_version()

__all__ = ["__version__", "get_version"]
