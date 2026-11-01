/* Isolated browser-script harness; no network, storage of credentials, or live accounts. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {validate} = require('../static/js/admin_users.js');
const roles = ['admin', 'user'];
const valid = {username:'Synthetic.User', email:'synthetic@example.test', full_name:' Synthetic User ', role:'user', password:'رمز🔑é', confirm_password:'رمز🔑é'};
assert.deepEqual(validate(valid, roles), {});
for (const [field,value] of [['username','x'.repeat(101)], ['username','has space'], ['email','bad@domain'], ['full_name','  '], ['role','unknown'], ['password','é'.repeat(37)], ['password','x\0y'], ['confirm_password','other']]) {
  assert.ok(validate({...valid,[field]:value},roles)[field], field);
}
for (const password of ['é'.repeat(36), '🔑'.repeat(18), 'a'.repeat(72)]) {
  assert.deepEqual(validate({...valid,password,confirm_password:password}, roles), {});
}
class Element {
  constructor() {this.attrs={}; this.listeners={}; this.hidden=false; this.disabled=false; this.value=''; this.textContent=''; this.dataset={}; this.options=[]; this.focused=false;}
  setAttribute(k,v) {this.attrs[k]=v;}
  addEventListener(k,fn) {this.listeners[k]=fn;}
  focus() {this.focused=true;}
  set innerHTML(value) {throw Error('Unsafe HTML rendering');}
}
const ids = ['usersForm','usersSubmit','usersError','usersStatus','usersTheme', ...Object.keys(valid).flatMap(k=>['user-'+k,'error-'+k])];
const elements = Object.fromEntries(ids.map(k=>[k,new Element()]));
const language = ['fa','en'].map(lang=>Object.assign(new Element(),{dataset:{lang}}));
elements['user-role'].options = roles.map(value=>({value}));
const classes = new Set();
const writes=[];
const documentEvents=[];
const windowEvents={};
const requests=[];
let respond;
const context={console, URL, Request, Headers, TextEncoder, CustomEvent:class {constructor(type, args){this.type=type;Object.assign(this,args);}},
  localStorage:{getItem:()=>null,setItem:(k,v)=>writes.push([k,v])},
  document:{cookie:'ragbot_web_csrf=synthetic-csrf',documentElement:{}, body:{classList:{toggle(k,on){const value=on??!classes.has(k);value?classes.add(k):classes.delete(k);return value;}}},
    getElementById:k=>elements[k],addEventListener:(type,fn)=>documentEvents.push(fn),querySelectorAll:selector=>selector==='[data-lang]'?language:[]},
};
context.window={location:{href:'http://localhost:8000/admin/users',origin:'http://localhost:8000',assign:()=>{}},
  fetch:(url,options)=>{requests.push({url,options});return new Promise(resolve=>{respond=resolve;});},
  addEventListener:(type,fn)=>{windowEvents[type]=fn;},dispatchEvent:e=>windowEvents[e.type]?.(e)};
context.fetch=(...args)=>context.window.fetch(...args);
vm.createContext(context);
for (const file of ['web_auth.js','i18n.js','admin_users.js']) vm.runInContext(fs.readFileSync('static/js/'+file,'utf8'),context);
for (const callback of documentEvents) callback();
function fill(data=valid){for(const [k,v] of Object.entries(data)) elements['user-'+k].value=v;}
function submit(){return elements.usersForm.listeners.submit({preventDefault(){}});}
function response(status,data){respond({status,ok:status<300,json:async()=>data});}
(async()=>{
  fill({...valid,password:'é'.repeat(37)});
  await submit();
  assert.equal(requests.length,0);
  assert.equal(elements['user-password'].attrs['aria-invalid'],'true');
  fill();
  const pending=submit();
  assert.equal(elements.usersSubmit.disabled,true);
  assert.equal(elements.usersForm.attrs['aria-busy'],'true');
  await submit();
  assert.equal(requests.length,1);
  assert.equal(requests[0].url,'/api/admin/users');
  assert.equal(requests[0].options.method,'POST');
  assert.equal(requests[0].options.headers.get('X-CSRF-Token'),'synthetic-csrf');
  assert.deepEqual(JSON.parse(requests[0].options.body),valid);
  response(201,{user:{id:101,username:'<img onerror=attack()>',role:'user'}});
  await pending;
  assert.ok(elements.usersStatus.textContent.includes('<img onerror=attack()>'));
  assert.equal(elements['user-password'].value,'');
  assert.equal(elements['user-confirm_password'].value,'');
  assert.equal(elements.usersSubmit.disabled,false);
  assert.equal(elements.usersForm.attrs['aria-busy'],'false');
  assert.ok(elements.usersStatus.focused);
  fill();
  const duplicate=submit();
  response(409,{errors:{email:'duplicate'},detail:'NEVER-DISPLAY-THIS'});
  await duplicate;
  assert.equal(elements['error-email'].textContent,'Email already exists.');
  assert.ok(!elements.usersError.textContent.includes('NEVER-DISPLAY-THIS'));
  language[0].listeners.click();
  assert.equal(context.document.documentElement.dir,'rtl');
  assert.equal(context.document.documentElement.lang,'fa');
  assert.equal(elements.usersSubmit.textContent,'افزودن کاربر');
  assert.equal(elements['error-email'].textContent,'ایمیل از قبل وجود دارد.');
  for (const status of [401,403,503]) {
    fill(); const pending=submit(); response(status,{detail:'NEVER-DISPLAY-THIS'}); await pending;
    assert.ok(elements.usersError.textContent);
    assert.ok(!elements.usersError.textContent.includes('NEVER-DISPLAY-THIS'));
    assert.equal(elements.usersSubmit.disabled,false);
  }
  assert.ok(writes.every(([key])=>['lang','theme'].includes(key)));
  assert.ok(!JSON.stringify(writes).includes(valid.password));
  console.log('admin users frontend: PASS (validation, CSRF transport, busy state, safe success/errors, Unicode, language, storage)');
})().catch(error=>{console.error(error);process.exitCode=1;});
