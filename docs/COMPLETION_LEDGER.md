# Completion Release Ledger

Baseline: `5eebb0384416116e6244542cac3224664963cf32` plus preserved uncommitted Phase 0BH-0BM work. Branch: `codex/metis-completion-2026-09-16`. No reset, clean, push, deployment, external write, paid request, or MCE activation was performed.

Evidence states are deliberately separate: component, production-path fixture, and live target-machine evidence.

| Task | Dependencies | State | Component evidence | Production-path fixture | Live evidence / blocker |
|---|---|---|---|---|---|
| N0 tree/contracts | none | verified | dirty/untracked work preserved; contracts reconciled | baseline and delta suites | not applicable |
| N1 lifecycle/cancellation | N0 | verified | early tokens, legal terminalization, recovery | delayed STT, invalid input, provider failure, no-artifact speech | device timing pending |
| N2 browser capture/playback | N0/N1 | verified | capture and playback modules | executable Node harnesses plus API tests | microphone/Piper/browser run pending |
| N3 context/attribution | N0 | verified | trusted clock/account/calendar/project envelope; bounded BOH evidence | actual Ollama codec payload and Friday follow-up | live model pending |
| N4 Google lifecycle | N3 | verified | real discovery transport, refresh persistence, selection metadata, disconnect | broker-backed Calendar/Gmail/Contacts; dashboard selection flow | desktop OAuth consent pending |
| N5 Atlas/BOH | N3 | verified | Atlas registry in ordinary tool composition | named-project resolution, provenance, MCP envelope normalization | configured local MCP freshness recheck pending |
| N6 paid provider | N0/N3 | blocked | cross-process ledger/reservations fixture-verified | production OpenAI dispatch intentionally disabled | explicit credential/pricing/product decision required |
| N7 setup/readiness/retention | applicable N1-N6 | verified | shared runtime paths; bounded histories/artifacts/commands; truthful readiness | readiness and packaging tests | installed asset checks pending |
| N8 release acceptance | N1-N7 | verified (fixture) | 571-test suite, compileall, JS syntax/harnesses, independent review regressions | integrated controlled external boundaries | target-machine procedure pending |

## C01-C10 disposition

- C01-C03: repaired with pre-STT turn ownership, cancellation epochs, centralized terminalization, idempotent playback acknowledgement, STOP draining, and pre-start failure handling.
- C04-C05: repaired with one authoritative context envelope; BOH is supplied to the actual model payload and source labels distinguish sourced, degraded, and unsourced responses.
- C06: repaired in software with real calendar discovery, persistent selection, restored actual scopes, practical disconnect, and broker enforcement on every read route. Live OAuth remains pending.
- C07: repaired in ordinary tool-capable Ollama composition through the Atlas registry. Live MCP configuration/freshness remains pending.
- C08: shared ledger races and reservation recovery are repaired. Cloud chat is formally deferred and reports `implemented_but_disabled`; no paid dispatch is reachable.
- C09: readiness checks the actual speech gates/assets, global and per-service MCP gates, Google metadata, and disabled cloud path. State defaults outside the package directory.
- C10: lifecycle, playback, context, connectors, model adapters, accounting, readiness, and runtime paths are focused modules. `brain.py`/dashboard retain compatibility glue; wholesale rewrite is intentionally deferred.

## External blockers

Live Google acceptance requires desktop OAuth consent. Live voice acceptance requires browser microphone permission, an installed faster-whisper model, and configured Piper executable/model. Ollama requires a tool-capable installed model. Atlas/BOH require private local read-only MCP configuration. OpenAI remains unavailable by design until a separately authorized credential/pricing integration is completed.

## Final automated evidence

- `python -m pytest -q` → `571 passed in 13.05s`.
- `python -m compileall -q metis_head tests` → passed.
- Dashboard inline JavaScript parse → passed; executable browser modules are included in the pytest total.
- `git diff --check` → passed; only Windows line-ending conversion warnings were emitted.
- The independent read-only review initially found cancellation, attribution, and selection gaps; each now has a production-path regression in `test_completion_review_regressions.py` or `test_completion_google_selection_routes.py`.
