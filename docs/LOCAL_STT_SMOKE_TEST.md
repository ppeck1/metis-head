# Local STT Smoke Test (Phase 0BC)

Manual verification that `LocalFasterWhisperSTT` transcribes real audio on your machine.
This requires a working microphone, `pip install -e ".[mic,stt-whisper]"`, and both
env flags set.

**CI does not run this.** The automated test suite runs with no real mic, no model, and
no env vars; all 361 tests pass in that configuration.

---

## Prerequisites

```powershell
# Install both optional extras
pip install -e ".[mic,stt-whisper]"

# Confirm packages
python -c "import sounddevice; print('sounddevice:', sounddevice.__version__)"
python -c "import faster_whisper; print('faster_whisper:', faster_whisper.__version__)"
```

---

## Run the dev server

```powershell
$env:METIS_AUDIO_ALLOW_LOCAL_MIC = "true"
$env:METIS_STT_ALLOW_LOCAL       = "true"
$env:METIS_STT_ENGINE            = "faster_whisper"
$env:METIS_STT_MODEL             = "small"   # tiny/base/small/medium/large
uvicorn metis_head.brain:app --reload
```

> **Model download**: The first run downloads the selected Whisper model to the
> HuggingFace cache (~`%USERPROFILE%\.cache\huggingface`). For offline use set
> `METIS_STT_MODEL_DIR` to a directory where the model is already present.

---

## Enable state gates

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"audio_input","state":"on"}'

Invoke-RestMethod -Method POST http://localhost:8000/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"push_to_talk"}'
```

---

## Check status (should show STT fields)

```powershell
Invoke-RestMethod http://localhost:8000/metis/audio/input | ConvertTo-Json -Depth 4
```

**Expected:**
```json
{
  "stt_engine": "faster_whisper",
  "stt_allow_local": true,
  "faster_whisper_available": true,
  "stt_model": "small",
  "selected_stt_provider": "faster_whisper",
  "allow_local_mic": true,
  "sounddevice_available": true,
  "audio_input_enabled": true,
  "listen_mode": "push_to_talk"
}
```

---

## Orchestrated listen (capture → STT → governed voice command)

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/metis/audio/listen `
  -ContentType "application/json" `
  -Body '{"provider":"local_mic","duration_ms":3000}'
```

Speak a command (e.g., "git status") during the 3-second capture window.

**Expected:** `status == "listen_complete"`, `stt.provider_id == "faster_whisper"`,
`stt.text_redacted == true`, `stt.text_len > 0`, and a proposal queued in
`state.approval_queue` for the recognized intent. The raw transcript is not
present anywhere in the response.

---

## Offline model use (no network)

```powershell
# Download model to a local directory first:
python -c "
from faster_whisper import WhisperModel
m = WhisperModel('small', device='cpu', compute_type='int8', download_root='C:/models/whisper')
print('model downloaded')
"

# Then set the dir and relaunch:
$env:METIS_STT_MODEL_DIR = "C:/models/whisper"
$env:METIS_STT_MODEL     = "small"
uvicorn metis_head.brain:app --reload
```

---

## Privacy reminder

- `mic_hardware_enabled` must be `true` (hardware cutoff switch on the radio chassis).
- `METIS_AUDIO_ALLOW_LOCAL_MIC` and `METIS_STT_ALLOW_LOCAL` are **interim software proxies** —
  in production both should be driven by the physical cutoff switch over the bridge.
- In-memory WAV bytes (`_wav_bytes`) and recognized text (`_recognized_text`) are
  **never written to state, the event log, or any response payload**. They are consumed
  within the single `/metis/audio/listen` request and discarded.
- Recognized text enters only `POST /metis/voice/command`; it is immediately redacted
  to `text_len`/`text_hash` in state and events.

---

## Disable and reset

```powershell
Remove-Item Env:\METIS_AUDIO_ALLOW_LOCAL_MIC
Remove-Item Env:\METIS_STT_ALLOW_LOCAL
Remove-Item Env:\METIS_STT_ENGINE
Invoke-RestMethod -Method POST http://localhost:8000/metis/state/reset
```
