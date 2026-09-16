const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/ui/work-preview.js', 'utf8');
async function test() {
  const elements = new Map();
  const requests = [];
  const get = id => {
    if (!elements.has(id)) elements.set(id, {value:'',innerHTML:'',textContent:'',
      handlers:{},replaceChildren(){this.innerHTML='';},insertAdjacentHTML(_,v){this.innerHTML+=v;},
      addEventListener(name, fn){this.handlers[name]=fn;}});
    return elements.get(id);
  };
  const payload = {total:1,generated_at:'2026-09-16T07:00:00Z',rule_version:'pilot-2',
    counts:{research:1,verification:0,opportunity:0}, items:[{
      lane:'research',severity:'medium',title:'<img src=x onerror=alert(1)>',
      url:'javascript:alert(1)',reason:'Controleer',first_step:'Stap',role:'Redactie',
      completion:'Gereed',description:'Bewijs',evidence_reason:'Passende meting',
      evidence_facts:['<script>alert(1)</script>'],tasks:[]}]};
  vm.runInNewContext(source, {document:{getElementById:get},URL,URLSearchParams,
    location:{search:'?website_id=pilot'},fetch:async path=>{
      requests.push(String(path));
      return {ok:true,json:async()=>path==='/api/v1/websites'?
        [{id:'pilot',name:'Pilot',base_url:'https://human.nl'}]:payload};
    }});
  const settle=()=>new Promise(resolve=>setImmediate(resolve));
  await settle();
  assert.match(get('cards').innerHTML,/&lt;script&gt;/);
  assert.doesNotMatch(get('cards').innerHTML,/<script>|href="javascript:/);
  assert.match(get('cards').innerHTML,/href="#"/);
  assert.match(get('cards').innerHTML,/Passende meting/);
  assert.doesNotMatch(requests.at(-1),/include_history/);
  get('lane').value='all'; get('lane').handlers.change(); await settle();
  assert.match(requests.at(-1),/include_history=true/);
  assert.doesNotMatch(requests.at(-1),/lane=all/);
  get('lane').value='verification'; get('lane').handlers.change(); await settle();
  assert.match(requests.at(-1),/lane=verification/);
  assert.doesNotMatch(get('counts').innerHTML,/undefined/);
  console.log('Work preview: history selection, evidence rendering and escaping verified.');
}
test().catch(error=>{console.error(error);process.exitCode=1;});
