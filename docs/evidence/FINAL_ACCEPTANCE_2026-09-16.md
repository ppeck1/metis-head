# Final acceptance evidence — 2026-09-16 account-aware repair

- Branch: `codex/metis-completion-2026-09-16`
- Working source baseline before checkpoint commit: `354b570253f0`
- Runtime build while validating: `354b570253f0+working`
- Interpreter: Python 3.11
- App URL: `http://127.0.0.1:8787/` (loopback)

## Automated verification

```powershell
python -m pytest -q
```

Result: **620 passed in 16.68s**.

Additional checks:

- `python -m compileall -q metis_head tests` — passed.
- `node tests\node_audio_setup.cjs` — passed.
- `node tests\node_voice_capture.cjs` — passed.
- `node tests\node_setup_connections.cjs` — passed with six dummy connections, stable IDs, independent removal, and reload.
- `git diff --check` — passed; Windows line-ending conversion notices only.

Production-path regressions cover:

- exact full-label and unique-alias account routing, exclusions, ambiguity, deliberate combined accounts, revoked mappings, and typed/voice clarification;
- real Google OAuth library callback handling with token/API transport mocked, strict expiry/state/single-use/denial behavior, and no HTTPS-validation bypass;
- calendar discovery and empty/non-empty persisted grant enforcement;
- saved voice/STT initialization ordering and stale catalog/capture/transcription cancellation;
- variable-length setup schema migration and six dummy connections;
- Atlas Off blocking ordinary registry transport plus exact named-project MCP status routing.

## Restarted runtime check

The old process was stopped and the tracked launcher restarted the application from this checkout. Sanitized endpoint inspection reported:

- setup schema: `2`;
- effective LLM: `ollama` from saved Setup state;
- effective STT: `faster_whisper` from the explicit launcher environment override;
- effective TTS: `piper` from saved Setup state.

Configuration is not treated as execution evidence. The readiness payload separately reports effective configuration, recorded successful local probes, and operator-confirmed physical output.

## Browser and live-service boundary

Windows browser control was attempted twice after the restart. The trusted helper exited during initialization with `helper_unknown_error: setup refresh had errors`; no UI action was performed. A headless/cloud browser was not substituted.

Preserved prior target-machine evidence: the operator confirmed browser microphone capture, faster-whisper transcription, and audible Piper output earlier on 2026-09-16. This repair did not independently re-confirm physical microphone/speaker behavior.

Still requires the operator:

- reload `/setup` and the dashboard, confirm saved model/voice/STT, run one spoken question and follow-up, Stop speech, then run another turn;
- complete Google sign-in/consent, discover and select a real calendar, save/reload, and run a label-specific read;
- run a named-project read with the configured local Atlas helper, then turn Atlas Off and confirm the blocked response.

No paid request, live Google request, email send, calendar write, real connection removal, live Atlas request, MCE activation, credential export, or mutation-capable helper action was performed.
