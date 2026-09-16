(() => {
  const $ = id => document.getElementById(id);
  let serial = 0, page = 0;
  const labels = {execute:'Nu uitvoeren', decision:'Beslissing nodig', research:'Eerst onderzoeken', periodic:'Periodieke beoordeling', history:'Resultaten en historie', unassessed:'Nog niet beoordeeld'};
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date = value => value ? new Date(value).toLocaleString('nl-NL') : 'Niet beschikbaar';
  const safeLink = value => { try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? esc(url.href) : '#'; } catch { return '#'; } };
  async function read(path) {
    const response = await fetch(path, {credentials:'same-origin', cache:'no-store'});
    if (!response.ok) throw new Error(response.status === 403 ? 'Beheerderstoegang voor deze klant is vereist.' : response.status === 401 ? 'Log opnieuw in via de hoofdpagina.' : `Ophalen mislukt (${response.status}).`);
    return response.json();
  }
  async function load() {
    const id = ++serial, site = $('site').value;
    $('cards').replaceChildren(); $('counts').replaceChildren(); $('page').textContent = '';
    $('previous').disabled = true; $('next').disabled = true;
    if (!site) { $('message').textContent = 'Selecteer een pilotwebsite.'; return; }
    $('message').textContent = 'Beoordelingen worden geladen…';
    const query = new URLSearchParams({offset:String(page*20),limit:'20',q:$('search').value.trim()});
    if ($('lane').value) query.set('lane', $('lane').value);
    try {
      const data = await read(`/api/v1/websites/${site}/work-preview?${query}`);
      if (id !== serial || site !== $('site').value) return;
      $('message').textContent = `${data.total} ${data.total === 1 ? "signaal" : "signalen"} in deze selectie · beoordeeld op ${date(data.generated_at)} · ${data.rule_version}`;
      $('counts').innerHTML = Object.entries(data.counts).map(([key,count]) => `<div><strong>${count}</strong> ${esc(labels[key])}</div>`).join('');
      $('cards').innerHTML = data.items.map(item => `<article><span class="badge">${esc(labels[item.lane])}</span><span class="urgency">Geregistreerde ernst: ${esc({high:'hoog',medium:'middel',low:'laag'}[item.severity] || item.severity)}</span><h2>${esc(item.title)}</h2>${item.url ? `<a href="${safeLink(item.url)}" target="_blank" rel="noopener">${esc(item.url)}</a>` : '<p>Websitebreed signaal</p>'}<p>${esc(item.reason)}</p><dl><dt>Eerste stap</dt><dd>${esc(item.first_step)}</dd><dt>Voorgestelde rol</dt><dd>${esc(item.role)}</dd><dt>Gereed wanneer</dt><dd>${esc(item.completion)}</dd></dl>${item.tasks.length ? `<p><strong>Bestaand werk</strong></p><ul>${item.tasks.map(task => `<li>${esc(task.title)} · ${esc(task.status)}</li>`).join('')}</ul>` : '<p>Nog geen gekoppelde taak.</p>'}<details><summary>Onderbouwing en meetmomenten</summary><p>${esc(item.description)}</p><dl><dt>Issue-status</dt><dd>${esc(item.status)}</dd><dt>Bewijswaarneming</dt><dd>${date(item.evidence_at)}</dd><dt>Nieuwste paginameting</dt><dd>${date(item.latest_checked_at)}</dd><dt>Snapshot bij bewijs</dt><dd>${esc(item.snapshot_id)}</dd><dt>Issuetype</dt><dd>${esc(item.issue_type)}</dd></dl></details></article>`).join('') || '<p>Geen signalen in deze selectie.</p>';
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
