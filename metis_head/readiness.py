from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .schemas import READINESS_CHECKLIST_VERSION


CHECKLIST = [
    ("canonical_state_represented", "Canonical state represented", 8, "pass"),
    ("power_state_represented", "Power state represented", 4, "pass"),
    ("audio_state_represented", "Audio state represented", 4, "pass"),
    ("cognition_state_represented", "Cognition state represented", 4, "pass"),
    ("authority_state_represented", "Authority state represented", 4, "pass"),
    ("human_agent_mode_represented", "Human/Agent mode represented", 4, "pass"),
    ("initiative_knob_represented", "Initiative knob represented", 4, "pass"),
    ("conversation_depth_knob_represented", "Conversation depth knob represented", 4, "pass"),
    ("volume_output_mute_represented", "Volume/output mute represented", 4, "pass"),
    ("mic_cutoff_represented", "Mic cutoff represented", 5, "pass"),
    ("camera_cutoff_represented", "Camera cutoff represented", 5, "pass"),
    ("logging_state_represented", "Logging state represented", 4, "pass"),
    ("activity_led_represented", "Activity LED represented", 5, "pass"),
    ("authority_led_represented", "Authority LED represented", 5, "pass"),
    ("visualizer_represented", "Visualizer represented", 5, "pass"),
    ("failure_scenarios_represented", "Failure scenarios represented", 6, "pass"),
    ("provider_registry_represented", "Provider registry represented", 6, "pass"),
    ("adapter_health_represented", "Adapter health represented", 5, "pass"),
    ("do_not_rebuild_map_represented", "Do-not-rebuild map represented", 4, "pass"),
    ("hardware_free_simulation_plan_represented", "Hardware-free simulation plan represented", 5, "pass"),
    ("acceptance_tests_listed", "Acceptance tests listed", 4, "pass"),
    ("scenario_assertions_executable", "Scenario assertions executable", 5, "pass"),
    ("event_replay_available", "Event replay available", 4, "pass"),
    ("bridge_emulator_protocol_available", "Bridge emulator protocol available", 4, "pass"),
    ("persistence_config_export_available", "Persistence/config export available", 3, "pass"),
    ("simulator_to_spec_traceability_available", "Simulator-to-spec traceability available", 3, "pass"),
    ("hardware_parity_manifest_available", "Hardware parity manifest available", 4, "pass"),
]

CREDIT = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "unknown": 0.0}


def calculate_readiness(domain: str = "simulation_readiness") -> dict[str, Any]:
    total_weight = sum(item[2] for item in CHECKLIST)
    earned = sum(weight * CREDIT[status] for _, _, weight, status in CHECKLIST)
    counts = {status: sum(1 for item in CHECKLIST if item[3] == status) for status in CREDIT}
    return {
        "readiness_domain": domain,
        "score": round((earned / total_weight) * 100),
        "checklist_version": READINESS_CHECKLIST_VERSION,
        "passed": counts["pass"],
        "partial": counts["partial"],
        "failed": counts["fail"],
        "unknown": counts["unknown"],
        "source": "computed_phase_0a_0s_checklist",
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "items": [
            {"id": item_id, "label": label, "weight": weight, "status": status}
            for item_id, label, weight, status in CHECKLIST
        ],
    }
