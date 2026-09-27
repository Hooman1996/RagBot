const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const script = fs.readFileSync(path.join(__dirname, '..', 'static/js/kb_manager.js'), 'utf8');
const tick = () => new Promise((resolve) => setImmediate(resolve));

function makePage(canWrite, versions) {
  const nodes = new Map();
  const created = [];
  class Element {
    constructor(id = '') {
      this.id = id;
      this.children = [];
      this.handlers = {};
      this.html = '';
      this.value = '';
      this.classList = { add() {}, remove() {}, toggle() {} };
    }
    set innerHTML(value) { this.html = value; this.children = []; }
    get innerHTML() { return this.html; }
    appendChild(child) { this.children.push(child); }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    click() { this.handlers.click?.({ target: this }); }
    remove() {}
  }
  const ids = ['document-sidebar-list', 'chunks-workspace-wrapper', 'kb-search-input',
    'kb-search-trigger', 'global-toast', 'toast-text', 'history-modal-overlay',
    'history-versions-stack', 'close-history-modal'];
  if (canWrite) ids.push('add-chunk-modal-overlay', 'close-add-modal', 'submit-new-chunk-btn',
    'new-chunk-is-qa', 'new-chunk-qa-fields-wrapper', 'new-chunk-question',
    'new-chunk-answer', 'new-chunk-operator-name');
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
  const fetch = async (url) => ({ json: async () => {
    if (url.endsWith('/documents')) return { documents: [{ id: 3, title: 'Document' }] };
    if (url.endsWith('/versions')) return { versions };
    return { chunks: [{ id: 7, chunk_index: 0, is_qa: true,
      question: 'Question', answer: 'Full answer\nsecond line' }], has_more: false };
  } });
  vm.runInNewContext(script, { document, fetch, setTimeout, alert() {}, confirm() { return false; } });
  document.ready();
  return { nodes, created, document };
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
