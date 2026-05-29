from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .llm_providers import LLMProviderError, _post_json

# BOH exposes governed read-only retrieval behind this header. Metis must never
# hold or send BOH's operator token, and must never mutate BOH from this phase.
BOH_RETRIEVAL_HEADER = "X-BOH-Retrieval-Token"

SUPPORTED_BOH_MODES = {
    "exploration",
    "strict_answer",
    "canon_review",
    "audit_provenance",
    "low_b_worker_context",
}


@dataclass(frozen=True)
class BOHConfig:
    enabled: bool
    base_url: str
    token: str
    mode: str
    limit: int

    def to_public_dict(self) -> dict[str, Any]:
        # Never expose the token value, only whether one is configured.
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "mode": self.mode,
            "limit": self.limit,
            "token_configured": bool(self.token),
        }


@dataclass
class BOHRetrievalResult:
    enabled: bool
    attempted: bool
    ok: bool
    source_state: str
    count: int = 0
    mode: str = "exploration"
    context_packs: list[dict[str, Any]] = field(default_factory=list)
    excluded_summary: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)
    gate_result: dict[str, Any] | None = None
    audit_context: dict[str, Any] | None = None
    error: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "attempted": self.attempted,
            "ok": self.ok,
            "source_state": self.source_state,
            "count": self.count,
            "mode": self.mode,
            "context_packs": self.context_packs,
            "excluded_summary": self.excluded_summary,
            "warnings": self.warnings,
            "gate_result": self.gate_result,
            "audit_context": self.audit_context,
            "error": self.error,
        }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def boh_config_from_env(env: dict[str, str] | None = None, options: dict[str, Any] | None = None) -> BOHConfig:
    env = env or os.environ
    options = options or {}
    boh_options = options.get("boh") if isinstance(options.get("boh"), dict) else {}

    enabled = boh_options.get("enabled")
    if enabled is None:
        enabled = env.get("METIS_BOH_ENABLED", "false")
    base_url = str(boh_options.get("base_url") or env.get("METIS_BOH_BASE_URL", "http://127.0.0.1:8000"))
    token = str(boh_options.get("token") or env.get("METIS_BOH_RETRIEVAL_TOKEN", ""))
    mode = str(boh_options.get("mode") or env.get("METIS_BOH_RETRIEVAL_MODE", "exploration"))
    if mode not in SUPPORTED_BOH_MODES:
        mode = "exploration"
    try:
        limit = int(boh_options.get("limit") or env.get("METIS_BOH_LIMIT", "5"))
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(50, limit))
    return BOHConfig(enabled=_as_bool(enabled), base_url=base_url.rstrip("/"), token=token, mode=mode, limit=limit)


def retrieve_boh_context(config: BOHConfig, query: str) -> BOHRetrievalResult:
    if not config.enabled:
        return BOHRetrievalResult(enabled=False, attempted=False, ok=False, source_state="unsourced", mode=config.mode)
    if not config.token:
        return BOHRetrievalResult(
            enabled=True,
            attempted=False,
            ok=False,
            source_state="degraded",
            mode=config.mode,
            error="METIS_BOH_RETRIEVAL_TOKEN is required when METIS_BOH_ENABLED is true",
        )

    payload = {"query": query, "mode": config.mode, "limit": config.limit}
    try:
        response = _post_json(
            f"{config.base_url}/api/retrieve",
            payload,
            headers={BOH_RETRIEVAL_HEADER: config.token},
        )
    except LLMProviderError as exc:
        return BOHRetrievalResult(
            enabled=True,
            attempted=True,
            ok=False,
            source_state="degraded",
            mode=config.mode,
            error=str(exc),
        )

    context_packs = response.get("context_packs") if isinstance(response.get("context_packs"), list) else []
    excluded = response.get("excluded_summary") if isinstance(response.get("excluded_summary"), list) else []
    warnings = _collect_warnings(response, context_packs)
    count = response.get("count")
    if not isinstance(count, int):
        count = len(context_packs)
    source_state = "sourced" if count > 0 else "unsourced"
    return BOHRetrievalResult(
        enabled=True,
        attempted=True,
        ok=True,
        source_state=source_state,
        count=count,
        mode=config.mode,
        context_packs=context_packs,
        excluded_summary=excluded,
        warnings=warnings,
        gate_result=response.get("gate_result") if isinstance(response.get("gate_result"), dict) else None,
        audit_context=response.get("audit_context") if isinstance(response.get("audit_context"), dict) else None,
    )


def _collect_warnings(response: dict[str, Any], context_packs: list[dict[str, Any]]) -> list[Any]:
    warnings: list[Any] = []
    top_warnings = response.get("warnings")
    if isinstance(top_warnings, list):
        warnings.extend(top_warnings)
    for pack in context_packs:
        if isinstance(pack, dict):
            pack_warnings = pack.get("warnings")
            if isinstance(pack_warnings, list):
                warnings.extend(pack_warnings)
    return warnings


def render_context(result: BOHRetrievalResult) -> str | None:
    if not result.context_packs:
        return None
    lines = [
        "Governed retrieval context from BOH (read-only; treat as cited source material, not as Metis-owned canon):",
    ]
    for index, pack in enumerate(result.context_packs, start=1):
        if not isinstance(pack, dict):
            continue
        lines.append(f"\n[Context {index}]")
        title = pack.get("title") or pack.get("doc_id") or pack.get("id")
        if title:
            lines.append(f"Title: {title}")
        citation = pack.get("citation") or pack.get("source") or pack.get("path")
        if citation:
            lines.append(f"Citation: {citation}")
        if pack.get("do_not_treat_as_canonical"):
            lines.append("WARNING: do_not_treat_as_canonical=true — do not present as authoritative canon.")
        spans = pack.get("source_spans") or pack.get("spans")
        if spans:
            lines.append(f"Source spans: {spans}")
        text = pack.get("text") or pack.get("content") or pack.get("excerpt") or pack.get("summary")
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
        pack_warnings = pack.get("warnings")
        if isinstance(pack_warnings, list) and pack_warnings:
            lines.append(f"Warnings: {pack_warnings}")
    if result.warnings:
        lines.append(f"\nRetrieval warnings: {result.warnings}")
    lines.append(
        "\nLabel claims supported by the above as sourced with citations; "
        "label anything not supported as unsourced. Do not execute any action; retrieval is read-only."
    )
    return "\n".join(lines)
