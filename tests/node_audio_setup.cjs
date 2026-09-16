'use strict';

const assert = require('node:assert/strict');
const {MetisAudioSetupController, AUDIO_SETUP_STATES} = require('../metis_head/static/audio_setup.js');

class FakeAudioContext {
  constructor() {
    this.currentTime = 5;
    this.state = FakeAudioContext.initialState;
    this.destination = {};
    this.resumed = false;
    this.closed = false;
    this.oscillator = {
      type: '',
      frequency: {setValueAtTime: (value, time) => { this.frequency = [value, time]; }},
      connect: (target) => { this.oscillatorTarget = target; },
      start: (time) => { this.startedAt = time; },
      stop: (time) => { this.stoppedAt = time; queueMicrotask(() => this.oscillator.onended()); },
      onended: null
    };
    this.gainNode = {
      gain: {
        values: [],
        setValueAtTime: (value, time) => this.gainNode.gain.values.push(['set', value, time]),
        exponentialRampToValueAtTime: (value, time) => this.gainNode.gain.values.push(['ramp', value, time])
      },
      connect: (target) => { this.gainTarget = target; }
    };
    FakeAudioContext.instances.push(this);
  }
  async resume() { this.resumed = true; this.state = 'running'; }
  createOscillator() { return this.oscillator; }
  createGain() { return this.gainNode; }
  async close() { this.closed = true; this.state = 'closed'; }
}
FakeAudioContext.initialState = 'suspended';
FakeAudioContext.instances = [];

function browser(overrides) {
  return Object.assign({
    isSecureContext: true,
    navigator: {mediaDevices: {getUserMedia() {}}},
    setTimeout,
    clearTimeout
  }, overrides || {});
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

async function settle() {
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
}

async function speakerTestRequiresHumanConfirmation() {
  const updates = [];
  const controller = new MetisAudioSetupController({
    global: browser(),
    AudioContext: FakeAudioContext,
    durationMs: 200,
    gain: 0.04,
    onStatus: (status) => updates.push(status.state)
  });
  const completed = await controller.playSpeakerTest();
  const context = FakeAudioContext.instances.at(-1);
  assert.equal(completed.state, AUDIO_SETUP_STATES.SPEAKER_AWAITING_CONFIRMATION);
  assert.match(completed.message, /Confirm whether you actually heard it/);
  assert.equal(context.resumed, true);
  assert.equal(context.startedAt, 5);
  assert.equal(context.stoppedAt, 5.2);
  assert.equal(context.closed, true);
  assert.ok(context.gainNode.gain.values.some((entry) => entry[1] === 0.04));
  assert.deepEqual(updates.slice(0, 2), [
    AUDIO_SETUP_STATES.SPEAKER_PLAYING,
    AUDIO_SETUP_STATES.SPEAKER_AWAITING_CONFIRMATION
  ]);
  assert.equal(controller.confirmSpeakerAudible(true).state, AUDIO_SETUP_STATES.SPEAKER_CONFIRMED);
}

async function negativeSpeakerConfirmationIsActionable() {
  const controller = new MetisAudioSetupController({global: browser(), AudioContext: FakeAudioContext});
  await controller.playSpeakerTest();
  const result = controller.confirmSpeakerAudible(false);
  assert.equal(result.state, AUDIO_SETUP_STATES.SPEAKER_NOT_HEARD);
  assert.match(result.message, /output device/);
}

function capabilitiesAreExplicit() {
  const controller = new MetisAudioSetupController({
    global: browser({isSecureContext: false}),
    AudioContext: null,
    VoiceCapture: function () {}
  });
  assert.deepEqual(controller.checkCapabilities(), {
    secureContext: false,
    audioOutput: false,
    microphone: false,
    mediaDevices: true,
    inputLevelAvailable: true
  });
}

async function microphoneUsesCaptureAndBoundedTranscription() {
  const wav = new Blob(['wav'], {type: 'audio/wav'});
  const calls = [];
  const transcripts = [];
  const capture = {
    async start() { calls.push('start'); return true; },
    async stop() { calls.push('stop'); return wav; },
    async cancel() { calls.push('cancel'); }
  };
  const controller = new MetisAudioSetupController({
    global: browser(),
    AudioContext: FakeAudioContext,
    captureFactory: (options) => { calls.push(['factory', typeof options.onStatus]); return capture; },
    transcribe: async (audio) => { calls.push(['transcribe', audio]); return {transcript: '  four profile test  '}; },
    onTranscript: (text) => transcripts.push(text)
  });
  assert.equal((await controller.startMicrophoneTest()).state, AUDIO_SETUP_STATES.MICROPHONE_RECORDING);
  const completed = await controller.stopMicrophoneTest();
  assert.equal(completed.state, AUDIO_SETUP_STATES.MICROPHONE_COMPLETE);
  assert.equal(completed.transcript, 'four profile test');
  assert.deepEqual(transcripts, ['four profile test']);
  assert.deepEqual(calls.map((item) => Array.isArray(item) ? item[0] : item), ['factory', 'start', 'stop', 'transcribe']);
}

async function microphoneFailureDoesNotInvokeTranscription() {
  let transcribeCalls = 0;
  const controller = new MetisAudioSetupController({
    global: browser(),
    AudioContext: FakeAudioContext,
    captureFactory: () => ({async start() { return true; }, async stop() { return null; }}),
    transcribe: async () => { transcribeCalls += 1; }
  });
  await controller.startMicrophoneTest();
  const result = await controller.stopMicrophoneTest();
  assert.equal(result.state, AUDIO_SETUP_STATES.MICROPHONE_ERROR);
  assert.equal(transcribeCalls, 0);
}

async function cancellationCleansCapture() {
  let cancelled = false;
  const controller = new MetisAudioSetupController({
    global: browser(),
    AudioContext: FakeAudioContext,
    captureFactory: () => ({async start() { return true; }, async cancel() { cancelled = true; }})
  });
  await controller.startMicrophoneTest();
  const result = await controller.cancelMicrophoneTest();
  assert.equal(cancelled, true);
  assert.equal(result.state, AUDIO_SETUP_STATES.IDLE);
}

async function cancelledTranscriptionCannotPublishLateResult() {
  const gate = deferred();
  const transcripts = [];
  const controller = new MetisAudioSetupController({
    global: browser(),
    AudioContext: FakeAudioContext,
    captureFactory: () => ({
      async start() { return true; },
      async stop() { return new Blob(['wav'], {type: 'audio/wav'}); },
      async cancel() {}
    }),
    transcribe: () => gate.promise,
    onTranscript: (text) => transcripts.push(text)
  });
  await controller.startMicrophoneTest();
  const stopping = controller.stopMicrophoneTest();
  await settle();
  await controller.cancelMicrophoneTest();
  gate.resolve({transcript: 'stale words'});
  const result = await stopping;
  assert.equal(result.state, AUDIO_SETUP_STATES.IDLE);
  assert.deepEqual(transcripts, []);
  assert.equal(controller.transcript, '');
}

async function cancelledStartCannotBecomeRecordingLater() {
  const gate = deferred();
  let captureCancelled = false;
  const controller = new MetisAudioSetupController({
    global: browser(),
    AudioContext: FakeAudioContext,
    captureFactory: () => ({
      start: () => gate.promise,
      async cancel() { captureCancelled = true; }
    })
  });
  const starting = controller.startMicrophoneTest();
  await controller.cancelMicrophoneTest();
  gate.resolve(true);
  const result = await starting;
  assert.equal(result.state, AUDIO_SETUP_STATES.IDLE);
  assert.equal(captureCancelled, true);
}

async function staleCaptureCallbacksCannotOverwriteNewerState() {
  const gate = deferred();
  let captureOptions = null;
  const controller = new MetisAudioSetupController({
    global: browser(),
    AudioContext: FakeAudioContext,
    captureFactory: (options) => {
      captureOptions = options;
      return {start: () => gate.promise, async cancel() {}};
    }
  });
  const starting = controller.startMicrophoneTest();
  await controller.cancelMicrophoneTest();
  captureOptions.onStatus('stale status');
  captureOptions.onLevel(0.9);
  gate.reject(new Error('late failure'));
  const result = await starting;
  assert.equal(result.state, AUDIO_SETUP_STATES.IDLE);
  assert.equal(result.message, 'Microphone test cancelled.');
  assert.equal(result.inputLevel, null);
}

async function main() {
  await speakerTestRequiresHumanConfirmation();
  await negativeSpeakerConfirmationIsActionable();
  capabilitiesAreExplicit();
  await microphoneUsesCaptureAndBoundedTranscription();
  await microphoneFailureDoesNotInvokeTranscription();
  await cancellationCleansCapture();
  await cancelledTranscriptionCannotPublishLateResult();
  await cancelledStartCannotBecomeRecordingLater();
  await staleCaptureCallbacksCannotOverwriteNewerState();
  process.stdout.write('audio setup controller tests passed\n');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
