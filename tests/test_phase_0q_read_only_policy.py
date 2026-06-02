from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.execution_policy import READ_ONLY_EXECUTION_POLICY_VERSION, read_only_execution_policy


ROOT = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_read_only_execution_policy_endpoint_is_available() -> None:
    client = _client()

    response = client.get("/metis/execution/policy")

    assert response.status_code == 200
    policy = response.json()
    assert policy["schema_version"] == READ_ONLY_EXECUTION_POLICY_VERSION
    assert policy["execution_enabled"] is False
    assert policy["phase"] == "0Q"
    assert "filesystem.read" in {lane["lane"] for lane in policy["candidate_lanes"]}
    assert "review_status=approved" in policy["required_gates"]
    assert "full_file_contents" in policy["redaction_requirements"]


def test_read_only_execution_policy_doc_matches_structured_contract() -> None:
    policy = read_only_execution_policy()
    doc = (ROOT / policy["contract_path"]).read_text(encoding="utf-8")

    assert "Read-Only Execution Policy v0.1" in doc
    assert "Phase 0L activates only the internal `time.now` lane" in doc
    assert "`filesystem.read`" in doc
    assert "`git.status`" in doc
    assert "`fetch.url`" in doc
    assert "`boh.retrieve`" in doc
    assert "No shell execution" in doc


def test_phase_0q_policy_does_not_enable_side_effectful_execution() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read_proposed", "arguments": {"path": "B:\\secret.txt"}}).json()
    proposal_id = queued["state"]["approval_queue"][0]["proposal_id"]
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "policy review only"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "try after policy"})

    assert response.status_code == 200
    body = response.json()
    assert body["receipt"]["execution_status"] == "blocked_side_effect"
    assert body["receipt"]["execution_allowed"] is False
    assert body["state"]["external_action_executed"] is False


def test_dashboard_contains_execution_policy_hook() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "refreshExecutionPolicy" in dashboard
    assert "/metis/execution/policy" in dashboard
