'use strict';

const assert = require('node:assert/strict');
const {MetisConversationClient, MetisPlaybackController} = require('../metis_head/static/conversation_client.js');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

function response(body, status = 200) {
  return {ok: status >= 200 && status < 300, status, json: async () => body};
}

async function settle() {
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
}

async function deduplicatesSessionCreation() {
  const creation = deferred();
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({url, options});
    if (url === '/metis/sessions') return creation.promise;
    return response({message: 'ok'});
  };
  const storage = {getItem: () => null, setItem: () => {}};
  const client = new MetisConversationClient(fetchImpl, storage, () => 'tab');
  const left = client.ensureSession();
  const right = client.ensureSession();
  assert.equal(calls.filter((call) => call.url === '/metis/sessions').length, 1);
  creation.resolve(response({session_id: 'session'}));
  assert.equal(await left, 'session');
  assert.equal(await right, 'session');
}

async function cancellationBeforeSessionRegistrationDispatchesNoChat() {
  const creation = deferred();
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({url, options});
    if (url === '/metis/sessions') return creation.promise;
    if (url.endsWith('/cancel')) return response({status: 'cancelled'});
    throw new Error(`unexpected dispatch: ${url}`);
  };
  const storage = {getItem: () => null, setItem: () => {}};
  const client = new MetisConversationClient(fetchImpl, storage, () => 'tab');
  const request = client.requestChat('never dispatch', {});
  await settle();
  await client.cancel();
  creation.resolve(response({session_id: 'late'}));
  await assert.rejects(request, /cancelled before dispatch/);
  await settle();
  assert.equal(calls.filter((call) => call.url === '/metis/chat').length, 0);
  assert.equal(calls.filter((call) => call.url.endsWith('/cancel')).length, 1);
}

async function copiedTabStorageDoesNotSharePlaybackOwner() {
  const values = new Map([['metis.client_id', 'copied-owner']]);
  const storage = {getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value)};
  let sequence = 0;
  const factory = () => `document-${++sequence}`;
  const first = new MetisConversationClient(async () => response({}), storage, factory);
  const second = new MetisConversationClient(async () => response({}), storage, factory);
  assert.equal(first.clientId, 'document-1');
  assert.equal(second.clientId, 'document-2');
  assert.notEqual(first.clientId, second.clientId);
}

async function closeDuringSessionCreationDeletesLateSession() {
  const creation = deferred();
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({url, options});
    if (url === '/metis/sessions') return creation.promise;
    return response({status: 'closed'});
  };
  const storage = {getItem: () => null, setItem: () => {}};
  const client = new MetisConversationClient(fetchImpl, storage, () => 'tab');
  const pending = client.ensureSession();
  client.close();
  creation.resolve(response({session_id: 'late-close'}));
  await pending;
  await settle();
  const deletion = calls.find((call) => call.url === '/metis/sessions/late-close');
  assert.equal(deletion.options.method, 'DELETE');
  assert.equal(deletion.options.keepalive, true);
  assert.equal(client.sessionId, null);
}

class FakeAudio {
  constructor(src) {
    this.src = src;
    this.paused = false;
    this.onended = null;
    this.onerror = null;
    FakeAudio.instances.push(this);
  }
  async play() { this.played = true; }
  pause() { this.paused = true; }
}
FakeAudio.instances = [];

async function lateQueueResponseCannotRestartAfterStop() {
  const next = deferred();
  const controller = new MetisPlaybackController(async () => next.promise, FakeAudio, {getSessionId: () => 's'});
  const pending = controller.playNext('tab');
  controller.stop();
  next.resolve(response({command: {kind: 'play', playback_id: 'p', session_id: 's', audio_ref: '/a'}}));
  assert.equal(await pending, null);
  assert.equal(FakeAudio.instances.length, 0);
}

async function drainsStopThenPlaysAndAcknowledges() {
  const calls = [];
  const commands = [
    response({command: {kind: 'stop', playback_id: 'old', session_id: 's'}}),
    response({command: {kind: 'play', playback_id: 'new', session_id: 's', audio_ref: '/new'}})
  ];
  const fetchImpl = async (url, options) => {
    calls.push({url, options});
    if (url.startsWith('/metis/playback/next')) return commands.shift();
    return response({status: 'accepted'});
  };
  const controller = new MetisPlaybackController(fetchImpl, FakeAudio, {getSessionId: () => 's'});
  const command = await controller.playNext('tab');
  assert.equal(command.playback_id, 'new');
  const audio = FakeAudio.instances.at(-1);
  audio.onended();
  await settle();
  const states = calls.filter((call) => call.url === '/metis/playback/ack')
    .map((call) => JSON.parse(call.options.body).state);
  assert.deepEqual(states, ['started', 'completed']);
}

async function rejectedPlayGetsPreStartFailureAck() {
  class RejectingAudio extends FakeAudio {
    async play() { throw new Error('autoplay'); }
  }
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({url, options});
    if (url.startsWith('/metis/playback/next')) {
      return response({command: {kind: 'play', playback_id: 'reject', session_id: 's', audio_ref: '/reject'}});
    }
    return response({status: 'accepted'});
  };
  const controller = new MetisPlaybackController(fetchImpl, RejectingAudio, {getSessionId: () => 's'});
  assert.equal(await controller.playNext('tab'), null);
  const ack = JSON.parse(calls.find((call) => call.url === '/metis/playback/ack').options.body);
  assert.equal(ack.state, 'failed');
  assert.equal(ack.failure_code, 'audio_play_rejected');
  assert.equal(controller.current, null);
}

async function main() {
  await deduplicatesSessionCreation();
  await cancellationBeforeSessionRegistrationDispatchesNoChat();
  await copiedTabStorageDoesNotSharePlaybackOwner();
  await closeDuringSessionCreationDeletesLateSession();
  await lateQueueResponseCannotRestartAfterStop();
  await drainsStopThenPlaysAndAcknowledges();
  await rejectedPlayGetsPreStartFailureAck();
  process.stdout.write('conversation client lifecycle tests passed\n');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
