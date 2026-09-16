(function () {
  'use strict';

  let snapshot = null;
  const byId = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
  const browserFetch = window.fetch.bind(window);

  async function json(url, options) {
    const response = await browserFetch(url, options);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || 'Request failed'));
    }
    return data;
  }

  const conversation = new MetisConversationClient(browserFetch, sessionStorage, () => crypto.randomUUID());
  const playback = new MetisPlaybackController(browserFetch, Audio, {
    getSessionId: () => conversation.sessionId,
    onStateChange: (event) => {
      const retry = byId('retryPlayback');
      retry.hidden = event.state !== 'blocked';
      if (event.state === 'blocked') {
        byId('audioStatus').textContent = 'Browser playback was blocked. Click Play blocked audio.';
      } else if (event.state === 'playing') {
        byId('audioStatus').textContent = 'Browser playback started. Confirm separately whether it is audible.';
      } else if (event.state === 'completed') {
        byId('audioStatus').textContent = 'Browser playback completed. This does not by itself prove the speakers were audible.';
      } else if (event.state === 'failed') {
        byId('audioStatus').textContent = `Browser playback failed: ${event.failure_code || 'unknown playback error'}`;
      }
    }
  });
  const audio = new MetisAudioSetupController({
    onStatus: (state) => {
      const waiting = state.state === 'speaker_awaiting_confirmation';
      byId('heardYes').disabled = !waiting;
      byId('heardNo').disabled = !waiting;
      if (state.state.startsWith('speaker_')) byId('audioStatus').textContent = state.message;
      if (state.state.startsWith('microphone_')) byId('micStatus').textContent = state.message;
      byId('micLevel').value = state.inputLevel || 0;
    },
    onTranscript: (text) => { byId('transcript').textContent = text; },
    transcribe: async (blob) => {
      const form = new FormData();
      form.append('audio', blob, 'setup-mic.wav');
      form.append('stt_provider', byId('stt').value);
      return json('/metis/setup/audio/transcribe', {method: 'POST', body: form});
    }
  });

  async function load() {
    snapshot = await json('/metis/setup');
    byId('build').textContent = `Build ${snapshot.build.build_id} · ${snapshot.build.branch}`;
    renderProviders();
    renderModels();
    renderConnections();
    byId('projects').textContent = snapshot.readiness.projects?.detail
      || snapshot.readiness.boh?.detail
      || 'Optional project helpers are not verified in this setup run.';
  }

  function renderProviders() {
    byId('providers').innerHTML = snapshot.providers.providers.map((provider) =>
      `<label><input type="radio" name="provider" value="${esc(provider.id)}" `
      + `${provider.id === snapshot.setup.provider.choice ? 'checked' : ''} ${provider.selectable ? '' : 'disabled'}>`
      + ` <strong>${esc(provider.label)}</strong> — ${esc(provider.summary)}<br>`
      + `<span class="muted">${esc(provider.billing.notice)}`
      + `${provider.selectable ? '' : ` Unavailable: ${esc(provider.limitations.join(' '))}`}</span></label>`
    ).join('');
  }

  function renderModels() {
    const select = byId('model');
    const models = snapshot.llm_options?.ollama?.models || [];
    select.innerHTML = models.map((model) => `<option>${esc(model.name || model)}</option>`).join('');
    if (snapshot.setup.provider.model) {
      if (![...select.options].some((option) => option.value === snapshot.setup.provider.model)) {
        select.add(new Option(snapshot.setup.provider.model));
      }
      select.value = snapshot.setup.provider.model;
    }
  }

  function renderConnections() {
    const accounts = snapshot.connections || [];
    const mappings = snapshot.setup.google_profiles.filter((profile) => profile.account_id);
    const usedSlots = new Set(mappings.map((profile) => profile.slot_id));
    const freeSlots = snapshot.setup.google_profiles.filter((profile) => !usedSlots.has(profile.slot_id));
    const cards = accounts.map((account, index) => {
      const mapped = mappings.find((profile) => profile.account_id === account.account_id);
      const slot = mapped || freeSlots.shift();
      if (!slot) return '';
      const label = mapped?.label || `Google account ${index + 1}`;
      return `<div class="profile" data-slot="${esc(slot.slot_id)}" data-account="${esc(account.account_id)}">`
        + `<label>Label<input class="label" value="${esc(label)}"></label>`
        + `<div><strong>Verified identity</strong><br>${esc(account.account_id)}</div>`
        + `<div class="muted">${esc(account.status)} · ${(account.scopes || []).length} read grant(s) · `
        + `${(account.selected_calendar_ids || []).length} selected calendar(s)</div>`
        + `<button type="button" class="removeConnection">Remove connection</button></div>`;
    }).filter(Boolean);
    byId('profiles').innerHTML = cards.length ? cards.join('') : '<p>No Google accounts connected.</p>';
    document.querySelectorAll('.removeConnection').forEach((button) => {
      button.addEventListener('click', () => removeConnection(button.closest('.profile')));
    });
    byId('profileStatus').textContent = accounts.length
      ? `${accounts.length} verified connection(s). Mention a label in chat; Metis will use that exact account set or ask when unclear.`
      : 'No Google accounts are connected. Choose a Desktop OAuth client JSON and click Connect Google account.';
  }

  function makePatch(completed) {
    const profileUpdates = {};
    snapshot.setup.google_profiles.forEach((profile, index) => {
      profileUpdates[profile.slot_id] = {
        label: `Google connection ${index + 1}`,
        account_id: null,
        status: 'not_connected',
        scopes: [],
        calendar_ids: [],
        last_verification: null
      };
    });
    const assignedSlots = [];
    document.querySelectorAll('.profile[data-account]').forEach((card) => {
      const account = card.dataset.account;
      const connection = (snapshot.connections || []).find((item) => item.account_id === account);
      profileUpdates[card.dataset.slot] = {
        label: card.querySelector('.label').value,
        account_id: account,
        status: 'verified',
        scopes: connection?.scopes || [],
        calendar_ids: connection?.selected_calendar_ids || [],
        last_verification: {
          timestamp: new Date().toISOString(), device: null, provider: 'google', model: null,
          status: 'verified', error_code: null
        }
      };
      assignedSlots.push(card.dataset.slot);
    });
    const defaultSlot = assignedSlots[0] || 'profile_1';
    return {
      provider: {
        choice: document.querySelector('input[name="provider"]:checked')?.value || 'ollama',
        model: byId('model').value || null,
        status: 'unverified',
        last_verification: null
      },
      google_profiles: profileUpdates,
      profile_selection: {mode: 'default', default_slot_id: defaultSlot, active_slot_ids: [defaultSlot]},
      wizard: {completed: Boolean(completed), completed_version: completed ? '1' : null}
    };
  }

  async function patchSetup(patch) {
    const data = await json('/metis/setup', {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({patch, expected_revision: snapshot.setup.revision})
    });
    snapshot.setup = data.setup;
    return data;
  }

  async function save(completed) {
    try {
      await patchSetup(makePatch(completed));
      byId('saveStatus').textContent = completed
        ? 'Setup saved. Open Metis and run the final live conversation check.'
        : 'Progress saved.';
      renderConnections();
    } catch (error) {
      byId('saveStatus').textContent = String(error);
    }
  }

  async function connectGoogle() {
    const popup = window.open('about:blank', 'metisGoogleOAuth', 'width=640,height=760');
    if (!popup) {
      byId('profileStatus').textContent = 'The Google sign-in window was blocked. Allow popups for this local page and retry.';
      return;
    }
    popup.document.body.textContent = 'Preparing secure Google sign-in…';
    try {
      const form = new FormData();
      const file = byId('googleClientFile').files[0];
      if (file) form.append('client_secrets', file, file.name);
      const result = await json('/metis/connectors/google/oauth/start', {method: 'POST', body: form});
      byId('profileStatus').textContent = 'Complete Google sign-in and read-only consent in the opened window.';
      popup.location.replace(result.authorization_url);
    } catch (error) {
      popup.close();
      byId('profileStatus').textContent = `Google connection could not start: ${String(error)}`;
    }
  }

  async function removeConnection(card) {
    const account = card?.dataset.account;
    if (!account || !window.confirm(`Remove the Google connection labeled “${card.querySelector('.label').value}”?`)) return;
    try {
      const response = await browserFetch(`/metis/connectors/google/accounts/${encodeURIComponent(account)}`, {method: 'DELETE'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Connection removal failed');
      await patchSetup({google_profiles: {
        [card.dataset.slot]: {
          label: 'Google connection', account_id: null, status: 'not_connected', scopes: [],
          calendar_ids: [], last_verification: null
        }
      }});
      await load();
    } catch (error) {
      byId('profileStatus').textContent = String(error);
    }
  }

  byId('speakerTest').onclick = () => audio.playSpeakerTest();
  byId('heardYes').onclick = async () => {
    audio.confirmSpeakerAudible(true);
    try {
      await patchSetup({voice: {last_verification: {
        timestamp: new Date().toISOString(), device: 'browser default output', provider: 'web_audio',
        model: null, status: 'verified', error_code: null
      }}});
    } catch (error) { byId('audioStatus').textContent += ` Verification could not be saved: ${String(error)}`; }
  };
  byId('heardNo').onclick = async () => {
    audio.confirmSpeakerAudible(false);
    try { await patchSetup({voice: {last_verification: null}}); } catch (_) {}
  };
  byId('micStart').onclick = async () => {
    const state = await audio.startMicrophoneTest();
    const recording = state.state === 'microphone_recording';
    byId('micStart').disabled = recording;
    byId('micStop').disabled = !recording;
    byId('micCancel').disabled = !recording;
  };
  byId('micStop').onclick = async () => {
    await audio.stopMicrophoneTest();
    byId('micStart').disabled = false; byId('micStop').disabled = true; byId('micCancel').disabled = true;
  };
  byId('micCancel').onclick = async () => {
    await audio.cancelMicrophoneTest();
    byId('micStart').disabled = false; byId('micStop').disabled = true; byId('micCancel').disabled = true;
  };
  byId('speechPreview').onclick = async () => {
    try {
      const sessionId = await conversation.ensureSession({});
      const voice = snapshot.setup.voice;
      await json('/metis/voice/preview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          session_id: sessionId, client_id: conversation.clientId, text: 'Metis voice preview.',
          provider: voice.engine,
          voice_id: voice.voice_id || (voice.engine === 'piper' ? 'piper-local' : null),
          enabled: true,
          allow_piper: voice.engine === 'piper', piper_playback: false
        })
      });
      byId('audioStatus').textContent = 'Speech synthesized and queued; starting browser playback…';
      await playback.playNext(conversation.clientId);
    } catch (error) { byId('audioStatus').textContent = `Speech preview failed: ${String(error)}`; }
  };
  byId('retryPlayback').onclick = () => playback.resumeBlocked();
  byId('testProvider').onclick = async () => {
    try {
      const model = byId('model').value;
      const data = await json('/metis/llm/health', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({provider: 'ollama', model})
      });
      byId('providerStatus').textContent = JSON.stringify(data, null, 2);
      const ok = (data.reachable === true && data.model_available === true)
        || data.available === true || data.status === 'ready' || data.status === 'available';
      await patchSetup({provider: {status: ok ? 'verified' : 'error', model: model || null, last_verification: {
        timestamp: new Date().toISOString(), device: null, provider: 'ollama', model: model || null,
        status: ok ? 'verified' : 'error', error_code: ok ? null : 'provider_probe_failed'
      }}});
    } catch (error) { byId('providerStatus').textContent = String(error); }
  };
  byId('addGoogle').onclick = connectGoogle;
  byId('reload').onclick = load;
  byId('save').onclick = () => save(false);
  byId('finish').onclick = () => save(true);
  window.addEventListener('message', async (event) => {
    if (event.origin === window.location.origin && event.data === 'metis-google-connected') await load();
  });
  window.addEventListener('pagehide', () => { audio.cancelMicrophoneTest(); conversation.close(); });
  load().catch((error) => { byId('saveStatus').textContent = String(error); });
})();
