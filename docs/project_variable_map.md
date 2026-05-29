# Metis Head Project Variable Map

Version: `metis_variable_map.v0.1`

Last phase updated: `0A + 0S + 0R virtual chat`

Purpose: keep canonical names, state fields, event fields, API routes, adapter IDs,
scenario IDs, and future build placeholders reviewable before each phase commit.

Current Phase 0S/0R UI estimate: `86%` functional for simulation review. Core state/API/scenario panels work, the virtual radio can emit canonical events, event logs can be exported/replayed, virtual chat can call a governed LLM router, and the dashboard can select locally available Ollama models. The UI testing environment is satisfactory for now; next work shifts toward backend/provider/governance readiness.

Dashboard order: `Virtual Radio` -> `Virtual Chat` -> readiness/LED/adapter/state/scenario panels -> `Export and Replay` -> `Event Log`.

## Phase Commit Checklist

Before committing any phase:

- Update `README.md` with current phase status, run commands, verification, and limitations.
- Update this file with all new or changed variables, routes, events, adapters, readiness domains, and scenarios.
- Keep reference repos as read-only pattern donors. Do not record them as runtime dependencies unless a future adapter contract explicitly allows it.

## Schema Versions

| Name | Current Value | Owner | Notes |
|---|---|---|---|
| `STATE_SCHEMA_VERSION` | `metis_state.v0.3` | `metis_head.schemas` | Canonical state version from v0.5 buildspec state object. |
| `EVENT_SCHEMA_VERSION` | `metis_event.v0.1` | `metis_head.schemas` | Phase 0S mock Brain event envelope version. |
| `READINESS_CHECKLIST_VERSION` | `metis_readiness.v0.1` | `metis_head.schemas` | Computed readiness checklist version. |
| `BRIDGE_SCHEMA_VERSION` | `metis_bridge_event.v0.1` | `metis_head.bridge` | Simulated bridge event protocol version. |
| `metis_export.v0.1` | `metis_export.v0.1` | `metis_head.brain` | Dashboard/API export envelope version. |
| `LLMResult` | dataclass | `metis_head.llm_providers` | Provider-neutral virtual chat result envelope. |
| `POLICY_VERSION` | `metis_governance_policy.v0.1` | `metis_head.governance` | Deterministic action-classification policy version. |
| `PROPOSAL_SCHEMA_VERSION` | `metis_proposal.v0.1` | `metis_head.proposals` | Structured approval/memory proposal record version. |
| `metis_variable_map.v0.1` | `metis_variable_map.v0.1` | `docs/project_variable_map.md` | Documentation map version. |

## Canonical State Fields

| Field | Type | Current Phase | Meaning |
|---|---|---|---|
| `schema_version` | string | 0A | Canonical state schema identifier. |
| `timestamp` | string | 0A | Last state timestamp, UTC-ish ISO string in current mock implementation. |
| `session_id` | string | 0A | Local simulation session identifier. |
| `power_state` | enum | 0A | `awake`, `standby`, future `off`/`disconnected`. |
| `audio_state` | enum | 0A | `idle`, `listening`, `speaking`, `capture_blocked`, `standby_no_listen`; `tts_failure` forces `speaking` back to `idle`. |
| `cognition_state` | enum | 0A | `idle`, `retrieving`, `drafting`, `awaiting_approval`. |
| `authority_state` | enum | 0A | `local_governed`, `source_grounded`, `awaiting_approval`, `blocked`. |
| `interaction_mode` | enum | 0A | `human` or `agent`. |
| `initiative_level` | number | 0A | Normalized tuning knob value `0.0` to `1.0`. |
| `initiative_bucket` | enum | 0A | `reactive`, `helpful`, `proactive`. |
| `conversation_depth_level` | number | 0A | Normalized depth knob value `0.0` to `1.0`. |
| `conversation_depth_bucket` | enum | 0A | `direct`, `rationale`, `systems`. |
| `volume_level` | number | 0A | Spoken output volume only. |
| `output_muted` | boolean | 0A | LOUD/output mute; does not imply privacy. |
| `mic_hardware_enabled` | boolean | 0A | Hardware mic cutoff state. Capture blocked when false. |
| `camera_hardware_enabled` | boolean | 0A | Hardware camera cutoff state. Capture blocked when false. |
| `logging_state` | enum | 0A | Current session logging display state. |
| `vision_state` | enum | 0A | `disabled`, `idle`, `capture_blocked`. |
| `source_grounding_enabled` | boolean | 0A | AFC/source grounding control state. |
| `source_state` | enum | 0A | `sourced`, `inferred`, `unsourced`, `stale`, `conflicted`, `blocked`. |
| `active_failure` | nullable string | 0A | Current visible failure ID. |
| `pending_approval_count` | integer | 0A | Governed action or memory proposals awaiting review. |
| `memory_proposal_count` | integer | 0A | Memory proposals awaiting review. |
| `tool_queue_count` | integer | 0A | Tool/action proposals queued, not executed. |
| `approval_queue` | array | 0R | Structured pending proposal records; no execution path in Phase 0R. |
| `module_health` | object | 0A | High-level module status map. |
| `input_adapters` | object | 0A | Versioned adapter registry. |
| `event_log` | array | 0S | In-memory event log for replay/testing. |
| `external_action_executed` | boolean | 0S | Assertion field proving Agent Mode queues instead of executes. |
| `chat_history` | array | 0R | User/assistant virtual chat transcript, stored in canonical state. |
| `last_llm_provider` | nullable string | 0R | Last successful LLM provider ID. |
| `last_llm_model` | nullable string | 0R | Last successful LLM model name. |
| `memory_promoted` | boolean | 0S | Assertion field proving memory promotion requires approval. |
| `blocked_capture_count` | integer | 0S | Count of capture attempts blocked by hardware cutoff. |
| `capture_count` | integer | 0S | Count of allowed simulated captures. |
| `last_block_reason` | nullable string | 0S | Human-readable reason for last block/failure. |
| `spec_traceability` | object | 0S | Buildspec section anchors for dashboard/API review. |

## Event Types

| Event Type | Current Phase | Key Fields | Purpose |
|---|---|---|---|
| `control_change` | 0A/0S | `control`, `value`, `raw`, `timestamp_ms` | Bridge/virtual knob movement. |
| `button_event` | 0A/0S | `button`, `state`, `event`, `timestamp_ms` | PWR, LOUD, AFC, AM/FM events. |
| `hardware_privacy` | 0A/0S | `device`, `enabled` | Mic/camera hardware cutoff state. |
| `heartbeat` | 0S | `bridge_id`, `uptime_ms`, `firmware` | Simulated bridge health. |
| `provider_event` | 0S | `provider`, `status`, `failure_id` | Mock provider success/failure/degradation. |
| `chat_event` | 0R | `status`, `provider`, `model`, `user_message`, `assistant_message`, `source_state` | Governed virtual chat completion/failure. |
| `failure_event` | 0A/0S | `failure_id`, `reason` | Explicit visible failure trigger. |
| `user_intent` | 0S | `intent`, `action_class` | Agent Mode governance classification. |
| `memory_event` | 0S | `operation`, `memory_id` | Memory proposal/delete lifecycle simulation. |
| `capture_request` | 0S | `device`, `metadata` | Simulated mic/camera capture attempt. |
| `adapter_health` | 0S | `adapter_id`, `health`, `enabled`, `mode` | Adapter health mutation endpoint input. |
| `adapter_schema_check` | 0S | `adapter_id`, `schema_version` | Adapter schema mismatch testing. |
| `bridge_disconnected` | 0S | optional `reason` | Bridge failure simulation. |

## Control and Button Names

| Name | Type | Maps To |
|---|---|---|
| `volume` | control | `volume_level` |
| `conversation_depth` | control | `conversation_depth_level`, `conversation_depth_bucket` |
| `initiative` | control | `initiative_level`, `initiative_bucket` |
| `pwr` | button | `power_state`, `audio_state` |
| `loud` | button | `output_muted` |
| `afc` | button | `source_grounding_enabled`, `authority_state` |
| `am_fm` | button | `interaction_mode` |
| `mic` | hardware privacy device | `mic_hardware_enabled`, `audio_state` |
| `camera` | hardware privacy device | `camera_hardware_enabled`, `vision_state` |

## Adapter IDs

| Adapter ID | Role | Schema | Current Default | Future Phase |
|---|---|---|---|---|
| `stt` | speech-to-text provider | `stt_adapter.v0.1` | disabled mock | 0R provider bakeoff |
| `tts` | text-to-speech provider | `tts_adapter.v0.1` | disabled mock | 0R provider bakeoff |
| `vision` | vision provider | `vision_adapter.v0.1` | disabled mock | 0R/vision spike |
| `memory` | generic memory provider | `memory_adapter.v0.1` | disabled mock | 9 memory lifecycle |
| `tools` | tool provider | `tools_adapter.v0.1` | disabled mock | governed tool lane |
| `llm_router` | model router provider | `llm_router_adapter.v0.1` | disabled mock | 0R router review |
| `project_atlas` | task lifecycle provider | `atlas_adapter.v0.1` | disabled mock | future adapter only |
| `boh_memory` | memory vault provider | `boh_adapter.v0.1` | disabled mock | future BOH adapter only |
| `robot_safety` | safety pattern provider | `robot_safety_adapter.v0.1` | disabled mock | future safety doctrine adapter |

## LLM Provider Environment

| Variable | Values | Default | Purpose |
|---|---|---|---|
| `METIS_LLM_PROVIDER` | `mock`, `ollama`, `openai` | `mock` | Selects the Phase 0R virtual chat provider. |
| `METIS_OLLAMA_BASE_URL` | URL | `http://127.0.0.1:11434` | Ollama API base URL. |
| `METIS_OLLAMA_MODEL` | model name | none | Required when `METIS_LLM_PROVIDER=ollama`. |
| `OPENAI_API_KEY` | secret | none | Required when `METIS_LLM_PROVIDER=openai`. |
| `METIS_OPENAI_MODEL` | model name | `gpt-4o-mini` | OpenAI chat model. |

## LLM Provider Classes

| Class | Current Phase | Purpose |
|---|---|---|
| `BaseLLMProvider` | 0R | Interface with `generate(messages, state, options) -> LLMResult`. |
| `MockLLMProvider` | 0R | Deterministic governed local chat provider for tests and safe boot. |
| `OllamaLLMProvider` | 0R | Calls local Ollama `/api/chat`; no tools or retrieval. |
| `OpenAILLMProvider` | 0R | Calls OpenAI Chat Completions; no tools or retrieval. |
| `LLMProviderError` | 0R | Provider failure exception converted into visible `llm_failure`. |
| `list_ollama_models` | 0R | Lists local Ollama models via `/api/tags` for dashboard selection. |
| `probe_llm_provider` | 0R | Reports provider configuration/reachability without generating chat. |

## Governance Policy

| Name | Current Phase | Purpose |
|---|---|---|
| `ActionPolicy` | 0R | Action class, approval requirement, default decision, and reasons. |
| `classify_intent` | 0R | Deterministically maps intent text to an action policy. |
| `should_queue_proposal` | 0R | Checks whether Agent Mode should queue a proposal instead of acting. |
| `POLICY_VERSION` | 0R | Current governance policy schema/version label. |

## Proposal Queue

| Field | Current Phase | Purpose |
|---|---|---|
| `proposal_id` | 0R | Deterministic ID derived from queue index, action class, and intent. |
| `proposal_type` | 0R | `action` or `memory`. |
| `status` | 0R | `pending_review`; no approval/execution lifecycle yet. |
| `intent` | 0R | Original user intent or memory proposal label. |
| `action_class` | 0R | Governance action class. |
| `requires_approval` | 0R | Whether the policy requires review/approval. |
| `default_decision` | 0R | Policy default decision. |
| `reasons` | 0R | Human-readable policy reasons. |
| `execution_allowed` | 0R | Always `false` in this phase. |

## Module Health Keys

| Key | Current Values |
|---|---|
| `metis_head_bridge` | `ok`, `unavailable` |
| `metis_core` | `ok` |
| `metis_audio` | `ok`, `disabled`, `stt_failure`, `tts_failure` |
| `metis_memory` | `disabled`, `unavailable` |
| `metis_vision` | `disabled`, `unavailable` |
| `metis_governance` | `ok`, `blocked` |
| `metis_tools` | `disabled` |
| `metis_dashboard` | `ok` |
| `metis_integrations` | `disabled` |
| `metis_llm` | `disabled`, `ok`, `unavailable` |

## Failure IDs

| Failure ID | Meaning |
|---|---|
| `brain_offline` | Metis Brain unavailable. |
| `bridge_disconnected` | Host bridge heartbeat missing. |
| `stt_failure` | Speech-to-text provider failed. |
| `tts_failure` | Text-to-speech provider failed. |
| `vault_unavailable` | Memory vault unavailable. |
| `camera_failure` | Vision provider or camera unavailable. |
| `tool_blocked` | Tool action blocked by governance. |
| `governance_block` | Governance blocked requested action. |
| `adapter_schema_mismatch` | Adapter schema version unsupported. |
| `llm_failure` | LLM router provider failed. |

## LED Resolver Output

| Output Field | Meaning |
|---|---|
| `activity_led.state` | Collapsed user-visible activity/failure/block state. |
| `activity_led.color` | Deterministic color label for renderer/provider. |
| `activity_led.priority` | Numeric precedence for renderer comparison. |
| `authority_led.state` | Collapsed authority/source/governance state. |
| `authority_led.color` | Deterministic color label for renderer/provider. |
| `authority_led.priority` | Numeric precedence for renderer comparison. |
| `visualizer.mode` | `active` or `muted`; output mute does not hide listening/logging. |
| `visualizer.privacy` | Mic/camera hardware cutoff values. |

## Dashboard DOM IDs

| ID | Current Phase | Purpose |
|---|---|---|
| `score` | 0S | Readiness score display. |
| `domain` | 0S | Readiness domain display. |
| `readiness` | 0S | Readiness JSON panel. |
| `activityDot` | 0S | Diagnostic activity LED dot. |
| `authorityDot` | 0S | Diagnostic authority LED dot. |
| `state` | 0S | Canonical state JSON panel. |
| `adapters` | 0S | Adapter registry JSON panel. |
| `scenarios` | 0S | Scenario result JSON panel. |
| `eventLog` | 0S | Event log JSON panel. |
| `radioActivityLed` | 0S | Virtual tuning-window activity LED. |
| `radioAuthorityLed` | 0S | Virtual tuning-window authority LED. |
| `radioMeter` | 0S | Virtual visualizer bars. |
| `volumeKnob` | 0S | Virtual top/volume knob. |
| `depthKnob` | 0S | Virtual middle/depth knob. |
| `initiativeKnob` | 0S | Virtual large tuning/initiative knob. |
| `volumeRange` | 0S | Emits `control_change:volume`. |
| `depthRange` | 0S | Emits `control_change:conversation_depth`. |
| `initiativeRange` | 0S | Emits `control_change:initiative`. |
| `radioPower` | 0S | Virtual PWR readout. |
| `radioAudio` | 0S | Virtual audio-state readout. |
| `radioMode` | 0S | Virtual human/agent and initiative readout. |
| `radioAuthority` | 0S | Virtual authority/source readout. |
| `radioMic` | 0S | Virtual mic cutoff readout. |
| `radioCamera` | 0S | Virtual camera cutoff readout. |
| `replayInput` | 0S | JSON/JSONL event-log replay input. |
| `replayStatus` | 0S | Export/replay status line. |
| `chatLog` | 0R | Virtual chat transcript display. |
| `chatInput` | 0R | Governed virtual chat input. |
| `chatStatus` | 0R | Provider/proposal/source/failure status line. |
| `chatProvider` | 0R | UI provider selector: `mock`, `ollama`, or `openai`. |
| `ollamaBaseUrl` | 0R | UI override for local Ollama base URL. |
| `ollamaModel` | 0R | UI model selector populated from Ollama `/api/tags`. |

## Dashboard Functions

| Function | Current Phase | Purpose |
|---|---|---|
| `downloadExport` | 0S | Downloads `/metis/export` response as JSON. |
| `downloadEvents` | 0S | Downloads current `event_log` as JSON. |
| `copyEvents` | 0S | Copies current `event_log` JSON to clipboard. |
| `loadCurrentEvents` | 0S | Loads current `event_log` into replay input. |
| `replayEvents` | 0S | Posts parsed JSON/JSONL events to `/metis/replay`. |
| `resetState` | 0S | Posts to `/metis/state/reset`. |
| `sendChat` | 0R | Posts chat input to `/metis/chat`. |
| `clearChatInput` | 0R | Clears unsent chat input. |
| `refreshLlmOptions` | 0R | Refreshes provider defaults and Ollama model list. |
| `handleProviderChange` | 0R | Enables/disables Ollama controls based on selected provider. |
| `chatOptions` | 0R | Builds provider/model/base URL options for `/metis/chat`. |

## API Routes

| Method | Route | Owner | Purpose |
|---|---|---|---|
| `GET` | `/` | `metis_head.brain` | Static dashboard. |
| `GET` | `/metis/state` | `metis_head.brain` | Canonical state, LEDs, readiness. |
| `POST` | `/metis/event` | `metis_head.brain` | Reduce one event into state. |
| `POST` | `/metis/chat` | `metis_head.brain` | Governed virtual chat through selected LLM provider. |
| `GET` | `/metis/llm/options` | `metis_head.brain` | Provider defaults and available Ollama models. |
| `POST` | `/metis/llm/health` | `metis_head.brain` | Probe Mock/Ollama/OpenAI readiness without sending a chat completion. |
| `POST` | `/metis/governance/classify` | `metis_head.brain` | Return deterministic governance policy for an intent. |
| `GET` | `/metis/proposals` | `metis_head.brain` | Return structured approval queue records. |
| `GET` | `/metis/export` | `metis_head.brain` | Export state, LEDs, readiness, and event log. |
| `POST` | `/metis/replay` | `metis_head.brain` | Replay a JSON event list from baseline or current state. |
| `POST` | `/metis/state/reset` | `metis_head.brain` | Reset mock Brain state and scenario results to baseline. |
| `POST` | `/metis/scenario/run` | `metis_head.brain` | Run one scenario or all scenarios. |
| `GET` | `/metis/scenario/results` | `metis_head.brain` | Return latest scenario results. |
| `GET` | `/metis/health` | `metis_head.brain` | Brain health, failures, readiness, parity manifest. |
| `GET` | `/metis/adapters` | `metis_head.brain` | Current adapter registry. |
| `POST` | `/metis/adapters/{adapter_id}/set_health` | `metis_head.brain` | Mutate mock adapter health. |
| `POST` | `/metis/failures/{failure_id}/trigger` | `metis_head.brain` | Trigger visible failure. |
| `POST` | `/metis/failures/clear` | `metis_head.brain` | Clear active failure state. |

## Scenario IDs

| Scenario ID | Requirement Covered |
|---|---|
| `baseline_boot_no_adapters` | Safe boot with all adapters disabled. |
| `pwr_standby_no_hidden_listening` | Standby does not imply hidden listening. |
| `output_muted_not_privacy` | Output mute does not imply privacy. |
| `mic_cutoff_blocks_capture` | Mic cutoff blocks capture. |
| `camera_cutoff_blocks_capture` | Camera cutoff blocks capture. |
| `source_grounding_unsourced` | AFC labels unsourced answer when retrieval unavailable. |
| `source_grounding_sourced` | AFC surfaces provenance when retrieval succeeds. |
| `agent_mode_requires_approval` | Agent Mode queues action instead of executing. |
| `governance_block_overrides_leds` | Governance block overrides LEDs. |
| `stt_failure_visible` | STT failure visible. |
| `tts_failure_visible` | TTS failure visible; mid-speech failure must not leave `audio_state` as `speaking`. |
| `vault_failure_visible` | Vault failure visible. |
| `adapter_schema_mismatch_disables` | Schema mismatch disables adapter. |
| `memory_proposal_needs_review` | Memory proposal requires review. |
| `memory_deletion_logs_without_content` | Deletion audit does not retain sensitive content. |
| `simulator_replay_deterministic` | Same event replay produces same final state. |

## Readiness Domain

| Domain | Current Phase | Notes |
|---|---|---|
| `simulation_readiness` | 0A/0S | Computed from weighted checklist, not static text. |

## Future Build Placeholders

| Future Area | Placeholder Names | Notes |
|---|---|---|
| Phase 0R provider research | `stt_provider_candidate`, `tts_provider_candidate`, `vision_provider_candidate`, `llm_runtime_candidate` | Record evidence-backed recommendations only after bakeoff. |
| Hardware bridge | `serial_bridge`, `websocket_bridge`, `bridge_transport` | Must emit same event schema as simulator. |
| LED provider | `led_renderer`, `led_provider`, `led_command` | Provider receives already-resolved Metis LED state. |
| Persistence | `event_log_path`, `state_export`, `scenario_manifest_path` | Start JSONL; add SQLite only if needed. |
| Memory lifecycle | `memory_candidate`, `memory_review`, `memory_promotion`, `memory_deletion_audit` | No silent promotion. |
| External tool lane | `tool_proposal`, `approval_request`, `execution_receipt` | No execution without governance approval. |
| Project Atlas adapter | `atlas_task_proposal`, `atlas_task_receipt` | Future adapter only, no internal imports. |
| BOH adapter | `boh_retrieval_candidate`, `boh_citation` | Future adapter only, no internal imports. |
| Robot safety adapter | `actuator_action_classification`, `safety_gate_result` | Pattern donor now; future adapter only. |
