from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_chat_tool_awareness_is_deterministic_not_provider_dependent() -> None:
    client = _client()

    response = client.post("/metis/chat", json={"message": "What tools can you use?", "options": {"provider": "ollama"}})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_capability"
    assert body["model"] == "metis_tool_capability_awareness.v0.1"
    assert "Metis has governed tools available" in body["message"]
    assert "I do not call tools directly as an LLM" in body["message"]
    assert "time.now" in body["message"]
    assert "math.calculate" in body["message"]
    assert "filesystem.read" in body["message"]
    assert "git.status" in body["message"]
    assert "no tools" not in body["message"].lower()
    assert body["proposal_queued"] is False
    assert body["plan_queued"] is False
    assert body["state"]["approval_queue"] == []
    assert body["state"]["execution_audit_log"] == []
    assert body["state"]["external_action_executed"] is False


def test_chat_tool_awareness_returns_registry_lanes_as_metadata() -> None:
    client = _client()

    body = client.post("/metis/chat", json={"message": "list current capabilities and tools"}).json()

    capabilities = body["tool_capabilities"]
    assert capabilities["schema_version"] == "metis_tool_capability_awareness.v0.1"
    assert capabilities["llm_direct_tool_calling"] is False
    assert capabilities["voice_instruction_supported"] is True
    assert "time.now" in capabilities["safe_dry_run_tools"]
    assert "filesystem.read" in capabilities["approved_read_only_lanes"]
    assert "git.status" in capabilities["approved_read_only_lanes"]
    assert "memory.propose" in capabilities["proposal_only_lanes"]


def test_voice_tool_awareness_uses_same_governed_capability_route_and_speaks() -> None:
    client = _client()

    response = client.post("/metis/voice/command", json={"text": "What tools are available to you?"})

    assert response.status_code == 200
    body = response.json()
    assert body["input_mode"] == "simulated_voice_command"
    assert body["voice_command"]["recognized"] is True
    assert body["voice_command"]["route"] == "metis_chat"
    assert body["voice_command"]["speech_reply_requested"] is True
    assert body["provider"] == "tool_capability"
    assert body["tool_capabilities"]["voice_instruction_supported"] is True
    assert body["voice"]["spoken"] is True
    assert "Typed or spoken tool requests are routed" in body["message"]
    assert body["state"]["approval_queue"] == []
    assert body["state"]["external_action_executed"] is False


def test_agent_mode_tool_awareness_names_proposal_only_boundary() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})

    body = client.post("/metis/chat", json={"message": "do you have access to tools?"}).json()

    assert body["provider"] == "tool_capability"
    assert body["state"]["interaction_mode"] == "agent"
    assert "Agent Mode queues proposals only" in body["tool_capabilities"]["agent_mode_boundary"]
    assert body["state"]["external_action_executed"] is False
