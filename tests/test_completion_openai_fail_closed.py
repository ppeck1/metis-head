from __future__ import annotations

import pytest

from metis_head import llm_providers
from metis_head.llm_providers import LLMProviderError, OpenAILLMProvider


def test_legacy_openai_provider_fails_before_network_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(llm_providers, "_post_json", lambda *args, **kwargs: calls.append((args, kwargs)))

    with pytest.raises(LLMProviderError, match="budgeted paid-provider adapter"):
        OpenAILLMProvider("test-key", "test-model").generate(
            [{"role": "user", "content": "hello"}], {}, {}
        )

    assert calls == []
