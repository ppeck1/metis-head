from __future__ import annotations

from copy import deepcopy
from typing import Any

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
        failure_id = event.get("failure_id") or f"{provider}_failure"
        _set_failure(state, failure_id, event.get("reason"))
    elif provider == "stt" and status == "transcript":
        if state.get("mic_hardware_enabled"):
            state["audio_state"] = "listening"
    elif provider == "tts" and status == "speaking":
        state["audio_state"] = "idle" if state.get("output_muted") else "speaking"
    elif provider == "tts" and status == "complete":
        state["audio_state"] = "idle"
    elif provider in {"vault", "memory", "boh_memory"} and status == "retrieved":
        state["cognition_state"] = "idle"
        state["source_state"] = "sourced"
    elif provider in {"vault", "memory", "boh_memory"} and status == "unavailable":
        _set_failure(state, "vault_unavailable", event.get("reason"))
        state["source_state"] = "unsourced"


def _reduce_intent(state: dict[str, Any], event: dict[str, Any]) -> None:
    action_class = event.get("action_class")
    intent = event.get("intent", "")
    if action_class is None and any(word in intent for word in ("send", "publish", "purchase", "external")):
        action_class = "external_action"
    if state.get("interaction_mode") == "agent" and action_class in {"external_action", "modify_local", "sensitive_action", "actuator_action"}:
        state["pending_approval_count"] += 1
        state["tool_queue_count"] += 1
        state["cognition_state"] = "awaiting_approval"
        state["authority_state"] = "awaiting_approval"
        state["external_action_executed"] = False
    elif action_class == "sensitive_action":
        _set_failure(state, "governance_block", "sensitive action blocked by default")
        state["authority_state"] = "blocked"
    else:
        state["cognition_state"] = "drafting" if action_class == "draft" else "idle"


def _reduce_memory(state: dict[str, Any], event: dict[str, Any]) -> None:
    operation = event.get("operation")
    if operation == "propose":
        state["memory_proposal_count"] += 1
        state["pending_approval_count"] += 1
        state["authority_state"] = "awaiting_approval"
        state["memory_promoted"] = False
    elif operation == "delete":
        state["memory_promoted"] = False
        state["last_block_reason"] = "memory deletion audit retained without deleted content"


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
        if state.get("audio_state") == "speaking":
            state["audio_state"] = "idle"
    elif failure_id == "vault_unavailable":
        state["module_health"]["metis_memory"] = "unavailable"
    elif failure_id == "camera_failure":
        state["module_health"]["metis_vision"] = "unavailable"
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
