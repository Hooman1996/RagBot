/* Coverage check page. Text-only DOM rendering; no private browser storage. */
(function (global) {
    'use strict';
    const API = '/api/knowledge-coverage/';
    const RESULT_LABELS = {
        answered: 'Answered', answered_combined: 'Answered by combining', partial: 'Partly answered',
        not_answered: 'Not answered', chitchat: 'Chit-chat', error: 'Error', waiting: 'Waiting'
    };
    const TONES = { answered: 'good', answered_combined: 'good', partial: 'review', not_answered: 'gap', error: 'error' };
    const LEGEND = [
        ['answered', 'One batch of chunks fully answers the question; the batch number is shown.'],
        ['answered_combined', 'No single batch was complete, but the chunks the model used from partial batches answer it together.'],
        ['partial', 'Some chunks cover part of the question, but nothing answers it fully.'],
        ['not_answered', 'No batch covers the question.'],
        ['chitchat', 'The chat\'s intent classifier calls it chit-chat, so nothing was searched.'],
        ['error', 'The check could not finish this row; the reason is shown.']
    ];
    const ERROR_REASONS = {
        empty_query: 'Empty question',
        normalization_failed: 'Normalizing failed',
        intent_failed: 'Intent classifier failed',
        retrieval_failed: 'Search or rerank failed',
        model_failed: 'Model call failed',
        invalid_model_output: 'Model reply did not match the format'
    };
    const PHASES = { initial: 'initial', broader: 'wider' };
    const NOT_SAVED = 'Text not saved for this row (checked before this update)';
    const PAGE_SIZE = 50;
    const CLIP_CHARS = 480, CLIP_LINES = 6;

    function label(result) { return RESULT_LABELS[result || 'waiting'] || String(result); }
    function reason(code) { return ERROR_REASONS[code] || String(code || ''); }
    function phase(name) { return PHASES[name] || String(name || ''); }
    function node(document, tag, text, className) {
        const n = document.createElement(tag);
        if (text !== undefined && text !== null) n.textContent = String(text);
        if (className) n.className = className;
        return n;
    }
    function batchLine(keep, batchSize) {
        keep = Number(keep); batchSize = Number(batchSize);
        if (!Number.isInteger(keep) || !Number.isInteger(batchSize) || keep < 1 || batchSize < 1) return '';
        const count = Math.ceil(keep / batchSize), last = keep - (count - 1) * batchSize;
        return '= ' + count + ' batch' + (count === 1 ? '' : 'es') + ' of ' + batchSize + (last !== batchSize ? ' (last has ' + last + ')' : '');
    }
    function titles(chunks) { return (chunks || []).map(c => c.title || c.chunk_id).join(' · '); }
    function badge(document, result) {
        const b = node(document, 'span', label(result), 'coverage-badge');
        b.setAttribute('data-tone', TONES[result] || 'neutral');
        return b;
    }
    function checkingBadge(document) {
        const b = node(document, 'span', 'Checking…', 'coverage-badge');
        b.setAttribute('data-tone', 'active');
        return b;
    }
    function renderCounts(document, container, counts) {
        container.replaceChildren(...Object.keys(RESULT_LABELS).map(key => {
            const cell = node(document, 'div');
            cell.append(node(document, 'strong', counts && counts[key] !== undefined ? counts[key] : 0), node(document, 'span', RESULT_LABELS[key]));
            return cell;
        }));
    }
    function renderLegend(document, container) {
        container.replaceChildren(...LEGEND.map(([key, text]) => {
            const item = node(document, 'li');
            item.append(badge(document, key), node(document, 'span', text));
            return item;
        }));
    }

    // Row details ------------------------------------------------------
    function chunkItem(document, chunk) {
        const item = node(document, 'li', undefined, 'coverage-chunk' + (chunk.relied ? ' coverage-chunk--used' : ''));
        const head = node(document, 'div', undefined, 'coverage-chunk-head');
        head.append(node(document, 'span', chunk.number, 'coverage-chunk-number'));
        const title = node(document, 'span', chunk.title || chunk.chunk_id, 'coverage-chunk-title'); title.dir = 'auto';
        head.append(title);
        if (chunk.relied) head.append(node(document, 'span', 'Used', 'coverage-mark coverage-mark--used'));
        item.append(head);
        if (chunk.text === null || chunk.text === undefined) {
            item.append(node(document, 'p', NOT_SAVED, 'coverage-chunk-missing'));
            return item;
        }
        const body = node(document, 'p', chunk.text, 'coverage-chunk-text'); body.dir = 'auto';
        item.append(body);
        const text = String(chunk.text);
        if (text.length > CLIP_CHARS || text.split('\n').length > CLIP_LINES) {
            body.className = 'coverage-chunk-text coverage-chunk-text--clipped';
            const more = node(document, 'button', 'Show more', 'coverage-more'); more.type = 'button';
            more.setAttribute('aria-expanded', 'false');
            more.addEventListener('click', () => {
                const open = more.getAttribute('aria-expanded') !== 'true';
                body.className = 'coverage-chunk-text' + (open ? '' : ' coverage-chunk-text--clipped');
                more.textContent = open ? 'Show less' : 'Show more';
                more.setAttribute('aria-expanded', String(open));
            });
            item.append(more);
        }
        return item;
    }
    function stepBlock(document, heading, step, answered) {
        const section = node(document, 'section', undefined, 'coverage-step' + (answered ? ' coverage-step--answer' : ''));
        const head = node(document, 'h3', undefined, 'coverage-step-head');
        head.append(node(document, 'span', heading));
        if (answered) head.append(node(document, 'span', 'Answer', 'coverage-mark coverage-mark--answer'));
        section.append(head);
        if (step.note) {
            const note = node(document, 'p', undefined, 'coverage-step-note');
            const text = node(document, 'span', step.note); text.dir = 'auto';
            note.append(node(document, 'strong', 'Model note: '), text);
            section.append(note);
        }
        const list = node(document, 'ol', undefined, 'coverage-chunks');
        (step.chunks || []).forEach(chunk => list.append(chunkItem(document, chunk)));
        section.append(list);
        return section;
    }
    function detailParts(document, view) {
        const head = node(document, 'div', undefined, 'coverage-detail-head');
        head.append(badge(document, view.result));
        const facts = [];
        if (view.result === 'error') facts.push(reason(view.error_code));
        if (view.result) {
            facts.push(view.answer_batch ? 'Answer batch ' + view.answer_batch + (view.answer_phase === 'broader' ? ' (wider)' : '') : 'No answer batch');
            facts.push((view.model_calls || 0) + ' model call' + (view.model_calls === 1 ? '' : 's'));
            if (view.duration_ms !== null && view.duration_ms !== undefined) facts.push((view.duration_ms / 1000).toFixed(1) + ' s');
        }
        facts.forEach(fact => head.append(node(document, 'span', fact, 'coverage-detail-fact')));
        const parts = [head];
        (view.batches || []).forEach(batch => parts.push(stepBlock(document,
            'Batch ' + batch.number + ' · ' + phase(batch.phase) + ' · ' + batch.verdict, batch,
            view.result === 'answered' && batch.number === view.answer_batch)));
        if ((view.combines || []).length) {
            parts.push(node(document, 'h3', 'Combined', 'coverage-detail-section'));
            view.combines.forEach(combine => parts.push(stepBlock(document,
                'Combined · ' + phase(combine.phase) + ' · ' + combine.verdict, combine,
                view.result === 'answered_combined' && combine.verdict === 'complete')));
        }
        if (parts.length === 1) {
            let empty = 'No batches were checked.';
            if (!view.result) empty = 'Not checked yet.';
            else if (view.result === 'chitchat') empty = 'Chit-chat: nothing was searched.';
            else if (view.result === 'error') empty = 'Error: ' + reason(view.error_code);
            parts.push(node(document, 'p', empty, 'coverage-hint'));
        }
        return parts;
    }
    function renderDetail(document, view) {
        const box = node(document, 'div', undefined, 'coverage-detail-body');
        box.append(...detailParts(document, view));
        return box;
    }

    // Tables -----------------------------------------------------------
    /* options: activeRow, expanded (Set of row numbers), detailFor(row, cell), onToggle(row, open).
       Returns the active row's <tr>, or null. */
    function renderRows(document, tbody, rows, options) {
        options = options || {};
        const expanded = options.expanded || new Set();
        if (!rows.length) { const tr = node(document, 'tr'); const td = node(document, 'td', 'No rows match.', 'coverage-empty'); td.setAttribute('colspan', '6'); tr.append(td); tbody.replaceChildren(tr); return null; }
        const out = [];
        let activeTr = null;
        rows.forEach(row => {
            const active = options.activeRow === row.row, open = expanded.has(row.row);
            const tr = node(document, 'tr', undefined, active ? 'coverage-row coverage-row--active' : 'coverage-row');
            if (active) { tr.setAttribute('aria-current', 'true'); activeTr = tr; }
            const detail = node(document, 'tr', undefined, 'coverage-detail');
            const toggle = node(document, 'button', String(row.row), 'coverage-link');
            toggle.type = 'button'; toggle.setAttribute('aria-expanded', String(open));
            toggle.setAttribute('aria-label', 'Show batches for row ' + row.row);
            const cell = node(document, 'td'); cell.append(toggle); tr.append(cell);
            tr.append(node(document, 'td', row.id));
            const q = node(document, 'td', row.question, 'coverage-query'); q.dir = 'auto'; tr.append(q);
            const r = node(document, 'td', undefined, 'coverage-result');
            r.append(active ? checkingBadge(document) : badge(document, row.result));
            if (!active && row.result === 'error') r.append(node(document, 'span', reason(row.error_code), 'coverage-reason'));
            tr.append(r);
            tr.append(node(document, 'td', row.answer_batch ? row.answer_batch + (row.answer_phase === 'broader' ? ' (wider)' : '') : ''));
            const t = node(document, 'td', titles(row.answer_chunks)); t.dir = 'auto'; tr.append(t);
            const dcell = node(document, 'td'); dcell.setAttribute('colspan', '6');
            detail.append(dcell); detail.hidden = !open;
            if (open && options.detailFor) options.detailFor(row, dcell);
            toggle.addEventListener('click', () => {
                const show = detail.hidden;
                detail.hidden = !show; toggle.setAttribute('aria-expanded', String(show));
                if (show && options.detailFor) options.detailFor(row, dcell);
                if (options.onToggle) options.onToggle(row, show);
            });
            out.push(tr, detail);
        });
        tbody.replaceChildren(...out);
        return activeTr;
    }
    function renderChecks(document, tbody, checks, canStart, actions) {
        if (!checks.length) { const tr = node(document, 'tr'); const td = node(document, 'td', 'No checks yet.', 'coverage-empty'); td.setAttribute('colspan', '6'); tr.append(td); tbody.replaceChildren(tr); return; }
        tbody.replaceChildren(...checks.map(check => {
            const tr = node(document, 'tr');
            tr.append(node(document, 'td', String(check.created_at || '').replace('T', ' ').slice(0, 19)));
            const f = node(document, 'td', check.file_name); f.dir = 'auto'; tr.append(f);
            const progress = check.done + '/' + check.row_count + (check.state === 'running' && check.active_row ? ' · row ' + check.active_row : '');
            tr.append(node(document, 'td', check.row_count), node(document, 'td', progress), node(document, 'td', check.state));
            const cell = node(document, 'td', undefined, 'coverage-actions');
            const add = (text, fn) => { const b = node(document, 'button', text, 'coverage-secondary'); b.type = 'button'; b.addEventListener('click', () => fn(check.run_id)); cell.append(b); };
            add('Open', actions.open);
            if (canStart && ['queued', 'running'].includes(check.state)) add('Stop', actions.stop);
            if (canStart && ['cancelled', 'interrupted'].includes(check.state)) add('Resume', actions.resume);
            tr.append(cell);
            return tr;
        }));
    }
    function base64(buffer) {
        const bytes = new Uint8Array(buffer); let binary = '';
        for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
        return global.btoa ? global.btoa(binary) : Buffer.from(binary, 'binary').toString('base64');
    }

    function boot(document) {
        const $ = name => document.getElementById('coverage' + name);
        const root = $('Root'), canStart = root.dataset.canStart === 'true', follow = $('Follow');
        const state = {
            checks: [], open: null, openState: null, offset: 0, total: 0, timer: null,
            expanded: new Set(), details: new Map(), lastKey: null, lastActive: null, activeTr: null
        };
        if (follow) follow.checked = true;
        function showError(code) { $('Error').textContent = code ? 'Error: ' + code : ''; $('Error').hidden = !code; }
        function stopFollowing() { if (follow) follow.checked = false; }
        async function call(path, options) {
            const response = await global.fetch(API + path, options);
            let body = null; try { body = await response.json(); } catch (e) { body = null; }
            if (!response.ok) throw new Error(body && typeof body.detail === 'string' ? body.detail : 'request_failed');
            return body;
        }
        function post(path, payload) {
            return call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload || {}) });
        }
        function updateBatchLine() { if ($('BatchLine')) $('BatchLine').textContent = batchLine($('Keep').value, $('BatchSize').value); }
        function updateBroader() { if ($('Broader')) [$('BroaderDepth'), $('BroaderKeep')].forEach(n => { n.disabled = !$('Broader').checked; }); }
        function updateStop() {
            if ($('Stop')) $('Stop').hidden = !(canStart && ['queued', 'running'].includes(state.openState));
        }
        // One cached element per opened row: fetched once, again only when the row's result changes.
        function detailFor(row, cell) {
            const id = state.open, result = row.result || null;
            let entry = state.details.get(row.row);
            if (!entry || entry.result !== result) {
                const holder = node(document, 'div', 'Loading details…', 'coverage-detail-body');
                entry = { result, element: holder };
                state.details.set(row.row, entry);
                const current = entry;
                call('checks/' + id + '/rows/' + row.row).then(view => {
                    if (state.open !== id || state.details.get(row.row) !== current) return;
                    holder.textContent = '';
                    holder.replaceChildren(...detailParts(document, view));
                }, e => {
                    if (state.details.get(row.row) === current) state.details.delete(row.row);
                    holder.textContent = 'Could not load details: ' + e.message;
                });
            }
            cell.replaceChildren(entry.element);
        }
        function onToggle(row, open) {
            if (open) { state.expanded.add(row.row); stopFollowing(); }
            else state.expanded.delete(row.row);
        }
        async function loadResults() {
            if (!state.open) return;
            const id = state.open;
            const detail = await call('checks/' + id);
            if (state.open !== id) return;
            const filter = $('Filter').value, active = detail.active_row || null;
            if (follow && follow.checked && !filter && active) state.offset = Math.floor((active - 1) / PAGE_SIZE) * PAGE_SIZE;
            const offset = state.offset;
            const page = await call('checks/' + id + '/rows?offset=' + offset + '&limit=' + PAGE_SIZE + (filter ? '&result=' + encodeURIComponent(filter) : ''));
            if (state.open !== id) return;
            state.openState = detail.meta && detail.meta.state;
            $('Results').hidden = false;
            renderCounts(document, $('Counts'), detail.counts);
            updateStop();
            const key = JSON.stringify([filter, offset, active, page.rows]);
            if (key !== state.lastKey) {
                state.lastKey = key;
                state.activeTr = renderRows(document, $('Rows'), page.rows, { activeRow: active, expanded: state.expanded, detailFor, onToggle });
            }
            if (active !== state.lastActive) {
                state.lastActive = active;
                if (active && follow && follow.checked && state.activeTr && typeof state.activeTr.scrollIntoView === 'function') state.activeTr.scrollIntoView({ block: 'nearest' });
            }
            state.total = page.total;
            $('PageLabel').textContent = page.total ? (offset + 1) + '–' + Math.min(offset + PAGE_SIZE, page.total) + ' of ' + page.total : '';
            $('Previous').disabled = offset === 0;
            $('Next').disabled = offset + PAGE_SIZE >= page.total;
            $('Download').setAttribute('href', API + 'checks/' + id + '/export');
        }
        async function loadChecks() {
            state.checks = await call('checks');
            renderChecks(document, $('Checks'), state.checks, canStart, actions);
            const active = state.checks.some(c => c.state === 'queued' || c.state === 'running');
            if (active && !state.timer) state.timer = global.setInterval(() => refresh(), 3000);
            if (!active && state.timer) { global.clearInterval(state.timer); state.timer = null; }
        }
        async function refresh() {
            try { await loadChecks(); await loadResults(); } catch (e) { showError(e.message); }
        }
        async function stopRun(id) {
            try { await post('checks/' + id + '/cancel'); await refresh(); } catch (e) { showError(e.message); }
        }
        const actions = {
            open: async id => {
                if (state.open !== id) {
                    state.expanded = new Set(); state.details = new Map(); state.lastActive = null; state.openState = null;
                    if (follow) follow.checked = true;
                }
                state.open = id; state.offset = 0; state.lastKey = null; showError(''); await refresh();
            },
            stop: stopRun,
            resume: async id => { try { await post('checks/' + id + '/resume'); await refresh(); } catch (e) { showError(e.message); } }
        };
        async function stopOpen() {
            const button = $('Stop');
            button.disabled = true; button.textContent = 'Stopping…';
            try { await stopRun(state.open); } finally { button.disabled = false; button.textContent = 'Stop'; }
        }
        async function loadDocuments() {
            const listing = await call('documents');
            $('Documents').replaceChildren(...(listing.documents || []).map(doc => {
                const l = node(document, 'label', undefined, 'coverage-check'), box = node(document, 'input');
                box.type = 'checkbox'; box.checked = true; box.value = doc.name;
                const name = node(document, 'span', doc.name); name.dir = 'auto';
                l.append(box, name); return l;
            }));
        }
        async function start(event) {
            event.preventDefault(); showError('');
            const file = $('File').files && $('File').files[0];
            if (!file) { showError('choose_a_csv_file'); return; }
            if (file.size > Number(root.dataset.uploadLimit)) { showError('upload_too_large'); return; }
            const documents = Array.from($('Documents').querySelectorAll('input:checked'), n => n.value);
            $('Start').disabled = true;
            try {
                const payload = {
                    csv_base64: base64(await file.arrayBuffer()), file_name: file.name || 'questions.csv', documents,
                    depth: Number($('Depth').value), keep: Number($('Keep').value), batch_size: Number($('BatchSize').value),
                    broader_enabled: $('Broader').checked, broader_depth: Number($('BroaderDepth').value), broader_keep: Number($('BroaderKeep').value)
                };
                const created = await post('checks', payload);
                await actions.open(created.run_id);
            } catch (e) { showError(e.message); }
            finally { $('Start').disabled = false; }
        }

        if (global.localStorage && global.localStorage.getItem('theme') === 'light') document.body.classList.add('light-mode');
        $('Theme').addEventListener('click', () => { const light = document.body.classList.toggle('light-mode'); global.localStorage.setItem('theme', light ? 'light' : 'dark'); });
        if ($('Legend')) renderLegend(document, $('Legend'));
        $('Filter').addEventListener('change', () => { stopFollowing(); state.offset = 0; loadResults().catch(e => showError(e.message)); });
        $('Previous').addEventListener('click', () => { stopFollowing(); state.offset = Math.max(0, state.offset - PAGE_SIZE); loadResults().catch(e => showError(e.message)); });
        $('Next').addEventListener('click', () => { stopFollowing(); state.offset += PAGE_SIZE; loadResults().catch(e => showError(e.message)); });
        if (follow) follow.addEventListener('change', () => { if (follow.checked) { state.lastActive = null; loadResults().catch(e => showError(e.message)); } });
        if (canStart && $('Stop')) $('Stop').addEventListener('click', stopOpen);
        if (canStart && $('Form')) {
            ['Keep', 'BatchSize'].forEach(name => $(name).addEventListener('input', updateBatchLine));
            $('Broader').addEventListener('change', updateBroader);
            $('Form').addEventListener('submit', start);
            updateBatchLine(); updateBroader();
            loadDocuments().catch(e => showError(e.message));
        }
        return refresh().then(() => ({ state, actions, refresh }));
    }

    const api = {
        boot, batchLine, renderCounts, renderLegend, renderRows, renderChecks, renderDetail, label, reason,
        RESULT_LABELS, ERROR_REASONS, LEGEND, PAGE_SIZE
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else if (global.document) boot(global.document);
})(typeof window !== 'undefined' ? window : globalThis);
