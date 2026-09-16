(function (global) {
  'use strict';

  const AUDIO_SETUP_STATES = Object.freeze({
    IDLE: 'idle',
    SPEAKER_PLAYING: 'speaker_playing',
    SPEAKER_AWAITING_CONFIRMATION: 'speaker_awaiting_confirmation',
    SPEAKER_CONFIRMED: 'speaker_confirmed',
    SPEAKER_NOT_HEARD: 'speaker_not_heard',
    SPEAKER_ERROR: 'speaker_error',
    MICROPHONE_STARTING: 'microphone_starting',
    MICROPHONE_RECORDING: 'microphone_recording',
    MICROPHONE_TRANSCRIBING: 'microphone_transcribing',
    MICROPHONE_COMPLETE: 'microphone_complete',
    MICROPHONE_ERROR: 'microphone_error'
  });

  class MetisAudioSetupController {
    constructor(options) {
      options = options || {};
      this.global = options.global || global;
      this.AudioContextType = options.AudioContext || this.global.AudioContext || this.global.webkitAudioContext;
      this.mediaDevices = options.mediaDevices || (this.global.navigator && this.global.navigator.mediaDevices);
      this.VoiceCaptureType = options.VoiceCapture || this.global.MetisVoiceCapture;
      this.captureFactory = options.captureFactory || null;
      this.captureOptions = options.captureOptions || {};
      this.transcribe = options.transcribe;
      this.onStatus = typeof options.onStatus === 'function' ? options.onStatus : function () {};
      this.onTranscript = typeof options.onTranscript === 'function' ? options.onTranscript : function () {};
      this.durationMs = boundedNumber(options.durationMs, 350, 100, 1000);
      this.frequencyHz = boundedNumber(options.frequencyHz, 660, 120, 1600);
      this.gain = boundedNumber(options.gain, 0.035, 0.005, 0.08);
      this.setTimer = options.setTimeout || this.global.setTimeout.bind(this.global);
      this.clearTimer = options.clearTimeout || this.global.clearTimeout.bind(this.global);
      this.state = AUDIO_SETUP_STATES.IDLE;
      this.message = 'Audio setup has not started.';
      this.transcript = '';
      this.inputLevel = null;
      this.capture = null;
      this._speakerAttempt = 0;
      this._microphoneAttempt = 0;
    }

    checkCapabilities() {
      const secureContext = this.global.isSecureContext !== false;
      const audioOutput = typeof this.AudioContextType === 'function';
      const microphone = Boolean(
        secureContext &&
        this.mediaDevices &&
        typeof this.mediaDevices.getUserMedia === 'function' &&
        (this.captureFactory || typeof this.VoiceCaptureType === 'function')
      );
      return Object.freeze({
        secureContext,
        audioOutput,
        microphone,
        mediaDevices: Boolean(this.mediaDevices && typeof this.mediaDevices.getUserMedia === 'function'),
        inputLevelAvailable: Boolean(this.VoiceCaptureType || this.captureFactory)
      });
    }

    snapshot() {
      return Object.freeze({
        state: this.state,
        message: this.message,
        transcript: this.transcript,
        inputLevel: this.inputLevel,
        capabilities: this.checkCapabilities()
      });
    }

    async playSpeakerTest() {
      const capabilities = this.checkCapabilities();
      if (!capabilities.audioOutput) {
        return this._setState(AUDIO_SETUP_STATES.SPEAKER_ERROR, 'Browser audio output is unavailable.');
      }
      if (this.state === AUDIO_SETUP_STATES.SPEAKER_PLAYING) return this.snapshot();

      const attempt = ++this._speakerAttempt;
      this._setState(AUDIO_SETUP_STATES.SPEAKER_PLAYING, 'Playing a short, low-volume speaker test…');
      let context = null;
      let timer = null;
      try {
        // This method must be invoked directly by a click/tap handler so resume() is
        // covered by a user gesture. It intentionally does not use autoplay or URLs.
        context = new this.AudioContextType();
        if (typeof context.resume === 'function' && context.state === 'suspended') await context.resume();
        const oscillator = context.createOscillator();
        const gainNode = context.createGain();
        const startAt = Number(context.currentTime) || 0;
        const stopAt = startAt + this.durationMs / 1000;
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(this.frequencyHz, startAt);
        gainNode.gain.setValueAtTime(0.0001, startAt);
        gainNode.gain.exponentialRampToValueAtTime(this.gain, startAt + 0.02);
        gainNode.gain.exponentialRampToValueAtTime(0.0001, Math.max(startAt + 0.03, stopAt - 0.03));
        oscillator.connect(gainNode);
        gainNode.connect(context.destination);

        await new Promise((resolve, reject) => {
          let finished = false;
          const finish = (error) => {
            if (finished) return;
            finished = true;
            if (timer !== null) this.clearTimer(timer);
            error ? reject(error) : resolve();
          };
          oscillator.onended = () => finish();
          timer = this.setTimer(() => finish(), this.durationMs + 250);
          try {
            oscillator.start(startAt);
            oscillator.stop(stopAt);
          } catch (error) {
            finish(error);
          }
        });
        if (attempt !== this._speakerAttempt) return this.snapshot();
        return this._setState(
          AUDIO_SETUP_STATES.SPEAKER_AWAITING_CONFIRMATION,
          'The browser completed the tone. Confirm whether you actually heard it.'
        );
      } catch (error) {
        if (attempt !== this._speakerAttempt) return this.snapshot();
        return this._setState(AUDIO_SETUP_STATES.SPEAKER_ERROR, speakerErrorMessage(error), error);
      } finally {
        if (timer !== null) this.clearTimer(timer);
        if (context && context.state !== 'closed' && typeof context.close === 'function') {
          try { await context.close(); } catch (_) {}
        }
      }
    }

    confirmSpeakerAudible(heard) {
      if (this.state !== AUDIO_SETUP_STATES.SPEAKER_AWAITING_CONFIRMATION) {
        return this._setState(
          AUDIO_SETUP_STATES.SPEAKER_ERROR,
          'Run the speaker test before recording an audibility result.'
        );
      }
      if (heard === true) {
        return this._setState(AUDIO_SETUP_STATES.SPEAKER_CONFIRMED, 'You confirmed that the speaker tone was audible.');
      }
      return this._setState(
        AUDIO_SETUP_STATES.SPEAKER_NOT_HEARD,
        'The tone was not heard. Check the selected output device, volume, mute state, and browser audio permission, then retry.'
      );
    }

    async startMicrophoneTest() {
      const capabilities = this.checkCapabilities();
      if (!capabilities.secureContext) {
        return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, 'Microphone access requires a secure browser context.');
      }
      if (!capabilities.mediaDevices) {
        return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, 'Browser microphone access is unavailable.');
      }
      if (!this.captureFactory && typeof this.VoiceCaptureType !== 'function') {
        return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, 'The local voice capture component is unavailable.');
      }
      if (this.capture) return this.snapshot();

      const attempt = ++this._microphoneAttempt;
      this.transcript = '';
      this.inputLevel = null;
      this._setState(AUDIO_SETUP_STATES.MICROPHONE_STARTING, 'Requesting microphone access…');
      const options = Object.assign({}, this.captureOptions, {
        mediaDevices: this.mediaDevices,
        authorize: this.captureOptions.authorize || (async () => ({status: 'ptt_pressed'})),
        cleanup: this.captureOptions.cleanup || (async () => {}),
        onStatus: (message) => {
          if (attempt === this._microphoneAttempt) this._captureStatus(message);
        },
        onLevel: (level) => {
          if (attempt !== this._microphoneAttempt) return;
          this.inputLevel = boundedNumber(level, 0, 0, 1);
          this.onStatus(this.snapshot());
        }
      });
      try {
        this.capture = this.captureFactory
          ? this.captureFactory(options)
          : new this.VoiceCaptureType(options);
        const capture = this.capture;
        const started = await capture.start();
        if (attempt !== this._microphoneAttempt || this.capture !== capture) {
          if (started && typeof capture.cancel === 'function') {
            try { await capture.cancel(); } catch (_) {}
          }
          return this.snapshot();
        }
        if (!started) {
          this.capture = null;
          const reason = this.message && this.message !== 'Requesting microphone access…'
            ? this.message
            : 'Microphone capture did not start.';
          this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, reason);
          return this.snapshot();
        }
        return this._setState(
          AUDIO_SETUP_STATES.MICROPHONE_RECORDING,
          'Microphone is recording locally. Speak a short phrase, then stop.'
        );
      } catch (error) {
        if (attempt !== this._microphoneAttempt) return this.snapshot();
        this.capture = null;
        return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, microphoneErrorMessage(error), error);
      }
    }

    async stopMicrophoneTest() {
      if (!this.capture) {
        return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, 'Start the microphone test before stopping it.');
      }
      const capture = this.capture;
      const attempt = this._microphoneAttempt;
      this.capture = null;
      try {
        const wav = await capture.stop();
        if (attempt !== this._microphoneAttempt) return this.snapshot();
        if (!wav) {
          return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, 'No microphone audio was captured.');
        }
        if (typeof this.transcribe !== 'function') {
          return this._setState(
            AUDIO_SETUP_STATES.MICROPHONE_ERROR,
            'Audio was captured, but the bounded speech-to-text test is unavailable.'
          );
        }
        this._setState(AUDIO_SETUP_STATES.MICROPHONE_TRANSCRIBING, 'Checking the captured phrase with speech-to-text…');
        const result = await this.transcribe(wav);
        if (attempt !== this._microphoneAttempt) return this.snapshot();
        const transcript = normalizeTranscript(result);
        if (!transcript) {
          return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, 'Speech-to-text returned no recognized phrase.');
        }
        this.transcript = transcript;
        this.onTranscript(transcript, result);
        return this._setState(AUDIO_SETUP_STATES.MICROPHONE_COMPLETE, 'Microphone and speech-to-text test completed.');
      } catch (error) {
        if (attempt !== this._microphoneAttempt) return this.snapshot();
        return this._setState(AUDIO_SETUP_STATES.MICROPHONE_ERROR, microphoneErrorMessage(error), error);
      }
    }

    async cancelMicrophoneTest() {
      ++this._microphoneAttempt;
      const capture = this.capture;
      this.capture = null;
      if (capture && typeof capture.cancel === 'function') {
        try { await capture.cancel(); } catch (_) {}
      }
      return this._setState(AUDIO_SETUP_STATES.IDLE, 'Microphone test cancelled.');
    }

    _captureStatus(message) {
      if (!message) return;
      this.message = String(message);
      this.onStatus(this.snapshot());
    }

    _setState(state, message, error) {
      this.state = state;
      this.message = message;
      const snapshot = this.snapshot();
      this.onStatus(snapshot, error || null);
      return snapshot;
    }
  }

  function boundedNumber(value, fallback, minimum, maximum) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.min(maximum, Math.max(minimum, parsed));
  }

  function normalizeTranscript(result) {
    if (typeof result === 'string') return result.trim();
    if (!result || typeof result !== 'object') return '';
    const value = result.transcript !== undefined ? result.transcript : result.text;
    return typeof value === 'string' ? value.trim() : '';
  }

  function speakerErrorMessage(error) {
    if (error && error.name === 'NotAllowedError') return 'Browser audio was blocked. Click the test button again and allow audio.';
    return 'The browser could not play the speaker test tone.';
  }

  function microphoneErrorMessage(error) {
    if (error && error.name === 'NotAllowedError') return 'Microphone permission was denied.';
    if (error && error.message) return `Microphone test failed: ${error.message}`;
    return 'The microphone test failed.';
  }

  global.MetisAudioSetupController = MetisAudioSetupController;
  global.MetisAudioSetupStates = AUDIO_SETUP_STATES;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {MetisAudioSetupController, AUDIO_SETUP_STATES, normalizeTranscript};
  }
})(typeof window !== 'undefined' ? window : globalThis);
