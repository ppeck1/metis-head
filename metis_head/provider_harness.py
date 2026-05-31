from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .providers import (
    BlockedToolProvider,
    BlockedVisionProvider,
    FailedSTTProvider,
    FailedTTSProvider,
    FailedVaultProvider,
    FakeAtlasProvider,
    FakeBOHMemoryProvider,
    FakeLLMRouterProvider,
    FakeRobotSafetyProvider,
    FakeSTTProvider,
    FakeTTSProvider,
    FakeToolProvider,
    FakeVisionProvider,
    NoOpSTTProvider,
    NoOpVisionProvider,
)


PROVIDER_HARNESS_VERSION = "metis_provider_harness.v0.1"


@dataclass(frozen=True)
class ProviderOperation:
    provider_id: str
    variant: str
    operation: str
    description: str

    @property
    def operation_id(self) -> str:
        return f"{self.provider_id}.{self.variant}.{self.operation}"

    def to_dict(self) -> dict[str, str]:
        return {
            "operation_id": self.operation_id,
            "provider_id": self.provider_id,
            "variant": self.variant,
            "operation": self.operation,
            "description": self.description,
            "harness_version": PROVIDER_HARNESS_VERSION,
        }


OPERATIONS: dict[str, ProviderOperation] = {
    item.operation_id: item
    for item in [
        ProviderOperation("stt", "noop", "transcribe", "Return an empty transcript event."),
        ProviderOperation("stt", "fake", "transcribe", "Return a deterministic transcript event."),
        ProviderOperation("stt", "failed", "transcribe", "Emit a visible STT failure event."),
        ProviderOperation("tts", "fake", "speak", "Emit speaking then complete events without audio."),
        ProviderOperation("tts", "failed", "speak", "Emit a visible TTS failure event."),
        ProviderOperation("vision", "noop", "capture", "Emit a camera capture request."),
        ProviderOperation("vision", "fake", "capture", "Emit a synthetic camera capture request."),
        ProviderOperation("vision", "blocked", "capture", "Emit a visible camera failure event."),
        ProviderOperation("boh_memory", "fake", "retrieve", "Emit a cited synthetic retrieval event."),
        ProviderOperation("vault", "failed", "retrieve", "Emit a visible vault unavailable event."),
        ProviderOperation("tools", "fake", "queue", "Queue a governed tool proposal event."),
        ProviderOperation("tools", "blocked", "queue", "Emit a governed tool-block failure event."),
        ProviderOperation("project_atlas", "fake", "propose_task", "Queue a governed Atlas task proposal event."),
        ProviderOperation("llm_router", "fake", "route", "Return a canned routing result without model execution."),
        ProviderOperation("robot_safety", "fake", "classify", "Return a denied actuator-action classification."),
    ]
}


class ProviderHarnessError(ValueError):
    pass


def provider_catalog() -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for operation in OPERATIONS.values():
        grouped.setdefault(operation.provider_id, []).append(operation.to_dict())
    return {"harness_version": PROVIDER_HARNESS_VERSION, "providers": grouped}


def invoke_provider(operation_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if operation_id not in OPERATIONS:
        raise ProviderHarnessError(f"unknown provider operation: {operation_id}")

    if operation_id == "stt.noop.transcribe":
        result = NoOpSTTProvider().transcribe()
    elif operation_id == "stt.fake.transcribe":
        result = FakeSTTProvider().transcribe()
    elif operation_id == "stt.failed.transcribe":
        result = FailedSTTProvider().transcribe()
    elif operation_id == "tts.fake.speak":
        result = FakeTTSProvider().speak(str(payload.get("text") or "metis test speech"))
    elif operation_id == "tts.failed.speak":
        result = FailedTTSProvider().speak(str(payload.get("text") or "metis test speech"))
    elif operation_id == "vision.noop.capture":
        result = NoOpVisionProvider().capture()
    elif operation_id == "vision.fake.capture":
        result = FakeVisionProvider().capture()
    elif operation_id == "vision.blocked.capture":
        result = BlockedVisionProvider().capture()
    elif operation_id == "boh_memory.fake.retrieve":
        result = FakeBOHMemoryProvider().retrieve()
    elif operation_id == "vault.failed.retrieve":
        result = FailedVaultProvider().retrieve()
    elif operation_id == "tools.fake.queue":
        result = FakeToolProvider().queue(str(payload.get("action_class") or "external_action"))
    elif operation_id == "tools.blocked.queue":
        result = BlockedToolProvider().queue(str(payload.get("action_class") or "external_action"))
    elif operation_id == "project_atlas.fake.propose_task":
        result = FakeAtlasProvider().propose_task()
    elif operation_id == "llm_router.fake.route":
        result = FakeLLMRouterProvider().route(str(payload.get("role") or "default"))
    elif operation_id == "robot_safety.fake.classify":
        result = FakeRobotSafetyProvider().classify(str(payload.get("action") or "move actuator"))
    else:
        raise ProviderHarnessError(f"unimplemented provider operation: {operation_id}")

    events = result if isinstance(result, list) else [result] if _is_event(result) else []
    return {
        "harness_version": PROVIDER_HARNESS_VERSION,
        "operation": OPERATIONS[operation_id].to_dict(),
        "result": result,
        "events": events,
        "event_count": len(events),
    }


def _is_event(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("type"), str)
