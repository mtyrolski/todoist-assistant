"""Activity sync keeps its cache across repeated and interrupted fetches."""

import pytest

from tests.unit.database.helpers import make_event
from todoist.core.utils import Cache
from todoist.features.activity import load_activity_cache
from todoist.features.data_sync import backfill_activity_history, sync_recent_activity


def test_recent_sync_merges_and_deduplicates(monkeypatch, tmp_path):
    monkeypatch.setenv("TODOIST_CACHE_DIR", str(tmp_path))
    previous = make_event("previous")
    added = make_event("added")
    Cache().activity.save({previous})

    class FakeDatabase:
        def fetch_activity_incremental(self, existing, *, overlap_days):
            assert existing == {previous}
            assert overlap_days == 1
            return [previous, added]

    result = sync_recent_activity(FakeDatabase())

    assert result.new_events == {added}
    assert result.events == {previous, added}
    assert load_activity_cache() == result.events


def test_history_checkpoint_survives_interrupted_scan(monkeypatch, tmp_path):
    monkeypatch.setenv("TODOIST_CACHE_DIR", str(tmp_path))
    checkpoint = make_event("checkpoint")

    class InterruptedDatabase:
        def fetch_activity_history(self, **kwargs):
            kwargs["on_events"]({checkpoint})
            raise RuntimeError("network interrupted")

    with pytest.raises(RuntimeError, match="network interrupted"):
        backfill_activity_history(InterruptedDatabase())

    assert load_activity_cache() == {checkpoint}
