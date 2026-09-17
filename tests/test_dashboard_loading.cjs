const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/ui/app.js', 'utf8');
const code = source.slice(source.indexOf('async function loadDashboard()'), source.indexOf('async function loadOperations()'));
async function run() {
  const elements = new Map();
  const $ = key => {if (!elements.has(key)) elements.set(key, {value:'',innerHTML:'',textContent:''});return elements.get(key);};
  $('#website-select').value = 'one'; $('#client-select').value = 'client';
  const state = {currentView:'dashboard',currentUser:{role:'editor'},integrationHealth:{}};
  const requests = [];
  const pending = [];
  const context = {state,$,escapeHtml:s=>s,labels:{},groupChanges:rows=>rows,changeGroupLabel:()=>'',crawlRunMetrics:()=>({summary:''}),durationLabel:()=>'',renderIntegrationWarning(){},
    api:path=>{requests.push(path);return new Promise((resolve,reject)=>pending.push({path,resolve,reject}));}};
  vm.runInNewContext(code, context);
  const first = context.loadDashboard();
  const same = context.loadDashboard();
  assert.equal(requests.length,5,'concurrent dashboard requests are deduplicated');
  assert.equal(requests.some(path=>/\/urls\?|url-coverage|issue-suppressions|\/exports|system\/status|\/issues\?/.test(path)),false);
  assert.match($('#dashboard-performance').textContent,/geladen/);
  pending.find(p=>p.path.includes('issue-summary')).resolve({counts:{total:9,high:9,medium:0,low:0},items:[]});
  await new Promise(r=>setImmediate(r));
  assert.match($('#dashboard-priorities').innerHTML,/Actieve acties: 9/,'signals render before other panels');
  pending.find(p=>p.path.includes('client-report')).reject(Error('unavailable'));
  await new Promise(r=>setImmediate(r));
  assert.match($('#dashboard-performance').textContent,/niet worden geladen/);
  // A response from the old website cannot overwrite the current dashboard.
  $('#website-select').value='two'; state.dashboard=null;
  const second=context.loadDashboard();
  for (const request of pending) {
    if (request.path.includes('issue-summary')) request.resolve({counts:{total:2,high:0,medium:2,low:0},items:[]});
    else if (request.path.includes('job-listings')) request.resolve({summary:{active:0}});
    else if (request.path.includes('client-report')) request.resolve({current:{clicks:0}});
    else request.resolve([]);
  }
  await Promise.all([first,same,second]);
  assert.equal(state.dashboard.websiteId,'two');
  assert.equal(state.dashboard.data.signals.counts.total,2);
  assert.match($('#dashboard-priorities').innerHTML,/Actieve acties: 2/);
  assert.match($('#dashboard-changes').innerHTML,/Geen betekenisvolle/);
  assert.match($('#dashboard-performance').innerHTML,/<strong>0<\/strong>/,'a real zero remains visible');
  assert.doesNotMatch(source.slice(source.indexOf('async function refreshSelectedWebsite('),source.indexOf('$("#client-select").addEventListener')),/\["dashboard", "actions", "urls"\]/);
  console.log('Dashboard: bounded reads, independent panels, errors, deduplication and website isolation verified.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
