# Active Task

**Current active task:** Phase `0BG` — repair pass in progress/completing.

---

## Phase 0BG — REPAIR PASS

Phase 0BG repairs documentation/state alignment, voice-origin privacy, browser
verbal-path clarity, and local-prototype upload safety. It does not add physical
radio-panel work.

### Delivered

- **Documentation alignment**: current phase is `0BG`; Phase `0BF` is complete at
  commit `56602df` with audit baseline `410 passed`.
- **Voice-origin privacy contract**: recognized voice text may be used transiently
  for routing and response generation, but raw voice text is not persisted in
  canonical state, `chat_history`, `chat_event.user_message`, or provider events.
- **Browser path clarity**: dashboard Hold to Talk uses browser `SpeechRecognition`
  and sends recognized text as a simulated STT hint through `/metis/audio/ptt`.
  It does not upload raw browser audio to faster-whisper.
- **Multipart backend guardrails**: `POST /metis/audio/browser_ptt` remains a
  backend multipart lane and now rejects oversized uploads, unsupported content
  types, empty payloads, and invalid WAV payloads.
- **Tests repaired/added** in `tests/test_phase_0bf_browser_ptt.py`: actual
  provider event shape, sentinel non-persistence, oversized upload, unsupported
  content type, and invalid WAV payload.
- **Verification**: `414 passed` under Python 3.11; `compileall` passed.
  Coverage command was attempted but `pytest-cov`/`coverage` is not installed in
  this Python 3.11 environment.

### Boundary (preserved)

No background listener, no autonomous execution, no physical panel wiring, no
new tool authority, and no dashboard MediaRecorder-to-faster-whisper wiring.

---

## Phase 0BF — COMPLETE

Phase 0BF delivered browser held-to-talk verbal conversation via a multipart audio
upload route that feeds into the existing STT + 0BE confirmation routing cycle.

### Delivered

- **`POST /metis/audio/browser_ptt`** — async multipart route accepting `audio: UploadFile`,
  `stt_provider: str`, `stt_hint: str`, `options_json: str`. Governance gate order mirrors
  `audio_ptt`: `mic_hardware_enabled` → `audio_input_enabled` → `listen_mode==push_to_talk`
  → `power_state==awake`. Returns `wrong_mode` when `listen_mode != push_to_talk`.
- **`_run_stt_route_cycle` helper** extracted from `_run_listen_cycle` — STT transcription +
  0BE routing fork shared by both the existing capture-based routes and the new browser upload
  route. `_run_listen_cycle` unchanged in external contract; all 402 existing tests pass.
- **`CaptureResult` added to module-level import** in `brain.py`.
- **Dashboard "Hold to Talk" button** in the Voice Conversation Test panel:
  `pointerdown` starts browser `SpeechRecognition` when available; release sends the
  recognized text as a simulated STT hint through `/metis/audio/ptt`. It does not
  upload raw browser audio to `browser_ptt` or faster-whisper.
- **8 new tests** in `tests/test_phase_0bf_browser_ptt.py`. Full suite: **410 passed**.

### Boundary (preserved)

`listen_mode` must be `push_to_talk` — `wake_word` and `no_listen` are rejected.
Raw audio bytes are never persisted (in-memory only for the upload request).
`_wav_bytes` excluded from `CaptureResult.to_dict()`, state, and event log.
`execution_allowed` remains `false` after spoken confirmation. No background listener.
No autonomous execution.

---

## Phase 0BE — COMPLETE

Phase 0BE wired the existing `/metis/voice/confirm` flow into the shared
`_run_listen_cycle` so a spoken approval phrase arriving via PTT, wake, or direct
`audio/listen` can confirm a pending proposal without a separate HTTP call.

### Delivered

- **`_run_listen_cycle` routing fork**: after STT, calls `_parse_voice_confirmation` +
  `_pending_proposals`. If pending proposals exist AND the recognized text contains a
  decision phrase or explicit proposal ID → routes to `voice_confirm`; otherwise routes
  to `voice_command` as before. Response includes `route_used` field.
- **`SimulatedSTT` passthrough**: `SIMULATED_TRANSCRIPT_MAP.get(hint) or hint or default`
  — unknown hints return the hint text verbatim, enabling injection of arbitrary
  confirmation phrases in tests.
- **Voice Conversation Test panel** in `dashboard.html`: controls for audio input, mic
  hardware, listen mode, audio provider, STT provider, duration, and hint. Buttons: Listen
  Once, PTT Press, PTT Release, Send Wake Phrase. Syncs with server state on every
  `refresh()`. Reuses `voiceChatOptions()`, `pulseRadioFromVoice()`, `renderVoiceTrace()`,
  `updateRadio()`.
- **13 new tests** in `tests/test_phase_0be_voice_confirm_listen.py`. Full suite: **402 passed**.
- **`docs/VOICE_CONVERSATION_TEST.md`**: PowerShell smoke-test instructions.

### Boundary (preserved)

`execution_allowed` remains `false` after spoken confirmation. No standing approval.
Mic cutoff highest precedence — blocks the PTT release before `_run_listen_cycle` is
entered. Recognized text not persisted; `STTResult.to_dict()` exposes only
`text_len`/`text_hash`/`text_redacted`. No background listener. One utterance per
explicit trigger.

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

## Next phase

After Phase 0BG, choose the next phase from the current repo state. Do not treat
physical radio-panel wiring as the automatic next step until this repair is
reviewed and the next scope is explicitly selected.
