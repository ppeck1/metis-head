from __future__ import annotations

from collections import Counter
from typing import Any

from .tool_registry import TOOL_REGISTRY_VERSION, TOOLS


TOOL_CONTRACT_VERSION = "metis_tool_contract.v0.1"


def build_tool_contract_manifest() -> dict[str, Any]:
    tools = [tool.to_dict() for tool in TOOLS.values()]
    permission_counts = Counter(tool["permission_mode"] for tool in tools)
    risk_counts = Counter(tool["risk_class"] for tool in tools)
    side_effect_counts = Counter(tool["side_effect_class"] for tool in tools)
    lifecycle_counts = Counter(tool["lifecycle"]["lifecycle_label"] for tool in tools)
    active_read_only = [tool["tool_id"] for tool in tools if tool["permission_mode"] == "approved_read_only"]
    dry_run_only = [tool["tool_id"] for tool in tools if tool["permission_mode"] == "dry_run"]
    proposal_only = [tool["tool_id"] for tool in tools if tool["permission_mode"] == "proposal_only"]
    future_only = [tool["tool_id"] for tool in tools if "future_only" in tool["lifecycle"].get("lifecycle_tags", [])]
    matrix = [
        {
            "tool_id": tool["tool_id"],
            "permission_mode": tool["permission_mode"],
            "risk_class": tool["risk_class"],
            "side_effect_class": tool["side_effect_class"],
            "lifecycle_label": tool["lifecycle"]["lifecycle_label"],
            "execution_result": tool["lifecycle"]["execution_result"],
            "requires_human_review": tool["permission_requirements"]["requires_human_review"],
            "required_gates": tool["permission_requirements"]["required_gates"],
            "blocked_capabilities": tool["permission_requirements"]["blocked_capabilities"],
        }
        for tool in tools
    ]
    return {
        "schema_version": TOOL_CONTRACT_VERSION,
        "tool_registry_version": TOOL_REGISTRY_VERSION,
        "summary": {
            "tool_count": len(tools),
            "active_read_only_count": len(active_read_only),
            "dry_run_only_count": len(dry_run_only),
            "proposal_only_count": len(proposal_only),
            "future_only_count": len(future_only),
        },
        "counts": {
            "permission_modes": dict(sorted(permission_counts.items())),
            "risk_classes": dict(sorted(risk_counts.items())),
            "side_effect_classes": dict(sorted(side_effect_counts.items())),
            "lifecycle_labels": dict(sorted(lifecycle_counts.items())),
        },
        "lanes": {
            "active_read_only": active_read_only,
            "dry_run_only": dry_run_only,
            "proposal_only": proposal_only,
            "future_only": future_only,
        },
        "governance_matrix": matrix,
        "boundaries": [
            "No autonomous execution.",
            "No shell execution.",
            "No live fetch execution.",
            "No BOH retrieval-as-tool execution.",
            "No BOH or Atlas mutation.",
            "No memory promotion.",
            "No external mutation lanes are active.",
        ],
    }
