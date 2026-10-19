/* Synthetic DOM contracts for the coverage check page; fixture JSON only, not a rendered browser test. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const ui = require('../static/js/knowledge_coverage.js');

class Element {
    constructor(tag, document) { this.tagName = tag.toUpperCase(); this.document = document; this.children = []; this.dataset = {}; this.listeners = {}; this.attributes = {}; this.value = ''; this.hidden = false; this.checked = false; this.disabled = false; this.textContent = ''; this._id = ''; this.className = ''; }
    set id(value) { this._id = value; if (value) this.document.ids.set(value, this); }
    get id() { return this._id; }
    append(...items) { this.children.push(...items); }
    replaceChildren(...items) { this.children = items; }
    setAttribute(key, value) { this.attributes[key] = value; }
    getAttribute(key) { return this.attributes[key]; }
    addEventListener(name, listener) { this.listeners[name] = listener; }
    dispatch(name, extra = {}) { return this.listeners[name]?.({ preventDefault() {}, ...extra }); }
    querySelectorAll(selector) {
        const found = [];
        const visit = n => { if (n.tagName === 'INPUT' && selector === 'input:checked' && n.checked) found.push(n); (n.children || []).forEach(visit); };
        this.children.forEach(visit); return found;
    }
}
const text = element => (element.textContent || '') + (element.children || []).map(text).join('');
const find = (element, predicate) => predicate(element) ? element : (element.children || []).map(c => find(c, predicate)).find(Boolean);

function dom(canStart) {
    const document = { ids: new Map(), createElement(tag) { return new Element(tag, this); }, getElementById(id) { return this.ids.get(id); } };
    const html = fs.readFileSync('templates/knowledge_coverage.html', 'utf8');
    [...html.matchAll(/id="(coverage[^"]+)"/g)].forEach(m => { document.createElement('div').id = m[1]; });
    document.body = { classList: { values: new Set(), add(v) { this.values.add(v); }, toggle(v) { if (this.values.has(v)) { this.values.delete(v); return false; } this.values.add(v); return true; } } };
    document.getElementById('coverageRoot').dataset = { canStart: String(canStart), uploadLimit: '5242880' };
    document.getElementById('coverageKeep').value = '50';
    document.getElementById('coverageBatchSize').value = '5';
    return document;
}

const RUN = 'c_' + 'a'.repeat(32);
const FIXTURE = {
    checks: [{ run_id: RUN, created_at: '2026-01-01T10:00:00.000+00:00', file_name: 'synthetic.csv', row_count: 3, done: 2, state: 'running' }],
    detail: { meta: { run_id: RUN }, done: 2, counts: { answered: 1, answered_combined: 0, partial: 0, not_answered: 0, chitchat: 1, error: 0, waiting: 1 } },
    rows: { total: 3, offset: 0, rows: [
        { row: 1, id: 'q1', question: '<img src=x onerror=alert(1)> سوال آزمایشی', result: 'answered', answer_batch: 2, answer_phase: 'initial',
          answer_chunks: [{ chunk_id: 'k7', title: 'عنوان آزمایشی هفت' }],
          batches: [{ number: 1, phase: 'initial', verdict: 'none', chunks: [{ chunk_id: 'k1', title: 'عنوان یک' }, { chunk_id: 'k2', title: null }] },
                    { number: 2, phase: 'initial', verdict: 'complete', chunks: [{ chunk_id: 'k7', title: 'عنوان آزمایشی هفت' }] }],
          combines: [], model_calls: 2, duration_ms: 900, error_code: null, note: 'synthetic note' },
        { row: 2, id: 'q2', question: 'سلام', result: 'chitchat', answer_batch: null, answer_phase: null, answer_chunks: [], batches: [], combines: [], model_calls: 0, duration_ms: 5, error_code: null, note: null },
        { row: 3, id: 'q3', question: 'منتظر', result: null, answer_batch: null, answer_phase: null, answer_chunks: [], batches: [], combines: [], model_calls: null, duration_ms: null, error_code: null, note: null }
    ] },
    documents: { documents: [{ name: 'Synthetic_FAQ', category: 'FAQ' }, { name: 'Synthetic_Policies', category: 'Policy' }], count: 2 }
};

test('"= N batches of M" line', () => {
    assert.equal(ui.batchLine(50, 5), '= 10 batches of 5');
    assert.equal(ui.batchLine(50, 10), '= 5 batches of 10');
    assert.equal(ui.batchLine(5, 5), '= 1 batch of 5');
    assert.equal(ui.batchLine(50, 20), '= 3 batches of 20 (last has 10)');
    assert.equal(ui.batchLine('', 5), '');
});

test('counts, rows as text, batch detail and the start payload', async () => {
    const document = dom(true), $ = name => document.getElementById('coverage' + name);
    const requests = [], timers = [];
    const saved = { fetch: global.fetch, localStorage: global.localStorage, setInterval: global.setInterval, clearInterval: global.clearInterval };
    global.localStorage = { getItem() { return null; }, setItem() {} };
    global.setInterval = fn => { timers.push(fn); return timers.length; }; global.clearInterval = () => {};
    global.fetch = async (url, options = {}) => {
        requests.push({ url, options });
        const path = url.replace('/api/knowledge-coverage/', '');
        let value;
        if (path === 'documents') value = FIXTURE.documents;
        else if (path === 'checks' && options.method === 'POST') value = { run_id: RUN };
        else if (path === 'checks') value = FIXTURE.checks;
        else if (path.includes('/rows?')) value = FIXTURE.rows;
        else value = FIXTURE.detail;
        return { ok: true, json: async () => value };
    };
    try {
        const booted = await ui.boot(document);
        await new Promise(resolve => setImmediate(resolve));
        assert.equal($('BatchLine').textContent, '= 10 batches of 5');
        $('BatchSize').value = '10'; $('BatchSize').dispatch('input');
        assert.equal($('BatchLine').textContent, '= 5 batches of 10');
        assert.equal($('BroaderDepth').disabled, true);
        $('Broader').checked = true; $('Broader').dispatch('change');
        assert.equal($('BroaderDepth').disabled, false);
        assert.equal($('Documents').querySelectorAll('input:checked').length, 2);
        assert.match(text($('Checks')), /synthetic\.csv/); assert.match(text($('Checks')), /2\/3/);
        assert.equal(timers.length, 1, 'polls while a run is running');

        await booted.actions.open(RUN);
        assert.equal($('Results').hidden, false);
        const counts = text($('Counts'));
        ['Answered', 'Answered by combining', 'Partly answered', 'Not answered', 'Chit-chat', 'Error', 'Waiting'].forEach(name => assert.ok(counts.includes(name), name));
        assert.match(counts, /1Answered/); assert.match(counts, /1Waiting/);
        const rows = $('Rows');
        assert.equal(rows.children.length, 6, 'each row has a hidden detail row');
        assert.match(text(rows.children[0]), /<img src=x onerror=alert\(1\)>/, 'question rendered as text');
        assert.match(text(rows.children[0]), /عنوان آزمایشی هفت/);
        const detail = rows.children[1];
        assert.equal(detail.hidden, true);
        const toggle = find(rows.children[0], n => n.tagName === 'BUTTON');
        toggle.dispatch('click');
        assert.equal(detail.hidden, false); assert.equal(toggle.getAttribute('aria-expanded'), 'true');
        assert.match(text(detail), /Batch 1 · initial · none/);
        assert.match(text(detail), /عنوان یک · k2/);
        assert.match(text(detail), /Batch 2 · initial · complete/);
        assert.match(text(rows.children[4]), /Waiting/);
        assert.equal($('Download').getAttribute('href'), '/api/knowledge-coverage/checks/' + RUN + '/export');

        const raw = 'id,query\r\n1,سوال\r\n';
        $('File').files = [{ name: 'synthetic.csv', size: Buffer.byteLength(raw), arrayBuffer: async () => new TextEncoder().encode(raw).buffer }];
        $('Depth').value = '150'; $('Keep').value = '50'; $('BroaderDepth').value = '200'; $('BroaderKeep').value = '50';
        await $('Form').dispatch('submit');
        const post = requests.find(r => r.options.method === 'POST');
        const payload = JSON.parse(post.options.body);
        assert.equal(Buffer.from(payload.csv_base64, 'base64').toString('utf8'), raw);
        assert.deepEqual(payload.documents, ['Synthetic_FAQ', 'Synthetic_Policies']);
        assert.deepEqual([payload.depth, payload.keep, payload.batch_size, payload.broader_enabled, payload.broader_depth, payload.broader_keep], [150, 50, 10, true, 200, 50]);
    } finally { Object.assign(global, saved); }
});

test('batch detail without batches shows the error code', () => {
    const document = dom(false);
    const list = ui.batchDetail(document, { batches: [], combines: [], error_code: 'retrieval_failed' });
    assert.match(text(list), /Error: retrieval_failed/);
    const combined = ui.batchDetail(document, { batches: [], combines: [{ phase: 'initial', verdict: 'complete', chunks: [{ chunk_id: 'k3', title: 'ترکیب' }] }] });
    assert.match(text(combined), /Combined · initial · complete/);
});
