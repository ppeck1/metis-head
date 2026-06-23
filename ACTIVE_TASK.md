# Active Task

**Current active task:** Phase `0BB` — Enable `LocalMicAudioInput` (real device capture behind explicit config + hardware cutoff).

Plan: Next phase scaffolded in `metis_head/audio_input.py` (`LocalMicAudioInput` provider).

## Phase 0BA — COMPLETE

Phase 0BA added the modular audio-intake layer for the radio form factor. All work is committed.

### Delivered

- `metis_head/audio_input.py` — `audio_input_adapter.v0.1`: `NoneAudioInput`, `SimulatedAudioInput`, disabled `LocalMicAudioInput` scaffold.
- `metis_head/stt.py` — `stt_engine.v0.1`: `NoneSTT`, `SimulatedSTT`, disabled `LocalWhisperSTT` scaffold.
- Canonical state: `audio_input_state`, `audio_input_enabled`, `listen_mode`, `last_audio_capture`, `input_adapters.audio_input`.
- Endpoints: `GET /metis/audio/input`, `POST /metis/audio/input/capture`, `POST /metis/audio/transcribe`, `POST /metis/audio/listen`.
- 35 tests; full suite `319 passed`.

### Boundary (preserved)

Capture fail-closed behind `mic_hardware_enabled`. STT output redacted. Recognized text enters the existing `POST /metis/voice/command` governed route only. No real microphone, no new deps, no new execution authority.

## Next phase (`0BB`)

- Enable `LocalMicAudioInput` behind explicit config (`METIS_AUDIO_ALLOW_LOCAL_MIC=true`) **and** hardware cutoff.
- Add `sounddevice` as an optional extra; tested locally, not in CI.
- Provider slot already exists; only the not-enabled guard needs to be lifted.
