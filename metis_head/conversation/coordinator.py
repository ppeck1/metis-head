from __future__ import annotations

from threading import RLock
from typing import Callable, Mapping, Sequence

from metis_head.orchestration import (
    AuthorizationContext,
    CancellationToken,
    LoopLimits,
    ModelAdapter,
    OrchestrationOutcome,
    ToolExecutor,
    ToolOrchestrator,
    ToolSpec,
)
from metis_head.orchestration.contracts import ToolHandler


AdapterFactory = Callable[[CancellationToken], ModelAdapter]


class PersonalConversationCoordinator:
    """Coordinate one cancellable orchestration at a time per session.

    No history is owned or committed here. Callers decide whether an outcome is
    still current before storing or playing it.
    """

    def __init__(
        self,
        *,
        entries: Mapping[str, tuple[ToolSpec, ToolHandler]],
        authorization: AuthorizationContext,
        adapter_factory: AdapterFactory,
        limits: LoopLimits | None = None,
    ) -> None:
        self._executor = ToolExecutor(entries)
        self._authorization = authorization
        self._adapter_factory = adapter_factory
        self._limits = limits or LoopLimits()
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = RLock()

    def run_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        conversation: Sequence[Mapping[str, str]],
        system_instructions: str = "",
        preflight: Callable[[], bool] | None = None,
    ) -> OrchestrationOutcome:
        if not session_id.strip() or not turn_id.strip():
            raise ValueError("session_id and turn_id are required")
        token = CancellationToken()
        with self._lock:
            previous = self._tokens.get(session_id)
            if previous is not None:
                previous.cancel("superseded by a newer turn")
            self._tokens[session_id] = token
            # Register the cancellation token before consulting the caller's
            # session authority.  A cancellation that happened before this
            # coordinator was published is caught by preflight; one after
            # registration reaches cancel_session and cancels this token.
            if preflight is not None and not preflight():
                token.cancel("turn cancelled before coordinator dispatch")
        try:
            orchestrator = ToolOrchestrator(self._executor, self._adapter_factory(token), self._limits)
            return orchestrator.run(
                session_id=session_id,
                turn_id=turn_id,
                conversation=conversation,
                authorization=self._authorization,
                cancellation=token,
                system_instructions=system_instructions,
            )
        finally:
            with self._lock:
                if self._tokens.get(session_id) is token:
                    del self._tokens[session_id]

    def cancel_session(self, session_id: str, reason: str = "session cancelled") -> bool:
        with self._lock:
            token = self._tokens.pop(session_id, None)
        if token is None:
            return False
        token.cancel(reason)
        return True

    def active_sessions(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._tokens))
