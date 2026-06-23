# Metis Head Project Variable Map

Version: `metis_variable_map.v0.2`

Last phase updated: `0BD` (push-to-talk and wake-word listen loop)

Full phase chain: `0A 0S 0S/S3 0S/S4 0M 0X 0Y 0R 0P 0V 0V/AUDIO9–12 0B 0C 0E 0T 0U 0W 0Q 0L 0G 0F 0J 0K 0N 0D 0I 0H 0AA–0AG 0AH–0AO 0AP–0AY 0AZ 0BA 0BB 0BC 0BD`

Purpose: keep canonical names, state fields, event fields, API routes, adapter IDs,
scenario IDs, and future build placeholders reviewable before each phase commit.

---

## Phase Commit Checklist

Before committing any phase:

- Update `README.md` with current phase status, run commands, verification, and limitations.
- Update this file with all new or changed variables, routes, events, adapters, readiness domains, and scenarios.
- Keep reference repos as read-only pattern donors. Do not record them as runtime dependencies unless a future adapter contract explicitly allows it.

---

## Notes

| Phase | Decision / Constraint | Rationale |
|---|---|---|
| `0BD` | Listen loop is event-driven and bounded — one capture→STT→route cycle per explicit PTT or wake trigger; never an always-listening background thread. | Core design principle. Standby must not imply hidden listening. Mic cutoff is highest precedence. |
| `0BD` | `POST /metis/audio/ptt press` sets `listen_session_active=true` but does NOT start capture. Capture only runs on `release`. | Separates intent signal from capture execution; lets governance fire once with correct state. |
| `0BD` | `POST /metis/audio/wake` requires caller-supplied text (no embedded audio stream). `LocalWakeWordDetector` is a disabled scaffold with no external imports. | Real wake-word engine (openWakeWord/Porcupine) is future-phase; simulated path exercises full governed cycle now. |
| `0BD` | `wake_phrase` defaults to `"hey metis"`, case-insensitive prefix match. Configurable via `button_event`. | Allows integration test flexibility without code changes; casing normalised in reducer and wake route. |
| `0BD` | `last_listen_trigger` is set by the reducer from `ptt_released` / `wake_triggered` events; `/metis/audio/listen` does not set it (keeps legacy route neutral). | Keeps the three routes distinct in audit trail without breaking existing tests. |
| `0BD` | Recognized text flows into `user_intent` events by design (the governed output channel). STT-level events never carry raw text. | `user_intent.intent` is the correct redacted summary field; blocking it from `user_intent` would break tool routing. |
| `0BC` | `CaptureResult._wav_bytes` is a private in-memory field only; `to_dict()` excludes it. | Prevents WAV bytes from ever entering state, event log, or API responses. |
| `0BB` | Triple gate for real mic: `METIS_AUDIO_ALLOW_LOCAL_MIC` env + `mic_hardware_enabled` state + `audio_input_enabled` state. All three must hold before any device access. | Defense-in-depth; env gate as CI/test barrier, state gates as runtime governance. |
| `0AX` | `/metis/voice/confirm` never requests execution or grants standing approval. Explicit proposal-specific phrase required. | Simulated voice confirmation must not weaken the approval gate. |
| `0AW` | Tool/capability questions are answered deterministically before LLM generation. | Prevents provider drift; LLM should not say "I have no tools." |
| `0AQ` | `METIS_REPO_ROOT` set by launch script; read-only lanes use it as allowlist anchor. | Prevents clean-export tests from reading outside repo root. |
| `0Q` | `execution_enabled=false` covers arbitrary/autonomous execution only; scoped approved read-only receipts are represented separately as `scoped_read_only_receipts_enabled=true`. | Distinction matters for operator review: blocking general execution ≠ blocking safe read-only receipt lanes. |
| General | Reference repos (MCP, openWakeWord, Porcupine, etc.) are pattern donors only. Never vendored, imported, or spawned. | Keeps dependency surface explicit and auditable. |
| General | All schema versions are caller-visible; reducers validate event type before mutating state. | Enables replay determinism and handoff reproducibility. |

---

## Public Repository Media

| Name | Path | Type | Notes |
|---|---|---|---|
| `PUBLIC_REPO_TARGET` | `https://github.com/ppeck1/metis-head` | public GitHub URL | Intended public repository for the current Metis Head project. |
| `METIS_RADIO_REFERENCE_IMAGE` | `docs/assets/metis-radio-reference.jpg` | tracked image asset | Physical Magnavox radio reference supplied for the public repo. |
| `METIS_VISUAL_REPRESENTATION_IMAGE` | `docs/assets/metis-head-visual-representation.png` | tracked image asset | Planned implementation visual representation supplied for the public repo. |
| `METIS_DASHBOARD_PUBLIC_SCREENSHOT` | `docs/screenshots/metis-dashboard-public.png` | tracked screenshot | Headless Edge capture of the current mock Brain dashboard at `http://127.0.0.1:8791/`. |

---

## Schema Versions

| Name | Current Value | Owner | Notes |
|---|---|---|---|
| `STATE_SCHEMA_VERSION` | `metis_state.v0.3` | `metis_head.schemas` | Canonical state schema version from v0.5 buildspec state object. |
| `EVENT_SCHEMA_VERSION` | `metis_event.v0.1` | `metis_head.schemas` | Phase 0S mock Brain event envelope version. |
| `READINESS_CHECKLIST_VERSION` | `metis_readiness.v0.1` | `metis_head.schemas` | Computed readiness checklist version. |
| `BRIDGE_SCHEMA_VERSION` | `metis_bridge_event.v0.1` | `metis_head.bridge` | Simulated bridge event protocol version. |
| `BRIDGE_EMULATOR_VERSION` | `metis_bridge_emulator.v0.1` | `metis_head.bridge_emulator` | CLI/library wrapper for simulator bridge event emission and replay. |
| `PROVIDER_HARNESS_VERSION` | `metis_provider_harness.v0.1` | `metis_head.provider_harness` | Mock provider catalog/invocation harness version. |
| `PERSONALITY_VERSION` | `metis_personality.v1.0` | `metis_head.personality` | Structured Metis personality constitution version. |
| `VOICE_SCHEMA_VERSION` | `metis_voice.v0.1` | `metis_head.voice` | Governed voice output provider/result schema version. |
| `VOICE_OPTIONS_VERSION` | `metis_voice_options.v0.1` | `metis_head.voice` | Reviewable voice option catalog version. |
| `AUDIO_INPUT_SCHEMA_VERSION` | `audio_input_adapter.v0.1` | `metis_head.audio_input` | Capture provider and result schema version. Added 0BA. |
| `STT_SCHEMA_VERSION` | `stt_engine.v0.1` | `metis_head.stt` | STT provider and result schema version. Added 0BA. |
| `AUDIO_SPECTRUM_ROWS` | `32` | `metis_head.voice` | Fixed vertical frequency-row contract for the virtual and future physical mirrored LED analyzer. |
| `AUDIO_SPECTRUM_SEGMENTS_PER_SIDE` | `8` | `metis_head.voice` | Fixed amplitude-segment count on each side of the analyzer center spine. |
| `SIM_TEST_MANIFEST_VERSION` | `metis_sim_tests.v0.1` | `metis_head.sim_manifest` | Portable simulation scenario/acceptance/parity manifest version. |
| `ARTIFACT_SCHEMA_VERSION` | `metis_artifact.v0.1` | `metis_head.artifacts` | Portable saved artifact envelope version. |
| `metis_export.v0.1` | `metis_export.v0.1` | `metis_head.brain` | Dashboard/API export envelope version. |
| `LLMResult` | dataclass | `metis_head.llm_providers` | Provider-neutral virtual chat result envelope. |
| `POLICY_VERSION` | `metis_governance_policy.v0.1` | `metis_head.governance` | Deterministic action-classification policy version. |
| `PROPOSAL_SCHEMA_VERSION` | `metis_proposal.v0.1` | `metis_head.proposals` | Structured approval/memory proposal record version. |
| `PROPOSAL_REVIEW_SCHEMA_VERSION` | `metis_proposal_review.v0.1` | `metis_head.proposals` | Review receipt version for approve/deny proposal transitions. |
| `PROPOSAL_REVIEW_SCOPE_VERSION` | `metis_proposal_review_scope.v0.1` | `metis_head.proposals` | Single-proposal review scope metadata version. |
| `EXECUTION_RECEIPT_VERSION` | `metis_execution_receipt.v0.1` | `metis_head.execution` | Audit receipt version for execution requests that do not execute real actions. |
| `READ_ONLY_EXECUTION_POLICY_VERSION` | `metis_read_only_execution_policy.v0.1` | `metis_head.execution_policy` | Active contract for scoped approved read-only receipt lanes and arbitrary execution boundaries. |
| `TOOL_REGISTRY_VERSION` | `metis_tool_registry.v0.1` | `metis_head.tool_registry` | Governed tool manifest registry schema. |
| `TOOL_RECEIPT_VERSION` | `metis_tool_receipt.v0.1` | `metis_head.tool_registry` | Dry-run/blocked tool receipt schema. |
| `TOOL_ARGUMENT_VALIDATION_VERSION` | `metis_tool_arguments.v0.1` | `metis_head.tool_registry` | Tool input argument validation metadata schema. |
| `TOOL_CONTRACT_VERSION` | `metis_tool_contract.v0.1` | `metis_head.tool_contract` | Derived governed tool contract manifest schema. |
| `TOOL_POLICY_SNAPSHOT_VERSION` | `metis_tool_policy_snapshot.v0.1` | `metis_head.tool_policy_snapshot` | Composed governed tool policy review packet schema. |
| `TOOL_GATE_EVALUATION_VERSION` | `metis_tool_gate_evaluation.v0.1` | `metis_head.tool_governance` | Advisory governed tool gate decision schema. |
| `TOOL_READINESS_VERSION` | `metis_tool_readiness.v0.1` | `metis_head.tool_readiness` | Computed governed-tool readiness checklist schema. |
| `TOOL_COMPLETION_VERSION` | `metis_tool_completion.v0.1` | `metis_head.tool_completion` | Computed governed-tool track completion report schema. |
| `TOOL_TASK_PLAN_VERSION` | `metis_tool_task_plan.v0.1` | `metis_head.tool_task_planner` | Reviewable governed tool task plan schema. |
| `TOOL_PLAN_REVIEW_VERSION` | `metis_tool_plan_review.v0.1` | `metis_head.tool_task_planner` | Non-standing approve/deny receipt schema for persisted tool plans. |
| `PLAN_ADVANCE_VERSION` | `metis_tool_plan_advance.v0.1` | `metis_head.tool_plan_runner` | Guided next-action calculator schema for plan advancement. |
| `metis_tool_plan_status.v0.1` | `metis_tool_plan_status.v0.1` | `metis_head.brain` | Chat response model label for governed plan status/next-gate reports. |
| `metis_tool_approval_status.v0.1` | `metis_tool_approval_status.v0.1` | `metis_head.brain` | Chat response model label for bounded approval-queue status reports. |
| `metis_tool_receipt_status.v0.1` | `metis_tool_receipt_status.v0.1` | `metis_head.brain` | Chat response model label for bounded execution-receipt status reports. |
| `metis_tool_next_action.v0.1` | `metis_tool_next_action.v0.1` | `metis_head.brain` | Chat response model label for exact next-step governed UI/API instructions. |
| `metis_tool_capability_awareness.v0.1` | `metis_tool_capability_awareness.v0.1` | `metis_head.brain` | Deterministic chat/voice response metadata for registry-derived tool awareness. |
| `metis_voice_confirmation.v0.1` | `metis_voice_confirmation.v0.1` | `metis_head.brain` | Redacted simulated voice-confirmation event metadata for proposal review phrases. |
| `metis_voice_confirmation_readback.v0.1` | `metis_voice_confirmation_readback.v0.1` | `metis_head.brain` | Safe spoken/readable summary for one pending proposal before voice confirmation. |
| `metis_variable_map.v0.2` | `metis_variable_map.v0.2` | `docs/project_variable_map.md` | Documentation map version. Added Notes matrix in v0.2. |

---

## Canonical State Fields

| Field | Type | Phase Added | Default | Notes |
|---|---|---|---|---|
| `schema_version` | string | 0A | `metis_state.v0.3` | Canonical state schema identifier. |
| `timestamp` | string | 0A | boot time | Last state timestamp, UTC ISO string. |
| `session_id` | string | 0A | `local-sim-session` | Local simulation session identifier. |
| `power_state` | enum | 0A | `awake` | `awake`, `standby`; future `off`/`disconnected`. |
| `audio_state` | enum | 0A | `idle` | `idle`, `listening`, `speaking`, `capture_blocked`, `standby_no_listen`; `tts_failure` forces `speaking` back to `idle`. |
| `voice_output_state` | enum | 0V | `idle` | `idle`, `queued`, `synthesizing`, `speaking`, `muted`, `complete`, `cancelled`, `failed`. |
| `cognition_state` | enum | 0A | `idle` | `idle`, `retrieving`, `drafting`, `awaiting_approval`. |
| `authority_state` | enum | 0A | `local_governed` | `local_governed`, `source_grounded`, `awaiting_approval`, `blocked`. |
| `interaction_mode` | enum | 0A | `human` | `human` or `agent`. |
| `initiative_level` | number | 0A | `0.5` | Normalized tuning knob value `0.0`–`1.0`. |
| `initiative_bucket` | enum | 0A | `helpful` | `reactive`, `helpful`, `proactive`. |
| `conversation_depth_level` | number | 0A | `0.5` | Normalized depth knob value `0.0`–`1.0`. |
| `conversation_depth_bucket` | enum | 0A | `rationale` | `direct`, `rationale`, `systems`. |
| `volume_level` | number | 0A | `0.6` | Spoken output volume only. |
| `output_muted` | boolean | 0A | `false` | LOUD/output mute; does not imply privacy. |
| `mic_hardware_enabled` | boolean | 0A | `true` | Hardware mic cutoff state. Capture blocked when false. Highest-precedence gate. |
| `camera_hardware_enabled` | boolean | 0A | `false` | Hardware camera cutoff state. Capture blocked when false. |
| `logging_state` | enum | 0A | `session_logging_active` | Current session logging display state. |
| `vision_state` | enum | 0A | `disabled` | `disabled`, `idle`, `capture_blocked`. |
| `source_grounding_enabled` | boolean | 0A | `false` | AFC/source grounding control state. |
| `source_state` | enum | 0A | `unsourced` | `sourced`, `inferred`, `unsourced`, `stale`, `conflicted`, `blocked`, `degraded`. `degraded` added 0B. |
| `active_failure` | nullable string | 0A | `null` | Current visible failure ID from `FAILURE_TABLE`. |
| `pending_approval_count` | integer | 0A | `0` | Governed action or memory proposals awaiting review. |
| `memory_proposal_count` | integer | 0A | `0` | Memory proposals awaiting review. |
| `tool_queue_count` | integer | 0A | `0` | Tool/action proposals queued, not executed. |
| `approval_queue` | array | 0R | `[]` | Structured pending proposal records; no execution path. |
| `execution_audit_log` | array | 0W | `[]` | Safe execution request receipts; no raw secrets, file contents, command output, or external receipts. |
| `tool_plan_queue` | array | 0AI | `[]` | Persistent reviewable governed tool plans; all transitions are governed and non-autonomous. |
| `module_health` | object | 0A | see keys below | High-level module status map. |
| `input_adapters` | object | 0A | all disabled | Versioned adapter registry. |
| `event_log` | array | 0S | `[]` | In-memory event log for replay/testing. |
| `external_action_executed` | boolean | 0S | `false` | Assertion field proving Agent Mode queues instead of executes. |
| `chat_history` | array | 0R | `[]` | User/assistant virtual chat transcript, stored in canonical state. |
| `last_llm_provider` | nullable string | 0R | `null` | Last successful LLM provider ID. |
| `last_llm_model` | nullable string | 0R | `null` | Last successful LLM model name. |
| `memory_promoted` | boolean | 0S | `false` | Assertion field proving memory promotion requires approval. |
| `blocked_capture_count` | integer | 0S | `0` | Count of capture attempts blocked by hardware cutoff. |
| `capture_count` | integer | 0S | `0` | Count of allowed simulated captures. |
| `tts_output_count` | integer | 0V | `0` | Count of voice speaking events allowed by output controls. |
| `tts_muted_drop_count` | integer | 0V | `0` | Count of voice outputs blocked by output mute/standby. |
| `tts_failure_count` | integer | 0V | `0` | Count of visible TTS provider failures. |
| `last_tts_request_id` | nullable string | 0V | `null` | Last TTS request identifier when available. |
| `last_tts_provider` | nullable string | 0V | `null` | Last voice provider that emitted a TTS event. |
| `last_tts_voice` | nullable string | 0V | `null` | Last voice ID used by the voice harness. |
| `last_tts_error` | nullable string | 0V | `null` | Last TTS provider/blocking error. |
| `last_block_reason` | nullable string | 0S | `null` | Human-readable reason for last block/failure. |
| `audio_input_state` | enum | 0BA | `disabled` | `disabled`, `idle`, `capturing`, `transcribing`. Set by audio_input reducer. |
| `audio_input_enabled` | boolean | 0BA | `false` | Software gate for audio input. Must be true for capture to proceed past governance. |
| `listen_mode` | enum | 0BA | `no_listen` | `no_listen`, `wake_word`, `push_to_talk`. Controls which audio trigger routes are active. |
| `listen_session_active` | boolean | 0BD | `false` | True while a PTT press is outstanding. Cleared by PTT release or governance block. Never true in `wake_word` mode. |
| `wake_phrase` | string | 0BD | `"hey metis"` | Configurable prefix for POST /metis/audio/wake. Case-insensitive match. Configurable via `button_event`. |
| `last_listen_trigger` | nullable enum | 0BD | `null` | Last completed listen cycle trigger: `"ptt"`, `"wake"`, or `null`. Not set by the `/listen` route. |
| `last_audio_capture` | nullable object | 0BA | `null` | Redacted summary of last completed capture+STT: `audio_duration_ms`, `frame_count`, `sample_rate`, `audio_provider_id`, `stt_provider_id`, `text_len`, `text_hash`, `text_redacted=true`, `listen_trigger`. Raw audio, WAV bytes, and recognized text never stored. |
| `spec_traceability` | object | 0S | see schema | Buildspec section anchors for dashboard/API review. |

---

## Event Types

| Event Type | Phase | Key Fields | Notes |
|---|---|---|---|
| `control_change` | 0A/0S | `control`, `value`, `raw`, `timestamp_ms` | Bridge/virtual knob movement. |
| `button_event` | 0A/0S | `button`, `state`, `event`, `timestamp_ms` | PWR, LOUD, AFC, AM/FM, listen_mode, wake_phrase, audio_input events. |
| `hardware_privacy` | 0A/0S | `device`, `enabled` | Mic/camera hardware cutoff state. |
| `heartbeat` | 0S | `bridge_id`, `uptime_ms`, `firmware` | Simulated bridge health. |
| `provider_event` | 0S | `provider`, `status`, `failure_id` | Mock provider success/failure/degradation. |
| `provider_event` (tts) | 0V/AUDIO9 | `status`, `voice_provider`, `voice_id`, `voice_schema`, `text_len`, `text_hash`, `text_redacted`, `normalized_text`, `source_text_len`, `source_text_hash`, `playback_strategy`, `playback_mode`, `audio_visualization_hint_ms`, `audio_levels`, `audio_level_count`, `audio_spectrum_levels`, `audio_spectrum_count`, `audio_spectrum_frames`, `audio_spectrum_frame_count`, `audio_spectrum_rows`, `audio_spectrum_segments_per_side`, optional `audio_duration_ms`, optional `audio_file=local_temp_wav` | Voice output events. Raw spoken text, raw audio, and temp paths are not persisted. `audio_spectrum_frames` drives the mirrored analyzer. |
| `provider_event` (stt — simulated voice command) | 0AV | `status=transcript\|complete\|blocked`, `input_mode=simulated_voice_command`, `text_len`, `text_hash`, `text_redacted=true`, optional `reason` | Simulated voice-command recognition events. Raw audio and raw transcript not stored. |
| `provider_event` (audio_input — capture lifecycle) | 0BA | `provider=audio_input`, `status=capturing\|transcribing\|complete\|blocked`, `input_mode=simulated_audio_input`, `audio_input_schema`, optional `audio_duration_ms`, `frame_count`, `sample_rate`, `captured`, `audio_provider_id`, `stt_provider_id`, `text_len`, `text_hash`, `text_redacted=true`, `block_reason` | Capture, transcription, and completion events. Raw audio, WAV bytes, and recognized text never included. |
| `provider_event` (audio_input — PTT) | 0BD | `provider=audio_input`, `status=ptt_pressed\|ptt_released`, `input_mode=simulated_audio_input` | PTT session state events. `ptt_pressed` → reducer sets `listen_session_active=true`, `audio_input_state=capturing`. `ptt_released` → reducer clears `listen_session_active`, sets `last_listen_trigger=ptt`. |
| `provider_event` (audio_input — wake) | 0BD | `provider=audio_input`, `status=wake_triggered\|wake_not_detected`, `input_mode=simulated_audio_input`, optional `block_reason` | Wake detection events. `wake_triggered` → reducer sets `last_listen_trigger=wake`. `wake_not_detected` → no state change; informational only. |
| `failure_event` | 0A/0S | `failure_id`, `reason` | Explicit visible failure trigger. |
| `user_intent` | 0S | `intent`, `action_class` | Agent Mode governance classification. |
| `user_intent` (tool proposal) | 0T | `intent`, `action_class`, `policy`, `tool_id`, `tool_arguments`, `risk_class`, `side_effect_class`, `dry_run_available` | Governed tool proposal event. Arguments sanitized/redacted before storage. |
| `proposal_review` | 0U | `proposal_id`, `decision`, `reason`, `reviewed_at` | Replayable proposal approve/deny transition. Review does not execute tools or grant execution permission. |
| `execution_request` | 0W | `proposal_id`, `reason`, `requested_at`, optional `dry_run_receipt` | Replayable execution request. Reducer appends a receipt; never performs real execution. |
| `tool_plan` | 0AI | `plan` | Replayable event storing a reviewable tool task plan in `tool_plan_queue`; does not execute tools. |
| `tool_plan_review` | 0AJ | `plan_id`, `decision`, `reason`, `reviewed_at` | Replayable tool-plan approve/deny transition. Does not create step proposals or execute tools. |
| `tool_plan_step_queue` | 0AK | `plan_id`, `queued_steps`, `queued_at` | Replayable bookkeeping event. Does not approve or execute proposals. |
| `tool_plan_execution_request` | 0AL | `plan_id`, `executed_steps`, `requested_at` | Replayable bookkeeping event. Does not bypass proposal review or receipt gates. |
| `tool_plan_result_binding` | 0AM | `plan_id`, `bindings`, `bound_at` | Replayable event binding bounded receipt summaries into pending dependent step proposals. Raw content not included. |
| `memory_event` | 0S | `operation`, `memory_id` | Memory proposal/delete lifecycle simulation. |
| `capture_request` | 0S | `device`, `metadata` | Simulated mic/camera capture attempt. |
| `adapter_health` | 0S | `adapter_id`, `health`, `enabled`, `mode` | Adapter health mutation endpoint input. |
| `adapter_schema_check` | 0S | `adapter_id`, `schema_version` | Adapter schema mismatch testing. |
| `bridge_disconnected` | 0S | optional `reason` | Bridge failure simulation. |

---

## Control and Button Names

| Name | Type | Phase | Maps To | Notes |
|---|---|---|---|---|
| `volume` | control | 0A | `volume_level` | |
| `conversation_depth` | control | 0A | `conversation_depth_level`, `conversation_depth_bucket` | |
| `initiative` | control | 0A | `initiative_level`, `initiative_bucket` | |
| `pwr` | button | 0A | `power_state`, `audio_state` | |
| `loud` | button | 0A | `output_muted` | |
| `afc` | button | 0A | `source_grounding_enabled`, `authority_state` | |
| `am_fm` | button | 0A | `interaction_mode` | |
| `mic` | hardware privacy device | 0A | `mic_hardware_enabled`, `audio_state` | Highest-precedence capture gate. |
| `camera` | hardware privacy device | 0A | `camera_hardware_enabled`, `vision_state` | |
| `audio_input` | button | 0BA | `audio_input_enabled`, `audio_input_state` | `state: "on"` enables; `state: "off"` disables and sets `audio_input_state=disabled`. |
| `listen_mode` | button | 0BA | `listen_mode` | Valid values: `no_listen`, `wake_word`, `push_to_talk`. Invalid values silently ignored by reducer. |
| `wake_phrase` | button | 0BD | `wake_phrase` | `state: "<phrase>"` sets wake phrase (stripped, lowercased). Empty/non-string ignored. |

---

## Audio Input and STT Environment

| Variable | Values | Default | Phase | Notes |
|---|---|---|---|---|
| `METIS_AUDIO_ALLOW_LOCAL_MIC` | bool | `false` | 0BB | Opt-in env gate for real microphone capture. One of three required gates. |
| `METIS_STT_ENGINE` | `simulated`, `faster_whisper`, `none` | `simulated` | 0BC | Selects the active STT provider for `/metis/audio/listen`, `/ptt`, and `/wake`. |
| `METIS_STT_ALLOW_LOCAL` | bool | `false` | 0BC | Opt-in env gate for `LocalFasterWhisperSTT`. Required in addition to `METIS_STT_ENGINE=faster_whisper`. |
| `METIS_STT_MODEL` | model name | `small` | 0BC | faster-whisper model size. |
| `METIS_STT_MODEL_DIR` | filesystem path | none | 0BC | Optional offline model directory for faster-whisper. |

---

## Audio Input Provider Classes

| Class | Phase | Provider ID | Status | Notes |
|---|---|---|---|---|
| `NoneAudioInput` | 0BA | `none` | always disabled | Returns `captured=false`, `block_reason=audio_input_provider_none`. Safe default. |
| `SimulatedAudioInput` | 0BA | `simulated` | enabled | Generates deterministic sine-wave WAV in tempfile, analyses it, deletes it. Sets `result._wav_bytes` (in-memory only, never serialized). |
| `LocalMicAudioInput` | 0BB | `local_mic` | triple-gated | Real `sounddevice` capture; lazy import; all three env+state gates must hold. Sets `result._wav_bytes`. Tempfile deleted after analysis. |
| `LocalWakeWordDetector` | 0BD | `local_wake_word` | scaffold (disabled) | No external imports. `detect()` always returns `not_enabled`. Stub for openWakeWord / Porcupine. |
| `AudioInputProvider` | 0BA | `base` | base class | Interface: `capture(context) -> CaptureResult`, `health() -> dict`. |
| `CaptureContext` | 0BA | — | dataclass | `hint`, `fixture_id`, `sample_rate`, `duration_ms`. |
| `CaptureResult` | 0BA | — | dataclass | `provider_id`, `status`, `captured`, `audio_duration_ms`, `audio_levels`, `audio_spectrum_frames`, `frame_count`, `sample_rate`, `block_reason`. `_wav_bytes` is a private in-memory field excluded from `to_dict()`. |

---

## STT Provider Classes

| Class | Phase | Provider ID | Status | Notes |
|---|---|---|---|---|
| `NoneSTT` | 0BA | `none` | always disabled | Returns empty result, `status=disabled`. |
| `SimulatedSTT` | 0BA | `simulated` | enabled | Deterministic `hint → text` map; no model or network. Used by default in CI. |
| `LocalFasterWhisperSTT` | 0BC | `faster_whisper` | env-gated | Real CTranslate2/faster-whisper; lazy import inside `transcribe()` only. Fail-closed: env opt-in → lazy import → model load. |
| `VoskSTT` | 0BC | `vosk` | scaffold (disabled) | Returns `not_enabled`. No imports. |
| `OpenAIWhisperSTT` | 0BC | `openai_whisper` | scaffold (disabled) | Returns `not_enabled`. No imports. |
| `WhisperCppSTT` | 0BC | `whispercpp` | scaffold (disabled) | Returns `not_enabled`. No imports. |
| `STTProvider` | 0BA | `base` | base class | Interface: `transcribe(capture_result, context) -> STTResult`, `health() -> dict`. |
| `STTResult` | 0BA | — | dataclass | `provider_id`, `status`, `_recognized_text` (private), `text_len`, `text_hash`, `text_redacted=true`, `confidence`. `to_dict()` excludes `_recognized_text`. |

---

## Brain Functions (Audio Input — Phase 0BA–0BD)

| Function | Phase | Notes |
|---|---|---|
| `_audio_capture_governance(require_listen_mode=False)` | 0BB | Returns `(allowed, block_reason)`. Gate order: `mic_hardware_enabled` → `audio_input_enabled` → `[listen_mode != no_listen if require_listen_mode]` → `power_state == awake`. |
| `_audio_input_event(status, *, block_reason, capture, stt_result, trigger)` | 0BA/0BD | Builds a `provider_event` dict for audio_input. `trigger` field added in 0BD; flows to `last_audio_capture.listen_trigger` via reducer. |
| `_run_listen_cycle(payload, trigger)` | 0BD | One bounded capture→STT→voice_command cycle. Governance verified by caller. `trigger` is `"listen"`, `"ptt"`, or `"wake"`. Never starts a background thread. |
| `audio_input_status` | 0BA/0BD | `GET /metis/audio/input`. Reports audio/STT providers, state fields, trigger routes, and wake_word provider scaffold. |
| `audio_capture` | 0BA | `POST /metis/audio/input/capture`. Capture only, no STT. |
| `audio_transcribe` | 0BA | `POST /metis/audio/transcribe`. Transcription only, no capture (requires `_wav_bytes` in payload-injected fixture). |
| `audio_listen` | 0BA/0BD | `POST /metis/audio/listen`. Governance → `_run_listen_cycle(payload, "listen")`. |
| `audio_ptt` | 0BD | `POST /metis/audio/ptt`. Press: sets `listen_session_active`. Release: governance → `_run_listen_cycle` → clears session. Wrong mode or pressless release → safe no-op. |
| `audio_wake` | 0BD | `POST /metis/audio/wake`. Mode check → governance → wake_phrase prefix match → strip phrase → `_run_listen_cycle(payload, "wake")`. No match or wrong mode → `wake_not_detected`. |

---

## Bridge Emulator

| Name | Phase | Notes |
|---|---|---|
| `metis_head.bridge_emulator` | 0S/S4 | Library and CLI for emitting canonical bridge events without hardware. |
| `metis-bridge-emulator` | 0S/S4 | Optional installed console script entry point. |
| `python -m metis_head.bridge_emulator control <control> <value>` | 0S/S4 | Emit `control_change` for `volume`, `conversation_depth`, or `initiative`. |
| `python -m metis_head.bridge_emulator button <button> <state>` | 0S/S4 | Emit `button_event` for `pwr`, `loud`, `afc`, `am_fm`, `audio_input`, `listen_mode`, `wake_phrase`. |
| `python -m metis_head.bridge_emulator privacy <device> <enabled>` | 0S/S4 | Emit `hardware_privacy` for `mic` or `camera`. |
| `python -m metis_head.bridge_emulator heartbeat` | 0S/S4 | Emit a bridge heartbeat event. |
| `python -m metis_head.bridge_emulator replay <path>` | 0S/S4 | Parse JSONL bridge events and replay through the deterministic local reducer. |
| `--post <base_url>` | 0S/S4 | Posts emitted/replayed events to `<base_url>/metis/event` using blocking `urllib`. |

---

## Hardware Parity Manifest

| Name | Phase | Notes |
|---|---|---|
| `HARDWARE_PARITY_MANIFEST` | 0Y | Maps each future hardware behavior to event, state, dashboard surface, failure, and executable scenario. |
| `validate_hardware_parity_manifest(scenario_ids)` | 0Y | Verifies each manifest row is complete and references a real scenario ID. |
| `volume_control_updates_state` | 0Y | Scenario proving volume knob parity. |
| `conversation_depth_control_updates_state` | 0Y | Scenario proving depth knob parity. |
| `bridge_heartbeat_sets_bridge_ok` | 0Y | Scenario proving bridge heartbeat recovery parity. |

Every hardware parity row must reference an executable scenario ID. Generic labels such as `scenario_replay` are not accepted by the parity validator.

---

## Adapter IDs

| Adapter ID | Role | Schema | Default | Future Phase | Notes |
|---|---|---|---|---|---|
| `stt` | speech-to-text provider | `stt_adapter.v0.1` | disabled mock | 0R provider bakeoff | |
| `tts` | text-to-speech provider | `tts_adapter.v0.1` | disabled mock | 0R provider bakeoff | |
| `vision` | vision provider | `vision_adapter.v0.1` | disabled mock | 0R/vision spike | |
| `memory` | generic memory provider | `memory_adapter.v0.1` | disabled mock | 9 memory lifecycle | |
| `tools` | tool provider | `tools_adapter.v0.1` | disabled mock, enabled when proposals queued | governed tool lane | |
| `llm_router` | model router provider | `llm_router_adapter.v0.1` | disabled mock | 0R router review | |
| `project_atlas` | task lifecycle provider | `atlas_adapter.v0.1` | disabled mock | future adapter only | Never imported; pattern donor only. |
| `boh_memory` | memory vault provider | `boh_adapter.v0.1` | disabled mock | future BOH adapter only | Never imported; pattern donor only. |
| `robot_safety` | safety pattern provider | `robot_safety_adapter.v0.1` | disabled mock | future safety doctrine adapter | Never imported; pattern donor only. |
| `audio_input` | audio input provider | `audio_input_adapter.v0.1` | disabled | 0BA+ | Enabled by `audio_input_enabled` state flag. |

---

## Provider Harness

| Operation ID | Phase | Emits Events? | Notes |
|---|---|---|---|
| `stt.noop.transcribe` | 0S/S3 | yes | Empty transcript event. |
| `stt.fake.transcribe` | 0S/S3 | yes | Deterministic transcript event. |
| `stt.failed.transcribe` | 0S/S3 | yes | Visible `stt_failure`. |
| `tts.fake.speak` | 0S/S3 | yes | `speaking` then `complete` events without audio. |
| `tts.failed.speak` | 0S/S3 | yes | Visible `tts_failure`. |
| `vision.noop.capture` | 0S/S3 | yes | Camera capture request. |
| `vision.fake.capture` | 0S/S3 | yes | Synthetic camera capture request. |
| `vision.blocked.capture` | 0S/S3 | yes | Visible `camera_failure`. |
| `boh_memory.fake.retrieve` | 0S/S3 | yes | Synthetic cited BOH retrieval event. |
| `vault.failed.retrieve` | 0S/S3 | yes | Visible `vault_unavailable`. |
| `tools.fake.queue` | 0S/S3 | yes | Governed tool proposal event. |
| `tools.blocked.queue` | 0S/S3 | yes | Visible `tool_blocked`. |
| `project_atlas.fake.propose_task` | 0S/S3 | yes | Governed Atlas task proposal event. |
| `llm_router.fake.route` | 0S/S3 | no | Canned routing result only. |
| `robot_safety.fake.classify` | 0S/S3 | no | Denied actuator-action classification only. |

Provider events pass through the same reducer used by `/metis/event`. Non-event provider results are returned for inspection but do not mutate canonical state.

---

## LLM Provider Environment

| Variable | Values | Default | Notes |
|---|---|---|---|
| `METIS_LLM_PROVIDER` | `mock`, `ollama`, `openai` | `mock` | Selects the Phase 0R virtual chat provider. |
| `METIS_OLLAMA_BASE_URL` | URL | `http://127.0.0.1:11434` | Ollama API base URL. |
| `METIS_OLLAMA_MODEL` | model name | none | Required when `METIS_LLM_PROVIDER=ollama`. |
| `OPENAI_API_KEY` | secret | none | Required when `METIS_LLM_PROVIDER=openai`. |
| `METIS_OPENAI_MODEL` | model name | `gpt-4o-mini` | OpenAI chat model. |

---

## Voice Output Environment

| Variable | Values | Default | Notes |
|---|---|---|---|
| `METIS_VOICE_ENABLED` | bool | `false` | Enables automatic voice output. Direct speak endpoints opt in per request. |
| `METIS_VOICE_PROVIDER` | `mock`, `system`, `piper` | `mock` | Selects the voice provider shape. |
| `METIS_VOICE_ID` | voice id | `metis-counsel-mock` | Voice profile identifier. |
| `METIS_VOICE_RATE` | float `0.5-2.0` | `1.0` | Speech rate metadata. |
| `METIS_VOICE_VOLUME` | float `0.0-1.0` | state `volume_level` or `0.6` | Voice volume metadata. |
| `METIS_VOICE_ALLOW_SYSTEM_TTS` | bool | `false` | Explicit gate for future real OS speech. |
| `METIS_VOICE_ALLOW_PIPER` | bool | `false` | Explicit gate for local Piper CLI speech. |
| `METIS_PIPER_EXE` | filesystem path | none | Local Piper executable path. |
| `METIS_PIPER_MODEL` | filesystem path | none | Local Piper `.onnx` model path. |
| `METIS_PIPER_CONFIG` | filesystem path | none | Optional Piper model config path. |
| `METIS_PIPER_PLAYBACK` | bool | `true` | Plays generated WAV through Windows audio when true. |
| `METIS_PIPER_PLAYBACK_STRATEGY` | `soundplayer`, `winsound` | `soundplayer` | Windows playback strategy for generated Piper WAV files. |
| `METIS_PIPER_PLAYBACK_MODE` | `async`, `sync` | `async` | Background launch by default so chat text and radio pulse can align with speech. |
| `METIS_VOICE_NORMALIZE_TEXT` | bool | `true` | Sends audibility-normalized text to TTS while preserving display Markdown in chat history. |

Default local Piper assets when present:

| Name | Value | Notes |
|---|---|---|
| `DEFAULT_PIPER_VOICE_DIR` | `models/piper/en_US/hfc_female/medium` | Repo-local ignored model folder. |
| `DEFAULT_PIPER_MODEL` | `en_US-hfc_female-medium.onnx` | From `rhasspy/piper-voices/en/en_US/hfc_female/medium`. |
| `DEFAULT_PIPER_CONFIG` | `en_US-hfc_female-medium.onnx.json` | Matching Piper voice config. |
| `DEFAULT_PIPER_EXE` | Python 3.11 `Scripts/piper.exe` when installed | Discovered through PATH or Python scripts directory. |

Boundary: Phase 0V is output-only TTS. It does not imply mic capture, listening, wake-word, or privacy mode. `output_muted=true` blocks speech but does not change mic/camera/logging state.

---

## Tool Registry

| Name | Phase | Notes |
|---|---|---|
| `metis_head.tool_registry` | 0T | Metis-native governed tool registry and dry-run/proposal surface. |
| `metis_head.tool_contract` | 0AA | Derived governed tool contract manifest; visibility only, not enforcement. |
| `metis_head.tool_policy_snapshot` | 0AB | Composes contract, policy, proposals, receipts, and authority flags for operator review. |
| `metis_head.tool_governance` | 0AD | Advisory gate evaluator; does not mutate state. |
| `metis_head.tool_readiness` | 0AF | Computes domain-labeled governed-tool readiness from registry/policy/proposal/receipt checks. |
| `metis_head.tool_completion` | 0AG | Computes completion for current simulation-first governed substrate; lists future live lanes as out of scope. |
| `metis_head.tool_task_planner` | 0AH/0AJ | Deterministically turns broad task requests into reviewable non-executing tool plans. |
| `metis_head.tool_plan_runner` | 0AN | Calculates the next governed plan action; never grants autonomous execution. |
| `ToolManifest` | 0T | Versioned tool manifest with ID, schemas, risk, side-effect class, permission mode, enabled flag, and source reference. |
| `TOOLS` | 0T | Seed tool bank inspired by MCP reference categories; no external runtime dependency. |

Permission modes: `disabled`, `dry_run`, `proposal_only`, `approved_read_only`.
Side-effect classes: `none`, `read_only`, `local_mutation`, `external_mutation`.
Risk classes: `low`, `medium`, `high`, `blocked`.

Boundary: public MCP repositories are pattern donors only. Metis does not vendor, import, spawn, or depend on MCP/Anthropic reference repos.

Active tool lanes: `time.now`, `git.status`, `filesystem.read` (all approved read-only receipt lanes).
Future tool lanes: `fetch.url_proposed`, `boh.retrieve_proposed`, live writes, shell, hardware, external mutation.

---

## BOH Retrieval Bridge Environment

| Variable | Values | Default | Notes |
|---|---|---|---|
| `METIS_BOH_ENABLED` | bool | `false` | Enables the read-only BOH retrieval bridge. |
| `METIS_BOH_BASE_URL` | URL | `http://127.0.0.1:8000` | BOH instance base URL. |
| `METIS_BOH_RETRIEVAL_TOKEN` | secret | none | Sent as `X-BOH-Retrieval-Token`. Read-only retrieval token only; BOH operator token never held. |
| `METIS_BOH_RETRIEVAL_MODE` | `exploration`, `strict_answer`, `canon_review`, `audit_provenance`, `low_b_worker_context` | `exploration` | BOH retrieval mode. |
| `METIS_BOH_LIMIT` | integer | `5` | Max context packs requested per retrieval (clamped 1-50). |
| `METIS_BOH_BACKGROUND_ENABLED` | bool | `false` | Enables the background read-only link poller. |
| `METIS_BOH_POLL_SECONDS` | integer | `15` | Poll interval (clamped 5-3600). |
| `METIS_BOH_PROBE_QUERY` | string | `__metis_connection_probe__` | Query used for the tiny `limit=1` liveness probe. |

BOH link states: `disabled`, `connecting`, `connected`, `degraded`, `disconnected`, `auth_failed`.

---

## LLM Provider Classes

| Class | Phase | Notes |
|---|---|---|
| `BaseLLMProvider` | 0R | Interface: `generate(messages, state, options) -> LLMResult`. |
| `MockLLMProvider` | 0R | Deterministic governed local chat provider for tests and safe boot. |
| `OllamaLLMProvider` | 0R/0AP | Calls local Ollama `/api/chat`; receives truthful governed-tool capability context in messages. |
| `OpenAILLMProvider` | 0R/0AP | Calls OpenAI Chat Completions; receives truthful governed-tool capability context in messages. |
| `LLMProviderError` | 0R | Provider failure exception converted into visible `llm_failure`. |
| `list_ollama_models` | 0R | Lists local Ollama models via `/api/tags` for dashboard selection. |
| `probe_llm_provider` | 0R | Reports provider configuration/reachability without generating chat. |
| `_governed_tool_capability_context(state)` | 0AP | Builds registry-derived system prompt text so LLM providers can describe governed tool lanes truthfully. |

---

## Voice Provider Classes

| Class | Phase | Notes |
|---|---|---|
| `VoiceConfig` | 0V | Environment/request-derived voice config. |
| `VoiceResult` | 0V | Provider-neutral voice result envelope with events and block reason. |
| `BaseVoiceProvider` | 0V | Interface: `speak(text, config) -> events`. |
| `MockVoiceProvider` | 0V | Deterministic no-audio TTS event provider. |
| `SystemVoiceProvider` | 0V | Gated system-TTS shape; real OS speech disabled unless explicitly allowed. |
| `PiperVoiceProvider` | 0V/AUDIO4 | Invokes local Piper CLI, writes temp WAV, optionally plays through Windows audio. |
| `normalize_spoken_text` | 0V/AUDIO3 | Removes/converts Markdown before text is sent to TTS. |
| `_wav_duration_ms` | 0V/AUDIO11 | Extracts exact generated-WAV playback duration for one-pass analyzer timing. |
| `_wav_spectrum_frames` | 0V/AUDIO10 | Extracts duration-scaled, loudness-preserving frequency-band frames for animated analyzer motion. |
| `speak_text` | 0V | Applies output-mute/standby gates and returns redacted TTS events. |
| `voice_command(payload)` | 0AV | Simulated recognized voice-command route; emits redacted STT events, routes through chat, defaults to spoken response. |

---

## Voice Options

| Option ID | Provider | Status | Privacy Class | Notes |
|---|---|---|---|---|
| `metis-counsel-mock` | `mock` | `available` | `local_no_audio` | Current default; emits governed TTS events but no audible speech. |
| `windows-system-tts` | `system` | `gated` | `local_os_audio` | Local OS audio shape; disabled unless explicitly allowed. |
| `piper-local` | `piper` | `candidate` or `available` | `local_model_audio` | Local neural TTS; available when Piper exe/model paths configured. |
| `openai-tts` | `openai` | `candidate` | `cloud_audio_external` | Future cloud TTS candidate; requires explicit cloud/privacy labeling. |

---

## Governance Policy

| Name | Phase | Notes |
|---|---|---|
| `ActionPolicy` | 0R | Action class, approval requirement, default decision, and reasons. |
| `classify_intent` | 0R | Deterministically maps intent text to an action policy. |
| `should_queue_proposal` | 0R | Checks whether Agent Mode should queue a proposal instead of acting. |

---

## Proposal Queue

| Field | Phase | Notes |
|---|---|---|
| `proposal_id` | 0R | Deterministic ID derived from queue index, action class, and intent. |
| `proposal_type` | 0R | `action` or `memory`. |
| `status` / `review_status` | 0R/0U | `pending_review` / `pending`, `approved`, `denied`. |
| `intent` | 0R | Original user intent or memory proposal label. |
| `action_class` | 0R | Governance action class. |
| `requires_approval` | 0R | Whether the policy requires review/approval. |
| `execution_allowed` | 0R | Always `false`. |
| `tool_id` | 0T | Optional tool proposal ID when proposal came from the governed tool registry. |
| `tool_arguments` | 0T | Optional sanitized/redacted tool argument snapshot. |
| `risk_class` | 0T | Optional tool risk label. |
| `side_effect_class` | 0T | Optional tool side-effect label. |
| `dry_run_available` | 0T | Optional boolean showing whether a dry-run receipt exists for the tool. |
| `review_receipt` | 0U | `metis_proposal_review.v0.1` receipt; always has `execution_allowed=false`. |
| `review_scope` | 0AE | `metis_proposal_review_scope.v0.1`; single-proposal, non-transferable, non-standing. |
| `voice_confirmation` | 0AX | `/metis/voice/confirm` response: recognized status, decision, proposal ID, `execution_allowed=false`, `standing_approval=false`. |
| `readback` | 0AX | Safe `metis_voice_confirmation_readback.v0.1` proposal summary; excludes raw output and secrets. |

---

## Execution Audit

| Name | Phase | Notes |
|---|---|---|
| `metis_head.execution` | 0W | Builds deterministic execution receipts for execution requests. |
| `metis_head.read_only_tools` | 0G/0F | Narrow approved read-only local executors: current-repo `git.status` and `filesystem.read` text preview. |
| `METIS_REPO_ROOT` | 0AQ | Env allowlist anchor for `filesystem.read` and `git.status`; set by `scripts/launch_metis.ps1`. |
| `tests/conftest.py` | handoff-QA | Sets `METIS_REPO_ROOT` during tests; initializes `.git` only when a clean export lacks git metadata. |
| `receipt_id` | 0W | Deterministic ID derived from receipt index, proposal ID, status, and requested timestamp. |
| `execution_status` | 0W | `blocked_unreviewed`, `blocked_denied`, `blocked_side_effect`, or `dry_run_only_not_executed`. |
| `execution_allowed` | 0W | Always `false`; Phase 0W records receipts only. |
| `executed_read_only` | 0L/0G/0F | Execution status for approved `time.now`, `git.status`, or `filesystem.read`; no arbitrary shell/network/filesystem/external. |

---

## Read-Only Execution Policy

| Name | Phase | Notes |
|---|---|---|
| `docs/READ_ONLY_EXECUTION_POLICY_v0_1.md` | 0Q/0AQ | Human-readable contract for scoped approved read-only receipt lanes. |
| `metis_head.execution_policy` | 0Q/0AQ | Structured policy export for API/tests. |
| `execution_enabled` | 0Q | Always `false` for arbitrary/autonomous execution. |
| `scoped_read_only_receipts_enabled` | 0AQ | `true`: reviewed `time.now`, `filesystem.read`, `git.status` receipt lanes are active. |
| `active_approved_read_only_lanes` | 0AQ | `time.now`, `filesystem.read`, `git.status`. |
| `scripts/launch_metis.ps1` | 0AQ | Sets `METIS_REPO_ROOT`, changes to repo root, starts Uvicorn. |

---

## Module Health Keys

| Key | Values | Notes |
|---|---|---|
| `metis_head_bridge` | `ok`, `unavailable` | |
| `metis_core` | `ok` | |
| `metis_audio` | `ok`, `disabled`, `stt_failure`, `tts_failure` | |
| `metis_memory` | `disabled`, `unavailable` | |
| `metis_vision` | `disabled`, `unavailable` | |
| `metis_governance` | `ok`, `blocked` | |
| `metis_tools` | `disabled` | |
| `metis_dashboard` | `ok` | |
| `metis_integrations` | `disabled` | |
| `metis_llm` | `disabled`, `ok`, `unavailable` | |

---

## Failure IDs

| Failure ID | Meaning | Notes |
|---|---|---|
| `brain_offline` | Metis Brain unavailable. | |
| `bridge_disconnected` | Host bridge heartbeat missing. | |
| `stt_failure` | Speech-to-text provider failed. | |
| `tts_failure` | Text-to-speech provider failed. | |
| `vault_unavailable` | Memory vault unavailable. | |
| `camera_failure` | Vision provider or camera unavailable. | |
| `tool_blocked` | Tool action blocked by governance. | |
| `governance_block` | Governance blocked requested action. | |
| `adapter_schema_mismatch` | Adapter schema version unsupported. | |
| `llm_failure` | LLM router provider failed. | |

---

## LED Resolver Output

| Output Field | Meaning | Notes |
|---|---|---|
| `activity_led.state` | Collapsed user-visible activity/failure/block state. | |
| `activity_led.color` | Deterministic color label for renderer/provider. | |
| `activity_led.priority` | Numeric precedence for renderer comparison. | |
| `authority_led.state` | Collapsed authority/source/governance state. | |
| `authority_led.color` | Deterministic color label for renderer/provider. | |
| `authority_led.priority` | Numeric precedence for renderer comparison. | |
| `visualizer.mode` | `active` or `muted`; output mute does not hide listening/logging. | |
| `visualizer.privacy` | Mic/camera hardware cutoff values. | |

---

## API Routes

| Method | Route | Phase | Notes |
|---|---|---|---|
| `GET` | `/` | 0S | Static dashboard. |
| `GET` | `/metis/state` | 0S | Canonical state, LEDs, readiness. |
| `POST` | `/metis/event` | 0S | Reduce one event into state. |
| `POST` | `/metis/chat` | 0R/0AW | Governed virtual chat. Phase 0J routes explicit chat tool requests; 0AO routes `plan:` to persisted governed plans; 0AR routes plan status/advance; 0AS routes approval/receipt summaries; 0AT routes next-step instructions; 0AW answers tool/capability questions deterministically before LLM generation. |
| `GET` | `/metis/voice` | 0V | Current voice config/status and output-only boundary. |
| `GET` | `/metis/voice/options` | 0V | Reviewable `metis_voice_options.v0.1` voice option catalog. |
| `POST` | `/metis/voice/speak` | 0V | Speak supplied text through the governed voice harness. |
| `POST` | `/metis/voice/preview` | 0V | Speak a preview phrase. |
| `POST` | `/metis/voice/stop` | 0V | Emit a deterministic voice cancellation event. |
| `POST` | `/metis/voice/command` | 0AV | Simulated voice-command ingress. Accepts recognized text, emits redacted STT events, routes to `/metis/chat`, blocks on mic cutoff. |
| `POST` | `/metis/voice/confirm` | 0AX | Simulated voice confirmation for one pending proposal. Requires explicit approve/deny phrase + proposal ID. Never requests execution. |
| `GET` | `/metis/audio/input` | 0BA/0BD | Audio input + STT provider status, state fields (`listen_session_active`, `wake_phrase`, `last_listen_trigger`), trigger routes, and provider scaffolds. |
| `POST` | `/metis/audio/input/capture` | 0BA | Capture only (no STT). Governed by `_audio_capture_governance`. |
| `POST` | `/metis/audio/transcribe` | 0BA | Transcription only (no capture). Requires `audio_input_enabled`. |
| `POST` | `/metis/audio/listen` | 0BA/0BD | Governance → `_run_listen_cycle(payload, "listen")`. One bounded cycle. |
| `POST` | `/metis/audio/ptt` | 0BD | `action=press`: sets `listen_session_active`; `action=release`: one `_run_listen_cycle` then clears session. Wrong mode or pressless release → safe no-op. |
| `POST` | `/metis/audio/wake` | 0BD | Wake-phrase match → one `_run_listen_cycle`. No match or wrong mode → `wake_not_detected`, no capture. |
| `GET` | `/metis/personality` | 0P | Return active Metis personality constitution profile and trait matrix. |
| `GET` | `/metis/personality/console` | 0P | Serve the supplied personality console HTML. |
| `GET` | `/metis/boh/status` | 0C | Safe BOH background link state. Never exposes any token. |
| `GET` | `/metis/llm/options` | 0R | Provider defaults and available Ollama models. |
| `GET` | `/metis/tools` | 0T | Governed tool registry listing. |
| `GET` | `/metis/tools/contract` | 0AA | Derived governed tool contract manifest; visibility only. |
| `GET` | `/metis/tools/completion` | 0AG | Computed governed-tool completion report. |
| `GET` | `/metis/tools/policy_snapshot` | 0AB | Composed governed tool review packet; visibility only. |
| `GET` | `/metis/tools/readiness` | 0AF | Computed governed-tool readiness checklist and score. |
| `POST` | `/metis/tools/governance/evaluate` | 0AD | Advisory gate evaluation; does not mutate state. |
| `POST` | `/metis/tools/task/plan` | 0AH | Deterministic reviewable tool-task planner; does not queue, approve, or execute. |
| `GET` | `/metis/tools/{tool_id}` | 0T | One governed tool manifest. |
| `GET` | `/metis/tools/plans` | 0AI | List persisted governed tool task plans. |
| `GET` | `/metis/tools/plans/{plan_id}` | 0AI | Return one persisted governed tool task plan. |
| `POST` | `/metis/tools/plans/{plan_id}/approve` | 0AJ | Review-approve a plan; does not execute steps. |
| `POST` | `/metis/tools/plans/{plan_id}/deny` | 0AJ | Review-deny a plan; does not execute steps. |
| `POST` | `/metis/tools/plans/{plan_id}/queue_steps` | 0AK | Queue eligible step proposals; no approval or execution. |
| `POST` | `/metis/tools/plans/{plan_id}/request_execution` | 0AL | Request execution for individually approved step proposals through existing receipt gates. |
| `POST` | `/metis/tools/plans/{plan_id}/bind_results` | 0AM | Bind bounded receipt summaries into pending dependent dry-run steps; no raw output. |
| `POST` | `/metis/tools/plans/{plan_id}/advance` | 0AN | Guided next-action; queues/binds/requests only when gates allow, otherwise returns human review gate. |
| `GET` | `/metis/proposals/{proposal_id}` | 0R | Return one proposal record. |
| `POST` | `/metis/proposals/{proposal_id}/approve` | 0U | Review-approve a proposal; does not execute. |
| `POST` | `/metis/proposals/{proposal_id}/deny` | 0U | Review-deny a proposal; does not execute. |
| `POST` | `/metis/proposals/{proposal_id}/request_execution` | 0W | Records an execution request receipt; blocks unreviewed, denied, side-effectful, and external actions. |
| `GET` | `/metis/execution/receipts` | 0W | Return safe execution audit receipts. |
| `GET` | `/metis/execution/receipts/{receipt_id}` | 0W | Return one execution receipt. |
| `GET` | `/metis/execution/policy` | 0Q | Return `metis_read_only_execution_policy.v0.1`. |
| `POST` | `/metis/tools/propose` | 0T | Queue a governed tool proposal with sanitized arguments. |
| `POST` | `/metis/tools/{tool_id}/dry_run` | 0T | Return a safe dry-run receipt for side-effect-free tools; otherwise queue proposal. |
| `POST` | `/metis/tools/{tool_id}/execute` | 0T | Phase 0T execution boundary; returns dry-run-only receipt or blocked proposal. |
| `POST` | `/metis/llm/health` | 0R | Probe LLM readiness without sending a chat completion. |
| `POST` | `/metis/governance/classify` | 0R | Return deterministic governance policy for an intent. |
| `GET` | `/metis/proposals` | 0R/0I | Return structured approval queue records. Phase 0I adds `status`, `proposal_type`, `tool_id` query filters. |
| `GET` | `/metis/export` | 0S | Export state, LEDs, readiness, and event log. |
| `POST` | `/metis/artifacts/save` | 0X | Persist an `export` or `manifest` JSON artifact locally. |
| `GET` | `/metis/artifacts` | 0X | List saved artifact metadata. |
| `GET` | `/metis/artifacts/{filename}` | 0X | Read one saved artifact envelope by safe filename. |
| `GET` | `/metis/sim/manifest` | 0M | Portable `metis_sim_tests.v0.1` manifest with optional scenario results. |
| `GET` | `/metis/sim/tests` | 0M | Alias for the simulation test manifest endpoint. |
| `POST` | `/metis/replay` | 0S | Replay a JSON event list from baseline or current state. |
| `POST` | `/metis/state/reset` | 0S | Reset mock Brain state and scenario results to baseline. |
| `POST` | `/metis/scenario/run` | 0S | Run one scenario or all scenarios. |
| `GET` | `/metis/scenario/results` | 0S | Return latest scenario results. |
| `GET` | `/metis/health` | 0S | Brain health, failures, readiness, parity manifest. |
| `GET` | `/metis/adapters` | 0S | Current adapter registry. |
| `GET` | `/metis/providers` | 0S | Mock provider harness catalog grouped by provider. |
| `POST` | `/metis/providers/{operation_id}/invoke` | 0S | Invoke a deterministic mock provider operation and reduce any emitted events. |
| `POST` | `/metis/adapters/{adapter_id}/set_health` | 0S | Mutate mock adapter health. |
| `POST` | `/metis/failures/{failure_id}/trigger` | 0S | Trigger visible failure. |
| `POST` | `/metis/failures/clear` | 0S | Clear active failure state. |

---

## CLI Entry Points

| Command | Owner | Notes |
|---|---|---|
| `python -m metis_head.bridge_emulator` | `metis_head.bridge_emulator` | Emit or replay simulator bridge events as JSON, local reducer state, or mock-Brain POSTs. |
| `metis-bridge-emulator` | `pyproject.toml` | Installed console-script alias for the bridge emulator. |

---

## Scenario IDs

| Scenario ID | Requirement Covered | Notes |
|---|---|---|
| `baseline_boot_no_adapters` | Safe boot with all adapters disabled. | |
| `pwr_standby_no_hidden_listening` | Standby does not imply hidden listening. | |
| `output_muted_not_privacy` | Output mute does not imply privacy. | |
| `volume_control_updates_state` | Volume control updates spoken output level. | |
| `conversation_depth_control_updates_state` | Conversation depth control updates depth bucket. | |
| `mic_cutoff_blocks_capture` | Mic cutoff blocks capture. | |
| `camera_cutoff_blocks_capture` | Camera cutoff blocks capture. | |
| `source_grounding_unsourced` | AFC labels unsourced answer when retrieval unavailable. | |
| `source_grounding_sourced` | AFC surfaces provenance when retrieval succeeds. | |
| `agent_mode_requires_approval` | Agent Mode queues action instead of executing. | |
| `governance_block_overrides_leds` | Governance block overrides LEDs. | |
| `stt_failure_visible` | STT failure visible. | |
| `tts_failure_visible` | TTS failure visible; mid-speech failure must not leave `audio_state=speaking`. | |
| `vault_failure_visible` | Vault failure visible. | |
| `adapter_schema_mismatch_disables` | Schema mismatch disables adapter. | |
| `memory_proposal_needs_review` | Memory proposal requires review. | |
| `memory_deletion_logs_without_content` | Deletion audit does not retain sensitive content. | |
| `simulator_replay_deterministic` | Same event replay produces same final state. | |
| `bridge_heartbeat_sets_bridge_ok` | Bridge heartbeat marks bridge module healthy. | |

---

## Readiness Domains

| Domain | Phase | Notes |
|---|---|---|
| `simulation_readiness` | 0A/0S/0Y | Computed from weighted checklist, not static text; all checklist items currently pass. |

---

## Future Build Placeholders

| Future Area | Placeholder Names | Notes |
|---|---|---|
| Hardware bridge | `serial_bridge`, `websocket_bridge`, `bridge_transport` | Must emit same event schema as simulator. |
| LED provider | `led_renderer`, `led_provider`, `led_command` | Provider receives already-resolved Metis LED state. |
| Real wake-word engine | `wake_word_engine`, `local_wake_word_detector` | `LocalWakeWordDetector` scaffold exists; real engine (openWakeWord / Porcupine) is future-phase. No external imports until integrated. |
| Physical radio panel | `panel_display`, `panel_led`, `panel_button_matrix` | `panel.py` and `PHYSICAL_RADIO_PANEL_CONTRACT_v0_1.md` define the contract; hardware wiring is future. |
| Real mic PTT integration | `bridge_ptt_button`, `ptt_bridge_event` | `POST /metis/audio/ptt` accepts press/release; the physical PTT button → bridge → ptt route is future. |
| Real STT integration | `stt_live_engine`, `faster_whisper_live`, `vosk_live` | `LocalFasterWhisperSTT` scaffold exists; scaffolds for Vosk, OpenAI Whisper, WhisperCpp also present. |
| Voice-only approval | `voice_confirm_ptt`, `voice_confirm_wake` | Phase 0BE: wire `_run_listen_cycle` output into `/metis/voice/confirm` so spoken approve/deny can flow from PTT or wake path. |
| Phase 0R provider research | `stt_provider_candidate`, `tts_provider_candidate`, `vision_provider_candidate`, `llm_runtime_candidate` | Record evidence-backed recommendations only after bakeoff. |
| Persistence | `event_log_path`, `state_export`, `scenario_manifest_path` | Start JSONL; add SQLite only if needed. |
| Memory lifecycle | `memory_candidate`, `memory_review`, `memory_promotion`, `memory_deletion_audit` | No silent promotion. |
| Project Atlas adapter | `atlas_task_proposal`, `atlas_task_receipt` | Future adapter only; no internal imports. |
| BOH adapter | `boh_retrieval_candidate`, `boh_citation` | Read-only retrieval bridge implemented in 0B; deeper adapter wiring still future. |
| Robot safety adapter | `actuator_action_classification`, `safety_gate_result` | Pattern donor now; future adapter only. |
| External tool execution | `tool_proposal`, `approval_request`, `execution_receipt` | Approval remains separate from execution; future live integrations require additional scoped execution phases after explicit governance gates. |
