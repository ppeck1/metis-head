from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.tool_governance import TOOL_GATE_EVALUATION_VERSION


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_gate_evaluation_allows_human_safe_dry_run_without_mutation() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/governance/evaluate",
        json={"tool_id": "math.calculate", "request_type": "dry_run", "arguments": {"operation": "add", "a": 2, "b": 3}},
    )
    state = client.get("/metis/state").json()["state"]

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == TOOL_GATE_EVALUATION_VERSION
    assert body["decision"] == "dry_run_allowed"
    assert body["dry_run_allowed"] is True
    assert body["execution_allowed"] is False
    assert state["approval_queue"] == []
    assert state["external_action_executed"] is False


def test_tool_gate_evaluation_agent_mode_requires_proposal_even_for_safe_tool() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})

    response = client.post(
        "/metis/tools/governance/evaluate",
        json={"tool_id": "time.now", "request_type": "dry_run", "arguments": {"timezone": "UTC"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "queue_proposal_agent_mode"
    assert body["dry_run_allowed"] is False
    assert body["proposal_required"] is True
    assert body["autonomous_execution_allowed"] is False


def test_tool_gate_evaluation_execute_request_never_grants_execution() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/governance/evaluate",
        json={"tool_id": "math.calculate", "request_type": "execute", "arguments": {"operation": "multiply", "a": 4, "b": 5}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "dry_run_receipt_only"
    assert body["execution_allowed"] is False
    assert body["proposal_required"] is True


def test_tool_gate_evaluation_surfaces_read_only_gates() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/governance/evaluate",
        json={"tool_id": "filesystem.read", "request_type": "dry_run", "arguments": {"path": "README.md"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "queue_proposal_required"
    assert body["permission_mode"] == "approved_read_only"
    assert "repo_path_allowlist" in body["required_gates"]
    assert body["execution_allowed"] is False


def test_tool_gate_evaluation_rejects_invalid_arguments_and_dashboard_hook_exists() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/governance/evaluate",
        json={"tool_id": "math.calculate", "request_type": "dry_run", "arguments": {"operation": "add", "a": 2}},
    )
    dashboard = client.get("/").text

    assert response.status_code == 400
    assert "missing required argument" in response.json()["detail"]
    assert "evaluateToolGate" in dashboard
    assert "/metis/tools/governance/evaluate" in dashboard
