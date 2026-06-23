# Local Mic Smoke Test (Phase 0BB)

Manual verification that `LocalMicAudioInput` captures real audio on your machine.
This requires a working microphone and `pip install -e ".[mic]"`.

**CI does not run this.** The automated test suite runs with no real microphone and
no `METIS_AUDIO_ALLOW_LOCAL_MIC` env var; all tests pass in that configuration.

---

## Prerequisites

```powershell
# Install the mic optional extra
pip install -e ".[mic]"

# Confirm sounddevice installed
python -c "import sounddevice; print(sounddevice.__version__)"
```

---

## Run the dev server

```powershell
$env:METIS_AUDIO_ALLOW_LOCAL_MIC = "true"
uvicorn metis_head.brain:app --reload
```

---

## Enable audio capture in state

```powershell
# Enable the audio_input software gate
Invoke-RestMethod -Method POST http://localhost:8000/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"audio_input","state":"on"}'

# Set listen mode to push_to_talk
Invoke-RestMethod -Method POST http://localhost:8000/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"push_to_talk"}'
```

---

## Check status (should show input devices)

```powershell
Invoke-RestMethod http://localhost:8000/metis/audio/input | ConvertTo-Json -Depth 4
```

**Expected healthy result:**
```json
{
  "allow_local_mic": true,
  "sounddevice_available": true,
  "input_devices": [
    { "index": 0, "name": "Microphone (Realtek ...)" }
  ],
  "selected_audio_provider": "local_mic",
  "audio_input_state": "idle",
  "audio_input_enabled": true,
  "listen_mode": "push_to_talk",
  "mic_hardware_enabled": true,
  "audio_provider_health": { "status": "ok", "allow_local_mic": true, ... }
}
```

---

## Trigger a capture (1 second of audio)

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/metis/audio/input/capture `
  -ContentType "application/json" `
  -Body '{"provider":"local_mic","duration_ms":1000}'
```

**Expected:**
```json
{
  "status": "captured",
  "capture": {
    "provider_id": "local_mic",
    "status": "ok",
    "captured": true,
    "audio_duration_ms": 1000,
    "audio_levels": [...],
    "frame_count": 16
  }
}
```

---

## Orchestrated listen (capture → STT → governed voice command)

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/metis/audio/listen `
  -ContentType "application/json" `
  -Body '{"provider":"local_mic","stt_provider":"simulated","hint":"git_status","duration_ms":1000}'
```

**Expected:** `status == "listen_complete"`, `stt.text_redacted == true`, and a
`git.status` proposal queued in `state.approval_queue`. The recognized text is not
present anywhere in the response.

> **Note:** `stt_provider` is still `simulated` in Phase 0BB — real STT (Whisper/Vosk)
> arrives in Phase 0BC. The `hint` parameter selects what the simulated STT returns.

---

## Privacy reminder

- `mic_hardware_enabled` must be `true` (hardware cutoff switch on the radio chassis).
- The software flag `METIS_AUDIO_ALLOW_LOCAL_MIC` is an **interim proxy** — in
  production the hardware cutoff switch will be wired through the bridge to
  `mic_hardware_enabled` in state. Software mute (`output_muted`) is never a privacy
  control.
- Raw PCM and the tempfile WAV are never stored; only compact audio metadata
  (`audio_levels`, `frame_count`, `audio_duration_ms`) enters the redacted
  `CaptureResult`.

---

## Disable and reset

```powershell
# Remove the env flag
Remove-Item Env:\METIS_AUDIO_ALLOW_LOCAL_MIC

# Reset state
Invoke-RestMethod -Method POST http://localhost:8000/metis/state/reset
```
