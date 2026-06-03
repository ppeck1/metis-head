from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .execution_policy import read_only_execution_policy
from .tool_contract import build_tool_contract_manifest


TOOL_POLICY_SNAPSHOT_VERSION = "metis_tool_policy_snapshot.v0.1"


def build_tool_policy_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    proposals = deepcopy(state.get("approval_queue", []))
    receipts = deepcopy(state.get("execution_audit_log", []))
    review_counts = Counter(str(proposal.get("review_status", "unknown")) for proposal in proposals)
    proposal_type_counts = Counter(str(proposal.get("proposal_type", "unknown")) for proposal in proposals)
    receipt_status_counts = Counter(str(receipt.get("execution_status", "unknown")) for receipt in receipts)
    return {
        "schema_version": TOOL_POLICY_SNAPSHOT_VERSION,
        "contract": build_tool_contract_manifest(),
        "read_only_policy": read_only_execution_policy(),
        "proposal_queue": {
            "total_count": len(proposals),
            "pending_count": int(state.get("pending_approval_count", 0)),
            "review_counts": dict(sorted(review_counts.items())),
            "proposal_type_counts": dict(sorted(proposal_type_counts.items())),
            "proposals": proposals,
        },
        "execution_audit": {
            "receipt_count": len(receipts),
            "status_counts": dict(sorted(receipt_status_counts.items())),
            "receipts": receipts,
        },
        "authority": {
            "execution_authority_changed": False,
            "autonomous_execution_allowed": False,
            "external_action_executed": bool(state.get("external_action_executed", False)),
            "standing_approval_active": False,
        },
        "boundaries": [
            "Snapshot is inspection-only.",
            "Snapshot does not approve proposals.",
            "Snapshot does not request execution.",
            "Snapshot does not run tools.",
            "Snapshot does not broaden read-only lanes.",
        ],
    }
