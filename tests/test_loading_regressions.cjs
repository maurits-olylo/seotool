const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/ui/app.js', 'utf8');
const pick = (a,b) => source.slice(source.indexOf(a), source.indexOf(b, source.indexOf(a)));
function setup(state = {}) {
  const elements = new Map();
  const $ = key => {
    if (!elements.has(key)) {
      const classes = new Set();
      elements.set(key, {value:'',innerHTML:'',textContent:'',disabled:false,
        classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),toggle:(k,on)=>on?classes.add(k):classes.delete(k),contains:k=>classes.has(k)}});
    }
    return elements.get(key);
  };
  const context = {state,$,URL,URLSearchParams,Map,Date,Set,CHANGE_PAGE_SIZE:25,URL_PAGE_SIZE:50,escapeHtml:String,labels:{},window:{},renderUrlCoverage(){}};
  vm.createContext(context);
  return context;
}
async function run() {
  const c = setup({urls:new Map(),changePage:1,changesRequestId:0});
  vm.runInContext(pick('async function readWebsiteChanges(', 'async function showChangeGroup('), c);
  c.$('#website-select').value='a';
  const row = {id:'x',url_id:'u',normalized_url:'https://example.test/path',current_snapshot_id:'s',detected_at:'2026-09-22',change_type:'main_content_changed'};
  c.changeLabel=()=> 'Content gewijzigd';
  c.state.changeGroups=c.groupChanges([row]);
  c.$('#change-search').value='example.test/path';
  c.renderChanges();
  assert.match(c.$('#change-rows').innerHTML,/href="https:\/\/example.test\/path"/);
  assert.equal(c.state.changeFiltered.length,1,'search uses API labels without inventory');
  c.state.changeGroups=c.groupChanges([{...row,normalized_url:null}]);c.$('#change-search').value='';c.renderChanges();
  assert.doesNotMatch(c.$('#change-rows').innerHTML,/href="Onbekende/);
  c.state.changeGroups=c.groupChanges([
    {...row,change_type:'canonical_changed',current_crawl_run_id:'crawl',old_value:'https://old.test/path',new_value:'https://new.test/path'},
    {...row,id:'y',url_id:'v',normalized_url:'https://example.test/other',current_snapshot_id:'s2',change_type:'canonical_changed',current_crawl_run_id:'crawl',old_value:'https://old.test/other',new_value:'https://new.test/other'}
  ]);
  c.$('#change-search').value='example.test/other';c.renderChanges();
  assert.equal(c.state.changeFiltered.length,1,'domain-swap search includes all affected URL labels');
  assert.equal(c.changeUrl(c.state.changeGroups[0],'v'),'https://example.test/other');
  c.$('#change-search').value='';
  const offsets=[];
  c.api=async path=>{offsets.push(path);return offsets.length===1?Array.from({length:1000},()=>row):[row];};
  assert.equal((await c.readWebsiteChanges('a')).length,1001,'full history preserved across pages');
  assert.match(offsets[1],/offset=1000/);
  let calls=0,resolve;
  c.api=()=>{calls++;return new Promise(r=>resolve=r);};
  const first=c.readWebsiteChanges('a'),second=c.readWebsiteChanges('a');
  assert.equal(calls,1,'dashboard and changes share in-flight pagination');
  resolve([row]);await Promise.all([first,second]);
  assert.equal(c.state.changesRead,null,'completed requests are not persistent caches');
  c.api=async()=>{throw Error('API-fout 503');};
  await c.loadChanges();
  assert.match(c.$('#change-rows').innerHTML,/503/);
  assert.equal(c.$('#change-empty').classList.contains('hidden'),true);
  c.api=async()=>[];await c.loadChanges();
  assert.equal(c.$('#change-empty').classList.contains('hidden'),false,'successful empty result differs from failure');
  const requests=[];c.api=()=>new Promise((resolve,reject)=>requests.push({resolve,reject}));
  const old=c.loadChanges(); c.$('#website-select').value='b';c.state.changesRead=null;
  const newer=c.loadChanges();requests[1].resolve([row]);await newer;
  const rendered=c.$('#change-rows').innerHTML; requests[0].reject(Error('old failure'));await old;
  assert.equal(c.$('#change-rows').innerHTML,rendered,'late failure cannot overwrite current website');

  const u=setup({issuesLoading:true,urlRecords:[],signalsError:false});
  vm.runInContext(pick('function renderTableState(', 'function groupChanges(')+pick('function renderUrls()', 'function renderUrlCoverage()'),u);
  u.renderUrls();assert.match(u.$('#url-rows').innerHTML,/worden geladen/);assert.equal(u.$('#url-empty').classList.contains('hidden'),true);
  u.state.issuesLoading=false;u.state.signalsError=true;u.renderUrls();assert.match(u.$('#url-rows').innerHTML,/niet worden geladen/);
  u.state.signalsError=false;u.renderUrls();assert.equal(u.$('#url-empty').classList.contains('hidden'),false);

  const t=setup({currentUser:{role:'editor'},recommendationTasks:[],taskMembers:[]});
  Object.assign(t,{taskRoleLabels:{},taskStatusLabels:{},verificationStatusLabels:{},taskOwnerLabel:()=>'',formatTaskEffort:()=>'',taskAssigneeOptions:()=>[],renderTaskNotifications(){}});
  vm.runInContext(pick('async function loadTaskCenter()', 'async function openTaskNotification('),t);
  t.$('#website-select').value='a';t.$('#client-select').value='client';
  const pending=[];t.api=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
  const a=t.loadTaskCenter();
  assert.match(t.$('#task-center-message').textContent,/worden geladen/);assert.equal(t.$('#task-empty').classList.contains('hidden'),true);
  t.$('#website-select').value='b';const b=t.loadTaskCenter();
  t.$('#website-select').value='a';const a2=t.loadTaskCenter();
  pending[4].resolve([]);pending[5].resolve([]);await a2;
  pending[0].reject(Error('stale A'));pending[1].resolve([]);await a;
  pending[2].resolve([{id:'old-b'}]);pending[3].resolve([]);await b;
  assert.equal(t.state.recommendationTasks.length,0,'A-B-A ignores stale successes and failures');
  assert.equal(t.$('#task-center-message').textContent,'');
  t.api=async()=>{throw Error('offline');};await t.loadTaskCenter();
  assert.match(t.$('#task-center-message').textContent,/offline/);assert.equal(t.$('#task-empty').classList.contains('hidden'),true);
  console.log('Loading regressions: independent URL labels, deduplication, errors, empty states and stale task responses verified.');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
