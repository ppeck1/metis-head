# Metis Head

Simulation-first skeleton for the v0.5 Metis Head buildspec.

This repo intentionally contains no real hardware, microphone, camera, BOH, Atlas,
tool, or provider integrations. External systems are represented only by versioned
adapters and deterministic mock providers.

## Current Phase

Phase scope: `0A + 0S + 0R virtual chat`

Status: initial simulation-first skeleton implemented with a governed Phase 0R LLM router.

Latest patch: the Virtual Chat panel now sits directly under the Virtual Radio so conversation happens next to the simulated control surface. `/metis/chat` routes governed virtual chat through `mock`, `ollama`, or `openai` providers, and the dashboard can refresh locally available Ollama models from `/api/tags`.

Functioning UI estimate: about `86%` for the Phase 0S/0R simulator UI. The dashboard can view state, LEDs, adapters, readiness, scenario output, event logs, a virtual radio control surface, export/replay current events, governed virtual chat, and Ollama model selection. Remaining UI work is mostly richer scenario summaries, bridge replay presets, provider health controls, and chat transcript export polish.

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
- Governed LLM router with `MockLLMProvider`, `OllamaLLMProvider`, and `OpenAILLMProvider`.
- Virtual chat panel that maps depth, initiative, Agent Mode, and source grounding into chat behavior.
- Ollama model selector that reads locally available models from the configured Ollama base URL.
- Dashboard order: Virtual Radio, Virtual Chat, readiness/LED/adapter/state/scenario panels, export/replay, event log.

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

## LLM Provider Config

Default provider is mock:

```powershell
$env:METIS_LLM_PROVIDER="mock"
```

Ollama:

```powershell
$env:METIS_LLM_PROVIDER="ollama"
$env:METIS_OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:METIS_OLLAMA_MODEL="llama3.1"
```

The dashboard can also select `Ollama` in the Virtual Chat panel, refresh models from the configured base URL, and send the selected model in the chat request. This is a UI override; it does not change your shell environment.

OpenAI:

```powershell
$env:METIS_LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="..."
$env:METIS_OPENAI_MODEL="gpt-4o-mini"
```

Phase 0R does not enable tools, retrieval, BOH, Atlas, hardware, mic, camera, or autonomous execution. Agent Mode chat can queue proposals only.

## API

- `GET /metis/state`
- `GET /metis/export`
- `GET /metis/llm/options`
- `POST /metis/event`
- `POST /metis/chat`
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
21 passed under Python 3.11
```

Known environment note: Python 3.13 is present on this machine but did not have `pytest` installed during Phase 0A/0S verification.

## Boundaries

Phase 0A/0S/0R does not implement real hardware, microphone, camera, BOH retrieval, Project Atlas integration, external tools, or autonomous execution. Reference repositories remain pattern donors only.
