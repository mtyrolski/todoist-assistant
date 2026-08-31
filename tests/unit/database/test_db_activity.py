import datetime as dt
import inspect
from datetime import datetime, timezone
from threading import Lock
from time import sleep
from unittest.mock import patch

from todoist.core.utils import set_tqdm_progress_callback
from tests.unit.database.helpers import event_payload, make_event

ProgressCall = tuple[
    str,
    int,
    int,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]


@patch("todoist.database.db_activity.logger")
def test_fetch_activity_adaptively_empty_windows(_mock_logger, db_activity):
    with patch.object(db_activity, "_fetch_activity_range") as mock_fetch_window:
        mock_fetch_window.side_effect = [[], []]

        result = db_activity.fetch_activity_adaptively(
            nweeks_window_size=1, early_stop_after_n_windows=2
        )

    assert result == []
    assert mock_fetch_window.call_count == 2


@patch("todoist.database.db_activity.logger")
def test_fetch_activity_adaptively_does_not_cap_pages_by_window_size(
    _mock_logger, db_activity
):
    with patch.object(db_activity, "_fetch_activity_range") as mock_fetch_window:
        mock_fetch_window.side_effect = [[], []]

        db_activity.fetch_activity_adaptively(
            nweeks_window_size=10,
            early_stop_after_n_windows=2,
        )

    first_call_kwargs = mock_fetch_window.call_args_list[0].kwargs
    assert first_call_kwargs["max_pages"] is None


@patch("todoist.database.db_activity.logger")
def test_fetch_activity_adaptively_with_events(_mock_logger, db_activity):
    event = make_event("event1")

    with patch.object(db_activity, "_fetch_activity_range") as mock_fetch_window:
        mock_fetch_window.side_effect = [[event], []]

        result = db_activity.fetch_activity_adaptively(
            nweeks_window_size=1, early_stop_after_n_windows=1
        )

    assert len(result) == 1
    assert result[0].id == "event1"
    assert mock_fetch_window.call_count == 2


@patch("todoist.database.db_activity.logger")
def test_fetch_activity_adaptively_checkpoints_each_completed_window(
    _mock_logger, db_activity
):
    first_event = make_event("event1")
    second_event = make_event("event2")
    checkpoints: list[set] = []

    with patch.object(db_activity, "_fetch_activity_range") as mock_fetch_window:
        mock_fetch_window.side_effect = [[first_event], [second_event], []]

        db_activity.fetch_activity_adaptively(
            nweeks_window_size=1,
            early_stop_after_n_windows=1,
            on_events=checkpoints.append,
        )

    assert checkpoints == [{first_event}, {second_event}]


@patch("todoist.database.db_activity.logger")
def test_fetch_activity_adaptively_passes_cached_events_to_range(
    _mock_logger, db_activity
):
    cached_event = make_event("cached1")

    with patch.object(
        db_activity, "_fetch_activity_range", return_value=[]
    ) as mock_fetch_window:
        db_activity.fetch_activity_adaptively(
            nweeks_window_size=1,
            early_stop_after_n_windows=1,
            events_already_fetched={cached_event},
        )

    first_call_kwargs = mock_fetch_window.call_args_list[0].kwargs
    assert first_call_kwargs["events_already_fetched"] == {cached_event}


@patch("todoist.database.db_activity.logger")
def test_fetch_activity_adaptively_reports_window_progress(_mock_logger, db_activity):
    progress_calls: list[tuple[str, int, int, str | None]] = []
    set_tqdm_progress_callback(
        lambda desc, current, total, unit: progress_calls.append(
            (desc, current, total, unit)
        )
    )
    try:
        with patch.object(db_activity, "_fetch_activity_range") as mock_fetch_window:
            mock_fetch_window.side_effect = [[], []]
            db_activity.fetch_activity_adaptively(
                nweeks_window_size=4,
                early_stop_after_n_windows=2,
                progress_desc="Backfilling activity history",
            )
    finally:
        set_tqdm_progress_callback(None)

    assert any(
        call == ("Backfilling activity history", 0, 2, "window")
        for call in progress_calls
    )
    assert any(
        desc == "Backfilling activity history" and current >= 1 and unit == "window"
        for desc, current, _total, unit in progress_calls
    )


@patch("todoist.database.db_activity.logger")
def test_fetch_activity_adaptively_reports_verbose_window_detail(
    _mock_logger, db_activity
):
    progress_calls: list[tuple[str, int, int, str | None, str | None]] = []

    def _capture(
        desc: str,
        current: int,
        total: int,
        unit: str | None,
        detail: str | None = None,
    ) -> None:
        progress_calls.append((desc, current, total, unit, detail))

    set_tqdm_progress_callback(_capture)
    try:
        with patch.object(db_activity, "_fetch_activity_range") as mock_fetch_window:
            mock_fetch_window.side_effect = [[], []]
            db_activity.fetch_activity_adaptively(
                nweeks_window_size=4,
                early_stop_after_n_windows=2,
                progress_desc="Backfilling activity history",
            )
    finally:
        set_tqdm_progress_callback(None)

    details = [detail or "" for *_rest, detail in progress_calls]
    assert any("scanning" in detail and "to" in detail for detail in details)
    assert any("workers=2" in detail for detail in details)
    assert any("empty windows=" in detail for detail in details)


@patch("todoist.database.db_activity.TodoistAPIClient.request_json")
def test_fetch_activity_range_reports_page_progress(mock_request_json, db_activity):
    mock_request_json.return_value = {"results": [], "next_cursor": None}
    progress_calls: list[tuple[str, int, int, str | None]] = []
    set_tqdm_progress_callback(
        lambda desc, current, total, unit: progress_calls.append(
            (desc, current, total, unit)
        )
    )
    try:
        getattr(db_activity, "_fetch_activity_range")(
            date_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2024, 1, 8, tzinfo=timezone.utc),
            progress_desc="Fetching activity history",
        )
    finally:
        set_tqdm_progress_callback(None)

    assert any(
        desc == "Fetching activity history" and unit == "page" and current >= 1
        for desc, current, _total, unit in progress_calls
    )


@patch("todoist.database.db_activity.TodoistAPIClient.request_json")
def test_fetch_activity_range_continues_past_cached_page_to_backfill_gaps(
    mock_request_json, db_activity
):
    cached_event = make_event(
        "event-cached",
        date=dt.datetime(2024, 1, 2, 12, 0, 0),
        event_date="2024-01-02T12:00:00Z",
        content="Task cached",
    )
    mock_request_json.side_effect = [
        {
            "results": [
                event_payload(
                    "event-new",
                    event_date="2024-01-03T12:00:00Z",
                    content="Task new",
                )
            ],
            "next_cursor": "cursor-1",
        },
        {
            "results": [
                event_payload(
                    "event-cached",
                    event_date="2024-01-02T12:00:00Z",
                    content="Task cached",
                )
            ],
            "next_cursor": "cursor-2",
        },
        {
            "results": [
                event_payload(
                    "event-older-missing",
                    event_date="2024-01-01T12:00:00Z",
                    content="Task older missing",
                )
            ],
            "next_cursor": None,
        },
    ]

    events = getattr(db_activity, "_fetch_activity_range")(
        date_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        date_to=datetime(2024, 1, 31, tzinfo=timezone.utc),
        events_already_fetched={cached_event},
    )

    assert [event.id for event in events] == ["event-new", "event-older-missing"]
    assert mock_request_json.call_count == 3


@patch("todoist.database.db_activity.TodoistAPIClient.request_json")
def test_fetch_activity_range_filters_by_parent_project_id(
    mock_request_json, db_activity
):
    mock_request_json.return_value = {"results": [], "next_cursor": None}

    getattr(db_activity, "_fetch_activity_range")(
        date_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        date_to=datetime(2024, 1, 31, tzinfo=timezone.utc),
        parent_project_id="archived-parent",
    )

    spec_arg = mock_request_json.call_args.args[0]
    assert spec_arg.params["parent_project_id"] == "archived-parent"


def test_fetch_activity_for_parent_projects_scans_each_parent_window(db_activity):
    event = make_event(
        "event-parent",
        event_date="2024-01-03T12:00:00Z",
        parent_project_id="parent-a",
        content="Task parent",
    )

    with patch.object(db_activity, "_fetch_activity_range") as mock_fetch_range:
        mock_fetch_range.side_effect = [[event], []]
        events = db_activity.fetch_activity_for_parent_projects(
            ["parent-a", "parent-b"],
            date_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2024, 1, 8, tzinfo=timezone.utc),
            window_weeks=1,
            events_already_fetched=set(),
        )

    assert events == [event]
    assert mock_fetch_range.call_count == 2
    assert {
        call.kwargs["parent_project_id"] for call in mock_fetch_range.call_args_list
    } == {"parent-a", "parent-b"}


def test_fetch_activity_for_parent_projects_stops_after_cached_empty_windows(
    db_activity,
):
    cached_event = make_event(
        "event-cached",
        date=dt.datetime(2023, 1, 3, 12, 0, 0),
        event_date="2023-01-03T12:00:00Z",
        parent_project_id="parent-a",
        content="Cached task",
    )

    with patch.object(db_activity, "_fetch_activity_range", return_value=[]) as fetch:
        events = db_activity.fetch_activity_for_parent_projects(
            ["parent-a"],
            date_from=datetime(2023, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2024, 1, 1, tzinfo=timezone.utc),
            window_weeks=4,
            events_already_fetched={cached_event},
            early_stop_after_n_windows=2,
        )

    assert events == []
    assert fetch.call_count == 2


def test_fetch_activity_for_parent_projects_runs_projects_in_parallel_and_reports_lanes(
    db_activity,
):
    access_lock = Lock()
    active_fetches = 0
    max_active_fetches = 0
    progress_calls: list[ProgressCall] = []

    def _fetch_range(**_kwargs):
        nonlocal active_fetches, max_active_fetches
        with access_lock:
            active_fetches += 1
            max_active_fetches = max(max_active_fetches, active_fetches)
        sleep(0.05)
        with access_lock:
            active_fetches -= 1
        return []

    def _capture_progress(
        desc: str,
        current: int,
        total: int,
        unit: str | None,
        detail: str | None = None,
        lane_id: str | None = None,
        lane_label: str | None = None,
        lane_status: str | None = None,
    ) -> None:
        progress_calls.append(
            (
                desc,
                current,
                total,
                unit,
                detail,
                lane_id,
                lane_label,
                lane_status,
            )
        )

    set_tqdm_progress_callback(_capture_progress)
    try:
        with (
            patch(
                "todoist.database.db_activity.get_max_concurrent_requests",
                return_value=2,
            ),
            patch.object(
                db_activity, "_fetch_activity_range", side_effect=_fetch_range
            ),
        ):
            db_activity.fetch_activity_for_parent_projects(
                ["parent-a", "parent-b"],
                date_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
                date_to=datetime(2024, 1, 8, tzinfo=timezone.utc),
                window_weeks=1,
                progress_lane_labels={
                    "parent-a": "Archived A",
                    "parent-b": "Archived B",
                },
            )
    finally:
        set_tqdm_progress_callback(None)

    lane_ids = {call[5] for call in progress_calls}
    queued_lane_ids = {call[5] for call in progress_calls if call[7] == "queued"}
    details = {call[4] for call in progress_calls}
    assert max_active_fetches == 2
    assert {"archived-project:parent-a", "archived-project:parent-b"} <= lane_ids
    assert queued_lane_ids == {
        "archived-project:parent-a",
        "archived-project:parent-b",
    }
    assert any(detail is not None and "workers=2" in detail for detail in details)


def test_fetch_activity_signature(db_activity):
    signature = inspect.signature(db_activity.fetch_activity)
    params = list(signature.parameters)

    assert "max_pages" in params
    assert "starting_page" in params
    assert signature.parameters["max_pages"].default == 4
    assert signature.parameters["starting_page"].default == 0
