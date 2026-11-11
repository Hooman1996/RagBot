/* Repository VM/DOM harness: real API, session creation, document tags and Chat.send. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
class Element {
  constructor(doc) {
    this.doc = doc; this.children = []; this.style = {}; this.dataset = {};
    this.value = ''; this.disabled = false; this.textContent = ''; this.className = '';
    this.classes = new Set();
    this.classList = {add: c => this.classes.add(c), contains: c => this.classes.has(c),
      toggle: c => this.classes.has(c) ? this.classes.delete(c) : this.classes.add(c)};
  }
  set id(v) { this._id = v; this.doc.ids.set(v, this); }
  get id() { return this._id; }
  set innerHTML(v) { this._html = v; if (v === '') this.children = []; }
  get innerHTML() { return this._html || ''; }
  appendChild(el) { el.parent = this; this.children.push(el); }
  setAttribute(k,v) { this[k] = v; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); this.doc.ids.delete(this.id); }
  addEventListener() {}
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function harness() {
  const document = {ids: new Map(), querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
    getElementById(id) { return this.ids.get(id); }, createElement() { return new Element(this); }};
  for (const id of ['messages','chatInput','sendBtn','lockNotice','docFilters']) document.createElement().id = id;
  const requests = [], state = {failure: null, createFailure: false};
  const response = (data, status=200) => ({ok: status < 400, status, json: async () => data});
  const fetch = async (url, options={}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    requests.push({url, options, body});
    if (url === '/api/sessions' && options.method === 'POST') {
      if (state.createFailure) throw new Error('private-network-diagnostic');
      return response({id: 12});
    }
    if (url === '/api/sessions') return response({sessions:[{id:12, last_activity_at:new Date().toISOString()}]});
    if (url.endsWith('/messages')) return response({messages:[{role:'user', content:'existing history'}]});
    if (url === '/api/query') {
      if (state.failure === 'network') throw new Error('private-network-diagnostic');
      if (state.failure === 'non-json') return {ok:false,status:502,json:async()=>{throw new Error('<html>private stack trace</html>');}};
      if (state.failure) return response(state.failure.data, state.failure.status);
      return response({status:'success', answer:'synthetic answer', related_questions:[{question:'q',answer:'a'}]});
    }
    throw new Error('Unexpected harness request');
  };
  const context = vm.createContext({document,fetch,console,window:{addEventListener() {}},I18N:{t:k=>k},alert(){},confirm:()=>true});
  for (const file of ['api.js','sidebar.js','chat.js','categoryFilter.js']) vm.runInContext(fs.readFileSync('static/js/'+file,'utf8'),context);
  vm.runInContext('globalThis.modules = {API,Chat,Sessions,CategoryFilter};',context);
  const {Chat,Sessions,CategoryFilter,API} = context.modules;
  Chat.messagesContainer = document.getElementById('messages');
  Chat.textarea = document.getElementById('chatInput'); Chat.sendBtn = document.getElementById('sendBtn');
  Chat.lockNotice = document.getElementById('lockNotice');
  // Rendering model answers is outside this test; error rendering remains the real implementation.
  Chat._buildMessage = (role, text) => {const el=document.createElement();el.textContent=text;return el;};
  Chat.addUserMessage = text => {const el=document.createElement();el.textContent=text;Chat.messagesContainer.appendChild(el);};
  Chat.addAIMessage = text => {const el=document.createElement();el.textContent=text;Chat.messagesContainer.appendChild(el);};
  Chat.allDocuments = CategoryFilter.allDocuments = ['General_FAQ','NegahBoom_FAQ','New_FAQ'].map(name=>({name,category:'FAQ'}));
  CategoryFilter.applyFilter();
  await tick();
  function select(name) {
    const bar = document.getElementById('docFilters');
    for (const old of [...Chat.selectedDocs]) bar.children.find(el=>el.innerText===old).onclick();
    bar.children.find(el=>el.innerText===name).onclick();
  }
  async function send() { Chat.textarea.value='synthetic question';await Chat.send();await tick(); }
  return {Chat,Sessions,API,CategoryFilter,document,requests,state,select,send};
}
test('ordinary create then General -> NegahBoom -> General retains session, history and current selection', async () => {
  const h = await harness();
  await h.Sessions.create(); // ordinary direct fetch path, no source or header at creation
  await h.Sessions.select(12); // actual history loader
  assert.equal(h.Chat.messagesContainer.children[0].textContent,'existing history');
  for (const source of ['General_FAQ','NegahBoom_FAQ','General_FAQ','New_FAQ']) {
    h.select(source); await h.send();
    assert.equal(h.Sessions.currentSessionId,12);
    assert.equal(h.Chat.isSending,false); assert.equal(h.Chat.sendBtn.disabled,false);
  }
  assert.equal(h.requests.filter(r=>r.url==='/api/sessions' && r.options.method==='POST').length,1);
  assert.deepEqual(h.requests.filter(r=>r.url==='/api/query').map(r=>r.body.documents),[['General_FAQ'],['NegahBoom_FAQ'],['General_FAQ'],['New_FAQ']]);
  assert(h.requests.every(r=>!r.options.headers?.['X-Chatbot-Platform']));
  assert.equal(h.Chat.messagesContainer.children[0].textContent,'existing history');
  assert.equal(h.Chat.messagesContainer.children.length,9);
});
test('HTTP, application, non-JSON and network errors render safely and recover controls', async () => {
  const h = await harness(); h.select('NegahBoom_FAQ');
  for (const failure of [
    {status:400,data:{errorCode:'INVALID_REQUEST',errorDesc:'<img src=x onerror=alert(1)> private-stack-trace'}},
    {status:200,data:{errorCode:'SERVICE_BUSY',errorDesc:'private-stack-trace'}},
    {status:404,data:{detail:'Session not found'}},
    {status:500,data:{detail:'password=private-stack-trace'}},
    'non-json','network'
  ]) {
    h.state.failure=failure; await h.send();
    const error=h.Chat.messagesContainer.children.at(-1);
    assert.equal(error.role,'alert'); assert(error.textContent.length>10);
    assert(!/private|<img|password|stack/.test(error.textContent));
    assert.equal(error.innerHTML,'');
    assert.equal(h.Chat.isSending,false); assert.equal(h.Chat.textarea.disabled,false);assert.equal(h.Chat.sendBtn.disabled,false);
    assert(!h.document.getElementById('typing'));
  }
  h.state.failure=null; await h.send();
  assert.equal(h.Chat.messagesContainer.children.at(-1).textContent,'synthetic answer');
});
test('model and dependency errors show service messages, never ask for a shorter question', async () => {
  const h = await harness(); h.select('NegahBoom_FAQ');
  const cases = [
    [{status:502,data:{errorCode:'MODEL_CONTEXT_LIMIT',errorDesc:'Language model context limit exceeded'}}, 'سامانه نتوانست به این پرسش پاسخ دهد. لطفاً کمی بعد دوباره تلاش کنید.'],
    [{status:502,data:{errorCode:'DEPENDENCY_INVALID_RESPONSE',errorDesc:'Language model rejected the request'}}, 'سرویس پاسخ‌گویی پاسخ معتبری برنگرداند. لطفاً دوباره تلاش کنید.'],
    [{status:502,data:{detail:'Bad Gateway'}}, 'سرویس پاسخ‌گویی پاسخ معتبری برنگرداند. لطفاً دوباره تلاش کنید.'],
  ];
  for (const [failure, expected] of cases) {
    h.state.failure=failure; await h.send();
    const error=h.Chat.messagesContainer.children.at(-1);
    assert.equal(error.role,'alert');
    assert.equal(error.textContent, expected);
    assert(!/کوتاه/.test(error.textContent));
    assert.equal(h.Chat.isSending,false); assert.equal(h.Chat.sendBtn.disabled,false);
  }
});
test('failed session creation clears pending promise and allows retry', async () => {
  const h=await harness(); h.select('NegahBoom_FAQ'); h.state.createFailure=true;
  await h.send();
  assert.equal(h.Sessions.createPromise,null); assert.equal(h.Sessions.currentSessionId,null);
  assert.equal(h.Chat.isSending,false); assert.equal(h.Chat.sendBtn.disabled,false);
  assert.equal(h.Chat.messagesContainer.children.at(-1).role,'alert');
  h.state.createFailure=false; await h.send();
  assert.equal(h.Sessions.currentSessionId,12);
  assert.deepEqual(h.requests.filter(r=>r.url==='/api/query').at(-1).body.documents,['NegahBoom_FAQ']);
});
