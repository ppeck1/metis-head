# Handoff

## Candidate

- Branch: `codex/metis-completion-2026-09-16`
- Baseline: `5eebb0384416116e6244542cac3224664963cf32`
- Scope: local typed/browser-voice assistant with private sessions, Ollama tool loop, selected read-only Google data, and named Atlas/BOH reads.
- Boundary: no deployment, publication, external mutation, paid request, or MCE activation.

## Capability status

Component and controlled production-path fixtures cover early turn ownership, cancellation/error recovery, browser WAV capture, owned playback, authoritative context, Google discovery/selections/grants, Atlas registry/provenance, and concurrent durable paid accounting. Live microphone, speech models, OAuth accounts, Ollama model, and current MCP sources remain target-machine checks.

Final local verification: `571 passed in 13.05s`; compileall, dashboard JavaScript parsing, and diff hygiene passed. An independent read-only review found three integration gaps, which were repaired and covered by delayed-retrieval/pre-registration cancellation, attribution, session selection, unselected-calendar, and cross-account denial regressions.

OpenAI chat is deliberately unavailable in the application even if an API key exists. The accounting foundation is tested, but production paid-provider composition requires a separate credential/pricing decision and authorization.

## Extracted boundaries

- `conversation/`: private sessions, turn tokens, legal state transitions, cancellation.
- `audio/` and `static/conversation_client.js`: bounded artifacts, playback queue/acknowledgements, browser epochs.
- `conversation_context.py`: trusted clock/selections/capabilities and separately delimited untrusted BOH evidence.
- `connectors/` and `personal_orchestration.py`: Google/Atlas transports, grants, discovery, tool registry, provenance.
- `model_adapters/`: bounded provider-neutral and local Ollama codecs.
- `usage/`: reservations, reconciliation, cross-process locking, exports.
- `runtime_paths.py` and `startup_readiness.py`: installed-state paths and truthful capability checks.

## Verification and blockers

See `docs/COMPLETION_LEDGER.md` for C01-C10/N0-N8 status and `docs/ACCEPTANCE.md` for exact setup and live checks. Live results must not be inferred from fixture results.

## Rollback

Use the branch/commit history and scoped diffs. Never run a blanket reset/clean against this checkout; earlier Phase 0BH-0BM work and local ignored configuration coexist with this candidate.
