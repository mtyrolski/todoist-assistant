from typing import TYPE_CHECKING

__all__ = ["AutomationObserver", "Cache"]

if TYPE_CHECKING:
    from .automation import AutomationObserver, Cache


def __getattr__(name: str):
    if name in __all__:
        from . import automation as _automation

        return getattr(_automation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
