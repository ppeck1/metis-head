from __future__ import annotations

from contextlib import asynccontextmanager
from hashlib import sha1
from pathlib import Path
import html
import re
import os
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from .artifacts import ArtifactError, list_artifacts, read_artifact, save_artifact
from .boh_link import (
    LINK_AUTH_FAILED,
    get_link_state,
    start_background_link,
    stop_background_link,
)
from .boh_retrieval import BOHRetrievalResult, boh_config_from_env, render_context, retrieve_boh_context
from .bridge import HARDWARE_PARITY_MANIFEST
from .execution_policy import read_only_execution_policy
from .governance import POLICY_VERSION, classify_intent, should_queue_proposal
from .leds import resolve_leds
from .panel import resolve_panel
from .llm_providers import LLMProviderError, LLMResult, governed_messages, list_ollama_models, probe_llm_provider, provider_from_config
from .mcp_chat_bridge import route_mcp_chat_read
from .personality import personality_profile
from .provider_harness import ProviderHarnessError, invoke_provider, provider_catalog
from .read_only_tools import ReadOnlyToolError, execute_filesystem_read, execute_git_status
from .readiness import calculate_readiness
from .reducer import clear_failures, reduce_metis_event, replay_events
from .scenarios import SCENARIOS, run_all_scenarios, run_scenario
from .schemas import FAILURE_TABLE, baseline_state, utc_now
from .sim_manifest import build_sim_test_manifest
from .tool_contract import build_tool_contract_manifest
from .tool_completion import calculate_tool_completion
from .tool_governance import evaluate_tool_request
from .tool_policy_snapshot import build_tool_policy_snapshot
from .tool_plan_runner import next_plan_action
from .tool_readiness import calculate_tool_readiness
from .tool_registry import ToolRegistryError, build_tool_proposal_event, dry_run_tool, execute_tool, get_tool, list_tools, route_tool_request
from .tool_task_planner import plan_tool_task
from .audio_input import CaptureContext, CaptureResult, LocalWakeWordDetector, audio_input_provider_from_config
from .stt import _local_stt_allowed, get_recognized_text, stt_provider_from_config
from .voice import VoiceResult, speak_text, stop_voice, voice_options, voice_profile
from .conversation import PersonalConversationCoordinator, SessionContext, SessionStore, TurnOrigin, TurnStage, TurnToken
from .audio import AUDIO_ARTIFACTS, PlaybackAck, PlaybackQueue, PlaybackState
from .startup_readiness import build_startup_readiness
from .credentials import CredentialStore
from .connectors import AtlasReadConnector, CalendarConnector, ContactsConnector, GmailConnector, GoogleReadBroker, transports_from_connections
from .model_adapters import build_local_ollama_adapter
from .orchestration import AccountGrant, AuthorizationContext, LoopLimits
from .personal_orchestration import atlas_registry_entries, google_broker_entries, run_google_broker_read
from .mcp_access import call_configured_mcp_tool
from .conversation_context import TrustedConversationContext, assemble_conversation_context, trusted_now
from .runtime_paths import connections_path
from .setup_state import SetupStateError, SetupStateStore
from .provider_capabilities import provider_capabilities
from .build_info import build_info
from .google_oauth_web import GoogleOAuthWebError, GoogleOAuthWebManager


@asynccontextmanager
async def _lifespan(_: FastAPI):
    start_background_link()
    try:
        yield
    finally:
        stop_background_link()


app = FastAPI(title="Metis Head Mock Brain", version="0.0.1", lifespan=_lifespan)
STATE = baseline_state()
SCENARIO_RESULTS: list[dict[str, Any]] = []
SESSIONS = SessionStore()
PLAYBACK = PlaybackQueue(SESSIONS.accepts)
ACTIVE_PERSONAL_COORDINATORS: dict[str, PersonalConversationCoordinator] = {}
GOOGLE_OAUTH_WEB = GoogleOAuthWebManager()
BROWSER_PTT_MAX_UPLOAD_BYTES = 1_000_000
BROWSER_PTT_ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/webm",
    "application/octet-stream",
}
BROWSER_PTT_WAV_TYPES = {"audio/wav", "audio/wave", "audio/x-wav", "application/octet-stream"}


@app.get("/")
def dashboard() -> FileResponse:
    return _static_file("dashboard.html")


def _static_file(name: str, *, media_type: str | None = None) -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "static" / name,
        media_type=media_type,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/static/voice_capture.js")
def voice_capture_script() -> FileResponse:
    return _static_file("voice_capture.js", media_type="application/javascript")


@app.get("/static/conversation_client.js")
def conversation_client_script() -> FileResponse:
    return _static_file("conversation_client.js", media_type="application/javascript")


@app.get("/setup")
def setup_page() -> FileResponse:
    return _static_file("setup.html")


@app.get("/static/audio_setup.js")
def audio_setup_script() -> FileResponse:
    return _static_file("audio_setup.js", media_type="application/javascript")


@app.get("/static/setup_wizard.js")
def setup_wizard_script() -> FileResponse:
    return _static_file("setup_wizard.js", media_type="application/javascript")


def _setup_store() -> SetupStateStore:
    return SetupStateStore()


@app.get("/metis/build")
def runtime_build() -> dict[str, object]:
    return build_info()


@app.get("/metis/setup")
def setup_status() -> dict[str, Any]:
    try:
        setup = _setup_store().public_view(include_account_ids=True)
    except SetupStateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "setup": setup,
        "providers": provider_capabilities(),
        "build": build_info(),
        "connections": google_accounts()["accounts"],
        "readiness": startup_readiness(),
        "llm_options": llm_options(setup["provider"].get("base_url")),
        "voice_options": voice_options(STATE),
    }


@app.patch("/metis/setup")
def update_setup(payload: dict[str, Any]) -> dict[str, Any]:
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else payload
    profile_updates = patch.get("google_profiles") if isinstance(patch, dict) else None
    provider_update = patch.get("provider") if isinstance(patch, dict) else None
    if isinstance(provider_update, dict) and provider_update.get("choice"):
        requested = str(provider_update["choice"])
        capability = next(
            (item for item in provider_capabilities()["providers"] if item["id"] == requested), None
        )
        if capability is None or not capability["selectable"]:
            raise HTTPException(status_code=400, detail="selected conversation provider is not available")
    if isinstance(profile_updates, dict):
        connected = {
            str(item.get("account_id")) for item in _google_store().list_connections()
            if item.get("provider") == "google" and item.get("status") == "connected"
        }
        for update in profile_updates.values():
            if isinstance(update, dict) and update.get("account_id") and str(update["account_id"]) not in connected:
                raise HTTPException(status_code=400, detail="profile identity must be a verified connected Google account")
    try:
        state = _setup_store().update(
            patch, expected_revision=payload.get("expected_revision") if "patch" in payload else None
        )
    except SetupStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"setup": state, "restart_required": False}


@app.get("/metis/setup/conversation-context")
def setup_conversation_context() -> dict[str, Any]:
    try:
        state = _setup_store().load()
    except SetupStateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    connected = [item for item in state["google_profiles"] if item.get("account_id")]
    return {
        "mode": "label_routed",
        "account_ids": [],
        "account_id": None,
        "calendars_by_account": {},
        "calendar_ids": [],
        "labels": {item["account_id"]: item["label"] for item in connected},
    }


def _profile_label_aliases(label: str) -> tuple[str, ...]:
    normalized = " ".join(re.findall(r"[a-z0-9]+", label.casefold()))
    aliases = {normalized} if normalized else set()
    aliases.update(part for part in normalized.split() if len(part) >= 3)
    return tuple(sorted(aliases, key=len, reverse=True))


@app.post("/metis/setup/resolve-profile")
def resolve_setup_profile(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message") or "").strip().casefold()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    state = _setup_store().load()
    profiles = [item for item in state["google_profiles"] if item.get("account_id")]
    matched = []
    for profile in profiles:
        aliases = _profile_label_aliases(str(profile["label"]))
        if any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", message) for alias in aliases):
            matched.append(profile)
    if not matched and len(profiles) == 1:
        matched = profiles
        status = "sole_profile"
    elif matched:
        status = "matched"
    elif profiles:
        status = "clarification_required"
    else:
        status = "no_profiles"
    account_ids = tuple(item["account_id"] for item in matched)
    calendars = {item["account_id"]: list(item.get("calendar_ids") or ()) for item in matched}
    _validate_persisted_google_selections(
        account_ids, {key: tuple(value) for key, value in calendars.items()}
    )
    return {
        "status": status,
        "explicit_match": status == "matched",
        "account_ids": list(account_ids),
        "account_id": account_ids[0] if len(account_ids) == 1 else None,
        "calendars_by_account": calendars,
        "calendar_ids": calendars.get(account_ids[0], []) if len(account_ids) == 1 else [],
        "matched_labels": [item["label"] for item in matched],
        "available_labels": [item["label"] for item in profiles],
    }


@app.get("/metis/startup/readiness")
def startup_readiness() -> dict[str, Any]:
    try:
        connections = _google_store().list_connections()
    except (OSError, ValueError):
        connections = []
    return build_startup_readiness(connection_records=connections)


@app.post("/metis/sessions")
def create_session(payload: dict[str, Any]) -> dict[str, Any]:
    client_id = str(payload.get("client_id") or "").strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    context_payload = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    account_id = _optional_session_value(context_payload.get("account_id"))
    calendar_ids = tuple(
        str(item) for item in context_payload.get("calendar_ids", ())
        if isinstance(item, str) and item.strip()
    ) if isinstance(context_payload.get("calendar_ids"), list) else ()
    account_ids = tuple(
        str(item).strip() for item in context_payload.get("account_ids", ())
        if isinstance(item, str) and item.strip()
    ) if isinstance(context_payload.get("account_ids"), list) else (() if account_id is None else (account_id,))
    if account_id is not None and account_ids and account_id not in account_ids:
        raise HTTPException(status_code=400, detail="primary account must be within selected accounts")
    raw_calendar_map = context_payload.get("calendars_by_account")
    calendars_by_account = {
        str(key).strip(): tuple(str(item).strip() for item in values if isinstance(item, str) and item.strip())
        for key, values in raw_calendar_map.items()
        if isinstance(key, str) and key.strip() and isinstance(values, list)
    } if isinstance(raw_calendar_map, dict) else ({account_id: calendar_ids} if account_id else {})
    _validate_persisted_google_selections(account_ids, calendars_by_account)
    try:
        snapshot = SESSIONS.create_session(
            client_id,
            context=SessionContext(
                account_id=account_id,
                project_id=_optional_session_value(context_payload.get("project_id")),
                timezone=_optional_session_value(context_payload.get("timezone")),
                calendar_ids=calendar_ids,
                account_ids=account_ids,
                calendars_by_account=tuple(calendars_by_account.items()),
            ),
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SESSIONS.safe_export(snapshot.session_id)


@app.get("/metis/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    try:
        return SESSIONS.safe_export(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/metis/sessions/{session_id}/context")
def update_session_context(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    account_id = _optional_session_value(payload.get("account_id")) if "account_id" in payload else None
    calendar_ids = payload.get("calendar_ids")
    if calendar_ids is not None and not isinstance(calendar_ids, list):
        raise HTTPException(status_code=400, detail="calendar_ids must be an array")
    account_ids_payload = payload.get("account_ids")
    if account_ids_payload is not None and not isinstance(account_ids_payload, list):
        raise HTTPException(status_code=400, detail="account_ids must be an array")
    calendars_map_payload = payload.get("calendars_by_account")
    if calendars_map_payload is not None and not isinstance(calendars_map_payload, dict):
        raise HTTPException(status_code=400, detail="calendars_by_account must be an object")
    try:
        prior = SESSIONS.snapshot(session_id).context
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    effective_account = account_id if "account_id" in payload else prior.account_id
    effective_calendars = (
        tuple(str(item).strip() for item in calendar_ids if isinstance(item, str) and item.strip())
        if calendar_ids is not None else prior.calendar_ids
    )
    effective_accounts = tuple(
        str(item).strip() for item in account_ids_payload if isinstance(item, str) and item.strip()
    ) if account_ids_payload is not None else prior.account_ids
    if not effective_accounts and effective_account:
        effective_accounts = (effective_account,)
    if effective_account is not None and effective_accounts and effective_account not in effective_accounts:
        raise HTTPException(status_code=400, detail="primary account must be within selected accounts")
    effective_calendar_map = (
        {
            str(key).strip(): tuple(str(item).strip() for item in values if isinstance(item, str) and item.strip())
            for key, values in calendars_map_payload.items()
            if isinstance(key, str) and key.strip() and isinstance(values, list)
        }
        if calendars_map_payload is not None
        else dict(prior.calendars_by_account)
    )
    if effective_account and (calendar_ids is not None or effective_account not in effective_calendar_map):
        effective_calendar_map[effective_account] = effective_calendars
    _validate_persisted_google_selections(effective_accounts, effective_calendar_map)
    try:
        updates: dict[str, Any] = {}
        if "account_id" in payload:
            updates["account_id"] = account_id
        if "project_id" in payload:
            updates["project_id"] = _optional_session_value(payload.get("project_id"))
        if "timezone" in payload:
            updates["timezone"] = _optional_session_value(payload.get("timezone"))
        if "calendar_ids" in payload:
            updates["calendar_ids"] = calendar_ids
        if "account_ids" in payload:
            updates["account_ids"] = account_ids_payload
        if "calendars_by_account" in payload:
            updates["calendars_by_account"] = effective_calendar_map
        snapshot = SESSIONS.update_context(session_id, **updates)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 400, detail=str(exc)) from exc
    return SESSIONS.safe_export(snapshot.session_id)


@app.post("/metis/sessions/{session_id}/cancel")
def cancel_session(session_id: str) -> dict[str, Any]:
    coordinator = ACTIVE_PERSONAL_COORDINATORS.pop(session_id, None)
    if coordinator is not None:
        coordinator.cancel_session(session_id)
    try:
        generation = SESSIONS.cancel(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    cancelled = PLAYBACK.cancel_session(session_id, through_generation=generation - 1)
    return {"status": "cancelled", "generation": generation, "playback_cancelled": list(cancelled)}


@app.delete("/metis/sessions/{session_id}")
def close_session(session_id: str) -> dict[str, Any]:
    coordinator = ACTIVE_PERSONAL_COORDINATORS.pop(session_id, None)
    if coordinator is not None:
        coordinator.cancel_session(session_id)
    try:
        SESSIONS.close_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    PLAYBACK.cancel_session(session_id)
    return {"status": "closed", "session_id": session_id}


def _optional_session_value(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _validate_persisted_google_selection(account_id: str | None, calendar_ids: tuple[str, ...]) -> None:
    if calendar_ids and not account_id:
        raise HTTPException(status_code=400, detail="calendar selection requires a connected Google account")
    if not account_id:
        return
    record = next(
        (
            item for item in _google_store().list_connections()
            if item.get("provider") == "google"
            and item.get("status") == "connected"
            and item.get("account_id") == account_id
        ),
        None,
    )
    if record is None:
        raise HTTPException(status_code=400, detail="selected Google account is not connected")
    selected = {str(item) for item in record.get("selected_calendar_ids", ())}
    if any(item not in selected for item in calendar_ids):
        raise HTTPException(status_code=400, detail="session calendars must be within the persisted selection")


def _validate_persisted_google_selections(
    account_ids: tuple[str, ...], calendars_by_account: dict[str, tuple[str, ...]]
) -> None:
    if len(set(account_ids)) != len(account_ids):
        raise HTTPException(status_code=400, detail="selected Google accounts must be unique")
    if any(account not in account_ids for account in calendars_by_account):
        raise HTTPException(status_code=400, detail="calendar selections must be keyed by a selected Google account")
    for account in account_ids:
        _validate_persisted_google_selection(account, calendars_by_account.get(account, ()))


def _session_turn(payload: dict[str, Any], user_message: str, options: dict[str, Any]) -> TurnToken | None:
    existing = payload.get("_turn_token")
    if isinstance(existing, TurnToken):
        if not SESSIONS.accepts(existing):
            raise HTTPException(status_code=409, detail="turn was cancelled or expired")
        return existing
    session_id = _optional_session_value(payload.get("session_id") or options.get("session_id"))
    if session_id is None:
        return None
    origin = TurnOrigin.VOICE if options.get("_metis_voice_origin") else TurnOrigin.TEXT
    try:
        return SESSIONS.begin_turn(session_id, origin=origin, user_text=user_message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _private_history_for(token: TurnToken | None) -> list[dict[str, str]] | None:
    if token is None:
        return None
    return [
        {"role": item.role, "content": item.text}
        for item in SESSIONS.private_history(token.session_id)
        if item.turn_id != token.turn_id and item.role in {"user", "assistant"}
    ]


def _google_store() -> CredentialStore:
    return CredentialStore(connections_path())


def _google_connectors() -> tuple[CalendarConnector, GmailConnector, ContactsConnector]:
    transports = transports_from_connections(_google_store())
    return CalendarConnector(transports), GmailConnector(transports), ContactsConnector(transports)


def _google_read_broker() -> GoogleReadBroker:
    store = _google_store()
    return GoogleReadBroker.restore_from_credential_store(store).broker


def _personal_tool_entries(broker: GoogleReadBroker) -> dict[str, Any]:
    entries = dict(google_broker_entries(broker))
    atlas = AtlasReadConnector(
        lambda tool_name, arguments: call_configured_mcp_tool("project_atlas", tool_name, dict(arguments))
    )
    entries.update(atlas_registry_entries(atlas))
    return entries


def _build_personal_coordinator(
    options: dict[str, Any],
    broker: GoogleReadBroker | None = None,
    *,
    selected_account_id: str | None = None,
    selected_account_ids: tuple[str, ...] = (),
) -> PersonalConversationCoordinator:
    model = str(options.get("model") or os.environ.get("METIS_OLLAMA_MODEL") or "").strip()
    if not model:
        raise LLMProviderError("METIS_OLLAMA_MODEL or chat option model is required")
    base_url = str(options.get("base_url") or os.environ.get("METIS_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    broker = broker or _google_read_broker()
    authorized_ids = frozenset(selected_account_ids or (() if selected_account_id is None else (selected_account_id,)))
    accounts = {
        account.account_id: AccountGrant(account.account_id, frozenset(account.scopes))
        for account in broker.accounts()
        if account.account_id in authorized_ids
    }
    try:
        timeout_seconds = float(
            options.get("request_timeout_seconds")
            or os.environ.get("METIS_OLLAMA_TIMEOUT_SECONDS")
            or 120
        )
    except (TypeError, ValueError):
        timeout_seconds = 120.0
    # Local models can need a long first-token warm-up, especially after a model
    # switch. Keep the conversation bounded while avoiding a false failure at
    # the old 30-second default.
    timeout_seconds = max(10.0, min(timeout_seconds, 600.0))
    return PersonalConversationCoordinator(
        entries=_personal_tool_entries(broker),
        authorization=AuthorizationContext(accounts=accounts),
        adapter_factory=lambda cancellation: build_local_ollama_adapter(
            model=model,
            base_url=base_url,
            cancellation=cancellation,
            max_output_tokens=int(options.get("max_output_tokens") or 512),
            request_timeout_seconds=timeout_seconds,
        ),
        limits=LoopLimits(
            max_rounds=4,
            max_tool_calls=6,
            max_calls_per_round=3,
            max_total_seconds=timeout_seconds,
        ),
    )


def _run_personal_ollama_turn(
    token: TurnToken,
    options: dict[str, Any],
    *,
    broker: GoogleReadBroker,
    system_instructions: str,
    conversation: list[dict[str, str]],
) -> LLMResult:
    session_context = SESSIONS.snapshot(token.session_id).context
    available_accounts = tuple(account.account_id for account in broker.accounts())
    selected_account = session_context.account_id
    selected_accounts = session_context.account_ids
    if selected_account is None and len(available_accounts) == 1:
        selected_account = available_accounts[0]
        selected_accounts = (selected_account,)
    if len(selected_accounts) > 1:
        coordinator = _build_personal_coordinator(
            options, broker, selected_account_id=selected_account, selected_account_ids=selected_accounts
        )
    else:
        coordinator = _build_personal_coordinator(options, broker, selected_account_id=selected_account)
    ACTIVE_PERSONAL_COORDINATORS[token.session_id] = coordinator
    try:
        outcome = coordinator.run_turn(
            session_id=token.session_id,
            turn_id=token.turn_id,
            conversation=conversation,
            system_instructions=system_instructions,
            preflight=lambda: SESSIONS.accepts(token),
        )
    finally:
        if ACTIVE_PERSONAL_COORDINATORS.get(token.session_id) is coordinator:
            ACTIVE_PERSONAL_COORDINATORS.pop(token.session_id, None)
    if outcome.stop_reason != "completed" or not outcome.text:
        raise LLMProviderError(f"tool-enabled Ollama conversation stopped: {outcome.stop_reason}")
    return LLMResult(
        text=outcome.text,
        provider="ollama",
        model=str(options.get("model") or os.environ.get("METIS_OLLAMA_MODEL")),
        metadata={
            "tool_orchestration": True,
            "rounds": outcome.rounds,
            "tool_calls": len(outcome.exchanges),
            "sources": [source.source_id for exchange in outcome.exchanges for source in exchange.result.provenance],
        },
    )


def _trusted_conversation_context(
    token: TurnToken | None,
    options: dict[str, Any],
    broker: GoogleReadBroker,
) -> TrustedConversationContext:
    timezone_name = str(options.get("timezone") or os.environ.get("METIS_TIMEZONE") or "America/New_York")
    selected_account: str | None = None
    selected_project: str | None = None
    selected_calendars: tuple[str, ...] = ()
    selected_accounts: tuple[str, ...] = ()
    selected_calendar_map: tuple[tuple[str, tuple[str, ...]], ...] = ()
    if token is not None:
        context = SESSIONS.snapshot(token.session_id).context
        selected_account = context.account_id
        selected_project = context.project_id
        selected_calendars = tuple(getattr(context, "calendar_ids", ()) or ())
        selected_accounts = tuple(getattr(context, "account_ids", ()) or ())
        selected_calendar_map = tuple(getattr(context, "calendars_by_account", ()) or ())
        timezone_name = str(getattr(context, "timezone", None) or timezone_name)
    accounts = tuple(account.account_id for account in broker.accounts())
    if token is None:
        if options.get("account_id"):
            selected_account = str(options["account_id"])
        if isinstance(options.get("calendar_ids"), list):
            selected_calendars = tuple(str(item) for item in options["calendar_ids"] if str(item).strip())
    elif selected_account is None and len(accounts) == 1:
        selected_account = accounts[0]
        selected_calendars = broker.selected_calendar_ids(selected_account)
        selected_accounts = (selected_account,)
        selected_calendar_map = ((selected_account, selected_calendars),)
    entries = _personal_tool_entries(broker)
    try:
        profile_labels = tuple(
            str(item["label"])
            for item in _setup_store().load()["google_profiles"]
            if item.get("account_id")
        )
    except SetupStateError:
        profile_labels = ()
    return TrustedConversationContext(
        now=trusted_now(timezone_name),
        timezone_name=timezone_name,
        selected_account_id=selected_account,
        selected_calendar_ids=selected_calendars,
        selected_project_id=selected_project,
        available_accounts=accounts,
        allowed_tools=tuple(sorted(entries)),
        selected_account_ids=selected_accounts,
        selected_calendars_by_account=selected_calendar_map,
        profile_labels=profile_labels,
    )


@app.get("/metis/connectors/google/accounts")
def google_accounts() -> dict[str, Any]:
    accounts = [
        {
            "account_id": item["account_id"],
            "scopes": item["scopes"],
            "status": item["status"],
            "selected_calendar_ids": item.get("selected_calendar_ids", []),
            "calendar_grant_restricted": item.get("allowed_calendar_ids") is not None,
        }
        for item in _google_store().list_connections()
        if item.get("provider") == "google"
    ]
    return {"provider": "google", "accounts": accounts, "count": len(accounts)}


@app.post("/metis/connectors/google/oauth/start")
async def google_oauth_start(
    request: Request,
    client_secrets: UploadFile | None = File(None),
) -> dict[str, Any]:
    """Start a local, read-only Google OAuth flow without persisting client JSON."""
    if client_secrets is not None:
        raw = await client_secrets.read(65_537)
        if len(raw) > 65_536:
            raise HTTPException(status_code=413, detail="OAuth client JSON exceeds the 64 KiB limit")
        try:
            config = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="OAuth client file is not valid JSON") from exc
    else:
        configured_path = os.environ.get("METIS_GOOGLE_CLIENT_SECRETS", "").strip()
        if not configured_path:
            raise HTTPException(
                status_code=400,
                detail="Choose your Google desktop OAuth client JSON, then click Connect Google account",
            )
        try:
            config = json.loads(Path(configured_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="configured Google OAuth client JSON is unavailable") from exc
    callback = str(request.url_for("google_oauth_callback"))
    parsed = urlparse(callback)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=400, detail="Google OAuth callback must remain on loopback")
    try:
        started = GOOGLE_OAUTH_WEB.start(config, redirect_uri=callback)
    except GoogleOAuthWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "authorization_required", **started, "client_config_persisted": False}


@app.get("/metis/connectors/google/oauth/callback", name="google_oauth_callback")
def google_oauth_callback(request: Request, state: str = "", error: str = "") -> HTMLResponse:
    if error:
        return HTMLResponse(
            "<h1>Google connection was not completed</h1><p>You can close this window and retry in Metis.</p>",
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    try:
        result = GOOGLE_OAUTH_WEB.complete(
            state=state,
            authorization_response=str(request.url),
            store=_google_store(),
        )
    except (GoogleOAuthWebError, RuntimeError) as exc:
        return HTMLResponse(
            f"<h1>Google connection failed</h1><p>{html.escape(str(exc))}</p><p>Close this window and retry in Metis.</p>",
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    duplicate = " The existing connection was refreshed." if result["duplicate_identity"] else ""
    return HTMLResponse(
        "<h1>Google account connected</h1>"
        f"<p>The verified identity was connected with read-only grants.{duplicate}</p>"
        "<p>You may close this window and return to Metis.</p>"
        "<script>if(window.opener){window.opener.postMessage('metis-google-connected', window.location.origin);}window.close();</script>",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/metis/connectors/google/selection")
def google_selection(payload: dict[str, Any]) -> dict[str, Any]:
    account_id = str(payload.get("account_id") or "").strip()
    calendar_ids = payload.get("calendar_ids")
    if not account_id or not isinstance(calendar_ids, list):
        raise HTTPException(status_code=400, detail="account_id and calendar_ids are required")
    try:
        record = _google_store().update_google_selection(account_id, calendar_ids)
        session_id = _optional_session_value(payload.get("session_id"))
        if session_id:
            SESSIONS.update_context(session_id, account_id=account_id, calendar_ids=record.selected_calendar_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "selected",
        "account_id": record.account_id,
        "calendar_ids": list(record.selected_calendar_ids),
        "session_id": _optional_session_value(payload.get("session_id")),
    }


@app.delete("/metis/connectors/google/accounts/{account_id}")
def disconnect_google_account(account_id: str) -> dict[str, Any]:
    from .credentials import SecretStoreUnavailable

    connection_id = f"google:{account_id.strip()}"
    try:
        _google_store().disconnect(connection_id)
    except SecretStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "disconnected", "account_id": account_id.strip()}


@app.post("/metis/connectors/google/calendar/events")
def google_calendar_events(payload: dict[str, Any]) -> Any:
    try:
        start = datetime.fromisoformat(str(payload.get("start") or "").replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(payload.get("end") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="start and end must be ISO-8601 datetimes") from exc
    return _google_read_broker().calendar_events(
        account_id=str(payload.get("account_id") or ""),
        calendar_ids=payload.get("calendar_ids") if isinstance(payload.get("calendar_ids"), list) else ["primary"],
        start=start,
        end=end,
        timezone=str(payload.get("timezone") or "America/New_York"),
        max_events=min(500, max(1, int(payload.get("max_events") or 100))),
    )


@app.post("/metis/connectors/google/calendars")
def google_calendars(payload: dict[str, Any]) -> Any:
    return _google_read_broker().list_calendars(
        account_id=str(payload.get("account_id") or ""),
        max_calendars=min(250, max(1, int(payload.get("max_calendars") or 100))),
        max_pages=min(50, max(1, int(payload.get("max_pages") or 10))),
    )


@app.post("/metis/connectors/google/gmail/search")
def google_gmail_search(payload: dict[str, Any]) -> Any:
    return _google_read_broker().gmail_search(
        account_id=str(payload.get("account_id") or ""),
        query=str(payload.get("query") or ""),
        max_messages=min(100, max(1, int(payload.get("max_messages") or 25))),
    )


@app.post("/metis/connectors/google/gmail/messages/{message_id}")
def google_gmail_message(message_id: str, payload: dict[str, Any]) -> Any:
    return _google_read_broker().gmail_message(account_id=str(payload.get("account_id") or ""), message_id=message_id)


@app.post("/metis/connectors/google/gmail/threads/{thread_id}")
def google_gmail_thread(thread_id: str, payload: dict[str, Any]) -> Any:
    return _google_read_broker().gmail_thread(
        account_id=str(payload.get("account_id") or ""),
        thread_id=thread_id,
        max_messages=min(20, max(1, int(payload.get("max_messages") or 20))),
    )


@app.post("/metis/connectors/google/contacts/lookup")
def google_contact_lookup(payload: dict[str, Any]) -> Any:
    return _google_read_broker().contact_email(
        account_id=str(payload.get("account_id") or ""),
        query=str(payload.get("query") or ""),
        max_contacts=min(100, max(1, int(payload.get("max_contacts") or 20))),
    )


@app.post("/metis/orchestration/google/read")
def orchestrate_google_read(payload: dict[str, Any]) -> Any:
    account_id = str(payload.get("account_id") or "").strip()
    tool_name = str(payload.get("tool_name") or "").strip()
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    if not account_id or not tool_name:
        raise HTTPException(status_code=400, detail="account_id and tool_name are required")
    return run_google_broker_read(
        session_id=str(payload.get("session_id") or "api-session"),
        turn_id=str(payload.get("turn_id") or "api-turn"),
        tool_name=tool_name,
        arguments=arguments,
        account_id=account_id,
        broker=_google_read_broker(),
    )


@app.get("/metis/personality/console")
def personality_console() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "personality_console.html")


@app.get("/metis/personality")
def personality(mode: str | None = None) -> dict[str, Any]:
    if mode is None:
        mode = "agent" if STATE.get("interaction_mode") == "agent" else "counsel"
    return personality_profile(mode)


@app.get("/metis/boh/status")
def boh_status() -> dict[str, Any]:
    return get_link_state().to_dict()



@app.get("/metis/control_center")
def control_center_status() -> dict[str, Any]:
    from .control_center import build_control_center_status
    from .mcp_access import mcp_status

    return build_control_center_status(STATE, mcp_status(), get_link_state().to_dict())


def _payload_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


@app.post("/metis/control_center/toggles")
def control_center_toggle(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    from .control_center import CONTROL_CENTER_CONTROLS, build_control_center_status
    from .mcp_access import mcp_status

    payload = payload or {}
    control = str(payload.get("control") or "")
    if control not in CONTROL_CENTER_CONTROLS:
        raise HTTPException(status_code=400, detail="unknown control-center toggle")
    enabled = _payload_bool(payload.get("enabled"))
    mode = "read" if enabled else "off"
    event = {
        "type": "tool_control_toggle",
        "control": control,
        "enabled": enabled,
        "mode": mode,
        "toggled_at": utc_now(),
    }
    STATE = reduce_metis_event(STATE, event)
    return {
        "status": "control_center_updated",
        "event": event,
        "state": STATE,
        "leds": resolve_leds(STATE),
        "control_center": build_control_center_status(STATE, mcp_status(), get_link_state().to_dict()),
    }


@app.post("/metis/control_center/modes")
def control_center_mode(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    from .control_center import CONTROL_CENTER_CONTROLS, CONTROL_CENTER_MODES, build_control_center_status
    from .mcp_access import mcp_status

    payload = payload or {}
    control = str(payload.get("control") or "")
    mode = str(payload.get("mode") or "")
    if control not in CONTROL_CENTER_CONTROLS:
        raise HTTPException(status_code=400, detail="unknown control-center mode control")
    if mode not in CONTROL_CENTER_MODES:
        raise HTTPException(status_code=400, detail="unknown control-center mode")
    event = {
        "type": "tool_control_toggle",
        "control": control,
        "enabled": mode != "off",
        "mode": mode,
        "toggled_at": utc_now(),
    }
    STATE = reduce_metis_event(STATE, event)
    return {
        "status": "control_center_mode_updated",
        "event": event,
        "state": STATE,
        "leds": resolve_leds(STATE),
        "control_center": build_control_center_status(STATE, mcp_status(), get_link_state().to_dict()),
    }

@app.get("/metis/state")
def get_state() -> dict[str, Any]:
    return {"state": STATE, "leds": resolve_leds(STATE), "readiness": calculate_readiness()}


@app.get("/metis/panel")
def get_panel() -> dict[str, Any]:
    return {"panel": resolve_panel(STATE), "state": STATE, "leds": resolve_leds(STATE)}


@app.get("/metis/export")
def export_state() -> dict[str, Any]:
    return {
        "state": STATE,
        "leds": resolve_leds(STATE),
        "readiness": calculate_readiness(),
        "event_log": STATE.get("event_log", []),
        "export_schema": "metis_export.v0.1",
    }


def _export_payload() -> dict[str, Any]:
    return {
        "state": STATE,
        "leds": resolve_leds(STATE),
        "readiness": calculate_readiness(),
        "event_log": STATE.get("event_log", []),
        "export_schema": "metis_export.v0.1",
    }


@app.post("/metis/artifacts/save")
def artifacts_save(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    artifact_type = str(payload.get("artifact_type") or "export")
    label = payload.get("label")
    try:
        if artifact_type == "export":
            artifact_payload = _export_payload()
        elif artifact_type == "manifest":
            artifact_payload = build_sim_test_manifest(include_results=bool(payload.get("include_results", True)))
        else:
            raise ArtifactError(f"unsupported artifact type: {artifact_type}")
        return save_artifact(artifact_payload, artifact_type, str(label) if label is not None else None)
    except ArtifactError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/metis/artifacts")
def artifacts_list() -> dict[str, Any]:
    return {"artifact_schema": "metis_artifact.v0.1", "artifacts": list_artifacts()}


@app.get("/metis/artifacts/{filename}")
def artifacts_get(filename: str) -> dict[str, Any]:
    try:
        return read_artifact(filename)
    except ArtifactError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/metis/sim/manifest")
def sim_manifest(include_results: bool = True) -> dict[str, Any]:
    return build_sim_test_manifest(include_results=include_results)


@app.get("/metis/sim/tests")
def sim_tests(include_results: bool = True) -> dict[str, Any]:
    return build_sim_test_manifest(include_results=include_results)


@app.get("/metis/proposals")
def proposals(status: str | None = None, proposal_type: str | None = None, tool_id: str | None = None) -> dict[str, Any]:
    queue = list(STATE.get("approval_queue", []))
    filtered = queue
    if status:
        filtered = [proposal for proposal in filtered if proposal.get("review_status") == status or proposal.get("status") == status]
    if proposal_type:
        filtered = [proposal for proposal in filtered if proposal.get("proposal_type") == proposal_type]
    if tool_id:
        filtered = [proposal for proposal in filtered if proposal.get("tool_id") == tool_id]
    return {
        "proposals": filtered,
        "pending_approval_count": STATE.get("pending_approval_count", 0),
        "total_count": len(queue),
        "filtered_count": len(filtered),
        "filters": {"status": status or "", "proposal_type": proposal_type or "", "tool_id": tool_id or ""},
    }


@app.get("/metis/tools/plans")
def tool_plans(status: str | None = None) -> dict[str, Any]:
    plans = list(STATE.get("tool_plan_queue", []))
    filtered = plans
    if status:
        filtered = [plan for plan in filtered if plan.get("review_status") == status or plan.get("status") == status]
    return {
        "plans": filtered,
        "total_count": len(plans),
        "filtered_count": len(filtered),
        "filters": {"status": status or ""},
    }


def _tool_plan_by_id(plan_id: str) -> dict[str, Any] | None:
    for plan in STATE.get("tool_plan_queue", []):
        if plan.get("plan_id") == plan_id:
            return plan
    return None


@app.get("/metis/tools/plans/{plan_id}")
def tool_plan_detail(plan_id: str) -> dict[str, Any]:
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    return {"plan": plan}


def _review_tool_plan(plan_id: str, decision: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status", "pending") != "pending":
        raise HTTPException(status_code=409, detail="tool plan already reviewed")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    event = {
        "type": "tool_plan_review",
        "plan_id": plan_id,
        "decision": decision,
        "reason": reason,
        "reviewed_at": utc_now(),
    }
    STATE = reduce_metis_event(STATE, event)
    reviewed = _tool_plan_by_id(plan_id)
    return {
        "status": f"tool_plan_{decision}",
        "plan": reviewed,
        "review_receipt": reviewed.get("review_receipt") if reviewed else None,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/tools/plans/{plan_id}/approve")
def approve_tool_plan(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_tool_plan(plan_id, "approved", payload)


@app.post("/metis/tools/plans/{plan_id}/deny")
def deny_tool_plan(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_tool_plan(plan_id, "denied", payload)


def _plan_step_queue_candidates(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "")
        tool_id = step.get("tool_id")
        if not tool_id:
            skipped.append({"step_id": step_id, "reason": "no_tool"})
        elif step.get("proposal_id"):
            skipped.append({"step_id": step_id, "tool_id": tool_id, "reason": "already_queued"})
        elif step.get("status") in {"blocked_no_tool", "blocked_invalid_arguments"}:
            skipped.append({"step_id": step_id, "tool_id": tool_id, "reason": step.get("status")})
        else:
            candidates.append(step)
    return candidates, skipped


@app.post("/metis/tools/plans/{plan_id}/queue_steps")
def queue_tool_plan_steps(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status") != "approved":
        raise HTTPException(status_code=409, detail="tool plan must be approved before steps can be queued")
    candidates, skipped = _plan_step_queue_candidates(plan)
    queued_steps: list[dict[str, Any]] = []
    queued_proposals: list[dict[str, Any]] = []
    reason_prefix = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str) and payload["reason"].strip():
        reason_prefix = f"{payload['reason'].strip()}; "
    try:
        for step in candidates:
            tool_id = str(step["tool_id"])
            reason = f"{reason_prefix}plan {plan_id} {step.get('step_id')}: {step.get('reason', 'planned tool step')}"
            queued = _queue_tool_proposal(tool_id, step.get("arguments") or {}, reason)
            proposal = queued.get("proposal") or {}
            queued_steps.append({"step_id": step.get("step_id"), "tool_id": tool_id, "proposal_id": proposal.get("proposal_id")})
            queued_proposals.append(proposal)
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if queued_steps:
        event = {"type": "tool_plan_step_queue", "plan_id": plan_id, "queued_steps": queued_steps, "queued_at": utc_now()}
        STATE = reduce_metis_event(STATE, event)
    else:
        event = None
    reviewed_plan = _tool_plan_by_id(plan_id)
    return {
        "status": "plan_step_proposals_queued" if queued_steps else "no_plan_steps_queued",
        "plan": reviewed_plan,
        "queued_steps": queued_steps,
        "queued_proposals": queued_proposals,
        "skipped_steps": skipped,
        "event": event,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/tools/plans/{plan_id}/request_execution")
def request_tool_plan_execution(plan_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status") != "approved":
        raise HTTPException(status_code=409, detail="tool plan must be approved before execution can be requested")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    executed_steps: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    skipped_steps: list[dict[str, Any]] = []
    try:
        for step in plan.get("steps", []):
            if not isinstance(step, dict):
                continue
            proposal_id = step.get("proposal_id")
            if not proposal_id:
                skipped_steps.append({"step_id": step.get("step_id"), "reason": "no_proposal"})
                continue
            if step.get("execution_receipt_id"):
                skipped_steps.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "already_requested"})
                continue
            proposal = _proposal_by_id(str(proposal_id))
            if proposal is None:
                skipped_steps.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "proposal_missing"})
                continue
            if proposal.get("review_status") != "approved":
                skipped_steps.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "proposal_not_approved"})
                continue
            event = _execution_request_event_for_proposal(proposal, reason or f"plan {plan_id} {step.get('step_id')}")
            STATE = reduce_metis_event(STATE, event)
            receipt = STATE.get("execution_audit_log", [])[-1]
            receipts.append(receipt)
            executed_steps.append(
                {
                    "step_id": step.get("step_id"),
                    "proposal_id": proposal_id,
                    "receipt_id": receipt.get("receipt_id"),
                    "execution_status": receipt.get("execution_status"),
                }
            )
    except (ToolRegistryError, ReadOnlyToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if executed_steps:
        plan_event = {"type": "tool_plan_execution_request", "plan_id": plan_id, "executed_steps": executed_steps, "requested_at": utc_now()}
        STATE = reduce_metis_event(STATE, plan_event)
    else:
        plan_event = None
    return {
        "status": "plan_execution_requested" if executed_steps else "no_plan_execution_requested",
        "plan": _tool_plan_by_id(plan_id),
        "executed_steps": executed_steps,
        "receipts": receipts,
        "skipped_steps": skipped_steps,
        "event": plan_event,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


def _receipt_for_step(step: dict[str, Any]) -> dict[str, Any] | None:
    receipt_id = step.get("execution_receipt_id")
    if receipt_id:
        return _receipt_by_id(str(receipt_id))
    proposal_id = step.get("proposal_id")
    if not proposal_id:
        return None
    for receipt in reversed(STATE.get("execution_audit_log", [])):
        if receipt.get("proposal_id") == proposal_id:
            return receipt
    return None


def _binding_text_from_receipt(receipt: dict[str, Any]) -> str:
    summary = receipt.get("output_summary") if isinstance(receipt.get("output_summary"), dict) else {}
    preview = summary.get("preview") if isinstance(summary.get("preview"), dict) else {}
    preview_items: list[str] = []
    for key in sorted(preview):
        value = str(preview[key])
        preview_items.append(f"{key}: {value[:180]}")
    text = "; ".join(preview_items)
    return (
        f"Governed receipt summary from {receipt.get('tool_id')} "
        f"({receipt.get('receipt_id')}, hash {receipt.get('output_hash', 'none')}): {text}"
    )[:900]


def _plan_result_bindings(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bindings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    source_step: dict[str, Any] | None = None
    source_receipt: dict[str, Any] | None = None
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue
        receipt = _receipt_for_step(step)
        if receipt and receipt.get("execution_status") in {"executed_read_only", "dry_run_only_not_executed"}:
            source_step = step
            source_receipt = receipt
        if step.get("tool_id") != "text.summarize":
            continue
        proposal_id = step.get("proposal_id")
        proposal = _proposal_by_id(str(proposal_id)) if proposal_id else None
        if proposal is None:
            skipped.append({"step_id": step.get("step_id"), "reason": "proposal_missing"})
            continue
        if proposal.get("review_status", "pending") != "pending":
            skipped.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "proposal_already_reviewed"})
            continue
        current_text = str(proposal.get("tool_arguments", {}).get("text") or "")
        step_text = str(step.get("arguments", {}).get("text") or "")
        if "<requires approved" not in current_text and "<requires approved" not in step_text and not step.get("bound_arguments"):
            skipped.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "no_binding_placeholder"})
            continue
        if source_step is None or source_receipt is None:
            skipped.append({"step_id": step.get("step_id"), "proposal_id": proposal_id, "reason": "source_receipt_missing"})
            continue
        bindings.append(
            {
                "step_id": step.get("step_id"),
                "proposal_id": proposal_id,
                "source_step_id": source_step.get("step_id"),
                "source_receipt_id": source_receipt.get("receipt_id"),
                "source_output_hash": source_receipt.get("output_hash"),
                "arguments": {"text": _binding_text_from_receipt(source_receipt), "max_words": 48},
            }
        )
    return bindings, skipped


@app.post("/metis/tools/plans/{plan_id}/bind_results")
def bind_tool_plan_results(plan_id: str) -> dict[str, Any]:
    global STATE
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    if plan.get("review_status") != "approved":
        raise HTTPException(status_code=409, detail="tool plan must be approved before results can be bound")
    bindings, skipped = _plan_result_bindings(plan)
    if bindings:
        event = {"type": "tool_plan_result_binding", "plan_id": plan_id, "bindings": bindings, "bound_at": utc_now()}
        STATE = reduce_metis_event(STATE, event)
    else:
        event = None
    return {
        "status": "plan_results_bound" if bindings else "no_plan_results_bound",
        "plan": _tool_plan_by_id(plan_id),
        "bindings": bindings,
        "skipped_steps": skipped,
        "event": event,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/tools/plans/{plan_id}/advance")
def advance_tool_plan(plan_id: str) -> dict[str, Any]:
    plan = _tool_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    action = next_plan_action(plan, STATE)
    if action["action"] == "can_queue_step_proposals":
        result = queue_tool_plan_steps(plan_id, {"reason": "guided advance queued step proposals"})
        return {"status": "advanced", "advanced_action": action, "result": result, "next_action": next_plan_action(_tool_plan_by_id(plan_id), STATE)}
    if action["action"] == "can_request_step_execution":
        result = request_tool_plan_execution(plan_id, {"reason": "guided advance requested approved step execution"})
        return {"status": "advanced", "advanced_action": action, "result": result, "next_action": next_plan_action(_tool_plan_by_id(plan_id), STATE)}
    if action["action"] == "can_bind_results":
        result = bind_tool_plan_results(plan_id)
        return {"status": "advanced", "advanced_action": action, "result": result, "next_action": next_plan_action(_tool_plan_by_id(plan_id), STATE)}
    return {"status": "waiting", "next_action": action, "plan": plan, "state": STATE, "leds": resolve_leds(STATE)}


def _proposal_by_id(proposal_id: str) -> dict[str, Any] | None:
    for proposal in STATE.get("approval_queue", []):
        if proposal.get("proposal_id") == proposal_id:
            return proposal
    return None


@app.get("/metis/proposals/{proposal_id}")
def proposal_detail(proposal_id: str) -> dict[str, Any]:
    proposal = _proposal_by_id(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    return {"proposal": proposal}


def _review_proposal(proposal_id: str, decision: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    proposal = _proposal_by_id(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if proposal.get("review_status", "pending") != "pending":
        raise HTTPException(status_code=409, detail="proposal already reviewed")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    event = {
        "type": "proposal_review",
        "proposal_id": proposal_id,
        "decision": decision,
        "reason": reason,
        "reviewed_at": utc_now(),
    }
    STATE = reduce_metis_event(STATE, event)
    reviewed = _proposal_by_id(proposal_id)
    return {
        "status": f"proposal_{decision}",
        "proposal": reviewed,
        "review_receipt": reviewed.get("review_receipt") if reviewed else None,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_proposal(proposal_id, "approved", payload)


@app.post("/metis/proposals/{proposal_id}/deny")
def deny_proposal(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _review_proposal(proposal_id, "denied", payload)


def _receipt_by_id(receipt_id: str) -> dict[str, Any] | None:
    for receipt in STATE.get("execution_audit_log", []):
        if receipt.get("receipt_id") == receipt_id:
            return receipt
    return None


@app.get("/metis/execution/receipts")
def execution_receipts() -> dict[str, Any]:
    return {"receipts": STATE.get("execution_audit_log", []), "receipt_count": len(STATE.get("execution_audit_log", []))}


@app.get("/metis/execution/receipts/{receipt_id}")
def execution_receipt_detail(receipt_id: str) -> dict[str, Any]:
    receipt = _receipt_by_id(receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="execution receipt not found")
    return {"receipt": receipt}


@app.get("/metis/execution/policy")
def execution_policy() -> dict[str, Any]:
    return read_only_execution_policy()


def _execution_request_event_for_proposal(proposal: dict[str, Any], reason: str = "") -> dict[str, Any]:
    dry_run_receipt = None
    read_only_result = None
    if proposal.get("review_status") == "approved" and proposal.get("tool_id") == "time.now":
        read_only_result = dry_run_tool("time.now", proposal.get("tool_arguments") or {})["result"]
    elif proposal.get("review_status") == "approved" and proposal.get("tool_id") == "git.status":
        read_only_result = execute_git_status(proposal.get("tool_arguments") or {})
    elif proposal.get("review_status") == "approved" and proposal.get("tool_id") == "filesystem.read":
        read_only_result = execute_filesystem_read(proposal.get("tool_arguments") or {})
    elif proposal.get("review_status") == "approved" and proposal.get("dry_run_available") and proposal.get("side_effect_class") == "none":
        dry_run_receipt = dry_run_tool(str(proposal.get("tool_id")), proposal.get("tool_arguments") or {})
    event = {
        "type": "execution_request",
        "proposal_id": proposal.get("proposal_id"),
        "reason": reason,
        "requested_at": utc_now(),
    }
    if dry_run_receipt:
        event["dry_run_receipt"] = dry_run_receipt
    if read_only_result:
        event["read_only_result"] = read_only_result
    return event


@app.post("/metis/proposals/{proposal_id}/request_execution")
def request_proposal_execution(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    proposal = _proposal_by_id(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    try:
        event = _execution_request_event_for_proposal(proposal, reason)
    except (ToolRegistryError, ReadOnlyToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    STATE = reduce_metis_event(STATE, event)
    receipt = STATE.get("execution_audit_log", [])[-1] if STATE.get("execution_audit_log") else None
    return {
        "status": receipt.get("execution_status") if receipt else "not_recorded",
        "receipt": receipt,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.get("/metis/tools")
def tools() -> dict[str, Any]:
    return list_tools()


@app.get("/metis/tools/contract")
def tool_contract() -> dict[str, Any]:
    return build_tool_contract_manifest()


@app.get("/metis/tools/policy_snapshot")
def tool_policy_snapshot() -> dict[str, Any]:
    return build_tool_policy_snapshot(STATE)


@app.post("/metis/tools/governance/evaluate")
def tool_governance_evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    tool_id = payload.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise HTTPException(status_code=400, detail="tool_id is required")
    try:
        return evaluate_tool_request(tool_id, payload.get("arguments") or {}, STATE, str(payload.get("request_type") or "dry_run"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/metis/tools/readiness")
def tool_readiness() -> dict[str, Any]:
    return calculate_tool_readiness(STATE)


@app.get("/metis/tools/completion")
def tool_completion() -> dict[str, Any]:
    return calculate_tool_completion(STATE)


@app.post("/metis/tools/task/plan")
def tool_task_plan(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    try:
        plan = plan_tool_task(str(payload.get("task") or ""), STATE)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.get("persist", True) is False:
        return plan
    if _tool_plan_by_id(plan["plan_id"]):
        return {"status": "plan_already_exists", "plan": _tool_plan_by_id(plan["plan_id"]), "state": STATE, "leds": resolve_leds(STATE)}
    event = {"type": "tool_plan", "plan": plan}
    STATE = reduce_metis_event(STATE, event)
    return {"status": "plan_queued", "plan": _tool_plan_by_id(plan["plan_id"]), "event": event, "state": STATE, "leds": resolve_leds(STATE)}


def _route_chat_plan_request(message: str) -> str | None:
    text = message.strip()
    lowered = text.lower()
    prefixes = ("plan task:", "plan tool task:", "task plan:", "create tool plan:", "make tool plan:")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip()
    return None


def _queue_chat_tool_plan(task: str) -> dict[str, Any]:
    global STATE
    if not task:
        raise ValueError("task is required")
    plan = plan_tool_task(task, STATE)
    existing = _tool_plan_by_id(plan["plan_id"])
    if existing:
        return {"status": "plan_already_exists", "plan": existing, "next_action": next_plan_action(existing, STATE)}
    event = {"type": "tool_plan", "plan": plan}
    STATE = reduce_metis_event(STATE, event)
    queued_plan = _tool_plan_by_id(plan["plan_id"])
    return {"status": "plan_queued", "plan": queued_plan, "event": event, "next_action": next_plan_action(queued_plan, STATE)}


def _latest_tool_plan() -> dict[str, Any] | None:
    plans = STATE.get("tool_plan_queue", [])
    if not plans:
        return None
    return plans[-1]


def _plan_id_from_text(message: str) -> str | None:
    for token in re.split(r"[\s,;]+", message):
        cleaned = token.strip().strip(".:?!()[]{}'\"")
        if cleaned.startswith("plan_id="):
            return cleaned.split("=", 1)[1].strip(".:?!()[]{}'\"") or None
        if cleaned.startswith("plan_"):
            return cleaned
    return None


def _route_chat_plan_control_request(message: str) -> dict[str, str | None] | None:
    text = message.strip()
    lowered = text.lower()
    plan_id = _plan_id_from_text(text)
    advance_phrases = (
        "advance tool plan",
        "continue tool plan",
        "advance plan",
        "continue plan",
        "move tool plan forward",
    )
    status_phrases = (
        "tool plan status",
        "plan status",
        "what is next for my tool plan",
        "what's next for my tool plan",
        "next tool plan step",
        "tool plan next",
    )
    if any(phrase in lowered for phrase in advance_phrases):
        return {"action": "advance", "plan_id": plan_id}
    if any(phrase in lowered for phrase in status_phrases):
        return {"action": "status", "plan_id": plan_id}
    return None


def _resolve_chat_plan(plan_id: str | None) -> dict[str, Any]:
    plan = _tool_plan_by_id(plan_id) if plan_id else _latest_tool_plan()
    if plan is None:
        raise HTTPException(status_code=404, detail="tool plan not found")
    return plan


def _plan_control_message(plan: dict[str, Any], next_action: dict[str, Any], status: str) -> str:
    review_status = plan.get("review_status", "pending")
    action = next_action.get("action", "unknown")
    reason = next_action.get("reason") or next_action.get("message") or "No additional detail."
    return (
        f"Governed tool plan {status}: {plan['plan_id']} is {review_status} with "
        f"{plan.get('step_count', 0)} step(s). Next action: {action}. {reason} "
        "Chat cannot approve plans, approve proposals, or grant standing execution."
    )


def _chat_plan_status(plan_id: str | None) -> dict[str, Any]:
    plan = _resolve_chat_plan(plan_id)
    action = next_plan_action(plan, STATE)
    return {"status": "plan_status", "plan": plan, "next_action": action}


def _chat_plan_advance(plan_id: str | None) -> dict[str, Any]:
    plan = _resolve_chat_plan(plan_id)
    advanced = advance_tool_plan(plan["plan_id"])
    latest = _tool_plan_by_id(plan["plan_id"]) or plan
    return {"status": "plan_advance_requested", "plan": latest, "advance": advanced, "next_action": advanced.get("next_action") or next_plan_action(latest, STATE)}


def _route_chat_queue_status_request(message: str) -> str | None:
    lowered = message.strip().lower()
    proposal_phrases = (
        "what needs approval",
        "what is waiting for approval",
        "what's waiting for approval",
        "pending approvals",
        "pending proposals",
        "approval queue",
        "proposal status",
        "what needs review",
    )
    receipt_phrases = (
        "execution receipts",
        "receipt summary",
        "receipt status",
        "audit receipts",
        "tool receipts",
        "what receipts",
    )
    if any(phrase in lowered for phrase in receipt_phrases):
        return "receipts"
    if any(phrase in lowered for phrase in proposal_phrases):
        return "proposals"
    return None


def _proposal_id_from_text(message: str) -> str | None:
    for token in re.split(r"[\s,;]+", message):
        cleaned = token.strip().strip(".:?!()[]{}'\"")
        if cleaned.startswith("proposal_id="):
            return cleaned.split("=", 1)[1].strip(".:?!()[]{}'\"") or None
        if cleaned.startswith("proposal_"):
            return cleaned
    return None


def _route_chat_next_action_request(message: str) -> dict[str, str | None] | None:
    text = message.strip()
    lowered = text.lower()
    phrases = (
        "what should i do next",
        "what do i do next",
        "next governed action",
        "next approval step",
        "what is the next approval step",
        "how do i approve",
        "how do i deny",
        "how do i request execution",
        "how should i proceed",
    )
    if not any(phrase in lowered for phrase in phrases):
        return None
    return {"plan_id": _plan_id_from_text(text), "proposal_id": _proposal_id_from_text(text)}


def _receipt_exists_for_proposal(proposal_id: str) -> bool:
    return any(receipt.get("proposal_id") == proposal_id for receipt in STATE.get("execution_audit_log", []))


def _instruction_payload(
    *,
    recommended_action: str,
    target_type: str,
    target_id: str | None,
    ui_instruction: str,
    api_instruction: dict[str, str | None],
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "next_action_instruction",
        "recommended_action": recommended_action,
        "target": {"type": target_type, "id": target_id},
        "ui_instruction": ui_instruction,
        "api_instruction": api_instruction,
        "reason": reason,
        "execution_allowed": False,
        "chat_may_perform_action": False,
    }


def _proposal_instruction(proposal: dict[str, Any]) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposal_id") or "")
    review_status = str(proposal.get("review_status") or "pending")
    if review_status == "pending":
        return _instruction_payload(
            recommended_action="review_proposal",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Approve or Deny.",
            api_instruction={"approve": f"POST /metis/proposals/{proposal_id}/approve", "deny": f"POST /metis/proposals/{proposal_id}/deny"},
            reason="Proposal is pending human review.",
        )
    if review_status == "approved" and not _receipt_exists_for_proposal(proposal_id):
        return _instruction_payload(
            recommended_action="request_execution_receipt",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Request Execution.",
            api_instruction={"request_execution": f"POST /metis/proposals/{proposal_id}/request_execution"},
            reason="Proposal is approved and can move to the existing execution-request receipt gate.",
        )
    if review_status == "approved":
        return _instruction_payload(
            recommended_action="inspect_receipt",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction="Open the Tools panel and refresh Execution Receipts.",
            api_instruction={"list_receipts": "GET /metis/execution/receipts"},
            reason="Proposal is already approved and has at least one receipt.",
        )
    return _instruction_payload(
        recommended_action="no_action_available",
        target_type="proposal",
        target_id=proposal_id,
        ui_instruction="No governed action is available for this proposal.",
        api_instruction={"detail": f"GET /metis/proposals/{proposal_id}"},
        reason=f"Proposal review status is {review_status}.",
    )


def _plan_instruction(plan: dict[str, Any]) -> dict[str, Any]:
    plan_id = str(plan.get("plan_id") or "")
    action = next_plan_action(plan, STATE)
    action_name = action.get("action")
    if action_name == "needs_plan_review":
        return _instruction_payload(
            recommended_action="review_tool_plan",
            target_type="tool_plan",
            target_id=plan_id,
            ui_instruction=f"Open the Tools panel, select plan {plan_id}, then click Approve Plan or Deny Plan.",
            api_instruction={"approve": f"POST /metis/tools/plans/{plan_id}/approve", "deny": f"POST /metis/tools/plans/{plan_id}/deny"},
            reason=str(action.get("detail") or "Plan requires review."),
        )
    if action_name == "can_queue_step_proposals":
        return _instruction_payload(
            recommended_action="advance_plan_queue_steps",
            target_type="tool_plan",
            target_id=plan_id,
            ui_instruction=f"Open the Tools panel, select plan {plan_id}, then click Advance Plan.",
            api_instruction={"advance": f"POST /metis/tools/plans/{plan_id}/advance", "queue_steps": f"POST /metis/tools/plans/{plan_id}/queue_steps"},
            reason=str(action.get("detail") or "Approved plan can queue step proposals."),
        )
    if action_name == "needs_step_proposal_review":
        waiting = action.get("waiting_on", [])
        proposal_id = waiting[0].get("proposal_id") if waiting and isinstance(waiting[0], dict) else None
        return _instruction_payload(
            recommended_action="review_step_proposal",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Approve or Deny.",
            api_instruction={"approve": f"POST /metis/proposals/{proposal_id}/approve", "deny": f"POST /metis/proposals/{proposal_id}/deny"},
            reason=str(action.get("detail") or "A step proposal requires review."),
        )
    if action_name == "can_request_step_execution":
        ready = action.get("ready_steps", [])
        proposal_id = ready[0].get("proposal_id") if ready and isinstance(ready[0], dict) else None
        return _instruction_payload(
            recommended_action="request_step_execution_receipt",
            target_type="proposal",
            target_id=proposal_id,
            ui_instruction=f"Open the Tools panel, select proposal {proposal_id}, then click Request Execution, or select plan {plan_id} and click Advance Plan.",
            api_instruction={"request_execution": f"POST /metis/proposals/{proposal_id}/request_execution", "advance": f"POST /metis/tools/plans/{plan_id}/advance"},
            reason=str(action.get("detail") or "Approved step proposal can move to the receipt gate."),
        )
    if action_name == "can_bind_results":
        return _instruction_payload(
            recommended_action="bind_plan_results",
            target_type="tool_plan",
            target_id=plan_id,
            ui_instruction=f"Open the Tools panel, select plan {plan_id}, then click Bind Results or Advance Plan.",
            api_instruction={"bind_results": f"POST /metis/tools/plans/{plan_id}/bind_results", "advance": f"POST /metis/tools/plans/{plan_id}/advance"},
            reason=str(action.get("detail") or "Safe receipt summaries can be bound into dependent steps."),
        )
    return _instruction_payload(
        recommended_action=str(action_name or "no_action_available"),
        target_type="tool_plan",
        target_id=plan_id,
        ui_instruction="No governed operator action is currently required for this plan.",
        api_instruction={"detail": f"GET /metis/tools/plans/{plan_id}"},
        reason=str(action.get("detail") or "No next action."),
    )


def _next_action_instruction(plan_id: str | None = None, proposal_id: str | None = None) -> dict[str, Any]:
    if proposal_id:
        proposal = _proposal_by_id(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        return _proposal_instruction(proposal)
    if plan_id:
        return _plan_instruction(_resolve_chat_plan(plan_id))
    for plan in STATE.get("tool_plan_queue", []):
        if isinstance(plan, dict):
            instruction = _plan_instruction(plan)
            if instruction["recommended_action"] not in {"complete_for_current_scope", "plan_denied", "no_action_available"}:
                return instruction
    for proposal in STATE.get("approval_queue", []):
        if isinstance(proposal, dict) and proposal.get("review_status", "pending") == "pending":
            return _proposal_instruction(proposal)
    for proposal in STATE.get("approval_queue", []):
        if isinstance(proposal, dict) and proposal.get("review_status") == "approved" and not _receipt_exists_for_proposal(str(proposal.get("proposal_id") or "")):
            return _proposal_instruction(proposal)
    return _instruction_payload(
        recommended_action="no_action_available",
        target_type="workspace",
        target_id=None,
        ui_instruction="No governed approval or receipt action is currently waiting.",
        api_instruction={"proposals": "GET /metis/proposals", "plans": "GET /metis/tools/plans", "receipts": "GET /metis/execution/receipts"},
        reason="There are no pending plan reviews, proposal reviews, or approved proposals awaiting receipt requests.",
    )


def _next_action_message(instruction: dict[str, Any]) -> str:
    return (
        f"Next governed action: {instruction['recommended_action']} for "
        f"{instruction['target']['type']} {instruction['target']['id'] or 'current workspace'}. "
        f"{instruction['ui_instruction']} Chat cannot perform this action."
    )


def _proposal_status_summary(limit: int = 6) -> dict[str, Any]:
    proposals_queue = list(STATE.get("approval_queue", []))
    counts: dict[str, int] = {}
    pending: list[dict[str, Any]] = []
    for proposal in proposals_queue:
        review_status = str(proposal.get("review_status") or proposal.get("status") or "unknown")
        counts[review_status] = counts.get(review_status, 0) + 1
        if review_status == "pending":
            arguments = proposal.get("tool_arguments") if isinstance(proposal.get("tool_arguments"), dict) else {}
            pending.append(
                {
                    "proposal_id": proposal.get("proposal_id"),
                    "proposal_type": proposal.get("proposal_type"),
                    "tool_id": proposal.get("tool_id"),
                    "review_status": review_status,
                    "risk_class": proposal.get("risk_class"),
                    "side_effect_class": proposal.get("side_effect_class"),
                    "dry_run_available": bool(proposal.get("dry_run_available")),
                    "execution_allowed": False,
                    "argument_keys": sorted(str(key) for key in arguments),
                }
            )
    return {
        "status": "approval_queue_status",
        "total_count": len(proposals_queue),
        "pending_count": len(pending),
        "counts_by_review_status": counts,
        "pending_proposals": pending[:limit],
        "truncated": len(pending) > limit,
    }


def _receipt_status_summary(limit: int = 6) -> dict[str, Any]:
    receipts = list(STATE.get("execution_audit_log", []))
    counts: dict[str, int] = {}
    safe_receipts: list[dict[str, Any]] = []
    for receipt in receipts[-limit:]:
        execution_status = str(receipt.get("execution_status") or "unknown")
        counts[execution_status] = counts.get(execution_status, 0) + 1
        output_summary = receipt.get("output_summary") if isinstance(receipt.get("output_summary"), dict) else {}
        safe_receipts.append(
            {
                "receipt_id": receipt.get("receipt_id"),
                "proposal_id": receipt.get("proposal_id"),
                "tool_id": receipt.get("tool_id"),
                "execution_status": execution_status,
                "policy_decision": receipt.get("policy_decision"),
                "review_status": receipt.get("review_status"),
                "execution_allowed": False,
                "output_hash": receipt.get("output_hash"),
                "output_keys": output_summary.get("keys", []),
                "redactions": receipt.get("redactions", []),
            }
        )
    return {
        "status": "execution_receipt_status",
        "receipt_count": len(receipts),
        "counts_by_execution_status": counts,
        "receipts": safe_receipts,
        "truncated": len(receipts) > limit,
    }


def _proposal_status_message(summary: dict[str, Any]) -> str:
    pending = summary["pending_proposals"]
    if not pending:
        return (
            f"Approval queue: {summary['pending_count']} pending of {summary['total_count']} total proposals. "
            "Chat can report queue status, but cannot approve, deny, or request execution."
        )
    parts = [
        f"{item.get('proposal_id')} ({item.get('tool_id') or item.get('proposal_type')}, "
        f"{item.get('risk_class')}, {item.get('side_effect_class')})"
        for item in pending
    ]
    suffix = " More pending proposals are omitted from this summary." if summary.get("truncated") else ""
    return (
        f"Approval queue: {summary['pending_count']} pending of {summary['total_count']} total proposals. "
        f"Pending: {'; '.join(parts)}.{suffix} "
        "Chat can report queue status, but cannot approve, deny, or request execution."
    )


def _receipt_status_message(summary: dict[str, Any]) -> str:
    receipts = summary["receipts"]
    if not receipts:
        return "Execution receipts: 0 recorded. Chat can summarize receipts, but cannot create approvals or execution authority."
    parts = [
        f"{item.get('receipt_id')} ({item.get('tool_id')}, {item.get('execution_status')}, {item.get('policy_decision')})"
        for item in receipts
    ]
    suffix = " Older receipts are omitted from this summary." if summary.get("truncated") else ""
    return (
        f"Execution receipts: {summary['receipt_count']} recorded. Latest: {'; '.join(parts)}.{suffix} "
        "Raw file contents, command output, secrets, and external receipts are not included."
    )


def _route_chat_tool_capability_request(message: str) -> bool:
    normalized = re.sub(r"[^a-z0-9.\s_-]+", " ", message.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return False
    tool_terms = ("tool", "tools", "capability", "capabilities", "can you do", "available to you")
    if not any(term in normalized for term in tool_terms):
        return False
    awareness_terms = (
        "what",
        "which",
        "list",
        "show",
        "available",
        "access",
        "use",
        "can you",
        "do you have",
        "current capabilities",
    )
    return any(term in normalized for term in awareness_terms)


def _tool_capability_summary() -> dict[str, Any]:
    tools = list_tools()["tools"]
    safe_dry_run = [
        tool["tool_id"]
        for tool in tools
        if tool.get("enabled") and tool.get("permission_mode") == "dry_run" and tool.get("side_effect_class") == "none"
    ]
    approved_read_only = [
        tool["tool_id"]
        for tool in tools
        if tool.get("enabled") and tool.get("permission_mode") == "approved_read_only"
    ]
    proposal_only = [
        tool["tool_id"]
        for tool in tools
        if tool.get("enabled") and tool.get("permission_mode") == "proposal_only"
    ]
    return {
        "schema_version": "metis_tool_capability_awareness.v0.1",
        "safe_dry_run_tools": safe_dry_run,
        "approved_read_only_lanes": approved_read_only,
        "proposal_only_lanes": proposal_only,
        "llm_direct_tool_calling": False,
        "voice_instruction_supported": True,
        "execution_boundary": "Tool use is routed through deterministic governed lanes; chat and voice do not create autonomous execution authority.",
        "agent_mode_boundary": "Agent Mode queues proposals only and never executes tools directly.",
    }


def _tool_capability_message(summary: dict[str, Any]) -> str:
    safe = ", ".join(summary["safe_dry_run_tools"]) or "none"
    read_only = ", ".join(summary["approved_read_only_lanes"]) or "none"
    proposals = ", ".join(summary["proposal_only_lanes"]) or "none"
    return (
        "Metis has governed tools available through native tool lanes. "
        f"Safe dry-run tools: {safe}. "
        f"Approved read-only lanes after proposal and human review: {read_only}. "
        f"Proposal-only or future lanes: {proposals}. "
        "I do not call tools directly as an LLM, and I do not perform autonomous external actions. "
        "Typed or spoken tool requests are routed into proposals, dry-runs, plans, review gates, and bounded receipts."
    )


@app.get("/metis/tools/{tool_id}")
def tool_detail(tool_id: str) -> dict[str, Any]:
    try:
        return get_tool(tool_id).to_dict()
    except ToolRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _queue_tool_proposal(tool_id: str, arguments: Any, reason: str | None = None) -> dict[str, Any]:
    global STATE
    event = build_tool_proposal_event(tool_id, arguments, STATE, reason)
    STATE = reduce_metis_event(STATE, event)
    return {
        "status": "proposal_queued",
        "tool_id": tool_id,
        "event": event,
        "proposal": STATE.get("approval_queue", [])[-1] if STATE.get("approval_queue") else None,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


def _handle_chat_tool_request(user_message: str, options: dict[str, Any]) -> dict[str, Any] | None:
    tool_options = options.get("tools") if isinstance(options.get("tools"), dict) else {}
    if tool_options.get("enabled", True) is False:
        return None
    route = route_tool_request(user_message)
    if route is None:
        return None
    tool_id = route["tool_id"]
    arguments = route.get("arguments") or {}
    tool = get_tool(tool_id)
    if STATE.get("interaction_mode") == "agent" or tool.permission_mode != "dry_run" or tool.side_effect_class != "none":
        queued = _queue_tool_proposal(tool_id, arguments, route.get("reason"))
        return {"status": "proposal_queued", "tool_id": tool_id, "route": route, "proposal": queued.get("proposal")}
    receipt = dry_run_tool(tool_id, arguments)
    return {"status": "dry_run_complete", "tool_id": tool_id, "route": route, "receipt": receipt}


def _tool_chat_message(tool_result: dict[str, Any]) -> str:
    tool_id = tool_result["tool_id"]
    if tool_result["status"] == "proposal_queued":
        return f"Tool proposal queued: {tool_id}. Execution allowed: false. Review is required before any side-effectful action."
    receipt = tool_result.get("receipt", {})
    return f"Tool dry-run complete: {tool_id}\n\nResult: {receipt.get('result')}\n\nNo external action was executed."


@app.post("/metis/tools/propose")
def tool_propose(payload: dict[str, Any]) -> dict[str, Any]:
    tool_id = payload.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise HTTPException(status_code=400, detail="tool_id is required")
    try:
        return _queue_tool_proposal(tool_id, payload.get("arguments") or {}, payload.get("reason"))
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/metis/tools/{tool_id}/dry_run")
def tool_dry_run(tool_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else payload
    try:
        tool = get_tool(tool_id)
        if STATE.get("interaction_mode") == "agent" or tool.permission_mode != "dry_run" or tool.side_effect_class != "none":
            return _queue_tool_proposal(tool_id, arguments, payload.get("reason") if isinstance(payload, dict) else None)
        receipt = dry_run_tool(tool_id, arguments)
        return {"status": "dry_run_complete", "receipt": receipt, "state": STATE, "leds": resolve_leds(STATE)}
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/metis/tools/{tool_id}/execute")
def tool_execute(tool_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else payload
    try:
        receipt = execute_tool(tool_id, arguments, STATE)
        if receipt.get("proposal_required"):
            queued = _queue_tool_proposal(tool_id, arguments, payload.get("reason") if isinstance(payload, dict) else None)
            return {**queued, "execution_status": receipt["status"], "blocked_reason": receipt["blocked_reason"], "execution_allowed": False}
        return {"status": receipt["status"], "receipt": receipt, "state": STATE, "leds": resolve_leds(STATE)}
    except ToolRegistryError as exc:
        status_code = 404 if str(exc).startswith("unknown tool") else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/metis/llm/options")
def llm_options(base_url: str | None = None) -> dict[str, Any]:
    import os

    saved_provider: dict[str, Any] = {}
    try:
        setup_provider = _setup_store().load().get("provider")
        if isinstance(setup_provider, dict):
            saved_provider = setup_provider
    except (OSError, SetupStateError):
        # Environment-only operation remains available if the local setup
        # document is absent or invalid.
        saved_provider = {}

    saved_choice = str(saved_provider.get("choice") or "").strip().lower()
    saved_model = str(saved_provider.get("model") or "").strip() or None
    configured_provider = os.environ.get("METIS_LLM_PROVIDER")
    if not configured_provider and saved_choice == "ollama" and saved_model:
        configured_provider = "ollama"
    ollama_base_url = (
        base_url
        or os.environ.get("METIS_OLLAMA_BASE_URL")
        or saved_provider.get("base_url")
        or "http://127.0.0.1:11434"
    )
    return {
        "selected_provider": configured_provider or "mock",
        "ollama_base_url": ollama_base_url,
        "ollama_model": os.environ.get("METIS_OLLAMA_MODEL") or saved_model,
        "openai_model": os.environ.get("METIS_OPENAI_MODEL", "gpt-4o-mini"),
        "ollama": list_ollama_models(ollama_base_url),
    }


@app.post("/metis/llm/health")
def llm_health(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    config = payload.get("options") if isinstance(payload.get("options"), dict) else payload
    return probe_llm_provider(config)


@app.post("/metis/governance/classify")
def governance_classify(payload: dict[str, Any]) -> dict[str, Any]:
    intent = payload.get("intent")
    if not isinstance(intent, str) or not intent.strip():
        raise HTTPException(status_code=400, detail="intent is required")
    policy = classify_intent(intent, STATE)
    return {"policy_version": POLICY_VERSION, "policy": policy.to_dict()}


@app.post("/metis/event")
def post_event(event: dict[str, Any]) -> dict[str, Any]:
    global STATE
    try:
        STATE = reduce_metis_event(STATE, event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"state": STATE, "leds": resolve_leds(STATE)}


def _apply_voice_result(result: VoiceResult) -> None:
    global STATE
    for event in result.events:
        STATE = reduce_metis_event(STATE, event)


def _speak_chat_response(
    assistant_message: str,
    options: dict[str, Any],
    token: TurnToken | None = None,
) -> dict[str, Any] | None:
    voice_options = options.get("voice") if isinstance(options.get("voice"), dict) else {}
    if not voice_options.get("speak_response"):
        return None
    speak_options = {"voice": {**voice_options, "enabled": True}}
    voice_result = speak_text(assistant_message, STATE, speak_options)
    _apply_voice_result(voice_result)
    if token is not None and voice_result.ok and voice_result.spoken:
        audio_ref = next(
            (str(event.get("audio_ref")) for event in voice_result.events if event.get("audio_ref")),
            None,
        )
        if audio_ref and SESSIONS.accepts(token):
            artifact_id = audio_ref.rsplit("/", 1)[-1]
            if AUDIO_ARTIFACTS.bind(
                artifact_id,
                session_id=token.session_id,
                turn_id=token.turn_id,
                generation=token.generation,
            ):
                owned_ref = f"{audio_ref}?session_id={token.session_id}"
                client_id = SESSIONS.snapshot(token.session_id).client_id
                item = PLAYBACK.enqueue(client_id=client_id, token=token, audio_ref=owned_ref, content_type="audio/wav")
                if item is not None:
                    for event in voice_result.events:
                        if event.get("audio_ref"):
                            event["audio_ref"] = owned_ref
                            event["playback_id"] = item.playback_id
                    voice_result.metadata["playback_id"] = item.playback_id
                    SESSIONS.transition(token, TurnStage.PLAYBACK_QUEUED)
    return _voice_response_payload(voice_result)


def _finish_chat_turn(
    token: TurnToken | None,
    assistant_message: str,
    options: dict[str, Any],
) -> dict[str, Any] | None:
    """Commit text and finish or queue speech without stranding the session."""
    if token is None:
        return _speak_chat_response(assistant_message, options)
    if not SESSIONS.commit_assistant_text(token, assistant_message):
        raise HTTPException(status_code=409, detail="turn was cancelled before the response committed")
    voice_options_payload = options.get("voice") if isinstance(options.get("voice"), dict) else {}
    speak_requested = bool(voice_options_payload.get("speak_response"))
    if not speak_requested:
        SESSIONS.transition(token, TurnStage.COMPLETED)
        return None
    SESSIONS.transition(token, TurnStage.SYNTHESIZING)
    try:
        voice = _speak_chat_response(assistant_message, options, token)
    except Exception:
        if SESSIONS.accepts(token):
            SESSIONS.transition(token, TurnStage.FAILED, failure_code="tts_exception")
        return {"ok": False, "spoken": False, "blocked_reason": "tts_exception", "metadata": {}}
    playback_queued = bool(voice and voice.get("metadata", {}).get("playback_id"))
    if not playback_queued and SESSIONS.accepts(token):
        target = TurnStage.FAILED if voice and not voice.get("ok", True) else TurnStage.COMPLETED
        SESSIONS.transition(token, target, failure_code="tts_failed" if target is TurnStage.FAILED else None)
    return voice


def _fail_chat_turn(token: TurnToken | None, failure_code: str) -> None:
    if token is not None and SESSIONS.accepts(token):
        SESSIONS.transition(token, TurnStage.FAILED, failure_code=failure_code)


@app.post("/metis/chat")
def chat(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    user_message = payload.get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    request_session_id = _optional_session_value(payload.get("session_id") or options.get("session_id"))
    if request_session_id is not None:
        options = {**options, "session_id": request_session_id, "_metis_private_session": True}
    session_token = _session_turn(payload, user_message, options)
    persisted_user_message = _persisted_chat_user_message(user_message, options)
    plan_task = _route_chat_plan_request(user_message)
    if plan_task is not None:
        try:
            planned = _queue_chat_tool_plan(plan_task)
        except ValueError as exc:
            _fail_chat_turn(session_token, "invalid_plan_request")
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        plan = planned["plan"]
        next_action = planned["next_action"]
        plan_status = "queued" if planned["status"] == "plan_queued" else "already exists"
        assistant_message = (
            f"Governed tool plan {plan_status}: {plan['plan_id']} with {plan['step_count']} step(s). "
            f"Next action: {next_action['action']}. Execution allowed: false."
        )
        persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": "metis_tool_task_plan.v0.1",
                "user_message": persisted_user_message,
                "assistant_message": persisted_assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _finish_chat_turn(session_token, assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": "metis_tool_task_plan.v0.1",
            "proposal_queued": False,
            "plan_queued": planned["status"] == "plan_queued",
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"tool_plan": planned},
            "retrieval": None,
            "voice": voice,
            "tool_plan": planned,
        }
    plan_control = _route_chat_plan_control_request(user_message)
    if plan_control is not None:
        if plan_control["action"] == "advance":
            controlled = _chat_plan_advance(plan_control["plan_id"])
            model = "metis_tool_plan_advance.v0.1"
            plan = controlled["plan"]
            next_action = controlled["next_action"]
            assistant_message = _plan_control_message(plan, next_action, "advance checked")
        else:
            controlled = _chat_plan_status(plan_control["plan_id"])
            model = "metis_tool_plan_status.v0.1"
            plan = controlled["plan"]
            next_action = controlled["next_action"]
            assistant_message = _plan_control_message(plan, next_action, "status")
        persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": model,
                "user_message": persisted_user_message,
                "assistant_message": persisted_assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _finish_chat_turn(session_token, assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": model,
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"tool_plan": controlled},
            "retrieval": None,
            "voice": voice,
            "tool_plan": controlled,
        }
    next_action_request = _route_chat_next_action_request(user_message)
    if next_action_request is not None:
        instruction = _next_action_instruction(next_action_request["plan_id"], next_action_request["proposal_id"])
        assistant_message = _next_action_message(instruction)
        persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": "metis_tool_next_action.v0.1",
                "user_message": persisted_user_message,
                "assistant_message": persisted_assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _finish_chat_turn(session_token, assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": "metis_tool_next_action.v0.1",
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"next_action": instruction},
            "retrieval": None,
            "voice": voice,
            "next_action": instruction,
        }
    queue_status_request = _route_chat_queue_status_request(user_message)
    if queue_status_request is not None:
        if queue_status_request == "receipts":
            queue_summary = _receipt_status_summary()
            model = "metis_tool_receipt_status.v0.1"
            assistant_message = _receipt_status_message(queue_summary)
        else:
            queue_summary = _proposal_status_summary()
            model = "metis_tool_approval_status.v0.1"
            assistant_message = _proposal_status_message(queue_summary)
        persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_planner",
                "model": model,
                "user_message": persisted_user_message,
                "assistant_message": persisted_assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _finish_chat_turn(session_token, assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_planner",
            "model": model,
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": classify_intent(user_message, STATE).to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"queue_status": queue_summary},
            "retrieval": None,
            "voice": voice,
            "queue_status": queue_summary,
        }
    proposal_queued = False
    policy = classify_intent(user_message, STATE)
    capability_request = _route_chat_tool_capability_request(user_message)
    if capability_request:
        capability_summary = _tool_capability_summary()
        assistant_message = _tool_capability_message(capability_summary)
        persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_capability",
                "model": capability_summary["schema_version"],
                "user_message": persisted_user_message,
                "assistant_message": persisted_assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _finish_chat_turn(session_token, assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_capability",
            "model": capability_summary["schema_version"],
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": policy.to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"tool_capabilities": capability_summary},
            "retrieval": None,
            "voice": voice,
            "tool_capabilities": capability_summary,
        }
    mcp_chat_read = route_mcp_chat_read(user_message, STATE)
    if mcp_chat_read is not None:
        assistant_message = mcp_chat_read["message"]
        persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
        for event in mcp_chat_read.get("events") or [mcp_chat_read["event"]]:
            STATE = reduce_metis_event(STATE, event)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": mcp_chat_read["provider"],
                "model": mcp_chat_read["model"],
                "user_message": persisted_user_message,
                "assistant_message": persisted_assistant_message,
                "source_state": mcp_chat_read["source_state"],
            },
        )
        voice = _finish_chat_turn(session_token, assistant_message, options)
        return {
            "message": assistant_message,
            "provider": mcp_chat_read["provider"],
            "model": mcp_chat_read["model"],
            "proposal_queued": False,
            "plan_queued": False,
            "source_state": mcp_chat_read["source_state"],
            "policy": policy.to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"mcp_chat_read": mcp_chat_read["metadata"]},
            "retrieval": None,
            "voice": voice,
            "mcp_chat_read": mcp_chat_read["metadata"],
        }

    tool_result = None
    try:
        tool_result = _handle_chat_tool_request(user_message, options)
    except ToolRegistryError as exc:
        _fail_chat_turn(session_token, "invalid_tool_request")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if tool_result is None and should_queue_proposal(policy, STATE):
        STATE = reduce_metis_event(
            STATE,
            {"type": "user_intent", "intent": persisted_user_message, "action_class": policy.action_class, "policy": policy.to_dict()},
        )
        proposal_queued = True
    if tool_result is not None:
        assistant_message = _tool_chat_message(tool_result)
        persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_router",
                "model": tool_result["tool_id"],
                "user_message": persisted_user_message,
                "assistant_message": persisted_assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _finish_chat_turn(session_token, assistant_message, options)
        return {
            "message": assistant_message,
            "provider": "tool_router",
            "model": tool_result["tool_id"],
            "proposal_queued": proposal_queued or tool_result["status"] == "proposal_queued",
            "source_state": STATE.get("source_state", "unsourced"),
            "policy": policy.to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
            "metadata": {"tool": tool_result},
            "retrieval": None,
            "voice": voice,
            "tool": tool_result,
        }

    retrieval = None
    retrieval_context = None
    if STATE.get("source_grounding_enabled"):
        config = boh_config_from_env(options=options)
        link = get_link_state()
        if config.enabled and link.enabled and link.state == LINK_AUTH_FAILED:
            # The background manager already established that BOH rejects our
            # read-only token. Don't repeatedly hammer BOH per message; surface
            # a visible degraded state instead of a silent failure.
            retrieval = BOHRetrievalResult(
                enabled=True,
                attempted=False,
                ok=False,
                source_state="degraded",
                mode=config.mode,
                error="BOH background link reports auth_failed; check the read-only retrieval token.",
            )
        else:
            retrieval = retrieve_boh_context(config, user_message)
        retrieval_context = render_context(retrieval)

    if session_token is not None and not SESSIONS.accepts(session_token):
        raise HTTPException(status_code=409, detail="turn was cancelled during source retrieval")

    broker = _google_read_broker()
    if session_token is not None and not SESSIONS.accepts(session_token):
        raise HTTPException(status_code=409, detail="turn was cancelled during connector restoration")
    if session_token is not None:
        session_context = SESSIONS.snapshot(session_token.session_id).context
        selected_accounts = session_context.account_ids or (
            (session_context.account_id,) if session_context.account_id else ()
        )
        if selected_accounts:
            calendar_map = dict(session_context.calendars_by_account)
            if session_context.account_id and session_context.account_id not in calendar_map:
                calendar_map[session_context.account_id] = session_context.calendar_ids
            broker = broker.restrict_to(selected_accounts, calendar_map)
    if session_token is not None:
        context_history = [
            {"role": item.role, "content": item.text}
            for item in SESSIONS.private_history(session_token.session_id)
            if item.role in {"user", "assistant"}
        ]
    else:
        context_history = [
            {"role": str(item.get("role") or ""), "content": str(item.get("content") or item.get("message") or "")}
            for item in STATE.get("chat_history", [])[-12:]
            if isinstance(item, dict)
        ]
        context_history.append({"role": "user", "content": user_message})
    trusted = _trusted_conversation_context(session_token, options, broker)
    assembled = assemble_conversation_context(
        state=STATE,
        history=context_history,
        trusted=trusted,
        retrieval_context=retrieval_context,
    )
    messages = [{"role": "system", "content": assembled.system_instructions}, *assembled.conversation]
    if session_token is not None and not SESSIONS.accepts(session_token):
        raise HTTPException(status_code=409, detail="turn was cancelled before model dispatch")
    try:
        selected_provider = str(options.get("provider") or os.environ.get("METIS_LLM_PROVIDER") or "mock").lower()
        if selected_provider == "ollama" and session_token is not None:
            result = _run_personal_ollama_turn(
                session_token,
                options,
                broker=broker,
                system_instructions=assembled.system_instructions,
                conversation=list(assembled.conversation),
            )
        else:
            result = provider_from_config(options).generate(messages, STATE, options)
    except LLMProviderError as exc:
        if session_token is not None:
            SESSIONS.transition(session_token, TurnStage.FAILED, failure_code="llm_provider_error")
        STATE = reduce_metis_event(
            STATE,
            {"type": "chat_event", "status": "failure", "provider": "llm_router", "reason": str(exc)},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        if session_token is not None and SESSIONS.accepts(session_token):
            SESSIONS.transition(session_token, TurnStage.FAILED, failure_code="llm_unexpected_error")
        STATE = reduce_metis_event(
            STATE,
            {"type": "chat_event", "status": "failure", "provider": "llm_router", "reason": "unexpected provider failure"},
        )
        raise HTTPException(status_code=502, detail="model provider failed unexpectedly") from exc

    assistant_message = result.text
    if not STATE.get("source_grounding_enabled"):
        source_state = STATE.get("source_state", "unsourced")
    elif retrieval is not None and assembled.evidence_supplied:
        source_state = retrieval.source_state
    elif retrieval is not None and retrieval.source_state == "degraded":
        # Availability and grounding are separate facts: preserve a failed
        # retrieval's degraded state, while the label below states explicitly
        # that no evidence reached the model.
        source_state = "degraded"
    else:
        source_state = "unsourced"
    if proposal_queued and not assistant_message.lower().startswith("proposal only"):
        assistant_message = f"Proposal only: {assistant_message}"
    if STATE.get("source_grounding_enabled"):
        if source_state == "sourced" and "source label" not in assistant_message.lower():
            assistant_message = (
                f"{assistant_message}\n\nSource label: sourced context delivered; "
                f"{retrieval.count} BOH context pack(s) were included in the model input via mode "
                f"'{retrieval.mode}'. This records evidence delivery, not independent verification "
                "that every answer claim is supported by that evidence."
            )
        elif source_state == "degraded":
            assistant_message = (
                f"{assistant_message}\n\nSource label: degraded; BOH retrieval was requested but "
                f"unavailable ({retrieval.error}). Treat the above as unsourced."
            )
        elif source_state == "unsourced" and "unsourced" not in assistant_message.lower():
            assistant_message = f"{assistant_message}\n\nSource label: unsourced; no adequate retrieved source was available."
    persisted_assistant_message = _persisted_chat_assistant_message(assistant_message, user_message, options)
    STATE = reduce_metis_event(
        STATE,
        {
            "type": "chat_event",
            "status": "complete",
            "provider": result.provider,
            "model": result.model,
            "user_message": persisted_user_message,
            "assistant_message": persisted_assistant_message,
            "source_state": source_state,
        },
    )
    voice = _finish_chat_turn(session_token, assistant_message, options)
    metadata = dict(result.metadata)
    if retrieval is not None:
        metadata["boh"] = retrieval.to_metadata()
        metadata["boh_evidence_delivery"] = "delivered" if assembled.evidence_supplied else "not_delivered"
        metadata["answer_attribution"] = "unverified"
    return {
        "message": assistant_message,
        "provider": result.provider,
        "model": result.model,
        "proposal_queued": proposal_queued,
        "source_state": source_state,
        "policy": policy.to_dict(),
        "state": STATE,
        "leds": resolve_leds(STATE),
        "metadata": metadata,
        "retrieval": retrieval.to_metadata() if retrieval is not None else None,
        "voice": voice,
        "session": SESSIONS.safe_export(session_token.session_id) if session_token is not None else None,
    }


@app.get("/metis/voice")
def voice() -> dict[str, Any]:
    profile = voice_profile(STATE)
    return {
        **profile,
        "selected_provider": profile["provider"],
        "profile": {
            "id": profile["voice_id"],
            "provider": profile["provider"],
            "can_speak": not profile["output_muted"],
            "boundary": profile["boundary"],
        },
    }


@app.get("/metis/voice/options")
def voice_options_route() -> dict[str, Any]:
    return voice_options(STATE)


@app.get("/metis/voice/audio/{artifact_id}")
def voice_audio(artifact_id: str, session_id: str | None = None) -> Response:
    artifact = AUDIO_ARTIFACTS.consume(artifact_id, session_id=session_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="audio artifact expired or was already consumed")
    return Response(content=artifact.data, media_type=artifact.content_type, headers={"Cache-Control": "no-store"})


@app.get("/metis/playback/next")
def playback_next(client_id: str) -> dict[str, Any]:
    command = PLAYBACK.next_command(client_id)
    if command is None:
        return {"command": None}
    return {
        "command": {
            "kind": command.kind.value,
            "playback_id": command.playback_id,
            "session_id": command.token.session_id,
            "turn_id": command.token.turn_id,
            "generation": command.token.generation,
            "audio_ref": command.audio_ref,
            "content_type": command.content_type,
        }
    }


@app.post("/metis/playback/ack")
def playback_ack(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        state = PlaybackState(str(payload.get("state") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid playback state") from exc
    ack = PlaybackAck(
        playback_id=str(payload.get("playback_id") or ""),
        client_id=str(payload.get("client_id") or ""),
        state=state,
        failure_code=_optional_session_value(payload.get("failure_code")),
    )
    try:
        before = PLAYBACK.get(ack.playback_id)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail="playback acknowledgement rejected") from exc
    accepted = PLAYBACK.acknowledge(ack)
    if not accepted:
        raise HTTPException(status_code=409, detail="playback acknowledgement rejected")
    item = PLAYBACK.get(ack.playback_id)
    duplicate = before.state is state
    if not duplicate and SESSIONS.accepts(item.token):
        if state is PlaybackState.STARTED:
            SESSIONS.transition(item.token, TurnStage.PLAYING)
        elif state is PlaybackState.COMPLETED:
            SESSIONS.transition(item.token, TurnStage.COMPLETED)
        elif state is PlaybackState.FAILED:
            SESSIONS.transition(item.token, TurnStage.FAILED, failure_code=ack.failure_code or "playback_failed")
    return {"status": "accepted", "playback_id": ack.playback_id, "state": state.value, "duplicate": duplicate}


@app.post("/metis/voice/speak")
def voice_speak(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    options = {"voice": {**payload, "enabled": payload.get("enabled", True)}}
    result = speak_text(text, STATE, options)
    _apply_voice_result(result)
    response = {**_voice_response_payload(result), "state": STATE, "leds": resolve_leds(STATE)}
    if not result.ok:
        raise HTTPException(status_code=502, detail=response)
    return response


@app.post("/metis/voice/stop")
def voice_stop(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    session_id = _optional_session_value(payload.get("session_id"))
    if session_id is not None:
        try:
            generation = SESSIONS.cancel(session_id)
            PLAYBACK.cancel_session(session_id, through_generation=generation - 1)
        except KeyError:
            pass
    result = stop_voice(STATE, {"voice": payload})
    _apply_voice_result(result)
    return {**_voice_response_payload(result), "state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/voice/preview")
def voice_preview(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    text = str(payload.get("text") or "Metis voice preview.")
    session_id = _optional_session_value(payload.get("session_id"))
    if session_id is None:
        raise HTTPException(status_code=400, detail="session_id is required for owned browser playback")
    try:
        token = SESSIONS.begin_turn(
            session_id, origin=TurnOrigin.TEXT, initial_stage=TurnStage.SYNTHESIZING
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    options = {"voice": {**payload, "enabled": True, "speak_response": True}}
    try:
        response = _speak_chat_response(text, options, token)
    except Exception as exc:
        if SESSIONS.accepts(token):
            SESSIONS.transition(token, TurnStage.FAILED, failure_code="tts_exception")
        raise HTTPException(status_code=502, detail="speech preview synthesis failed") from exc
    if not response or not response.get("ok"):
        if SESSIONS.accepts(token):
            SESSIONS.transition(token, TurnStage.FAILED, failure_code="tts_failed")
        raise HTTPException(status_code=502, detail=response or {"blocked_reason": "tts_failed"})
    if not response.get("metadata", {}).get("playback_id"):
        if SESSIONS.accepts(token):
            SESSIONS.transition(token, TurnStage.FAILED, failure_code="playback_not_queued")
        raise HTTPException(status_code=502, detail="speech was synthesized but browser playback was not queued")
    return {**response, "state": STATE, "leds": resolve_leds(STATE)}


def _voice_origin_privacy_enabled(options: dict[str, Any]) -> bool:
    return bool(options.get("_metis_voice_origin") and options.get("_redact_voice_transcript_persistence", True))


def _redacted_voice_turn_text(text: str) -> str:
    digest = sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"[voice transcript redacted; text_len={len(text)}; text_hash={digest}]"


def _persisted_chat_user_message(user_message: str, options: dict[str, Any]) -> str:
    if _voice_origin_privacy_enabled(options) or options.get("_metis_private_session"):
        return _redacted_voice_turn_text(user_message)
    return user_message


def _persisted_chat_assistant_message(assistant_message: str, user_message: str, options: dict[str, Any]) -> str:
    if options.get("_metis_private_session"):
        digest = sha1(assistant_message.encode("utf-8")).hexdigest()[:16]
        return f"[private assistant response redacted; text_len={len(assistant_message)}; text_hash={digest}]"
    if not _voice_origin_privacy_enabled(options):
        return assistant_message
    redacted = _redacted_voice_turn_text(user_message)
    return assistant_message.replace(user_message, redacted)


def _voice_command_text(payload: dict[str, Any]) -> str:
    for key in ("text", "transcript", "recognized_text", "command"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(status_code=400, detail="text is required")


def _voice_command_event(text: str, status: str, reason: str | None = None) -> dict[str, Any]:
    event = {
        "type": "provider_event",
        "provider": "stt",
        "status": status,
        "input_mode": "simulated_voice_command",
        "text_len": len(text),
        "text_hash": sha1(text.encode("utf-8")).hexdigest()[:16],
        "text_redacted": True,
    }
    if reason:
        event["reason"] = reason
    return event


def _pending_proposals() -> list[dict[str, Any]]:
    return [
        proposal
        for proposal in STATE.get("approval_queue", [])
        if proposal.get("status") == "pending_review" and proposal.get("review_status", "pending") == "pending"
    ]


def _proposal_readback(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "metis_voice_confirmation_readback.v0.1",
        "proposal_id": proposal.get("proposal_id"),
        "tool_id": proposal.get("tool_id"),
        "proposal_type": proposal.get("proposal_type"),
        "risk_class": proposal.get("risk_class"),
        "side_effect_class": proposal.get("side_effect_class"),
        "dry_run_available": bool(proposal.get("dry_run_available")),
        "execution_allowed": False,
        "readback": (
            f"Proposal {proposal.get('proposal_id')} for {proposal.get('tool_id') or proposal.get('action_class')} "
            f"is pending review. Say 'confirm approve {proposal.get('proposal_id')}', "
            f"'deny {proposal.get('proposal_id')}', or 'cancel {proposal.get('proposal_id')}'."
        ),
    }


def _voice_confirmation_event(text: str, status: str, proposal_id: str | None = None, reason: str | None = None) -> dict[str, Any]:
    event = _voice_command_event(text, status, reason)
    event["voice_confirmation_schema"] = "metis_voice_confirmation.v0.1"
    if proposal_id:
        event["proposal_id"] = proposal_id
    return event


def _parse_voice_confirmation(text: str) -> dict[str, str | None]:
    normalized = re.sub(r"[^a-z0-9_\-\s]+", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    proposal_match = re.search(r"\bproposal_[0-9]{4}_[a-f0-9]{10}\b", normalized)
    proposal_id = proposal_match.group(0) if proposal_match else None
    if any(phrase in normalized for phrase in ("confirm approve", "approve proposal", "approve this proposal")):
        decision = "approved"
    elif any(phrase in normalized for phrase in ("confirm deny", "deny proposal", "reject proposal", "deny this proposal", "reject this proposal")):
        decision = "denied"
    elif any(phrase in normalized for phrase in ("cancel", "stop", "never mind", "nevermind")):
        decision = "cancelled"
    else:
        decision = None
    return {"decision": decision, "proposal_id": proposal_id}


@app.post("/metis/voice/confirm")
def voice_confirm(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    payload = payload or {}
    text = _voice_command_text(payload)
    if not STATE.get("mic_hardware_enabled"):
        event = _voice_confirmation_event(text, "blocked", reason="mic cutoff blocks voice confirmation")
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "input_mode": "simulated_voice_confirmation",
            "reason": "mic cutoff blocks voice confirmation",
            "voice_confirmation": {"recognized": False, "text_redacted": True, "text_len": len(text)},
            "state": STATE,
            "leds": resolve_leds(STATE),
        }
    parsed = _parse_voice_confirmation(text)
    proposal_id = parsed["proposal_id"]
    explicit_proposal_id = proposal_id is not None
    proposal = _proposal_by_id(proposal_id) if proposal_id else None
    pending = _pending_proposals()
    if proposal is None and proposal_id is None and len(pending) == 1:
        proposal = pending[0]
        proposal_id = proposal.get("proposal_id")
    transcript_event = _voice_confirmation_event(text, "confirmation_transcript", proposal_id)
    STATE = reduce_metis_event(STATE, transcript_event)
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    voice_options_payload = options.get("voice") if isinstance(options.get("voice"), dict) else {}
    speak_options = {
        **options,
        "voice": {
            **voice_options_payload,
            "speak_response": voice_options_payload.get("speak_response", True),
            "enabled": voice_options_payload.get("enabled", True),
        },
    }
    if proposal is None:
        message = "I could not identify a pending proposal to confirm. Say the full proposal ID."
        complete_event = _voice_confirmation_event(text, "readback_required", reason="proposal not found")
        STATE = reduce_metis_event(STATE, complete_event)
        voice = _speak_chat_response(message, speak_options)
        return {
            "status": "readback_required",
            "input_mode": "simulated_voice_confirmation",
            "message": message,
            "voice_confirmation": {
                "recognized": True,
                "decision": None,
                "proposal_id": proposal_id,
                "confirmation_accepted": False,
                "requires_explicit_phrase": True,
            },
            "pending_proposals": [_proposal_readback(item) for item in pending[:5]],
            "state": STATE,
            "leds": resolve_leds(STATE),
            "voice": voice,
        }
    readback = _proposal_readback(proposal)
    if proposal.get("review_status", "pending") != "pending":
        message = f"Proposal {proposal_id} has already been reviewed. No voice confirmation was applied."
        complete_event = _voice_confirmation_event(text, "readback_required", proposal_id, "proposal already reviewed")
        STATE = reduce_metis_event(STATE, complete_event)
        voice = _speak_chat_response(message, speak_options)
        return {
            "status": "readback_required",
            "input_mode": "simulated_voice_confirmation",
            "message": message,
            "voice_confirmation": {
                "recognized": True,
                "decision": None,
                "proposal_id": proposal_id,
                "confirmation_accepted": False,
                "requires_explicit_phrase": True,
            },
            "readback": readback,
            "state": STATE,
            "leds": resolve_leds(STATE),
            "voice": voice,
        }
    decision = parsed["decision"]
    if decision is None or (decision in {"approved", "denied", "cancelled"} and not explicit_proposal_id):
        message = readback["readback"]
        reason = "explicit proposal id required" if decision else "explicit confirmation phrase required"
        complete_event = _voice_confirmation_event(text, "readback_required", proposal_id, reason)
        STATE = reduce_metis_event(STATE, complete_event)
        voice = _speak_chat_response(message, speak_options)
        return {
            "status": "readback_required",
            "input_mode": "simulated_voice_confirmation",
            "message": message,
            "voice_confirmation": {
                "recognized": True,
                "decision": None,
                "proposal_id": proposal_id,
                "confirmation_accepted": False,
                "requires_explicit_phrase": True,
                "requires_explicit_proposal_id": True,
            },
            "readback": readback,
            "state": STATE,
            "leds": resolve_leds(STATE),
            "voice": voice,
        }
    if decision == "cancelled":
        message = f"Voice confirmation cancelled for proposal {proposal_id}. The proposal remains pending."
        complete_event = _voice_confirmation_event(text, "cancelled", proposal_id)
        STATE = reduce_metis_event(STATE, complete_event)
        voice = _speak_chat_response(message, speak_options)
        return {
            "status": "cancelled",
            "input_mode": "simulated_voice_confirmation",
            "message": message,
            "voice_confirmation": {
                "recognized": True,
                "decision": "cancelled",
                "proposal_id": proposal_id,
                "confirmation_accepted": False,
                "execution_allowed": False,
            },
            "readback": readback,
            "state": STATE,
            "leds": resolve_leds(STATE),
            "voice": voice,
        }
    reviewed = _review_proposal(proposal_id, decision, {"reason": f"simulated voice confirmation: {decision}"})
    complete_event = _voice_confirmation_event(text, "confirmed", proposal_id)
    STATE = reduce_metis_event(STATE, complete_event)
    reviewed["state"] = STATE
    reviewed["leds"] = resolve_leds(STATE)
    message = f"Voice confirmation recorded: proposal {proposal_id} {decision}. Execution allowed: false."
    voice = _speak_chat_response(message, speak_options)
    return {
        **reviewed,
        "input_mode": "simulated_voice_confirmation",
        "message": message,
        "voice_confirmation": {
            "recognized": True,
            "decision": decision,
            "proposal_id": proposal_id,
            "confirmation_accepted": True,
            "execution_allowed": False,
            "standing_approval": False,
        },
        "readback": readback,
        "voice": voice,
    }


@app.post("/metis/voice/command")
def voice_command(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    payload = payload or {}
    text = _voice_command_text(payload)
    if not STATE.get("mic_hardware_enabled"):
        event = _voice_command_event(text, "blocked", "mic cutoff blocks voice command")
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "input_mode": "simulated_voice_command",
            "reason": "mic cutoff blocks voice command",
            "voice_command": {"recognized": False, "text_redacted": True, "text_len": len(text)},
            "state": STATE,
            "leds": resolve_leds(STATE),
        }
    transcript_event = _voice_command_event(text, "transcript")
    STATE = reduce_metis_event(STATE, transcript_event)
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    voice_options_payload = options.get("voice") if isinstance(options.get("voice"), dict) else {}
    options = {
        **options,
        "_metis_voice_origin": True,
        "_redact_voice_transcript_persistence": True,
        "voice": {
            **voice_options_payload,
            "speak_response": voice_options_payload.get("speak_response", True),
            "enabled": voice_options_payload.get("enabled", True),
        },
    }
    chat_payload: dict[str, Any] = {"message": text, "options": options}
    if isinstance(payload.get("_turn_token"), TurnToken):
        chat_payload["_turn_token"] = payload["_turn_token"]
    response = chat(chat_payload)
    complete_event = _voice_command_event(text, "complete")
    STATE = reduce_metis_event(STATE, complete_event)
    response["state"] = STATE
    response["leds"] = resolve_leds(STATE)
    response["input_mode"] = "simulated_voice_command"
    response["voice_command"] = {
        "recognized": True,
        "text_redacted": True,
        "text_len": len(text),
        "route": "metis_chat",
        "speech_reply_requested": bool(options["voice"].get("speak_response")),
    }
    return response


def _voice_response_payload(result: VoiceResult) -> dict[str, Any]:
    payload = result.to_dict()
    payload["speech_blocked"] = bool(result.blocked_reason)
    payload["block_reason"] = result.blocked_reason.replace(" ", "_") if result.blocked_reason else None
    return payload


def _audio_input_event(
    status: str,
    *,
    block_reason: str | None = None,
    capture=None,
    stt_result=None,
    trigger: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "provider_event",
        "provider": "audio_input",
        "status": status,
        "input_mode": "simulated_audio_input",
        "audio_input_schema": "audio_input_adapter.v0.1",
    }
    if block_reason:
        event["block_reason"] = block_reason
    if trigger:
        event["listen_trigger"] = trigger
    if capture is not None:
        event["audio_duration_ms"] = capture.audio_duration_ms
        event["frame_count"] = capture.frame_count
        event["sample_rate"] = capture.sample_rate
        event["captured"] = capture.captured
        event["audio_provider_id"] = capture.provider_id
    if stt_result is not None:
        event["text_len"] = stt_result.text_len
        event["text_hash"] = stt_result.text_hash
        event["text_redacted"] = True
        event["stt_provider_id"] = stt_result.provider_id
    return event


def _audio_capture_governance(*, require_listen_mode: bool = False) -> tuple[bool, str | None]:
    """Return (allowed, block_reason).

    Enforces: mic_hardware_enabled -> audio_input_enabled
              -> [listen_mode != no_listen  (when require_listen_mode)]
              -> power_state == awake.
    Order matches buildspec section 2.5/section 3.4 precedence: hardware cutoff is highest.
    """
    if not STATE.get("mic_hardware_enabled"):
        return False, "mic_hardware_cutoff"
    if not STATE.get("audio_input_enabled"):
        return False, "audio_input_disabled"
    if require_listen_mode and STATE.get("listen_mode", "no_listen") == "no_listen":
        return False, "listen_mode_no_listen"
    if STATE.get("power_state") != "awake":
        return False, "standby_blocks_capture"
    return True, None


@app.get("/metis/audio/input")
def audio_input_status() -> dict[str, Any]:
    import os as _os

    allow_local_mic = _os.environ.get("METIS_AUDIO_ALLOW_LOCAL_MIC", "").strip().lower() in {
        "1", "true", "yes", "on", "enabled",
    }
    selected_provider = "local_mic" if allow_local_mic else "simulated"
    audio_provider = audio_input_provider_from_config(selected_provider)

    stt_engine = _os.environ.get("METIS_STT_ENGINE", "simulated")
    stt_allow_local = _local_stt_allowed()
    stt_provider = stt_provider_from_config(stt_engine)
    stt_model = _os.environ.get("METIS_STT_MODEL", "small")

    faster_whisper_available = False
    if stt_allow_local:
        try:
            import faster_whisper  # noqa: PLC0415
            faster_whisper_available = True
        except ImportError:
            pass

    input_devices: list[dict[str, Any]] = []
    sounddevice_available = False
    if allow_local_mic and STATE.get("mic_hardware_enabled"):
        try:
            import sounddevice as sd  # noqa: PLC0415

            sounddevice_available = True
            for idx, device in enumerate(sd.query_devices()):
                if device.get("max_input_channels", 0) > 0:
                    input_devices.append({"index": idx, "name": str(device.get("name", ""))})
        except Exception:
            pass

    return {
        "audio_input_adapter_version": "audio_input_adapter.v0.1",
        "stt_engine_version": "stt_engine.v0.1",
        "audio_input_state": STATE.get("audio_input_state"),
        "audio_input_enabled": STATE.get("audio_input_enabled"),
        "listen_mode": STATE.get("listen_mode"),
        "listen_session_active": STATE.get("listen_session_active"),
        "wake_phrase": STATE.get("wake_phrase"),
        "last_listen_trigger": STATE.get("last_listen_trigger"),
        "mic_hardware_enabled": STATE.get("mic_hardware_enabled"),
        "last_audio_capture": STATE.get("last_audio_capture"),
        "allow_local_mic": allow_local_mic,
        "sounddevice_available": sounddevice_available,
        "input_devices": input_devices,
        "selected_audio_provider": selected_provider,
        "stt_engine": stt_engine,
        "stt_allow_local": stt_allow_local,
        "faster_whisper_available": faster_whisper_available,
        "stt_model": stt_model,
        "selected_stt_provider": stt_engine,
        "audio_provider_health": audio_provider.health(),
        "stt_provider_health": stt_provider.health(),
        "trigger_routes": {
            "ptt": "POST /metis/audio/ptt",
            "wake": "POST /metis/audio/wake",
            "listen": "POST /metis/audio/listen",
        },
        "providers": {
            "audio_input": ["none", "simulated", "local_mic"],
            "stt": ["none", "simulated", "faster_whisper", "local_whisper", "vosk", "openai_whisper", "whispercpp"],
            "wake_word": ["local_wake_word (scaffold, not_enabled)"],
        },
        "boundary": (
            "Capture fail-closed behind mic_hardware_enabled; "
            "event-driven and bounded - one utterance per explicit PTT or wake trigger, never always-listening; "
            "real mic requires METIS_AUDIO_ALLOW_LOCAL_MIC=true AND mic_hardware_enabled AND audio_input_enabled; "
            "real STT requires METIS_STT_ALLOW_LOCAL=true AND faster-whisper installed; "
            "mic_hardware_enabled should ultimately be driven by the physical cutoff switch over the bridge "
            "(software flag is an interim proxy)."
        ),
    }


@app.post("/metis/audio/input/capture")
def audio_input_capture(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    payload = payload or {}

    allowed, block_reason = _audio_capture_governance()
    if not allowed:
        event = _audio_input_event("blocked", block_reason=block_reason)
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "block_reason": block_reason,
            "captured": False,
            "capture": None,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    provider_name = str(payload.get("provider") or "simulated")
    hint = str(payload.get("hint") or "default")
    duration_ms = int(payload.get("duration_ms") or 1000)
    context = CaptureContext(hint=hint, fixture_id=hint, duration_ms=duration_ms)

    audio_provider = audio_input_provider_from_config(provider_name)
    capture_result = audio_provider.capture(context)

    if not capture_result.captured:
        event = _audio_input_event("blocked", block_reason=capture_result.block_reason or "capture_failed", capture=capture_result)
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "block_reason": capture_result.block_reason,
            "captured": False,
            "capture": capture_result.to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    event = _audio_input_event("complete", capture=capture_result)
    STATE = reduce_metis_event(STATE, event)
    return {
        "status": "captured",
        "capture": capture_result.to_dict(),
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


@app.post("/metis/audio/transcribe")
def audio_transcribe(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    payload = payload or {}

    allowed, block_reason = _audio_capture_governance()
    if not allowed:
        event = _audio_input_event("blocked", block_reason=block_reason)
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "block_reason": block_reason,
            "stt": None,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    provider_name = str(payload.get("stt_provider") or "simulated")
    hint = str(payload.get("hint") or "default")
    stt = stt_provider_from_config(provider_name)
    stt_context = {"hint": hint}
    stt_result = stt.transcribe(None, stt_context)

    event = _audio_input_event("transcribing", stt_result=stt_result)
    STATE = reduce_metis_event(STATE, event)
    complete_event = _audio_input_event("complete", stt_result=stt_result)
    STATE = reduce_metis_event(STATE, complete_event)

    return {
        "status": "transcribed",
        "stt": stt_result.to_dict(),
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


def _run_stt_route_cycle(
    capture_result: Any,
    stt_name: str,
    stt_context: dict[str, Any],
    options: dict[str, Any],
    trigger: str,
    turn_token: TurnToken | None = None,
) -> dict[str, Any]:
    """STT transcription + 0BE routing fork. Caller must have already captured audio.

    Emits transcribing and complete events; routes recognized text to voice_confirm or
    voice_command via the 0BE fork; returns the full listen_complete response dict.
    Raw text is never stored; STTResult.to_dict() exposes only text_len/text_hash.
    """
    global STATE

    if turn_token is not None and not SESSIONS.accepts(turn_token):
        return {"status": "cancelled", "voice_command": None, "state": STATE, "leds": resolve_leds(STATE)}
    stt = stt_provider_from_config(stt_name)
    transcribing_event = _audio_input_event("transcribing", capture=capture_result, trigger=trigger)
    STATE = reduce_metis_event(STATE, transcribing_event)
    try:
        stt_result = stt.transcribe(capture_result, stt_context)
    except Exception:
        if turn_token is not None and SESSIONS.accepts(turn_token):
            SESSIONS.transition(turn_token, TurnStage.FAILED, failure_code="stt_failed")
        raise

    if turn_token is not None and not SESSIONS.accepts(turn_token):
        return {"status": "cancelled", "voice_command": None, "state": STATE, "leds": resolve_leds(STATE)}

    recognized_text = get_recognized_text(stt_result)

    if not recognized_text.strip():
        if turn_token is not None and SESSIONS.accepts(turn_token):
            SESSIONS.transition(turn_token, TurnStage.FAILED, failure_code="no_text_recognized")
        complete_event = _audio_input_event(
            "complete", capture=capture_result, stt_result=stt_result, trigger=trigger
        )
        STATE = reduce_metis_event(STATE, complete_event)
        return {
            "status": "no_text_recognized",
            "capture": capture_result.to_dict(),
            "stt": stt_result.to_dict(),
            "voice_command": None,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    if turn_token is not None:
        if not SESSIONS.set_transcript(turn_token, recognized_text):
            return {"status": "cancelled", "voice_command": None, "state": STATE, "leds": resolve_leds(STATE)}
        if not SESSIONS.transition(turn_token, TurnStage.THINKING):
            return {"status": "cancelled", "voice_command": None, "state": STATE, "leds": resolve_leds(STATE)}

    parsed_intent = _parse_voice_confirmation(recognized_text)
    if _pending_proposals() and (
        parsed_intent["decision"] is not None or parsed_intent["proposal_id"] is not None
    ):
        vc_response = voice_confirm({"text": recognized_text, "options": options})
        route_used = "voice_confirm"
        if turn_token is not None and SESSIONS.accepts(turn_token):
            SESSIONS.transition(turn_token, TurnStage.COMPLETED)
    else:
        vc_response = voice_command({"text": recognized_text, "options": options, "_turn_token": turn_token})
        route_used = "voice_command"

    complete_event = _audio_input_event(
        "complete", capture=capture_result, stt_result=stt_result, trigger=trigger
    )
    STATE = reduce_metis_event(STATE, complete_event)
    vc_response["state"] = STATE
    vc_response["leds"] = resolve_leds(STATE)

    return {
        "status": "listen_complete",
        "capture": capture_result.to_dict(),
        "stt": stt_result.to_dict(),
        "voice_command": vc_response,
        "route_used": route_used,
        # Returned only to the requesting local browser for its private tab
        # transcript. Canonical state/events and safe exports remain redacted.
        "recognized_text": recognized_text,
        "state": STATE,
        "leds": resolve_leds(STATE),
    }


def _run_listen_cycle(payload: dict[str, Any], trigger: str) -> dict[str, Any]:
    """One bounded capture -> STT -> voice_command cycle.

    Governance must be verified by the caller before invoking.
    trigger is "listen", "ptt", or "wake"; recorded in emitted events and
    in last_audio_capture.listen_trigger but never in state/events as raw text.
    Adds no execution authority: recognized text enters POST /metis/voice/command only.
    """
    global STATE
    import os as _os

    provider_name = str(payload.get("provider") or "simulated")
    hint = str(payload.get("hint") or "default")
    duration_ms = int(payload.get("duration_ms") or 1000)
    context = CaptureContext(hint=hint, fixture_id=hint, duration_ms=duration_ms)

    audio_provider = audio_input_provider_from_config(provider_name)
    capturing_event = _audio_input_event("capturing", trigger=trigger)
    STATE = reduce_metis_event(STATE, capturing_event)
    capture_result = audio_provider.capture(context)

    if not capture_result.captured:
        fail_event = _audio_input_event(
            "blocked",
            block_reason=capture_result.block_reason or "capture_failed",
            capture=capture_result,
            trigger=trigger,
        )
        STATE = reduce_metis_event(STATE, fail_event)
        return {
            "status": "blocked",
            "block_reason": capture_result.block_reason,
            "captured": False,
            "capture": capture_result.to_dict(),
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    stt_name = str(payload.get("stt_provider") or _os.environ.get("METIS_STT_ENGINE", "simulated"))
    hint = str(payload.get("hint") or "default")
    stt_context = {"hint": hint}
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}

    return _run_stt_route_cycle(capture_result, stt_name, stt_context, options, trigger)


@app.post("/metis/audio/listen")
def audio_listen(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Orchestrated path: capture -> transcribe -> forward to voice_command.

    Respects the full governance chain (mic cutoff, audio_input_enabled, listen_mode,
    power_state). Adds no new execution authority.
    """
    global STATE
    payload = payload or {}

    allowed, block_reason = _audio_capture_governance(require_listen_mode=True)
    if not allowed:
        event = _audio_input_event("blocked", block_reason=block_reason)
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "block_reason": block_reason,
            "captured": False,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    return _run_listen_cycle(payload, "listen")


@app.post("/metis/audio/ptt")
def audio_ptt(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Push-to-talk control. Models the radio PTT button.

    action=press: validates push_to_talk mode + full governance; marks session active.
                  Does NOT start a thread or begin capture - capture happens on release.
    action=release: if session active + correct mode + governance passes, runs exactly
                    one bounded _run_listen_cycle, then clears the session.
                    A release without a prior press (listen_session_active=False) or in
                    the wrong mode is a safe no-op (no capture, no routing).

    Hard boundaries: event-driven and bounded; one utterance per trigger; never always-on.
    """
    global STATE
    payload = payload or {}
    action = str(payload.get("action") or "").strip().lower()

    if action not in {"press", "release", "cancel"}:
        raise HTTPException(status_code=400, detail="action must be 'press', 'release', or 'cancel'")

    if action == "cancel":
        if STATE.get("listen_session_active"):
            STATE = reduce_metis_event(STATE, _audio_input_event("ptt_released"))
        return {
            "status": "ptt_cancelled",
            "listen_session_active": False,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    if action == "press":
        if STATE.get("listen_mode") != "push_to_talk":
            return {
                "status": "wrong_mode",
                "block_reason": "listen_mode_not_push_to_talk",
                "listen_mode": STATE.get("listen_mode"),
                "state": STATE,
                "leds": resolve_leds(STATE),
            }
        allowed, block_reason = _audio_capture_governance()
        if not allowed:
            event = _audio_input_event("blocked", block_reason=block_reason)
            STATE = reduce_metis_event(STATE, event)
            return {
                "status": "blocked",
                "block_reason": block_reason,
                "state": STATE,
                "leds": resolve_leds(STATE),
            }
        ptt_event = _audio_input_event("ptt_pressed")
        STATE = reduce_metis_event(STATE, ptt_event)
        return {
            "status": "ptt_pressed",
            "listen_session_active": STATE.get("listen_session_active"),
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    # action == "release"
    if not STATE.get("listen_session_active") or STATE.get("listen_mode") != "push_to_talk":
        return {
            "status": "ptt_release_ignored",
            "listen_session_active": STATE.get("listen_session_active"),
            "listen_mode": STATE.get("listen_mode"),
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    allowed, block_reason = _audio_capture_governance()
    if not allowed:
        release_event = _audio_input_event("ptt_released")
        STATE = reduce_metis_event(STATE, release_event)
        block_event = _audio_input_event("blocked", block_reason=block_reason)
        STATE = reduce_metis_event(STATE, block_event)
        return {
            "status": "blocked",
            "block_reason": block_reason,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    if str(payload.get("provider") or "simulated") == "local_mic":
        # LocalMicAudioInput is a fixed-duration recorder. Starting it after
        # release would violate held-to-talk semantics, so keep that provider
        # disabled on this route until a streaming capture handle is available.
        STATE = reduce_metis_event(STATE, _audio_input_event("ptt_released"))
        return {
            "status": "unsupported_local_ptt",
            "block_reason": "local_mic_requires_press_time_capture",
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    result = _run_listen_cycle(payload, "ptt")
    release_event = _audio_input_event("ptt_released")
    STATE = reduce_metis_event(STATE, release_event)
    result["state"] = STATE
    result["leds"] = resolve_leds(STATE)
    result["trigger"] = "ptt"
    return result


@app.post("/metis/audio/wake")
def audio_wake(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Simulated wake-word detection endpoint.

    The caller supplies text containing the wake phrase (simulating what a real
    wake-word engine would deliver). If the text starts with the configured
    wake_phrase AND listen_mode==wake_word AND governance passes, the phrase is
    stripped and one bounded _run_listen_cycle runs on the remainder.

    No real wake-word engine import occurs. LocalWakeWordDetector is a scaffold only.

    Hard boundaries: event-driven; one utterance per trigger; never always-listening.
    """
    global STATE
    payload = payload or {}
    text = str(payload.get("text") or "").strip()

    if STATE.get("listen_mode") != "wake_word":
        event = _audio_input_event("wake_not_detected", block_reason="listen_mode_not_wake_word")
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "wake_not_detected",
            "block_reason": "listen_mode_not_wake_word",
            "listen_mode": STATE.get("listen_mode"),
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    allowed, block_reason = _audio_capture_governance()
    if not allowed:
        event = _audio_input_event("blocked", block_reason=block_reason)
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "block_reason": block_reason,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    wake_phrase = str(STATE.get("wake_phrase") or "hey metis").lower().strip()
    if not text.lower().startswith(wake_phrase):
        event = _audio_input_event("wake_not_detected", block_reason="wake_phrase_not_detected")
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "wake_not_detected",
            "block_reason": "wake_phrase_not_detected",
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    remainder = text[len(wake_phrase):].strip()

    wake_event = _audio_input_event("wake_triggered")
    STATE = reduce_metis_event(STATE, wake_event)

    cycle_payload = {**payload, "hint": remainder or payload.get("hint") or "default"}
    result = _run_listen_cycle(cycle_payload, "wake")
    result["trigger"] = "wake"
    result["wake_phrase_detected"] = True
    return result


def _normalized_upload_content_type(audio: UploadFile) -> str:
    return (audio.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()


def _validate_browser_ptt_upload(content_type: str, wav_bytes: bytes) -> None:
    if not wav_bytes:
        raise HTTPException(status_code=400, detail="audio upload is empty")
    if len(wav_bytes) > BROWSER_PTT_MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"audio upload exceeds {BROWSER_PTT_MAX_UPLOAD_BYTES} byte local prototype limit",
        )
    if content_type not in BROWSER_PTT_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"unsupported audio content type: {content_type}")
    if content_type in BROWSER_PTT_WAV_TYPES and not (
        len(wav_bytes) >= 44 and wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"
    ):
        raise HTTPException(status_code=400, detail="invalid WAV upload")


@app.post("/metis/setup/audio/transcribe")
async def setup_audio_transcribe(
    audio: UploadFile = File(...),
    stt_provider: str = Form(""),
) -> dict[str, Any]:
    """Run one explicit, in-memory microphone/STT check without invoking the LLM."""
    if not STATE.get("mic_hardware_enabled"):
        raise HTTPException(status_code=409, detail="mic_hardware_cutoff")
    if STATE.get("power_state") != "awake":
        raise HTTPException(status_code=409, detail="standby_blocks_capture")
    content_type = _normalized_upload_content_type(audio)
    wav_bytes = await audio.read(BROWSER_PTT_MAX_UPLOAD_BYTES + 1)
    _validate_browser_ptt_upload(content_type, wav_bytes)
    capture = CaptureResult(
        provider_id="browser_setup",
        status="captured",
        captured=True,
        audio_duration_ms=0,
        audio_levels=[],
        audio_spectrum_frames=[],
        frame_count=0,
        sample_rate=16000,
    )
    capture._wav_bytes = wav_bytes
    provider_name = stt_provider.strip() or os.environ.get("METIS_STT_ENGINE", "faster_whisper")
    try:
        result = await run_in_threadpool(
            stt_provider_from_config(provider_name).transcribe, capture, {}
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"speech-to-text failed: {type(exc).__name__}") from exc
    transcript = get_recognized_text(result).strip()
    return {
        "status": "transcribed" if transcript else "no_text_recognized",
        "provider": result.provider_id,
        "transcript": transcript,
        "stt": result.to_dict(),
        "persisted": False,
        "llm_invoked": False,
    }


@app.post("/metis/audio/browser_ptt")
async def audio_browser_ptt(
    audio: UploadFile = File(...),
    stt_provider: str = Form(""),
    stt_hint: str = Form(""),
    options_json: str = Form("{}"),
) -> dict[str, Any]:
    """Browser held-to-talk - accepts a multipart audio upload from the dashboard and
    routes it through the existing STT + 0BE confirmation routing cycle.

    Governance gate order (same as audio_ptt):
      mic_hardware_enabled -> audio_input_enabled -> listen_mode==push_to_talk
      -> power_state==awake

    Hard boundaries: raw audio bytes and transcript are never persisted; no background
    listener; no autonomous execution; listen_mode must be push_to_talk.
    """
    global STATE
    import json as _json
    import os as _os

    if STATE.get("listen_mode") != "push_to_talk":
        return {
            "status": "wrong_mode",
            "block_reason": "listen_mode_not_push_to_talk",
            "listen_mode": STATE.get("listen_mode"),
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    allowed, block_reason = _audio_capture_governance()
    if not allowed:
        event = _audio_input_event("blocked", block_reason=block_reason)
        STATE = reduce_metis_event(STATE, event)
        return {
            "status": "blocked",
            "block_reason": block_reason,
            "state": STATE,
            "leds": resolve_leds(STATE),
        }

    try:
        options: dict[str, Any] = _json.loads(options_json) if options_json.strip() else {}
        if not isinstance(options, dict):
            options = {}
    except Exception:
        options = {}

    session_id = _optional_session_value(options.get("session_id"))
    turn_token: TurnToken | None = None
    if session_id is not None:
        try:
            turn_token = SESSIONS.begin_turn(
                session_id,
                origin=TurnOrigin.VOICE,
                user_text=None,
                initial_stage=TurnStage.TRANSCRIBING,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    content_type = _normalized_upload_content_type(audio)
    wav_bytes = await audio.read(BROWSER_PTT_MAX_UPLOAD_BYTES + 1)
    try:
        _validate_browser_ptt_upload(content_type, wav_bytes)
    except HTTPException:
        if turn_token is not None and SESSIONS.accepts(turn_token):
            SESSIONS.transition(turn_token, TurnStage.FAILED, failure_code="invalid_audio")
        raise

    capture_result = CaptureResult(
        provider_id="browser_ptt",
        status="captured",
        captured=True,
        audio_duration_ms=0,
        audio_levels=[],
        audio_spectrum_frames=[],
        frame_count=0,
        sample_rate=16000,
    )
    capture_result._wav_bytes = wav_bytes  # in-memory only; excluded from to_dict()

    capturing_event = _audio_input_event("capturing", trigger="browser_ptt")
    STATE = reduce_metis_event(STATE, capturing_event)

    stt_name = stt_provider or _os.environ.get("METIS_STT_ENGINE", "simulated")
    hint = stt_hint or "default"
    stt_context = {"hint": hint}

    result = await run_in_threadpool(
        _run_stt_route_cycle,
        capture_result,
        stt_name,
        stt_context,
        options,
        "browser_ptt",
        turn_token,
    )
    if STATE.get("listen_session_active"):
        STATE = reduce_metis_event(STATE, _audio_input_event("ptt_released"))
        result["state"] = STATE
        result["leds"] = resolve_leds(STATE)
    return result


@app.post("/metis/replay")
def replay(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    events = payload.get("events")
    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="events must be a list")
    initial_state = baseline_state() if payload.get("reset", True) else STATE
    try:
        STATE = replay_events(initial_state, events)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"state": STATE, "leds": resolve_leds(STATE), "event_count": len(events)}


@app.post("/metis/state/reset")
def reset_state() -> dict[str, Any]:
    global STATE, SCENARIO_RESULTS
    STATE = baseline_state()
    SCENARIO_RESULTS = []
    return {"state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/scenario/run")
def scenario_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global SCENARIO_RESULTS
    payload = payload or {}
    scenario_id = payload.get("scenario_id")
    if scenario_id:
        if scenario_id not in SCENARIOS:
            raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_id}")
        result = run_scenario(scenario_id)
        SCENARIO_RESULTS.append(result)
        return result
    SCENARIO_RESULTS = run_all_scenarios()
    return {"results": SCENARIO_RESULTS, "passed": all(item["passed"] for item in SCENARIO_RESULTS)}


@app.get("/metis/scenario/results")
def scenario_results() -> dict[str, Any]:
    return {"results": SCENARIO_RESULTS}


@app.get("/metis/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if STATE.get("active_failure") is None else "degraded",
        "active_failure": STATE.get("active_failure"),
        "failures": FAILURE_TABLE,
        "readiness": calculate_readiness(),
        "hardware_parity_manifest": HARDWARE_PARITY_MANIFEST,
    }


@app.get("/metis/adapters")
def adapters() -> dict[str, Any]:
    return {"adapters": STATE["input_adapters"]}


@app.get("/metis/providers")
def providers() -> dict[str, Any]:
    return provider_catalog()


@app.post("/metis/providers/{operation_id}/invoke")
def provider_invoke(operation_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    try:
        result = invoke_provider(operation_id, payload)
    except ProviderHarnessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    applied: list[dict[str, Any]] = []
    for event in result["events"]:
        STATE = reduce_metis_event(STATE, event)
        applied.append(event)
    return {**result, "applied_events": applied, "state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/adapters/{adapter_id}/set_health")
def set_adapter_health(adapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    if adapter_id not in STATE["input_adapters"]:
        raise HTTPException(status_code=404, detail=f"unknown adapter: {adapter_id}")
    event = {
        "type": "adapter_health",
        "adapter_id": adapter_id,
        "health": payload.get("health", "ok"),
        "enabled": payload.get("enabled", payload.get("health", "ok") == "ok"),
        "mode": payload.get("mode"),
    }
    STATE = reduce_metis_event(STATE, event)
    return {"adapter": STATE["input_adapters"][adapter_id], "state": STATE}


@app.post("/metis/failures/{failure_id}/trigger")
def trigger_failure(failure_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    if failure_id not in FAILURE_TABLE:
        raise HTTPException(status_code=404, detail=f"unknown failure: {failure_id}")
    payload = payload or {}
    STATE = reduce_metis_event(STATE, {"type": "failure_event", "failure_id": failure_id, "reason": payload.get("reason")})
    return {"state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/failures/clear")
def clear_all_failures() -> dict[str, Any]:
    global STATE
    STATE = clear_failures(STATE)
    return {"state": STATE, "leds": resolve_leds(STATE)}


@app.get("/metis/mcp/status")
def mcp_access_status() -> dict[str, Any]:
    from .mcp_access import mcp_status

    return mcp_status()


@app.get("/metis/mcp/tools")
def mcp_access_tools() -> dict[str, Any]:
    from .mcp_access import list_mcp_tools

    return list_mcp_tools()


@app.post("/metis/mcp/{server_id}/tools/{tool_name}/call")
def mcp_access_call(server_id: str, tool_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from .mcp_access import MCPAccessError, call_configured_mcp_tool

    payload = payload or {}
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    try:
        return {"mcp": call_configured_mcp_tool(server_id, tool_name, arguments)}
    except MCPAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
