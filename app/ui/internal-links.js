(() => {
  const el = (id) => document.getElementById(`internal-links-${id}`);
  const escape = (value) => escapeHtml(String(value ?? ""));
  const link = (url) => {
    try { const parsed = new URL(url); return ["https:", "http:"].includes(parsed.protocol) ? escape(parsed.href) : "#"; }
    catch { return "#"; }
  };
  const pageLabel = (url) => {
    try { const parsed = new URL(url); return parsed.pathname + parsed.search || "/"; }
    catch { return url; }
  };
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
    clearDetail(); el("rows").innerHTML = ""; el("chart").innerHTML = ""; el("page").textContent = "";
    el("previous").disabled = true; el("next").disabled = true; el("empty").textContent = "";
    if (!site) { el("context").textContent = "Selecteer een website."; el("context").dataset.loading = "false"; return; }
    el("context").dataset.loading = "true"; el("context").textContent = "Interne links worden opgehaald…";
    const params = new URLSearchParams({q:el("search").value.trim(), order:el("order").value, offset:String(page*25), limit:"25"});
    try {
      const result = await api(`/api/v1/websites/${selected}/internal-links?${params}`);
      if (id !== request || selected !== currentSite()) return;
      data = result;
      if (!data.crawl_run_id) { el("context").textContent = data.reason || "Nog geen geslaagde volledige crawl beschikbaar. Een light check levert dit overzicht niet."; return; }
      el("context").textContent = `Volledige crawl afgerond op ${new Date(data.finished_at).toLocaleString("nl-NL")}. ${data.previous_finished_at ? `Verschil ten opzichte van ${new Date(data.previous_finished_at).toLocaleString("nl-NL")}; — betekent geen eerdere meting voor deze URL.` : "Geen eerdere volledige crawl met recente linkdetails om mee te vergelijken."}`;
      const maximum = data.top[0]?.incoming_pages || 1;
      el("chart").innerHTML = data.top.map(item => `<button type="button" class="internal-link-bar" data-internal-target="${escape(item.url_id)}" data-internal-url="${escape(item.url)}" aria-label="${escape(item.url)}: ${item.incoming_pages} verwijzende pagina’s"><span title="${escape(item.url)}">${escape(pageLabel(item.url))}</span><span class="internal-link-bar-track" aria-hidden="true"><i style="width:${100*item.incoming_pages/maximum}%"></i></span><strong>${item.incoming_pages}</strong></button>`).join("");
      el("rows").innerHTML = data.items.map(item => `<tr><td><a href="${link(item.url)}" target="_blank" rel="noopener">${escape(item.url)}</a></td><td>${item.incoming_pages}</td><td>${item.change == null ? "—" : item.change > 0 ? `+${item.change}` : item.change}</td><td>${item.status_code ?? "Niet gemeten"}</td><td><button type="button" class="detail-button" data-internal-target="${escape(item.url_id)}" data-internal-url="${escape(item.url)}">Toon bronnen</button></td></tr>`).join("");
      el("empty").textContent = data.items.length ? "" : "Geen pagina’s gevonden binnen deze selectie.";
      el("page").textContent = `${data.total} pagina’s · pagina ${page+1} van ${Math.max(1,Math.ceil(data.total/25))}`;
      el("previous").disabled = page === 0; el("next").disabled = (page+1)*25 >= data.total;
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
    const button = event.target.closest("[data-internal-target]"); if (!button) return;
    clearDetail(); target = button.dataset.internalTarget; el("detail").classList.remove("hidden");
    el("detail-title").textContent = `Verwijzende pagina’s naar ${button.dataset.internalUrl}`;
    sources();
  });
  el("more").addEventListener("click", sources);
  el("refresh").addEventListener("click", () => { page=0; load(true); });
  el("search").addEventListener("input", () => { clearTimeout(timer); timer=setTimeout(() => { page=0; load(true); },250); });
  el("order").addEventListener("change", () => { page=0; load(true); });
  el("previous").addEventListener("click", () => { page--; load(true); });
  el("next").addEventListener("click", () => { page++; load(true); });
  document.getElementById("website-select").addEventListener("change", () => { if (state.currentView === "urls") load(true); else { request++; clearDetail(); data=null; } });
  window.loadInternalLinks = load;
  if (state.currentView === "urls") load();
})();
