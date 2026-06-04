# Metis Head Project Variable Map

Version: `metis_variable_map.v0.1`

Last phase updated: `0AO` (chat-facing governed task planning; builds on `0A + 0S + 0R virtual chat + 0B retrieval bridge + 0C BOH link + 0S/S4 bridge emulator + 0P personality + 0V voice + 0M manifest + 0X artifacts + 0Y parity + 0V/AUDIO9 animated analyzer + 0T/CHAT governed tools + 0U proposal review + 0W execution audit + 0Q read-only policy + 0L time lane + 0G git status lane + 0F filesystem read lane + 0J active read-only chat routing + 0K fetch/planning seeds + 0N audit replay hardening + 0D lifecycle visibility + 0E BOH proposal lane + 0I proposal filters + 0H permission metadata + 0AA contract manifest + 0AB policy snapshot + 0AC argument validation + 0AD gate evaluation + 0AE review scope + 0AF tool readiness + 0AG completion report + 0AH task planner + 0AI plan queue + 0AJ plan review + 0AK step proposals + 0AL execution requests + 0AM result binding + 0AN guided advance`)

Purpose: keep canonical names, state fields, event fields, API routes, adapter IDs,
scenario IDs, and future build placeholders reviewable before each phase commit.

Current Phase 0S/0R/0T/0U/0W/0Q/0L/0G/0F/0J/0K/0N/0D/0E/0I/0H/0AA/0AB/0AC/0AD/0AE/0AF/0AG/0AH/0AI/0AJ/0AK/0AL/0AM/0AN/0AO UI estimate: `90%` functional for simulation review. Core state/API/scenario panels work, the virtual radio can emit canonical events, event logs can be exported/replayed, virtual chat can call a governed LLM router, route explicit tool requests through `tool_router`, or create persisted governed plans through `tool_planner`, the dashboard can select locally available Ollama models, and the Tools panel can inspect the registry, dry-run safe tools, queue proposals, review proposals, request execution receipts, inspect the audit log, review the read-only execution policy, view the tool contract manifest, view the composed policy snapshot, evaluate tool gates, view governed-tool readiness, view governed-tool completion, plan governed tool tasks, persist/review plan records, queue approved plan step proposals, request execution for individually approved plan step proposals, bind safe receipt summaries into dependent plan steps, advance plans through governed non-review transitions, and exercise approved `time.now`, `git.status`, and `filesystem.read` read-only lanes. As of Phase 0J, chat `git status` and `read/open file` intents queue the active approved read-only proposal lanes, not the legacy placeholder lanes. As of Phase 0K, chat `fetch ...` queues blocked fetch proposals and `plan:` returns visible planning dry-runs. As of Phase 0N, replay and receipt-detail tests cover blocked fetch proposals and dry-run-only planning receipts. As of Phase 0D, tool catalog/detail responses expose lifecycle labels. As of Phase 0E, `search boh`, `retrieve boh`, and `search library` chat intents queue `boh.retrieve_proposed` without live BOH retrieval. As of Phase 0I, proposal listings can be filtered by status, proposal type, and tool ID. As of Phase 0H, tool catalog/detail responses expose `permission_requirements` metadata. As of Phase 0AA, `/metis/tools/contract` exports a governed contract manifest with registry counts, lanes, matrix rows, and boundary text. As of Phase 0AB, `/metis/tools/policy_snapshot` composes the contract, read-only policy, proposals, receipts, and authority flags into one review packet. As of Phase 0AC, tool arguments are validated against manifest input schemas before dry-run, proposal, execute, or chat tool routing proceeds. As of Phase 0AD, `/metis/tools/governance/evaluate` provides advisory gate decisions without mutating state. As of Phase 0AE, proposal review receipts and reviewed proposal records include single-proposal, non-standing review scope. As of Phase 0AF, `/metis/tools/readiness` computes a domain-labeled governed-tool readiness score. As of Phase 0AG, `/metis/tools/completion` computes `100%` completion for the current simulation-first governed tool substrate while listing future live lanes as out of scope. As of Phase 0AH, `/metis/tools/task/plan` turns broad task requests into deterministic reviewable tool plans. As of Phase 0AI, plans persist in canonical `tool_plan_queue` and can be listed/detail-read. As of Phase 0AJ, persisted plans can be approved or denied with non-standing review receipts, still without step execution. As of Phase 0AK, approved plans can queue eligible step proposals through the existing proposal queue without executing them. As of Phase 0AL, approved plan step proposals can have execution requested through existing receipt gates. As of Phase 0AM, bounded receipt summaries can be bound into later pending dry-run steps without raw-content leakage. As of Phase 0AN, `/advance` computes the next governed action and stops at human review gates. As of Phase 0AO, explicit chat planning prefixes queue persisted governed plans and return the first `next_action` without approval, proposal materialization, result binding, or execution. Governed tools substrate: `100%` complete for the current simulation-first scope. Practical tool-using task requests: about `88%` complete; general live data-dependent plan execution, live fetch, BOH-as-tool, Atlas/tool adapters, writes, shell, hardware actions, external mutation, and autonomy remain future-phase work.

Dashboard order: `Virtual Radio` -> `Virtual Chat` -> `Tools` -> `Radio Status` -> `BOH Library Link` -> readiness/LED/adapter/state/scenario panels -> `Export and Replay` -> `Event Log`.

Virtual Radio is a 3-zone instrument (`grid-template-columns: 58% 19% 23%`): an inert `radio-speaker` grille (visual only), a tuning-window `radio-strip` carrying the activity LED, authority LED, and full-panel vertical mirrored `radio-meter` spectrum analyzer, and a right `radio-controls` stack (Volume + Depth knobs, PWR/LOUD/AFC/AM-FM `radio-switches`, and the large Tuning/Initiative knob). The analyzer is a simulator rendering of the buildspec tuning-window LED/status visualizer, not a selected LCD panel or final LED firmware. Power/audio/mode/authority readouts and the mic/camera cutoff buttons were moved out of the radio face into the `Radio Status` panel. Virtual Chat's Send button is attached to the composer textarea (Enter sends, Shift+Enter inserts a newline, Send disables while generating); Clear Input is a secondary action. Control meanings are unchanged.

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
| `BRIDGE_EMULATOR_VERSION` | `metis_bridge_emulator.v0.1` | `metis_head.bridge_emulator` | CLI/library wrapper for simulator bridge event emission and replay. |
| `PROVIDER_HARNESS_VERSION` | `metis_provider_harness.v0.1` | `metis_head.provider_harness` | Mock provider catalog/invocation harness version. |
| `PERSONALITY_VERSION` | `metis_personality.v1.0` | `metis_head.personality` | Structured Metis personality constitution version. |
| `VOICE_SCHEMA_VERSION` | `metis_voice.v0.1` | `metis_head.voice` | Governed voice output provider/result schema version. |
| `VOICE_OPTIONS_VERSION` | `metis_voice_options.v0.1` | `metis_head.voice` | Reviewable voice option catalog version. |
| `SIM_TEST_MANIFEST_VERSION` | `metis_sim_tests.v0.1` | `metis_head.sim_manifest` | Portable simulation scenario/acceptance/parity manifest version. |
| `ARTIFACT_SCHEMA_VERSION` | `metis_artifact.v0.1` | `metis_head.artifacts` | Portable saved artifact envelope version. |
| `metis_export.v0.1` | `metis_export.v0.1` | `metis_head.brain` | Dashboard/API export envelope version. |
| `LLMResult` | dataclass | `metis_head.llm_providers` | Provider-neutral virtual chat result envelope. |
| `POLICY_VERSION` | `metis_governance_policy.v0.1` | `metis_head.governance` | Deterministic action-classification policy version. |
| `PROPOSAL_SCHEMA_VERSION` | `metis_proposal.v0.1` | `metis_head.proposals` | Structured approval/memory proposal record version. |
| `PROPOSAL_REVIEW_SCHEMA_VERSION` | `metis_proposal_review.v0.1` | `metis_head.proposals` | Review receipt version for approve/deny proposal transitions. |
| `PROPOSAL_REVIEW_SCOPE_VERSION` | `metis_proposal_review_scope.v0.1` | `metis_head.proposals` | Single-proposal review scope metadata version. |
| `EXECUTION_RECEIPT_VERSION` | `metis_execution_receipt.v0.1` | `metis_head.execution` | Audit receipt version for execution requests that do not execute real actions. |
| `READ_ONLY_EXECUTION_POLICY_VERSION` | `metis_read_only_execution_policy.v0.1` | `metis_head.execution_policy` | Draft contract for future approved read-only execution lanes. |
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
| `metis_variable_map.v0.1` | `metis_variable_map.v0.1` | `docs/project_variable_map.md` | Documentation map version. |

## Canonical State Fields

| Field | Type | Current Phase | Meaning |
|---|---|---|---|
| `schema_version` | string | 0A | Canonical state schema identifier. |
| `timestamp` | string | 0A | Last state timestamp, UTC-ish ISO string in current mock implementation. |
| `session_id` | string | 0A | Local simulation session identifier. |
| `power_state` | enum | 0A | `awake`, `standby`, future `off`/`disconnected`. |
| `audio_state` | enum | 0A | `idle`, `listening`, `speaking`, `capture_blocked`, `standby_no_listen`; `tts_failure` forces `speaking` back to `idle`. |
| `voice_output_state` | enum | 0V | `idle`, `queued`, `synthesizing`, `speaking`, `muted`, `complete`, `cancelled`, `failed`. |
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
| `source_state` | enum | 0A (`degraded` added 0B) | `sourced`, `inferred`, `unsourced`, `stale`, `conflicted`, `blocked`, `degraded`. `degraded` = source grounding requested but BOH unreachable. |
| `active_failure` | nullable string | 0A | Current visible failure ID. |
| `pending_approval_count` | integer | 0A | Governed action or memory proposals awaiting review. |
| `memory_proposal_count` | integer | 0A | Memory proposals awaiting review. |
| `tool_queue_count` | integer | 0A | Tool/action proposals queued, not executed. |
| `approval_queue` | array | 0R | Structured pending proposal records; no execution path in Phase 0R. |
| `execution_audit_log` | array | 0W | Safe execution request receipts; no raw secrets, file contents, command output, or external receipts. |
| `tool_plan_queue` | array | 0AI/0AJ/0AK/0AL/0AM | Persistent reviewable governed tool plans; planning, review, step-proposal queueing, execution requests, and result bindings remain governed and non-autonomous. |
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
| `tts_output_count` | integer | 0V | Count of voice speaking events allowed by output controls. |
| `tts_muted_drop_count` | integer | 0V | Count of voice outputs blocked by output mute/standby. |
| `tts_failure_count` | integer | 0V | Count of visible TTS provider failures. |
| `last_tts_request_id` | nullable string | 0V | Last TTS request identifier when available. |
| `last_tts_provider` | nullable string | 0V | Last voice provider that emitted a TTS event. |
| `last_tts_voice` | nullable string | 0V | Last voice ID used by the voice harness. |
| `last_tts_error` | nullable string | 0V | Last TTS provider/blocking error. |
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
| `provider_event` (`tts`) | 0V/AUDIO9 | `status`, `voice_provider`, `voice_id`, `voice_schema`, `text_len`, `text_hash`, `text_redacted`, `normalized_text`, `source_text_len`, `source_text_hash`, `playback_strategy`, `playback_mode`, `audio_visualization_hint_ms`, `audio_levels`, `audio_level_count`, `audio_spectrum_levels`, `audio_spectrum_count`, `audio_spectrum_frames`, `audio_spectrum_frame_count`, optional `audio_file=local_temp_wav` | Voice output events; raw spoken text, raw audio, and concrete temp paths are not persisted. `audio_spectrum_frames` and `audio_spectrum_levels` are derived from the actual Piper WAV and drive the mirrored analyzer. |
| `failure_event` | 0A/0S | `failure_id`, `reason` | Explicit visible failure trigger. |
| `user_intent` | 0S | `intent`, `action_class` | Agent Mode governance classification. |
| `user_intent` (`tool proposal`) | 0T | `intent`, `action_class`, `policy`, `tool_id`, `tool_arguments`, `risk_class`, `side_effect_class`, `dry_run_available` | Governed tool proposal event. Arguments are sanitized/redacted before proposal storage. |
| `proposal_review` | 0U | `proposal_id`, `decision`, `reason`, `reviewed_at` | Replayable proposal approve/deny transition. Review does not execute tools or grant execution permission. |
| `execution_request` | 0W | `proposal_id`, `reason`, `requested_at`, optional `dry_run_receipt` | Replayable execution request. Reducer appends a `metis_execution_receipt.v0.1` receipt and never performs real execution. |
| `tool_plan` | 0AI | `plan` | Replayable event storing a reviewable tool task plan in `tool_plan_queue`; does not execute tools. |
| `tool_plan_review` | 0AJ | `plan_id`, `decision`, `reason`, `reviewed_at` | Replayable tool-plan approve/deny transition. Review does not create step proposals or execute tools. |
| `tool_plan_step_queue` | 0AK | `plan_id`, `queued_steps`, `queued_at` | Replayable bookkeeping event linking approved plan steps to proposal IDs. It does not approve or execute proposals. |
| `tool_plan_execution_request` | 0AL | `plan_id`, `executed_steps`, `requested_at` | Replayable bookkeeping event linking approved plan step proposals to execution receipts. It does not bypass proposal review or receipt gates. |
| `tool_plan_result_binding` | 0AM | `plan_id`, `bindings`, `bound_at` | Replayable event binding bounded receipt summaries into pending dependent step proposals. Raw content is not included. |
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

## Bridge Emulator

| Name | Current Phase | Purpose |
|---|---|---|
| `metis_head.bridge_emulator` | 0S/S4 | Library and CLI for emitting canonical bridge events without hardware. |
| `metis-bridge-emulator` | 0S/S4 | Optional installed console script entry point. |
| `python -m metis_head.bridge_emulator control <control> <value>` | 0S/S4 | Emit a `control_change` event for `volume`, `conversation_depth`, or `initiative`. |
| `python -m metis_head.bridge_emulator button <button> <state>` | 0S/S4 | Emit a `button_event` for `pwr`, `loud`, `afc`, or `am_fm`. |
| `python -m metis_head.bridge_emulator privacy <device> <enabled>` | 0S/S4 | Emit a `hardware_privacy` event for `mic` or `camera`. |
| `python -m metis_head.bridge_emulator heartbeat` | 0S/S4 | Emit a bridge heartbeat event. |
| `python -m metis_head.bridge_emulator replay <path>` | 0S/S4 | Parse JSONL bridge events and replay them through the deterministic local reducer. |
| `--post <base_url>` | 0S/S4 | Posts emitted/replayed events to `<base_url>/metis/event` using blocking `urllib`. |

Bridge emulator JSONL lines must be one event object per line. The parser reports line numbers for
invalid JSON or unsupported event types. All emitted events include `bridge_schema` and
`emulator_version`, then pass through the same event validator used by the mock Brain.

## Hardware Parity Manifest

| Name | Current Phase | Purpose |
|---|---|---|
| `HARDWARE_PARITY_MANIFEST` | 0Y | Maps each future hardware behavior to event, state, dashboard surface, failure, and executable scenario. |
| `validate_hardware_parity_manifest(scenario_ids)` | 0Y | Verifies each manifest row is complete and references a real scenario ID. |
| `volume_control_updates_state` | 0Y | Scenario proving volume knob parity. |
| `conversation_depth_control_updates_state` | 0Y | Scenario proving depth knob parity. |
| `bridge_heartbeat_sets_bridge_ok` | 0Y | Scenario proving bridge heartbeat recovery parity. |

Every hardware parity row must reference an executable scenario ID. Decorative or generic labels
such as `scenario_replay` are no longer accepted by the parity validator.

## Adapter IDs

| Adapter ID | Role | Schema | Current Default | Future Phase |
|---|---|---|---|---|
| `stt` | speech-to-text provider | `stt_adapter.v0.1` | disabled mock | 0R provider bakeoff |
| `tts` | text-to-speech provider | `tts_adapter.v0.1` | disabled mock | 0R provider bakeoff |
| `vision` | vision provider | `vision_adapter.v0.1` | disabled mock | 0R/vision spike |
| `memory` | generic memory provider | `memory_adapter.v0.1` | disabled mock | 9 memory lifecycle |
| `tools` | tool provider | `tools_adapter.v0.1` | disabled mock, enabled when proposals are queued | governed tool lane |
| `llm_router` | model router provider | `llm_router_adapter.v0.1` | disabled mock | 0R router review |
| `project_atlas` | task lifecycle provider | `atlas_adapter.v0.1` | disabled mock | future adapter only |
| `boh_memory` | memory vault provider | `boh_adapter.v0.1` | disabled mock | future BOH adapter only |
| `robot_safety` | safety pattern provider | `robot_safety_adapter.v0.1` | disabled mock | future safety doctrine adapter |

## Provider Harness

| Operation ID | Current Phase | Emits Events? | Purpose |
|---|---|---:|---|
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

Provider events are applied through the same reducer used by `/metis/event`. Non-event provider
results are returned for inspection but do not mutate canonical state.

## LLM Provider Environment

| Variable | Values | Default | Purpose |
|---|---|---|---|
| `METIS_LLM_PROVIDER` | `mock`, `ollama`, `openai` | `mock` | Selects the Phase 0R virtual chat provider. |
| `METIS_OLLAMA_BASE_URL` | URL | `http://127.0.0.1:11434` | Ollama API base URL. |
| `METIS_OLLAMA_MODEL` | model name | none | Required when `METIS_LLM_PROVIDER=ollama`. |
| `OPENAI_API_KEY` | secret | none | Required when `METIS_LLM_PROVIDER=openai`. |
| `METIS_OPENAI_MODEL` | model name | `gpt-4o-mini` | OpenAI chat model. |

## Voice Output Environment (Phase 0V)

| Variable | Values | Default | Purpose |
|---|---|---|---|
| `METIS_VOICE_ENABLED` | bool | `false` | Enables automatic voice output when used by config/env. Direct speak endpoints opt in per request. |
| `METIS_VOICE_PROVIDER` | `mock`, `system`, `piper` | `mock` | Selects the voice provider shape. |
| `METIS_VOICE_ID` | voice id | `metis-counsel-mock` | Voice profile identifier. |
| `METIS_VOICE_RATE` | float `0.5-2.0` | `1.0` | Speech rate metadata. |
| `METIS_VOICE_VOLUME` | float `0.0-1.0` | state `volume_level` or `0.6` | Voice volume metadata. |
| `METIS_VOICE_ALLOW_SYSTEM_TTS` | bool | `false` | Explicit gate for future real OS speech. |
| `METIS_VOICE_ALLOW_PIPER` | bool | `false` | Explicit environment gate for local Piper CLI speech; dashboard Piper selection also opts in per request. |
| `METIS_PIPER_EXE` | filesystem path | none | Local Piper executable path. |
| `METIS_PIPER_MODEL` | filesystem path | none | Local Piper `.onnx` model path. |
| `METIS_PIPER_CONFIG` | filesystem path | none | Optional Piper model config path. |
| `METIS_PIPER_PLAYBACK` | bool | `true` | Plays the generated temporary WAV through Windows audio when true. |
| `METIS_PIPER_PLAYBACK_STRATEGY` | `soundplayer`, `winsound` | `soundplayer` | Windows playback strategy for generated Piper WAV files. |
| `METIS_PIPER_PLAYBACK_MODE` | `async`, `sync` | `async` | Launches playback in the background by default so chat text and radio pulse can align with speech. |
| `METIS_VOICE_NORMALIZE_TEXT` | bool | `true` | Sends audibility-normalized text to TTS while preserving display Markdown in chat history. |

Default local Piper assets when present:

| Name | Current Value | Notes |
|---|---|---|
| `DEFAULT_PIPER_VOICE_DIR` | `models/piper/en_US/hfc_female/medium` | Repo-local ignored model folder. |
| `DEFAULT_PIPER_MODEL` | `en_US-hfc_female-medium.onnx` | Downloaded from `rhasspy/piper-voices/en/en_US/hfc_female/medium`. |
| `DEFAULT_PIPER_CONFIG` | `en_US-hfc_female-medium.onnx.json` | Matching Piper voice config. |
| `DEFAULT_PIPER_EXE` | Python 3.11 `Scripts/piper.exe` when installed | Discovered through PATH or Python scripts directory. |

Boundary: Phase 0V is output-only TTS. It does not imply microphone capture, camera capture,
listening, wake-word detection, or privacy mode. `output_muted=true` blocks speech but does not
change mic/camera/logging state. Spoken text is represented in TTS events as `text_len`,
`text_hash`, and `text_redacted=true`; raw spoken content is not stored in the event log.

## Tool Registry (Phase 0T)

| Name | Current Phase | Purpose |
|---|---|---|
| `metis_head.tool_registry` | 0T | Metis-native governed tool registry and dry-run/proposal surface. |
| `metis_head.tool_contract` | 0AA | Derived governed tool contract manifest builder; visibility only, not enforcement. |
| `metis_head.tool_policy_snapshot` | 0AB | Composes contract, read-only policy, proposal queue, execution audit, and authority flags for operator review. |
| `metis_head.tool_governance` | 0AD | Advisory gate evaluator for dry-run/propose/execute/chat-route requests; does not mutate state. |
| `metis_head.tool_readiness` | 0AF | Computes domain-labeled governed-tool readiness from registry, policy, proposal, receipt, and boundary checks. |
| `metis_head.tool_completion` | 0AG | Computes completion for the current simulation-first governed tool substrate and lists future live lanes as out of scope. |
| `metis_head.tool_task_planner` | 0AH/0AJ | Deterministically turns broad task requests into reviewable non-executing tool plans and builds non-standing plan review receipts. |
| `metis_head.tool_plan_runner` | 0AN | Calculates the next governed plan action and never grants autonomous execution. |
| `_route_chat_plan_request(message)` | 0AO | Detects explicit chat planning prefixes and extracts the task text without invoking an LLM. |
| `_queue_chat_tool_plan(task)` | 0AO | Queues or reuses a persisted governed tool plan from chat and returns the next governed action. |
| `ToolManifest` | 0T | Versioned tool manifest with ID, schemas, risk, side-effect class, permission mode, enabled flag, and source reference. |
| `TOOLS` | 0T | Seed tool bank inspired by MCP reference categories; no external runtime dependency. |
| `build_tool_contract_manifest()` | 0AA | Builds `metis_tool_contract.v0.1` with registry counts, lanes, governance matrix rows, and boundary statements. |
| `build_tool_policy_snapshot(state)` | 0AB | Builds `metis_tool_policy_snapshot.v0.1`; inspection-only and does not mutate state or authorize execution. |
| `governance_matrix` | 0AA | Per-tool contract rows summarizing permission mode, risk, side-effect class, lifecycle label, execution result, gates, and blocked capabilities. |
| `lanes.active_read_only` / `lanes.dry_run_only` / `lanes.proposal_only` / `lanes.future_only` | 0AA | Derived tool lane lists for operator inspection; not permission grants. |
| `validate_tool_arguments(tool_id, arguments)` | 0AC | Validates manifest-backed object schemas before dry-run, proposal, execute, or chat tool routing proceeds. |
| `evaluate_tool_request(tool_id, arguments, state, request_type)` | 0AD | Returns advisory gate decision: dry-run allowed, proposal required, Agent Mode gated, or dry-run receipt only. |
| `calculate_tool_readiness(state)` | 0AF | Returns computed `metis_tool_readiness.v0.1` score/checklist; score is derived from checks, not static text. |
| `calculate_tool_completion(state)` | 0AG | Returns computed `metis_tool_completion.v0.1`; reaches 100% only when readiness and boundary criteria pass. |
| `plan_tool_task(task, state)` | 0AH | Builds a deterministic `metis_tool_task_plan.v0.1` with dry-run, proposal-required, future-only, and blocked steps. |
| `argument_validation` | 0AC | Persisted proposal/receipt metadata with schema version, validity, and warning labels; does not store raw rejected values. |
| `tool_lifecycle(tool)` | 0D | Derived operator lifecycle metadata for catalog/detail responses; visibility only, not enforcement. |
| `lifecycle_label` | 0D | Tool catalog label: `disabled`, `dry_run_available`, `approved_read_only`, or `proposal_only`. |
| `lifecycle_tags` | 0D | Tool catalog tags including `proposal_only`, `blocked_after_review`, `future_only`, and `approved_read_only` where applicable. |
| `tool_permission_requirements(tool)` | 0H | Derived operator metadata describing required gates and blocked capabilities; visibility only, not enforcement. |
| `permission_requirements.required_gates` | 0H | Reviewable gate labels such as `proposal_queued`, `human_review_approved`, `lane_scope_match`, and `audit_receipt`. |
| `permission_requirements.blocked_capabilities` | 0H | Reviewable blocked-capability labels such as `shell_execution`, `mutation`, `boh_http_call`, or `arbitrary_git_command`. |
| `route_tool_request(message)` | 0T/CHAT/0J/0K/0E | Deterministically routes clear chat requests to governed tool IDs without LLM inference; `git status` routes to `git.status`, `read/open file` routes to `filesystem.read`, `fetch ...` routes to `fetch.url_proposed`, `plan:` routes to `thinking.plan_outline`, and BOH/library search phrases route to `boh.retrieve_proposed`. |
| `_route_math(text)` | 0T/CHAT | Parses narrow arithmetic requests into `math.calculate` operands; no `eval`. |
| `time.now` | 0T | Side-effect-free dry-run time-shaped result. |
| `text.summarize` | 0T | Deterministic local summary-shaped dry run. |
| `math.calculate` | 0T | Narrow arithmetic dry run from explicit operands; no eval. |
| `thinking.plan_outline` | 0K | Side-effect-free visible planning dry-run; no hidden reasoning and no execution authority. |
| `filesystem.read_proposed` | 0T | Legacy proposal-only file-read shape; direct use remains blocked after approval. |
| `filesystem.read` | 0F | Approved read-only current-repo text preview with path/extension/size gates and redacted/truncated output. |
| `git.status_proposed` | 0T | Legacy proposal-only git-status shape; direct use remains blocked after approval. |
| `git.status` | 0G | Approved read-only current-repo git status using fixed no-shell `git status --short --branch`; no arbitrary git command execution. |
| `fetch.url_proposed` | 0K | Proposal-only future URL fetch shape; Phase 0K does not perform network calls. |
| `boh.retrieve_proposed` | 0E | Proposal-only future BOH retrieval-as-tool shape; Phase 0E does not call BOH through the tool registry. |
| `memory.propose` | 0T | Proposal-only memory review shape; no promotion. |
| `dry_run_tool` | 0T | Returns safe `metis_tool_receipt.v0.1` receipts for side-effect-free dry-run tools. |
| `execute_tool` | 0T | Blocks execution or returns a dry-run receipt; never performs side-effectful execution. |
| `sanitize_arguments` | 0T | Redacts secret-like argument keys and truncates persisted argument values. |

Permission modes: `disabled`, `dry_run`, `proposal_only`, `approved_read_only`.
Side-effect classes: `none`, `read_only`, `local_mutation`, `external_mutation`.
Risk classes: `low`, `medium`, `high`, `blocked`.

Boundary: public MCP repositories are pattern donors only. Metis does not vendor, import, spawn, or
depend on MCP/Anthropic reference repos in Phase 0T.

## BOH Retrieval Bridge Environment (Phase 0B)

| Variable | Values | Default | Purpose |
|---|---|---|---|
| `METIS_BOH_ENABLED` | bool | `false` | Enables the read-only BOH retrieval bridge. |
| `METIS_BOH_BASE_URL` | URL | `http://127.0.0.1:8000` | BOH instance base URL. |
| `METIS_BOH_RETRIEVAL_TOKEN` | secret | none | Sent as `X-BOH-Retrieval-Token`. Read-only retrieval token only; the BOH operator token is never held or sent. |
| `METIS_BOH_RETRIEVAL_MODE` | `exploration`, `strict_answer`, `canon_review`, `audit_provenance`, `low_b_worker_context` | `exploration` | BOH retrieval mode. |
| `METIS_BOH_LIMIT` | integer | `5` | Max context packs requested per retrieval (clamped 1-50). |

Each variable can be overridden per chat request via `options.boh` (`enabled`, `base_url`,
`token`, `mode`, `limit`). Boundary: Metis calls only `POST {base_url}/api/retrieve` (read-only),
never mutates BOH, and never sends BOH's operator token. When source grounding is on and BOH is
unreachable, `source_state` becomes `degraded` and the answer is labeled unsourced rather than
failing silently. BOH `gate_result`, warnings, citations, `do_not_treat_as_canonical` flags, and
source spans are preserved in the chat response under `metadata.boh` / `retrieval`. Owner:
`metis_head.boh_retrieval`.

## BOH Background Link Manager Environment (Phase 0C)

| Variable | Values | Default | Purpose |
|---|---|---|---|
| `METIS_BOH_BACKGROUND_ENABLED` | bool | `false` | Enables the background read-only link poller. When false the link state stays `disabled`. |
| `METIS_BOH_POLL_SECONDS` | integer | `15` | Poll interval (clamped 5-3600). Auth-failed state backs off to at least 60s. |
| `METIS_BOH_PROBE_QUERY` | string | `__metis_connection_probe__` | Query used for the tiny `limit=1` read-only liveness probe. |

The manager also reuses `METIS_BOH_BASE_URL`, `METIS_BOH_RETRIEVAL_TOKEN`, `METIS_BOH_RETRIEVAL_MODE`,
and `METIS_BOH_LIMIT` from the Phase 0B bridge. It polls `GET /api/health`, `GET /api/retrieve/status`,
and a `limit=1` `POST /api/retrieve` probe; it never mutates BOH, never sends the operator token, and
never copies the BOH corpus into Metis (BOH remains the source of truth for library/index/chunks/
citations). Link state enum: `disabled`, `connecting`, `connected`, `degraded`, `disconnected`,
`auth_failed`. Transition rules: health reachable + probe 200 -> `connected`; health, retrieve/status,
or retrieve-probe 401/403 -> `auth_failed`; health connection-refused/timeout -> `disconnected`;
health reachable but 5xx or probe network error -> `degraded`. Transition events are recorded only
on actual change (bounded to ~20). `GET /metis/boh/status` returns the safe serialized state (no token,
no operator token, no Authorization, error strings and surfaced payload values scrubbed of the token).
Chat: when the background link reports `auth_failed`, `/metis/chat`
skips the per-message live retrieval and labels the answer `degraded` instead of repeatedly hammering BOH.
Owner: `metis_head.boh_link`.

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

## Personality Constitution

| Name | Current Phase | Purpose |
|---|---|---|
| `docs/METIS_PERSONALITY_CONSTITUTION_v1_0.md` | 0P | Canonical supplied Metis personality constitution. |
| `metis_head/static/personality_console.html` | 0P | Supplied visual personality console served by FastAPI. |
| `metis_head.personality` | 0P | Structured profile, trait matrix, mode modifiers, invariants, and system prompt. |
| `PERSONALITY_VERSION` | 0P | `metis_personality.v1.0`. |
| `PERSONALITY_ARCHETYPE` | 0P | `Wise counsel with governed agency`. |
| `SHORT_PERSONALITY_PROMPT` | 0P | Short system-prompt form injected into governed chat messages. |
| `NON_NEGOTIABLE_INVARIANTS` | 0P | Human authority, approval boundaries, epistemic honesty, provenance, fail-closed restraint, privacy/logging visibility, operator load awareness, and memory humility. |
| `MODE_MODIFIERS` | 0P | Counsel, builder/explorer, governor, and agent trait modulation rules. |
| `personality_profile(mode)` | 0P | Returns weighted active profile and all 27 traits. |
| `personality_system_prompt(mode)` | 0P | Runtime prompt text used by the LLM router path. |

Personality is now a runtime governance/behavior layer, not a decorative dashboard-only asset.
`governed_messages()` includes `metis_personality.v1.0` for mock, Ollama, and OpenAI providers.

## Voice Provider Classes

| Class | Current Phase | Purpose |
|---|---|---|
| `VoiceConfig` | 0V | Environment/request-derived voice config. |
| `VoiceResult` | 0V | Provider-neutral voice result envelope with events and block reason. |
| `BaseVoiceProvider` | 0V | Interface with `speak(text, config) -> events`. |
| `MockVoiceProvider` | 0V | Deterministic no-audio TTS event provider. |
| `SystemVoiceProvider` | 0V | Gated system-TTS shape; real OS speech remains disabled unless explicitly allowed. |
| `PiperVoiceProvider` | 0V/AUDIO4 | Invokes local Piper CLI, writes a temporary WAV, and optionally plays it through Windows `Media.SoundPlayer` or `winsound` in async or sync mode. |
| `normalize_spoken_text` | 0V/AUDIO3 | Removes or converts Markdown/control punctuation before text is sent to TTS. |
| `_wav_spectrum_envelope` | 0V/AUDIO7 | Extracts compact frequency-band levels from the generated Piper WAV for the vertical mirrored analyzer. |
| `_wav_spectrum_frames` | 0V/AUDIO9 | Extracts time-sliced compact frequency-band frames from the generated Piper WAV for animated analyzer motion. |
| `FailedVoiceProvider` | 0V | Deterministic visible TTS failure provider for tests. |
| `speak_text` | 0V | Applies output-mute/standby gates and returns redacted TTS events. |
| `stop_voice` | 0V | Emits a deterministic cancelled TTS event. |
| `voice_profile` | 0V | Returns current voice config/status boundary. |
| `VOICE_OPTION_CATALOG` | 0V+ | Reviewable current/gated/candidate voice options. |
| `voice_options(state)` | 0V+ | Returns selected voice, current audibility, boundary, and option catalog. |

## Voice Options

| Option ID | Provider | Status | Privacy Class | Notes |
|---|---|---|---|---|
| `metis-counsel-mock` | `mock` | `available` | `local_no_audio` | Current default; emits governed TTS events but no audible speech. |
| `windows-system-tts` | `system` | `gated` | `local_os_audio` | Local OS audio shape; disabled unless explicitly allowed and implemented. |
| `piper-local` | `piper` | `candidate` or `available` | `local_model_audio` | Local neural TTS path; becomes available when Piper executable/model paths are configured. |
| `openai-tts` | `openai` | `candidate` | `cloud_audio_external` | Future cloud TTS candidate; would require explicit cloud/privacy labeling. |

## Simulation Test Manifest

| Name | Current Phase | Purpose |
|---|---|---|
| `metis_head.sim_manifest` | 0M | Builds a portable simulation manifest from scenarios, readiness, acceptance requirements, and hardware parity. |
| `SIM_TEST_MANIFEST_VERSION` | 0M | `metis_sim_tests.v0.1`. |
| `ACCEPTANCE_REQUIREMENTS` | 0M | Required acceptance coverage labels for simulation review. |
| `REQUIREMENT_SCENARIO_MAP` | 0M | Maps acceptance requirements to executable scenario IDs where applicable. |
| `build_sim_test_manifest(include_results=True)` | 0M | Returns schemas, readiness, summary, acceptance coverage, scenario summaries, hardware parity, and boundaries. |

The manifest is intentionally portable JSON. It does not require hardware, BOH, Atlas, Robot Shell,
real microphone/camera capture, or real external tools. `include_results=false` can be used when a
caller wants the inventory without executing scenarios.

## Artifact Persistence

| Name | Current Phase | Purpose |
|---|---|---|
| `metis_head.artifacts` | 0X | Save/list/read portable JSON artifacts under the local `artifacts/` directory. |
| `ARTIFACT_SCHEMA_VERSION` | 0X | `metis_artifact.v0.1`. |
| `ARTIFACT_DIR` | 0X | Repository-local artifact directory; created on demand. |
| `save_artifact(payload, artifact_type, label)` | 0X | Save `export` or `manifest` artifact with safe filename. |
| `list_artifacts()` | 0X | Return metadata records for saved artifacts. |
| `read_artifact(filename)` | 0X | Read one artifact envelope; rejects path traversal. |

Supported artifact types: `export` (`metis_export.v0.1`) and `manifest`
(`metis_sim_tests.v0.1`). This is intentionally JSON-file storage, not SQLite.

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
| `tool_id` | 0T | Optional tool proposal ID when proposal came from the governed tool registry. |
| `tool_arguments` | 0T | Optional sanitized/redacted tool argument snapshot. |
| `risk_class` | 0T | Optional tool risk label. |
| `side_effect_class` | 0T | Optional tool side-effect label. |
| `dry_run_available` | 0T | Optional boolean showing whether a dry-run receipt exists for the tool. |
| `review_status` | 0U | `pending`, `approved`, or `denied`. |
| `reviewed_at` | 0U | Review timestamp supplied by the reducer event/API. |
| `review_decision` | 0U | Mirrors approved/denied decision for audit readability. |
| `review_reason` | 0U | Optional operator review reason. |
| `review_receipt` | 0U | `metis_proposal_review.v0.1` receipt; always has `execution_allowed=false` and `execution_status=not_executed`. |
| `review_scope` | 0AE | `metis_proposal_review_scope.v0.1`; single-proposal, non-transferable, non-standing review scope with `execution_allowed=false`. |
| `proposal filters` | 0I | `/metis/proposals` query filters: `status`, `proposal_type`, and `tool_id`; response includes `total_count`, `filtered_count`, and `filters`. |

## Execution Audit

| Field | Current Phase | Purpose |
|---|---|---|
| `metis_head.execution` | 0W | Builds deterministic execution receipts for execution requests. |
| `metis_head.read_only_tools` | 0G/0F | Narrow approved read-only local executors; currently current-repo `git.status` and current-repo `filesystem.read` text preview. |
| `EXECUTION_RECEIPT_VERSION` | 0W | `metis_execution_receipt.v0.1`. |
| `receipt_id` | 0W | Deterministic ID derived from receipt index, proposal ID, status, and requested timestamp. |
| `proposal_id` | 0W | Proposal that the operator attempted to execute. |
| `tool_id` | 0W | Tool associated with the proposal, when present. |
| `policy_decision` | 0W | `review_required`, `denied`, `blocked_after_review`, or `dry_run_only`. |
| `execution_status` | 0W | `blocked_unreviewed`, `blocked_denied`, `blocked_side_effect`, or `dry_run_only_not_executed`. |
| `execution_allowed` | 0W | Always `false`; Phase 0W records receipts only. |
| `redactions` | 0W | Declares omitted unsafe classes: secrets, raw file contents, command output, external receipts. |
| `dry_run_receipt` | 0W | Optional nested `metis_tool_receipt.v0.1` only for approved side-effect-free dry-run tools. |
| `executed_read_only` | 0L/0G/0F | Execution status for approved `time.now`, current-repo `git.status`, or current-repo `filesystem.read` preview; no arbitrary shell/network/filesystem/external action. |
| `output_summary` | 0L | Bounded key/count/preview summary for approved read-only output. |
| `output_hash` | 0L | Short hash of approved read-only output for audit comparison. |
| `test_phase_0n_tool_audit_hardening.py` | 0N | Regression coverage for deterministic replay and receipt detail around `fetch.url_proposed` and `thinking.plan_outline`. |

## Read-Only Execution Policy

| Name | Current Phase | Purpose |
|---|---|---|
| `docs/READ_ONLY_EXECUTION_POLICY_v0_1.md` | 0Q | Human-readable draft contract for future approved read-only execution. |
| `metis_head.execution_policy` | 0Q | Structured policy export for API/tests. |
| `READ_ONLY_EXECUTION_POLICY_VERSION` | 0Q | `metis_read_only_execution_policy.v0.1`. |
| `read_only_execution_policy()` | 0Q | Returns the policy contract as JSON-safe data. |
| `candidate_lanes` | 0Q/0L/0G/0F/0J/0K/0E | Read-only lane list: `time.now` active in 0L, `git.status` active in 0G, `filesystem.read` active in 0F; Phase 0J routes chat intents into active `git.status`/`filesystem.read` proposals; Phase 0K adds blocked `fetch.url_proposed`; Phase 0E adds blocked `boh.retrieve_proposed`. `fetch.url` execution and deeper `boh.retrieve` execution remain future-only. |
| `required_gates` | 0Q | Future gates: proposal ID, approved review, approved read-only permission, lane policy match, pre-result receipt, redaction. |
| `execution_enabled` | 0Q | Always `false`; Phase 0Q is policy only. |

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
| `radioMeter` | 0V/AUDIO9 | Virtual tuning-window visualizer; renders an idle center spine and a full-height bottom-to-top mirrored analog spectrum analyzer from Piper `audio_spectrum_frames` during speech. Primary analyzer color is `#3AA3A7`. |
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
| `chatStatus` | 0R/0AO | Provider/proposal/source/failure status line; shows `plan_queued` and `tool_planner` for chat-created governed plans. |
| `chatProvider` | 0R | UI provider selector: `mock`, `ollama`, or `openai`. |
| `ollamaBaseUrl` | 0R | UI override for local Ollama base URL. |
| `ollamaModel` | 0R | UI model selector populated from Ollama `/api/tags`. |
| `voiceProvider` | 0V/UI | UI voice provider selector populated from `/metis/voice/options`. |
| `voiceId` | 0V/UI | UI voice ID selector; unsupported candidate options are disabled until implemented. |
| `voiceReplyEnabled` | 0V/UI | Chat voice-reply switch; sends `options.voice.speak_response=true` when checked. |
| `voiceStatus` | 0V/UI | Voice option/status line. |
| `piperControls` | 0V/AUDIO | Shows local Piper path inputs when the Piper voice provider is selected. |
| `piperExe` | 0V/AUDIO | Per-request Piper executable path override. |
| `piperModel` | 0V/AUDIO | Per-request Piper `.onnx` model path override. |
| `piperConfig` | 0V/AUDIO+ | Per-request Piper `.onnx.json` config path override. |
| `toolSelect` | 0T/0D | Tool selector populated from `/metis/tools`; displays `lifecycle.lifecycle_label` when available. |
| `toolArguments` | 0T | JSON input for dry-run/proposal arguments. |
| `toolStatus` | 0T | Tool registry/proposal/dry-run status line. |
| `toolsPanel` | 0T | Tool registry, dry-run receipt, or proposal JSON panel. |
| `proposalSelect` | 0U | Proposal selector populated from `/metis/proposals`. |
| `proposalReason` | 0U | Optional review reason sent to approve/deny endpoints. |
| `proposalStatusFilter` | 0I | Dashboard filter for proposal status/review status. |
| `proposalTypeFilter` | 0I | Dashboard filter for action vs memory proposal type. |
| `proposalToolFilter` | 0I | Dashboard filter for a specific tool ID. |
| `toolPlanSelect` | 0AJ | Tool plan selector populated from `/metis/tools/plans`. |
| `toolPlanReason` | 0AJ | Optional review reason sent to plan approve/deny endpoints. |
| `executionReceipts` | 0W | Dashboard JS cache for `/metis/execution/receipts`. |

## Dashboard Functions

| Function | Current Phase | Purpose |
|---|---|---|
| `downloadExport` | 0S | Downloads `/metis/export` response as JSON. |
| `downloadEvents` | 0S | Downloads current `event_log` as JSON. |
| `copyEvents` | 0S | Copies current `event_log` JSON to clipboard. |
| `loadCurrentEvents` | 0S | Loads current `event_log` into replay input. |
| `replayEvents` | 0S | Posts parsed JSON/JSONL events to `/metis/replay`. |
| `resetState` | 0S | Posts to `/metis/state/reset`. |
| `sendChat` | 0R | Posts chat input to `/metis/chat`; disables the Send button while generating. |
| `handleChatKeydown` | 0C | Enter sends the message; Shift+Enter inserts a newline in the composer. |
| `clearChatInput` | 0R | Clears unsent chat input. |
| `refreshBohStatus` | 0C | Polls `/metis/boh/status` for the BOH Library panel and surfaces link transitions. |
| `refreshLlmOptions` | 0R | Refreshes provider defaults and Ollama model list. |
| `handleProviderChange` | 0R | Enables/disables Ollama controls based on selected provider. |
| `chatOptions` | 0R | Builds provider/model/base URL options for `/metis/chat`. |
| `refreshVoiceOptions` | 0V/UI | Refreshes reviewable voice options and selected voice controls. |
| `handleVoiceProviderChange` | 0V/UI | Updates voice IDs when the provider changes. |
| `voiceChatOptions` | 0V/UI | Builds `options.voice` for `/metis/chat`. |
| `previewVoice` | 0V/UI | Calls `/metis/voice/preview` with the selected voice option. |
| `pulseRadioAudio` | 0V/AUDIO | Pulses the virtual radio meter/strip when TTS output is active or newly completed. |
| `renderRadioWave` | 0V/AUDIO9 | Renders one vertical mirrored spectrum frame, resamples real bands to fill the panel, normalizes per utterance, and falls back to aggregate levels for compatibility. |
| `resampleLevels` | 0V/AUDIO8 | Interpolates compact Piper spectrum metadata into the dashboard's full-height analyzer row count without inventing new source signal. |
| `pulseRadioFromVoice` | 0V/AUDIO9 | Pulses the radio strip from returned voice event metadata, using `audio_spectrum_frames`, `audio_spectrum_levels`, `audio_levels`, and `audio_visualization_hint_ms` when available. |
| `refreshTools` | 0T/0D | Populates the Tools panel from `/metis/tools` and displays operator lifecycle labels in the tool selector. |
| `dryRunTool` | 0T | Calls `/metis/tools/{tool_id}/dry_run`. Agent Mode or proposal-only tools queue proposals instead. |
| `proposeTool` | 0T | Calls `/metis/tools/propose`. |
| `parseToolArguments` | 0T | Parses dashboard tool argument JSON before dry-run/proposal calls. |
| `refreshProposals` | 0U/0I | Populates the proposal selector from `/metis/proposals`, applying status/type/tool filters and showing filtered counts. |
| `reviewProposal` | 0U | Calls approve/deny endpoints and displays review receipts. |
| `approveProposal` | 0U | Approves selected proposal as review state only. |
| `denyProposal` | 0U | Denies selected proposal and recomputes pending counters. |
| `requestExecution` | 0W | Calls `/metis/proposals/{proposal_id}/request_execution` and displays a receipt; no real execution. |
| `refreshExecutionReceipts` | 0W | Calls `/metis/execution/receipts` and displays safe audit receipts. |
| `refreshExecutionPolicy` | 0Q | Calls `/metis/execution/policy` and displays the read-only execution policy contract. |
| `refreshToolContract` | 0AA | Calls `/metis/tools/contract` and displays the governed tool contract manifest. |
| `refreshToolPolicySnapshot` | 0AB | Calls `/metis/tools/policy_snapshot` and displays the composed governed tool review packet. |
| `evaluateToolGate` | 0AD | Calls `/metis/tools/governance/evaluate` for the selected tool and displays advisory gate decisions. |
| `refreshToolReadiness` | 0AF | Calls `/metis/tools/readiness` and displays the computed governed-tool readiness checklist. |
| `refreshToolCompletion` | 0AG | Calls `/metis/tools/completion` and displays the computed governed-tool completion report. |
| `planToolTask` | 0AH | Calls `/metis/tools/task/plan` using the chat composer text and displays the reviewable task plan. |
| `refreshToolPlans` | 0AJ | Calls `/metis/tools/plans` and populates the persisted plan selector. |
| `reviewToolPlan` | 0AJ | Calls plan approve/deny endpoints and displays non-executing plan review receipts. |
| `approveToolPlan` | 0AJ | Approves selected tool plan as review state only. |
| `denyToolPlan` | 0AJ | Denies selected tool plan and recomputes pending counters. |
| `queueToolPlanSteps` | 0AK | Calls `/metis/tools/plans/{plan_id}/queue_steps` to queue eligible plan step proposals without executing them. |
| `requestToolPlanExecution` | 0AL | Calls `/metis/tools/plans/{plan_id}/request_execution` and displays receipts for approved step proposals only. |
| `bindToolPlanResults` | 0AM | Calls `/metis/tools/plans/{plan_id}/bind_results` to bind safe receipt summaries into pending dependent step proposals. |
| `advanceToolPlan` | 0AN | Calls `/metis/tools/plans/{plan_id}/advance`; performs only safe non-review transitions and otherwise reports the required human gate. |

## API Routes

| Method | Route | Owner | Purpose |
|---|---|---|---|
| `GET` | `/` | `metis_head.brain` | Static dashboard. |
| `GET` | `/metis/state` | `metis_head.brain` | Canonical state, LEDs, readiness. |
| `POST` | `/metis/event` | `metis_head.brain` | Reduce one event into state. |
| `POST` | `/metis/chat` | `metis_head.brain` | Governed virtual chat through selected LLM provider, `tool_router` for explicit governed tool requests, or `tool_planner` for explicit governed planning prefixes. When source grounding is on and BOH enabled (0B), retrieves read-only context first; response adds `source_state`, `metadata.boh`, and `retrieval`. Tool routing can be disabled per request with `options.tools.enabled=false`; Phase 0J chat routing queues active `git.status` and `filesystem.read` proposals without direct execution; Phase 0K routes `fetch ...` to blocked proposals and `plan:` to visible dry-runs; Phase 0AO routes `plan task:` and related prefixes to persisted governed plans and returns the first `next_action`. |
| `GET` | `/metis/voice` | `metis_head.brain` | Current voice config/status and output-only boundary. |
| `GET` | `/metis/voice/options` | `metis_head.brain` | Reviewable `metis_voice_options.v0.1` voice option catalog. |
| `POST` | `/metis/voice/speak` | `metis_head.brain` | Speak supplied text through the governed voice harness and reduce emitted TTS events. |
| `POST` | `/metis/voice/preview` | `metis_head.brain` | Speak a preview phrase through the governed voice harness. |
| `POST` | `/metis/voice/stop` | `metis_head.brain` | Emit a deterministic voice cancellation event. |
| `GET` | `/metis/personality` | `metis_head.brain` | Return active Metis personality constitution profile and trait matrix. |
| `GET` | `/metis/personality/console` | `metis_head.brain` | Serve the supplied personality console HTML. |
| `GET` | `/metis/boh/status` | `metis_head.brain` | Safe BOH background link state (0C): state enum, last checked/connected, last error (token-scrubbed), probe count, bounded transition events. Never exposes any token. |
| `GET` | `/metis/llm/options` | `metis_head.brain` | Provider defaults and available Ollama models. |
| `GET` | `/metis/tools` | `metis_head.brain` | Governed tool registry listing. |
| `GET` | `/metis/tools/contract` | `metis_head.brain` | Derived governed tool contract manifest with counts, lanes, matrix rows, and boundaries; visibility only. |
| `GET` | `/metis/tools/completion` | `metis_head.brain` | Computed governed-tool completion report for the simulation-first governed substrate. |
| `GET` | `/metis/tools/policy_snapshot` | `metis_head.brain` | Composed governed tool review packet with contract, read-only policy, proposal queue, execution receipts, and authority flags; visibility only. |
| `GET` | `/metis/tools/readiness` | `metis_head.brain` | Computed governed-tool readiness checklist and score. |
| `POST` | `/metis/tools/governance/evaluate` | `metis_head.brain` | Advisory gate evaluation for selected tool/request type; validates arguments and does not mutate state. |
| `POST` | `/metis/tools/task/plan` | `metis_head.brain` | Deterministic reviewable tool-task planner; does not queue, approve, request, or execute tools. |
| `GET` | `/metis/tools/{tool_id}` | `metis_head.brain` | One governed tool manifest. |
| `GET` | `/metis/tools/plans` | `metis_head.brain` | List persisted governed tool task plans. |
| `GET` | `/metis/tools/plans/{plan_id}` | `metis_head.brain` | Return one persisted governed tool task plan. |
| `POST` | `/metis/tools/plans/{plan_id}/approve` | `metis_head.brain` | Review-approve a persisted tool plan; emits `tool_plan_review`, recomputes pending counters, and does not execute steps. |
| `POST` | `/metis/tools/plans/{plan_id}/deny` | `metis_head.brain` | Review-deny a persisted tool plan; emits `tool_plan_review`, recomputes pending counters, and does not execute steps. |
| `POST` | `/metis/tools/plans/{plan_id}/queue_steps` | `metis_head.brain` | For an approved plan, queue eligible step proposals through the governed proposal lane and record `tool_plan_step_queue`; no proposal is approved or executed. |
| `POST` | `/metis/tools/plans/{plan_id}/request_execution` | `metis_head.brain` | For an approved plan, request execution only for individually approved step proposals through existing receipt gates. |
| `POST` | `/metis/tools/plans/{plan_id}/bind_results` | `metis_head.brain` | Bind bounded receipt summaries into pending dependent dry-run step proposals; does not expose raw outputs or bypass review. |
| `POST` | `/metis/tools/plans/{plan_id}/advance` | `metis_head.brain` | Guided next-action endpoint; queues/binds/requests only when gates allow, otherwise returns the human review gate. |
| `GET` | `/metis/proposals/{proposal_id}` | `metis_head.brain` | Return one proposal record by deterministic proposal ID. |
| `POST` | `/metis/proposals/{proposal_id}/approve` | `metis_head.brain` | Review-approve a proposal; emits `proposal_review`, recomputes pending counters, and does not execute. |
| `POST` | `/metis/proposals/{proposal_id}/deny` | `metis_head.brain` | Review-deny a proposal; emits `proposal_review`, recomputes pending counters, and does not execute. |
| `GET` | `/metis/execution/receipts` | `metis_head.brain` | Return safe execution audit receipts. |
| `GET` | `/metis/execution/receipts/{receipt_id}` | `metis_head.brain` | Return one execution receipt by deterministic receipt ID. |
| `GET` | `/metis/execution/policy` | `metis_head.brain` | Return `metis_read_only_execution_policy.v0.1`; does not enable runtime execution. |
| `POST` | `/metis/proposals/{proposal_id}/request_execution` | `metis_head.brain` | Records an execution request receipt; blocks unreviewed, denied, side-effectful, and external actions. |
| `POST` | `/metis/tools/propose` | `metis_head.brain` | Queue a governed tool proposal with sanitized arguments. |
| `POST` | `/metis/tools/{tool_id}/dry_run` | `metis_head.brain` | Return a safe dry-run receipt for side-effect-free tools in Human Mode; otherwise queue proposal. |
| `POST` | `/metis/tools/{tool_id}/execute` | `metis_head.brain` | Phase 0T execution boundary; returns dry-run-only receipt or blocked proposal. |
| `POST` | `/metis/llm/health` | `metis_head.brain` | Probe Mock/Ollama/OpenAI readiness without sending a chat completion. |
| `POST` | `/metis/governance/classify` | `metis_head.brain` | Return deterministic governance policy for an intent. |
| `GET` | `/metis/proposals` | `metis_head.brain` | Return structured approval queue records; Phase 0I adds optional `status`, `proposal_type`, and `tool_id` query filters plus filtered/total counts. |
| `GET` | `/metis/export` | `metis_head.brain` | Export state, LEDs, readiness, and event log. |
| `POST` | `/metis/artifacts/save` | `metis_head.brain` | Persist an `export` or `manifest` JSON artifact locally. |
| `GET` | `/metis/artifacts` | `metis_head.brain` | List saved artifact metadata. |
| `GET` | `/metis/artifacts/{filename}` | `metis_head.brain` | Read one saved artifact envelope by safe filename. |
| `GET` | `/metis/sim/manifest` | `metis_head.brain` | Portable `metis_sim_tests.v0.1` manifest with optional scenario results. |
| `GET` | `/metis/sim/tests` | `metis_head.brain` | Alias for the simulation test manifest endpoint. |
| `POST` | `/metis/replay` | `metis_head.brain` | Replay a JSON event list from baseline or current state. |
| `POST` | `/metis/state/reset` | `metis_head.brain` | Reset mock Brain state and scenario results to baseline. |
| `POST` | `/metis/scenario/run` | `metis_head.brain` | Run one scenario or all scenarios. |
| `GET` | `/metis/scenario/results` | `metis_head.brain` | Return latest scenario results. |
| `GET` | `/metis/health` | `metis_head.brain` | Brain health, failures, readiness, parity manifest. |
| `GET` | `/metis/adapters` | `metis_head.brain` | Current adapter registry. |
| `GET` | `/metis/providers` | `metis_head.brain` | Mock provider harness catalog grouped by provider. |
| `POST` | `/metis/providers/{operation_id}/invoke` | `metis_head.brain` | Invoke a deterministic mock provider operation and reduce any emitted events. |
| `POST` | `/metis/adapters/{adapter_id}/set_health` | `metis_head.brain` | Mutate mock adapter health. |
| `POST` | `/metis/failures/{failure_id}/trigger` | `metis_head.brain` | Trigger visible failure. |
| `POST` | `/metis/failures/clear` | `metis_head.brain` | Clear active failure state. |

## CLI Entry Points

| Command | Owner | Purpose |
|---|---|---|
| `python -m metis_head.bridge_emulator` | `metis_head.bridge_emulator` | Emit or replay simulator bridge events as JSON, local reducer state, or mock-Brain POSTs. |
| `metis-bridge-emulator` | `pyproject.toml` | Installed console-script alias for the bridge emulator. |

## Scenario IDs

| Scenario ID | Requirement Covered |
|---|---|
| `baseline_boot_no_adapters` | Safe boot with all adapters disabled. |
| `pwr_standby_no_hidden_listening` | Standby does not imply hidden listening. |
| `output_muted_not_privacy` | Output mute does not imply privacy. |
| `volume_control_updates_state` | Volume control updates spoken output level. |
| `conversation_depth_control_updates_state` | Conversation depth control updates depth bucket. |
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
| `bridge_heartbeat_sets_bridge_ok` | Bridge heartbeat marks bridge module healthy. |

## Readiness Domain

| Domain | Current Phase | Notes |
|---|---|---|
| `simulation_readiness` | 0A/0S/0Y | Computed from weighted checklist, not static text; currently all checklist items pass. |

## Future Build Placeholders

| Future Area | Placeholder Names | Notes |
|---|---|---|
| Phase 0R provider research | `stt_provider_candidate`, `tts_provider_candidate`, `vision_provider_candidate`, `llm_runtime_candidate` | Record evidence-backed recommendations only after bakeoff. |
| Hardware bridge | `serial_bridge`, `websocket_bridge`, `bridge_transport` | Must emit same event schema as simulator. |
| LED provider | `led_renderer`, `led_provider`, `led_command` | Provider receives already-resolved Metis LED state. |
| Persistence | `event_log_path`, `state_export`, `scenario_manifest_path` | Start JSONL; add SQLite only if needed. |
| Memory lifecycle | `memory_candidate`, `memory_review`, `memory_promotion`, `memory_deletion_audit` | No silent promotion. |
| External tool lane | `tool_proposal`, `approval_request`, `execution_receipt` | 0T registry/dry-run/proposal lane exists, 0T/CHAT can route clear chat intents into that lane, 0U can review proposals, 0W records execution receipts, 0Q documents the future read-only execution policy, 0J routes chat `git.status`/`filesystem.read` requests to active approved read-only proposal lanes, 0K adds blocked fetch proposals plus visible planning dry-runs, 0N hardens replay/receipt coverage for those lanes, 0D exposes lifecycle labels for operator visibility, 0E adds blocked BOH retrieval proposals, 0I adds proposal filters, 0H exposes permission requirement metadata, 0AA exports the derived tool contract manifest, 0AB composes the operator policy snapshot, 0AC validates tool arguments against manifest schemas, 0AD exposes advisory gate evaluation, 0AE adds single-proposal review scope, 0AF computes governed-tool readiness, 0AG computes 100% completion for the current simulation-first governed tool substrate, 0AH adds deterministic task planning, 0AI persists reviewable plans, 0AJ adds non-standing plan review, 0AK queues eligible approved-plan step proposals, 0AL requests execution for approved step proposals through existing receipt gates, 0AM binds safe receipt summaries into dependent pending proposals, 0AN adds guided advancement with review stops, and 0AO lets explicit chat planning requests create persisted plans. Approval remains separate from execution; future live integrations require additional scoped execution phases after explicit governance gates. |
| Project Atlas adapter | `atlas_task_proposal`, `atlas_task_receipt` | Future adapter only, no internal imports. |
| BOH adapter | `boh_retrieval_candidate`, `boh_citation` | Read-only retrieval bridge implemented in 0B (`metis_head.boh_retrieval`); deeper adapter wiring still future. |
| Robot safety adapter | `actuator_action_classification`, `safety_gate_result` | Pattern donor now; future adapter only. |
