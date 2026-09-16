from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient

from metis_head import brain


ROOT = Path(__file__).resolve().parents[1]


def test_conversation_client_executes_owned_session_contract() -> None:
    node = shutil.which("node")
    assert node, "Node.js is required for executable browser contract tests"
    script = ROOT / "metis_head" / "static" / "conversation_client.js"
    probe = r"""
const fs = require('fs');
const vm = require('vm');
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const stored = new Map();
const storage = {getItem:k => stored.get(k) || null, setItem:(k,v) => stored.set(k,v)};
const calls = [];
const responses = [
  {ok:true, status:200, json:async()=>({session_id:'session-a'})},
  {ok:true, status:200, json:async()=>({message:'answer'})}
];
const fetchImpl = async (url, options={}) => { calls.push({url, options}); return responses.shift(); };
(async () => {
  const client = new MetisConversationClient(fetchImpl, storage, ()=>'tab-a');
  const result = await client.requestChat('hello', {provider:'openai', model:'fixture', voice:{provider:'piper', speak_response:false}});
  const payload = JSON.parse(calls[1].options.body);
  if (result.message !== 'answer') throw new Error('missing answer');
  if (payload.session_id !== 'session-a') throw new Error('missing owned session');
  if (payload.options.provider !== 'openai') throw new Error('LLM provider changed');
  if (payload.options.voice.provider !== 'piper') throw new Error('speech provider not nested');
  if (calls.filter(call => call.url === '/metis/sessions').length !== 1) throw new Error('session recreated');
  process.stdout.write(JSON.stringify({ok:true}));
})().catch(error => { console.error(error); process.exit(1); });
"""
    completed = subprocess.run([node, "-e", probe, str(script)], capture_output=True, text=True, timeout=10, check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True}


def test_conversation_client_does_not_replay_after_expired_session() -> None:
    node = shutil.which("node")
    assert node, "Node.js is required for executable browser contract tests"
    script = ROOT / "metis_head" / "static" / "conversation_client.js"
    probe = r"""
const fs = require('fs');
const vm = require('vm');
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const storage = {getItem:()=>null, setItem:()=>{}};
const calls = [];
const responses = [
  {ok:true, status:200, json:async()=>({session_id:'gone'})},
  {ok:false, status:404, json:async()=>({detail:'unknown session'})}
];
const fetchImpl = async (url, options={}) => { calls.push({url, options}); return responses.shift(); };
(async () => {
  const client = new MetisConversationClient(fetchImpl, storage, ()=>'tab-b');
  let failed = false;
  try { await client.requestChat('do not replay', {provider:'ollama'}); } catch (_) { failed = true; }
  if (!failed || client.sessionId !== null) throw new Error('expired session was not invalidated');
  if (calls.filter(call => call.url === '/metis/chat').length !== 1) throw new Error('message replayed');
  process.stdout.write('ok');
})().catch(error => { console.error(error); process.exit(1); });
"""
    completed = subprocess.run([node, "-e", probe, str(script)], capture_output=True, text=True, timeout=10, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "ok"


def test_conversation_client_asset_is_installed_route() -> None:
    with TestClient(brain.app) as client:
        response = client.get("/static/conversation_client.js")
    assert response.status_code == 200
    assert "MetisConversationClient" in response.text
