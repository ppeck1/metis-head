'use strict';

const assert = require('node:assert/strict');
const {MetisVoiceCapture, STATES} = require('../metis_head/static/voice_capture.js');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

function fakeStream() {
  const track = {stopped: false, stop() { this.stopped = true; }};
  return {track, getTracks() { return [track]; }};
}

class FakeAudioContext {
  constructor() {
    this.sampleRate = 48000;
    this.state = 'running';
    this.destination = {};
    this.source = {connected: false, connect() { this.connected = true; }, disconnect() { this.connected = false; }};
    this.processor = {
      connected: false,
      onaudioprocess: null,
      connect() { this.connected = true; },
      disconnect() { this.connected = false; }
    };
    FakeAudioContext.instances.push(this);
  }
  createMediaStreamSource() { return this.source; }
  createScriptProcessor() { return this.processor; }
  async close() { this.state = 'closed'; }
}
FakeAudioContext.instances = [];

async function settle() {
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
}

async function cancelDuringAuthorization() {
  const gate = deferred();
  let mediaCalls = 0;
  const cleanups = [];
  const capture = new MetisVoiceCapture({
    authorize: () => gate.promise,
    cleanup: async (reason) => cleanups.push(reason),
    mediaDevices: {async getUserMedia() { mediaCalls += 1; return fakeStream(); }},
    AudioContext: FakeAudioContext
  });
  const starting = capture.start();
  assert.equal(capture.state, STATES.AUTHORIZING);
  await capture.cancel();
  gate.resolve({status: 'ptt_pressed'});
  assert.equal(await starting, false);
  assert.equal(mediaCalls, 0);
  assert.equal(capture.state, STATES.IDLE);
  assert.deepEqual(cleanups, ['cancelled']);
}

async function releaseDuringGetUserMediaStopsLateStream() {
  const media = deferred();
  const capture = new MetisVoiceCapture({
    authorize: async () => ({status: 'ptt_pressed'}),
    mediaDevices: {getUserMedia: () => media.promise},
    AudioContext: FakeAudioContext
  });
  const starting = capture.start();
  await settle();
  assert.equal(capture.state, STATES.ACQUIRING);
  assert.equal(await capture.stop(), null);
  const stream = fakeStream();
  media.resolve(stream);
  assert.equal(await starting, false);
  assert.equal(stream.track.stopped, true);
  assert.equal(capture.active, false);
  assert.equal(capture.state, STATES.IDLE);
}

async function cancelDuringGetUserMediaStopsLateStream() {
  const media = deferred();
  const capture = new MetisVoiceCapture({
    authorize: async () => ({status: 'ptt_pressed'}),
    mediaDevices: {getUserMedia: () => media.promise},
    AudioContext: FakeAudioContext
  });
  const starting = capture.start();
  await settle();
  await capture.cancel();
  const stream = fakeStream();
  media.resolve(stream);
  assert.equal(await starting, false);
  assert.equal(stream.track.stopped, true);
  assert.equal(await capture.stop(), null);
}

async function successfulCaptureProducesBoundedWavAndCleansUp() {
  const stream = fakeStream();
  const cleanups = [];
  const capture = new MetisVoiceCapture({
    authorize: async () => ({status: 'ptt_pressed'}),
    mediaDevices: {async getUserMedia() { return stream; }},
    AudioContext: FakeAudioContext,
    cleanup: async (reason) => cleanups.push(reason),
    maxDurationMs: 1000
  });
  assert.equal(await capture.start(), true);
  const context = FakeAudioContext.instances.at(-1);
  context.processor.onaudioprocess({inputBuffer: {getChannelData: () => new Float32Array([0, 0.5, -0.5, 1])}});
  const wav = await capture.stop();
  assert.ok(wav instanceof Blob);
  assert.ok(wav.size > 44);
  assert.equal(stream.track.stopped, true);
  assert.equal(context.state, 'closed');
  assert.equal(capture.state, STATES.IDLE);
  assert.deepEqual(cleanups, ['released']);
}

async function permissionFailureCleansBackendExactlyOnce() {
  const cleanups = [];
  const capture = new MetisVoiceCapture({
    authorize: async () => ({status: 'ptt_pressed'}),
    cleanup: async (reason) => cleanups.push(reason),
    mediaDevices: {async getUserMedia() { const error = new Error('denied'); error.name = 'NotAllowedError'; throw error; }},
    AudioContext: FakeAudioContext
  });
  assert.equal(await capture.start(), false);
  assert.deepEqual(cleanups, ['permission_denied']);
  await capture.cancel();
  assert.deepEqual(cleanups, ['permission_denied']);
}

async function emptyReleaseStillCleansBackend() {
  const cleanups = [];
  const capture = new MetisVoiceCapture({
    authorize: async () => ({status: 'ptt_pressed'}),
    cleanup: async (reason) => cleanups.push(reason),
    mediaDevices: {async getUserMedia() { return fakeStream(); }},
    AudioContext: FakeAudioContext
  });
  assert.equal(await capture.start(), true);
  assert.equal(await capture.stop(), null);
  assert.deepEqual(cleanups, ['released']);
}

async function resourceLimitCancelsInsteadOfUploadingPartialAudio() {
  const statuses = [];
  const stream = fakeStream();
  const capture = new MetisVoiceCapture({
    authorize: async () => ({status: 'ptt_pressed'}),
    mediaDevices: {async getUserMedia() { return stream; }},
    AudioContext: FakeAudioContext,
    maxFrames: 1,
    maxDurationMs: 30000,
    onStatus: (status) => statuses.push(status)
  });
  assert.equal(await capture.start(), true);
  const processor = FakeAudioContext.instances.at(-1).processor;
  const event = {inputBuffer: {getChannelData: () => new Float32Array([0.1, 0.2])}};
  processor.onaudioprocess(event);
  processor.onaudioprocess(event);
  await settle();
  assert.equal(capture.state, STATES.IDLE);
  assert.equal(stream.track.stopped, true);
  assert.equal(await capture.stop(), null);
  assert.ok(statuses.some((status) => status.includes('limit reached')));
}

async function main() {
  await cancelDuringAuthorization();
  await releaseDuringGetUserMediaStopsLateStream();
  await cancelDuringGetUserMediaStopsLateStream();
  await successfulCaptureProducesBoundedWavAndCleansUp();
  await permissionFailureCleansBackendExactlyOnce();
  await emptyReleaseStillCleansBackend();
  await resourceLimitCancelsInsteadOfUploadingPartialAudio();
  process.stdout.write('voice capture state-machine tests passed\n');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
