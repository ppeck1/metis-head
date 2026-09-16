from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Event, Lock
from typing import Any, Mapping, Protocol, Sequence


class AccessMode(StrEnum):
    READ = "read"
    WRITE = "write"


class ToolResultStatus(StrEnum):
    SUCCESS = "success"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    DENIED = "denied"
    INVALID = "invalid"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class FreshnessStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Freshness:
    status: FreshnessStatus = FreshnessStatus.UNKNOWN
    observed_at: datetime | None = None
    valid_until: datetime | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        for value in (self.observed_at, self.valid_until):
            if value is not None and value.tzinfo is None:
                raise ValueError("freshness timestamps must be timezone-aware")


@dataclass(frozen=True)
class Provenance:
    source_id: str
    source_label: str
    account_id: str | None = None
    resource_id: str | None = None
    source_uri: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.source_label.strip():
            raise ValueError("provenance source identity is required")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    input_schema: Mapping[str, Any]
    access: AccessMode
    required_scopes: frozenset[str] = field(default_factory=frozenset)
    account_required: bool = False
    resource_argument: str | None = None
    timeout_seconds: float = 10.0
    max_result_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("tool name and version are required")
        if self.timeout_seconds <= 0:
            raise ValueError("tool timeout must be positive")
        if self.max_result_bytes <= 0:
            raise ValueError("tool result bound must be positive")
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input schema must describe an object")


@dataclass(frozen=True)
class ToolRequest:
    request_id: str
    session_id: str
    turn_id: str
    tool_name: str
    tool_version: str
    arguments: Mapping[str, Any]
    account_id: str | None = None
    granted_scopes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for field_name in ("request_id", "session_id", "turn_id", "tool_name", "tool_version"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class ToolResult:
    request_id: str
    status: ToolResultStatus
    data: Any = None
    provenance: tuple[Provenance, ...] = ()
    freshness: Freshness = field(default_factory=Freshness)
    error_code: str | None = None
    message: str | None = None
    retry_after_seconds: float | None = None
    truncated: bool = False
    byte_count: int = 0

    @property
    def ok(self) -> bool:
        return self.status in {ToolResultStatus.SUCCESS, ToolResultStatus.EMPTY}

    @classmethod
    def failure(
        cls,
        request_id: str,
        status: ToolResultStatus,
        error_code: str,
        message: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> "ToolResult":
        if status in {ToolResultStatus.SUCCESS, ToolResultStatus.EMPTY}:
            raise ValueError("failure result must use a failure status")
        return cls(
            request_id=request_id,
            status=status,
            error_code=error_code,
            message=message,
            retry_after_seconds=retry_after_seconds,
        )


class CancellationToken:
    """Thread-safe cooperative cancellation shared across one turn."""

    def __init__(self) -> None:
        self._event = Event()
        self._lock = Lock()
        self._reason: str | None = None

    def cancel(self, reason: str = "cancelled") -> None:
        with self._lock:
            self._reason = self._reason or reason
            self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    tool_name: str
    tool_version: str
    arguments: Mapping[str, Any]
    account_id: str | None = None


@dataclass(frozen=True)
class ToolExchange:
    call: ToolCall
    result: ToolResult
    # The adapter must preserve this boundary and must not promote data to instructions.
    trust: str = "untrusted_tool_data"


@dataclass(frozen=True)
class AdapterContext:
    system_instructions: str
    conversation: tuple[Mapping[str, str], ...]
    tool_specs: tuple[ToolSpec, ...]
    exchanges: tuple[ToolExchange, ...]
    remaining_rounds: int


@dataclass(frozen=True)
class AdapterResponse:
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.text) == bool(self.tool_calls):
            raise ValueError("adapter response must contain either final text or tool calls")


class ModelAdapter(Protocol):
    def next_step(self, context: AdapterContext) -> AdapterResponse: ...


class ToolHandler(Protocol):
    def __call__(self, request: ToolRequest, cancellation: CancellationToken) -> ToolResult: ...


@dataclass(frozen=True)
class OrchestrationOutcome:
    text: str | None
    exchanges: tuple[ToolExchange, ...]
    stop_reason: str
    rounds: int


def utc_now() -> datetime:
    return datetime.now(UTC)
