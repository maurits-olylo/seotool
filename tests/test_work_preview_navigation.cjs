const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/ui/app.js', 'utf8');
const next = source.slice(source.indexOf('function recommendationNextStep('), source.indexOf('function renderRecommendationTask('));
const ctx = {};
vm.runInNewContext(next, ctx);
for (const status of ['open','planned','in_progress','waiting_for_input']) {
  assert.doesNotMatch(ctx.recommendationNextStep({status}).join(' '), /Start de uitvoering|Rond het werk af/);
  assert.match(ctx.recommendationNextStep({status, readiness:{lane:'research',label:'Eerst onderzoeken',reason:'Oud bewijs',first_step:'Controleer bronnen'}}).join(' '), /Oud bewijs/);
}
assert.equal(ctx.recommendationNextStep({status:'planned',readiness:{lane:'execute',first_step:'Pas de afgesproken link aan'}})[0], 'Start de uitvoering');
const navigation = source.slice(source.indexOf('async function openWorkPreviewLink('), source.indexOf('async function loadClients('));
async function run(mismatch=false, task=false) {
  const calls = [], selected = {value:'old-site'};
  const context = {URL, URLSearchParams, encodeURIComponent,
    window:{history:{replaceState(){}},location:{href:'https://test/app?website_id=site&task_id=task#acties',search: task ? '?website_id=site&task_id=task' : '?website_id=site&issue_id=issue'}},
    api:async path=>{calls.push(path);return path.includes('/websites/') ? {id:'site',client_id:'client'} : path.includes('/recommendation-tasks/') ? {website_id:'site',primary_issue_id:'issue'} : {id:'issue',website_id:mismatch?'other':'site'};},
    showApp(){},clearWebsiteViewState(){calls.push('clear');},
    loadClients:async(client,site)=>{calls.push([client,site]); selected.value=site;},
    $:()=>selected,showView:view=>calls.push(view),showIssue:async(id,task,issue,loadedTask)=>{assert.equal(issue.id, "issue"); if(task) assert.equal(loadedTask.primary_issue_id,"issue"); calls.push(['open',id,task]);},alert:msg=>calls.push(msg)};
  vm.runInNewContext(navigation, context);
  assert.equal(await context.openWorkPreviewLink(), true);
  if (mismatch) {
    assert.equal(selected.value,'old-site');
    assert.equal(calls.some(v=>Array.isArray(v)&&v[0]==='open'),false);
    assert.match(calls.at(-1),/andere website/);
  } else {
    assert.equal(selected.value,'site');
    assert.deepEqual(calls.at(-1),['open','issue',task?'task':null]);
    assert.equal(calls.at(-2),task?'tasks':'actions');
  }
}
Promise.all([run(),run(true),run(false,true),run(true,true)]).then(()=>console.log('Preview navigation: correct website, task and review guidance verified.')).catch(e=>{console.error(e);process.exitCode=1;});
