const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const script = fs.readFileSync(path.join(__dirname, '..', 'static/js/analytics.js'), 'utf8');

class Element {
  constructor(tag, document, id = '') {
    this.tagName = tag;
    this.document = document;
    this.id = id;
    this.children = [];
    this.className = '';
    this.style = {};
    this.attributes = {};
    this.hidden = false;
    this.textContent = '';
    this.parentElement = null;
    document.nodes.push(this);
  }
  appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
  replaceChildren(...children) { this.children.forEach((c) => { c.parentElement = null; }); this.children = []; children.forEach((c) => this.appendChild(c)); }
  insertAdjacentElement(_position, child) { this.parentElement.appendChild(child); }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter((c) => c !== this); this.parentElement = null; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener() {}
}

function makeDashboard(responseFactory) {
  const document = {
    nodes: [], readyState: 'complete',
    body: { classList: { contains: () => false } },
    createElement(tag) { return new Element(tag, this); },
    getElementById(id) { return this.nodes.find((n) => n.id === id); },
    querySelectorAll(selector) {
      if (selector === '.chart-message') return this.nodes.filter((n) => n.parentElement && n.className.includes('chart-message'));
      if (selector === '.chart-card canvas') return this.nodes.filter((n) => n.tagName === 'canvas');
      return [];
    },
  };
  const ids = ['timeRange', 'refreshAnalytics', 'analyticsStatus', 'analyticsTimezone', 'kpiRow',
    'queriesDayMeta', 'feedbackMeta', 'depthMeta', 'durationMeta', 'usersDayMeta', 'statesMeta',
    'weeklyMeta', 'heatmapMeta', 'heatmapContainer', 'heatmapSummary', 'heatmapDetails'];
  ids.forEach((id) => new Element('div', document, id));
  document.getElementById('timeRange').value = '7';
  for (const id of ['chartQueriesDay', 'chartFeedback', 'chartDepth', 'chartDuration', 'chartUsersDay', 'chartStates', 'chartWeekly']) {
    const card = new Element('div', document);
    card.className = 'chart-card';
    card.appendChild(new Element('canvas', document, id));
  }
  const charts = [];
  class Chart {
    constructor(canvas, config) { this.canvas = canvas; this.config = config; charts.push(this); }
    destroy() {}
  }
  const context = { document, Chart, fetch: responseFactory, window: { Chart }, console };
  vm.runInNewContext(script, context);
  return { document, charts, window: context.window };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));
function payload(total) {
  const labels = ['2026-09-21'];
  return {
    meta: { days: 7, timezone: 'UTC', start: '2026-09-21T00:00:00Z', end: '2026-09-27T10:00:00Z' },
    kpis: { total_queries: total, active_users: total, avg_completion_seconds: total ? 3 : null,
      completion_measured: total, completed_queries: total, rated_responses: 0, documents_indexed: 1 },
    queries_per_day: { labels, data: [total], total },
    users_per_day: { labels, data: [total], query_total: total },
    feedback_outcomes: { labels: ['Helpful', 'Unhelpful', 'No feedback'], data: [0, 0, total], rated_responses: 0, total_queries: total, other_values: 0 },
    conversation_depth: { labels: ['1', '2–4', '5–9', '10+'], data: [total ? 1 : 0, 0, 0, 0], sessions: total ? 1 : 0, queries_without_session: 0 },
    completion_duration: { labels: ['<2 s', '2–5 s', '5–10 s', '10–20 s', '20+ s'], data: [0, total, 0, 0, 0], measured: total, completed: total, excluded_completed: 0, unavailable_reason: total ? null : 'No completed queries with valid timestamps' },
    query_states: { labels: total ? ['completed'] : [], data: total ? [total] : [], total },
    weekly_comparison: { labels: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], current: [total, 0, 0, 0, 0, 0, 0], previous: [0, 0, 0, 0, 0, 0, 0], current_total: total, previous_total: 0 },
    heatmap: { weekdays: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], hours: Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, '0')}:00`), matrix: Array.from({ length: 7 }, (_, d) => Array.from({ length: 24 }, (_, h) => d === 0 && h === 0 ? total : 0)), weekday_totals: [total, 0, 0, 0, 0, 0, 0], total },
  };
}

test('new charts, rated denominator, and keyboard-readable heatmap render', async () => {
  const view = makeDashboard(async () => ({ ok: true, json: async () => payload(2) }));
  await tick();
  assert.equal(view.charts.length, 7);
  assert.deepEqual(view.charts.map((c) => c.canvas.id), ['chartQueriesDay', 'chartFeedback', 'chartDepth', 'chartDuration', 'chartUsersDay', 'chartStates', 'chartWeekly']);
  assert.match(view.document.getElementById('feedbackMeta').textContent, /0 rated responses \/ 2 queries/);
  assert.match(view.document.getElementById('analyticsTimezone').textContent, /Timezone: UTC/);
  assert.equal(view.document.getElementById('heatmapDetails').hidden, false);
  const table = view.document.getElementById('heatmapSummary').children[0];
  assert.equal(table.tagName, 'table');
  assert.equal(table.children.length, 9); // caption, header, seven weekdays
  assert.equal(table.children[2].children.length, 26); // weekday, 24 hours, total
});

test('empty activity, unavailable duration, and failed load remain distinct', async () => {
  let fail = false;
  const view = makeDashboard(async () => {
    if (fail) throw Error('network');
    return { ok: true, json: async () => payload(0) };
  });
  await tick();
  assert.equal(view.charts.length, 0);
  assert.equal(view.document.getElementById('heatmapDetails').hidden, true);
  assert.match(view.document.getElementById('chartDuration').parentElement.children.at(-1).textContent, /Unavailable:/);
  assert.match(view.document.getElementById('chartFeedback').parentElement.children.at(-1).textContent, /No query activity/);
  fail = true;
  await view.window._analyticsDashboard.reload();
  assert.match(view.document.getElementById('analyticsStatus').textContent, /could not be loaded/);
  assert.equal(view.document.getElementById('chartFeedback').parentElement.children.at(-1).className, 'chart-message chart-message--error');
});
