from pathlib import Path

from todometry.dashboard.settings import resolve_dashboard_config_path


def test_dashboard_config_defaults_to_repository_configs(monkeypatch):
    monkeypatch.delenv("TODOIST_CONFIG_DIR", raising=False)
    monkeypatch.delenv("TODOIST_DATA_DIR", raising=False)
    path = resolve_dashboard_config_path()
    assert path == Path(__file__).resolve().parents[3] / "configs" / "dashboard.yaml"
    assert path.is_file()


def test_dashboard_config_uses_persistent_data_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("TODOIST_CONFIG_DIR", raising=False)
    monkeypatch.setenv("TODOIST_DATA_DIR", str(tmp_path))
    assert resolve_dashboard_config_path() == tmp_path / "configs" / "dashboard.yaml"
    monkeypatch.setenv("TODOIST_CONFIG_DIR", str(tmp_path / "override"))
    assert resolve_dashboard_config_path() == tmp_path / "override" / "dashboard.yaml"
