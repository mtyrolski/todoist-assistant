from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import todoist.cli as cli


runner = CliRunner()


def test_enable_telemetry_shows_missing_endpoint_note(monkeypatch, tmp_path: Path, capsys) -> None:
    calls: list[tuple[Path, bool]] = []

    monkeypatch.setattr(cli.telemetry, "resolve_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        cli.telemetry,
        "set_enabled",
        lambda config_dir, enabled: calls.append((config_dir, enabled)),
    )
    monkeypatch.delenv(str(cli.EnvVar.TELEMETRY_ENDPOINT), raising=False)

    with pytest.raises(typer.Exit) as exc_info:
        cli.main(enable_telemetry=True, disable_telemetry=False, version=False)

    captured = capsys.readouterr()

    assert exc_info.value.exit_code == 0
    assert "Telemetry enabled." in captured.out
    assert "no telemetry will be sent" in captured.out
    assert calls == [(tmp_path, True)]


def test_version_check_reports_update(monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_version", lambda: "0.2.0")
    monkeypatch.setattr(cli, "_fetch_latest_release", lambda: {"tag_name": "v0.3.1"})

    result = runner.invoke(cli.app, ["version", "--check"])

    assert result.exit_code == 0
    assert "0.2.0" in result.stdout
    assert "Update available: 0.3.1" in result.stdout
