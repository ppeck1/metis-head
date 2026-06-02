from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_git_status_registry_lane_is_present() -> None:
    client = _client()

    response = client.get("/metis/tools")

    assert response.status_code == 200
    tools = {tool["tool_id"]: tool for tool in response.json()["tools"]}
    assert tools["git.status"]["permission_mode"] == "approved_read_only"
    assert tools["git.status"]["side_effect_class"] == "read_only"
    assert tools["git.status_proposed"]["permission_mode"] == "proposal_only"


def test_approved_git_status_executes_read_only_with_safe_receipt() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "git.status", "arguments": {"repository": "."}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "approved current repo status"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "operator requested status"})

    assert response.status_code == 200
    body = response.json()
    receipt = body["receipt"]
    assert body["status"] == "executed_read_only"
    assert receipt["tool_id"] == "git.status"
    assert receipt["policy_decision"] == "approved_read_only"
    assert receipt["execution_allowed"] is False
    assert receipt["output_summary"]["preview"]["branch"].startswith("##")
    assert "stdout" not in receipt
    assert "command_output" in receipt["redactions"]
    assert body["state"]["external_action_executed"] is False


def test_git_status_requires_allowlisted_repository() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "git.status", "arguments": {"repository": "B:\\"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "not allowed"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"]


def test_legacy_git_status_proposed_remains_blocked_after_approval() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "git.status_proposed", "arguments": {"repository": "."}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "legacy proposal"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["execution_status"] == "blocked_side_effect"
    assert receipt["execution_allowed"] is False


def test_policy_marks_git_status_active() -> None:
    client = _client()

    policy = client.get("/metis/execution/policy").json()
    lanes = {lane["lane"]: lane["status"] for lane in policy["candidate_lanes"]}

    assert lanes["git.status"] == "active_approved_read_only"
    assert lanes["filesystem.read"] == "active_approved_read_only"
    assert lanes["fetch.url"] == "future_only"
