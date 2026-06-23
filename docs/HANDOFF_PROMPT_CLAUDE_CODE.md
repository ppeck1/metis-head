# Handoff Prompt for Claude Code

Paste the block below into Claude Code running in `B:\dev\metis_head\metis_head`.

---

You are picking up the Metis Head project at `B:\dev\metis_head\metis_head` (the inner folder is the
git repo root). Phases 0BA–0BC are complete: simulated audio-input, real mic capture (triple-gated),
and real faster-whisper STT — all governed and redacted. The active task is Phase **0BD — wake-word /
push-to-talk listen loop**.

**Core design principle (do not violate):** the listen loop is **event-driven and bounded**, never an
always-listening background thread. A capture→STT→route cycle fires only on an explicit push-to-talk
event or a detected wake word, and only one utterance per trigger. Standby must never imply
always-listening (buildspec §3.4). Mic cutoff remains the highest-precedence gate.

**Step 0 — Confirm the environment is operational.** Run:

```
python -m pytest -q
```

(Use `C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe` if `python` isn't 3.11.)
Expected: `361 passed`. If pytest cannot run, STOP and report exactly what failed.

**Step 1 — Read** `ACTIVE_TASK.md` and `docs/PHASE_0BA_AUDIO_INPUT_STT_PLAN.md`. Note `listen_mode`
already exists with values `no_listen` (default) / `wake_word` / `push_to_talk`, and
`/metis/audio/listen` already does one governed capture→STT→route pass.

**Step 2 — Refactor the listen pipeline into a shared helper (no behavior change).**
Extract the capture→transcribe→forward-to-`/metis/voice/command` body of `/metis/audio/listen` into a
single internal function (e.g. `_run_listen_cycle(hint, options)`) that PTT and wake-word will both
call. It must keep using `_audio_capture_governance(require_listen_mode=True)` and the in-memory
`_wav_bytes` handoff. Run the suite; confirm still `361 passed`.

**Step 3 — Push-to-talk (`POST /metis/audio/ptt`).**
- Body `{"action": "press" | "release"}`. Models the radio's PTT button (a `button_event` from the
  bridge can map to these).
- `press`: only when `listen_mode == "push_to_talk"` and the full capture gate passes (mic cutoff →
  `audio_input_enabled` → `power_state == awake`). Set a bounded session marker
  (`listen_session_active=true`, `audio_input_state="capturing"`); emit a redacted `provider_event`.
  Do NOT start a thread.
- `release`: run exactly one `_run_listen_cycle(...)` for the held utterance, then clear the session
  marker. If `press` never happened or gates fail, return a governed blocked result.
- A `release` without an active session, or in the wrong `listen_mode`, is a safe no-op (no capture).

**Step 4 — Wake-word (`POST /metis/audio/wake`).**
- Body supplies a recognized hint/text (simulated detector — no real engine this phase).
- Deterministic detector: a configurable wake phrase (`wake_phrase`, default `"hey metis"`). If the
  supplied text starts with the wake phrase AND `listen_mode == "wake_word"` AND the gate passes, strip
  the wake phrase and run one `_run_listen_cycle(...)` on the remainder. Otherwise return
  `wake_not_detected` with no capture, no route, no STT — emit a redacted `provider_event` only.
- Add a disabled real wake-word scaffold (e.g. `LocalWakeWordDetector` for openWakeWord/Porcupine) that
  imports nothing this phase — same pattern as the STT scaffolds.

**Step 5 — State + status.**
- Add minimal canonical fields: `listen_session_active` (default `false`), `wake_phrase` (default
  `"hey metis"`), `last_listen_trigger` (`"ptt" | "wake" | null`). Defaults safe/off.
- `GET /metis/audio/input`: report `listen_mode`, `listen_session_active`, `wake_phrase`, and the
  available trigger routes.

**Step 6 — Tests (CI green, no hardware, no engine).**
- PTT happy path: set `listen_mode=push_to_talk`, enable, `press` then `release` → one `git status`
  routed via the governed path → `git.status` proposal queued, NOT executed.
- PTT `release` without `press`, and PTT while `listen_mode != push_to_talk` → safe no-op, no capture.
- Wake happy path: `listen_mode=wake_word`, text `"hey metis git status"` → routes `git status`.
- Wake negative: text without the wake phrase, or wrong `listen_mode` → `wake_not_detected`, no capture,
  no proposal, no STT.
- Mic cutoff and `no_listen` block both PTT and wake before any capture.
- Assert there is no background thread and no capture without an explicit trigger.
- Assert no raw audio / `_wav_bytes` / transcript text appears in state, event log, or responses.
- No new `external_action_executed`; no new tool lane or execution authority.
- Run the full suite; report the new count (361 + new).

**Step 7 — Docs + commit.** Update `README.md` (phase 0BD, PTT/wake routes, event-driven-not-always-on
note) and `ACTIVE_TASK.md` (mark 0BD done; next `0BE` — voice-only approval confirmation wiring real
audio→STT into the existing `/metis/voice/confirm`, with readback + explicit-phrase gating). Commit and
report the commit hash + final test count.

**Hard boundaries:** event-driven and bounded — one utterance per explicit trigger, never an
always-listening thread; mic cutoff is highest precedence; standby is not always-listening; recognized
text stays redacted and enters only `POST /metis/voice/command`; no new execution authority.

---
