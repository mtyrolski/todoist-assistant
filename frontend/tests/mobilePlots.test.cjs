const { test } = require('node:test');
const assert = require('node:assert/strict');

process.env.TZ = 'Europe/Warsaw';
const { weekDate, mobileHistoryEnd, completionFigure } = require('../.test-build/lib/mobile.js');
const { calendarCompletionFigure, eventsFigure, hierarchyFigure, lifespanFigure, paceWindowAvailable, weeklyPaceFigure } = require('../.test-build/lib/mobilePlots.js');

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

test('weekly charts distinguish years and label each point with its full week-ending date', () => {
  const shortHistory = model();
  assert.equal(completionFigure(shortHistory, 8, []).layout.xaxis.tickformat, '%b %-d');
  const longHistory = model({
    weekStart: '2021-01-04',
    syncedAt: '2021-01-05T12:00:00Z',
    weeks: Array(60).fill(1),
    weeklyProjects: Array.from({ length: 60 }, () => ({ Work: 1 })),
    plotData: { ...shortHistory.plotData, historyStart: '2019-11-01', historyAsOf: '2021-01-05' },
  });
  assert.equal(completionFigure(longHistory, 4, []).layout.xaxis.tickformat, '%d %b\n%Y');
  for (const cumulative of [false, true]) {
    const figure = completionFigure(longHistory, 0, [], cumulative);
    assert.equal(figure.layout.xaxis.tickformat, '%b %Y');
    assert.ok(figure.data.every((trace) => trace.hovertemplate.includes('Week ending %{x|%d %b %Y}')));
    assert.equal(figure.data[0].x[0], '2019-11-24');
    assert.equal(figure.data[0].x.at(-1), '2021-01-03');
  }
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

test('deep project hierarchy keeps all completions while initially limiting visible depth', () => {
  const value = model();
  value.plotData.hierarchy = [
    { id: 'root', name: 'Work', parentId: '', rootName: 'Work', weeklyCounts: { 8: 3 } },
    { id: 'child', name: 'Child', parentId: 'root', rootName: 'Work', weeklyCounts: { 8: 2 } },
    { id: 'grandchild', name: 'Grandchild', parentId: 'child', rootName: 'Work', weeklyCounts: { 8: 1 } },
  ];
  const figure = hierarchyFigure(value, 0), trace = figure.data[0];
  assert.equal(trace.maxdepth, 2);
  assert.equal(trace.values.reduce((sum, count) => sum + count, 0), 6);
  assert.ok(trace.ids.includes('project:grandchild'));
  assert.equal(trace.parents[trace.ids.indexOf('project:grandchild')], 'project:child');
  assert.equal(figure.layout.uniformtext.mode, 'hide');
});

test('lifespan duration buckets include each valid completion exactly once at boundaries', () => {
  const value = model();
  const durations = [0.5, 59, 60, 3599, 3600, 86399, 86400, 7 * 86400, 28 * 86400, 365 * 86400];
  value.plotData.lifespans = durations.map((seconds) => ({ completedAt: '2020-11-03', seconds }));
  value.plotData.lifespans.push(...[0, -1, NaN, Infinity].map((seconds) => ({ completedAt: '2020-11-03', seconds })));
  const trace = lifespanFigure(value, 0, true).data[0];
  assert.equal(trace.orientation, 'h');
  assert.deepEqual(trace.x, [2, 2, 2, 1, 1, 1, 1]);
  assert.equal(trace.x.reduce((sum, count) => sum + count, 0), durations.length);
  assert.deepEqual(trace.y, ['Under 1 min', '1–59 min', '1–23 hours', '1–6 days', '1–<4 weeks', '4 weeks–<1 year', '1+ year']);
});

test('lifespan range uses completion dates and never includes future or invalid durations', () => {
  const value = model();
  value.plotData.lifespans = [
    { completedAt: '2020-08-01', seconds: 5 },
    { completedAt: '2020-10-31', seconds: 3600 },
    { completedAt: '2020-11-03', seconds: 86400 },
    { completedAt: '2020-11-05', seconds: 60 },
  ];
  assert.deepEqual(lifespanFigure(value, 1, false).data[0].x, [0, 0, 0, 1, 0, 0, 0]);
  assert.deepEqual(lifespanFigure(value, 1, true).data[0].x, [1, 0, 1, 1, 0, 0, 0]);
});

test('lifespan count axis uses whole-number ticks for small samples', () => {
  const value = model();
  value.plotData.lifespans = [{ completedAt: '2020-11-03', seconds: 60 }];
  assert.equal(lifespanFigure(value, 0, true).layout.xaxis.dtick, 1);
  value.plotData.lifespans = Array.from({ length: 100 }, () => ({ completedAt: '2020-11-03', seconds: 60 }));
  assert.equal(lifespanFigure(value, 0, true).layout.xaxis.dtick, undefined);
});

test('weekly pace renders the percentile band without duplicate markers', () => {
  const value = model();
  value.plotData.dailyActivity = [day('2020-10-20', 3, { Work: 3 }), day('2020-11-02', 1, { Work: 1 })];
  const traces = weeklyPaceFigure(value, 3).data;
  assert.equal(traces[0].mode, 'lines');
  assert.equal(traces[1].mode, 'lines');
  assert.equal(traces[2].mode, 'lines+markers');
  assert.equal(traces.at(-1).customdata[0], 1);
  assert.equal(traces.at(-1).customdata[3], null);
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
