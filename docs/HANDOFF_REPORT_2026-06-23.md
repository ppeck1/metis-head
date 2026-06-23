# Metis Head Handoff Report — 2026-06-23

## Snapshot

| Field | Value |
|---|---|
| Repo | `B:\dev\metis_head\metis_head` |
| Branch | `main` |
| Phase entering repair | `0BF` complete |
| Phase completed by this handoff | `0BG` repair |
| Audit baseline commit | `56602df` — Phase 0BF: browser held-to-talk verbal conversation |
| Audit baseline verification | `410 passed` under Python 3.11; coverage audit `84%`; `compileall` passed |
| Public repo target | `https://github.com/ppeck1/metis-head` |
| Variable map version | `metis_variable_map.v0.5` |

Final Phase 0BG verification:

- `python -m pytest -q` → `414 passed`.
- `python -m compileall -q metis_head tests` → passed.
- `python -m pytest --cov=metis_head --cov-report=term -q` was attempted but could not run because
  `pytest-cov`/`coverage` is not installed in this Python 3.11 environment.

---

## Phase 0BG Repair Results

Phase 0BG was a repair pass only. It did not add physical radio-panel work, new tool authority,
autonomous execution, or always-listening behavior.

### Documentation/state alignment

- `ACTIVE_TASK.md`, `README.md`, this handoff report, and `docs/project_variable_map.md` now identify
  Phase `0BG` as the current repair pass.
- Stale handoff references to Phase `0BE`, commit `4b0a58f`, `402 passed`, and "next 0BF physical
  radio panel wiring" were removed.
- Phase `0BF` remains documented as complete at commit `56602df` with audit baseline `410 passed`.
- The next phase is intentionally left for operator selection after reviewing the 0BG repair; physical
  radio-panel wiring is not claimed as the automatic next step.

### Browser verbal-input architecture

There are three distinct verbal-input paths:

1. Dashboard Hold to Talk:
   - Uses browser `SpeechRecognition` when available.
   - Sends recognized text as a simulated STT hint through `POST /metis/audio/ptt`.
   - Does not upload raw browser-recorded audio.
   - Does not require local faster-whisper.

2. Backend multipart browser PTT:
   - `POST /metis/audio/browser_ptt` accepts `multipart/form-data` with `audio`, `stt_provider`,
     `stt_hint`, and `options_json`.
   - This is a backend/local-prototype upload lane for clients and tests.
   - It routes through `_run_stt_route_cycle` after governance and upload validation.

3. Optional local faster-whisper STT:
   - Env-gated by `METIS_STT_ALLOW_LOCAL=true` and selected with `METIS_STT_ENGINE=faster_whisper`.
   - Requires the optional `stt-whisper` dependency.
   - Not used by the dashboard Web Speech path unless a future phase explicitly wires that behavior.

### Voice privacy contract

The stronger contract is now the repo contract:

- Voice-origin raw text is transient.
- It may be used during a request for routing, provider generation, proposal detection, or voice confirmation.
- It must not persist raw in canonical state, `chat_history`, `chat_event.user_message`, or provider/audio
  event payloads.
- Voice/audio provider events continue to store only redacted metadata such as `text_len`, `text_hash`,
  and `text_redacted`.
- If an assistant response repeats the raw voice transcript exactly, that repeated phrase is redacted
  before persistence and voice playback.

### Browser upload safety

`POST /metis/audio/browser_ptt` now has local-prototype guardrails:

- Maximum upload size: `BROWSER_PTT_MAX_UPLOAD_BYTES`.
- Supported content types: WAV variants, WebM audio, and `application/octet-stream`.
- Empty payloads return `400`.
- Unsupported content types return `415`.
- WAV-like uploads require a simple `RIFF`/`WAVE` header check and invalid WAV payloads return `400`.
- Oversized uploads return `413`.

### Tests added/repaired

`tests/test_phase_0bf_browser_ptt.py` now covers:

- Actual event shape: `type == "provider_event"` and `provider == "audio_input"`.
- Sentinel non-persistence for voice-origin text:
  `VOICE_SENTINEL_SHOULD_NOT_PERSIST_0BG`.
- Oversized upload rejection.
- Unsupported content-type rejection.
- Invalid WAV payload rejection.

---

## Current Capability State

| Capability | Status |
|---|---|
| Canonical state, events, reducer, LED/status resolver | Active |
| Scenarios, readiness, adapters, provider harness, static dashboard | Active |
| Governed LLM chat (mock, Ollama, OpenAI) | Active |
| Local Piper voice output + radio analyzer | Active |
| Governed tool registry + proposal/review/receipt lanes | Active |
| Approved read-only receipt lanes (`time.now`, `git.status`, `filesystem.read`) | Active |
| Deterministic task planner, plan queue, plan review, guided advance | Active |
| Deterministic tool/capability awareness (chat + voice) | Active |
| Simulated voice-command ingress (`POST /metis/voice/command`) | Active; raw voice text redacted before persistence |
| Simulated voice confirmation (`POST /metis/voice/confirm`) | Active |
| Passive dashboard Voice Trace panel | Active |
| Simulated audio capture + STT substrate | Active |
| Real local mic capture | Active only when env/state gates allow |
| Real local STT via faster-whisper | Active only when optional dependency and env gates allow |
| Push-to-talk listen loop (`POST /metis/audio/ptt`) | Active |
| Wake-word listen loop (`POST /metis/audio/wake`) | Active simulated path |
| Browser Hold to Talk dashboard path | Active through Web Speech + `/metis/audio/ptt` hint routing |
| Backend multipart browser PTT (`POST /metis/audio/browser_ptt`) | Active with 0BG upload guardrails |
| Real wake-word engine (openWakeWord / Porcupine) | Scaffold/future only |
| Physical radio panel | Contract defined; hardware wiring future |

---

## Governance Boundaries

- Mic cutoff (`mic_hardware_enabled=false`) remains the highest-precedence capture gate.
- Listen loops remain event-driven and bounded: one utterance per explicit PTT, wake, listen, or browser
  PTT trigger.
- No background listener or always-listening standby is introduced.
- No new execution authority is introduced.
- `execution_allowed` remains `false` after PTT, wake, browser PTT, and spoken confirmation cycles.
- Reference repos remain pattern donors only; do not vendor/import/spawn them.

---

## Key Files

| File | Notes |
|---|---|
| `metis_head/brain.py` | Chat, voice, PTT/wake/browser PTT orchestration; 0BG privacy and upload guards. |
| `tests/test_phase_0bf_browser_ptt.py` | Repaired/expanded 0BG coverage. |
| `README.md` | Current phase, architecture clarification, verification, boundaries. |
| `ACTIVE_TASK.md` | Phase history and current repair status. |
| `docs/project_variable_map.md` | Canonical variable/route/event/state map. |
| `docs/VOICE_CONVERSATION_TEST.md` | Manual smoke-test instructions for voice conversation routes. |
| `scripts/launch_metis.ps1` | Repo-root-aware launch script. |

---

## Recommended Next Step

Review Phase 0BG results and choose the next phase explicitly. Physical radio-panel wiring remains a
future candidate, but it is not part of this repair pass and should not be assumed as the next step
until selected.
