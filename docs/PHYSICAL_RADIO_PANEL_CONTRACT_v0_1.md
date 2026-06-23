# Physical Radio Panel Contract v0.1

Phase: `0AZ`

Status: design contract only. No hardware is bound, driven, or assumed by this phase. This document
defines the small-panel display/LED contract for **tool, approval, and voice** states so that a future
physical Metis Head panel can render from the same canonical state the simulator already produces.

Spec traceability: buildspec section 5 (canonical state), section 6 (LED/visualizer rules and
precedence), section 7 (host-bridge protocol), section 11 (failure table). This contract extends those
sections to cover the governed-tool, approval-queue, and voice surfaces added in phases `0T`–`0AY`.

---

## 1. Purpose

The radio shell is an instrumented control surface, not the reasoning core (buildspec section 1.1).
When hardware arrives, a small front panel must show the operator what Metis is doing — especially when
a governed tool is queued, an approval is pending, or voice input/output is active — without exposing
content, without becoming an authority, and without diverging from the dashboard.

This contract specifies:

1. The minimal physical panel element set.
2. The exact canonical state fields each element reads.
3. A versioned `panel_render.v0.1` Brain → Bridge message that drives the panel.
4. Panel precedence rules (privacy and governance first).
5. Redaction invariants for voice and tool content.
6. Acceptance criteria for a future implementing phase.

It does **not** authorize hardware, capture, execution, or any new action class.

---

## 2. Non-Goals

- No real panel, LED driver, microcontroller, or display is built or selected in this phase.
- The panel never decides policy, approves proposals, requests execution, or runs tools (buildspec
  section 7.4 bridge constraints remain in force).
- The panel never displays raw transcript text, raw file contents, command output, secrets, or BOH
  corpus chunks.
- No microphone, camera, actuator, or audio capture is enabled.
- The panel is a **render target**, not a source of truth. It must fail visible for status and fail
  closed for actions.

---

## 3. Panel Element Set

The v0.1 panel is intentionally small. It reuses the two status LEDs and vertical visualizer already
defined by `resolve_leds()` and buildspec section 6, and adds four governed-surface indicators plus two
privacy indicators.

| Element | Type | Purpose |
|---|---|---|
| `activity_led` | RGB LED | Runtime activity: idle / listening / retrieving / speaking / awaiting / blocked / failure. Existing. |
| `authority_led` | RGB LED | Authority lane: governed / source-grounded / agent / awaiting-approval / blocked. Existing. |
| `visualizer` | Vertical LED column (32 rows × 8+8 segments target) | Audio-reactive / idle line / muted / privacy-blocked. Existing (phase 0V analyzer geometry). |
| `approval_indicator` | Amber LED + count digit(s) | Pending operator approvals waiting in the queue. New. |
| `tool_indicator` | Blue LED + count digit(s) | Governed tool requests/plans queued but not executed. New. |
| `memory_indicator` | Soft-white LED + count digit(s) | Memory proposals awaiting review. New. |
| `voice_indicator` | Multi-state LED | Voice command active / awaiting spoken confirmation / speaking / output-muted. New. |
| `mic_cutoff_indicator` | Red/off LED | Hardware mic cutoff state (privacy). New, but maps to existing field. |
| `camera_cutoff_indicator` | Red/off LED | Hardware camera cutoff state (privacy). New, but maps to existing field. |

Count digits are optional on minimal hardware; an LED that is simply on/off (with the count available
on the dashboard) satisfies v0.1. The dashboard remains the full audit surface (buildspec section 9);
the panel is a glanceable subset, never a replacement.

---

## 4. Signal Source — Canonical State Only

Every panel element derives from the canonical state object (`metis_state.v0.3`) and the existing
`resolve_leds()` output. The panel must not read provider internals, the event log payloads, or any
adapter directly. Field names below are exact and already present in `baseline_state()`.

| Element | Canonical fields (authoritative) |
|---|---|
| `activity_led` | `resolve_leds().activity_led` (derived from `active_failure`, `authority_state`, `cognition_state`, `audio_state`, `pending_approval_count`, `power_state`) |
| `authority_led` | `resolve_leds().authority_led` (derived from `authority_state`, `source_state`, `source_grounding_enabled`, `interaction_mode`) |
| `visualizer` | `resolve_leds().visualizer` + `output_muted`, `audio_state` |
| `approval_indicator` | `pending_approval_count`, `approval_queue[].status == "pending_review"` |
| `tool_indicator` | `tool_queue_count`, `tool_plan_queue[]` (plans awaiting review/step queueing) |
| `memory_indicator` | `memory_proposal_count`, `approval_queue[].proposal_type == "memory"` |
| `voice_indicator` | `voice_output_state`, `audio_state`, `output_muted`, plus latest voice-command / voice-confirmation status from `event_log` (status only, never text) |
| `mic_cutoff_indicator` | `mic_hardware_enabled` |
| `camera_cutoff_indicator` | `camera_hardware_enabled` |

Rule: **the panel renders state; it never computes policy.** All classification, gating, and approval
logic stay in `governance`, the reducer, and the execution receipt lanes.

---

## 5. Panel Render Message — `panel_render.v0.1`

This extends the Brain → Bridge `render_state` message (buildspec section 7.3). The Brain computes the
full panel frame from canonical state and sends it down; the bridge only illuminates it.

```json
{
  "type": "panel_render",
  "schema_version": "panel_render.v0.1",
  "activity_led": {"state": "awaiting_approval", "color": "amber", "priority": 75},
  "authority_led": {"state": "awaiting_approval", "color": "amber", "priority": 75},
  "visualizer": {"mode": "active", "audio_state": "idle"},
  "approval_indicator": {"on": true, "count": 1, "reason": "proposal_pending_review"},
  "tool_indicator": {"on": true, "count": 1, "reason": "tool_request_queued_not_executed"},
  "memory_indicator": {"on": false, "count": 0},
  "voice_indicator": {"state": "awaiting_confirmation", "output_muted": false},
  "mic_cutoff_indicator": {"capture_enabled": true},
  "camera_cutoff_indicator": {"capture_enabled": false},
  "panel_precedence_applied": "awaiting_approval",
  "execution_allowed": false
}
```

Constraints on the message:

- It carries **no** transcript text, file content, command output, secrets, or proposal payloads —
  only states, counts, and safe reason labels.
- `execution_allowed` is always `false` on the panel frame; the panel cannot represent an executing or
  autonomous state because none exists.
- `reason` strings are drawn from a fixed enum (see section 8), not free text.
- The bridge must treat an unknown field or higher `schema_version` minor as renderable-where-known and
  ignore-the-rest, never as authority to act.

---

## 6. Voice Indicator States

The voice surface (phases 0AV–0AY) is simulation-first today: recognized text is supplied by a caller,
not captured. The panel must reflect voice status truthfully and silently — it shows *that* a voice
interaction is happening, never *what* was said.

| `voice_indicator.state` | Source condition | Panel meaning |
|---|---|---|
| `idle` | `voice_output_state == "idle"` and no active voice command | No voice activity |
| `command_active` | latest `event_log` voice-command event is in transcript/processing status | A recognized voice command is being routed through governed chat/tool paths |
| `awaiting_confirmation` | a voice-confirmation readback is pending for a queued proposal | Metis is waiting for an explicit spoken approve/deny of one proposal |
| `speaking` | `voice_output_state == "speaking"` or `audio_state == "speaking"` | Governed TTS output is active |
| `output_muted` | `output_muted == true` | Output muted — **not** a privacy state; capture/logging unchanged |

Redaction invariant: the panel and the `panel_render` frame must never include the spoken text, its
normalized form, or any field other than redacted length/hash already present in the event log. This
mirrors the existing voice-event redaction (`text_redacted=true`).

---

## 7. Panel Precedence

The panel collapses multiple simultaneous states into one dominant signal using buildspec section 6.4
precedence, extended for the governed-tool/voice surfaces. Highest wins:

1. **Hardware privacy / cutoff** — `mic_cutoff_indicator` / `camera_cutoff_indicator` show red whenever
   capture is disabled while requested; this can never be suppressed by a lower state.
2. **Governance block** — `active_failure == "governance_block"`, `authority_state == "blocked"`, or
   `source_state == "blocked"` → both LEDs red (matches `resolve_leds()`).
3. **System failure** — any other `active_failure` → activity red, authority amber.
4. **Awaiting approval** — `pending_approval_count > 0` or `authority_state == "awaiting_approval"` or
   `voice_indicator == "awaiting_confirmation"` → amber.
5. **Agent mode** — `interaction_mode == "agent"` → authority purple/agent tint.
6. **Source grounding** — `source_state` sourced/unsourced shaping per `resolve_leds()`.
7. **Active runtime** — listening / retrieving / speaking.
8. **Idle**.

The `approval_indicator`, `tool_indicator`, `memory_indicator`, and `voice_indicator` are **additive
status lights**: they may be lit alongside the dominant LED state, because an operator glancing at the
panel needs to see "something is queued" even while another state dominates the main LEDs.
`panel_precedence_applied` records which rule won for audit parity with the dashboard.

---

## 8. Reason Label Enum

`reason` fields use only these labels (extend by minor version when new governed lanes appear):

```
proposal_pending_review
proposal_approved_awaiting_receipt
tool_request_queued_not_executed
tool_plan_pending_review
tool_plan_steps_queued
memory_proposal_pending_review
voice_command_routing
voice_confirmation_readback
output_muted_listening_unchanged
mic_hardware_cutoff
camera_hardware_cutoff
governance_block
provider_failure
```

---

## 9. Privacy Invariants (Core Requirement)

Carried forward from buildspec sections 2.5 and 3.5, unchanged and non-negotiable:

- A software mute (`output_muted`) is never represented as a privacy state. The `voice_indicator`
  `output_muted` value and the `mic_cutoff_indicator` are distinct elements and must never be conflated
  on the panel.
- Whenever capture or session logging is active, the panel must make that visible; the panel may not
  show an "off/quiet" appearance while `logging_state == "session_logging_active"` and capture is live.
- Hardware mic/camera cutoff is the only privacy control. Its panel indicator is driven by the hardware
  line, not by software state, in the eventual implementation.

---

## 10. Failure Display Mapping

Panel failure rendering maps from `active_failure` (buildspec section 11 / `FAILURE_TABLE`). The panel
shows the failure as red activity + a safe reason; the operator goes to the dashboard Failure Console
for recovery detail.

| `active_failure` | Panel signal |
|---|---|
| `governance_block` | both LEDs red, `reason=governance_block` |
| `brain_offline` / `bridge_disconnected` | red heartbeat / no-data pulse on activity LED |
| `stt_failure` / `tts_failure` | activity red; `voice_indicator` returns to `idle`; reason `provider_failure` |
| `vault_unavailable` / `llm_failure` | activity red, authority amber, reason `provider_failure` |
| `tool_blocked` | authority red, reason `governance_block` |
| `mic_cutoff_enabled` (privacy, not a fault) | `mic_cutoff_indicator` red; takes precedence over runtime states |

---

## 11. Acceptance Criteria for the Implementing Phase

A later phase (suggested `0BA` panel resolver) should satisfy these without binding hardware:

1. A pure `resolve_panel(state) -> panel_render.v0.1` function exists, deriving every field from
   canonical state and `resolve_leds()` only.
2. Privacy and governance precedence are proven: with mic cutoff engaged, the panel shows the cutoff
   indicator regardless of any concurrent runtime or approval state.
3. `pending_approval_count`, `tool_queue_count`, `memory_proposal_count`, and `tool_plan_queue` length
   drive their indicators deterministically, including the zero/off case.
4. Voice indicator transitions (`idle → command_active → awaiting_confirmation → speaking → idle`) are
   derived from `voice_output_state`/`audio_state` and voice-event status, never from text.
5. The `panel_render` frame contains no transcript text, file content, command output, secrets, or
   proposal payloads — asserted by test.
6. `execution_allowed` is `false` in every produced frame.
7. The panel frame is consistent with the dashboard for the same state (no divergence in counts or
   dominant state).
8. Deterministic replay: identical state in → identical `panel_render` out.

---

## 12. Boundary Statement

This contract adds **zero** execution authority. The panel is a downstream render of governed state.
It cannot approve, deny, request execution, queue, promote memory, capture audio/video, or bypass any
gate. The bridge that eventually drives it remains bound by buildspec section 7.4: it may render and
report, but it may not decide Agent Mode permissions, execute external actions, promote memory,
override governance blocks, or hide active capture/logging state.

When hardware is introduced, it must plug into `panel_render.v0.1` (and the existing event schema)
rather than introducing a parallel state path — preserving the v0.5 requirement that hardware reuse the
same contracts already exercised by the simulator.
