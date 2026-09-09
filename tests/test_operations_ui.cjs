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
