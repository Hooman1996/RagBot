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
    scrollIntoView(options) { this.document.scrolls.push({ element: this, options }); }
    querySelectorAll(selector) {
        const found = [];
        const visit = n => { if (n.tagName === 'INPUT' && selector === 'input:checked' && n.checked) found.push(n); (n.children || []).forEach(visit); };
        this.children.forEach(visit); return found;
    }
}
const text = element => (element.textContent || '') + (element.children || []).map(text).join('');
const find = (element, predicate) => predicate(element) ? element : (element.children || []).map(c => find(c, predicate)).find(Boolean);
const findAll = (element, predicate, out = []) => { if (predicate(element)) out.push(element); (element.children || []).forEach(c => findAll(c, predicate, out)); return out; };
const tick = () => new Promise(resolve => setImmediate(resolve));

function dom(canStart) {
    const document = { ids: new Map(), scrolls: [], createElement(tag) { return new Element(tag, this); }, createTextNode(value) { return { nodeType: 3, textContent: String(value), children: [] }; }, getElementById(id) { return this.ids.get(id); } };
    const html = fs.readFileSync('templates/knowledge_coverage.html', 'utf8');
    [...html.matchAll(/id="(coverage[^"]+)"/g)].forEach(m => { document.createElement('div').id = m[1]; });
    document.body = { classList: { values: new Set(), add(v) { this.values.add(v); }, toggle(v) { if (this.values.has(v)) { this.values.delete(v); return false; } this.values.add(v); return true; } } };
    document.getElementById('coverageRoot').dataset = { canStart: String(canStart), uploadLimit: '5242880' };
    document.getElementById('coverageKeep').value = '50';
    document.getElementById('coverageBatchSize').value = '5';
    return document;
}

const RUN = 'c_' + 'a'.repeat(32);
const clone = value => JSON.parse(JSON.stringify(value));
function fixture() {
    return {
        checks: [{ run_id: RUN, created_at: '2026-01-01T10:00:00.000+00:00', file_name: 'synthetic.csv', row_count: 3, done: 2, state: 'running', active_row: 3 }],
        detail: { meta: { run_id: RUN, state: 'running', active_row: 3 }, done: 2, active_row: 3, counts: { answered: 1, answered_combined: 0, partial: 0, not_answered: 0, chitchat: 1, error: 0, waiting: 1 } },
        rows: { total: 3, offset: 0, rows: [
            { row: 1, id: 'q1', question: '<img src=x onerror=alert(1)> سوال آزمایشی', result: 'answered', answer_batch: 2, answer_phase: 'initial',
              answer_chunks: [{ chunk_id: 'k7', title: 'عنوان آزمایشی هفت' }],
              batches: [{ number: 1, phase: 'initial', verdict: 'none', chunks: [{ chunk_id: 'k1', title: 'عنوان یک' }, { chunk_id: 'k2', title: null }] },
                        { number: 2, phase: 'initial', verdict: 'complete', chunks: [{ chunk_id: 'k7', title: 'عنوان آزمایشی هفت' }] }],
              combines: [], model_calls: 2, duration_ms: 900, error_code: null, note: 'synthetic note', active: false },
            { row: 2, id: 'q2', question: 'سلام', result: 'chitchat', answer_batch: null, answer_phase: null, answer_chunks: [], batches: [], combines: [], model_calls: 0, duration_ms: 5, error_code: null, note: null, active: false },
            { row: 3, id: 'q3', question: 'منتظر', result: null, answer_batch: null, answer_phase: null, answer_chunks: [], batches: [], combines: [], model_calls: null, duration_ms: null, error_code: null, note: null, active: true }
        ] },
        rowDetails: {
            1: { row: 1, id: 'q1', question: 'سوال', result: 'answered', answer_batch: 2, answer_phase: 'initial', model_calls: 2, duration_ms: 900, error_code: null,
                 batches: [
                     { number: 1, phase: 'initial', verdict: 'none', note: 'یادداشت یک', chunks: [
                         { number: 1, chunk_id: 'k1', title: 'عنوان یک', text: '<b>متن یک</b>', relied: false },
                         { number: 2, chunk_id: 'k2', title: null, text: null, relied: false }] },
                     { number: 2, phase: 'initial', verdict: 'complete', note: 'synthetic note', chunks: [
                         { number: 1, chunk_id: 'k7', title: 'عنوان آزمایشی هفت', text: 'متن هفت', relied: true }] }],
                 combines: [] }
        },
        documents: { documents: [{ name: 'Synthetic_FAQ', category: 'FAQ' }, { name: 'Synthetic_Policies', category: 'Policy' }], count: 2 }
    };
}

/* Boots the page against fixture data; returns helpers for the fake server and timers. */
async function harness(canStart, data = fixture()) {
    const document = dom(canStart), $ = name => document.getElementById('coverage' + name);
    const requests = [], timers = [];
    const saved = { fetch: global.fetch, localStorage: global.localStorage, setInterval: global.setInterval, clearInterval: global.clearInterval };
    global.localStorage = { getItem() { return null; }, setItem() {} };
    global.setInterval = fn => { timers.push(fn); return timers.length; }; global.clearInterval = () => {};
    const server = { data, hold: null };
    global.fetch = async (url, options = {}) => {
        requests.push({ url, options });
        if (server.hold && url.endsWith('/cancel')) await server.hold;
        const path = url.replace('/api/knowledge-coverage/', '');
        const d = server.data;
        let value;
        const detailMatch = path.match(/\/rows\/(\d+)$/);
        if (path === 'documents') value = d.documents;
        else if (path === 'checks' && options.method === 'POST') value = { run_id: RUN };
        else if (path === 'checks') value = d.checks;
        else if (path.endsWith('/suggestions/cancel')) value = { cancelled: 1 };
        else if (path.endsWith('/suggestions') && options.method === 'POST') { value = { queued: 1 }; if (server.onSuggest) server.onSuggest(JSON.parse(options.body)); }
        else if (path.endsWith('/suggestions')) value = d.suggestions || { queued: 0, active_row: null, done: 0, errors: 0, eligible: 0 };
        else if (detailMatch) value = d.rowDetails[detailMatch[1]];
        else if (path.includes('/rows?')) value = d.rows;
        else if (path.endsWith('/cancel')) value = { run_id: RUN, state: 'cancelled' };
        else value = d.detail;
        return { ok: true, json: async () => clone(value) };
    };
    const booted = await ui.boot(document);
    await tick();
    return { document, $, requests, timers, server, booted, restore: () => Object.assign(global, saved) };
}
const rowTr = ($, n) => $('Rows').children[(n - 1) * 2];
const detailTr = ($, n) => $('Rows').children[(n - 1) * 2 + 1];
const toggleOf = ($, n) => find(rowTr($, n), e => e.tagName === 'BUTTON');

test('"= N batches of M" line', () => {
    assert.equal(ui.batchLine(50, 5), '= 10 batches of 5');
    assert.equal(ui.batchLine(50, 10), '= 5 batches of 10');
    assert.equal(ui.batchLine(5, 5), '= 1 batch of 5');
    assert.equal(ui.batchLine(50, 20), '= 3 batches of 20 (last has 10)');
    assert.equal(ui.batchLine('', 5), '');
});

test('counts, rows as text, batch detail and the start payload', async () => {
    const h = await harness(true), { $ } = h;
    try {
        assert.equal($('BatchLine').textContent, '= 10 batches of 5');
        $('BatchSize').value = '10'; $('BatchSize').dispatch('input');
        assert.equal($('BatchLine').textContent, '= 5 batches of 10');
        assert.equal($('BroaderDepth').disabled, true);
        $('Broader').checked = true; $('Broader').dispatch('change');
        assert.equal($('BroaderDepth').disabled, false);
        assert.equal($('Documents').querySelectorAll('input:checked').length, 2);
        assert.match(text($('Checks')), /synthetic\.csv/);
        assert.match(text($('Checks')), /2\/3 · row 3/, 'progress names the row being checked');
        assert.match(text($('Checks')), /Stop/); assert.doesNotMatch(text($('Checks')), /Cancel/);
        assert.equal(h.timers.length, 1, 'polls while a run is running');

        await h.booted.actions.open(RUN);
        assert.equal($('Results').hidden, false);
        const counts = text($('Counts'));
        ['Answered', 'Answered by combining', 'Partly answered', 'Not answered', 'Chit-chat', 'Error', 'Waiting'].forEach(name => assert.ok(counts.includes(name), name));
        assert.match(counts, /1Answered/); assert.match(counts, /1Waiting/);
        const rows = $('Rows');
        assert.equal(rows.children.length, 6, 'each row has a hidden detail row');
        assert.match(text(rows.children[0]), /<img src=x onerror=alert\(1\)>/, 'question rendered as text');
        assert.match(text(rows.children[0]), /عنوان آزمایشی هفت/);
        const detail = detailTr($, 1);
        assert.equal(detail.hidden, true);
        toggleOf($, 1).dispatch('click'); await tick();
        assert.equal(detail.hidden, false); assert.equal(toggleOf($, 1).getAttribute('aria-expanded'), 'true');
        const shown = text(detail);
        assert.match(shown, /Answer batch 2/); assert.match(shown, /2 model calls/); assert.match(shown, /0\.9 s/);
        assert.match(shown, /Batch 1 · initial · none/); assert.match(shown, /Batch 2 · initial · complete/);
        assert.match(shown, /Model note: یادداشت یک/);
        assert.match(shown, /<b>متن یک<\/b>/, 'chunk text rendered as text');
        const chunkText = find(detail, e => e.className === 'coverage-chunk-text');
        assert.equal(chunkText.dir, 'auto');
        const answer = findAll(detail, e => /coverage-step--answer/.test(e.className));
        assert.equal(answer.length, 1); assert.match(text(answer[0]), /^Batch 2.*Answer/);
        assert.equal($('Download').getAttribute('href'), '/api/knowledge-coverage/checks/' + RUN + '/export');

        const raw = 'id,query\r\n1,سوال\r\n';
        $('File').files = [{ name: 'synthetic.csv', size: Buffer.byteLength(raw), arrayBuffer: async () => new TextEncoder().encode(raw).buffer }];
        $('Depth').value = '150'; $('Keep').value = '50'; $('BroaderDepth').value = '200'; $('BroaderKeep').value = '50';
        await $('Form').dispatch('submit');
        const post = h.requests.find(r => r.options.method === 'POST');
        const payload = JSON.parse(post.options.body);
        assert.equal(Buffer.from(payload.csv_base64, 'base64').toString('utf8'), raw);
        assert.deepEqual(payload.documents, ['Synthetic_FAQ', 'Synthetic_Policies']);
        assert.deepEqual([payload.depth, payload.keep, payload.batch_size, payload.broader_enabled, payload.broader_depth, payload.broader_keep], [150, 50, 10, true, 200, 50]);
    } finally { h.restore(); }
});

test('the active row is highlighted and marked Checking…', async () => {
    const h = await harness(false), { $ } = h;
    try {
        await h.booted.actions.open(RUN);
        const active = rowTr($, 3);
        assert.match(active.className, /\bcoverage-row--active\b/);
        assert.equal(active.getAttribute('aria-current'), 'true');
        assert.match(text(active), /Checking…/);
        const badge = find(active, e => e.className === 'coverage-badge');
        assert.equal(badge.getAttribute('data-tone'), 'active');
        [1, 2].forEach(n => { assert.doesNotMatch(rowTr($, n).className, /active/); assert.equal(rowTr($, n).getAttribute('aria-current'), undefined); });
        assert.equal(h.document.scrolls.length, 1, 'scrolled to the active row once');
        assert.deepEqual(h.document.scrolls[0].options, { block: 'nearest' });
        await h.timers[0](); await tick();
        assert.equal(h.document.scrolls.length, 1, 'no scroll when the active row is unchanged');
    } finally { h.restore(); }
});

test('an expanded row stays open across polls and its details are fetched once', async () => {
    const h = await harness(false), { $ } = h;
    try {
        await h.booted.actions.open(RUN);
        toggleOf($, 1).dispatch('click'); await tick();
        const firstBody = detailTr($, 1).children[0].children[0];
        const detailFetches = () => h.requests.filter(r => /\/rows\/1$/.test(r.url)).length;
        assert.equal(detailFetches(), 1);
        for (const result of ['not_answered', 'partial']) {
            const data = fixture();
            data.rows.rows[2] = { ...data.rows.rows[2], result, active: false };
            data.rows.rows[1] = { ...data.rows.rows[1], note: 'changed ' + result };
            data.detail.active_row = null; data.detail.meta.active_row = null;
            h.server.data = { ...data, rowDetails: h.server.data.rowDetails };
            await h.timers[0](); await tick();
            assert.match(text(rowTr($, 3)), result === 'partial' ? /Partly answered/ : /Not answered/, 'table redrawn with the new result');
            assert.equal(detailTr($, 1).hidden, false, 'still expanded after poll');
            assert.equal(toggleOf($, 1).getAttribute('aria-expanded'), 'true');
            assert.equal(detailTr($, 1).children[0].children[0], firstBody, 'cached detail element reused');
        }
        assert.equal(detailFetches(), 1, 'details fetched once');
        // A changed result refetches.
        const data = clone(h.server.data); data.rows.rows[0].result = 'partial';
        h.server.data = data;
        await h.timers[0](); await tick();
        assert.equal(detailFetches(), 2);
    } finally { h.restore(); }
});

test('Follow moves to the active row page and is unchecked by details, paging and filter', async () => {
    const data = fixture();
    data.detail.active_row = 120; data.rows.total = 200;
    const h = await harness(false, data), { $ } = h;
    try {
        assert.equal($('Follow').checked, true, 'checked by default');
        await h.booted.actions.open(RUN);
        const rowsCall = () => h.requests.filter(r => r.url.includes('/rows?')).pop().url;
        assert.match(rowsCall(), /offset=100&/, 'page holding row 120');

        h.server.data = fixture();
        await h.timers[0](); await tick();
        toggleOf($, 1).dispatch('click'); await tick();
        assert.equal($('Follow').checked, false, 'opening details unchecks Follow');

        $('Follow').checked = true;
        $('Previous').dispatch('click'); await tick();
        assert.equal($('Follow').checked, false, 'Previous unchecks Follow');
        $('Follow').checked = true;
        $('Next').dispatch('click'); await tick();
        assert.equal($('Follow').checked, false, 'Next unchecks Follow');
        $('Follow').checked = true;
        $('Filter').value = 'answered'; $('Filter').dispatch('change'); await tick();
        assert.equal($('Follow').checked, false, 'a filter change unchecks Follow');
        assert.match(rowsCall(), /offset=0&.*result=answered/);
    } finally { h.restore(); }
});

test('Stop shows only for a running check and only with coverage_run_start', async () => {
    const viewer = await harness(false);
    try {
        await viewer.booted.actions.open(RUN);
        assert.equal(viewer.$('Stop').hidden, true, 'hidden without coverage_run_start');
        assert.doesNotMatch(text(viewer.$('Checks')), /Stop/);
    } finally { viewer.restore(); }

    const done = fixture(); done.detail.meta.state = 'completed'; done.checks[0].state = 'completed';
    const finished = await harness(true, done);
    try {
        await finished.booted.actions.open(RUN);
        assert.equal(finished.$('Stop').hidden, true, 'hidden for a finished check');
    } finally { finished.restore(); }

    const h = await harness(true), { $ } = h;
    try {
        await h.booted.actions.open(RUN);
        assert.equal($('Stop').hidden, false);
        let release; h.server.hold = new Promise(resolve => { release = resolve; });
        const pending = $('Stop').dispatch('click');
        await tick();
        assert.equal($('Stop').textContent, 'Stopping…'); assert.equal($('Stop').disabled, true);
        const stopped = fixture(); stopped.detail.meta.state = 'cancelled'; stopped.detail.active_row = null; stopped.checks[0].state = 'cancelled';
        h.server.data = stopped;
        release(); await pending;
        assert.ok(h.requests.some(r => r.url.endsWith('/checks/' + RUN + '/cancel') && r.options.method === 'POST'));
        assert.equal($('Stop').textContent, 'Stop'); assert.equal($('Stop').disabled, false);
        assert.equal($('Stop').hidden, true, 'hidden once the check is cancelled');
    } finally { h.restore(); }
});

test('relied chunks are marked Used and missing text shows the not-saved message', () => {
    const document = dom(false);
    const view = fixture().rowDetails[1];
    view.batches[0].chunks[0].text = 'line\n'.repeat(10);
    const detail = ui.renderDetail(document, view);
    const chunks = findAll(detail, e => /^coverage-chunk( |$)/.test(e.className));
    assert.equal(chunks.length, 3);
    const used = chunks.filter(c => /coverage-chunk--used/.test(c.className));
    assert.equal(used.length, 1); assert.match(text(used[0]), /^1عنوان آزمایشی هفتUsed/);
    assert.doesNotMatch(text(chunks[0]), /Used/);
    assert.match(text(chunks[1]), /Text not saved for this row \(checked before this update\)/);
    const clipped = find(chunks[0], e => /coverage-chunk-text--clipped/.test(e.className));
    assert.ok(clipped, 'long text is clipped');
    const more = find(chunks[0], e => e.tagName === 'BUTTON');
    assert.equal(more.textContent, 'Show more');
    more.dispatch('click');
    assert.equal(more.textContent, 'Show less'); assert.equal(clipped.className, 'coverage-chunk-text');

    const combined = ui.renderDetail(document, { result: 'answered_combined', answer_batch: null, model_calls: 3, duration_ms: 10, batches: [],
        combines: [{ phase: 'broader', verdict: 'complete', note: '', chunks: [{ number: 1, chunk_id: 'k3', title: 'ترکیب', text: 'متن', relied: true }] }] });
    assert.match(text(combined), /Combined/); assert.match(text(combined), /Combined · wider · complete/);
    assert.match(text(combined), /Answer/); assert.match(text(combined), /Used/);
});

test('error rows show their reason and the legend has six lines', async () => {
    const document = dom(false);
    const rows = [
        { row: 1, id: '', question: 'q', result: 'error', error_code: 'retrieval_failed', answer_chunks: [] },
        { row: 2, id: '', question: 'q', result: 'error', error_code: 'synthetic_unknown_code', answer_chunks: [] }];
    const tbody = document.createElement('tbody');
    ui.renderRows(document, tbody, rows, {});
    assert.match(text(tbody.children[0]), /ErrorSearch or rerank failed/);
    assert.match(text(tbody.children[2]), /Errorsynthetic_unknown_code/);
    assert.deepEqual(Object.keys(ui.ERROR_REASONS), ['empty_query', 'normalization_failed', 'intent_failed', 'retrieval_failed', 'model_failed', 'invalid_model_output', 'model_output_cut', 'invalid_chunk_numbers']);
    const detail = ui.renderDetail(document, { result: 'error', error_code: 'model_failed', model_calls: 2, duration_ms: 50, batches: [], combines: [] });
    assert.match(text(detail), /Model call failed/);

    const h = await harness(false), { $ } = h;
    try {
        const legend = $('Legend').children;
        assert.equal(legend.length, 6);
        ['Answered', 'Answered by combining', 'Partly answered', 'Not answered', 'Chit-chat', 'Error'].forEach((name, i) => assert.ok(text(legend[i]).startsWith(name), name));
        assert.match(text(legend[0]), /the batch number is shown/);
        assert.match(text(legend[4]), /intent classifier/);
    } finally { h.restore(); }
});

test('the two new error reasons render in rows and details', () => {
    const document = dom(false);
    const rows = [
        { row: 1, id: '', question: 'q', result: 'error', error_code: 'model_output_cut', answer_chunks: [] },
        { row: 2, id: '', question: 'q', result: 'error', error_code: 'invalid_chunk_numbers', answer_chunks: [] }];
    const tbody = document.createElement('tbody');
    ui.renderRows(document, tbody, rows, {});
    assert.match(text(tbody.children[0]), /ErrorModel reply was cut off/);
    assert.match(text(tbody.children[2]), /ErrorModel cited chunks that are not in the batch/);
    const cut = ui.renderDetail(document, { result: 'error', error_code: 'model_output_cut', model_calls: 2, duration_ms: 50, batches: [], combines: [] });
    assert.match(text(cut), /Model reply was cut off/);
    const cited = ui.renderDetail(document, { result: 'error', error_code: 'invalid_chunk_numbers', model_calls: 4, duration_ms: 50,
        batches: [{ number: 1, phase: 'initial', verdict: 'none', note: '', chunks: [] }], combines: [] });
    assert.match(text(cited), /Model cited chunks that are not in the batch/);
});

test('the Checks table shows the prompt version and a prompt change blocks resume', async () => {
    const data = fixture();
    data.checks = [
        { ...data.checks[0], state: 'cancelled', active_row: null, prompt_version: '0123456789ab' },
        { ...data.checks[0], run_id: 'c_' + 'b'.repeat(32), state: 'completed', active_row: null, prompt_version: null }];
    const h = await harness(true, data), { $ } = h;
    try {
        const header = fs.readFileSync('templates/knowledge_coverage.html', 'utf8');
        assert.match(header, /<th scope="col">State<\/th><th scope="col">Prompt<\/th>/);
        const [first, second] = $('Checks').children;
        assert.equal(first.children.length, 7);
        assert.equal(first.children[5].textContent, '0123456789ab');
        assert.equal(second.children[5].textContent, '—');
        const ok = global.fetch;
        global.fetch = async (url, options = {}) => url.endsWith('/resume')
            ? { ok: false, json: async () => ({ detail: 'prompt_changed' }) } : ok(url, options);
        await h.booted.actions.resume(RUN);
        assert.equal($('Error').hidden, false);
        assert.equal($('Error').textContent, 'The prompts changed since this check started; start a new check.');
    } finally { h.restore(); }
});

// Suggested FAQ ---------------------------------------------------------
const SUGGESTION = {
    status: 'done', error_code: null, faq_question: 'چگونه سقف انتقال را ببینم؟',
    faq_answer: 'به بخش انتقال بروید. سقف روزانه [تکمیل شود: سقف روزانه] است و کارمزد 700 ریال است.',
    missing: ['daily transfer limit'], chunks: [{ number: 1, chunk_id: 'k1', title: 'عنوان یک' }, { number: 2, chunk_id: 'k2', title: null }],
    used_chunk_ids: ['k1', 'k2'], unverified_numbers: ['700'], suggest_prompt_version: 'abcdefabcdef', model_calls: 1
};
const detailView = (result, extra = {}) => ({ row: 2, id: 'q2', question: 'سوال', result, answer_batch: null, model_calls: 1, duration_ms: 10,
    error_code: null, batches: [{ number: 1, phase: 'initial', verdict: 'none', note: '', chunks: [] }], combines: [], suggestion: null, suggestion_status: null, ...extra });
const buttons = element => findAll(element, e => e.tagName === 'BUTTON').map(b => b.textContent);

test('the Suggest button shows only on eligible rows, and only with coverage_run_start', () => {
    const document = dom(true);
    for (const result of ['not_answered', 'partial']) {
        const detail = ui.renderDetail(document, detailView(result), { canStart: true });
        assert.deepEqual(buttons(detail), ['Suggest FAQ'], result);
        assert.equal(ui.renderSuggestion(document, detailView(result), { canStart: false }), null, 'nothing for a viewer');
    }
    for (const result of ['answered', 'answered_combined', 'chitchat', 'error', null]) {
        const detail = ui.renderDetail(document, detailView(result), { canStart: true });
        assert.deepEqual(buttons(detail), [], String(result));
        assert.equal(findAll(detail, e => e.className === 'coverage-suggest').length, 0);
    }
    const busy = ui.renderSuggestion(document, detailView('partial'), { canStart: true, status: 'queued' });
    const button = find(busy, e => e.tagName === 'BUTTON');
    assert.equal(button.textContent, 'Suggesting…'); assert.equal(button.disabled, true);
    const again = ui.renderSuggestion(document, detailView('partial', { suggestion: SUGGESTION, suggestion_status: 'done' }), { canStart: true });
    assert.deepEqual(buttons(again), ['Copy', 'Suggest again']);
    const viewer = ui.renderSuggestion(document, detailView('partial', { suggestion: SUGGESTION }), { canStart: false });
    assert.deepEqual(buttons(viewer), ['Copy'], 'a viewer can read and copy a suggestion');
});

test('placeholders render as <mark>, missing facts, chunks used and the unverified-numbers warning', async () => {
    const document = dom(false);
    const box = ui.renderSuggestion(document, detailView('not_answered', { suggestion: SUGGESTION, suggestion_status: 'done' }), {});
    assert.match(text(box), /^Suggested FAQ/);
    const marks = findAll(box, e => e.tagName === 'MARK');
    assert.equal(marks.length, 1); assert.equal(marks[0].textContent, '[تکمیل شود: سقف روزانه]');
    const answer = marks[0] && findAll(box, e => e.className === 'coverage-suggest-text')[1];
    assert.equal(answer.dir, 'auto');
    assert.deepEqual(answer.children.map(c => c.nodeType === 3 ? 'text' : c.tagName), ['text', 'MARK', 'text'], 'text nodes around the mark');
    assert.equal(text(answer), SUGGESTION.faq_answer);
    assert.match(text(box), /Missing factsdaily transfer limit/);
    assert.match(text(box), /Chunks used: عنوان یک · k2/);
    const warning = find(box, e => e.className === 'coverage-suggest-warning');
    assert.equal(warning.textContent, 'Check these numbers; they are not in the chunks: 700');
    const clean = ui.renderSuggestion(document, detailView('not_answered', { suggestion: { ...SUGGESTION, unverified_numbers: [] } }), {});
    assert.equal(find(clean, e => e.className === 'coverage-suggest-warning'), undefined);

    const copied = [];
    const saved = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText: async value => { copied.push(value); } } } });
    try {
        const copy = find(box, e => e.tagName === 'BUTTON' && e.textContent === 'Copy');
        await copy.dispatch('click');
        assert.deepEqual(copied, [SUGGESTION.faq_question + '\n\n' + SUGGESTION.faq_answer]);
        assert.equal(copy.textContent, 'Copied');
    } finally { Object.defineProperty(globalThis, 'navigator', saved); }

    for (const [code, reason] of [['no_saved_chunks', /No chunk text was saved/], ['not_eligible', /Only Not answered or Partly answered/],
        ['empty_suggestion', /empty question or answer/], ['model_output_cut', /Model reply was cut off/]]) {
        const failed = ui.renderSuggestion(document, detailView('partial', { suggestion: { status: 'error', error_code: code } }), { canStart: true });
        assert.match(text(failed), reason, code);
        assert.deepEqual(buttons(failed), ['Suggest again']);
    }
});

test('"Suggest for all unanswered (N)" is disabled at N = 0 and hidden without coverage_run_start', async () => {
    const h = await harness(true), { $ } = h;
    try {
        await h.booted.actions.open(RUN);
        assert.equal($('SuggestAll').hidden, false);
        assert.equal($('SuggestAll').textContent, 'Suggest for all unanswered (0)');
        assert.equal($('SuggestAll').disabled, true);
        assert.equal($('SuggestProgress').hidden, true); assert.equal($('SuggestStop').hidden, true);
        const data = clone(h.server.data); data.suggestions = { queued: 0, active_row: null, done: 1, errors: 0, eligible: 3 };
        h.server.data = data;
        await h.timers[0](); await tick();
        assert.equal($('SuggestAll').textContent, 'Suggest for all unanswered (3)');
        assert.equal($('SuggestAll').disabled, false);
        const sent = []; h.server.onSuggest = body => sent.push(body);
        await $('SuggestAll').dispatch('click');
        assert.deepEqual(sent, [{ all: true }]);
    } finally { h.restore(); }

    const viewer = await harness(false);
    try {
        await viewer.booted.actions.open(RUN);
        assert.equal(viewer.$('SuggestAll').hidden, true);
    } finally { viewer.restore(); }
});

test('an open detail stays open while its suggestion moves from queued to done', async () => {
    const data = fixture();
    data.checks[0].state = 'completed'; data.detail.meta.state = 'completed'; data.detail.active_row = null; data.detail.meta.active_row = null;
    data.rows.rows[1] = { ...data.rows.rows[1], result: 'not_answered', suggestion_status: null };
    data.rows.rows[2] = { ...data.rows.rows[2], result: 'answered', active: false };
    data.rowDetails[2] = detailView('not_answered');
    data.suggestions = { queued: 0, active_row: null, done: 0, errors: 0, eligible: 1 };
    const h = await harness(true, data), { $ } = h;
    const step = (status, summary, detail) => {
        const next = clone(h.server.data);
        next.rows.rows[1].suggestion_status = status; next.suggestions = summary;
        if (detail) next.rowDetails[2] = detail;
        h.server.data = next;
    };
    try {
        assert.equal(h.timers.length, 0, 'no polling for a finished check');
        await h.booted.actions.open(RUN);
        toggleOf($, 2).dispatch('click'); await tick();
        const holder = detailTr($, 2).children[0].children[0];
        const batch = holder.children[2];
        assert.match(text(batch), /Batch 1/);
        const fetches = () => h.requests.filter(r => /\/rows\/2$/.test(r.url)).length;
        assert.equal(fetches(), 1);
        const suggestButton = find(holder, e => e.tagName === 'BUTTON' && e.textContent === 'Suggest FAQ');
        assert.ok(suggestButton, 'Suggest FAQ button in the open detail');

        const sent = []; h.server.onSuggest = body => { sent.push(body); step('queued', { queued: 1, active_row: null, done: 0, errors: 0, eligible: 1 }); };
        await suggestButton.dispatch('click'); await tick();
        assert.deepEqual(sent, [{ rows: [2] }]);
        assert.equal(h.timers.length, 1, 'polls while a suggestion is queued');
        assert.equal(detailTr($, 2).hidden, false, 'still open while queued');
        assert.equal(detailTr($, 2).children[0].children[0], holder);
        const queuedButton = find(holder, e => e.className === 'coverage-secondary coverage-suggest-button');
        assert.equal(queuedButton.textContent, 'Suggesting…'); assert.equal(queuedButton.disabled, true);
        assert.match(text(rowTr($, 2)), /Suggestion queued/);
        assert.equal($('SuggestProgress').hidden, false); assert.equal($('SuggestProgress').textContent, 'Suggestions: 0/1');
        assert.equal($('SuggestStop').hidden, false);

        step('active', { queued: 0, active_row: 2, done: 0, errors: 0, eligible: 1 });
        await h.timers[0](); await tick();
        assert.match(text(rowTr($, 2)), /Suggesting…/);
        assert.equal(fetches(), 1, 'queued and active need no refetch');

        step('done', { queued: 0, active_row: null, done: 1, errors: 0, eligible: 0 },
            detailView('not_answered', { suggestion: SUGGESTION, suggestion_status: 'done' }));
        await h.timers[0](); await tick();
        assert.equal(detailTr($, 2).hidden, false, 'still open when done');
        assert.equal(toggleOf($, 2).getAttribute('aria-expanded'), 'true');
        assert.equal(detailTr($, 2).children[0].children[0], holder, 'same detail element');
        assert.equal(holder.children[2], batch, 'only the suggestion box was redrawn');
        assert.match(text(holder), /Suggested FAQ/);
        assert.equal(findAll(holder, e => e.tagName === 'MARK').length, 1);
        assert.doesNotMatch(text(rowTr($, 2)), /Suggesting…|Suggestion queued/);
        assert.equal(fetches(), 2);
        assert.equal($('SuggestProgress').hidden, true); assert.equal($('SuggestStop').hidden, true);
        assert.equal($('SuggestAll').disabled, true);
    } finally { h.restore(); }
});

test('Has suggestion filters with suggested=1 and Stop suggestions posts cancel', async () => {
    const data = fixture(); data.suggestions = { queued: 2, active_row: 1, done: 0, errors: 0, eligible: 3 };
    const h = await harness(true, data), { $ } = h;
    try {
        assert.match(fs.readFileSync('templates/knowledge_coverage.html', 'utf8'), /<option value="suggested">Has suggestion<\/option>/);
        await h.booted.actions.open(RUN);
        $('Filter').value = 'suggested'; $('Filter').dispatch('change'); await tick();
        const rowsCall = h.requests.filter(r => r.url.includes('/rows?')).pop().url;
        assert.match(rowsCall, /&suggested=1$/); assert.doesNotMatch(rowsCall, /result=/);
        assert.equal($('SuggestStop').hidden, false);
        await $('SuggestStop').dispatch('click');
        assert.ok(h.requests.some(r => r.url.endsWith('/checks/' + RUN + '/suggestions/cancel') && r.options.method === 'POST'));
    } finally { h.restore(); }
});
