const $ = (selector) => document.querySelector(selector);
const ACTIVE_STATUSES = new Set(["new", "review", "accepted", "planned", "in_progress", "waiting_for_client"]);
const PAGE_SIZE = 25;
const labels = {
  high: "Hoog", medium: "Middel", low: "Laag", new: "Nieuw", review: "Te beoordelen",
  accepted: "Geaccepteerd", planned: "Gepland", in_progress: "Bezig",
  waiting_for_client: "Wacht op klant", resolved: "Opgelost", verified: "Geverifieerd",
  ignored: "Genegeerd", accepted_risk: "Risico geaccepteerd",
};
const state = { clients: [], websites: [], issues: [], urls: new Map(), filtered: [], page: 1 };

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

function render() {
  applyFilters();
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

function showIssue(issueId) {
  const issue = state.issues.find((item) => item.id === issueId);
  if (!issue) return;
  $("#detail-title").textContent = issue.title;
  const url = issueUrl(issue); $("#detail-url").textContent = url || "Websitebreed issue";
  if (url) $("#detail-url").href = url; else $("#detail-url").removeAttribute("href");
  $("#detail-severity").textContent = labels[issue.severity] || issue.severity;
  $("#detail-status").textContent = labels[issue.status] || issue.status;
  $("#detail-description").textContent = issue.description;
  $("#detail-action").textContent = issue.recommended_action;
  $("#issue-dialog").showModal();
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); $("#login-error").textContent = "";
  const response = await fetch("/ui/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: $("#api-key").value }) });
  if (!response.ok) { $("#login-error").textContent = "De API-key is ongeldig."; return; }
  $("#api-key").value = ""; showApp(); await loadClients();
});
$("#logout").addEventListener("click", async () => { await fetch("/ui/logout", { method: "POST" }); showLogin(); });
$("#client-select").addEventListener("change", loadWebsites);
$("#website-select").addEventListener("change", loadIssues);
for (const selector of ["#severity-filter", "#type-filter", "#status-filter"]) $(selector).addEventListener("change", () => { state.page = 1; render(); });
$("#search-filter").addEventListener("input", () => { state.page = 1; render(); });
$("#previous-page").addEventListener("click", () => { state.page -= 1; render(); });
$("#next-page").addEventListener("click", () => { state.page += 1; render(); });
$("#issues").addEventListener("click", (event) => { const button = event.target.closest("[data-issue-id]"); if (button) showIssue(button.dataset.issueId); });
$("#close-dialog").addEventListener("click", () => $("#issue-dialog").close());

loadClients().then(showApp).catch(() => showLogin());
