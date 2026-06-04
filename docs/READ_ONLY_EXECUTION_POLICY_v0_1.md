# Read-Only Execution Policy v0.1

Phase: `0Q`

Status: active contract with three scoped approved read-only receipt lanes.

## Purpose

This policy defines the minimum contract Metis must satisfy before any future phase can execute
approved read-only tools. Phase 0L activates the internal `time.now` lane after proposal review.
Phase 0G activates `git.status` for the current allowlisted repo with fixed no-shell arguments. It
Phase 0F activates `filesystem.read` for current-repo text preview with path, extension, and size
gates. Phase 0J routes explicit chat requests into those active approved read-only proposal lanes,
but chat still never executes them directly. Phase 0K adds a blocked `fetch.url_proposed` lane for
future URL retrieval review and a side-effect-free visible planning dry-run. Phase 0E adds blocked
`boh.retrieve_proposed` for future retrieval-as-tool review. Phase 0AA adds a derived tool contract
manifest for inspection/export only; it does not grant permission or execution authority. Phase 0AB
adds a composed policy snapshot for operator review only; it does not approve proposals, request
execution, or broaden any lane. Phase 0AC validates tool arguments against manifest input schemas
before proposals, dry-runs, execution requests, or chat-routed tool requests proceed. Phase 0AD adds
advisory gate evaluation for operator preflight review only; it does not queue, approve, request, or
execute tools. Phase 0AE makes proposal review scope explicit: approvals and denials are
single-proposal, non-transferable, non-standing, and still do not directly allow execution. It does
not enable arbitrary filesystem reads, arbitrary git commands, live URL fetch, BOH mutation, Atlas,
hardware, shell, or external actions. Phase 0AF adds a computed governed-tool readiness checklist;
it is a measurement surface only. Phase 0AG adds a computed completion report for the current
simulation-first governed tool substrate; future live integrations remain out of scope. Phase 0AH
adds a deterministic task planner that produces reviewable tool plans without running or queueing
tools. Phase 0AI persists those plans in canonical state for review, still without approving,
requesting, or executing any step. Phase 0AJ reviews persisted plans with approve/deny receipts,
still without creating step proposals, requesting execution, or executing any step. Phase 0AK lets
an approved plan queue eligible step proposals through the existing governed proposal lane, still
without approving those proposals, requesting execution, or executing any step.
Phase 0AL can request execution for approved plan step proposals through the same receipt gates used
by single proposals. Unapproved steps are skipped, and future-only or side-effectful steps remain
blocked by their existing proposal/receipt policies.
Phase 0AM can bind bounded receipt summaries and output hashes from completed approved steps into
later pending dry-run proposals. It must not bind raw file contents, raw command output, external
receipts, secrets, or reviewed/immutable proposals.
Phase 0AN can guide the next plan transition by calling already-governed endpoints. It must stop at
plan review and proposal review gates, and must not approve, deny, or execute unreviewed work.
Phase 0AO can route explicit chat planning requests into persisted governed tool plans and return the
first next-action recommendation. Chat planning must not approve plans, queue step proposals, request
execution, bind results, or execute tools.
Phase 0AP can describe governed tool capabilities in LLM system context. This is prompt accuracy
only; it does not let LLM providers call tools directly or add execution authority.
Phase 0AQ clarifies the policy language: arbitrary/autonomous execution remains disabled, while
scoped approved read-only receipt lanes may run only after proposal review and lane gates. It also
anchors current-repo local read-only lanes to `METIS_REPO_ROOT` when configured.

## Non-Goals

- No arbitrary filesystem reads outside the approved current-repo preview lane.
- No git command execution.
- No network fetch.
- No BOH mutation or corpus mirroring.
- No Atlas integration.
- No hardware, microphone, camera, actuator, or robot action.
- No shell execution.
- No autonomous execution from Agent Mode.

## Candidate Read-Only Lanes

| Lane | Status | Minimum Gate |
|---|---|---|
| `time.now` | active approved read-only | Side-effect class must be `none`; proposal must be reviewed; no shell, network, filesystem, or external process may be used. |
| `filesystem.read` | active approved read-only | Current repo path allowlist anchored to `METIS_REPO_ROOT` when configured, text extension allowlist, 32KB size limit, redacted/truncated preview, explicit operator approval. |
| `git.status` | active approved read-only | Current repo allowlist anchored to `METIS_REPO_ROOT` when configured, fixed `git status --short --branch`, output truncation, no porcelain mutation commands. |
| `fetch.url_proposed` | proposal-only blocked | Queues a future URL-fetch proposal for review; performs no DNS, HTTP, or network I/O in Phase 0K. |
| `boh.retrieve_proposed` | proposal-only blocked | Queues a future BOH retrieval-as-tool proposal for review; performs no BOH HTTP call in Phase 0E. |
| `fetch.url` | future only | Domain allowlist, timeout, size limit, content-type filter, no credential forwarding. |
| `boh.retrieve` | existing read-only retrieval bridge | Retrieval token only; never operator token; no mutation; no corpus copy. |

## Chat Routing Boundary

Phase 0J allows the virtual chat `tool_router` to queue proposals for active approved read-only
lanes when the request is explicit and deterministic: `git status` routes to `git.status`, and
`read file ...` / `open file ...` routes to `filesystem.read`. This routing is proposal creation
only. The chat endpoint must not run git, read files, or return read-only previews inline; operator
review plus a separate execution request remain required.

Phase 0K additionally routes explicit `fetch ...` requests to `fetch.url_proposed`, which remains
blocked and performs no network access, and routes `plan:` / `outline plan:` to
`thinking.plan_outline`, a visible side-effect-free dry-run that grants no execution authority.
Phase 0E routes explicit BOH/library search requests to `boh.retrieve_proposed`, which remains
blocked and does not call the existing live BOH chat-grounding bridge.

## Required Approval Gates

Read-only execution requires all of these:

1. A queued proposal with deterministic `proposal_id`.
2. Human review state `review_status=approved`.
3. Tool manifest permission and lane policy allow the requested read-only action.
4. Tool manifest `side_effect_class=none` or `read_only`.
5. Explicit lane policy match.
6. An execution receipt emitted before any result is exposed.
7. Redaction and truncation applied before state, event log, dashboard, or artifacts receive output.

Agent Mode cannot bypass these gates. Approval remains scoped to one proposal unless a future standing
approval contract is explicitly added.

## Redaction Requirements

Receipts and logs must not contain:

- Raw secrets, tokens, passwords, keys, or credentials.
- Full file contents.
- Full command output.
- Raw external HTTP bodies.
- Raw BOH corpus chunks beyond the approved citation/context contract.
- Concrete temporary audio paths.

Allowed receipt summaries:

- Tool ID and proposal ID.
- Policy decision and execution status.
- Redaction classes applied.
- Output hash.
- Output byte/line/item counts.
- Bounded preview only when the lane policy explicitly allows it.

## Receipt Requirements

Future read-only execution receipts must extend `metis_execution_receipt.v0.1` or supersede it with
a documented schema. Required fields:

- `receipt_id`
- `proposal_id`
- `tool_id`
- `policy_decision`
- `execution_allowed`
- `execution_status`
- `side_effect_class`
- `risk_class`
- `created_at`
- `redactions`
- `operator_review_required`
- `output_hash`
- `output_summary`

## Phase 0J Boundary

Phase 0J aligns chat routing with the active `time.now`, `git.status`, and `filesystem.read`
approved read-only lanes. Phase 0F activates `time.now`, `git.status`, and `filesystem.read` as
approved read-only lanes. Phase 0K adds blocked fetch proposals and visible planning dry-runs only.
Phase 0N adds deterministic replay and receipt-detail tests for those paths without enabling
additional execution. Phase 0D adds lifecycle labels to the tool catalog for operator visibility;
these labels do not grant permission or bypass review. Phase 0E adds blocked BOH retrieval proposals
only; BOH retrieval-as-tool remains future work. Phase 0I adds proposal listing filters for operator
inspection only; filters do not mutate review state or authorize execution. Phase 0H adds
`permission_requirements` metadata to the tool catalog for operator review; this metadata does not
grant permission, standing approval, or execution authority. Phase 0AA adds `/metis/tools/contract`
as a derived manifest of counts, lanes, matrix rows, and boundaries; it is visibility only and does
not change any execution gate. Phase 0AB adds `/metis/tools/policy_snapshot`, which composes the
tool contract, read-only policy, proposal queue, execution receipts, and explicit authority flags
into one packet for review. It is visibility only and does not mutate review state, request
execution, or run tools. Phase 0AC adds manifest-backed argument validation and persists
`argument_validation` metadata on proposal/dry-run records; it rejects malformed arguments and drops
secret-like extra fields without persisting raw values. Existing Phase 0W behavior remains for every
other lane. Phase 0AD adds `/metis/tools/governance/evaluate` to report the same gates as an
advisory decision packet; it does not mutate state or grant authority. Execution requests create
blocked or dry-run-only audit receipts, and `external_action_executed` remains `false`. Phase 0AE
adds `metis_proposal_review_scope.v0.1` to reviewed proposals and review receipts so approval cannot
be misread as standing, transferable, or autonomous permission. Phase 0AF adds
`metis_tool_readiness.v0.1`, a derived checklist/score for registry, schema, governance, review,
audit, and boundary readiness. The score does not itself authorize execution.
Phase 0AG adds `metis_tool_completion.v0.1`, which reports 100% completion only for the current
simulation-first governed tool substrate. It does not mark live URL fetch, BOH retrieval-as-tool,
Atlas execution, filesystem writes, arbitrary git commands, shell execution, hardware actions,
external mutation, or autonomous execution as complete.
Phase 0AH adds `metis_tool_task_plan.v0.1`, a non-executing task plan surface. Plans may reference
dry-run, proposal-required, future-only, or blocked steps, but the planner itself does not create
proposals, approve proposals, request execution, or execute tools.
Phase 0AI stores plans in `tool_plan_queue` via replayable `tool_plan` events. Persistence is for
review lifecycle only and does not imply plan approval or step execution.
Phase 0AJ adds `metis_tool_plan_review.v0.1` receipts through replayable `tool_plan_review` events.
Approval or denial is scoped to one persisted plan, is non-transferable and non-standing, and still
does not create proposals for plan steps, request execution, or run tools.
Phase 0AK adds replayable `tool_plan_step_queue` bookkeeping after proposal events are created for
eligible steps of an approved plan. The resulting proposals still require their own review and
execution request gates; blocked/future-only steps remain proposal-only and no step is run by plan
materialization.
Phase 0AL adds replayable `tool_plan_execution_request` bookkeeping after execution-request receipts
are created for individually approved step proposals. It reuses the existing proposal execution
policy; it does not grant standing approval, bypass review, execute unapproved steps, or expand the
approved read-only lane set.
Phase 0AM adds replayable `tool_plan_result_binding` events. Bindings may update only pending
dependent dry-run proposals using bounded `output_summary.preview` and `output_hash` data from prior
receipts. Binding does not approve the dependent proposal, request execution, or expose raw source
content.
Phase 0AN adds `metis_tool_plan_advance.v0.1`, a visibility and orchestration layer over existing
plan endpoints. It may queue step proposals, request execution for already-approved proposals, or
bind safe summaries when the preceding gates are satisfied. It must return `waiting` at human review
gates and does not create standing approval or autonomous execution authority.
Phase 0AO adds a chat-facing planner route for explicit prefixes such as `plan task:`. It creates or
reuses a persisted governed plan, returns `tool_planner` metadata and the first next action, and then
stops. Later review, proposal materialization, execution requests, and result binding remain separate
operator actions.
Phase 0AP adds registry-derived tool capability context to governed chat messages so broad tool
questions do not receive stale "no tools" answers. The LLM prompt must still state that deterministic
Metis routes own tool handling and that providers must not claim autonomous execution.
Phase 0AR adds chat-facing plan status and explicit plan advance prompts. Status prompts are
read-only reports over the latest or named plan. Advance prompts invoke only the existing guided
advance path, which still stops at plan/proposal review gates and cannot approve plans, approve
proposals, create standing authority, or execute unreviewed work.
