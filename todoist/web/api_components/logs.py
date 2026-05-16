from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException


@dataclass(frozen=True)
class RuntimeLogSpec:
    key: str
    label: str
    category: str
    description: str
    relative_path: str


def display_log_path(path: Path, *, data_dir: Path, cache_dir: Path) -> str:
    resolved = path.resolve()
    for root in (data_dir.resolve(), cache_dir.resolve()):
        try:
            return str(resolved.relative_to(root))
        except ValueError:
            continue
    return str(resolved)


def runtime_log_specs() -> tuple[RuntimeLogSpec, ...]:
    return (
        RuntimeLogSpec(
            key="api",
            label="Backend API",
            category="backend",
            description="FastAPI and Uvicorn application output.",
            relative_path="dashboard/api.log",
        ),
        RuntimeLogSpec(
            key="frontend",
            label="Frontend",
            category="frontend",
            description="Next.js dashboard server output.",
            relative_path="dashboard/frontend.log",
        ),
        RuntimeLogSpec(
            key="observer",
            label="Observer",
            category="observer",
            description="Background observer polling and automation trigger output.",
            relative_path="dashboard/observer.log",
        ),
        RuntimeLogSpec(
            key="triton",
            label="Triton",
            category="triton",
            description="Triton container logs tailed by the dashboard launcher.",
            relative_path="dashboard/triton.log",
        ),
        RuntimeLogSpec(
            key="triton_inference",
            label="Triton Inference",
            category="triton",
            description="Per-request Triton model logs including grouped batch execution details.",
            relative_path="dashboard/triton-inference.log",
        ),
        RuntimeLogSpec(
            key="automation",
            label="Automation Jobs",
            category="automation",
            description="Shared automation runner output outside the dashboard stack.",
            relative_path="automation.log",
        ),
    )


def runtime_log_path(spec: RuntimeLogSpec, *, cache_dir: Path) -> Path:
    return (cache_dir / spec.relative_path).resolve()


def runtime_log_sources(*, data_dir: Path, cache_dir: Path) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for spec in runtime_log_specs():
        path = runtime_log_path(spec, cache_dir=cache_dir)
        available = path.is_file()
        size: int | None = None
        mtime: str | None = None
        if available:
            try:
                stat = path.stat()
            except OSError:
                available = False
            else:
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        sources.append(
            {
                "id": spec.key,
                "label": spec.label,
                "kind": spec.category,
                "description": spec.description,
                "path": display_log_path(path, data_dir=data_dir, cache_dir=cache_dir),
                "available": available,
                "inspectOnly": True,
                "size": size,
                "mtime": mtime,
            }
        )
    return sources


def resolve_runtime_log_source(
    source: str, *, cache_dir: Path
) -> tuple[RuntimeLogSpec, Path]:
    key = source.strip().lower()
    for spec in runtime_log_specs():
        if spec.key == key:
            return spec, runtime_log_path(spec, cache_dir=cache_dir)
    raise HTTPException(status_code=404, detail=f"Unknown runtime log source: {source}")


def resolve_runtime_log_request(
    *,
    data_dir: Path,
    cache_dir: Path,
    source: str | None = None,
    path: str | None = None,
) -> tuple[RuntimeLogSpec, Path]:
    if source is not None and source.strip():
        return resolve_runtime_log_source(source, cache_dir=cache_dir)
    if path is not None and path.strip():
        normalized = path.strip()
        for spec in runtime_log_specs():
            candidate = runtime_log_path(spec, cache_dir=cache_dir)
            if normalized in {
                spec.relative_path,
                display_log_path(candidate, data_dir=data_dir, cache_dir=cache_dir),
            }:
                return spec, candidate
        raise HTTPException(status_code=404, detail=f"Unknown runtime log path: {path}")
    raise HTTPException(status_code=400, detail="Missing runtime log source")


def read_log_file(path: Path, *, tail_lines: int, page: int) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError as exc:
        raise HTTPException(
            status_code=404, detail=f"Unable to read log file: {exc}"
        ) from exc

    total_lines = len(lines)
    per_page = max(1, min(2000, int(tail_lines)))
    total_pages = max(1, (total_lines + per_page - 1) // per_page)
    page_i = max(1, min(int(page), total_pages))

    end_line = total_lines - (page_i - 1) * per_page
    start_line = max(0, end_line - per_page)
    content = "".join(lines[start_line:end_line])
    return {
        "content": content,
        "page": page_i,
        "perPage": per_page,
        "totalPages": total_pages,
        "totalLines": total_lines,
    }
