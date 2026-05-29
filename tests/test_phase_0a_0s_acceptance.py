from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.leds import resolve_leds
from metis_head.readiness import calculate_readiness
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.scenarios import SCENARIOS, run_all_scenarios, run_scenario
from metis_head.schemas import READINESS_CHECKLIST_VERSION, baseline_state


def test_required_scenarios_present_and_pass() -> None:
    required = {
        "baseline_boot_no_adapters",
        "pwr_standby_no_hidden_listening",
        "output_muted_not_privacy",
        "mic_cutoff_blocks_capture",
        "camera_cutoff_blocks_capture",
        "source_grounding_unsourced",
        "source_grounding_sourced",
        "agent_mode_requires_approval",
        "governance_block_overrides_leds",
        "stt_failure_visible",
        "tts_failure_visible",
        "vault_failure_visible",
        "adapter_schema_mismatch_disables",
        "memory_proposal_needs_review",
        "memory_deletion_logs_without_content",
        "simulator_replay_deterministic",
    }
    assert required <= set(SCENARIOS)
    results = run_all_scenarios()
    assert all(result["passed"] for result in results), [result for result in results if not result["passed"]]


def test_safe_boot_with_all_adapters_disabled() -> None:
    state = baseline_state()
    assert state["power_state"] == "awake"
    assert state["active_failure"] is None
    assert all(not adapter["enabled"] for adapter in state["input_adapters"].values())


def test_output_mute_does_not_imply_privacy() -> None:
    state = reduce_metis_event(baseline_state(), {"type": "button_event", "button": "loud", "state": "off"})
    assert state["output_muted"] is True
    assert state["mic_hardware_enabled"] is True
    assert state["logging_state"] == "session_logging_active"


def test_mic_cutoff_blocks_capture() -> None:
    result = run_scenario("mic_cutoff_blocks_capture")
    assert result["final_state"]["audio_state"] == "capture_blocked"
    assert result["final_state"]["blocked_capture_count"] == 1


def test_camera_cutoff_blocks_capture() -> None:
    result = run_scenario("camera_cutoff_blocks_capture")
    assert result["final_state"]["vision_state"] == "capture_blocked"
    assert result["final_state"]["blocked_capture_count"] == 1


def test_agent_mode_queues_external_action_and_does_not_execute() -> None:
    state = replay_events(baseline_state(), SCENARIOS["agent_mode_requires_approval"]["events"])
    assert state["interaction_mode"] == "agent"
    assert state["pending_approval_count"] == 1
    assert state["tool_queue_count"] == 1
    assert state["external_action_executed"] is False


def test_governance_block_overrides_leds() -> None:
    state = reduce_metis_event(baseline_state(), {"type": "failure_event", "failure_id": "governance_block"})
    leds = resolve_leds(state)
    assert leds["activity_led"]["state"] == "blocked"
    assert leds["activity_led"]["color"] == "red"
    assert leds["authority_led"]["color"] == "red"


def test_provider_failures_visible() -> None:
    stt = run_scenario("stt_failure_visible")["final_state"]
    tts = run_scenario("tts_failure_visible")["final_state"]
    vault = run_scenario("vault_failure_visible")["final_state"]
    assert stt["active_failure"] == "stt_failure"
    assert tts["active_failure"] == "tts_failure"
    assert tts["audio_state"] != "speaking"
    assert vault["active_failure"] == "vault_unavailable"
    assert vault["source_state"] == "unsourced"


def test_tts_failure_mid_speech_forces_audio_idle() -> None:
    state = replay_events(
        baseline_state(),
        [
            {"type": "provider_event", "provider": "tts", "status": "speaking"},
            {"type": "provider_event", "provider": "tts", "status": "failure", "failure_id": "tts_failure"},
        ],
    )
    assert state["active_failure"] == "tts_failure"
    assert state["audio_state"] == "idle"
    assert state["module_health"]["metis_audio"] == "tts_failure"


def test_adapter_schema_mismatch_disables_adapter() -> None:
    state = run_scenario("adapter_schema_mismatch_disables")["final_state"]
    adapter = state["input_adapters"]["boh_memory"]
    assert state["active_failure"] == "adapter_schema_mismatch"
    assert adapter["enabled"] is False
    assert adapter["health"] == "schema_mismatch"


def test_memory_proposal_requires_review() -> None:
    state = run_scenario("memory_proposal_needs_review")["final_state"]
    assert state["memory_proposal_count"] == 1
    assert state["pending_approval_count"] == 1
    assert state["memory_promoted"] is False


def test_same_event_replay_produces_same_final_state() -> None:
    events = deepcopy(SCENARIOS["simulator_replay_deterministic"]["events"])
    first = replay_events(baseline_state(), events)
    second = replay_events(baseline_state(), events)
    assert first == second


def test_readiness_score_is_checklist_derived_and_domain_labeled() -> None:
    readiness = calculate_readiness("simulation_readiness")
    total = sum(item["weight"] for item in readiness["items"])
    earned = sum(item["weight"] * {"pass": 1.0, "partial": 0.5, "fail": 0.0, "unknown": 0.0}[item["status"]] for item in readiness["items"])
    assert readiness["score"] == round((earned / total) * 100)
    assert readiness["readiness_domain"] == "simulation_readiness"
    assert readiness["checklist_version"] == READINESS_CHECKLIST_VERSION


def test_mock_brain_endpoints_accept_bridge_events_and_run_scenarios() -> None:
    client = TestClient(app)
    state_response = client.get("/metis/state")
    assert state_response.status_code == 200
    event_response = client.post("/metis/event", json={"type": "control_change", "control": "initiative", "value": 0.9})
    assert event_response.status_code == 200
    assert event_response.json()["state"]["initiative_bucket"] == "proactive"
    scenario_response = client.post("/metis/scenario/run", json={})
    assert scenario_response.status_code == 200
    assert scenario_response.json()["passed"] is True
    adapters_response = client.get("/metis/adapters")
    assert adapters_response.status_code == 200
    failure_response = client.post("/metis/failures/stt_failure/trigger", json={})
    assert failure_response.status_code == 200
    assert failure_response.json()["state"]["active_failure"] == "stt_failure"


def test_mock_brain_exports_resets_and_replays_event_log() -> None:
    client = TestClient(app)
    reset_response = client.post("/metis/state/reset")
    assert reset_response.status_code == 200
    events = [
        {"type": "control_change", "control": "initiative", "value": 0.9},
        {"type": "button_event", "button": "am_fm", "state": "fm"},
        {"type": "user_intent", "intent": "send_email", "action_class": "external_action"},
    ]
    replay_response = client.post("/metis/replay", json={"events": events, "reset": True})
    assert replay_response.status_code == 200
    replayed = replay_response.json()
    assert replayed["event_count"] == 3
    assert replayed["state"]["initiative_bucket"] == "proactive"
    assert replayed["state"]["pending_approval_count"] == 1
    export_response = client.get("/metis/export")
    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["export_schema"] == "metis_export.v0.1"
    assert len(exported["event_log"]) == 3
    assert exported["event_log"][0]["schema_version"] == "metis_event.v0.1"
    assert exported["event_log"][2]["action_class"] == "external_action"


def test_dashboard_contains_virtual_radio_controls() -> None:
    dashboard = Path("metis_head/static/dashboard.html").read_text(encoding="utf-8")
    assert "Virtual Radio" in dashboard
    assert "volumeRange" in dashboard
    assert "depthRange" in dashboard
    assert "initiativeRange" in dashboard
    assert "radioActivityLed" in dashboard
    assert "radioAuthorityLed" in dashboard
    assert "toggleMic" in dashboard
    assert "toggleCamera" in dashboard
    assert "Export and Replay" in dashboard
    assert "downloadExport" in dashboard
    assert "replayEvents" in dashboard
    assert "resetState" in dashboard
