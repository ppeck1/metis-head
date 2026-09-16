from __future__ import annotations

from pathlib import Path

from metis_head.mcp_access import mcp_status


ROOT = Path(__file__).resolve().parents[1]


def test_launch_script_defaults_mcp_gates_active_without_private_config() -> None:
    content = (ROOT / "scripts" / "launch_metis.ps1").read_text(encoding="utf-8")

    assert 'METIS_MCP_ENABLED = "true"' in content
    assert 'METIS_MCP_BOH_ENABLED = "true"' in content
    assert 'METIS_MCP_ATLAS_ENABLED = "true"' in content
    assert "METIS_MCP_BOH_COMMAND" not in content
    assert "METIS_MCP_ATLAS_COMMAND" not in content


def test_dashboard_names_backend_gate_disabled_status_clearly() -> None:
    dashboard = (ROOT / "metis_head" / "static" / "dashboard.html").read_text(encoding="utf-8")

    assert 'global_disabled: "MCP gate disabled"' in dashboard
    assert 'global_disabled: "global disabled"' not in dashboard


def test_active_gates_without_commands_stop_at_not_configured() -> None:
    status = mcp_status(
        {
            "METIS_MCP_ENABLED": "true",
            "METIS_MCP_BOH_ENABLED": "true",
            "METIS_MCP_ATLAS_ENABLED": "true",
        }
    )

    assert status["enabled"] is True
    assert status["servers"]["boh"]["enabled"] is True
    assert status["servers"]["boh"]["command_configured"] is False
    assert status["servers"]["project_atlas"]["enabled"] is True
    assert status["servers"]["project_atlas"]["command_configured"] is False


def test_launch_script_optionally_loads_ignored_local_mcp_config() -> None:
    content = (ROOT / "scripts" / "launch_metis.ps1").read_text(encoding="utf-8")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".project\\local_mcp_env.ps1" in content
    assert ". $LocalMcpEnv" in content
    assert ".project/local_mcp_env.ps1" in ignore
    assert ".project/local_mcp/" in ignore
