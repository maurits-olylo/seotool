const $ = (selector) => document.querySelector(selector);
const ACTIVE_STATUSES = new Set(["new", "review", "accepted", "planned", "in_progress", "waiting_for_client"]);
const PAGE_SIZE = 25;
const labels = {
  high: "Hoog", medium: "Middel", low: "Laag", new: "Nieuw", review: "Te beoordelen",
  accepted: "Geaccepteerd", planned: "Gepland", in_progress: "Bezig",
  waiting_for_client: "Wacht op klant", resolved: "Opgelost", verified: "Geverifieerd",
  ignored: "Genegeerd", accepted_risk: "Risico geaccepteerd",
};
const state = { clients: [], websites: [], issues: [], urls: new Map(), filtered: [], page: 1, selectedIssueId: null, googleConnectionId: null };

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
  $("#mapping-website").textContent = $("#website-select").selectedOptions[0]?.textContent || "website";
  $("#property-mapping").classList.remove("hidden");
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
  const integrations = view === "integrations";
  $("#overview-view").classList.toggle("hidden", integrations);
  $("#integrations-view").classList.toggle("hidden", !integrations);
  $("#overview-nav").classList.toggle("nav-active", !integrations);
  $("#integrations-nav").classList.toggle("nav-active", integrations);
  if (integrations) loadIntegrations();
}

async function loadIssues() {
  const websiteId = $("#website-select").value;
  if (!websiteId) { state.issues = []; render(); return; }
  const [issues, urls] = await Promise.all([
    api(`/api/v1/websites/${websiteId}/issues`),
    api(`/api/v1/websites/${websiteId}/urls?limit=1000`),
  ]);
  state.issues = issues;
  state.urls = new Map(urls.map((url) => [url.id, url.normalized_url]));
  const types = [...new Set(issues.map((issue) => issue.issue_type))].sort();
  $("#type-filter").innerHTML = `<option value="">Alle issue-types</option>${types.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`).join("")}`;
  state.page = 1;
  render();
}

function applyFilters() {
  const query = $("#search-filter").value.trim().toLowerCase();
  const severity = $("#severity-filter").value;
  const type = $("#type-filter").value;
  const status = $("#status-filter").value;
  state.filtered = state.issues.filter((issue) => {
    const statusMatch = status === "all" || (status === "active" ? ACTIVE_STATUSES.has(issue.status) : issue.status === status);
    const searchText = `${issue.title} ${issue.issue_type} ${issueUrlLabel(issue)}`.toLowerCase();
    return statusMatch && (!severity || issue.severity === severity) && (!type || issue.issue_type === type) && (!query || searchText.includes(query));
  }).sort((a, b) => ({high: 0, medium: 1, low: 2}[a.severity] - {high: 0, medium: 1, low: 2}[b.severity] || new Date(b.last_detected_at) - new Date(a.last_detected_at)));
}

function renderGroups() {
  const query = $("#search-filter").value.trim().toLowerCase();
  const severity = $("#severity-filter").value;
  const status = $("#status-filter").value;
  const counts = new Map();
  state.issues.forEach((issue) => {
    const statusMatch = status === "all" || (status === "active" ? ACTIVE_STATUSES.has(issue.status) : issue.status === status);
    const searchText = `${issue.title} ${issue.issue_type} ${issueUrlLabel(issue)}`.toLowerCase();
    if (statusMatch && (!severity || issue.severity === severity) && (!query || searchText.includes(query))) counts.set(issue.issue_type, (counts.get(issue.issue_type) || 0) + 1);
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
$("#website-select").addEventListener("change", async () => { await loadIssues(); if (!$("#integrations-view").classList.contains("hidden")) await loadIntegrations(); });
for (const selector of ["#severity-filter", "#type-filter", "#status-filter"]) $(selector).addEventListener("change", () => { state.page = 1; render(); });
$("#search-filter").addEventListener("input", () => { state.page = 1; render(); });
$("#previous-page").addEventListener("click", () => { state.page -= 1; render(); });
$("#next-page").addEventListener("click", () => { state.page += 1; render(); });
$("#issues").addEventListener("click", (event) => { const button = event.target.closest("[data-issue-id]"); if (button) showIssue(button.dataset.issueId); });
$("#issue-groups").addEventListener("click", (event) => { const button = event.target.closest("[data-group-type]"); if (button) { $("#type-filter").value = button.dataset.groupType; state.page = 1; render(); } });
$("#close-dialog").addEventListener("click", () => $("#issue-dialog").close());
$("#save-status").addEventListener("click", saveIssueStatus);
$("#overview-nav").addEventListener("click", () => showView("overview"));
$("#integrations-nav").addEventListener("click", () => showView("integrations"));
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
