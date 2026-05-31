import json
from pathlib import Path

from todoist import telemetry


def test_bootstrap_config_defaults_to_disabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(telemetry, "_read_windows_registry_opt_in", lambda: None)

    enabled = telemetry.bootstrap_config(tmp_path)
    config = json.loads((tmp_path / telemetry.CONFIG_FILENAME).read_text(encoding="utf-8"))

    assert enabled is False
    assert config == {"enabled": False}


def test_send_event_skips_when_endpoint_missing(monkeypatch, tmp_path: Path) -> None:
    telemetry.set_enabled(tmp_path, True)
    monkeypatch.delenv(str(telemetry.EnvVar.TELEMETRY_ENDPOINT), raising=False)

    sent = telemetry.send_event("install_success", config_dir=tmp_path, _data_dir=tmp_path)

    assert sent is False


def test_maybe_send_install_success_writes_sentinel(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setattr(telemetry, "send_event", lambda *args, **kwargs: True)

    telemetry.maybe_send_install_success(config_dir, data_dir)

    sentinel = data_dir / telemetry.SENTINEL_FILENAME
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == "sent\n"
