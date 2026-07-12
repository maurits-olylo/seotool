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
};
const state = { clients: [], websites: [], issues: [], changes: [], urls: new Map(), urlRecords: [], filtered: [], urlFiltered: [], changeFiltered: [], page: 1, urlPage: 1, changePage: 1, selectedIssueId: null, googleConnectionId: null };

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (response.status === 401) { showLogin(); throw new Error("Niet aangemeld"); }
  if (!response.ok) throw new Error(`API-fout ${response.status}`);
  return response.status === 204 ? null : response.json();
}

function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
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

function showView(view) {
  for (const name of ["overview", "urls", "changes", "integrations"]) {
    $(`#${name}-view`).classList.toggle("hidden", name !== view);
    $(`#${name}-nav`).classList.toggle("nav-active", name === view);
  }
  if (view === "integrations") loadIntegrations();
  if (view === "urls") renderUrls();
  if (view === "changes") loadChanges();
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
  const selected = $("#change-type-filter").value;
  const types = [...new Set(state.changes.map((change) => change.change_type))].sort();
  $("#change-type-filter").innerHTML = `<option value="">Alle wijzigingstypen</option>${types.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(changeLabel({change_type: type}))}</option>`).join("")}`;
  if (types.includes(selected)) $("#change-type-filter").value = selected;
  state.changePage = 1;
  renderChanges();
}

function renderChanges() {
  const query = $("#change-search").value.trim().toLowerCase();
  const type = $("#change-type-filter").value;
  const days = Number($("#change-period-filter").value || 0);
  const since = days ? Date.now() - days * 86400000 : 0;
  state.changeFiltered = state.changes.filter((change) => {
    const url = state.urls.get(change.url_id) || "";
    const text = `${url} ${changeLabel(change)} ${change.field_name || ""}`.toLowerCase();
    return isMeaningfulChange(change) && (!type || change.change_type === type) && (!since || new Date(change.detected_at).getTime() >= since) && (!query || text.includes(query));
  });
  const pages = Math.max(1, Math.ceil(state.changeFiltered.length / CHANGE_PAGE_SIZE));
  state.changePage = Math.min(state.changePage, pages);
  const start = (state.changePage - 1) * CHANGE_PAGE_SIZE;
  const rows = state.changeFiltered.slice(start, start + CHANGE_PAGE_SIZE);
  $("#changes-website-name").textContent = $("#website-select").selectedOptions[0]?.textContent || "de website";
  $("#change-rows").innerHTML = rows.map((change) => {
    const url = state.urls.get(change.url_id) || "Onbekende URL";
    return `<tr><td>${new Date(change.detected_at).toLocaleString("nl-NL")}</td><td><a class="change-url" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a></td><td><span class="change-kind">${escapeHtml(changeLabel(change))}</span></td><td>${escapeHtml(change.field_name || "—")}</td><td><button class="detail-button" data-change-id="${change.id}">Bekijk</button></td></tr>`;
  }).join("");
  $("#change-result-count").textContent = `${state.changeFiltered.length} wijzigingen`;
  $("#change-page-label").textContent = `Pagina ${state.changePage} van ${pages}`;
  $("#change-previous-page").disabled = state.changePage === 1;
  $("#change-next-page").disabled = state.changePage === pages;
  $("#change-empty").classList.toggle("hidden", rows.length !== 0);
}

function isMeaningfulChange(change) {
  if (!["title_changed", "description_changed", "h1_changed", "robots_changed"].includes(change.change_type)) return true;
  const normalized = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  return normalized(change.old_value) !== normalized(change.new_value);
}

async function showChange(changeId) {
  const change = await api(`/api/v1/changes/${changeId}`);
  if (!change) return;
  const url = state.urls.get(change.url_id) || "Onbekende URL";
  $("#change-detail-title").textContent = changeLabel(change);
  $("#change-detail-url").textContent = url;
  $("#change-detail-url").href = url;
  $("#change-detail-date").textContent = new Date(change.detected_at).toLocaleString("nl-NL");
  $("#change-detail-field").textContent = change.field_name || "Niet van toepassing";
  const details = change.details || {};
  $("#change-detail-summary").textContent = details.summary || "";
  $("#change-detail-summary").classList.toggle("hidden", !details.summary);
  const linkChange = change.field_name === "links_hash";
  $("#change-old-label").textContent = linkChange ? "Verwijderde links" : "Oude waarde";
  $("#change-new-label").textContent = linkChange ? "Toegevoegde links" : "Nieuwe waarde";
  $("#change-detail-old").textContent = details.old_display ?? change.old_value ?? "Geen eerdere waarde";
  $("#change-detail-new").textContent = details.new_display ?? change.new_value ?? "Geen nieuwe waarde";
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
  $("#api-key").value = ""; showApp(); await loadClients();
});
$("#logout").addEventListener("click", async () => { await fetch("/ui/logout", { method: "POST" }); showLogin(); });
$("#client-select").addEventListener("change", async () => { await loadWebsites(); if (!$("#integrations-view").classList.contains("hidden")) await loadIntegrations(); });
$("#website-select").addEventListener("change", async () => { await loadIssues(); if (!$("#integrations-view").classList.contains("hidden")) await loadIntegrations(); if (!$("#urls-view").classList.contains("hidden")) renderUrls(); if (!$("#changes-view").classList.contains("hidden")) await loadChanges(); });
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
$("#change-rows").addEventListener("click", (event) => { const button = event.target.closest("[data-change-id]"); if (button) showChange(button.dataset.changeId); });
$("#close-change-dialog").addEventListener("click", () => $("#change-dialog").close());
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
    window.history.replaceState({}, "", "/");
  }
}).catch(() => showLogin());
