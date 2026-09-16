# Local Atlas / BOH helper templates

This file documents the private workstation boundary without copying workstation paths,
database names, tokens, credentials, or helper implementations into the repository or export.

## Local environment template

Create `.project/local_mcp_env.ps1` locally when needed. The directory and file are ignored.

```powershell
$env:METIS_MCP_ENABLED = "true"

$env:METIS_MCP_BOH_ENABLED = "true"
$env:METIS_MCP_BOH_COMMAND = "<python-or-mcp-runner>"
$env:METIS_MCP_BOH_ARGS_JSON = '["<module-or-script>"]'
$env:METIS_MCP_BOH_CWD = "<boh-repository-root>"
$env:METIS_MCP_BOH_ENV_JSON = '{"<NONSECRET_OR_SECRET_NAME>":"<value-supplied-locally>"}'

$env:METIS_MCP_ATLAS_ENABLED = "true"
$env:METIS_MCP_ATLAS_COMMAND = "<atlas-mcp-runner>"
$env:METIS_MCP_ATLAS_ARGS_JSON = '["<module-or-script>"]'
$env:METIS_MCP_ATLAS_CWD = "<atlas-repository-root>"
$env:METIS_MCP_ATLAS_ENV_JSON = '{"<LOCAL_DATA_NAME>":"<value-supplied-locally>"}'
```

Never place real values from that file in source control, logs, screenshots, or exports.

## BOH read helper contract

The configured stdio MCP server must implement only the BOH read tools allowlisted in
`metis_head/mcp_access.py`. It should return bounded result objects with stable source identifiers,
source links where available, and observation/freshness metadata. It must not accept an operator
mutation token, promote content, or expose its command line, working directory, environment, or
database path in results.

## Atlas read helper contract

The configured stdio MCP server must implement only the Atlas read tools allowlisted in
`metis_head/mcp_access.py`. Named-project status reads must first resolve a stable project identity,
then fetch status for that identity. Results should include stable source identity, observation time,
and freshness. MCP `isError: true` responses are failures and must never be rendered as successful
project data. Apply, delete, push, and other mutations remain unavailable.

## Operational checks

1. Keep all helper code and configuration below ignored `.project/` paths or in the owning project.
2. Confirm `/metis/mcp/status` reports configured/usable without revealing private values.
3. Exercise an allowlisted read and an unavailable/error case.
4. Confirm returned and persisted metadata contain no credentials, local absolute paths, or raw child environment values.
5. Re-run `python -m pytest -q` after changing a helper contract.
