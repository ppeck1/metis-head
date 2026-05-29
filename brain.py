from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .bridge import HARDWARE_PARITY_MANIFEST
from .leds import resolve_leds
from .readiness import calculate_readiness
from .reducer import clear_failures, reduce_metis_event
from .scenarios import SCENARIOS, run_all_scenarios, run_scenario
from .schemas import FAILURE_TABLE, baseline_state


app = FastAPI(title="Metis Head Mock Brain", version="0.0.1")
STATE = baseline_state()
SCENARIO_RESULTS: list[dict[str, Any]] = []


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")


@app.get("/metis/state")
def get_state() -> dict[str, Any]:
    return {"state": STATE, "leds": resolve_leds(STATE), "readiness": calculate_readiness()}


@app.post("/metis/event")
def post_event(event: dict[str, Any]) -> dict[str, Any]:
    global STATE
    try:
        STATE = reduce_metis_event(STATE, event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
