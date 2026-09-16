# Variable Matrix

Secret policy: names only. Secret values must never be recorded.

## Capsule Audit

| Field | Value |
|---|---|
| Project ID | metis-head |
| Visibility | public |
| Profiles | public_repo, software_project |
| Primary variable map | docs/project_variable_map.md |
| Last capsule audit | 2026-09-16 |

## Required Public Safety Rules

| Name | Type | Location | Default | Required | Secret | Used By | Notes | Last Verified |
|---|---|---|---|---|---|---|---|---|
| OPENAI_API_KEY | environment variable | README.md, docs/project_variable_map.md | none | only when METIS_LLM_PROVIDER=openai | yes | OpenAI chat provider | Name may be documented; value must never be committed. | 2026-06-30T17:33:26-04:00 |
| METIS_BOH_RETRIEVAL_TOKEN | environment variable | README.md, docs/project_variable_map.md | none | only when BOH retrieval is enabled | yes | read-only BOH retrieval bridge | Read-only retrieval token only; never BOH operator token. | 2026-06-30T17:33:26-04:00 |
| METIS_MCP_ENABLED | environment variable | README.md, docs/project_variable_map.md, scripts/launch_metis.ps1 | launch default true | no | no | MCP access bridge | Global enable flag for configured MCP access. Local launcher defaults it to true when unset; direct process default still fails closed when absent. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_TIMEOUT_SECONDS | environment variable | README.md, docs/project_variable_map.md | 8 | no | no | MCP access bridge | Timeout clamp for stdio MCP responses. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_BOH_ENABLED | environment variable | README.md, docs/project_variable_map.md, scripts/launch_metis.ps1 | launch default true | no | no | BOH MCP access bridge | Per-server enable flag for BOH MCP. Local launcher defaults it to true when unset; command/cwd/token config remains private and unset. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_BOH_COMMAND | environment variable | README.md, docs/project_variable_map.md | none | only when BOH MCP is enabled | no | BOH MCP access bridge | May contain private local command path; public docs use placeholders only. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_BOH_ARGS_JSON | environment variable | README.md, docs/project_variable_map.md | [] | only when BOH MCP command needs args | no | BOH MCP access bridge | JSON string array of stdio server args. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_BOH_CWD | environment variable | README.md, docs/project_variable_map.md | none | only when BOH MCP command needs cwd | no | BOH MCP access bridge | May contain private local repo path; value must not be committed. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_BOH_ENV_JSON | environment variable | README.md, docs/project_variable_map.md | {} | only when BOH MCP child env is needed | yes | BOH MCP access bridge | Child environment JSON may carry secret/path values; names only in repo docs. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_ATLAS_ENABLED | environment variable | README.md, docs/project_variable_map.md, scripts/launch_metis.ps1 | launch default true | no | no | Project Atlas MCP access bridge | Per-server enable flag for Project Atlas MCP. Local launcher defaults it to true when unset; command/cwd/token config remains private and unset. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_ATLAS_COMMAND | environment variable | README.md, docs/project_variable_map.md | none | only when Atlas MCP is enabled | no | Project Atlas MCP access bridge | May contain private local command path; public docs use placeholders only. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_ATLAS_ARGS_JSON | environment variable | README.md, docs/project_variable_map.md | [] | only when Atlas MCP command needs args | no | Project Atlas MCP access bridge | JSON string array of stdio server args. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_ATLAS_CWD | environment variable | README.md, docs/project_variable_map.md | none | only when Atlas MCP command needs cwd | no | Project Atlas MCP access bridge | May contain private local repo path; value must not be committed. | 2026-06-30T18:42:31-04:00 |
| METIS_MCP_ATLAS_ENV_JSON | environment variable | README.md, docs/project_variable_map.md | {} | only when Atlas MCP child env is needed | yes | Project Atlas MCP access bridge | Child environment JSON may carry secret/path values; names only in repo docs. | 2026-06-30T18:42:31-04:00 |
| .project/runs/ | local evidence path | .gitignore | ignored | yes for capsule runs | no | Project Ops Capsule | Raw run ledgers are local-only for this public repo. | 2026-06-30T17:33:26-04:00 |
| .project/atlas_outbox/ | local evidence path | .gitignore | ignored | yes for outbox sync | no | Project Ops Capsule / Project Atlas | Raw Atlas event packets are queued locally and not committed. | 2026-06-30T17:33:26-04:00 |
| .project/boh_outbox/ | local evidence path | .gitignore | ignored | yes when BOH sync is enabled | no | Project Ops Capsule / BOH | Raw BOH packets are evidence-only and not committed. | 2026-06-30T17:33:26-04:00 |
| .project/local_mcp_env.ps1 | local ignored config | .gitignore, scripts/launch_metis.ps1 | absent | only for local MCP use | yes | MCP access bridge | Workstation-only MCP command/env config; must not be committed. | 2026-07-01T18:30:00-04:00 |
| .project/local_mcp/ | local ignored shims | .gitignore | absent | only for local MCP use | yes | MCP access bridge | Workstation-only read shims such as the temporary Atlas stdio shim; must not be committed. | 2026-07-01T18:30:00-04:00 |

## Project Variable Map Status

The detailed project variable map remains docs/project_variable_map.md. This capsule matrix audits the public/private boundary and points operators to the canonical Metis variable map rather than duplicating the full phase matrix.

## Phase 0BM Runtime Notes

| Name | Type | Location | Default | Required | Secret | Used By | Notes | Last Verified |
|---|---|---|---|---|---|---|---|---|
| MCP_CHAT_BRIDGE_VERSION | code constant | metis_head/mcp_chat_bridge.py | metis_mcp_chat_bridge.v0.1 | yes | no | Virtual Chat MCP read bridge | Explicit MCP read routing schema. Stores status/hash/timing metadata only; raw MCP payloads and private config values are not persisted as metadata. | 2026-07-01T19:30:00-04:00 |
| MCP chat read cache | in-process cache | metis_head/mcp_chat_bridge.py | 10 second TTL, 16 entries | no | no | Virtual Chat MCP read bridge | Caches only successful read_only_complete results keyed by server/tool/args/config fingerprint; not a standing approval or write cache. | 2026-07-01T19:30:00-04:00 |

## Completion Release Settings

| Name | Purpose | Default | Secret | Scope | Restart required |
|---|---|---|---|---|---|
| METIS_STATE_DIR | Per-user writable state directory | `%LOCALAPPDATA%\MetisHead` on Windows; XDG/local-state equivalent elsewhere | no | host | yes |
| METIS_CONNECTIONS_FILE | Exact non-secret connection metadata file override | `<METIS_STATE_DIR>\connections.json` | no | host | yes |
| METIS_USAGE_FILE | Exact durable paid-usage ledger override | `<METIS_STATE_DIR>\usage.json` | no | host | yes |
| METIS_SETUP_FILE | Exact non-secret setup wizard state file override | `<METIS_STATE_DIR>\setup.json` | no | host | yes |
| METIS_BUILD_ID | Optional sanitized build identifier override | derived from local Git revision | no | process | yes |
| METIS_GOOGLE_CLIENT_SECRETS | Path to Google desktop OAuth client JSON used during one-time setup | unset | yes | setup process | no |
| METIS_PAID_BUDGET_USD | Application ceiling for paid-provider reservations | unset; paid calls blocked | no | host | yes |
| METIS_LLM_PROVIDER | Chat provider selector; explicit environment override takes precedence over saved Setup state | saved configured Ollama provider when present, otherwise mock | no | process/user setup | environment: yes; setup: no |
| METIS_OLLAMA_BASE_URL | Local Ollama base URL; loopback HTTP only for the tool adapter | `http://127.0.0.1:11434` | no | host | yes |
| METIS_OLLAMA_MODEL | Ollama model used by ordinary chat/tool orchestration; environment override takes precedence over saved Setup state | saved Setup model or unset | no | process/user setup | environment: yes; setup: no |
| METIS_OLLAMA_TIMEOUT_SECONDS | Bounded local Ollama request and orchestration timeout, clamped to 10-600 seconds | 120 | no | process | yes |
| METIS_OPENAI_MODEL | Paid OpenAI model identifier | `gpt-4o-mini` | no | process | yes |
| OPENAI_API_KEY | OpenAI credential; never stored in repository or exports | unset | yes | process | yes |
| METIS_STT_ALLOW_LOCAL | Enables local faster-whisper execution | direct process: false; tracked launcher: true | no | process | yes |
| METIS_STT_ENGINE | Selected STT adapter | direct process: simulated; tracked launcher: faster_whisper | no | process | yes |
| METIS_STT_MODEL | Warmed faster-whisper model name | direct process: small; tracked launcher: base.en | no | process | yes |
| METIS_STT_MODEL_DIR | Optional local model/download directory | unset | no | host | yes |
| METIS_AUDIO_ALLOW_LOCAL_MIC | Enables optional server-host microphone adapter; browser held-to-talk does not require it | false | no | process | yes |
| METIS_VOICE_ENABLED | Enables automatic voice output | false | no | process | yes |
| METIS_VOICE_PROVIDER | Voice provider selector (`mock`, `system`, `piper`) | mock | no | process/request | yes |
| METIS_VOICE_ID | Voice profile identifier | `metis-counsel-mock` | no | process/request | yes |
| METIS_VOICE_RATE | Speech-rate metadata, clamped by voice configuration | 1.0 | no | process/request | yes |
| METIS_VOICE_VOLUME | Voice volume | state volume or 0.6 | no | process/request | yes |
| METIS_VOICE_ALLOW_SYSTEM_TTS | Explicit Windows system-TTS gate | false | no | process | yes |
| METIS_VOICE_ALLOW_PIPER | Enables local Piper synthesis | false | no | process | yes |
| METIS_PIPER_EXE | Piper executable path | auto-detect | no | host | yes |
| METIS_PIPER_MODEL | Piper voice model path | auto-detect bundled path | no | host | yes |
| METIS_PIPER_CONFIG | Optional matching Piper voice configuration path | auto-detect bundled path | no | host | yes |
| METIS_PIPER_PLAYBACK | Legacy backend-speaker playback; browser delivery does not require it | false | no | process | yes |
| METIS_PIPER_PLAYBACK_STRATEGY | Legacy Windows backend playback implementation (`soundplayer` or `winsound`) | soundplayer | no | process | yes |
| METIS_PIPER_PLAYBACK_MODE | Legacy backend playback mode (`async` or `sync`) | async | no | process | yes |
| METIS_VOICE_NORMALIZE_TEXT | Normalizes display Markdown before TTS | true | no | process | yes |
