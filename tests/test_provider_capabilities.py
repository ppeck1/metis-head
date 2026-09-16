import json

from metis_head.provider_capabilities import provider_capabilities


PROVIDER_KEYS = {
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


def _by_id(result):
    return {provider["id"]: provider for provider in result["providers"]}


def test_contract_is_strict_json_safe_and_has_unique_provider_ids() -> None:
    result = provider_capabilities({})

    assert set(result) == {"schema_version", "providers"}
    assert result["schema_version"] == "1"
    assert all(set(provider) == PROVIDER_KEYS for provider in result["providers"])
    assert len({provider["id"] for provider in result["providers"]}) == len(result["providers"])
    json.dumps(result)


def test_ollama_is_the_only_selectable_provider_by_default() -> None:
    providers = _by_id(provider_capabilities({}))

    assert providers["ollama"]["selectable"] is True
    assert providers["ollama"]["status"] == "available"
    assert providers["openai_api"]["selectable"] is False
    assert providers["codex_app_server"]["selectable"] is False


def test_openai_key_alone_never_overclaims_implementation_or_exposes_secret() -> None:
    secret = "sk-test-do-not-return"
    result = provider_capabilities(
        {
            "OPENAI_API_KEY": secret,
            "METIS_OPENAI_MODEL": "test-model",
            "METIS_ENABLE_OPENAI_API": "true",
        }
    )
    provider = _by_id(result)["openai_api"]

    assert provider["selectable"] is False
    assert provider["implementation_status"] == "not_implemented"
    assert provider["configuration"]["configured"] is True
    assert secret not in json.dumps(result)
    assert "separately" in provider["billing"]["notice"]


def test_openai_requires_implementation_explicit_enablement_key_and_model() -> None:
    incomplete = provider_capabilities(
        {"OPENAI_API_KEY": "present", "METIS_OPENAI_MODEL": "test-model"},
        openai_dispatch_implemented=True,
    )
    complete = provider_capabilities(
        {
            "OPENAI_API_KEY": "present",
            "METIS_OPENAI_MODEL": "test-model",
            "METIS_ENABLE_OPENAI_API": "1",
        },
        openai_dispatch_implemented=True,
    )

    assert _by_id(incomplete)["openai_api"]["selectable"] is False
    assert _by_id(complete)["openai_api"]["selectable"] is True


def test_codex_app_server_requires_integration_and_least_authority_guard() -> None:
    integrated_only = provider_capabilities({}, codex_app_server_integrated=True)
    complete = provider_capabilities(
        {},
        codex_app_server_integrated=True,
        codex_least_authority_guard_implemented=True,
    )

    provider = _by_id(integrated_only)["codex_app_server"]
    assert provider["selectable"] is False
    assert any("least-authority" in limitation for limitation in provider["limitations"])
    assert _by_id(complete)["codex_app_server"]["selectable"] is True


def test_unavailable_providers_include_official_explanation_links() -> None:
    providers = _by_id(provider_capabilities({}))

    openai_urls = {item["url"] for item in providers["openai_api"]["source_links"]}
    codex_urls = {item["url"] for item in providers["codex_app_server"]["source_links"]}
    assert "https://developers.openai.com/api/docs/pricing" in openai_urls
    assert "https://developers.openai.com/codex/auth/" in codex_urls
    assert "https://developers.openai.com/codex/app-server/" in codex_urls
