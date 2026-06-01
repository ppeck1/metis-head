from __future__ import annotations

from fastapi.testclient import TestClient

import metis_head.artifacts as artifacts
from metis_head.brain import app


def _client_with_tmp_artifacts(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(artifacts, "ARTIFACT_DIR", tmp_path)
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_save_export_artifact_lists_and_reads(monkeypatch, tmp_path) -> None:
    client = _client_with_tmp_artifacts(monkeypatch, tmp_path)
    client.post("/metis/event", json={"type": "control_change", "control": "initiative", "value": 0.9})

    saved = client.post("/metis/artifacts/save", json={"artifact_type": "export", "label": "test export"}).json()
    listed = client.get("/metis/artifacts").json()
    loaded = client.get(f"/metis/artifacts/{saved['filename']}").json()

    assert saved["artifact_schema"] == "metis_artifact.v0.1"
    assert saved["artifact_type"] == "export"
    assert saved["filename"].endswith(".json")
    assert len(listed["artifacts"]) == 1
    assert loaded["artifact_type"] == "export"
    assert loaded["payload"]["export_schema"] == "metis_export.v0.1"
    assert loaded["payload"]["state"]["initiative_bucket"] == "proactive"


def test_save_manifest_artifact_can_skip_results(monkeypatch, tmp_path) -> None:
    client = _client_with_tmp_artifacts(monkeypatch, tmp_path)

    saved = client.post(
        "/metis/artifacts/save",
        json={"artifact_type": "manifest", "label": "manifest no results", "include_results": False},
    ).json()
    loaded = client.get(f"/metis/artifacts/{saved['filename']}").json()

    assert loaded["artifact_type"] == "manifest"
    assert loaded["payload"]["manifest_version"] == "metis_sim_tests.v0.1"
    assert loaded["payload"]["summary"]["scenario_passed"] is None


def test_artifact_save_rejects_unknown_type(monkeypatch, tmp_path) -> None:
    client = _client_with_tmp_artifacts(monkeypatch, tmp_path)

    response = client.post("/metis/artifacts/save", json={"artifact_type": "unknown"})

    assert response.status_code == 400


def test_artifact_read_rejects_path_traversal(monkeypatch, tmp_path) -> None:
    client = _client_with_tmp_artifacts(monkeypatch, tmp_path)

    response = client.get("/metis/artifacts/..%2Fsecret.json")

    assert response.status_code == 404
