# Active Task

**Current active task:** Phase `0BC` — Real local STT provider (Whisper or Vosk) as an optional extra, swappable behind `STTProvider`.

Plan: `LocalWhisperSTT` scaffold already exists in `metis_head/stt.py`; only the not-enabled guard and the optional dep need to be lifted.

## Phase 0BB — COMPLETE

Phase 0BB enabled real local microphone capture via `LocalMicAudioInput`, triple-gated and opt-in.

### Delivered

- `LocalMicAudioInput` — real `sounddevice` capture, lazy-imported, triple-gated:
  1. `METIS_AUDIO_ALLOW_LOCAL_MIC=true` (env opt-in)
  2. `mic_hardware_enabled` (state/hardware gate, governed in brain.py)
  3. `audio_input_enabled` (software gate, governed in brain.py)
- Capture pipeline: `sounddevice.rec()` → tempfile WAV → Piper WAV-analysis helpers → compact redacted `CaptureResult`. Tempfile deleted; raw PCM never stored.
- `_audio_capture_governance(require_listen_mode=False|True)` extended; all three audio routes use it.
- `GET /metis/audio/input`: reports `allow_local_mic`, `sounddevice_available`, `input_devices` (tolerates absent dep).
- `mic = ["sounddevice>=0.4"]` optional extra in `pyproject.toml`.
- `docs/LOCAL_MIC_SMOKE_TEST.md`: manual PowerShell smoke-test.
- 17 new tests; full suite `336 passed` (no real mic in CI).

### Boundary (preserved)

Capture fail-closed at all three gates. `mic_hardware_enabled` is the hardware privacy gate (interim: env flag is proxy; production: physical cutoff switch via bridge). Raw PCM, tempfile path, and recognized text never stored. Recognized text still enters only `POST /metis/voice/command`.

## Next phase (`0BC`)

- Enable `LocalWhisperSTT` behind `METIS_STT_ALLOW_LOCAL_WHISPER=true` and optional `whisper = ["openai-whisper"]` extra.
- Same lazy-import pattern; same triple-gate structure as `LocalMicAudioInput`.
- STT result redaction contract unchanged: only `text_len`/`text_hash` in state/events.
