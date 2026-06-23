# Phase 0BA — Audio Input + STT Adapter Plan

Status: **active task** (planning complete, implementation pending). See `/ACTIVE_TASK.md`.

Phase target: a modular, simulation-first **audio-input and speech-to-text layer** for the radio form
factor. It captures audio and produces recognized text through governed, swappable providers, gated by
the hardware mic cutoff. No real microphone and no new runtime dependency are enabled in this phase —
real capture and real STT engines are scaffolded as **disabled** providers for a later phase.

Spec traceability: buildspec section 2.5 (hardware mic cutoff, core requirement), section 3.4–3.5
(standby/listening clarity, output mute is not privacy), section 8.3 (metis-audio responsibilities),
section 13 (provider abstraction pattern). Reuses the existing `stt` adapter slot
(`stt_adapter.v0.1`) and the redacted STT-style `provider_event` records already emitted by
`POST /metis/voice/command`.

---

## 1. Design Principle — Where This Sits

The intake pipeline is three swappable stages. This phase adds the first two as simulated providers
and wires them into the existing governed voice path:

```
[mic hardware] -> AudioInputProvider.capture() -> STTProvider.transcribe() -> recognized text
                                                                                   |
                                                          existing POST /metis/voice/command
                                                          (governed chat/tool routing, redacted)
```

Each stage is a narrow provider behind a Metis-owned interface (buildspec section 1.6: provider vs
adapter vs authority). Providers are selected by config, default to `none`/disabled, and have mock
implementations for tests. Nothing downstream changes: recognized text still enters the same
already-governed `/metis/voice/command` route, so tool gates, approval queues, and redaction are
inherited, not re-implemented.

**Keep it modular and simple:** small interfaces, deterministic mock providers, config-driven
selection, fail-closed for capture, fail-visible for status.

---

## 2. New Modules

### 2.1 `metis_head/audio_input.py`

```python
class AudioInputProvider:           # base interface
    provider_id: str
    schema_version: str             # "audio_input_adapter.v0.1"
    def health(self) -> dict: ...
    def capture(self, context: CaptureContext) -> CaptureResult: ...
```

Providers:

| Provider | Status this phase | Behavior |
|---|---|---|
| `NoneAudioInput` | active baseline | No capture; reports `disabled`. Required safe default. |
| `SimulatedAudioInput` | active | Reads a repo-local fixture WAV (or caller-supplied PCM), returns compact `audio_levels` / `audio_spectrum_frames` and `audio_duration_ms`. Reuses the Piper WAV-analysis helpers from the voice path. |
| `LocalMicAudioInput` | **scaffolded, disabled** | Placeholder for a real device (e.g. `sounddevice`). Raises a governed "not enabled" result unless explicit config **and** hardware cutoff allow it. No dependency imported in this phase. |

`CaptureResult` carries only redacted metadata: `provider_id`, `status`, `audio_duration_ms`,
compact `audio_levels`, `frame_count`, `sample_rate`, `captured` (bool), `block_reason` — **never** a
raw audio path or raw PCM in state/event log.

### 2.2 `metis_head/stt.py`

```python
class STTProvider:                  # base interface
    provider_id: str
    schema_version: str             # "stt_engine.v0.1"
    def health(self) -> dict: ...
    def transcribe(self, capture: CaptureResult, context) -> STTResult: ...
```

Providers:

| Provider | Status this phase | Behavior |
|---|---|---|
| `NoneSTT` | active baseline | Returns `unavailable`; no transcription. |
| `SimulatedSTT` | active | Deterministic map from a fixture id / supplied hint to canonical recognized text (e.g. `"git status"`, `"what time is it"`). No model, no network. |
| `LocalWhisperSTT` / `VoskSTT` | **scaffolded, disabled** | Placeholder for a real local engine. Disabled by default; no dependency imported this phase. |

`STTResult` carries only: `provider_id`, `status`, `text_len`, `text_hash`, `text_redacted=true`,
`confidence` (mock), and the recognized text passed **in-memory** to the voice route. Raw transcript
text is never persisted to state or the event log (matches existing voice redaction).

---

## 3. Capture Governance (Core)

`capture()` must check, in order, and fail closed:

1. **Hardware mic cutoff** — if `mic_hardware_enabled is False`: return `captured=false`,
   `block_reason="mic_hardware_cutoff"`, increment `blocked_capture_count`, emit a redacted
   `provider_event`. No STT, no routing. (Highest precedence; matches panel/LED rules.)
2. **Software enable** — `audio_input.enabled` config flag, default `false`. If off: `captured=false`,
   `block_reason="audio_input_disabled"`.
3. **Power/standby** — only capture when `power_state == "awake"` and the configured listen mode
   (`wake_word` | `push_to_talk` | `no_listen`) permits it. Standby must not imply always-listening
   (buildspec 3.4).
4. On success: emit redacted STT-style `provider_event` (`transcribing` → `complete`), update
   `audio_input_state`, and (for the orchestrated route) hand recognized text to
   `/metis/voice/command`.

A software mute (`output_muted`) must **never** gate capture and must never be shown as privacy
(buildspec 3.5). Mic cutoff is the only privacy control.

---

## 4. Canonical State Additions

Add to `baseline_state()` (all default to safe/off):

- `audio_input_state`: `disabled | idle | capturing | transcribing | blocked | failed` (default `disabled`).
- `audio_input_enabled`: `false`.
- `listen_mode`: `no_listen` (default) | `wake_word` | `push_to_talk`.
- `last_audio_capture`: redacted metadata of the most recent capture (no raw audio), or `null`.
- Reuse existing `input_adapters.stt` for STT health; add `input_adapters.audio_input`
  (`audio_input_adapter.v0.1`).

New `provider_event` shapes reuse the existing redacted STT event family; add
`failure` ids only if needed: `stt_failure` already exists.

---

## 5. Endpoints (modular, small)

| Route | Purpose |
|---|---|
| `GET /metis/audio/input` | Status: providers available, selected provider, health, `audio_input_state`, `listen_mode`, cutoff state. |
| `POST /metis/audio/input/capture` | Simulated capture only → returns redacted `CaptureResult` (frames/levels/duration). No transcription, no routing. |
| `POST /metis/audio/transcribe` | Run the selected STT provider over a (simulated) capture → redacted `STTResult`. No routing. |
| `POST /metis/audio/listen` | Orchestrated simulated path: capture → transcribe → forward recognized text to existing `/metis/voice/command` governance. Respects cutoff and `listen_mode`. |

`/metis/audio/listen` adds **no** new execution authority: it is a thin upstream feeder into the
already-governed voice-command route.

---

## 6. Dashboard / Panel (optional this phase)

- Reuse the existing analyzer: feed captured `audio_levels` / `audio_spectrum_frames` into the same
  tuning-window visualizer used for TTS so input audio drives the radio meter too.
- The `panel_render.v0.1` `voice_indicator` already covers `command_active`; `mic_cutoff_indicator`
  already covers privacy. No panel contract change required.

---

## 7. Tests (must pass with no hardware, no new deps)

1. Mic cutoff blocks capture before STT/routing; `blocked_capture_count` increments; redacted event only.
2. `audio_input_enabled=false` blocks capture with `audio_input_disabled` reason.
3. `SimulatedAudioInput.capture()` returns deterministic frames/levels/duration from a fixture WAV.
4. `SimulatedSTT.transcribe()` is deterministic and returns canonical recognized text.
5. `/metis/audio/listen` routes recognized `"git status"` through the existing governed path and queues
   the expected `git.status` proposal — **without** executing it.
6. No raw audio path, raw PCM, or raw transcript text appears in state, event log, or any response —
   asserted by string scan.
7. `LocalMicAudioInput` / `LocalWhisperSTT` remain disabled and raise a governed not-enabled result.
8. Replay determinism: identical events → identical audio-input state.
9. No new `external_action_executed`, no execution authority added.

Target: existing suite plus these tests stays green under Python 3.11.

---

## 8. Non-Goals (this phase)

- No real microphone capture.
- No real STT engine or model download; no `sounddevice`/`whisper`/`vosk` dependency imported.
- No wake-word engine (only the `listen_mode` flag and gating semantics).
- No always-listening standby.
- No new execution authority, tool lane, or external action.
- No change to the approval/governance boundary.

---

## 9. Follow-on Phases

- `0BB` — enable `LocalMicAudioInput` behind explicit config + hardware cutoff on the user's machine
  (adds `sounddevice` as an optional extra; tested locally, not in CI).
- `0BC` — real local STT provider (Whisper/Vosk) as an optional extra, swappable behind `STTProvider`.
- `0BD` — wake-word / push-to-talk loop and the voice-only approval confirmation protocol.

---

## 10. Boundary Statement

This phase adds intake plumbing only. Capture is fail-closed behind the hardware mic cutoff; STT
output is redacted; recognized text re-enters the existing governed voice-command route rather than a
new privileged path. Hardware and real engines plug into `audio_input_adapter.v0.1` /
`stt_engine.v0.1` later without changing the governance spine.
