# Metis Head Handoff Report - 2026-06-05

## Snapshot

- Repo: `B:\dev\metis_head\metis_head`
- Branch: `main`
- Latest feature commit before this handoff: `e3c54e2 Add simulated voice command routing`
- Current phase documented: `0AV` - simulated voice-command tool awareness
- Verification: `257 passed` under Python 3.11 before this handoff pass
- Clean-export target: tracked source/docs/tests only; no caches, local voice models, temp WAVs, or virtual environments
- Opus review follow-up: clean-export test reproducibility was hardened after review; see the notes below.

## Current Capability State

Metis is a simulation-first mock Brain for the radio form factor. The current build has:

- Canonical state, event schema, deterministic reducer, LED/status resolver, scenarios, readiness, adapters, provider harness, and static dashboard.
- Real governed LLM chat path via mock, Ollama, or OpenAI providers.
- Local Piper voice-output path with audible-text normalization and voice-reactive virtual radio analyzer.
- Governed tool registry and proposal/review/receipt lanes.
- Approved read-only receipt lanes for `time.now`, `git.status`, and `filesystem.read`.
- Deterministic task planner, persistent plan queue, plan review, step proposal queueing, execution-request receipts, result binding, guided advance, and next-action guidance.
- Chat-visible tool awareness so LLM-backed answers should not claim Metis has no tools.
- Dashboard guided-action shortcuts that select the relevant proposal or plan without clicking governed action buttons.
- Simulated voice-command ingress at `POST /metis/voice/command`, which routes recognized text through canonical chat/tool governance and requests spoken replies by default.

## Voice/Radio Readiness

The current voice-first path is simulation-ready, not hardware-ready.

Working now:

- Caller supplies recognized text to `/metis/voice/command`.
- Metis emits redacted STT-style provider events.
- The command is routed through `/metis/chat`, so tool awareness, proposal gates, approval summaries, and next-action guidance all work from the voice path.
- Mic cutoff blocks the simulated command before chat/tool routing.
- Voice replies default on for voice commands, using the existing governed TTS path.

Still future:

- Real microphone capture.
- Wake word / push-to-talk loop.
- Real STT engine.
- Voice-only approval confirmation protocol.
- Physical radio panel integration.

## Tool Governance Boundary

The LLM is tool-aware, but it does not call tools directly. Metis Brain owns routing, queueing, review, receipt creation, and policy gates.

Current allowed action surface:

- Safe dry-runs for side-effect-free tools.
- Proposal queueing for governed tool requests.
- Explicit operator review via API/UI.
- Explicit execution-request receipts for approved, scoped read-only lanes.
- No autonomous execution.
- No side-effectful local mutation.
- No arbitrary shell.
- No live URL fetch.
- No BOH-as-tool execution.
- No Atlas mutation.
- No hardware actions.

## Key Runtime Commands

Launch:

```powershell
cd B:\dev\metis_head\metis_head
.\scripts\launch_metis.ps1 -PythonExe "C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe" -Port 8787
```

Full tests:

```powershell
cd B:\dev\metis_head\metis_head
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m pytest
```

Simulated voice-command example:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/voice/command `
  -ContentType "application/json" `
  -Body '{"text":"git status"}'
```

## Important Files

- `README.md` - current phase, launch, boundaries, verification.
- `docs/project_variable_map.md` - canonical variable/API/event/route map.
- `docs/READ_ONLY_EXECUTION_POLICY_v0_1.md` - current governed execution boundary.
- `metis_head/brain.py` - FastAPI mock Brain and chat/voice/tool route orchestration.
- `metis_head/tool_registry.py` - governed tool manifests and dry-run/proposal behavior.
- `metis_head/tool_plan_runner.py` - deterministic plan next-action logic.
- `metis_head/voice.py` - governed TTS/Piper path and voice metadata.
- `metis_head/static/dashboard.html` - virtual radio, chat, tools, guided action UI.
- `scripts/launch_metis.ps1` - repo-root-aware launch script.

## Recommended Next Phases

1. `0AW` - Voice confirmation protocol simulator.
   Add a simulated spoken approval loop with readback, explicit confirmation phrases, cancellation, and tests proving no silent approval.

2. `0AX` - Voice command dashboard/operator trace.
   Show simulated voice-command events, transcript redaction, and speech reply status in the dashboard.

3. `0AY` - Real STT adapter contract.
   Add adapter interface and health/readiness checks for future local STT, without enabling real mic capture yet.

4. `0AZ` - Physical radio panel contract.
   Define the small-panel display/LED contract for tool/approval/voice states before hardware binding.

## Handoff Notes

- Keep reference repos as pattern donors only. Do not vendor or import their internals.
- Keep docs updated before each commit.
- Preserve the approval boundary: guidance may select or describe, but must not approve or execute.
- Treat the radio form factor as the target UX: dashboard controls are development scaffolding, not the final operator path.

## Opus Review Follow-Up

The Opus 4.8 review correctly identified that the clean export omitted `.git`, while several tests
expected a git checkout. The test suite now initializes `.git` only when missing and sets
`METIS_REPO_ROOT` during tests, so unzip-and-test runs can reproduce the current verification state.

The review also flagged filesystem read gate ordering. `filesystem.read` now evaluates allowlist and
extension gates before file existence, so rejection reasons are deterministic and security-relevant
gates are checked first.

The Windows-specific outside-allowlist test path was replaced with a `tmp_path` outside the repo root.
