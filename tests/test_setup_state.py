from __future__ import annotations

import json

import pytest

from metis_head.setup_state import PROFILE_SLOT_IDS, SetupStateError, SetupStateStore, default_setup_path


def test_default_path_can_be_overridden_without_touching_user_state(tmp_path):
    expected = (tmp_path / "custom.json").resolve()
    assert default_setup_path({"METIS_SETUP_FILE": str(expected)}) == expected


def test_load_seeds_four_non_personal_profiles_and_persists(tmp_path):
    path = tmp_path / "setup.json"
    store = SetupStateStore(path)

    state = store.load()

    assert path.exists()
    assert state["schema_version"] == 1
    assert state["revision"] == 0
    assert [profile["slot_id"] for profile in state["google_profiles"]] == list(PROFILE_SLOT_IDS)
    assert [profile["label"] for profile in state["google_profiles"]] == [
        "Personal / Main", "Nursing", "Photography", "Sinternet Cult"
    ]
    assert all(profile["account_id"] is None for profile in state["google_profiles"])
    assert state["profile_selection"] == {
        "mode": "default",
        "default_slot_id": "profile_1",
        "active_slot_ids": ["profile_1"],
    }


def test_update_round_trips_allowed_settings_and_verification_metadata(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    original = store.load()

    updated = store.update(
        {
            "wizard": {"completed": True, "completed_version": "1"},
            "provider": {"choice": "ollama", "model": "local-model", "status": "verified"},
            "voice": {"volume": 0.45, "rate": 1.15, "voice_id": "calm"},
            "google_profiles": {
                "profile_1": {
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
                }
            },
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
    store.update({"google_profiles": {"profile_2": {"account_id": "person@example.test", "status": "verified"}}})

    public = store.public_view()
    private = store.public_view(include_account_ids=True)

    assert public["google_profiles"][1]["account_id"] is None
    assert public["google_profiles"][1]["connected"] is True
    assert private["google_profiles"][1]["account_id"] == "person@example.test"
    assert "connected" not in private["google_profiles"][1]


@pytest.mark.parametrize(
    "patch",
    [
        {"unknown": True},
        {"provider": {"api_key": "not-allowed"}},
        {"voice": {"transcript": "do not store this"}},
        {"provider": {"model": "sk-abcdefghijklmnopqrstuvwxyz"}},
        {"google_profiles": {"profile_5": {"label": "Extra"}}},
    ],
)
def test_update_rejects_unknown_or_sensitive_material(tmp_path, patch):
    store = SetupStateStore(tmp_path / "setup.json")
    with pytest.raises(SetupStateError):
        store.update(patch)


def test_default_mode_cannot_silently_expand_selected_profiles(tmp_path):
    store = SetupStateStore(tmp_path / "setup.json")
    with pytest.raises(SetupStateError, match="default selection mode"):
        store.update({"profile_selection": {"active_slot_ids": ["profile_1", "profile_2"]}})


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
