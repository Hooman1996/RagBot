const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const servedBundle = process.env.ANALYTICS_SERVED_BUNDLE
  ? JSON.parse(fs.readFileSync(process.env.ANALYTICS_SERVED_BUNDLE, 'utf8')) : null;
const script = servedBundle?.script || fs.readFileSync(path.join(__dirname, '..', 'static/js/analytics.js'), 'utf8');

const escapeText = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const VOID_TAGS = new Set(['img']);

class Element {
  constructor(tag, document, id = '', register = true) {
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
    this.dataset = {};
    const classes = new Set();
    this.classes = classes;
    this.classList = { add: (value) => classes.add(value), remove: (value) => classes.delete(value), contains: (value) => classes.has(value) };
    this.listeners = {};
    if (register) document.nodes.push(this);
  }
  appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
  replaceChildren(...children) { this.children.forEach((c) => { c.parentElement = null; }); this.children = []; children.forEach((c) => this.appendChild(c)); }
  insertAdjacentElement(_position, child) { this.parentElement.appendChild(child); }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter((c) => c !== this); this.parentElement = null; }
  setAttribute(key, value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  click() { this.listeners.click?.(); }
  replaceWith(node) {
    const parent = this.parentElement;
    parent.children = parent.children.map((c) => (c === this ? node : c));
    node.parentElement = parent;
    this.parentElement = null;
  }
  cloneNode(deep) {
    const copy = new Element(this.tagName, this.document, this.id, false);
    Object.assign(copy, { className: this.className, hidden: this.hidden, textContent: this.textContent,
      attributes: { ...this.attributes }, dataset: { ...this.dataset }, style: { ...this.style } });
    this.classes.forEach((value) => copy.classList.add(value));
    if (deep) this.children.forEach((child) => copy.appendChild(child.cloneNode(true)));
    return copy;
  }
  matches(selector) {
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    if (selector.startsWith('.')) return this.className.split(' ').includes(selector.slice(1)) || this.classList.contains(selector.slice(1));
    return this.tagName === selector;
  }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  get outerHTML() {
    const classes = [this.className, ...this.classes].filter(Boolean).join(' ');
    const attrs = { ...(this.id ? { id: this.id } : {}), ...(classes ? { class: classes } : {}), ...this.attributes,
      ...(this.hidden ? { hidden: '' } : {}) };
    const open = `<${this.tagName}${Object.entries(attrs).map(([k, v]) => ` ${k}="${escapeText(v)}"`).join('')}>`;
    if (VOID_TAGS.has(this.tagName)) return open;
    return `${open}${escapeText(this.textContent)}${this.children.map((c) => c.outerHTML).join('')}</${this.tagName}>`;
  }
}

function makeDashboard(responseFactory, options = {}) {
  const document = {
    nodes: [], readyState: 'complete',
    body: {
      className: 'light-mode', classList: { contains: () => false }, appended: [],
      appendChild(child) { this.appended.push(child); return child; }, removeChild(child) { return child; },
    },
    styleSheets: [
      { cssRules: [{ cssText: '.kpi-card { color: red; }' }, { cssText: '@font-face { font-family: Test; src: url(test.woff2); }' }] },
      { get cssRules() { throw new Error('SecurityError'); } },
    ],
    createElement(tag) { return new Element(tag, this); },
    createElementNS(_namespace, tag) { return new Element(tag, this); },
    getElementById(id) { return this.nodes.find((n) => n.id === id); },
    querySelectorAll(selector) {
      if (selector === '.chart-message') return this.nodes.filter((n) => n.parentElement && n.className.includes('chart-message'));
      if (selector === '.chart-card canvas') return this.nodes.filter((n) => n.tagName === 'canvas');
      return [];
    },
  };
  const ids = ['analyticsRoot', 'timeRange', 'refreshAnalytics', 'exportSnapshot', 'exportCsv', 'analyticsStatus', 'analyticsTimezone', 'kpiRow',
    'queriesDayMeta', 'feedbackMeta', 'depthMeta', 'durationMeta', 'usersDayMeta', 'statesMeta',
    'weeklyMeta', 'heatmapMeta', 'heatmapContainer', 'heatmapSummary', 'heatmapDetails'];
  ids.filter((id) => !options.omitNewNodes || !['analyticsStatus', 'heatmapSummary', 'heatmapDetails'].includes(id))
    .forEach((id) => new Element('div', document, id));
  const root = document.getElementById('analyticsRoot');
  for (const id of ids.slice(5)) { const node = document.getElementById(id); if (node) root.appendChild(node); }
  for (const id of ['exportSnapshot', 'exportCsv']) document.getElementById(id).disabled = true;
  document.getElementById('timeRange').value = '7';
  document.getElementById('analyticsRoot').dataset.analyticsContract = options.contract || 'main-analytics/v3';
  document.getElementById('analyticsRoot').dataset.iconsUrl = '/static/_v/test/icons.svg';
  for (const id of options.cardIds || ['chartQueriesDay', 'chartFeedback', 'chartDepth', 'chartDuration', 'chartUsersDay', 'chartStates', 'chartWeekly']) {
    const card = new Element('div', document);
    card.className = 'chart-card';
    const title = card.appendChild(new Element('p', document));
    title.className = 'chart-card__title';
    title.appendChild(new Element('svg', document)).setAttribute('aria-hidden', 'true');
    title.textContent = `Title ${id}`;
    const canvas = card.appendChild(new Element('canvas', document, id));
    canvas.toDataURL = () => 'data:image/png;base64,AAAA';
    root.appendChild(card);
  }
  const charts = [];
  class Chart {
    constructor(canvas, config) {
      if (canvas.id === options.chartErrorId) throw new Error("synthetic Chart.js failure");
      this.canvas = canvas; this.config = config; charts.push(this);
    }
    destroy() {}
  }
  const errors = [];
  const safeConsole = { error: (...args) => errors.push(args) };
  const blobs = [], urls = { created: [], revoked: [] };
  class Blob { constructor(parts, opts = {}) { this.parts = parts; this.type = opts.type; blobs.push(this); } }
  const URL = { createObjectURL: (blob) => { urls.created.push(blob); return 'blob:test'; },
    revokeObjectURL: (url) => { urls.revoked.push(url); } };
  const context = { document, Chart, fetch: responseFactory, window: { Chart }, console: safeConsole, Blob, URL };
  vm.runInNewContext(script, context);
  return { document, charts, errors, window: context.window, blobs, urls };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));
function payload(total) {
  const labels = ['2026-09-21'];
  return {
    meta: { contract_version: 'main-analytics/v3', days: 7, timezone: 'UTC', start: '2026-09-21T00:00:00Z', end: '2026-09-27T10:00:00Z' },
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
  const cards = view.document.getElementById('kpiRow').children;
  assert.equal(cards.length, 5);
  assert.equal(cards.filter((card) => card.children[0].tagName === 'svg' && card.children[0].attributes['aria-hidden'] === 'true').length, 5);
  assert.deepEqual(view.charts.map((c) => c.canvas.id), ['chartQueriesDay', 'chartFeedback', 'chartDepth', 'chartDuration', 'chartUsersDay', 'chartStates', 'chartWeekly']);
  assert.match(view.document.getElementById('feedbackMeta').textContent, /0 rated responses \/ 2 queries/);
  assert.match(view.document.getElementById('analyticsTimezone').textContent, /Timezone: UTC/);
  assert.equal(view.window._analyticsDashboard.contractVersion, 'main-analytics/v3');
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


test('HTML or API contract mismatch shows one actionable error', async () => {
  let fetched = false;
  const staleHtml = makeDashboard(async () => { fetched = true; return { ok: true, json: async () => payload(2) }; }, { contract: 'old-contract' });
  await tick();
  assert.equal(fetched, false);
  assert.equal(staleHtml.charts.length, 0);
  assert.equal(staleHtml.document.getElementById('analyticsRoot').classList.contains('contract-mismatch'), true);
  assert.match(staleHtml.document.getElementById('analyticsStatus').textContent, /Reload this page/);
  const olderHtml = makeDashboard(async () => { throw Error('should not fetch'); }, { contract: 'old-contract', omitNewNodes: true });
  await tick();
  assert.match(olderHtml.document.getElementById('analyticsStatus').textContent, /Reload this page/);
  const oldApi = payload(2);
  oldApi.meta.contract_version = 'old-contract';
  const staleApi = makeDashboard(async () => ({ ok: true, json: async () => oldApi }));
  await tick();
  assert.equal(staleApi.charts.length, 0);
  assert.equal(staleApi.document.getElementById('analyticsRoot').classList.contains('contract-mismatch'), true);
  assert.match(staleApi.document.getElementById('analyticsStatus').textContent, /version mismatch/);
});

test('chart construction failure names the card and leaves other cards visible', async () => {
  const view = makeDashboard(async () => ({ ok: true, json: async () => payload(2) }), { chartErrorId: 'chartFeedback' });
  await tick();
  assert.equal(view.charts.length, 6);
  assert.match(view.document.getElementById('chartFeedback').parentElement.children.at(-1).textContent, /could not be rendered/);
  assert.ok(view.errors.some((args) => args.includes('chartFeedback')));
  assert.ok(view.charts.some((chart) => chart.canvas.id === 'chartWeekly'));
});

if (servedBundle) {
  test('render path uses served HTML, versioned JS, and actual API contract for populated and empty data', async () => {
    assert.match(servedBundle.html, /data-analytics-contract="main-analytics\/v3"/);
    assert.deepEqual(servedBundle.cardIds, ['chartQueriesDay', 'chartFeedback', 'chartDepth', 'chartDuration', 'chartUsersDay', 'chartStates', 'chartWeekly']);
    for (const [data, populated] of [[servedBundle.populated, true], [servedBundle.empty, false]]) {
      assert.equal(data.meta.contract_version, 'main-analytics/v3');
      const view = makeDashboard(async () => ({ ok: true, json: async () => data }), { cardIds: servedBundle.cardIds });
      await tick();
      const weekly = view.document.getElementById('chartWeekly');
      const heatmap = view.document.getElementById('heatmapContainer');
      if (populated) {
        assert.ok(data.kpis.total_queries > 0);
        assert.equal(view.charts.length, 7);
        assert.equal(view.document.getElementById('heatmapDetails').hidden, false);
        assert.equal(view.document.getElementById('heatmapSummary').children[0].tagName, 'table');
        assert.ok(view.charts.some((chart) => chart.canvas.id === weekly.id));
      } else {
        assert.equal(data.kpis.total_queries, 0);
        assert.equal(view.charts.length, 0);
        assert.match(weekly.parentElement.children.at(-1).textContent, /No query activity/);
        assert.match(heatmap.children[0].textContent, /No query activity/);
      }
      assert.doesNotMatch(view.document.getElementById('analyticsStatus').textContent, /version mismatch|could not be loaded/);
    }
  });
}

if (servedBundle) {
  test('served HTML bootstrap rejects stale or missing browser script', () => {
    for (const dashboard of [undefined, { reload() {} }]) {
      const classes = new Set();
      const root = { dataset: { analyticsContract: 'main-analytics/v3' },
        classList: { add: (value) => classes.add(value) } };
      const status = { textContent: '' };
      const document = { getElementById: (id) => id === 'analyticsRoot' ? root : status };
      const errors = [];
      vm.runInNewContext(servedBundle.bootstrap, {
        document, window: { _analyticsDashboard: dashboard },
        console: { error: (...args) => errors.push(args) },
      });
      assert.equal(classes.has('contract-mismatch'), true);
      assert.match(status.textContent, /Reload this page/);
      assert.equal(errors.length, 1);
    }
  });
}


test('all reporting windows request their own data and keep populated cards visible', async () => {
  const urls = [];
  const view = makeDashboard(async (url) => { urls.push(url); return { ok: true, json: async () => payload(2) }; });
  await tick();
  for (const days of ['14', '30']) {
    view.document.getElementById('timeRange').value = days;
    await view.window._analyticsDashboard.reload();
    assert.equal(view.document.getElementById('kpiRow').children.length, 5);
    assert.equal(view.charts.length, 7 * (urls.length)); // Chart mocks record each successful render.
  }
  assert.deepEqual(urls, ['/api/analytics?days=7', '/api/analytics?days=14', '/api/analytics?days=30']);
});

const ok = (data) => async () => ({ ok: true, json: async () => data });
const csvRows = (text) => text.slice(1).split('\r\n').filter(Boolean);
const csvCells = (row) => row.match(/("([^"]|"")*"|[^,]*)(,|$)/g).filter((cell, i, all) => i < all.length - 1 || cell !== '');
const exportDisabled = (view) => ['exportSnapshot', 'exportCsv'].map((id) => view.document.getElementById(id).disabled);

test('export buttons are enabled only while the rendered data matches the screen', async () => {
  let release, fail = false;
  const view = makeDashboard(async () => {
    if (fail) throw Error('network');
    await new Promise((resolve) => { release = resolve; });
    return { ok: true, json: async () => payload(2) };
  });
  await tick();
  assert.deepEqual(exportDisabled(view), [true, true]);
  release();
  await tick(); await tick();
  assert.deepEqual(exportDisabled(view), [false, false]);
  fail = true;
  await view.window._analyticsDashboard.reload();
  assert.deepEqual(exportDisabled(view), [true, true]);
  const staleHtml = makeDashboard(ok(payload(2)), { contract: 'old-contract' });
  await tick();
  assert.deepEqual(exportDisabled(staleHtml), [true, true]);
  const oldApi = payload(2);
  oldApi.meta.contract_version = 'old-contract';
  const staleApi = makeDashboard(ok(oldApi));
  await tick();
  assert.deepEqual(exportDisabled(staleApi), [true, true]);
});

test('CSV holds every card number in order with a BOM and four cells per row', async () => {
  const view = makeDashboard(ok(payload(2)));
  await tick();
  const csv = view.window._analyticsDashboard.analyticsCsv(payload(2));
  assert.equal(csv[0], '﻿');
  const rows = csvRows(csv);
  assert.equal(rows[0], 'section,label,series,value');
  assert.equal(rows.length - 1, 5 + 7 + 1 + 1 + 3 + 4 + 5 + 1 + 14 + 168);
  rows.forEach((row) => assert.equal(csvCells(row).length, 4, row));
  assert.ok(rows.includes('heatmap,Monday,00:00,2'));
  assert.ok(rows.includes('weekly_comparison,Monday,Current 7 days,2'));
  assert.ok(rows.includes('weekly_comparison,Monday,Previous 7 days,0'));
  assert.ok(rows.includes('meta,contract_version,,main-analytics/v3'));
  assert.ok(csv.includes('\r\n') && !/[^\r]\n/.test(csv));
});

test('CSV of an empty window keeps every row with zero counts', () => {
  const view = makeDashboard(ok(payload(0)));
  const rows = csvRows(view.window._analyticsDashboard.analyticsCsv(payload(0)));
  assert.equal(rows.length - 1, 5 + 7 + 1 + 1 + 3 + 4 + 5 + 0 + 14 + 168);
  assert.ok(rows.includes('kpis,avg_completion_seconds,,'));
  assert.ok(rows.includes('kpis,total_queries,,0'));
  assert.ok(rows.includes('heatmap,Monday,00:00,0'));
});

test('CSV quotes separators and neutralises formula text but not numbers', () => {
  const view = makeDashboard(ok(payload(2)));
  const data = payload(2);
  data.query_states.labels = ['=SUM(A1),"x"'];
  data.query_states.data = [-5];
  const rows = csvRows(view.window._analyticsDashboard.analyticsCsv(data));
  assert.ok(rows.includes('query_states,"\'=SUM(A1),""x""",Queries,-5'));
});

test('snapshot is a self-contained offline copy of the rendered dashboard', async () => {
  let fetches = 0;
  const view = makeDashboard(async () => { fetches += 1; return { ok: true, json: async () => payload(2) }; });
  await tick();
  const html = view.window._analyticsDashboard.analyticsSnapshot();
  assert.ok(html.startsWith('<!DOCTYPE html>'));
  assert.ok(html.includes(`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">`));
  assert.equal((html.match(/<img[^>]*src="data:image\/png;base64,/g) || []).length, 7);
  assert.ok(html.includes('alt="Title chartWeekly"'));
  for (const banned of ['<canvas', '<svg', '<script', 'http://', 'https://', 'id="analyticsStatus"'])
    assert.equal(html.includes(banned), false, banned);
  assert.ok(html.includes('.kpi-card { color: red; }'));
  assert.ok(html.indexOf('html, body { height: auto !important; overflow: visible !important; }') > html.indexOf('.kpi-card { color: red; }'));
  assert.equal(html.includes('@font-face'), false);
  assert.ok(html.includes('RagBot analytics – 7 days (UTC)'));
  assert.ok(html.includes('<body class="light-mode">'));
  assert.ok(/id="heatmapDetails"[^>]*open=""/.test(html));
  assert.equal(fetches, 1);
  assert.equal(view.document.getElementById('chartWeekly').tagName, 'canvas');
});

test('snapshot of an empty window keeps the empty messages and has no images', async () => {
  const view = makeDashboard(ok(payload(0)));
  await tick();
  const html = view.window._analyticsDashboard.analyticsSnapshot();
  assert.equal(html.includes('<img'), false);
  assert.equal(html.includes('<canvas'), false);
  assert.ok(html.includes('No query activity in this period.'));
});

test('export buttons download named files from loaded data without fetching', async () => {
  let fetches = 0;
  const view = makeDashboard(async () => { fetches += 1; return { ok: true, json: async () => payload(2) }; });
  await tick();
  const status = view.document.getElementById('analyticsStatus');
  view.document.getElementById('exportCsv').click();
  assert.equal(view.blobs.length, 1);
  assert.equal(view.blobs[0].type, 'text/csv;charset=utf-8');
  assert.equal(view.document.body.appended.at(-1).download, 'ragbot-analytics-7d-2026-09-27.csv');
  assert.equal(view.document.body.appended.at(-1).href, 'blob:test');
  assert.deepEqual([view.urls.created.length, view.urls.revoked.length], [1, 1]);
  assert.equal(status.textContent, 'CSV exported for 7 days in UTC.');
  view.document.getElementById('exportSnapshot').click();
  assert.equal(view.blobs.length, 2);
  assert.equal(view.blobs[1].type, 'text/html;charset=utf-8');
  assert.ok(view.blobs[1].parts[0].startsWith('<!DOCTYPE html>'));
  assert.equal(view.document.body.appended.at(-1).download, 'ragbot-analytics-7d-2026-09-27.html');
  assert.deepEqual([view.urls.created.length, view.urls.revoked.length], [2, 2]);
  assert.deepEqual(view.urls.revoked, ['blob:test', 'blob:test']);
  assert.equal(status.textContent, 'Snapshot exported for 7 days in UTC.');
  assert.equal(fetches, 1);
  assert.equal(view.errors.length, 0);
});

test('clicking export after a failed load creates no file', async () => {
  let fail = false;
  const view = makeDashboard(async () => {
    if (fail) throw Error('network');
    return { ok: true, json: async () => payload(2) };
  });
  await tick();
  fail = true;
  await view.window._analyticsDashboard.reload();
  view.document.getElementById('exportCsv').click();
  view.document.getElementById('exportSnapshot').click();
  assert.equal(view.blobs.length, 0);
  assert.equal(view.urls.created.length, 0);
});
