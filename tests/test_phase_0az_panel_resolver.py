from __future__ import annotations

from copy import deepcopy
import json

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.panel import PANEL_REASONS, PANEL_RENDER_VERSION, resolve_panel
from metis_head.reducer import reduce_metis_event, replay_events
from metis_head.scenarios import SCENARIOS, run_scenario
from metis_head.schemas import baseline_state


EXPECTED_KEYS = {
    "type",
    "schema_version",
    "activity_led",
    "authority_led",
    "visualizer",
    "approval_indicator",
    "tool_indicator",
    "memory_indicator",
    "voice_indicator",
    "mic_cutoff_indicator",
    "camera_cutoff_indicator",
    "panel_precedence_applied",
    "execution_allowed",
}


def test_resolver_shape_and_idle_baseline() -> None:
    panel = resolve_panel(baseline_state())

    assert set(panel) == EXPECTED_KEYS
    assert panel["schema_version"] == PANEL_RENDER_VERSION
    assert panel["type"] == "panel_render"
    assert panel["execution_allowed"] is False
    assert panel["panel_precedence_applied"] == "idle"
    assert panel["approval_indicator"] == {"on": False, "count": 0, "reason": None}
    assert panel["tool_indicator"]["on"] is False
    assert panel["memory_indicator"]["on"] is False
    assert panel["voice_indicator"]["state"] == "idle"
    assert panel["mic_cutoff_indicator"]["capture_enabled"] is True
    assert panel["camera_cutoff_indicator"]["capture_enabled"] is False


def test_panel_leds_match_resolve_leds_via_endpoint() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")

    response = client.get("/metis/panel")

    assert response.status_code == 200
    body = response.json()
    panel = body["panel"]
    leds = body["leds"]
    assert panel["activity_led"] == leds["activity_led"]
    assert panel["authority_led"] == leds["authority_led"]
    assert panel["execution_allowed"] is False
    assert "state" in body


def test_mic_cutoff_takes_panel_precedence() -> None:
    state = run_scenario("mic_cutoff_blocks_capture")["final_state"]

    panel = resolve_panel(state)

    assert panel["panel_precedence_applied"] == "mic_hardware_cutoff"
    assert panel["mic_cutoff_indicator"]["capture_enabled"] is False


def test_camera_cutoff_takes_panel_precedence() -> None:
    state = run_scenario("camera_cutoff_blocks_capture")["final_state"]

    panel = resolve_panel(state)

    assert panel["panel_precedence_applied"] == "camera_hardware_cutoff"
    assert panel["camera_cutoff_indicator"]["capture_enabled"] is False


def test_governance_block_dominates() -> None:
    state = reduce_metis_event(baseline_state(), {"type": "failure_event", "failure_id": "governance_block"})

    panel = resolve_panel(state)

    assert panel["panel_precedence_applied"] == "governance_block"
    assert panel["activity_led"]["color"] == "red"
    assert panel["authority_led"]["color"] == "red"


def test_pending_approval_lights_indicator_and_precedence() -> None:
    state = replay_events(baseline_state(), SCENARIOS["agent_mode_requires_approval"]["events"])

    panel = resolve_panel(state)

    assert panel["approval_indicator"] == {"on": True, "count": 1, "reason": "proposal_pending_review"}
    assert panel["panel_precedence_applied"] == "awaiting_approval"


def test_memory_proposal_lights_memory_indicator() -> None:
    state = run_scenario("memory_proposal_needs_review")["final_state"]

    panel = resolve_panel(state)

    assert panel["memory_indicator"]["on"] is True
    assert panel["memory_indicator"]["reason"] == "memory_proposal_pending_review"


def test_voice_indicator_speaking_and_muted() -> None:
    speaking = deepcopy(baseline_state())
    speaking["voice_output_state"] = "speaking"
    assert resolve_panel(speaking)["voice_indicator"]["state"] == "speaking"

    muted = reduce_metis_event(baseline_state(), {"type": "button_event", "button": "loud", "state": "off"})
    voice = resolve_panel(muted)["voice_indicator"]
    assert muted["output_muted"] is True
    assert voice["state"] == "output_muted"
    assert voice["output_muted"] is True


def test_voice_confirmation_readback_sets_awaiting_state() -> None:
    state = deepcopy(baseline_state())
    state["event_log"] = [
        {"schema_version": "metis_voice_confirmation.v0.1", "status": "readback_required", "text_redacted": True}
    ]

    panel = resolve_panel(state)

    assert panel["voice_indicator"]["state"] == "awaiting_confirmation"
    assert panel["panel_precedence_applied"] == "awaiting_approval"


def test_panel_frame_never_leaks_text_or_secrets() -> None:
    state = deepcopy(baseline_state())
    state["chat_history"] = [{"role": "user", "content": "SECRETVALUE_SHOULD_NOT_APPEAR"}]
    state["event_log"] = [
        {
            "schema_version": "metis_voice_confirmation.v0.1",
            "status": "readback_required",
            "text": "SECRETVALUE_SHOULD_NOT_APPEAR",
        }
    ]

    dumped = json.dumps(resolve_panel(state))

    assert "SECRETVALUE_SHOULD_NOT_APPEAR" not in dumped


def test_all_reasons_are_in_fixed_enum() -> None:
    states = [
        baseline_state(),
        run_scenario("mic_cutoff_blocks_capture")["final_state"],
        run_scenario("memory_proposal_needs_review")["final_state"],
        replay_events(baseline_state(), SCENARIOS["agent_mode_requires_approval"]["events"]),
    ]
    for state in states:
        panel = resolve_panel(state)
        for indicator in ("approval_indicator", "tool_indicator", "memory_indicator"):
            reason = panel[indicator].get("reason")
            assert reason is None or reason in PANEL_REASONS


def test_panel_is_deterministic_on_replay() -> None:
    events = deepcopy(SCENARIOS["agent_mode_requires_approval"]["events"])
    first = resolve_panel(replay_events(baseline_state(), events))
    second = resolve_panel(replay_events(baseline_state(), events))

    assert first == second


def test_execution_allowed_false_across_states() -> None:
    states = [
        baseline_state(),
        run_scenario("mic_cutoff_blocks_capture")["final_state"],
        reduce_metis_event(baseline_state(), {"type": "failure_event", "failure_id": "governance_block"}),
        replay_events(baseline_state(), SCENARIOS["agent_mode_requires_approval"]["events"]),
    ]
    for state in states:
        assert resolve_panel(state)["execution_allowed"] is False
