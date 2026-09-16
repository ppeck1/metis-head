from __future__ import annotations

from threading import Event, Thread

from metis_head.conversation.coordinator import PersonalConversationCoordinator
from metis_head.orchestration import (
    AccessMode,
    AdapterResponse,
    AuthorizationContext,
    LoopLimits,
    ToolCall,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
    ToolSpec,
)


def test_coordinator_preserves_session_and_turn_ids_without_committing_state() -> None:
    requests: list[ToolRequest] = []
    spec = ToolSpec(
        "local.echo",
        "1",
        "fixture",
        {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        AccessMode.READ,
    )

    def handler(request, cancellation):
        requests.append(request)
        return ToolResult(request.request_id, ToolResultStatus.SUCCESS, {"value": request.arguments["value"]})

    class Adapter:
        def next_step(self, context):
            if not context.exchanges:
                return AdapterResponse(tool_calls=(ToolCall("provider-call-7", "local.echo", "1", {"value": "hello"}),))
            return AdapterResponse(text=f"echo={context.exchanges[0].result.data['value']}")

    coordinator = PersonalConversationCoordinator(
        entries={spec.name: (spec, handler)},
        authorization=AuthorizationContext(accounts={}),
        adapter_factory=lambda token: Adapter(),
        limits=LoopLimits(max_rounds=2),
    )
    conversation = ({"role": "user", "content": "echo hello"},)
    outcome = coordinator.run_turn(
        session_id="session-a",
        turn_id="turn-42",
        conversation=conversation,
        system_instructions="fixture",
    )

    assert outcome.text == "echo=hello"
    assert requests[0].session_id == "session-a"
    assert requests[0].turn_id == "turn-42"
    assert requests[0].request_id == "provider-call-7"
    assert conversation == ({"role": "user", "content": "echo hello"},)
    assert coordinator.active_sessions() == ()


def test_cancel_session_stops_active_orchestration() -> None:
    entered = Event()
    release = Event()

    class BlockedAdapter:
        def next_step(self, context):
            entered.set()
            release.wait(1)
            return AdapterResponse(text="late response")

    coordinator = PersonalConversationCoordinator(
        entries={},
        authorization=AuthorizationContext(accounts={}),
        adapter_factory=lambda token: BlockedAdapter(),
        limits=LoopLimits(max_total_seconds=2),
    )
    result = []
    worker = Thread(
        target=lambda: result.append(
            coordinator.run_turn(session_id="session-a", turn_id="turn-a", conversation=())
        )
    )
    worker.start()
    assert entered.wait(0.5)
    assert coordinator.cancel_session("session-a", "user interrupted") is True
    worker.join(0.5)
    release.set()

    assert not worker.is_alive()
    assert result[0].stop_reason == "cancelled"
    assert result[0].text is None
    assert coordinator.cancel_session("session-a") is False


def test_new_turn_cancels_older_turn_in_same_session() -> None:
    first_entered = Event()
    release = Event()
    created = 0

    class Adapter:
        def __init__(self, number):
            self.number = number

        def next_step(self, context):
            if self.number == 1:
                first_entered.set()
                release.wait(1)
            return AdapterResponse(text=f"response-{self.number}")

    def factory(token):
        nonlocal created
        created += 1
        return Adapter(created)

    coordinator = PersonalConversationCoordinator(
        entries={}, authorization=AuthorizationContext(accounts={}), adapter_factory=factory
    )
    outcomes = []
    old = Thread(
        target=lambda: outcomes.append(
            coordinator.run_turn(session_id="same", turn_id="old", conversation=())
        )
    )
    old.start()
    assert first_entered.wait(0.5)
    current = coordinator.run_turn(session_id="same", turn_id="new", conversation=())
    old.join(0.5)
    release.set()

    assert current.text == "response-2"
    assert outcomes[0].stop_reason == "cancelled"
