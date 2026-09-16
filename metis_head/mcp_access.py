from __future__ import annotations

import os
from copy import deepcopy
from hashlib import sha1
from typing import Any, Callable

from .connectors.mcp_contracts import normalize_mcp_read_result

MCP_ACCESS_VERSION = 'metis_mcp_access.v0.1'
MCP_ARGUMENT_REDACTION = '***'
SENSITIVE_MARKERS = ('token', 'password', 'secret', 'credential', 'authorization', 'api_key')

class MCPAccessError(ValueError):
    pass

Transport = Callable[[str, str, dict[str, Any]], Any]

READ_ONLY_TOOLS: dict[str, tuple[str, ...]] = {
    'boh': (
        'search_boh',
        'retrieve_context',
        'get_document',
        'get_current_state',
        'assemble_context_pack',
        'build_governed_handoff',
        'classify_failure',
    ),
    'project_atlas': (
        'list_projects',
        'get_project_status',
        'get_project_brief',
        'get_project_summary',
        'get_stale_projects',
        'list_agent_proposals',
        'preview_local_refresh',
        'inspect_git_visibility',
        'get_github_remote_status',
        'list_project_enrichment_runs',
        'get_project_enrichment_run',
    ),
}

PROPOSAL_TOOLS: dict[str, tuple[str, ...]] = {
    'boh': (),
    'project_atlas': (
        'refresh_github_remote_status',
        'refresh_project_summaries',
        'run_project_enrichment',
        'propose_status_change',
        'propose_task_update',
        'propose_manifest_update',
        'record_validation_run',
        'record_handoff',
    ),
}

BLOCKED_CAPABILITIES: dict[str, tuple[str, ...]] = {
    'boh': (
        'boh_write_tools',
        'boh_promotion',
        'boh_review_mutation',
        'operator_token_use',
        'arbitrary_shell_execution',
        'arbitrary_filesystem_access',
    ),
    'project_atlas': (
        'atlas_apply_proposal',
        'atlas_delete_project',
        'atlas_github_push',
        'atlas_source_repo_mutation',
        'atlas_unreviewed_record_mutation',
        'arbitrary_shell_execution',
    ),
}

SERVER_ENV_PREFIX = {'boh': 'METIS_MCP_BOH', 'project_atlas': 'METIS_MCP_ATLAS'}
SERVER_DISPLAY_NAME = {'boh': 'BOH MCP Adapter', 'project_atlas': 'Project Atlas MCP Adapter'}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _server_public_config(server_id: str, env: dict[str, str]) -> dict[str, Any]:
    prefix = SERVER_ENV_PREFIX[server_id]
    enabled = _as_bool(env.get('METIS_MCP_ENABLED', 'false')) and _as_bool(env.get(f'{prefix}_ENABLED', 'false'))
    command_configured = bool(env.get(f'{prefix}_COMMAND'))
    return {
        'server_id': server_id,
        'display_name': SERVER_DISPLAY_NAME[server_id],
        'enabled': enabled,
        'command_configured': command_configured,
        'cwd_configured': bool(env.get(f'{prefix}_CWD')),
        'timeout_seconds': _int(env.get('METIS_MCP_TIMEOUT_SECONDS', '8'), 8, 1, 30),
        'transport': 'external_stdio_configured' if command_configured else 'not_configured',
    }


def mcp_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    servers = {}
    for server_id in SERVER_ENV_PREFIX:
        servers[server_id] = {
            **_server_public_config(server_id, env),
            'policy': {
                'read_only_tools': list(READ_ONLY_TOOLS[server_id]),
                'proposal_tools': list(PROPOSAL_TOOLS[server_id]),
                'blocked_capabilities': list(BLOCKED_CAPABILITIES[server_id]),
            },
        }
    return {
        'schema_version': MCP_ACCESS_VERSION,
        'enabled': _as_bool(env.get('METIS_MCP_ENABLED', 'false')),
        'servers': servers,
        'execution_allowed': False,
        'boundary': 'Metis may call only configured, allowlisted MCP read tools; Atlas proposal tools are classified but not invoked in this phase.',
    }


def list_mcp_tools() -> dict[str, Any]:
    tools = []
    for server_id in SERVER_ENV_PREFIX:
        for tool_name in READ_ONLY_TOOLS[server_id]:
            tools.append({
                'server_id': server_id,
                'tool_name': tool_name,
                'permission_mode': 'read_only',
                'side_effect_class': 'read_only',
                'execution_allowed': False,
            })
        for tool_name in PROPOSAL_TOOLS[server_id]:
            tools.append({
                'server_id': server_id,
                'tool_name': tool_name,
                'permission_mode': 'proposal_only',
                'side_effect_class': 'local_mutation',
                'execution_allowed': False,
            })
    return {'schema_version': MCP_ACCESS_VERSION, 'tools': tools}


def call_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    transport: Transport | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    if server_id not in SERVER_ENV_PREFIX:
        raise MCPAccessError(f'unknown MCP server: {server_id}')
    if not isinstance(arguments, dict):
        arguments = {}
    sanitized_args = scrub_payload(arguments, env=env)
    config = _server_public_config(server_id, env)
    side_effect_class = 'read_only' if tool_name in READ_ONLY_TOOLS[server_id] else 'local_mutation'
    base = {
        'schema_version': MCP_ACCESS_VERSION,
        'server_id': server_id,
        'tool_name': tool_name,
        'arguments': sanitized_args,
        'execution_allowed': False,
        'side_effect_class': side_effect_class,
    }
    if not _as_bool(env.get('METIS_MCP_ENABLED', 'false')) or not config['enabled']:
        return {**base, 'status': 'disabled', 'attempted': False, 'blocked_reason': 'mcp_server_disabled'}
    if tool_name in PROPOSAL_TOOLS[server_id]:
        return {
            **base,
            'status': 'proposal_required',
            'attempted': False,
            'blocked_reason': 'mcp_tool_is_proposal_only',
            'proposal_only': True,
        }
    if tool_name not in READ_ONLY_TOOLS[server_id]:
        return {
            **base,
            'status': 'blocked',
            'attempted': False,
            'blocked_reason': 'mcp_tool_not_allowlisted',
            'blocked_capabilities': list(BLOCKED_CAPABILITIES[server_id]),
        }
    if transport is None:
        return {
            **base,
            'status': 'not_configured',
            'attempted': False,
            'blocked_reason': 'no_mcp_transport_registered',
            'transport': config['transport'],
        }
    raw_result = transport(server_id, tool_name, deepcopy(sanitized_args))
    result = scrub_payload(raw_result, env=env, string_limit=2000)
    normalized = normalize_mcp_read_result(result)
    return {
        **base,
        'status': normalized.status,
        'attempted': True,
        'blocked_reason': normalized.blocked_reason,
        'result': result,
        'result_hash': sha1(repr(result).encode('utf-8')).hexdigest()[:16],
    }


def scrub_payload(value: Any, *, env: dict[str, str] | None = None, string_limit: int = 500) -> Any:
    return _scrub_value(value, _secret_values(env or os.environ), string_limit)


def _scrub_value(value: Any, secret_values: tuple[str, ...], string_limit: int) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if _is_sensitive_key(text_key):
                scrubbed[text_key] = MCP_ARGUMENT_REDACTION
            else:
                scrubbed[text_key] = _scrub_value(item, secret_values, string_limit)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_value(item, secret_values, string_limit) for item in value]
    if isinstance(value, tuple):
        return [_scrub_value(item, secret_values, string_limit) for item in value]
    if isinstance(value, str):
        text = value
        for secret in secret_values:
            text = text.replace(secret, MCP_ARGUMENT_REDACTION)
        if len(text) > string_limit:
            return f'{text[:string_limit]}...[truncated]'
        return text
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _scrub_value(str(value), secret_values, string_limit)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)


def _legacy_secret_values(env: dict[str, str]) -> tuple[str, ...]:
    secrets: list[str] = []
    for key, value in env.items():
        if not value or len(value) < 4:
            continue
        if _is_sensitive_key(str(key)):
            secrets.append(str(value))
    return tuple(sorted(set(secrets), key=len, reverse=True))


def _legacy_call_configured_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    preview = call_mcp_tool(server_id, tool_name, arguments, env=env)
    if preview.get('status') != 'not_configured':
        return preview
    if preview.get('transport') != 'external_stdio_configured':
        return preview
    try:
        return call_mcp_tool(
            server_id,
            tool_name,
            arguments,
            transport=lambda sid, name, args: _call_stdio_mcp(sid, name, args, env=env),
            env=env,
        )
    except (MCPAccessError, OSError, TimeoutError) as exc:
        return {
            **preview,
            'status': 'transport_error',
            'attempted': True,
            'blocked_reason': 'mcp_transport_error',
            'error': scrub_payload(str(exc), env=env, string_limit=240),
        }


def _private_stdio_config(server_id: str, env: dict[str, str]) -> dict[str, Any]:
    import json

    prefix = SERVER_ENV_PREFIX[server_id]
    command = str(env.get(f'{prefix}_COMMAND') or '').strip()
    cwd = str(env.get(f'{prefix}_CWD') or '').strip() or None
    try:
        args = json.loads(env.get(f'{prefix}_ARGS_JSON') or '[]')
    except json.JSONDecodeError as exc:
        raise MCPAccessError(f'invalid {prefix}_ARGS_JSON') from exc
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise MCPAccessError(f'{prefix}_ARGS_JSON must be a JSON string array')
    try:
        extra_env = json.loads(env.get(f'{prefix}_ENV_JSON') or '{}')
    except json.JSONDecodeError as exc:
        raise MCPAccessError(f'invalid {prefix}_ENV_JSON') from exc
    if not isinstance(extra_env, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in extra_env.items()):
        raise MCPAccessError(f'{prefix}_ENV_JSON must be a JSON object with string values')
    if not command:
        raise MCPAccessError('MCP command is not configured')
    return {'argv': [command, *args], 'cwd': cwd, 'extra_env': extra_env}


def _legacy_call_stdio_mcp(server_id: str, tool_name: str, arguments: dict[str, Any], *, env: dict[str, str]) -> Any:
    import json
    import subprocess

    config = _private_stdio_config(server_id, env)
    timeout = _int(env.get('METIS_MCP_TIMEOUT_SECONDS', '8'), 8, 1, 30)
    child_env = dict(os.environ)
    child_env.update(config['extra_env'])
    proc = subprocess.Popen(
        config['argv'],
        cwd=config['cwd'],
        env=child_env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _send_mcp_message(
            proc,
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'initialize',
                'params': {
                    'protocolVersion': '2024-11-05',
                    'capabilities': {},
                    'clientInfo': {'name': 'metis-head', 'version': MCP_ACCESS_VERSION},
                },
            },
        )
        _read_mcp_message(proc, timeout)
        _send_mcp_message(proc, {'jsonrpc': '2.0', 'method': 'notifications/initialized', 'params': {}})
        _send_mcp_message(
            proc,
            {
                'jsonrpc': '2.0',
                'id': 2,
                'method': 'tools/call',
                'params': {'name': tool_name, 'arguments': arguments},
            },
        )
        response = _read_mcp_message(proc, timeout)
        if isinstance(response, dict) and response.get('error'):
            raise MCPAccessError(json.dumps(response['error'], sort_keys=True, default=str))
        return response.get('result') if isinstance(response, dict) else response
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()


def _send_mcp_message(proc: Any, message: dict[str, Any]) -> None:
    import json

    if proc.stdin is None:
        raise MCPAccessError('MCP stdin unavailable')
    body = json.dumps(message, separators=(',', ':'), default=str).encode('utf-8')
    header = f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii')
    proc.stdin.write(header + body)
    proc.stdin.flush()


def _read_mcp_message(proc: Any, timeout: int) -> dict[str, Any]:
    import json
    import queue
    import threading

    if proc.stdout is None:
        raise MCPAccessError('MCP stdout unavailable')
    result_queue: queue.Queue[dict[str, Any] | BaseException] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            headers: dict[str, str] = {}
            while True:
                line = proc.stdout.readline()
                if line == b'':
                    raise MCPAccessError('MCP stdout closed before response')
                if line in {b'\r\n', b'\n'}:
                    break
                name, _, value = line.decode('ascii', errors='replace').partition(':')
                headers[name.strip().lower()] = value.strip()
            length = int(headers.get('content-length') or '0')
            if length <= 0:
                raise MCPAccessError('MCP response missing content length')
            raw = proc.stdout.read(length)
            if len(raw) != length:
                raise MCPAccessError('MCP response ended early')
            result_queue.put(json.loads(raw.decode('utf-8')))
        except BaseException as exc:  # pragma: no cover - exercised through timeout/error tests.
            result_queue.put(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        item = result_queue.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError('MCP response timed out') from exc
    if isinstance(item, BaseException):
        raise item
    return item


def _secret_values(env: dict[str, str]) -> tuple[str, ...]:
    import json

    secrets: list[str] = []
    for key, value in env.items():
        if not value:
            continue
        text_key = str(key)
        text_value = str(value)
        if _is_sensitive_key(text_key) and len(text_value) >= 4:
            secrets.append(text_value)
        if text_key.endswith('_ENV_JSON'):
            try:
                child_env = json.loads(text_value)
            except json.JSONDecodeError:
                child_env = {}
            if isinstance(child_env, dict):
                for child_key, child_value in child_env.items():
                    if _is_sensitive_key(str(child_key)) and isinstance(child_value, str) and len(child_value) >= 4:
                        secrets.append(child_value)
    return tuple(sorted(set(secrets), key=len, reverse=True))



def _call_stdio_mcp(server_id: str, tool_name: str, arguments: dict[str, Any], *, env: dict[str, str]) -> Any:
    import anyio

    return anyio.run(_call_stdio_mcp_async, server_id, tool_name, arguments, env)


async def _legacy_call_stdio_mcp_async(server_id: str, tool_name: str, arguments: dict[str, Any], env: dict[str, str]) -> Any:
    from datetime import timedelta
    import io

    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    config = _private_stdio_config(server_id, env)
    timeout = _int(env.get('METIS_MCP_TIMEOUT_SECONDS', '8'), 8, 1, 30)
    params = StdioServerParameters(
        command=config['argv'][0],
        args=config['argv'][1:],
        cwd=config['cwd'],
        env=config['extra_env'],
    )
    errlog = io.StringIO()
    async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=timeout),
        ) as session:
            await session.initialize()
            result = await session.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=timedelta(seconds=timeout),
            )
    if hasattr(result, 'model_dump'):
        return result.model_dump(mode='json')
    return result


async def _call_stdio_mcp_async(server_id: str, tool_name: str, arguments: dict[str, Any], env: dict[str, str]) -> Any:
    from datetime import timedelta
    import os as _os

    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    config = _private_stdio_config(server_id, env)
    timeout = _int(env.get('METIS_MCP_TIMEOUT_SECONDS', '8'), 8, 1, 30)
    params = StdioServerParameters(
        command=config['argv'][0],
        args=config['argv'][1:],
        cwd=config['cwd'],
        env=config['extra_env'],
    )
    with open(_os.devnull, 'w', encoding='utf-8') as errlog:
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=timeout),
            ) as session:
                await session.initialize()
                result = await session.call_tool(
                    tool_name,
                    arguments,
                    read_timeout_seconds=timedelta(seconds=timeout),
                )
    if hasattr(result, 'model_dump'):
        return result.model_dump(mode='json')
    return result



def call_configured_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    preview = call_mcp_tool(server_id, tool_name, arguments, env=env)
    if preview.get('status') != 'not_configured':
        return preview
    if preview.get('transport') != 'external_stdio_configured':
        return preview
    try:
        return call_mcp_tool(
            server_id,
            tool_name,
            arguments,
            transport=lambda sid, name, args: _call_stdio_mcp(sid, name, args, env=env),
            env=env,
        )
    except Exception as exc:
        return {
            **preview,
            'status': 'transport_error',
            'attempted': True,
            'blocked_reason': 'mcp_transport_error',
            'error': scrub_payload(str(exc), env=env, string_limit=240),
        }
