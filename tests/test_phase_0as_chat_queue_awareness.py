from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_chat_pending_approval_summary_is_observational() -> None:
    client = _client()
    queued = client.post("/metis/chat", json={"message": "git status"}).json()
    proposal = queued["tool"]["proposal"]

    response = client.post("/metis/chat", json={"message": "what needs approval?"})

    assert response.status_code == 200
    body = response.json()
    summary = body["queue_status"]
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_approval_status.v0.1"
    assert body["proposal_queued"] is False
    assert summary["status"] == "approval_queue_status"
    assert summary["pending_count"] == 1
    assert summary["pending_proposals"][0]["proposal_id"] == proposal["proposal_id"]
    assert summary["pending_proposals"][0]["tool_id"] == "git.status"
    assert summary["pending_proposals"][0]["execution_allowed"] is False
    assert summary["pending_proposals"][0]["argument_keys"] == ["repository"]
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False
    assert "cannot approve" in body["message"]


def test_chat_pending_approval_summary_handles_empty_queue() -> None:
    client = _client()

    response = client.post("/metis/chat", json={"message": "pending approvals"})

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "metis_tool_approval_status.v0.1"
    assert body["queue_status"]["pending_count"] == 0
    assert body["queue_status"]["total_count"] == 0
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_receipt_summary_is_safe_and_observational() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})
    queued = client.post("/metis/tools/math.calculate/dry_run", json={"arguments": {"operation": "add", "a": 2, "b": 5}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "reviewed safe dry run"})
    receipt = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "operator requested receipt"}).json()["receipt"]

    response = client.post("/metis/chat", json={"message": "receipt summary"})

    assert response.status_code == 200
    body = response.json()
    summary = body["queue_status"]
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_receipt_status.v0.1"
    assert summary["status"] == "execution_receipt_status"
    assert summary["receipt_count"] == 1
    assert summary["receipts"][0]["receipt_id"] == receipt["receipt_id"]
    assert summary["receipts"][0]["tool_id"] == "math.calculate"
    assert summary["receipts"][0]["execution_status"] == "dry_run_only_not_executed"
    assert summary["receipts"][0]["execution_allowed"] is False
    assert "dry_run_receipt" not in summary["receipts"][0]
    assert "result" not in summary["receipts"][0]
    assert "Raw file contents" in body["message"]
    assert body["state"]["external_action_executed"] is False


def test_chat_receipt_summary_handles_no_receipts() -> None:
    client = _client()

    response = client.post("/metis/chat", json={"message": "what receipts do we have?"})

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "metis_tool_receipt_status.v0.1"
    assert body["queue_status"]["receipt_count"] == 0
    assert body["queue_status"]["receipts"] == []
    assert body["state"]["execution_audit_log"] == []


def test_chat_queue_status_does_not_request_execution_for_approved_proposal() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "time.now", "arguments": {"now": "2026-06-04T12:00:00Z"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "reviewed"})

    response = client.post("/metis/chat", json={"message": "proposal status"})

    assert response.status_code == 200
    body = response.json()
    assert body["queue_status"]["pending_count"] == 0
    assert body["queue_status"]["counts_by_review_status"]["approved"] == 1
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False
