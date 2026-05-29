from __future__ import annotations

from typing import Any


BRIDGE_SCHEMA_VERSION = "metis_bridge_event.v0.1"

HARDWARE_PARITY_MANIFEST = [
    {"hardware": "volume_knob", "event": "control_change:volume", "state": "volume_level", "dashboard": "canonical_state", "failure": "bridge_disconnected", "test": "scenario_replay"},
    {"hardware": "conversation_depth_knob", "event": "control_change:conversation_depth", "state": "conversation_depth_bucket", "dashboard": "canonical_state", "failure": "bridge_disconnected", "test": "scenario_replay"},
    {"hardware": "initiative_knob", "event": "control_change:initiative", "state": "initiative_bucket", "dashboard": "canonical_state", "failure": "bridge_disconnected", "test": "simulator_replay_deterministic"},
    {"hardware": "pwr_button", "event": "button_event:pwr", "state": "power_state", "dashboard": "canonical_state", "failure": "bridge_disconnected", "test": "pwr_standby_no_hidden_listening"},
    {"hardware": "loud_button", "event": "button_event:loud", "state": "output_muted", "dashboard": "canonical_state", "failure": "tts_failure", "test": "output_muted_not_privacy"},
    {"hardware": "afc_button", "event": "button_event:afc", "state": "source_grounding_enabled", "dashboard": "canonical_state", "failure": "vault_unavailable", "test": "source_grounding_unsourced"},
    {"hardware": "am_fm_button", "event": "button_event:am_fm", "state": "interaction_mode", "dashboard": "canonical_state", "failure": "governance_block", "test": "agent_mode_requires_approval"},
    {"hardware": "mic_cutoff", "event": "hardware_privacy:mic", "state": "mic_hardware_enabled", "dashboard": "privacy", "failure": "stt_failure", "test": "mic_cutoff_blocks_capture"},
    {"hardware": "camera_cutoff", "event": "hardware_privacy:camera", "state": "camera_hardware_enabled", "dashboard": "privacy", "failure": "camera_failure", "test": "camera_cutoff_blocks_capture"},
    {"hardware": "bridge_heartbeat", "event": "heartbeat", "state": "module_health.metis_head_bridge", "dashboard": "adapter_health", "failure": "bridge_disconnected", "test": "safe_boot_simulated"},
]


def control_change(control: str, value: float, raw: int | None = None, timestamp_ms: int = 0) -> dict[str, Any]:
    event = {"type": "control_change", "control": control, "value": value, "timestamp_ms": timestamp_ms, "bridge_schema": BRIDGE_SCHEMA_VERSION}
    if raw is not None:
        event["raw"] = raw
    return event


def button_event(button: str, state: str | bool, timestamp_ms: int = 0) -> dict[str, Any]:
    return {"type": "button_event", "button": button, "event": "pressed", "state": state, "timestamp_ms": timestamp_ms, "bridge_schema": BRIDGE_SCHEMA_VERSION}


def hardware_privacy(device: str, enabled: bool, timestamp_ms: int = 0) -> dict[str, Any]:
    return {"type": "hardware_privacy", "device": device, "enabled": enabled, "timestamp_ms": timestamp_ms, "bridge_schema": BRIDGE_SCHEMA_VERSION}


def heartbeat(bridge_id: str = "sim-bridge-001", uptime_ms: int = 0, firmware: str = "sim.0.1") -> dict[str, Any]:
    return {"type": "heartbeat", "bridge_id": bridge_id, "uptime_ms": uptime_ms, "firmware": firmware, "bridge_schema": BRIDGE_SCHEMA_VERSION}
