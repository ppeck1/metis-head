from __future__ import annotations

from fastapi.testclient import TestClient

import metis_head.boh_retrieval as boh_retrieval
from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_boh_retrieve_proposed_registry_shape_is_proposal_only() -> None:
    client = _client()

    response = client.get("/metis/tools/boh.retrieve_proposed")

    assert response.status_code == 200
    tool = response.json()
    assert tool["tool_id"] == "boh.retrieve_proposed"
    assert tool["permission_mode"] == "proposal_only"
    assert tool["side_effect_class"] == "read_only"
    assert tool["lifecycle"]["lifecycle_label"] == "proposal_only"
    assert "future_only" in tool["lifecycle"]["lifecycle_tags"]
    assert tool["lifecycle"]["execution_request_allowed"] is False


def test_chat_routes_boh_search_to_proposal_without_live_retrieval(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    monkeypatch.setenv("METIS_BOH_ENABLED", "true")
    monkeypatch.setenv("METIS_BOH_RETRIEVAL_TOKEN", "test-token")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("BOH retrieval tool proposal must not call live BOH retrieval")

    monkeypatch.setattr(boh_retrieval, "_post_json", fail_if_called)
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "afc", "state": True})

    response = client.post("/metis/chat", json={"message": "search boh Metis tool governance"})

    assert response.status_code == 200
    body = response.json()
    proposal = body["state"]["approval_queue"][0]
    assert body["provider"] == "tool_router"
    assert body["model"] == "boh.retrieve_proposed"
    assert body["retrieval"] is None
    assert body["proposal_queued"] is True
    assert proposal["tool_id"] == "boh.retrieve_proposed"
    assert proposal["tool_arguments"] == {"query": "Metis tool governance", "mode": "exploration", "limit": 5}
    assert proposal["execution_allowed"] is False
    assert body["state"]["external_action_executed"] is False


def test_boh_retrieve_proposed_blocks_after_review_without_boh_call(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("blocked BOH tool execution must not call live BOH retrieval")

    monkeypatch.setattr(boh_retrieval, "_post_json", fail_if_called)
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "boh.retrieve_proposed", "arguments": {"query": "Metis source grounding"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "reviewed proposal shape only"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "confirm blocked"})

    assert response.status_code == 200
    body = response.json()
    assert body["receipt"]["tool_id"] == "boh.retrieve_proposed"
    assert body["receipt"]["execution_status"] == "blocked_side_effect"
    assert body["receipt"]["execution_allowed"] is False
    assert body["state"]["external_action_executed"] is False
