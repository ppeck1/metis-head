from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .boh_link import (
    LINK_AUTH_FAILED,
    get_link_state,
    start_background_link,
    stop_background_link,
)
from .boh_retrieval import BOHRetrievalResult, boh_config_from_env, render_context, retrieve_boh_context
from .bridge import HARDWARE_PARITY_MANIFEST
from .governance import POLICY_VERSION, classify_intent, should_queue_proposal
from .leds import resolve_leds
from .llm_providers import LLMProviderError, governed_messages, list_ollama_models, probe_llm_provider, provider_from_config
from .personality import personality_profile
from .provider_harness import ProviderHarnessError, invoke_provider, provider_catalog
from .readiness import calculate_readiness
from .reducer import clear_failures, reduce_metis_event, replay_events
from .scenarios import SCENARIOS, run_all_scenarios, run_scenario
from .schemas import FAILURE_TABLE, baseline_state


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


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")


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


@app.get("/metis/state")
def get_state() -> dict[str, Any]:
    return {"state": STATE, "leds": resolve_leds(STATE), "readiness": calculate_readiness()}


@app.get("/metis/export")
def export_state() -> dict[str, Any]:
    return {
        "state": STATE,
        "leds": resolve_leds(STATE),
        "readiness": calculate_readiness(),
        "event_log": STATE.get("event_log", []),
        "export_schema": "metis_export.v0.1",
    }


@app.get("/metis/proposals")
def proposals() -> dict[str, Any]:
    return {"proposals": STATE.get("approval_queue", []), "pending_approval_count": STATE.get("pending_approval_count", 0)}


@app.get("/metis/llm/options")
def llm_options(base_url: str | None = None) -> dict[str, Any]:
    import os

    ollama_base_url = base_url or os.environ.get("METIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    return {
        "selected_provider": os.environ.get("METIS_LLM_PROVIDER", "mock"),
        "ollama_base_url": ollama_base_url,
        "ollama_model": os.environ.get("METIS_OLLAMA_MODEL"),
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


@app.post("/metis/chat")
def chat(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    user_message = payload.get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    proposal_queued = False
    policy = classify_intent(user_message, STATE)
    if should_queue_proposal(policy, STATE):
        STATE = reduce_metis_event(
            STATE,
            {"type": "user_intent", "intent": user_message, "action_class": policy.action_class, "policy": policy.to_dict()},
        )
        proposal_queued = True

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

    messages = governed_messages(user_message, STATE, STATE.get("chat_history", []), retrieval_context)
    try:
        result = provider_from_config(options).generate(messages, STATE, options)
    except LLMProviderError as exc:
        STATE = reduce_metis_event(
            STATE,
            {"type": "chat_event", "status": "failure", "provider": "llm_router", "reason": str(exc)},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    assistant_message = result.text
    if not STATE.get("source_grounding_enabled"):
        source_state = STATE.get("source_state", "unsourced")
    elif retrieval is not None:
        source_state = retrieval.source_state
    else:
        source_state = "unsourced"
    if proposal_queued and not assistant_message.lower().startswith("proposal only"):
        assistant_message = f"Proposal only: {assistant_message}"
    if STATE.get("source_grounding_enabled"):
        if source_state == "sourced" and "source label" not in assistant_message.lower():
            assistant_message = (
                f"{assistant_message}\n\nSource label: sourced; grounded on "
                f"{retrieval.count} BOH context pack(s) via mode '{retrieval.mode}'."
            )
        elif source_state == "degraded":
            assistant_message = (
                f"{assistant_message}\n\nSource label: degraded; BOH retrieval was requested but "
                f"unavailable ({retrieval.error}). Treat the above as unsourced."
            )
        elif source_state == "unsourced" and "unsourced" not in assistant_message.lower():
            assistant_message = f"{assistant_message}\n\nSource label: unsourced; no adequate retrieved source was available."
    STATE = reduce_metis_event(
        STATE,
        {
            "type": "chat_event",
            "status": "complete",
            "provider": result.provider,
            "model": result.model,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "source_state": source_state,
        },
    )
    metadata = dict(result.metadata)
    if retrieval is not None:
        metadata["boh"] = retrieval.to_metadata()
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
    }


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
