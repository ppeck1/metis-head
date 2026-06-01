from __future__ import annotations

from metis_head.bridge import HARDWARE_PARITY_MANIFEST, validate_hardware_parity_manifest
from metis_head.readiness import calculate_readiness
from metis_head.scenarios import SCENARIOS, run_scenario
from metis_head.sim_manifest import build_sim_test_manifest


def test_all_hardware_parity_items_reference_executable_scenarios() -> None:
    validation = validate_hardware_parity_manifest(set(SCENARIOS))

    assert validation["passed"] is True
    assert validation["failures"] == []
    assert validation["item_count"] == len(HARDWARE_PARITY_MANIFEST)


def test_control_parity_scenarios_pass() -> None:
    volume = run_scenario("volume_control_updates_state")
    depth = run_scenario("conversation_depth_control_updates_state")
    heartbeat = run_scenario("bridge_heartbeat_sets_bridge_ok")

    assert volume["passed"] is True
    assert depth["passed"] is True
    assert heartbeat["passed"] is True


def test_sim_manifest_reports_hardware_parity_passed() -> None:
    manifest = build_sim_test_manifest(include_results=False)

    assert manifest["summary"]["hardware_parity_passed"] is True
    assert manifest["hardware_parity_validation"]["passed"] is True


def test_readiness_hardware_parity_item_is_pass() -> None:
    readiness = calculate_readiness()
    item = next(item for item in readiness["items"] if item["id"] == "hardware_parity_manifest_available")

    assert item["status"] == "pass"
    assert readiness["partial"] == 0
    assert readiness["score"] == 100
