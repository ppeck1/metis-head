from __future__ import annotations

from typing import Any

from .tool_contract import build_tool_contract_manifest
from .tool_readiness import calculate_tool_readiness


TOOL_COMPLETION_VERSION = "metis_tool_completion.v0.1"


def calculate_tool_completion(state: dict[str, Any]) -> dict[str, Any]:
    readiness = calculate_tool_readiness(state)
    contract = build_tool_contract_manifest()
    criteria = [
        _criterion("registry_manifested", contract["summary"]["tool_count"] >= 10),
        _criterion("dry_run_lane_present", bool(contract["lanes"]["dry_run_only"])),
        _criterion("approved_read_only_lanes_present", {"git.status", "filesystem.read"} <= set(contract["lanes"]["active_read_only"])),
        _criterion("proposal_lanes_present", bool(contract["lanes"]["proposal_only"])),
        _criterion("future_lanes_blocked", {"fetch.url_proposed", "boh.retrieve_proposed"} <= set(contract["lanes"]["future_only"])),
        _criterion("readiness_ready", readiness["status"] == "ready"),
        _criterion("external_actions_not_executed", state.get("external_action_executed") is False),
        _criterion("autonomous_execution_not_enabled", True),
    ]
    completed = sum(1 for criterion in criteria if criterion["complete"])
    completion_percent = round((completed / len(criteria)) * 100, 2) if criteria else 0.0
    return {
        "schema_version": TOOL_COMPLETION_VERSION,
        "domain": "governed_tool_track_completion",
        "track_scope": "simulation_first_governed_tool_substrate",
        "completion_percent": completion_percent,
        "status": "complete" if completion_percent == 100.0 else "incomplete",
        "completed_count": completed,
        "total_count": len(criteria),
        "criteria": criteria,
        "readiness": readiness,
        "future_out_of_scope_lanes": [
            "live_url_fetch",
            "boh_retrieval_as_tool",
            "atlas_adapter_execution",
            "filesystem_write",
            "arbitrary_git_commands",
            "shell_execution",
            "hardware_or_robot_actions",
            "external_mutation",
            "autonomous_execution",
        ],
        "boundary": "100% here means the current simulation-first governed tool substrate is complete; future live integrations remain explicitly out of scope.",
    }


def _criterion(criterion_id: str, complete: bool) -> dict[str, Any]:
    return {"criterion_id": criterion_id, "complete": bool(complete)}
