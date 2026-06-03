from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any


STATE_SCHEMA_VERSION = "metis_state.v0.3"
EVENT_SCHEMA_VERSION = "metis_event.v0.1"
READINESS_CHECKLIST_VERSION = "metis_readiness.v0.1"
SUPPORTED_ADAPTER_SCHEMAS = {
    "stt_adapter.v0.1",
    "tts_adapter.v0.1",
    "vision_adapter.v0.1",
    "memory_adapter.v0.1",
    "tools_adapter.v0.1",
    "llm_router_adapter.v0.1",
    "atlas_adapter.v0.1",
    "boh_adapter.v0.1",
    "robot_safety_adapter.v0.1",
}

EVENT_TYPES = {
    "control_change",
    "button_event",
    "hardware_privacy",
    "heartbeat",
    "provider_event",
    "chat_event",
    "failure_event",
    "user_intent",
    "memory_event",
    "capture_request",
    "adapter_health",
    "adapter_schema_check",
    "bridge_disconnected",
    "proposal_review",
    "execution_request",
    "tool_plan",
}

ACTION_CLASSES = {
    "observe": "allowed",
    "retrieve": "allowed_if_source_lane_permits",
    "draft": "draft_only",
    "propose_memory": "requires_review",
    "modify_local": "requires_explicit_approval",
    "external_action": "requires_explicit_approval_every_time",
    "sensitive_action": "blocked_by_default",
    "actuator_action": "requires_hardware_and_governance_gate",
}

FAILURE_TABLE = {
    "brain_offline": "Metis Brain unavailable",
    "bridge_disconnected": "Host bridge heartbeat missing",
    "stt_failure": "Speech-to-text provider failed",
    "tts_failure": "Text-to-speech provider failed",
    "vault_unavailable": "Memory vault unavailable",
    "camera_failure": "Vision provider or camera unavailable",
    "tool_blocked": "Tool action blocked by governance",
    "governance_block": "Governance blocked requested action",
    "adapter_schema_mismatch": "Adapter schema version unsupported",
    "llm_failure": "LLM router provider failed",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def adapter(
    adapter_id: str,
    role: str,
    schema_version: str,
    *,
    enabled: bool = False,
    health: str = "disabled",
    mode: str = "disabled",
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "adapter_id": adapter_id,
        "enabled": enabled,
        "role": role,
        "health": health,
        "mode": mode,
        "capabilities": capabilities or [],
        "schema_version": schema_version,
        "schema_supported": schema_version in SUPPORTED_ADAPTER_SCHEMAS,
    }


BASE_ADAPTERS: dict[str, dict[str, Any]] = {
    "stt": adapter("stt", "speech_to_text_provider", "stt_adapter.v0.1", capabilities=["transcribe"]),
    "tts": adapter("tts", "text_to_speech_provider", "tts_adapter.v0.1", capabilities=["speak"]),
    "vision": adapter("vision", "vision_provider", "vision_adapter.v0.1", capabilities=["capture_metadata"]),
    "memory": adapter("memory", "memory_provider", "memory_adapter.v0.1", capabilities=["retrieve", "propose_memory"]),
    "tools": adapter("tools", "tool_provider", "tools_adapter.v0.1", capabilities=["queue_proposal"]),
    "llm_router": adapter("llm_router", "model_router_provider", "llm_router_adapter.v0.1", capabilities=["route"]),
    "project_atlas": adapter("project_atlas", "task_lifecycle_provider", "atlas_adapter.v0.1", capabilities=["propose_task"]),
    "boh_memory": adapter("boh_memory", "memory_vault_provider", "boh_adapter.v0.1", capabilities=["retrieve_cited_candidates"]),
    "robot_safety": adapter("robot_safety", "safety_pattern_provider", "robot_safety_adapter.v0.1", capabilities=["safety_patterns"]),
}


def baseline_state(*, adapters_enabled: bool = False, timestamp: str = "2026-05-29T00:00:00Z") -> dict[str, Any]:
    adapters = deepcopy(BASE_ADAPTERS)
    if adapters_enabled:
        for item in adapters.values():
            item["enabled"] = True
            item["health"] = "ok"
            item["mode"] = "mock"
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "timestamp": timestamp,
        "session_id": "local-sim-session",
        "power_state": "awake",
        "audio_state": "idle",
        "voice_output_state": "idle",
        "cognition_state": "idle",
        "authority_state": "local_governed",
        "interaction_mode": "human",
        "initiative_level": 0.5,
        "initiative_bucket": "helpful",
        "conversation_depth_level": 0.5,
        "conversation_depth_bucket": "rationale",
        "volume_level": 0.6,
        "output_muted": False,
        "mic_hardware_enabled": True,
        "camera_hardware_enabled": False,
        "logging_state": "session_logging_active",
        "vision_state": "disabled",
        "source_grounding_enabled": False,
        "source_state": "unsourced",
        "active_failure": None,
        "pending_approval_count": 0,
        "memory_proposal_count": 0,
        "tool_queue_count": 0,
        "approval_queue": [],
        "execution_audit_log": [],
        "tool_plan_queue": [],
        "module_health": {
            "metis_head_bridge": "ok",
            "metis_core": "ok",
            "metis_audio": "ok",
            "metis_memory": "disabled",
            "metis_vision": "disabled",
            "metis_governance": "ok",
            "metis_tools": "disabled",
            "metis_dashboard": "ok",
            "metis_integrations": "disabled",
            "metis_llm": "disabled",
        },
        "input_adapters": adapters,
        "event_log": [],
        "external_action_executed": False,
        "chat_history": [],
        "last_llm_provider": None,
        "last_llm_model": None,
        "memory_promoted": False,
        "blocked_capture_count": 0,
        "capture_count": 0,
        "tts_output_count": 0,
        "tts_muted_drop_count": 0,
        "tts_failure_count": 0,
        "last_tts_request_id": None,
        "last_tts_provider": None,
        "last_tts_voice": None,
        "last_tts_error": None,
        "last_block_reason": None,
        "spec_traceability": {
            "canonical_state": "buildspec section 5",
            "led_precedence": "buildspec section 6",
            "readiness": "buildspec section 25",
            "scenarios": "buildspec section 28",
            "phase": "Phase 0A/0S only",
        },
    }


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    normalized = dict(event)
    normalized.setdefault("schema_version", EVENT_SCHEMA_VERSION)
    event_type = normalized.get("type") or normalized.get("event_type")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported event type: {event_type!r}")
    normalized["type"] = event_type
    normalized.pop("event_type", None)
    return normalized
