from __future__ import annotations

from typing import Any


def resolve_leds(state: dict[str, Any]) -> dict[str, Any]:
    failure = state.get("active_failure")
    authority = state.get("authority_state")
    cognition = state.get("cognition_state")
    audio = state.get("audio_state")
    source = state.get("source_state")

    if failure == "governance_block" or authority == "blocked" or source == "blocked":
        activity = ("blocked", "red", 100)
        authority_led = ("blocked", "red", 100)
    elif failure:
        activity = ("failure", "red", 90)
        authority_led = ("degraded", "amber", 70)
    elif state.get("power_state") != "awake":
        activity = ("standby", "dim_white", 80)
        authority_led = ("standby", "dim_white", 80)
    elif state.get("pending_approval_count", 0) > 0 or authority == "awaiting_approval":
        activity = ("awaiting_approval", "amber", 75)
        authority_led = ("awaiting_approval", "amber", 75)
    elif audio == "speaking":
        activity = ("speaking", "green", 55)
        authority_led = ("governed", "blue", 35)
    elif audio == "listening":
        activity = ("listening", "blue", 50)
        authority_led = ("governed", "blue", 35)
    elif cognition == "retrieving":
        activity = ("retrieving", "cyan", 45)
        authority_led = ("source_working", "blue", 40)
    else:
        activity = ("idle", "soft_white", 10)
        authority_led = ("governed", "blue", 20)

    if source in {"sourced", "source_grounded"} and not failure:
        authority_led = ("source_grounded", "blue", max(authority_led[2], 45))
    elif source == "unsourced" and state.get("source_grounding_enabled") and not failure:
        authority_led = ("unsourced", "amber", max(authority_led[2], 55))

    return {
        "activity_led": {"state": activity[0], "color": activity[1], "priority": activity[2]},
        "authority_led": {"state": authority_led[0], "color": authority_led[1], "priority": authority_led[2]},
        "visualizer": {
            "mode": "muted" if state.get("output_muted") else "active",
            "audio_state": audio,
            "privacy": {
                "mic_hardware_enabled": state.get("mic_hardware_enabled"),
                "camera_hardware_enabled": state.get("camera_hardware_enabled"),
            },
        },
    }
