from __future__ import annotations

import json
from dataclasses import replace
from queue import Empty, Queue
from threading import Thread
from time import monotonic
from typing import Mapping

from .authorization import AuthorizationContext, AuthorizationError
from .contracts import CancellationToken, ToolHandler, ToolRequest, ToolResult, ToolResultStatus, ToolSpec
from .validation import SchemaValidationError, validate_arguments


class ToolRegistryError(ValueError):
    pass


class ToolExecutor:
    """The sole validation, authorization, timeout, and result-bounding boundary."""

    def __init__(self, entries: Mapping[str, tuple[ToolSpec, ToolHandler]]) -> None:
        self._entries = dict(entries)
        for name, (spec, _) in self._entries.items():
            if name != spec.name:
                raise ToolRegistryError(f"registry key does not match tool spec: {name}")

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._entries[name][0] for name in sorted(self._entries))

    def execute(
        self,
        request: ToolRequest,
        authorization: AuthorizationContext,
        cancellation: CancellationToken,
        *,
        timeout_seconds: float | None = None,
        max_result_bytes: int | None = None,
    ) -> ToolResult:
        entry = self._entries.get(request.tool_name)
        if entry is None:
            return ToolResult.failure(
                request.request_id, ToolResultStatus.INVALID, "unknown_tool", "requested tool is not registered"
            )
        spec, handler = entry
        if cancellation.cancelled:
            return self._cancelled(request, cancellation)
        try:
            validated = validate_arguments(spec.input_schema, request.arguments)
            trusted_request = replace(request, arguments=validated)
            authorization.authorize(spec, trusted_request)
        except SchemaValidationError as exc:
            return ToolResult.failure(request.request_id, ToolResultStatus.INVALID, "invalid_arguments", str(exc))
        except AuthorizationError as exc:
            return ToolResult.failure(request.request_id, ToolResultStatus.DENIED, exc.code, str(exc))

        timeout = min(spec.timeout_seconds, timeout_seconds) if timeout_seconds is not None else spec.timeout_seconds
        if timeout <= 0:
            return ToolResult.failure(
                request.request_id, ToolResultStatus.TIMEOUT, "tool_timeout", "tool deadline was exhausted"
            )
        queue: Queue[ToolResult | BaseException] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                queue.put(handler(trusted_request, cancellation), block=False)
            except BaseException as exc:  # exceptions never cross the executor boundary
                queue.put(exc, block=False)

        Thread(target=invoke, name=f"metis-tool-{spec.name}", daemon=True).start()
        deadline = monotonic() + timeout
        while True:
            if cancellation.cancelled:
                return self._cancelled(request, cancellation)
            remaining = deadline - monotonic()
            if remaining <= 0:
                cancellation.cancel("tool timeout")
                return ToolResult.failure(
                    request.request_id, ToolResultStatus.TIMEOUT, "tool_timeout", "tool execution timed out"
                )
            try:
                outcome = queue.get(timeout=min(remaining, 0.05))
                break
            except Empty:
                continue

        if cancellation.cancelled:
            return self._cancelled(request, cancellation)
        if isinstance(outcome, BaseException):
            return ToolResult.failure(
                request.request_id, ToolResultStatus.ERROR, "tool_error", "tool execution failed"
            )
        if not isinstance(outcome, ToolResult):
            return ToolResult.failure(
                request.request_id, ToolResultStatus.ERROR, "invalid_tool_result", "tool returned an invalid result"
            )
        if outcome.request_id != request.request_id:
            return ToolResult.failure(
                request.request_id,
                ToolResultStatus.ERROR,
                "request_id_mismatch",
                "tool result did not match the request",
            )
        result_limit = spec.max_result_bytes
        if max_result_bytes is not None:
            result_limit = min(result_limit, max_result_bytes)
        return _bound_result(outcome, result_limit)

    @staticmethod
    def _cancelled(request: ToolRequest, cancellation: CancellationToken) -> ToolResult:
        return ToolResult.failure(
            request.request_id,
            ToolResultStatus.CANCELLED,
            "cancelled",
            cancellation.reason or "tool execution was cancelled",
        )


def _bound_result(result: ToolResult, limit: int) -> ToolResult:
    try:
        encoded = json.dumps(result.data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    except (TypeError, ValueError):
        return ToolResult.failure(
            result.request_id,
            ToolResultStatus.ERROR,
            "non_serializable_result",
            "tool result was not JSON serializable",
        )
    byte_count = len(encoded)
    if byte_count <= limit:
        return replace(result, byte_count=byte_count)
    if limit < 2:
        return replace(result, data="", truncated=True, byte_count=limit)
    preview = encoded[: max(0, limit - 2)].decode("utf-8", errors="ignore")
    while len(json.dumps(preview, ensure_ascii=False).encode("utf-8")) > limit:
        preview = preview[:-1]
    delivered_bytes = len(json.dumps(preview, ensure_ascii=False).encode("utf-8"))
    return replace(result, data=preview, truncated=True, byte_count=delivered_bytes)
