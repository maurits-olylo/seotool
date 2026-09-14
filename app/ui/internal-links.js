(() => {
  const el = (id) => document.getElementById(`internal-links-${id}`);
  const escape = (value) => escapeHtml(String(value ?? ""));
  const link = (url) => {
    try { const parsed = new URL(url); return ["https:", "http:"].includes(parsed.protocol) ? escape(parsed.href) : "#"; }
    catch { return "#"; }
  };
  const labels = {low:"Weinig verwijzingen", lost:"Verloren verwijzingen", errors:"Gelinkte foutpagina’s", repeated:"Breed herhaald", technical:"Technische URL’s"};
  let site = "", request = 0, page = 0, data = null, detailRequest = 0, target = null, sourceOffset = 0, timer;
  const currentSite = () => document.getElementById("website-select").value;
  function clearDetail() {
    detailRequest++; target = null; sourceOffset = 0;
    el("detail").classList.add("hidden"); el("sources").innerHTML = ""; el("more").hidden = true;
  }
  async function load(force = false) {
    const selected = currentSite();
    if (!force && selected === site && data) return;
    if (!force && selected === site && el("context").dataset.loading === "true") return;
    if (selected !== site) { page = 0; el("search").value = ""; }
    site = selected; data = null; const id = ++request;
    clearDetail(); el("rows").innerHTML = ""; el("summary").innerHTML = ""; el("page").textContent = "";
    el("previous").disabled = true; el("next").disabled = true; el("empty").textContent = "";
    if (!site) { el("context").textContent = "Selecteer een website."; el("context").dataset.loading = "false"; return; }
    el("context").dataset.loading = "true"; el("context").textContent = "Interne links worden opgehaald…";
    const params = new URLSearchParams({q:el("search").value.trim(), view:el("view").value, order:el("order").value, offset:String(page*5), limit:"5"});
    try {
      const result = await api(`/api/v1/websites/${selected}/internal-links?${params}`);
      if (id !== request || selected !== currentSite()) return;
      data = result;
      if (!data.crawl_run_id) { el("context").textContent = data.reason || "Nog geen afgeronde volledige crawl beschikbaar. Een light check levert dit overzicht niet."; return; }
      el("context").textContent = `Volledige crawl afgerond op ${new Date(data.finished_at).toLocaleString("nl-NL")}. ${data.previous_finished_at ? `Verschil ten opzichte van ${new Date(data.previous_finished_at).toLocaleString("nl-NL")}; — betekent geen eerdere meting voor deze URL.` : "Geen eerdere volledige crawl met recente linkdetails om mee te vergelijken."}`;
      if (data.crawl_status === "partially_succeeded") {
        el("context").textContent = `Volledige crawl afgerond op ${new Date(data.finished_at).toLocaleString("nl-NL")}, deels geslaagd: ${data.crawled_urls} URL’s verwerkt, ${data.failed_urls} mislukt. Beschikbare links worden getoond; aantallen kunnen te laag zijn.`;
      }
      if (data.previous_finished_at && data.comparison_available === false) {
        el("context").textContent += " Verschillen worden niet berekend omdat een van de crawls deels geslaagd is; — betekent geen vergelijkbare meting.";
      }
      el("summary").innerHTML = Object.entries(labels).map(([key,label]) => `<button type="button" data-link-view="${key}" aria-pressed="${el("view").value === key}"><strong>${data.summary?.[key] ?? 0}</strong><span>${label}</span></button>`).join("");
      el("rows").innerHTML = data.items.map(item => `<tr><td><a href="${link(item.url)}" target="_blank" rel="noopener">${escape(item.url)}</a></td><td>${item.incoming_pages}</td><td>${(item.signals || []).filter(key => labels[key]).map(key => escape(labels[key])).join(" · ") || "—"}</td><td>${item.change == null ? "—" : item.change > 0 ? `+${item.change}` : item.change}</td><td>${item.status_code ?? "Niet gemeten"}</td><td><button type="button" class="detail-button" data-internal-target="${escape(item.url_id)}" data-internal-url="${escape(item.url)}">Toon bronnen</button></td></tr>`).join("");
      el("empty").textContent = data.items.length ? "" : "Geen pagina’s gevonden binnen deze selectie.";
      el("page").textContent = `${data.total} pagina’s · pagina ${page+1} van ${Math.max(1,Math.ceil(data.total/5))}`;
      el("previous").disabled = page === 0; el("next").disabled = (page+1)*5 >= data.total;
    } catch (error) {
      if (id === request && selected === currentSite()) el("context").textContent = `Interne links konden niet worden opgehaald: ${error.message}`;
    } finally { if (id === request) el("context").dataset.loading = "false"; }
  }
  async function sources() {
    const id = ++detailRequest, selected = site, selectedTarget = target, run = data?.crawl_run_id;
    if (!run || !target) return;
    el("more").hidden = true; el("detail-context").textContent = "Bronpagina’s worden opgehaald…";
    try {
      const result = await api(`/api/v1/websites/${selected}/internal-links/${target}/sources?crawl_run_id=${run}&offset=${sourceOffset}&limit=25`);
      if (id !== detailRequest || selected !== currentSite() || selectedTarget !== target) return;
      el("sources").insertAdjacentHTML("beforeend", result.items.map(item => `<tr><td><a href="${link(item.url)}" target="_blank" rel="noopener">${escape(item.url)}</a></td><td>${item.anchor_texts.map(text => escape(text || "(lege linktekst)")).join("<br>")}</td></tr>`).join(""));
      sourceOffset += result.items.length;
      el("detail-context").textContent = `${sourceOffset} van ${result.total} unieke verwijzende pagina’s uit dezelfde crawl.`;
      el("more").hidden = sourceOffset >= result.total;
    } catch (error) { if (id === detailRequest && selected === currentSite()) el("detail-context").textContent = `Bronnen konden niet worden opgehaald: ${error.message}`; }
  }
  document.querySelector(".internal-links-panel").addEventListener("click", event => {
    const filter = event.target.closest("[data-link-view]");
    if (filter) { el("view").value=filter.dataset.linkView; page=0; load(true); return; }
    const button = event.target.closest("[data-internal-target]"); if (!button) return;
    clearDetail(); target = button.dataset.internalTarget; el("detail").classList.remove("hidden");
    el("detail-title").textContent = `Verwijzende pagina’s naar ${button.dataset.internalUrl}`;
    sources();
  });
  el("more").addEventListener("click", sources);
  el("refresh").addEventListener("click", () => { page=0; load(true); });
  el("search").addEventListener("input", () => { clearTimeout(timer); timer=setTimeout(() => { page=0; load(true); },250); });
  el("view").addEventListener("change", () => { page=0; load(true); });
  el("order").addEventListener("change", () => { page=0; load(true); });
  el("previous").addEventListener("click", () => { page--; load(true); });
  el("next").addEventListener("click", () => { page++; load(true); });
  document.getElementById("website-select").addEventListener("change", () => { if (state.currentView === "urls") load(true); else { request++; clearDetail(); data=null; } });
  window.loadInternalLinks = load;
  if (state.currentView === "urls") load();
})();
