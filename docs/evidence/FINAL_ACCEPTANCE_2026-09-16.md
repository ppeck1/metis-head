# Final acceptance evidence — 2026-09-16

- Source baseline: `97467f832aed067997a8f27cefb0ffd44cc9705f`
- Branch: `codex/metis-completion-2026-09-16`
- Runtime build ID: `97467f832aed+working`
- Interpreter: Python 3.11
- App URL: `http://127.0.0.1:8787/` (loopback)

## Latest automated run

Command:

```powershell
python -m pytest -q
```

Result: `603 passed in 15.94s`

Additional checks:

- `python -m compileall -q metis_head tests` — passed.
- `node --check metis_head\static\setup_wizard.js` — passed.
- `node --check metis_head\static\audio_setup.js` — passed.
- `node tests\node_audio_setup.cjs` — passed.
- `node tests\node_conversation_client.cjs` — passed.
- `git diff --check` — passed; Windows line-ending conversion warnings only.

## Runtime checks

- A stale process on port 8787 was stopped by exact PID and restarted from the current checkout.
- `/metis/build`, `/metis/setup`, and `/metis/startup/readiness` are served by the restarted runtime.
- Ollama health: reachable. Saved Setup selection `mistral-small3.2:24b` is restored by Virtual Chat and voice turns; a live bounded request returned a genuine Ollama answer.
- Setup page: HTTP 200; no-store caching; Connect/Remove UI present; old CLI-only OAuth text absent; bound browser fetch present.
- Real Piper preview: session-owned `play` command, `audio/wav`, 59,948 bytes, RIFF header.
- Local STT: `faster_whisper`, dependency available, model `base.en`, health `ok`. An 86,060-byte Piper phrase returned status `transcribed`, provider `faster_whisper`, and `persisted=false`.
- OAuth start with a fake desktop client produced a Google authorization URL and `client_config_persisted=false`.
- Browser-control bridge: unavailable because its trusted Node helper exited during initialization twice. No headless/cloud browser was substituted.
- Browser microphone capture, faster-whisper transcription, and Piper audio output were confirmed by the operator.
- Google connections: zero; four profile slots are present but live account acceptance is blocked on user sign-in and consent.

No credentials, OAuth material, personal content, recording, model weights, browser profile, or private `.project` data is included in release evidence.
