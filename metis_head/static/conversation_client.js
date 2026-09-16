(function (root) {
  'use strict';

  class MetisConversationClient {
    constructor(fetchImpl, storage, clientIdFactory) {
      this.fetch = fetchImpl || root.fetch.bind(root);
      this.storage = storage || root.sessionStorage;
      this.clientIdFactory = clientIdFactory || (() => root.crypto.randomUUID());
      this.sessionId = null;
      // sessionStorage is copied when a tab is duplicated.  Reusing a stored
      // playback owner therefore lets one tab consume another tab's commands.
      // A client ID belongs to this document instance and is always fresh.
      this.clientId = this.clientIdFactory();
      this.storage.setItem('metis.client_id', this.clientId);
      this._sessionPromise = null;
      this._epoch = 0;
    }

    async ensureSession(context) {
      if (this.sessionId) return this.sessionId;
      if (!this._sessionPromise) {
        this._sessionPromise = (async () => {
          const response = await this.fetch('/metis/sessions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({client_id: this.clientId, context: context || {}})
          });
          const result = await response.json();
          if (!response.ok || !result.session_id) throw new Error(result.detail || 'Session creation failed');
          this.sessionId = result.session_id;
          return this.sessionId;
        })().finally(() => { this._sessionPromise = null; });
      }
      return this._sessionPromise;
    }

    async requestChat(message, modelOptions, context) {
      const epoch = this._epoch;
      const sessionId = await this.ensureSession(context);
      if (epoch !== this._epoch) throw new Error('Conversation request cancelled before dispatch.');
      const response = await this.fetch('/metis/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message, session_id: sessionId, options: modelOptions || {}})
      });
      const result = await response.json();
      if (epoch !== this._epoch) throw new Error('Conversation response ignored after cancellation.');
      if (response.status === 404) {
        this.sessionId = null;
        throw new Error('Conversation session expired. A new session is ready for your next message; the previous message was not replayed.');
      }
      if (!response.ok) throw new Error(result.detail || 'Chat failed');
      return result;
    }

    async cancel() {
      ++this._epoch;
      const sessionId = this.sessionId;
      if (!sessionId) {
        // If creation is already in flight, invalidate the request immediately
        // and cancel the late-created session without dispatching chat work.
        if (this._sessionPromise) {
          this._sessionPromise.then((created) => this._cancelSession(created)).catch(() => {});
        }
        return null;
      }
      return this._cancelSession(sessionId);
    }

    invalidateSession(expectedSessionId) {
      if (!expectedSessionId || this.sessionId === expectedSessionId) {
        ++this._epoch;
        this.sessionId = null;
      }
    }

    close() {
      ++this._epoch;
      if (!this.sessionId) {
        if (this._sessionPromise) {
          this._sessionPromise.then((created) => {
            if (this.sessionId === created) this.sessionId = null;
            this._closeSession(created);
          }).catch(() => {});
        }
        return;
      }
      const sessionId = this.sessionId;
      this.sessionId = null;
      this._closeSession(sessionId);
    }

    async _cancelSession(sessionId) {
      const response = await this.fetch(`/metis/sessions/${encodeURIComponent(sessionId)}/cancel`, {method: 'POST'});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Conversation cancellation failed');
      return result;
    }

    _closeSession(sessionId) {
      this.fetch(`/metis/sessions/${encodeURIComponent(sessionId)}`, {method: 'DELETE', keepalive: true}).catch(() => {});
    }
  }

  class MetisPlaybackController {
    constructor(fetchImpl, AudioType, options) {
      options = options || {};
      this.fetch = fetchImpl || root.fetch.bind(root);
      this.AudioType = AudioType || root.Audio;
      this.maxDrain = positiveInteger(options.maxDrain, 8);
      this.getSessionId = options.getSessionId || (() => null);
      this.isCommandCurrent = options.isCommandCurrent || ((command) => {
        const sessionId = this.getSessionId();
        return !sessionId || command.session_id === sessionId;
      });
      this.onStateChange = typeof options.onStateChange === 'function' ? options.onStateChange : function () {};
      this.current = null;
      this._epoch = 0;
    }

    async playNext(clientId) {
      const epoch = this._epoch;
      for (let count = 0; count < this.maxDrain; count += 1) {
        const response = await this.fetch(`/metis/playback/next?client_id=${encodeURIComponent(clientId)}`);
        if (!response.ok) throw new Error(`Playback queue request failed (${response.status}).`);
        const result = await response.json();
        if (epoch !== this._epoch) return null;
        const command = result.command;
        if (!command) return null;
        if (command.kind === 'stop') {
          this._stopMatching(command.playback_id);
          continue;
        }
        if (command.kind !== 'play') throw new Error('Unknown playback command.');
        if (!this.isCommandCurrent(command)) throw new Error('Playback command does not belong to the current turn.');
        if (epoch !== this._epoch) return null;
        return this._play(command, clientId, epoch);
      }
      throw new Error('Playback command drain limit reached.');
    }

    stop(reason) {
      ++this._epoch;
      const active = this.current;
      if (!active) return;
      this.current = null;
      active.settled = true;
      active.audio.onended = null;
      active.audio.onerror = null;
      try { active.audio.pause(); } catch (_) {}
      this._ack(active.command, active.clientId, 'failed', reason || 'client_stopped').catch(() => {});
      this._notify('failed', active.command, reason || 'client_stopped');
    }

    async resumeBlocked() {
      const active = this.current;
      if (!active || !active.blocked || active.settled) return null;
      try {
        await active.audio.play();
      } catch (error) {
        if (error && error.name === 'NotAllowedError') {
          this._notify('blocked', active.command, 'audio_play_rejected');
          return null;
        }
        await active.finish('failed', 'audio_play_rejected');
        return null;
      }
      return this._confirmStarted(active);
    }

    async _play(command, clientId, epoch) {
      const audio = new this.AudioType(command.audio_ref);
      const active = {audio, command, clientId, epoch, settled: false, started: false, blocked: false, pendingTerminal: null};
      this.current = active;
      this._notify('loading', command);
      const finish = async (state, failureCode) => {
        if (active.settled) return;
        if (!active.started && state !== 'failed') {
          active.pendingTerminal = {state, failureCode};
          return;
        }
        active.settled = true;
        if (this.current === active) this.current = null;
        await this._ack(command, clientId, state, failureCode);
        this._notify(state, command, failureCode);
      };
      active.finish = finish;
      audio.onended = () => { finish('completed').catch(() => {}); };
      audio.onerror = () => { finish('failed', 'audio_decode_failed').catch(() => {}); };
      try {
        await audio.play();
      } catch (error) {
        if (error && error.name === 'NotAllowedError') {
          active.blocked = true;
          this._notify('blocked', command, 'audio_play_rejected');
          return command;
        }
        await finish('failed', 'audio_play_rejected');
        return null;
      }
      return this._confirmStarted(active);
    }

    async _confirmStarted(active) {
      const {audio, command, clientId, epoch, finish} = active;
      if (epoch !== this._epoch || this.current !== active) {
        try { audio.pause(); } catch (_) {}
        await finish('failed', 'stale_playback');
        return null;
      }
      try {
        await this._ack(command, clientId, 'started');
      } catch (error) {
        active.settled = true;
        if (this.current === active) this.current = null;
        audio.onended = null;
        audio.onerror = null;
        try { audio.pause(); } catch (_) {}
        throw error;
      }
      active.started = true;
      active.blocked = false;
      this._notify('playing', command);
      if (active.pendingTerminal) {
        const pending = active.pendingTerminal;
        active.pendingTerminal = null;
        await finish(pending.state, pending.failureCode);
      }
      return command;
    }

    _stopMatching(playbackId) {
      const active = this.current;
      if (!active || active.command.playback_id !== playbackId) return;
      this.current = null;
      active.settled = true;
      active.audio.onended = null;
      active.audio.onerror = null;
      try { active.audio.pause(); } catch (_) {}
    }

    async _ack(command, clientId, state, failureCode) {
      const response = await this.fetch('/metis/playback/ack', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          playback_id: command.playback_id,
          client_id: clientId,
          state,
          failure_code: failureCode || null
        })
      });
      if (!response.ok) throw new Error(`Playback acknowledgement rejected (${response.status}).`);
      return response.json();
    }

    _notify(state, command, failureCode) {
      try { this.onStateChange({state, command, failure_code: failureCode || null}); } catch (_) {}
    }
  }

  function positiveInteger(value, fallback) {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
  }

  root.MetisConversationClient = MetisConversationClient;
  root.MetisPlaybackController = MetisPlaybackController;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {MetisConversationClient, MetisPlaybackController};
  }
})(typeof window !== 'undefined' ? window : globalThis);
