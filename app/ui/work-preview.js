(() => {
  const $ = id => document.getElementById(id);
  let serial = 0, page = 0;
  const labels = {execute:'Nu uitvoeren', decision:'Beslissing nodig', research:'Eerst onderzoeken', periodic:'Periodieke beoordeling', verification:'Herstel controleren', opportunity:'Inhoudelijke kansen', history:'Resultaten en historie', unassessed:'Nog niet beoordeeld'};
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date = value => value ? new Date(value).toLocaleString('nl-NL') : 'Niet beschikbaar';
  const safeLink = value => { try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? esc(url.href) : '#'; } catch { return '#'; } };
  async function read(path) {
    const response = await fetch(path, {credentials:'same-origin', cache:'no-store'});
    if (!response.ok) throw new Error(response.status === 403 ? 'Beheerderstoegang voor deze klant is vereist.' : response.status === 401 ? 'Log opnieuw in via de hoofdpagina.' : `Ophalen mislukt (${response.status}).`);
    return response.json();
  }
  const internalLink = (kind, id) => `/app?${esc(new URLSearchParams({website_id:$('site').value,[kind]:String(id)}))}#metingen/signalen`;
  function memberLink(item) {
    return `${item.url ? `<a href="${safeLink(item.url)}" target="_blank" rel="noopener">${esc(item.url)}</a>` : 'Websitebreed signaal'}${item.issue_id && item.issue_type !== 'query_content_review' ? ` · <a href="${internalLink('issue_id',item.issue_id)}">Open signaal</a>` : ''}${item.url_id && item.source_run_id ? `<details><summary>Verwijzende bronpagina’s</summary><p>Opgeslagen volledige crawl van ${date(item.source_run_at)}${item.source_run_status === 'partially_succeeded' ? ' · deels geslaagd, de bronlijst kan onvolledig zijn' : ''}; dit is geen live controle.</p><div class="sources" aria-live="polite"></div><button data-source-url="${esc(item.url_id)}" data-source-run="${esc(item.source_run_id)}" data-offset="0">Toon bronnen</button></details>` : ''}`;
  }
  $('cards').addEventListener('click', async event => {
    const button = event.target.closest('[data-source-url]');
    if (!button) return;
    const site = $('site').value, request = serial;
    const output = button.previousElementSibling;
    button.disabled = true;
    try {
      const params = new URLSearchParams({crawl_run_id:button.dataset.sourceRun,offset:button.dataset.offset,limit:'25'});
      const result = await read(`/api/v1/websites/${site}/internal-links/${button.dataset.sourceUrl}/sources?${params}`);
      if (request !== serial || site !== $('site').value) return;
      output.insertAdjacentHTML('beforeend', result.items.map(item => `<p><a href="${safeLink(item.url)}" target="_blank" rel="noopener">${esc(item.url)}</a><br>${item.anchor_texts.map(esc).join(' · ')}</p>`).join(''));
      const offset = Number(button.dataset.offset) + result.items.length;
      button.dataset.offset = String(offset);
      button.textContent = `${offset} van ${result.total} bronpagina’s${offset < result.total ? ' · Toon meer' : ''}`;
      if (!result.total) output.textContent = 'Geen verwijzende pagina’s in deze crawl gevonden; dit bewijst op zichzelf geen onbereikbaarheid.';
      button.disabled = offset >= result.total || !result.items.length;
    } catch (error) { if (request === serial) { button.textContent = `${error.message} Klik om opnieuw te proberen.`; button.disabled = false; } }
  });
  async function load() {
    const id = ++serial, site = $('site').value;
    $('cards').replaceChildren(); $('counts').replaceChildren(); $('page').textContent = '';
    $('previous').disabled = true; $('next').disabled = true;
    if (!site) { $('message').textContent = 'Selecteer een pilotwebsite.'; return; }
    $('message').textContent = 'Beoordelingen worden geladen…';
    const query = new URLSearchParams({offset:String(page*20),limit:'20',q:$('search').value.trim()});
    if ($('lane').value === 'all') query.set('include_history', 'true');
    else if ($('lane').value) query.set('lane', $('lane').value);
    try {
      const data = await read(`/api/v1/websites/${site}/work-preview?${query}`);
      if (id !== serial || site !== $('site').value) return;
      $('message').textContent = `${data.total} ${data.total === 1 ? "beoordeling" : "beoordelingen"} in deze selectie · beoordeeld op ${date(data.generated_at)} · ${data.rule_version}`;
      $('counts').innerHTML = Object.entries(data.counts).map(([key,count]) => `<div><strong>${count}</strong> ${esc(labels[key])}</div>`).join('');
      $('cards').innerHTML = data.items.map(item => `<article><span class="badge">${esc(labels[item.lane])}</span><span class="urgency">Geregistreerde ernst: ${esc({high:'hoog',medium:'middel',low:'laag'}[item.severity] || item.severity)}</span><h2>${esc(item.title)}</h2>${item.members?.length ? `<p><strong>${item.members.length} signalen met dezelfde onderbouwing</strong></p><ul>${item.members.map(member => `<li>${memberLink(member)}<small> · bewijs ${date(member.evidence_at)} · nieuwste paginameting ${date(member.latest_checked_at)}</small></li>`).join('')}</ul>` : memberLink(item)}<p>${esc(item.reason)}</p>${item.task_context ? `<p>${esc(item.task_context)}</p>` : ''}<dl><dt>Eerste stap</dt><dd>${esc(item.first_step)}</dd><dt>Voorgestelde rol</dt><dd>${esc(item.role)}</dd><dt>Gereed wanneer</dt><dd>${esc(item.completion)}</dd></dl>${item.tasks.length ? `<p><strong>Bestaand werk</strong></p><ul>${item.tasks.map(task => `<li><a href="${internalLink('task_id',task.id)}">${esc(task.title)}</a> · ${esc(task.status)}</li>`).join('')}</ul>` : '<p>Nog geen gekoppelde taak.</p>'}<details><summary>Onderbouwing en meetmomenten</summary><p>${esc(item.description)}</p><p>${esc(item.evidence_reason)}</p>${item.evidence_facts?.length ? `<ul>${item.evidence_facts.map(fact => `<li>${esc(fact)}</li>`).join('')}</ul>` : '<p>Concrete bewijsdetails ontbreken; controleer de bronmeting vóór een wijziging.</p>'}<dl><dt>Issue-status</dt><dd>${esc(item.status)}</dd><dt>Bewijswaarneming</dt><dd>${date(item.evidence_at)}</dd><dt>Nieuwste paginameting</dt><dd>${date(item.latest_checked_at)}</dd><dt>Nieuwste inhoudelijke analyse</dt><dd>${date(item.analysis_checked_at)}</dd><dt>Snapshot bij bewijs</dt><dd>${esc(item.snapshot_id)}</dd><dt>Issuetype</dt><dd>${esc(item.issue_type)}</dd></dl></details></article>`).join('') || '<p>Geen signalen in deze selectie.</p>';
      $('page').textContent = `Pagina ${page+1} van ${Math.max(1,Math.ceil(data.total/20))}`;
      $('previous').disabled = page === 0; $('next').disabled = (page+1)*20 >= data.total;
    } catch(error) { if (id === serial) $('message').textContent = error.message; }
  }
  for (const id of ['site','lane']) $(id).addEventListener('change', () => {page=0;load();});
  $('refresh').addEventListener('click', () => {page=0;load();});
  $('search').addEventListener('keydown', event => {if(event.key==='Enter'){page=0;load();}});
  $('previous').addEventListener('click', () => {page--;load();});
  $('next').addEventListener('click', () => {page++;load();});
  $('lane').insertAdjacentHTML('beforeend',Object.entries(labels).map(([key,label])=>`<option value="${key}">${label}</option>`).join(''));
  read('/api/v1/websites').then(sites => {
    const pilots = sites.filter(site => {try {return ['human.nl','schipperkozijnen.nl'].includes(new URL(site.base_url).hostname.replace(/^www\./,''));} catch{return false;}});
    $('site').insertAdjacentHTML('beforeend', pilots.map(site=>`<option value="${esc(site.id)}">${esc(site.name)}</option>`).join(''));
    const initial = new URLSearchParams(location.search).get('website_id');
    if (pilots.some(site=>site.id===initial)) $('site').value=initial;
    load();
  }).catch(error => {$('message').textContent=error.message;});
})();
