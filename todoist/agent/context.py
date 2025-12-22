"""Utilities for loading read-only local context for the agent."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
import pandas as pd

from todoist.types import Event
from todoist.utils import Cache


@dataclass(frozen=True)
class LocalAgentContext:
    """In-memory, read-only data available to the Python analysis tool."""

    events: tuple[Event, ...]
    events_df: pd.DataFrame
    cache_path: Path


def _events_to_simple_dataframe(events: tuple[Event, ...]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for event in events:
        entry = event.event_entry
        rows.append({
            "id": str(event.id),
            "date": event.date,
            "event_type": event.event_type,
            "object_type": entry.object_type,
            "object_id": entry.object_id,
            "parent_project_id": entry.parent_project_id,
            "parent_item_id": entry.parent_item_id,
            "title": event.name,
            "extra_data": dict(entry.extra_data) if isinstance(entry.extra_data, dict) else entry.extra_data,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.sort_values("date", inplace=True)
        df.set_index("date", inplace=True)
    return df


def load_local_agent_context(cache_path: str | Path = ".") -> LocalAgentContext:
    """Load local caches (read-only) to be used by the agent.

    This intentionally avoids any Todoist API access. It only reads local cache files.
    """

    cache_root = Path(cache_path)
    cache = Cache(str(cache_root))
    activity: set[Event] = cache.activity.load()
    events = tuple(sorted(activity, key=lambda e: e.date))
    logger.info("Loaded {} events from {}", len(events), str(cache_root / "activity.joblib"))
    df = _events_to_simple_dataframe(events)
    if not df.empty:
        logger.info("events_df ready: rows={}, date_range=[{}..{}]", len(df), df.index.min(), df.index.max())
    return LocalAgentContext(events=events, events_df=df, cache_path=cache_root)
