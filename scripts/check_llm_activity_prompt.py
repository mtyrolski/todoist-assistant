#!/usr/bin/env python3
"""Quick verification for LLM activity prompt + 2025 completion count."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types

from todoist.agent.constants import TOOL_PROMPT
from todoist.core.constants import EventType  # noqa: E402

try:  # noqa: E402
    from joblib import load as _joblib_load  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional
    _joblib_load = None


def _check_prompt(prompt: str) -> list[str]:
    required = [
        "Activity data",
        "events (tuple[Event])",
        "events_df",
        "event_entry",
        "object_type",
        "object_id",
        "parent_project_id",
        "parent_item_id",
        "extra_data",
    ]
    return [item for item in required if item not in prompt]


def _load_activity(cache_root: Path) -> set:
    cache_path = cache_root / "activity.joblib"
    if not cache_path.exists():
        raise FileNotFoundError(f"activity.joblib missing at {cache_path}")
    _ensure_stub_dependencies()
    if _joblib_load is not None:
        activity = _joblib_load(cache_path)
    else:
        import pickle

        with cache_path.open("rb") as handle:
            activity = pickle.load(handle)
    if not isinstance(activity, set):
        raise TypeError("activity cache is not a set")
    return activity


def _to_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _count_completed(events: set, year: int) -> tuple[int, int]:
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)
    completed = []
    unique_object_ids: set[str] = set()
    for event in events:
        try:
            when = _to_naive(event.date)
        except Exception:
            continue
        if when < start or when >= end:
            continue
        if event.event_type != EventType.COMPLETED.value:
            continue
        completed.append(event)
        obj_id = getattr(event.event_entry, "object_id", None)
        if obj_id is not None:
            unique_object_ids.add(str(obj_id))
    return len(completed), len(unique_object_ids)


def _filter_completed(events: set, start: datetime, end: datetime) -> list:
    completed = []
    for event in events:
        try:
            when = _to_naive(event.date)
        except Exception:
            continue
        if when < start or when >= end:
            continue
        if event.event_type != EventType.COMPLETED.value:
            continue
        completed.append(event)
    return completed


def _unique_task_ids(events: list) -> set[str]:
    unique_object_ids: set[str] = set()
    for event in events:
        obj_id = getattr(event.event_entry, "object_id", None)
        if obj_id is not None:
            unique_object_ids.add(str(obj_id))
    return unique_object_ids


def _completed_by_object_type(events: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        obj_type = getattr(event.event_entry, "object_type", None)
        key = str(obj_type) if obj_type is not None else "(unknown)"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _print_run_header(idx: int, title: str) -> None:
    print(f"\n== RUN {idx}: {title} ==")


def _print_code(code: str) -> None:
    print("code:")
    for line in code.strip().splitlines():
        print(f"  {line}")


def _check(label: str, condition: bool, detail: str | None = None) -> tuple[str, bool]:
    status = "OK" if condition else "FAILED"
    msg = f"{label}: {status}"
    if detail:
        msg += f" ({detail})"
    print(f"check: {msg}")
    return msg, condition


def _ensure_stub_dependencies() -> None:
    if "loguru" not in sys.modules:
        if importlib.util.find_spec("loguru") is None:

            class _StubLogger:
                def __getattr__(self, name: str):
                    def _noop(*_args, **_kwargs):
                        return None

                    return _noop

            stub = types.ModuleType("loguru")
            setattr(stub, "logger", _StubLogger())
            sys.modules["loguru"] = stub
    if "pandas" not in sys.modules:
        if importlib.util.find_spec("pandas") is None:

            class _StubDataFrame:  # minimal placeholder
                pass

            stub = types.ModuleType("pandas")
            setattr(stub, "DataFrame", _StubDataFrame)
            sys.modules["pandas"] = stub


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check LLM prompt + activity completion counts."
    )
    parser.add_argument(
        "--cache-path",
        default=str((Path.cwd() / ".cache" / "todoist-assistant").resolve()),
        help="Cache root containing activity.joblib (default: ./.cache/todoist-assistant)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Year to count completed tasks (default: 2025)",
    )
    args = parser.parse_args()

    cache_root = Path(args.cache_path).resolve()

    print("== LLM TOOL PROMPT ==")
    prompt = TOOL_PROMPT
    print(prompt)
    missing = _check_prompt(prompt)
    if missing:
        print(f"FAILED: prompt missing fields: {', '.join(missing)}")
    else:
        print("OK: prompt includes activity data structure.")

    print("\n== ACTIVITY COUNT ==")
    try:
        events = _load_activity(cache_root)
    except Exception as exc:
        print(f"FAILED: unable to load activity cache ({type(exc).__name__}: {exc})")
        return 1

    total_events = len(events)
    print(f"Loaded events: {total_events}")

    summary: list[dict[str, object]] = []
    base_year = args.year

    # Run 1: Completed events in base year.
    _print_run_header(1, f"Completed events in {base_year}")
    _print_code(
        """
start = datetime(year, 1, 1)
end = datetime(year + 1, 1, 1)
completed = [e for e in events if start <= e.date < end and e.event_type == 'completed']
unique_tasks = {e.event_entry.object_id for e in completed}
        """
    )
    completed_count, unique_tasks = _count_completed(events, base_year)
    print(f"Completed events: {completed_count}")
    print(f"Unique completed task ids: {unique_tasks}")
    checks = []
    checks.append(_check("non_negative", completed_count >= 0))
    checks.append(_check("unique<=completed", unique_tasks <= completed_count))
    summary.append(
        {
            "run": 1,
            "title": f"{base_year} completed",
            "completed": completed_count,
            "unique_tasks": unique_tasks,
            "checks_ok": all(ok for _, ok in checks),
        }
    )

    # Run 2: Completed events in base_year - 1.
    prior_year = base_year - 1
    _print_run_header(2, f"Completed events in {prior_year}")
    _print_code(
        """
start = datetime(year - 1, 1, 1)
end = datetime(year, 1, 1)
completed = [e for e in events if start <= e.date < end and e.event_type == 'completed']
unique_tasks = {e.event_entry.object_id for e in completed}
        """
    )
    completed_prev, unique_prev = _count_completed(events, prior_year)
    print(f"Completed events: {completed_prev}")
    print(f"Unique completed task ids: {unique_prev}")
    checks = []
    checks.append(_check("non_negative", completed_prev >= 0))
    checks.append(_check("unique<=completed", unique_prev <= completed_prev))
    summary.append(
        {
            "run": 2,
            "title": f"{prior_year} completed",
            "completed": completed_prev,
            "unique_tasks": unique_prev,
            "checks_ok": all(ok for _, ok in checks),
        }
    )

    # Run 3: Completed events in January of base year.
    _print_run_header(3, f"Completed events in Jan {base_year}")
    _print_code(
        """
start = datetime(year, 1, 1)
end = datetime(year, 2, 1)
completed = [e for e in events if start <= e.date < end and e.event_type == 'completed']
        """
    )
    jan_start = datetime(base_year, 1, 1)
    jan_end = datetime(base_year, 2, 1)
    completed_jan = _filter_completed(events, jan_start, jan_end)
    unique_jan = len(_unique_task_ids(completed_jan))
    print(f"Completed events: {len(completed_jan)}")
    print(f"Unique completed task ids: {unique_jan}")
    checks = []
    checks.append(_check("non_negative", len(completed_jan) >= 0))
    checks.append(_check("jan<=year", len(completed_jan) <= completed_count))
    checks.append(_check("unique<=completed", unique_jan <= len(completed_jan)))
    summary.append(
        {
            "run": 3,
            "title": f"Jan {base_year} completed",
            "completed": len(completed_jan),
            "unique_tasks": unique_jan,
            "checks_ok": all(ok for _, ok in checks),
        }
    )

    # Run 4: Completed events by object_type in base year.
    _print_run_header(4, f"Completed event types in {base_year}")
    _print_code(
        """
completed = [e for e in events if in_year(e.date, year) and e.event_type == 'completed']
counts = count_by(e.event_entry.object_type for e in completed)
        """
    )
    year_start = datetime(base_year, 1, 1)
    year_end = datetime(base_year + 1, 1, 1)
    completed_year = _filter_completed(events, year_start, year_end)
    by_type = _completed_by_object_type(completed_year)
    top_types = sorted(by_type.items(), key=lambda item: item[1], reverse=True)[:5]
    print("Top object_type counts:")
    for name, count in top_types:
        print(f"  {name}: {count}")
    checks = []
    checks.append(
        _check("sum_matches_total", sum(by_type.values()) == len(completed_year))
    )
    summary.append(
        {
            "run": 4,
            "title": f"{base_year} by object_type",
            "completed": len(completed_year),
            "top_types": top_types,
            "checks_ok": all(ok for _, ok in checks),
        }
    )

    # Run 5: Completed event date bounds in base year.
    _print_run_header(5, f"Completed event date bounds in {base_year}")
    _print_code(
        """
completed = [e for e in events if in_year(e.date, year) and e.event_type == 'completed']
min_date = min(e.date for e in completed)
max_date = max(e.date for e in completed)
        """
    )
    if completed_year:
        dates = [(_to_naive(e.date)) for e in completed_year]
        min_dt = min(dates)
        max_dt = max(dates)
        print(f"Earliest completed: {min_dt.isoformat(sep=' ')}")
        print(f"Latest completed:   {max_dt.isoformat(sep=' ')}")
        checks = []
        checks.append(_check("within_year_start", min_dt >= year_start))
        checks.append(_check("within_year_end", max_dt < year_end))
        ok = all(ok for _, ok in checks)
    else:
        print("No completed events found for the year.")
        ok = True
    summary.append(
        {
            "run": 5,
            "title": f"{base_year} date bounds",
            "checks_ok": ok,
        }
    )

    print("\n== SUMMARY ==")
    failed = 0
    for item in summary:
        ok = bool(item.get("checks_ok"))
        status = "OK" if ok else "FAILED"
        line = f"Run {item.get('run')}: {item.get('title')} -> {status}"
        if "completed" in item:
            line += f", completed={item.get('completed')}"
        if "unique_tasks" in item:
            line += f", unique_tasks={item.get('unique_tasks')}"
        print(line)
        if not ok:
            failed += 1

    return 0 if not missing and failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
