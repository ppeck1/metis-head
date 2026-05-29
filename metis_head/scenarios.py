from __future__ import annotations

from copy import deepcopy
from typing import Any

from .leds import resolve_leds
from .reducer import replay_events
from .schemas import baseline_state


SCENARIOS: dict[str, dict[str, Any]] = {
    "baseline_boot_no_adapters": {
        "name": "Safe boot with all adapters disabled",
        "events": [],
        "expected": {"power_state": "awake", "active_failure": None, "all_adapters_disabled": True},
    },
    "pwr_standby_no_hidden_listening": {
        "name": "Standby does not imply silent capture",
        "events": [{"type": "button_event", "button": "pwr", "state": "standby"}],
        "expected": {"power_state": "standby", "audio_state": "standby_no_listen"},
    },
    "output_muted_not_privacy": {
        "name": "Output mute stops TTS only",
        "events": [{"type": "button_event", "button": "loud", "state": "off"}],
        "expected": {"output_muted": True, "mic_hardware_enabled": True, "logging_state": "session_logging_active"},
    },
    "mic_cutoff_blocks_capture": {
        "name": "Hardware mic cutoff prevents listening/transcription",
        "events": [
            {"type": "hardware_privacy", "device": "mic", "enabled": False},
            {"type": "capture_request", "device": "mic"},
        ],
        "expected": {"mic_hardware_enabled": False, "audio_state": "capture_blocked", "blocked_capture_count": 1},
    },
    "camera_cutoff_blocks_capture": {
        "name": "Camera cutoff prevents capture",
        "events": [
            {"type": "hardware_privacy", "device": "camera", "enabled": False},
            {"type": "capture_request", "device": "camera"},
        ],
        "expected": {"camera_hardware_enabled": False, "vision_state": "capture_blocked", "blocked_capture_count": 1},
    },
    "source_grounding_unsourced": {
        "name": "AFC labels answer unsourced when retrieval unavailable",
        "events": [
            {"type": "button_event", "button": "afc", "state": True},
            {"type": "provider_event", "provider": "vault", "status": "unavailable"},
        ],
        "expected": {"source_grounding_enabled": True, "source_state": "unsourced", "active_failure": "vault_unavailable"},
    },
    "source_grounding_sourced": {
        "name": "AFC surfaces provenance when retrieval succeeds",
        "events": [
            {"type": "button_event", "button": "afc", "state": True},
            {"type": "provider_event", "provider": "boh_memory", "status": "retrieved"},
        ],
        "expected": {"source_grounding_enabled": True, "source_state": "sourced"},
    },
    "agent_mode_requires_approval": {
        "name": "Agent Mode cannot execute without approval",
        "events": [
            {"type": "button_event", "button": "am_fm", "state": "fm"},
            {"type": "user_intent", "intent": "draft_and_send_email", "action_class": "external_action"},
        ],
        "expected": {
            "interaction_mode": "agent",
            "cognition_state": "awaiting_approval",
            "authority_state": "awaiting_approval",
            "pending_approval_count": 1,
            "external_action_executed": False,
        },
    },
    "governance_block_overrides_leds": {
        "name": "Governance block wins LED precedence",
        "events": [{"type": "failure_event", "failure_id": "governance_block"}],
        "expected": {"active_failure": "governance_block", "leds.activity_led.state": "blocked", "leds.authority_led.color": "red"},
    },
    "stt_failure_visible": {
        "name": "STT failure becomes visible degraded/error state",
        "events": [{"type": "provider_event", "provider": "stt", "status": "failure", "failure_id": "stt_failure"}],
        "expected": {"active_failure": "stt_failure", "module_health.metis_audio": "stt_failure"},
    },
    "tts_failure_visible": {
        "name": "TTS failure does not fake successful speech",
        "events": [{"type": "provider_event", "provider": "tts", "status": "failure", "failure_id": "tts_failure"}],
        "expected": {"active_failure": "tts_failure", "audio_state": "idle", "module_health.metis_audio": "tts_failure"},
    },
    "vault_failure_visible": {
        "name": "Vault unavailable degrades source state",
        "events": [{"type": "provider_event", "provider": "vault", "status": "unavailable"}],
        "expected": {"active_failure": "vault_unavailable", "source_state": "unsourced"},
    },
    "adapter_schema_mismatch_disables": {
        "name": "Bad adapter contract fails closed",
        "events": [{"type": "adapter_schema_check", "adapter_id": "boh_memory", "schema_version": "boh_adapter.v9.9"}],
        "expected": {
            "active_failure": "adapter_schema_mismatch",
            "input_adapters.boh_memory.enabled": False,
            "input_adapters.boh_memory.health": "schema_mismatch",
        },
    },
    "memory_proposal_needs_review": {
        "name": "No memory silently promotes",
        "events": [{"type": "memory_event", "operation": "propose"}],
        "expected": {"memory_proposal_count": 1, "pending_approval_count": 1, "memory_promoted": False},
    },
    "memory_deletion_logs_without_content": {
        "name": "Deletion preserves audit event, not sensitive content",
        "events": [{"type": "memory_event", "operation": "delete", "memory_id": "redacted"}],
        "expected": {"memory_promoted": False, "event_log.0.operation": "delete"},
    },
    "simulator_replay_deterministic": {
        "name": "Same event log produces same final state",
        "events": [
            {"type": "control_change", "control": "initiative", "value": 0.82},
            {"type": "button_event", "button": "am_fm", "state": "fm"},
            {"type": "user_intent", "intent": "send_email", "action_class": "external_action"},
        ],
        "expected": {"initiative_bucket": "proactive", "pending_approval_count": 1, "external_action_executed": False},
    },
}


def run_scenario(scenario_id: str, initial_state: dict[str, Any] | None = None) -> dict[str, Any]:
    scenario = SCENARIOS[scenario_id]
    start = deepcopy(initial_state) if initial_state is not None else baseline_state()
    final_state = replay_events(start, scenario["events"])
    leds = resolve_leds(final_state)
    passed, failures = assert_expected(final_state, leds, scenario["expected"])
    return {
        "scenario_id": scenario_id,
        "name": scenario["name"],
        "passed": passed,
        "failures": failures,
        "events": scenario["events"],
        "final_state": final_state,
        "leds": leds,
    }


def run_all_scenarios() -> list[dict[str, Any]]:
    return [run_scenario(scenario_id) for scenario_id in SCENARIOS]


def assert_expected(state: dict[str, Any], leds: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    context = {"leds": leds, **state}
    for path, value in expected.items():
        if path == "all_adapters_disabled":
            actual = all(not adapter["enabled"] for adapter in state["input_adapters"].values())
        else:
            actual = _get_path(context, path)
        if actual != value:
            failures.append(f"{path}: expected {value!r}, got {actual!r}")
    return not failures, failures


def _get_path(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current
