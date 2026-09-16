from __future__ import annotations

import importlib.util
import json
import os
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def build_startup_readiness(
    env: dict[str, str] | None = None,
    *,
    connection_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    env = os.environ if env is None else env
    checks: list[dict[str, Any]] = []

    def add(component: str, status: str, reason: str, remedy: str | None = None) -> None:
        item = {"component": component, "status": status, "reason": reason}
        if remedy:
            item["remedy"] = remedy
        checks.append(item)

    add("http", "available", "FastAPI application imports")
    multipart_ok = importlib.util.find_spec("multipart") is not None
    add(
        "browser_audio_upload",
        "available" if multipart_ok else "unavailable",
        "python-multipart installed" if multipart_ok else "python-multipart missing",
        None if multipart_ok else "pip install -e .",
    )

    stt_engine = str(env.get("METIS_STT_ENGINE") or "simulated").strip().lower()
    stt_model = str(env.get("METIS_STT_MODEL") or "small").strip()
    stt_model_dir = str(env.get("METIS_STT_MODEL_DIR") or "").strip()
    local_stt = _truthy(env.get("METIS_STT_ALLOW_LOCAL"))
    whisper_ok = importlib.util.find_spec("faster_whisper") is not None
    whisper_assets = _whisper_assets_present(stt_model, stt_model_dir)
    if stt_engine == "faster_whisper":
        if not local_stt:
            stt_status, stt_reason = "disabled", "faster_whisper is selected but METIS_STT_ALLOW_LOCAL is false"
        elif not whisper_ok:
            stt_status, stt_reason = "unavailable", "faster_whisper is selected and allowed but the dependency is missing"
        elif not stt_model:
            stt_status, stt_reason = "unavailable", "faster_whisper is selected but no model is configured"
        elif whisper_assets:
            stt_status, stt_reason = "available", f"faster_whisper is selected and allowed with model: {stt_model}"
        else:
            stt_status = "configured"
            stt_reason = (
                f"faster_whisper is selected and allowed with model {stt_model}, "
                "but local model assets were not confirmed; first load may require a download"
            )
    elif stt_engine == "simulated":
        stt_status, stt_reason = "fixture_only", "simulated STT is selected; it does not transcribe live speech"
    elif stt_engine == "none":
        stt_status, stt_reason = "disabled", "STT provider is explicitly disabled"
    else:
        stt_status, stt_reason = "unavailable", f"unsupported STT provider: {stt_engine}"
    add(
        "local_stt",
        stt_status,
        stt_reason,
        None if stt_status == "available" else "select faster_whisper, install .[stt-whisper], set its model, and explicitly allow local STT",
    )

    voice_enabled = _truthy(env.get("METIS_VOICE_ENABLED"))
    voice_provider = str(env.get("METIS_VOICE_PROVIDER") or "mock").strip().lower()
    allow_piper = _truthy(env.get("METIS_VOICE_ALLOW_PIPER"))
    allow_system = _truthy(env.get("METIS_VOICE_ALLOW_SYSTEM_TTS"))
    piper_exe = env.get("METIS_PIPER_EXE") or shutil.which("piper") or shutil.which("piper.exe")
    piper_model = env.get("METIS_PIPER_MODEL")
    piper_assets = bool(piper_exe and Path(piper_exe).is_file() and piper_model and Path(piper_model).is_file())
    if not voice_enabled:
        tts_status, tts_reason = "disabled", "voice output is disabled by METIS_VOICE_ENABLED"
    elif voice_provider == "piper":
        if not allow_piper:
            tts_status, tts_reason = "disabled", "Piper is selected but METIS_VOICE_ALLOW_PIPER is false"
        elif not piper_assets:
            tts_status, tts_reason = "unavailable", "Piper is selected and allowed but its executable/model is unavailable"
        else:
            tts_status, tts_reason = "available", "Piper is selected, explicitly allowed, and its executable/model were found"
    elif voice_provider == "system":
        if not allow_system:
            tts_status, tts_reason = "disabled", "system TTS is selected but METIS_VOICE_ALLOW_SYSTEM_TTS is false"
        elif os.name != "nt":
            tts_status, tts_reason = "unavailable", "system TTS is only implemented for Windows"
        else:
            tts_status, tts_reason = "available", "Windows system TTS is selected and explicitly allowed"
    elif voice_provider == "mock":
        tts_status, tts_reason = "fixture_only", "mock TTS is selected; it produces no audible speech"
    else:
        tts_status, tts_reason = "unavailable", f"unsupported TTS provider: {voice_provider}"
    add(
        "local_tts",
        tts_status,
        tts_reason,
        None if tts_status == "available" else "enable voice, select and allow Piper, and set METIS_PIPER_EXE and METIS_PIPER_MODEL",
    )

    google_accounts = [
        item for item in (connection_records or [])
        if item.get("provider") == "google" and item.get("status") == "connected"
    ]
    google_config = bool(google_accounts)
    add(
        "google",
        "configured" if google_config else "disabled",
        f"{len(google_accounts)} connected account(s) recorded" if google_config else "no connected Google account is recorded",
        None if google_config else "install .[google] and connect an account through the supported OAuth flow",
    )

    mcp_enabled = _truthy(env.get("METIS_MCP_ENABLED"))
    atlas_service_enabled = _truthy(env.get("METIS_MCP_ATLAS_ENABLED"))
    atlas_enabled = mcp_enabled and atlas_service_enabled
    atlas_command = bool(env.get("METIS_MCP_ATLAS_COMMAND"))
    atlas_status, atlas_reason = _mcp_readiness(
        global_enabled=mcp_enabled,
        service_enabled=atlas_service_enabled,
        command_configured=atlas_command,
        label="Atlas",
    )
    add(
        "project_atlas",
        atlas_status,
        atlas_reason,
        None if atlas_enabled and atlas_command else "configure the existing read-only Atlas MCP variables",
    )
    boh_service_enabled = _truthy(env.get("METIS_MCP_BOH_ENABLED"))
    boh_enabled = mcp_enabled and boh_service_enabled
    boh_command = bool(env.get("METIS_MCP_BOH_COMMAND"))
    boh_status, boh_reason = _mcp_readiness(
        global_enabled=mcp_enabled,
        service_enabled=boh_service_enabled,
        command_configured=boh_command,
        label="BOH",
    )
    add(
        "boh",
        boh_status,
        boh_reason,
        None if boh_enabled and boh_command else "configure the existing read-only BOH MCP variables",
    )
    add("mce", "disabled", "MCE is intentionally inactive and is not a startup dependency")

    paid_budget = env.get("METIS_PAID_BUDGET_USD")
    budget_valid = _valid_nonnegative_money(paid_budget)
    add(
        "paid_usage",
        "configured" if budget_valid else "disabled",
        "cumulative application budget configured" if budget_valid else "paid providers blocked until a valid cumulative budget is configured",
        None if budget_valid else "set METIS_PAID_BUDGET_USD to a finite non-negative amount before enabling paid providers",
    )
    llm_provider = str(env.get("METIS_LLM_PROVIDER") or "mock").strip().lower()
    llm_model = env.get("METIS_OLLAMA_MODEL") if llm_provider == "ollama" else env.get("METIS_OPENAI_MODEL")
    if llm_provider == "mock":
        llm_status, llm_reason, text_ready = "fixture_only", "mock provider is available for non-live testing", True
        llm_remedy = None
    elif llm_provider == "ollama":
        text_ready = bool(llm_model)
        llm_status, llm_reason = ("configured", f"local Ollama model selected: {llm_model}") if text_ready else ("unavailable", "METIS_OLLAMA_MODEL is not configured")
        llm_remedy = None if text_ready else "configure METIS_OLLAMA_MODEL"
    elif llm_provider == "openai":
        text_ready = False
        llm_status = "implemented_but_disabled"
        llm_reason = "OpenAI production dispatch remains guarded off; configuration alone does not enable it"
        llm_remedy = "use the supported local Ollama path until guarded OpenAI production composition is completed"
    else:
        llm_status, llm_reason, text_ready = "unavailable", f"unsupported provider: {llm_provider}", False
        llm_remedy = "configure a supported provider and model"
    add("language_model", llm_status, llm_reason, llm_remedy)
    browser_audio_ready = multipart_ok and stt_status == "available"
    return {
        "schema_version": "metis_startup_readiness.v1",
        "ready_for_text": text_ready,
        "ready_for_browser_audio": browser_audio_ready,
        "selected_llm_provider": llm_provider,
        "selected_stt_provider": stt_engine,
        "selected_tts_provider": voice_provider,
        "ready_for_spoken_browser_loop": browser_audio_ready and tts_status == "available",
        "checks": checks,
    }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _valid_nonnegative_money(value: str | None) -> bool:
    if value is None or not str(value).strip():
        return False
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return amount.is_finite() and amount >= 0


def _mcp_readiness(
    *,
    global_enabled: bool,
    service_enabled: bool,
    command_configured: bool,
    label: str,
) -> tuple[str, str]:
    if not global_enabled:
        return "disabled", f"{label} is disabled by the global METIS_MCP_ENABLED gate"
    if not service_enabled:
        return "disabled", f"{label} is disabled by its service gate"
    if not command_configured:
        return "unavailable", f"{label} is enabled but its MCP command is not configured"
    return "configured", f"{label} read-only MCP gates and command are configured"


def _whisper_assets_present(model: str, model_dir: str) -> bool:
    model_path = Path(model)
    if model_path.is_absolute() and model_path.is_dir() and (model_path / "model.bin").is_file():
        return True
    if not model_dir:
        return False
    root = Path(model_dir)
    if not root.is_dir():
        return False
    if (root / "model.bin").is_file():
        return True
    cache_root = root / f"models--Systran--faster-whisper-{model}"
    return any(cache_root.glob("snapshots/*/model.bin")) if cache_root.is_dir() else False


def main() -> None:
    print(json.dumps(build_startup_readiness(), indent=2))


if __name__ == "__main__":
    main()
