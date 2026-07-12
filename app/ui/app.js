const $ = (selector) => document.querySelector(selector);
const ACTIVE_STATUSES = new Set(["new", "review", "accepted", "planned", "in_progress", "waiting_for_client"]);
const PAGE_SIZE = 25;
const URL_PAGE_SIZE = 30;
const CHANGE_PAGE_SIZE = 30;
const labels = {
  high: "Hoog", medium: "Middel", low: "Laag", new: "Nieuw", review: "Te beoordelen",
  accepted: "Geaccepteerd", planned: "Gepland", in_progress: "Bezig",
  waiting_for_client: "Wacht op klant", resolved: "Opgelost", verified: "Geverifieerd",
  ignored: "Genegeerd", accepted_risk: "Risico geaccepteerd",
  pending: "In wachtrij", running: "Bezig", succeeded: "Geslaagd",
  partially_succeeded: "Deels geslaagd", failed: "Mislukt", cancelled: "Geannuleerd",
};
const state = { clients: [], websites: [], issues: [], changes: [], changeGroups: [], crawlRuns: [], exports: [], operationsLoading: false, urls: new Map(), urlRecords: [], filtered: [], urlFiltered: [], changeFiltered: [], page: 1, urlPage: 1, changePage: 1, selectedIssueId: null, googleConnectionId: null };
const VIEW_HASHES = {overview: "overzicht", urls: "urls", changes: "wijzigingen", operations: "beheer", integrations: "integraties"};
let operationsPollTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (response.status === 401) { showLogin(); throw new Error("Niet aangemeld"); }
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(payload.detail || `API-fout ${response.status}`); }
  return response.status === 204 ? null : response.json();
}

function showLogin() { stopOperationsPolling(); $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); }
function escapeHtml(value = "") { const node = document.createElement("span"); node.textContent = value; return node.innerHTML; }
function option(item) { return `<option value="${item.id}">${escapeHtml(item.name)}</option>`; }
function issueUrl(issue) { return state.urls.get(issue.url_id) || ""; }
function issueUrlLabel(issue) { return issueUrl(issue) || "Websitebreed issue"; }
function impactLevel(issue) { return issue.organic_impact?.level || "none"; }
function impactRank(issue) { return ({high: 0, medium: 1, low: 2, unknown: 3, none: 4})[impactLevel(issue)] ?? 4; }
function impactVolume(issue) {
  const impact = issue.organic_impact || {};
  return (impact.key_events || 0) * 10000 + (impact.sessions || 0) * 10 + (impact.clicks || 0) + (impact.impressions || 0) / 1000;
}
function impactMarkup(issue) {
  const impact = issue.organic_impact;
  if (!impact) return `<span class="impact-badge">Geen data</span>`;
  const label = {high: "Hoog", medium: "Middel", low: "Laag", unknown: "Onbekend"}[impact.level] || "Onbekend";
  const primary = impact.sessions !== undefined ? `${impact.sessions} sessies` : `${impact.clicks || 0} klikken`;
  const secondary = impact.key_events ? ` · ${impact.key_events} gebeurtenissen` : "";
  return `<span class="impact-badge ${impact.level}">${label}</span><span class="impact-metrics">${primary}${secondary}</span>`;
}
function issueUrlMarkup(issue) {
  const url = issueUrl(issue);
  return url ? `<a class="url" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>` : `<span class="url">Websitebreed issue</span>`;
}

async function loadClients() {
  state.clients = await api("/api/v1/clients");
  $("#client-select").innerHTML = state.clients.map(option).join("");
  await loadWebsites();
}

async function loadWebsites() {
  const clientId = $("#client-select").value;
  if (!clientId) { state.websites = []; state.issues = []; render(); return; }
  state.websites = await api(`/api/v1/websites?client_id=${clientId}`);
  $("#website-select").innerHTML = state.websites.map(option).join("");
  await loadIssues();
}

async function loadIntegrations() {
  const clientId = $("#client-select").value;
  if (!clientId) return;
  const [connections, googleConfig] = await Promise.all([
    api(`/api/v1/clients/${clientId}/integrations`),
    api("/api/v1/integrations/google/config"),
  ]);
  for (const provider of ["google", "bing"]) {
    const connection = connections.find((item) => item.provider === provider);
    const target = $(`#${provider}-status`);
    target.textContent = connection ? `${labels[connection.status] || connection.status}${connection.account_email ? ` · ${connection.account_email}` : ""}` : "Niet gekoppeld";
  }
  const googleConnection = connections.find((item) => item.provider === "google" && item.status === "connected");
  const googleLink = $("#google-connect");
  googleLink.textContent = googleConnection ? "Opnieuw koppelen" : "Google koppelen";
  if (googleConfig.configured) {
    googleLink.href = `/api/v1/integrations/google/authorize?client_id=${clientId}`;
    googleLink.setAttribute("aria-disabled", "false");
  } else {
    googleLink.removeAttribute("href");
    googleLink.setAttribute("aria-disabled", "true");
  }
  if (googleConnection) {
    state.googleConnectionId = googleConnection.id;
    await loadGoogleProperties().catch(() => {
      $("#integration-message").textContent = "Google-properties konden niet worden geladen. Controleer de API-rechten en probeer opnieuw.";
      $("#integration-message").classList.remove("hidden");
    });
  } else {
    state.googleConnectionId = null;
    $("#property-mapping").classList.add("hidden");
  }
}

async function loadGoogleProperties() {
  const clientId = $("#client-select").value;
  const websiteId = $("#website-select").value;
  if (!clientId || !websiteId || !state.googleConnectionId) return;
  const [properties, mappings] = await Promise.all([
    api(`/api/v1/clients/${clientId}/integrations/google/properties`),
    api(`/api/v1/websites/${websiteId}/integrations`),
  ]);
  const searchConsoleMapping = mappings.find((item) => item.service === "search_console");
  const ga4Mapping = mappings.find((item) => item.service === "ga4");
  fillPropertySelect("#search-console-property", properties.search_console, searchConsoleMapping);
  fillPropertySelect("#ga4-property", properties.ga4, ga4Mapping);
  showMappingStatus(searchConsoleMapping, "#search-console-message", "Search Console");
  showMappingStatus(ga4Mapping, "#ga4-message", "GA4");
  $("#mapping-website").textContent = $("#website-select").selectedOptions[0]?.textContent || "website";
  $("#property-mapping").classList.remove("hidden");
}

function showMappingStatus(mapping, selector, label) {
  const target = $(selector);
  if (!mapping) { target.textContent = ""; return; }
  if (mapping.status === "error") { target.textContent = `${label}: laatste synchronisatie mislukt.`; return; }
  target.textContent = mapping.last_synced_at
    ? `${label} laatst bijgewerkt: ${new Date(mapping.last_synced_at).toLocaleString("nl-NL")}.`
    : `${label}-property gekoppeld; nog niet gesynchroniseerd.`;
}

function fillPropertySelect(selector, properties, mapping) {
  const select = $(selector);
  select.innerHTML = `<option value="">Selecteer een property</option>${properties.map((property) => `<option value="${escapeHtml(property.id)}" data-name="${escapeHtml(property.name)}">${escapeHtml(property.name)}${property.account ? ` · ${escapeHtml(property.account)}` : ""}</option>`).join("")}`;
  if (mapping) select.value = mapping.external_property_id;
}

async function saveProperty(service, selector, buttonSelector, messageSelector) {
  const websiteId = $("#website-select").value;
  const select = $(selector);
  if (!websiteId || !select.value || !state.googleConnectionId) return;
  const button = $(buttonSelector); const message = $(messageSelector);
  button.disabled = true; button.textContent = "Bezig…"; message.textContent = "";
  try {
    await api(`/api/v1/websites/${websiteId}/integrations/${service}`, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ connection_id: state.googleConnectionId, external_property_id: select.value, external_property_name: select.selectedOptions[0]?.dataset.name || select.value }),
    });
    button.textContent = "Opgeslagen ✓"; message.textContent = `${service === "ga4" ? "GA4" : "Search Console"}-property opgeslagen.`;
  } catch (error) { button.textContent = "Opnieuw proberen"; message.textContent = "Opslaan is mislukt."; }
  finally { button.disabled = false; }
}

async function syncSearchConsole() {
  const websiteId = $("#website-select").value;
  const button = $("#sync-search-console"); const message = $("#search-console-message");
  if (!websiteId) return;
  button.disabled = true; button.textContent = "Importeren…"; message.textContent = "";
  try {
    const result = await api(`/api/v1/websites/${websiteId}/integrations/search_console/sync`, {method: "POST"});
    message.textContent = `${result.rows} dag/pagina-regels geïmporteerd; ${result.matched_urls} gekoppeld aan URLs.`;
    button.textContent = "Opnieuw synchroniseren";
    await loadIssues();
  } catch (error) { message.textContent = "GSC-import is mislukt."; button.textContent = "Opnieuw proberen"; }
  finally { button.disabled = false; }
}

async function syncGa4() {
  const websiteId = $("#website-select").value;
  const button = $("#sync-ga4"); const message = $("#ga4-message");
  if (!websiteId) return;
  button.disabled = true; button.textContent = "Importeren…"; message.textContent = "";
  try {
    const result = await api(`/api/v1/websites/${websiteId}/integrations/ga4/sync`, {method: "POST"});
    message.textContent = `${result.rows} dag/landingspagina-regels geïmporteerd; ${result.matched_urls} gekoppeld aan URLs.`;
    button.textContent = "Opnieuw synchroniseren";
    await loadIssues();
  } catch (error) { message.textContent = "GA4-import is mislukt."; button.textContent = "Opnieuw proberen"; }
  finally { button.disabled = false; }
}

function showView(view, updateHash = true) {
  for (const name of ["overview", "urls", "changes", "operations", "integrations"]) {
    $(`#${name}-view`).classList.toggle("hidden", name !== view);
    $(`#${name}-nav`).classList.toggle("nav-active", name === view);
  }
  if (view === "integrations") loadIntegrations();
  if (view === "urls") renderUrls();
  if (view === "changes") loadChanges();
  if (view === "operations") { loadOperations(); startOperationsPolling(); } else stopOperationsPolling();
  if (updateHash) window.history.replaceState({}, "", `#${VIEW_HASHES[view]}`);
}

function viewFromHash() {
  const hash = window.location.hash.slice(1);
  return Object.keys(VIEW_HASHES).find((view) => VIEW_HASHES[view] === hash) || "overview";
}

function startOperationsPolling() {
  stopOperationsPolling();
  operationsPollTimer = window.setInterval(loadOperations, 4000);
}

function stopOperationsPolling() {
  if (operationsPollTimer) window.clearInterval(operationsPollTimer);
  operationsPollTimer = null;
}

async function loadIssues() {
  const websiteId = $("#website-select").value;
  if (!websiteId) { state.issues = []; render(); return; }
  const [issues, urls] = await Promise.all([
    api(`/api/v1/websites/${websiteId}/issues`),
    loadAllUrls(websiteId),
  ]);
  state.issues = issues;
  state.urlRecords = urls;
  state.urls = new Map(urls.map((url) => [url.id, url.normalized_url]));
  const types = [...new Set(issues.map((issue) => issue.issue_type))].sort();
  $("#type-filter").innerHTML = `<option value="">Alle issue-types</option>${types.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`).join("")}`;
  state.page = 1;
  render();
}

async function loadAllUrls(websiteId) {
  const urls = [];
  for (let offset = 0; ; offset += 1000) {
    const batch = await api(`/api/v1/websites/${websiteId}/urls?limit=1000&offset=${offset}`);
    urls.push(...batch);
    if (batch.length < 1000) return urls;
  }
}

function urlIndexState(url) {
  if (url.is_indexable === true) return "indexable";
  if (url.is_indexable === false) return "blocked";
  return "unknown";
}

function renderUrls() {
  const query = $("#url-search").value.trim().toLowerCase();
  const status = $("#url-status-filter").value;
  const indexation = $("#url-index-filter").value;
  const depth = $("#url-depth-filter").value;
  state.urlFiltered = state.urlRecords.filter((url) => {
    const code = url.current_status_code;
    const statusMatch = !status || (status === "none" ? code === null : code >= Number(status[0]) * 100 && code < (Number(status[0]) + 1) * 100);
    const indexMatch = !indexation || urlIndexState(url) === indexation;
    const depthMatch = !depth || (depth === "none" ? url.crawl_depth === null : depth === "0-2" ? url.crawl_depth >= 0 && url.crawl_depth <= 2 : depth === "3-4" ? url.crawl_depth >= 3 && url.crawl_depth <= 4 : url.crawl_depth >= 5);
    return statusMatch && indexMatch && depthMatch && (!query || url.normalized_url.toLowerCase().includes(query));
  });
  const pages = Math.max(1, Math.ceil(state.urlFiltered.length / URL_PAGE_SIZE));
  state.urlPage = Math.min(state.urlPage, pages);
  const start = (state.urlPage - 1) * URL_PAGE_SIZE;
  const rows = state.urlFiltered.slice(start, start + URL_PAGE_SIZE);
  $("#urls-website-name").textContent = $("#website-select").selectedOptions[0]?.textContent || "de website";
  $("#url-rows").innerHTML = rows.map((url) => {
    const indexState = urlIndexState(url);
    const indexLabel = {indexable: "Indexeerbaar", blocked: "Niet indexeerbaar", unknown: "Onbekend"}[indexState];
    const checked = url.last_full_analyzed_at ? new Date(url.last_full_analyzed_at).toLocaleDateString("nl-NL") : "—";
    return `<tr><td><a class="url-address" href="${escapeHtml(url.normalized_url)}" target="_blank" rel="noopener">${escapeHtml(url.normalized_url)}</a></td><td><span class="status-code">${url.current_status_code ?? "—"}</span></td><td><span class="index-state ${indexState}">${indexLabel}</span></td><td>${url.crawl_depth ?? "—"}</td><td>${checked}</td><td><button class="detail-button" data-url-id="${url.id}">Bekijk</button></td></tr>`;
  }).join("");
  $("#url-result-count").textContent = `${state.urlFiltered.length} URLs`;
  $("#url-page-label").textContent = `Pagina ${state.urlPage} van ${pages}`;
  $("#url-previous-page").disabled = state.urlPage === 1;
  $("#url-next-page").disabled = state.urlPage === pages;
  $("#url-empty").classList.toggle("hidden", rows.length !== 0);
}

async function showUrl(urlId) {
  const url = state.urlRecords.find((item) => item.id === urlId);
  if (!url) return;
  const snapshots = await api(`/api/v1/urls/${urlId}/snapshots?limit=1`);
  const snapshot = snapshots[0];
  const issues = state.issues.filter((issue) => issue.url_id === urlId && ACTIVE_STATUSES.has(issue.status));
  $("#url-detail-link").textContent = url.normalized_url;
  $("#url-detail-link").href = url.normalized_url;
  $("#url-detail-status").textContent = `${url.current_status_code ?? "Niet gecontroleerd"}${url.current_final_url && url.current_final_url !== url.normalized_url ? ` → ${url.current_final_url}` : ""}`;
  $("#url-detail-indexation").textContent = {indexable: "Indexeerbaar", blocked: "Niet indexeerbaar", unknown: "Onbekend"}[urlIndexState(url)];
  $("#url-detail-crawl").textContent = `Crawl-diepte: ${url.crawl_depth ?? "onbekend"} · Paginatype: ${url.page_type || "onbekend"}`;
  $("#url-detail-snapshot").textContent = snapshot ? `${new Date(snapshot.checked_at).toLocaleString("nl-NL")} · ${snapshot.response_size ?? 0} bytes · ${snapshot.response_time_ms ?? "—"} ms · ${snapshot.word_count ?? "—"} woorden` : "Geen snapshot beschikbaar.";
  $("#url-detail-issues").textContent = issues.length ? issues.map((issue) => `${labels[issue.severity] || issue.severity}: ${issue.title}`).join("\n") : "Geen actieve issues.";
  $("#url-dialog").showModal();
}

async function loadOperations() {
  const websiteId = $("#website-select").value;
  if (!websiteId || state.operationsLoading) return;
  state.operationsLoading = true;
  try {
    [state.crawlRuns, state.exports] = await Promise.all([
      api(`/api/v1/websites/${websiteId}/crawl-runs?limit=20`),
      api(`/api/v1/exports?website_id=${websiteId}&limit=20`),
    ]);
    $("#operations-website-name").textContent = $("#website-select").selectedOptions[0]?.textContent || "de website";
    renderOperations();
  } finally { state.operationsLoading = false; }
}

function durationLabel(run) {
  if (!run.finished_at) return run.status === "running" ? "Bezig" : "—";
  const seconds = Math.max(0, Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000));
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`;
}

function renderOperations() {
  const runLabels = {light_check: "Light check", full_site_crawl: "Volledige crawl", fetch_sitemap: "Sitemap", full_page_analysis: "Pagina-analyse"};
  $("#crawl-run-rows").innerHTML = state.crawlRuns.map((run) => `<tr><td>${new Date(run.started_at).toLocaleString("nl-NL")}</td><td>${runLabels[run.crawl_type] || escapeHtml(run.crawl_type)}</td><td><span class="run-status ${run.status}">${labels[run.status] || run.status}</span></td><td>${run.discovered_urls}</td><td>${run.crawled_urls}</td><td>${run.failed_urls}</td><td>${durationLabel(run)}</td></tr>`).join("");
  $("#crawl-runs-empty").classList.toggle("hidden", state.crawlRuns.length !== 0);
  const runningCrawl = state.crawlRuns.find((run) => run.status === "running");
  $("#crawl-live-status").classList.toggle("hidden", !runningCrawl);
  $("#start-light-check").disabled = Boolean(runningCrawl);
  $("#start-full-crawl").disabled = Boolean(runningCrawl);
  if (runningCrawl) $("#crawl-live-label").textContent = `${runLabels[runningCrawl.crawl_type] || runningCrawl.crawl_type} bezig · ${runningCrawl.crawled_urls} gecrawld · ${runningCrawl.failed_urls} mislukt`;
  const currentExport = state.exports.find((item) => !item.downloaded_at && ["pending", "running", "succeeded"].includes(item.status));
  const exportPanel = $("#current-export"); const exportButton = $("#generate-excel"); const download = $("#current-export-download");
  exportPanel.classList.toggle("hidden", !currentExport);
  exportButton.disabled = Boolean(currentExport);
  if (currentExport) {
    $("#current-export-label").textContent = currentExport.status === "succeeded" ? "Excel-export is gereed voor download." : currentExport.status === "running" ? "Excel-export wordt opgebouwd…" : "Excel-export staat in de wachtrij…";
    $("#export-progress").classList.toggle("hidden", currentExport.status === "succeeded");
    download.classList.toggle("hidden", currentExport.status !== "succeeded");
    if (currentExport.status === "succeeded") download.href = `/api/v1/exports/${currentExport.id}/download`;
  } else if (state.exports[0]?.status === "failed") {
    $("#export-action-message").classList.add("error");
    $("#export-action-message").textContent = state.exports[0].error_message || "De laatste export is mislukt.";
  } else {
    $("#export-action-message").classList.remove("error");
    if (state.exports[0]?.downloaded_at) $("#export-action-message").textContent = "De laatste export is gedownload. Je kunt een nieuwe genereren.";
  }
}

async function startCrawl(jobType) {
  if (jobType === "full_site_crawl" && !window.confirm("Volledige crawl starten? Dit controleert de gehele website.")) return;
  const button = jobType === "light_check" ? $("#start-light-check") : $("#start-full-crawl");
  const message = $("#crawl-action-message");
  button.disabled = true; message.classList.remove("error"); message.textContent = "Crawl wordt ingepland…";
  try {
    const job = await api("/api/v1/crawl-jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({website_id: $("#website-select").value, job_type: jobType, settings_snapshot: {}})});
    message.textContent = `${jobType === "light_check" ? "Light check" : "Volledige crawl"} is gestart (${job.id.slice(0, 8)}).`;
    setTimeout(loadOperations, 2000);
  } catch (error) { message.classList.add("error"); message.textContent = error.message; button.disabled = false; }
}

async function generateExcel() {
  const button = $("#generate-excel"); const message = $("#export-action-message");
  button.disabled = true; message.classList.remove("error"); message.textContent = "Excel-export wordt opgebouwd…";
  try {
    await api("/api/v1/exports", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({website_id: $("#website-select").value, export_type: "excel"})});
    message.textContent = "Export gestart; de status wordt automatisch bijgewerkt.";
    await loadOperations();
  } catch (error) { message.classList.add("error"); message.textContent = error.message; button.disabled = false; }
}

function changeLabel(change) {
  const known = {
    new_url: "Nieuwe URL", disappeared_url: "URL verdwenen", status_code_changed: "Statuscode gewijzigd",
    redirect_target_changed: "Redirect gewijzigd", title_changed: "Title gewijzigd", description_changed: "Description gewijzigd",
    h1_changed: "H1 gewijzigd", canonical_changed: "Canonical gewijzigd", robots_changed: "Robots gewijzigd",
    indexability_changed: "Indexeerbaarheid gewijzigd", main_content_changed: "Hoofdcontent gewijzigd",
    internal_links_changed: "Interne links gewijzigd", structured_data_changed: "Structured data gewijzigd",
  };
  return known[change.change_type] || change.change_type.replaceAll("_", " ");
}

async function loadChanges() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  state.changes = [];
  for (let offset = 0; ; offset += 1000) {
    const batch = await api(`/api/v1/websites/${websiteId}/changes?limit=1000&offset=${offset}`);
    state.changes.push(...batch);
    if (batch.length < 1000) break;
  }
  state.changeGroups = groupChanges(state.changes);
  const selected = $("#change-type-filter").value;
  const types = [...new Set(state.changeGroups.flatMap((group) => group.changes.map((change) => change.change_type)))].sort();
  $("#change-type-filter").innerHTML = `<option value="">Alle wijzigingstypen</option>${types.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(changeLabel({change_type: type}))}</option>`).join("")}`;
  if (types.includes(selected)) $("#change-type-filter").value = selected;
  state.changePage = 1;
  renderChanges();
}

function groupChanges(changes) {
  const groups = new Map();
  changes.filter((change) => !change.is_baseline && isMeaningfulChange(change)).forEach((change) => {
    const key = change.current_snapshot_id;
    if (!groups.has(key)) groups.set(key, {id: key, url_id: change.url_id, detected_at: change.detected_at, changes: []});
    groups.get(key).changes.push(change);
  });
  return [...groups.values()].sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at));
}

function changeGroupLabel(group) {
  const labels = [...new Set(group.changes.map(changeLabel))];
  return labels.length === 1 ? labels[0] : `${labels.length} onderdelen gewijzigd`;
}

function renderChanges() {
  const query = $("#change-search").value.trim().toLowerCase();
  const type = $("#change-type-filter").value;
  const days = Number($("#change-period-filter").value || 0);
  const since = days ? Date.now() - days * 86400000 : 0;
  state.changeFiltered = state.changeGroups.filter((group) => {
    const url = state.urls.get(group.url_id) || "";
    const text = `${url} ${group.changes.map((change) => `${changeLabel(change)} ${change.field_name || ""}`).join(" ")}`.toLowerCase();
    return (!type || group.changes.some((change) => change.change_type === type)) && (!since || new Date(group.detected_at).getTime() >= since) && (!query || text.includes(query));
  });
  const pages = Math.max(1, Math.ceil(state.changeFiltered.length / CHANGE_PAGE_SIZE));
  state.changePage = Math.min(state.changePage, pages);
  const start = (state.changePage - 1) * CHANGE_PAGE_SIZE;
  const rows = state.changeFiltered.slice(start, start + CHANGE_PAGE_SIZE);
  $("#changes-website-name").textContent = $("#website-select").selectedOptions[0]?.textContent || "de website";
  $("#change-rows").innerHTML = rows.map((group) => {
    const url = state.urls.get(group.url_id) || "Onbekende URL";
    const parts = [...new Set(group.changes.map(changeLabel))];
    return `<tr><td>${new Date(group.detected_at).toLocaleString("nl-NL")}</td><td><a class="change-url" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a></td><td><span class="change-kind">${escapeHtml(changeGroupLabel(group))}</span></td><td>${parts.length}</td><td><button class="detail-button" data-change-group-id="${group.id}">Bekijk</button></td></tr>`;
  }).join("");
  $("#change-result-count").textContent = `${state.changeFiltered.length} gebeurtenissen`;
  $("#change-page-label").textContent = `Pagina ${state.changePage} van ${pages}`;
  $("#change-previous-page").disabled = state.changePage === 1;
  $("#change-next-page").disabled = state.changePage === pages;
  $("#change-empty").classList.toggle("hidden", rows.length !== 0);
}

function isMeaningfulChange(change) {
  if (["links_hash", "schema_hash"].includes(change.field_name)) return false;
  if (!["title_changed", "description_changed", "h1_changed", "robots_changed"].includes(change.change_type)) return true;
  const normalized = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  return normalized(change.old_value) !== normalized(change.new_value);
}

async function showChangeGroup(groupId) {
  const group = state.changeGroups.find((item) => item.id === groupId);
  if (!group) return;
  const changes = await Promise.all(group.changes.map((change) => api(`/api/v1/changes/${change.id}`)));
  const url = state.urls.get(group.url_id) || "Onbekende URL";
  $("#change-detail-title").textContent = changeGroupLabel(group);
  $("#change-detail-url").textContent = url;
  $("#change-detail-url").href = url;
  $("#change-detail-date").textContent = new Date(group.detected_at).toLocaleString("nl-NL");
  $("#change-detail-summary").textContent = `${changes.length} inhoudelijke onderdelen zijn bij dezelfde meting gewijzigd.`;
  $("#change-detail-summary").classList.remove("hidden");
  $("#change-group-details").innerHTML = changes.map((change) => {
    const details = change.details || {};
    const linkChange = ["links_hash", "internal_links"].includes(change.field_name);
    const oldLabel = linkChange ? "Verwijderde links" : "Oude waarde";
    const newLabel = linkChange ? "Toegevoegde links" : "Nieuwe waarde";
    const oldValue = details.old_display ?? change.old_value ?? "Geen eerdere waarde";
    const newValue = details.new_display ?? change.new_value ?? "Geen nieuwe waarde";
    return `<section class="change-detail-part"><h3>${escapeHtml(changeLabel(change))}</h3>${details.summary ? `<p>${escapeHtml(details.summary)}</p>` : ""}<dl><div><dt>Veld</dt><dd>${escapeHtml(change.field_name || "Niet van toepassing")}</dd></div><div><dt>${oldLabel}</dt><dd class="change-value">${escapeHtml(String(oldValue))}</dd></div><div><dt>${newLabel}</dt><dd class="change-value">${escapeHtml(String(newValue))}</dd></div></dl></section>`;
  }).join("");
  $("#change-dialog").showModal();
}

function applyFilters() {
  const query = $("#search-filter").value.trim().toLowerCase();
  const severity = $("#severity-filter").value;
  const type = $("#type-filter").value;
  const impact = $("#impact-filter").value;
  const status = $("#status-filter").value;
  state.filtered = state.issues.filter((issue) => {
    const statusMatch = status === "all" || (status === "active" ? ACTIVE_STATUSES.has(issue.status) : issue.status === status);
    const searchText = `${issue.title} ${issue.issue_type} ${issueUrlLabel(issue)}`.toLowerCase();
    return statusMatch && (!severity || issue.severity === severity) && (!type || issue.issue_type === type) && (!impact || impactLevel(issue) === impact) && (!query || searchText.includes(query));
  }).sort((a, b) => ({high: 0, medium: 1, low: 2}[a.severity] - {high: 0, medium: 1, low: 2}[b.severity] || impactRank(a) - impactRank(b) || impactVolume(b) - impactVolume(a) || new Date(b.last_detected_at) - new Date(a.last_detected_at)));
}

function renderGroups() {
  const query = $("#search-filter").value.trim().toLowerCase();
  const severity = $("#severity-filter").value;
  const impact = $("#impact-filter").value;
  const status = $("#status-filter").value;
  const counts = new Map();
  state.issues.forEach((issue) => {
    const statusMatch = status === "all" || (status === "active" ? ACTIVE_STATUSES.has(issue.status) : issue.status === status);
    const searchText = `${issue.title} ${issue.issue_type} ${issueUrlLabel(issue)}`.toLowerCase();
    if (statusMatch && (!severity || issue.severity === severity) && (!impact || impactLevel(issue) === impact) && (!query || searchText.includes(query))) counts.set(issue.issue_type, (counts.get(issue.issue_type) || 0) + 1);
  });
  $("#issue-groups").innerHTML = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)
    .map(([type, count]) => `<button data-group-type="${escapeHtml(type)}"><strong>${count}</strong><span>${escapeHtml(type.replaceAll("_", " "))}</span></button>`).join("");
}

function render() {
  applyFilters();
  renderGroups();
  const counts = { high: 0, medium: 0, low: 0, total: state.filtered.length };
  state.filtered.forEach((issue) => { if (counts[issue.severity] !== undefined) counts[issue.severity] += 1; });
  $("#summary").innerHTML = [["total","Actief"],["high","Hoog"],["medium","Middel"],["low","Laag"]]
    .map(([key,label]) => `<article class="card ${key}"><strong>${counts[key]}</strong><span>${label}</span></article>`).join("");
  const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  state.page = Math.min(state.page, pages);
  const start = (state.page - 1) * PAGE_SIZE;
  const rows = state.filtered.slice(start, start + PAGE_SIZE);
  $("#issues").innerHTML = rows.map((issue) => `<tr>
    <td><span class="severity ${issue.severity}">${labels[issue.severity] || issue.severity}</span></td>
    <td><strong>${escapeHtml(issue.title)}</strong>${issueUrlMarkup(issue)}</td>
    <td>${impactMarkup(issue)}</td>
    <td><span class="badge">${labels[issue.status] || issue.status}</span></td>
    <td>${new Date(issue.last_detected_at).toLocaleDateString("nl-NL")}</td>
    <td><button class="detail-button" data-issue-id="${issue.id}">Bekijk</button></td>
  </tr>`).join("");
  $("#result-count").textContent = `${state.filtered.length} resultaten`;
  $("#page-label").textContent = `Pagina ${state.page} van ${pages}`;
  $("#previous-page").disabled = state.page === 1;
  $("#next-page").disabled = state.page === pages;
  $("#empty").classList.toggle("hidden", rows.length !== 0);
}

async function showIssue(issueId) {
  const issue = await api(`/api/v1/issues/${issueId}`);
  if (!issue) return;
  state.selectedIssueId = issueId;
  $("#detail-title").textContent = issue.title;
  const url = issueUrl(issue); $("#detail-url").textContent = url || "Websitebreed issue";
  if (url) $("#detail-url").href = url; else $("#detail-url").removeAttribute("href");
  $("#detail-severity").textContent = labels[issue.severity] || issue.severity;
  $("#detail-status").value = issue.status;
  $("#detail-description").textContent = issue.description;
  $("#detail-action").textContent = issue.recommended_action;
  const impact = issue.organic_impact;
  const impactParts = impact ? [
    impact.clicks !== undefined ? `${impact.clicks} organische klikken` : null,
    impact.impressions !== undefined ? `${impact.impressions} vertoningen` : null,
    impact.average_position !== undefined ? `gemiddelde positie ${impact.average_position}` : null,
    impact.sessions !== undefined ? `${impact.sessions} sessies` : null,
    impact.active_users !== undefined ? `${impact.active_users} actieve gebruikers` : null,
    impact.key_events !== undefined ? `${impact.key_events} belangrijke gebeurtenissen` : null,
  ].filter(Boolean) : [];
  $("#detail-impact").textContent = impactParts.length ? `Impact (28 dagen): ${impactParts.join(" · ")}` : "";
  $("#detail-impact").classList.toggle("hidden", !impact);
  $("#detail-evidence").textContent = Object.entries(issue.evidence).map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`).join("\n") || "Geen aanvullend bewijs opgeslagen.";
  $("#detail-sources").innerHTML = issue.source_urls.map((source) => `<li><a href="${escapeHtml(source)}" target="_blank" rel="noopener">${escapeHtml(source)}</a></li>`).join("");
  $("#source-section").classList.toggle("hidden", issue.source_urls.length === 0);
  $("#issue-dialog").showModal();
}

async function saveIssueStatus() {
  if (!state.selectedIssueId) return;
  const updated = await api(`/api/v1/issues/${state.selectedIssueId}`, {
    method: "PATCH", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({status: $("#detail-status").value}),
  });
  const index = state.issues.findIndex((issue) => issue.id === updated.id);
  if (index >= 0) state.issues[index] = updated;
  $("#issue-dialog").close(); state.selectedIssueId = null; render();
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); $("#login-error").textContent = "";
  const response = await fetch("/ui/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: $("#api-key").value }) });
  if (!response.ok) { $("#login-error").textContent = "De API-key is ongeldig."; return; }
  $("#api-key").value = ""; showApp(); await loadClients(); showView(viewFromHash(), false);
});
$("#logout").addEventListener("click", async () => { await fetch("/ui/logout", { method: "POST" }); showLogin(); });
$("#client-select").addEventListener("change", async () => { await loadWebsites(); if (!$("#integrations-view").classList.contains("hidden")) await loadIntegrations(); });
$("#website-select").addEventListener("change", async () => { await loadIssues(); if (!$("#integrations-view").classList.contains("hidden")) await loadIntegrations(); if (!$("#urls-view").classList.contains("hidden")) renderUrls(); if (!$("#changes-view").classList.contains("hidden")) await loadChanges(); if (!$("#operations-view").classList.contains("hidden")) await loadOperations(); });
for (const selector of ["#severity-filter", "#type-filter", "#impact-filter", "#status-filter"]) $(selector).addEventListener("change", () => { state.page = 1; render(); });
$("#search-filter").addEventListener("input", () => { state.page = 1; render(); });
$("#previous-page").addEventListener("click", () => { state.page -= 1; render(); });
$("#next-page").addEventListener("click", () => { state.page += 1; render(); });
$("#issues").addEventListener("click", (event) => { const button = event.target.closest("[data-issue-id]"); if (button) showIssue(button.dataset.issueId); });
$("#issue-groups").addEventListener("click", (event) => { const button = event.target.closest("[data-group-type]"); if (button) { $("#type-filter").value = button.dataset.groupType; state.page = 1; render(); } });
$("#close-dialog").addEventListener("click", () => $("#issue-dialog").close());
$("#save-status").addEventListener("click", saveIssueStatus);
$("#overview-nav").addEventListener("click", () => showView("overview"));
$("#urls-nav").addEventListener("click", () => showView("urls"));
$("#changes-nav").addEventListener("click", () => showView("changes"));
$("#operations-nav").addEventListener("click", () => showView("operations"));
$("#integrations-nav").addEventListener("click", () => showView("integrations"));
for (const selector of ["#url-status-filter", "#url-index-filter", "#url-depth-filter"]) $(selector).addEventListener("change", () => { state.urlPage = 1; renderUrls(); });
$("#url-search").addEventListener("input", () => { state.urlPage = 1; renderUrls(); });
$("#url-previous-page").addEventListener("click", () => { state.urlPage -= 1; renderUrls(); });
$("#url-next-page").addEventListener("click", () => { state.urlPage += 1; renderUrls(); });
$("#url-rows").addEventListener("click", (event) => { const button = event.target.closest("[data-url-id]"); if (button) showUrl(button.dataset.urlId); });
$("#close-url-dialog").addEventListener("click", () => $("#url-dialog").close());
for (const selector of ["#change-type-filter", "#change-period-filter"]) $(selector).addEventListener("change", () => { state.changePage = 1; renderChanges(); });
$("#change-search").addEventListener("input", () => { state.changePage = 1; renderChanges(); });
$("#change-previous-page").addEventListener("click", () => { state.changePage -= 1; renderChanges(); });
$("#change-next-page").addEventListener("click", () => { state.changePage += 1; renderChanges(); });
$("#change-rows").addEventListener("click", (event) => { const button = event.target.closest("[data-change-group-id]"); if (button) showChangeGroup(button.dataset.changeGroupId); });
$("#close-change-dialog").addEventListener("click", () => $("#change-dialog").close());
$("#start-light-check").addEventListener("click", () => startCrawl("light_check"));
$("#start-full-crawl").addEventListener("click", () => startCrawl("full_site_crawl"));
$("#generate-excel").addEventListener("click", generateExcel);
$("#refresh-operations").addEventListener("click", loadOperations);
$("#current-export-download").addEventListener("click", () => window.setTimeout(loadOperations, 2000));
$("#save-search-console").addEventListener("click", () => saveProperty("search_console", "#search-console-property", "#save-search-console", "#search-console-message"));
$("#save-ga4").addEventListener("click", () => saveProperty("ga4", "#ga4-property", "#save-ga4", "#ga4-message"));
$("#sync-search-console").addEventListener("click", syncSearchConsole);
$("#sync-ga4").addEventListener("click", syncGa4);

loadClients().then(() => {
  showApp();
  const integrationResult = new URLSearchParams(window.location.search).get("integration");
  if (integrationResult) {
    showView("integrations");
    $("#integration-message").textContent = integrationResult === "google-connected" ? "Google-account is succesvol gekoppeld." : "Google-koppeling is niet voltooid. Probeer opnieuw.";
    $("#integration-message").classList.remove("hidden");
    window.history.replaceState({}, "", "/#integraties");
  } else showView(viewFromHash(), false);
}).catch(() => showLogin());
