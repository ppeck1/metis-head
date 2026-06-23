# Voice Conversation Test — Smoke Test Instructions

Covers Phase 0BE: spoken confirmation routing in the audio listen path.

All paths are simulation-first and fail-closed. Real mic and real STT are opt-in via
environment variables and never active by default.

---

## Prerequisites

```powershell
cd B:\dev\metis_head\metis_head
.\scripts\launch_metis.ps1 -PythonExe "C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe" -Port 8787
```

---

## Path 1 — Simulated audio + simulated STT (default; no hardware required)

### 1a. Queue a proposal then confirm it by spoken phrase

```powershell
# 1. Enable audio input
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"audio_input","state":"on"}'

# 2. Set push-to-talk mode
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"push_to_talk"}'

# 3. Queue a proposal (spoken "git status" via PTT)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"release","hint":"git status"}'
$proposalId = $r.state.approval_queue[0].proposal_id
Write-Host "Queued: $proposalId"

# 4. Confirm via PTT — hint is the exact spoken text (SimulatedSTT returns it verbatim)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" `
  -Body (ConvertTo-Json @{action="release"; hint="confirm approve $proposalId"})

# Expected results:
Write-Host "status:              $($c.status)"          # listen_complete
Write-Host "route_used:          $($c.route_used)"       # voice_confirm
Write-Host "confirmation_accept: $($c.voice_command.voice_confirmation.confirmation_accepted)"  # True
Write-Host "execution_allowed:   $($c.voice_command.voice_confirmation.execution_allowed)"      # False
```

### 1b. Verify readback is required when proposal ID is omitted

```powershell
# Queue another proposal
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"release","hint":"git status"}'

# Confirm without explicit ID
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
$rb = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"release","hint":"confirm approve"}'

Write-Host "status:     $($rb.voice_command.status)"                                  # readback_required
Write-Host "explicit_id: $($rb.voice_command.voice_confirmation.requires_explicit_proposal_id)" # True
```

### 1c. Verify mic cutoff blocks before confirmation

```powershell
# Queue a proposal
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
$rq = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"release","hint":"git status"}'
$pid2 = $rq.state.approval_queue[-1].proposal_id

# Press PTT, then cut mic, then release — must be blocked
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"hardware_privacy","device":"mic","state":"off"}'
$blk = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" `
  -Body (ConvertTo-Json @{action="release"; hint="confirm approve $pid2"})

Write-Host "status:       $($blk.status)"       # blocked
Write-Host "block_reason: $($blk.block_reason)"  # mic_hardware_cutoff

# Restore mic
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"hardware_privacy","device":"mic","enabled":$true}'
```

### 1d. Wake-word path with confirmation

```powershell
# Set wake-word mode
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"wake_word"}'

# Queue a proposal
$wq = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/wake `
  -ContentType "application/json" -Body '{"text":"hey metis git status"}'
$wpid = $wq.state.approval_queue[-1].proposal_id
Write-Host "Queued via wake: $wpid"

# Confirm via wake phrase — the text after "hey metis " is the recognized utterance
$wc = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/wake `
  -ContentType "application/json" `
  -Body (ConvertTo-Json @{text="hey metis confirm approve $wpid"})

Write-Host "route_used: $($wc.route_used)"  # voice_confirm
Write-Host "confirmed:  $($wc.voice_command.voice_confirmation.confirmation_accepted)"  # True
```

---

## Path 2 — Real local mic + faster-whisper STT

> Requires `sounddevice` and `faster-whisper` installed and a working microphone.

```powershell
# Set environment variables before launching
$env:METIS_AUDIO_ALLOW_LOCAL_MIC = "true"
$env:METIS_STT_ALLOW_LOCAL = "true"
$env:METIS_STT_ENGINE = "faster_whisper"
$env:METIS_STT_MODEL = "small"

.\scripts\launch_metis.ps1 -PythonExe "C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe" -Port 8787
```

With the server running, use the **Voice Conversation Test** panel in the dashboard
(`http://127.0.0.1:8787/static/dashboard.html`):

1. Tick **Audio Input** and **Mic Hardware** checkboxes.
2. Select `local_mic` / `faster_whisper` from the provider dropdowns.
3. Set **Listen Mode** to `push_to_talk`.
4. Click **Listen Once** and say "git status" — a proposal should appear in the queue.
5. Note the `proposal_id` from the result panel.
6. Type `confirm approve <proposal_id>` in the **Hint/fixture** field.
7. Click **PTT Press**, then **PTT Release** — the result should show `route_used: voice_confirm`
   and `confirmation_accepted: true`.

Alternatively via PowerShell, same steps as Path 1 but omit the `hint` field — the server
will capture real microphone audio instead.

---

## Path 3 — Piper voice output

> Requires Piper TTS configured (`PIPER_EXECUTABLE`, `PIPER_MODEL`).

When voice output is enabled in the **Virtual Chat** section of the dashboard, spoken
confirmations trigger Piper TTS for the readback prompt. The readback text says:

```
Proposal <id> for <tool> is pending review. Say 'confirm approve <id>', ...
```

To hear the readback:

1. Enable Piper voice in the Virtual Chat controls.
2. Queue a proposal via PTT with `hint=git status`.
3. PTT Release with `hint=confirm approve` (no proposal ID) — `readback_required` triggers
   Piper to speak the readback text.
4. PTT Release with `hint=confirm approve <id>` — triggers Piper to speak the confirmation.

---

## Path 4 — Browser held-to-talk (Phase 0BF/0BG)

There are two distinct browser-related paths:

- Dashboard Hold to Talk uses browser `SpeechRecognition` when available, then sends
  recognized text as a simulated STT hint through `POST /metis/audio/ptt`.
- `POST /metis/audio/browser_ptt` is a backend multipart upload route for local
  prototype clients/tests. As of Phase 0BG it enforces upload size, content-type,
  empty-payload, and WAV-header guardrails.

The dashboard does not upload raw browser-recorded audio to faster-whisper.

### 4a. Browser dashboard — Hold to Talk button

1. Launch the server (see Prerequisites).
2. Open `http://127.0.0.1:8787/` in a browser.
3. In the **Voice Conversation Test** panel:
   - Tick **Audio Input** and confirm **Mic Hardware** is ticked.
   - Set **Listen Mode** to `push_to_talk`.
4. Click and hold **Hold to Talk** — browser speech recognition starts when available.
5. Speak your command, then release the button — recognized text is sent as a
   simulated STT hint through `/metis/audio/ptt` and the result appears below.

Expected: `status: listen_complete`, `route_used: voice_command` for a plain command.

### 4b. Backend browser_ptt — simulated path (no microphone required)

Use the `stt_hint` field to inject text without a real mic:

```powershell
# Enable audio + push-to-talk mode
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"audio_input","state":"on"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"push_to_talk"}'

# Upload a minimal WAV-shaped payload; stt_hint drives SimulatedSTT
$bytes = [byte[]](82,73,70,70,36,0,0,0,87,65,86,69,102,109,116,32,16,0,0,0,1,0,1,0,128,62,0,0,0,125,0,0,2,0,16,0,100,97,116,97,0,0,0,0)
$boundary = "----BoundaryXYZ"
$body = "--$boundary`r`nContent-Disposition: form-data; name=`"audio`"; filename=`"ptt.wav`"`r`nContent-Type: audio/wav`r`n`r`n" + [System.Text.Encoding]::UTF8.GetString($bytes) + "`r`n--$boundary`r`nContent-Disposition: form-data; name=`"stt_provider`"`r`n`r`nsimulated`r`n--$boundary`r`nContent-Disposition: form-data; name=`"stt_hint`"`r`n`r`ngit status`r`n--$boundary--"
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/browser_ptt `
  -ContentType "multipart/form-data; boundary=$boundary" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

Expected: `status: listen_complete`, `route_used: voice_command`.

### 4c. Backend browser_ptt — confirmation phrase via simulated path

```powershell
# Queue a proposal first
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"press"}'
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/ptt `
  -ContentType "application/json" -Body '{"action":"release","hint":"git status"}'
$proposalId = $r.state.approval_queue[-1].proposal_id
Write-Host "Queued: $proposalId"

# Upload browser PTT with confirmation phrase as stt_hint
$hint = "confirm approve $proposalId"
$bytes = [byte[]](82,73,70,70,36,0,0,0,87,65,86,69,102,109,116,32,16,0,0,0,1,0,1,0,128,62,0,0,0,125,0,0,2,0,16,0,100,97,116,97,0,0,0,0)
$boundary = "----BoundaryXYZ"
$body = "--$boundary`r`nContent-Disposition: form-data; name=`"audio`"; filename=`"ptt.wav`"`r`nContent-Type: audio/wav`r`n`r`n" + [System.Text.Encoding]::UTF8.GetString($bytes) + "`r`n--$boundary`r`nContent-Disposition: form-data; name=`"stt_provider`"`r`n`r`nsimulated`r`n--$boundary`r`nContent-Disposition: form-data; name=`"stt_hint`"`r`n`r`n$hint`r`n--$boundary--"
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/audio/browser_ptt `
  -ContentType "multipart/form-data; boundary=$boundary" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))

Write-Host "route_used:          $($c.route_used)"        # voice_confirm
Write-Host "confirmation_accept: $($c.voice_command.voice_confirmation.confirmation_accepted)"  # True
Write-Host "execution_allowed:   $($c.voice_command.voice_confirmation.execution_allowed)"      # False
```

### 4d. Governance blocks

```powershell
# Block: wrong listen_mode
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"button_event","button":"listen_mode","state":"no_listen"}'
# Same upload → expected: status=wrong_mode, block_reason=listen_mode_not_push_to_talk

# Block: mic hardware off
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/metis/event `
  -ContentType "application/json" `
  -Body '{"type":"hardware_privacy","device":"mic","state":"off"}'
# Set mode back to push_to_talk, then upload → expected: status=blocked, block_reason=mic_hardware_cutoff
```

---

## Governance invariants (verified by tests)

| Invariant | Check |
|---|---|
| `execution_allowed` is always `false` | `voice_command.voice_confirmation.execution_allowed == false` |
| `standing_approval` is never granted | `voice_command.voice_confirmation.standing_approval == false` |
| Mic cutoff blocks before any mutation | Response `status == "blocked"`, proposal `review_status == "pending"` |
| Raw transcript not in event log | `audio_input` events contain only `text_len`/`text_hash`/`text_redacted` |
| No background listener | Server starts and completes; no thread leaks |
