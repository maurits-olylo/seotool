const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/ui/app.js'), 'utf8');
const render = source.slice(source.indexOf('function renderSystemStatus()'), source.indexOf('\nfunction durationLabel'));
function display(status) {
  const elements = new Map();
  const context = {state: {systemStatus: status}, $: (selector) => {
    if (!elements.has(selector)) elements.set(selector, {classList: {toggle() {}}});
    return elements.get(selector);
  }};
  vm.runInNewContext(render + '\nrenderSystemStatus();', context);
  return elements;
}
let result = display(null);
assert.equal(result.get('#system-status-summary').textContent, 'Status onbekend');
assert.doesNotMatch(result.get('#system-status-grid').innerHTML, /0 worker|Database niet bereikbaar|Geen openstaande dead letters/);
result = display({status: 'degraded', api: 'ok', database: 'ok', queues: {exports: {status: 'unknown', workers: null, queued_jobs: null}}, dead_letters: {unresolved: null}});
assert.match(result.get('#system-status-grid').innerHTML, /Bereikbaar/);
assert.doesNotMatch(result.get('#system-status-grid').innerHTML, /null worker|0 worker|Geen openstaande dead letters/);
result = display({status: 'degraded', api: 'ok', database: 'ok', queues: {exports: {status: 'unavailable', workers: 0, queued_jobs: 2}}, dead_letters: {unresolved: 0}});
assert.match(result.get('#system-status-grid').innerHTML, /0 worker · 2 in wachtrij/);
assert.match(result.get('#system-status-grid').innerHTML, /Geen openstaande dead letters/);
console.log('Operations UI: unknown, partial and measured-zero states verified.');

async function selectionRegression() {
  const handlers = new Map();
  const elements = new Map([
    ['#client-select', {value: 'schipper'}],
    ['#website-select', {value: 'human', innerHTML: ''}],
  ]);
  const calls = [];
  const state = {currentView: 'operations', externalEvidenceRequests: new Map(),
    operationsRequestId: 1, changesRequestId: 1, crawlRuns: ['human'],
    issues: ['human'], clientReport: {website: 'human'}, jobListings: ['human']};
  const context = {state, Map, CLIENT_STORAGE_KEY: 'client', WEBSITE_STORAGE_KEY: 'website',
    localStorage: {setItem() {}, removeItem() {}},
    $: (selector) => {
      if (!elements.has(selector)) elements.set(selector, {});
      const el = elements.get(selector);
      el.addEventListener = (name, handler) => handlers.set(selector, handler);
      return el;
    },
    renderOperations() { calls.push('clear'); assert.equal(state.crawlRuns.length, 0); },
    async loadWebsites() {
      assert.equal(state.issues.length, 0);
      assert.equal(state.clientReport, null);
      elements.get('#website-select').value = 'schipper-site';
      calls.push('websites');
    },
    async loadOperations() {
      assert.equal(elements.get('#website-select').value, 'schipper-site');
      calls.push('operations');
    },
    async loadIssues() { calls.push('issues'); },
  };
  const selection = source.slice(source.indexOf('function clearWebsiteViewState()'),
    source.indexOf('\nfor (const selector of ["#severity-filter"'));
  vm.runInNewContext(selection, context);
  await handlers.get('#client-select')();
  assert.deepEqual(calls, ['clear', 'websites', 'operations']);
  calls.length = 0;
  await handlers.get('#website-select')();
  assert.deepEqual(calls, ['clear', 'issues', 'operations']);
  console.log('Client and website switches clear cached data and reload operations.');
}
selectionRegression().catch((error) => { console.error(error); process.exitCode = 1; });

async function staleIssuesRegression() {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const elements = new Map([
    ['#client-select', {value: 'old-client'}], ['#website-select', {value: 'old-site'}],
    ['#status-filter', {value: 'active'}],
  ]);
  const state = {issues: ['current'], currentUser: {role: 'member'}};
  const context = {state, $: (selector) => elements.get(selector),
    api: async () => { await pending; return []; }, loadAllUrls: async () => [],
  };
  const loader = source.slice(source.indexOf('async function loadIssues()'),
    source.indexOf('\nasync function loadAllUrls'));
  vm.runInNewContext(loader, context);
  const request = context.loadIssues();
  elements.get('#website-select').value = 'new-site';
  elements.get('#client-select').value = 'new-client';
  release();
  await request;
  assert.deepEqual(state.issues, ['current']);
  console.log('Late issue responses cannot overwrite another website.');
}
staleIssuesRegression().catch((error) => { console.error(error); process.exitCode = 1; });
