from __future__ import annotations

from contextlib import asynccontextmanager
from hashlib import sha1
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .artifacts import ArtifactError, list_artifacts, read_artifact, save_artifact
from .boh_link import (
    LINK_AUTH_FAILED,
    get_link_state,
    start_background_link,
    stop_background_link,
)
from .boh_retrieval import BOHRetrievalResult, boh_config_from_env, render_context, retrieve_boh_context
from .bridge import HARDWARE_PARITY_MANIFEST
from .execution_policy import read_only_execution_policy
from .governance import POLICY_VERSION, classify_intent, should_queue_proposal
from .leds import resolve_leds
from .llm_providers import LLMProviderError, governed_messages, list_ollama_models, probe_llm_provider, provider_from_config
from .personality import personality_profile
from .provider_harness import ProviderHarnessError, invoke_provider, provider_catalog
from .read_only_tools import ReadOnlyToolError, execute_filesystem_read, execute_git_status
from .readiness import calculate_readiness
from .reducer import clear_failures, reduce_metis_event, replay_events
from .scenarios import SCENARIOS, run_all_scenarios, run_scenario
from .schemas import FAILURE_TABLE, baseline_state, utc_now
from .sim_manifest import build_sim_test_manifest
from .tool_contract import build_tool_contract_manifest
from .tool_completion import calculate_tool_completion
from .tool_governance import evaluate_tool_request
from .tool_policy_snapshot import build_tool_policy_snapshot
from .tool_plan_runner import next_plan_action
from .tool_readiness import calculate_tool_readiness
from .tool_registry import ToolRegistryError, build_tool_proposal_event, dry_run_tool, execute_tool, get_tool, list_tools, route_tool_request
from .tool_task_planner import plan_tool_task
from .voice import VoiceResult, speak_text, stop_voice, voice_options, voice_profile


@asynccontextmanager
async def _lifespan(_: FastAPI):
    start_background_link()
    try:
        yield
    finally:
        stop_background_link()


app = FastAPI(title="Metis Head Mock Brain", version="0.0.1", lifespan=_lifespan)
STATE = baseline_state()
SCENARIO_RESULTS: list[dict[str, Any]] = []


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")


@app.get("/metis/personality/console")
def personality_console() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "personality_console.html")


@app.get("/metis/personality")
def personality(mode: str | None = None) -> dict[str, Any]:
    if mode is None:
        mode = "agent" if STATE.get("interaction_mode") == "agent" else "counsel"
    return personality_profile(mode)


@app.get("/metis/boh/status")
def boh_status() -> dict[str, Any]:
    return get_link_state().to_dict()


@app.get("/metis/state")
def get_state() -> dict[str, Any]:
    return {"state": STATE, "leds": resolve_leds(STATE), "readiness": calculate_readiness()}


@app.get("/metis/export")
def export_state() -> dict[str, Any]:
    return {
        "state": STATE,
        "leds": resolve_leds(STATE),
        "readiness": calculate_readiness(),
        "event_log": STATE.get("event_log", []),
        "export_schema": "metis_export.v0.1",
    }


def _export_payload() -> dict[str, Any]:
    return {
        "state": STATE,
        "leds": resolve_leds(STATE),
        "readiness": calculate_readiness(),
        "event_log": STATE.get("event_log", []),
        "export_schema": "metis_export.v0.1",
    }


@app.post("/metis/artifacts/save")
def artifacts_save(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    artifact_type = str(payload.get("artifact_type") or "export")
    label = payload.get("label")
    try:
        if artifact_type == "export":
            artifact_payload = _export_payload()
        elif artifact_type == "manifest":
            artifact_payload = build_sim_test_manifest(include_results=bool(payload.get("include_results", True)))
        else:
            raise ArtifactError(f"unsupported artifact type: {artifact_type}")
        return save_artifact(artifact_payload, artifact_type, str(label) if label is not None else None)
    except ArtifactError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/metis/artifacts")
def artifacts_list() -> dict[str, Any]:
    return {"artifact_schema": "metis_artifact.v0.1", "artifacts": list_artifacts()}


@app.get("/metis/artifacts/{filename}")
def artifacts_get(filename: str) -> dict[str, Any]:
    try:
        return read_artifact(filename)
    except ArtifactError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/metis/sim/manifest")
def sim_manifest(include_results: bool = True) -> dict[str, Any]:
    return build_sim_test_manifest(include_results=include_results)


@app.get("/metis/sim/tests")
def sim_tests(include_results: bool = True) -> dict[str, Any]:
    return build_sim_test_manifest(include_results=include_results)


@app.get("/metis/proposals")
def proposals(status: str | None = None, proposal_type: str | None = None, tool_id: str | None = None) -> dict[str, Any]:
    queue = list(STATE.get("approval_queue", []))
    filtered = queue
    if status:
        filtered = [proposal for proposal in filtered if proposal.get("review_status") == status or proposal.get("status") == status]
    if proposal_type:
        filtered = [proposal for proposal in filtered if proposal.get("proposal_type") == proposal_type]
    if tool_id:
        filtered = [proposal for proposal in filtered if proposal.get("tool_id") == tool_id]
    return {
        "proposals": filtered,
        "pending_approval_count": STATE.get("pending_approval_count", 0),
        "total_count": len(queue),
        "filtered_count": len(filtered),
        "filters": {"status": status or "", "proposal_type": proposal_type or "", "tool_id": tool_id or ""},
    }


@app.get("/metis/tools/plans")
def tool_plans(status: str | None = None) -> dict[str, Any]:
    plans = list(STATE.get("tool_plan_queue", []))
    filtered = plans
    if status:
        filtered = [plan for plan in filtered if plan.get("review_status") == status or plan.get("status") == status]
    return {
        "plans": filtered,
        "total_count": len(plans),
        "filtered_count": len(filtered),
        "filters": {"status": status or ""},
    }


def _tool_plan_by_id(plan_id: str) -> dict[str, Any] | None:
    for plan in STATE.get("tool_plan_queue", []):
        if plan.get("plan_id") == plan_id:
            return plan
    return None


@app.get("/metis/tools/plans/{plan_id}")
def tool_plan_detail(plan_id: str) -> dict[str, Any]:
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    return {"plan": plan}


def _review_tool_plan(plan_id: str, decision: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status", "pending") != "pending":
        raise HTTPException(status_code=409, detail="tool plan already reviewed")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    event = {
        "type": "tool_plan_review",
        "plan_id": plan_id,
        "decision": decision,
        "reason": reason,
        "reviewed_at": utc_now(),
    }
    STATE = reduce_metis_event(STATE, event)
    reviewed = _tool_plan_by_id(plan_id)
    return {
        "status": f"tool_plan_{decision}",
        "plan": reviewed,
        "review_receipt": reviewed.get("review_receipt") if reviewed else None,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/tools/plans/{plan_id}/approve")
def approve_tool_plan(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_tool_plan(plan_id, "approved", payload)


@app.post("/metis/tools/plans/{plan_id}/deny")
def deny_tool_plan(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_tool_plan(plan_id, "denied", payload)


def _plan_step_queue_candidates(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "")
        tool_id = step.get("tool_id")
        if not tool_id:
            skipped.append({"step_id": step_id, "reason": "no_tool"})
        elif step.get("proposal_id"):
            skipped.append({"step_id": step_id, "tool_id": tool_id, "reason": "already_queued"})
        elif step.get("status") in {"blocked_no_tool", "blocked_invalid_arguments"}:
            skipped.append({"step_id": step_id, "tool_id": tool_id, "reason": step.get("status")})
        else:
            candidates.append(step)
    return candidates, skipped


@app.post("/metis/tools/plans/{plan_id}/queue_steps")
def queue_tool_plan_steps(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status") != "approved":
        raise HTTPException(status_code=409, detail="tool plan must be approved before steps can be queued")
    candidates, skipped = _plan_step_queue_candidates(plan)
    queued_steps: list[dict[str, Any]] = []
    queued_proposals: list[dict[str, Any]] = []
    reason_prefix = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str) and payload["reason"].strip():
        reason_prefix = f"{payload['reason'].strip()}; "
    try:
        for step in candidates:
            tool_id = str(step["tool_id"])
            reason = f"{reason_prefix}plan {plan_id} {step.get('step_id')}: {step.get('reason', 'planned tool step')}"
            queued = _queue_tool_proposal(tool_id, step.get("arguments") or {}, reason)
            proposal = queued.get("proposal") or {}
            queued_steps.append({"step_id": step.get("step_id"), "tool_id": tool_id, "proposal_id": proposal.get("proposal_id")})
            queued_proposals.append(proposal)
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if queued_steps:
        event = {"type": "tool_plan_step_queue", "plan_id": plan_id, "queued_steps": queued_steps, "queued_at": utc_now()}
        STATE = reduce_metis_event(STATE, event)
    else:
        event = None
    reviewed_plan = _tool_plan_by_id(plan_id)
    return {
        "status": "plan_step_proposals_queued" if queued_steps else "no_plan_steps_queued",
        "plan": reviewed_plan,
        "queued_steps": queued_steps,
        "queued_proposals": queued_proposals,
        "skipped_steps": skipped,
        "event": event,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/tools/plans/{plan_id}/request_execution")
def request_tool_plan_execution(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status") != "approved":
        raise HTTPException(status_code=409, detail="tool plan must be approved before execution can be requested")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    executed_steps: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    skipped_steps: list[dict[str, Any]] = []
    try:
        for step in plan.get("steps", []):
            if not isinstance(step, dict):
                continue
            proposal_id = step.get("proposal_id")
            if not proposal_id:
                skipped_steps.append({"step_id": step.get("step_id"), "reason": "no_proposal"})
                continue
            if step.get("execution_receipt_id"):
                skipped_steps.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "already_requested"})
                continue
            proposal = _proposal_by_id(str(proposal_id))
            if proposal is None:
                skipped_steps.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "proposal_missing"})
                continue
            if proposal.get("review_status") != "approved":
                skipped_steps.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "proposal_not_approved"})
                continue
            event = _execution_request_event_for_proposal(proposal, reason or f"plan {plan_id} {step.get('step_id')}")
            STATE = reduce_metis_event(STATE, event)
            receipt = STATE.get("execution_audit_log", [])[-1]
            receipts.append(receipt)
            executed_steps.append(
                {
                    "step_id": step.get("step_id"),
                    "proposal_id": proposal_id,
                    "receipt_id": receipt.get("receipt_id"),
                    "execution_status": receipt.get("execution_status"),
                }
            )
    except (ToolRegistryError, ReadOnlyToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if executed_steps:
        plan_event = {"type": "tool_plan_execution_request", "plan_id": plan_id, "executed_steps": executed_steps, "requested_at": utc_now()}
        STATE = reduce_metis_event(STATE, plan_event)
    else:
        plan_event = None
    return {
        "status": "plan_execution_requested" if executed_steps else "no_plan_execution_requested",
        "plan": _tool_plan_by_id(plan_id),
        "executed_steps": executed_steps,
        "receipts": receipts,
        "skipped_steps": skipped_steps,
        "event": plan_event,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


def _receipt_for_step(step: dict[str, Any]) -> dict[str, Any] | None:
    receipt_id = step.get("execution_receipt_id")
    if receipt_id:
        return _receipt_by_id(str(receipt_id))
    proposal_id = step.get("proposal_id")
    if not proposal_id:
        return None
    for receipt in reversed(STATE.get("execution_audit_log", [])):
        if receipt.get("proposal_id") == proposal_id:
            return receipt
    return None


def _binding_text_from_receipt(receipt: dict[str, Any]) -> str:
    summary = receipt.get("output_summary") if isinstance(receipt.get("output_summary"), dict) else {}
    preview = summary.get("preview") if isinstance(summary.get("preview"), dict) else {}
    preview_items: list[str] = []
    for key in sorted(preview):
        value = str(preview[key])
        preview_items.append(f"{key}: {value[:180]}")
    text = "; ".join(preview_items)
    return (
        f"Governed receipt summary from {receipt.get('tool_id')} "
        f"({receipt.get('receipt_id')}, hash {receipt.get('output_hash', 'none')}): {text}"
    )[:900]


def _plan_result_bindings(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bindings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    source_step: dict[str, Any] | None = None
    source_receipt: dict[str, Any] | None = None
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue
        receipt = _receipt_for_step(step)
        if receipt and receipt.get("execution_status") in {"executed_read_only", "dry_run_only_not_executed"}:
            source_step = step
            source_receipt = receipt
        if step.get("tool_id") != "text.summarize":
            continue
        proposal_id = step.get("proposal_id")
        proposal = _proposal_by_id(str(proposal_id)) if proposal_id else None
        if proposal is None:
            skipped.append({"step_id": step.get("step_id"), "reason": "proposal_missing"})
            continue
        if proposal.get("review_status", "pending") != "pending":
            skipped.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "proposal_already_reviewed"})
            continue
        current_text = str(proposal.get("tool_arguments", {}).get("text") or "")
        step_text = str(step.get("arguments", {}).get("text") or "")
        if "<requires approved" not in current_text and "<requires approved" not in step_text and not step.get("bound_arguments"):
            skipped.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "no_binding_placeholder"})
            continue
        if source_step is None or source_receipt is None:
            skipped.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "source_receipt_missing"})
            continue
        bindings.append(
            {
                "step_id": step.get("step_id"),
                "proposal_id": proposal_id,
                "source_step_id": source_step.get("step_id"),
                "source_receipt_id": source_receipt.get("receipt_id"),
                "source_output_hash": source_receipt.get("output_hash"),
                "arguments": {"text": _binding_text_from_receipt(source_receipt), "max_words": 48},
            }
        )
    return bindings, skipped


@app.post("/metis/tools/plans/{plan_id}/bind_results")
def bind_tool_plan_results(plan_id: str) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status") != "approved":
        raise HTTPException(status_code=409, detail="tool plan must be approved before results can be bound")
    bindings, skipped = _plan_result_bindings(plan)
    if bindings:
        event = {"type": "tool_plan_result_binding", "plan_id": plan_id, "bindings": bindings, "bound_at": utc_now()}
        STATE = reduce_metis_event(STATE, event)
    else:
        event = None
    return {
        "status": "plan_results_bound" if bindings else "no_plan_results_bound",
        "plan": _tool_plan_by_id(plan_id),
        "bindings": bindings,
        "skipped_steps": skipped,
        "event": event,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/tools/plans/{plan_id}/advance")
def advance_tool_plan(plan_id: str) -> dict[str, Any]:
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    action = next_plan_action(plan, STATE)
    if action["action"] == "can_queue_step_proposals":
        result = queue_tool_plan_steps(plan_id, {"reason": "guided advance queued step proposals"})
        return {"status": "advanced", "advanced_action": action, "result": result, "next_action": next_plan_action(_tool_plan_by_id(plan_id), STATE)}
    if action["action"] == "can_request_step_execution":
        result = request_tool_plan_execution(plan_id, {"reason": "guided advance requested approved step execution"})
        return {"status": "advanced", "advanced_action": action, "result": result, "next_action": next_plan_action(_tool_plan_by_id(plan_id), STATE)}
    if action["action"] == "can_bind_results":
        result = bind_tool_plan_results(plan_id)
        return {"status": "advanced", "advanced_action": action, "result": result, "next_action": next_plan_action(_tool_plan_by_id(plan_id), STATE)}
    return {"status": "waiting", "next_action": action, "plan": plan, "state": STATE, "leds": resolve_leds(STATE)}


def _proposal_by_id(proposal_id: str) -> dict[str, Any] | None:
    for proposal in STATE.get("approval_queue", []):
        if proposal.get("proposal_id") == proposal_id:
            return proposal
    return None


@app.get("/metis/proposals/{proposal_id}")
def proposal_detail(proposal_id: str) -> dict[str, Any]:
    proposal = _proposal_by_id(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    return {"proposal": proposal}


def _review_proposal(proposal_id: str, decision: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    proposal = _proposal_by_id(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if proposal.get("review_status", "pending") != "pending":
        raise HTTPException(status_code=409, detail="proposal already reviewed")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": decision,
        "reason": reason,
        "reviewed_at": utc_now(),
    }
    STATE = reduce_metis_event(STATE, event)
    reviewed = _proposal_by_id(proposal_id)
    return {
        "status": f"proposal_{decision}",
        "proposal": reviewed,
        "review_receipt": reviewed.get("review_receipt") if reviewed else None,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_proposal(proposal_id, "approved", payload)


@app.post("/metis/proposals/{proposal_id}/deny")
def deny_proposal(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_proposal(proposal_id, "denied", payload)


def _receipt_by_id(receipt_id: str) -> dict[str, Any] | None:
    for receipt in STATE.get("execution_audit_log", []):
        if receipt.get("receipt_id") == receipt_id:
            return receipt
    return None


@app.get("/metis/execution/receipts")
def execution_receipts() -> dict[str, Any]:
    return {"receipts": STATE.get("execution_audit_log", []), "receipt_count": len(STATE.get("execution_audit_log", []))}


@app.get("/metis/execution/receipts/{receipt_id}")
def execution_receipt_detail(receipt_id: str) -> dict[str, Any]:
    receipt = _receipt_by_id(receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="execution receipt not found")
    return {"receipt": receipt}


@app.get("/metis/execution/policy")
def execution_policy() -> dict[str, Any]:
    return read_only_execution_policy()


def _execution_request_event_for_proposal(proposal: dict[str, Any], reason: str = "") -> dict[str, Any]:
    dry_run_receipt = None
    read_only_result = None
    if proposal.get("review_status") == "approved" and proposal.get("tool_id") == "time.now":
        read_only_result = dry_run_tool("time.now", proposal.get("tool_arguments") or {})["result"]
    elif proposal.get("review_status") == "approved" and proposal.get("tool_id") == "git.status":
        read_only_result = execute_git_status(proposal.get("tool_arguments") or {})
    elif proposal.get("review_status") == "approved" and proposal.get("tool_id") == "filesystem.read":
        read_only_result = execute_filesystem_read(proposal.get("tool_arguments") or {})
    elif proposal.get("review_status") == "approved" and proposal.get("dry_run_available") and proposal.get("side_effect_class") == "none":
        dry_run_receipt = dry_run_tool(str(proposal.get("tool_id")), proposal.get("tool_arguments") or {})
    event = {
        "type": "execution_request",
        "proposal_id": proposal.get("proposal_id"),
        "reason": reason,
        "requested_at": utc_now(),
    }
    if dry_run_receipt:
        event["dry_run_receipt"] = dry_run_receipt
    if read_only_result:
        event["read_only_result"] = read_only_result
    return event


@app.post("/metis/proposals/{proposal_id}/request_execution")
def request_proposal_execution(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    proposal = _proposal_by_id(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    try:
        event = _execution_request_event_for_proposal(proposal, reason)
    except (ToolRegistryError, ReadOnlyToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    STATE = reduce_metis_event(STATE, event)
    receipt = STATE.get("execution_audit_log", [])[-1] if STATE.get("execution_audit_log") else None
    return {
        "status": receipt.get("execution_status") if receipt else "not_recorded",
        "receipt": receipt,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.get("/metis/tools")
def tools() -> dict[str, Any]:
    return list_tools()


@app.get("/metis/tools/contract")
def tool_contract() -> dict[str, Any]:
    return build_tool_contract_manifest()


@app.get("/metis/tools/policy_snapshot")
def tool_policy_snapshot() -> dict[str, Any]:
    return build_tool_policy_snapshot(STATE)


@app.post("/metis/tools/governance/evaluate")
def tool_governance_evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    tool_id = payload.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise HTTPException(status_code=400, detail="tool_id is required")
    try:
        return evaluate_tool_request(tool_id, payload.get("arguments") or {}, STATE, str(payload.get("request_type") or "dry_run"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/metis/tools/readiness")
def tool_readiness() -> dict[str, Any]:
    return calculate_tool_readiness(STATE)


@app.get("/metis/tools/completion")
def tool_completion() -> dict[str, Any]:
    return calculate_tool_completion(STATE)


@app.post("/metis/tools/task/plan")
def tool_task_plan(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    try:
        plan = plan_tool_task(str(payload.get("task") or ""), STATE)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.get("persist", True) is False:
        return plan
    if _tool_plan_by_id(plan["plan_id"]):
        return {"status": "plan_already_exists", "plan": _tool_plan_by_id(plan["plan_id"]), "state": STATE, "leds": resolve_leds(STATE)}
    event = {"type": "tool_plan", "plan": plan}
    STATE = reduce_metis_event(STATE, event)
    return {"status": "plan_queued", "plan": _tool_plan_by_id(plan["plan_id"]), "event": event, "state": STATE, "leds": resolve_leds(STATE)}


def _route_chat_plan_request(message: str) -> str | None:
    text = message.strip()
    lowered = text.lower()
    prefixes = ("plan task:", "plan tool task:", "task plan:", "create tool plan:", "make tool plan:")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip()
    return None


def _queue_chat_tool_plan(task: str) -> dict[str, Any]:
    global STATE
    if not task:
        raise ValueError("task is required")
    plan = plan_tool_task(task, STATE)
    existing = _tool_plan_by_id(plan["plan_id"])
    if existing:
        return {"status": "plan_already_exists", "plan": existing, "next_action": next_plan_action(existing, STATE)}
    event = {"type": "tool_plan", "plan": plan}
    STATE = reduce_metis_event(STATE, event)
    queued_plan = _tool_plan_by_id(plan["plan_id"])
    return {"status": "plan_queued", "plan": queued_plan, "event": event, "next_action": next_plan_action(queued_plan, STATE)}


def _latest_tool_plan() -> dict[str, Any] | None:
    plans = STATE.get("tool_plan_queue", [])
    if not plans:
        return None
    return plans[-1]


def _plan_id_from_text(message: str) -> str | None:
    for token in re.split(r"[\s,;]+", message):
        cleaned = token.strip().strip(".:?!()[]{}'\"")
        if cleaned.startswith("plan_id="):
            return cleaned.split("=", 1)[1].strip(".:?!()[]{}'\"") or None
        if cleaned.startswith("plan_"):
            return cleaned
    return None


def _route_chat_plan_control_request(message: str) -> dict[str, str | None] | None:
    text = message.strip()
    lowered = text.lower()
    plan_id = _plan_id_from_text(text)
    advance_phrases = (
        "advance tool plan",
        "continue tool plan",
        "advance plan",
        "continue plan",
        "move tool plan forward",
    )
    status_phrases = (
        "tool plan status",
        "plan status",
        "what is next for my tool plan",
        "what's next for my tool plan",
        "next tool plan step",
        "tool plan next",
    )
    if any(phrase in lowered for phrase in advance_phrases):
        return {"action": "advance", "plan_id": plan_id}
    if any(phrase in lowered for phrase in status_phrases):
        return {"action": "status", "plan_id": plan_id}
    return None


def _resolve_chat_plan(plan_id: str | None) -> dict[str, Any]:
    plan = _tool_plan_by_id(plan_id) if plan_id else _latest_tool_plan()
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    return plan


def _plan_control_message(plan: dict[str, Any], next_action: dict[str, Any], status: str) -> str:
    review_status = plan.get("review_status", "pending")
    action = next_action.get("action", "unknown")
    reason = next_action.get("reason") or next_action.get("message") or "No additional detail."
    return (
        f"Governed tool plan {status}: {plan['plan_id']} is {review_status} with "
        f"{plan.get('step_count', 0)} step(s). Next action: {action}. {reason} "
        "Chat cannot approve plans, approve proposals, or grant standing execution."
    )


def _chat_plan_status(plan_id: str | None) -> dict[str, Any]:
    plan = _resolve_chat_plan(plan_id)
    action = next_plan_action(plan, STATE)
    return {"status": "plan_status", "plan": plan, "next_action": action}


def _chat_plan_advance(plan_id: str | None) -> dict[str, Any]:
    plan = _resolve_chat_plan(plan_id)
    advanced = advance_tool_plan(plan["plan_id"])
    latest = _tool_plan_by_id(plan["plan_id"]) or plan
    return {"status": "plan_advance_requested", "plan": latest, "advance": advanced, "next_action": advanced.get("next_action") or next_plan_action(latest, STATE)}


def _route_chat_queue_status_request(message: str) -> str | None:
    lowered = message.strip().lower()
    proposal_phrases = (
        "what needs approval",
        "what is waiting for approval",
        "what's waiting for approval",
        "pending approvals",
        "pending proposals",
        "approval queue",
        "proposal status",
        "what needs review",
    )
    receipt_phrases = (
        "execution receipts",
        "receipt summary",
        "receipt status",
        "audit receipts",
        "tool receipts",
        "what receipts",
    )
    if any(phrase in lowered for phrase in receipt_phrases):
        return "receipts"
    if any(phrase in lowered for phrase in proposal_phrases):
        return "proposals"
    return None


def _proposal_id_from_text(message: str) -> str | None:
    for token in re.split(r"[\s,;]+", message):
        cleaned = token.strip().strip(".:?!()[]{}'\"")
        if cleaned.startswith("proposal_id="):
            return cleaned.split("=", 1)[1].strip(".:?!()[]{}'\"") or None
        if cleaned.startswith("proposal_"):
            return cleaned
    return None


def _route_chat_next_action_request(message: str) -> dict[str, str | None] | None:
    text = message.strip()
    lowered = text.lower()
    phrases = (
        "what should i do next",
        "what do i do next",
        "next governed action",
        "next approval step",
        "what is the next approval step",
        "how do i approve",
        "how do i deny",
        "how do i request execution",
        "how should i proceed",
    )
    if not any(phrase in lowered for phrase in phrases):
        return None
    return {"plan_id": _plan_id_from_text(text), "proposal_id": _proposal_id_from_text(text)}


def _receipt_exists_for_proposal(proposal_id: str) -> bool:
    return any(receipt.get("proposal_id") == proposal_id for receipt in STATE.get("execution_audit_log", []))


def _instruction_payload(
    *,
    recommended_action: str,
    target_type: str,
    target_id: str | None,
    ui_instruction: str,
    api_instruction: dict[str, str | None],
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "next_action_instruction",
        "recommended_action": recommended_action,
        "target": {"type": target_type, "id": target_id},
        "ui_instruction": ui_instruction,
        "api_instruction": api_instruction,
        "reason": reason,
        "execution_allowed": False,
        "chat_may_perform_action": False,
    }


def _proposal_instruction(proposal: dict[str, Any]) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposal_id") or "")
    review_status = str(proposal.get("review_status") or "pending")
    if review_status == "pending":
        return _instruction_payload(
            recommended_action="review_proposal",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Approve or Deny.",
            api_instruction={"approve": f"POST /metis/proposals/{proposal_id}/approve", "deny": f"POST /metis/proposals/{proposal_id}/deny"},
            reason="Proposal is pending human review.",
        )
    if review_status == "approved" and not _receipt_exists_for_proposal(proposal_id):
        return _instruction_payload(
            recommended_action="request_execution_receipt",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Request Execution.",
            api_instruction={"request_execution": f"POST /metis/proposals/{proposal_id}/request_execution"},
            reason="Proposal is approved and can move to the existing execution-request receipt gate.",
        )
    if review_status == "approved":
        return _instruction_payload(
            recommended_action="inspect_receipt",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction="Open the Tools panel and refresh Execution Receipts.",
            api_instruction={"list_receipts": "GET /metis/execution/receipts"},
            reason="Proposal is already approved and has at least one receipt.",
        )
    return _instruction_payload(
        recommended_action="no_action_available",
        target_type="proposal",
        target_id=proposal_id,
        ui_instruction="No governed action is available for this proposal.",
        api_instruction={"detail": f"GET /metis/proposals/{proposal_id}"},
        reason=f"Proposal review status is {review_status}.",
    )


def _plan_instruction(plan: dict[str, Any]) -> dict[str, Any]:
    plan_id = str(plan.get("plan_id") or "")
    action = next_plan_action(plan, STATE)
    action_name = action.get("action")
    if action_name == "needs_plan_review":
        return _instruction_payload(
            recommended_action="review_tool_plan",
            target_type="tool_plan",
            target_id=plan_id,
            ui_instruction=f"Open the Tools panel, select plan {plan_id}, then click Approve Plan or Deny Plan.",
            api_instruction={"approve": f"POST /metis/tools/plans/{plan_id}/approve", "deny": f"POST /metis/tools/plans/{plan_id}/deny"},
            reason=str(action.get("detail") or "Plan requires review."),
        )
    if action_name == "can_queue_step_proposals":
        return _instruction_payload(
            recommended_action="advance_plan_queue_steps",
            target_type="tool_plan",
            target_id=plan_id,
            ui_instruction=f"Open the Tools panel, select plan {plan_id}, then click Advance Plan.",
            api_instruction={"advance": f"POST /metis/tools/plans/{plan_id}/advance", "queue_steps": f"POST /metis/tools/plans/{plan_id}/queue_steps"},
            reason=str(action.get("detail") or "Approved plan can queue step proposals."),
        )
    if action_name == "needs_step_proposal_review":
        waiting = action.get("waiting_on", [])
        proposal_id = waiting[0].get("proposal_id") if waiting and isinstance(waiting[0], dict) else None
        return _instruction_payload(
            recommended_action="review_step_proposal",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Approve or Deny.",
            api_instruction={"approve": f"POST /metis/proposals/{proposal_id}/approve", "deny": f"POST /metis/proposals/{proposal_id}/deny"},
            reason=str(action.get("detail") or "A step proposal requires review."),
        )
    if action_name == "can_request_step_execution":
        ready = action.get("ready_steps", [])
        proposal_id = ready[0].get("proposal_id") if ready and isinstance(ready[0], dict) else None
        return _instruction_payload(
            recommended_action="request_step_execution_receipt",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Request Execution, or select plan {plan_id} and click Advance Plan.",
            api_instruction={"request_execution": f"POST /metis/proposals/{proposal_id}/request_execution", "advance": f"POST /metis/tools/plans/{plan_id}/advance"},
            reason=str(action.get("detail") or "Approved step proposal can move to the receipt gate."),
        )
    if action_name == "can_bind_results":
        return _instruction_payload(
            recommended_action="bind_plan_results",
            target_type="tool_plan",
            target_id=plan_id,
            ui_instruction=f"Open the Tools panel, select plan {plan_id}, then click Bind Results or Advance Plan.",
            api_instruction={"bind_results": f"POST /metis/tools/plans/{plan_id}/bind_results", "advance": f"POST /metis/tools/plans/{plan_id}/advance"},
            reason=str(action.get("detail") or "Safe receipt summaries can be bound into dependent steps."),
        )
    return _instruction_payload(
        recommended_action=str(action_name or "no_action_available"),
        target_type="tool_plan",
        target_id=plan_id,
        ui_instruction="No governed operator action is currently required for this plan.",
        api_instruction={"detail": f"GET /metis/tools/plans/{plan_id}"},
        reason=str(action.get("detail") or "No next action."),
    )


def _next_action_instruction(plan_id: str | None = None, proposal_id: str | None = None) -> dict[str, Any]:
    if proposal_id:
        proposal = _proposal_by_id(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        return _proposal_instruction(proposal)
    if plan_id:
        return _plan_instruction(_resolve_chat_plan(plan_id))
    for plan in STATE.get("tool_plan_queue", []):
        if isinstance(plan, dict):
            instruction = _plan_instruction(plan)
            if instruction["recommended_action"] not in {"complete_for_current_scope", "plan_denied", "no_action_available"}:
                return instruction
    for proposal in STATE.get("approval_queue", []):
        if isinstance(proposal, dict) and proposal.get("review_status", "pending") == "pending":
            return _proposal_instruction(proposal)
    for proposal in STATE.get("approval_queue", []):
        if isinstance(proposal, dict) and proposal.get("review_status") == "approved" and not _receipt_exists_for_proposal(str(proposal.get("proposal_id") or "")):
            return _proposal_instruction(proposal)
    return _instruction_payload(
        recommended_action="no_action_available",
        target_type="workspace",
        target_id=None,
        ui_instruction="No governed approval or receipt action is currently waiting.",
        api_instruction={"proposals": "GET /metis/proposals", "plans": "GET /metis/tools/plans", "receipts": "GET /metis/execution/receipts"},
        reason="There are no pending plan reviews, proposal reviews, or approved proposals awaiting receipt requests.",
    )


def _next_action_message(instruction: dict[str, Any]) -> str:
    return (
        f"Next governed action: {instruction['recommended_action']} for "
        f"{instruction['target']['type']} {instruction['target']['id'] or 'current workspace'}. "
        f"{instruction['ui_instruction']} Chat cannot perform this action."
    )


def _proposal_status_summary(limit: int = 6) -> dict[str, Any]:
    proposals_queue = list(STATE.get("approval_queue", []))
    counts: dict[str, int] = {}
    pending: list[dict[str, Any]] = []
    for proposal in proposals_queue:
        review_status = str(proposal.get("review_status") or proposal.get("status") or "unknown")
        counts[review_status] = counts.get(review_status, 0) + 1
        if review_status == "pending":
            arguments = proposal.get("tool_arguments") if isinstance(proposal.get("tool_arguments"), dict) else {}
            pending.append(
                {
                    "proposal_id": proposal.get("proposal_id"),
                    "proposal_type": proposal.get("proposal_type"),
                    "tool_id": proposal.get("tool_id"),
                    "review_status": review_status,
                    "risk_class": proposal.get("risk_class"),
                    "side_effect_class": proposal.get("side_effect_class"),
                    "dry_run_available": bool(proposal.get("dry_run_available")),
                    "execution_allowed": False,
                    "argument_keys": sorted(str(key) for key in arguments),
                }
            )
    return {
        "status": "approval_queue_status",
        "total_count": len(proposals_queue),
        "pending_count": len(pending),
        "counts_by_review_status": counts,
        "pending_proposals": pending[:limit],
        "truncated": len(pending) > limit,
    }


def _receipt_status_summary(limit: int = 6) -> dict[str, Any]:
    receipts = list(STATE.get("execution_audit_log", []))
    counts: dict[str, int] = {}
    safe_receipts: list[dict[str, Any]] = []
    for receipt in receipts[-limit:]:
        execution_status = str(receipt.get("execution_status") or "unknown")
        counts[execution_status] = counts.get(execution_status, 0) + 1
        output_summary = receipt.get("output_summary") if isinstance(receipt.get("output_summary"), dict) else {}
        safe_receipts.append(
            {
                "receipt_id": receipt.get("receipt_id"),
                "proposal_id": receipt.get("proposal_id"),
                "tool_id": receipt.get("tool_id"),
                "execution_status": execution_status,
                "policy_decision": receipt.get("policy_decision"),
                "review_status": receipt.get("review_status"),
                "execution_allowed": False,
                "output_hash": receipt.get("output_hash"),
                "output_keys": output_summary.get("keys", []),
                "redactions": receipt.get("redactions", []),
            }
        )
    return {
        "status": "execution_receipt_status",
        "receipt_count": len(receipts),
        "counts_by_execution_status": counts,
        "receipts": safe_receipts,
        "truncated": len(receipts) > limit,
    }


def _proposal_status_message(summary: dict[str, Any]) -> str:
    pending = summary["pending_proposals"]
    if not pending:
        return (
            f"Approval queue: {summary['pending_count']} pending of {summary['total_count']} total proposals. "
            "Chat can report queue status, but cannot approve, deny, or request execution."
        )
    parts = [
        f"{item.get('proposal_id')} ({item.get('tool_id') or item.get('proposal_type')}, "
        f"{item.get('risk_class')}, {item.get('side_effect_class')})"
        for item in pending
    ]
    suffix = " More pending proposals are omitted from this summary." if summary.get("truncated") else ""
    return (
        f"Approval queue: {summary['pending_count']} pending of {summary['total_count']} total proposals. "
        f"Pending: {'; '.join(parts)}.{suffix} "
        "Chat can report queue status, but cannot approve, deny, or request execution."
    )


def _receipt_status_message(summary: dict[str, Any]) -> str:
    receipts = summary["receipts"]
    if not receipts:
        return "Execution receipts: 0 recorded. Chat can summarize receipts, but cannot create approvals or execution authority."
    parts = [
        f"{item.get('receipt_id')} ({item.get('tool_id')}, {item.get('execution_status')}, {item.get('policy_decision')})"
        for item in receipts
    ]
    suffix = " Older receipts are omitted from this summary." if summary.get("truncated") else ""
    return (
        f"Execution receipts: {summary['receipt_count']} recorded. Latest: {'; '.join(parts)}.{suffix} "
        "Raw file contents, command output, secrets, and external receipts are not included."
    )


@app.get("/metis/tools/{tool_id}")
def tool_detail(tool_id: str) -> dict[str, Any]:
    try:
        return get_tool(tool_id).to_dict()
    except ToolRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _queue_tool_proposal(tool_id: str, arguments: Any, reason: str | None = None) -> dict[str, Any]:
    global STATE
    event = build_tool_proposal_event(tool_id, arguments, STATE, reason)
    STATE = reduce_metis_event(STATE, event)
    return {
        "status": "proposal_queued",
        "tool_id": tool_id,
        "event": event,
        "proposal": STATE.get("approval_queue", [])[-1] if STATE.get("approval_queue") else None,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


def _handle_chat_tool_request(user_message: str, options: dict[str, Any]) -> dict[str, Any] | None:
    tool_options = options.get("tools") if isinstance(options.get("tools"), dict) else {}
    if tool_options.get("enabled", True) is False:
        return None
    route = route_tool_request(user_message)
    if route is None:
        return None
    tool_id = route["tool_id"]
    arguments = route.get("arguments") or {}
    tool = get_tool(tool_id)
    if STATE.get("interaction_mode") == "agent" or tool.permission_mode != "dry_run" or tool.side_effect_class != "none":
        queued = _queue_tool_proposal(tool_id, arguments, route.get("reason"))
        return {"status": "proposal_queued", "tool_id": tool_id, "route": route, "proposal": queued.get("proposal")}
    receipt = dry_run_tool(tool_id, arguments)
    return {"status": "dry_run_complete", "tool_id": tool_id, "route": route, "receipt": receipt}


def _tool_chat_message(tool_result: dict[str, Any]) -> str:
    tool_id = tool_result["tool_id"]
    if tool_result["status"] == "proposal_queued":
        return f"Tool proposal queued: {tool_id}. Execution allowed: false. Review is required before any side-effectful action."
    receipt = tool_result.get("receipt", {})
    return f"Tool dry-run complete: {tool_id}\n\nResult: {receipt.get('result')}\n\nNo external action was executed."


@app.post("/metis/tools/propose")
def tool_propose(payload: dict[str, Any]) -> dict[str, Any]:
    tool_id = payload.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise HTTPException(status_code=400, detail="tool_id is required")
    try:
        return _queue_tool_proposal(tool_id, payload.get("arguments") or {}, payload.get("reason"))
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/metis/tools/{tool_id}/dry_run")
def tool_dry_run(tool_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else payload
    try:
        tool = get_tool(tool_id)
        if STATE.get("interaction_mode") == "agent" or tool.permission_mode != "dry_run" or tool.side_effect_class != "none":
            return _queue_tool_proposal(tool_id, arguments, payload.get("reason") if isinstance(payload, dict) else None)
        receipt = dry_run_tool(tool_id, arguments)
        return {"status": "dry_run_complete", "receipt": receipt, "state": STATE, "leds": resolve_leds(STATE)}
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/metis/tools/{tool_id}/execute")
def tool_execute(tool_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else payload
    try:
        receipt = execute_tool(tool_id, arguments, STATE)
        if receipt.get("proposal_required"):
            queued = _queue_tool_proposal(tool_id, arguments, payload.get("reason") if isinstance(payload, dict) else None)
            return {**queued, "execution_status": receipt["status"], "blocked_reason": receipt["blocked_reason"], "execution_allowed": False}
        return {"status": receipt["status"], "receipt": receipt, "state": STATE, "leds": resolve_leds(STATE)}
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/metis/llm/options")
def llm_options(base_url: str | None = None) -> dict[str, Any]:
    import os

    ollama_base_url = base_url or os.environ.get("METIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    return {
        "selected_provider": os.environ.get("METIS_LLM_PROVIDER", "mock"),
        "ollama_base_url": ollama_base_url,
        "ollama_model": os.environ.get("METIS_OLLAMA_MODEL"),
        "openai_model": os.environ.get("METIS_OPENAI_MODEL", "gpt-4o-mini"),
        "ollama": list_ollama_models(ollama_base_url),
    }


@app.post("/metis/llm/health")
def llm_health(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    config = payload.get("options") if isinstance(payload.get("options"), dict) else payload
    return probe_llm_provider(config)


@app.post("/metis/governance/classify")
def governance_classify(payload: dict[str, Any]) -> dict[str, Any]:
    intent = payload.get("intent")
    if not isinstance(intent, str) or not intent.strip():
        raise HTTPException(status_code=400, detail="intent is required")
    policy = classify_intent(intent, STATE)
    return {"policy_version": POLICY_VERSION, "policy": policy.to_dict()}


@app.post("/metis/event")
def post_event(event: dict[str, Any]) -> dict[str, Any]:
    global STATE
    try:
        STATE = reduce_metis_event(STATE, event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"state": STATE, "leds": resolve_leds(STATE)}


def _apply_voice_result(result: VoiceResult) -> None:
    global STATE
    for event in result.events:
        STATE = reduce_metis_event(STATE, event)


def _speak_chat_response(assistant_message: str, options: dict[str, Any]) -> dict[str, Any] | None:
    voice_options = options.get("voice") if isinstance(options.get("voice"), dict) else {}
    if not voice_options.get("speak_response"):
        return None
    speak_options = {"voice": {**voice_options, "enabled": True}}
    voice_result = speak_text(assistant_message, STATE, speak_options)
    _apply_voice_result(voice_result)
    return _voice_response_payload(voice_result)


@app.post("/metis/chat")
def chat(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    user_message = payload.get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    plan_task = _route_chat_plan_request(user_message)
    if plan_task is not None:
        try:
            planned = _queue_chat_tool_plan(plan_task)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        plan = planned["plan"]
        next_action = planned["next_action"]
        plan_status = "queued" if planned["status"] == "plan_queued" else "already exists"
        assistant_message = (
            f"Governed tool plan {plan_status}: {plan['plan_id']} with {plan['step_count']} step(s). "
            f"Next action: {next_action['action']}. Execution allowed: false."
        )
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": "metis_tool_task_plan.v0.1",
                "user_message": user_message,
                "assistant_message": assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _speak_chat_response(assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": "metis_tool_task_plan.v0.1",
            "proposal_queued": False,
            "plan_queued": planned["status"] == "plan_queued",
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"tool_plan": planned},
            "retrieval": None,
            "voice": voice,
            "tool_plan": planned,
        }
    plan_control = _route_chat_plan_control_request(user_message)
    if plan_control is not None:
        if plan_control["action"] == "advance":
            controlled = _chat_plan_advance(plan_control["plan_id"])
            model = "metis_tool_plan_advance.v0.1"
            plan = controlled["plan"]
            next_action = controlled["next_action"]
            assistant_message = _plan_control_message(plan, next_action, "advance checked")
        else:
            controlled = _chat_plan_status(plan_control["plan_id"])
            model = "metis_tool_plan_status.v0.1"
            plan = controlled["plan"]
            next_action = controlled["next_action"]
            assistant_message = _plan_control_message(plan, next_action, "status")
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": model,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _speak_chat_response(assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": model,
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"tool_plan": controlled},
            "retrieval": None,
            "voice": voice,
            "tool_plan": controlled,
        }
    next_action_request = _route_chat_next_action_request(user_message)
    if next_action_request is not None:
        instruction = _next_action_instruction(next_action_request["plan_id"], next_action_request["proposal_id"])
        assistant_message = _next_action_message(instruction)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": "metis_tool_next_action.v0.1",
                "user_message": user_message,
                "assistant_message": assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _speak_chat_response(assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": "metis_tool_next_action.v0.1",
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"next_action": instruction},
            "retrieval": None,
            "voice": voice,
            "next_action": instruction,
        }
    queue_status_request = _route_chat_queue_status_request(user_message)
    if queue_status_request is not None:
        if queue_status_request == "receipts":
            queue_summary = _receipt_status_summary()
            model = "metis_tool_receipt_status.v0.1"
            assistant_message = _receipt_status_message(queue_summary)
        else:
            queue_summary = _proposal_status_summary()
            model = "metis_tool_approval_status.v0.1"
            assistant_message = _proposal_status_message(queue_summary)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": model,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _speak_chat_response(assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": model,
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"queue_status": queue_summary},
            "retrieval": None,
            "voice": voice,
            "queue_status": queue_summary,
        }
    proposal_queued = False
    policy = classify_intent(user_message, STATE)
    tool_result = None
    try:
        tool_result = _handle_chat_tool_request(user_message, options)
    except ToolRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if tool_result is None and should_queue_proposal(policy, STATE):
        STATE = reduce_metis_event(
            STATE,
            {"type": "user_intent", "intent": user_message, "action_class": policy.action_class, "policy": policy.to_dict()},
        )
        proposal_queued = True
    if tool_result is not None:
        assistant_message = _tool_chat_message(tool_result)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_router",
                "model": tool_result["tool_id"],
                "user_message": user_message,
                "assistant_message": assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _speak_chat_response(assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_router",
            "model": tool_result["tool_id"],
            "proposal_queued": proposal_queued or tool_result["status"] == "proposal_queued",
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": policy.to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"tool": tool_result},
            "retrieval": None,
            "voice": voice,
            "tool": tool_result,
        }

    retrieval = None
    retrieval_context = None
    if STATE.get("source_grounding_enabled"):
        config = boh_config_from_env(options=options)
        link = get_link_state()
        if config.enabled and link.enabled and link.state == LINK_AUTH_FAILED:
            # The background manager already established that BOH rejects our
            # read-only token. Don't repeatedly hammer BOH per message; surface
            # a visible degraded state instead of a silent failure.
            retrieval = BOHRetrievalResult(
                enabled=True,
                attempted=False,
                ok=False,
                source_state="degraded",
                mode=config.mode,
                error="BOH background link reports auth_failed; check the read-only retrieval token.",
            )
        else:
            retrieval = retrieve_boh_context(config, user_message)
        retrieval_context = render_context(retrieval)

    messages = governed_messages(user_message, STATE, STATE.get("chat_history", []), retrieval_context)
    try:
        result = provider_from_config(options).generate(messages, STATE, options)
    except LLMProviderError as exc:
        STATE = reduce_metis_event(
            STATE,
            {"type": "chat_event", "status": "failure", "provider": "llm_router", "reason": str(exc)},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    assistant_message = result.text
    if not STATE.get("source_grounding_enabled"):
        source_state = STATE.get("source_state", "unsourced")
    elif retrieval is not None:
        source_state = retrieval.source_state
    else:
        source_state = "unsourced"
    if proposal_queued and not assistant_message.lower().startswith("proposal only"):
        assistant_message = f"Proposal only: {assistant_message}"
    if STATE.get("source_grounding_enabled"):
        if source_state == "sourced" and "source label" not in assistant_message.lower():
            assistant_message = (
                f"{assistant_message}\n\nSource label: sourced; grounded on "
                f"{retrieval.count} BOH context pack(s) via mode '{retrieval.mode}'."
            )
        elif source_state == "degraded":
            assistant_message = (
                f"{assistant_message}\n\nSource label: degraded; BOH retrieval was requested but "
                f"unavailable ({retrieval.error}). Treat the above as unsourced."
            )
        elif source_state == "unsourced" and "unsourced" not in assistant_message.lower():
            assistant_message = f"{assistant_message}\n\nSource label: unsourced; no adequate retrieved source was available."
    STATE = reduce_metis_event(
        STATE,
        {
            "type": "chat_event",
            "status": "complete",
            "provider": result.provider,
            "model": result.model,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "source_state": source_state,
        },
    )
    voice = _speak_chat_response(assistant_message, options)
    metadata = dict(result.metadata)
    if retrieval is not None:
        metadata["boh"] = retrieval.to_metadata()
    return {
        "message": assistant_message,
        "provider": result.provider,
        "model": result.model,
        "proposal_queued": proposal_queued,
        "source_state": source_state,
        "policy": policy.to_dict(),
        "state": STATE,
        "leds": resolve_leds(STATE),
        "metadata": metadata,
        "retrieval": retrieval.to_metadata() if retrieval is not None else None,
        "voice": voice,
    }


@app.get("/metis/voice")
def voice() -> dict[str, Any]:
    profile = voice_profile(STATE)
    return {
        **profile,
        "selected_provider": profile["provider"],
        "profile": {
            "id": profile["voice_id"],
            "provider": profile["provider"],
            "can_speak": not profile["output_muted"],
            "boundary": profile["boundary"],
        },
    }


@app.get("/metis/voice/options")
def voice_options_route() -> dict[str, Any]:
    return voice_options(STATE)


@app.post("/metis/voice/speak")
def voice_speak(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    options = {"voice": {**payload, "enabled": payload.get("enabled", True)}}
    result = speak_text(text, STATE, options)
    _apply_voice_result(result)
    response = {**_voice_response_payload(result), "state": STATE, "leds": resolve_leds(STATE)}
    if not result.ok:
        raise HTTPException(status_code=502, detail=response)
    return response


@app.post("/metis/voice/stop")
def voice_stop(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = stop_voice(STATE, {"voice": payload or {}})
    _apply_voice_result(result)
    return {**_voice_response_payload(result), "state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/voice/preview")
def voice_preview(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    text = str(payload.get("text") or "Metis voice preview.")
    options = {"voice": {**payload, "enabled": payload.get("enabled", True)}}
    result = speak_text(text, STATE, options)
    _apply_voice_result(result)
    response = {**_voice_response_payload(result), "state": STATE, "leds": resolve_leds(STATE)}
    if not result.ok:
        raise HTTPException(status_code=502, detail=response)
    return response


def _voice_command_text(payload: dict[str, Any]) -> str:
    for key in ("text", "transcript", "recognized_text", "command"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(status_code=400, detail="text is required")


def _voice_command_event(text: str, status: str, reason: str | None = None) -> dict[str, Any]:
    event = {
        "type": "provider_event",
        "provider": "stt",
        "status": status,
        "input_mode": "simulated_voice_command",
        "text_len": len(text),
        "text_hash": sha1(text.encode("utf-8")).hexdigest()[:16],
        "text_redacted": True,
    }
    if reason:
        event["reason"] = reason
    return event


@app.post("/metis/voice/command")
def voice_command(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    payload = payload or {}
    text = _voice_command_text(payload)
    if not STATE.get("mic_hardware_enabled"):
        event = _voice_command_event(text, "blocked", "mic cutoff blocks voice command")
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "input_mode": "simulated_voice_command",
            "reason": "mic cutoff blocks voice command",
            "voice_command": {"recognized": False, "text_redacted": True, "text_len": len(text)},
            "state": STATE,
            "leds": resolve_leds(STATE),
        }
    transcript_event = _voice_command_event(text, "transcript")
    STATE = reduce_metis_event(STATE, transcript_event)
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    voice_options_payload = options.get("voice") if isinstance(options.get("voice"), dict) else {}
    options = {
        **options,
        "voice": {
            **voice_options_payload,
            "speak_response": voice_options_payload.get("speak_response", True),
            "enabled": voice_options_payload.get("enabled", True),
        },
    }
    response = chat({"message": text, "options": options})
    complete_event = _voice_command_event(text, "complete")
    STATE = reduce_metis_event(STATE, complete_event)
    response["state"] = STATE
    response["leds"] = resolve_leds(STATE)
    response["input_mode"] = "simulated_voice_command"
    response["voice_command"] = {
        "recognized": True,
        "text_redacted": True,
        "text_len": len(text),
        "route": "metis_chat",
        "speech_reply_requested": bool(options["voice"].get("speak_response")),
    }
    return response


def _voice_response_payload(result: VoiceResult) -> dict[str, Any]:
    payload = result.to_dict()
    payload["speech_blocked"] = bool(result.blocked_reason)
    payload["block_reason"] = result.blocked_reason.replace(" ", "_") if result.blocked_reason else None
    return payload


@app.post("/metis/replay")
def replay(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    events = payload.get("events")
    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="events must be a list")
    initial_state = baseline_state() if payload.get("reset", True) else STATE
    try:
        STATE = replay_events(initial_state, events)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"state": STATE, "leds": resolve_leds(STATE), "event_count": len(events)}


@app.post("/metis/state/reset")
def reset_state() -> dict[str, Any]:
    global STATE, SCENARIO_RESULTS
    STATE = baseline_state()
    SCENARIO_RESULTS = []
    return {"state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/scenario/run")
def scenario_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global SCENARIO_RESULTS
    payload = payload or {}
    scenario_id = payload.get("scenario_id")
    if scenario_id:
        if scenario_id not in SCENARIOS:
            raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_id}")
        result = run_scenario(scenario_id)
        SCENARIO_RESULTS.append(result)
        return result
    SCENARIO_RESULTS = run_all_scenarios()
    return {"results": SCENARIO_RESULTS, "passed": all(item["passed"] for item in SCENARIO_RESULTS)}


@app.get("/metis/scenario/results")
def scenario_results() -> dict[str, Any]:
    return {"results": SCENARIO_RESULTS}


@app.get("/metis/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if STATE.get("active_failure") is None else "degraded",
        "active_failure": STATE.get("active_failure"),
        "failures": FAILURE_TABLE,
        "readiness": calculate_readiness(),
        "hardware_parity_manifest": HARDWARE_PARITY_MANIFEST,
    }


@app.get("/metis/adapters")
def adapters() -> dict[str, Any]:
    return {"adapters": STATE["input_adapters"]}


@app.get("/metis/providers")
def providers() -> dict[str, Any]:
    return provider_catalog()


@app.post("/metis/providers/{operation_id}/invoke")
def provider_invoke(operation_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    try:
        result = invoke_provider(operation_id, payload)
    except ProviderHarnessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    applied: list[dict[str, Any]] = []
    for event in result["events"]:
        STATE = reduce_metis_event(STATE, event)
        applied.append(event)
    return {**result, "applied_events": applied, "state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/adapters/{adapter_id}/set_health")
def set_adapter_health(adapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    if adapter_id not in STATE["input_adapters"]:
        raise HTTPException(status_code=404, detail=f"unknown adapter: {adapter_id}")
    event = {
        "type": "adapter_health",
        "adapter_id": adapter_id,
        "health": payload.get("health", "ok"),
        "enabled": payload.get("enabled", payload.get("health", "ok") == "ok"),
        "mode": payload.get("mode"),
    }
    STATE = reduce_metis_event(STATE, event)
    return {"adapter": STATE["input_adapters"][adapter_id], "state": STATE}


@app.post("/metis/failures/{failure_id}/trigger")
def trigger_failure(failure_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    if failure_id not in FAILURE_TABLE:
        raise HTTPException(status_code=404, detail=f"unknown failure: {failure_id}")
    payload = payload or {}
    STATE = reduce_metis_event(STATE, {"type": "failure_event", "failure_id": failure_id, "reason": payload.get("reason")})
    return {"state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/failures/clear")
def clear_all_failures() -> dict[str, Any]:
    global STATE
    STATE = clear_failures(STATE)
    return {"state": STATE, "leds": resolve_leds(STATE)}
