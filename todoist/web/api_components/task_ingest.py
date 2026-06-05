# pyright: reportUndefinedVariable=false
"""Task ingest and status update helper logic for the web API facade."""

# pylint: disable=protected-access,cyclic-import,too-many-lines,undefined-variable

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, Field

from todoist.automations.llm_breakdown.models import BreakdownNode
from todoist.database.base import Database
from todoist.core.types import Project


def _sync_api_globals():
    from todoist.web import api as web_api

    current = globals()
    for name, value in vars(web_api).items():
        if name.startswith("__"):
            continue
        original = _ORIGINALS.get(name)
        if (
            original is not None
            and getattr(value, "_component_wrapper_for", None) == name
        ):
            current[name] = original
        else:
            current[name] = value
    return web_api


def _template_path(category: str, name: str) -> Path:
    _sync_api_globals()
    return _component_template_path(_TEMPLATES_DIR, category, name)


class _TaskIngestNode(BaseModel):
    content: str
    description: str | None = None
    children: list["_TaskIngestNode"] = Field(default_factory=list)


class _TaskIngestTree(BaseModel):
    tasks: list[_TaskIngestNode] = Field(default_factory=list)


_TaskIngestNode.model_rebuild()


_BULLET_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?:[-*+]|(?:\d+|[A-Za-z])[.)])\s+(?P<content>.+?)\s*$"
)


def _task_ingest_db() -> Database:
    _sync_api_globals()
    if _state.db is not None:
        return _state.db
    return Database(str(_resolve_env_path()))


def _task_ingest_project_payload(projects: Sequence[Project]) -> list[dict[str, Any]]:
    _sync_api_globals()
    active_projects = [
        project
        for project in projects
        if not project.is_archived
        and not project.project_entry.is_archived
        and not project.project_entry.is_deleted
    ]
    by_id = {project.id: project for project in active_projects}

    def project_path(project: Project) -> list[str]:
        names: list[str] = []
        current: Project | None = project
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            names.append(current.project_entry.name)
            parent_id = current.project_entry.parent_id
            current = by_id.get(str(parent_id)) if parent_id else None
        return list(reversed(names))

    payload = []
    for project in active_projects:
        path = project_path(project)
        payload.append(
            {
                "id": project.id,
                "name": project.project_entry.name,
                "label": " / ".join(path),
                "parentId": project.project_entry.parent_id,
            }
        )
    payload.sort(key=lambda item: str(item["label"]).lower())
    return payload


def _load_task_ingest_projects_sync(refresh: bool) -> list[dict[str, Any]]:
    _sync_api_globals()
    dbio = _task_ingest_db() if not refresh else Database(str(_resolve_env_path()))
    return _task_ingest_project_payload(dbio.fetch_projects(include_tasks=False))


def _task_ingest_total_nodes(tasks: Sequence[Mapping[str, Any]]) -> int:
    _sync_api_globals()
    total = 0
    for task in tasks:
        total += 1
        children = task.get("children")
        if isinstance(children, list):
            total += _task_ingest_total_nodes(
                [child for child in children if isinstance(child, Mapping)]
            )
    return total


def _task_ingest_trim_text(value: Any) -> str:
    _sync_api_globals()
    return _sanitize_text(value) or ""


def _normalize_task_ingest_node(
    raw: Mapping[str, Any],
    *,
    depth: int = 1,
    max_depth: int = 3,
    include_descriptions: bool = True,
) -> dict[str, Any] | None:
    _sync_api_globals()
    content = _task_ingest_trim_text(raw.get("content"))
    if not content:
        return None
    node: dict[str, Any] = {"content": content}
    description = _task_ingest_trim_text(raw.get("description"))
    if include_descriptions and description:
        node["description"] = description
    if depth < max_depth:
        raw_children = raw.get("children")
        if isinstance(raw_children, list):
            children = [
                normalized
                for child in raw_children
                if isinstance(child, Mapping)
                for normalized in [
                    _normalize_task_ingest_node(
                        child,
                        depth=depth + 1,
                        max_depth=max_depth,
                        include_descriptions=include_descriptions,
                    )
                ]
                if normalized is not None
            ]
            if children:
                node["children"] = children
    return node


def _task_ingest_tree_payload(
    tasks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    _sync_api_globals()
    return _task_ingest_tree_payload_with_options(
        tasks, max_depth=3, include_descriptions=True
    )


def _task_ingest_tree_payload_with_options(
    tasks: Sequence[Mapping[str, Any]], *, max_depth: int, include_descriptions: bool
) -> list[dict[str, Any]]:
    _sync_api_globals()
    return [
        normalized
        for task in tasks
        if isinstance(task, Mapping)
        for normalized in [
            _normalize_task_ingest_node(
                task,
                max_depth=max_depth,
                include_descriptions=include_descriptions,
            )
        ]
        if normalized is not None
    ]


def _task_ingest_options(payload: Mapping[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    raw_options = payload.get("options")
    options = raw_options if isinstance(raw_options, Mapping) else payload

    requested_depth = options.get("maxDepth")
    max_depth = 3
    if isinstance(requested_depth, int):
        max_depth = requested_depth
    elif isinstance(requested_depth, str) and requested_depth.strip().isdigit():
        max_depth = int(requested_depth.strip())
    max_depth = min(4, max(2, max_depth))

    granularity = (
        _task_ingest_trim_text(options.get("granularity")).lower() or "balanced"
    )
    if granularity not in {"compact", "balanced", "detailed"}:
        granularity = "balanced"

    preference = (
        _task_ingest_trim_text(options.get("preference")).lower() or "action-first"
    )
    if preference not in {
        "action-first",
        "milestone-driven",
        "checklist-heavy",
        "meeting-notes",
    }:
        preference = "action-first"

    include_descriptions_raw = options.get("includeDescriptions")
    include_descriptions = (
        True if include_descriptions_raw is None else bool(include_descriptions_raw)
    )

    return {
        "maxDepth": max_depth,
        "granularity": granularity,
        "preference": preference,
        "includeDescriptions": include_descriptions,
    }


def _heuristic_task_ingest_tree(
    raw_content: str, *, granularity: str
) -> list[dict[str, Any]]:
    _sync_api_globals()
    lines = raw_content.splitlines()
    roots: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = [(-1, {"children": roots})]
    current_node: dict[str, Any] | None = None
    preamble: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            current_node = None
            continue
        match = _BULLET_LINE_RE.match(line)
        if match:
            indent = len(match.group("indent").replace("\t", "    "))
            content = _task_ingest_trim_text(match.group("content"))
            if not content:
                continue
            node = {"content": content, "children": []}
            while len(stack) > 1 and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            parent.setdefault("children", []).append(node)
            stack.append((indent, node))
            current_node = node
            continue
        if current_node is not None:
            description = _task_ingest_trim_text(current_node.get("description"))
            current_node["description"] = (
                f"{description}\n{stripped}".strip() if description else stripped
            )
        else:
            preamble.append(stripped)

    if roots:
        heading = _task_ingest_trim_text(preamble[0]) if preamble else ""
        if heading:
            wrapper = {"content": heading, "children": roots}
            if len(preamble) > 1:
                wrapper["description"] = "\n".join(preamble[1:])
            return [wrapper]
        return roots

    paragraphs = [
        segment.strip()
        for segment in re.split(r"\n\s*\n+", raw_content)
        if segment.strip()
    ]
    if len(paragraphs) > 1:
        tasks: list[dict[str, Any]] = []
        for paragraph in paragraphs:
            paragraph_lines = [
                part.strip() for part in paragraph.splitlines() if part.strip()
            ]
            if not paragraph_lines:
                continue
            node: dict[str, Any] = {"content": paragraph_lines[0]}
            if len(paragraph_lines) > 1:
                node["description"] = "\n".join(paragraph_lines[1:])
            tasks.append(node)
        if tasks:
            return tasks

    sentence_limit = {"compact": 5, "balanced": 8, "detailed": 12}[granularity]
    sentences = [
        sentence.strip(" -\t")
        for sentence in re.split(r"(?:\n|;|(?<=\.)\s+)", raw_content)
        if sentence.strip(" -\t")
    ]
    if not sentences:
        return []
    if len(sentences) == 1:
        return [{"content": sentences[0]}]
    return [{"content": sentence} for sentence in sentences[:sentence_limit]]


def _task_ingest_from_breakdown(nodes: Sequence[BreakdownNode]) -> list[dict[str, Any]]:
    _sync_api_globals()
    payload: list[dict[str, Any]] = []
    for node in nodes:
        item: dict[str, Any] = {"content": _task_ingest_trim_text(node.content)}
        if not item["content"]:
            continue
        description = _task_ingest_trim_text(node.description)
        if description:
            item["description"] = description
        children = _task_ingest_from_breakdown(node.children)
        if children:
            item["children"] = children
        payload.append(item)
    return payload


def _task_ingest_build_llm_messages(
    raw_content: str,
    *,
    max_depth: int,
    granularity: str,
    preference: str,
    include_descriptions: bool,
) -> list[dict[str, str]]:
    _sync_api_globals()
    granularity_instruction = {
        "compact": "Prefer fewer, broader tasks and avoid over-splitting.",
        "balanced": "Aim for a practical middle ground between clarity and brevity.",
        "detailed": "Break the work down more aggressively into clear substeps when useful.",
    }[granularity]
    preference_instruction = {
        "action-first": "Favor concrete next actions over abstract buckets.",
        "milestone-driven": "Group subtasks under visible milestones when useful.",
        "checklist-heavy": "Prefer crisp checklist-style subtasks.",
        "meeting-notes": "Turn notes into decisions, follow-ups, and owners where possible.",
    }[preference]
    return [
        {
            "role": MessageRole.SYSTEM.value,
            "content": (
                "Rewrite the pasted source into an actionable Todoist task tree. "
                "Return only concrete tasks. Keep titles concise and imperative. "
                + (
                    "Use descriptions only for supporting context. "
                    if include_descriptions
                    else "Avoid descriptions unless absolutely required. "
                )
                + f"Keep nesting to at most {max_depth} levels total. "
                f"{granularity_instruction} "
                f"{preference_instruction}"
            ),
        },
        {
            "role": MessageRole.USER.value,
            "content": raw_content,
        },
    ]


def _task_ingest_rewrite_with_llm_sync(
    raw_content: str,
    *,
    max_depth: int,
    granularity: str,
    preference: str,
    include_descriptions: bool,
) -> tuple[list[dict[str, Any]], str] | None:
    _sync_api_globals()
    async_loaded_model = _LLM_CHAT_MODEL
    model: _LlmChatModel | None = async_loaded_model
    created_model = False
    if model is None:
        settings = _resolve_llm_chat_settings()
        try:
            model = _build_llm_from_settings(settings, max_output_tokens=768)
            created_model = True
        except (TypeError, ValueError) as exc:
            logger.warning(f"Task ingest LLM unavailable: {type(exc).__name__}: {exc}")
    if model is None:
        return None
    try:
        breakdown = model.structured_chat(
            _task_ingest_build_llm_messages(
                raw_content,
                max_depth=max_depth,
                granularity=granularity,
                preference=preference,
                include_descriptions=include_descriptions,
            ),
            TaskBreakdown,
        )
        tasks = _task_ingest_tree_payload_with_options(
            _task_ingest_from_breakdown(breakdown.children),
            max_depth=max_depth,
            include_descriptions=include_descriptions,
        )
        if tasks:
            source = "llm"
            backend = model_backend(model)
            if created_model and backend == "triton_local":
                source = "triton"
            elif created_model and backend == "codex":
                source = "codex"
            elif not created_model:
                source = "loaded-model"
            return tasks, source
    except Exception as exc:  # pragma: no cover - fallback path
        logger.warning(f"Task ingest LLM rewrite failed: {type(exc).__name__}: {exc}")
    return None


def _task_ingest_preview_sync(
    raw_content: str,
    *,
    max_depth: int,
    granularity: str,
    preference: str,
    include_descriptions: bool,
) -> tuple[list[dict[str, Any]], str]:
    _sync_api_globals()
    llm_result = _task_ingest_rewrite_with_llm_sync(
        raw_content,
        max_depth=max_depth,
        granularity=granularity,
        preference=preference,
        include_descriptions=include_descriptions,
    )
    if llm_result is not None:
        return llm_result
    return (
        _task_ingest_tree_payload_with_options(
            _heuristic_task_ingest_tree(raw_content, granularity=granularity),
            max_depth=max_depth,
            include_descriptions=include_descriptions,
        ),
        "outline",
    )


def _task_ingest_create_node_sync(
    dbio: Database,
    *,
    project_id: str,
    node: Mapping[str, Any],
    parent_id: str | None = None,
    created: list[dict[str, Any]],
) -> None:
    _sync_api_globals()
    payload = dbio.insert_task(
        content=str(node["content"]),
        description=_task_ingest_trim_text(node.get("description")) or None,
        project_id=project_id if parent_id is None else None,
        parent_id=parent_id,
    )
    task_id = _task_ingest_trim_text(payload.get("id"))
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
    children = node.get("children")
    if not isinstance(children, list):
        return
    for child in children:
        if isinstance(child, Mapping):
            _task_ingest_create_node_sync(
                dbio,
                project_id=project_id,
                node=child,
                parent_id=task_id,
                created=created,
            )


def _task_ingest_create_sync(
    project_id: str, tasks: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    _sync_api_globals()
    dbio = _task_ingest_db()
    created: list[dict[str, Any]] = []
    for task in tasks:
        _task_ingest_create_node_sync(
            dbio,
            project_id=project_id,
            node=task,
            created=created,
        )
    return created


def _load_status_update_projects_sync(refresh: bool) -> list[dict[str, Any]]:
    _sync_api_globals()
    dbio = _status_update_db() if not refresh else Database(str(_resolve_env_path()))
    return load_status_update_projects(dbio)


def _status_update_parse_date(value: Any, *, field: str) -> date:
    _sync_api_globals()
    parsed = _task_ingest_trim_text(value)
    if not parsed:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    try:
        return date.fromisoformat(parsed)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"{field} must be YYYY-MM-DD"
        ) from exc


_COMPONENT_EXPORTS = (
    "_TaskIngestNode",
    "_TaskIngestTree",
    "_heuristic_task_ingest_tree",
    "_load_status_update_projects_sync",
    "_load_task_ingest_projects_sync",
    "_normalize_task_ingest_node",
    "_status_update_parse_date",
    "_task_ingest_build_llm_messages",
    "_task_ingest_create_node_sync",
    "_task_ingest_create_sync",
    "_task_ingest_db",
    "_task_ingest_from_breakdown",
    "_task_ingest_options",
    "_task_ingest_preview_sync",
    "_task_ingest_project_payload",
    "_task_ingest_rewrite_with_llm_sync",
    "_task_ingest_total_nodes",
    "_task_ingest_tree_payload",
    "_task_ingest_tree_payload_with_options",
    "_task_ingest_trim_text",
    "_template_path",
)
_ORIGINALS = {name: globals()[name] for name in _COMPONENT_EXPORTS}
