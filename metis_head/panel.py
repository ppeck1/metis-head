"""Physical radio panel resolver (Phase 0AZ / panel_render.v0.1).

Pure, deterministic projection of canonical state onto the small front-panel
display/LED contract defined in docs/PHYSICAL_RADIO_PANEL_CONTRACT_v0_1.md.

This module renders state; it never computes policy, approves proposals,
requests execution, or grants any authority. Every produced frame carries
``execution_allowed=False`` and contains states/counts/reason-labels only --
never transcript text, file contents, command output, or secrets.
"""

from __future__ import annotations

from typing import Any

from .leds import resolve_leds


PANEL_RENDER_VERSION = "panel_render.v0.1"

# Fixed reason-label enum (extend by minor version when new governed lanes appear).
PANEL_REASONS = {
    "proposal_pending_review",
    "proposal_approved_awaiting_receipt",
    "tool_request_queued_not_executed",
    "tool_plan_pending_review",
    "tool_plan_steps_queued",
    "memory_proposal_pending_review",
    "voice_command_routing",
    "voice_confirmation_readback",
    "output_muted_listening_unchanged",
    "mic_hardware_cutoff",
    "camera_hardware_cutoff",
    "governance_block",
    "provider_failure",
}


def resolve_panel(state: dict[str, Any]) -> dict[str, Any]:
    """Return a ``panel_render.v0.1`` frame derived only from canonical state."""

    leds = resolve_leds(state)
    visualizer = leds.get("visualizer", {})

    return {
        "type": "panel_render",
        "schema_version": PANEL_RENDER_VERSION,
        "activity_led": leds["activity_led"],
        "authority_led": leds["authority_led"],
        "visualizer": {
            "mode": visualizer.get("mode", "active"),
            "audio_state": visualizer.get("audio_state"),
        },
        "approval_indicator": _approval_indicator(state),
        "tool_indicator": _tool_indicator(state),
        "memory_indicator": _memory_indicator(state),
        "voice_indicator": _voice_indicator(state),
        "mic_cutoff_indicator": {"capture_enabled": bool(state.get("mic_hardware_enabled"))},
        "camera_cutoff_indicator": {"capture_enabled": bool(state.get("camera_hardware_enabled"))},
        "panel_precedence_applied": _precedence(state),
        "execution_allowed": False,
    }


def _approval_indicator(state: dict[str, Any]) -> dict[str, Any]:
    count = int(state.get("pending_approval_count", 0) or 0)
    return {
        "on": count > 0,
        "count": count,
        "reason": "proposal_pending_review" if count > 0 else None,
    }


def _tool_indicator(state: dict[str, Any]) -> dict[str, Any]:
    queued = int(state.get("tool_queue_count", 0) or 0)
    plans = state.get("tool_plan_queue") or []
    plan_count = len(plans) if isinstance(plans, list) else 0
    on = queued > 0 or plan_count > 0
    if queued > 0:
        reason = "tool_request_queued_not_executed"
    elif plan_count > 0:
        reason = "tool_plan_pending_review"
    else:
        reason = None
    return {"on": on, "count": queued, "plan_count": plan_count, "reason": reason}


def _memory_indicator(state: dict[str, Any]) -> dict[str, Any]:
    count = int(state.get("memory_proposal_count", 0) or 0)
    return {
        "on": count > 0,
        "count": count,
        "reason": "memory_proposal_pending_review" if count > 0 else None,
    }


def _voice_indicator(state: dict[str, Any]) -> dict[str, Any]:
    audio = state.get("audio_state")
    voice_out = state.get("voice_output_state")
    output_muted = bool(state.get("output_muted"))

    if voice_out == "speaking" or audio == "speaking":
        voice_state = "speaking"
    elif _voice_confirmation_pending(state):
        voice_state = "awaiting_confirmation"
    elif audio in {"listening", "transcribing"}:
        voice_state = "command_active"
    elif output_muted:
        voice_state = "output_muted"
    else:
        voice_state = "idle"

    return {"state": voice_state, "output_muted": output_muted}


def _voice_confirmation_pending(state: dict[str, Any]) -> bool:
    """Best-effort, defensive scan for a pending spoken-confirmation readback.

    Reads only redacted status fields from the event log; never reads text.
    Returns False when no recognizable voice-confirmation readback is present.
    """

    event_log = state.get("event_log")
    if not isinstance(event_log, list):
        return False
    for event in reversed(event_log):
        if not isinstance(event, dict):
            continue
        schema = str(event.get("schema_version", ""))
        if schema.startswith("metis_voice_confirmation"):
            return event.get("status") == "readback_required"
    return False


def _precedence(state: dict[str, Any]) -> str:
    """Dominant panel state label, privacy and governance first."""

    if not state.get("mic_hardware_enabled") and state.get("audio_state") == "capture_blocked":
        return "mic_hardware_cutoff"
    if not state.get("camera_hardware_enabled") and state.get("vision_state") == "capture_blocked":
        return "camera_hardware_cutoff"

    failure = state.get("active_failure")
    if failure == "governance_block" or state.get("authority_state") == "blocked" or state.get("source_state") == "blocked":
        return "governance_block"
    if failure:
        return "provider_failure"
    if state.get("power_state") != "awake":
        return "standby"
    if int(state.get("pending_approval_count", 0) or 0) > 0 or state.get("authority_state") == "awaiting_approval" or _voice_confirmation_pending(state):
        return "awaiting_approval"
    if state.get("interaction_mode") == "agent":
        return "agent_mode"
    if state.get("source_grounding_enabled") and state.get("source_state") in {"sourced", "unsourced", "source_grounded"}:
        return "source_grounding"
    if state.get("audio_state") in {"speaking", "listening", "transcribing"} or state.get("cognition_state") == "retrieving":
        return "active_runtime"
    return "idle"
