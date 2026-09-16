from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import re
from typing import Callable, Generic, Mapping, TypeVar


T = TypeVar("T")


class ResultStatus(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class ErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    ACCOUNT_NOT_CONFIGURED = "account_not_configured"
    PERMISSION_DENIED = "permission_denied"
    AUTH_EXPIRED = "auth_expired"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"


class Freshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ConnectorError:
    code: ErrorCode
    message: str
    retryable: bool = False
    retry_after_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class Provenance:
    provider: str
    service: str
    account_id: str
    resource_ids: tuple[str, ...] = ()
    source_links: tuple[str, ...] = ()
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    freshness: Freshness = Freshness.UNKNOWN


@dataclass(frozen=True, slots=True)
class ConnectorResult(Generic[T]):
    status: ResultStatus
    data: T | None
    provenance: Provenance
    error: ConnectorError | None = None
    truncated: bool = False
    next_page_token: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {ResultStatus.SUCCESS, ResultStatus.EMPTY}


class ConnectorTransportError(Exception):
    """A safe, provider-neutral transport failure.

    Transports should use a short non-secret message. Connector boundaries still
    redact common credential shapes before returning it to callers.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def select_transport(transports: Mapping[str, T], account_id: str) -> T:
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("account_id is required")
    try:
        return transports[account_id]
    except KeyError as exc:
        raise LookupError("account is not configured") from exc


_SECRET_PATTERNS = (
    re.compile(r"(?i)(access[_ -]?token|refresh[_ -]?token|authorization|api[_ -]?key|client[_ -]?secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+\-/]+=*"),
)


def safe_message(message: object, fallback: str = "provider request failed") -> str:
    if not isinstance(message, str) or not message.strip():
        return fallback
    value = message.strip()[:240]
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value


def error_from_exception(exc: Exception) -> ConnectorError:
    if isinstance(exc, ConnectorTransportError):
        return ConnectorError(
            code=exc.code,
            message=safe_message(exc.public_message),
            retryable=exc.retryable,
            retry_after_seconds=exc.retry_after_seconds,
        )
    if isinstance(exc, TimeoutError):
        return ConnectorError(ErrorCode.TIMEOUT, "provider request timed out", retryable=True)
    return ConnectorError(ErrorCode.UNAVAILABLE, "provider request failed", retryable=True)


def failed_result(
    *,
    provider: str,
    service: str,
    account_id: str,
    observed_at: datetime,
    error: ConnectorError,
) -> ConnectorResult[object]:
    status = ResultStatus.UNAVAILABLE if error.code in {
        ErrorCode.ACCOUNT_NOT_CONFIGURED,
        ErrorCode.AUTH_EXPIRED,
        ErrorCode.PERMISSION_DENIED,
        ErrorCode.TIMEOUT,
        ErrorCode.UNAVAILABLE,
    } else ResultStatus.ERROR
    return ConnectorResult(
        status=status,
        data=None,
        provenance=Provenance(
            provider=provider,
            service=service,
            account_id=account_id,
            observed_at=observed_at,
            freshness=Freshness.UNKNOWN,
        ),
        error=error,
    )
