# Active Task

**Current active task:** Phase `0BD` — Wake-word / push-to-talk activation + voice-only
approval confirmation (auto-confirm loop gated behind the existing `listen_mode` and
`mic_hardware_enabled` governance spine).

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

## Next phase (`0BD`)

- **Wake-word and push-to-talk activation loop**: auto-listen when `listen_mode ==
  wake_word` or trigger on button event when `listen_mode == push_to_talk`.
- **Voice-only approval confirmation**: the `/metis/voice/confirm` flow already exists;
  `0BD` should wire it into the audio listen pipeline so a recognized approval phrase
  can confirm a pending proposal without a separate HTTP call.
- Gate everything behind the existing `mic_hardware_enabled` + `listen_mode` governance
  spine; no new execution authority.
