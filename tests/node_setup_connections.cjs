'use strict';

const assert = require('node:assert/strict');
const connections = require('../metis_head/static/setup_connections.js');

const accounts = Array.from({length: 6}, (_, index) => ({
  connection_id: `google:a${index}@example.test`,
  account_id: `a${index}@example.test`,
  scopes: ['calendar.readonly'],
  status: 'connected',
  selected_calendar_ids: index === 0 ? [] : [`calendar-${index}`]
}));
const existing = [{
  slot_id: 'profile_preserved',
  account_id: 'a0@example.test',
  label: 'Nursing',
  scopes: ['calendar.readonly'],
  status: 'verified',
  calendar_ids: []
}];

const first = connections.connectionViews(accounts, existing);
assert.equal(first.length, 6);
assert.equal(first[0].profile_id, 'profile_preserved');
assert.equal(first[0].label, 'Nursing');
assert.deepEqual(first[0].calendar_ids, []);
assert.equal(new Set(first.map((item) => item.profile_id)).size, 6);

const removed = connections.withoutAccount(first, 'a2@example.test');
assert.equal(removed.length, 5);
assert.deepEqual(
  removed.map((item) => item.account_id),
  ['a0@example.test', 'a1@example.test', 'a3@example.test', 'a4@example.test', 'a5@example.test']
);

const reloaded = connections.connectionViews(
  accounts.filter((item) => item.account_id !== 'a2@example.test'),
  removed.map((item) => ({
    slot_id: item.profile_id, account_id: item.account_id, label: item.label,
    calendar_ids: item.calendar_ids
  }))
);
assert.deepEqual(
  reloaded.map((item) => item.profile_id),
  removed.map((item) => item.profile_id)
);

console.log('setup connections ok');
