from __future__ import annotations

import json

import pytest

from metis_head.bridge import BRIDGE_SCHEMA_VERSION
from metis_head.bridge_emulator import (
    BRIDGE_EMULATOR_VERSION,
    BridgeEmulatorError,
    emulator_button,
    emulator_control,
    emulator_heartbeat,
    emulator_privacy,
    events_to_jsonl,
    parse_jsonl_events,
    replay_jsonl_locally,
)


def test_emulator_control_event_matches_bridge_schema() -> None:
    event = emulator_control("initiative", 0.82, raw=839, timestamp_ms=120311)

    assert event["type"] == "control_change"
    assert event["control"] == "initiative"
    assert event["value"] == 0.82
    assert event["raw"] == 839
    assert event["bridge_schema"] == BRIDGE_SCHEMA_VERSION
    assert event["emulator_version"] == BRIDGE_EMULATOR_VERSION
    assert event["schema_version"] == "metis_event.v0.1"


def test_emulator_button_privacy_and_heartbeat_events_validate() -> None:
    button = emulator_button("am_fm", "fm", timestamp_ms=120522)
    privacy = emulator_privacy("mic", False, timestamp_ms=121002)
    beat = emulator_heartbeat(uptime_ms=99120)

    assert button["type"] == "button_event"
    assert button["button"] == "am_fm"
    assert button["state"] == "fm"
    assert privacy["type"] == "hardware_privacy"
    assert privacy["device"] == "mic"
    assert privacy["enabled"] is False
    assert beat["type"] == "heartbeat"
    assert beat["bridge_id"] == "sim-bridge-001"


def test_jsonl_round_trip_and_local_replay() -> None:
    events = [
        emulator_control("conversation_depth", 0.9),
        emulator_button("am_fm", "fm"),
        emulator_privacy("camera", True),
        emulator_heartbeat(uptime_ms=12),
    ]
    jsonl = events_to_jsonl(events)
    parsed = parse_jsonl_events(jsonl)
    state = replay_jsonl_locally(jsonl)

    assert parsed == [json.loads(line) for line in jsonl.splitlines()]
    assert state["conversation_depth_bucket"] == "systems"
    assert state["interaction_mode"] == "agent"
    assert state["camera_hardware_enabled"] is True
    assert state["module_health"]["metis_head_bridge"] == "ok"


def test_jsonl_parser_reports_line_numbers() -> None:
    with pytest.raises(BridgeEmulatorError, match="line 2"):
        parse_jsonl_events('{"type":"heartbeat"}\nnot-json')


def test_jsonl_parser_rejects_non_object_events() -> None:
    with pytest.raises(BridgeEmulatorError, match="line 1"):
        parse_jsonl_events("[1, 2, 3]")
