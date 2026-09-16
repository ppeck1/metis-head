# Current Handoff — setup, browser audio, and labeled connections

Source baseline is commit `97467f832aed067997a8f27cefb0ffd44cc9705f` on `codex/metis-completion-2026-09-16`, with the current working changes identified in the UI as `97467f832aed+working`.

## Implemented

- `/setup` is a permanent resumable page. Speaker tone, owned Piper preview, microphone level/capture, local transcription, Google connections, and provider checks are separate and retryable.
- Voice preview now requires a browser session and uses the same artifact ownership, playback queue, acknowledgements, Stop, and cancellation lifecycle as conversational speech. The former preview path synthesized a WAV but never queued it for the browser.
- The speaker test is a user-clicked Web Audio tone independent of LLM, Google, STT, Piper, and backend audio. Software completion and the user's audibility confirmation remain separate.
- Browser calls bind native `window.fetch`, fixing the former `Illegal invocation` preview failure. Static setup/dashboard responses use no-store caching and versioned script URLs.
- Autoplay rejection retains the owned command and exposes **Play blocked audio**; acknowledgements are sent only after a successful retry.
- The microphone setup check supplies capture authorization, displays input level, and calls `/metis/setup/audio/transcribe`; audio/text are transient and no LLM is invoked.
- **Connect Google account** accepts a Desktop OAuth client JSON in memory, opens Google consent, verifies identity, and stores tokens only in Windows Credential Manager. Only real connections render and each has a Remove button.
- Google labels route exact account/calendar authorization. Multiple labels plus an unclear request authorize no account and instruct the model to ask rather than guess. The dashboard account picker and setup checkboxes are removed.
- Provider choices are truthful: Ollama is selectable; ordinary OpenAI API and Codex App Server are visible but unavailable because neither production dispatch nor the required least-authority integration is composed.
- `/metis/build` exposes sanitized source attribution. Port 8787 was restarted from this checkout after a stale process was found serving an older route set.

## Verified on this workstation

- Ollama is reachable and the installed `qwen3.5:9b` model is reported available. No model has been selected on Paul's behalf in saved setup.
- Full suite: `601 passed in 15.59s`.
- Real Piper synthesis queued an owned WAV (59,948 bytes, RIFF). A second 86,060-byte Piper phrase was transcribed by local faster-whisper (`base.en`) with `persisted=false`.
- OAuth start with a fake desktop configuration returned a Google authorization URL and `client_config_persisted=false`.
- Physical audibility, live browser microphone capture, Google consent, full browser conversation, and Stop timing remain manual because browser control failed during initialization. Software tests do not imply Paul heard sound.
- Four profile slots exist, but zero Google identities are currently connected. Live four-account acceptance therefore remains blocked on user sign-in/consent.

## Exact next local check

1. Open `http://127.0.0.1:8787/setup` and confirm the build label ends in `+working`.
2. Select an installed Ollama model and run the bounded provider test.
3. Click **Play local tone**, then record **I heard it** or **I did not hear it**.
4. Click **Play real speech preview**. This creates a fresh owned artifact; do not prefetch its one-use URL.
5. Start a microphone sample, speak, stop, and verify the displayed real transcript.
6. Choose a private Desktop OAuth JSON, click **Connect Google account**, complete consent, and assign a label. Repeat or remove connections as needed.
7. Return to Metis, name a label in a Google request, verify an ambiguous new request causes a question, press Stop during speech, then run another turn.

No deployment, remote exposure, paid request, credential export, or write-capable Google/Atlas/BOH operation was added.
