(function (global) {
  'use strict';

  const STATES = Object.freeze({
    IDLE: 'idle',
    AUTHORIZING: 'authorizing',
    ACQUIRING: 'acquiring',
    RECORDING: 'recording',
    FINALIZING: 'finalizing'
  });

  class MetisVoiceCapture {
    constructor(options) {
      options = options || {};
      if (typeof options.authorize !== 'function') throw new TypeError('authorize is required');
      this.authorize = options.authorize;
      this.cleanup = typeof options.cleanup === 'function' ? options.cleanup : async function () {};
      this.onStatus = options.onStatus || function () {};
      this.onLevel = typeof options.onLevel === 'function' ? options.onLevel : function () {};
      this.mediaDevices = options.mediaDevices || (global.navigator && global.navigator.mediaDevices);
      this.AudioContextType = options.AudioContext || global.AudioContext || global.webkitAudioContext;
      this.frameSize = positiveInteger(options.frameSize, 4096);
      this.maxDurationMs = positiveInteger(options.maxDurationMs, 30000);
      this.maxFrames = positiveInteger(options.maxFrames, 2048);
      this.stream = null;
      this.context = null;
      this.source = null;
      this.processor = null;
      this.frames = [];
      this.sampleCount = 0;
      this.sampleRate = 0;
      this.state = STATES.IDLE;
      this.active = false;
      this._epoch = 0;
      this._limitCancellation = null;
      this._backendEpoch = null;
    }

    async start() {
      if (this.state !== STATES.IDLE) return false;
      const epoch = ++this._epoch;
      this._backendEpoch = epoch;
      this.state = STATES.AUTHORIZING;

      let decision;
      try {
        decision = await this.authorize();
      } catch (_) {
        if (this._isCurrent(epoch)) {
          this._resetIdle();
          this.onStatus('Capture authorization failed.');
        }
        await this._cleanupBackend(epoch, 'authorization_failed');
        return false;
      }
      if (!this._isCurrent(epoch)) return false;
      if (!decision || decision.status !== 'ptt_pressed') {
        this._resetIdle();
        this.onStatus((decision && (decision.block_reason || decision.status)) || 'capture not authorized');
        await this._cleanupBackend(epoch, 'authorization_denied');
        return false;
      }
      if (!this.mediaDevices || typeof this.mediaDevices.getUserMedia !== 'function' || !this.AudioContextType) {
        this._resetIdle();
        this.onStatus('Microphone capture unavailable.');
        await this._cleanupBackend(epoch, 'capture_unavailable');
        return false;
      }

      this.state = STATES.ACQUIRING;
      let stream = null;
      let context = null;
      let source = null;
      let processor = null;
      try {
        stream = await this.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true}, video: false});
        if (!this._isCurrent(epoch)) {
          stopTracks(stream);
          return false;
        }
        context = new this.AudioContextType();
        if (context.state === 'suspended' && typeof context.resume === 'function') {
          await context.resume();
        }
        if (context.state === 'suspended') {
          const error = new Error('audio_context_suspended');
          error.name = 'NotAllowedError';
          throw error;
        }
        source = context.createMediaStreamSource(stream);
        processor = context.createScriptProcessor(this.frameSize, 1, 1);
        if (!this._isCurrent(epoch)) {
          await closeResources({stream, context, source, processor});
          return false;
        }

        this.stream = stream;
        this.context = context;
        this.source = source;
        this.processor = processor;
        this.sampleRate = context.sampleRate;
        this.frames = [];
        this.sampleCount = 0;
        processor.onaudioprocess = (event) => this._captureFrame(epoch, event);
        source.connect(processor);
        processor.connect(context.destination);
        this.state = STATES.RECORDING;
        this.active = true;
        this.onStatus('Recording locally — release to send');
        return true;
      } catch (error) {
        await closeResources({stream, context, source, processor});
        if (this._isCurrent(epoch)) {
          this._resetIdle();
          this.onStatus(
            error && error.message === 'audio_context_suspended'
              ? 'Browser audio input is suspended. Click and hold again to resume microphone capture.'
              : error && error.name === 'NotAllowedError'
                ? 'Microphone permission denied.'
                : 'Microphone capture failed.'
          );
        }
        await this._cleanupBackend(epoch, error && error.name === 'NotAllowedError' ? 'permission_denied' : 'capture_failed');
        return false;
      }
    }

    async stop() {
      if (this.state !== STATES.RECORDING) {
        if (this.state !== STATES.IDLE) await this.cancel();
        return null;
      }
      const epoch = ++this._epoch;
      this.state = STATES.FINALIZING;
      this.active = false;
      const frames = this.frames;
      const inputRate = this.sampleRate;
      this.frames = [];
      this.sampleCount = 0;
      const resources = this._takeResources();
      await closeResources(resources);
      await this._cleanupBackend(epoch - 1, 'released');
      if (!this._isCurrent(epoch)) return null;
      this._resetIdle();
      if (!frames.length || !inputRate) return null;
      const pcm = concatFrames(frames);
      const mono16k = resampleLinear(pcm, inputRate, 16000);
      return encodeWav(mono16k, 16000);
    }

    async cancel() {
      const backendEpoch = this._backendEpoch;
      ++this._epoch;
      this.active = false;
      this.state = STATES.IDLE;
      this.frames = [];
      this.sampleCount = 0;
      await closeResources(this._takeResources());
      if (backendEpoch !== null) await this._cleanupBackend(backendEpoch, 'cancelled');
    }

    _captureFrame(epoch, event) {
      if (!this._isCurrent(epoch) || this.state !== STATES.RECORDING) return;
      const samples = event.inputBuffer.getChannelData(0);
      const maxSamples = Math.ceil(this.sampleRate * this.maxDurationMs / 1000);
      if (this.frames.length >= this.maxFrames || this.sampleCount + samples.length > maxSamples) {
        if (!this._limitCancellation) {
          this.onStatus('Recording limit reached; capture cancelled.');
          this._limitCancellation = this.cancel().finally(() => { this._limitCancellation = null; });
        }
        return;
      }
      this.frames.push(new Float32Array(samples));
      this.sampleCount += samples.length;
      let sumSquares = 0;
      for (let index = 0; index < samples.length; index += 1) sumSquares += samples[index] * samples[index];
      this.onLevel(Math.min(1, Math.sqrt(sumSquares / Math.max(1, samples.length)) * 4));
    }

    _isCurrent(epoch) {
      return this._epoch === epoch;
    }

    _takeResources() {
      const resources = {stream: this.stream, context: this.context, source: this.source, processor: this.processor};
      this.stream = null;
      this.context = null;
      this.source = null;
      this.processor = null;
      return resources;
    }

    _resetIdle() {
      this.active = false;
      this.state = STATES.IDLE;
      this.frames = [];
      this.sampleCount = 0;
      this.sampleRate = 0;
    }

    async _cleanupBackend(epoch, reason) {
      if (this._backendEpoch !== epoch) return;
      this._backendEpoch = null;
      try {
        await this.cleanup(reason);
      } catch (_) {
        this.onStatus('Capture cleanup could not be confirmed.');
      }
    }
  }

  async function closeResources(resources) {
    resources = resources || {};
    if (resources.processor) {
      resources.processor.onaudioprocess = null;
      try { resources.processor.disconnect(); } catch (_) {}
    }
    if (resources.source) { try { resources.source.disconnect(); } catch (_) {} }
    stopTracks(resources.stream);
    if (resources.context && resources.context.state !== 'closed') {
      try { await resources.context.close(); } catch (_) {}
    }
  }

  function stopTracks(stream) {
    if (!stream || typeof stream.getTracks !== 'function') return;
    stream.getTracks().forEach((track) => { try { track.stop(); } catch (_) {} });
  }

  function positiveInteger(value, fallback) {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
  }

  function concatFrames(frames) {
    const length = frames.reduce((sum, frame) => sum + frame.length, 0);
    const output = new Float32Array(length);
    let offset = 0;
    frames.forEach((frame) => { output.set(frame, offset); offset += frame.length; });
    return output;
  }

  function resampleLinear(input, inputRate, outputRate) {
    if (inputRate === outputRate) return input;
    const length = Math.max(1, Math.round(input.length * outputRate / inputRate));
    const output = new Float32Array(length);
    const ratio = inputRate / outputRate;
    for (let index = 0; index < length; index += 1) {
      const position = index * ratio;
      const left = Math.min(input.length - 1, Math.floor(position));
      const right = Math.min(input.length - 1, left + 1);
      const fraction = position - left;
      output[index] = input[left] * (1 - fraction) + input[right] * fraction;
    }
    return output;
  }

  function encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const ascii = (offset, value) => { for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i)); };
    ascii(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); ascii(8, 'WAVE');
    ascii(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    ascii(36, 'data'); view.setUint32(40, samples.length * 2, true);
    for (let index = 0; index < samples.length; index += 1) {
      const value = Math.max(-1, Math.min(1, samples[index]));
      view.setInt16(44 + index * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
    }
    return new Blob([buffer], {type: 'audio/wav'});
  }

  class MetisVoiceCatalogState {
    constructor() {
      this._request = 0;
      this._saved = null;
      this._touched = false;
    }

    beginRequest() {
      this._request += 1;
      return this._request;
    }

    accepts(request) {
      return request === this._request;
    }

    setSaved(voice) {
      if (!voice || typeof voice !== 'object') {
        this._saved = null;
        return;
      }
      this._saved = {
        engine: String(voice.engine || ''),
        voice_id: voice.voice_id ? String(voice.voice_id) : null
      };
    }

    markTouched() {
      this._touched = true;
    }

    preferred(currentProvider, currentVoice, serverProvider, serverVoice) {
      if (!this._touched && this._saved && this._saved.engine) return {...this._saved};
      return {
        engine: currentProvider || serverProvider || 'mock',
        voice_id: currentVoice || serverVoice || 'metis-counsel-mock'
      };
    }

    saved() {
      return this._saved ? {...this._saved} : null;
    }
  }

  global.MetisVoiceCapture = MetisVoiceCapture;
  global.MetisVoiceCatalogState = MetisVoiceCatalogState;
  if (typeof module !== 'undefined' && module.exports) module.exports = {MetisVoiceCapture, MetisVoiceCatalogState, STATES};
})(typeof window !== 'undefined' ? window : globalThis);
