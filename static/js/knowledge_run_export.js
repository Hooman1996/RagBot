/* A5 explicit run-level revision selection. No model calls or private storage. */
(function(global) {
    'use strict';
    function mount(root, api, fail) {
        const document=root.ownerDocument;
        let run='', source='', generation=0, refreshSequence=0, selected=new Map(), preview=null, options=null;
        function el(tag,text,cls) {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
        function button(text,action,cls) {const n=el('button',text,cls||'coverage-secondary');n.type='button';n.addEventListener('click',async()=>{n.disabled=true;try{await action();}catch(e){if(n.isConnected)fail(e);}finally{n.disabled=false;}});return n;}
        function post(path,value) {return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value||{})});}
        const heading=el('h2','Run download'), intro=el('p','Freeze one coverage source, choose drafts and reviews for individual rows, then check the full-dataset summary. Filters and pagination never limit the CSV.','coverage-summary');
        const status=el('p','Open a pilot run to prepare its download.','coverage-summary');status.setAttribute('role','status');
        const sourceLabel=el('label','Frozen coverage source');const sourceSelect=el('select');sourceSelect.id='coverageExportSource';sourceLabel.append(sourceSelect);
        const freeze=button('Freeze current coverage',async()=>{
            const token=generation, rid=run;
            const captured=await post('runs/'+encodeURIComponent(rid)+'/export-revisions');
            if(token!==generation)return;
            source=captured.export_revision_id;selected.clear();invalidate();await refresh();
        });freeze.id='coverageFreezeSource';
        const sourceControls=el('div',undefined,'coverage-export-source');sourceControls.append(sourceLabel,freeze);
        const draftContainer=el('div'), summary=el('div',undefined,'coverage-export-summary');summary.setAttribute('aria-live','polite');
        const check=button('Check download summary',checkSummary), prepare=button('Prepare run CSV',prepareExport,'coverage-primary');check.id='coverageCheckRunExport';prepare.id='coveragePrepareRunExport';
        const actions=el('div',undefined,'coverage-run-actions');actions.append(check,prepare);
        const links=el('div',undefined,'recommendation-downloads');
        const warning=el('p','Proposal approval covers questions and taxonomy only. Independent confirmation of gaps remains pending; no answer or KB absence is approved.','coverage-scope-note');
        root.replaceChildren(heading,intro,status,sourceControls,draftContainer,summary,actions,links,warning);
        function invalidate(){preview=null;summary.replaceChildren();links.replaceChildren();prepare.disabled=true;}
        function payload(){return {coverage_export_revision_id:source,selections:Array.from(selected,([row,v])=>({source_row_id:row,...v}))};}
        function clearSources(){sourceSelect.replaceChildren(el('option','Choose an existing frozen source'));sourceSelect.firstChild.value='';}
        clearSources();check.disabled=true;prepare.disabled=true;freeze.disabled=true;
        sourceSelect.addEventListener('change',async()=>{source=sourceSelect.value;selected.clear();invalidate();try{await refresh();}catch(e){fail(e);}});
        function selectOptions(select,items,value,empty) {
            select.replaceChildren(el('option',empty));select.firstChild.value='';
            items.forEach(item=>{const option=el('option',item.label);option.value=item.value;select.append(option);});select.value=value;
        }
        function renderDrafts(data) {
            draftContainer.replaceChildren();
            if(!source){draftContainer.append(el('p','Select or freeze a coverage source before drafting or choosing recommendations.','coverage-summary'));return;}
            draftContainer.append(el('h3','Recommendation and review selection'));
            const rowIds=Array.from(new Set(data.draft_revisions.flatMap(d=>d.selected_row_ids)));
            if(!rowIds.length){draftContainer.append(el('p','No draft revisions for this run. Coverage-only export is available; eligible questions can be drafted from this selected source.','coverage-summary'));return;}
            const table=el('table'), head=el('thead'), hrow=el('tr');
            ['Source row','Draft revision','Pinned proposal review'].forEach(t=>hrow.append(el('th',t)));head.append(hrow);table.append(head);
            const body=el('tbody');
            rowIds.forEach(row=>{
                const candidates=data.draft_revisions.filter(d=>d.selected_row_ids.includes(row)), compatible=candidates.filter(d=>d.compatible&&!['queued','running'].includes(d.state));
                const tr=el('tr'), rowCell=el('td');const rowLabel=el('bdi','#'+((data.source_row_ordinals||{})[row]||'?'));const identity=el('details'),id=el('bdi',row,'coverage-id');identity.append(el('summary','Row identity'),id);rowCell.append(rowLabel,identity);tr.append(rowCell);
                const draftCell=el('td'), select=el('select');select.setAttribute('aria-label','Draft for '+row);
                const current=selected.get(row);
                selectOptions(select,compatible.map(d=>({value:d.recommendation_revision_id,label:d.row_statuses[row].replaceAll('_',' ')+' · '+d.created_at+' · '+d.recommendation_revision_id.slice(-8)})),current?.recommendation_revision_id||'','No draft selected');
                const count=el('p',candidates.length+' available · '+candidates.filter(d=>!d.compatible).length+' use a different coverage source','coverage-summary');draftCell.append(select,count);tr.append(draftCell);
                const reviewCell=el('td'), review=el('select');review.setAttribute('aria-label','Review for '+row);reviewCell.append(review);tr.append(reviewCell);
                function reviews() {
                    const draft=compatible.find(d=>d.recommendation_revision_id===select.value);
                    selectOptions(review,(draft?.review_revisions||[]).map(r=>({value:r.review_revision_id,label:Array.from(new Set(Object.entries(r.states).filter(([k])=>k.startsWith(row+':')).map(([,s])=>s.replaceAll('_',' ')))).join(' / ')+' · '+r.created_at})),selected.get(row)?.review_revision_id||'','Unreviewed · no decisions');
                    review.disabled=!draft;
                }
                reviews();
                select.addEventListener('change',()=>{if(select.value)selected.set(row,{recommendation_revision_id:select.value,review_revision_id:''});else selected.delete(row);invalidate();reviews();});
                review.addEventListener('change',()=>{const value=selected.get(row);if(value){value.review_revision_id=review.value;invalidate();}});
                body.append(tr);
            });
            table.append(body);const scroll=el('div',undefined,'coverage-table-scroll');scroll.tabIndex=0;scroll.setAttribute('aria-label','Scrollable revision selection');scroll.append(table);draftContainer.append(scroll);
            const details=el('details'), title=el('summary','All available draft revisions · including incompatible and unselected');details.append(title);
            data.draft_revisions.forEach(d=>{const p=el('p',(d.compatible?'Same coverage source':'Different coverage source')+' · '+d.state+' · '+d.recommendation_revision_id+' · source '+d.source_export_revision_id,'coverage-summary');p.dir='auto';details.append(p);});draftContainer.append(details);
        }
        async function refresh(){
            if(!run)return;
            const token=generation, seq=++refreshSequence, rid=run, expectedSource=source;
            const data=await api('runs/'+encodeURIComponent(rid)+'/export-options?coverage_export_revision_id='+encodeURIComponent(source));
            if(token!==generation||seq!==refreshSequence||expectedSource!==source)return;
            if(options && JSON.stringify(options)!==JSON.stringify(data))invalidate();options=data;clearSources();data.coverage_sources.forEach(s=>{const option=el('option',s.row_count+' rows · '+s.state+' · '+s.export_captured_at+' · '+s.export_revision_id.slice(-8));option.value=s.export_revision_id;sourceSelect.append(option);});sourceSelect.value=source;
            renderDrafts(data);freeze.disabled=false;check.disabled=!source;
            status.textContent=source?'All drafts started from query details will use this selected source. Changing it clears the draft selection.':'Choose one frozen coverage source. No draft is implicitly included.';
            if(data.source_summary)status.textContent+=' '+data.source_summary.total_source_rows+' source rows retained; '+data.source_summary.coverage_evaluated+' have coverage evaluations.';
        }
        async function checkSummary(){
            const token=generation, p=payload(), key=JSON.stringify(p);
            if(!source)throw new Error('Choose a frozen coverage source first.');
            const value=await post('runs/'+encodeURIComponent(run)+'/combined-export-preview',p);
            if(token!==generation||JSON.stringify(payload())!==key)return;
            preview=value;summary.replaceChildren(el('h3','Check before download'));
            const s=value.summary;
            summary.append(el('p',s.total_source_rows+' source rows · '+s.coverage_evaluated+' coverage evaluations · '+s.pending+' pending · '+s.excluded+' excluded · '+s.review_needed+' need context/review · '+s.errors+' errors'));
            summary.append(el('p',s.rows_with_selected_recommendations+' rows with selected draft revisions · review states: '+(Object.entries(s.recommendation_review_states).map(([k,v])=>k.replaceAll('_',' ')+': '+v).join(' · ')||'no proposals selected')));
            summary.append(el('p',s.unselected_drafts.length+' available row/draft combinations not selected, including '+s.incompatible_draft_count+' from incompatible sources. They are not included as recommendations.'));
            summary.append(el('p',value.evidence_visible?'Evidence-visible download.':'Restricted download: evidence, notes and proposal text are withheld.'));
            prepare.disabled=false;
        }
        async function prepareExport(){
            if(!preview)throw new Error('Check the download summary first.');
            const token=generation, p=payload(), key=JSON.stringify(p), rid=run;
            const value=await post('runs/'+encodeURIComponent(rid)+'/combined-export-revisions',p);
            if(token!==generation||JSON.stringify(payload())!==key)return;
            links.replaceChildren();
            [['Download run CSV','combined-export'],['Matching manifest','combined-export-manifest']].forEach(([label,path])=>{const a=el('a',label,'coverage-link');a.href='/api/knowledge-coverage/runs/'+encodeURIComponent(rid)+'/'+path+'?revision_id='+encodeURIComponent(value.export_revision_id);a.setAttribute('download','');links.append(a);});
            links.append(el('p',value.row_count+' rows · immutable download prepared '+value.captured_at+'. Later decisions require a new download.','coverage-summary'));
        }
        function setRun(value){generation++;refreshSequence++;run=value;source='';selected.clear();options=null;invalidate();clearSources();draftContainer.replaceChildren();root.hidden=!value;freeze.disabled=!value;check.disabled=true;status.textContent='Loading frozen sources and draft revisions…';if(value)refresh().catch(e=>{if(run===value)fail(e);});}
        return {setRun,refresh,getSource:rid=>rid===run?source:'',focusSource:()=>sourceSelect.focus()};
    }
    global.KnowledgeRunExport={mount};
    if(typeof module!=='undefined'&&module.exports)module.exports={mount};
})(typeof window!=='undefined'?window:globalThis);
