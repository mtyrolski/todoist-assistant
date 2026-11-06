"""Public package exports for Telemetry for Todoist."""

from todometry.core.version import get_version

__version__ = get_version()

__all__ = ["__version__", "get_version"]
