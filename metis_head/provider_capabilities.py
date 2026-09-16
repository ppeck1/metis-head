"""Truthful, JSON-safe provider choices for the setup experience.

This module describes what Metis can actually select.  It deliberately does
not probe providers or expose secrets; runtime health belongs to the existing
provider probes.  Capability gates that are not implemented default closed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "1"

AUTH_DOC_URL = "https://developers.openai.com/codex/auth/"
APP_SERVER_DOC_URL = "https://developers.openai.com/codex/app-server/"
API_PRICING_URL = "https://developers.openai.com/api/docs/pricing"
OLLAMA_API_URL = "https://github.com/ollama/ollama/blob/main/docs/api.md"

_PROVIDER_KEYS = {
    "id",
    "label",
    "selectable",
    "status",
    "implementation_status",
    "summary",
    "billing",
    "configuration",
    "limitations",
    "source_links",
}


def provider_capabilities(
    env: Mapping[str, str] | None = None,
    *,
    openai_dispatch_implemented: bool = False,
    codex_app_server_integrated: bool = False,
    codex_least_authority_guard_implemented: bool = False,
) -> dict[str, Any]:
    """Return the strict, JSON-serializable provider-choice contract.

    The implementation flags are intentionally explicit rather than inferred
    from imports.  A future integration point must affirm the relevant safety
    boundary before the setup API can present that provider as selectable.
    Credentials are only checked for presence and are never returned.
    """

    environment = os.environ if env is None else env
    openai_enabled = _is_true(environment.get("METIS_ENABLE_OPENAI_API"))
    openai_key_configured = bool(environment.get("OPENAI_API_KEY", "").strip())
    openai_model_configured = bool(environment.get("METIS_OPENAI_MODEL", "").strip())
    openai_selectable = bool(
        openai_dispatch_implemented
        and openai_enabled
        and openai_key_configured
        and openai_model_configured
    )
    codex_selectable = bool(
        codex_app_server_integrated and codex_least_authority_guard_implemented
    )

    providers = [
        _provider(
            provider_id="ollama",
            label="Ollama (local)",
            selectable=True,
            implementation_status="implemented",
            summary="Run supported chat models through a local Ollama service.",
            billing={
                "mode": "local_runtime",
                "notice": "Metis does not send Ollama requests to OpenAI or use ChatGPT plan credits.",
            },
            configuration={
                "required": ["model"],
                "optional": ["base_url"],
                "configured": None,
                "notice": "Reachability and installed-model checks are performed separately at runtime.",
            },
            limitations=[
                "A running Ollama service and an installed model are required.",
                "Model capability and resource requirements depend on the selected local model.",
            ],
            source_links=[{"title": "Ollama API documentation", "url": OLLAMA_API_URL}],
        ),
        _provider(
            provider_id="openai_api",
            label="OpenAI API (usage-based)",
            selectable=openai_selectable,
            implementation_status="implemented" if openai_dispatch_implemented else "not_implemented",
            summary="Use the ordinary OpenAI API with separate API credentials and usage-based billing.",
            billing={
                "mode": "usage_based_api",
                "notice": "OpenAI API usage is billed separately from a ChatGPT subscription; ChatGPT plan credits are not ordinary API credits.",
            },
            configuration={
                "required": ["explicit_enablement", "api_key", "model"],
                "optional": [],
                "configured": bool(openai_enabled and openai_key_configured and openai_model_configured),
                "notice": "The API key is checked only for presence and is never returned by this contract.",
            },
            limitations=_openai_limitations(
                dispatch_implemented=openai_dispatch_implemented,
                enabled=openai_enabled,
                key_configured=openai_key_configured,
                model_configured=openai_model_configured,
            ),
            source_links=[{"title": "OpenAI API pricing", "url": API_PRICING_URL}],
        ),
        _provider(
            provider_id="codex_app_server",
            label="Codex App Server (ChatGPT sign-in)",
            selectable=codex_selectable,
            implementation_status="implemented" if codex_app_server_integrated else "not_integrated",
            summary="Codex App Server supports ChatGPT-managed authentication, but Metis does not currently integrate it as a provider.",
            billing={
                "mode": "chatgpt_managed_auth",
                "notice": "Codex can use ChatGPT sign-in for subscription access; this is distinct from ordinary API-key billing and remains subject to account plan limits.",
            },
            configuration={
                "required": ["metis_app_server_integration", "least_authority_guard", "chatgpt_sign_in"],
                "optional": [],
                "configured": None,
                "notice": "Metis does not inspect or expose Codex authentication tokens through setup.",
            },
            limitations=_codex_limitations(
                integrated=codex_app_server_integrated,
                least_authority_guard=codex_least_authority_guard_implemented,
            ),
            source_links=[
                {"title": "Codex authentication", "url": AUTH_DOC_URL},
                {"title": "Codex App Server", "url": APP_SERVER_DOC_URL},
            ],
        ),
    ]
    assert all(set(provider) == _PROVIDER_KEYS for provider in providers)
    return {"schema_version": SCHEMA_VERSION, "providers": providers}


def _provider(
    *,
    provider_id: str,
    label: str,
    selectable: bool,
    implementation_status: str,
    summary: str,
    billing: dict[str, Any],
    configuration: dict[str, Any],
    limitations: list[str],
    source_links: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": provider_id,
        "label": label,
        "selectable": selectable,
        "status": "available" if selectable else "unavailable",
        "implementation_status": implementation_status,
        "summary": summary,
        "billing": billing,
        "configuration": configuration,
        "limitations": limitations,
        "source_links": source_links,
    }


def _openai_limitations(
    *, dispatch_implemented: bool, enabled: bool, key_configured: bool, model_configured: bool
) -> list[str]:
    limitations: list[str] = []
    if not dispatch_implemented:
        limitations.append("Metis OpenAI API dispatch is not implemented and no request will be sent.")
    if not enabled:
        limitations.append("Explicit OpenAI API enablement is required.")
    if not key_configured:
        limitations.append("An OpenAI API key is not configured.")
    if not model_configured:
        limitations.append("An OpenAI API model is not configured.")
    return limitations


def _codex_limitations(*, integrated: bool, least_authority_guard: bool) -> list[str]:
    limitations: list[str] = []
    if not integrated:
        limitations.append("Metis has not implemented a Codex App Server provider integration.")
    if not least_authority_guard:
        limitations.append(
            "Metis has not implemented the required least-authority guard for Codex agent capabilities."
        )
    return limitations


def _is_true(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})
