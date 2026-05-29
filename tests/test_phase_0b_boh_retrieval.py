from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import metis_head.boh_retrieval as boh_retrieval
import metis_head.brain as brain
from metis_head.brain import app
from metis_head.llm_providers import LLMProviderError, LLMResult


def _enable_boh(monkeypatch, *, token: str = "test-retrieval-token", base_url: str = "http://127.0.0.1:8000") -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    monkeypatch.setenv("METIS_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_BOH_BASE_URL", base_url)
    monkeypatch.setenv("METIS_BOH_RETRIEVAL_TOKEN", token)
    monkeypatch.setenv("METIS_BOH_RETRIEVAL_MODE", "exploration")
    monkeypatch.setenv("METIS_BOH_LIMIT", "5")


def _afc_on(client: TestClient) -> None:
    client.post("/metis/event", json={"type": "button_event", "button": "afc", "state": True})


def _sample_boh_response() -> dict[str, Any]:
    return {
        "query": "what do we know",
        "count": 2,
        "context_packs": [
            {
                "doc_id": "doc-1",
                "title": "Governed Note One",
                "citation": "boh://doc-1",
                "text": "First governed context body.",
                "do_not_treat_as_canonical": True,
                "source_spans": [[0, 28]],
                "warnings": ["pack-level-warning"],
            },
            {
                "doc_id": "doc-2",
                "title": "Governed Note Two",
                "citation": "boh://doc-2",
                "text": "Second governed context body.",
            },
        ],
        "excluded_summary": [{"doc_id": "doc-9", "reason": "below_threshold"}],
        "warnings": ["top-level-warning"],
        "gate_result": {"allowed": True, "canon_eligible": False},
        "audit_context": {"trace": "abc"},
    }


def test_boh_disabled_chat_behavior_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    monkeypatch.delenv("METIS_BOH_ENABLED", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("BOH must not be contacted when disabled")

    monkeypatch.setattr(boh_retrieval, "_post_json", fail_if_called)
    client = TestClient(app)
    client.post("/metis/state/reset")
    _afc_on(client)
    response = client.post("/metis/chat", json={"message": "What do we know?"})
    assert response.status_code == 200
    body = response.json()
    assert body["source_state"] == "unsourced"
    assert "unsourced" in body["message"].lower()
    assert body["state"]["source_state"] == "unsourced"
    assert body["retrieval"]["enabled"] is False
    assert body["retrieval"]["attempted"] is False


def test_boh_not_called_when_source_grounding_off(monkeypatch) -> None:
    _enable_boh(monkeypatch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("BOH must not be contacted when source grounding is off")

    monkeypatch.setattr(boh_retrieval, "_post_json", fail_if_called)
    client = TestClient(app)
    client.post("/metis/state/reset")
    response = client.post("/metis/chat", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval"] is None


def test_boh_enabled_calls_retrieve_with_token(monkeypatch) -> None:
    _enable_boh(monkeypatch, token="secret-123")
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        calls.append({"url": url, "payload": payload, "headers": headers})
        return _sample_boh_response()

    monkeypatch.setattr(boh_retrieval, "_post_json", fake_post)
    client = TestClient(app)
    client.post("/metis/state/reset")
    _afc_on(client)
    response = client.post("/metis/chat", json={"message": "What do we know?"})
    assert response.status_code == 200
    assert len(calls) == 1
    call = calls[0]
    assert call["url"].endswith("/api/retrieve")
    assert call["headers"]["X-BOH-Retrieval-Token"] == "secret-123"
    assert "Authorization" not in call["headers"]
    assert call["payload"]["mode"] == "exploration"
    assert call["payload"]["limit"] == 5
    assert call["payload"]["query"] == "What do we know?"


def test_retrieved_context_injected_into_prompt(monkeypatch) -> None:
    _enable_boh(monkeypatch)
    monkeypatch.setattr(boh_retrieval, "_post_json", lambda *a, **k: _sample_boh_response())
    captured: dict[str, Any] = {}

    class CapturingProvider:
        provider_id = "capture"

        def generate(self, messages, state, options):
            captured["messages"] = messages
            return LLMResult(text="ok", provider="capture", model="capture-1")

    monkeypatch.setattr(brain, "provider_from_config", lambda options=None: CapturingProvider())
    client = TestClient(app)
    client.post("/metis/state/reset")
    _afc_on(client)
    response = client.post("/metis/chat", json={"message": "What do we know?"})
    assert response.status_code == 200
    joined = "\n".join(message["content"] for message in captured["messages"])
    assert "Governed Note One" in joined
    assert "boh://doc-1" in joined
    assert "First governed context body." in joined
    assert "do_not_treat_as_canonical" in joined


def test_source_grounded_marks_sourced_with_preserved_metadata(monkeypatch) -> None:
    _enable_boh(monkeypatch)
    monkeypatch.setattr(boh_retrieval, "_post_json", lambda *a, **k: _sample_boh_response())
    client = TestClient(app)
    client.post("/metis/state/reset")
    _afc_on(client)
    response = client.post("/metis/chat", json={"message": "What do we know?"})
    assert response.status_code == 200
    body = response.json()
    assert body["source_state"] == "sourced"
    assert body["state"]["source_state"] == "sourced"
    message_lower = body["message"].lower()
    # Must carry the authoritative sourced label and must NOT leak a stale unsourced label.
    assert "source label: sourced" in message_lower
    assert "unsourced" not in message_lower
    boh = body["metadata"]["boh"]
    assert boh["ok"] is True
    assert boh["count"] == 2
    assert boh["gate_result"] == {"allowed": True, "canon_eligible": False}
    assert "top-level-warning" in boh["warnings"]
    assert "pack-level-warning" in boh["warnings"]
    assert boh["excluded_summary"] == [{"doc_id": "doc-9", "reason": "below_threshold"}]
    assert boh["context_packs"][0]["do_not_treat_as_canonical"] is True
    assert boh["context_packs"][0]["source_spans"] == [[0, 28]]


def test_source_grounded_unsourced_when_no_context(monkeypatch) -> None:
    _enable_boh(monkeypatch)
    monkeypatch.setattr(boh_retrieval, "_post_json", lambda *a, **k: {"count": 0, "context_packs": []})
    client = TestClient(app)
    client.post("/metis/state/reset")
    _afc_on(client)
    response = client.post("/metis/chat", json={"message": "What do we know?"})
    assert response.status_code == 200
    body = response.json()
    assert body["source_state"] == "unsourced"
    assert "unsourced" in body["message"].lower()


def test_boh_unreachable_marks_degraded_not_silent(monkeypatch) -> None:
    _enable_boh(monkeypatch)

    def boom(*args, **kwargs):
        raise LLMProviderError("connection refused")

    monkeypatch.setattr(boh_retrieval, "_post_json", boom)
    client = TestClient(app)
    client.post("/metis/state/reset")
    _afc_on(client)
    response = client.post("/metis/chat", json={"message": "What do we know?"})
    assert response.status_code == 200
    body = response.json()
    assert body["source_state"] == "degraded"
    assert "degraded" in body["message"].lower()
    assert body["retrieval"]["ok"] is False
    assert body["retrieval"]["error"]
    # BOH unavailability must not be reported as an LLM failure.
    assert body["state"]["active_failure"] is None


def test_agent_mode_still_proposal_only_and_no_boh_mutation(monkeypatch) -> None:
    _enable_boh(monkeypatch)
    calls: list[str] = []

    def fake_post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        calls.append(url)
        return _sample_boh_response()

    monkeypatch.setattr(boh_retrieval, "_post_json", fake_post)
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "fm"})
    _afc_on(client)
    response = client.post("/metis/chat", json={"message": "Send an email to the team"})
    assert response.status_code == 200
    body = response.json()
    assert body["proposal_queued"] is True
    assert body["message"].startswith("Proposal only:")
    assert body["state"]["external_action_executed"] is False
    assert body["state"]["pending_approval_count"] == 1
    # Every BOH call must be the read-only retrieval endpoint; no mutation paths.
    assert calls and all(url.endswith("/api/retrieve") for url in calls)
