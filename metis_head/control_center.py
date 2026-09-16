from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTROL_CENTER_VERSION = "metis_control_center.v0.2"
CONTROL_CENTER_STATE_VERSION = "metis_control_center_state.v0.2"
CONTROL_CENTER_CONTROLS = {"tool_usage", "boh_mcp", "project_atlas_mcp"}
CONTROL_CENTER_MODES = {"off", "read", "write_proposal", "read_write_proposal"}
SERVER_CONTROL_MAP = {"boh": "boh_mcp", "project_atlas": "project_atlas_mcp"}
MODE_LABELS = {
    "off": "Off",
    "read": "Read",
    "write_proposal": "Write Proposal",
    "read_write_proposal": "Read + Write Proposal",
}


def default_control_center_state() -> dict[str, Any]:
    return {
        "schema_version": CONTROL_CENTER_STATE_VERSION,
        "tool_usage_requested": False,
        "boh_mcp_requested": False,
        "project_atlas_mcp_requested": False,
        "tool_usage_mode": "off",
        "boh_mcp_mode": "off",
        "project_atlas_mcp_mode": "off",
        "last_updated_at": None,
        "last_toggle": None,
    }


def normalize_control_mode(value: Any, *, fallback_requested: bool = False) -> str:
    if isinstance(value, str):
        mode = value.strip().lower()
        if mode in CONTROL_CENTER_MODES:
            return mode
    return "read" if fallback_requested else "off"


def mode_allows_read(mode: str) -> bool:
    return mode in {"read", "read_write_proposal"}


def mode_allows_write_proposal(mode: str) -> bool:
    return mode in {"write_proposal", "read_write_proposal"}


def normalize_control_center_state(value: Any) -> dict[str, Any]:
    state = default_control_center_state()
    if isinstance(value, dict):
        tool_mode = normalize_control_mode(
            value.get("tool_usage_mode"),
            fallback_requested=bool(value.get("tool_usage_requested")),
        )
        boh_mode = normalize_control_mode(
            value.get("boh_mcp_mode"),
            fallback_requested=bool(value.get("boh_mcp_requested")),
        )
        atlas_mode = normalize_control_mode(
            value.get("project_atlas_mcp_mode"),
            fallback_requested=bool(value.get("project_atlas_mcp_requested")),
        )
        state.update(
            {
                "tool_usage_requested": tool_mode != "off",
                "boh_mcp_requested": boh_mode != "off",
                "project_atlas_mcp_requested": atlas_mode != "off",
                "tool_usage_mode": tool_mode,
                "boh_mcp_mode": boh_mode,
                "project_atlas_mcp_mode": atlas_mode,
                "last_updated_at": value.get("last_updated_at"),
                "last_toggle": deepcopy(value.get("last_toggle")) if isinstance(value.get("last_toggle"), dict) else None,
            }
        )
    return state


def _read_status_for_server(
    *,
    global_mode: str,
    server_mode: str,
    global_enabled: bool,
    server_enabled: bool,
    command_configured: bool,
) -> str:
    if not mode_allows_read(server_mode):
        return "off"
    if not mode_allows_read(global_mode):
        return "master_off"
    if not global_enabled:
        return "global_disabled"
    if not server_enabled:
        return "server_disabled"
    if not command_configured:
        return "not_configured"
    return "usable"


def _write_status_for_server(
    *,
    global_mode: str,
    server_mode: str,
    proposal_tool_count: int,
    server_id: str,
) -> str:
    if not mode_allows_write_proposal(server_mode):
        return "off"
    if not mode_allows_write_proposal(global_mode):
        return "master_off"
    if server_id == "project_atlas" and proposal_tool_count > 0:
        return "proposal_ready"
    if server_id == "boh":
        return "proposal_ready"
    return "proposal_unavailable"


def _combined_status(mode: str, read_status: str, write_status: str) -> str:
    wants_read = mode_allows_read(mode)
    wants_write = mode_allows_write_proposal(mode)
    if not wants_read and not wants_write:
        return "off"
    if wants_read and wants_write:
        if read_status == "usable" and write_status == "proposal_ready":
            return "read_write_ready"
        if read_status != "usable":
            return read_status
        return write_status
    if wants_read:
        return read_status
    return write_status


def _server_status(server_id: str, control_state: dict[str, Any], mcp: dict[str, Any]) -> dict[str, Any]:
    server = dict((mcp.get("servers") or {}).get(server_id) or {})
    control = SERVER_CONTROL_MAP[server_id]
    global_mode = normalize_control_mode(control_state.get("tool_usage_mode"))
    server_mode = normalize_control_mode(control_state.get(f"{control}_mode"))
    global_enabled = bool(mcp.get("enabled"))
    server_enabled = bool(server.get("enabled"))
    command_configured = bool(server.get("command_configured"))
    policy = server.get("policy") if isinstance(server.get("policy"), dict) else {}
    proposal_tool_count = len(policy.get("proposal_tools") or [])
    read_status = _read_status_for_server(
        global_mode=global_mode,
        server_mode=server_mode,
        global_enabled=global_enabled,
        server_enabled=server_enabled,
        command_configured=command_configured,
    )
    write_status = _write_status_for_server(
        global_mode=global_mode,
        server_mode=server_mode,
        proposal_tool_count=proposal_tool_count,
        server_id=server_id,
    )
    read_usable = read_status == "usable"
    return {
        "server_id": server_id,
        "display_name": server.get("display_name", server_id),
        "control": control,
        "mode": server_mode,
        "mode_label": MODE_LABELS[server_mode],
        "requested": server_mode != "off",
        "effective_requested": global_mode != "off" and server_mode != "off",
        "read_requested": mode_allows_read(server_mode),
        "write_proposal_requested": mode_allows_write_proposal(server_mode),
        "effective_read_requested": mode_allows_read(global_mode) and mode_allows_read(server_mode),
        "effective_write_proposal_requested": mode_allows_write_proposal(global_mode) and mode_allows_write_proposal(server_mode),
        "enabled": server_enabled,
        "configured": command_configured,
        "cwd_configured": bool(server.get("cwd_configured")),
        "transport": server.get("transport", "not_configured"),
        "running": read_usable,
        "usable": read_usable,
        "read_status": read_status,
        "write_status": write_status,
        "status": _combined_status(server_mode, read_status, write_status),
        "read_only_tool_count": len(policy.get("read_only_tools") or []),
        "proposal_tool_count": proposal_tool_count,
        "write_apply_allowed": False,
        "write_boundary": "Write mode is proposal/outbox intent only; direct apply remains blocked.",
        "blocked_capabilities": list(policy.get("blocked_capabilities") or []),
    }


def build_control_center_status(
    state: dict[str, Any],
    mcp: dict[str, Any],
    boh_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    control_state = normalize_control_center_state(state.get("tool_control_center"))
    boh = boh_status or {}
    tool_mode = normalize_control_mode(control_state.get("tool_usage_mode"))
    servers = {
        server_id: _server_status(server_id, control_state, mcp)
        for server_id in SERVER_CONTROL_MAP
    }
    return {
        "schema_version": CONTROL_CENTER_VERSION,
        "state": control_state,
        "allowed_modes": [
            {"mode": mode, "label": MODE_LABELS[mode]}
            for mode in ("off", "read", "write_proposal", "read_write_proposal")
        ],
        "controls": {
            "tool_usage": {
                "mode": tool_mode,
                "mode_label": MODE_LABELS[tool_mode],
                "requested": tool_mode != "off",
                "read_requested": mode_allows_read(tool_mode),
                "write_proposal_requested": mode_allows_write_proposal(tool_mode),
                "status": "requested" if tool_mode != "off" else "off",
                "execution_allowed": False,
                "write_apply_allowed": False,
            },
            "boh_mcp": {
                "mode": servers["boh"]["mode"],
                "mode_label": servers["boh"]["mode_label"],
                "requested": servers["boh"]["requested"],
                "read_requested": servers["boh"]["read_requested"],
                "write_proposal_requested": servers["boh"]["write_proposal_requested"],
                "status": servers["boh"]["status"],
                "execution_allowed": False,
                "write_apply_allowed": False,
            },
            "project_atlas_mcp": {
                "mode": servers["project_atlas"]["mode"],
                "mode_label": servers["project_atlas"]["mode_label"],
                "requested": servers["project_atlas"]["requested"],
                "read_requested": servers["project_atlas"]["read_requested"],
                "write_proposal_requested": servers["project_atlas"]["write_proposal_requested"],
                "status": servers["project_atlas"]["status"],
                "execution_allowed": False,
                "write_apply_allowed": False,
            },
        },
        "mcp": {
            "schema_version": mcp.get("schema_version"),
            "enabled": bool(mcp.get("enabled")),
            "execution_allowed": bool(mcp.get("execution_allowed")),
            "boundary": mcp.get("boundary", ""),
            "servers": servers,
        },
        "boh_library": {
            "enabled": bool(boh.get("enabled")),
            "state": boh.get("state", "unknown"),
            "running": bool(boh.get("enabled")) and boh.get("state") in {"connecting", "connected", "degraded"},
            "usable": boh.get("state") == "connected",
            "last_checked_at": boh.get("last_checked_at"),
            "last_connected_at": boh.get("last_connected_at"),
            "last_error": boh.get("last_error") or "",
        },
        "execution_allowed": False,
        "write_apply_allowed": False,
        "boundary": "Control-center modes record operator intent only; read access still requires server-side MCP env gates and read-only allowlists, while write mode is proposal/outbox intent only.",
    }
