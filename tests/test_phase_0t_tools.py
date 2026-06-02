from __future__ import annotations

from fastapi.testclient import TestClient

from metis_head.brain import app
from metis_head.reducer import replay_events
from metis_head.schemas import baseline_state
from metis_head.tool_registry import build_tool_proposal_event


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/metis/state/reset")
    return client


def test_tool_registry_lists_seeded_tools_with_governance_labels() -> None:
    client = _client()

    response = client.get("/metis/tools")

    assert response.status_code == 200
    body = response.json()
    tools = {tool["tool_id"]: tool for tool in body["tools"]}
    assert body["tool_registry_version"] == "metis_tool_registry.v0.1"
    assert {"time.now", "text.summarize", "math.calculate", "filesystem.read_proposed", "git.status_proposed", "memory.propose"} <= set(tools)
    assert tools["time.now"]["permission_mode"] == "dry_run"
    assert tools["filesystem.read_proposed"]["side_effect_class"] == "read_only"
    assert tools["git.status_proposed"]["source_reference"] == "modelcontextprotocol/servers:git"


def test_unknown_tool_returns_404() -> None:
    client = _client()

    response = client.get("/metis/tools/nope.missing")

    assert response.status_code == 404


def test_dry_run_safe_tool_returns_receipt_without_execution() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/math.calculate/dry_run",
        json={"arguments": {"operation": "add", "a": 2, "b": 3}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "dry_run_complete"
    assert body["receipt"]["execution_allowed"] is False
    assert body["receipt"]["result"]["result"] == 5.0
    assert body["state"]["external_action_executed"] is False
    assert body["state"]["tool_queue_count"] == 0


def test_time_now_dry_run_accepts_deterministic_test_clock() -> None:
    client = _client()

    response = client.post(
        "/metis/tools/time.now/dry_run",
        json={"arguments": {"now": "2026-06-02T12:00:00Z", "timezone": "UTC"}},
    )

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["result"]["iso_time"] == "2026-06-02T12:00:00Z"
    assert receipt["result"]["timezone"] == "UTC"


def test_filesystem_and_git_tools_queue_proposals_without_reading_or_running() -> None:
    client = _client()

    fs = client.post("/metis/tools/filesystem.read_proposed/dry_run", json={"arguments": {"path": "B:\\secret.txt"}})
    git = client.post("/metis/tools/git.status_proposed/dry_run", json={"arguments": {"repository": "B:\\dev\\metis_head\\metis_head"}})

    assert fs.status_code == 200
    assert git.status_code == 200
    state = git.json()["state"]
    assert state["tool_queue_count"] == 2
    assert state["external_action_executed"] is False
    assert state["approval_queue"][0]["tool_id"] == "filesystem.read_proposed"
    assert state["approval_queue"][0]["execution_allowed"] is False
    assert "content" not in state["approval_queue"][0]
    assert "stdout" not in state["approval_queue"][1]


def test_agent_mode_always_queues_tool_proposal_even_for_safe_dry_run() -> None:
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "fm"})

    response = client.post("/metis/tools/time.now/dry_run", json={"arguments": {"now": "2026-06-02T12:00:00Z"}})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proposal_queued"
    assert body["proposal"]["tool_id"] == "time.now"
    assert body["proposal"]["execution_allowed"] is False
    assert body["state"]["external_action_executed"] is False


def test_tool_proposal_ids_are_deterministic_on_replay() -> None:
    state = baseline_state()
    event = build_tool_proposal_event("filesystem.read_proposed", {"path": "B:\\data.txt"}, state)

    first = replay_events(baseline_state(), [event])
    second = replay_events(baseline_state(), [event])

    assert first["approval_queue"] == second["approval_queue"]
    assert first["approval_queue"][0]["tool_arguments"]["path"] == "B:\\data.txt"


def test_execute_blocks_side_effectful_tools_and_queues_review() -> None:
    client = _client()

    response = client.post("/metis/tools/filesystem.read_proposed/execute", json={"arguments": {"path": "B:\\data.txt"}})

    assert response.status_code == 200
    body = response.json()
    assert body["execution_status"] == "blocked_pending_review"
    assert body["proposal"]["tool_id"] == "filesystem.read_proposed"
    assert body["proposal"]["execution_allowed"] is False
    assert body["state"]["external_action_executed"] is False


def test_memory_tool_queues_memory_proposal_without_promotion() -> None:
    client = _client()

    response = client.post("/metis/tools/propose", json={"tool_id": "memory.propose", "arguments": {"memory_id": "metis_pref_1", "summary": "review me"}})

    assert response.status_code == 200
    state = response.json()["state"]
    assert state["memory_proposal_count"] == 1
    assert state["memory_promoted"] is False
    assert state["approval_queue"][0]["proposal_type"] == "memory"
    assert state["approval_queue"][0]["tool_id"] == "memory.propose"


def test_chat_routes_clear_math_request_through_tool_dry_run(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _client()

    response = client.post("/metis/chat", json={"message": "calculate 7 + 5"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_router"
    assert body["model"] == "math.calculate"
    assert body["tool"]["status"] == "dry_run_complete"
    assert body["tool"]["receipt"]["result"]["result"] == 12.0
    assert body["state"]["external_action_executed"] is False
    assert body["state"]["tool_queue_count"] == 0


def test_chat_routes_git_status_to_proposal_without_running_git(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    client = _client()

    response = client.post("/metis/chat", json={"message": "git status please"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_router"
    assert body["tool"]["status"] == "proposal_queued"
    assert body["proposal_queued"] is True
    assert body["state"]["approval_queue"][0]["tool_id"] == "git.status_proposed"
    assert body["state"]["approval_queue"][0]["execution_allowed"] is False
    assert body["state"]["external_action_executed"] is False


def test_chat_tool_routing_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    client = _client()

    response = client.post("/metis/chat", json={"message": "calculate 7 + 5", "options": {"tools": {"enabled": False}}})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert "tool" not in body


def test_agent_mode_tool_chat_queues_one_tool_proposal(monkeypatch) -> None:
    monkeypatch.setenv("METIS_LLM_PROVIDER", "mock")
    client = _client()
    client.post("/metis/event", json={"type": "button_event", "button": "am_fm", "state": "agent"})

    response = client.post("/metis/chat", json={"message": "calculate 7 + 5"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "tool_router"
    assert body["tool"]["status"] == "proposal_queued"
    assert body["state"]["tool_queue_count"] == 1
    assert len(body["state"]["approval_queue"]) == 1
    assert body["state"]["approval_queue"][0]["tool_id"] == "math.calculate"
    assert body["state"]["approval_queue"][0]["execution_allowed"] is False
