from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ActionPolicy:
    action_class: str
    requires_approval: bool
    default_decision: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


POLICY_VERSION = "metis_governance_policy.v0.1"

KEYWORDS: tuple[tuple[str, str, str], ...] = (
    ("sensitive_action", "credentials", "credential or secret material"),
    ("sensitive_action", "password", "credential or secret material"),
    ("sensitive_action", "token", "credential or secret material"),
    ("sensitive_action", "legal", "legal-sensitive action"),
    ("sensitive_action", "bank", "financial-sensitive action"),
    ("sensitive_action", "medical", "health-sensitive action"),
    ("actuator_action", "move robot", "physical actuation"),
    ("actuator_action", "turn on camera", "capture or hardware actuation"),
    ("actuator_action", "start recording", "capture or hardware actuation"),
    ("external_action", "send", "external or identity-bearing action"),
    ("external_action", "email", "external or identity-bearing action"),
    ("external_action", "publish", "external publication"),
    ("external_action", "post", "external publication"),
    ("external_action", "purchase", "external purchase"),
    ("external_action", "buy", "external purchase"),
    ("external_action", "schedule", "calendar or external action"),
    ("external_action", "create issue", "external issue creation"),
    ("modify_local", "commit", "local repository modification"),
    ("modify_local", "edit file", "local file modification"),
    ("modify_local", "write file", "local file modification"),
    ("propose_memory", "remember", "memory proposal"),
    ("propose_memory", "save memory", "memory proposal"),
    ("retrieve", "search", "retrieval request"),
    ("retrieve", "find", "retrieval request"),
    ("draft", "draft", "draft-only work"),
    ("draft", "plan", "planning or drafting work"),
)

DECISIONS = {
    "observe": ("allow", False),
    "retrieve": ("allow", False),
    "draft": ("allow_draft_only", False),
    "propose_memory": ("queue_for_review", True),
    "modify_local": ("queue_for_approval", True),
    "external_action": ("queue_for_approval", True),
    "sensitive_action": ("block_by_default", True),
    "actuator_action": ("queue_for_hardware_and_governance", True),
}


def classify_intent(intent: str, state: dict[str, Any] | None = None) -> ActionPolicy:
    lowered = intent.lower()
    matches: list[tuple[str, str]] = []
    for action_class, keyword, reason in KEYWORDS:
        if keyword in lowered:
            matches.append((action_class, reason))
    action_class = _highest_priority([item[0] for item in matches]) or "observe"
    default_decision, requires_approval = DECISIONS[action_class]
    reasons = [reason for matched_class, reason in matches if matched_class == action_class]
    if not reasons:
        reasons = ["no governed action keyword detected"]
    if state and state.get("interaction_mode") == "agent" and action_class in {"external_action", "modify_local", "sensitive_action", "actuator_action", "propose_memory"}:
        reasons.append("Agent Mode can prepare proposals only")
    return ActionPolicy(
        action_class=action_class,
        requires_approval=requires_approval,
        default_decision=default_decision,
        reasons=list(dict.fromkeys(reasons)),
    )


def should_queue_proposal(policy: ActionPolicy, state: dict[str, Any]) -> bool:
    return bool(
        state.get("interaction_mode") == "agent"
        and policy.action_class in {"external_action", "modify_local", "sensitive_action", "actuator_action", "propose_memory"}
    )


def _highest_priority(classes: list[str]) -> str | None:
    priority = ["sensitive_action", "actuator_action", "external_action", "modify_local", "propose_memory", "retrieve", "draft", "observe"]
    for action_class in priority:
        if action_class in classes:
            return action_class
    return None
