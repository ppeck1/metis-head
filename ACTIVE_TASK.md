# Active Task

**Current active task:** Phase `0BE` — Voice-only approval confirmation: wire real audio → STT
into `/metis/voice/confirm` with readback + explicit-phrase gating.

---

## Phase 0BD — COMPLETE

Phase 0BD delivered an event-driven push-to-talk and wake-word listen loop.

### Delivered

- **`POST /metis/audio/ptt {"action":"press"|"release"}`** — models the radio PTT button.
  `press` validates `listen_mode==push_to_talk` + full governance chain (mic cutoff →
  `audio_input_enabled` → `power_state`); sets `listen_session_active=true`. Does NOT start
  a thread or begin capture. `release` runs exactly one `_run_listen_cycle`, then clears the
  session. A press-less release or release in the wrong mode is a safe no-op.
- **`POST /metis/audio/wake {"text":"..."}`** — caller-supplied text simulates a real wake-word
  detector. Case-insensitive prefix match against configurable `wake_phrase` (default `"hey metis"`).
  If match AND `listen_mode==wake_word` AND governance passes, strips phrase and runs one cycle on
  the remainder. Otherwise returns `wake_not_detected` with no capture or routing.
- **`LocalWakeWordDetector` scaffold** — `audio_input.py`; disabled, no external imports; stub for
  openWakeWord / Porcupine. Returns `not_enabled` always.
- **`_run_listen_cycle(payload, trigger)`** — shared capture → STT → `voice_command` function
  called by `/listen`, `/ptt`, and `/wake`. Governance verified by the caller; `trigger` field
  flows through emitted events to `last_audio_capture.listen_trigger`.
- **New state fields**: `listen_session_active` (default `false`), `wake_phrase` (default
  `"hey metis"`), `last_listen_trigger` (`"ptt"` | `"wake"` | `null`). Set by reducer; configurable
  via `button_event`.
- **`GET /metis/audio/input`** reports all new fields plus `trigger_routes` and `wake_word` scaffold
  entry in `providers`.
- **28 new tests** in `tests/test_phase_0bd_ptt_wake.py`; full suite: **389 passed**.

### Boundary (preserved)

Event-driven and bounded — one utterance per explicit PTT or wake trigger, never always-listening.
Mic cutoff highest precedence. Standby is not always-listening. Recognized text redacted; enters
only `POST /metis/voice/command`. No new execution authority.

---

## Phase 0BC — COMPLETE

Phase 0BC delivered real local STT behind a hardened swappable `STTProvider` contract.

### Delivered

- **In-memory audio handoff**: `CaptureResult._wav_bytes` (private, non-serialised) carries
  WAV bytes from capture to STT within a single `/metis/audio/listen` request.
  Set by `SimulatedAudioInput` and `LocalMicAudioInput`; absent from `to_dict()`,
  state, event log, and all responses.
- **`LocalFasterWhisperSTT`** — real CTranslate2/faster-whisper engine; fail-closed:
  1. `METIS_STT_ALLOW_LOCAL=true` (env opt-in, checked first)
  2. Lazy `from faster_whisper import WhisperModel` inside `transcribe()` only
  3. `METIS_STT_MODEL` (default `small`), `METIS_STT_MODEL_DIR` (offline path)
  4. Model load fail → `model_unavailable`; missing dep → `dependency_unavailable`; no crash
- **Disabled scaffolds**: `VoskSTT`, `OpenAIWhisperSTT`, `WhisperCppSTT` — return
  `not_enabled`; no imports.
- **`METIS_STT_ENGINE`** env var (default `simulated`) selects the active STT provider.
- **`stt-whisper = ["faster-whisper>=1.0"]`** optional extra in `pyproject.toml`.
- **`GET /metis/audio/input`** now reports `stt_engine`, `stt_allow_local`,
  `faster_whisper_available`, `stt_model`; device enumeration gated behind
  `mic_hardware_enabled`.
- **`POST /metis/audio/listen`** falls back to `METIS_STT_ENGINE` when no
  `stt_provider` is in the payload.
- **`docs/LOCAL_STT_SMOKE_TEST.md`**: manual PowerShell smoke-test.
- **25 new tests**; full suite **361 passed** (no real mic, no model, no env vars in CI).

### Boundary (preserved)

Real STT opt-in and lazy; no PyTorch/openai-whisper. In-memory WAV bytes and recognized
text never persisted. Recognized text enters only `POST /metis/voice/command`; redacted
to `text_len`/`text_hash` in state and events. No new tool lane or execution authority.

---

## Phase 0BB — COMPLETE

Phase 0BB enabled real local microphone capture via `LocalMicAudioInput`, triple-gated
and opt-in.

### Delivered

- `LocalMicAudioInput` — real `sounddevice` capture, lazy-imported, triple-gated:
  1. `METIS_AUDIO_ALLOW_LOCAL_MIC=true` (env opt-in)
  2. `mic_hardware_enabled` (state/hardware gate, governed in brain.py)
  3. `audio_input_enabled` (software gate, governed in brain.py)
- Capture pipeline: `sounddevice.rec()` → tempfile WAV → Piper WAV-analysis helpers → compact
  redacted `CaptureResult`. Tempfile deleted; raw PCM never stored.
- `_audio_capture_governance(require_listen_mode=False|True)` extended; all three audio
  routes use it.
- `GET /metis/audio/input`: reports `allow_local_mic`, `sounddevice_available`,
  `input_devices` (gated behind `mic_hardware_enabled`).
- `mic = ["sounddevice>=0.4"]` optional extra in `pyproject.toml`.
- `docs/LOCAL_MIC_SMOKE_TEST.md`: manual PowerShell smoke-test.
- 17 new tests; full suite `336 passed` (no real mic in CI).

### Boundary (preserved)

Capture fail-closed at all three gates. `mic_hardware_enabled` is the hardware privacy gate
(interim: env flag is proxy; production: physical cutoff switch via bridge). Raw PCM,
tempfile path, and recognized text never stored. Recognized text still enters only
`POST /metis/voice/command`.

---

## Next phase (`0BE`)

Wire the existing `POST /metis/voice/confirm` flow into the audio listen pipeline so a
recognized approval phrase (spoken via PTT or wake) can confirm a pending proposal without
a separate HTTP call:

- When `_run_listen_cycle` routes to `/metis/voice/command` and no matching tool route is
  found, if there is a pending proposal, try `/metis/voice/confirm` with the recognized text.
- Readback + explicit-phrase gating from `0AX` remains; still `execution_allowed=false`.
- Gate everything behind the existing `mic_hardware_enabled` + `listen_mode` governance.
- No new execution authority.
