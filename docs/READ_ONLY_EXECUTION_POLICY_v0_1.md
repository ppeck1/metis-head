# Read-Only Execution Policy v0.1

Phase: `0Q`

Status: draft contract with three active read-only lanes.

## Purpose

This policy defines the minimum contract Metis must satisfy before any future phase can execute
approved read-only tools. Phase 0L activates the internal `time.now` lane after proposal review.
Phase 0G activates `git.status` for the current allowlisted repo with fixed no-shell arguments. It
Phase 0F activates `filesystem.read` for current-repo text preview with path, extension, and size
gates. Phase 0J routes explicit chat requests into those active approved read-only proposal lanes,
but chat still never executes them directly. Phase 0K adds a blocked `fetch.url_proposed` lane for
future URL retrieval review and a side-effect-free visible planning dry-run. Phase 0E adds blocked
`boh.retrieve_proposed` for future retrieval-as-tool review. It does not enable
arbitrary filesystem reads, arbitrary git commands, live URL fetch, BOH mutation, Atlas, hardware,
shell, or external actions.

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
| `filesystem.read` | active approved read-only | Current repo path allowlist, text extension allowlist, 32KB size limit, redacted/truncated preview, explicit operator approval. |
| `git.status` | active approved read-only | Current repo allowlist, fixed `git status --short --branch`, output truncation, no porcelain mutation commands. |
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
only; BOH retrieval-as-tool remains future work. Existing Phase 0W behavior remains for every other
lane: execution requests create blocked or dry-run-only audit receipts, and
`external_action_executed` remains `false`.
