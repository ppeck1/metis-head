from __future__ import annotations

from metis_head.llm_providers import governed_messages
from metis_head.schemas import baseline_state


def _system_for(message: str, state: dict | None = None) -> str:
    messages = governed_messages(message, state or baseline_state(), [])
    return messages[0]["content"]


def test_llm_system_context_advertises_governed_tool_lane() -> None:
    system = _system_for("What tools can you use?")

    assert "Metis has a governed native tool lane" in system
    assert "do not say there are no tools" in system
    assert "time.now" in system
    assert "math.calculate" in system
    assert "filesystem.read" in system
    assert "git.status" in system
    assert "persisted governed tool plans" in system


def test_llm_system_context_keeps_execution_boundary_visible() -> None:
    system = _system_for("Can you use tools?")

    assert "LLM provider does not call tools directly" in system
    assert "proposal and human review" in system
    assert "do not claim autonomous execution" in system
    assert "shell" in system
    assert "arbitrary filesystem" in system
    assert "external actions" in system


def test_agent_mode_tool_context_is_proposal_only() -> None:
    state = baseline_state()
    state["interaction_mode"] = "agent"

    system = _system_for("Use a tool", state)

    assert "In Agent Mode every tool request becomes proposal-only." in system
