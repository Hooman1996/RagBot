/* Synthetic DOM/transport contracts; this is not a rendered browser test. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const ui = require('../static/js/knowledge_coverage.js');

class Element {
    constructor(tag, document) { this.tagName=tag.toUpperCase(); this.document=document; this.children=[]; this.dataset={}; this.listeners={}; this.attributes={}; this.value=''; this.hidden=false; this.checked=false; this.disabled=false; this.textContent=''; this.isConnected=true; this._id=''; this.className=''; }
    set id(value) { this._id=value; if(value) this.document.ids.set(value,this); }
    get id() { return this._id; }
    get firstChild() { return this.children[0]; }
    append(...items) { this.children.push(...items); }
    appendChild(item) { this.children.push(item); return item; }
    replaceChildren(...items) { this.children.forEach(n=>{n.isConnected=false; if(n.id)this.document.ids.delete(n.id);}); this.children=items; }
    setAttribute(key,value) { this.attributes[key]=value; }
    addEventListener(name,listener) { this.listeners[name]=listener; }
    dispatch(name,extra={}) { return this.listeners[name]?.({preventDefault(){},...extra}); }
    focus() { this.document.activeElement=this; }
    scrollIntoView() {}
    querySelectorAll(selector) {
        const found=[];
        function visit(n) { if(n.tagName==='INPUT' && selector==='input:checked' && n.checked) found.push(n); (n.children||[]).forEach(visit); }
        this.children.forEach(visit); return found;
    }
}
function text(element) { return (element.textContent||'')+element.children.map(text).join(''); }
function dom() {
    const document={ids:new Map(),activeElement:null,createElement(tag){return new Element(tag,this);},createTextNode(text){return {textContent:text,children:[]};},getElementById(id){return this.ids.get(id);},documentElement:{dir:'ltr',lang:'en'}};
    const names=[...fs.readFileSync('templates/knowledge_coverage.html','utf8').matchAll(/id="(coverage[^"]+)"/g)].map(m=>m[1]);
    names.forEach(name=>{const n=document.createElement('div'); n.id=name;});
    document.body={classList:{values:new Set(),add(v){this.values.add(v);},toggle(v){if(this.values.has(v)){this.values.delete(v);return false;}this.values.add(v);return true;}}};
    document.getElementById('coverageRoot').dataset={contract:ui.contractVersion,canStart:'true',canEvidence:'true',canExport:'true',uploadLimit:'5242880'};
    document.getElementById('coverageDelimiter').value=','; document.getElementById('coverageCalendar').value='gregorian'; document.getElementById('coverageBudget').value='300';
    return document;
}
function buttons(element) { return element.children.flatMap(n=>(n.tagName==='BUTTON'?[n]:[]).concat(n.children?buttons(n):[])); }
async function flush() { for(let i=0;i<8;i++) await Promise.resolve(); }

test('CSV header BOM, quoting, delimiter and multiline parsing',()=>{
    assert.deepEqual(ui.headersFromCsv('\ufeff"پرسش، اول",session,"time\nvalue"\r\nignored',','),['پرسش، اول','session','time\nvalue']);
    assert.deepEqual(ui.headersFromCsv('"quoted""name";query\n',';'),['quoted"name','query']);
    assert.throws(()=>ui.headersFromCsv('"unclosed',','));
});
test('upload → explicit selection → progress → evidence → complete export and keyboard/RTL controls',async()=>{
    const document=dom(), $=name=>document.getElementById('coverage'+name);
    const did='d_'+'a'.repeat(32), rid='r_'+'b'.repeat(32), sid='c'.repeat(64), rowId='row_'+'d'.repeat(32);
    const raw='query,session_id,timestamp\r\n"سؤال، متعدد\nالأسطر",synthetic,2026-01-01T12:00:00Z\r\n';
    const input={source_row_id:rowId,source_record_ordinal:1,input_query_redacted:'<img src=x onerror=alert(1)> پرسش',preparation_status:'pending_model',history_status:'user_only'};
    const assessed={...input,preparation_status:'prepared',outcome:'covered_reachable',coverage_status:'full',evaluated_entry_count:1,
        standalone_query_redacted:'پرسش مستقل',canonical_retrieval_query_redacted:'عبارت جستجو',explanation:'Supported synthetic fact.',verification_result:'accepted',
        production_context_sufficiency:'full',stopping_reason:'verified_full',kb_snapshot_id:sid,
        failure_diagnostics:[{failure_category:'model_read_timeout',boundary:'completion',evaluation_phase:'production',attempt:1,duration_ms:40000}],
        requested_aspects:[{aspect_id:'a1',description:'مدت زمان',conditions:['Working days']}],
        supporting_sentence_refs:[{chunk_id:'1',faq_entry_id:'1',sentence_number:1}],
        audit_assessment:{witness:[{aspect_id:'a1',applicability:'applicable',conditions:[],citations:[{chunk_id:'1',faq_entry_id:'1',sentence_number:1}]}]}};
    const requests=[], timers=[];
    const saved={fetch:global.fetch,localStorage:global.localStorage,setInterval:global.setInterval,clearInterval:global.clearInterval,setTimeout:global.setTimeout,clearTimeout:global.clearTimeout};
    global.localStorage={getItem(){return null;},setItem(k){assert.equal(k,'theme');}};
    global.setInterval=fn=>{timers.push(fn);return timers.length;}; global.clearInterval=()=>{};
    global.setTimeout=fn=>{fn();return 1;}; global.clearTimeout=()=>{};
    global.fetch=async (url,options={})=>{
        requests.push({url,options}); let value;
        const path=url.replace('/api/knowledge-coverage/','');
        if(path==='datasets' && options.method==='POST') { const payload=JSON.parse(options.body); assert.equal(Buffer.from(payload.csv_base64,'base64').toString('utf8'),raw); assert.equal(payload.mapping.query,'query'); assert.equal(payload.mapping.session,'session_id'); value={dataset_id:did}; }
        else if(path==='datasets') value=[{dataset_id:did,structure:{selected_row_count:918,source_row_count:918},preparation_counts:{pending_model:857,needs_context:51,prepared:10},preparation_status:'ready'}];
        else if(path.startsWith('datasets/')) value={state:'ready',total:918,rows:[input]};
        else if(path==='snapshots') value=[{snapshot_id:sid,record_count:1526,documents:['Synthetic_FAQ']}];
        else if(path==='runs' && options.method==='POST') { const payload=JSON.parse(options.body); assert.deepEqual(payload.row_ids,[rowId]); assert.deepEqual(payload.documents,['Synthetic_FAQ']); assert.equal(payload.entry_budget,300); value={run_id:rid}; }
        else if(path==='runs') value=[{run_id:rid,state:'completed',selected_row_ids:[rowId]}];
        else if(path.includes('/results?')) value={total:918,source_total:918,rows:[assessed]};
        else if(path.includes('/rows/')) value={result:assessed,evidence:[{chunk_id:'1',faq_entry_id:'1',question:'سؤال آزمایشی',main_category:'Synthetic',sub_category:'Test',sentences:[{sentence_number:1,text:'دو روز کاری.'}]}]};
        else if(path.includes('/export-revisions')) value={export_revision_id:'rev_'+ 'e'.repeat(32),export_captured_at:'2026-01-01T00:00:00Z',state:'completed',row_count:918};
        else value={run_id:rid,state:'completed',selected_row_ids:[rowId],completed_pilot_rows:1,input_row_count:918,stage:'finished'};
        return {ok:true,json:async()=>value};
    };
    try {
        ui.boot(document); await flush();
        $('File').files=[{size:Buffer.byteLength(raw),arrayBuffer:async()=>new TextEncoder().encode(raw).buffer}];
        await $('File').dispatch('change'); await $('ImportForm').dispatch('submit'); await flush();
        assert.match($('DatasetSummary').textContent,/918/); assert.match(text($('Rows')),/<img src=x onerror=alert\(1\)>/);
        assert.equal($('Rows').children[0].children[1].tagName,'TD');
        const checkbox=$('Rows').children[0].children[0].children[0]; checkbox.checked=true; checkbox.dispatch('change');
        $('Snapshot').value=sid; $('Snapshot').dispatch('change');
        assert.equal($('SelectionCount').textContent,'1 selected / 918 imported queries');
        await $('Start').dispatch('click'); await flush();
        assert.equal($('Progress').value,1); assert.match($('ProgressText').textContent,/918 rows retained/);
        await $('PrepareExport').dispatch('click');
        const revision='?revision_id=rev_'+ 'e'.repeat(32);
        assert.equal($('Export').href,'/api/knowledge-coverage/runs/'+rid+'/export'+revision);
        assert.equal($('Manifest').href,'/api/knowledge-coverage/runs/'+rid+'/export-manifest'+revision);
        assert.match($('ExportState').textContent,/918 rows/);
        const review=buttons($('Rows')).find(n=>n.textContent==='Review'); await review.dispatch('click'); await flush();
        assert.equal(document.activeElement,$('Evidence')); assert.match(text($('EvidenceContent')),/مدت زمان/);
        assert.match(text($('EvidenceContent')),/دو روز کاری/); assert.match(text($('EvidenceContent')),/sentence 1/);
        assert.match(text($('EvidenceContent')),/Model request/); assert.match(text($('EvidenceContent')),/40000 ms/);
        assert.match(text($('EvidenceContent')),/read.timeout/i);
        $('Evidence').dispatch('keydown',{key:'Escape'}); assert.equal(document.activeElement,review);
        $('Language').dispatch('click'); assert.equal(document.documentElement.dir,'rtl');
        $('Theme').dispatch('click'); assert(document.body.classList.values.has('light-mode'));
        assert(requests.some(r=>r.url.includes('/results?')));
    } finally {Object.assign(global,saved);}
});
test('frontend never inserts untrusted HTML or stores customer data',()=>{
    const js=fs.readFileSync('static/js/knowledge_coverage.js','utf8');
    assert(!js.includes('.innerHTML')); assert(!js.includes('console.log'));
    assert.equal((js.match(/localStorage\.setItem/g)||[]).length,1);
    const css=fs.readFileSync('static/css/knowledge_coverage.css','utf8');
    assert(css.includes('focus-visible') && css.includes('prefers-reduced-motion') && css.includes('overflow-y: auto'));
    assert(css.includes('max-width: 760px') && css.includes('dir=rtl') && css.includes('Vazirmatn'));
});

test('delayed progress is not duplicated and stale row/run responses cannot repaint the current view',async()=>{
    const document=dom(),$=name=>document.getElementById('coverage'+name);
    document.getElementById('coverageRoot').dataset.canStart='false';
    document.getElementById('coverageRoot').dataset.canExport='false';
    const runA='r_'+'a'.repeat(32),runB='r_'+'b'.repeat(32),rowA='row_'+'a'.repeat(32),rowB='row_'+'b'.repeat(32);
    let releaseProgress,releaseEvidence,slowProgress=true,progressRequests=0;
    const progressGate=()=>new Promise(resolve=>{releaseProgress=resolve;});
    const old={fetch:global.fetch,setInterval:global.setInterval,clearInterval:global.clearInterval,localStorage:global.localStorage,KnowledgeRecommendations:global.KnowledgeRecommendations};
    global.KnowledgeRecommendations={mount(container,identity){assert.equal(identity.onRevisionChange,null);assert.equal(identity.getCoverageSource(),'');return {stop(){}};}};
    global.localStorage={getItem(){return null;}};global.setInterval=()=>1;global.clearInterval=()=>{};
    const run=(id,count)=>({run_id:id,state:'completed',completed_pilot_rows:1,selected_row_ids:[rowA],input_row_count:count,outcome_counts:{pending:count-1},retryable_rows:0});
    global.fetch=async url=>{
        const path=url.replace('/api/knowledge-coverage/','');let value;
        if(path==='datasets')value=[];
        else if(path==='runs')value=[run(runA,918),run(runB,17)];
        else if(path==='runs/'+runA){progressRequests++;value=slowProgress?await progressGate():run(runA,918);}
        else if(path==='runs/'+runB)value=run(runB,17);
        else if(path.includes('/results?'))value={total:0,rows:[]};
        else if(path.endsWith('/rows/'+rowA))value=await new Promise(resolve=>{releaseEvidence=resolve;});
        else if(path.endsWith('/rows/'+rowB))value={result:{source_record_ordinal:2,input_query_redacted:'New selected query',outcome:'pending',coverage_status:'not_evaluated'},evidence:[]};
        else throw new Error('Unexpected synthetic route');
        return {ok:true,json:async()=>value};
    };
    try{
        const controller=ui.boot(document);await flush();$('Runs').value=runA;const change=$('Runs').dispatch('change');await flush();
        await controller.progress();assert.equal(progressRequests,1);
        releaseProgress(run(runA,918));await change;assert.match($('ProgressText').textContent,/918 rows retained/);
        const oldRow=controller.openEvidence(rowA,{id:'old'});await flush();await controller.openEvidence(rowB,{id:'new'});
        releaseEvidence({result:{source_record_ordinal:1,input_query_redacted:'Old discarded query',outcome:'pending'},evidence:[]});await oldRow;
        assert.match(text($('EvidenceContent')),/New selected query/);assert.doesNotMatch(text($('EvidenceContent')),/Old discarded query/);
        const oldProgress=controller.progress();await flush();$('Runs').value=runB;await $('Runs').dispatch('change');releaseProgress(run(runA,918));await oldProgress;
        assert.match($('ProgressText').textContent,/17 rows retained/);assert.doesNotMatch($('ProgressText').textContent,/918/);
    }finally{Object.assign(global,old);}
});

test('a delayed CSV upload never replaces a run selected while it was in flight',async()=>{
    const document=dom(),$=name=>document.getElementById('coverage'+name),runId='r_'+'c'.repeat(32),datasetId='d_'+'d'.repeat(32);
    let releaseUpload;const saved={fetch:global.fetch,setInterval:global.setInterval,clearInterval:global.clearInterval,localStorage:global.localStorage};
    global.localStorage={getItem(){return null;}};global.setInterval=()=>1;global.clearInterval=()=>{};
    global.fetch=async(url,options={})=>{
        const path=url.replace('/api/knowledge-coverage/','');let body;
        if(path==='datasets'&&options.method==='POST')body=await new Promise(resolve=>{releaseUpload=resolve;});
        else if(path==='datasets'||path==='snapshots')body=[];
        else if(path==='runs')body=[{run_id:runId,state:'completed',selected_row_ids:['row_'+'a'.repeat(32)]}];
        else if(path==='runs/'+runId)body={state:'completed',selected_row_ids:['row_'+'a'.repeat(32)],completed_pilot_rows:1,input_row_count:17,outcome_counts:{pending:16},retryable_rows:0};
        else if(path.includes('/results?'))body={total:0,rows:[]};
        else throw new Error('Unexpected synthetic route');
        return {ok:true,json:async()=>body};
    };
    try{
        const controller=ui.boot(document);await flush();const bytes=Buffer.from('query\nSynthetic question?\n');
        $('File').files=[{size:bytes.length,arrayBuffer:async()=>bytes}];await $('File').dispatch('change');
        const upload=$('ImportForm').dispatch('submit');await flush();$('Runs').value=runId;await $('Runs').dispatch('change');
        releaseUpload({dataset_id:datasetId});await upload;await controller.progress();
        assert.match($('ProgressText').textContent,/17 rows retained/);assert.equal($('Runs').value,runId);
    }finally{Object.assign(global,saved);}
});

test('full-input estimate table marks cells over the limit and Start waits for the partial-run checkbox',async()=>{
    const document=dom(), $=name=>document.getElementById('coverage'+name);
    const did='d_'+'a'.repeat(32), sid='c'.repeat(64), rid='r_'+'b'.repeat(32);
    const comparison={completions:{limit:200,expected:129,high:201,fits_expected:true,fits_high:false},
        tokens:{limit:1000000,expected:121334,high:193667,fits_expected:true,fits_high:true},
        seconds:{limit:3600,expected:5400,high:9000,fits_expected:false,fits_high:false},fits:false};
    const view={row_count:918,estimate:{version:'coverage-sizing-1',row_count:918},comparison,reference:{run_ids:[rid],row_count:6},sizing_version:'coverage-sizing-1'};
    const requests=[];
    const saved={fetch:global.fetch,localStorage:global.localStorage,setInterval:global.setInterval,clearInterval:global.clearInterval,setTimeout:global.setTimeout,clearTimeout:global.clearTimeout};
    global.localStorage={getItem(){return null;},setItem(){}};
    global.setInterval=()=>1; global.clearInterval=()=>{}; global.setTimeout=fn=>{fn();return 1;}; global.clearTimeout=()=>{};
    global.fetch=async (url,options={})=>{
        const path=url.replace('/api/knowledge-coverage/',''); requests.push({path,options}); let value;
        if(path==='datasets') value=[{dataset_id:did,structure:{selected_row_count:918,source_row_count:918},preparation_counts:{prepared:918},preparation_status:'ready'}];
        else if(path.startsWith('datasets/')) value={state:'ready',total:918,rows:[]};
        else if(path==='snapshots') value=[{snapshot_id:sid,record_count:2,documents:['Synthetic_FAQ']}];
        else if(path==='runs/estimate') value=view;
        else if(path==='runs' && options.method==='POST') value={run_id:rid};
        else if(path==='runs') value=[];
        else value={run_id:rid,state:'queued',selected_row_ids:[],input_row_count:918,stage:'waiting'};
        return {ok:true,json:async()=>value};
    };
    try {
        ui.boot(document); await flush();
        $('Dataset').value=did; await $('Dataset').dispatch('change'); await flush();
        $('Mode').value='full_input'; $('Mode').dispatch('change');
        $('Snapshot').value=sid; $('Snapshot').dispatch('change'); await flush();
        const estimates=requests.filter(r=>r.path==='runs/estimate');
        assert(estimates.length>=1);
        const sent=JSON.parse(estimates.at(-1).options.body);
        assert.equal(sent.execution_mode,'full_input'); assert.deepEqual(sent.row_ids,[]); assert.deepEqual(sent.documents,['Synthetic_FAQ']);
        const table=$('SizingTable').children[0]; assert.equal(table.tagName,'TABLE');
        assert.match(text(table),/Completions/); assert.match(text(table),/Hours/); assert.match(text(table),/1\.5/);
        const rows=table.children[2].children, over=rows.flatMap(r=>r.children.filter(c=>c.dataset.over==='true').map(c=>r.children[0].textContent+':'+text(c)));
        assert.deepEqual(over,['Completions:201 · over limit','Hours:1.5 · over limit','Hours:2.5 · over limit']);
        assert.equal(rows[0].children[3].children[0].dataset.tone,'error');
        assert.equal($('PartialAckLabel').hidden,false); assert.equal($('SizingAckLabel').hidden,true);
        assert.match($('SizingStatus').textContent,/will pause before finishing/);
        $('BudgetAck').checked=true; $('BudgetAck').dispatch('change');
        assert.equal($('Start').disabled,true);
        $('PartialAck').checked=true; $('PartialAck').dispatch('change');
        assert.equal($('Start').disabled,false);
        await $('Start').dispatch('click'); await flush();
        const start=JSON.parse(requests.find(r=>r.path==='runs' && r.options.method==='POST').options.body);
        assert.equal(start.accept_partial_run,true); assert.equal(start.sizing_acknowledged,false); assert.equal(start.budget_acknowledged,true);
        assert.equal(ui.sizingRequirement(null),'pending'); assert.equal(ui.sizingRequirement({estimate:null}),'unsized');
        assert.equal(ui.sizingRequirement(view),'partial'); assert.equal(ui.sizingRequirement({...view,comparison:{...comparison,fits:true}}),'');
    } finally {Object.assign(global,saved);}
});
