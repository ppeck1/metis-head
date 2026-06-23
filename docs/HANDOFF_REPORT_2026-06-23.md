# Metis Head Handoff Report — 2026-06-23

## Snapshot

| Field | Value |
|---|---|
| Repo | `B:\dev\metis_head\metis_head` |
| Branch | `main` |
| Latest commit | `4b0a58f` — Phase 0BE: spoken confirmation routing in audio listen path |
| Current phase | `0BE` |
| Verification | `402 passed` under Python 3.11 |
| Public repo target | `https://github.com/ppeck1/metis-head` |
| Variable map version | `metis_variable_map.v0.3` |

---

## What Phases 0BA–0BE Added

### 0BA — Simulated audio input + STT substrate

- `metis_head/audio_input.py`: `audio_input_adapter.v0.1` with `NoneAudioInput`, `SimulatedAudioInput` (synthetic WAV + Piper helpers), and `LocalMicAudioInput` scaffold.
- `metis_head/stt.py`: `stt_engine.v0.1` with `NoneSTT`, `SimulatedSTT` (deterministic hint→text map), and `LocalWhisperSTT` scaffold.
- State: `audio_input_state`, `audio_input_enabled`, `listen_mode`, `last_audio_capture`.
- Routes: `GET /metis/audio/input`, `POST /metis/audio/input/capture`, `POST /metis/audio/transcribe`, `POST /metis/audio/listen`.
- STT redaction: `STTResult.to_dict()` exposes only `text_len`/`text_hash`/`text_redacted`; raw text enters only `POST /metis/voice/command`.

### 0BB — Real local microphone capture (triple-gated)

- `LocalMicAudioInput`: real `sounddevice` capture, lazy-imported, triple-gated: `METIS_AUDIO_ALLOW_LOCAL_MIC` env + `mic_hardware_enabled` state + `audio_input_enabled` state.
- Capture pipeline: `sounddevice.rec()` → tempfile WAV → Piper WAV-analysis helpers → compact redacted `CaptureResult`. Tempfile deleted; raw PCM never stored.
- `CaptureResult._wav_bytes`: private in-memory field; excluded from `to_dict()`, state, event log, and all responses.
- `_audio_capture_governance(require_listen_mode=False)` extended.

### 0BC — Real local STT via faster-whisper

- `LocalFasterWhisperSTT`: real CTranslate2/faster-whisper; fail-closed dual gate (`METIS_STT_ALLOW_LOCAL` env + lazy `faster_whisper` import inside `transcribe()` only).
- Disabled scaffolds: `VoskSTT`, `OpenAIWhisperSTT`, `WhisperCppSTT` (no imports, return `not_enabled`).
- `METIS_STT_ENGINE` env var (default `simulated`) selects the active STT engine.
- `stt-whisper = ["faster-whisper>=1.0"]` optional extra in `pyproject.toml`. No PyTorch or openai-whisper dependency.

### 0BE — Spoken confirmation routing in the audio listen path

- **`_run_listen_cycle` routing fork**: after STT, calls `_parse_voice_confirmation` + `_pending_proposals`. If pending proposals exist AND recognized text contains a decision phrase or explicit proposal_id → routes to `voice_confirm`; otherwise `voice_command`. Response includes `route_used` (`"voice_confirm"` or `"voice_command"`).
- **`SimulatedSTT` passthrough**: `SIMULATED_TRANSCRIPT_MAP.get(hint) or hint or default` — unknown hints return the hint text verbatim. Enables test injection of arbitrary confirmation phrases (including dynamic proposal IDs) without changing the static map.
- **Governance preserved**: `voice_confirm` still requires explicit decision phrase AND explicit proposal_id. Ambiguous phrases (e.g., "yes", "confirm approve" without ID) return `readback_required`. Mic cutoff blocks PTT release before `_run_listen_cycle` is entered. `execution_allowed` remains `false`; no standing approval.
- **Dashboard Voice Conversation Test panel**: audio/listen, PTT press/release, and wake-phrase controls with audio provider, STT provider, duration, and hint fields. Syncs with server state on every `refresh()`. Reuses `voiceChatOptions()`, `pulseRadioFromVoice()`, `renderVoiceTrace()`, `updateRadio()`.
- **13 new tests** in `tests/test_phase_0be_voice_confirm_listen.py`; full suite: **402 passed**.
- **`docs/VOICE_CONVERSATION_TEST.md`**: PowerShell smoke-test instructions for simulated, local mic + faster-whisper, and Piper voice output paths.

### 0BD — Event-driven push-to-talk and wake-word listen loop

- **`_run_listen_cycle(payload, trigger)`**: shared capture → STT → `voice_command` cycle. One utterance per call; no background threads. Called by all three audio routes.
- **`POST /metis/audio/ptt {"action":"press"|"release"}`**: models the radio PTT button.
  - `press`: validates `listen_mode==push_to_talk` + governance; sets `listen_session_active=true`. No capture yet.
  - `release`: if session active + correct mode + governance → one `_run_listen_cycle("ptt")` → clears session. Pressless release or wrong mode → safe no-op (no capture, no routing).
- **`POST /metis/audio/wake {"text":"..."}`**: caller supplies recognized text.
  - Case-insensitive prefix match against `wake_phrase` (default `"hey metis"`) + `listen_mode==wake_word` + governance → strips phrase → one `_run_listen_cycle("wake")`.
  - No match or wrong mode → `wake_not_detected`; no capture, no routing, no proposal.
- **`LocalWakeWordDetector`** scaffold in `audio_input.py`: disabled, no external imports, always returns `not_enabled`. Stub for openWakeWord / Porcupine.
- **State additions**: `listen_session_active` (default `false`), `wake_phrase` (default `"hey metis"`), `last_listen_trigger` (`"ptt"` | `"wake"` | `null`).
- **28 new tests** in `tests/test_phase_0bd_ptt_wake.py`. Full suite: **389 passed**.

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
| Simulated voice-command ingress (`POST /metis/voice/command`) | Active |
| Simulated voice confirmation (`POST /metis/voice/confirm`) | Active |
| Passive dashboard Voice Trace panel | Active |
| Simulated audio capture + STT substrate | Active |
| Real local mic capture (triple-gated, opt-in) | Active (env-gated) |
| Real local STT via faster-whisper (env-gated) | Active (env-gated) |
| Push-to-talk listen loop (`POST /metis/audio/ptt`) | Active |
| Wake-word listen loop (`POST /metis/audio/wake`) | Active (simulated detector) |
| Spoken confirmation routing (PTT/wake/listen → confirm) | Active (Phase 0BE) |
| Real wake-word engine (openWakeWord / Porcupine) | Scaffold only |
| Physical radio panel | Contract defined; hardware wiring future |

---

## Audio/Voice Path — What Works Now

1. Caller presses PTT → `POST /metis/audio/ptt {"action":"press"}` → `listen_session_active=true`.
2. Caller releases PTT → `POST /metis/audio/ptt {"action":"release", "hint":"<fixture>"}` → one capture→STT→route cycle. `route_used` is `"voice_command"` or `"voice_confirm"` depending on pending proposals and phrase content.
3. Caller speaks wake phrase → `POST /metis/audio/wake {"text":"hey metis <command>"}` → phrase stripped → one cycle on remainder.
4. If pending proposals exist and recognized text contains a decision phrase + proposal ID → routes to `POST /metis/voice/confirm` → confirms/denies/cancels with `execution_allowed=false`, no standing approval.
5. Ambiguous phrases (no proposal ID or unrecognized decision) → `readback_required`; proposal stays pending.
6. Recognized text never stored; `STTResult.to_dict()` exposes only `text_len`/`text_hash`/`text_redacted`.
7. Mic cutoff (`hardware_privacy device=mic state=off`) blocks press, release, and wake before any capture.
8. All governance blocks return a structured `status: blocked` response; no partial state.

Real mic path (opt-in):

```powershell
$env:METIS_AUDIO_ALLOW_LOCAL_MIC = "true"
# mic_hardware_enabled and audio_input_enabled must also be set via button events
```

Real STT path (opt-in):

```powershell
$env:METIS_STT_ALLOW_LOCAL = "true"
$env:METIS_STT_ENGINE = "faster_whisper"
$env:METIS_STT_MODEL = "small"
```

---

## Key Runtime Commands

Launch:

```powershell
cd B:\dev\metis_head\metis_head
.\scripts\launch_metis.ps1 -PythonExe "C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe" -Port 8787
```

Full tests:

```powershell
cd B:\dev\metis_head\metis_head
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m pytest
```

PTT example (simulated):

```powershell
# Enable audio
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"audio_input","state":"on"}'

# Set push-to-talk mode
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"push_to_talk"}'

# Press PTT
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'

# Release PTT (triggers one listen cycle)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"release","hint":"git status"}'
```

Wake-word example (simulated):

```powershell
# Set wake-word mode
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"wake_word"}'

# Simulated wake phrase
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/wake `
  -ContentType "application/json" -Body '{"text":"hey metis git status"}'
```

Spoken confirmation example (simulated, Phase 0BE):

```powershell
# Queue a proposal then confirm it by spoken phrase via PTT
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"release","hint":"git status"}'
$proposalId = $r.state.approval_queue[0].proposal_id

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" `
  -Body (ConvertTo-Json @{action="release"; hint="confirm approve $proposalId"})

# Expected: route_used=voice_confirm, confirmation_accepted=True, execution_allowed=False
$c.route_used
$c.voice_command.voice_confirmation
```

---

## Important Files

| File | Notes |
|---|---|
| `README.md` | Current phase, launch, boundaries, verification. |
| `ACTIVE_TASK.md` | Phase history and next phase description. |
| `docs/project_variable_map.md` | Full canonical variable/route/event/state map (v0.2). |
| `docs/READ_ONLY_EXECUTION_POLICY_v0_1.md` | Current governed execution boundary. |
| `metis_head/brain.py` | FastAPI mock Brain; all route orchestration including PTT/wake. |
| `metis_head/audio_input.py` | Audio capture providers + `LocalWakeWordDetector` scaffold. |
| `metis_head/stt.py` | STT providers including `LocalFasterWhisperSTT`. |
| `metis_head/reducer.py` | Event reducer; handles all PTT/wake state transitions. |
| `metis_head/schemas.py` | `baseline_state()` including new 0BD fields. |
| `tests/test_phase_0bd_ptt_wake.py` | 28 tests for PTT/wake routing, no-op paths, redaction, no execution. |
| `tests/test_phase_0be_voice_confirm_listen.py` | 13 tests for spoken confirmation routing, readback, mic cutoff, redaction, no execution. |
| `docs/VOICE_CONVERSATION_TEST.md` | Smoke-test instructions for simulated, local mic, and Piper paths. |
| `scripts/launch_metis.ps1` | Repo-root-aware launch script. |

---

## Governance Boundaries (Unchanged)

- Mic cutoff (`mic_hardware_enabled=false`) blocks all capture. Highest precedence.
- `listen_session_active=true` is informational; governance still fires on release.
- Recognized text is redacted: `STTResult.to_dict()` exposes only `text_len`/`text_hash`/`text_redacted`. Raw text enters `voice_command` or `voice_confirm` only; never stored in state or event log.
- No background threads. No always-listening standby. One utterance per explicit trigger.
- No new execution authority. All routing goes through the existing governed proposal/review/receipt chain.
- `execution_allowed` remains `false` after any PTT, wake, or spoken confirmation cycle.
- `standing_approval` is never granted by spoken confirmation.
- `external_action_executed` remains `false` after any PTT or wake cycle.

---

## Recommended Next Phase

### 0BF — Physical radio panel wiring

Wire the panel contract (`docs/PHYSICAL_RADIO_PANEL_CONTRACT_v0_1.md` and `metis_head/panel.py`) to the bridge emulator so the physical Magnavox radio's buttons, knobs, and PTT report as governed events. The software path is complete through 0BE; 0BF is the hardware integration step.

### Future

- **Real mic PTT** — Wire the physical PTT button through the bridge emulator to `POST /metis/audio/ptt`.
- **Real wake-word engine** — Implement `LocalWakeWordDetector.detect()` using openWakeWord or Porcupine; no streaming thread; keep event-driven contract.

---

## Handoff Notes

- Keep mic cutoff as the absolute highest-precedence gate; no future refactor should bypass it.
- Keep the listen loop event-driven and bounded; never add a background listener thread.
- The `wake_phrase` default is `"hey metis"`; tests use `"state"` key in `button_event` (not `"value"`).
- `tests/conftest.py` sets `METIS_REPO_ROOT` and initializes `.git` only when missing — clean-export test reproducibility is preserved.
- Reference repos (openWakeWord, Porcupine, MCP, etc.) are pattern donors only; never import.
- Dashboard controls are development scaffolding; the radio form factor is the target operator UX.
