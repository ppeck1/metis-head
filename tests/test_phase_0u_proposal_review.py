from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_registry import build_tool_proposal_event


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_approve_safe_tool_proposal_reviews_without_execution() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})
    queued = client.post("/metis/tools/time.now/dry_run", json={"arguments": {"now": "2026-06-02T12:00:00Z"}}).json()
    proposal_id = _first_proposal_id(queued["state"])

    response = client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "operator reviewed"})

    assert response.status_code == 200
    body = response.json()
    proposal = body["proposal"]
    assert body["status"] == "proposal_approved"
    assert proposal["review_status"] == "approved"
    assert proposal["status"] == "reviewed"
    assert proposal["execution_allowed"] is False
    assert proposal["review_receipt"]["execution_allowed"] is False
    assert proposal["review_receipt"]["next_allowed_action"] == "dry_run"
    assert body["state"]["pending_approval_count"] == 0
    assert body["state"]["tool_queue_count"] == 0
    assert body["state"]["external_action_executed"] is False
    assert body["state"]["authority_state"] == "local_governed"


def test_approve_side_effectful_tool_remains_non_executable() -> None:
    client = _client()
    queued = client.post("/metis/tools/filesystem.read_proposed/execute", json={"arguments": {"path": "B:\\data.txt"}}).json()
    proposal_id = _first_proposal_id(queued["state"])

    response = client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "reviewed shape only"})

    assert response.status_code == 200
    body = response.json()
    receipt = body["review_receipt"]
    assert receipt["decision"] == "approved"
    assert receipt["execution_allowed"] is False
    assert receipt["execution_status"] == "not_executed"
    assert receipt["next_allowed_action"] == "none"
    assert body["state"]["external_action_executed"] is False
    assert "content" not in body["proposal"]


def test_deny_proposal_updates_counts_and_receipt() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "memory.propose", "arguments": {"memory_id": "m1", "summary": "review"}}).json()
    proposal_id = _first_proposal_id(queued["state"])

    response = client.post(f"/metis/proposals/{proposal_id}/deny", json={"reason": "not durable"})

    assert response.status_code == 200
    body = response.json()
    proposal = body["proposal"]
    assert body["status"] == "proposal_denied"
    assert proposal["proposal_type"] == "memory"
    assert proposal["review_status"] == "denied"
    assert proposal["review_reason"] == "not durable"
    assert proposal["review_receipt"]["decision"] == "denied"
    assert body["state"]["pending_approval_count"] == 0
    assert body["state"]["memory_proposal_count"] == 0
    assert body["state"]["memory_promoted"] is False


def test_review_unknown_or_already_reviewed_proposal_returns_error() -> None:
    client = _client()

    missing = client.post("/metis/proposals/nope/approve", json={})
    assert missing.status_code == 404

    queued = client.post("/metis/tools/propose", json={"tool_id": "git.status_proposed", "arguments": {"repository": "."}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    first = client.post(f"/metis/proposals/{proposal_id}/deny", json={})
    second = client.post(f"/metis/proposals/{proposal_id}/approve", json={})

    assert first.status_code == 200
    assert second.status_code == 409


def test_proposal_review_replay_is_deterministic() -> None:
    proposal_event = build_tool_proposal_event("filesystem.read_proposed", {"path": "B:\\data.txt"}, baseline_state())
    queued = reduce_metis_event(baseline_state(), proposal_event)
    proposal_id = _first_proposal_id(queued)
    review_event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": "approved",
        "reason": "fixed review",
        "reviewed_at": "2026-06-02T12:00:00Z",
    }

    first = replay_events(baseline_state(), [proposal_event, review_event])
    second = replay_events(baseline_state(), [proposal_event, review_event])

    assert first == second
    assert first["approval_queue"][0]["review_status"] == "approved"
    assert first["approval_queue"][0]["execution_allowed"] is False
    assert first["pending_approval_count"] == 0


def test_dashboard_contains_proposal_review_controls() -> None:
    client = _client()

    response = client.get("/")
    dashboard = response.text

    assert "proposalSelect" in dashboard
    assert "approveProposal" in dashboard
    assert "denyProposal" in dashboard
    assert "/metis/proposals/" in dashboard
