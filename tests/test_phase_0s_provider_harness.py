from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.provider_harness import PROVIDER_HARNESS_VERSION, invoke_provider, provider_catalog


def test_provider_catalog_lists_required_mock_providers() -> None:
    catalog = provider_catalog()

    assert catalog["harness_version"] == PROVIDER_HARNESS_VERSION
    for provider_id in ["stt", "tts", "vision", "boh_memory", "vault", "tools", "project_atlas", "llm_router", "robot_safety"]:
        assert provider_id in catalog["providers"]


def test_invoke_fake_tts_returns_speaking_and_complete_events() -> None:
    result = invoke_provider("tts.fake.speak", {"text": "hello"})

    assert result["event_count"] == 2
    assert result["events"][0]["status"] == "speaking"
    assert result["events"][1]["status"] == "complete"


def test_brain_provider_failure_updates_visible_state() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")

    response = client.post("/metis/providers/stt.failed.transcribe/invoke", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["state"]["active_failure"] == "stt_failure"
    assert body["state"]["module_health"]["metis_audio"] == "stt_failure"
    assert body["event_count"] == 1


def test_tool_provider_queues_proposal_in_agent_mode_without_execution() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "fm"})

    response = client.post("/metis/providers/tools.fake.queue/invoke", json={"action_class": "external_action"})

    assert response.status_code == 200
    state = response.json()["state"]
    assert state["interaction_mode"] == "agent"
    assert state["pending_approval_count"] == 1
    assert state["tool_queue_count"] == 1
    assert state["external_action_executed"] is False
    assert state["approval_queue"][0]["execution_allowed"] is False


def test_robot_safety_result_is_not_applied_as_state_event() -> None:
    client = TestClient(app)
    client.post("/metis/state/reset")

    response = client.post("/metis/providers/robot_safety.fake.classify/invoke", json={"action": "move arm"})

    assert response.status_code == 200
    body = response.json()
    assert body["event_count"] == 0
    assert body["result"]["allowed"] is False
    assert body["state"]["active_failure"] is None


def test_unknown_provider_operation_is_404() -> None:
    client = TestClient(app)
    response = client.post("/metis/providers/nope.fake.run/invoke", json={})
    assert response.status_code == 404
