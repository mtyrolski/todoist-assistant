"""Tests for the local runtime cleanup helper."""

from pathlib import Path

from scripts.clear_local_env import clear_local_env, main
from todoist.core.env import EnvVar
from todoist.core.utils import RUNTIME_MIGRATABLE_FILENAMES


def _write_runtime_files(root: Path) -> None:
    for filename in RUNTIME_MIGRATABLE_FILENAMES:
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("payload", encoding="utf-8")


def test_clear_local_env_removes_source_of_truth_runtime_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / ".cache" / "todoist-assistant"
    monkeypatch.setenv(str(EnvVar.DATA_DIR), str(data_dir))
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(cache_dir))

    _write_runtime_files(tmp_path)
    _write_runtime_files(data_dir)
    (tmp_path / ".cache-migration-backup").mkdir(parents=True, exist_ok=True)
    (data_dir / ".cache-migration-backup").mkdir(parents=True, exist_ok=True)
    (cache_dir / "nested").mkdir(parents=True, exist_ok=True)
    (cache_dir / "nested" / "cache.txt").write_text("cache", encoding="utf-8")
    (cache_dir / "activity.joblib").write_text("activity", encoding="utf-8")
    (cache_dir / "automation_run_signals.joblib").write_text(
        "signals", encoding="utf-8"
    )
    (data_dir / "cache" / "nested").mkdir(parents=True, exist_ok=True)
    (data_dir / "cache" / "nested" / "cache.txt").write_text("cache", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")

    clear_local_env()

    for filename in RUNTIME_MIGRATABLE_FILENAMES:
        assert not (tmp_path / filename).exists()
        assert not (data_dir / filename).exists()
    assert not cache_dir.exists()
    assert not (data_dir / "cache").exists()
    assert not (tmp_path / ".cache-migration-backup").exists()
    assert not (data_dir / ".cache-migration-backup").exists()
    assert (tmp_path / "keep.txt").exists()


def test_clear_local_env_verbose_prints_removed_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cache_dir = tmp_path / ".cache" / "todoist-assistant"
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(cache_dir))
    (cache_dir / "activity.joblib").parent.mkdir(parents=True, exist_ok=True)
    (cache_dir / "activity.joblib").write_text("activity", encoding="utf-8")

    assert main(["--verbose"]) == 0

    output = capsys.readouterr().out
    assert "Removed:" in output
    assert str(cache_dir) in output
    assert not cache_dir.exists()
