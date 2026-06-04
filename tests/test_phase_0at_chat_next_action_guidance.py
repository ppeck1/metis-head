from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_chat_next_action_guides_pending_proposal_review_without_mutation() -> None:
    client = _client()
    queued = client.post("/metis/chat", json={"message": "git status"}).json()
    proposal_id = queued["tool"]["proposal"]["proposal_id"]

    response = client.post("/metis/chat", json={"message": "what should I do next?"})

    assert response.status_code == 200
    body = response.json()
    instruction = body["next_action"]
    assert body["provider"] == "tool_planner"
    assert body["model"] == "metis_tool_next_action.v0.1"
    assert instruction["recommended_action"] == "review_proposal"
    assert instruction["target"] == {"type": "proposal", "id": proposal_id}
    assert instruction["api_instruction"]["approve"] == f"POST /metis/proposals/{proposal_id}/approve"
    assert instruction["api_instruction"]["deny"] == f"POST /metis/proposals/{proposal_id}/deny"
    assert instruction["execution_allowed"] is False
    assert instruction["chat_may_perform_action"] is False
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False
    assert "Chat cannot perform this action" in body["message"]


def test_chat_next_action_guides_approved_proposal_execution_request_without_creating_receipt() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "time.now", "arguments": {"now": "2026-06-04T12:00:00Z"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "reviewed"})

    response = client.post("/metis/chat", json={"message": f"how do I request execution proposal_id={proposal_id}?"})

    assert response.status_code == 200
    body = response.json()
    instruction = body["next_action"]
    assert instruction["recommended_action"] == "request_execution_receipt"
    assert instruction["target"] == {"type": "proposal", "id": proposal_id}
    assert instruction["api_instruction"]["request_execution"] == f"POST /metis/proposals/{proposal_id}/request_execution"
    assert body["state"]["approval_queue"][0]["review_status"] == "approved"
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_next_action_guides_pending_plan_review() -> None:
    client = _client()
    planned = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()
    plan_id = planned["tool_plan"]["plan"]["plan_id"]

    response = client.post("/metis/chat", json={"message": "next governed action"})

    assert response.status_code == 200
    body = response.json()
    instruction = body["next_action"]
    assert instruction["recommended_action"] == "review_tool_plan"
    assert instruction["target"] == {"type": "tool_plan", "id": plan_id}
    assert instruction["api_instruction"]["approve"] == f"POST /metis/tools/plans/{plan_id}/approve"
    assert body["state"]["tool_plan_queue"][0]["review_status"] == "pending"
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_next_action_guides_step_proposal_review_after_plan_advance() -> None:
    client = _client()
    planned = client.post("/metis/chat", json={"message": "plan task: check git status"}).json()
    plan_id = planned["tool_plan"]["plan"]["plan_id"]
    client.post(f"/metis/tools/plans/{plan_id}/approve", json={"reason": "reviewed plan"})
    advanced = client.post(f"/metis/tools/plans/{plan_id}/advance", json={}).json()
    proposal_id = advanced["result"]["queued_proposals"][0]["proposal_id"]

    response = client.post("/metis/chat", json={"message": "what is the next approval step?"})

    assert response.status_code == 200
    body = response.json()
    instruction = body["next_action"]
    assert instruction["recommended_action"] == "review_step_proposal"
    assert instruction["target"] == {"type": "proposal", "id": proposal_id}
    assert instruction["api_instruction"]["approve"] == f"POST /metis/proposals/{proposal_id}/approve"
    assert body["state"]["approval_queue"][0]["review_status"] == "pending"
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_next_action_reports_no_action_when_workspace_is_clear() -> None:
    client = _client()

    response = client.post("/metis/chat", json={"message": "what do I do next?"})

    assert response.status_code == 200
    body = response.json()
    instruction = body["next_action"]
    assert instruction["recommended_action"] == "no_action_available"
    assert instruction["target"] == {"type": "workspace", "id": None}
    assert instruction["api_instruction"]["proposals"] == "GET /metis/proposals"
    assert body["state"]["approval_queue"] == []
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False
