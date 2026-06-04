# Metis Head

Simulation-first skeleton for the v0.5 Metis Head buildspec.

This repo intentionally contains no real hardware, microphone, camera, Atlas, or
tool integrations. External systems are represented by versioned adapters and
deterministic mock providers. As of Phase 0B the one live external integration is a
read-only BOH retrieval bridge (opt-in, never mutates BOH, never holds BOH's operator
token).

## Current Phase

Phase scope: `0V/AUDIO10` - duration-scaled Piper spectrum frames (builds on `0A + 0S + 0R virtual chat + 0B retrieval bridge + 0C BOH link + 0S/S4 bridge emulator + 0S/S3 provider harness + 0P personality + 0V voice + 0M manifest + 0X artifacts + 0Y parity + 0V/AUDIO9 animated analyzer + 0T/CHAT governed tools + 0U proposal review + 0W execution audit + 0Q read-only policy + 0L time lane + 0G git status lane + 0F filesystem read lane + 0J active read-only chat routing + 0K fetch/planning seeds + 0N audit replay hardening + 0D lifecycle visibility + 0E BOH proposal lane + 0I proposal filters + 0H permission metadata + 0AA contract manifest + 0AB policy snapshot + 0AC argument validation + 0AD gate evaluation + 0AE review scope + 0AF tool readiness + 0AG completion report + 0AH task planner + 0AI plan queue + 0AJ plan review + 0AK step proposals + 0AL execution requests + 0AM result binding + 0AN guided advance + 0AO chat planning + 0AP truthful tool context`).

Status: Piper voice visualization now generates spectrum frames based on actual WAV duration instead
of a fixed 48-frame packet. Frame amplitudes preserve real segment loudness, and the dashboard uses
one utterance-level visual gain so quiet/loud differences survive animation while the panel still
fills like an old stereo analyzer.

Phase 0V/AUDIO10 implemented:

- Replaced fixed default `audio_spectrum_frames=48` with duration-scaled frame counts at about 16 fps,
  capped for event-log size.
- Scaled each spectrum frame by actual segment RMS relative to the utterance peak instead of
  normalizing every frame to max brightness.
- Added dashboard utterance-level visual gain via `lastVoiceVisualGain` and `visualGainForVoice()`.
- Added tests for duration-scaled frames, loudness preservation, and dashboard gain hooks.

Previous Phase 0AP status: Metis gives Ollama/OpenAI/mock chat providers an explicit governed-tool capability
context derived from the canonical tool registry. Broad questions like "what tools can you use?"
should no longer produce stale "I have no tools" answers; the model is instructed to describe the
governed lanes truthfully while preserving the boundary that LLM providers do not call tools
directly or execute autonomously.

Phase 0AP implemented:

- Added registry-derived tool capability context to `governed_messages()`.
- Listed safe dry-run tools, approved read-only lanes, proposal/future lanes, and persisted task-plan
  gates in the LLM system context.
- Added Agent Mode wording that every tool request becomes proposal-only.
- Added tests preventing the LLM prompt from regressing to "no tools" or autonomous-execution claims.

Previous Phase 0AO status: Metis chat can create persisted governed tool plans from explicit planning
requests such as `plan task: summarize pyproject.toml`. The chat route returns the queued plan, first
governed `next_action`, and `tool_planner` metadata, but it does not approve the plan, queue step
proposals, request execution, bind results, or execute anything.

Phase 0AO implemented:

- Added explicit chat planning prefixes for persisted governed tool plans.
- Added chat responses with provider `tool_planner`, model `metis_tool_task_plan.v0.1`, plan status,
  and next-action metadata.
- Added dashboard chat status markers for `plan_queued` and `tool_planner`.
- Added tests for chat-created plans, duplicate plan reuse, Agent Mode plan-only behavior, empty-task
  rejection, dashboard hooks, and no external execution.

Previous Phase 0AN status: Metis has a guided `advance` control for tool plans. It calculates the next
governed action and either performs safe mechanical transitions (`queue_steps`, approved step
`request_execution`, or `bind_results`) or stops at human review gates (`needs_plan_review`,
`needs_step_proposal_review`). It never approves proposals, bypasses review, or grants autonomous
execution.

Phase 0AN implemented:

- Added `metis_head/tool_plan_runner.py` with `metis_tool_plan_advance.v0.1`.
- Added `POST /metis/tools/plans/{plan_id}/advance`.
- Added dashboard `Advance Plan` control.
- Added tests for review-gate stops, guided queueing, guided approved-step execution, guided result
  binding, deterministic next-action calculation, dashboard hooks, and no execution bypass.

Previous Phase 0AM status: Metis can bind safe receipt summaries from completed approved plan steps
into later pending dry-run step proposals. The first supported handoff is approved
`filesystem.read` / `git.status` receipt summaries into a pending `text.summarize` step. Binding
uses bounded receipt previews and hashes only; it does not expose raw file contents, command output,
or external receipts.

Phase 0AM implemented:

- Added replayable `tool_plan_result_binding` reducer events.
- Added `POST /metis/tools/plans/{plan_id}/bind_results`.
- Added dashboard `Bind Results` control.
- Added tests for safe binding, dependent summarize execution, reviewed-proposal immutability,
  deterministic replay, dashboard hooks, and no raw-content leakage.

Previous Phase 0AL status: Metis can request execution for approved step proposals in an approved
governed tool plan. The endpoint reuses existing execution receipts and lane gates; unapproved steps
are skipped, side-effectful/future-only steps remain blocked by their receipts, and
`external_action_executed` stays false.

Phase 0AL implemented:

- Added replayable `tool_plan_execution_request` bookkeeping events.
- Added `POST /metis/tools/plans/{plan_id}/request_execution`.
- Refactored single-proposal execution request construction so plan requests reuse the same policy path.
- Added dashboard `Request Plan Execution` control.
- Added tests for approved step execution requests, unapproved-step skipping, idempotency,
  deterministic replay, dashboard hooks, and no external action.

Previous Phase 0AK status: Metis can take an approved governed tool plan and queue proposal records
for eligible plan steps. This turns a reviewed plan into the existing proposal/review/request
machinery while preserving the boundary: no step is executed, read-only proposals still require
their own review and request, and blocked/future-only tools remain governed proposals only.

Phase 0AK implemented:

- Added replayable `tool_plan_step_queue` bookkeeping events.
- Added `POST /metis/tools/plans/{plan_id}/queue_steps`.
- Added idempotent step materialization metadata on persisted plan steps.
- Added dashboard `Queue Step Proposals` control.
- Added tests for approved-plan step proposal queueing, unapproved/denied blocking, idempotency,
  deterministic replay, dashboard hooks, and no execution.

Previous Phase 0AJ status: Metis can review persisted governed tool task plans through deterministic
approve/deny events. Plan review records a non-standing receipt, clears pending plan counts, and
still does not execute plan steps, create step proposals, read files, run git, fetch URLs, call BOH,
or grant autonomous authority.

Phase 0AJ implemented:

- Added replayable `tool_plan_review` reducer events.
- Added `metis_tool_plan_review.v0.1` review receipts with `execution_allowed=false`.
- Added `POST /metis/tools/plans/{plan_id}/approve` and
  `POST /metis/tools/plans/{plan_id}/deny`.
- Added dashboard controls for plan review.
- Added tests for approve, deny, replay determinism, errors, dashboard hooks, and no execution.

Previous Phase 0AI status: Metis persists governed tool task plans in canonical state.
`POST /metis/tools/task/plan` queues a reviewable plan by default, `GET /metis/tools/plans` lists
saved plans, and `GET /metis/tools/plans/{plan_id}` returns one saved plan. Plan persistence still
does not approve, request, or execute tools.

Phase 0AI implemented:

- Added canonical `tool_plan_queue`.
- Added replayable `tool_plan` reducer events.
- Changed `/metis/tools/task/plan` to persist plans by default, with `persist=false` for preview-only.
- Added `GET /metis/tools/plans` and `GET /metis/tools/plans/{plan_id}`.
- Added tests for deterministic plan replay, persisted plan list/detail, preview-only planning, and
  no execution.

Previous Phase 0AH status: Metis accepts broad tool-task requests through
`POST /metis/tools/task/plan` and turns them into deterministic, reviewable tool plans. Plans can
include read-only proposal steps (`git.status`, `filesystem.read`), safe dry-run steps
(`text.summarize`, `thinking.plan_outline`), future-only steps (`fetch.url_proposed`,
`boh.retrieve_proposed`), and blocked mutation/external steps. Planning does not queue, approve,
request, or execute tools.

Phase 0AH implemented:

- Added `metis_head/tool_task_planner.py` with `metis_tool_task_plan.v0.1`.
- Added `POST /metis/tools/task/plan`.
- Added dashboard `Plan Task` visibility in the Tools panel.
- Added tests for multi-step read-only plans, future fetch plans, mutation blocking, and dashboard
  endpoint visibility.

Previous Phase 0AG status: Metis exposes a computed governed tool completion report at
`GET /metis/tools/completion`. The report reaches `100%` for the current
`simulation_first_governed_tool_substrate` only when readiness, registry lanes, proposal/review
controls, audit receipts, and no-execution boundaries all pass. Future live fetch, BOH-as-tool,
Atlas, filesystem write, shell, hardware, external mutation, and autonomous execution lanes remain
explicitly out of scope.

Phase 0AG implemented:

- Added `metis_head/tool_completion.py` with `metis_tool_completion.v0.1`.
- Added `GET /metis/tools/completion`.
- Added dashboard `Tool Completion` visibility in the Tools panel.
- Added tests proving completion is computed, reaches `100%` for the governed simulation substrate,
  drops when execution boundaries are violated, and lists future live lanes as out of scope.

Previous Phase 0AF status: Metis exposes a computed governed tool readiness checklist at
`GET /metis/tools/readiness`. The checklist derives score and status from registry/schema coverage,
argument validation, gate evaluation, policy/contract surfaces, review scope, receipt safety, and
no-execution boundary checks. The score is computed, not static.

Phase 0AF implemented:

- Added `metis_head/tool_readiness.py` with `metis_tool_readiness.v0.1`.
- Added `GET /metis/tools/readiness`.
- Added dashboard `Tool Readiness` visibility in the Tools panel.
- Added tests proving readiness score is computed, domain-labeled, and sensitive to failed
  execution-boundary state.

Previous Phase 0AE status: Metis records explicit review scope on proposal review receipts and
reviewed proposal records. Every approval or denial is scoped to one proposal, is non-transferable,
is not a standing approval, and still carries `execution_allowed=false`.

Phase 0AE implemented:

- Added `metis_proposal_review_scope.v0.1`.
- Added `review_scope` to proposal review receipts.
- Persisted `review_scope` onto reviewed proposal records.
- Added tests proving approvals and denials remain single-proposal, non-standing, non-transferable,
  and non-executing.

Previous Phase 0AD status: Metis exposes a centralized governed tool gate evaluator at
`POST /metis/tools/governance/evaluate`. The evaluator validates arguments, reports required gates
and blocked capabilities, and explains whether a request would dry-run, queue a proposal, or remain a
dry-run receipt only. It is advisory only: it does not queue proposals, approve requests, request
execution, or run tools.

Phase 0AD implemented:

- Added `metis_head/tool_governance.py` with `metis_tool_gate_evaluation.v0.1`.
- Added `POST /metis/tools/governance/evaluate`.
- Added dashboard `Evaluate Gate` visibility in the Tools panel.
- Added tests proving Human Mode safe dry-run, Agent Mode proposal gating, execute-request
  non-authority, read-only gate surfacing, and invalid-argument rejection.

Previous Phase 0AC status: Metis validates tool arguments against each manifest input schema before
dry-runs, proposal queueing, execution requests, and chat-routed tool requests proceed. Missing
required fields, primitive type mismatches, and non-sensitive extra fields are rejected with `400`;
secret-like extra fields are dropped with a replayable validation warning so raw values are not
persisted.

Phase 0AC implemented:

- Added `metis_tool_arguments.v0.1` validation receipts for tool argument checks.
- Added `validate_tool_arguments()` in `metis_head.tool_registry`.
- Wired validation into `build_tool_proposal_event()`, `dry_run_tool()`, and `execute_tool()`.
- Persisted proposal `argument_validation` metadata through the reducer.
- Added tests for missing required arguments, wrong types, unexpected extra fields, and secret-like
  extra-field dropping.

Previous Phase 0AB status: Metis exposes a governed tool policy snapshot at
`/metis/tools/policy_snapshot`. The snapshot composes the tool contract manifest, read-only execution
policy, current proposal queue, execution audit receipts, and explicit authority flags into one
operator review packet. This is an inspection/export surface only; it does not approve proposals,
request execution, run tools, or broaden any read-only lane.

Phase 0AB implemented:

- Added `metis_head/tool_policy_snapshot.py` with `metis_tool_policy_snapshot.v0.1`.
- Added `GET /metis/tools/policy_snapshot`.
- Added dashboard Policy Snapshot visibility in the Tools panel.
- Added tests proving the snapshot reflects live proposals/receipts while preserving
  `execution_authority_changed=false`.

Previous Phase 0AA status: Metis exposes a governed tool contract manifest at
`/metis/tools/contract`. The manifest summarizes registry counts, permission lanes, lifecycle lanes,
per-tool governance matrix rows, and non-execution boundaries for operator review. This is an
inspection/export surface only; it does not grant execution, standing approval, or bypass review.

Phase 0AA implemented:

- Added `metis_head/tool_contract.py` with `metis_tool_contract.v0.1`.
- Added `GET /metis/tools/contract`.
- Added dashboard Tool Contract visibility in the Tools panel.
- Added tests proving the manifest reports active, dry-run, proposal-only, and future-only lanes
  without broadening execution.

Previous Phase 0H status: Metis exposes derived `permission_requirements` metadata for every
registered tool in `/metis/tools` and `/metis/tools/{tool_id}`. This describes required gates and
blocked capabilities for operator review, but does not grant execution, standing approval, or bypass
review.

Phase 0H implemented:

- Added `permission_requirements` to tool catalog/detail responses.
- Captured required gates, blocked capabilities, human-review requirements, and standing approval
  status per tool.
- Added dashboard copy making clear permission metadata is visibility-only.
- Added tests proving permission metadata does not broaden execution.

Previous Phase 0I status: Metis supports operator proposal filtering in `/metis/proposals` and the dashboard.
Reviewers can filter by review/status, proposal type, and tool ID without mutating the queue or
changing approval/execution behavior.

Phase 0I implemented:

- Added optional `status`, `proposal_type`, and `tool_id` filters to `GET /metis/proposals`.
- Added `total_count`, `filtered_count`, and `filters` metadata to proposal listings.
- Added dashboard proposal filter controls and filtered count display.
- Added tests proving filters work for pending/reviewed, memory/action, and tool-specific proposals.

Previous Phase 0E status: Metis has a proposal-only `boh.retrieve_proposed` tool shape for future
retrieval-as-tool review. Chat requests like `search boh ...`, `retrieve boh ...`, and
`search library ...` queue a governed tool proposal and do not call live BOH retrieval. The existing
Phase 0B/0C BOH chat grounding bridge remains the only live BOH path.

Phase 0E implemented:

- Added `boh.retrieve_proposed` to the governed tool registry.
- Routed explicit BOH/library search chat requests to a queued proposal.
- Added tests proving BOH retrieval proposals do not call `/api/retrieve` and remain blocked after
  review/request execution.

Previous Phase 0D status: Metis exposes derived lifecycle metadata for every registered tool in `/metis/tools`
and `/metis/tools/{tool_id}`. The dashboard Tools selector displays operator-facing lifecycle labels
such as `dry_run_available`, `approved_read_only`, and `proposal_only` while enforcement remains in
the existing permission/review/execution gates.

Phase 0D implemented:

- Added centralized `lifecycle` metadata to tool manifest API output.
- Labeled dry-run-only, approved read-only, proposal-only, blocked-after-review, and future-only
  surfaces without broadening execution.
- Updated the dashboard tool selector to show lifecycle labels.
- Added tests proving lifecycle visibility does not enable fetch/network execution.

Current estimate: the overall simulation-first Metis mock brain/UI is about `90%` complete for the
current review target. The governed tools substrate is `100%` complete for the current
simulation-first scope. Practical tool-using task requests are about `88%` complete: Metis can plan
multi-step governed tool tasks from chat or API, persist/review them, queue eligible step proposals, request execution for individually approved step proposals, bind safe receipt summaries into later dry-run steps, and guide the next governed action, but cannot yet run
general live data-dependent plans, live fetch URLs, use BOH as a tool, mutate files, call Atlas, run shell commands,
or act autonomously. Phase 0AP improves usability by making LLM answers describe those tool lanes
accurately instead of denying their existence.

Previous Phase 0N status: Metis has deterministic replay and receipt-detail coverage for the newest tool lanes:
blocked `fetch.url_proposed` proposals and dry-run-only `thinking.plan_outline` execution requests.
No new execution capability was added; this phase hardens the audit contract around the existing
proposal/review/request flow.

Phase 0N implemented:

- Added deterministic replay coverage for approved-but-blocked `fetch.url_proposed` execution
  requests.
- Added deterministic replay coverage for `thinking.plan_outline` dry-run-only execution requests.
- Added receipt listing/detail coverage proving blocked fetch receipts remain inspectable and
  event-log safe.

Previous Phase 0K status: Metis has two additional MCP-inspired native tool shapes without enabling live network
or hidden reasoning: `fetch.url_proposed` queues future URL fetch proposals and remains blocked, while
`thinking.plan_outline` returns a visible dry-run planning outline with `execution_allowed=false`.
Runtime behavior remains locked for arbitrary filesystem reads, arbitrary git commands, network
fetches, BOH/Atlas mutation, hardware action, shell execution, and autonomous execution.

Phase 0K implemented:

- Added `fetch.url_proposed` as a high-risk proposal-only read-only lane; no HTTP request is made.
- Added `thinking.plan_outline` as a low-risk side-effect-free dry-run lane for visible planning.
- Routed explicit chat `fetch ...` requests to a queued fetch proposal.
- Routed explicit chat `plan:` / `outline plan:` requests to a visible planning dry-run receipt.
- Added tests proving fetch remains non-executable and planning produces no execution.

Previous Phase 0J status: Metis chat routes explicit `git status` and `read/open file` requests to the active
approved read-only lanes (`git.status` and `filesystem.read`) instead of the legacy proposal-only
placeholders. Chat still does not execute these tools directly: it queues governed proposals with
`execution_allowed=false`, and approved execution still requires the separate review/request flow.
Runtime behavior remains locked for arbitrary filesystem reads, arbitrary git commands, network
fetches, BOH/Atlas mutation, hardware action, shell execution, and autonomous execution.

Phase 0J implemented:

- Routed clear chat `git status` requests to `git.status`.
- Routed clear chat `read file ...` / `open file ...` requests to `filesystem.read`.
- Preserved legacy `git.status_proposed` and `filesystem.read_proposed` as direct compatibility
  lanes that remain proposal-only and blocked after approval.
- Added chat coverage proving active read-only proposals are queued without direct execution.

Previous Phase 0F status: Metis can execute approved read-only `filesystem.read` for current-repo text previews.
The lane requires a queued proposal and human review, enforces current-repo path allowlisting,
extension allowlisting, a 32KB preview cap, redacted/truncated preview lines, and an
`executed_read_only` audit receipt. Runtime behavior remains locked for arbitrary filesystem reads,
arbitrary git commands, network fetches, BOH/Atlas mutation, hardware action, shell execution, and
autonomous execution.

Phase 0F implemented:

- Added `filesystem.read` as an approved read-only current-repo text preview lane.
- Kept legacy `filesystem.read_proposed` proposal-only and blocked after approval.
- Added path allowlist, text extension allowlist, 32KB size limit, line redaction, and preview
  truncation.
- Added receipt summaries without raw full file contents.
- Updated the read-only execution policy to mark `filesystem.read` active.
- Added tests for approval, allowlist blocking, extension blocking, size blocking, legacy lane
  blocking, and policy status.

Previous Phase 0G status: Metis can execute approved read-only `git.status` for the current
allowlisted repo using fixed no-shell arguments: `git status --short --branch`. The lane requires a
queued proposal and human review, emits an `executed_read_only` audit receipt with bounded output
summary/hash, and still leaves `external_action_executed=false`.

Phase 0G implemented:

- Added `git.status` as an approved read-only tool lane.
- Kept legacy `git.status_proposed` proposal-only and blocked after approval.
- Added fixed-argument, no-shell `git status --short --branch` execution for the current repo only.
- Added output truncation and receipt summaries without raw `stdout`/command output fields.
- Updated the read-only execution policy to mark `git.status` active.
- Added tests for registry labels, approval, allowlist blocking, legacy lane blocking, and policy
  status.

Previous Phase 0L status: Metis can execute one approved internal read-only lane: `time.now`. The
lane requires a queued proposal and human review, emits an `executed_read_only` audit receipt with
bounded output summary/hash, and still leaves `external_action_executed=false`.

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
  `git.status_proposed`, and `memory.propose`. Phase 0K extends the seed bank with
  `thinking.plan_outline` and `fetch.url_proposed`; Phase 0E adds `boh.retrieve_proposed`.
- Added `/metis/tools`, `/metis/tools/{tool_id}`, `/metis/tools/propose`,
  `/metis/tools/{tool_id}/dry_run`, and `/metis/tools/{tool_id}/execute`.
- Extended proposal records with tool ID, sanitized arguments, risk class, side-effect class,
  dry-run availability, and `execution_allowed=false`.
- Added a compact dashboard Tools panel for registry inspection, dry-run, and proposal queueing.
- Added deterministic chat-to-tool routing for explicit `time.now`, `math.calculate`,
  `text.summarize`, `filesystem.read_proposed`, `git.status_proposed`, and `memory.propose`
  intents. As of Phase 0J, chat routes `git status` and `read/open file` intents to the active
  `git.status` and `filesystem.read` proposal lanes.
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
- `GET /metis/tools/contract`
- `GET /metis/tools/completion`
- `GET /metis/tools/policy_snapshot`
- `GET /metis/tools/readiness`
- `GET /metis/tools/{tool_id}`
- `GET /metis/tools/plans`
- `GET /metis/tools/plans/{plan_id}`
- `GET /metis/proposals/{proposal_id}`
- `GET /metis/execution/receipts`
- `GET /metis/execution/receipts/{receipt_id}`
- `GET /metis/execution/policy`
- `POST /metis/event`
- `POST /metis/chat` (selected LLM provider, `tool_router` for explicit governed tool requests, or
  `tool_planner` for explicit governed planning requests)
- `POST /metis/proposals/{proposal_id}/approve`
- `POST /metis/proposals/{proposal_id}/deny`
- `POST /metis/proposals/{proposal_id}/request_execution`
- `POST /metis/tools/plans/{plan_id}/approve`
- `POST /metis/tools/plans/{plan_id}/deny`
- `POST /metis/tools/plans/{plan_id}/queue_steps`
- `POST /metis/tools/plans/{plan_id}/request_execution`
- `POST /metis/tools/plans/{plan_id}/bind_results`
- `POST /metis/tools/plans/{plan_id}/advance`
- `POST /metis/tools/governance/evaluate`
- `POST /metis/tools/propose`
- `POST /metis/tools/task/plan`
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
233 passed under Python 3.11 (includes duration-scaled loudness-preserving Piper spectrum frames, truthful LLM tool capability context, chat-facing governed task planning, guided governed plan advance, governed plan result binding, approved plan execution requests, approved plan step proposal queueing, governed tool plan review, persistent governed tool plan queue, governed tool task planner, governed tool completion report, governed tool readiness checklist, single-proposal review scope, governed tool gate evaluation, governed tool argument validation, governed tool policy snapshot, tool contract manifest visibility, tool permission requirement visibility, proposal inspector filters, BOH retrieval proposal tool shape, tool lifecycle visibility, tool audit replay hardening, fetch proposal and visible planning tool seeds, active read-only chat routing, approved `filesystem.read`, `git.status`, and `time.now` read-only execution, read-only execution policy contract, execution receipt/audit contract, governed proposal review, governed tool registry/dry-run lane, explicit chat-to-tool routing, animated Piper spectrum frames, virtual chat, BOH link, voice, artifacts, and hardware parity coverage)
```

Phase 0B/0C tests monkeypatch the HTTP layer (`metis_head.boh_retrieval._post_json` and
`metis_head.boh_link._request`), so no running BOH instance is required to verify the suite.

Known environment note: Python 3.13 is present on this machine but did not have `pytest` installed during Phase 0A/0S verification.

## Boundaries

Phase 0A/0S/0R/0T/0U/0W/0Q/0L/0G/0F/0J/0K/0N/0D/0E/0I/0H/0AA/0AB/0AC/0AD/0AE/0AF/0AG/0AH/0AI/0AJ/0AK/0AL/0AM/0AN/0AO/0AP does not implement real hardware, microphone, camera, Project Atlas integration, side-effectful external tools, or autonomous execution. As of Phase 0B/0C the only live external integration is the read-only BOH link: the retrieval bridge (`/api/retrieve`, opt-in via `METIS_BOH_ENABLED`) and the background link manager (`/api/health` + `/api/retrieve/status` + a `limit=1` `/api/retrieve` probe, opt-in via `METIS_BOH_BACKGROUND_ENABLED`). Neither mutates BOH, holds BOH's operator token, nor copies the BOH corpus into Metis; BOH remains the source of truth. Phase 0L allows approved internal `time.now` read-only execution. Phase 0G allows approved current-repo `git.status` only. Phase 0F allows approved current-repo text-file previews only. Phase 0J routes chat requests into those active read-only proposal lanes but still requires separate review/request execution. Phase 0K adds blocked fetch proposals and visible planning dry-runs only. Phase 0N hardens deterministic replay and receipt inspection for those tool lanes. Phase 0D adds lifecycle visibility only. Phase 0E adds BOH retrieval proposals only; it does not call BOH through the tool registry. Phase 0I adds proposal filtering only. Phase 0H adds permission requirement visibility only. Phase 0AA adds tool contract manifest visibility only. Phase 0AB adds a composed policy snapshot only. Phase 0AC adds schema validation for tool arguments only. Phase 0AD adds advisory gate evaluation only. Phase 0AE makes review scope explicit and single-proposal only. Phase 0AF adds computed governed-tool readiness only. Phase 0AG adds computed completion reporting for the current governed simulation substrate only. Phase 0AH adds reviewable task planning only. Phase 0AI adds persistent plan storage only. Phase 0AJ adds plan review only. Phase 0AK queues proposal records for approved plan steps only. Phase 0AL requests execution only for already-approved step proposals through existing receipt gates. Phase 0AM binds bounded receipt summaries into pending dependent proposals only. Phase 0AN guides the next available governed transition but stops at every human review gate; it does not approve or execute unreviewed work. Phase 0AO lets chat create persisted governed plans from explicit planning requests only; it does not approve, materialize step proposals, request execution, bind results, or execute tools. Phase 0AP updates LLM context only so providers describe governed tools accurately; it adds no execution authority. Arbitrary filesystem reads, arbitrary git commands, live URL fetch, BOH-as-tool execution, BOH/Atlas mutation, hardware, shell, memory promotion, and external actions remain blocked. Other reference repositories remain pattern donors only.
