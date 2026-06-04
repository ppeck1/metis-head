from __future__ import annotations

from typing import Any

from .execution_policy import read_only_execution_policy
from .tool_contract import build_tool_contract_manifest
from .tool_governance import TOOL_GATE_EVALUATION_VERSION
from .tool_policy_snapshot import TOOL_POLICY_SNAPSHOT_VERSION
from .tool_registry import TOOL_ARGUMENT_VALIDATION_VERSION, TOOLS


TOOL_READINESS_VERSION = "metis_tool_readiness.v0.1"


def calculate_tool_readiness(state: dict[str, Any]) -> dict[str, Any]:
    contract = build_tool_contract_manifest()
    policy = read_only_execution_policy()
    tools = [tool.to_dict() for tool in TOOLS.values()]
    proposals = state.get("approval_queue", [])
    receipts = state.get("execution_audit_log", [])
    checks = [
        _check("registry_seeded", len(tools) >= 10, "registry", f"{len(tools)} tools registered"),
        _check("all_tools_have_input_schemas", all(bool(tool.get("input_schema")) for tool in tools), "schema", "manifest input schemas present"),
        _check("all_tools_have_output_schemas", all(bool(tool.get("output_schema")) for tool in tools), "schema", "manifest output schemas present"),
        _check("argument_validation_versioned", TOOL_ARGUMENT_VALIDATION_VERSION == "metis_tool_arguments.v0.1", "schema", TOOL_ARGUMENT_VALIDATION_VERSION),
        _check("gate_evaluation_versioned", TOOL_GATE_EVALUATION_VERSION == "metis_tool_gate_evaluation.v0.1", "governance", TOOL_GATE_EVALUATION_VERSION),
        _check("contract_manifest_versioned", contract["schema_version"] == "metis_tool_contract.v0.1", "governance", contract["schema_version"]),
        _check("policy_snapshot_versioned", TOOL_POLICY_SNAPSHOT_VERSION == "metis_tool_policy_snapshot.v0.1", "governance", TOOL_POLICY_SNAPSHOT_VERSION),
        _check("arbitrary_execution_disabled", policy["execution_enabled"] is False, "execution_boundary", "arbitrary execution disabled; scoped read-only receipts remain gated"),
        _check("no_external_action_executed", state.get("external_action_executed") is False, "execution_boundary", "external_action_executed=false"),
        _check("review_scope_on_reviewed_proposals", _reviewed_proposals_have_scope(proposals), "review", "reviewed proposals have review_scope"),
        _check("receipts_never_allow_execution", all(receipt.get("execution_allowed") is False for receipt in receipts), "audit", f"{len(receipts)} receipt(s) checked"),
        _check("future_lanes_remain_blocked", {"fetch.url_proposed", "boh.retrieve_proposed"} <= set(contract["lanes"]["future_only"]), "execution_boundary", "future lanes are proposal-only"),
    ]
    passed = sum(1 for check in checks if check["passed"])
    score = round(passed / len(checks), 4) if checks else 0.0
    return {
        "schema_version": TOOL_READINESS_VERSION,
        "domain": "governed_tool_readiness",
        "score": score,
        "passed_count": passed,
        "total_count": len(checks),
        "status": "ready" if passed == len(checks) else "incomplete",
        "checks": checks,
    }


def _check(check_id: str, passed: bool, domain: str, detail: str) -> dict[str, Any]:
    return {"check_id": check_id, "domain": domain, "passed": bool(passed), "detail": detail}


def _reviewed_proposals_have_scope(proposals: list[dict[str, Any]]) -> bool:
    reviewed = [proposal for proposal in proposals if proposal.get("review_status") in {"approved", "denied"}]
    return all(isinstance(proposal.get("review_scope"), dict) for proposal in reviewed)
