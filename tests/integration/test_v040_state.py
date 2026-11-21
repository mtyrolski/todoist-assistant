"""Exercise representative state written with the v0.4.0 code."""

from pathlib import Path
import shutil

from todometry.core.env import EnvVar
from todometry.core.utils import CACHE_STORAGE_REGISTRY, Cache
from todometry.dashboard.settings import load_dashboard_config
from todometry.database.dataframe import load_adjustments_file
from todometry.features.activity import load_activity_cache
import todometry.web.api as web_api


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "v040"


def test_v040_local_state_is_readable_and_ignored_state_is_untouched(
    tmp_path, monkeypatch
):
    cache_dir = tmp_path / ".cache" / "todoist-assistant"
    cache_dir.mkdir(parents=True)
    for filename in ("activity.joblib", "dashboard_state.joblib"):
        shutil.copyfile(FIXTURE / filename, cache_dir / filename)
    for filename in ("observer_state.joblib", "multiplication_label_usage.joblib"):
        (cache_dir / filename).write_bytes(b"unused legacy state")
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(cache_dir))
    monkeypatch.setenv(str(EnvVar.CONFIG_DIR), str(FIXTURE))
    monkeypatch.setenv(str(EnvVar.PERSONAL_DIR), str(FIXTURE))
    original = {p.name: p.read_bytes() for p in cache_dir.glob("*.joblib")}

    for _ in range(2):
        events = load_activity_cache()
        assert {event.id for event in events} == {"event-v040"}
        assert next(iter(events)).name == "fixture completion"
        assert load_adjustments_file(FIXTURE / "archived_root_projects.py") == (
            {"Legacy project": "Work"},
            [],
        )
        assert load_dashboard_config().urgency.enabled is True
        snapshot = Cache().dashboard_state.load()
        assert snapshot["version"] == 3
        assert snapshot["archived_projects"][0].project_entry.name == "Legacy project"
        # A v0.4.0 dashboard snapshot is a rebuildable cache, not the source of history.
        assert web_api._load_state_from_disk_cache(demo_mode=False) is False
        assert "observer_state" not in CACHE_STORAGE_REGISTRY
        assert "multiplication_label_usage" not in CACHE_STORAGE_REGISTRY
        assert {p.name: p.read_bytes() for p in cache_dir.glob("*.joblib")} == original


def _write_incompatible_cache(path, monkeypatch):
    import sys
    import types

    from joblib import dump

    module_name = "unavailable_v040_cache_type"
    module = types.ModuleType(module_name)
    exec("class Record: pass", module.__dict__)
    monkeypatch.setitem(sys.modules, module_name, module)
    dump({"record": module.Record()}, path)
    monkeypatch.delitem(sys.modules, module_name)
    return path.read_bytes()


def test_incompatible_activity_is_not_presented_as_empty(tmp_path, monkeypatch):
    import pytest
    from todometry.core.utils import IncompatibleCacheError
    from todometry.database.dataframe import load_activity_data

    path = tmp_path / "activity.joblib"
    original = _write_incompatible_cache(path, monkeypatch)
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    with pytest.raises(IncompatibleCacheError):
        load_activity_data(None)
    assert path.read_bytes() == original


def test_incompatible_dashboard_snapshot_is_not_discarded(tmp_path, monkeypatch):
    import pytest
    from todometry.core.utils import IncompatibleCacheError

    path = tmp_path / "dashboard_state.joblib"
    original = _write_incompatible_cache(path, monkeypatch)
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    with pytest.raises(IncompatibleCacheError):
        web_api._load_state_from_disk_cache(demo_mode=False)
    assert path.read_bytes() == original


def test_incompatible_dashboard_snapshot_is_not_overwritten_by_refresh(
    tmp_path, monkeypatch
):
    import pandas as pd

    path = tmp_path / "dashboard_state.joblib"
    original = _write_incompatible_cache(path, monkeypatch)
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setenv(str(EnvVar.PERSONAL_DIR), str(tmp_path / "personal"))
    state = web_api._DashboardState()
    state.df_activity = pd.DataFrame()
    state.active_projects = []
    state.archived_projects = []
    state.project_colors = {}
    monkeypatch.setattr(web_api, "_state", state)

    web_api._persist_state_to_disk_cache(demo_mode=False)
    assert path.read_bytes() == original


def test_incompatible_archived_scan_cache_is_not_overwritten(tmp_path, monkeypatch):
    import pytest
    from todometry.core.utils import IncompatibleCacheError

    path = tmp_path / "archived_activity_scans.joblib"
    original = _write_incompatible_cache(path, monkeypatch)
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    with pytest.raises(IncompatibleCacheError):
        web_api._call_dashboard_runtime(
            "_save_archived_activity_scan_fingerprints", {}, {}, set()
        )
    assert path.read_bytes() == original


def test_refresh_does_not_hide_incompatible_activity_data(tmp_path, monkeypatch):
    import pytest
    from todometry.core.utils import IncompatibleCacheError

    class FakeDatabase:
        def __init__(self, _path):
            pass

        def fetch_projects_incrementally(self, _previous, _changed):
            return []

        def fetch_archived_projects(self):
            return []

    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setenv(str(EnvVar.PERSONAL_DIR), str(tmp_path / "personal"))
    monkeypatch.setattr(web_api, "_state", web_api._DashboardState())
    monkeypatch.setattr(web_api, "Database", FakeDatabase)
    monkeypatch.setattr(web_api, "_resolve_api_key", lambda: "")
    monkeypatch.setattr(web_api, "_run_async_in_main_loop", lambda coro: coro.close())

    def incompatible(_db):
        raise IncompatibleCacheError("cannot decode old activity")

    monkeypatch.setattr(web_api, "load_activity_data", incompatible)
    with pytest.raises(IncompatibleCacheError, match="cannot decode old activity"):
        web_api._call_dashboard_runtime("_refresh_state_sync", demo_mode=False)


def test_v040_activity_rebuilds_history_with_legacy_project_mapping(
    tmp_path, monkeypatch
):
    from todometry.database.dataframe import load_activity_data

    for filename in ("activity.joblib", "dashboard_state.joblib"):
        shutil.copyfile(FIXTURE / filename, tmp_path / filename)
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setenv(str(EnvVar.PERSONAL_DIR), str(FIXTURE))
    project = Cache().dashboard_state.load()["archived_projects"][0]

    class FixtureDatabase:
        def fetch_mapping_project_id_to_root(self):
            return {project.id: project}

        def fetch_mapping_project_id_to_name(self):
            return {project.id: project.project_entry.name}

        def fetch_projects(self, include_tasks=False):
            return []

        def fetch_archived_projects(self):
            return [project]

    frame = load_activity_data(FixtureDatabase())
    assert list(frame["title"]) == ["fixture completion"]
    assert list(frame["parent_project_name"]) == ["Legacy project"]
    assert list(frame["root_project_name"]) == ["Work"]


def test_migration_preserves_retained_files_and_existing_destinations(tmp_path):
    from todometry.core.utils import migrate_legacy_files

    legacy, target = tmp_path / "old", tmp_path / "new"
    (legacy / "cache").mkdir(parents=True)
    (legacy / "config").mkdir()
    (legacy / "personal").mkdir()
    shutil.copyfile(FIXTURE / "activity.joblib", legacy / "cache/activity.joblib")
    (legacy / "cache/observer_state.joblib").write_bytes(b"unused")
    (legacy / "config/dashboard.yaml").write_text("legacy settings", encoding="utf-8")
    (legacy / "personal/mapping.py").write_text("legacy mapping", encoding="utf-8")
    (target / "config").mkdir(parents=True)
    (target / "config/dashboard.yaml").write_text("new settings", encoding="utf-8")
    entries = ("cache/activity.joblib", "config", "personal")

    migrate_legacy_files(legacy, target, entries)
    assert {event.id for event in Cache(str(target / "cache")).activity.load()} == {
        "event-v040"
    }
    assert (target / "config/dashboard.yaml").read_text() == "new settings"
    assert (target / "personal/mapping.py").read_text() == "legacy mapping"
    assert not (target / "cache/observer_state.joblib").exists()
    assert (legacy / "cache/activity.joblib").read_bytes() == (
        target / "cache/activity.joblib"
    ).read_bytes()

    (legacy / "personal/mapping.py").write_text("later", encoding="utf-8")
    migrate_legacy_files(legacy, target, entries)
    assert (target / "personal/mapping.py").read_text() == "legacy mapping"


def test_interrupted_migration_resumes_without_overwriting(tmp_path, monkeypatch):
    import os
    import pytest

    from todometry.core.utils import migrate_legacy_files

    legacy, target = tmp_path / "old", tmp_path / "new"
    legacy.mkdir()
    (legacy / "a").write_text("first", encoding="utf-8")
    (legacy / "b").write_text("second", encoding="utf-8")
    link = os.link

    def interrupt(source, destination):
        if Path(destination).name == "b":
            raise OSError("interrupted")
        return link(source, destination)

    monkeypatch.setattr(os, "link", interrupt)
    with pytest.raises(OSError, match="interrupted"):
        migrate_legacy_files(legacy, target, ("a", "b"))
    assert not (target / ".v040-migration-complete").exists()
    (target / "a").write_text("edited", encoding="utf-8")
    monkeypatch.setattr(os, "link", link)
    migrate_legacy_files(legacy, target, ("a", "b"))
    assert (target / "a").read_text() == "edited"
    assert (target / "b").read_text() == "second"


def test_launcher_discovers_legacy_default_state(tmp_path, monkeypatch):
    import sys

    from todometry.launcher import _default_data_dir

    monkeypatch.delenv(str(EnvVar.DATA_DIR), raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    old = tmp_path / ".local/share/todoist-assistant"
    (old / "cache").mkdir(parents=True)
    (old / "config").mkdir()
    (old / "personal").mkdir()
    shutil.copyfile(FIXTURE / "activity.joblib", old / "cache/activity.joblib")
    shutil.copyfile(FIXTURE / "dashboard.yaml", old / "config/dashboard.yaml")
    shutil.copyfile(
        FIXTURE / "archived_root_projects.py",
        old / "personal/archived_root_projects.py",
    )
    (old / ".env").write_text("API_KEY=legacy\n", encoding="utf-8")
    new = _default_data_dir()
    assert new == tmp_path / ".local/share/todometry"
    assert {event.id for event in Cache(str(new / "cache")).activity.load()} == {
        "event-v040"
    }
    assert load_adjustments_file(new / "personal/archived_root_projects.py")[0] == {
        "Legacy project": "Work"
    }
    assert (new / "config/dashboard.yaml").read_bytes() == (
        old / "config/dashboard.yaml"
    ).read_bytes()
    assert (new / ".env").read_text() == "API_KEY=legacy\n"
    assert _default_data_dir() == new


def test_clean_default_cache_and_explicit_override(tmp_path, monkeypatch):
    from todometry.core.utils import resolve_cache_dir

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(str(EnvVar.CACHE_DIR), raising=False)
    assert Path(resolve_cache_dir()) == tmp_path / ".cache/todometry"
    assert not (tmp_path / ".cache/todoist-assistant").exists()
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path / "custom"))
    assert Path(resolve_cache_dir()) == tmp_path / "custom"


def test_source_checkout_discovers_v040_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(str(EnvVar.CACHE_DIR), raising=False)
    legacy = tmp_path / ".cache/todoist-assistant"
    legacy.mkdir(parents=True)
    shutil.copyfile(FIXTURE / "activity.joblib", legacy / "activity.joblib")

    cache = Cache()
    assert Path(cache.path) == tmp_path / ".cache/todometry"
    assert {event.id for event in cache.activity.load()} == {"event-v040"}
    assert (legacy / "activity.joblib").read_bytes() == (
        Path(cache.path) / "activity.joblib"
    ).read_bytes()
