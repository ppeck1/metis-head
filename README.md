# Metis Head

Simulation-first skeleton for the v0.5 Metis Head buildspec.

This repo intentionally contains no real hardware, microphone, camera, BOH, Atlas,
tool, or provider integrations. External systems are represented only by versioned
adapters and deterministic mock providers.

## Current Phase

Phase scope: `0A + 0S`

Status: initial simulation-first skeleton implemented.

Latest patch: the dashboard now includes export/replay controls for state snapshots and event logs, plus a lightweight virtual radio view whose knobs and switches emit the same mock Brain events as the future bridge. TTS failure handling also forces simulated speech back to `idle` if the failure arrives while `audio_state` is `speaking`.

Functioning UI estimate: about `78%` for the Phase 0S simulator UI. The dashboard can view state, LEDs, adapters, readiness, scenario output, event logs, a virtual radio control surface, and export/replay current events. Remaining UI work is mostly richer scenario result summaries, bridge replay presets, and deeper provider failure controls.

Implemented:

- Canonical state schema matching the v0.5 buildspec intent.
- Event schema for bridge, control, button, privacy, failure, provider, memory, and adapter events.
- Deterministic state reducer and replay helper.
- LED/status precedence resolver shared by tests, API, and dashboard.
- Computed readiness checklist with domain label and item-level statuses.
- Scenario library and runner for required v0.5 scenarios.
- Mock providers for STT, TTS, vision, memory/BOH, tools, LLM router, Atlas, and robot safety.
- Adapter base interface with health, capability, and schema-version checks.
- FastAPI mock Brain with the v0.5 Phase 0S endpoint set.
- Static dashboard for canonical state, LEDs, adapter health, readiness, scenario results, and event log.
- Virtual radio view for volume, depth, initiative, PWR, LOUD, AFC, AM/FM, mic cutoff, camera cutoff, LEDs, visualizer, and speaker grille placement.
- Export/replay controls for state snapshots and JSON/JSONL event logs.

See [docs/project_variable_map.md](docs/project_variable_map.md) for the current and future build variable map.

## Phase Documentation Rule

Before each phase commit, update:

- `README.md` with the active phase, completed scope, verification command, and any known limitations.
- `docs/project_variable_map.md` with new or changed state fields, event fields, API routes, adapter IDs, readiness domains, scenario IDs, and future-phase placeholders.

This keeps each commit reviewable without needing to rediscover the architecture from code.

## Run

Run tests:

```powershell
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m pytest
```

Run the mock Brain:

```powershell
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn metis_head.brain:app --host 127.0.0.1 --port 8787
```

Dashboard:

```text
http://127.0.0.1:8787/
```

## API

- `GET /metis/state`
- `GET /metis/export`
- `POST /metis/event`
- `POST /metis/replay`
- `POST /metis/state/reset`
- `POST /metis/scenario/run`
- `GET /metis/scenario/results`
- `GET /metis/health`
- `GET /metis/adapters`
- `POST /metis/adapters/{adapter_id}/set_health`
- `POST /metis/failures/{failure_id}/trigger`
- `POST /metis/failures/clear`

## Verification

Last verified:

```text
16 passed under Python 3.11
```

Known environment note: Python 3.13 is present on this machine but did not have `pytest` installed during Phase 0A/0S verification.

## Boundaries

Phase 0A/0S does not implement real hardware, microphone, camera, BOH integration, Project Atlas integration, external tools, autonomous execution, or provider selection. Reference repositories remain pattern donors only.
