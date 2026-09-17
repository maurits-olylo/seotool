const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('app/ui/app.js','utf8');
const pick=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
async function run(){
  let release, loads=0;
  const elements=new Map([['#website-select',{value:'site'}]]);
  const state={};
  const context={state,$:s=>elements.get(s),loadIssues:async()=>{loads++;await new Promise(r=>release=r);state.signalsWebsiteId='site';}};
  vm.runInNewContext(pick('async function ensureSignals()', 'async function loadIssues()'),context);
  const first=context.ensureSignals(),second=context.ensureSignals();
  assert.equal(loads,1);release();await Promise.all([first,second]);
  await context.ensureSignals();assert.equal(loads,1);
  state.signalsWebsiteId=null;
  const third=context.ensureSignals();assert.equal(loads,2);release();await third;

  const calls=[];
  let showIssueArgs;
  const selected={value:'site'};
  const nav={URLSearchParams,encodeURIComponent,
    window:{location:{search:'?website_id=site&task_id=task'}},
    api:async path=>{calls.push(path);if(path.includes('/websites/'))return{id:'site',client_id:'client'};if(path.includes('/recommendation-tasks/'))return{id:'task',website_id:'site',primary_issue_id:'issue'};return{id:'issue',website_id:'site'};},
    clearWebsiteViewState(){},showApp(){},showView(){},$ :()=>selected,
    loadClients:async(c,s,loadSignals)=>assert.equal(loadSignals,false),
    showIssue:async(...args)=>{showIssueArgs=args;},alert:msg=>{throw Error(msg);}};
  vm.runInNewContext(pick('async function openWorkPreviewLink()', 'async function loadClients('),nav);
  await nav.openWorkPreviewLink();
  assert.equal(calls.length,3);
  assert.equal(showIssueArgs[2].id,'issue');assert.equal(showIssueArgs[3].id,'task');
  assert.equal(calls.some(p=>/\/urls\?|client-report|job-listings/.test(p)),false);

  // Boot must resolve a deep link before ordinary workspace loading.
  const bootCalls=[];
  const boot={state:{},api:async()=>({}),applyRolePermissions(){},openWorkPreviewLink:async()=>{bootCalls.push('deep');return true;},
    loadClients:async()=>bootCalls.push('workspace'),showApp(){bootCalls.push('app');},$:()=>null};
  vm.runInNewContext(source.slice(source.lastIndexOf('api("/api/v1/me").then')),boot);
  await new Promise(r=>setImmediate(r));
  assert.deepEqual(bootCalls,['deep']);

  const follow={};
  vm.runInNewContext(pick('function issueFollowup(', 'function recommendationNextStep('),follow);
  assert.match(follow.issueFollowup({status:'resolved'}).step,/nameting/);
  assert.match(follow.issueFollowup({status:'verified'}).step,/afgehandeld/);
  assert.equal(follow.issueFollowup({status:'new'}),null);
  console.log('Workspace loading: deduplication, direct boot, detail reuse and recovery guidance verified.');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
const verificationContext={state:{selectedRecommendationTask:{status:'planned',readiness:{lane:'verification'},urls:[],verification_status:'not_requested',recommendation_type:'repair_broken_internal_link'},recommendationVerificationPlan:{supported:true,missing_roles:[],required_roles:[],url_count:0},recommendationVerifications:[]},escapeHtml:s=>String(s)};
vm.runInNewContext(pick('function renderTaskVerification(', 'async function startRecommendationVerification('),verificationContext);
const verificationHtml=verificationContext.renderTaskVerification(false);
assert.match(verificationHtml,/Meld geen uitvoering die niet is gedaan/);
assert.doesNotMatch(verificationHtml,/Meld de taak eerst als/);
