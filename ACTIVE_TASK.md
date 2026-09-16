# Active Task

**Current active task:** Completion release candidate - integration fixes and independent-review regressions are fixture-verified; live device/OAuth/Ollama/MCP acceptance remains pending.

See `docs/COMPLETION_LEDGER.md` for gate owners, dependency state, fixture/live evidence, and exact blockers. Phase 0BM remains preserved below as the prior baseline.

## Completion release verification (2026-09-16)

- Full automated suite: `571 passed in 13.05s` under Python 3.11 (coverage evidence, not a live-capability metric).
- Executable browser voice-capture state-machine harness: passed.
- Isolated wheel build/install: passed; `dashboard.html`, `voice_capture.js`, and `conversation_client.js` are packaged.
- Ordinary-chat fixture integration: local Ollama adapter selected a real registered calendar tool, consumed its structured result, produced a natural answer, and retained the Friday follow-up context.
- Google discovery/selection/disconnect and ordinary Atlas composition are now integrated through the production broker/tool registry. Live microphone, local STT/TTS/Ollama models, Google OAuth, and current Atlas/BOH freshness checks remain target-machine acceptance work and are not claimed complete. OpenAI production dispatch remains explicitly unavailable.

---

## Phase 0BM - COMPLETE

Phase 0BM routes explicit Virtual Chat MCP read requests through a deterministic pre-LLM bridge. BOH and Project Atlas MCP reads now check Tool Control Center modes and server-side MCP gates, call only allowlisted read tools, return bounded sourced responses, and emit sanitized MCP read audit events. Write requests remain proposal-only and direct apply remains blocked.

### Verification

- `python -m pytest tests/test_phase_0bm_chat_mcp_routing.py -q` -> 6 passed.
- `python -m pytest tests/test_phase_0aq_launch_and_policy.py tests/test_phase_0bh_mcp_access.py tests/test_phase_0bi_control_center.py tests/test_phase_0bj_control_center_modes.py tests/test_phase_0bk_mcp_gate_defaults.py tests/test_phase_0bl_local_mcp_config.py tests/test_phase_0bm_chat_mcp_routing.py -q` -> 33 passed.
- `python -m pytest tests/test_phase_0bm_chat_mcp_routing.py tests/test_phase_0e_boh_tool_proposal.py tests/test_phase_0t_tools.py tests/test_phase_0aw_voice_first_tool_awareness.py -q` -> 31 passed.
- `python -m pytest -q` -> 444 passed.
- `python -m compileall -q metis_head tests` -> passed.
- Live BOH MCP chat smoke: `retrieve_context` -> read_only_complete, result_hash=4d5ca0159c4f1a95, grounded result `114 Microbiome Gardener`.
- Live Project Atlas MCP chat smoke: `list_projects` -> read_only_complete, result_hash=3ae759b9dbd97ac0, rendered project names/statuses.
- Live cache smoke: back-to-back BOH MCP chat calls -> first cache_hit=false, second cache_hit=true with same result hash.
- Live combined BOH + Project Atlas MCP chat smoke: one chat response emitted two read events (`get_current_state`, `list_projects`) and returned `multi_read_complete`.

### Boundary

The bridge routes only explicit MCP read intents. Legacy `search boh ...` chat behavior remains in the governed proposal lane. MCP write/apply requests return proposal-only messaging without transport calls. Chat history and event logs store bounded assistant text plus status/hash/timing metadata, not raw MCP payloads, command paths, cwd values, child env, tokens, or local database paths.

---
## Phase 0BL - COMPLETE

Phase 0BL adds optional loading for ignored local MCP configuration and creates local-only BOH/Project Atlas read configuration for this workstation.

### Verification

- `python -m pytest tests/test_phase_0aq_launch_and_policy.py tests/test_phase_0bh_mcp_access.py tests/test_phase_0bi_control_center.py tests/test_phase_0bj_control_center_modes.py tests/test_phase_0bk_mcp_gate_defaults.py tests/test_phase_0bl_local_mcp_config.py -q` -> 27 passed.
- `python -m pytest -q` -> 438 passed.
- `python -m compileall -q metis_head tests` -> passed.
- Local BOH MCP smoke: `get_current_state` -> read_only_complete.
- Local Project Atlas MCP smoke: `list_projects` -> read_only_complete.
- Live `/metis/control_center`: BOH MCP and Project Atlas MCP status -> usable.

### Boundary

Tracked files contain only the loader, ignore rules, tests, and public-safe protocol notes. Private command paths, database paths, and local read shims stay under ignored `.project/`. Direct BOH promotion, Project Atlas apply/delete/push, arbitrary shell execution, and write/apply authority remain blocked.

---

## Phase 0BK - COMPLETE

Phase 0BK makes the local PowerShell launcher default the MCP global, BOH, and Project Atlas gates to active when unset, and clarifies the dashboard disabled-gate wording.

### Verification

- `python -m pytest tests/test_phase_0aq_launch_and_policy.py tests/test_phase_0bi_control_center.py tests/test_phase_0bj_control_center_modes.py tests/test_phase_0bk_mcp_gate_defaults.py -q` -> 16 passed.
- `python -m pytest -q` -> 434 passed.
- `python -m compileall -q metis_head tests` -> passed.

### Boundary

No stdio command paths, child env, tokens, BOH promotion, Project Atlas apply/delete/push, arbitrary shell execution, or direct write/apply authority were added. Without private MCP commands, active gates stop at not_configured.

---

## Phase 0BJ - COMPLETE

Phase 0BJ upgrades the Tool Control Center from boolean toggles to explicit capability modes: Off, Read, Write Proposal, and Read + Write Proposal.

### Verification

- `python -m pytest tests/test_phase_0bi_control_center.py tests/test_phase_0bj_control_center_modes.py -q` -> 10 passed.
- `python -m pytest -q` -> 431 passed.
- `python -m compileall -q metis_head tests` -> passed.

### Boundary

Write mode is proposal/outbox intent only. Direct BOH promotion, Project Atlas apply/delete/push, arbitrary shell execution, and standing approval remain blocked.

---
## Phase 0BI - COMPLETE

Phase 0BI adds a governed Tool Control Center below Virtual Chat. It records replayable operator intent for Tools, BOH MCP, and Project Atlas MCP, and renders sanitized running/usable indicators from existing status endpoints.

### Delivered

- `GET /metis/control_center` composes safe control-center, MCP, and BOH link status without exposing command, cwd, env, token, or secret values.
- `POST /metis/control_center/toggles` records `tool_control_toggle` events in canonical state; toggles do not invoke tools, set env vars, approve proposals, or grant execution.
- The Virtual Chat section now includes a Tool Control Center below the chat/guided-action area with toggles for Tools, BOH MCP, and Project Atlas MCP.
- Focused tests cover disabled defaults, redaction, replay determinism, usable indicators, and dashboard placement.

### Verification

- `python -m pytest tests/test_phase_0bi_control_center.py -q` -> 5 passed.
- `python -m pytest -q` -> 426 passed.
- `python -m compileall -q metis_head tests` -> passed.

### Boundary (preserved)

No BOH promotion, no Project Atlas apply/delete/push, no arbitrary shell, no operator-token handling, no autonomous execution, and no MCP tool invocation from toggles.

---

## Phase 0BG â€” REPAIR PASS

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

## Phase 0BF â€” COMPLETE

Phase 0BF delivered browser held-to-talk verbal conversation via a multipart audio
upload route that feeds into the existing STT + 0BE confirmation routing cycle.

### Delivered

- **`POST /metis/audio/browser_ptt`** â€” async multipart route accepting `audio: UploadFile`,
  `stt_provider: str`, `stt_hint: str`, `options_json: str`. Governance gate order mirrors
  `audio_ptt`: `mic_hardware_enabled` â†’ `audio_input_enabled` â†’ `listen_mode==push_to_talk`
  â†’ `power_state==awake`. Returns `wrong_mode` when `listen_mode != push_to_talk`.
- **`_run_stt_route_cycle` helper** extracted from `_run_listen_cycle` â€” STT transcription +
  0BE routing fork shared by both the existing capture-based routes and the new browser upload
  route. `_run_listen_cycle` unchanged in external contract; all 402 existing tests pass.
- **`CaptureResult` added to module-level import** in `brain.py`.
- **Dashboard "Hold to Talk" button** in the Voice Conversation Test panel:
  `pointerdown` starts browser `SpeechRecognition` when available; release sends the
  recognized text as a simulated STT hint through `/metis/audio/ptt`. It does not
  upload raw browser audio to `browser_ptt` or faster-whisper.
- **8 new tests** in `tests/test_phase_0bf_browser_ptt.py`. Full suite: **410 passed**.

### Boundary (preserved)

`listen_mode` must be `push_to_talk` â€” `wake_word` and `no_listen` are rejected.
Raw audio bytes are never persisted (in-memory only for the upload request).
`_wav_bytes` excluded from `CaptureResult.to_dict()`, state, and event log.
`execution_allowed` remains `false` after spoken confirmation. No background listener.
No autonomous execution.

---

## Phase 0BE â€” COMPLETE

Phase 0BE wired the existing `/metis/voice/confirm` flow into the shared
`_run_listen_cycle` so a spoken approval phrase arriving via PTT, wake, or direct
`audio/listen` can confirm a pending proposal without a separate HTTP call.

### Delivered

- **`_run_listen_cycle` routing fork**: after STT, calls `_parse_voice_confirmation` +
  `_pending_proposals`. If pending proposals exist AND the recognized text contains a
  decision phrase or explicit proposal ID â†’ routes to `voice_confirm`; otherwise routes
  to `voice_command` as before. Response includes `route_used` field.
- **`SimulatedSTT` passthrough**: `SIMULATED_TRANSCRIPT_MAP.get(hint) or hint or default`
  â€” unknown hints return the hint text verbatim, enabling injection of arbitrary
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
Mic cutoff highest precedence â€” blocks the PTT release before `_run_listen_cycle` is
entered. Recognized text not persisted; `STTResult.to_dict()` exposes only
`text_len`/`text_hash`/`text_redacted`. No background listener. One utterance per
explicit trigger.

---

## Phase 0BD â€” COMPLETE

Phase 0BD delivered an event-driven push-to-talk and wake-word listen loop.

### Delivered

- **`POST /metis/audio/ptt {"action":"press"|"release"}`** â€” models the radio PTT button.
  `press` validates `listen_mode==push_to_talk` + full governance chain (mic cutoff â†’
  `audio_input_enabled` â†’ `power_state`); sets `listen_session_active=true`. Does NOT start
  a thread or begin capture. `release` runs exactly one `_run_listen_cycle`, then clears the
  session. A press-less release or release in the wrong mode is a safe no-op.
- **`POST /metis/audio/wake {"text":"..."}`** â€” caller-supplied text simulates a real wake-word
  detector. Case-insensitive prefix match against configurable `wake_phrase` (default `"hey metis"`).
  If match AND `listen_mode==wake_word` AND governance passes, strips phrase and runs one cycle on
  the remainder. Otherwise returns `wake_not_detected` with no capture or routing.
- **`LocalWakeWordDetector` scaffold** â€” `audio_input.py`; disabled, no external imports; stub for
  openWakeWord / Porcupine. Returns `not_enabled` always.
- **`_run_listen_cycle(payload, trigger)`** â€” shared capture â†’ STT â†’ `voice_command` function
  called by `/listen`, `/ptt`, and `/wake`. Governance verified by the caller; `trigger` field
  flows through emitted events to `last_audio_capture.listen_trigger`.
- **New state fields**: `listen_session_active` (default `false`), `wake_phrase` (default
  `"hey metis"`), `last_listen_trigger` (`"ptt"` | `"wake"` | `null`). Set by reducer; configurable
  via `button_event`.
- **`GET /metis/audio/input`** reports all new fields plus `trigger_routes` and `wake_word` scaffold
  entry in `providers`.
- **28 new tests** in `tests/test_phase_0bd_ptt_wake.py`; full suite: **389 passed**.

### Boundary (preserved)

Event-driven and bounded â€” one utterance per explicit PTT or wake trigger, never always-listening.
Mic cutoff highest precedence. Standby is not always-listening. Recognized text redacted; enters
only `POST /metis/voice/command`. No new execution authority.

---

## Phase 0BC â€” COMPLETE

Phase 0BC delivered real local STT behind a hardened swappable `STTProvider` contract.

### Delivered

- **In-memory audio handoff**: `CaptureResult._wav_bytes` (private, non-serialised) carries
  WAV bytes from capture to STT within a single `/metis/audio/listen` request.
  Set by `SimulatedAudioInput` and `LocalMicAudioInput`; absent from `to_dict()`,
  state, event log, and all responses.
- **`LocalFasterWhisperSTT`** â€” real CTranslate2/faster-whisper engine; fail-closed:
  1. `METIS_STT_ALLOW_LOCAL=true` (env opt-in, checked first)
  2. Lazy `from faster_whisper import WhisperModel` inside `transcribe()` only
  3. `METIS_STT_MODEL` (default `small`), `METIS_STT_MODEL_DIR` (offline path)
  4. Model load fail â†’ `model_unavailable`; missing dep â†’ `dependency_unavailable`; no crash
- **Disabled scaffolds**: `VoskSTT`, `OpenAIWhisperSTT`, `WhisperCppSTT` â€” return
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

## Phase 0BB â€” COMPLETE

Phase 0BB enabled real local microphone capture via `LocalMicAudioInput`, triple-gated
and opt-in.

### Delivered

- `LocalMicAudioInput` â€” real `sounddevice` capture, lazy-imported, triple-gated:
  1. `METIS_AUDIO_ALLOW_LOCAL_MIC=true` (env opt-in)
  2. `mic_hardware_enabled` (state/hardware gate, governed in brain.py)
  3. `audio_input_enabled` (software gate, governed in brain.py)
- Capture pipeline: `sounddevice.rec()` â†’ tempfile WAV â†’ Piper WAV-analysis helpers â†’ compact
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
