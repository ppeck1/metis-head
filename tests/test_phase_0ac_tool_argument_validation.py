from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.tool_registry import TOOL_ARGUMENT_VALIDATION_VERSION, validate_tool_arguments


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_argument_validation_rejects_missing_required_argument() -> None:
    client = _client()

    response = client.post("/metis/tools/math.calculate/dry_run", json={"arguments": {"operation": "add", "a": 2}})

    assert response.status_code == 400
    assert "missing required argument" in response.json()["detail"]


def test_tool_argument_validation_rejects_wrong_primitive_type() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/text.summarize/dry_run",
        json={"arguments": {"text": "one two three", "max_words": "2"}},
    )

    assert response.status_code == 400
    assert "invalid argument type" in response.json()["detail"]


def test_tool_argument_validation_drops_secret_like_extras_without_persisting_value() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/propose",
        json={"tool_id": "fetch.url_proposed", "arguments": {"url": "https://example.com", "token": "abc123"}},
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["argument_validation"]["schema_version"] == TOOL_ARGUMENT_VALIDATION_VERSION
    assert proposal["argument_validation"]["warnings"] == ["dropped_sensitive_argument:token"]
    assert proposal["tool_arguments"] == {"url": "https://example.com"}
    assert "abc123" not in str(proposal)


def test_tool_argument_validation_rejects_non_sensitive_extras() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/propose",
        json={"tool_id": "fetch.url_proposed", "arguments": {"url": "https://example.com", "headers": {"x": "y"}}},
    )

    assert response.status_code == 400
    assert "unexpected argument" in response.json()["detail"]


def test_validate_tool_arguments_returns_sanitized_valid_shape() -> None:
    validation = validate_tool_arguments("time.now", {"now": "2026-06-03T12:00:00Z", "timezone": "UTC"})

    assert validation == {
        "schema_version": TOOL_ARGUMENT_VALIDATION_VERSION,
        "valid": True,
        "arguments": {"now": "2026-06-03T12:00:00Z", "timezone": "UTC"},
        "warnings": [],
    }
