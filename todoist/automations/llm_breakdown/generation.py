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


def _generate_breakdown_result(
    *, llm: Any, request: PreparedBreakdownRequest
) -> BreakdownGenerationResult:
    logger.debug(
        "Submitting breakdown task {} (variant={}, depth={}, source={})",
        request.task.id,
        request.variant_key,
        request.depth,
        request.source,
    )
    try:
        breakdown = llm.structured_chat(request.messages, TaskBreakdown)
        if breakdown.children:
            return BreakdownGenerationResult(request=request, breakdown=breakdown)
        logger.warning(
            "Breakdown request for task {} returned no children; retrying",
            request.task.id,
        )
        return BreakdownGenerationResult(
            request=request,
            breakdown=llm.structured_chat(
                _non_empty_retry_messages(request), TaskBreakdown
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Breakdown request failed for task {}", request.task.id)
        return BreakdownGenerationResult(
            request=request,
            breakdown=None,
            error=str(exc),
        )


def _non_empty_retry_messages(
    request: PreparedBreakdownRequest,
) -> list[dict[str, str]]:
    messages = [dict(message) for message in request.messages]
    retry_instruction = (
        "The previous rollout had no children. Return strict JSON with a non-empty "
        "`children` array containing 3-6 concrete, actionable subtasks for this task. "
        "Do not return an empty list."
    )
    for message in messages:
        if str(message.get("role") or "").strip().lower() == "system":
            message["content"] = (
                f"{message.get('content', '').strip()} {retry_instruction}".strip()
            )
            return messages
    return [{"role": "system", "content": retry_instruction}, *messages]
