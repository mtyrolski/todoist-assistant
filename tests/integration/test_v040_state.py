"""Exercise representative state written with the v0.4.0 code."""

from pathlib import Path
import shutil

from todoist.core.env import EnvVar
from todoist.core.utils import CACHE_STORAGE_REGISTRY, Cache
from todoist.dashboard.settings import load_dashboard_config
from todoist.database.dataframe import load_adjustments_file
from todoist.features.activity import load_activity_cache
import todoist.web.api as web_api


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "v040"


def test_v040_local_state_is_readable_and_ignored_state_is_untouched(
    tmp_path, monkeypatch
):
    cache_dir = tmp_path / ".cache" / "todoist-assistant"
    cache_dir.mkdir(parents=True)
    for filename in (
        "activity.joblib",
        "dashboard_state.joblib",
        "observer_state.joblib",
        "multiplication_label_usage.joblib",
    ):
        shutil.copyfile(FIXTURE / filename, cache_dir / filename)
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
    from todoist.core.utils import IncompatibleCacheError
    from todoist.database.dataframe import load_activity_data

    path = tmp_path / "activity.joblib"
    original = _write_incompatible_cache(path, monkeypatch)
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    with pytest.raises(IncompatibleCacheError):
        load_activity_data(None)
    assert path.read_bytes() == original


def test_incompatible_dashboard_snapshot_is_not_discarded(tmp_path, monkeypatch):
    import pytest
    from todoist.core.utils import IncompatibleCacheError

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
    from todoist.core.utils import IncompatibleCacheError

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
    from todoist.core.utils import IncompatibleCacheError

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
