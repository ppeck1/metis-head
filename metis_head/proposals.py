from __future__ import annotations

from hashlib import sha1
from typing import Any


PROPOSAL_SCHEMA_VERSION = "metis_proposal.v0.1"


def build_proposal(
    *,
    queue_index: int,
    intent: str,
    action_class: str,
    policy: dict[str, Any],
    proposal_type: str = "action",
    status: str = "pending_review",
) -> dict[str, Any]:
    proposal_id = stable_proposal_id(queue_index, intent, action_class)
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "status": status,
        "intent": intent,
        "action_class": action_class,
        "requires_approval": bool(policy.get("requires_approval", True)),
        "default_decision": policy.get("default_decision", "queue_for_approval"),
        "reasons": list(policy.get("reasons", [])),
        "execution_allowed": False,
    }


def stable_proposal_id(queue_index: int, intent: str, action_class: str) -> str:
    digest = sha1(f"{queue_index}:{action_class}:{intent}".encode("utf-8")).hexdigest()[:10]
    return f"proposal_{queue_index + 1:04d}_{digest}"


def pending_count(proposals: list[dict[str, Any]]) -> int:
    return sum(1 for proposal in proposals if proposal.get("status") == "pending_review")
