"""Shared helpers for split FastAPI route modules."""

# pylint: disable=protected-access,cyclic-import


def _web_api():
    from todoist.web import api as web_api

    return web_api


def _sync_api_globals(target_globals: dict[str, object]):
    web_api = _web_api()
    target_globals.update(
        (name, value)
        for name, value in vars(web_api).items()
        if not name.startswith("__")
    )
    return web_api
