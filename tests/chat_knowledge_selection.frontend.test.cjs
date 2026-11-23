/* Repository VM/DOM harness: real API, session creation, document tags and Chat.send. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
class Element extends EventTarget {
  constructor(doc) {
    super();
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
  insertBefore(el, first) {
    if (!first) return this.appendChild(el);
    el.parent = this;
    this.children.splice(this.children.indexOf(first), 0, el);
  }
  get firstChild() { return this.children[0] || null; }
  click() { if (!this.disabled) this.dispatchEvent(new Event('click')); }
  focus() { this.doc.activeElement = this; }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
};
const response = (data, status = 200) => ({ok: status < 400, status, json: async () => data});

function mockMedia(supportedType) {
  const recordings = [];
  const makeStream = () => {
    const track = {stopped: false, stop() { this.stopped = true; }};
    return {track, getTracks: () => [track]};
  };
  class Recorder extends EventTarget {
    static isTypeSupported(type) { return type === supportedType; }
    constructor(stream, {mimeType}) {
      super();
      this.stream = stream;
      this.mimeType = mimeType;
      this.state = 'inactive';
      recordings.push(this);
    }
    start() { this.state = 'recording'; }
    stop() {
      this.state = 'inactive';
      queueMicrotask(() => {
        const event = new Event('dataavailable');
        event.data = new Blob(['test audio'], {type: this.recordedType ?? this.mimeType});
        this.dispatchEvent(event);
        this.dispatchEvent(new Event('stop'));
      });
    }
  }
  return {recordings, makeStream, Recorder};
}

function mockClock() {
  let now = 0;
  let nextId = 0;
  const tasks = new Map();
  const addTask = (callback, delay, interval = 0) => {
    const id = ++nextId;
    tasks.set(id, {callback, at: now + delay, interval});
    return id;
  };
  return {
    performance: {now: () => now},
    setTimeout: addTask,
    clearTimeout: id => tasks.delete(id),
    setInterval: (callback, delay) => addTask(callback, delay, delay),
    clearInterval: id => tasks.delete(id),
    async advance(delay) {
      const target = now + delay;
      while (tasks.size) {
        const [id, task] = [...tasks].sort((a, b) => a[1].at - b[1].at)[0];
        if (task.at > target) break;
        now = task.at;
        if (task.interval) task.at += task.interval;
        else tasks.delete(id);
        task.callback();
        await tick();
      }
      now = target;
    }
  };
}

const chatOrigin = 'https://chat.example.test';
const asrOrigin = 'https://speech.example.test';

async function harness(dictation) {
  const document = Object.assign(new EventTarget(), {
    ids: new Map(), visibilityState: 'visible', cookie: 'ragbot_web_csrf=test-only-csrf',
    querySelector: selector => selector === '.chat-input-actions' ? actions : null,
    querySelectorAll: () => [],
    getElementById(id) { return this.ids.get(id); }, createElement() { return new Element(this); }
  });
  const actions = document.createElement();
  document.body = document.createElement();
  for (const id of ['messages','chatInput','sendBtn','lockNotice','docFilters']) document.createElement().id = id;
  let mic, status, stop, cancel;
  if (dictation) {
    mic = document.createElement(); mic.id = 'dictationMic'; mic.disabled = true;
    mic.dataset.asrOrigin = dictation.origin ?? asrOrigin;
    status = document.createElement(); status.id = 'dictationStatus';
    stop = document.createElement(); stop.id = 'dictationStop';
    cancel = document.createElement(); cancel.id = 'dictationCancel';
    actions.appendChild(mic);
  }
  const requests = [], provider = [], redirects = [];
  const media = mockMedia(dictation?.supportedType ?? 'audio/webm;codecs=opus');
  const clock = mockClock();
  const state = {
    failure: null, createFailure: false, permissionRequests: 0,
    getPermission: async () => media.makeStream(),
    health: dictation?.health ?? (async () => response({status: 'ok', model_loaded: true})),
    transcribe: async () => response({text: 'پرسش بانکی'}),
  };
  const fetch = async (url, options={}) => {
    if (dictation && url.startsWith(mic.dataset.asrOrigin + '/api/') && mic.dataset.asrOrigin) {
      provider.push({url, options});
      const handler = url.endsWith('/health') ? state.health : state.transcribe;
      return handler(options);
    }
    const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body ?? null;
    requests.push({url, options, body});
    if (url === '/api/sessions' && options.method === 'POST') {
      if (state.createFailure) throw new Error('private-network-diagnostic');
      return response({id: 12});
    }
    if (url === '/api/sessions') return response({sessions:[{id:12, last_activity_at:new Date().toISOString()}]});
    if (url.endsWith('/messages')) return response({messages:[{role:'user', content:'existing history'}]});
    if (url === '/api/ocr/extract') return response({status: 'success', extracted_text: 'test OCR'});
    if (url === '/api/query') {
      if (state.failure === 'network') throw new Error('private-network-diagnostic');
      if (state.failure === 'non-json') return {ok:false,status:502,json:async()=>{throw new Error('<html>private stack trace</html>');}};
      if (state.failure) return response(state.failure.data, state.failure.status);
      return response({status:'success', answer:'synthetic answer', related_questions:[{question:'q',answer:'a'}]});
    }
    throw new Error('Unexpected harness request');
  };
  const windowEvents = new EventTarget();
  const context = vm.createContext({
    document, fetch, console, I18N: {t: k => k}, alert() {}, confirm: () => true,
    addEventListener: windowEvents.addEventListener.bind(windowEvents),
    URL, Request, Headers, Blob, FormData, AbortController,
    location: {href: chatOrigin + '/app', origin: chatOrigin, assign: path => redirects.push(path)},
    isSecureContext: dictation?.secure ?? true, MediaRecorder: media.Recorder, ...clock,
    navigator: {mediaDevices: {getUserMedia: constraints => {
      assert.equal(constraints.audio, true);
      state.permissionRequests++;
      return state.getPermission();
    }}},
  });
  context.window = context;
  if (dictation) {
    for (const file of ['chat_dictation.js', 'web_auth.js']) {
      vm.runInContext(fs.readFileSync('static/js/' + file, 'utf8'), context);
    }
  }
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
  if (dictation) await Chat.init();
  CategoryFilter.applyFilter();
  await tick();
  function select(name) {
    const bar = document.getElementById('docFilters');
    for (const old of [...Chat.selectedDocs]) bar.children.find(el=>el.innerText===old).onclick();
    bar.children.find(el=>el.innerText===name).onclick();
  }
  async function send() { Chat.textarea.value='synthetic question';await Chat.send();await tick(); }
  return {
    Chat, Sessions, API, CategoryFilter, document, requests, state, select, send,
    mic, status, stop, cancel, actions, provider, media, clock, windowEvents, redirects,
  };
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

const hangingRequest = ({signal}) => new Promise((_, reject) => {
  signal.addEventListener('abort', () => reject(signal.reason), {once: true});
});

async function startRecording(h) {
  h.mic.click();
  await tick();
  assert.equal(h.status.textContent, 'dictation_recording');
  assert.equal(h.stop.hidden, false);
  assert.equal(h.cancel.hidden, false);
  return h.media.recordings.at(-1);
}

test('readiness and composer lock gate recording; Persian text is editable before the ordinary send', async () => {
  const h = await harness({supportedType: 'audio/mp4'});
  assert.equal(h.mic.disabled, true);
  assert.equal(h.actions.firstChild.id, 'uploadFileBtn');
  assert.equal(h.actions.children[1], h.mic);
  assert.equal(h.state.permissionRequests, 0);
  h.select('NegahBoom_FAQ');
  assert.equal(h.mic.disabled, false);
  h.Chat.textarea.value = 'پیش‌نویس';
  const pending = deferred();
  h.state.transcribe = () => pending.promise;
  const recording = await startRecording(h);
  recording.recordedType = 'audio/mp4;codecs=mp4a.40.2';
  h.stop.click();
  assert.equal(recording.stream.track.stopped, true);
  await tick();
  assert.equal(h.status.textContent, 'dictation_transcribing');
  assert.equal(h.Chat.textarea.disabled, false);
  h.Chat.textarea.value += ' و ادامه';
  pending.resolve(response({text: '  پرسش بانکی <b>متن</b>  ', segments: [{text: 'نادیده'}]}));
  await tick();
  assert.equal(h.Chat.textarea.value, 'پیش‌نویس و ادامه پرسش بانکی <b>متن</b>');
  assert.equal(h.status.textContent, 'dictation_added');
  assert.equal(h.requests.filter(r => r.url === '/api/query').length, 0);
  const [health, upload] = h.provider;
  assert.equal(health.url, asrOrigin + '/api/health');
  assert.equal(upload.url, asrOrigin + '/api/transcribe');
  assert.equal(upload.options.method, 'POST');
  assert.deepEqual([...upload.options.body.keys()], ['file']);
  assert.equal(upload.options.body.get('file').name, 'dictation.mp4');
  assert.equal(upload.options.body.get('file').type, 'audio/mp4;codecs=mp4a.40.2');
  for (const {options} of h.provider) {
    assert.equal(options.credentials, 'omit');
    assert.equal(options.headers, undefined);
    assert.equal(options.redirect, 'error');
  }
  h.Chat.textarea.value = 'پرسش بانکی ویرایش‌شده';
  h.Chat.sendBtn.click();
  await tick();
  const [query] = h.requests.filter(r => r.url === '/api/query');
  assert.deepEqual(query.body, {
    query: 'پرسش بانکی ویرایش‌شده', documents: ['NegahBoom_FAQ'], session_id: 12,
    top_k: 10, alpha: 0.5, uploaded_text: null,
  });
  assert.equal(query.options.headers.get('X-CSRF-Token'), 'test-only-csrf');
  assert.equal(h.Chat.textarea.value, '');
});

test('blank, insecure and incompatible configurations leave typed chat and paperclip usable', async () => {
  for (const options of [{origin: ''}, {secure: false}, {supportedType: 'unsupported'}]) {
    const h = await harness(options);
    h.select('NegahBoom_FAQ');
    assert.equal(h.mic.disabled, true);
    h.mic.click();
    assert.equal(h.state.permissionRequests, 0);
    assert.equal(h.provider.length, 0);
    let opened = false;
    h.Chat.uploadInput.addEventListener('click', () => { opened = true; });
    h.actions.firstChild.click();
    assert.equal(opened, true);
    h.Chat.uploadInput.files = [new File(['test document'], 'test.pdf', {type: 'application/pdf'})];
    h.Chat.uploadInput.dispatchEvent(new Event('change'));
    await tick();
    assert.equal(h.Chat.uploadedDocText, 'test OCR');
    await h.send();
    const query = h.requests.find(r => r.url === '/api/query');
    assert.equal(query.body.uploaded_text, 'test OCR');
    assert.match(query.body.query, /synthetic question/);
  }
});

test('readiness recovers without reload and skips polling while hidden', async () => {
  const h = await harness({health: hangingRequest});
  h.select('NegahBoom_FAQ');
  await h.clock.advance(3_000);
  assert.equal(h.provider[0].options.signal.aborted, true);
  assert.equal(h.mic.disabled, true);
  for (const malformed of [
    () => response({status: 'ok', model_loaded: true}, 503),
    () => response({status: 'ok', model_loaded: 'true'}),
    () => ({ok: true, json: async () => { throw new SyntaxError(); }}),
  ]) {
    h.state.health = malformed;
    await h.clock.advance(30_000);
    assert.equal(h.mic.disabled, true);
  }
  const probes = h.provider.length;
  h.document.visibilityState = 'hidden';
  h.document.dispatchEvent(new Event('visibilitychange'));
  h.state.health = () => response({status: 'ok', model_loaded: true});
  await h.clock.advance(60_000);
  assert.equal(h.provider.length, probes);
  h.document.visibilityState = 'visible';
  h.document.dispatchEvent(new Event('visibilitychange'));
  await tick();
  assert.equal(h.mic.disabled, false);
  assert.equal(h.provider.length, probes + 1);
  h.Chat.selectedDocs.length = 0;
  h.Chat._updateLockState();
  assert.equal(h.mic.disabled, true);
});

test('transcription timeout, HTTP failures and empty results preserve the draft without retry or logout', async () => {
  const h = await harness({origin: chatOrigin});
  h.select('NegahBoom_FAQ');
  h.Chat.textarea.value = 'متن موجود';
  for (const [transcribe, expected] of [
    [hangingRequest, 'dictation_timeout'],
    [() => response({detail: 'private'}, 429), 'dictation_busy'],
    [() => response({detail: 'private'}, 401), 'dictation_error'],
    [() => response({detail: 'private'}, 500), 'dictation_error'],
    [() => response({segments: [{text: 'نادیده'}]}), 'dictation_error'],
    [() => response({text: '  '}), 'dictation_empty'],
  ]) {
    h.state.transcribe = transcribe;
    const uploads = h.provider.filter(r => r.url.endsWith('/transcribe')).length;
    await startRecording(h);
    h.stop.click();
    await tick();
    if (transcribe === hangingRequest) {
      await h.clock.advance(30_000);
      assert.equal(h.provider.find(r => r.url.endsWith('/transcribe')).options.signal.aborted, true);
    }
    assert.equal(h.status.textContent, expected);
    assert.equal(h.Chat.textarea.value, 'متن موجود');
    assert.equal(h.Chat.sendBtn.disabled, false);
    assert.equal(h.mic.disabled, false);
    assert.equal(h.provider.filter(r => r.url.endsWith('/transcribe')).length, uploads + 1);
  }
  assert.deepEqual(h.redirects, []);
  assert(h.provider.every(r => r.options.headers === undefined));
  h.state.failure = {status: 401, data: {}};
  await h.send();
  assert.deepEqual(h.redirects, ['/']);
});

test('permission denial and canceling pending access, active recording and navigation release the microphone', async () => {
  const h = await harness({});
  h.select('NegahBoom_FAQ');
  h.state.getPermission = async () => { throw new DOMException('denied', 'NotAllowedError'); };
  h.mic.click();
  await tick();
  assert.equal(h.status.textContent, 'dictation_denied');
  const permission = deferred();
  h.state.getPermission = () => permission.promise;
  h.mic.click();
  h.cancel.click();
  const stream = h.media.makeStream();
  permission.resolve(stream);
  await tick();
  assert.equal(stream.track.stopped, true);
  assert.equal(h.media.recordings.length, 0);
  assert.equal(h.status.textContent, 'dictation_cancelled');
  h.state.getPermission = async () => h.media.makeStream();
  const cancelled = await startRecording(h);
  h.cancel.click();
  assert.equal(cancelled.stream.track.stopped, true);
  const abandoned = await startRecording(h);
  h.windowEvents.dispatchEvent(new Event('pagehide'));
  assert.equal(abandoned.stream.track.stopped, true);
  await tick();
  assert.equal(h.provider.filter(r => r.url.endsWith('/transcribe')).length, 0);
});

test('recording automatically stops at 45 seconds and uploads a clip once', async () => {
  const h = await harness({});
  h.select('NegahBoom_FAQ');
  const recording = await startRecording(h);
  await h.clock.advance(44_999);
  assert.equal(recording.stream.track.stopped, false);
  await h.clock.advance(1);
  assert.equal(recording.stream.track.stopped, true);
  assert.equal(h.Chat.textarea.value, 'پرسش بانکی');
  assert.equal(h.provider.filter(r => r.url.endsWith('/transcribe')).length, 1);
});

test('late provider responses cannot change the draft after cancel, chat change, or send', async () => {
  const h = await harness({});
  h.select('NegahBoom_FAQ');
  for (const interrupt of [
    () => h.cancel.click(),
    () => h.Sessions.select('20'),
    () => h.Chat.sendBtn.click(),
    () => h.Sessions.create(),
  ]) {
    const result = deferred();
    h.state.transcribe = () => result.promise;
    h.Chat.textarea.value = 'پیش‌نویس';
    await startRecording(h);
    h.stop.click();
    await tick();
    const upload = h.provider.at(-1);
    assert.equal(upload.url, asrOrigin + '/api/transcribe');
    await interrupt();
    await tick();
    assert.equal(upload.options.signal.aborted, true);
    h.Chat.textarea.value = 'پیش‌نویس تازه';
    result.resolve(response({text: 'پاسخ دیررس'}));
    await tick();
    assert.equal(h.Chat.textarea.value, 'پیش‌نویس تازه');
  }
  assert.equal(h.requests.filter(r => r.url === '/api/query').length, 1);
});
