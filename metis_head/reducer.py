from __future__ import annotations

from copy import deepcopy
from typing import Any

from .execution import build_execution_receipt
from .governance import classify_intent
from .proposals import build_proposal, build_review_receipt, pending_count
from .tool_task_planner import build_tool_plan_review_receipt
from .schemas import FAILURE_TABLE, SUPPORTED_ADAPTER_SCHEMAS, validate_event


def bucket(value: float, low: str, mid: str, high: str) -> str:
    if value < 0.34:
        return low
    if value < 0.67:
        return mid
    return high


def reduce_metis_event(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    event = validate_event(event)
    next_state = deepcopy(state)
    next_state["timestamp"] = event.get("timestamp", next_state.get("timestamp"))
    event_record = deepcopy(event)
    next_state.setdefault("event_log", []).append(event_record)

    event_type = event["type"]
    if event_type == "control_change":
        _reduce_control(next_state, event)
    elif event_type == "button_event":
        _reduce_button(next_state, event)
    elif event_type == "hardware_privacy":
        _reduce_privacy(next_state, event)
    elif event_type == "provider_event":
        _reduce_provider(next_state, event)
    elif event_type == "chat_event":
        _reduce_chat(next_state, event)
    elif event_type == "failure_event":
        _set_failure(next_state, event.get("failure_id"), event.get("reason"))
    elif event_type == "user_intent":
        _reduce_intent(next_state, event)
    elif event_type == "memory_event":
        _reduce_memory(next_state, event)
    elif event_type == "capture_request":
        _reduce_capture(next_state, event)
    elif event_type == "adapter_health":
        _reduce_adapter_health(next_state, event)
    elif event_type == "adapter_schema_check":
        _reduce_adapter_schema(next_state, event)
    elif event_type == "bridge_disconnected":
        _set_failure(next_state, "bridge_disconnected", "bridge heartbeat missing")
        next_state["module_health"]["metis_head_bridge"] = "unavailable"
    elif event_type == "heartbeat":
        next_state["module_health"]["metis_head_bridge"] = "ok"
        if next_state.get("active_failure") == "bridge_disconnected":
            next_state["active_failure"] = None
            next_state["last_block_reason"] = None
    elif event_type == "proposal_review":
        _reduce_proposal_review(next_state, event)
    elif event_type == "execution_request":
        _reduce_execution_request(next_state, event)
    elif event_type == "tool_plan":
        _reduce_tool_plan(next_state, event)
    elif event_type == "tool_plan_review":
        _reduce_tool_plan_review(next_state, event)
    elif event_type == "tool_plan_step_queue":
        _reduce_tool_plan_step_queue(next_state, event)
    elif event_type == "tool_plan_execution_request":
        _reduce_tool_plan_execution_request(next_state, event)
    elif event_type == "tool_plan_result_binding":
        _reduce_tool_plan_result_binding(next_state, event)

    return next_state


def replay_events(initial_state: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    state = deepcopy(initial_state)
    for event in events:
        state = reduce_metis_event(state, event)
    return state


def _reduce_control(state: dict[str, Any], event: dict[str, Any]) -> None:
    control = event.get("control")
    value = max(0.0, min(1.0, float(event.get("value", 0.0))))
    if control == "volume":
        state["volume_level"] = value
    elif control == "conversation_depth":
        state["conversation_depth_level"] = value
        state["conversation_depth_bucket"] = bucket(value, "direct", "rationale", "systems")
    elif control == "initiative":
        state["initiative_level"] = value
        state["initiative_bucket"] = bucket(value, "reactive", "helpful", "proactive")


def _reduce_button(state: dict[str, Any], event: dict[str, Any]) -> None:
    button = event.get("button")
    value = event.get("state")
    if button == "pwr":
        state["power_state"] = value or ("standby" if state.get("power_state") == "awake" else "awake")
        if state["power_state"] == "standby":
            state["audio_state"] = "standby_no_listen"
        elif state.get("mic_hardware_enabled"):
            state["audio_state"] = "idle"
    elif button == "loud":
        state["output_muted"] = value in {"off", False, "muted"}
        if state["output_muted"] and state.get("audio_state") == "speaking":
            state["audio_state"] = "idle"
    elif button == "afc":
        state["source_grounding_enabled"] = bool(value)
        state["authority_state"] = "source_grounded" if value else "local_governed"
    elif button == "am_fm":
        state["interaction_mode"] = "agent" if value in {"fm", "agent"} else "human"
    elif button == "audio_input":
        enabled = value in {"on", "enabled", "true", "1", True, 1}
        state["audio_input_enabled"] = bool(enabled)
        if enabled and state.get("mic_hardware_enabled"):
            state["audio_input_state"] = "idle"
        elif not enabled:
            state["audio_input_state"] = "disabled"
    elif button == "listen_mode":
        if value in {"no_listen", "wake_word", "push_to_talk"}:
            state["listen_mode"] = value


def _reduce_privacy(state: dict[str, Any], event: dict[str, Any]) -> None:
    device = event.get("device")
    enabled = bool(event.get("enabled"))
    if device == "mic":
        state["mic_hardware_enabled"] = enabled
        if not enabled:
            state["audio_state"] = "capture_blocked"
        elif state.get("power_state") == "awake":
            state["audio_state"] = "idle"
    elif device == "camera":
        state["camera_hardware_enabled"] = enabled
        state["vision_state"] = "idle" if enabled else "capture_blocked"


def _reduce_provider(state: dict[str, Any], event: dict[str, Any]) -> None:
    provider = event.get("provider")
    status = event.get("status")
    if status == "failure":
        if provider == "tts":
            state["voice_output_state"] = "failed"
            state["tts_failure_count"] = state.get("tts_failure_count", 0) + 1
            state["last_tts_error"] = event.get("reason") or "tts failure"
            _remember_tts_event(state, event)
            adapter = state["input_adapters"].get("tts")
            if adapter:
                adapter["enabled"] = False
                adapter["health"] = "unavailable"
                adapter["mode"] = "disabled"
        failure_id = event.get("failure_id") or f"{provider}_failure"
        _set_failure(state, failure_id, event.get("reason"))
    elif provider == "stt" and status == "transcript":
        if state.get("mic_hardware_enabled"):
            state["audio_state"] = "listening"
    elif provider == "stt" and status == "complete":
        if state.get("audio_state") == "listening":
            state["audio_state"] = "idle"
    elif provider == "stt" and status == "blocked":
        state["audio_state"] = "capture_blocked"
        state["blocked_capture_count"] = state.get("blocked_capture_count", 0) + 1
        state["last_block_reason"] = event.get("reason") or "voice command blocked"
    elif provider == "tts" and status in {"queued", "synthesizing"}:
        state["voice_output_state"] = status
        _remember_tts_event(state, event)
    elif provider == "tts" and status == "speaking":
        _remember_tts_event(state, event)
        if state.get("output_muted"):
            state["voice_output_state"] = "muted"
            state["tts_muted_drop_count"] = state.get("tts_muted_drop_count", 0) + 1
            state["last_block_reason"] = "output muted blocks voice output"
            state["audio_state"] = "idle" if state.get("audio_state") == "speaking" else state.get("audio_state", "idle")
        elif state.get("power_state") != "awake":
            state["voice_output_state"] = "muted"
            state["last_block_reason"] = "standby blocks voice output"
        else:
            state["voice_output_state"] = "speaking"
            state["tts_output_count"] = state.get("tts_output_count", 0) + 1
            state["audio_state"] = "speaking"
    elif provider == "tts" and status == "complete":
        _remember_tts_event(state, event)
        state["voice_output_state"] = "complete"
        state["last_tts_error"] = None
        if state.get("audio_state") == "speaking":
            state["audio_state"] = "idle"
    elif provider == "tts" and status in {"muted", "cancelled"}:
        _remember_tts_event(state, event)
        state["voice_output_state"] = status
        if status == "muted":
            state["tts_muted_drop_count"] = state.get("tts_muted_drop_count", 0) + 1
        if state.get("audio_state") == "speaking":
            state["audio_state"] = "idle"
    elif provider in {"vault", "memory", "boh_memory"} and status == "retrieved":
        state["cognition_state"] = "idle"
        state["source_state"] = "sourced"
    elif provider in {"vault", "memory", "boh_memory"} and status == "unavailable":
        _set_failure(state, "vault_unavailable", event.get("reason"))
        state["source_state"] = "unsourced"
    elif provider == "audio_input" and status in {"capturing", "transcribing"}:
        state["audio_input_state"] = status
    elif provider == "audio_input" and status == "complete":
        state["audio_input_state"] = "idle"
        state["capture_count"] = state.get("capture_count", 0) + 1
        if event.get("captured") and event.get("audio_duration_ms") is not None:
            state["last_audio_capture"] = {
                "audio_duration_ms": event.get("audio_duration_ms"),
                "frame_count": event.get("frame_count"),
                "sample_rate": event.get("sample_rate"),
                "audio_provider_id": event.get("audio_provider_id"),
                "stt_provider_id": event.get("stt_provider_id"),
                "text_len": event.get("text_len"),
                "text_hash": event.get("text_hash"),
                "text_redacted": True,
            }
    elif provider == "audio_input" and status == "blocked":
        state["audio_input_state"] = "blocked"
        state["blocked_capture_count"] = state.get("blocked_capture_count", 0) + 1
        state["last_block_reason"] = event.get("block_reason") or "audio capture blocked"
    elif provider == "audio_input" and status in {"failed", "failure"}:
        state["audio_input_state"] = "failed"


def _reduce_chat(state: dict[str, Any], event: dict[str, Any]) -> None:
    status = event.get("status")
    if status == "complete":
        state["cognition_state"] = "idle"
        state["last_llm_provider"] = event.get("provider")
        state["last_llm_model"] = event.get("model")
        state["module_health"]["metis_llm"] = "ok"
        adapter = state["input_adapters"].get("llm_router")
        if adapter:
            adapter["enabled"] = True
            adapter["health"] = "ok"
            adapter["mode"] = event.get("provider") or "mock"
        if state.get("source_grounding_enabled"):
            state["source_state"] = event.get("source_state", "unsourced")
        history = state.setdefault("chat_history", [])
        user_message = event.get("user_message")
        assistant_message = event.get("assistant_message")
        if isinstance(user_message, str):
            history.append({"role": "user", "content": user_message})
        if isinstance(assistant_message, str):
            history.append({"role": "assistant", "content": assistant_message})
    elif status == "failure":
        _set_failure(state, "llm_failure", event.get("reason"))


def _reduce_intent(state: dict[str, Any], event: dict[str, Any]) -> None:
    action_class = event.get("action_class")
    intent = event.get("intent", "")
    policy = event.get("policy") if isinstance(event.get("policy"), dict) else classify_intent(intent, state).to_dict()
    if action_class is None:
        action_class = policy["action_class"]
    is_tool_proposal = bool(event.get("tool_id"))
    if is_tool_proposal or (state.get("interaction_mode") == "agent" and action_class in {"external_action", "modify_local", "sensitive_action", "actuator_action"}):
        proposal_type = "memory" if event.get("tool_id") == "memory.propose" else "action"
        proposal = build_proposal(
            queue_index=len(state.setdefault("approval_queue", [])),
            intent=intent,
            action_class=action_class,
            policy=policy,
            proposal_type=proposal_type,
            metadata=_proposal_metadata_from_event(event),
        )
        state["approval_queue"].append(proposal)
        _refresh_proposal_counts(state)
        state["cognition_state"] = "awaiting_approval"
        state["authority_state"] = "awaiting_approval"
        state["external_action_executed"] = False
        state["module_health"]["metis_tools"] = "ok"
        adapter = state["input_adapters"].get("tools")
        if adapter:
            adapter["enabled"] = True
            adapter["health"] = "ok"
            adapter["mode"] = "dry_run"
        state["last_block_reason"] = "; ".join(policy.get("reasons", []))
    elif action_class == "sensitive_action":
        _set_failure(state, "governance_block", "sensitive action blocked by default")
        state["authority_state"] = "blocked"
    else:
        state["cognition_state"] = "drafting" if action_class == "draft" else "idle"


def _reduce_memory(state: dict[str, Any], event: dict[str, Any]) -> None:
    operation = event.get("operation")
    if operation == "propose":
        policy = {
            "requires_approval": True,
            "default_decision": "queue_for_review",
            "reasons": ["memory proposal requires review"],
        }
        proposal = build_proposal(
            queue_index=len(state.setdefault("approval_queue", [])),
            intent=str(event.get("memory_id") or "memory proposal"),
            action_class="propose_memory",
            policy=policy,
            proposal_type="memory",
        )
        state["approval_queue"].append(proposal)
        _refresh_proposal_counts(state)
        state["authority_state"] = "awaiting_approval"
        state["memory_promoted"] = False
    elif operation == "delete":
        state["memory_promoted"] = False
        state["last_block_reason"] = "memory deletion audit retained without deleted content"


def _reduce_proposal_review(state: dict[str, Any], event: dict[str, Any]) -> None:
    proposal_id = event.get("proposal_id")
    decision = event.get("decision")
    if decision not in {"approved", "denied"}:
        return
    for proposal in state.setdefault("approval_queue", []):
        if proposal.get("proposal_id") != proposal_id:
            continue
        if proposal.get("review_status", "pending") != "pending":
            return
        reason = event.get("reason") if isinstance(event.get("reason"), str) else None
        proposal["status"] = "reviewed"
        proposal["review_status"] = decision
        proposal["review_decision"] = decision
        proposal["review_reason"] = reason or ""
        proposal["reviewed_at"] = event.get("reviewed_at") or event.get("timestamp")
        proposal["review_receipt"] = build_review_receipt(proposal, decision, reason)
        proposal["review_scope"] = proposal["review_receipt"]["review_scope"]
        proposal["execution_allowed"] = False
        state["external_action_executed"] = False
        _refresh_proposal_counts(state)
        if state.get("pending_approval_count", 0) == 0:
            if state.get("cognition_state") == "awaiting_approval":
                state["cognition_state"] = "idle"
            if state.get("authority_state") == "awaiting_approval":
                state["authority_state"] = "local_governed"
        state["last_block_reason"] = "proposal approved but not executed" if decision == "approved" else "proposal denied"
        return


def _refresh_proposal_counts(state: dict[str, Any]) -> None:
    queue = state.setdefault("approval_queue", [])
    plan_queue = state.setdefault("tool_plan_queue", [])
    pending_plans = sum(1 for plan in plan_queue if plan.get("review_status", "pending") == "pending")
    state["pending_approval_count"] = pending_count(queue) + pending_plans
    state["memory_proposal_count"] = pending_count([item for item in queue if item.get("proposal_type") == "memory"])
    state["tool_queue_count"] = pending_count([item for item in queue if item.get("proposal_type") == "action"]) + pending_plans


def _reduce_execution_request(state: dict[str, Any], event: dict[str, Any]) -> None:
    proposal_id = event.get("proposal_id")
    proposal = next((item for item in state.setdefault("approval_queue", []) if item.get("proposal_id") == proposal_id), None)
    if proposal is None:
        return
    receipt = build_execution_receipt(
        receipt_index=len(state.setdefault("execution_audit_log", [])),
        proposal=proposal,
        requested_at=event.get("requested_at") or event.get("timestamp"),
        reason=event.get("reason") if isinstance(event.get("reason"), str) else None,
        dry_run_receipt=event.get("dry_run_receipt") if isinstance(event.get("dry_run_receipt"), dict) else None,
        read_only_result=event.get("read_only_result") if isinstance(event.get("read_only_result"), dict) else None,
    )
    state["execution_audit_log"].append(receipt)
    state["external_action_executed"] = False
    state["module_health"]["metis_tools"] = "ok"
    state["last_block_reason"] = receipt["execution_status"]
    if receipt["execution_status"].startswith("blocked"):
        state["authority_state"] = "blocked"


def _reduce_tool_plan(state: dict[str, Any], event: dict[str, Any]) -> None:
    plan = deepcopy(event.get("plan")) if isinstance(event.get("plan"), dict) else {}
    if not plan:
        return
    plan.setdefault("review_status", "pending")
    plan.setdefault("execution_allowed", False)
    plan.setdefault("execution_status", "not_requested")
    plan["status"] = "pending_review"
    state.setdefault("tool_plan_queue", []).append(plan)
    _refresh_proposal_counts(state)
    state["cognition_state"] = "awaiting_approval"
    state["authority_state"] = "awaiting_approval"
    state["external_action_executed"] = False
    state["module_health"]["metis_tools"] = "ok"


def _reduce_tool_plan_review(state: dict[str, Any], event: dict[str, Any]) -> None:
    plan_id = str(event.get("plan_id") or "")
    decision = str(event.get("decision") or "").lower()
    if decision not in {"approved", "denied"}:
        return
    for plan in state.setdefault("tool_plan_queue", []):
        if plan.get("plan_id") != plan_id:
            continue
        if plan.get("review_status", "pending") != "pending":
            return
        reason = str(event.get("reason") or "")
        plan["review_status"] = decision
        plan["reviewed_at"] = event.get("reviewed_at")
        plan["review_decision"] = decision
        plan["review_reason"] = reason
        plan["review_receipt"] = build_tool_plan_review_receipt(plan, decision, reason)
        plan["status"] = "reviewed"
        plan["execution_allowed"] = False
        for step in plan.get("steps", []):
            if isinstance(step, dict):
                step["execution_allowed"] = False
        _refresh_proposal_counts(state)
        state["authority_state"] = "awaiting_approval" if state.get("pending_approval_count") else "local_governed"
        state["cognition_state"] = "idle" if not state.get("pending_approval_count") else "awaiting_approval"
        state["external_action_executed"] = False
        state["module_health"]["metis_tools"] = "ok"
        return


def _reduce_tool_plan_step_queue(state: dict[str, Any], event: dict[str, Any]) -> None:
    plan_id = str(event.get("plan_id") or "")
    queued_steps = event.get("queued_steps") if isinstance(event.get("queued_steps"), list) else []
    if not plan_id or not queued_steps:
        return
    for plan in state.setdefault("tool_plan_queue", []):
        if plan.get("plan_id") != plan_id:
            continue
        if plan.get("review_status") != "approved":
            return
        materialized_ids = list(plan.get("materialized_proposal_ids") or [])
        for queued in queued_steps:
            if not isinstance(queued, dict):
                continue
            step_id = queued.get("step_id")
            proposal_id = queued.get("proposal_id")
            if proposal_id and proposal_id not in materialized_ids:
                materialized_ids.append(proposal_id)
            for step in plan.get("steps", []):
                if isinstance(step, dict) and step.get("step_id") == step_id:
                    step["proposal_id"] = proposal_id
                    step["proposal_status"] = "queued"
                    step["status"] = "proposal_queued"
                    step["execution_allowed"] = False
        plan["materialized_proposal_ids"] = materialized_ids
        plan["materialized_step_count"] = len(materialized_ids)
        plan["last_materialized_at"] = event.get("queued_at")
        plan["status"] = "steps_queued" if materialized_ids else plan.get("status", "reviewed")
        plan["execution_allowed"] = False
        _refresh_proposal_counts(state)
        state["authority_state"] = "awaiting_approval" if state.get("pending_approval_count") else "local_governed"
        state["cognition_state"] = "awaiting_approval" if state.get("pending_approval_count") else "idle"
        state["external_action_executed"] = False
        state["module_health"]["metis_tools"] = "ok"
        return


def _reduce_tool_plan_execution_request(state: dict[str, Any], event: dict[str, Any]) -> None:
    plan_id = str(event.get("plan_id") or "")
    executed_steps = event.get("executed_steps") if isinstance(event.get("executed_steps"), list) else []
    if not plan_id or not executed_steps:
        return
    for plan in state.setdefault("tool_plan_queue", []):
        if plan.get("plan_id") != plan_id:
            continue
        if plan.get("review_status") != "approved":
            return
        receipt_ids = list(plan.get("execution_receipt_ids") or [])
        for executed in executed_steps:
            if not isinstance(executed, dict):
                continue
            proposal_id = executed.get("proposal_id")
            receipt_id = executed.get("receipt_id")
            if receipt_id and receipt_id not in receipt_ids:
                receipt_ids.append(receipt_id)
            for step in plan.get("steps", []):
                if isinstance(step, dict) and step.get("proposal_id") == proposal_id:
                    step["execution_receipt_id"] = receipt_id
                    step["execution_status"] = executed.get("execution_status")
                    step["execution_allowed"] = False
        plan["execution_receipt_ids"] = receipt_ids
        plan["execution_request_count"] = len(receipt_ids)
        plan["last_execution_requested_at"] = event.get("requested_at")
        plan["status"] = "execution_requested" if receipt_ids else plan.get("status", "steps_queued")
        plan["execution_allowed"] = False
        _refresh_proposal_counts(state)
        state["external_action_executed"] = False
        state["module_health"]["metis_tools"] = "ok"
        return


def _reduce_tool_plan_result_binding(state: dict[str, Any], event: dict[str, Any]) -> None:
    plan_id = str(event.get("plan_id") or "")
    bindings = event.get("bindings") if isinstance(event.get("bindings"), list) else []
    if not plan_id or not bindings:
        return
    proposals = state.setdefault("approval_queue", [])
    for plan in state.setdefault("tool_plan_queue", []):
        if plan.get("plan_id") != plan_id:
            continue
        bound_count = int(plan.get("result_binding_count") or 0)
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            proposal_id = binding.get("proposal_id")
            arguments = binding.get("arguments") if isinstance(binding.get("arguments"), dict) else {}
            proposal = next((item for item in proposals if item.get("proposal_id") == proposal_id), None)
            if proposal is None or proposal.get("review_status", "pending") != "pending":
                continue
            proposal["tool_arguments"] = arguments
            proposal["result_binding"] = {
                "source_step_id": binding.get("source_step_id"),
                "source_receipt_id": binding.get("source_receipt_id"),
                "source_output_hash": binding.get("source_output_hash"),
                "bound_at": event.get("bound_at"),
                "raw_content_included": False,
            }
            for step in plan.get("steps", []):
                if isinstance(step, dict) and step.get("proposal_id") == proposal_id:
                    step["bound_arguments"] = arguments
                    step["result_binding"] = proposal["result_binding"]
                    step["status"] = "result_bound"
                    step["execution_allowed"] = False
                    bound_count += 1
        plan["result_binding_count"] = bound_count
        plan["last_result_bound_at"] = event.get("bound_at")
        plan["execution_allowed"] = False
        _refresh_proposal_counts(state)
        state["external_action_executed"] = False
        state["module_health"]["metis_tools"] = "ok"
        return


def _proposal_metadata_from_event(event: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("tool_id", "tool_arguments", "risk_class", "side_effect_class", "dry_run_available", "argument_validation"):
        if key in event:
            metadata[key] = event[key]
    return metadata


def _reduce_capture(state: dict[str, Any], event: dict[str, Any]) -> None:
    device = event.get("device")
    if device == "mic" and not state.get("mic_hardware_enabled"):
        state["blocked_capture_count"] += 1
        state["audio_state"] = "capture_blocked"
        state["last_block_reason"] = "mic hardware cutoff blocks capture"
    elif device == "camera" and not state.get("camera_hardware_enabled"):
        state["blocked_capture_count"] += 1
        state["vision_state"] = "capture_blocked"
        state["last_block_reason"] = "camera hardware cutoff blocks capture"
    else:
        state["capture_count"] += 1


def _reduce_adapter_health(state: dict[str, Any], event: dict[str, Any]) -> None:
    adapter_id = event.get("adapter_id")
    if adapter_id not in state["input_adapters"]:
        return
    health = event.get("health", "ok")
    state["input_adapters"][adapter_id]["health"] = health
    state["input_adapters"][adapter_id]["enabled"] = bool(event.get("enabled", health == "ok"))
    state["input_adapters"][adapter_id]["mode"] = event.get("mode", "mock" if health == "ok" else "disabled")


def _reduce_adapter_schema(state: dict[str, Any], event: dict[str, Any]) -> None:
    adapter_id = event.get("adapter_id")
    schema_version = event.get("schema_version")
    if adapter_id not in state["input_adapters"]:
        return
    adapter = state["input_adapters"][adapter_id]
    adapter["schema_version"] = schema_version
    adapter["schema_supported"] = schema_version in SUPPORTED_ADAPTER_SCHEMAS
    if not adapter["schema_supported"]:
        adapter["enabled"] = False
        adapter["health"] = "schema_mismatch"
        adapter["mode"] = "disabled"
        _set_failure(state, "adapter_schema_mismatch", f"{adapter_id} uses unsupported schema {schema_version}")


def _set_failure(state: dict[str, Any], failure_id: str | None, reason: str | None = None) -> None:
    if not failure_id:
        return
    state["active_failure"] = failure_id
    state["last_block_reason"] = reason or FAILURE_TABLE.get(failure_id, failure_id)
    if failure_id == "stt_failure":
        state["module_health"]["metis_audio"] = "stt_failure"
    elif failure_id == "tts_failure":
        state["module_health"]["metis_audio"] = "tts_failure"
        state["voice_output_state"] = "failed"
        if state.get("audio_state") == "speaking":
            state["audio_state"] = "idle"
    elif failure_id == "vault_unavailable":
        state["module_health"]["metis_memory"] = "unavailable"
    elif failure_id == "camera_failure":
        state["module_health"]["metis_vision"] = "unavailable"
    elif failure_id == "llm_failure":
        state["module_health"]["metis_llm"] = "unavailable"
        adapter = state["input_adapters"].get("llm_router")
        if adapter:
            adapter["enabled"] = False
            adapter["health"] = "unavailable"
            adapter["mode"] = "disabled"
    elif failure_id in {"tool_blocked", "governance_block"}:
        state["module_health"]["metis_governance"] = "blocked"
        state["authority_state"] = "blocked"


def clear_failures(state: dict[str, Any]) -> dict[str, Any]:
    next_state = deepcopy(state)
    next_state["active_failure"] = None
    next_state["last_block_reason"] = None
    for key, value in list(next_state["module_health"].items()):
        if value in {"stt_failure", "tts_failure", "unavailable", "blocked"}:
            next_state["module_health"][key] = "ok" if key in {"metis_core", "metis_audio", "metis_governance"} else "disabled"
    if next_state.get("authority_state") == "blocked":
        next_state["authority_state"] = "local_governed"
    return next_state


def _remember_tts_event(state: dict[str, Any], event: dict[str, Any]) -> None:
    state["last_tts_request_id"] = event.get("request_id", state.get("last_tts_request_id"))
    state["last_tts_provider"] = event.get("voice_provider") or event.get("provider")
    state["last_tts_voice"] = event.get("voice_id", state.get("last_tts_voice"))
