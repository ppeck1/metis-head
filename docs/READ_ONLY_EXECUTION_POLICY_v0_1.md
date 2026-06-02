# Read-Only Execution Policy v0.1

Phase: `0Q`

Status: draft contract, not runtime execution.

## Purpose

This policy defines the minimum contract Metis must satisfy before any future phase can execute
approved read-only tools. Phase 0Q does not enable real execution. It only records the policy shape
that future code must pass before filesystem, git, fetch, time, BOH, Atlas, hardware, or external
actions are allowed.

## Non-Goals

- No real filesystem reads.
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
| `time.now` | eligible for dry-run-only execution receipts | Side-effect class must be `none`; receipt must remain non-executing in Phase 0W/0Q. |
| `filesystem.read` | future only | Path allowlist, size limit, extension policy, redacted preview, explicit operator approval. |
| `git.status` | future only | Repo allowlist, fixed argument set, output truncation, no porcelain mutation commands. |
| `fetch.url` | future only | Domain allowlist, timeout, size limit, content-type filter, no credential forwarding. |
| `boh.retrieve` | existing read-only retrieval bridge | Retrieval token only; never operator token; no mutation; no corpus copy. |

## Required Approval Gates

Future read-only execution requires all of these:

1. A queued proposal with deterministic `proposal_id`.
2. Human review state `review_status=approved`.
3. Tool manifest `permission_mode=approved_read_only` or stricter future equivalent.
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

## Phase 0Q Boundary

Phase 0Q only publishes this contract and exposes it for review. Existing Phase 0W behavior remains:
execution requests create audit receipts only, and `external_action_executed` remains `false`.
