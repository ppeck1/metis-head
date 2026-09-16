(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MetisSetupConnections = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function stableId(value) {
    const text = String(value || 'google');
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return `google_${(hash >>> 0).toString(16).padStart(8, '0')}`;
  }

  function connectionViews(accounts, profiles) {
    const configured = Array.isArray(profiles) ? profiles : [];
    const usedIds = new Set(configured.map((profile) => profile.slot_id));
    return (Array.isArray(accounts) ? accounts : []).map((account, index) => {
      const existing = configured.find((profile) => profile.account_id === account.account_id);
      let profileId = existing?.slot_id || stableId(account.connection_id || `google:${account.account_id}`);
      let suffix = 2;
      while (!existing && usedIds.has(profileId)) profileId = `${stableId(account.connection_id)}_${suffix++}`;
      usedIds.add(profileId);
      return {
        profile_id: profileId,
        account_id: account.account_id,
        label: existing?.label || `Google account ${index + 1}`,
        scopes: account.scopes || [],
        status: account.status || 'connected',
        calendar_ids: [...(existing?.calendar_ids || account.selected_calendar_ids || [])]
      };
    });
  }

  function withoutAccount(views, accountId) {
    return views.filter((view) => view.account_id !== accountId);
  }

  return {stableId, connectionViews, withoutAccount};
});
