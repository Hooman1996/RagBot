const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const script = fs.readFileSync(path.join(__dirname, '..', 'static/js/kb_manager.js'), 'utf8');
const tick = () => new Promise((resolve) => setImmediate(resolve));

function makePage(canWrite, versions = [], options = {}) {
  const nodes = new Map();
  const created = [];
  const requests = [];
  const decode = (text) => text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#039;/g, "'").replace(/&amp;/g, '&');
  class Element {
    constructor(id = '') {
      this.id = id;
      this.children = [];
      this.handlers = {};
      this.html = '';
      this.value = '';
      this.classList = { add() {}, remove() {}, toggle() {} };
    }
    set innerHTML(value) {
      this.html = value; this.children = [];
      for (const match of value.matchAll(/<(input|textarea)\b[^>]*id="([^"]+)"[^>]*>/g)) {
        const node = new Element(match[2]);
        const attr = match[0].match(/value="([^"]*)"/);
        node.value = attr ? decode(attr[1]) : '';
        if (match[1] === 'textarea') node.value = decode(value.slice(match.index + match[0].length).split('</textarea>')[0]);
        nodes.set(node.id, node);
      }
    }
    get innerHTML() { return this.html; }
    appendChild(child) { this.children.push(child); }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    click() { this.handlers.click?.({ target: this }); }
    focus() { this.focused = true; }
    remove() {}
  }
  const ids = ['document-sidebar-list', 'chunks-workspace-wrapper', 'kb-search-input',
    'kb-search-trigger', 'global-toast', 'toast-text', 'history-modal-overlay',
    'history-versions-stack', 'close-history-modal'];
  if (canWrite) ids.push('add-chunk-modal-overlay', 'close-add-modal', 'submit-new-chunk-btn',
    'new-chunk-is-qa', 'new-chunk-qa-fields-wrapper', 'new-chunk-question',
    'new-chunk-answer', 'new-chunk-operator-name', 'new-chunk-main-category', 'new-chunk-sub-category');
  ids.forEach((id) => nodes.set(id, new Element(id)));
  const document = {
    body: { dataset: { canWrite: String(canWrite) } },
    addEventListener(name, handler) { if (name === 'DOMContentLoaded') this.ready = handler; },
    createElement() { const node = new Element(); created.push(node); return node; },
    getElementById(id) {
      if (id === 'history-btn-7' || (canWrite && /^(sync-btn-7|delete-btn-7|revert-btn-9|global-add-chunk-trigger)$/.test(id))) {
        if (!nodes.has(id)) nodes.set(id, new Element(id));
      }
      return nodes.get(id) || null;
    },
    querySelectorAll() { return created.filter((node) => node.className?.includes('sidebar-doc-node')); },
  };
  const chunk = options.chunk || { id: 7, chunk_index: 0, is_qa: true,
    question: 'Question', answer: 'Full answer\nsecond line', main_category: 'Synthetic', sub_category: 'Review' };
  const fetch = async (url, init) => ({ ok: true, json: async () => {
    if (init) {
      requests.push({ url, ...init, payload: JSON.parse(init.body) });
      return options.result || { success: true, answer: chunk.answer, main_category: chunk.main_category, sub_category: chunk.sub_category };
    }
    if (url.endsWith('/documents')) return { documents: [{ id: 3, title: 'Document' }] };
    if (url.endsWith('/versions')) return { versions };
    return { chunks: [chunk], has_more: false };
  } });
  vm.runInNewContext(script, { document, fetch, setTimeout, alert() {}, confirm() { return false; } });
  document.ready();
  return { nodes, created, document, requests };
}

test('read-only Knowledge Base renders full content and escaped version history without write controls', async () => {
  const attack = '<img src=x onerror=alert(1)>\nsecond line';
  const page = makePage(false, [{ id: 9, is_qa: true, question: attack,
    answer: attack, changed_by: 'Editor', created_at: '2026-09-27T10:00:00Z' },
    { id: 10, is_qa: false, answer: attack, changed_by: 'Editor', created_at: '2026-09-27T09:00:00Z' }]);
  await tick();
  page.created.find((node) => node.className.includes('sidebar-doc-node')).click();
  await tick();
  const card = page.created.find((node) => node.id === 'chunk-card-wrapper-7');
  assert.ok(card);
  assert.match(card.innerHTML, /Full answer\nsecond line/);
  assert.doesNotMatch(card.innerHTML, /<textarea|operator-field|sync-btn|delete-btn/);
  assert.match(page.nodes.get('chunks-workspace-wrapper').children[0].innerHTML, /فقط خواندنی/);
  page.nodes.get('history-btn-7').click();
  await tick();
  const row = page.nodes.get('history-versions-stack').children[0];
  assert.ok(row);
  assert.match(row.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;\nsecond line/);
  assert.doesNotMatch(row.innerHTML, /<img|revert-btn/);
  const rawRow = page.nodes.get('history-versions-stack').children[1];
  assert.match(rawRow.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;\nsecond line/);
  assert.doesNotMatch(rawRow.innerHTML, /<img|revert-btn/);
  assert.equal(page.document.body.dataset.canWrite, 'false');
});

test('editor Knowledge Base keeps add, edit, delete, and revert controls', async () => {
  const page = makePage(true, [{ id: 9, is_qa: false, answer: 'Previous', changed_by: 'Editor', created_at: '2026-09-27T10:00:00Z' }]);
  await tick();
  page.created.find((node) => node.className.includes('sidebar-doc-node')).click();
  await tick();
  const card = page.created.find((node) => node.id === 'chunk-card-wrapper-7');
  assert.match(card.innerHTML, /<textarea|operator-field|sync-btn|delete-btn/);
  assert.match(page.nodes.get('chunks-workspace-wrapper').children[0].innerHTML, /global-add-chunk-trigger/);
  page.nodes.get('history-btn-7').click();
  await tick();
  assert.match(page.nodes.get('history-versions-stack').children[0].innerHTML, /revert-btn-9/);
});

async function openDocument(page) {
  await tick();
  page.created.find(node => node.className.includes('sidebar-doc-node')).click();
  await tick();
}

test('taxonomy prefills safely and answer-only payload omits stale taxonomy', async () => {
  const page = makePage(true, [], { result: { success: true, answer: 'New answer', main_category: 'Concurrent', sub_category: 'New child' } });
  await openDocument(page);
  assert.equal(page.nodes.get('main-category-7').value, 'Synthetic');
  assert.equal(page.nodes.get('sub-category-7').value, 'Review');
  const card = page.created.find(node => node.id === 'chunk-card-wrapper-7');
  assert.match(card.innerHTML, /label for="main-category-7"/);
  assert.match(card.innerHTML, /dir="auto"/);
  page.nodes.get('target-field-7').value = 'New answer';
  page.nodes.get('sync-btn-7').click();
  await tick();
  const payload = page.requests[0].payload;
  assert.equal(payload.answer, 'New answer');
  assert.equal(Object.hasOwn(payload, 'main_category'), false);
  assert.equal(Object.hasOwn(payload, 'sub_category'), false);
  assert.equal(page.nodes.get('main-category-7').value, 'Concurrent');
  assert.equal(page.nodes.get('sub-category-7').value, 'New child');
});

test('parent change clears child, sends explicit changes, and invalid orphan is not sent', async () => {
  const page = makePage(true);
  await openDocument(page);
  const main = page.nodes.get('main-category-7');
  const sub = page.nodes.get('sub-category-7');
  main.value = 'Other'; main.handlers.input();
  assert.equal(sub.value, '');
  page.nodes.get('sync-btn-7').click(); await tick();
  assert.equal(page.requests[0].payload.main_category, 'Other');
  assert.equal(page.requests[0].payload.sub_category, null);
  main.value = ''; sub.value = 'Orphan';
  page.nodes.get('sync-btn-7').click(); await tick();
  assert.equal(page.requests.length, 1);
  assert.equal(main.focused, true);
  assert.match(page.nodes.get('toast-text').textContent, /دسته‌بندی/);
});

test('create uses explicit taxonomy only for FAQ and validates required parent', async () => {
  const page = makePage(true); await openDocument(page);
  const n = page.nodes;
  n.get('new-chunk-is-qa').value = 'true';
  n.get('new-chunk-question').value = 'Synthetic question';
  n.get('new-chunk-answer').value = 'Synthetic answer';
  n.get('new-chunk-main-category').value = 'Category';
  n.get('new-chunk-sub-category').value = 'Child';
  n.get('submit-new-chunk-btn').click(); await tick();
  assert.equal(page.requests[0].payload.main_category, 'Category');
  assert.equal(page.requests[0].payload.sub_category, 'Child');
  n.get('new-chunk-main-category').value = '';
  n.get('submit-new-chunk-btn').click(); await tick();
  assert.equal(page.requests.length, 1);
  n.get('new-chunk-is-qa').value = 'false';
  n.get('submit-new-chunk-btn').click(); await tick();
  assert.equal(Object.hasOwn(page.requests[1].payload, 'main_category'), false);
  n.get('new-chunk-is-qa').value = 'true';
  n.get('new-chunk-sub-category').value = '';
  n.get('new-chunk-answer').value = 'Synthetic answer\nquestion category: Legacy. sub_category: Child';
  n.get('submit-new-chunk-btn').click(); await tick();
  assert.equal(Object.hasOwn(page.requests[2].payload, 'main_category'), false);
  assert.equal(Object.hasOwn(page.requests[2].payload, 'sub_category'), false);
  assert.match(page.requests[2].payload.answer, /question category: Legacy/);
});

test('taxonomy and history are escaped, ambiguity blocks save, and historical absence is shown', async () => {
  const attack = '"><img src=x onerror=alert(1)>';
  const page = makePage(true, [{ id: 9, is_qa: true, question: 'Synthetic', answer: 'Fact', main_category: attack,
    sub_category: attack, changed_by: 'Test', created_at: '2026-10-13T00:00:00Z' }], {
    chunk: { id: 7, chunk_index: 0, is_qa: true, question: 'Synthetic', answer: 'Fact', main_category: attack,
      sub_category: attack, taxonomy_error: 'Conflicting entries' } });
  await openDocument(page);
  const card = page.created.find(node => node.id === 'chunk-card-wrapper-7');
  assert.doesNotMatch(card.innerHTML, /<img/);
  assert.match(card.innerHTML, /&lt;img/);
  assert.equal(page.nodes.get('sync-btn-7').disabled, true);
  page.nodes.get('sync-btn-7').click(); await tick();
  assert.equal(page.requests.length, 0);
  page.nodes.get('history-btn-7').click(); await tick();
  assert.doesNotMatch(page.nodes.get('history-versions-stack').children[0].innerHTML, /<img/);
});
