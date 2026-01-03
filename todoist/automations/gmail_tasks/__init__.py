__all__ = [
    "Credentials",
    "GmailTasksAutomation",
    "GMAIL_CREDENTIALS_FILE",
    "GMAIL_TOKEN_FILE",
    "build",
]


def __getattr__(name: str):
    if name in __all__:
        from . import automation as _automation

        return getattr(_automation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
