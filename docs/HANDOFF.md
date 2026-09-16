# Current handoff — account-aware local assistant repair

Date: 2026-09-16. Branch: `codex/metis-completion-2026-09-16`. This checkpoint continues from `354b570` and preserves the previously confirmed browser microphone, faster-whisper, Piper, and genuine local Ollama evidence.

## Implemented

- Server-authoritative Google account routing uses exact full labels and unique aliases. Shared words are ambiguous, exclusions never authorize, deliberate combined requests select exactly the named accounts, and disconnected/changed mappings are revoked before dispatch.
- Typed and transcribed requests enter the same account-routing step. An unresolved question is retained privately through clarification; adopting the clarified account clears older account-private history before the original question is answered.
- Google OAuth loopback completion validates callback origin/path, expiring state, denial, code presence, and single use. It exchanges the code through the real Google library without globally relaxing HTTPS validation.
- Setup state schema v2 stores a variable-length collection of stable Google profile records and migrates the old four-slot state. The UI renders arbitrary real connections, supports per-account calendar discovery and selection, preserves an explicitly empty grant, and removes one connection without shifting the others.
- Saved Ollama, Piper voice, and faster-whisper settings are applied in deterministic order. Conversation controls wait for voice catalog and setup initialization; stale catalog responses cannot switch a valid saved voice to mock.
- Suspended browser audio contexts are resumed before capture. Cancel, page exit, and newer attempts invalidate delayed capture/transcription results. Unsupported STT choices are no longer offered in Setup.
- Atlas ordinary tool registration and final transport dispatch both honor Tool Control Center read state. Explicit named-project MCP status/brief questions resolve the exact project and call the named tool rather than returning a five-project diagnostic list.
- Startup readiness reports effective configuration sources separately from verified local execution and operator-confirmed physical output.

## Verification completed

- `python -m pytest -q` — **620 passed in 16.68s** on Windows/Python 3.11.
- `python -m compileall -q metis_head tests` — passed.
- `node tests\node_audio_setup.cjs` — passed.
- `node tests\node_voice_capture.cjs` — passed.
- `node tests\node_setup_connections.cjs` — passed with six dummy connections and independent removal/reload.
- `git diff --check` — passed; only Windows line-ending conversion notices were emitted.
- Focused real-library OAuth tests mock only the exchange/API transport; no live Google request or credential was used.
- Atlas Off and named-project status behavior were verified with fixture transports; no live Atlas helper request was made.

## Live/manual boundary

- Prior evidence records operator-confirmed browser microphone input, faster-whisper transcription, and Piper output. Automated WAV/Node tests are not presented as new physical-audio confirmation.
- Google sign-in/consent, selection of a real calendar, and a real label-specific Gmail/calendar read require the operator's Google account and remain a user action.
- Do not remove a real connection as a test shortcut. The six-connection/removal acceptance is covered with dummy state.
- No paid request, Google write, email send, calendar creation, MCE activation, Atlas mutation, BOH mutation, or GitHub write is part of runtime acceptance.

## Exact remaining operator journey

1. Open `/setup`, confirm the current build identity, and verify the saved Ollama model, Piper voice, and faster-whisper selection survived reload.
2. Run one real spoken question and follow-up, press Stop during speech, and confirm the next turn works.
3. Connect one Google account through the popup, discover calendars, explicitly select one, save, reload, and run one label-specific read. Repeat for additional accounts only as desired.
4. With Atlas read mode and the local helper configured, ask for one named project's status; turn Atlas Off and confirm the same request reports unavailable without transport.

The release/export excludes OAuth client files, tokens, credentials, personal setup state, recordings, virtual environments, local MCP commands/databases, and model weights.
