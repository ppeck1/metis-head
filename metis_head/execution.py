from __future__ import annotations

from hashlib import sha1
from typing import Any


EXECUTION_RECEIPT_VERSION = "metis_execution_receipt.v0.1"


def stable_receipt_id(receipt_index: int, proposal_id: str, execution_status: str, requested_at: str | None) -> str:
    digest = sha1(f"{receipt_index}:{proposal_id}:{execution_status}:{requested_at or ''}".encode("utf-8")).hexdigest()[:10]
    return f"execution_{receipt_index + 1:04d}_{digest}"


def build_execution_receipt(
    *,
    receipt_index: int,
    proposal: dict[str, Any],
    requested_at: str | None,
    reason: str | None = None,
    dry_run_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposal_id") or "unknown_proposal")
    decision = proposal.get("review_status", "pending")
    if decision == "pending":
        execution_status = "blocked_unreviewed"
        policy_decision = "review_required"
    elif decision == "denied":
        execution_status = "blocked_denied"
        policy_decision = "denied"
    elif proposal.get("dry_run_available") and proposal.get("side_effect_class") == "none":
        execution_status = "dry_run_only_not_executed"
        policy_decision = "dry_run_only"
    else:
        execution_status = "blocked_side_effect"
        policy_decision = "blocked_after_review"

    receipt = {
        "schema_version": EXECUTION_RECEIPT_VERSION,
        "receipt_id": stable_receipt_id(receipt_index, proposal_id, execution_status, requested_at),
        "proposal_id": proposal_id,
        "tool_id": proposal.get("tool_id"),
        "requested_action": proposal.get("intent"),
        "policy_decision": policy_decision,
        "execution_allowed": False,
        "execution_status": execution_status,
        "side_effect_class": proposal.get("side_effect_class"),
        "risk_class": proposal.get("risk_class"),
        "created_at": requested_at,
        "redactions": ["secrets", "raw_file_contents", "command_output", "external_receipts"],
        "operator_review_required": decision == "pending",
        "review_status": decision,
        "reason": reason or "",
    }
    if dry_run_receipt and execution_status == "dry_run_only_not_executed":
        receipt["dry_run_receipt"] = dry_run_receipt
    return receipt
