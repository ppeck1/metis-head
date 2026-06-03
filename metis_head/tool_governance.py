from __future__ import annotations

from typing import Any

from .tool_registry import get_tool, validate_tool_arguments


TOOL_GATE_EVALUATION_VERSION = "metis_tool_gate_evaluation.v0.1"
REQUEST_TYPES = {"dry_run", "propose", "execute", "chat_route"}


def evaluate_tool_request(tool_id: str, arguments: Any, state: dict[str, Any], request_type: str = "dry_run") -> dict[str, Any]:
    if request_type not in REQUEST_TYPES:
        raise ValueError(f"unsupported request_type: {request_type}")
    tool = get_tool(tool_id)
    validation = validate_tool_arguments(tool_id, arguments)
    requirements = tool.to_dict()["permission_requirements"]
    agent_mode = state.get("interaction_mode") == "agent"
    dry_run_allowed = (
        request_type in {"dry_run", "chat_route"}
        and not agent_mode
        and tool.permission_mode == "dry_run"
        and tool.side_effect_class == "none"
    )
    proposal_required = agent_mode or request_type in {"propose", "execute"} or not dry_run_allowed
    if request_type == "propose":
        decision = "queue_proposal"
    elif dry_run_allowed:
        decision = "dry_run_allowed"
    elif agent_mode:
        decision = "queue_proposal_agent_mode"
    elif request_type == "execute" and tool.permission_mode == "dry_run" and tool.side_effect_class == "none":
        decision = "dry_run_receipt_only"
    else:
        decision = "queue_proposal_required"
    return {
        "schema_version": TOOL_GATE_EVALUATION_VERSION,
        "tool_id": tool_id,
        "request_type": request_type,
        "decision": decision,
        "argument_validation": {
            "schema_version": validation["schema_version"],
            "valid": True,
            "warnings": validation["warnings"],
        },
        "permission_mode": tool.permission_mode,
        "side_effect_class": tool.side_effect_class,
        "risk_class": tool.risk_class,
        "dry_run_allowed": dry_run_allowed,
        "proposal_required": proposal_required,
        "review_required": proposal_required or requirements["requires_human_review"],
        "execution_allowed": False,
        "autonomous_execution_allowed": False,
        "required_gates": requirements["required_gates"],
        "blocked_capabilities": requirements["blocked_capabilities"],
        "boundary": "Gate evaluation is advisory and does not queue, approve, request, or execute tools.",
    }
