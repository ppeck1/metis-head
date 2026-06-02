from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_registry import build_tool_proposal_event, dry_run_tool


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_execution_before_review_is_blocked_and_audited() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "git.status_proposed", "arguments": {"repository": "."}}).json()
    proposal_id = _first_proposal_id(queued["state"])

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "operator clicked execute"})

    assert response.status_code == 200
    body = response.json()
    receipt = body["receipt"]
    assert body["status"] == "blocked_unreviewed"
    assert receipt["schema_version"] == "metis_execution_receipt.v0.1"
    assert receipt["execution_allowed"] is False
    assert receipt["operator_review_required"] is True
    assert body["state"]["external_action_executed"] is False
    assert len(body["state"]["execution_audit_log"]) == 1


def test_denied_proposal_execution_is_blocked() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "memory.propose", "arguments": {"memory_id": "m1", "summary": "x"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/deny", json={"reason": "not wanted"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["execution_status"] == "blocked_denied"
    assert receipt["execution_allowed"] is False
    assert response.json()["state"]["memory_promoted"] is False


def test_approved_side_effectful_proposal_remains_blocked() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read_proposed", "arguments": {"path": "B:\\secret.txt", "token": "abc"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "reviewed"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "still gated"})

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["execution_status"] == "blocked_side_effect"
    assert receipt["execution_allowed"] is False
    assert "dry_run_receipt" not in receipt
    assert "content" not in receipt
    assert "stdout" not in receipt
    assert receipt["redactions"] == ["secrets", "raw_file_contents", "command_output", "external_receipts"]


def test_approved_safe_tool_gets_dry_run_only_receipt() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})
    queued = client.post("/metis/tools/math.calculate/dry_run", json={"arguments": {"operation": "add", "a": 2, "b": 5}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "safe dry run"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 200
    body = response.json()
    receipt = body["receipt"]
    assert receipt["execution_status"] == "dry_run_only_not_executed"
    assert receipt["execution_allowed"] is False
    assert receipt["dry_run_receipt"]["status"] == "dry_run_complete"
    assert receipt["dry_run_receipt"]["result"]["result"] == 7.0
    assert body["state"]["external_action_executed"] is False


def test_execution_receipt_endpoint_returns_one_receipt() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "git.status_proposed", "arguments": {"repository": "."}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    receipt = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={}).json()["receipt"]

    listing = client.get("/metis/execution/receipts")
    detail = client.get(f"/metis/execution/receipts/{receipt['receipt_id']}")

    assert listing.status_code == 200
    assert listing.json()["receipt_count"] == 1
    assert detail.status_code == 200
    assert detail.json()["receipt"] == receipt


def test_execution_request_replay_is_deterministic() -> None:
    proposal_event = build_tool_proposal_event("math.calculate", {"operation": "multiply", "a": 3, "b": 4}, {"interaction_mode": "agent"})
    queued = reduce_metis_event(baseline_state(), proposal_event)
    proposal_id = _first_proposal_id(queued)
    review_event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": "approved",
        "reason": "fixed review",
        "reviewed_at": "2026-06-02T12:00:00Z",
    }
    execution_event = {
        "type": "execution_request",
        "proposal_id": proposal_id,
        "reason": "fixed execution request",
        "requested_at": "2026-06-02T12:01:00Z",
        "dry_run_receipt": dry_run_tool("math.calculate", {"operation": "multiply", "a": 3, "b": 4}),
    }

    first = replay_events(baseline_state(), [proposal_event, review_event, execution_event])
    second = replay_events(baseline_state(), [proposal_event, review_event, execution_event])

    assert first == second
    assert first["execution_audit_log"][0]["execution_status"] == "dry_run_only_not_executed"
    assert first["execution_audit_log"][0]["execution_allowed"] is False


def test_dashboard_contains_execution_audit_hooks() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "requestExecution" in dashboard
    assert "refreshExecutionReceipts" in dashboard
    assert "/metis/execution/receipts" in dashboard
