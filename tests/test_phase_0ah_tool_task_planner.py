from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.schemas import baseline_state
from metis_head.tool_task_planner import TOOL_TASK_PLAN_VERSION, plan_tool_task


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_task_planner_creates_reviewable_multi_step_read_only_plan() -> None:
    plan = plan_tool_task("Check git status and summarize README.md", baseline_state())

    assert plan["schema_version"] == TOOL_TASK_PLAN_VERSION
    assert plan["status"] == "reviewable_plan"
    assert plan["execution_allowed"] is False
    assert [step["tool_id"] for step in plan["steps"]] == ["git.status", "filesystem.read", "text.summarize"]
    assert plan["steps"][0]["status"] == "proposal_required"
    assert plan["steps"][1]["status"] == "proposal_required"
    assert plan["steps"][2]["status"] == "dry_run_available"
    assert plan["summary"]["proposal_required_count"] == 2


def test_tool_task_planner_marks_live_fetch_as_future_only() -> None:
    plan = plan_tool_task("Fetch https://example.com and summarize it", baseline_state())

    fetch_step = next(step for step in plan["steps"] if step["tool_id"] == "fetch.url_proposed")
    assert fetch_step["status"] == "future_only_blocked"
    assert fetch_step["future_out_of_scope"] is True
    assert fetch_step["execution_allowed"] is False


def test_tool_task_planner_blocks_mutation_without_tool() -> None:
    plan = plan_tool_task("Edit README.md and commit the change", baseline_state())

    blocked = [step for step in plan["steps"] if step["status"] == "blocked_no_tool"]
    assert blocked
    assert blocked[0]["future_out_of_scope"] is True
    assert blocked[0]["blocked_capabilities"] == ["mutation_or_external_action"]
    assert plan["execution_allowed"] is False


def test_tool_task_plan_endpoint_and_dashboard_hook_are_available() -> None:
    client = _client()

    response = client.post("/metis/tools/task/plan", json={"task": "Plan: prepare a governed tool review"})
    dashboard = client.get("/").text

    assert response.status_code == 200
    assert response.json()["schema_version"] == TOOL_TASK_PLAN_VERSION
    assert response.json()["execution_allowed"] is False
    assert "planToolTask" in dashboard
    assert "/metis/tools/task/plan" in dashboard
