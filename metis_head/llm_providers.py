from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    raw: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProviderError(RuntimeError):
    pass


class BaseLLMProvider:
    provider_id = "base"

    def generate(self, messages: list[dict[str, str]], state: dict[str, Any], options: dict[str, Any]) -> LLMResult:
        raise NotImplementedError


class MockLLMProvider(BaseLLMProvider):
    provider_id = "mock"

    def generate(self, messages: list[dict[str, str]], state: dict[str, Any], options: dict[str, Any]) -> LLMResult:
        user_text = _last_user_text(messages)
        detail = state.get("conversation_depth_bucket", "rationale")
        initiative = state.get("initiative_bucket", "helpful")
        mode = state.get("interaction_mode", "human")
        has_retrieved_context = any(
            message.get("role") == "system" and "retrieval context from boh" in str(message.get("content", "")).lower()
            for message in messages
        )
        if not state.get("source_grounding_enabled"):
            grounding = "local"
        elif has_retrieved_context:
            grounding = "sourced"
        else:
            grounding = "unsourced"
        lead = "Proposal only: " if mode == "agent" else ""
        text = f"{lead}Mock response to: {user_text}"
        if detail in {"rationale", "systems"}:
            text += f"\n\nRationale: using {detail} depth with {initiative} initiative."
        if detail == "systems":
            text += "\n\nSystems note: no tools, memory, hardware, or external actions were executed."
        # The Metis brain owns the authoritative source label (sourced/unsourced/degraded);
        # the provider must not emit its own, or it will contradict the real source_state.
        return LLMResult(
            text=text,
            provider=self.provider_id,
            model="mock-governed",
            metadata={"grounding": grounding, "mode": mode, "detail": detail, "initiative": initiative},
        )


class OllamaLLMProvider(BaseLLMProvider):
    provider_id = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, messages: list[dict[str, str]], state: dict[str, Any], options: dict[str, Any]) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": options.get("temperature", 0.2)},
        }
        response = _post_json(f"{self.base_url}/api/chat", payload, headers={})
        text = response.get("message", {}).get("content")
        if not isinstance(text, str):
            raise LLMProviderError("Ollama response did not contain message.content")
        return LLMResult(text=text, provider=self.provider_id, model=self.model, raw=response)


class OpenAILLMProvider(BaseLLMProvider):
    provider_id = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, messages: list[dict[str, str]], state: dict[str, Any], options: dict[str, Any]) -> LLMResult:
        if not self.api_key:
            raise LLMProviderError("OPENAI_API_KEY is required for METIS_LLM_PROVIDER=openai")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": options.get("temperature", 0.2),
        }
        response = _post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        choices = response.get("choices") or []
        text = choices[0].get("message", {}).get("content") if choices else None
        if not isinstance(text, str):
            raise LLMProviderError("OpenAI response did not contain choices[0].message.content")
        return LLMResult(text=text, provider=self.provider_id, model=self.model, raw=response)


def provider_from_env(env: dict[str, str] | None = None) -> BaseLLMProvider:
    env = env or os.environ
    return provider_from_config({}, env)


def provider_from_config(config: dict[str, Any] | None = None, env: dict[str, str] | None = None) -> BaseLLMProvider:
    config = config or {}
    env = env or os.environ
    provider = str(config.get("provider") or env.get("METIS_LLM_PROVIDER", "mock")).lower()
    if provider == "mock":
        return MockLLMProvider()
    if provider == "ollama":
        model = config.get("model") or env.get("METIS_OLLAMA_MODEL")
        if not model:
            raise LLMProviderError("METIS_OLLAMA_MODEL is required for METIS_LLM_PROVIDER=ollama")
        base_url = config.get("base_url") or env.get("METIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        return OllamaLLMProvider(str(base_url), str(model))
    if provider == "openai":
        model = config.get("model") or env.get("METIS_OPENAI_MODEL", "gpt-4o-mini")
        return OpenAILLMProvider(env.get("OPENAI_API_KEY", ""), str(model))
    raise LLMProviderError(f"unsupported METIS_LLM_PROVIDER: {provider}")


def list_ollama_models(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = _get_json(url)
    except LLMProviderError as exc:
        return {"available": False, "base_url": base_url, "models": [], "error": str(exc)}
    models = []
    for model in response.get("models", []):
        name = model.get("name")
        if isinstance(name, str):
            models.append(
                {
                    "name": name,
                    "modified_at": model.get("modified_at"),
                    "size": model.get("size"),
                    "details": model.get("details", {}),
                }
            )
    return {"available": True, "base_url": base_url, "models": models, "error": None}


def probe_llm_provider(config: dict[str, Any] | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    config = config or {}
    env = env or os.environ
    provider = str(config.get("provider") or env.get("METIS_LLM_PROVIDER", "mock")).lower()
    if provider == "mock":
        return {"provider": "mock", "configured": True, "reachable": True, "model": "mock-governed", "error": None}
    if provider == "ollama":
        base_url = str(config.get("base_url") or env.get("METIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
        model = config.get("model") or env.get("METIS_OLLAMA_MODEL")
        models = list_ollama_models(base_url)
        available_names = [item["name"] for item in models["models"]]
        configured = bool(model)
        reachable = bool(models["available"])
        model_available = bool(model and model in available_names)
        error = models["error"]
        if reachable and not configured:
            error = "METIS_OLLAMA_MODEL or chat option model is required"
        elif reachable and configured and not model_available:
            error = f"Ollama model not found: {model}"
        return {
            "provider": "ollama",
            "configured": configured,
            "reachable": reachable,
            "model": model,
            "model_available": model_available,
            "base_url": base_url,
            "available_models": available_names,
            "error": error,
        }
    if provider == "openai":
        model = str(config.get("model") or env.get("METIS_OPENAI_MODEL", "gpt-4o-mini"))
        configured = bool(env.get("OPENAI_API_KEY"))
        return {
            "provider": "openai",
            "configured": configured,
            "reachable": None,
            "model": model,
            "error": None if configured else "OPENAI_API_KEY is required",
        }
    return {"provider": provider, "configured": False, "reachable": False, "model": None, "error": f"unsupported provider: {provider}"}


def governed_messages(
    user_message: str,
    state: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    retrieval_context: str | None = None,
) -> list[dict[str, str]]:
    history = history or []
    system = (
        "You are Metis Head's governed virtual chat router. "
        "Do not execute tools, hardware, BOH, Project Atlas, microphone, camera, or external actions. "
        f"Conversation depth is {state.get('conversation_depth_bucket')}. "
        f"Initiative is {state.get('initiative_bucket')}. "
        f"Interaction mode is {state.get('interaction_mode')}. "
    )
    if state.get("interaction_mode") == "agent":
        system += "In Agent Mode, provide proposals only and never claim execution. "
    if state.get("source_grounding_enabled"):
        if retrieval_context:
            system += "Source grounding is on; use the provided governed retrieval context and cite it. "
        else:
            system += "Source grounding is on, but no adequate retrieved source is available, so label unsupported claims as unsourced. "
    messages = [{"role": "system", "content": system}]
    if retrieval_context:
        messages.append({"role": "system", "content": retrieval_context})
    messages.extend(_clean_history(history))
    messages.append({"role": "user", "content": user_message})
    return messages


def _clean_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned = []
    for message in history[-12:]:
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            cleaned.append({"role": role, "content": content})
    return cleaned


def _last_user_text(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    all_headers = {"Content-Type": "application/json", **headers}
    req = request.Request(url, data=body, headers=all_headers, method="POST")
    try:
        with request.urlopen(req, timeout=45) as response:
            data = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMProviderError(f"HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise LLMProviderError(str(exc)) from exc
    return json.loads(data)


def _get_json(url: str) -> dict[str, Any]:
    req = request.Request(url, headers={"Content-Type": "application/json"}, method="GET")
    try:
        with request.urlopen(req, timeout=8) as response:
            data = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMProviderError(f"HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise LLMProviderError(str(exc)) from exc
    return json.loads(data)
