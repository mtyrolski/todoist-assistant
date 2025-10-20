"""Reusable HTTP client helpers for the Todoist API."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock, local
from time import perf_counter
from typing import Any, Mapping, MutableMapping, Optional

import requests
from loguru import logger

from todoist.utils import (
    RETRY_BACKOFF_MEAN,
    RETRY_BACKOFF_STD,
    RETRY_MAX_ATTEMPTS,
    get_api_key,
    with_retry,
)

from .endpoints import Endpoint


@dataclass(frozen=True, slots=True)
class TimeoutSettings:
    """Pair of connect/read timeouts for HTTP requests."""

    connect: float = 5.0
    read: float = 30.0

    def as_tuple(self) -> tuple[float, float]:
        """Return the timeout as ``(connect, read)`` tuple."""

        return (self.connect, self.read)


@dataclass(slots=True)
class RequestSpec:
    """Description of a Todoist API call."""

    endpoint: Endpoint
    headers: Optional[Mapping[str, str]] = None
    params: Optional[Mapping[str, Any]] = None
    data: Optional[Mapping[str, Any]] = None
    json_body: Any | None = None
    timeout: TimeoutSettings = field(default_factory=TimeoutSettings)
    max_attempts: Optional[int] = None


@dataclass(slots=True)
class EndpointCallResult:
    """Structured response metadata for a Todoist API call."""

    endpoint: Endpoint
    request_headers: Mapping[str, str]
    request_params: Mapping[str, Any]
    status_code: int
    elapsed: float
    text: str
    json: Any | None


class TodoistAPIClient:
    """High level client that wraps HTTP calls with retry, timeout and logging."""

    def __init__(
        self,
        *,
        default_timeout: TimeoutSettings | None = None,
        max_attempts: int = RETRY_MAX_ATTEMPTS,
        backoff_mean: float = RETRY_BACKOFF_MEAN,
        backoff_std: float = RETRY_BACKOFF_STD,
    ) -> None:
        self._session_local = local()
        self._default_timeout = default_timeout or TimeoutSettings()
        self._max_attempts = max_attempts
        self._backoff_mean = backoff_mean
        self._backoff_std = backoff_std
        self._last_call_lock = Lock()
        self._last_call_result: EndpointCallResult | None = None

    @property
    def last_call_result(self) -> EndpointCallResult | None:
        """Return metadata for the most recent API call in a thread-safe way."""

        with self._last_call_lock:
            return self._last_call_result

    def request(
        self,
        spec: RequestSpec,
        *,
        expect_json: bool = False,
        operation_name: str | None = None,
    ) -> EndpointCallResult:
        """Execute an HTTP request and capture structured metadata."""

        timeout = spec.timeout if spec.timeout is not None else self._default_timeout
        attempts = spec.max_attempts or self._max_attempts
        headers = self._build_headers(spec.headers)
        params = self._build_params(spec.params)
        op_name = operation_name or spec.endpoint.name

        def _do_request() -> EndpointCallResult:
            start = perf_counter()
            logger.debug(
                "Calling Todoist endpoint",
                endpoint=spec.endpoint.name,
                method=spec.endpoint.method,
                url=spec.endpoint.url,
                params=params,
            )
            try:
                response = self._get_session().request(
                    method=spec.endpoint.method,
                    url=spec.endpoint.url,
                    headers=headers,
                    params=params if params else None,
                    data=spec.data,
                    json=spec.json_body,
                    timeout=timeout.as_tuple(),
                )
            except requests.Timeout as exc:
                logger.warning(
                    "Request timeout",
                    endpoint=spec.endpoint.name,
                    url=spec.endpoint.url,
                    timeout=timeout.as_tuple(),
                )
                raise RuntimeError(f"Timeout calling {spec.endpoint.name}") from exc
            except requests.RequestException as exc:
                logger.error(
                    "Request error",
                    endpoint=spec.endpoint.name,
                    url=spec.endpoint.url,
                    error=str(exc),
                )
                raise RuntimeError(f"HTTP error calling {spec.endpoint.name}") from exc

            elapsed = perf_counter() - start
            logger.debug(
                "Received response",
                endpoint=spec.endpoint.name,
                status=response.status_code,
                elapsed=f"{elapsed:.3f}s",
            )

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                logger.error(
                    "Todoist endpoint returned error",
                    endpoint=spec.endpoint.name,
                    status=response.status_code,
                    body=response.text,
                )
                raise RuntimeError(
                    f"Failed calling {spec.endpoint.name}: {response.status_code}"
                ) from exc

            json_payload: Any | None = None
            if expect_json and response.content:
                try:
                    json_payload = response.json()
                except ValueError as exc:  # pragma: no cover - network safety
                    logger.error(
                        "Failed to decode JSON response",
                        endpoint=spec.endpoint.name,
                        body=response.text[:500],
                    )
                    raise RuntimeError(
                        f"Invalid JSON returned by {spec.endpoint.name}"
                    ) from exc

            result = EndpointCallResult(
                endpoint=spec.endpoint,
                request_headers=headers,
                request_params=params,
                status_code=response.status_code,
                elapsed=elapsed,
                text=response.text,
                json=json_payload,
            )
            with self._last_call_lock:
                self._last_call_result = result
            return result

        return with_retry(
            _do_request,
            operation_name=op_name,
            max_attempts=attempts,
            backoff_mean=self._backoff_mean,
            backoff_std=self._backoff_std,
        )

    def request_json(
        self, spec: RequestSpec, *, operation_name: str | None = None
    ) -> Any:
        """Execute request expecting JSON payload and return parsed body."""

        result = self.request(spec, expect_json=True, operation_name=operation_name)
        return result.json

    def _build_headers(
        self, headers: Optional[Mapping[str, str]]
    ) -> MutableMapping[str, str]:
        merged: MutableMapping[str, str] = {
            "Authorization": f"Bearer {get_api_key()}",
        }
        if headers:
            merged.update(headers)
        return merged

    @staticmethod
    def _build_params(
        params: Optional[Mapping[str, Any]]
    ) -> MutableMapping[str, Any]:
        if not params:
            return {}
        return {k: v for k, v in params.items() if v is not None}

    def _get_session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session
