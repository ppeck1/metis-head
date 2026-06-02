from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

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
from .llm_providers import LLMProviderError, governed_messages, list_ollama_models, probe_llm_provider, provider_from_config
from .personality import personality_profile
from .provider_harness import ProviderHarnessError, invoke_provider, provider_catalog
from .read_only_tools import ReadOnlyToolError, execute_filesystem_read, execute_git_status
from .readiness import calculate_readiness
from .reducer import clear_failures, reduce_metis_event, replay_events
from .scenarios import SCENARIOS, run_all_scenarios, run_scenario
from .schemas import FAILURE_TABLE, baseline_state, utc_now
from .sim_manifest import build_sim_test_manifest
from .tool_registry import ToolRegistryError, build_tool_proposal_event, dry_run_tool, execute_tool, get_tool, list_tools, route_tool_request
from .voice import VoiceResult, speak_text, stop_voice, voice_options, voice_profile


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
def proposals() -> dict[str, Any]:
    return {"proposals": STATE.get("approval_queue", []), "pending_approval_count": STATE.get("pending_approval_count", 0)}


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


@app.post("/metis/proposals/{proposal_id}/request_execution")
def request_proposal_execution(proposal_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global STATE
    proposal = _proposal_by_id(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    reason = ""
    if isinstance(payload, dict) and isinstance(payload.get("reason"), str):
        reason = payload["reason"]
    dry_run_receipt = None
    read_only_result = None
    if proposal.get("review_status") == "approved" and proposal.get("tool_id") == "time.now":
        try:
            read_only_result = dry_run_tool("time.now", proposal.get("tool_arguments") or {})["result"]
        except ToolRegistryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif proposal.get("review_status") == "approved" and proposal.get("tool_id") == "git.status":
        try:
            read_only_result = execute_git_status(proposal.get("tool_arguments") or {})
        except ReadOnlyToolError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif proposal.get("review_status") == "approved" and proposal.get("tool_id") == "filesystem.read":
        try:
            read_only_result = execute_filesystem_read(proposal.get("tool_arguments") or {})
        except ReadOnlyToolError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif proposal.get("review_status") == "approved" and proposal.get("dry_run_available") and proposal.get("side_effect_class") == "none":
        try:
            dry_run_receipt = dry_run_tool(str(proposal.get("tool_id")), proposal.get("tool_arguments") or {})
        except ToolRegistryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    event = {
        "type": "execution_request",
        "proposal_id": proposal_id,
        "reason": reason,
        "requested_at": utc_now(),
    }
    if dry_run_receipt:
        event["dry_run_receipt"] = dry_run_receipt
    if read_only_result:
        event["read_only_result"] = read_only_result
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


def _apply_voice_result(result: VoiceResult) -> None:
    global STATE
    for event in result.events:
        STATE = reduce_metis_event(STATE, event)


def _speak_chat_response(assistant_message: str, options: dict[str, Any]) -> dict[str, Any] | None:
    voice_options = options.get("voice") if isinstance(options.get("voice"), dict) else {}
    if not voice_options.get("speak_response"):
        return None
    speak_options = {"voice": {**voice_options, "enabled": True}}
    voice_result = speak_text(assistant_message, STATE, speak_options)
    _apply_voice_result(voice_result)
    return _voice_response_payload(voice_result)


@app.post("/metis/chat")
def chat(payload: dict[str, Any]) -> dict[str, Any]:
    global STATE
    user_message = payload.get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    proposal_queued = False
    policy = classify_intent(user_message, STATE)
    tool_result = None
    try:
        tool_result = _handle_chat_tool_request(user_message, options)
    except ToolRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if tool_result is None and should_queue_proposal(policy, STATE):
        STATE = reduce_metis_event(
            STATE,
            {"type": "user_intent", "intent": user_message, "action_class": policy.action_class, "policy": policy.to_dict()},
        )
        proposal_queued = True
    if tool_result is not None:
        assistant_message = _tool_chat_message(tool_result)
        STATE = reduce_metis_event(
            STATE,
            {
                "type": "chat_event",
                "status": "complete",
                "provider": "tool_router",
                "model": tool_result["tool_id"],
                "user_message": user_message,
                "assistant_message": assistant_message,
                "source_state": STATE.get("source_state", "unsourced"),
            },
        )
        voice = _speak_chat_response(assistant_message, options)
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
    voice = _speak_chat_response(assistant_message, options)
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
        "voice": voice,
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
    result = stop_voice(STATE, {"voice": payload or {}})
    _apply_voice_result(result)
    return {**_voice_response_payload(result), "state": STATE, "leds": resolve_leds(STATE)}


@app.post("/metis/voice/preview")
def voice_preview(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    text = str(payload.get("text") or "Metis voice preview.")
    options = {"voice": {**payload, "enabled": payload.get("enabled", True)}}
    result = speak_text(text, STATE, options)
    _apply_voice_result(result)
    response = {**_voice_response_payload(result), "state": STATE, "leds": resolve_leds(STATE)}
    if not result.ok:
        raise HTTPException(status_code=502, detail=response)
    return response


def _voice_response_payload(result: VoiceResult) -> dict[str, Any]:
    payload = result.to_dict()
    payload["speech_blocked"] = bool(result.blocked_reason)
    payload["block_reason"] = result.blocked_reason.replace(" ", "_") if result.blocked_reason else None
    return payload


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
