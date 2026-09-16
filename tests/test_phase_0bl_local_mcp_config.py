from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_mcp_env_paths_are_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".project/local_mcp_env.ps1" in ignore
    assert ".project/local_mcp/" in ignore


def test_public_launch_script_loads_local_config_without_private_values() -> None:
    content = (ROOT / "scripts" / "launch_metis.ps1").read_text(encoding="utf-8")

    assert ".project\\local_mcp_env.ps1" in content
    assert ". $LocalMcpEnv" in content
    assert "METIS_MCP_BOH_COMMAND" not in content
    assert "METIS_MCP_ATLAS_COMMAND" not in content
    assert "project_atlas.sqlite" not in content


def test_public_repo_contains_no_local_mcp_config_values() -> None:
    tracked_like_paths = [
        ROOT / "scripts" / "launch_metis.ps1",
        ROOT / "README.md",
        ROOT / "docs" / "project_variable_map.md",
        ROOT / "docs" / "VARIABLE_MATRIX.md",
    ]
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in tracked_like_paths if path.exists())

    assert "C:/Users/peckm/AppData/Roaming/Paul Peck/Project Atlas/project_atlas.sqlite" not in rendered
    assert "B:/dev/Bag.of.holding/boh.db" not in rendered
