from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_chat_tool_plan_status_reports_latest_next_gate() -> None:
    client = _client()
    planned = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()
    plan_id = planned["tool_plan"]["plan"]["plan_id"]

    response = client.post("/metis/chat", json={"message": "what's next for my tool plan?"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_plan_status.v0.1"
    assert body["tool_plan"]["plan"]["plan_id"] == plan_id
    assert body["tool_plan"]["next_action"]["action"] == "needs_plan_review"
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False
    assert "Chat cannot approve plans" in body["message"]


def test_chat_tool_plan_status_can_target_explicit_plan_id() -> None:
    client = _client()
    first = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()
    second = client.post("/metis/chat", json={"message": "plan task: summarize pyproject.toml"}).json()
    first_plan_id = first["tool_plan"]["plan"]["plan_id"]
    second_plan_id = second["tool_plan"]["plan"]["plan_id"]

    response = client.post("/metis/chat", json={"message": f"tool plan status plan_id={first_plan_id}"})

    assert response.status_code == 200
    body = response.json()
    assert body["tool_plan"]["plan"]["plan_id"] == first_plan_id
    assert body["tool_plan"]["plan"]["plan_id"] != second_plan_id
    assert body["tool_plan"]["next_action"]["action"] == "needs_plan_review"


def test_chat_tool_plan_advance_stops_at_plan_review_gate() -> None:
    client = _client()
    planned = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()
    plan_id = planned["tool_plan"]["plan"]["plan_id"]

    response = client.post("/metis/chat", json={"message": "advance tool plan"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_plan_advance.v0.1"
    assert body["tool_plan"]["plan"]["plan_id"] == plan_id
    assert body["tool_plan"]["advance"]["status"] == "waiting"
    assert body["tool_plan"]["next_action"]["action"] == "needs_plan_review"
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_tool_plan_advance_queues_steps_after_plan_approval_only() -> None:
    client = _client()
    planned = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()
    plan_id = planned["tool_plan"]["plan"]["plan_id"]
    client.post(f"/metis/tools/plans/{plan_id}/approve", json={"reason": "reviewed plan"})

    response = client.post("/metis/chat", json={"message": f"continue tool plan {plan_id}"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_plan_advance.v0.1"
    assert body["tool_plan"]["advance"]["status"] == "advanced"
    assert body["tool_plan"]["advance"]["advanced_action"]["action"] == "can_queue_step_proposals"
    assert body["tool_plan"]["next_action"]["action"] == "needs_step_proposal_review"
    assert body["state"]["pending_approval_count"] == 1
    assert body["state"]["external_action_executed"] is False


def test_chat_tool_plan_status_unknown_plan_returns_404() -> None:
    client = _client()

    response = client.post("/metis/chat", json={"message": "tool plan status plan_missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "tool plan not found"
