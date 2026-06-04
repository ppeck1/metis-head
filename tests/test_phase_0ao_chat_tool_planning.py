from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_chat_plan_task_persists_governed_plan_without_execution() -> None:
    client = _client()

    response = client.post("/metis/chat", json={"message": "plan task: summarize pyproject.toml"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_task_plan.v0.1"
    assert body["plan_queued"] is True
    assert body["proposal_queued"] is False
    assert body["tool_plan"]["plan"]["review_status"] == "pending"
    assert body["tool_plan"]["next_action"]["action"] == "needs_plan_review"
    assert body["state"]["tool_plan_queue"][0]["plan_id"] == body["tool_plan"]["plan"]["plan_id"]
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_plan_task_duplicate_returns_existing_plan() -> None:
    client = _client()
    first = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()
    second = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()

    assert first["tool_plan"]["plan"]["plan_id"] == second["tool_plan"]["plan"]["plan_id"]
    assert second["tool_plan"]["status"] == "plan_already_exists"
    assert len(second["state"]["tool_plan_queue"]) == 1


def test_chat_plan_task_agent_mode_still_only_queues_plan() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})

    response = client.post("/metis/chat", json={"message": "plan tool task: read pyproject.toml and summarize it"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_planner"
    assert body["plan_queued"] is True
    assert body["state"]["interaction_mode"] == "agent"
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_plan_task_requires_non_empty_task() -> None:
    client = _client()

    response = client.post("/metis/chat", json={"message": "plan task:"})

    assert response.status_code == 400
    assert "task is required" in response.json()["detail"]


def test_dashboard_chat_status_mentions_plan_queue() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "plan_queued" in dashboard
    assert "tool_planner" in dashboard
