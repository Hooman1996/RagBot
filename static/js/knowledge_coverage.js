/* Main-dashboard audit UI. Text-only DOM rendering; no private browser storage. */
(function (global) {
    'use strict';
    const CONTRACT = 'coverage-page-2';
    const LABELS = {
        prepared: 'Prepared', pending_model: 'Pending model', needs_context: 'Needs preceding context', needs_review: 'Needs review',
        uncertain_preparation: 'Preparation needs review', invalid_input: 'Invalid input', failed: 'Error',
        covered_reachable: 'Covered and reachable', covered_not_reachable: 'Covered but not reachable',
        possible_partial_gap: 'Possible partial KB gap', possible_gap: 'Possible KB gap',
        excluded: 'Excluded', pending: 'Pending / not evaluated', error: 'Error',
        full: 'Verified full', partial: 'Partial support', unsupported: 'Unsupported in evaluated scope',
        uncertain: 'Uncertain', not_evaluated: 'Not evaluated', unavailable: 'No preceding history', user_only: 'User-only history'
    };
    function label(value) { return LABELS[value] || String(value || 'Not evaluated').replaceAll('_', ' '); }
    function headersFromCsv(text, delimiter) {
        text = text.replace(/^\uFEFF/, '');
        const cells = []; let cell = ''; let quoted = false;
        for (let i = 0; i < text.length; i++) {
            const c = text[i];
            if (c === '"') {
                if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
                else quoted = !quoted;
            } else if (!quoted && c === delimiter) { cells.push(cell); cell = ''; }
            else if (!quoted && (c === '\n' || c === '\r')) { cells.push(cell); return cells; }
            else cell += c;
        }
        if (quoted) throw new Error('The CSV header has an unclosed quote.');
        cells.push(cell); return cells;
    }
    function node(document, tag, text, className) {
        const n = document.createElement(tag);
        if (text !== undefined) n.textContent = String(text);
        if (className) n.className = className;
        return n;
    }
    function boot(document) {
        const root = document.getElementById('coverageRoot'); if (!root) return;
        const $ = id => document.getElementById('coverage' + id);
        if (root.dataset.contract !== CONTRACT) { $('Status').textContent = 'Workspace version mismatch. Reload this page.'; return; }
        const canStart = root.dataset.canStart === 'true', canEvidence = root.dataset.canEvidence === 'true';
        let datasets = [], snapshots = [], currentDataset = '', currentRun = '', offset = 0, total = 0;
        let selected = new Set(), fileBytes = null, lastEvidenceButton = null, poll = null, loading = false, querySequence = 0;
        let exportRevisionRun = '', evidenceSequence=0, progressSequence=0, recommendationPanel=null, selectedEvidenceRow='', progressInFlight=null, viewEpoch=0, inputPoll=null;
        let runExport=null;
        function viewChanged() { viewEpoch++;if(inputPoll){global.clearInterval(inputPoll);inputPoll=null;}querySequence++; progressSequence++; closeEvidence(false); exportRevisionRun=''; if(runExport)runExport.setRun(currentRun); }
        const status = message => { $('Status').textContent = message; };
        const fail = error => { $('Error').hidden = false; $('Error').textContent = error.message || 'The operation could not complete. Try again.'; };
        const clearError = () => { $('Error').hidden = true; $('Error').textContent = ''; };
        if(global.KnowledgeRunExport && $('RunExport') && root.dataset.canExport==='true')runExport=global.KnowledgeRunExport.mount($('RunExport'),api,fail);
        async function api(path, options) {
            const response = await global.fetch('/api/knowledge-coverage/' + path, options);
            const body = await response.json();
            if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Check the import mapping and selected settings.');
            return body;
        }
        function options(select, values, selectedValue, empty) {
            select.replaceChildren(node(document, 'option', empty)); select.firstChild.value = '';
            values.forEach(item => { const option = node(document, 'option', item.label); option.value = item.value; select.appendChild(option); });
            select.value = selectedValue;
        }
        function counts(value) { return Object.entries(value || {}).map(([key, count]) => label(key) + ': ' + count).join(' · '); }
        function selection() {
            $('SelectionCount').textContent = selected.size + ' of 5 selected';
            $('Start').disabled = selected.size < 1 || !currentDataset || !$('Snapshot').value;
        }
        async function refreshDatasets() {
            datasets = await api('datasets');
            if (canStart) {
                options($('Dataset'), datasets.map(d => ({value:d.dataset_id,label:d.structure.selected_row_count + ' questions · ' + d.dataset_id.slice(-8)})), currentDataset, 'Choose an imported dataset');
                const d = datasets.find(x => x.dataset_id === currentDataset);
                if (d) $('DatasetSummary').textContent = d.structure.selected_row_count + ' selected queries of ' + d.structure.source_row_count + ' source records · ' + counts(d.preparation_counts) + (d.structure.timestamp_status_counts ? ' · Timestamps: ' + counts(d.structure.timestamp_status_counts) : '') + (d.preparation_status !== 'ready' ? ' · Preparing input…' : '');
            }
        }
        function documents() {
            const snapshot = snapshots.find(s => s.snapshot_id === $('Snapshot').value);
            $('Documents').replaceChildren();
            (snapshot ? snapshot.documents : []).forEach(title => {
                const item = node(document, 'label'); const checkbox = node(document, 'input'); checkbox.type = 'checkbox'; checkbox.checked = true; checkbox.value = title;
                item.append(checkbox, node(document, 'span', title)); $('Documents').append(item);
            }); selection();
        }
        async function refreshSnapshots() {
            if (!canStart) return;
            snapshots = await api('snapshots');
            options($('Snapshot'), snapshots.map(s => ({value:s.snapshot_id,label:s.record_count + ' entries · ' + s.snapshot_id.slice(0,8)})), $('Snapshot').value, 'Choose a knowledge revision');
            documents();
        }
        async function refreshRuns() {
            const runs = await api('runs');
            options($('Runs'), runs.map(r => ({value:r.run_id,label:label(r.state) + ' · ' + r.selected_row_ids.length + ' questions · ' + r.run_id.slice(-8)})), currentRun, 'Select a previous run');
        }
        function badge(text, value) {
            const b = node(document, 'span', text, 'coverage-badge');
            b.dataset.tone = value === 'covered_reachable' ? 'good' : ['possible_gap','possible_partial_gap','needs_context','needs_review'].includes(value) ? 'review' : value === 'error' ? 'error' : 'neutral';
            return b;
        }
        function renderRows(rows) {
            $('Rows').replaceChildren();
            if (!rows.length) {
                const tr = node(document, 'tr'); const td = node(document, 'td', currentDataset || currentRun ? 'No matching rows. Change the filter or wait for input preparation.' : 'Import questions to begin. No coverage results have been assessed.', 'coverage-empty'); td.colSpan = 6; tr.append(td); $('Rows').append(tr);
            }
            rows.forEach(row => {
                const tr = node(document, 'tr');
                const first = node(document, 'td');
                if (canStart && !currentRun) {
                    const checkbox = node(document, 'input'); checkbox.type = 'checkbox'; checkbox.checked = selected.has(row.source_row_id);
                    checkbox.setAttribute('aria-label', 'Select source row ' + row.source_record_ordinal);
                    checkbox.addEventListener('change', () => {
                        if (checkbox.checked && selected.size >= 5) { checkbox.checked = false; fail(new Error('Choose at most five questions for this pilot.')); return; }
                        if (checkbox.checked) selected.add(row.source_row_id); else selected.delete(row.source_row_id);
                        selection();
                    }); first.append(checkbox, document.createTextNode(' '));
                }
                first.append(node(document, 'bdi', '#' + row.source_record_ordinal)); tr.append(first);
                const query = node(document, 'td', undefined, 'coverage-query'); query.dir='auto';query.append(node(document,'div',row.input_query_redacted,'coverage-query-text'));tr.append(query);
                const prep = node(document, 'td'); prep.append(badge(label(row.preparation_status), row.preparation_status));
                if (row.history_status) prep.append(node(document, 'p', label(row.history_status))); tr.append(prep);
                const outcome = row.outcome || (row.preparation_status === 'needs_context' ? 'needs_context' : 'pending');
                const result = node(document, 'td'); result.append(badge(label(outcome), outcome)); tr.append(result);
                tr.append(node(document, 'td', row.evaluated_entry_count || 0));
                const evidence = node(document, 'td');
                if (currentRun && canEvidence) {
                    const button = node(document, 'button', 'Review', 'coverage-link'); button.type = 'button'; button.id = 'coverage-review-' + row.source_row_id; button.setAttribute('aria-label', 'Review evidence for row ' + row.source_record_ordinal);
                    button.addEventListener('click', () => openEvidence(row.source_row_id, button)); evidence.append(button);
                } else evidence.textContent = currentRun ? 'Restricted' : 'Not assessed';
                tr.append(evidence); $('Rows').append(tr);
            });
            $('Previous').disabled = offset === 0; $('Next').disabled = offset + 25 >= total;
            $('PageLabel').textContent = 'Page ' + (Math.floor(offset / 25) + 1);
            $('ResultCount').textContent = total + ' matching rows' + (currentRun ? ' · download always includes the full dataset' : ' · select an explicit pilot');
        }
        async function refreshRows() {
            const sequence = ++querySequence;
            if (!currentRun && !currentDataset) { total = 0; renderRows([]); return; }
            const path = currentRun ? 'runs/' + encodeURIComponent(currentRun) + '/results?offset=' + offset + '&limit=25&outcome=' + encodeURIComponent($('Filter').value) + '&search=' + encodeURIComponent($('Search').value) : 'datasets/' + encodeURIComponent(currentDataset) + '/rows?offset=' + offset + '&limit=25';
            let data;try{data=await api(path);}catch(error){if(sequence!==querySequence)return;throw error;}
            if (sequence !== querySequence) return;
            total = data.total; renderRows(data.rows);
        }
        async function progress() {
            if (!currentRun) return;
            const requestedRun=currentRun, epoch=viewEpoch;
            if(progressInFlight && progressInFlight.run===requestedRun && progressInFlight.epoch===epoch)return;
            const marker={run:requestedRun,epoch};progressInFlight=marker;
            try {
            const sequence=++progressSequence;
            let run;try{run=await api('runs/'+encodeURIComponent(requestedRun));}catch(error){if(requestedRun!==currentRun||epoch!==viewEpoch||sequence!==progressSequence)return;throw error;}
            if(requestedRun!==currentRun || epoch!==viewEpoch || sequence!==progressSequence)return;
            const activeOption = Array.from($('Runs').children).find(option => option.value === currentRun);
            if (activeOption) activeOption.textContent = label(run.state) + ' · ' + run.selected_row_ids.length + ' questions · ' + currentRun.slice(-8);
            $('Progress').max = run.selected_row_ids.length; $('Progress').value = run.completed_pilot_rows;
            const errors=(run.outcome_counts||{}).error||0;
            const runLabel=run.state==='completed' && errors ? 'completed with errors' : ({failed:'Failed pilot',interrupted:'Interrupted pilot',cancelled:'Cancelled pilot'}[run.state]||label(run.state));
            $('ProgressText').textContent = runLabel + ' · ' + run.completed_pilot_rows + ' of ' + run.selected_row_ids.length + ' pilot questions processed · ' + run.input_row_count + ' rows retained' + (run.stage ? ' · ' + label(run.stage) : '');
            if($('RunCounts')) { const c=run.outcome_counts||{}; $('RunCounts').replaceChildren(); [['Imported queries',run.input_row_count],['Pilot processed',run.completed_pilot_rows+' / '+run.selected_row_ids.length],['Pending / not evaluated',c.pending||0],['Covered · reachable',c.covered_reachable||0],['Covered · retrieval work',c.covered_not_reachable||0],['Possible gaps',(c.possible_gap||0)+(c.possible_partial_gap||0)],['Context / review',(c.needs_context||0)+(c.needs_review||0)],['Excluded / errors',(c.excluded||0)+' / '+(c.error||0)]].forEach(([title,value])=>{const cell=node(document,'div');cell.append(node(document,'strong',value),node(document,'span',title));$('RunCounts').append(cell);}); }
            $('Cancel').hidden = !canStart || !['queued','running'].includes(run.state);
            $('Resume').hidden = !canStart || (!['failed','interrupted','cancelled'].includes(run.state) && !(run.state === 'completed' && run.retryable_rows > 0));
            $('PrepareExport').hidden = root.dataset.canExport !== 'true';
            $('Export').hidden = root.dataset.canExport !== 'true' || exportRevisionRun !== currentRun; $('Manifest').hidden = $('Export').hidden;
            if (exportRevisionRun !== currentRun) $('ExportState').textContent = 'Prepare a frozen CSV and matching manifest from current progress.';
            status(run.state === 'incompatible' ? 'Knowledge or serving revision changed. This pilot requires review; start a new compatible run.' : 'Pilot selection: ' + run.selected_row_ids.length + ' questions. Unselected rows remain pending / not evaluated.');
            if (!['queued','running'].includes(run.state) && poll) { global.clearInterval(poll); poll = null; }
            await refreshRows();
            } finally {if(progressInFlight===marker)progressInFlight=null;}
        }
        function startPoll() {
            if (poll) global.clearInterval(poll);
            poll = global.setInterval(() => progress().catch(fail), 2000);
        }
        function appendText(container, title, text, dir) {
            container.append(node(document, 'h3', title));
            const p = node(document, 'p', text || 'Unavailable'); if (dir) p.dir = dir; container.append(p);
        }
        async function openEvidence(rowId, button) {
            const evidenceRun = currentRun, sequence=++evidenceSequence; selectedEvidenceRow=rowId; if(recommendationPanel)recommendationPanel.stop(); lastEvidenceButton = button; const panel = $('EvidenceContent'); panel.replaceChildren(node(document, 'p', 'Loading evidence…'));
            $('Evidence').focus();
            if ($('Evidence').scrollIntoView) $('Evidence').scrollIntoView({block:'start',behavior:'auto'});
            try {
                const data = await api('runs/' + encodeURIComponent(evidenceRun) + '/rows/' + encodeURIComponent(rowId));
                if (evidenceRun !== currentRun || sequence!==evidenceSequence) return;
                panel.replaceChildren();
                if (data.evidence_visibility === 'snapshot_mismatch') { panel.append(node(document, 'p', 'This run is incompatible with its recorded knowledge revision. Evidence is withheld.')); return; }
                const row = data.result;
                panel.className = '';
                const selectedHeader=node(document,'div',undefined,'coverage-selected-query');
                selectedHeader.append(node(document,'strong','Selected query · source row '+row.source_record_ordinal),node(document,'p',row.standalone_query_redacted || row.normalized_query_redacted || row.input_query_redacted),badge(label(row.outcome),row.outcome));selectedHeader.children[1].dir='auto';selectedHeader.children[1].tabIndex=0;panel.append(selectedHeader);
                function group(id,title,open) {const block=node(document,'details',undefined,'coverage-detail-group');block.id=id;block.open=!!open;block.append(node(document,'summary',title));panel.append(block);return block;}
                const overview=group('coverage-detail-overview','Assessment and next step',true), aspects=group('coverage-detail-aspects','Requested aspects and conditions',true), sources=group('coverage-detail-sources','Numbered source evidence',false), proposals=group('coverage-detail-proposals','Missing information and question proposals',false), technical=group('coverage-detail-provenance','Provenance and validation',false);
                const nav=node(document,'nav',undefined,'coverage-detail-nav');nav.setAttribute('aria-label','Query detail sections');
                [[overview,'Assessment'],[aspects,'Aspects'],[sources,'Sources'],[proposals,'Proposals']].forEach(([section,text])=>{const link=node(document,'a',text,'coverage-link');link.href='#'+section.id;link.addEventListener('click',()=>{section.open=true;});nav.append(link);});panel.append(nav);
                if(panel.insertBefore)panel.insertBefore(nav,overview);
                appendText(overview, 'Assessment', label(row.outcome) + ' · ' + label(row.coverage_status));
                appendText(overview, 'Why', row.explanation || (row.scope_decision || {}).explanation || 'This row has not been evaluated.', 'auto');
                if (row.error_code) appendText(overview, 'Error code', row.error_code);
                if ((row.review_codes || []).length) appendText(overview, 'Review required', row.review_codes.map(label).join(' · '));
                (row.requested_aspects || []).forEach(aspect => {
                    const item = node(document, 'div', undefined, 'coverage-aspect'); item.append(node(document, 'span', aspect.aspect_id, 'coverage-aspect-id'));
                    const description = node(document, 'p', aspect.description); description.dir = 'auto'; item.append(description);
                    if (aspect.conditions.length) { const p = node(document, 'p', 'Conditions: ' + aspect.conditions.join(' · ')); p.dir = 'auto'; item.append(p); }
                    const assessment = row.audit_assessment || {};
                    const supported = (row.supported_aspects || []).some(a => (typeof a === 'string' ? a : a.aspect_id) === aspect.aspect_id);
                    const missing = (row.unresolved_aspects || []).some(a => (typeof a === 'string' ? a : a.aspect_id) === aspect.aspect_id);
                    const state = row.coverage_status === 'full' && supported ? 'Supported · verified' :
                        supported ? 'Apparent support · inspect conditions' : missing && ['possible_gap','possible_partial_gap'].includes(row.outcome) ?
                            'Missing in evaluated evidence' : 'Unresolved · needs review';
                    item.append(node(document, 'strong', state, 'coverage-aspect-state'));
                    const witnesses = (assessment.witness && assessment.witness.length ? assessment.witness : assessment.supports || []).filter(s => s.aspect_id === aspect.aspect_id);
                    witnesses.forEach(support => {
                        const p = node(document, 'p', support.applicability + (support.conditions.length ? ' · ' + support.conditions.join(' · ') : '')); p.dir = 'auto'; item.append(p);
                        support.citations.forEach(ref => {
                            const link = node(document, 'a', 'FAQ ' + ref.faq_entry_id + ' · sentence ' + ref.sentence_number, 'coverage-link');
                            link.href = '#coverage-source-' + ref.chunk_id + '-' + ref.sentence_number; link.addEventListener('click',()=>{sources.open=true;}); item.append(link);
                        });
                    });
                    aspects.append(item);
                });
                const cited = new Set((row.supporting_sentence_refs || []).map(r => r.chunk_id + ':' + r.sentence_number));
                data.evidence.forEach(entry => {
                    const source = node(document, 'section', undefined, 'coverage-citation');
                    const h = node(document, 'h3', 'FAQ ' + entry.faq_entry_id + ' · ' + [entry.main_category,entry.sub_category].filter(Boolean).join(' / ')); source.append(h);
                    const title = node(document, 'p', entry.question); title.dir = 'auto'; source.append(title);
                    entry.sentences.forEach(sentence => {
                        const line = node(document, 'div', undefined, 'coverage-sentence' + (cited.has(entry.chunk_id + ':' + sentence.sentence_number) ? ' coverage-highlight' : ''));
                        line.id = 'coverage-source-' + entry.chunk_id + '-' + sentence.sentence_number;
                        line.append(node(document, 'bdi', sentence.sentence_number, 'coverage-sentence-number'));
                        const text = node(document, 'p', sentence.text); text.dir = 'auto'; line.append(text); source.append(line);
                    }); sources.append(source);
                });
                appendText(overview, 'Production context', label(row.production_context_sufficiency));
                appendText(overview, 'Stopping reason', label(row.stopping_reason));
                appendText(overview, 'Verification', label(row.verification_result));
                (row.verifications || []).forEach(v => appendText(overview, 'Verification · ' + label(v.verdict), v.explanation, 'auto'));
                if (row.verification_reason) appendText(overview, 'Verification reason', row.verification_reason, 'auto');
                const search = (row.evaluation_scope || {}).bundle_search;
                if (search && row.coverage_status !== 'full') appendText(technical, 'Compatibility search',
                    'Bounded search · at most ' + search.seed_limit + ' seeds · ' + search.bundles_considered + ' bundles considered. A missing compatible proof is not proof of a missing fact.');
                (row.validation_diagnostics || []).forEach(d => appendText(technical, 'Output validation',
                    d.responsibility + ' · ' + d.schema_version + ' · ' + d.stage + ' · ' + (d.field_path || []).join('.') + ' · ' + d.error_type));
                (row.failure_diagnostics || []).forEach(d => appendText(technical, 'Model request',
                    label(d.failure_category) + ' · ' + label(d.boundary) + ' · ' + label(d.evaluation_phase || 'unknown') +
                    ' · attempt ' + (d.attempt || 1) + ' · ' + (d.duration_ms || 0) + ' ms'));
                if (global.KnowledgeRecommendations) recommendationPanel=global.KnowledgeRecommendations.mount(proposals, {runId:evidenceRun,rowId:rowId,getCoverageSource:()=>runExport?runExport.getSource(evidenceRun):'',focusCoverageSource:()=>runExport&&runExport.focusSource(),onRevisionChange:runExport?()=>runExport.refresh():null});
                const details=technical;
                appendText(details, 'Original query · redacted', row.input_query_redacted, 'auto');
                appendText(details, 'Retrieval wording', row.canonical_retrieval_query_redacted, 'auto');
                appendText(details, 'History', label(row.history_status));
                appendText(details, 'Snapshot', row.kb_snapshot_id);
                appendText(details, 'Entries checked', row.evaluated_entry_count);
                appendText(details, 'Review codes', (row.review_codes || []).join(' · '));
                if (row.output_recovery_count) appendText(details, 'Fresh output recovery attempts', row.output_recovery_count + ' · ' + row.recovery_policy);
            } catch (error) { if(sequence!==evidenceSequence || evidenceRun!==currentRun)return; fail(error); panel.replaceChildren(node(document, 'p', 'Evidence could not load. Select this row again to retry.')); }
        }
        function closeEvidence(returnFocus=true) { evidenceSequence++;selectedEvidenceRow='';if(recommendationPanel){recommendationPanel.stop();recommendationPanel=null;} $('EvidenceContent').className = 'coverage-empty'; $('EvidenceContent').replaceChildren(node(document, 'p', 'Open an assessed query to inspect its evidence.')); if(returnFocus){const target=lastEvidenceButton && document.getElementById(lastEvidenceButton.id); if(target) target.focus(); else $('Search').focus();} }
        $('CloseEvidence').addEventListener('click', closeEvidence);
        $('Evidence').addEventListener('keydown', event => { if (event.key === 'Escape') closeEvidence(); });
        $('Previous').addEventListener('click', () => { offset = Math.max(0,offset - 25); refreshRows().catch(fail); });
        $('Next').addEventListener('click', () => { offset += 25; refreshRows().catch(fail); });
        let searchTimer;
        $('Search').addEventListener('input', () => { global.clearTimeout(searchTimer); searchTimer = global.setTimeout(() => { offset = 0; refreshRows().catch(fail); },250); });
        $('Filter').addEventListener('change', () => { offset = 0; refreshRows().catch(fail); });
        $('Runs').addEventListener('change', async () => { currentRun = $('Runs').value; offset = 0; viewChanged(); clearError(); if (currentRun) { startPoll(); await progress().catch(fail); } else { if (poll) global.clearInterval(poll); await refreshRows().catch(fail); } });
        $('Cancel').addEventListener('click', async () => { try { await api('runs/' + currentRun + '/cancel',{method:'POST'}); status('Cancellation requested. Completed rows remain available.'); await progress(); } catch(e) { fail(e); } });
        $('Resume').addEventListener('click', async () => { try { await api('runs/' + currentRun + '/retry',{method:'POST'}); startPoll(); await progress(); } catch(e) { fail(e); } });
        $('PrepareExport').addEventListener('click', async () => {
            const run = currentRun; $('PrepareExport').disabled = true; clearError();
            try {
                const revision = await api('runs/' + encodeURIComponent(run) + '/export-revisions', {method:'POST'});
                if (run !== currentRun) return;
                const suffix = '?revision_id=' + encodeURIComponent(revision.export_revision_id);
                $('Export').href = '/api/knowledge-coverage/runs/' + encodeURIComponent(run) + '/export' + suffix;
                $('Manifest').href = '/api/knowledge-coverage/runs/' + encodeURIComponent(run) + '/export-manifest' + suffix;
                exportRevisionRun = run; $('Export').hidden = false; $('Manifest').hidden = false;
                $('ExportState').textContent = 'Frozen ' + revision.export_captured_at + ' · ' + label(revision.state) + ' pilot · ' + revision.row_count + ' rows. Prepare again to include newer progress.';
            } catch(e) { fail(e); } finally { $('PrepareExport').disabled = false; }
        });
        if (canStart) {
            function mapHeaders() {
                if (!fileBytes) return;
                const headers = headersFromCsv(new TextDecoder('utf-8',{fatal:true}).decode(fileBytes), $('Delimiter').value);
                if (new Set(headers).size !== headers.length || headers.some(h => !h)) throw new Error('CSV column names must be unique and nonempty.');
                [['QueryColumn','query','Choose the question column'],['SessionColumn','session_id','Independent rows'],['RoleColumn','role','All rows are user questions'],['TimestampColumn','timestamp','No combined timestamp'],['DateColumn','date','No separate date'],['TimeColumn','time','No separate time']].forEach(([id,guess,empty]) => options($(id),headers.map(h=>({value:h,label:h})),headers.includes(guess)?guess:'',empty));
            }
            $('File').addEventListener('change', async () => { clearError(); try { const file = $('File').files[0]; if (!file) return; if (file.size > Number(root.dataset.uploadLimit)) throw new Error('This CSV exceeds the upload limit.'); fileBytes = new Uint8Array(await file.arrayBuffer()); mapHeaders(); } catch(e) { fileBytes = null; fail(e); } });
            $('Delimiter').addEventListener('change', () => { try { mapHeaders(); } catch(e) { fail(e); } });
            $('ImportForm').addEventListener('submit', async event => {
                event.preventDefault(); if (loading || !fileBytes) return; const importEpoch=viewEpoch; clearError(); loading = true; $('Upload').disabled = true;
                try {
                    const mapping = {query:$('QueryColumn').value,session:$('SessionColumn').value||null,role:$('RoleColumn').value||null,
                        timestamp:$('TimestampColumn').value||null,date:$('DateColumn').value||null,time:$('TimeColumn').value||null};
                    let binary = ''; for (let i=0;i<fileBytes.length;i++) binary += String.fromCharCode(fileBytes[i]);
                    status('Importing and validating mapped records…');
                    const data = await api('datasets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv_base64:global.btoa(binary),mapping,
                        calendar:$('Calendar').value,source_timezone:$('Timezone').value||null,authoritative_source_order:$('TrustedOrder').checked,delimiter:$('Delimiter').value})});
                    if(importEpoch!==viewEpoch){await refreshDatasets();return;}
                    currentDataset = data.dataset_id; currentRun = ''; viewChanged(); selected.clear(); offset = 0;
                    await refreshDatasets(); selection(); await refreshRows();
                    const inputEpoch=viewEpoch;inputPoll=global.setInterval(async()=>{if(inputEpoch!==viewEpoch)return;try{await refreshDatasets();if(inputEpoch!==viewEpoch)return;await refreshRows();if(inputEpoch===viewEpoch && datasets.find(d=>d.dataset_id===currentDataset)?.preparation_status==='ready'){global.clearInterval(inputPoll);inputPoll=null;status('Input ready. Select up to five rows for a pilot; all rows will remain in the export.');}}catch(e){if(inputEpoch===viewEpoch){global.clearInterval(inputPoll);inputPoll=null;fail(e);}}},2000);
                } catch(e) { if(importEpoch===viewEpoch)fail(e); } finally { loading = false; $('Upload').disabled = false; }
            });
            $('Dataset').addEventListener('change', async () => { currentDataset = $('Dataset').value; currentRun=''; viewChanged(); selected.clear(); offset=0; $('Runs').value=''; if(poll) global.clearInterval(poll); await refreshDatasets().catch(fail); selection(); await refreshRows().catch(fail); });
            $('Snapshot').addEventListener('change', documents);
            $('Capture').addEventListener('click', async () => { $('Capture').disabled = true; clearError(); status('Capturing a consistent knowledge revision…'); try { const s=await api('snapshots',{method:'POST'}); await refreshSnapshots(); $('Snapshot').value=s.snapshot_id; documents(); status('Knowledge revision captured. Select questions and start a pilot.'); } catch(e) { fail(e); } finally { $('Capture').disabled=false; } });
            $('ClearSelection').addEventListener('click', () => { selected.clear(); selection(); refreshRows().catch(fail); });
            $('Start').addEventListener('click', async () => {
                $('Start').disabled=true; clearError(); try {
                    const docs=Array.from($('Documents').querySelectorAll('input:checked')).map(n=>n.value);
                    const run=await api('runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:currentDataset,snapshot_id:$('Snapshot').value,row_ids:Array.from(selected),entry_budget:Number($('Budget').value),documents:docs})});
                    currentRun=run.run_id; viewChanged(); offset=0; await refreshRuns(); startPoll(); await progress();
                } catch(e) { fail(e); } finally { selection(); }
            });
        }
        if (global.localStorage.getItem('theme')==='light') document.body.classList.add('light-mode');
        $('Theme').addEventListener('click',()=> { const light=document.body.classList.toggle('light-mode'); global.localStorage.setItem('theme',light?'light':'dark'); });
        $('Language').addEventListener('click',()=> { const rtl=document.documentElement.dir!=='rtl'; document.documentElement.dir=rtl?'rtl':'ltr'; $('Language').setAttribute('aria-pressed',String(rtl)); });
        Promise.all([refreshDatasets(),refreshSnapshots(),refreshRuns()]).then(()=>status('Choose an imported dataset or upload questions to begin.')).catch(fail);
        return {refreshRows,progress,openEvidence};
    }
    const api = {contractVersion:CONTRACT,headersFromCsv,label,boot};
    if (typeof module !== 'undefined' && module.exports) module.exports=api;
    global.KnowledgeCoverage=api;
    if (global.document) { if(global.document.readyState==='loading') global.document.addEventListener('DOMContentLoaded',()=>boot(global.document)); else boot(global.document); }
})(typeof window !== 'undefined' ? window : globalThis);
