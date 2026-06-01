from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.sim_manifest import SIM_TEST_MANIFEST_VERSION, build_sim_test_manifest


def test_sim_manifest_is_versioned_and_summary_is_computed() -> None:
    manifest = build_sim_test_manifest()

    assert manifest["manifest_version"] == SIM_TEST_MANIFEST_VERSION
    assert manifest["state_schema"] == "metis_state.v0.3"
    assert manifest["event_schema"] == "metis_event.v0.1"
    assert manifest["summary"]["scenario_count"] == len(manifest["scenarios"])
    assert manifest["summary"]["scenario_failed"] == 0
    assert manifest["summary"]["scenario_passed"] == manifest["summary"]["scenario_count"]
    assert manifest["readiness"]["source"].startswith("computed_")


def test_sim_manifest_maps_required_acceptance_coverage() -> None:
    manifest = build_sim_test_manifest()
    requirements = {item["requirement_id"]: item for item in manifest["acceptance_requirements"]}

    for requirement_id in [
        "safe_boot_simulated",
        "output_mute_not_privacy",
        "mic_cutoff_blocks_capture",
        "camera_cutoff_blocks_capture",
        "agent_mode_queues_action",
        "governance_block_overrides_leds",
        "stt_failure_visible",
        "tts_failure_visible",
        "vault_failure_visible",
        "adapter_schema_mismatch_disables",
        "memory_proposal_requires_review",
        "event_replay_deterministic",
        "readiness_score_computed",
        "voice_output_governed",
    ]:
        assert requirements[requirement_id]["status"] == "pass"


def test_sim_manifest_contains_hardware_parity_links() -> None:
    manifest = build_sim_test_manifest(include_results=False)
    parity = manifest["hardware_parity_manifest"]

    assert manifest["summary"]["hardware_parity_item_count"] == len(parity)
    assert any(item["hardware"] == "mic_cutoff" and item["event"] == "hardware_privacy:mic" for item in parity)
    assert any(item["hardware"] == "loud_button" and item["state"] == "output_muted" for item in parity)


def test_sim_manifest_endpoint_is_available() -> None:
    client = TestClient(app)
    response = client.get("/metis/sim/manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["manifest_version"] == SIM_TEST_MANIFEST_VERSION
    assert body["summary"]["scenario_failed"] == 0


def test_sim_tests_alias_endpoint_can_skip_results() -> None:
    client = TestClient(app)
    response = client.get("/metis/sim/tests", params={"include_results": False})

    assert response.status_code == 200
    body = response.json()
    assert body["manifest_version"] == SIM_TEST_MANIFEST_VERSION
    assert body["summary"]["scenario_passed"] is None
    assert all(item["passed"] is None for item in body["scenarios"])
