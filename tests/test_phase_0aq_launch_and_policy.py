from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.read_only_tools import execute_filesystem_read, execute_git_status


ROOT = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_launch_script_sets_repo_root_and_starts_uvicorn() -> None:
    script = ROOT / "scripts" / "launch_metis.ps1"

    content = script.read_text(encoding="utf-8")

    assert "METIS_REPO_ROOT" in content
    assert "Set-Location -LiteralPath $RepoRoot" in content
    assert "uvicorn" in content
    assert "metis_head.brain:app" in content
    assert "8787" in content


def test_read_only_tools_use_configured_repo_root_when_cwd_differs(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("METIS_REPO_ROOT", str(ROOT))
    monkeypatch.chdir(tmp_path)

    file_result = execute_filesystem_read({"path": "pyproject.toml"})
    git_result = execute_git_status({"repository": "."})

    assert file_result["path"].endswith("pyproject.toml")
    assert git_result["repository"] == str(ROOT.resolve())


def test_execution_policy_distinguishes_arbitrary_execution_from_scoped_read_only_lanes() -> None:
    client = _client()

    policy = client.get("/metis/execution/policy").json()

    assert policy["execution_enabled"] is False
    assert "Arbitrary or autonomous execution is disabled" in policy["execution_enabled_meaning"]
    assert policy["scoped_read_only_receipts_enabled"] is True
    assert policy["active_approved_read_only_lanes"] == ["time.now", "filesystem.read", "git.status"]
