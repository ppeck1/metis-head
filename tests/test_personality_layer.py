from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.llm_providers import governed_messages
from metis_head.personality import PERSONALITY_VERSION, personality_profile
from metis_head.schemas import baseline_state


def test_personality_profile_exposes_constitutional_invariants() -> None:
    profile = personality_profile("counsel")

    assert profile["personality_version"] == PERSONALITY_VERSION
    assert profile["archetype"] == "Wise counsel with governed agency"
    assert "approval_boundary_respect" in profile["non_negotiable_invariants"]
    assert len(profile["traits"]) == 27
    locked = [trait for trait in profile["traits"] if trait["locked"]]
    assert locked
    assert all(trait["active_score"] >= trait["floor"] for trait in locked)


def test_governed_messages_include_metis_personality_prompt() -> None:
    messages = governed_messages("What should we do next?", baseline_state())
    system = messages[0]["content"]

    assert PERSONALITY_VERSION in system
    assert "calm, systems-oriented counsel intelligence" in system
    assert "Never infer approval" in system
    assert "Preserve human authority" in system


def test_agent_mode_uses_agent_personality_mode() -> None:
    state = baseline_state()
    state["interaction_mode"] = "agent"
    messages = governed_messages("Send the email", state)

    assert "active mode: agent" in messages[0]["content"]
    assert "provide proposals only" in messages[0]["content"]


def test_personality_api_and_console_are_available() -> None:
    client = TestClient(app)
    profile = client.get("/metis/personality")
    console = client.get("/metis/personality/console")

    assert profile.status_code == 200
    assert profile.json()["personality_version"] == PERSONALITY_VERSION
    assert console.status_code == 200
    assert "METIS Personality Console" in console.text
