# Metis Head

Simulation-first skeleton for the v0.5 Metis Head buildspec.

This repo intentionally contains no real hardware, microphone, camera, Atlas, or
tool integrations. External systems are represented by versioned adapters and
deterministic mock providers. As of Phase 0B the one live external integration is a
read-only BOH retrieval bridge (opt-in, never mutates BOH, never holds BOH's operator
token).

## Current Phase

Phase scope: `0L` - first approved read-only execution lane for `time.now` (builds on `0A + 0S + 0R virtual chat + 0B retrieval bridge + 0C BOH link + 0S/S4 bridge emulator + 0S/S3 provider harness + 0P personality + 0V voice + 0M manifest + 0X artifacts + 0Y parity + 0V/AUDIO9 animated analyzer + 0T/CHAT governed tools + 0U proposal review + 0W execution audit + 0Q read-only policy`).

Status: Metis can now execute one approved internal read-only lane: `time.now`. The lane requires a
queued proposal and human review, emits an `executed_read_only` audit receipt with bounded output
summary/hash, and still leaves `external_action_executed=false`. Runtime behavior remains locked for
filesystem reads, git commands, network fetches, BOH/Atlas mutation, hardware action, shell execution,
and autonomous execution.

Phase 0L implemented:

- Added `executed_read_only` receipt behavior for approved `time.now` proposals.
- Added bounded `output_summary` and `output_hash` fields to read-only execution receipts.
- Kept approved `math.calculate` as dry-run-only and kept filesystem/git/memory blocked.
- Updated the read-only execution policy to mark only `time.now` as active.
- Added tests for approved time execution, review requirement, replay determinism, and continued
  filesystem/git blocking.

Previous Phase 0Q status: Metis publishes a reviewable read-only execution policy contract. The
contract defines candidate lanes (`time.now`, filesystem read, git status, fetch, and BOH retrieval),
approval gates, redaction requirements, receipt fields, and non-goals.

Phase 0Q implemented:

- Added `docs/READ_ONLY_EXECUTION_POLICY_v0_1.md`.
- Added `metis_head/execution_policy.py` with `metis_read_only_execution_policy.v0.1`.
- Added `GET /metis/execution/policy`.
- Added dashboard Policy control in the Tools panel.
- Added tests proving the contract is available, documented, visible in the dashboard, and does not
  enable side-effectful execution.

Previous Phase 0W status: Metis records execution requests as safe audit receipts without performing
real execution. Requesting execution for unreviewed, denied, or side-effectful proposals produces
blocked receipts; approved side-effect-free dry-run tools produce a dry-run-only receipt. No Phase 0W
path executes tools, reads files, runs git, promotes memory, calls BOH/Atlas, touches hardware, or
performs external actions.

Phase 0W implemented:

- Added `metis_head/execution.py` with `metis_execution_receipt.v0.1` receipts.
- Added canonical `execution_audit_log` state and replayable `execution_request` events.
- Added `GET /metis/execution/receipts`, `GET /metis/execution/receipts/{receipt_id}`, and
  `POST /metis/proposals/{proposal_id}/request_execution`.
- Added dashboard execution-request and receipt-refresh controls in the Tools panel.
- Preserved redaction boundaries: no secrets, raw file contents, command output, or external
  receipts are stored in execution receipts.
- Preserved `external_action_executed=false` for all Phase 0W paths.

Previous Phase 0U status: Metis can review queued proposals through deterministic approve/deny events
and FastAPI endpoints. A proposal review changes review state, emits a review receipt, and recomputes
pending counters, but it still does not execute tools, read files, run git, promote memory, call
BOH/Atlas, or perform external actions. Approval is explicitly not execution in Phase 0U.

Phase 0U implemented:

- Added `proposal_review` reducer events for replayable approve/deny transitions.
- Added review metadata to proposal records: `review_status`, `reviewed_at`, `review_decision`,
  `review_reason`, and `review_receipt`.
- Added `metis_proposal_review.v0.1` receipts with `execution_allowed=false` and
  `execution_status=not_executed`.
- Added `GET /metis/proposals/{proposal_id}`, `POST /metis/proposals/{proposal_id}/approve`, and
  `POST /metis/proposals/{proposal_id}/deny`.
- Added dashboard proposal review controls in the Tools panel.
- Preserved deterministic replay and the no-execution boundary for safe, side-effectful, memory,
  filesystem, git, BOH, Atlas, hardware, and external actions.

Previous Phase 0T/CHAT status: Metis has a native governed tool registry with MCP-inspired manifests,
seeded safe tools, proposal records, dry-run receipts, and deterministic routing for clear tool
requests in virtual chat. Safe Human Mode chat requests such as simple arithmetic can return a
dry-run receipt through `tool_router` without requiring an LLM provider; Agent Mode and side-effectful
tools always queue proposals with `execution_allowed=false`.

Phase 0T implemented:

- Added `metis_head/tool_registry.py` with `metis_tool_registry.v0.1` manifests and
  `metis_tool_receipt.v0.1` dry-run receipts.
- Seeded `time.now`, `text.summarize`, `math.calculate`, `filesystem.read_proposed`,
  `git.status_proposed`, and `memory.propose`.
- Added `/metis/tools`, `/metis/tools/{tool_id}`, `/metis/tools/propose`,
  `/metis/tools/{tool_id}/dry_run`, and `/metis/tools/{tool_id}/execute`.
- Extended proposal records with tool ID, sanitized arguments, risk class, side-effect class,
  dry-run availability, and `execution_allowed=false`.
- Added a compact dashboard Tools panel for registry inspection, dry-run, and proposal queueing.
- Added deterministic chat-to-tool routing for explicit `time.now`, `math.calculate`,
  `text.summarize`, `filesystem.read_proposed`, `git.status_proposed`, and `memory.propose`
  intents.
- Added `options.tools.enabled=false` to bypass chat tool routing and use the selected LLM provider.
- Used public MCP reference servers as pattern donors only; no runtime dependency was added.

Previous Phase 0V/AUDIO9 status: the tuning-window visualizer animated through time-sliced spectrum frames from the
actual Piper WAV instead of holding one aggregate spectrum shape. The dashboard played those frames
over the speech duration, kept the full-height mirrored analyzer, and used the project color
`#3AA3A7` as the primary phosphor/LED tone.

Phase 0V/AUDIO9 implemented:

- Added `audio_spectrum_frames` and `audio_spectrum_frame_count` to Piper TTS events.
- Extracted compact per-frame spectrum data from the generated Piper WAV for voice-reactive motion.
- Updated the dashboard to animate analyzer frames over the voice duration.
- Switched the analyzer base color from green to `#3AA3A7`.
- Kept aggregate `audio_spectrum_levels` and `audio_levels` for compatibility and reset/decay.

Previous Phase 0V/AUDIO8 status: the tuning-window visualizer filled its panel like a real
instrument. Piper synthesis still produced truthful `audio_spectrum_levels` from the generated WAV,
and the dashboard resampled that signal into a full-height mirrored spectrum analyzer with
per-utterance gain normalization, brighter phosphor-style segments, peak ticks, afterimage decay,
and idle reset.

Phase 0V/AUDIO8 implemented:

- Expanded the vertical analyzer from a compact cluster into a full-panel instrument surface.
- Added UI-side spectrum resampling so real Piper bands occupy the full tuning-window height.
- Added per-utterance visual gain normalization, preserving the real frequency shape while reducing
  wasted empty space.
- Improved the phosphor/LED aesthetic with deeper glass, grid, glow, color thresholds, and peak
  ticks.

Previous Phase 0V/AUDIO7 status: the tuning-window visualizer returned to a vertical mirrored analog
spectrum analyzer. Piper synthesis produced `audio_spectrum_levels` from the actual generated WAV;
the dashboard rendered those frequency-band levels bottom-to-top with matching left/right LED traces,
a short afterimage decay, and an idle reset after the current voice task completed.

Phase 0V/AUDIO7 implemented:

- Added Piper WAV spectrum extraction for truthful, audio-derived visualizer metadata.
- Reworked the dashboard tuning-window visualizer into a vertical mirrored spectrum analyzer.
- Preserved buildspec intent: the strip is an instrument/status visualizer, not eyes, mood lighting,
  or a hallucinated animation layer.
- Kept `audio_levels` as compatibility metadata while preferring `audio_spectrum_levels` for the UI.
- Kept the short `voice-decay` afterimage state and idle reset after voice duration.

Previous Phase 0V/AUDIO6 status: the tuning-window visualizer used a horizontal, two-sided old-stereo scope style with a
centerline glow and short afterimage decay. It reset to an idle line after the current voice task
completed instead of holding the last waveform.

Phase 0V/AUDIO6 implemented:

- Reworked the dashboard tuning-window visualizer from flat vertical bars into a glowing two-sided
  horizontal scope trace.
- Added a short `voice-decay` afterimage state that clears within one second after voice duration.
- Added explicit reset to the idle centerline after the current voice task completes.
- Kept the data source truthful: waveform height still comes from Piper WAV `audio_levels`, not
  random/decorative motion.

Previous Phase 0V/AUDIO5 status: the tuning-window visualizer behaves like an old stereo instrument: for Piper
speech, Metis extracts a compact RMS envelope from the actual synthesized WAV and renders it through
the radio strip. It is still a simulator preview, not final LED firmware, but it is driven by
generated audio data rather than decorative/random animation.

Phase 0V/AUDIO5 implemented:

- Piper voice events include a compact `audio_levels` envelope derived from the generated WAV.
- The dashboard radio strip renders a vertical waveform trace from those levels.
- The trace flows bottom-to-top to match the planned vertical tuning-window format.
- Idle remains a dim vertical instrument line; blocked/failure precedence still comes from the LED
  resolver/state path.
- No raw audio file path, raw audio, or spoken text is persisted in the event log.

Previous Phase 0V/AUDIO4 status: Piper playback launches asynchronously after synthesis, so the mock Brain can return the
chat response while audio is playing instead of after playback finishes. The dashboard uses the TTS
event metadata to pulse the virtual radio strip for an estimated speech duration.

Phase 0V/AUDIO4 implemented:

- Piper playback mode defaults to `async`.
- Temporary WAV cleanup happens after background playback completes.
- Voice events include `playback_mode` and `audio_visualization_hint_ms`.
- Dashboard chat rendering updates from the returned state before the follow-up refresh.
- The virtual radio strip pulses from the returned voice event duration hint.

Previous Phase 0V/AUDIO3 status: Piper receives a normalized spoken form of chat text rather than the display Markdown.
The dashboard can still show headings, bullets, links, and code formatting, but the voice path strips
or converts formatting markers that sound bad when read aloud.

Phase 0V/AUDIO3 implemented:

- Added `normalize_spoken_text()` for TTS input.
- Piper speaks the normalized text while screen chat keeps the original assistant message.
- Markdown headings, bullets, links, inline code marks, asterisks, block quotes, and table pipes are
  removed or converted for audibility.
- Voice events include redacted source text length/hash and normalized text metadata; raw spoken
  text is still not persisted.
- Piper synthesis timeout now scales up for longer normalized responses.

Previous Phase 0V/AUDIO2 status: Piper playback now defaults to Windows `Media.SoundPlayer` through a PowerShell subprocess,
with `winsound` still available as an explicit fallback strategy. This fixes the previous
`winsound.SND_SYNC` playback bug on this machine and makes endpoint playback less dependent on
uvicorn's Python audio session.

Phase 0V/AUDIO2 implemented:

- Replaced invalid `winsound.SND_SYNC` usage.
- Added configurable Piper playback strategy: `soundplayer` or `winsound`.
- Dashboard Piper requests now use `soundplayer`.
- Voice events include the effective playback strategy.
- Tests cover both playback paths.
- Subagent review confirmed the main failure mode was playback, not Piper synthesis.

Previous Phase 0V/AUDIO+ status: Piper is installed in the Python 3.11 runtime used by the mock Brain, and the requested
`rhasspy/piper-voices` `en_US/hfc_female/medium` model is downloaded locally under `models/`
(ignored by git). The backend auto-detects the local Piper executable and this default model/config
when present, while the dashboard still allows per-request overrides.

Phase 0V/AUDIO+ implemented:

- Installed `piper-tts` into the local Python 3.11 runtime.
- Downloaded `en_US-hfc_female-medium.onnx` and `en_US-hfc_female-medium.onnx.json` from
  `rhasspy/piper-voices`.
- Added repo-local default Piper path discovery for the downloaded model/config.
- Added dashboard auto-fill for Piper executable, model, and config paths.
- Added `voice` optional dependency metadata for future environment setup.
- Ignored `models/` so large local voice assets are not committed.

Previous Phase 0V/AUDIO status: Metis can route governed voice output to a local Piper CLI provider
when configured. The mock Brain dashboard exposes Piper path fields, sends a per-request local
playback opt-in, and the virtual radio meter pulses from TTS output events.

Phase 0V/AUDIO implemented:

- `PiperVoiceProvider` invokes a local Piper executable with text on stdin and a temporary WAV
  output file.
- Local WAV playback uses Windows `winsound` after Piper synthesis.
- Piper stays local and opt-in: select `piper` in the UI or set the environment variables below.
- The dashboard exposes `Piper executable path` and `Piper .onnx model path` fields when Piper is
  selected.
- The virtual radio AM/FM-style meter now pulses when voice output is queued/speaking or a new TTS
  output completes.

Previous Phase 0V/UI status: the mock Brain dashboard now exposes voice selection and a voice-reply switch in the
Virtual Chat panel. Chat requests include `options.voice.speak_response=true` only when the switch
is enabled.

Phase 0V/UI implemented:

- Voice provider selector populated from `/metis/voice/options`.
- Voice ID selector with unsupported candidate voices disabled until implemented.
- `Voice replies` switch for chat responses.
- `Preview Voice` action through `/metis/voice/preview`.
- Voice status line showing selected option, status, and privacy class.

Previous Phase 0V+ status: Metis exposes reviewable voice options. The current voice is
`metis-counsel-mock`, which is local and non-audible; real audible voice choices remain gated or
candidate status until explicitly approved.

Phase 0V+ implemented:

- `GET /metis/voice/options`
- `metis_voice_options.v0.1` catalog with current, gated, and candidate voice options.
- Current option: `metis-counsel-mock` (`mock`, local no-audio).
- Gated option: `windows-system-tts` (`system`, local OS audio shape, disabled by default).
- Candidate options: `piper-local` and `openai-tts`, review-only for now.

Previous Phase 0Y status: every hardware parity manifest item points to an executable scenario, and the manifest
has a validator used by tests and the simulation manifest. The computed simulation readiness
checklist has no partial/failed/unknown items.

Phase 0Y implemented:

- Added executable scenarios for volume control, conversation-depth control, and bridge heartbeat.
- Updated `HARDWARE_PARITY_MANIFEST` so every item references a real scenario ID.
- Added `validate_hardware_parity_manifest()`.
- `metis_sim_tests.v0.1` now reports `hardware_parity_validation`.
- Readiness checklist now marks hardware parity as `pass`.

Previous Phase 0X status: Metis can persist portable JSON artifacts for state exports and simulation manifests
inside a local `artifacts/` directory. This keeps review snapshots shareable without adding a
database.

Phase 0X implemented:

- `metis_head/artifacts.py`: safe artifact save/list/read helpers with `metis_artifact.v0.1`
  envelopes and filename/path validation.
- `POST /metis/artifacts/save` for `export` and `manifest` artifacts.
- `GET /metis/artifacts` and `GET /metis/artifacts/{filename}`.
- Readiness checklist now marks persistence/config export as `pass`.

Previous Phase 0M status: Metis publishes a portable `metis_sim_tests.v0.1` manifest that inventories scenarios,
acceptance coverage, readiness, hardware parity, schemas, and simulation boundaries.

Phase 0M implemented:

- `metis_head/sim_manifest.py`: manifest builder with scenario summaries, acceptance requirement
  coverage, computed readiness, hardware parity manifest, and boundary list.
- `GET /metis/sim/manifest` and `GET /metis/sim/tests`.
- Tests proving the manifest is versioned, computed, endpoint-accessible, and mapped to required
  acceptance coverage.

Previous Phase 0V status: Metis has a simulation-first voice output harness. It supports mock voice output,
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
- Governed tool registry and dry-run/proposal lane for safe tool review without execution.
- Virtual radio view rebuilt as a 3-zone instrument: an inert speaker grille, a thin vertical LED/visualizer status strip, and a right control stack (Volume + Depth dials, PWR/LOUD/AFC/AM-FM buttons, large Tuning/Initiative dial). Radio status readouts (power/audio/mode/authority) and mic/camera cutoff controls live in a separate Radio Status panel below.
- Export/replay controls for state snapshots and JSON/JSONL event logs.
- Governed LLM router with `MockLLMProvider`, `OllamaLLMProvider`, and `OpenAILLMProvider`.
- Metis personality constitution injected into governed chat prompts.
- Governed voice output harness for mock/system-shaped TTS, with output mute enforcement.
- Reviewable voice options catalog showing current, gated, and candidate voices.
- Dashboard controls for voice provider/voice selection and chat voice-reply toggle.
- Local Piper voice output path with dashboard-provided executable/model overrides.
- Radio meter visualization tied to TTS output events.
- Portable simulation test manifest for acceptance coverage, scenarios, readiness, and parity links.
- Portable JSON artifact persistence for exports and simulation manifests.
- Executable hardware parity manifest for every simulated physical control.
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
$env:METIS_VOICE_PROVIDER="mock"       # mock, system, or piper
$env:METIS_VOICE_ID="metis-counsel-mock"
$env:METIS_VOICE_RATE="1.0"
$env:METIS_VOICE_VOLUME="0.6"
$env:METIS_VOICE_ALLOW_SYSTEM_TTS="false"
$env:METIS_VOICE_ALLOW_PIPER="false"
$env:METIS_PIPER_EXE="B:\path\to\piper.exe"
$env:METIS_PIPER_MODEL="B:\path\to\voice.onnx"
$env:METIS_PIPER_CONFIG="B:\path\to\voice.onnx.json"   # optional
$env:METIS_PIPER_PLAYBACK="true"
$env:METIS_PIPER_PLAYBACK_STRATEGY="soundplayer"       # soundplayer or winsound
$env:METIS_PIPER_PLAYBACK_MODE="async"                 # async or sync
$env:METIS_VOICE_NORMALIZE_TEXT="true"
```

Default local Piper paths are auto-detected when installed/downloaded:

```text
C:\Users\peckm\AppData\Local\Programs\Python\Python311\Scripts\piper.exe
B:\dev\metis_head\metis_head\models\piper\en_US\hfc_female\medium\en_US-hfc_female-medium.onnx
B:\dev\metis_head\metis_head\models\piper\en_US\hfc_female\medium\en_US-hfc_female-medium.onnx.json
```

`system` is present as a gated provider shape only. Real OS speech remains disabled unless
`METIS_VOICE_ALLOW_SYSTEM_TTS=true`; the default `mock` provider emits deterministic TTS events
without audio.

For local audible speech, choose `piper` in the dashboard, enter the local Piper executable and
`.onnx` model paths, turn on `Voice replies`, then use `Preview Voice` or send a chat response.
The dashboard request sets `allow_piper=true` for that selected local provider; text is passed to
Piper over stdin and raw speech text is still not persisted in the Metis event log.

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
can queue proposals only and never mutates BOH. Phase 0T tool endpoints expose dry-run receipts and
proposal records only; filesystem, git, memory promotion, external, hardware, BOH, and Atlas actions
are not executed.

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
- `POST /metis/artifacts/save`
- `GET /metis/artifacts`
- `GET /metis/artifacts/{filename}`
- `GET /metis/sim/manifest`
- `GET /metis/sim/tests`
- `GET /metis/boh/status`
- `GET /metis/llm/options`
- `GET /metis/tools`
- `GET /metis/tools/{tool_id}`
- `GET /metis/proposals/{proposal_id}`
- `GET /metis/execution/receipts`
- `GET /metis/execution/receipts/{receipt_id}`
- `GET /metis/execution/policy`
- `POST /metis/event`
- `POST /metis/chat` (selected LLM provider, or `tool_router` for explicit governed tool requests)
- `POST /metis/proposals/{proposal_id}/approve`
- `POST /metis/proposals/{proposal_id}/deny`
- `POST /metis/proposals/{proposal_id}/request_execution`
- `POST /metis/tools/propose`
- `POST /metis/tools/{tool_id}/dry_run`
- `POST /metis/tools/{tool_id}/execute`
- `GET /metis/voice`
- `GET /metis/voice/options`
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
130 passed under Python 3.11 (includes approved `time.now` read-only execution, read-only execution policy contract, execution receipt/audit contract, governed proposal review, governed tool registry/dry-run lane, explicit chat-to-tool routing, animated Piper spectrum frames, virtual chat, BOH link, voice, artifacts, and hardware parity coverage)
```

Phase 0B/0C tests monkeypatch the HTTP layer (`metis_head.boh_retrieval._post_json` and
`metis_head.boh_link._request`), so no running BOH instance is required to verify the suite.

Known environment note: Python 3.13 is present on this machine but did not have `pytest` installed during Phase 0A/0S verification.

## Boundaries

Phase 0A/0S/0R/0T/0U/0W/0Q/0L does not implement real hardware, microphone, camera, Project Atlas integration, side-effectful external tools, or autonomous execution. As of Phase 0B/0C the only live external integration is the read-only BOH link: the retrieval bridge (`/api/retrieve`, opt-in via `METIS_BOH_ENABLED`) and the background link manager (`/api/health` + `/api/retrieve/status` + a `limit=1` `/api/retrieve` probe, opt-in via `METIS_BOH_BACKGROUND_ENABLED`). Neither mutates BOH, holds BOH's operator token, nor copies the BOH corpus into Metis — BOH remains the source of truth. Phase 0L allows only approved internal `time.now` read-only execution. Filesystem, git, fetch, BOH/Atlas mutation, hardware, shell, memory promotion, and external actions remain blocked. Other reference repositories remain pattern donors only.
