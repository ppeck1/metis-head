# Completion Release Acceptance

Use one Python interpreter for setup, tests, OAuth, readiness, and launch. The examples below use the installed Python 3.11 interpreter on this workstation.

## Install

```powershell
cd B:\dev\metis_head\metis_head
C:\Users\peckm\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test,google,mcp,voice,stt-whisper]"
node --version
.\.venv\Scripts\python.exe -m pytest -q
```

Node is required for the executable browser-module tests. `.[test]` alone does not install faster-whisper, Piper, Google clients, or their models. Model weights and OAuth files stay outside source control.

## Configure local conversation and speech

```powershell
$env:METIS_LLM_PROVIDER="ollama"
$env:METIS_OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:METIS_OLLAMA_MODEL="<installed-tool-capable-model>"
$env:METIS_STT_ENGINE="faster_whisper"
$env:METIS_STT_ALLOW_LOCAL="true"
$env:METIS_STT_MODEL="small"                 # or an absolute offline model directory
$env:METIS_STT_MODEL_DIR="<optional-model-cache>"
$env:METIS_VOICE_ENABLED="true"
$env:METIS_VOICE_PROVIDER="piper"
$env:METIS_VOICE_ALLOW_PIPER="true"
$env:METIS_PIPER_EXE="<path-to-piper.exe>"
$env:METIS_PIPER_MODEL="<path-to-voice.onnx>"
$env:METIS_PIPER_CONFIG="<path-to-voice.onnx.json>"
$env:METIS_PIPER_PLAYBACK="false"            # browser owns normal playback
```

## Connect Google and select calendars

Create a Google desktop OAuth client, enable Calendar, Gmail, and People APIs, and keep the client JSON private.

```powershell
.\.venv\Scripts\python.exe -m metis_head.google_oauth --client-secrets "<private-client-json>"
```

Tokens are stored only in the OS credential store. Non-secret metadata defaults to `%LOCALAPPDATA%\MetisHead\connections.json`; override the directory with `METIS_STATE_DIR` or the exact file with `METIS_CONNECTIONS_FILE`. In the dashboard, choose the connected account, discover calendars, select the allowed calendars, set timezone/project, and click **Save Personal Context**. Disconnect through `DELETE /metis/connectors/google/accounts/{account_id}` or revoke access in the Google account.

## Configure private read-only MCP helpers

Set `METIS_MCP_ENABLED=true`, the BOH/Atlas service gate, command, JSON args, optional cwd, and private child-env JSON. Use only sanitized helper templates in `docs/LOCAL_HELPER_TEMPLATES.md`; keep real paths/tokens under ignored local configuration.

## Verify and launch

```powershell
.\.venv\Scripts\python.exe -m metis_head.startup_readiness
.\scripts\launch_metis.ps1 -PythonExe ".\.venv\Scripts\python.exe" -Port 8787
```

Open `http://127.0.0.1:8787/`. The launcher binds loopback by default.

## Target-machine acceptance

1. Confirm readiness accurately reports Ollama, faster-whisper, Piper, Google metadata, and MCP gates.
2. Complete ten typed/voice turns; verify private tab history and useful follow-ups.
3. Ask about a selected calendar and then “What about Friday?”; verify timezone/date. Read a Gmail result and resolve an unambiguous contact.
4. Ask for a named Atlas project; verify stable identity, source, observation time, and honest freshness. Verify BOH grounding appears only when evidence reaches the model.
5. Stop during capture, STT, model/tool work, synthesis, delayed delivery, and audible playback. No cancelled work may restart; the next turn must work.
6. Exercise mic-off, mute, standby, browser play rejection, two tabs, tab closure, Google disconnect/reconnect, and application restart.
7. Record end-of-speech to first-audio, interruption delay, representative memory, and actual/estimated usage.

OpenAI is not an acceptance lane in this candidate: production dispatch is intentionally disabled. Do not set an API key expecting cloud chat, and do not claim cloud completion.

## Rollback

Review the branch diff and revert only completion-release commits/files. Do not reset or clean the working tree because it contains preserved earlier work. Revoking Google access and deleting the OS credential removes secrets; deleting the non-secret state files intentionally discards selections/accounting history.
