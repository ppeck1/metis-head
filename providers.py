from __future__ import annotations

from typing import Any


class NoOpSTTProvider:
    provider_id = "stt"

    def transcribe(self) -> dict[str, Any]:
        return {"type": "provider_event", "provider": "stt", "status": "transcript", "text": ""}


class FakeSTTProvider(NoOpSTTProvider):
    def transcribe(self) -> dict[str, Any]:
        return {"type": "provider_event", "provider": "stt", "status": "transcript", "text": "metis test transcript"}


class FailedSTTProvider(NoOpSTTProvider):
    def transcribe(self) -> dict[str, Any]:
        return {"type": "provider_event", "provider": "stt", "status": "failure", "failure_id": "stt_failure"}


class FakeTTSProvider:
    provider_id = "tts"

    def speak(self, text: str) -> list[dict[str, Any]]:
        return [
            {"type": "provider_event", "provider": "tts", "status": "speaking", "text": text},
            {"type": "provider_event", "provider": "tts", "status": "complete"},
        ]


class FailedTTSProvider(FakeTTSProvider):
    def speak(self, text: str) -> list[dict[str, Any]]:
        return [{"type": "provider_event", "provider": "tts", "status": "failure", "failure_id": "tts_failure"}]


class NoOpVisionProvider:
    provider_id = "vision"

    def capture(self) -> dict[str, Any]:
        return {"type": "capture_request", "device": "camera"}


class FakeVisionProvider(NoOpVisionProvider):
    def capture(self) -> dict[str, Any]:
        return {"type": "capture_request", "device": "camera", "metadata": {"synthetic": True}}


class BlockedVisionProvider(NoOpVisionProvider):
    def capture(self) -> dict[str, Any]:
        return {"type": "provider_event", "provider": "vision", "status": "failure", "failure_id": "camera_failure"}


class FakeBOHMemoryProvider:
    provider_id = "boh_memory"

    def retrieve(self) -> dict[str, Any]:
        return {
            "type": "provider_event",
            "provider": "boh_memory",
            "status": "retrieved",
            "candidates": [{"title": "Synthetic BOH note", "citation": "fake://boh/metis"}],
        }


class FailedVaultProvider(FakeBOHMemoryProvider):
    def retrieve(self) -> dict[str, Any]:
        return {"type": "provider_event", "provider": "vault", "status": "unavailable", "failure_id": "vault_unavailable"}


class FakeToolProvider:
    provider_id = "tools"

    def queue(self, action_class: str = "external_action") -> dict[str, Any]:
        return {"type": "user_intent", "intent": "queued tool proposal", "action_class": action_class}


class BlockedToolProvider(FakeToolProvider):
    def queue(self, action_class: str = "external_action") -> dict[str, Any]:
        return {"type": "failure_event", "failure_id": "tool_blocked", "reason": "mock tool provider blocked action"}


class FakeAtlasProvider:
    provider_id = "project_atlas"

    def propose_task(self) -> dict[str, Any]:
        return {"type": "user_intent", "intent": "stage atlas task proposal", "action_class": "external_action"}


class FakeLLMRouterProvider:
    provider_id = "llm_router"

    def route(self, role: str = "default") -> dict[str, Any]:
        return {"role": role, "text": f"canned response for {role}"}


class FakeRobotSafetyProvider:
    provider_id = "robot_safety"

    def classify(self, action: str) -> dict[str, Any]:
        return {"action": action, "action_class": "actuator_action", "allowed": False}
