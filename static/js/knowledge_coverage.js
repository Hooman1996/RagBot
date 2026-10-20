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
        invalid_model_output: 'Model reply did not match the format',
        model_output_cut: 'Model reply was cut off',
        invalid_chunk_numbers: 'Model cited chunks that are not in the batch'
    };
    const SUGGEST_ERRORS = Object.assign({}, ERROR_REASONS, {
        not_eligible: 'Only Not answered or Partly answered rows can get a suggestion',
        no_saved_chunks: 'No chunk text was saved for this row (checked before chunk text was kept)',
        empty_suggestion: 'The model returned an empty question or answer'
    });
    const API_ERRORS = {
        prompt_changed: 'The prompts changed since this check started; start a new check.',
        not_eligible: 'Only Not answered or Partly answered rows can get a suggestion.',
        suggestions_running: 'Stop the suggestions for this check before deleting it.'
    };
    const FINISHED = ['completed', 'cancelled', 'interrupted'];
    const DELETE_CONFIRM = 'Delete this check, its results and its suggestions? This cannot be undone. Download the CSV first if you need it.';
    const ELIGIBLE = ['not_answered', 'partial'];
    const SUGGEST_MARKS = { queued: 'Suggestion queued', active: 'Suggesting…' };
    const PLACEHOLDER = /\[تکمیل شود:[^\]]*\]/g;
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
    function renderDetail(document, view, options) {
        const box = node(document, 'div', undefined, 'coverage-detail-body');
        const parts = detailParts(document, view), slot = node(document, 'div', undefined, 'coverage-suggest-slot');
        const suggestion = renderSuggestion(document, view, options);
        if (suggestion) slot.append(suggestion);
        parts.splice(1, 0, slot);
        box.append(...parts);
        return box;
    }

    // Suggested FAQ ----------------------------------------------------
    function suggestReason(code) { return SUGGEST_ERRORS[code] || String(code || ''); }
    /* Text nodes for plain parts, <mark> for each [تکمیل شود: ...] placeholder. */
    function withPlaceholders(document, element, value) {
        const text = String(value || '');
        let last = 0;
        for (const match of text.matchAll(PLACEHOLDER)) {
            if (match.index > last) element.append(document.createTextNode(text.slice(last, match.index)));
            element.append(node(document, 'mark', match[0], 'coverage-placeholder'));
            last = match.index + match[0].length;
        }
        if (last < text.length) element.append(document.createTextNode(text.slice(last)));
        return element;
    }
    function suggestField(document, labelText, value) {
        const field = node(document, 'div', undefined, 'coverage-suggest-field');
        const body = withPlaceholders(document, node(document, 'p', undefined, 'coverage-suggest-text'), value);
        body.dir = 'auto';
        field.append(node(document, 'span', labelText, 'coverage-suggest-label'), body);
        return field;
    }
    /* options: canStart, status (live suggestion_status), onSuggest(button). Null when nothing to show. */
    function renderSuggestion(document, view, options) {
        options = options || {};
        const suggestion = view.suggestion || null;
        const status = options.status !== undefined ? options.status : (view.suggestion_status || null);
        const eligible = ELIGIBLE.includes(view.result), busy = status === 'queued' || status === 'active';
        const done = suggestion && suggestion.status === 'done';
        const canSuggest = options.canStart && eligible;
        if (!suggestion && !busy && !canSuggest) return null;
        const box = node(document, 'section', undefined, 'coverage-suggest');
        box.append(node(document, 'h3', done ? 'Suggested FAQ' : 'FAQ suggestion', 'coverage-step-head'));
        if (done) {
            box.append(suggestField(document, 'Question', suggestion.faq_question), suggestField(document, 'Answer', suggestion.faq_answer));
            const missing = suggestion.missing || [];
            if (missing.length) {
                const list = node(document, 'ul', undefined, 'coverage-suggest-missing');
                missing.forEach(item => { const li = node(document, 'li', item); li.dir = 'auto'; list.append(li); });
                box.append(node(document, 'span', 'Missing facts', 'coverage-suggest-label'), list);
            }
            const titlesById = new Map((suggestion.chunks || []).map(c => [c.chunk_id, c.title || c.chunk_id]));
            const used = (suggestion.used_chunk_ids || []).map(id => titlesById.get(id) || id);
            const usedLine = node(document, 'p', undefined, 'coverage-suggest-used');
            const usedTitles = node(document, 'span', used.length ? used.join(' · ') : 'none'); usedTitles.dir = 'auto';
            usedLine.append(node(document, 'span', 'Chunks used: '), usedTitles);
            box.append(usedLine);
            const numbers = suggestion.unverified_numbers || [];
            if (numbers.length) box.append(node(document, 'p', 'Check these numbers; they are not in the chunks: ' + numbers.join(', '), 'coverage-suggest-warning'));
        } else if (suggestion && suggestion.status === 'error') {
            box.append(node(document, 'p', 'Suggestion failed: ' + suggestReason(suggestion.error_code), 'coverage-suggest-error'));
        } else if (!busy) {
            box.append(node(document, 'p', 'Draft a FAQ entry from the closest chunks this check saved. It is a draft to read and copy; the knowledge base is not changed.', 'coverage-hint'));
        }
        if (busy && !canSuggest) box.append(node(document, 'p', SUGGEST_MARKS[status], 'coverage-hint'));
        const actions = node(document, 'div', undefined, 'coverage-actions');
        if (done) {
            const copy = node(document, 'button', 'Copy', 'coverage-secondary'); copy.type = 'button';
            copy.addEventListener('click', async () => {
                try { await global.navigator.clipboard.writeText(suggestion.faq_question + '\n\n' + suggestion.faq_answer); copy.textContent = 'Copied'; }
                catch (e) { copy.textContent = 'Copy failed'; }
            });
            actions.append(copy);
        }
        if (canSuggest) {
            const button = node(document, 'button', busy ? 'Suggesting…' : (suggestion ? 'Suggest again' : 'Suggest FAQ'), 'coverage-secondary coverage-suggest-button');
            button.type = 'button'; button.disabled = busy;
            button.addEventListener('click', () => { if (options.onSuggest) options.onSuggest(button); });
            actions.append(button);
        }
        if (actions.children.length) box.append(actions);
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
            if (SUGGEST_MARKS[row.suggestion_status]) r.append(node(document, 'span', SUGGEST_MARKS[row.suggestion_status], 'coverage-suggest-mark'));
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
        if (!checks.length) { const tr = node(document, 'tr'); const td = node(document, 'td', 'No checks yet.', 'coverage-empty'); td.setAttribute('colspan', '7'); tr.append(td); tbody.replaceChildren(tr); return; }
        tbody.replaceChildren(...checks.map(check => {
            const tr = node(document, 'tr');
            tr.append(node(document, 'td', String(check.created_at || '').replace('T', ' ').slice(0, 19)));
            const f = node(document, 'td', check.file_name); f.dir = 'auto'; tr.append(f);
            const progress = check.done + '/' + check.row_count + (check.state === 'running' && check.active_row ? ' · row ' + check.active_row : '');
            tr.append(node(document, 'td', check.row_count), node(document, 'td', progress), node(document, 'td', check.state));
            tr.append(node(document, 'td', check.prompt_version || '—'));
            const cell = node(document, 'td', undefined, 'coverage-actions');
            const add = (text, fn) => { const b = node(document, 'button', text, 'coverage-secondary'); b.type = 'button'; b.addEventListener('click', () => fn(check.run_id)); cell.append(b); };
            add('Open', actions.open);
            if (canStart && ['queued', 'running'].includes(check.state)) add('Stop', actions.stop);
            if (canStart && ['cancelled', 'interrupted'].includes(check.state)) add('Resume', actions.resume);
            if (canStart && FINISHED.includes(check.state)) add('Delete', actions.delete);
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
            expanded: new Set(), details: new Map(), lastKey: null, lastActive: null, activeTr: null, suggest: null
        };
        if (follow) follow.checked = true;
        function showError(code) { $('Error').textContent = code ? API_ERRORS[code] || 'Error: ' + code : ''; $('Error').hidden = !code; }
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
        function suggestBusy() { const s = state.suggest; return !!(s && (s.queued > 0 || s.active_row)); }
        function renderSuggestHeader() {
            const s = state.suggest || { queued: 0, active_row: null, done: 0, errors: 0, eligible: 0 }, busy = suggestBusy();
            if ($('SuggestAll')) {
                $('SuggestAll').hidden = !canStart;
                $('SuggestAll').textContent = 'Suggest for all unanswered (' + s.eligible + ')';
                $('SuggestAll').disabled = !s.eligible;
            }
            if ($('SuggestProgress')) { $('SuggestProgress').hidden = !busy; $('SuggestProgress').textContent = 'Suggestions: ' + s.done + '/' + (s.done + s.eligible); }
            if ($('SuggestStop')) $('SuggestStop').hidden = !(canStart && busy);
        }
        async function suggestRows(payload, button) {
            const text = button && button.textContent;
            if (button) { button.disabled = true; button.textContent = 'Suggesting…'; }
            try { await post('checks/' + state.open + '/suggestions', payload); await refresh(); }
            catch (e) { showError(e.message); if (button) { button.disabled = false; button.textContent = text; } }
        }
        // The suggestion box of an open row; redrawn alone when the row's suggestion status changes.
        function placeBox(entry, rowNumber) {
            if (!entry.view || !entry.slot) return;
            const box = renderSuggestion(document, entry.view, {
                canStart, status: entry.status, onSuggest: button => suggestRows({ rows: [rowNumber] }, button) });
            entry.slot.replaceChildren(...(box ? [box] : []));
        }
        function loadDetail(id, rowNumber, entry, full) {
            call('checks/' + id + '/rows/' + rowNumber).then(view => {
                if (state.open !== id || state.details.get(rowNumber) !== entry) return;
                entry.view = view;
                if (full || !entry.slot) {
                    const parts = detailParts(document, view);
                    entry.slot = node(document, 'div', undefined, 'coverage-suggest-slot');
                    parts.splice(1, 0, entry.slot);
                    entry.element.textContent = '';
                    entry.element.replaceChildren(...parts);
                }
                placeBox(entry, rowNumber);
            }, e => {
                if (!full) { showError(e.message); return; }
                if (state.details.get(rowNumber) === entry) state.details.delete(rowNumber);
                entry.element.textContent = 'Could not load details: ' + e.message;
            });
        }
        // One cached element per opened row: fetched once, again when the row's result changes; a changed
        // suggestion status redraws only the suggestion box.
        function detailFor(row, cell) {
            const id = state.open, result = row.result || null, status = row.suggestion_status || null;
            let entry = state.details.get(row.row);
            if (!entry || entry.result !== result) {
                entry = { result, status, element: node(document, 'div', 'Loading details…', 'coverage-detail-body'), view: null, slot: null };
                state.details.set(row.row, entry);
                loadDetail(id, row.row, entry, true);
            } else if (entry.status !== status) {
                entry.status = status;
                if (status === 'queued' || status === 'active') placeBox(entry, row.row);
                else loadDetail(id, row.row, entry, false);
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
            const query = filter === 'suggested' ? '&suggested=1' : (filter ? '&result=' + encodeURIComponent(filter) : '');
            const [page, summary] = await Promise.all([
                call('checks/' + id + '/rows?offset=' + offset + '&limit=' + PAGE_SIZE + query),
                call('checks/' + id + '/suggestions')]);
            if (state.open !== id) return;
            state.openState = detail.meta && detail.meta.state;
            state.suggest = summary;
            $('Results').hidden = false;
            renderCounts(document, $('Counts'), detail.counts);
            updateStop();
            renderSuggestHeader();
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
        }
        // Polls every 3 seconds while a check runs or the open check has suggestions queued or active.
        function updateTimer() {
            const active = state.checks.some(c => c.state === 'queued' || c.state === 'running') || suggestBusy();
            if (active && !state.timer) state.timer = global.setInterval(() => refresh(), 3000);
            if (!active && state.timer) { global.clearInterval(state.timer); state.timer = null; }
        }
        async function refresh() {
            try { await loadChecks(); await loadResults(); } catch (e) { showError(e.message); }
            updateTimer();
        }
        async function stopRun(id) {
            try { await post('checks/' + id + '/cancel'); await refresh(); } catch (e) { showError(e.message); }
        }
        const actions = {
            open: async id => {
                if (state.open !== id) {
                    state.expanded = new Set(); state.details = new Map(); state.lastActive = null; state.openState = null; state.suggest = null;
                    if (follow) follow.checked = true;
                }
                state.open = id; state.offset = 0; state.lastKey = null; showError(''); await refresh();
            },
            stop: stopRun,
            resume: async id => { try { await post('checks/' + id + '/resume'); await refresh(); } catch (e) { showError(e.message); } },
            delete: async id => {
                if (!global.confirm(DELETE_CONFIRM)) return;
                try {
                    await call('checks/' + id, { method: 'DELETE' });
                    if (state.open === id) closeResults();
                    await refresh();
                } catch (e) { showError(e.message); }
            }
        };
        function closeResults() {
            Object.assign(state, { open: null, openState: null, offset: 0, total: 0, lastKey: null, lastActive: null, activeTr: null, suggest: null });
            state.expanded = new Set(); state.details = new Map();
            $('Results').hidden = true; $('Rows').replaceChildren(); $('Download').setAttribute('href', '#');
            updateStop(); renderSuggestHeader();
        }
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
        if (canStart && $('SuggestAll')) $('SuggestAll').addEventListener('click', () => suggestRows({ all: true }, $('SuggestAll')));
        if (canStart && $('SuggestStop')) $('SuggestStop').addEventListener('click', async () => {
            try { await post('checks/' + state.open + '/suggestions/cancel'); await refresh(); } catch (e) { showError(e.message); }
        });
        renderSuggestHeader();
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
        boot, batchLine, renderCounts, renderLegend, renderRows, renderChecks, renderDetail, renderSuggestion, label, reason,
        RESULT_LABELS, ERROR_REASONS, SUGGEST_ERRORS, API_ERRORS, LEGEND, PAGE_SIZE
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else if (global.document) boot(global.document);
})(typeof window !== 'undefined' ? window : globalThis);
