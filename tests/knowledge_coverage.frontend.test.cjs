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
        assert.equal($('SelectionCount').textContent,'1 of 5 selected');
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
