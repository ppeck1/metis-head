from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_dashboard_contains_guided_action_shortcut_hooks() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "guidedActionPanel" in dashboard
    assert "renderGuidedAction" in dashboard
    assert "applyGuidedAction" in dashboard
    assert "selectGuidedProposal" in dashboard
    assert "selectGuidedPlan" in dashboard
    assert "result.next_action" in dashboard
    assert "Guided action selected proposal" in dashboard
    assert "Guided action selected plan" in dashboard
