from __future__ import annotations

from datetime import UTC, datetime

from metis_head.connectors.contracts import Freshness
from metis_head.connectors.mcp_contracts import evidence_freshness, mcp_config_identity, normalize_mcp_read_result


def test_mcp_is_error_is_not_a_completed_read():
    outcome = normalize_mcp_read_result({"isError": True, "content": [{"type": "text", "text": "failed"}]})
    assert outcome.completed is False
    assert outcome.status == "read_error"
    assert outcome.blocked_reason == "mcp_tool_reported_error"


def test_mcp_cache_identity_changes_with_command_cwd_args_and_child_env_without_exposing_them():
    base = {
        "METIS_MCP_ATLAS_COMMAND": "atlas-one",
        "METIS_MCP_ATLAS_CWD": "C:/atlas",
        "METIS_MCP_ATLAS_ARGS_JSON": '["serve"]',
        "METIS_MCP_ATLAS_ENV_JSON": '{"API_TOKEN":"top-secret"}',
    }
    first = mcp_config_identity("project_atlas", base)
    assert "atlas" not in first and "secret" not in first
    for key in base:
        changed = dict(base)
        changed[key] += "-changed"
        assert mcp_config_identity("project_atlas", changed) != first


def test_mcp_freshness_is_unknown_without_upstream_observation_time():
    now = datetime(2026, 9, 16, tzinfo=UTC)
    assert evidence_freshness({}, now=now) == (None, Freshness.UNKNOWN)
    observed, freshness = evidence_freshness({"observed_at": "2026-09-14T00:00:00Z"}, now=now, stale_after_seconds=3600)
    assert observed is not None
    assert freshness is Freshness.STALE
