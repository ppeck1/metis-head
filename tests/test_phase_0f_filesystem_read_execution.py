from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def _first_proposal_id(state: dict) -> str:
    return state["approval_queue"][0]["proposal_id"]


def test_filesystem_read_registry_lane_is_present() -> None:
    client = _client()

    response = client.get("/metis/tools")

    assert response.status_code == 200
    tools = {tool["tool_id"]: tool for tool in response.json()["tools"]}
    assert tools["filesystem.read"]["permission_mode"] == "approved_read_only"
    assert tools["filesystem.read"]["side_effect_class"] == "read_only"
    assert tools["filesystem.read_proposed"]["permission_mode"] == "proposal_only"


def test_approved_filesystem_read_returns_redacted_preview_receipt() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read", "arguments": {"path": "pyproject.toml"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "approved repo doc preview"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={"reason": "operator requested preview"})

    assert response.status_code == 200
    body = response.json()
    receipt = body["receipt"]
    preview = receipt["output_summary"]["preview"]
    assert body["status"] == "executed_read_only"
    assert receipt["tool_id"] == "filesystem.read"
    assert receipt["policy_decision"] == "approved_read_only"
    assert receipt["execution_allowed"] is False
    assert "pyproject.toml" in preview["path"]
    assert "preview_lines" in preview
    assert "content" not in receipt
    assert "raw_file_contents" in receipt["redactions"]
    assert body["state"]["external_action_executed"] is False


def test_filesystem_read_blocks_outside_allowlist(tmp_path) -> None:
    client = _client()
    outside_file = tmp_path / "not_allowed.txt"
    outside_file.write_text("outside", encoding="utf-8")
    queued = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read", "arguments": {"path": str(outside_file)}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "not allowed"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"]


def test_filesystem_read_blocks_disallowed_extension() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read", "arguments": {"path": ".git/index"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "binary git file"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 400
    assert "extension" in response.json()["detail"]


def test_filesystem_read_blocks_oversized_preview(monkeypatch) -> None:
    monkeypatch.setattr("metis_head.read_only_tools.MAX_FILE_PREVIEW_BYTES", 1)
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read", "arguments": {"path": "README.md"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "size gate"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 400
    assert "size limit" in response.json()["detail"]


def test_legacy_filesystem_read_proposed_remains_blocked_after_approval() -> None:
    client = _client()
    queued = client.post("/metis/tools/propose", json={"tool_id": "filesystem.read_proposed", "arguments": {"path": "README.md"}}).json()
    proposal_id = _first_proposal_id(queued["state"])
    client.post(f"/metis/proposals/{proposal_id}/approve", json={"reason": "legacy proposal"})

    response = client.post(f"/metis/proposals/{proposal_id}/request_execution", json={})

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["execution_status"] == "blocked_side_effect"
    assert receipt["execution_allowed"] is False


def test_policy_marks_filesystem_read_active() -> None:
    client = _client()

    policy = client.get("/metis/execution/policy").json()
    lanes = {lane["lane"]: lane["status"] for lane in policy["candidate_lanes"]}

    assert lanes["filesystem.read"] == "active_approved_read_only"
    assert lanes["fetch.url"] == "future_only"
