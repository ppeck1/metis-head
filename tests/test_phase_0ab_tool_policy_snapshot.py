from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.tool_policy_snapshot import TOOL_POLICY_SNAPSHOT_VERSION


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_policy_snapshot_composes_contract_policy_queue_and_receipts() -> None:
    client = _client()

    snapshot = client.get("/metis/tools/policy_snapshot").json()

    assert snapshot["schema_version"] == TOOL_POLICY_SNAPSHOT_VERSION
    assert snapshot["contract"]["schema_version"] == "metis_tool_contract.v0.1"
    assert snapshot["read_only_policy"]["schema_version"] == "metis_read_only_execution_policy.v0.1"
    assert snapshot["proposal_queue"]["total_count"] == 0
    assert snapshot["execution_audit"]["receipt_count"] == 0
    assert snapshot["authority"]["execution_authority_changed"] is False
    assert snapshot["authority"]["autonomous_execution_allowed"] is False


def test_tool_policy_snapshot_reflects_live_proposals_and_execution_receipts() -> None:
    client = _client()
    queued = client.post(
        "/metis/tools/propose",
        json={"tool_id": "time.now", "arguments": {"timezone": "UTC"}, "reason": "snapshot coverage"},
    ).json()
    proposal_id = queued["proposal"]["proposal_id"]
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "safe read-only check"})
    client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "operator snapshot test"})

    snapshot = client.get("/metis/tools/policy_snapshot").json()

    assert snapshot["proposal_queue"]["total_count"] == 1
    assert snapshot["proposal_queue"]["pending_count"] == 0
    assert snapshot["proposal_queue"]["review_counts"] == {"approved": 1}
    assert snapshot["execution_audit"]["receipt_count"] == 1
    assert snapshot["execution_audit"]["status_counts"] == {"executed_read_only": 1}
    assert snapshot["authority"]["execution_authority_changed"] is False
    assert snapshot["authority"]["external_action_executed"] is False


def test_tool_policy_snapshot_endpoint_and_dashboard_hook_are_available() -> None:
    client = _client()

    response = client.get("/metis/tools/policy_snapshot")
    dashboard = client.get("/").text

    assert response.status_code == 200
    assert response.json()["schema_version"] == TOOL_POLICY_SNAPSHOT_VERSION
    assert "refreshToolPolicySnapshot" in dashboard
    assert "/metis/tools/policy_snapshot" in dashboard
