from __future__ import annotations

import json

import pytest

from metis_head.setup_state import PROFILE_SLOT_IDS, SetupStateError, SetupStateStore, default_setup_path


def test_default_path_can_be_overridden_without_touching_user_state(tmp_path):
    expected = (tmp_path / "custom.json").resolve()
    assert default_setup_path({"METIS_SETUP_FILE": str(expected)}) == expected


def test_load_seeds_empty_dynamic_connections_and_persists(tmp_path):
    path = tmp_path / "setup.json"
    store = SetupStateStore(path)

    state = store.load()

    assert path.exists()
    assert state["schema_version"] == 2
    assert state["revision"] == 0
    assert state["google_profiles"] == []
    assert state["voice"]["stt_provider"] == "faster_whisper"
    assert state["profile_selection"] == {
        "mode": "default",
        "default_slot_id": None,
        "active_slot_ids": [],
    }


def test_update_round_trips_allowed_settings_and_verification_metadata(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    original = store.load()

    updated = store.update(
        {
            "wizard": {"completed": True, "completed_version": "1"},
            "provider": {"choice": "ollama", "model": "local-model", "status": "verified"},
            "voice": {"volume": 0.45, "rate": 1.15, "voice_id": "calm"},
            "google_profiles": [
                {
                    "slot_id": "profile_1",
                    "label": "Primary",
                    "account_id": "acct-opaque-1",
                    "calendar_ids": ["primary", "shared-calendar"],
                    "scopes": ["gmail.readonly", "calendar.readonly"],
                    "status": "verified",
                    "last_verification": {
                        "timestamp": "2026-09-16T10:30:00-04:00",
                        "device": "browser",
                        "provider": "google",
                        "model": None,
                        "status": "verified",
                        "error_code": None,
                    },
                },
                {
                    "slot_id": "profile_3", "label": "Photography", "account_id": "acct-opaque-3",
                    "calendar_ids": [], "scopes": [], "status": "verified", "last_verification": None,
                },
            ],
            "profile_selection": {
                "mode": "explicit",
                "default_slot_id": "profile_1",
                "active_slot_ids": ["profile_1", "profile_3"],
            },
        },
        expected_revision=original["revision"],
    )

    assert updated["revision"] == 1
    assert updated["google_profiles"][0]["label"] == "Primary"
    assert updated["google_profiles"][0]["last_verification"]["timestamp"] == "2026-09-16T14:30:00Z"
    assert SetupStateStore(store.path).load() == updated


def test_public_view_redacts_account_ids_by_default(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    store.update({
        "google_profiles": [{
            "slot_id": "profile_2", "label": "Person", "account_id": "person@example.test",
            "calendar_ids": [], "scopes": [], "status": "verified", "last_verification": None,
        }],
        "profile_selection": {
            "mode": "default", "default_slot_id": "profile_2", "active_slot_ids": ["profile_2"],
        },
    })

    public = store.public_view()
    private = store.public_view(include_account_ids=True)

    assert public["google_profiles"][0]["account_id"] is None
    assert public["google_profiles"][0]["connected"] is True
    assert private["google_profiles"][0]["account_id"] == "person@example.test"
    assert "connected" not in private["google_profiles"][0]


@pytest.mark.parametrize(
    "patch",
    [
        {"unknown": True},
        {"provider": {"api_key": "not-allowed"}},
        {"voice": {"transcript": "do not store this"}},
        {"provider": {"model": "sk-abcdefghijklmnopqrstuvwxyz"}},
        {"google_profiles": [{"slot_id": "bad id", "label": "Extra", "account_id": None, "calendar_ids": [], "scopes": [], "status": "not_connected", "last_verification": None}]},
    ],
)
def test_update_rejects_unknown_or_sensitive_material(tmp_path, patch):
    store = SetupStateStore(tmp_path / "setup.json")
    with pytest.raises(SetupStateError):
        store.update(patch)


def test_default_mode_cannot_silently_expand_selected_profiles(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    profiles = [
        {"slot_id": f"profile_{index}", "label": f"Account {index}", "account_id": f"a{index}@example.test",
         "calendar_ids": [], "scopes": [], "status": "verified", "last_verification": None}
        for index in (1, 2)
    ]
    with pytest.raises(SetupStateError, match="default selection mode"):
        store.update({
            "google_profiles": profiles,
            "profile_selection": {
                "mode": "default", "default_slot_id": "profile_1",
                "active_slot_ids": ["profile_1", "profile_2"],
            },
        })


def test_schema_one_four_slots_migrate_without_losing_labels_or_calendars(tmp_path):
    path = tmp_path / "setup.json"
    legacy = SetupStateStore(path).load()
    legacy["schema_version"] = 1
    legacy["voice"].pop("stt_provider")
    legacy["google_profiles"] = [
        {
            "slot_id": slot_id, "label": label, "account_id": f"{index}@example.test",
            "calendar_ids": [f"calendar-{index}"], "scopes": ["calendar.readonly"],
            "status": "verified", "last_verification": None,
        }
        for index, (slot_id, label) in enumerate(zip(PROFILE_SLOT_IDS, ("Main", "Nursing", "Photo", "Shop")), 1)
    ]
    legacy["profile_selection"] = {
        "mode": "default", "default_slot_id": "profile_1", "active_slot_ids": ["profile_1"],
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")

    migrated = SetupStateStore(path).load()

    assert migrated["schema_version"] == 2
    assert [item["slot_id"] for item in migrated["google_profiles"]] == list(PROFILE_SLOT_IDS)
    assert migrated["google_profiles"][4 - 1]["calendar_ids"] == ["calendar-4"]
    assert migrated["voice"]["stt_provider"] == "faster_whisper"


def test_five_dynamic_profiles_round_trip_and_one_can_be_removed(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    profiles = [
        {
            "slot_id": f"google_{index}", "label": f"Account {index}", "account_id": f"a{index}@example.test",
            "calendar_ids": [f"cal-{index}"], "scopes": ["calendar.readonly"],
            "status": "verified", "last_verification": None,
        }
        for index in range(5)
    ]
    saved = store.update({
        "google_profiles": profiles,
        "profile_selection": {
            "mode": "default", "default_slot_id": "google_0", "active_slot_ids": ["google_0"],
        },
    })
    remaining = [item for item in saved["google_profiles"] if item["slot_id"] != "google_2"]
    updated = store.update({
        "google_profiles": remaining,
        "profile_selection": {
            "mode": "default", "default_slot_id": "google_0", "active_slot_ids": ["google_0"],
        },
    })

    assert len(updated["google_profiles"]) == 4
    assert [item["slot_id"] for item in updated["google_profiles"]] == ["google_0", "google_1", "google_3", "google_4"]

    removed_by_id = store.update({
        "google_profiles": {"google_4": None},
        "profile_selection": {
            "mode": "default", "default_slot_id": "google_0", "active_slot_ids": ["google_0"],
        },
    })
    assert [item["slot_id"] for item in removed_by_id["google_profiles"]] == ["google_0", "google_1", "google_3"]


def test_expected_revision_prevents_lost_update(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    state = store.load()
    store.update({"voice": {"volume": 0.2}}, expected_revision=state["revision"])

    with pytest.raises(SetupStateError, match="revision changed"):
        store.update({"voice": {"volume": 0.3}}, expected_revision=state["revision"])


def test_invalid_existing_file_fails_closed_without_overwriting(tmp_path):
    path = tmp_path / "setup.json"
    path.write_text('{"schema_version": 999}', encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    with pytest.raises(SetupStateError):
        SetupStateStore(path).load()

    assert path.read_text(encoding="utf-8") == before


def test_atomic_write_leaves_no_temporary_file(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    store.update({"provider": {"status": "verified"}})

    assert json.loads(store.path.read_text(encoding="utf-8"))["revision"] == 1
    assert list(tmp_path.glob("*.tmp")) == []
