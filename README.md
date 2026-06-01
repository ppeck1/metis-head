# Metis Head

Simulation-first skeleton for the v0.5 Metis Head buildspec.

This repo intentionally contains no real hardware, microphone, camera, Atlas, or
tool integrations. External systems are represented by versioned adapters and
deterministic mock providers. As of Phase 0B the one live external integration is a
read-only BOH retrieval bridge (opt-in, never mutates BOH, never holds BOH's operator
token).

## Current Phase

Phase scope: `0V` — governed voice output harness (builds on `0A + 0S + 0R virtual chat + 0B retrieval bridge + 0C BOH link + 0S/S4 bridge emulator + 0S/S3 provider harness + 0P personality`).

Status: Metis now has a simulation-first voice output harness. It supports mock voice output,
explicitly gated system-TTS shape, voice status, speak/preview/stop endpoints, chat response speech,
output-mute blocking, visible TTS failures, and redacted speech metadata in the event log.

Phase 0V implemented:

- `metis_head/voice.py`: `BaseVoiceProvider`, `MockVoiceProvider`, gated `SystemVoiceProvider`,
  `FailedVoiceProvider`, `VoiceConfig`, and `VoiceResult`.
- `GET /metis/voice`, `POST /metis/voice/speak`, `POST /metis/voice/preview`, and
  `POST /metis/voice/stop`.
- `options.voice.speak_response=true` on `/metis/chat` speaks the completed chat response through
  the governed voice path.
- `output_muted=true` blocks voice output without changing mic/camera/logging privacy state.
- Voice events store `text_len`, `text_hash`, and `text_redacted=true`; raw spoken text is not
  persisted into the event log.

Previous Phase 0P status: Metis has a runtime personality constitution based on `METIS_PERSONALITY_CONSTITUTION_v1_0`.
The constitution is exposed as structured data, served as a static console, and injected into the
governed chat system prompt for mock, Ollama, and OpenAI providers.

Phase 0P implemented:

- `docs/METIS_PERSONALITY_CONSTITUTION_v1_0.md`: canonical personality constitution source.
- `metis_head/static/personality_console.html`: supplied personality console served by FastAPI.
- `metis_head/personality.py`: structured profile, 27 quantified traits, non-negotiable invariants,
  mode modifiers, weighted profile export, and short system-prompt form.
- `GET /metis/personality` returns the active personality profile.
- `GET /metis/personality/console` serves the visual personality console.
- Governed LLM messages now include the Metis constitution and active personality mode.

Previous Phase 0S/S3 status: the simulator includes a backend provider harness for deterministic mock STT, TTS,
vision, BOH memory, vault, tools, Atlas, LLM router, and robot safety operations. Provider
operations return event payloads and the mock Brain can reduce those events into canonical state.

Phase 0S/S3 implemented:

- `metis_head/provider_harness.py`: provider catalog, operation metadata, deterministic operation
  invocation, and event extraction.
- `GET /metis/providers` lists available mock provider operations.
- `POST /metis/providers/{operation_id}/invoke` invokes a mock provider operation, applies emitted
  events through the reducer, and returns state/LEDs.
- Tests proving visible provider failures, TTS event sequencing, Agent Mode proposal queuing, and
  robot-safety classification staying non-mutating.

Previous Phase 0S/S4 status: the simulator includes a backend bridge emulator that emits the same event schema as
future hardware controls. It can create control/button/privacy/heartbeat events, replay JSONL
event logs locally through the reducer, or post events to the mock Brain at `/metis/event`.

Phase 0S/S4 implemented:

- `metis_head/bridge_emulator.py`: canonical event builders for virtual bridge controls,
  JSONL parsing/serialization, local reducer replay, and optional HTTP posting to a mock Brain.
- CLI entry point: `python -m metis_head.bridge_emulator ...` or installed script
  `metis-bridge-emulator`.
- Tests proving bridge-schema parity, JSONL round trip, local replay, and parser diagnostics.

Previous Phase 0C status: a background, read-only poller maintains lightweight awareness of the BOH link
(connected/degraded/disconnected/auth_failed) and surfaces it on the dashboard and via
`GET /metis/boh/status`, without copying the BOH corpus. Phase 0B retrieval behavior is
unchanged; the link manager is opt-in via `METIS_BOH_BACKGROUND_ENABLED`.

Phase 0C implemented:

- `metis_head/boh_link.py`: env/option config, a daemon-thread poller, a pure
  `probe_boh_once()` cycle (health + retrieve/status + a `limit=1` retrieve probe), link-state
  transition detection, and token-free status serialization. Auth rejection from any probe layer
  maps to `auth_failed`, and surfaced BOH payloads are recursively scrubbed of the read-only
  retrieval token.
- FastAPI lifespan starts the poller only when `METIS_BOH_BACKGROUND_ENABLED=true`; otherwise the
  link state stays `disabled`.
- `GET /metis/boh/status` exposes the safe link state (no token, no operator token, no Authorization,
  error strings scrubbed). Dashboard shows a BOH Library badge, state, last checked/connected, probe
  count, last error, and transition messages.
- When the background link reports `auth_failed`, `/metis/chat` skips the per-message live retrieval
  and labels the answer `degraded` instead of repeatedly hammering BOH.
- Boundary: Metis only reads from BOH (`/api/health`, `/api/retrieve/status`, `/api/retrieve`), never
  mutates it, never holds or sends BOH's operator token, and never copies/mirrors the BOH corpus —
  BOH remains the source of truth for library/index/chunks/citations.

Status: governed virtual chat can retrieve read-only context packs from a running BOH
instance when source grounding (AFC) is on; otherwise behavior is unchanged.

Phase 0B implemented:

- `metis_head/boh_retrieval.py`: env/option config and a read-only client that calls
  `POST {METIS_BOH_BASE_URL}/api/retrieve` with the `X-BOH-Retrieval-Token` header.
- `/metis/chat` retrieves before LLM generation when `source_grounding_enabled` and BOH is
  enabled, injects context packs into the governed prompt, and labels the answer
  `sourced` / `unsourced` / `degraded`.
- BOH `gate_result`, warnings, citations, `do_not_treat_as_canonical` flags, and source spans
  are preserved in the chat response (`metadata.boh` / `retrieval`).
- BOH unreachable yields a visible `degraded` source state instead of failing silently.
- Boundary: Metis only reads from BOH (`/api/retrieve`), never mutates it, and never holds or
  sends BOH's operator token. With BOH disabled, chat behavior is unchanged.

Latest patch: the UI test harness is satisfactory for now, so focus has shifted back to backend readiness. Agent Mode and memory review now create structured proposal records in canonical state instead of only incrementing counters.

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
- Provider harness for deterministic mock STT/TTS/vision/memory/tool/Atlas/LLM/safety operations.
- Virtual radio view rebuilt as a 3-zone instrument: an inert speaker grille, a thin vertical LED/visualizer status strip, and a right control stack (Volume + Depth dials, PWR/LOUD/AFC/AM-FM buttons, large Tuning/Initiative dial). Radio status readouts (power/audio/mode/authority) and mic/camera cutoff controls live in a separate Radio Status panel below.
- Export/replay controls for state snapshots and JSON/JSONL event logs.
- Governed LLM router with `MockLLMProvider`, `OllamaLLMProvider`, and `OpenAILLMProvider`.
- Metis personality constitution injected into governed chat prompts.
- Governed voice output harness for mock/system-shaped TTS, with output mute enforcement.
- Virtual chat panel that maps depth, initiative, Agent Mode, and source grounding into chat behavior.
- Ollama model selector that reads locally available models from the configured Ollama base URL.
- Dashboard order: Virtual Radio, Virtual Chat (Send attached to the composer; Enter sends, Shift+Enter newlines), Radio Status, BOH Library Link, readiness/LED/adapter/state/scenario panels, export/replay, event log.
- LLM provider health probe for mock readiness, Ollama reachability/model availability, and OpenAI key configuration.
- Deterministic governance classifier for observe/retrieve/draft/propose-memory/local-modify/external/sensitive/actuator intents.
- Structured `approval_queue` records with deterministic proposal IDs, action class, reasons, review status, and `execution_allowed=false`.

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

## Voice Output Config (Phase 0V)

Voice output is opt-in. Phase 0V does not open a microphone, camera, or autonomous listening path.
It only converts completed text responses into governed TTS events.

```powershell
$env:METIS_VOICE_ENABLED="false"
$env:METIS_VOICE_PROVIDER="mock"       # mock or system
$env:METIS_VOICE_ID="metis-counsel-mock"
$env:METIS_VOICE_RATE="1.0"
$env:METIS_VOICE_VOLUME="0.6"
$env:METIS_VOICE_ALLOW_SYSTEM_TTS="false"
```

`system` is present as a gated provider shape only. Real OS speech remains disabled unless
`METIS_VOICE_ALLOW_SYSTEM_TTS=true`; the default `mock` provider emits deterministic TTS events
without audio.

## BOH Retrieval Bridge Config (Phase 0B)

The BOH bridge is opt-in and read-only. When `METIS_BOH_ENABLED=true` and source grounding
(AFC) is on, `/metis/chat` retrieves governed context from BOH before LLM generation.

```powershell
$env:METIS_BOH_ENABLED="true"
$env:METIS_BOH_BASE_URL="http://127.0.0.1:8000"
$env:METIS_BOH_RETRIEVAL_TOKEN="..."   # read-only retrieval token only; never the operator token
$env:METIS_BOH_RETRIEVAL_MODE="exploration"   # or strict_answer, canon_review, audit_provenance, low_b_worker_context
$env:METIS_BOH_LIMIT="5"
```

These can also be supplied per request via the chat `options.boh` object (UI override; does not
change your shell environment). Metis calls only `POST {base_url}/api/retrieve`, never mutates
BOH, and never sends BOH's operator token. If BOH is unreachable, the answer is labeled
`degraded`/unsourced rather than failing silently.

Tools, Atlas, hardware, mic, camera, and autonomous execution remain disabled. Agent Mode chat
can queue proposals only and never mutates BOH.

## Bridge Emulator (Phase 0S/S4)

Emit one canonical bridge event as JSON:

```powershell
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m metis_head.bridge_emulator control initiative 0.82 --raw 839
```

Post an event directly to a running mock Brain:

```powershell
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m metis_head.bridge_emulator --post http://127.0.0.1:8787 button am_fm fm
```

Replay a JSONL bridge log locally through the deterministic reducer:

```powershell
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m metis_head.bridge_emulator replay .\events.jsonl --local-final-state
```

Replay JSONL into the mock Brain:

```powershell
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m metis_head.bridge_emulator --post http://127.0.0.1:8787 replay .\events.jsonl
```

### Background Link Manager (Phase 0C)

The background link manager is opt-in and read-only. When `METIS_BOH_BACKGROUND_ENABLED=true`, a
daemon-thread poller maintains lightweight awareness of the BOH link and exposes it via
`GET /metis/boh/status` and the dashboard's BOH Library panel.

```powershell
$env:METIS_BOH_BACKGROUND_ENABLED="true"
$env:METIS_BOH_POLL_SECONDS="15"            # clamped 5-3600; auth_failed backs off to >= 60s
$env:METIS_BOH_PROBE_QUERY="__metis_connection_probe__"
```

It reuses `METIS_BOH_BASE_URL` / `METIS_BOH_RETRIEVAL_TOKEN` / `METIS_BOH_RETRIEVAL_MODE` /
`METIS_BOH_LIMIT`. It polls `/api/health`, `/api/retrieve/status`, and a `limit=1` `/api/retrieve`
probe; link states are `disabled`, `connecting`, `connected`, `degraded`, `disconnected`,
`auth_failed`. A 401/403 from health, retrieve/status, or the retrieve probe maps to
`auth_failed`; health connection refusal maps to `disconnected`; health 5xx or probe network
error maps to `degraded`. The status response never includes any token, and the corpus is never copied into
Metis — BOH remains the source of truth.

## API

- `GET /metis/state`
- `GET /metis/export`
- `GET /metis/boh/status`
- `GET /metis/llm/options`
- `POST /metis/event`
- `POST /metis/chat`
- `GET /metis/voice`
- `POST /metis/voice/speak`
- `POST /metis/voice/preview`
- `POST /metis/voice/stop`
- `GET /metis/personality`
- `GET /metis/personality/console`
- `POST /metis/llm/health`
- `POST /metis/governance/classify`
- `GET /metis/proposals`
- `POST /metis/replay`
- `POST /metis/state/reset`
- `POST /metis/scenario/run`
- `GET /metis/scenario/results`
- `GET /metis/health`
- `GET /metis/adapters`
- `GET /metis/providers`
- `POST /metis/providers/{operation_id}/invoke`
- `POST /metis/adapters/{adapter_id}/set_health`
- `POST /metis/failures/{failure_id}/trigger`
- `POST /metis/failures/clear`

## Verification

Last verified:

```text
71 passed under Python 3.11 (includes 8 Phase 0B BOH-bridge tests, 14 Phase 0C link-manager tests, 5 Phase 0S/S4 bridge-emulator tests, 6 Phase 0S/S3 provider-harness tests, 4 Phase 0P personality-layer tests, and 6 Phase 0V voice-harness tests)
```

Phase 0B/0C tests monkeypatch the HTTP layer (`metis_head.boh_retrieval._post_json` and
`metis_head.boh_link._request`), so no running BOH instance is required to verify the suite.

Known environment note: Python 3.13 is present on this machine but did not have `pytest` installed during Phase 0A/0S verification.

## Boundaries

Phase 0A/0S/0R does not implement real hardware, microphone, camera, Project Atlas integration, external tools, or autonomous execution. As of Phase 0B/0C the only live external integration is the read-only BOH link: the retrieval bridge (`/api/retrieve`, opt-in via `METIS_BOH_ENABLED`) and the background link manager (`/api/health` + `/api/retrieve/status` + a `limit=1` `/api/retrieve` probe, opt-in via `METIS_BOH_BACKGROUND_ENABLED`). Neither mutates BOH, holds BOH's operator token, nor copies the BOH corpus into Metis — BOH remains the source of truth. Other reference repositories remain pattern donors only.
