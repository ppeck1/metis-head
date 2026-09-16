from __future__ import annotations

from metis_head.orchestration import AdapterContext, AdapterResponse

from ._openai_compatible_impl import (
    JsonTransport,
    OpenAICompatibleConfig,
    OpenAICompatibleToolAdapter as _OpenAICompatibleToolAdapter,
    ProviderProtocolError,
    _heuristic_token_estimate,
)


class OpenAICompatibleToolAdapter(_OpenAICompatibleToolAdapter):
    """Bounded public adapter layered over the OpenAI-compatible wire codec."""

    def next_step(self, context: AdapterContext) -> AdapterResponse:
        if _heuristic_token_estimate(self._payload(context)) > self._config.maximum_input_tokens:
            raise ProviderProtocolError(
                "provider heuristic input-token estimate exceeded the configured estimate limit; "
                "this is not a tokenizer-enforced hard cap"
            )
        return super().next_step(context)


__all__ = [
    "JsonTransport",
    "OpenAICompatibleConfig",
    "OpenAICompatibleToolAdapter",
    "ProviderProtocolError",
]
