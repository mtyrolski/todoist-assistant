"""Read-only productivity context helpers for the local assistant."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, cast

from joblib import load as _joblib_load
import pandas as pd

from todoist.core import telemetry
from todoist.core.env import EnvVar
from todoist.core.utils import CACHE_STORAGE_REGISTRY, resolve_cache_dir
from todoist.database.base import Database
from todoist.features.ai_context import (
    aggregate_ai_context,
    collect_ai_context,
    render_ai_context,
    upsert_ai_context_task,
)
from todoist.llm.usage import load_llm_usage_summary

_SUBPROCESS_RUN = subprocess.run
_SCRIPT_TIMEOUT_SECONDS = 120
_SCRIPT_OUTPUT_LIMIT = 12_000
_SUMMARY_EVENT_TYPES = ("completed", "added", "updated", "deleted", "rescheduled")
_ALLOWED_SCRIPT_NAMES = frozenset(
    {
        "check_explicit_any",
        "check_llm_activity_prompt",
        "check_versions",
        "get_version",
        "status",
    }
)


@dataclass(frozen=True)
class ProductivityContext:
    """Callable helpers exposed to the assistant Python tool."""

    cache_path: Path
    repo_root: Path
    env_path: Path

    def cache_summary(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name, (filename, _factory) in sorted(CACHE_STORAGE_REGISTRY.items()):
            path = self.cache_path / filename
            stat = path.stat() if path.exists() else None
            item: dict[str, Any] = {
                "name": name,
                "filename": filename,
                "exists": stat is not None,
                "sizeBytes": stat.st_size if stat else 0,
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                )
                if stat
                else None,
            }
            if stat is not None:
                try:
                    payload = _joblib_load(path)
                    item["summary"] = _summarize_payload(payload)
                except Exception as exc:  # pragma: no cover - defensive
                    item["summary"] = {"error": f"{type(exc).__name__}: {exc}"}
            items.append(item)
        return items

    def load_cache(self, name: str) -> Any:
        normalized = str(name or "").strip()
        registry_entry = CACHE_STORAGE_REGISTRY.get(normalized)
        if registry_entry is None:
            allowed = ", ".join(sorted(CACHE_STORAGE_REGISTRY))
            raise ValueError(f"Unknown cache name {normalized!r}. Allowed: {allowed}")
        path = self.cache_path / registry_entry[0]
        if not path.exists():
            return registry_entry[1]()
        return _joblib_load(path)

    def activity_dataframe(self) -> pd.DataFrame:
        """Return the dashboard's mapped activity data as an isolated copy."""

        payload = self.load_cache("dashboard_state")
        frame = payload.get("df_activity") if isinstance(payload, dict) else None
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise RuntimeError(
                "Mapped dashboard activity is unavailable. Refresh the dashboard first."
            )
        required = {"date", "root_project_name"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise RuntimeError(
                "Mapped dashboard activity is missing columns: " + ", ".join(missing)
            )
        return frame.copy(deep=True)

    def project_comparison(
        self,
        period: str = "week",
        *,
        as_of: str | datetime | None = None,
        offset: int = 0,
        limit: int = 12,
        timezone_name: str = "Europe/Warsaw",
    ) -> dict[str, Any]:
        """Compare mapped root-project activity with the preceding period."""

        current_start, current_end = _period_bounds(
            period, as_of=as_of, offset=offset, timezone_name=timezone_name
        )
        as_of_timestamp = _coerce_timestamp(as_of, timezone_name=timezone_name)
        observed_end = (
            current_end
            if int(offset) > 0
            else min(current_end, max(current_start, as_of_timestamp))
        )
        span = current_end - current_start
        previous_start = current_start - span
        previous_observed_end = previous_start + (observed_end - current_start)
        frame = _prepare_activity_frame(
            self.activity_dataframe(), timezone_name=timezone_name
        )
        current = _slice_period(frame, current_start, observed_end)
        previous = _slice_period(frame, previous_start, previous_observed_end)
        projects = _compare_project_frames(current, previous)
        bounded_limit = max(1, min(int(limit), 50))
        return {
            "periodType": _normalize_period(period),
            "timezone": timezone_name,
            "asOf": as_of_timestamp.isoformat(),
            "periodComplete": observed_end >= current_end,
            "comparisonMode": (
                "full_period" if observed_end >= current_end else "elapsed_to_elapsed"
            ),
            "currentPeriod": _period_payload(
                current_start, current_end, observed_end=observed_end
            ),
            "previousPeriod": _period_payload(
                previous_start, current_start, observed_end=previous_observed_end
            ),
            "currentTotals": _event_counts(current),
            "previousTotals": _event_counts(previous),
            "projects": projects[:bounded_limit],
        }

    def executive_summary(
        self,
        period: str = "week",
        *,
        as_of: str | datetime | None = None,
        offset: int = 0,
        limit: int = 8,
        timezone_name: str = "Europe/Warsaw",
    ) -> dict[str, Any]:
        """Return decision-ready daily or weekly productivity context."""

        comparison = self.project_comparison(
            period,
            as_of=as_of,
            offset=offset,
            limit=limit,
            timezone_name=timezone_name,
        )
        start = cast(
            pd.Timestamp,
            pd.Timestamp(comparison["currentPeriod"]["start"], tz=timezone_name),
        )
        observed_end = cast(
            pd.Timestamp,
            pd.Timestamp(comparison["currentPeriod"]["observedThrough"]).tz_convert(
                timezone_name
            ),
        )
        frame = _prepare_activity_frame(
            self.activity_dataframe(), timezone_name=timezone_name
        )
        current = _slice_period(frame, start, observed_end)
        busiest_day = _busiest_day(current)
        recent_completions = _recent_completions(current, limit=limit)
        return {
            "periodType": comparison["periodType"],
            "timezone": timezone_name,
            "period": comparison["currentPeriod"],
            "comparisonPeriod": comparison["previousPeriod"],
            "totals": comparison["currentTotals"],
            "previousTotals": comparison["previousTotals"],
            "leadingProjects": comparison["projects"],
            "busiestDay": busiest_day,
            "recentCompletions": recent_completions,
            "signals": _summary_signals(comparison),
        }

    def script_catalog(self) -> list[dict[str, str]]:
        scripts_dir = self.repo_root / "scripts"
        items: list[dict[str, str]] = []
        for path in sorted(scripts_dir.glob("*.py")):
            name = path.stem
            if name not in _ALLOWED_SCRIPT_NAMES:
                continue
            items.append(
                {
                    "name": name,
                    "path": _display_path(path, self.repo_root),
                    "command": f"run_script({name!r}, args=[...])",
                }
            )
        return items

    def run_script(
        self,
        name: str,
        args: Sequence[str] | None = None,
        *,
        timeout_seconds: int = _SCRIPT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        normalized = str(name or "").strip()
        if normalized not in _ALLOWED_SCRIPT_NAMES:
            allowed = ", ".join(sorted(_ALLOWED_SCRIPT_NAMES))
            raise ValueError(
                f"Script {normalized!r} is not allowlisted. Allowed: {allowed}"
            )
        script_path = (self.repo_root / "scripts" / f"{normalized}.py").resolve()
        scripts_root = (self.repo_root / "scripts").resolve()
        if scripts_root not in script_path.parents or not script_path.exists():
            raise ValueError(f"Script not found: {normalized}")
        safe_args = [str(arg) for arg in (args or [])]
        timeout = max(1, min(int(timeout_seconds), _SCRIPT_TIMEOUT_SECONDS))
        result = _SUBPROCESS_RUN(
            [sys.executable, str(script_path), *safe_args],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "name": normalized,
            "returncode": int(result.returncode),
            "stdout": _truncate(result.stdout),
            "stderr": _truncate(result.stderr),
        }

    def llm_usage(self) -> dict[str, Any]:
        backend = os.getenv(str(EnvVar.AGENT_BACKEND), "disabled")
        model = os.getenv(str(EnvVar.AGENT_CODEX_MODEL), "disabled")
        return load_llm_usage_summary(
            selected_backend=backend,
            selected_model_id=model,
        )

    def telemetry_status(self) -> dict[str, Any]:
        config_dir = telemetry.resolve_config_dir()
        data_dir = telemetry.default_data_dir()
        config_path = config_dir / telemetry.CONFIG_FILENAME
        sentinel_path = data_dir / telemetry.SENTINEL_FILENAME
        endpoint = os.getenv(str(EnvVar.TELEMETRY_ENDPOINT))
        return {
            "enabled": telemetry.is_enabled(config_dir),
            "endpointConfigured": bool(endpoint),
            "debugEnabled": os.getenv(str(EnvVar.TELEMETRY_DEBUG), "").strip().lower()
            in {"1", "true", "yes"},
            "configPath": str(config_path),
            "sentinelPath": str(sentinel_path),
            "installSuccessSent": sentinel_path.exists(),
        }

    def projects(self) -> list[dict[str, Any]]:
        db = Database(str(self.env_path))
        projects = db.fetch_projects(include_tasks=False)
        items: list[dict[str, Any]] = []
        for project in projects:
            if project.is_archived or project.project_entry.is_deleted:
                continue
            items.append(
                {
                    "id": project.id,
                    "name": project.project_entry.name,
                    "parentId": project.project_entry.parent_id,
                    "archived": bool(project.project_entry.is_archived),
                }
            )
        items.sort(key=lambda item: str(item["name"]).lower())
        return items

    def ai_context(
        self,
        *,
        project_id: str | None = None,
        project_name: str | None = None,
    ) -> list[dict[str, str]]:
        """Fetch durable AI context, optionally scoped to an exact project."""

        db = Database(str(self.env_path))
        entries = collect_ai_context(
            db.fetch_projects(include_tasks=True),
            project_id=project_id,
            project_name=project_name,
        )
        return [entry.as_dict() for entry in entries]

    def rendered_ai_context(self) -> str:
        """Fetch and render bounded context for automatic prompt injection."""

        db = Database(str(self.env_path))
        entries = collect_ai_context(db.fetch_projects(include_tasks=True))
        return render_ai_context(entries)

    def project_ai_context(
        self,
        *,
        project_id: str | None = None,
        project_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return a fresh, lossless project grouping of all durable context tasks."""

        db = Database(str(self.env_path))
        entries = collect_ai_context(
            db.fetch_projects(include_tasks=True),
            project_id=project_id,
            project_name=project_name,
        )
        return [aggregate.as_dict() for aggregate in aggregate_ai_context(entries)]

    def upsert_ai_context(
        self,
        project_id: str,
        content: str,
        *,
        description: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a protected project-memory task."""

        normalized_project_id = str(project_id or "").strip()
        db = Database(str(self.env_path))
        projects = db.fetch_projects(include_tasks=True)
        active_project_ids = {
            project.id
            for project in projects
            if not project.is_archived and not project.project_entry.is_deleted
        }
        if normalized_project_id not in active_project_ids:
            raise ValueError("project_id must identify an active Todoist project")
        entries = collect_ai_context(projects, project_id=normalized_project_id)
        return upsert_ai_context_task(
            db,
            project_id=normalized_project_id,
            content=content,
            description=description,
            task_id=task_id,
            existing_entries=entries,
        )

    def create_tasks(
        self,
        project_id: str,
        tasks: Sequence[dict[str, Any]],
        *,
        confirmation: str = "",
    ) -> dict[str, Any]:
        """Create tasks only after the chat user explicitly confirms."""

        if confirmation != "CREATE_TODOIST_TASKS":
            raise PermissionError(
                "Task creation requires confirmation='CREATE_TODOIST_TASKS'."
            )
        project = str(project_id or "").strip()
        if not project:
            raise ValueError("project_id is required")
        normalized = _normalize_task_nodes(tasks)
        if not normalized:
            raise ValueError("No valid tasks to create")
        db = Database(str(self.env_path))
        created: list[dict[str, Any]] = []
        for task in normalized:
            _create_task_node(db, project_id=project, node=task, created=created)
        return {"created": created, "createdCount": len(created)}


def build_productivity_context(
    *,
    cache_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    env_path: str | Path | None = None,
) -> ProductivityContext:
    cache_root = Path(resolve_cache_dir(str(cache_path) if cache_path else None))
    root = Path(repo_root or Path.cwd()).expanduser().resolve()
    dotenv_path = Path(env_path or (root / ".env")).expanduser().resolve()
    return ProductivityContext(
        cache_path=cache_root, repo_root=root, env_path=dotenv_path
    )


def productivity_context_payload(ctx: ProductivityContext) -> dict[str, Any]:
    return {
        "cachePath": str(ctx.cache_path),
        "envPath": str(ctx.env_path),
        "scripts": ctx.script_catalog(),
        "cacheFiles": ctx.cache_summary(),
        "usage": ctx.llm_usage(),
        "telemetry": ctx.telemetry_status(),
        "tools": [
            "cache_summary()",
            "load_cache(name)",
            "script_catalog()",
            "run_script(name, args=None)",
            "llm_usage()",
            "telemetry_status()",
            "projects()",
            "ai_context(project_id=None, project_name=None)",
            "project_ai_context(project_id=None, project_name=None)",
            "activity_dataframe()",
            "project_comparison(period='week', as_of=None, offset=0, limit=12)",
            "executive_summary(period='week', as_of=None, offset=0, limit=8)",
            "upsert_ai_context(project_id, content, description='...', task_id=None)",
            "create_tasks(project_id, tasks, confirmation='CREATE_TODOIST_TASKS')",
        ],
    }


def _normalize_period(period: str) -> str:
    normalized = str(period or "").strip().lower()
    aliases = {"daily": "day", "today": "day", "weekly": "week", "this week": "week"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"day", "week"}:
        raise ValueError("period must be 'day' or 'week'")
    return normalized


def _period_bounds(
    period: str,
    *,
    as_of: str | datetime | None,
    offset: int,
    timezone_name: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    normalized_period = _normalize_period(period)
    if int(offset) < 0:
        raise ValueError("offset must be non-negative")
    timestamp = _coerce_timestamp(as_of, timezone_name=timezone_name)
    day_start = cast(pd.Timestamp, timestamp.normalize())
    if normalized_period == "week":
        start = day_start - pd.Timedelta(days=day_start.weekday())
        start -= pd.Timedelta(weeks=int(offset))
        return cast(pd.Timestamp, start), cast(
            pd.Timestamp, start + pd.Timedelta(weeks=1)
        )
    start = day_start - pd.Timedelta(days=int(offset))
    return cast(pd.Timestamp, start), cast(pd.Timestamp, start + pd.Timedelta(days=1))


def _coerce_timestamp(
    value: str | datetime | None, *, timezone_name: str
) -> pd.Timestamp:
    raw_timestamp = (
        pd.Timestamp.now(tz=timezone_name) if value is None else pd.Timestamp(value)
    )
    if pd.isna(raw_timestamp):
        raise ValueError("as_of must be a valid date or datetime")
    timestamp = cast(pd.Timestamp, raw_timestamp)
    timestamp = (
        cast(pd.Timestamp, timestamp.tz_localize(timezone_name))
        if timestamp.tzinfo is None
        else cast(pd.Timestamp, timestamp.tz_convert(timezone_name))
    )
    return timestamp


def _prepare_activity_frame(frame: pd.DataFrame, *, timezone_name: str) -> pd.DataFrame:
    prepared = cast(pd.DataFrame, frame.reset_index(drop=True).copy())
    date_values = cast(pd.Series, prepared["date"])
    parsed_dates = cast(
        pd.Series, pd.to_datetime(date_values, errors="coerce", utc=True)
    )
    prepared["_date"] = parsed_dates.dt.tz_convert(timezone_name)
    valid_dates = cast(pd.Series, prepared["_date"]).notna()
    prepared = cast(pd.DataFrame, prepared.loc[valid_dates].copy())
    event_column = "type" if "type" in prepared.columns else "event_type"
    if event_column not in prepared.columns:
        raise RuntimeError("Mapped dashboard activity has no event type column")
    prepared["_event_type"] = (
        cast(pd.Series, prepared[event_column]).fillna("").astype(str)
    )
    prepared["_project"] = (
        cast(pd.Series, prepared["root_project_name"]).fillna("(unknown)").astype(str)
    )
    if "title" not in prepared.columns:
        prepared["title"] = ""
    return prepared


def _slice_period(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    dates = cast(pd.Series, frame["_date"])
    return cast(pd.DataFrame, frame.loc[(dates >= start) & (dates < end)].copy())


def _event_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts = cast(
        pd.Series,
        cast(pd.Series, frame["_event_type"]).value_counts()
        if not frame.empty
        else pd.Series(dtype=int),
    )
    payload = {
        event_type: int(cast(Any, counts[event_type]))
        if event_type in counts.index
        else 0
        for event_type in _SUMMARY_EVENT_TYPES
    }
    payload["events"] = int(len(frame))
    return payload


def _compare_project_frames(
    current: pd.DataFrame, previous: pd.DataFrame
) -> list[dict[str, Any]]:
    current_projects = cast(pd.Series, current["_project"]).astype(str).to_list()
    previous_projects = cast(pd.Series, previous["_project"]).astype(str).to_list()
    project_names = sorted(set(current_projects) | set(previous_projects))
    rows: list[dict[str, Any]] = []
    for project_name in project_names:
        current_mask = cast(pd.Series, current["_project"]) == project_name
        previous_mask = cast(pd.Series, previous["_project"]) == project_name
        current_counts = _event_counts(cast(pd.DataFrame, current.loc[current_mask]))
        previous_counts = _event_counts(cast(pd.DataFrame, previous.loc[previous_mask]))
        change = {
            key: int(current_counts[key] - previous_counts[key])
            for key in current_counts
        }
        rows.append(
            {
                "project": str(project_name),
                "current": current_counts,
                "previous": previous_counts,
                "change": change,
            }
        )

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
        current_counts = cast(dict[str, int], item["current"])
        change_counts = cast(dict[str, int], item["change"])
        return (
            current_counts["events"],
            current_counts["completed"],
            abs(change_counts["events"]),
        )

    rows.sort(key=sort_key, reverse=True)
    return rows


def _period_payload(
    start: pd.Timestamp, end: pd.Timestamp, *, observed_end: pd.Timestamp
) -> dict[str, str]:
    return {
        "start": start.date().isoformat(),
        "end": (end - pd.Timedelta(days=1)).date().isoformat(),
        "endExclusive": end.date().isoformat(),
        "observedThrough": observed_end.isoformat(),
    }


def _busiest_day(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame.empty:
        return None
    dates = cast(pd.Series, frame["_date"])
    counts = cast(pd.Series, frame.groupby(dates.dt.date).size()).sort_values(
        ascending=False
    )
    return {"date": str(counts.index[0]), "events": int(counts.iloc[0])}


def _recent_completions(frame: pd.DataFrame, *, limit: int) -> list[dict[str, str]]:
    completed_mask = cast(pd.Series, frame["_event_type"]) == "completed"
    completed = cast(pd.DataFrame, frame.loc[completed_mask].sort_values(by="_date"))
    rows: list[dict[str, str]] = []
    for _, row in completed.tail(max(1, min(int(limit), 20))).iterrows():
        rows.append(
            {
                "title": str(row.get("title") or "(untitled)"),
                "project": str(row["_project"]),
                "date": cast(pd.Timestamp, row["_date"]).isoformat(),
            }
        )
    return rows


def _summary_signals(comparison: dict[str, Any]) -> list[str]:
    current = comparison["currentTotals"]
    previous = comparison["previousTotals"]
    completed_change = int(current["completed"] - previous["completed"])
    signals = [
        f"Completed tasks changed by {completed_change:+d} versus the previous period."
    ]
    if current["added"] > current["completed"]:
        signals.append(
            f"Task intake exceeded completions by {current['added'] - current['completed']}."
        )
    elif current["completed"] > current["added"]:
        signals.append(
            f"Completions exceeded task intake by {current['completed'] - current['added']}."
        )
    projects = comparison["projects"]
    if projects:
        leader = projects[0]
        signals.append(
            f"{leader['project']} led activity with {leader['current']['events']} events "
            f"and {leader['current']['completed']} completions."
        )
    if current["deleted"]:
        signals.append(f"The period included {current['deleted']} deleted tasks.")
    return signals


def _summarize_payload(payload: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {"type": type(payload).__name__}
    if isinstance(payload, dict):
        summary["count"] = len(payload)
        summary["keys"] = [str(key) for key in list(payload.keys())[:12]]
    elif isinstance(payload, (list, tuple, set, frozenset)):
        summary["count"] = len(payload)
    return summary


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _truncate(value: str) -> str:
    text = str(value or "")
    if len(text) <= _SCRIPT_OUTPUT_LIMIT:
        return text
    return text[: _SCRIPT_OUTPUT_LIMIT - 20].rstrip() + "\n...<truncated>"


def _normalize_task_nodes(nodes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or "").strip()
        if not content:
            continue
        node: dict[str, Any] = {"content": content}
        description = str(raw.get("description") or "").strip()
        if description:
            node["description"] = description
        children = raw.get("children")
        if isinstance(children, Sequence) and not isinstance(children, str):
            child_nodes = _normalize_task_nodes(
                [child for child in children if isinstance(child, dict)]
            )
            if child_nodes:
                node["children"] = child_nodes
        normalized.append(node)
    return normalized


def _create_task_node(
    db: Database,
    *,
    project_id: str,
    node: dict[str, Any],
    created: list[dict[str, Any]],
    parent_id: str | None = None,
) -> None:
    payload = db.insert_task(
        content=str(node["content"]),
        description=str(node.get("description") or "").strip() or None,
        project_id=project_id if parent_id is None else None,
        parent_id=parent_id,
    )
    task_id = str(payload.get("id") or "").strip()
    if not task_id:
        raise RuntimeError(f"Failed to create task: {node['content']}")
    created.append(
        {
            "id": task_id,
            "content": str(node["content"]),
            "parentId": parent_id,
            "projectId": project_id,
        }
    )
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _create_task_node(
                db,
                project_id=project_id,
                node=child,
                created=created,
                parent_id=task_id,
            )
