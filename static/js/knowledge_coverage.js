/* Coverage check page. Text-only DOM rendering; no private browser storage. */
(function (global) {
    'use strict';
    const API = '/api/knowledge-coverage/';
    const RESULT_LABELS = {
        answered: 'Answered', answered_combined: 'Answered by combining', partial: 'Partly answered',
        not_answered: 'Not answered', chitchat: 'Chit-chat', error: 'Error', waiting: 'Waiting'
    };
    const TONES = { answered: 'good', answered_combined: 'good', partial: 'review', not_answered: 'gap', error: 'error' };
    const PAGE_SIZE = 50;

    function label(result) { return RESULT_LABELS[result || 'waiting'] || String(result); }
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
    function renderCounts(document, container, counts) {
        container.replaceChildren(...Object.keys(RESULT_LABELS).map(key => {
            const cell = node(document, 'div');
            cell.append(node(document, 'strong', counts && counts[key] !== undefined ? counts[key] : 0), node(document, 'span', RESULT_LABELS[key]));
            return cell;
        }));
    }
    function batchDetail(document, row) {
        const list = node(document, 'ol', undefined, 'coverage-batches');
        (row.batches || []).forEach(batch => {
            const item = node(document, 'li');
            item.append(node(document, 'strong', 'Batch ' + batch.number + ' · ' + batch.phase + ' · ' + batch.verdict));
            const t = node(document, 'p', titles(batch.chunks)); t.dir = 'auto'; item.append(t);
            list.append(item);
        });
        (row.combines || []).forEach(combine => {
            const item = node(document, 'li');
            item.append(node(document, 'strong', 'Combined · ' + combine.phase + ' · ' + combine.verdict));
            const t = node(document, 'p', titles(combine.chunks)); t.dir = 'auto'; item.append(t);
            list.append(item);
        });
        if (!list.children.length) list.append(node(document, 'li', row.error_code ? 'Error: ' + row.error_code : 'No batches were checked.'));
        return list;
    }
    function renderRows(document, tbody, rows) {
        if (!rows.length) { const tr = node(document, 'tr'); const td = node(document, 'td', 'No rows match.', 'coverage-empty'); td.setAttribute('colspan', '6'); tr.append(td); tbody.replaceChildren(tr); return; }
        const out = [];
        rows.forEach(row => {
            const tr = node(document, 'tr'), detail = node(document, 'tr', undefined, 'coverage-detail');
            const toggle = node(document, 'button', String(row.row), 'coverage-link');
            toggle.type = 'button'; toggle.setAttribute('aria-expanded', 'false');
            toggle.setAttribute('aria-label', 'Show batches for row ' + row.row);
            const cell = node(document, 'td'); cell.append(toggle); tr.append(cell);
            tr.append(node(document, 'td', row.id));
            const q = node(document, 'td', row.question, 'coverage-query'); q.dir = 'auto'; tr.append(q);
            const r = node(document, 'td'); r.append(badge(document, row.result)); tr.append(r);
            tr.append(node(document, 'td', row.answer_batch ? row.answer_batch + (row.answer_phase === 'broader' ? ' (wider)' : '') : ''));
            const t = node(document, 'td', titles(row.answer_chunks)); t.dir = 'auto'; tr.append(t);
            const dcell = node(document, 'td'); dcell.setAttribute('colspan', '6'); dcell.append(batchDetail(document, row));
            if (row.note) { const n = node(document, 'p', 'Note: ' + row.note, 'coverage-hint'); n.dir = 'auto'; dcell.append(n); }
            detail.append(dcell); detail.hidden = true;
            toggle.addEventListener('click', () => { detail.hidden = !detail.hidden; toggle.setAttribute('aria-expanded', String(!detail.hidden)); });
            out.push(tr, detail);
        });
        tbody.replaceChildren(...out);
    }
    function renderChecks(document, tbody, checks, canStart, actions) {
        if (!checks.length) { const tr = node(document, 'tr'); const td = node(document, 'td', 'No checks yet.', 'coverage-empty'); td.setAttribute('colspan', '6'); tr.append(td); tbody.replaceChildren(tr); return; }
        tbody.replaceChildren(...checks.map(check => {
            const tr = node(document, 'tr');
            tr.append(node(document, 'td', String(check.created_at || '').replace('T', ' ').slice(0, 19)));
            const f = node(document, 'td', check.file_name); f.dir = 'auto'; tr.append(f);
            tr.append(node(document, 'td', check.row_count), node(document, 'td', check.done + '/' + check.row_count), node(document, 'td', check.state));
            const cell = node(document, 'td', undefined, 'coverage-actions');
            const add = (text, fn) => { const b = node(document, 'button', text, 'coverage-secondary'); b.type = 'button'; b.addEventListener('click', () => fn(check.run_id)); cell.append(b); };
            add('Open', actions.open);
            if (canStart && ['queued', 'running'].includes(check.state)) add('Cancel', actions.cancel);
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
        const root = $('Root'), canStart = root.dataset.canStart === 'true';
        const state = { checks: [], open: null, offset: 0, total: 0, timer: null };
        function showError(code) { $('Error').textContent = code ? 'Error: ' + code : ''; $('Error').hidden = !code; }
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
        async function loadResults() {
            if (!state.open) return;
            const id = state.open, filter = $('Filter').value;
            const [detail, page] = await Promise.all([
                call('checks/' + id),
                call('checks/' + id + '/rows?offset=' + state.offset + '&limit=' + PAGE_SIZE + (filter ? '&result=' + encodeURIComponent(filter) : ''))]);
            if (state.open !== id) return;
            $('Results').hidden = false;
            renderCounts(document, $('Counts'), detail.counts);
            renderRows(document, $('Rows'), page.rows);
            state.total = page.total;
            $('PageLabel').textContent = page.total ? (state.offset + 1) + '–' + Math.min(state.offset + PAGE_SIZE, page.total) + ' of ' + page.total : '';
            $('Previous').disabled = state.offset === 0;
            $('Next').disabled = state.offset + PAGE_SIZE >= page.total;
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
        const actions = {
            open: async id => { state.open = id; state.offset = 0; showError(''); await refresh(); },
            cancel: async id => { try { await post('checks/' + id + '/cancel'); await refresh(); } catch (e) { showError(e.message); } },
            resume: async id => { try { await post('checks/' + id + '/resume'); await refresh(); } catch (e) { showError(e.message); } }
        };
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
                state.open = created.run_id; state.offset = 0;
                await refresh();
            } catch (e) { showError(e.message); }
            finally { $('Start').disabled = false; }
        }

        if (global.localStorage && global.localStorage.getItem('theme') === 'light') document.body.classList.add('light-mode');
        $('Theme').addEventListener('click', () => { const light = document.body.classList.toggle('light-mode'); global.localStorage.setItem('theme', light ? 'light' : 'dark'); });
        $('Filter').addEventListener('change', () => { state.offset = 0; loadResults().catch(e => showError(e.message)); });
        $('Previous').addEventListener('click', () => { state.offset = Math.max(0, state.offset - PAGE_SIZE); loadResults().catch(e => showError(e.message)); });
        $('Next').addEventListener('click', () => { state.offset += PAGE_SIZE; loadResults().catch(e => showError(e.message)); });
        if (canStart && $('Form')) {
            ['Keep', 'BatchSize'].forEach(name => $(name).addEventListener('input', updateBatchLine));
            $('Broader').addEventListener('change', updateBroader);
            $('Form').addEventListener('submit', start);
            updateBatchLine(); updateBroader();
            loadDocuments().catch(e => showError(e.message));
        }
        return refresh().then(() => ({ state, actions, refresh }));
    }

    const api = { boot, batchLine, renderCounts, renderRows, renderChecks, batchDetail, label, RESULT_LABELS };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else if (global.document) boot(global.document);
})(typeof window !== 'undefined' ? window : globalThis);
