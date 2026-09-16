from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from math import ceil
from typing import Any, Mapping, Protocol

from metis_head.orchestration import (
    AdapterContext,
    AdapterResponse,
    CancellationToken,
    ToolCall,
    ToolExchange,
    ToolSpec,
)
from metis_head.usage.paid_calls import PaidCallExecutor, TokenUsage


class ProviderProtocolError(RuntimeError):
    pass


class JsonTransport(Protocol):
    """Authentication and I/O live outside the wire adapter."""

    def post_json(
        self,
        *,
        url: str,
        payload: Mapping[str, Any],
        timeout_seconds: float,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    provider: str
    model: str
    base_url: str
    max_output_tokens: int = 512
    max_output_characters: int = 16_384
    max_tool_calls_per_response: int = 4
    max_tool_argument_bytes: int = 16_384
    request_timeout_seconds: float = 30.0
    maximum_input_tokens: int = 16_000

    def __post_init__(self) -> None:
        if not self.provider or not self.model or not self.base_url:
            raise ValueError("provider, model, and base URL are required")
        bounds = (
            self.max_output_tokens,
            self.max_output_characters,
            self.max_tool_calls_per_response,
            self.max_tool_argument_bytes,
            self.maximum_input_tokens,
        )
        if min(bounds) <= 0 or self.request_timeout_seconds <= 0:
            raise ValueError("provider bounds must be positive")


class OpenAICompatibleToolAdapter:
    """OpenAI-compatible Chat Completions tool adapter with injected transport."""

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        transport: JsonTransport,
        paid_calls: PaidCallExecutor,
        cancellation: CancellationToken,
    ) -> None:
        self._config = config
        self._transport = transport
        self._paid_calls = paid_calls
        self._cancellation = cancellation

    def next_step(self, context: AdapterContext) -> AdapterResponse:
        payload = self._payload(context)
        estimated_input = _heuristic_token_estimate(payload)
        maximum_usage = TokenUsage(estimated_input, self._config.max_output_tokens)

        receipt = self._paid_calls.execute(
            provider=self._config.provider,
            model=self._config.model,
            maximum_usage=maximum_usage,
            cancellation=self._cancellation,
            call=lambda: self._transport.post_json(
                url=f"{self._config.base_url.rstrip('/')}/chat/completions",
                payload=payload,
                timeout_seconds=self._config.request_timeout_seconds,
                cancellation=self._cancellation,
            ),
            usage_from_result=_reported_usage,
            estimate_metadata={
                "input_accounting": "heuristic_estimate_not_hard_cap",
                "input_estimate_tokens": estimated_input,
                "configured_estimate_limit": self._config.maximum_input_tokens,
                "output_limit_tokens": self._config.max_output_tokens,
            },
        )
        return self._parse_response(receipt.value, context.tool_specs)

    def _payload(self, context: AdapterContext) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if context.system_instructions:
            messages.append({"role": "system", "content": context.system_instructions})
        messages.extend({"role": item["role"], "content": item["content"]} for item in context.conversation)
        for exchange in context.exchanges:
            messages.extend(_exchange_messages(exchange))
        return {
            "model": self._config.model,
            "messages": messages,
            "tools": [_tool_definition(spec) for spec in context.tool_specs],
            "tool_choice": "auto",
            "max_tokens": self._config.max_output_tokens,
        }

    def _parse_response(self, response: Mapping[str, Any], specs: tuple[ToolSpec, ...]) -> AdapterResponse:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ProviderProtocolError("provider response did not contain choices[0]")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise ProviderProtocolError("provider response did not contain a message")
        raw_calls = message.get("tool_calls") or []
        if raw_calls:
            if not isinstance(raw_calls, list) or len(raw_calls) > self._config.max_tool_calls_per_response:
                raise ProviderProtocolError("provider returned too many tool calls")
            by_name = {spec.name: spec for spec in specs}
            calls = tuple(self._parse_call(item, by_name) for item in raw_calls)
            return AdapterResponse(tool_calls=calls)
        content = message.get("content")
        if not isinstance(content, str) or not content:
            raise ProviderProtocolError("provider response contained neither text nor tool calls")
        if len(content) > self._config.max_output_characters:
            raise ProviderProtocolError("provider text exceeded the configured output bound")
        return AdapterResponse(text=content)

    def _parse_call(self, item: Any, specs: Mapping[str, ToolSpec]) -> ToolCall:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
            raise ProviderProtocolError("tool call is missing an id")
        function = item.get("function")
        if not isinstance(function, Mapping) or not isinstance(function.get("name"), str):
            raise ProviderProtocolError("tool call is missing a function name")
        name = function["name"]
        spec = specs.get(name)
        if spec is None:
            raise ProviderProtocolError("provider requested an unknown tool")
        raw_arguments = function.get("arguments")
        if not isinstance(raw_arguments, str) or len(raw_arguments.encode("utf-8")) > self._config.max_tool_argument_bytes:
            raise ProviderProtocolError("tool call arguments are missing or oversized")
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError("tool call arguments are not valid JSON") from exc
        if not isinstance(arguments, dict):
            raise ProviderProtocolError("tool call arguments must be an object")
        account_id = arguments.pop("account_id", None)
        if account_id is not None and not isinstance(account_id, str):
            raise ProviderProtocolError("tool account_id must be a string")
        return ToolCall(item["id"], name, spec.version, arguments, account_id)


def _tool_definition(spec: ToolSpec) -> dict[str, Any]:
    schema = dict(spec.input_schema)
    if spec.account_required:
        properties = dict(schema.get("properties", {}))
        properties["account_id"] = {"type": "string", "description": "Explicit connected account identifier"}
        schema["properties"] = properties
        schema["required"] = list(dict.fromkeys([*schema.get("required", []), "account_id"]))
    return {"type": "function", "function": {"name": spec.name, "description": spec.description, "parameters": schema}}


def _exchange_messages(exchange: ToolExchange) -> list[dict[str, Any]]:
    arguments = dict(exchange.call.arguments)
    if exchange.call.account_id is not None:
        arguments["account_id"] = exchange.call.account_id
    assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": exchange.call.call_id,
                "type": "function",
                "function": {"name": exchange.call.tool_name, "arguments": json.dumps(arguments, sort_keys=True)},
            }
        ],
    }
    result = exchange.result
    tool_content = {
        "status": result.status.value,
        "data": result.data,
        "provenance": [asdict(item) for item in result.provenance],
        "freshness": asdict(result.freshness),
        "truncated": result.truncated,
        "error_code": result.error_code,
    }
    tool_message = {
        "role": "tool",
        "tool_call_id": exchange.call.call_id,
        "content": json.dumps(tool_content, sort_keys=True, default=str),
    }
    return [assistant, tool_message]


def _reported_usage(response: Mapping[str, Any]) -> TokenUsage | None:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if not isinstance(prompt, int) or isinstance(prompt, bool) or prompt < 0:
        return None
    if not isinstance(completion, int) or isinstance(completion, bool) or completion < 0:
        return None
    return TokenUsage(prompt, completion)


def _heuristic_token_estimate(payload: Mapping[str, Any]) -> int:
    """Return a conservative sizing heuristic, not a tokenizer-backed bound."""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return max(1, ceil(len(encoded) / 3))


# Compatibility for existing internal imports. Callers must not describe this
# value as a tokenizer-enforced hard cap.
_estimate_tokens = _heuristic_token_estimate
