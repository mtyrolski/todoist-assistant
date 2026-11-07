const { test } = require('node:test');
const assert = require('node:assert/strict');

process.env.TZ = 'Europe/Warsaw';
const { weekDate, mobileHistoryEnd, completionFigure } = require('../.test-build/lib/mobile.js');
const { calendarCompletionFigure, eventsFigure, hierarchyFigure, paceWindowAvailable } = require('../.test-build/lib/mobilePlots.js');

function model(overrides = {}) {
  return {
    syncedAt: '2020-11-04T12:00:00Z', weekStart: '2020-11-02',
    weeks: [1, 1, 1, 1, 1, 1, 1, 1, 0], priorities: [0, 0, 0, 0],
    forecast: 0, forecastAvailable: true, historyAvailable: true, historyWarning: '',
    weeklyProjects: Array.from({ length: 9 }, () => ({ Work: 1 })),
    projectForecasts: {}, projectColors: {}, tasks: [], projects: [], activity: [],
    plotData: { historyComplete: true, historyStart: '2020-09-01', historyAsOf: '2020-11-04', dailyActivity: [], lifespans: [], hierarchy: [], taskCounts: [] },
    ...overrides,
  };
}

function day(date, effectiveCompletions, projects, counts = {}) {
  return { date, effectiveCompletions, ...(projects === undefined ? {} : { projects }), counts, hours: Array(24).fill(0) };
}

test('date-only week arithmetic survives daylight-saving and skipped local dates', () => {
  assert.equal(weekDate('2020-03-23', 1), '2020-03-30');
  assert.equal(weekDate('2020-10-19', 1), '2020-10-26');
  process.env.TZ = 'Pacific/Apia';
  try { assert.equal(weekDate('2011-12-26', 0, 4), '2011-12-30'); }
  finally { process.env.TZ = 'Europe/Warsaw'; }
});

test('history end respects exclusive local midnights and excludes past partial days across DST', () => {
  assert.equal(mobileHistoryEnd(model({ activitySyncedAt: '2020-03-29T22:00:00Z' })), '2020-03-29');
  assert.equal(mobileHistoryEnd(model({ activitySyncedAt: '2020-03-29T10:00:00Z' })), '2020-03-28');
  assert.equal(mobileHistoryEnd(model({ activitySyncedAt: '2020-10-25T23:00:00Z' })), '2020-10-25');
  assert.equal(mobileHistoryEnd(model({ activitySyncedAt: '2020-10-25T10:00:00Z' })), '2020-10-24');
  assert.equal(mobileHistoryEnd(model()), '2020-11-04'); // Legacy snapshots have a date-only inclusive bound.
});

test('incomplete history without a start never displays fabricated zeroes or a forecast', () => {
  for (const start of ['', '0000', '2020-02-30']) {
    const value = model(); value.plotData.historyComplete = false; value.plotData.historyStart = start;
    const traces = completionFigure(value, 8, []).data;
    assert.ok(traces.every((trace) => trace.y.every((number) => number === null)));
    assert.equal(paceWindowAvailable(value, 3), false);
  }
});

test('a partially refreshed past week is not represented as a completed week', () => {
  const value = model({ activitySyncedAt: '2020-10-28T10:00:00Z' });
  const traces = completionFigure(value, 8, []).data;
  const total = traces.find((trace) => trace.name === 'All projects');
  assert.equal(total.y.at(-1), null);
  assert.equal(total.y.at(-2), 1);
  assert.equal(traces.some((trace) => trace.line?.dash === 'dash'), false);
});

test('an invalid history end does not expose values or forecasts', () => {
  const value = model(); value.plotData.historyAsOf = 'invalid';
  const traces = completionFigure(value, 8, []).data;
  assert.ok(traces.every((trace) => trace.y.every((number) => number === null)));
  assert.equal(traces.some((trace) => trace.line?.dash === 'dash'), false);
});

test('calendar totals use completion counts and distinguish missing project attribution', () => {
  const value = model();
  value.plotData.historyAsOf = '2020-11-30';
  value.plotData.dailyActivity = [day('2020-11-02', 4, { Work: 2 }), day('2020-10-15', 3)];
  const traces = calendarCompletionFigure(value, 0, 'month', false).data;
  assert.deepEqual(traces.find((trace) => trace.name === 'All projects').y, [3, 4]);
  assert.deepEqual(traces.find((trace) => trace.name === 'Work').y, [0, 2]);
  assert.deepEqual(traces.find((trace) => trace.name === 'Unattributed').y, [3, 2]);
});

test('invalid project breakdown cannot exceed actual completion totals', () => {
  const value = model(); value.plotData.historyAsOf = '2020-11-30'; value.plotData.dailyActivity = [day('2020-11-02', 2, { Work: 20 })];
  const traces = calendarCompletionFigure(value, 0, 'month', false).data;
  assert.deepEqual(traces.find((trace) => trace.name === 'All projects').y, [2]);
  assert.deepEqual(traces.find((trace) => trace.name === 'Unattributed').y, [2]);
  assert.equal(traces.some((trace) => trace.name === 'Work'), false);
});

test('calendar charts leave partial historical periods blank instead of implying complete totals', () => {
  const value = model();
  value.plotData.historyComplete = false; value.plotData.historyStart = '2020-10-15'; value.plotData.historyAsOf = '2020-12-05';
  value.plotData.dailyActivity = [day('2020-10-15', 3, { Work: 3 }), day('2020-11-02', 4, { Work: 4 }), day('2020-12-02', 5, { Work: 5 })];
  const total = calendarCompletionFigure(value, 0, 'month', false).data.find((trace) => trace.name === 'All projects');
  assert.deepEqual(total.y, [null, 4, null]);
});

test('project hierarchy excludes a historical week that is only partially refreshed', () => {
  const value = model({ activitySyncedAt: '2020-10-28T10:00:00Z' });
  value.plotData.hierarchy = [{ id: 'work', name: 'Work', parentId: '', rootName: 'Work', color: 'blue', archived: false, createdAt: '2020-01-01', lastEventAt: '', archivedAt: '', weeklyCounts: { 6: 2, 7: 5 } }];
  const figure = hierarchyFigure(value, 0);
  assert.deepEqual(figure.data[0].values, [2]);
});

test('event smoothing orders data by local date, filling missing days with zero', () => {
  const value = model();
  value.plotData.dailyActivity = [day('2020-11-03', 0, {}, { added: 3 }), day('2020-11-01', 0, {}, { added: 1 })];
  const added = eventsFigure(value, 0).data.find((trace) => trace.name === 'Added');
  assert.deepEqual(added.x, ['2020-11-01', '2020-11-02', '2020-11-03', '2020-11-04']);
  assert.deepEqual(added.y, [1, 0.5, 4 / 3, 1]);
});

test('pace options require covered weeks with a usable baseline', () => {
  const value = model();
  value.plotData.historyComplete = false; value.plotData.historyStart = '2020-10-26';
  value.plotData.dailyActivity = [day('2020-10-27', 2, { Work: 2 })];
  assert.equal(paceWindowAvailable(value, 3), true);
  assert.equal(paceWindowAvailable(value, 6), false);
});

test('an empty account shows an empty chart instead of invented activity', () => {
  const value = model();
  const figure = calendarCompletionFigure(value, 0, 'month', false);
  assert.deepEqual(figure.data, []);
  assert.match(figure.layout.annotations[0].text, /No completed tasks/);
});

test('a large account retains every recorded completion across complete months', () => {
  const value = model();
  const start = Date.parse('2000-01-01T00:00:00Z'), end = Date.parse('2009-12-31T00:00:00Z');
  for (let timestamp = start; timestamp <= end; timestamp += 86400000)
    value.plotData.dailyActivity.push(day(new Date(timestamp).toISOString().slice(0, 10), 1, { Work: 1 }));
  value.plotData.historyAsOf = '2009-12-31';
  const total = calendarCompletionFigure(value, 0, 'month', false).data.find((trace) => trace.name === 'All projects');
  assert.equal(total.y.reduce((sum, count) => sum + count, 0), value.plotData.dailyActivity.length);
});
