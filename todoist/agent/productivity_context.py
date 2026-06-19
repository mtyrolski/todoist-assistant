"""Read-only productivity context helpers for the local assistant."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from joblib import load as _joblib_load

from todoist.core import telemetry
from todoist.core.env import EnvVar
from todoist.core.utils import CACHE_STORAGE_REGISTRY, resolve_cache_dir
from todoist.database.base import Database
from todoist.llm.usage import load_llm_usage_summary

_SUBPROCESS_RUN = subprocess.run
_SCRIPT_TIMEOUT_SECONDS = 120
_SCRIPT_OUTPUT_LIMIT = 12_000
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
            raise ValueError(f"Script {normalized!r} is not allowlisted. Allowed: {allowed}")
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
            "debugEnabled": os.getenv(str(EnvVar.TELEMETRY_DEBUG), "")
            .strip()
            .lower()
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
    return ProductivityContext(cache_path=cache_root, repo_root=root, env_path=dotenv_path)


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
            "create_tasks(project_id, tasks, confirmation='CREATE_TODOIST_TASKS')",
        ],
    }


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
