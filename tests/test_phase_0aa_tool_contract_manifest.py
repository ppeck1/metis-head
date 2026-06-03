from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.tool_contract import TOOL_CONTRACT_VERSION, build_tool_contract_manifest


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_contract_manifest_summarizes_registry_lanes() -> None:
    manifest = build_tool_contract_manifest()

    assert manifest["schema_version"] == TOOL_CONTRACT_VERSION
    assert manifest["tool_registry_version"] == "metis_tool_registry.v0.1"
    assert manifest["summary"]["tool_count"] == len(manifest["governance_matrix"])
    assert {"git.status", "filesystem.read"} <= set(manifest["lanes"]["active_read_only"])
    assert "time.now" in manifest["lanes"]["dry_run_only"]
    assert "boh.retrieve_proposed" in manifest["lanes"]["future_only"]
    assert "fetch.url_proposed" in manifest["lanes"]["future_only"]
    assert manifest["counts"]["permission_modes"]["approved_read_only"] >= 2
    assert manifest["counts"]["permission_modes"]["proposal_only"] >= 4


def test_tool_contract_manifest_matrix_contains_permission_requirements() -> None:
    manifest = build_tool_contract_manifest()
    matrix = {row["tool_id"]: row for row in manifest["governance_matrix"]}

    assert matrix["boh.retrieve_proposed"]["execution_result"] == "blocked_after_review"
    assert "boh_http_call" in matrix["boh.retrieve_proposed"]["blocked_capabilities"]
    assert matrix["filesystem.read"]["permission_mode"] == "approved_read_only"
    assert "repo_path_allowlist" in matrix["filesystem.read"]["required_gates"]
    assert matrix["math.calculate"]["requires_human_review"] is False


def test_tool_contract_endpoint_and_dashboard_hook_are_available() -> None:
    client = _client()

    response = client.get("/metis/tools/contract")
    dashboard = client.get("/").text

    assert response.status_code == 200
    assert response.json()["schema_version"] == TOOL_CONTRACT_VERSION
    assert "governance_matrix" in response.json()
    assert "refreshToolContract" in dashboard
    assert "/metis/tools/contract" in dashboard
