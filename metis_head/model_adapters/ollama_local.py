from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib import error, parse, request

from metis_head.orchestration import CancellationToken

from .openai_compatible import JsonTransport, OpenAICompatibleConfig, OpenAICompatibleToolAdapter


class LocalProviderError(RuntimeError):
    pass


class LocalCallCancelled(LocalProviderError):
    pass


@dataclass(frozen=True)
class LocalCallReceipt:
    value: Any


class UnmeteredLocalCallExecutor:
    """PaidCallExecutor-compatible boundary for explicitly local inference."""

    def execute(
        self,
        *,
        provider: str,
        model: str,
        maximum_usage: Any,
        cancellation: CancellationToken,
        call: Callable[[], Any],
        usage_from_result: Callable[[Any], Any],
        estimate_metadata: Mapping[str, Any] | None = None,
    ) -> LocalCallReceipt:
        del provider, model, maximum_usage, usage_from_result, estimate_metadata
        if cancellation.cancelled:
            raise LocalCallCancelled(cancellation.reason or "local call cancelled before dispatch")
        value = call()
        if cancellation.cancelled:
            raise LocalCallCancelled(cancellation.reason or "local call cancelled after dispatch")
        return LocalCallReceipt(value)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalProviderError("local provider redirects are not allowed")


class BoundedUrllibJsonTransport:
    """Loopback-only JSON transport with fixed request and response bounds."""

    def __init__(
        self,
        *,
        max_request_bytes: int = 512 * 1024,
        max_response_bytes: int = 2 * 1024 * 1024,
        opener: Any | None = None,
    ) -> None:
        if min(max_request_bytes, max_response_bytes) <= 0:
            raise ValueError("transport bounds must be positive")
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes
        self._opener = opener or request.build_opener(_NoRedirect())

    def post_json(
        self,
        *,
        url: str,
        payload: Mapping[str, Any],
        timeout_seconds: float,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]:
        _validate_loopback_url(url)
        if timeout_seconds <= 0:
            raise ValueError("transport timeout must be positive")
        if cancellation.cancelled:
            raise LocalCallCancelled(cancellation.reason or "local request cancelled")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > self._max_request_bytes:
            raise LocalProviderError("local provider request exceeded its size bound")
        req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self._opener.open(req, timeout=timeout_seconds) as response:
                data = response.read(self._max_response_bytes + 1)
        except LocalProviderError:
            raise
        except error.HTTPError as exc:
            raise LocalProviderError(f"local provider returned HTTP {exc.code}") from exc
        except (error.URLError, OSError, TimeoutError) as exc:
            raise LocalProviderError("local provider request failed") from exc
        if cancellation.cancelled:
            raise LocalCallCancelled(cancellation.reason or "local request cancelled")
        if len(data) > self._max_response_bytes:
            raise LocalProviderError("local provider response exceeded its size bound")
        try:
            decoded = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalProviderError("local provider returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise LocalProviderError("local provider response must be a JSON object")
        return decoded


def build_local_ollama_adapter(
    *,
    model: str,
    cancellation: CancellationToken,
    base_url: str = "http://127.0.0.1:11434/v1",
    transport: JsonTransport | None = None,
    max_output_tokens: int = 512,
    maximum_input_tokens: int = 16_000,
    request_timeout_seconds: float = 30.0,
) -> OpenAICompatibleToolAdapter:
    """Compose Ollama's local OpenAI-compatible chat-completions path."""
    _validate_loopback_url(base_url)
    return OpenAICompatibleToolAdapter(
        OpenAICompatibleConfig(
            provider="ollama-local",
            model=model,
            base_url=base_url,
            max_output_tokens=max_output_tokens,
            maximum_input_tokens=maximum_input_tokens,
            request_timeout_seconds=request_timeout_seconds,
        ),
        transport or BoundedUrllibJsonTransport(),
        UnmeteredLocalCallExecutor(),  # type: ignore[arg-type]
        cancellation,
    )


def _validate_loopback_url(url: str) -> None:
    parsed = parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("local provider URL must use HTTP or HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("local provider URL cannot contain credentials, query, or fragment")
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("local provider URL must target loopback")
