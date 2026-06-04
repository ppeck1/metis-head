from __future__ import annotations

from typing import Any


PLAN_ADVANCE_VERSION = "metis_tool_plan_advance.v0.1"


def next_plan_action(plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    review_status = str(plan.get("review_status", "pending"))
    if review_status == "pending":
        return _action("needs_plan_review", plan, "Plan must be approved or denied before any step proposal can be queued.")
    if review_status == "denied":
        return _action("plan_denied", plan, "Plan was denied; no further governed action is available.")

    steps = [step for step in plan.get("steps", []) if isinstance(step, dict)]
    eligible_steps = [step for step in steps if step.get("tool_id") and step.get("status") not in {"blocked_no_tool", "blocked_invalid_arguments"}]
    unqueued = [step for step in eligible_steps if not step.get("proposal_id")]
    if unqueued:
        return _action("can_queue_step_proposals", plan, "Approved plan has eligible steps without proposal IDs.")

    proposals = state.get("approval_queue", []) if isinstance(state.get("approval_queue"), list) else []
    proposal_map = {proposal.get("proposal_id"): proposal for proposal in proposals if isinstance(proposal, dict)}

    bindable = []
    for step in eligible_steps:
        proposal = proposal_map.get(step.get("proposal_id"))
        step_text = str(step.get("arguments", {}).get("text") or "")
        proposal_text = str((proposal or {}).get("tool_arguments", {}).get("text") or "")
        if (
            step.get("tool_id") == "text.summarize"
            and proposal
            and proposal.get("review_status", "pending") == "pending"
            and not step.get("bound_arguments")
            and ("<requires approved" in step_text or "<requires approved" in proposal_text)
            and _has_prior_executed_step(step, eligible_steps)
        ):
            bindable.append({"step_id": step.get("step_id"), "proposal_id": proposal.get("proposal_id")})
    if bindable:
        return _action("can_bind_results", plan, "Pending dependent dry-run steps can bind safe prior receipt summaries.", ready_steps=bindable)

    pending_reviews = []
    for step in eligible_steps:
        proposal = proposal_map.get(step.get("proposal_id"))
        if proposal and proposal.get("review_status", "pending") == "pending" and not _is_unbound_dependent_step(step, proposal):
            pending_reviews.append({"step_id": step.get("step_id"), "proposal_id": proposal.get("proposal_id"), "tool_id": proposal.get("tool_id")})
    if pending_reviews:
        return _action(
            "needs_step_proposal_review",
            plan,
            "One or more step proposals require human review.",
            waiting_on=pending_reviews,
        )

    executable = []
    for step in eligible_steps:
        proposal = proposal_map.get(step.get("proposal_id"))
        if proposal and proposal.get("review_status") == "approved" and not step.get("execution_receipt_id"):
            executable.append({"step_id": step.get("step_id"), "proposal_id": proposal.get("proposal_id"), "tool_id": proposal.get("tool_id")})
    if executable:
        return _action("can_request_step_execution", plan, "Approved step proposals can have execution requested.", ready_steps=executable)

    blocked = []
    for step in eligible_steps:
        proposal = proposal_map.get(step.get("proposal_id"))
        if proposal and proposal.get("review_status") == "denied":
            blocked.append({"step_id": step.get("step_id"), "proposal_id": proposal.get("proposal_id"), "tool_id": proposal.get("tool_id")})
    if blocked:
        return _action("blocked_by_denied_step", plan, "One or more step proposals were denied.", waiting_on=blocked)

    return _action("complete_for_current_scope", plan, "No further governed simulator action is available for this plan.")


def _action(action: str, plan: dict[str, Any], detail: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": PLAN_ADVANCE_VERSION,
        "action": action,
        "plan_id": plan.get("plan_id"),
        "detail": detail,
        "execution_allowed": False,
        "autonomous_execution_allowed": False,
        **extra,
    }


def _has_prior_executed_step(target_step: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    target_id = str(target_step.get("step_id") or "")
    for step in steps:
        if str(step.get("step_id") or "") >= target_id:
            return False
        if step.get("execution_receipt_id") or step.get("execution_status") in {"executed_read_only", "dry_run_only_not_executed"}:
            return True
    return False


def _is_unbound_dependent_step(step: dict[str, Any], proposal: dict[str, Any]) -> bool:
    if step.get("tool_id") != "text.summarize" or step.get("bound_arguments"):
        return False
    step_text = str(step.get("arguments", {}).get("text") or "")
    proposal_text = str(proposal.get("tool_arguments", {}).get("text") or "")
    return "<requires approved" in step_text or "<requires approved" in proposal_text
