const { test } = require('node:test');
const assert = require('node:assert/strict');
const { settingsDraft, settingsPayload } = require('../.test-build/lib/dashboardSettings.js');

function settings() {
  return {
    enabled: true, dangerOnFireLabel: true, warnOnPriority: true, warnOnDue: true, warnOnDeadline: true,
    fireLabel: 'fire', fireLabels: [], warnPriorityThresholds: [],
    warnPriorityMinCount: 1, warnDueWithinDays: 0, warnDueMinCount: 1,
    warnDeadlineWithinDays: 0, warnDeadlineMinCount: 1, plotEvents: [], configPath: '/private/configs/dashboard.yaml'
  };
}

test('empty selections stay empty instead of silently restoring defaults', () => {
  const payload = settingsPayload(settingsDraft(settings()));
  assert.deepEqual(payload.fireLabels, []);
  assert.deepEqual(payload.warnPriorityThresholds, []);
  assert.equal(payload.fireLabel, '');
  assert.equal('configPath' in payload, false);
});
for (const value of ['', ' ', '-1', '1.5', 'Infinity', '1e2', '100001']) {
  test(`invalid numeric draft ${JSON.stringify(value)} never becomes a saved default`, () => {
    const draft = settingsDraft(settings()); draft.warnPriorityMinCount = value;
    assert.throws(() => settingsPayload(draft), /Minimum priority matches/);
  });
}
test('zero-day windows are valid but zero match thresholds are not', () => {
  const draft = settingsDraft(settings());
  assert.equal(settingsPayload(draft).warnDueWithinDays, 0);
  draft.warnDueMinCount = '0';
  assert.throws(() => settingsPayload(draft), /Minimum due matches/);
});
test('blank plot rows are omitted while incomplete events are reported', () => {
  const draft = settingsDraft(settings()); draft.plotEvents = [{date:'', label:'', color:'#ff6b7a'}];
  assert.deepEqual(settingsPayload(draft).plotEvents, []);
  draft.plotEvents[0].label = 'Launch';
  assert.throws(() => settingsPayload(draft), /both a date and a label/);
});
test('payload conversion leaves the editable draft untouched', () => {
  const draft = settingsDraft(settings()); const before = JSON.stringify(draft);
  settingsPayload(draft);
  assert.equal(JSON.stringify(draft), before);
});
