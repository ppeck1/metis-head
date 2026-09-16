from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import re
from typing import Any, Mapping

from metis_head.orchestration import AdapterContext, AdapterResponse, ToolSpec

from ._bounded_openai_compatible import (
    JsonTransport,
    OpenAICompatibleConfig,
    OpenAICompatibleToolAdapter as _BoundedAdapter,
    ProviderProtocolError,
)


_VALID_FUNCTION_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class OpenAICompatibleToolAdapter(_BoundedAdapter):
    """Public adapter that maps Metis dotted tool IDs to portable wire names."""

    def _payload(self, context: AdapterContext) -> dict[str, Any]:
        payload = super()._payload(context)
        wire_names = {spec.name: _wire_name(spec.name) for spec in context.tool_specs}
        for tool in payload["tools"]:
            original = tool["function"]["name"]
            tool["function"]["name"] = wire_names[original]
        for message in payload["messages"]:
            for call in message.get("tool_calls", []):
                original = call["function"]["name"]
                call["function"]["name"] = wire_names.get(original, original)
        return payload

    def _parse_response(self, response: Mapping[str, Any], specs: tuple[ToolSpec, ...]) -> AdapterResponse:
        decoded = deepcopy(response)
        choices = decoded.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
                original_by_wire = {_wire_name(spec.name): spec.name for spec in specs}
                for call in message["tool_calls"]:
                    if isinstance(call, dict) and isinstance(call.get("function"), dict):
                        name = call["function"].get("name")
                        call["function"]["name"] = original_by_wire.get(name, name)
        return super()._parse_response(decoded, specs)


def _wire_name(tool_name: str) -> str:
    if _VALID_FUNCTION_NAME.fullmatch(tool_name):
        return tool_name
    return f"metis_{sha256(tool_name.encode('utf-8')).hexdigest()[:24]}"


__all__ = [
    "JsonTransport",
    "OpenAICompatibleConfig",
    "OpenAICompatibleToolAdapter",
    "ProviderProtocolError",
]
