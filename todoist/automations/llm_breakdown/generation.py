from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from .models import TaskBreakdown
from .planning import PreparedBreakdownRequest


@dataclass(frozen=True)
class BreakdownGenerationResult:
    request: PreparedBreakdownRequest
    breakdown: TaskBreakdown | None
    error: str | None = None


def generate_breakdowns(
    *,
    automation: Any,
    llm: Any,
    prepared_requests: list[PreparedBreakdownRequest],
) -> list[BreakdownGenerationResult]:
    if not prepared_requests:
        return []

    parallelism = automation.llm_request_parallelism(len(prepared_requests))
    if parallelism <= 1:
        return [
            _generate_breakdown_result(llm=llm, request=request)
            for request in prepared_requests
        ]

    logger.info(
        "Dispatching {} concurrent breakdown requests (tasks_per_tick={})",
        parallelism,
        len(prepared_requests),
    )
    with automation.concurrent_executor(max_workers=parallelism) as executor:
        futures = [
            executor.submit(_generate_breakdown_result, llm=llm, request=request)
            for request in prepared_requests
        ]
        return [future.result() for future in futures]


def _generate_breakdown_result(*, llm: Any, request: PreparedBreakdownRequest) -> BreakdownGenerationResult:
    logger.debug(
        "Submitting breakdown task {} (variant={}, depth={}, source={})",
        request.task.id,
        request.variant_key,
        request.depth,
        request.source,
    )
    try:
        return BreakdownGenerationResult(
            request=request,
            breakdown=llm.structured_chat(request.messages, TaskBreakdown),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Breakdown request failed for task {}", request.task.id)
        return BreakdownGenerationResult(
            request=request,
            breakdown=None,
            error=str(exc),
        )
