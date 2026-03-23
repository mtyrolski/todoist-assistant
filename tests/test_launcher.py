# pylint: disable=protected-access

from unittest.mock import Mock

from todoist import launcher


def test_maybe_start_dashboard_observer_skips_without_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    start_observer = Mock()
    monkeypatch.setattr(launcher, "_start_dashboard_observer", start_observer)

    result = launcher._maybe_start_dashboard_observer()

    assert result is None
    start_observer.assert_not_called()
    captured = capsys.readouterr()
    assert "Dashboard observer disabled until a Todoist API token is configured." in captured.out


def test_maybe_start_dashboard_observer_skips_placeholder_api_key(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "PUT YOUR API HERE")
    start_observer = Mock()
    monkeypatch.setattr(launcher, "_start_dashboard_observer", start_observer)

    result = launcher._maybe_start_dashboard_observer()

    assert result is None
    start_observer.assert_not_called()


def test_maybe_start_dashboard_observer_starts_with_real_api_key(monkeypatch) -> None:
    sentinel_thread = object()
    monkeypatch.setenv("API_KEY", "real_api_key_value_12345")
    monkeypatch.setattr(launcher, "_start_dashboard_observer", lambda: sentinel_thread)

    result = launcher._maybe_start_dashboard_observer()

    assert result is sentinel_thread
