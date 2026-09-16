from __future__ import annotations

import json

import pytest

from metis_head.model_adapters.ollama_local import (
    BoundedUrllibJsonTransport,
    LocalProviderError,
    build_local_ollama_adapter,
)
from metis_head.orchestration import AdapterContext, CancellationToken


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": "Local answer"}}]}


def test_ollama_factory_targets_local_openai_compatible_path_without_metering() -> None:
    transport = FakeTransport()
    adapter = build_local_ollama_adapter(
        model="qwen-fixture",
        cancellation=CancellationToken(),
        transport=transport,
        max_output_tokens=64,
    )
    response = adapter.next_step(
        AdapterContext("local only", ({"role": "user", "content": "hello"},), (), (), 1)
    )

    assert response.text == "Local answer"
    assert transport.calls[0]["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert transport.calls[0]["payload"]["model"] == "qwen-fixture"
    assert transport.calls[0]["payload"]["max_tokens"] == 64


@pytest.mark.parametrize(
    "url",
    ["https://example.com/v1", "file:///tmp/ollama", "http://user:pass@localhost:11434/v1"],
)
def test_ollama_factory_rejects_non_loopback_or_credential_urls(url: str) -> None:
    with pytest.raises(ValueError):
        build_local_ollama_adapter(model="fixture", cancellation=CancellationToken(), base_url=url)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount: int) -> bytes:
        return self.payload[:amount]


class FakeOpener:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requests = []

    def open(self, req, timeout):
        self.requests.append((req, timeout))
        return FakeResponse(self.payload)


def test_bounded_transport_posts_json_and_bounds_response() -> None:
    valid = FakeOpener(json.dumps({"choices": []}).encode())
    transport = BoundedUrllibJsonTransport(opener=valid, max_response_bytes=100)
    result = transport.post_json(
        url="http://localhost:11434/v1/chat/completions",
        payload={"model": "fixture"},
        timeout_seconds=2,
        cancellation=CancellationToken(),
    )
    assert result == {"choices": []}
    assert valid.requests[0][0].method == "POST"
    assert valid.requests[0][1] == 2

    oversized = BoundedUrllibJsonTransport(opener=FakeOpener(b"x" * 20), max_response_bytes=10)
    with pytest.raises(LocalProviderError, match="response exceeded"):
        oversized.post_json(
            url="http://127.0.0.1:11434/v1/chat/completions",
            payload={},
            timeout_seconds=1,
            cancellation=CancellationToken(),
        )


def test_bounded_transport_rejects_request_before_open() -> None:
    opener = FakeOpener(b"{}")
    transport = BoundedUrllibJsonTransport(opener=opener, max_request_bytes=10)
    with pytest.raises(LocalProviderError, match="request exceeded"):
        transport.post_json(
            url="http://127.0.0.1:11434/v1/chat/completions",
            payload={"large": "x" * 20},
            timeout_seconds=1,
            cancellation=CancellationToken(),
        )
    assert opener.requests == []
