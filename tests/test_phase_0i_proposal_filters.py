from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _queue_fixture_proposals(client: TestClient) -> None:
    client.post("/metis/tools/propose", json={"tool_id": "filesystem.read", "arguments": {"path": "README.md"}})
    client.post("/metis/tools/propose", json={"tool_id": "boh.retrieve_proposed", "arguments": {"query": "Metis tools"}})
    client.post("/metis/tools/propose", json={"tool_id": "memory.propose", "arguments": {"memory_id": "m1", "summary": "remember this"}})


def test_proposals_endpoint_filters_by_tool_type_and_status() -> None:
    client = _client()
    _queue_fixture_proposals(client)

    by_tool = client.get("/metis/proposals", params={"tool_id": "boh.retrieve_proposed"})
    by_type = client.get("/metis/proposals", params={"proposal_type": "memory"})
    by_status = client.get("/metis/proposals", params={"status": "pending"})

    assert by_tool.status_code == 200
    assert by_tool.json()["total_count"] == 3
    assert by_tool.json()["filtered_count"] == 1
    assert by_tool.json()["filters"]["tool_id"] == "boh.retrieve_proposed"
    assert by_tool.json()["proposals"][0]["tool_id"] == "boh.retrieve_proposed"
    assert by_type.json()["filtered_count"] == 1
    assert by_type.json()["proposals"][0]["proposal_type"] == "memory"
    assert by_status.json()["filtered_count"] == 3


def test_proposals_endpoint_filters_reviewed_proposals() -> None:
    client = _client()
    _queue_fixture_proposals(client)
    proposals = client.get("/metis/proposals").json()["proposals"]
    client.post(f"/metis/proposals/{proposals[0]['proposal_id']}/approve", json={"reason": "reviewed"})

    approved = client.get("/metis/proposals", params={"status": "approved"})
    pending = client.get("/metis/proposals", params={"status": "pending"})

    assert approved.status_code == 200
    assert approved.json()["filtered_count"] == 1
    assert approved.json()["proposals"][0]["review_status"] == "approved"
    assert pending.json()["filtered_count"] == 2


def test_dashboard_contains_proposal_filter_controls() -> None:
    client = _client()

    dashboard = client.get("/").text

    assert "proposalStatusFilter" in dashboard
    assert "proposalTypeFilter" in dashboard
    assert "proposalToolFilter" in dashboard
    assert "URLSearchParams" in dashboard
