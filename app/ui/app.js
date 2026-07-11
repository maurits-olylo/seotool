const $ = (selector) => document.querySelector(selector);
const state = { clients: [], websites: [], issues: [] };

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (response.status === 401) { showLogin(); throw new Error("Niet aangemeld"); }
  if (!response.ok) throw new Error(`API-fout ${response.status}`);
  return response.status === 204 ? null : response.json();
}

function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); }
function option(item) { return `<option value="${item.id}">${escapeHtml(item.name)}</option>`; }
function escapeHtml(value = "") { const node = document.createElement("span"); node.textContent = value; return node.innerHTML; }

async function loadClients() {
  state.clients = await api("/api/v1/clients");
  $("#client-select").innerHTML = state.clients.map(option).join("");
  await loadWebsites();
}

async function loadWebsites() {
  const clientId = $("#client-select").value;
  if (!clientId) { state.websites = []; $("#website-select").innerHTML = ""; state.issues = []; render(); return; }
  state.websites = await api(`/api/v1/websites?client_id=${clientId}`);
  $("#website-select").innerHTML = state.websites.map(option).join("");
  await loadIssues();
}

async function loadIssues() {
  const websiteId = $("#website-select").value;
  if (!websiteId) { state.issues = []; render(); return; }
  const status = $("#status-filter").value;
  state.issues = await api(`/api/v1/websites/${websiteId}/issues${status ? `?status=${status}` : ""}`);
  render();
}

function render() {
  const counts = { high: 0, medium: 0, low: 0, total: state.issues.length };
  state.issues.forEach((issue) => { if (counts[issue.severity] !== undefined) counts[issue.severity] += 1; });
  $("#summary").innerHTML = [["total","Totaal"],["high","Hoog"],["medium","Middel"],["low","Laag"]]
    .map(([key,label]) => `<article class="card"><strong>${counts[key]}</strong><span>${label}</span></article>`).join("");
  $("#issues").innerHTML = state.issues.map((issue) => `<tr>
    <td class="${issue.severity}">${escapeHtml(issue.severity)}</td>
    <td>${escapeHtml(issue.title)}<br><small>${escapeHtml(issue.issue_type)}</small></td>
    <td><span class="badge">${escapeHtml(issue.status)}</span></td>
    <td>${new Date(issue.last_detected_at).toLocaleDateString("nl-NL")}</td>
  </tr>`).join("");
  $("#empty").classList.toggle("hidden", state.issues.length !== 0);
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
$("#status-filter").addEventListener("change", loadIssues);

loadClients().then(showApp).catch(() => showLogin());
