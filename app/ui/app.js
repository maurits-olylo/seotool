const $ = (selector) => document.querySelector(selector);
const ACTIVE_STATUSES = new Set(["new", "review", "accepted", "planned", "in_progress", "waiting_for_client"]);
const PAGE_SIZE = 25;
const URL_PAGE_SIZE = 30;
const CHANGE_PAGE_SIZE = 30;
const TASK_TRANSITIONS = {
  open: ["planned", "in_progress", "closed"],
  planned: ["in_progress", "waiting_for_input", "closed"],
  in_progress: ["waiting_for_input", "implemented", "closed"],
  waiting_for_input: ["planned", "in_progress", "closed"],
  implemented: ["in_progress", "closed"],
  closed: ["open"],
};
const taskStatusLabels = {open: "Open", planned: "Gepland", in_progress: "In uitvoering", waiting_for_input: "Wacht op input", implemented: "Uitgevoerd", closed: "Afgesloten"};
const taskRoleLabels = {content: "Content", development: "Development", seo_analytics: "SEO & analytics", project_management: "Projectmanagement", content_editor: "Contentredactie", ux_ui_design: "UX/UI-design", web_development: "Webdevelopment", seo_specialist: "SEO-specialist", analytics_specialist: "Analytics-specialist", website_management: "Websitebeheer"};
const closeReasonLabels = {verified: "Geverifieerd", manually_accepted: "Handmatig akkoord", rejected: "Afgewezen", superseded: "Vervangen door andere taak", no_longer_relevant: "Niet meer relevant"};
const labels = {
  critical: "Kritiek", high: "Hoog", normal: "Normaal", medium: "Middel", low: "Laag", new: "Nieuw", review: "Te beoordelen",
  accepted: "Geaccepteerd", planned: "Gepland", in_progress: "Bezig",
  waiting_for_client: "Wacht op klant", resolved: "Opgelost", verified: "Geverifieerd",
  ignored: "Genegeerd", accepted_risk: "Risico geaccepteerd",
  waiting_for_capacity: "Wacht op capaciteit", pending: "In wachtrij", running: "Bezig", succeeded: "Geslaagd",
  partially_succeeded: "Deels geslaagd", failed: "Mislukt", cancelled: "Geannuleerd",
  pause_requested: "Pauze wordt voorbereid", paused: "Gepauzeerd",
  cancel_requested: "Stop wordt voorbereid", connected: "Gekoppeld", error: "Fout",
};
const state = { currentUser: null, currentView: "dashboard", clients: [], websites: [], organizationWebsites: [], websiteOnboarding: null, verificationFileContent: null, issues: [], suppressions: [], selectedIssueIds: new Set(), selectedSuppressionIds: new Set(), changes: [], changeGroups: [], changesRequestId: 0, jobListings: [], jobSummary: {}, consultantInsights: null, insightDays: 28, contentAnalysis: null, contentAnalysisDays: 28, contentAnalysisTab: "overview", contentAnalysisPage: 1, questionScopes: null, externalEvidenceRequests: new Map(), effectEvaluations: [], crawlRuns: [], showCrawlArchive: false, activeCrawlJob: null, exports: [], systemStatus: null, operationsLoading: false, operationsRequestId: 0, integrationHealth: {connections: [], mappings: []}, urls: new Map(), urlRecords: [], urlCoverage: null, filtered: [], urlFiltered: [], changeFiltered: [], vacancyFiltered: [], page: 1, urlPage: 1, changePage: 1, selectedIssueId: null, selectedInspectionSnapshotId: null, selectedRecommendationTask: null, recommendationFeedback: [], recommendationDefinitions: null, recommendationTasks: [], taskNotifications: [], taskMembers: [], googleConnectionId: null, bingConnectionId: null, matomoConnectionId: null, clientReport: null, reportPeriod: "month", reportSnapshots: [], selectedReportSnapshotId: null };
const VIEW_HASHES = {dashboard: "overzicht", insights: "inzichten", opportunities: "kansen", tasks: "acties", actions: "metingen/signalen", urls: "metingen/urls", changes: "metingen/wijzigingen", contentAnalysis: "metingen/content", vacancies: "metingen/vacatures", reports: "rapportages", operations: "crawls-exports", clients: "instellingen/klanten-websites", team: "instellingen/team-toegang", integrations: "instellingen/integraties"};
const LEGACY_HASHES = {rapportage: "reports", urls: "urls", wijzigingen: "changes", inzichten: "insights", vacatures: "vacancies", beheer: "operations", organisatie: "clients", integraties: "integrations", acties: "actions", taken: "tasks", "analyse/acties": "actions", "analyse/urls": "urls", "analyse/wijzigingen": "changes", "analyse/inzichten": "insights", "analyse/content": "contentAnalysis", "analyse/vacatures": "vacancies"};
const ANALYSIS_VIEWS = new Set(["actions", "urls", "changes", "contentAnalysis", "vacancies"]);
const SETTINGS_VIEWS = new Set(["clients", "team", "integrations"]);
const CLIENT_STORAGE_KEY = "seo-monitor-client-id";
const WEBSITE_STORAGE_KEY = "seo-monitor-website-id";
const ONBOARDING_STORAGE_KEY = "seo-monitor-website-onboarding-id";
let onboardingPollTimer = null;
let platformDetectionLoading = false;
let onboardingEditingDetails = false;
let operationsPollTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (response.status === 401) { showLogin(); throw new Error("Niet aangemeld"); }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item?.msg || String(item)).join(" · ")
      : typeof payload.detail === "object" && payload.detail
        ? JSON.stringify(payload.detail)
        : payload.detail;
    throw new Error(detail || `API-fout ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

function showLogin() { stopOperationsPolling(); window.location.assign("/login"); }
function showApp() { $("#app").classList.remove("hidden"); }
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

function renderClientReport() {
  const report = state.clientReport;
  if (!report) { $("#report-conclusion").textContent = "Rapportage wordt geladen…"; return; }
  const current = report.current || {};
  const comparisons = report.comparisons || {};
  const qualifiedEvents = report.qualified_key_events || {};
  const signal = report.primary_metric || (qualifiedEvents.configured && current.key_events ? "key_events" : current.sessions ? "sessions" : "clicks");
  const signalLabels = {key_events:"gekwalificeerde organische leads",sessions:"organische sessies",clicks:"organische klikken"};
  const change = comparisons[signal];
  const currentValue = Number(current[signal] || 0).toLocaleString("nl-NL");
  const previousValue = Number(report.previous?.[signal] || 0).toLocaleString("nl-NL");
  const label = signalLabels[signal];
  $("#report-conclusion").textContent = change === null || change === undefined
    ? `${currentValue} ${label} gemeten`
    : `${label[0].toUpperCase()}${label.slice(1)} ${change >= 0 ? "stegen" : "daalden"} ${Math.abs(change)}%`;
  $("#report-explanation").textContent = change === null || change === undefined
    ? `Er is nog geen volledige voorafgaande periode om deze ${label} eerlijk te vergelijken.`
    : `Van ${previousValue} naar ${currentValue} ${label}, vergeleken met ${report.comparison_context || "de vergelijkbare periode"}.`;
  $("#report-date").textContent = `${new Date(report.start_date).toLocaleDateString("nl-NL")} – ${new Date(report.end_date).toLocaleDateString("nl-NL")}`;
  $("#report-coverage").textContent = report.coverage?.from ? `Data beschikbaar vanaf ${new Date(report.coverage.from).toLocaleDateString("nl-NL")}` : "Nog geen GSC/GA4-data beschikbaar";
  $("#report-comparison").textContent = report.comparison_context ? `Vergelijking: ${report.comparison_context}` : "";
  const metricDefinitions = [["clicks","Organische klikken"],["impressions","Vertoningen in Google"],["sessions","Organische sessies"],["key_events","Gekwalificeerde leads"]];
  $("#report-metrics").innerHTML = metricDefinitions.map(([key, label]) => {
    const delta = comparisons[key];
    const deltaLabel = key === "key_events" && !qualifiedEvents.configured ? "Kies conversies in Integraties" : delta === null || delta === undefined ? "Geen vergelijkingsdata" : `${delta >= 0 ? "+" : ""}${delta}% t.o.v. vorige periode`;
    return `<article class="report-metric"><strong>${key === "key_events" && !qualifiedEvents.configured ? "—" : Number(current[key] || 0).toLocaleString("nl-NL")}</strong><span>${label}</span><small class="${delta > 0 ? "positive" : delta < 0 ? "negative" : ""}">${deltaLabel}</small></article>`;
  }).join("");
  const availablePeriods = new Set(report.available_periods || []);
  $("#report-periods").querySelectorAll("button").forEach((button) => {
    const available = availablePeriods.has(button.dataset.reportPeriod) || (!availablePeriods.size && button.dataset.reportPeriod === "month");
    button.classList.toggle("hidden", !available);
    button.setAttribute("aria-pressed", String(button.dataset.reportPeriod === state.reportPeriod));
  });
  const conversionEvents = qualifiedEvents.events || [];
  $("#report-conversions").innerHTML = qualifiedEvents.configured
    ? `<div class="panel-head"><div><span class="eyebrow">CONVERSIES</span><h2>Gekwalificeerde leads uit organic</h2></div></div><div class="conversion-breakdown">${conversionEvents.map((event) => `<article><strong>${Number(event.key_events).toLocaleString("nl-NL")}</strong><span>${escapeHtml(event.event_name)}</span></article>`).join("") || `<p class="report-empty">Geen gekwalificeerde leads in deze periode.</p>`}</div>`
    : `<div class="panel-head"><div><span class="eyebrow">CONVERSIES</span><h2>Gekwalificeerde leads nog niet ingesteld</h2><p>Selecteer als admin de relevante GA4-events bij Integraties.</p></div></div>`;
  renderReportInsights(report, signal);

  const months = (report.monthly || [])
    .filter((month) => month.month !== String(report.end_date || "").slice(0, 7))
    .slice(-12);
  const chartMetric = months.some((month) => month.sessions) ? "sessions" : "clicks";
  const trendValues = months.map((month) => Number(month[chartMetric] || 0));
  const trendMax = trendValues.length ? Math.ceil(Math.max(...trendValues) / 1000) * 1000 : 0;
  $("#report-trend-label").textContent = `${chartMetric === "sessions" ? "Organische sessies" : "Organische klikken"} · 0–${trendMax.toLocaleString("nl-NL")} · volledige maanden`;
  $("#report-chart").innerHTML = renderTrendChart(months, chartMetric);

  const activities = report.work_completed?.activities || [];
  $("#report-completed").innerHTML = activities.length
    ? `${activities.map((activity) => `<article class="report-list-item"><strong>${escapeHtml(activity.summary)}</strong><p>${escapeHtml(activity.actor || "Systeem")} · ${new Date(activity.occurred_at).toLocaleDateString("nl-NL")}</p></article>`).join("")}<article class="report-work-summary"><strong>${report.work_completed?.technically_verified || 0}</strong><span>technische issues geverifieerd of opgelost</span></article>`
    : `<p class="report-empty">Nog geen handmatig werk gelogd in deze periode.</p><article class="report-work-summary"><strong>${report.work_completed?.technically_verified || 0}</strong><span>technische issues geverifieerd of opgelost</span></article>`;
  $("#report-planned").innerHTML = renderReportIssues(report.planned, "Er staan nog geen acties met status gepland of bezig.");
  $("#report-new-issues").innerHTML = renderReportIssues(report.new_issues, "Geen nieuwe aandachtspunten in deze periode.");
}

function renderReportInsights(report, signal) {
  const current = report.current || {}; const comparisons = report.comparisons || {};
  const signalName = {key_events:"gekwalificeerde leads", sessions:"organische sessies", clicks:"organische klikken"}[signal];
  const delta = comparisons[signal];
  const performance = delta === null || delta === undefined
    ? `${Number(current[signal] || 0).toLocaleString("nl-NL")} ${signalName}; een eerlijke vergelijking is nog niet beschikbaar.`
    : `${Number(report.previous?.[signal] || 0).toLocaleString("nl-NL")} → ${Number(current[signal] || 0).toLocaleString("nl-NL")} ${signalName} (${delta >= 0 ? "+" : ""}${delta}%).`;
  const clickDelta = comparisons.clicks;
  const visibility = clickDelta === null || clickDelta === undefined
    ? `${Number(current.impressions || 0).toLocaleString("nl-NL")} vertoningen in Google.`
    : `${Number(report.previous?.clicks || 0).toLocaleString("nl-NL")} → ${Number(current.clicks || 0).toLocaleString("nl-NL")} organische klikken (${clickDelta >= 0 ? "+" : ""}${clickDelta}%).`;
  const newIssues = (report.new_issues || []).length;
  const planned = (report.planned || []).length;
  const resolved = report.work_completed?.technically_verified || 0;
  const action = newIssues ? `${newIssues} nieuwe aandachtspunten; ${resolved} issues opgelost of geverifieerd.` : planned ? `${planned} acties gepland of in uitvoering; ${resolved} issues opgelost of geverifieerd.` : `${resolved} issues opgelost of geverifieerd; geen nieuwe technische aandachtspunten.`;
  $("#report-insights").innerHTML = [["PRESTATIE", performance], ["ZICHTBAARHEID", visibility], ["ACTIE", action]]
    .map(([label, text]) => `<article><span>${label}</span><p>${text}</p></article>`).join("");
}

function renderSearchInsights(insights) {
  const panel = $("#report-search-insights");
  const header = '<div class="panel-head"><div><span class="eyebrow">ZOEKZICHTBAARHEID</span><h2>Zoekwoordkansen</h2>';
  if (!insights.length) {
    panel.innerHTML = header + '<p>Nog geen duidelijke kansen binnen de beschikbare GSC-querydata.</p></div></div>';
    return;
  }
  const labels = {cannibalization: "Meerdere pagina’s", ctr_opportunity: "CTR-kans", declining_query: "Daling"};
  const items = insights.map((insight) => {
    const link = insight.url
      ? '<a href="' + escapeHtml(insight.url) + '" target="_blank" rel="noopener">Bekijk pagina</a>'
      : "";
    return '<article class="report-list-item"><span class="badge">' +
      escapeHtml(labels[insight.type] || "Kans") + '</span><strong>' +
      escapeHtml(insight.title) + '</strong><p>' + escapeHtml(insight.description) +
      '</p>' + link + '</article>';
  }).join("");
  panel.innerHTML = header + '<p>Gebaseerd op beschikbare Search Console-querydata.</p></div></div>' +
    '<div class="report-list report-list-grid">' + items + '</div>';
}

function renderTrendChart(months, metric) {
  if (months.length < 2) return `<p class="report-empty">Nog onvoldoende volledige maanden voor een betrouwbare maandtrend.</p>`;
  const width = 1000; const height = 245; const padding = {left: 46, right: 24, top: 28, bottom: 42};
  const values = months.map((month) => Number(month[metric] || 0));
  const max = Math.max(...values);
  const axisMax = Math.max(1, Math.ceil(max / 1000) * 1000);
  const plotWidth = width - padding.left - padding.right; const plotHeight = height - padding.top - padding.bottom;
  const x = (index) => padding.left + (plotWidth * index / (months.length - 1));
  const y = (value) => padding.top + ((axisMax - value) / axisMax * plotHeight);
  const points = values.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const grid = [0, 0.5, 1].map((ratio) => { const lineY = padding.top + plotHeight * ratio; const label = Math.round(axisMax * (1 - ratio)).toLocaleString("nl-NL"); return `<line x1="${padding.left}" y1="${lineY}" x2="${width - padding.right}" y2="${lineY}"/><text x="0" y="${lineY + 4}">${label}</text>`; }).join("");
  const dots = values.map((value, index) => `<g><title>${months[index].month}: ${value.toLocaleString("nl-NL")}</title><circle cx="${x(index)}" cy="${y(value)}" r="4" fill="#fff" stroke="#124b3b" stroke-width="3"/><text x="${x(index)}" y="${height - 12}" text-anchor="middle">${months[index].month.slice(5)}/${months[index].month.slice(2,4)}</text></g>`).join("");
  return `<svg class="report-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Maandelijkse organische prestaties"><g class="report-chart-grid">${grid}</g><polyline class="report-chart-line" points="${points}" fill="none" stroke="#124b3b" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>${dots}</svg>`;
}

function renderReportIssues(issues = [], emptyText) {
  if (!issues.length) return `<p class="report-empty">${emptyText}</p>`;
  return issues.map((issue) => `<article class="report-list-item"><div><span class="severity ${issue.severity}">${labels[issue.severity] || issue.severity}</span><span class="badge">${labels[issue.status] || issue.status}</span></div><strong>${escapeHtml(issue.title)}</strong><p>${escapeHtml(issue.recommended_action)}</p></article>`).join("");
}

function renderIntegrationWarning() {
  const panel = $("#integration-warning");
  const providerLabels = {google: "Google (GSC en GA4)", bing: "Bing Webmaster Tools", matomo: "Matomo"};
  const serviceLabels = {search_console: "Google Search Console", ga4: "Google Analytics 4", bing_webmaster: "Bing Webmaster Tools", matomo: "Matomo"};
  const connectionErrors = (state.integrationHealth.connections || []).filter((item) => item.status === "error");
  const mappingErrors = (state.integrationHealth.mappings || []).filter((item) => item.status === "error");
  const warnings = [
    ...connectionErrors.map((item) => ({name: providerLabels[item.provider] || item.provider, detail: item.last_error})),
    ...mappingErrors.map((item) => ({name: serviceLabels[item.service] || item.service, detail: item.settings?.last_error})),
  ];
  panel.classList.toggle("hidden", warnings.length === 0);
  if (!warnings.length) return;
  $("#integration-warning-title").textContent = `${warnings.map((item) => item.name).join(" en ")} ${warnings.length === 1 ? "heeft" : "hebben"} aandacht nodig`;
  $("#integration-warning-detail").textContent = warnings.map((item) => item.detail || "De laatste synchronisatie is mislukt.").join(" · ");
}

async function loadClientReport() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  state.clientReport = state.selectedReportSnapshotId
    ? await api(`/api/v1/websites/${websiteId}/monthly-reports/${state.selectedReportSnapshotId}`)
    : await api(`/api/v1/websites/${websiteId}/client-report?period=${state.reportPeriod}`);
  if (!state.selectedReportSnapshotId) {
    const availablePeriods = state.clientReport.available_periods || [];
    if (availablePeriods.length && !availablePeriods.includes(state.reportPeriod)) {
      state.reportPeriod = availablePeriods.includes("month") ? "month" : availablePeriods[0] || "month";
      return loadClientReport();
    }
  }
  renderClientReport();
}

async function loadReportSnapshots() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  state.reportSnapshots = await api(`/api/v1/websites/${websiteId}/monthly-reports`);
  const byYear = state.reportSnapshots.reduce((groups, snapshot) => {
    const year = snapshot.period_start.slice(0, 4); (groups[year] ||= []).push(snapshot); return groups;
  }, {});
  const monthName = (value) => new Intl.DateTimeFormat("nl-NL", {month:"long", year:"numeric"}).format(new Date(`${value}T12:00:00`));
  $("#report-archive-list").innerHTML = Object.entries(byYear).map(([year, snapshots]) => `<details><summary>${year}</summary>${snapshots.map((snapshot) => `<button type="button" data-report-snapshot="${snapshot.id}" class="${snapshot.id === state.selectedReportSnapshotId ? "active" : ""}">${escapeHtml(monthName(snapshot.period_start))}</button>`).join("")}</details>`).join("") || `<p>Het eerste maandrapport verschijnt na de eerste volledige maand.</p>`;
}
function issueUrlMarkup(issue) {
  const url = issueUrl(issue);
  return url ? `<a class="url" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>` : `<span class="url">Websitebreed issue</span>`;
}

function applyRolePermissions() {
  const canAdmin = ["superuser", "admin"].includes(state.currentUser?.role);
  const isClient = state.currentUser?.role === "client";
  $("#integrations-nav").classList.toggle("hidden", !canAdmin);
  $("#settings-nav").classList.toggle("hidden", !canAdmin);
  $("#clients-nav").classList.toggle("hidden", !canAdmin);
  $("#team-nav").classList.toggle("hidden", !canAdmin);
  $("#crawl-operation-card").classList.toggle("hidden", !canAdmin);
  $("#dashboard-nav").classList.toggle("hidden", isClient);
  $("#analysis-nav").classList.toggle("hidden", isClient);
  $("#tasks-nav").classList.toggle("hidden", isClient);
  $(".notification-area").classList.toggle("hidden", isClient);
  for (const selector of ["#actions-nav", "#urls-nav", "#changes-nav", "#insights-nav", "#vacancies-nav", "#operations-nav"]) $(selector).classList.toggle("hidden", isClient);
  $("#detail-status").classList.toggle("hidden", isClient);
  $("#save-status").classList.toggle("hidden", isClient);
  $("#wont-fix-issue").classList.toggle("hidden", isClient);
  $("#client-status-label").classList.toggle("hidden", !isClient);
  $("#invitation-role").querySelector('option[value="admin"]').disabled = state.currentUser?.role !== "superuser";
  $("#current-user").textContent = state.currentUser?.email || "Technische toegang";
  $(".profile-avatar").textContent = (state.currentUser?.email || "M").slice(0, 1).toUpperCase();
  if (isClient && !["#rapportages", "#rapportage"].includes(window.location.hash)) window.location.hash = "#rapportages";
  else if (!canAdmin && (window.location.hash.includes("instellingen") || ["#organisatie", "#integraties"].includes(window.location.hash))) window.location.hash = "#overzicht";
}

function updateReportSelectors() {
  const isClient = state.currentUser?.role === "client";
  $("#context-bar").querySelector("label:first-child").classList.toggle("hidden", isClient);
}

async function loadOrganization() {
  const options = state.clients.map(option).join("");
  $("#new-website-client").innerHTML = options;
  $("#website-onboarding-client").innerHTML = options;
  $("#invitation-client").innerHTML = options;
  if ($("#client-select").value) {
    $("#new-website-client").value = $("#client-select").value;
    $("#website-onboarding-client").value = $("#client-select").value;
    $("#invitation-client").value = $("#client-select").value;
  }
  state.organizationWebsites = await api("/api/v1/websites");
  renderClientDirectory();
  await loadMembers();
  await resumeWebsiteOnboarding();
}

function renderClientDirectory() {
  const query = $("#client-directory-search").value.trim().toLowerCase();
  const websitesByClient = state.organizationWebsites.reduce((groups, website) => {
    (groups[website.client_id] ||= []).push(website); return groups;
  }, {});
  const clients = state.clients.filter((client) => {
    const websites = websitesByClient[client.id] || [];
    const searchable = `${client.name} ${client.internal_reference || ""} ${websites.map((website) => `${website.name} ${website.base_url}`).join(" ")}`.toLowerCase();
    return !query || searchable.includes(query);
  });
  $("#client-rows").innerHTML = clients.map((client) => {
    const websites = websitesByClient[client.id] || [];
    const websiteMarkup = websites.length
      ? websites.map((website) => `<span><strong>${escapeHtml(website.name)}</strong><small>${escapeHtml(website.base_url)}</small></span>`).join("")
      : `<span class="client-no-website">Nog geen website</span>`;
    return `<tr><td><input class="client-name-input" data-client-id="${client.id}" value="${escapeHtml(client.name)}" maxlength="255"></td><td><div class="client-websites">${websiteMarkup}</div></td><td>${escapeHtml(client.internal_reference || "—")}</td><td><div class="client-actions"><button type="button" class="detail-button client-open" data-client-id="${client.id}">Open</button><button type="button" class="detail-button client-save" data-client-id="${client.id}">Opslaan</button><button type="button" class="detail-button danger client-delete" data-client-id="${client.id}" data-client-name="${escapeHtml(client.name)}">Verwijder</button></div></td></tr>`;
  }).join("");
  $("#client-cards").innerHTML = clients.map((client) => {
    const websites = websitesByClient[client.id] || [];
    const websiteMarkup = websites.length
      ? websites.map((website) => `<span><strong>${escapeHtml(website.name)}</strong><small>${escapeHtml(website.base_url)}</small></span>`).join("")
      : `<span class="client-no-website">Nog geen website</span>`;
    return `<article class="client-card"><label>Klantnaam<input class="client-name-input" data-client-id="${client.id}" value="${escapeHtml(client.name)}" maxlength="255"></label><div class="client-card-reference"><span>Interne referentie</span><strong>${escapeHtml(client.internal_reference || "—")}</strong></div><div class="client-websites">${websiteMarkup}</div><div class="client-actions"><button type="button" class="detail-button client-open" data-client-id="${client.id}">Open</button><button type="button" class="detail-button client-save" data-client-id="${client.id}">Opslaan</button><button type="button" class="detail-button danger client-delete" data-client-id="${client.id}" data-client-name="${escapeHtml(client.name)}">Verwijder</button></div></article>`;
  }).join("");
  $("#clients-empty").classList.toggle("hidden", clients.length !== 0);
}

async function loadMembers() {
  const clientId = $("#invitation-client").value;
  if (!clientId) { $("#member-rows").innerHTML = ""; $("#member-cards").innerHTML = ""; return; }
  const members = await api(`/api/v1/clients/${clientId}/members`);
  $("#member-rows").innerHTML = members.map((member) => {
    const isSelf = member.id === state.currentUser?.id;
    const roles = [["admin","Admin"],["user","User"],["client","Client"]];
    const roleOptions = roles.map(([value, label]) => `<option value="${value}" ${member.client_role === value ? "selected" : ""}>${label}</option>`).join("");
    return `<tr><td>${escapeHtml(member.display_name || "—")}</td><td>${escapeHtml(member.email)}</td><td><select class="member-role" data-member-id="${member.id}" ${isSelf ? "disabled" : ""}>${roleOptions}</select></td><td>${member.is_active ? "Actief" : "Geblokkeerd"}</td><td><button class="member-remove detail-button" data-member-id="${member.id}" data-member-email="${escapeHtml(member.email)}" ${isSelf ? "disabled" : ""}>Verwijder</button></td></tr>`;
  }).join("");
  $("#member-cards").innerHTML = members.map((member) => {
    const isSelf = member.id === state.currentUser?.id;
    const roles = [["admin","Admin"],["user","User"],["client","Client"]];
    const roleOptions = roles.map(([value, label]) => `<option value="${value}" ${member.client_role === value ? "selected" : ""}>${label}</option>`).join("");
    return `<article class="member-card"><div><strong>${escapeHtml(member.display_name || member.email)}</strong><span class="member-state ${member.is_active ? "active" : "blocked"}">${member.is_active ? "Actief" : "Geblokkeerd"}</span></div><small>${escapeHtml(member.email)}</small><label>Rol<select class="member-role" data-member-id="${member.id}" ${isSelf ? "disabled" : ""}>${roleOptions}</select></label><button class="member-remove detail-button" data-member-id="${member.id}" data-member-email="${escapeHtml(member.email)}" ${isSelf ? "disabled" : ""}>Toegang verwijderen</button></article>`;
  }).join("");
  $("#members-empty").classList.toggle("hidden", members.length !== 0);
}

async function updateMemberRole(memberId, role) {
  const clientId = $("#invitation-client").value;
  const message = $("#members-message");
  try {
    await api(`/api/v1/clients/${clientId}/members/${memberId}`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({role})});
    message.textContent = "Rol bijgewerkt.";
    await loadMembers();
  } catch (error) { message.textContent = error.message; await loadMembers(); }
}

async function removeMember(memberId, email) {
  if (!window.confirm(`Toegang voor ${email} tot deze klant verwijderen?`)) return;
  const clientId = $("#invitation-client").value;
  const message = $("#members-message");
  try {
    await api(`/api/v1/clients/${clientId}/members/${memberId}`, {method:"DELETE"});
    message.textContent = "Toegang verwijderd.";
    await loadMembers();
  } catch (error) { message.textContent = error.message; }
}

async function onboardClient(event) {
  event.preventDefault();
  const form = event.currentTarget; const button = form.querySelector('button[type="submit"]'); const message = $("#client-form-message");
  button.disabled = true; message.classList.remove("error"); message.textContent = "Hoofdklant wordt aangemaakt…";
  try {
    const result = await api("/api/v1/clients", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name:$("#new-client-name").value.trim(), internal_reference:$("#new-client-reference").value.trim() || null})});
    form.reset();
    localStorage.setItem(CLIENT_STORAGE_KEY, result.id);
    localStorage.removeItem(WEBSITE_STORAGE_KEY);
    await loadClients(result.id); await loadOrganization();
    $("#website-onboarding-client").value = result.id;
    message.textContent = "Hoofdklant is aangemaakt. Je kunt nu optioneel een website koppelen.";
  } catch (error) { message.classList.add("error"); message.textContent = error.message; }
  finally { button.disabled = false; }
}

function websiteVerificationMessage(errorCode) {
  return ({
    verification_expired: "Het bestand is verlopen. Download een nieuw verificatiebestand.",
    verification_file_unavailable: "Het bestand is nog niet bereikbaar op de aangegeven locatie.",
    verification_redirect_outside_scope: "De bestandslocatie verwijst door naar een ander domein.",
    verification_token_mismatch: "Het gevonden bestand is niet het laatst gedownloade bestand.",
    verification_timeout: "De website reageerde niet op tijd. Probeer het over enkele minuten opnieuw.",
    verification_ssrf_blocked: "Deze website kan om veiligheidsredenen niet worden gecontroleerd.",
  })[errorCode] || "De plaatsing kon nog niet worden bevestigd. Controleer het bestand en probeer opnieuw.";
}

function onboardingPhaseLabel(phase) {
  return ({
    sitemap_import: "Sitemap wordt gelezen",
    url_check: "Pagina's worden gecontroleerd",
    crawl: "Website wordt verkend",
    "404_analysis": "Foutpagina's worden beoordeeld",
    internal_link_analysis: "Interne links worden geanalyseerd",
    finalizing: "Eerste inzichten worden samengesteld",
  })[phase] || "Website wordt gecontroleerd";
}

function renderFirstCrawlProgress(onboarding) {
  const panel = $("#first-crawl-progress");
  const status = onboarding.first_crawl_status;
  const finished = ["succeeded", "partially_succeeded"].includes(status);
  const failed = ["failed", "cancelled"].includes(status);
  const current = Number(onboarding.first_crawl_current || 0);
  const total = Number(onboarding.first_crawl_total || 0);
  const percentage = finished ? 100 : total > 0 ? Math.min(95, Math.round((current / total) * 100)) : 8;
  panel.classList.toggle("hidden", !onboarding.first_crawl_job_id);
  if (!onboarding.first_crawl_job_id) return;
  $("#website-onboarding-wizard").appendChild(panel);
  $("#first-crawl-progress-bar").style.width = `${percentage}%`;
  $("#retry-first-crawl").classList.toggle("hidden", !failed);
  $("#view-first-results").classList.toggle("hidden", !finished);
  renderOnboardingMeasurement(onboarding, finished);
  if (finished) {
    $("#first-crawl-progress-title").textContent = "Je eerste inzichten staan klaar";
    $("#first-crawl-progress-message").textContent = status === "partially_succeeded"
      ? "De bruikbare resultaten zijn beschikbaar. Enkele pagina's konden nog niet worden gecontroleerd."
      : "De eerste controle is afgerond. Bekijk waar de meeste verbetering mogelijk is.";
  } else if (failed) {
    $("#first-crawl-progress-title").textContent = "De controle kon niet worden afgerond";
    $("#first-crawl-progress-message").textContent = "Je instellingen zijn bewaard. Probeer de controle opnieuw; er wordt geen dubbele crawl aangemaakt.";
  } else if (status === "running") {
    $("#first-crawl-progress-title").textContent = onboardingPhaseLabel(onboarding.first_crawl_phase);
    $("#first-crawl-progress-message").textContent = "Je kunt dit scherm sluiten. De controle gaat op de achtergrond verder.";
  } else {
    $("#first-crawl-progress-title").textContent = "De eerste controle staat klaar";
    $("#first-crawl-progress-message").textContent = status === "waiting_for_capacity"
      ? "De controle start automatisch zodra er capaciteit beschikbaar is."
      : "De controle start automatisch. Je hoeft niets meer te doen.";
  }
  $("#first-crawl-progress-metrics").textContent = `${onboarding.first_crawl_discovered_urls || 0} gevonden · ${onboarding.first_crawl_crawled_urls || 0} gecontroleerd · ${onboarding.first_crawl_failed_urls || 0} niet gelukt`;
}

function renderOnboardingMeasurement(onboarding, visible) {
  const panel = $("#onboarding-measurement-quality");
  const configure = $("#configure-onboarding-measurement");
  panel.classList.toggle("hidden", !visible);
  configure.classList.toggle("hidden", !visible || onboarding.conversion_insights_reliable);
  if (!visible) return;
  const status = onboarding.analytics_quality_status || "not_configured";
  const labels = {
    not_configured: ["Technische monitoring is actief", "Analytics is optioneel. Conversie-inzichten worden pas als betrouwbaar getoond nadat je een bron en leadevents hebt ingesteld."],
    insufficient_data: ["Metingen nog niet gevalideerd", "De analyticsbron is gekoppeld, maar er is nog onvoldoende gecontroleerde historie voor betrouwbare conversie-inzichten."],
    attention_needed: ["Meetkwaliteit vraagt aandacht", "De meting bevat een sterke afwijking. Technische inzichten blijven beschikbaar; conversieconclusies worden begrensd."],
    provisional: ["Metingen voorlopig hersteld", "Eén schone controle is voltooid. Nog één schone controle is nodig voor het label betrouwbaar."],
    reliable: ["Metingen betrouwbaar", "De gekoppelde analyticsbron ondersteunt betrouwbare conversie-inzichten."],
  };
  const [title, message] = labels[status] || labels.insufficient_data;
  $("#onboarding-measurement-title").textContent = onboarding.analytics_quality_source_label ? `${onboarding.analytics_quality_source_label}: ${title}` : title;
  $("#onboarding-measurement-message").textContent = message;
  $("#onboarding-measurement-evidence").textContent = onboarding.analytics_quality_last_checked_at
    ? `Laatst gecontroleerd op ${new Date(onboarding.analytics_quality_last_checked_at).toLocaleString("nl-NL")}.`
    : "Deze stap blokkeert de eerste crawl niet.";
}

function scheduleOnboardingPoll() {
  clearTimeout(onboardingPollTimer);
  const status = state.websiteOnboarding?.first_crawl_status;
  if (state.websiteOnboarding?.first_crawl_job_id && !["succeeded", "partially_succeeded", "failed", "cancelled"].includes(status)) {
    onboardingPollTimer = setTimeout(loadOnboardingProgress, 4000);
  }
}

async function loadOnboardingProgress() {
  if (!state.websiteOnboarding?.id) return;
  try {
    state.websiteOnboarding = await api(`/api/v1/website-onboarding/${state.websiteOnboarding.id}`);
    renderWebsiteOnboarding();
  } catch (_error) {
    scheduleOnboardingPoll();
  }
}

function renderWebsiteOnboarding() {
  ensurePlatformGuidance();
  const onboarding = state.websiteOnboarding;
  const active = Boolean(onboarding);
  $("#website-onboarding-form").classList.toggle("hidden", active && !onboardingEditingDetails);
  $("#website-verification-step").classList.toggle("hidden", !active || onboardingEditingDetails);
  $("#verification-step-label").textContent = !active
    ? "Stap 1 van 3"
    : onboarding?.first_crawl_job_id
      ? "Stap 3 van 3"
      : onboarding?.verification_status === "verified"
        ? "Stap 3 van 3"
        : "Stap 2 van 3";
  if (!onboarding) return;
  renderPlatformGuidance(onboarding);
  const verified = onboarding.verification_status === "verified";
  const crawlStarted = Boolean(onboarding.first_crawl_job_id);
  $("#verification-instructions").classList.toggle("hidden", verified);
  $("#first-crawl-preferences").classList.toggle("hidden", !verified || crawlStarted);
  renderFirstCrawlProgress(onboarding);
  $("#website-verification-message").classList.toggle("error", Boolean(onboarding.last_error_code) && !crawlStarted);
  $("#website-verification-message").textContent = crawlStarted
    ? ""
    : verified
      ? "Website geverifieerd. Bevestig de veilige crawlvoorkeuren."
    : onboarding.last_error_code
      ? websiteVerificationMessage(onboarding.last_error_code)
      : "Download het bestand en plaats het op je website.";
  scheduleOnboardingPoll();
}

const platformLabels = {wordpress:"WordPress",shopify:"Shopify",webflow:"Webflow",wix:"Wix",squarespace:"Squarespace",custom:"maatwerk of een ander platform",unknown:"onbekend platform"};
const platformHelp = {
  wordpress:"Laat je beheerder dit via hosting of SFTP in de publieke map .well-known plaatsen. De mediabibliotheek is niet geschikt.",
  shopify:"Laat je Shopify-developer dit via de storefront of een proxyroute publiceren; de gewone bestandsupload maakt dit adres niet aan.",
  webflow:"Laat je Webflow-developer dit exacte pad via hosting of een proxy publiceren; de Assets-bibliotheek is niet voldoende.",
  wix:"Laat je Wix-developer een openbare route met dit exacte pad en deze inhoud maken; Media Manager is niet voldoende.",
  squarespace:"Laat je Squarespace-beheerder of developer dit exacte openbare pad publiceren; een gewone bestandslink krijgt een ander adres.",
  custom:"Plaats het bestand in de publieke webroot onder .well-known, of stuur deze opdracht naar je websitebeheerder.",
  unknown:"Stuur de getoonde URL en het verificatiebestand naar degene die je website beheert. Diegene kan het bestand op het juiste adres publiceren.",
};

function ensurePlatformGuidance() {
  const container = $("#verification-instructions");
  if ($("#platform-confirmation")) return;
  container.innerHTML = `<div class="verification-back"><button id="edit-onboarding-details" class="detail-button" type="button">← Terug naar websitegegevens</button></div><section id="platform-confirmation" class="platform-confirmation"><span class="eyebrow">PLATFORMHERKENNING</span><div id="platform-detection-loader" class="platform-loader hidden"><span class="loading-spinner" aria-hidden="true"></span><div><h3>Websiteplatform herkennen…</h3><p>Thactual bekijkt de openbare website. Dit duurt meestal enkele seconden.</p></div></div><div id="platform-detection-result"><h3 id="platform-confirmation-title"></h3><p id="platform-confirmation-message"></p><div id="platform-confirmation-actions" class="verification-actions hidden"><button id="confirm-detected-platform" class="primary-button" type="button">Ja, dat klopt</button><button id="change-detected-platform" class="secondary-button" type="button">Nee, ander platform</button></div><div id="platform-selection" class="platform-selection hidden"><label>Welk platform gebruik je?<select id="website-platform"><option value="wordpress">WordPress</option><option value="shopify">Shopify</option><option value="webflow">Webflow</option><option value="wix">Wix</option><option value="squarespace">Squarespace</option><option value="custom">Maatwerk of anders</option><option value="unknown">Weet ik niet</option></select></label><button id="confirm-selected-platform" class="primary-button" type="button">Ga verder</button></div></div></section><section id="verification-methods" class="verification-methods hidden"></section><ol id="verification-instruction-list" class="hidden"><li><strong>Download het verificatiebestand.</strong><span>Dit bestand hoort alleen bij deze website.</span></li><li><strong>Publiceer het op het juiste adres.</strong><span id="platform-upload-help"></span><span>Het moet bereikbaar zijn op <code id="verification-public-url"></code>.</span></li><li><strong>Laat Thactual controleren.</strong><span>Open eerst het adres hierboven. Zie je de bestandsinhoud, klik dan op ‘Controleer plaatsing’.</span></li></ol><div id="verification-actions" class="verification-actions hidden"><button id="download-verification-file" class="primary-button" type="button">Download verificatiebestand</button><button id="check-website-verification" class="secondary-button" type="button">Controleer plaatsing</button></div>`;
  $("#confirm-detected-platform").addEventListener("click", () => confirmWebsitePlatform(state.websiteOnboarding.detected_platform));
  $("#change-detected-platform").addEventListener("click", () => $("#platform-selection").classList.remove("hidden"));
  $("#confirm-selected-platform").addEventListener("click", () => confirmWebsitePlatform($("#website-platform").value));
  $("#download-verification-file").addEventListener("click", downloadWebsiteVerificationFile);
  $("#check-website-verification").addEventListener("click", checkWebsiteVerification);
  $("#edit-onboarding-details").addEventListener("click", editWebsiteOnboardingDetails);
}

function renderPlatformGuidance(onboarding) {
  const detected = onboarding.detected_platform;
  const confirmed = onboarding.confirmed_platform;
  $("#platform-detection-loader").classList.toggle("hidden", !platformDetectionLoading);
  $("#platform-detection-result").classList.toggle("hidden", platformDetectionLoading);
  if (platformDetectionLoading) {
    $("#verification-instruction-list").classList.add("hidden");
    $("#verification-actions").classList.add("hidden");
    $("#verification-methods").classList.add("hidden");
    return;
  }
  $("#platform-confirmation-actions").classList.toggle("hidden", !detected || Boolean(confirmed));
  $("#platform-selection").classList.toggle("hidden", Boolean(confirmed) || Boolean(detected));
  if (confirmed) {
    $("#platform-confirmation-title").textContent = `${platformLabels[confirmed] || confirmed} bevestigd`;
    $("#platform-confirmation-message").textContent = "Hieronder staan de passende uitvoeringsstappen.";
  } else if (detected) {
    const qualifier = onboarding.platform_confidence === "high" ? "We herkennen" : "Dit lijkt op";
    $("#platform-confirmation-title").textContent = `${qualifier} ${platformLabels[detected] || detected}. Klopt dat?`;
    $("#platform-confirmation-message").textContent = "Bevestig dit zodat Thactual de juiste instructies toont.";
  } else {
    $("#platform-confirmation-title").textContent = "We herkennen het websiteplatform niet";
    $("#platform-confirmation-message").textContent = "Geef aan welk platform je gebruikt; technische kennis is niet nodig.";
    $("#platform-selection").classList.remove("hidden");
  }
  $("#verification-instruction-list").classList.toggle("hidden", !confirmed);
  $("#verification-actions").classList.toggle("hidden", !confirmed);
  if (confirmed) {
    $("#platform-upload-help").textContent = platformHelp[confirmed] || platformHelp.custom;
    const knownWebsite = state.organizationWebsites.find(item => item.id === onboarding.website_id);
    const origin = new URL(onboarding.base_url || knownWebsite?.base_url || location.origin).origin;
    $("#verification-public-url").textContent = `${origin}${onboarding.verification_path}`;
    renderVerificationMethods(confirmed);
  }
}

function renderVerificationMethods(platform) {
  const methods = $("#verification-methods");
  methods.classList.remove("hidden");
  if (platform === "wordpress") {
    methods.innerHTML = `<h3>Kies hoe je WordPress koppelt</h3><div class="verification-method-grid"><article class="verification-method recommended"><span>Aanbevolen</span><h4>WordPress-plugin</h4><p>Installeer en activeer de plugin. Gebruik je Multisite? Activeer hem dan alleen op deze website, niet voor het hele netwerk.</p><button id="download-wordpress-plugin" class="primary-button" type="button">Download WordPress-plugin</button></article><article class="verification-method"><h4>Handmatig plaatsen</h4><p>Gebruik hosting of SFTP als je liever geen plugin installeert.</p><button id="show-manual-verification" class="secondary-button" type="button">Toon handmatige stappen</button></article></div>`;
    $("#verification-instruction-list").classList.add("hidden");
    $("#download-verification-file").classList.add("hidden");
    $("#download-wordpress-plugin").addEventListener("click", downloadWordPressPlugin);
    $("#show-manual-verification").addEventListener("click", () => {
      $("#verification-instruction-list").classList.remove("hidden");
      $("#download-verification-file").classList.remove("hidden");
    });
  } else {
    methods.innerHTML = `<h3>Instructies voor ${platformLabels[platform] || platform}</h3><p>${platformHelp[platform] || platformHelp.custom}</p>`;
    $("#download-verification-file").classList.remove("hidden");
  }
}

async function detectWebsitePlatform() {
  platformDetectionLoading = true;
  renderWebsiteOnboarding();
  try {
    const result = await api(`/api/v1/website-onboarding/${state.websiteOnboarding.id}/platform/detect`, {method:"POST"});
    state.websiteOnboarding = {...state.websiteOnboarding, ...result};
  } catch (_error) {
    state.websiteOnboarding = {...state.websiteOnboarding, detected_platform:null, platform_confidence:null};
  }
  platformDetectionLoading = false;
  renderWebsiteOnboarding();
}

function editWebsiteOnboardingDetails() {
  const onboarding = state.websiteOnboarding;
  onboardingEditingDetails = true;
  $("#website-onboarding-client").value = onboarding.client_id;
  $("#website-onboarding-name").value = onboarding.website_name;
  $("#website-onboarding-url").value = onboarding.base_url;
  $("#website-onboarding-sitemap").value = onboarding.sitemap_urls?.[0] || "";
  $("#website-onboarding-form button[type='submit']").textContent = "Wijzigingen opslaan";
  renderWebsiteOnboarding();
}

async function confirmWebsitePlatform(platform) {
  if (!platform) return;
  const result = await api(`/api/v1/website-onboarding/${state.websiteOnboarding.id}/platform/confirm`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({platform})});
  state.websiteOnboarding = {...state.websiteOnboarding, ...result};
  renderWebsiteOnboarding();
}

async function startWebsiteOnboarding(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  const message = $("#website-onboarding-message");
  button.disabled = true;
  message.classList.remove("error");
  message.textContent = "Website wordt klaargezet…";
  try {
    const sitemap = $("#website-onboarding-sitemap").value.trim();
    const baseUrl = $("#website-onboarding-url").value.trim();
    const editing = onboardingEditingDetails && state.websiteOnboarding;
    state.websiteOnboarding = await api(editing ? `/api/v1/website-onboarding/${state.websiteOnboarding.id}/details` : `/api/v1/website-onboarding/clients/${$("#website-onboarding-client").value}`, {
      method: editing ? "PATCH" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        ...(editing ? {} : {request_id: crypto.randomUUID()}),
        website_name: $("#website-onboarding-name").value.trim(),
        base_url: baseUrl,
        ...(editing ? {sitemap_url: sitemap || null} : {settings: {sitemap_urls: sitemap ? [sitemap] : []}}),
      }),
    });
    state.websiteOnboarding.base_url = baseUrl;
    state.verificationFileContent = state.websiteOnboarding.verification_file_content;
    localStorage.setItem(ONBOARDING_STORAGE_KEY, state.websiteOnboarding.id);
    onboardingEditingDetails = false;
    $("#website-onboarding-form button[type='submit']").textContent = "Website toevoegen";
    message.textContent = "";
    renderWebsiteOnboarding();
    await detectWebsitePlatform();
  } catch (error) {
    message.classList.add("error");
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function downloadWordPressPlugin() {
  const button = $("#download-wordpress-plugin");
  button.disabled = true;
  try {
    const response = await fetch(`/api/v1/website-onboarding/${state.websiteOnboarding.id}/verification/wordpress-plugin`, {method:"POST", credentials:"same-origin"});
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "De plugin kon niet worden gemaakt.");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = "thactual-verification.zip";
    document.body.appendChild(link); link.click(); URL.revokeObjectURL(link.href); link.remove();
    $("#website-verification-message").textContent = "Plugin gedownload. Ga in WordPress naar Plugins → Nieuwe plugin → Plugin uploaden, installeer en activeer hem. Bij Multisite activeer je hem alleen op deze website.";
  } catch (error) {
    $("#website-verification-message").classList.add("error");
    $("#website-verification-message").textContent = error.message;
  } finally { button.disabled = false; }
}

function saveVerificationFile(content) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], {type: "text/plain;charset=utf-8"}));
  link.download = "thactual-verification.txt";
  document.body.appendChild(link);
  link.click();
  URL.revokeObjectURL(link.href);
  link.remove();
}

async function downloadWebsiteVerificationFile() {
  const button = $("#download-verification-file");
  const message = $("#website-verification-message");
  button.disabled = true;
  try {
    let content = state.verificationFileContent;
    if (!content) {
      const response = await fetch(`/api/v1/website-onboarding/${state.websiteOnboarding.id}/verification/file`, {method: "POST", credentials: "same-origin"});
      if (response.status === 401) { showLogin(); throw new Error("Niet aangemeld"); }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Het verificatiebestand kon niet worden vernieuwd.");
      }
      content = await response.text();
      state.websiteOnboarding.last_error_code = null;
    }
    saveVerificationFile(content);
    state.verificationFileContent = null;
    button.textContent = "Nieuw bestand downloaden";
    message.classList.remove("error");
    message.textContent = "Bestand gedownload. Plaats het nu op de aangegeven locatie.";
  } catch (error) {
    message.classList.add("error");
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function checkWebsiteVerification() {
  const button = $("#check-website-verification");
  const message = $("#website-verification-message");
  button.disabled = true;
  message.classList.remove("error");
  message.textContent = "Plaatsing wordt gecontroleerd…";
  try {
    const result = await api(`/api/v1/website-onboarding/${state.websiteOnboarding.id}/verification/check`, {method: "POST"});
    state.websiteOnboarding = {...state.websiteOnboarding, ...result};
    renderWebsiteOnboarding();
  } catch (error) {
    message.classList.add("error");
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function startFirstOnboardingCrawl(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  const message = $("#website-verification-message");
  button.disabled = true;
  message.classList.remove("error");
  message.textContent = "Eerste crawl wordt veilig klaargezet…";
  try {
    const result = await api(`/api/v1/website-onboarding/${state.websiteOnboarding.id}/first-crawl`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        max_urls: Number($("#first-crawl-max-urls").value),
        request_delay_ms: Number($("#first-crawl-delay").value),
        concurrency: Number($("#first-crawl-concurrency").value),
        respect_robots_txt: true,
      }),
    });
    state.websiteOnboarding = {
      ...state.websiteOnboarding,
      status: result.status,
      current_step: result.current_step,
      first_crawl_job_id: result.crawl_job_id,
      first_crawl_status: result.queue_status,
    };
    renderWebsiteOnboarding();
  } catch (error) {
    message.classList.add("error");
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function resumeWebsiteOnboarding() {
  const onboardingId = localStorage.getItem(ONBOARDING_STORAGE_KEY);
  if (!onboardingId || state.websiteOnboarding) return;
  try {
    state.websiteOnboarding = await api(`/api/v1/website-onboarding/${onboardingId}`);
    renderWebsiteOnboarding();
  } catch (_error) {
    localStorage.removeItem(ONBOARDING_STORAGE_KEY);
  }
}

function restartWebsiteOnboarding() {
  clearTimeout(onboardingPollTimer);
  state.websiteOnboarding = null;
  state.verificationFileContent = null;
  localStorage.removeItem(ONBOARDING_STORAGE_KEY);
  $("#website-onboarding-form").reset();
  renderWebsiteOnboarding();
}

async function retryFirstOnboardingCrawl() {
  const button = $("#retry-first-crawl");
  button.disabled = true;
  try {
    await api(`/api/v1/website-onboarding/${state.websiteOnboarding.id}/first-crawl/retry`, {method: "POST"});
    await loadOnboardingProgress();
  } catch (error) {
    $("#first-crawl-progress-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function viewFirstOnboardingResults() {
  localStorage.setItem(CLIENT_STORAGE_KEY, state.websiteOnboarding.client_id);
  localStorage.setItem(WEBSITE_STORAGE_KEY, state.websiteOnboarding.website_id);
  await loadClients(state.websiteOnboarding.client_id, state.websiteOnboarding.website_id);
  showView("insights");
}

async function configureOnboardingMeasurement() {
  localStorage.setItem(CLIENT_STORAGE_KEY, state.websiteOnboarding.client_id);
  localStorage.setItem(WEBSITE_STORAGE_KEY, state.websiteOnboarding.website_id);
  await loadClients(state.websiteOnboarding.client_id, state.websiteOnboarding.website_id);
  showView("integrations");
}

async function createWebsite(event) {
  event.preventDefault();
  const form = event.currentTarget; const button = form.querySelector('button[type="submit"]'); const message = $("#website-form-message");
  button.disabled = true; message.classList.remove("error");
  try {
    const website = await api("/api/v1/websites", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({client_id:$("#new-website-client").value, name:$("#new-website-name").value, base_url:$("#new-website-url").value})});
    const clientId = $("#new-website-client").value; form.reset();
    localStorage.setItem(CLIENT_STORAGE_KEY, clientId); localStorage.setItem(WEBSITE_STORAGE_KEY, website.id);
    await loadClients(clientId, website.id); await loadOrganization(); message.textContent = "Website toegevoegd.";
  } catch (error) { message.classList.add("error"); message.textContent = error.message; }
  finally { button.disabled = false; }
}

async function createInvitation(event) {
  event.preventDefault(); const message = $("#invitation-form-message");
  try {
    const invitation = await api("/api/v1/invitations", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({client_id:$("#invitation-client").value, email:$("#invitation-email").value, role:$("#invitation-role").value})});
    $("#invitation-link").value = `${window.location.origin}${invitation.accept_path}`;
    $("#invitation-link-wrap").classList.remove("hidden"); message.textContent = "Uitnodiging gemaakt; deel de eenmalige link veilig.";
  } catch (error) { message.textContent = error.message; }
}

async function loadClients(preferredClientId = null, preferredWebsiteId = null) {
  state.clients = await api("/api/v1/clients");
  $("#client-select").innerHTML = state.clients.map(option).join("");
  const selectedClientId = preferredClientId || localStorage.getItem(CLIENT_STORAGE_KEY);
  if (selectedClientId && state.clients.some((client) => client.id === selectedClientId)) $("#client-select").value = selectedClientId;
  if ($("#client-select").value) localStorage.setItem(CLIENT_STORAGE_KEY, $("#client-select").value);
  await loadWebsites(preferredWebsiteId);
}

async function loadWebsites(preferredWebsiteId = null) {
  const clientId = $("#client-select").value;
  if (!clientId) { state.websites = []; state.issues = []; $("#website-select").innerHTML = ""; render(); return; }
  state.websites = await api(`/api/v1/websites?client_id=${clientId}`);
  $("#website-select").innerHTML = state.websites.map(option).join("");
  const selectedWebsiteId = preferredWebsiteId || localStorage.getItem(WEBSITE_STORAGE_KEY);
  if (selectedWebsiteId && state.websites.some((website) => website.id === selectedWebsiteId)) $("#website-select").value = selectedWebsiteId;
  if ($("#website-select").value) localStorage.setItem(WEBSITE_STORAGE_KEY, $("#website-select").value);
  else localStorage.removeItem(WEBSITE_STORAGE_KEY);
  updateReportSelectors();
  if ($("#website-select").value) await loadIssues();
  else { state.issues = []; state.urlRecords = []; state.urls = new Map(); render(); }
}

async function openClient(clientId) {
  localStorage.setItem(CLIENT_STORAGE_KEY, clientId); localStorage.removeItem(WEBSITE_STORAGE_KEY);
  $("#client-select").value = clientId; await loadWebsites(); showView("dashboard");
}

async function saveClient(clientId, input = null) {
  const nameInput = input || $(`.client-name-input[data-client-id="${clientId}"]`); const message = $("#clients-message");
  try {
    await api(`/api/v1/clients/${clientId}`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name:nameInput.value.trim()})});
    message.classList.remove("error"); message.textContent = "Klantnaam bijgewerkt."; await loadClients(clientId); await loadOrganization();
  } catch (error) { message.classList.add("error"); message.textContent = error.message; }
}

async function deleteClient(clientId, clientName) {
  if (!window.confirm(`Klant “${clientName}” definitief verwijderen? Websites, crawldata, issues, integraties en rapportages worden ook verwijderd.`)) return;
  const message = $("#clients-message");
  try {
    await api(`/api/v1/clients/${clientId}`, {method:"DELETE"});
    if (localStorage.getItem(CLIENT_STORAGE_KEY) === clientId) { localStorage.removeItem(CLIENT_STORAGE_KEY); localStorage.removeItem(WEBSITE_STORAGE_KEY); }
    message.classList.remove("error"); message.textContent = "Klant verwijderd."; await loadClients(); await loadOrganization();
  } catch (error) { message.classList.add("error"); message.textContent = error.message; }
}

async function loadIntegrations() {
  const clientId = $("#client-select").value;
  if (!clientId) return;
  const [connections, googleConfig, bingConfig] = await Promise.all([
    api(`/api/v1/clients/${clientId}/integrations`),
    api("/api/v1/integrations/google/config"),
    api("/api/v1/integrations/bing/config"),
  ]);
  for (const provider of ["google", "bing", "matomo"]) {
    const connection = connections.find((item) => item.provider === provider);
    const target = $(`#${provider}-status`);
    target.textContent = connection ? `${labels[connection.status] || connection.status}${connection.account_email ? ` · ${connection.account_email}` : ""}` : "Niet gekoppeld";
    target.classList.toggle("error", connection?.status === "error");
    target.classList.toggle("connected", connection?.status === "connected");
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
  const bingConnection = connections.find((item) => item.provider === "bing" && item.status === "connected");
  const bingLink = $("#bing-connect");
  bingLink.textContent = bingConnection ? "Opnieuw koppelen" : "Bing koppelen";
  if (bingConfig.configured) {
    bingLink.href = `/api/v1/integrations/bing/authorize?client_id=${clientId}`;
    bingLink.setAttribute("aria-disabled", "false");
  } else {
    bingLink.removeAttribute("href");
    bingLink.setAttribute("aria-disabled", "true");
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
  if (bingConnection) {
    state.bingConnectionId = bingConnection.id;
    await loadBingProperties().catch(() => {
      $("#integration-message").textContent = "Bing-sites konden niet worden geladen. Controleer de API-rechten en probeer opnieuw.";
      $("#integration-message").classList.remove("hidden");
    });
  } else {
    state.bingConnectionId = null;
    $("#bing-property-mapping").classList.add("hidden");
  }
  const matomoConnection = connections.find((item) => item.provider === "matomo" && item.status === "connected");
  state.matomoConnectionId = matomoConnection?.id || null;
  $("#matomo-connect").textContent = matomoConnection ? "Verbinding vervangen" : "Matomo koppelen";
  if (matomoConnection) {
    $("#matomo-server-url").value = matomoConnection.settings?.server_url || "";
    await loadMatomoSites().catch(() => {
      $("#matomo-connect-message").textContent = "Matomo-sites konden niet worden geladen. Controleer het token en de leesrechten.";
      $("#matomo-connect-panel").classList.remove("hidden");
    });
  } else {
    $("#matomo-property-mapping").classList.add("hidden");
  }
  await loadPrimaryAnalyticsSource().catch(() => {});
  await loadExternalEvidenceControls().catch((error) => {
    $("#external-evidence-controls-message").textContent = error.message;
  });
}

async function loadExternalEvidenceControls() {
  const websiteId = $("#website-select").value;
  const panel = $("#external-evidence-controls");
  if (!websiteId) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
  const controls = await api(`/api/v1/websites/${websiteId}/content-analysis/external-evidence-controls`);
  $("#external-evidence-enabled").checked = controls.enabled;
  $("#external-evidence-enabled").disabled = !controls.available;
  $("#external-evidence-monthly-limit").value = controls.monthly_check_limit || 25;
  $("#external-evidence-active-limit").value = controls.active_question_limit || 5;
  $("#save-external-evidence-controls").disabled = !controls.available;
  $("#external-evidence-summary").textContent = controls.available
    ? `${controls.checks_completed_this_month} afgerond deze maand · ${controls.checks_in_progress} bezig · ${controls.active_questions} actief`
    : "Deze functie is nog niet beschikbaar in deze omgeving.";
}

async function saveExternalEvidenceControls() {
  const websiteId = $("#website-select").value;
  const message = $("#external-evidence-controls-message");
  const button = $("#save-external-evidence-controls");
  button.disabled = true; message.textContent = "Instellingen worden opgeslagen…";
  try {
    await api(`/api/v1/websites/${websiteId}/content-analysis/external-evidence-controls`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({enabled:$("#external-evidence-enabled").checked, monthly_check_limit:Number($("#external-evidence-monthly-limit").value), active_question_limit:Number($("#external-evidence-active-limit").value)})});
    message.textContent = "Instellingen opgeslagen.";
    await loadExternalEvidenceControls();
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
}

function showMatomoConnect() {
  $("#matomo-connect-panel").classList.toggle("hidden");
  if (!$("#matomo-connect-panel").classList.contains("hidden")) $("#matomo-server-url").focus();
}

async function connectMatomo() {
  const clientId = $("#client-select").value;
  const serverUrl = $("#matomo-server-url").value.trim();
  const token = $("#matomo-token").value.trim();
  const button = $("#test-matomo"); const message = $("#matomo-connect-message");
  if (!clientId || !serverUrl || !token) { message.textContent = "Vul het HTTPS-adres en API-token in."; return; }
  button.disabled = true; button.textContent = "Testen…"; message.textContent = "";
  try {
    const result = await api(`/api/v1/clients/${clientId}/integrations/matomo`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({server_url:serverUrl, token_auth:token})});
    $("#matomo-token").value = "";
    message.textContent = `Verbinding geslaagd; ${result.sites.length} site(s) beschikbaar.`;
    await loadIntegrations();
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; button.textContent = "Verbinding testen en sites laden"; }
}

async function loadMatomoSites() {
  const clientId = $("#client-select").value; const websiteId = $("#website-select").value;
  if (!clientId || !websiteId || !state.matomoConnectionId) return;
  const [properties, mappings] = await Promise.all([api(`/api/v1/clients/${clientId}/integrations/matomo/sites`), api(`/api/v1/websites/${websiteId}/integrations`)]);
  const mapping = mappings.find((item) => item.service === "matomo");
  fillPropertySelect("#matomo-property", properties.sites, mapping);
  showMappingStatus(mapping, "#matomo-property-message", "Matomo");
  $("#matomo-mapping-website").textContent = $("#website-select").selectedOptions[0]?.textContent || "website";
  $("#matomo-property-mapping").classList.remove("hidden");
}

async function loadPrimaryAnalyticsSource() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  const [mappings, primary] = await Promise.all([api(`/api/v1/websites/${websiteId}/integrations`), api(`/api/v1/websites/${websiteId}/integrations/analytics-primary`)]);
  const options = mappings.filter((item) => ["ga4", "matomo"].includes(item.service) && item.status === "active");
  const select = $("#analytics-primary-source");
  select.innerHTML = `<option value="">Selecteer een gekoppelde bron</option>${options.map((item) => `<option value="${item.service}">${item.service === "ga4" ? "Google Analytics 4" : "Matomo"}</option>`).join("")}`;
  select.value = primary.source || "";
  $("#analytics-primary-message").textContent = primary.source ? `${primary.source === "ga4" ? "GA4" : "Matomo"} is de primaire bron.` : "Kies een primaire analyticsbron.";
  $("#analytics-primary-panel").classList.toggle("hidden", options.length === 0);
  if (options.length) await loadAnalyticsQualityStatus();
}

async function savePrimaryAnalyticsSource() {
  const websiteId = $("#website-select").value; const source = $("#analytics-primary-source").value;
  const message = $("#analytics-primary-message");
  if (!websiteId || !source) { message.textContent = "Selecteer eerst een bron."; return; }
  await api(`/api/v1/websites/${websiteId}/integrations/analytics-primary`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({source})});
  message.textContent = `${source === "ga4" ? "GA4" : "Matomo"} is nu de primaire bron.`;
  await loadAnalyticsQualityStatus();
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
  if (ga4Mapping) await loadGa4KeyEvents();
  else $("#ga4-key-events-panel").classList.add("hidden");
  pollIntegrationHistory(websiteId).catch(() => {});
}

async function loadGa4KeyEvents() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  const events = await api(`/api/v1/websites/${websiteId}/integrations/ga4/key-events`);
  $("#ga4-key-events").innerHTML = events.map((event) => `<article class="key-event"><label><input type="checkbox" value="${escapeHtml(event.event_name)}" ${event.selected ? "checked" : ""}>${escapeHtml(event.event_name)}</label><span>${Number(event.key_events).toLocaleString("nl-NL")} organische gebeurtenissen</span></article>`).join("") || `<p class="key-event-empty">Nog geen organische key-eventdata. Synchroniseer GA4 opnieuw.</p>`;
  $("#ga4-key-events-panel").classList.remove("hidden");
}

async function loadAnalyticsQualityStatus() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  const quality = await api(`/api/v1/websites/${websiteId}/integrations/analytics-quality`);
  const labels = {
    not_configured: ["Nog niet ingesteld", "Kies een primaire bron en stel de conversiemeting in."],
    insufficient_data: ["Nog niet gevalideerd", `Synchroniseer ${quality.source_label || "analytics"} om de meetkwaliteit te controleren.`],
    attention_needed: ["Aandacht nodig", "De event-/sessieverhouding bevat een sterke afwijking. Leadconclusies blijven begrensd."],
    provisional: ["Voorlopig hersteld", "Eén schone controle is voltooid; nog één schone controle is nodig voor verificatie."],
    reliable: ["Metingen betrouwbaar", "De laatste twee controles bevatten geen sterke event-/sessieafwijking."],
  };
  const [title, description] = labels[quality.status] || labels.insufficient_data;
  const anomaly = quality.evidence?.anomalies?.[0];
  const evidence = anomaly
    ? `${anomaly.events} events bij ${anomaly.sessions} sessies op ${new Date(anomaly.date).toLocaleDateString("nl-NL")}.`
    : quality.last_checked_at ? `Laatst gecontroleerd op ${new Date(quality.last_checked_at).toLocaleString("nl-NL")}.` : "";
  const target = $("#analytics-quality-status");
  target.className = `ga4-quality-status ${quality.status}`;
  target.innerHTML = `<strong>${escapeHtml(quality.source_label ? `${quality.source_label}: ${title}` : title)}</strong><span>${escapeHtml(description)}</span>${evidence ? `<small>${escapeHtml(evidence)}</small>` : ""}`;
}

async function saveGa4KeyEvents() {
  const websiteId = $("#website-select").value;
  const button = $("#save-ga4-key-events"); const message = $("#ga4-key-events-message");
  const eventNames = [...document.querySelectorAll("#ga4-key-events input:checked")].map((input) => input.value);
  button.disabled = true; message.textContent = "";
  try {
    await api(`/api/v1/websites/${websiteId}/integrations/ga4/key-events`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({event_names:eventNames})});
    message.textContent = `${eventNames.length} conversie-events opgeslagen.`;
    await Promise.all([loadGa4KeyEvents(), loadAnalyticsQualityStatus()]);
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
}

async function loadBingProperties() {
  const clientId = $("#client-select").value;
  const websiteId = $("#website-select").value;
  if (!clientId || !websiteId || !state.bingConnectionId) return;
  const [properties, mappings] = await Promise.all([
    api(`/api/v1/clients/${clientId}/integrations/bing/properties`),
    api(`/api/v1/websites/${websiteId}/integrations`),
  ]);
  const mapping = mappings.find((item) => item.service === "bing_webmaster");
  fillPropertySelect("#bing-property", properties.sites, mapping);
  showMappingStatus(mapping, "#bing-property-message", "Bing Webmaster Tools");
  $("#bing-mapping-website").textContent = $("#website-select").selectedOptions[0]?.textContent || "website";
  $("#bing-property-mapping").classList.remove("hidden");
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

async function saveProperty(service, selector, buttonSelector, messageSelector, connectionId) {
  const websiteId = $("#website-select").value;
  const select = $(selector);
  if (!websiteId || !select.value || !connectionId) return;
  const button = $(buttonSelector); const message = $(messageSelector);
  button.disabled = true; button.textContent = "Bezig…"; message.textContent = "";
  try {
    await api(`/api/v1/websites/${websiteId}/integrations/${service}`, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ connection_id: connectionId, external_property_id: select.value, external_property_name: select.selectedOptions[0]?.dataset.name || select.value }),
    });
    const serviceLabel = service === "ga4" ? "GA4" : service === "matomo" ? "Matomo" : service === "bing_webmaster" ? "Bing" : "Search Console";
    button.textContent = "Opgeslagen ✓"; message.textContent = `${serviceLabel}-property opgeslagen.`;
    if (service === "ga4") await loadGa4KeyEvents();
    if (["ga4", "matomo"].includes(service)) await loadPrimaryAnalyticsSource();
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
    await Promise.all([loadIssues(), loadAnalyticsQualityStatus()]);
  } catch (error) { message.textContent = "GA4-import is mislukt."; button.textContent = "Opnieuw proberen"; }
  finally { button.disabled = false; }
}

async function syncMatomo() {
  const websiteId = $("#website-select").value;
  const button = $("#sync-matomo"); const message = $("#matomo-property-message");
  if (!websiteId) return;
  button.disabled = true; button.textContent = "Importeren…"; message.textContent = "";
  try {
    const result = await api(`/api/v1/websites/${websiteId}/integrations/matomo/sync`, {method:"POST"});
    const percentage = result.url_match_rate == null ? "onbekend" : `${Math.round(result.url_match_rate * 100)}%`;
    const warning = result.warnings?.length ? ` Waarschuwing: ${result.warnings.join("; ")}.` : "";
    message.textContent = `${result.page_rows} pagina-regels geïmporteerd; ${result.matched_urls} gekoppeld (${percentage}).${warning}`;
    button.textContent = "Opnieuw synchroniseren";
    await Promise.all([loadIssues(), loadAnalyticsQualityStatus()]);
  } catch (error) { message.textContent = error.message; button.textContent = "Opnieuw proberen"; }
  finally { button.disabled = false; }
}

async function syncBing() {
  const websiteId = $("#website-select").value;
  const button = $("#sync-bing"); const message = $("#bing-property-message");
  if (!websiteId) return;
  button.disabled = true; button.textContent = "Importeren…"; message.textContent = "";
  try {
    const result = await api(`/api/v1/websites/${websiteId}/integrations/bing_webmaster/sync`, {method: "POST"});
    const limited = result.link_counts_truncated || result.link_details_truncated ? " De linkimport bereikte de veiligheidslimiet; dit is opgeslagen als gedeeltelijke dekking." : "";
    const linkStatus = result.link_api_status === "unavailable_empty" ? " Bing leverde via de API geen backlinkdekking; bestaande exportdata blijft behouden." : ` ${result.link_targets} linkdoelen en ${result.link_details} inkomende links geïmporteerd.`;
    message.textContent = `${result.page_rows} pagina-regels en ${result.query_rows} zoektermregels geïmporteerd; ${result.matched_urls} gekoppeld aan URL’s.${linkStatus}${limited}`;
    button.textContent = "Opnieuw synchroniseren";
  } catch (error) { message.textContent = "Bing-import is mislukt."; button.textContent = "Opnieuw proberen"; }
  finally { button.disabled = false; }
}

async function importBingBacklinks() {
  const websiteId = $("#website-select").value;
  const button = $("#import-bing-backlinks");
  const message = $("#bing-backlink-import-message");
  const files = [$("#bing-domains-file").files[0], $("#bing-pages-file").files[0], $("#bing-anchors-file").files[0]];
  if (!websiteId || files.some((file) => !file)) { message.textContent = "Selecteer alle drie de Bing CSV-exports."; return; }
  button.disabled = true; message.textContent = "Backlinkexports worden geïmporteerd…";
  try {
    const [domainsCsv, pagesCsv, anchorsCsv] = await Promise.all(files.map((file) => file.text()));
    const result = await api(`/api/v1/websites/${websiteId}/integrations/bing_webmaster/backlinks/import`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({domains_csv:domainsCsv, pages_csv:pagesCsv, anchors_csv:anchorsCsv})});
    message.textContent = `${result.domains} domeinen, ${result.pages} verwijzende pagina’s en ${result.anchors} ankerteksten geïmporteerd; ${result.matched_targets} doelen gekoppeld.`;
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
}

function updateBingFileName(inputSelector, nameSelector) {
  const file = $(inputSelector).files[0];
  $(nameSelector).textContent = file ? file.name : "CSV selecteren";
  $(inputSelector).closest(".file-upload-card").classList.toggle("selected", Boolean(file));
}

async function syncIntegrationHistory() {
  const websiteId = $("#website-select").value;
  const button = $("#sync-integration-history"); const message = $("#integration-history-message");
  if (!websiteId) return;
  button.disabled = true; message.textContent = "Historische import wordt ingepland…";
  try {
    await api(`/api/v1/websites/${websiteId}/integrations/history-sync`, {method: "POST"});
    message.textContent = "Historische GSC- en GA4-import staat in de wachtrij. Voortgang wordt automatisch bijgewerkt.";
    await pollIntegrationHistory(websiteId);
  } catch (error) { message.textContent = error.message; button.disabled = false; }
}

function historyCoverageText(coverage = {}) {
  const ranges = [["GSC", coverage.gsc_from, coverage.gsc_through], ["GSC-zoekopdrachten", coverage.gsc_query_from, coverage.gsc_query_through], ["GA4", coverage.ga4_from, coverage.ga4_through], ["Bing", coverage.bing_from, coverage.bing_through]]
    .filter(([, from]) => from)
    .map(([source, from, through]) => `${source}: ${new Date(from).toLocaleDateString("nl-NL")} – ${new Date(through).toLocaleDateString("nl-NL")}`);
  return ranges.join(" · ");
}

function insightLink(url) {
  if (!url) return "";
  const safe = escapeHtml(url);
  return /^https?:\/\//.test(url)
    ? `<a href="${safe}" target="_blank" rel="noopener">${safe}</a>`
    : `<span>${safe}</span>`;
}

function renderConsultantInsight(insight) {
  const query = insight.query ? `<p class="insight-query">Zoekopdracht: “${escapeHtml(insight.query)}”</p>` : "";
  const url = insight.url ? `<p>${insightLink(insight.url)}</p>` : "";
  const pages = (insight.pages || []).length
    ? `<ul class="insight-pages">${insight.pages.map((page) => `<li>${page.label ? `<strong>${escapeHtml(page.label)}:</strong> ` : ""}${insightLink(page.url)} · ${Number(page.impressions || 0).toLocaleString("nl-NL")} vertoningen · positie ${page.position}</li>`).join("")}</ul>`
    : "";
  const confidence = insight.confidence ? `<span class="insight-confidence ${escapeHtml(insight.confidence)}">Betrouwbaarheid: ${escapeHtml(insight.confidence)}</span>` : "";
  const action = insight.recommended_action ? `<p class="insight-action"><strong>Controle:</strong> ${escapeHtml(insight.recommended_action)}</p>` : "";
  return `<article class="insight-item"><h3>${escapeHtml(insight.title)}</h3>${confidence}<p>${escapeHtml(insight.description)}</p>${query}${url}${pages}${action}</article>`;
}

function renderConsultantInsights() {
  const data = state.consultantInsights;
  if (!data) return;
  const search = data.search || [];
  const content = data.content || [];
  const conversion = data.conversion || [];
  const conversionContext = data.conversion_context || {};
  $("#insight-summary").innerHTML = [
    [search.length, "Zoekkansen"],
    [content.length, "Contentvragen"],
    [search.filter((item) => item.type === "declining_query" || item.type === "declining_page").length, "Dalingen"],
    [conversion.length, "Conversiekansen"],
  ].map(([count, label]) => `<article class="card"><strong>${count}</strong><span>${label}</span></article>`).join("");
  $("#content-insight-list").innerHTML = content.map(renderConsultantInsight).join("") || `<p class="insight-empty">Geen materiële onbeantwoorde zoekvragen gevonden.</p>`;
  $("#search-insight-list").innerHTML = search.map(renderConsultantInsight).join("") || `<p class="insight-empty">Geen duidelijke GSC-kansen in deze periode.</p>`;
  const conversionEmpty = !conversionContext.configured
    ? "Selecteer eerst de gekwalificeerde GA4-events bij Integraties."
    : conversionContext.needs_sync
      ? "Synchroniseer GA4 opnieuw om gekwalificeerde leads per landingspagina te laden."
      : "Geen landingspagina’s met voldoende verkeer en een opvallend laag gekwalificeerd leadsignaal.";
  $("#conversion-insight-list").innerHTML = conversion.map(renderConsultantInsight).join("") || `<p class="insight-empty">${conversionEmpty}</p>`;
}

async function loadConsultantInsights() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  $("#search-insight-list").innerHTML = `<p class="insight-empty">Inzichten worden geladen…</p>`;
  $("#content-insight-list").innerHTML = `<p class="insight-empty">Contentvragen worden geladen…</p>`;
  $("#conversion-insight-list").innerHTML = `<p class="insight-empty">Inzichten worden geladen…</p>`;
  $("#performance-context-answer").innerHTML = "";
  state.consultantInsights = await api(`/api/v1/websites/${websiteId}/consultant-insights?days=${state.insightDays}`);
  renderConsultantInsights();
}

async function submitPerformanceContextQuestion(event) {
  event.preventDefault();
  const websiteId = $("#website-select").value;
  const form = event.currentTarget;
  const answer = $("#performance-context-answer");
  const button = form.querySelector("button");
  const question = $("#performance-context-question").value.trim();
  if (!websiteId || !question) return;
  const periodEnd = new Date();
  periodEnd.setDate(periodEnd.getDate() - 1);
  const periodEndValue = `${periodEnd.getFullYear()}-${String(periodEnd.getMonth() + 1).padStart(2, "0")}-${String(periodEnd.getDate()).padStart(2, "0")}`;
  button.disabled = true;
  answer.innerHTML = `<p>Gelijkwaardige perioden en pagina-aandrijvers worden vergeleken…</p>`;
  try {
    const result = await api(`/api/v1/websites/${websiteId}/context-assistant/answer`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({question, context_type: "website_performance", context_id: websiteId, period_end: periodEndValue, days: state.insightDays})});
    answer.innerHTML = contextAnswerMarkup(result);
  } catch (error) { answer.innerHTML = `<p>Vergelijking kon niet worden geladen: ${escapeHtml(error.message)}</p>`; }
  finally { button.disabled = false; }
}

function contentAnalysisDates() {
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - state.contentAnalysisDays + 1);
  return {start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10)};
}

function distributionMarkup(distribution = {}) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, item) => sum + item[1], 0) || 1;
  return entries.map(([name, count]) => `<div class="distribution-row"><span>${escapeHtml(name.replaceAll("_", " "))}</span><span class="distribution-track"><i style="width:${Math.round(count / total * 100)}%"></i></span><strong>${count}</strong></div>`).join("") || `<p class="insight-empty">Nog geen geclassificeerde pagina’s.</p>`;
}

function evidenceMarkup(evidence = {}) {
  return Object.entries(evidence).slice(0, 5).map(([key, value]) => `<span class="evidence-chip">${escapeHtml(key.replaceAll("_", " "))}: ${escapeHtml(Array.isArray(value) ? value.join(", ") : String(value))}</span>`).join("");
}

const opportunityPatternLabels = {ctr: "CTR-kans", page_two: "Pagina-twee-kans", internal_link: "Interne-linkkans", important_accessibility: "Belangrijke toegankelijkheidskans", journey_friction: "Mogelijke doorstroomkans", underperforming_winner: "Kansrijke pagina met lage uitkomst", intent_mismatch: "Mogelijke mismatch tussen vraag en pagina", device_friction: "Mogelijke mobiele frictie"};
const opportunityPriorityLabels = {high_opportunity: "Hoge kans", opportunity: "Kans", monitor: "Volgen", insufficient_evidence: "Onvoldoende bewijs"};
const opportunityCoverageLabels = {gsc: "Zoekprestatie", search_performance: "Zoekprestatie", crawler_issues: "Paginacontrole", analytics: "Gebruiksdata", journey_behavior: "Bezoekersgedrag"};
const opportunityFeasibilityLabels = {direct: "Direct uitvoerbaar", needs_content_input: "Inhoudelijke afstemming nodig", needs_technical_research: "Technische controle nodig", needs_hypothesis_review: "Hypothese beoordelen"};
const opportunityUrgencyLabels = {low: "Laag", medium: "Middel", high: "Hoog", critical: "Kritiek"};
const opportunityTestabilityLabels = {testable: "Test overwegen", longer_observation_needed: "Langer observeren", effect_measurement_preferred: "Effectmeting heeft voorkeur"};

function opportunityFactorValue(entry) {
  if (entry.signal === "feasibility") return opportunityFeasibilityLabels[entry.value] || "Nadere controle nodig";
  if (entry.signal === "strongest_issue_severity") return opportunityUrgencyLabels[entry.value] || "Nog te bepalen";
  if (entry.signal === "testability_band") return opportunityTestabilityLabels[entry.value] || "Eerst meetplan bepalen";
  if (entry.signal === "affected_pages") return `${entry.value} ${Number(entry.value) === 1 ? "pagina" : "pagina’s"}`;
  if (entry.signal === "important_page_context") {
    const demand = Number(entry.value?.observed_demand || 0);
    if (entry.value?.important_url && demand > 0) return `Belangrijke pagina met ${demand} waargenomen vertoningen`;
    if (entry.value?.important_url) return "Belangrijke pagina";
    return demand > 0 ? `${demand} waargenomen vertoningen` : "Geen extra businesscontext";
  }
  return Array.isArray(entry.value) ? entry.value.join(", ") : String(entry.value ?? "onbekend");
}

function scoredOpportunityMarkup(item) {
  const pattern = item.source_coverage?.pattern || "unknown";
  const coverage = Object.entries(item.source_coverage || {}).filter(([key]) => key !== "pattern").map(([key, available]) => `<span class="coverage-pill ${available ? "" : "coverage-missing"}">${escapeHtml(opportunityCoverageLabels[key] || "Aanvullend signaal")}: ${available ? "aanwezig" : "onbekend"}</span>`).join("");
  const prioritySummary = (item.contributors || []).find((entry) => entry.signal === "priority_summary")?.value || "De beschikbare factoren bepalen de volgorde.";
  const contributors = (item.contributors || []).filter((entry) => entry.signal !== "priority_summary" && entry.label).map((entry) => `<span class="evidence-chip">${escapeHtml(String(entry.label))}: ${escapeHtml(opportunityFactorValue(entry))}</span>`).join("");
  const comparison = item.previous_total_score == null ? "Eerste meting" : `${item.total_score_change >= 0 ? "+" : ""}${item.total_score_change} sinds vorige meting`;
  const disabled = item.priority_class === "insufficient_evidence" ? " disabled" : "";
  return `<article class="opportunity-row scored-opportunity"><div class="opportunity-head"><div><span class="eyebrow">${escapeHtml(opportunityPatternLabels[pattern] || pattern)}</span><h3>${item.primary_url ? `<a href="${escapeHtml(item.primary_url)}" target="_blank" rel="noopener">${escapeHtml(item.primary_url)}</a>` : escapeHtml(item.scope_key)}</h3></div><strong>${escapeHtml(opportunityPriorityLabels[item.priority_class] || item.priority_class)}</strong></div><p>${escapeHtml(String(prioritySummary))}</p><p>${escapeHtml(comparison)} · ${escapeHtml(item.period_start)} t/m ${escapeHtml(item.period_end)}</p><div class="coverage-pills">${coverage}</div><details><summary>Waarom deze prioriteit?</summary><div class="opportunity-evidence">${contributors}</div></details><button type="button" class="detail-button opportunity-action" data-opportunity-evaluation="${escapeHtml(item.id)}"${disabled}>Maak taak</button></article>`;
}

function contextAssistantFormMarkup(contextType, contextId, label) {
  const inputId = `context-question-${contextId}`;
  return `<details class="context-assistant" data-context-type="${escapeHtml(contextType)}" data-context-id="${escapeHtml(contextId)}"><summary>${escapeHtml(label)}</summary><p>Het antwoord gebruikt alleen dit zichtbare record en opgeslagen bewijs.</p><form class="context-question-form"><label for="${escapeHtml(inputId)}">Jouw vraag</label><textarea id="${escapeHtml(inputId)}" maxlength="500" required placeholder="Bijvoorbeeld: waarom heeft dit deze prioriteit?"></textarea><button class="detail-button" type="submit">Beantwoord vraag</button></form><div class="context-answer" aria-live="polite"></div></details>`;
}

function contextAnswerList(title, items) {
  if (!items?.length) return "";
  return `<section class="context-answer-card"><h4>${escapeHtml(title)}</h4><ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>`;
}

function contextAnswerMarkup(result) {
  if (result.status === "scope_limited") return `<p class="scope-limited">${escapeHtml(result.answer)}</p>`;
  const sources = (result.sources || []).map((source) => `${source.description}${source.measured_at ? ` · ${new Date(source.measured_at).toLocaleString("nl-NL")}` : ""}`);
  return `<p>${escapeHtml(result.answer)}</p><div class="context-answer-grid">${contextAnswerList("Gemeten feiten", result.facts)}${contextAnswerList("Interpretatie", result.interpretations)}${contextAnswerList("Ontbrekend bewijs", result.missing_evidence)}${contextAnswerList("Gebruikte bronnen", sources)}</div><p class="context-answer-meta">Confidence: ${escapeHtml(result.confidence)} · alleen-lezen; er zijn geen acties uitgevoerd.</p>`;
}

const effectStatusLabels = {too_early: "Te vroeg om te beoordelen", insufficient_data: "Onvoldoende data", not_comparable: "Niet vergelijkbaar", development_visible: "Ontwikkeling zichtbaar"};

function effectDeltaMarkup(label, change) {
  if (!change) return "";
  const relative = change.relative_percent == null ? "geen bruikbare basis" : `${change.relative_percent >= 0 ? "+" : ""}${change.relative_percent}%`;
  return `<div class="effect-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(relative)}</strong><small>${change.absolute >= 0 ? "+" : ""}${escapeHtml(String(change.absolute))} absoluut</small></div>`;
}

function effectEvaluationMarkup(item) {
  const gsc = item.metrics?.gsc?.changes || {};
  const questionGsc = item.metrics?.question_gsc?.changes || {};
  const analytics = item.metrics?.analytics?.changes || {};
  const gscCoverage = item.source_coverage?.gsc || {};
  const analyticsCoverage = item.source_coverage?.analytics || {};
  const evidence = (item.evidence || []).map((entry) => `<p class="effect-evidence">${escapeHtml(String(entry.message || entry.basis))}</p>`).join("");
  const questionMetrics = item.source_coverage?.question_gsc?.scope_count ? `<div class="effect-question-metrics"><span class="eyebrow">GEKOPPELDE VRAAG</span>${effectDeltaMarkup("Vraagklikken", questionGsc.clicks)}${effectDeltaMarkup("Vraagvertoningen", questionGsc.impressions)}${effectDeltaMarkup("Vraag-CTR", questionGsc.ctr)}${effectDeltaMarkup("Vraagpositie", questionGsc.position)}</div>` : "";
  return `<article class="effect-row"><div class="opportunity-head"><div><span class="eyebrow">${escapeHtml(effectStatusLabels[item.status] || item.status)}</span><h3>${escapeHtml(item.change_period_start)} t/m ${escapeHtml(item.change_period_end)}</h3></div><strong>${item.intervention_ids.length} interventie${item.intervention_ids.length === 1 ? "" : "s"}</strong></div><p>Basis ${escapeHtml(item.baseline_start)}–${escapeHtml(item.baseline_end)} · observatie ${escapeHtml(item.observation_start)}–${escapeHtml(item.observation_end)}</p>${questionMetrics}<div class="effect-metrics">${effectDeltaMarkup("GSC-klikken", gsc.clicks)}${effectDeltaMarkup("GSC-impressies", gsc.impressions)}${effectDeltaMarkup("Bezoeken", analytics.visits)}${effectDeltaMarkup("Conversies", analytics.conversions)}</div><div class="coverage-pills"><span class="coverage-pill">GSC ${gscCoverage.baseline_days || 0}/${gscCoverage.expected_days || 28} + ${gscCoverage.observation_days || 0}/${gscCoverage.expected_days || 28} dagen</span><span class="coverage-pill">${escapeHtml((item.analytics_source || "analytics ontbreekt").toUpperCase())} ${analyticsCoverage.baseline_days || 0}/${analyticsCoverage.expected_days || 28} + ${analyticsCoverage.observation_days || 0}/${analyticsCoverage.expected_days || 28} dagen</span><span class="coverage-pill">${item.url_ids.length} URL's</span><span class="coverage-pill">${item.confidence_factors?.overlapping_urls || 0} overlap</span></div><details><summary>Bewijs en methode</summary>${evidence}<p class="formula-version">Methode ${escapeHtml(item.method_version)} · berekend ${new Date(item.created_at).toLocaleString("nl-NL")}</p></details></article>`;
}

function renderEffectEvaluations() {
  const comparable = state.effectEvaluations.filter((item) => item.status === "development_visible" && item.metrics?.gsc?.changes?.clicks?.relative_percent != null);
  if (comparable.length < 3) {
    $("#content-effect-learning").textContent = `Nog onvoldoende vergelijkbare metingen voor een historisch patroon (${comparable.length}/3).`;
  } else {
    const positive = comparable.filter((item) => item.metrics.gsc.changes.clicks.relative_percent > 0).length;
    $("#content-effect-learning").textContent = `Binnen deze website ontwikkelden organische klikken zich positief bij ${positive} van ${comparable.length} vergelijkbare metingen. Dit is beschrijvende historie; causaliteit is niet bewezen.`;
  }
  $("#content-effect-list").innerHTML = state.effectEvaluations.map(effectEvaluationMarkup).join("") || `<p class="content-loading">Nog geen effectevaluaties. Alleen uitgevoerde taken met een concrete URL-scope worden meegenomen.</p>`;
}

async function submitContextQuestion(form, contextType, contextId) {
  const websiteId = $("#website-select").value;
  const answer = form.parentElement.querySelector(".context-answer");
  const button = form.querySelector("button");
  const question = form.querySelector("textarea").value.trim();
  if (!question) return;
  button.disabled = true;
  answer.innerHTML = `<p>Antwoord wordt opgebouwd uit de zichtbare data…</p>`;
  try {
    const result = await api(`/api/v1/websites/${websiteId}/context-assistant/answer`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({question, context_type: contextType, context_id: contextId})});
    answer.innerHTML = contextAnswerMarkup(result);
  } catch (error) { answer.innerHTML = `<p>Antwoord kon niet worden geladen: ${escapeHtml(error.message)}</p>`; }
  finally { button.disabled = false; }
}

function renderContentAnalysis() {
  const data = state.contentAnalysis;
  if (!data) return;
  const opportunities = data.opportunities;
  const journey = data.journey;
  const pages = opportunities.pages || [];
  const classified = opportunities.coverage?.classified_pages || 0;
  const gscPages = opportunities.coverage?.pages_with_gsc || 0;
  const deadEnds = journey.dead_end_opportunities || [];
  const scoredOpportunities = data.scoredOpportunities || [];
  $("#content-analysis-summary").innerHTML = [[classified,"Geclassificeerd"],[gscPages,"Met GSC-bewijs"],[scoredOpportunities.length,"Gescoorde kansen"],[deadEnds.length,"Mogelijke eindpunten"]].map(([count,label]) => `<article class="card"><strong>${count}</strong><span>${label}</span></article>`).join("");
  $("#content-intent-distribution").innerHTML = distributionMarkup(opportunities.website_distribution);
  const stageTotals = Object.fromEntries(Object.entries(journey.stage_totals || {}).map(([stage, totals]) => [stage, totals.visits || 0]));
  $("#content-journey-summary").innerHTML = distributionMarkup(stageTotals);

  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(pages.length / pageSize));
  state.contentAnalysisPage = Math.min(state.contentAnalysisPage, pageCount);
  const pageRows = pages.slice((state.contentAnalysisPage - 1) * pageSize, state.contentAnalysisPage * pageSize);
  $("#content-page-rows").innerHTML = pageRows.map((page) => {
    const coverage = Object.entries(page.source_coverage || {}).filter((item) => item[1]).map(([name]) => `<span class="coverage-pill">${escapeHtml(name.replaceAll("_", " "))}</span>`).join("") || `<span class="coverage-pill">Onbekend</span>`;
    return `<tr><td><a class="content-page-url" href="${escapeHtml(page.url)}" target="_blank" rel="noopener">${escapeHtml(page.url)}</a></td><td>${escapeHtml(page.search_intent)}</td><td>${escapeHtml(page.journey_stage)}</td><td>${escapeHtml(page.content_role)}</td><td><span class="confidence-value">${Math.round((page.confidence || 0) * 100)}%</span>${page.overridden ? `<span class="coverage-pill">Handmatig</span>` : ""}</td><td><span class="coverage-pills">${coverage}</span></td></tr>`;
  }).join("");
  $("#content-page-count").textContent = `${pages.length} pagina’s`;
  $("#content-page-label").textContent = `Pagina ${state.contentAnalysisPage} van ${pageCount}`;
  $("#content-page-previous").disabled = state.contentAnalysisPage === 1;
  $("#content-page-next").disabled = state.contentAnalysisPage === pageCount;

  $("#content-cluster-list").innerHTML = Object.entries(opportunities.cluster_distribution || {}).map(([cluster, values]) => `<article class="cluster-row"><div class="cluster-head"><h3>/${escapeHtml(cluster === "/" ? "" : cluster)}</h3><strong>${Object.values(values).reduce((sum, count) => sum + count, 0)} pagina’s</strong></div><div class="cluster-values">${Object.entries(values).map(([intent, count]) => `<span>${escapeHtml(intent)} · ${count}</span>`).join("")}</div></article>`).join("") || `<p class="content-loading">Nog geen clusters beschikbaar.</p>`;
  renderQuestionScopes();

  $("#content-analytics-source").textContent = journey.primary_source ? `Primaire bron: ${journey.primary_source.toUpperCase()}` : "Geen primaire bron";
  $("#content-dead-end-list").innerHTML = deadEnds.map((item) => `<article class="opportunity-row"><div class="opportunity-head"><h3>${escapeHtml(item.url)}</h3><strong>${Math.round(item.confidence * 100)}% betrouwbaar</strong></div><p>${escapeHtml(item.recommendation)}</p><div class="opportunity-evidence"><span class="evidence-chip">Doorklik ${Math.round(item.continuation_rate * 100)}%</span><span class="evidence-chip">Referentie ${Math.round(item.benchmark_rate * 100)}%</span><span class="evidence-chip">${item.entry_visits} instapsessies</span></div></article>`).join("") || `<p class="content-loading">Geen statistisch betrouwbare onbedoelde landing-eindpunten gevonden.</p>`;
  const coverage = journey.coverage || {};
  $("#content-route-coverage").textContent = `Dekking — landingsgedrag: ${coverage.landing_continuation || "unknown"}; paginatransities: ${coverage.transitions || "unknown"}; microconversies: ${coverage.micro_conversions || "unknown"}. ${journey.interpretation}`;

  const scoredMarkup = scoredOpportunities.map((item) => scoredOpportunityMarkup(item) + contextAssistantFormMarkup("opportunity_evaluation", item.id, "Vraag over deze kans")).join("");
  const contentMarkup = (opportunities.opportunities || []).map((item) => `<article class="opportunity-row"><div class="opportunity-head"><div><span class="eyebrow">INHOUDELIJK CONTROLEPUNT</span><h3>${escapeHtml(item.title)}</h3></div><strong>${Math.round((item.confidence || 0) * 100)}%</strong></div><p>${escapeHtml(item.description)}</p><div class="opportunity-evidence">${evidenceMarkup(item.evidence)}</div><button type="button" class="detail-button opportunity-action" data-content-opportunity="${escapeHtml(item.key)}">Maak taak</button></article>`).join("");
  $("#content-opportunity-list").innerHTML = scoredMarkup + contentMarkup || `<p class="content-loading">Nog geen kansen berekend voor deze periode.</p>`;
  $("#content-branded-terms").value = (data.settings.branded_terms || []).join(", ");
  $("#content-sector-template").value = data.settings.sector_template || "";
  renderEffectEvaluations();
}

function questionScopeKey(item) { return `${item.url_id}|${item.question}`; }

function questionEvidenceDetailMarkup(detail) {
  if (!detail) return "";
  const observed = detail.observations || [];
  const sources = observed.flatMap((item) => item.sources || []);
  const questions = [...new Set(observed.map((item) => item.observed_question).filter(Boolean))];
  const sourceMarkup = sources.length ? `<ul>${sources.map((source) => `<li><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener">${escapeHtml(source.title || source.url)}</a></li>`).join("")}</ul>` : `<p>Bij deze meting zijn geen citeerbare bronnen aangetroffen.</p>`;
  const assessment = detail.assessment;
  const coverageLabels = {answered:"Beantwoord",partial:"Gedeeltelijk beantwoord",implicit:"Niet duidelijk vindbaar",missing:"Niet aantoonbaar beantwoord"};
  const taskAction = assessment?.status === "observed_citation_gap" ? `<button type="button" class="detail-button question-gap-task" data-question-gap-task="${escapeHtml(detail.observation_id)}" ${detail.task_id ? "disabled" : ""}>${detail.task_id ? "Taak aangemaakt" : "Maak taak"}</button>` : "";
  const assessmentMarkup = assessment ? `<section class="question-evidence-assessment"><div><span class="eyebrow">CONCLUSIE</span><span class="evidence-chip">${escapeHtml(coverageLabels[assessment.coverage_status] || assessment.coverage_status)}</span></div><p>${escapeHtml(assessment.summary)}</p>${assessment.recommended_action ? `<h4>Advies</h4><p>${escapeHtml(assessment.recommended_action)}</p>${taskAction}` : ""}</section>` : "";
  return `<div class="question-evidence-detail">${assessmentMarkup}<div><span class="eyebrow">AANGETROFFEN BEWIJS</span><strong>Gemeten ${new Date(detail.observed_at).toLocaleString("nl-NL")}</strong></div>${questions.length ? `<p>Aangetroffen formulering: ${escapeHtml(questions.join(" · "))}</p>` : ""}<h4>Geciteerde bronnen</h4>${sourceMarkup}</div>`;
}

function renderQuestionScopes() {
  const selection = state.questionScopes;
  if (!selection) { $("#content-question-list").innerHTML = `<p class="content-loading">Vragen worden geladen…</p>`; return; }
  const available = selection.external_evidence_available;
  const statusLabels = {queued:"Wordt voorbereid",pending:"Wordt voorbereid",running:"Wordt gecontroleerd",available:"Bewijs beschikbaar",failed:"Controle mislukt",cancelled:"Niet gestart",budget_exceeded:"Maandlimiet bereikt",scope_limit_reached:"Selectielimiet bereikt"};
  $("#content-question-count").textContent = `${selection.candidates.length} voorgesteld`;
  $("#content-question-list").innerHTML = selection.candidates.map((item) => {
    const current = state.externalEvidenceRequests.get(questionScopeKey(item));
    const requestStatus = current?.status;
    const busy = ["queued", "pending", "running"].includes(requestStatus);
    const disabled = !available || busy || requestStatus === "available";
    const action = requestStatus === "available" ? `<button type="button" class="detail-button" data-view-question-evidence="${escapeHtml(questionScopeKey(item))}">${current?.detail ? "Verberg bewijs" : "Bekijk bewijs"}</button>` : `<button type="button" class="detail-button" data-question-evidence="${escapeHtml(questionScopeKey(item))}" ${disabled ? "disabled" : ""}>${busy ? "Controleren…" : "Controleer AI-dekking"}</button>`;
    return `<article class="question-scope-row"><div class="question-scope-copy"><h3>${escapeHtml(item.question)}</h3><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.url)}</a><div class="question-scope-meta"><span class="evidence-chip">${item.impressions} vertoningen</span><span class="evidence-chip">Positie ${item.position}</span><span class="evidence-chip">Prioriteit ${Math.round(item.selection_priority)}</span></div></div><div class="question-scope-action">${action}${requestStatus ? `<span class="question-scope-status ${requestStatus === "available" ? "available" : ""}">${escapeHtml(statusLabels[requestStatus] || requestStatus)}</span>` : ""}</div>${questionEvidenceDetailMarkup(current?.detail)}</article>`;
  }).join("") || `<p class="content-loading">Geen relevante vragen gevonden binnen deze periode.</p>`;
  $("#content-question-message").textContent = available ? "Kies alleen vragen waarvoor extra bewijs een beslissing kan verbeteren." : "Extra bewijs is voor deze website nog niet beschikbaar.";
}

async function viewQuestionEvidence(key) {
  const current = state.externalEvidenceRequests.get(key);
  if (!current?.observation_id) return;
  if (current.detail) { state.externalEvidenceRequests.set(key, {...current, detail:null}); renderQuestionScopes(); return; }
  try {
    const websiteId = $("#website-select").value;
    const detail = await api(`/api/v1/websites/${websiteId}/content-analysis/external-evidence/observations/${current.observation_id}`);
    state.externalEvidenceRequests.set(key, {...current, detail}); renderQuestionScopes();
  } catch (error) { $("#content-question-message").textContent = `Bewijs kon niet worden geladen: ${error.message}`; }
}

async function createQuestionGapTask(key, observationId) {
  const current = state.externalEvidenceRequests.get(key);
  if (!current?.detail || current.detail.task_id) return;
  try {
    const websiteId = $("#website-select").value;
    const result = await api(`/api/v1/websites/${websiteId}/content-analysis/external-evidence/observations/${observationId}/task`, {method:"POST"});
    state.externalEvidenceRequests.set(key, {...current, detail:{...current.detail, task_id:result.task_id}});
    renderQuestionScopes();
    $("#content-question-message").textContent = result.created ? "Taak aangemaakt." : "Deze taak bestond al.";
  } catch (error) { $("#content-question-message").textContent = `Taak kon niet worden aangemaakt: ${error.message}`; }
}

async function requestQuestionEvidence(key) {
  const item = state.questionScopes?.candidates.find((candidate) => questionScopeKey(candidate) === key);
  if (!item) return;
  const website = state.websites.find((entry) => entry.id === $("#website-select").value) || {};
  state.externalEvidenceRequests.set(key, {status: "queued"}); renderQuestionScopes();
  try {
    const result = await api(`/api/v1/websites/${website.id}/content-analysis/external-evidence`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({capability:"ai_citations",question:item.question,language:website.language || "nl",country:website.country || "NL",device:"mobile",url_id:item.url_id})});
    state.externalEvidenceRequests.set(key, result); renderQuestionScopes();
    if (result.request_id && ["queued", "pending", "running"].includes(result.status)) pollQuestionEvidence(key, result.request_id, 0);
  } catch (error) {
    state.externalEvidenceRequests.set(key, {status:"failed"}); renderQuestionScopes();
    $("#content-question-message").textContent = `Controle kon niet worden gestart: ${error.message}`;
  }
}

async function pollQuestionEvidence(key, requestId, attempt) {
  if (attempt >= 20 || !state.externalEvidenceRequests.has(key)) return;
  window.setTimeout(async () => {
    try {
      const websiteId = $("#website-select").value;
      const result = await api(`/api/v1/websites/${websiteId}/content-analysis/external-evidence/${requestId}`);
      state.externalEvidenceRequests.set(key, result); renderQuestionScopes();
      if (["pending", "running"].includes(result.status)) pollQuestionEvidence(key, requestId, attempt + 1);
    } catch (error) { $("#content-question-message").textContent = `Status kon niet worden bijgewerkt: ${error.message}`; }
  }, 3000);
}

function showContentAnalysisTab(tab) {
  state.contentAnalysisTab = tab;
  $("#content-analysis-tabs").querySelectorAll("button").forEach((button) => { const active = button.dataset.contentTab === tab; button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active)); });
  document.querySelectorAll("[data-content-panel]").forEach((panel) => panel.classList.toggle("hidden", panel.id !== `content-tab-${tab}`));
}

async function timedContentRequest(path) {
  const started = performance.now();
  const data = await api(path);
  return {data, milliseconds: Math.round(performance.now() - started)};
}

async function loadContentAnalysis() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  const {start, end} = contentAnalysisDates();
  const query = `period_start=${start}&period_end=${end}`;
  $("#content-analysis-context").textContent = "Classificaties, kansen en doorstroom worden parallel geladen…";
  $("#content-analysis-summary").innerHTML = Array.from({length: 4}, () => `<article class="card content-skeleton"><strong>&nbsp;</strong><span>&nbsp;</span></article>`).join("");
  document.querySelectorAll("[data-content-panel]").forEach((panel) => { if (!panel.classList.contains("hidden")) panel.setAttribute("aria-busy", "true"); });
  try {
    const [opportunityResult, journeyResult, settingsResult, scoredResult, effectsResult, questionResult] = await Promise.all([
      timedContentRequest(`/api/v1/websites/${websiteId}/content-analysis/opportunities?${query}`),
      timedContentRequest(`/api/v1/websites/${websiteId}/content-analysis/journey?${query}`),
      timedContentRequest(`/api/v1/websites/${websiteId}/content-analysis/settings`),
      timedContentRequest(`/api/v1/websites/${websiteId}/opportunity-evaluations?limit=100&latest_only=true`),
      timedContentRequest(`/api/v1/websites/${websiteId}/effect-evaluations?limit=25`),
      timedContentRequest(`/api/v1/websites/${websiteId}/content-analysis/question-scopes?${query}`),
    ]);
    const opportunities = opportunityResult.data;
    const journey = journeyResult.data;
    const settings = settingsResult.data;
    state.contentAnalysis = {opportunities, journey, settings, scoredOpportunities: scoredResult.data};
    state.effectEvaluations = effectsResult.data;
    state.questionScopes = questionResult.data;
    $("#content-analysis-context").textContent = `${start} t/m ${end} · inhoud ${opportunityResult.milliseconds} ms · doorstroom ${journeyResult.milliseconds} ms · scores ${scoredResult.milliseconds} ms · effect ${effectsResult.milliseconds} ms · vragen ${questionResult.milliseconds} ms · bronnen en ontbrekende dekking worden per onderdeel vermeld.`;
    renderContentAnalysis();
  } catch (error) {
    $("#content-analysis-context").textContent = `Contentanalyse kon niet worden geladen: ${error.message}`;
  } finally {
    document.querySelectorAll("[data-content-panel]").forEach((panel) => panel.removeAttribute("aria-busy"));
  }
}

async function createContentOpportunityTask(opportunityKey) {
  const websiteId = $("#website-select").value;
  const {start, end} = contentAnalysisDates();
  const message = $("#content-opportunity-message");
  message.textContent = "Taak wordt aangemaakt…";
  try {
    const result = await api(`/api/v1/websites/${websiteId}/content-analysis/opportunities/${opportunityKey}/task?period_start=${start}&period_end=${end}`, {method: "POST"});
    message.textContent = result.created ? "Taak aangemaakt." : "Deze kans heeft al een actieve taak.";
  } catch (error) { message.textContent = `Taak kon niet worden aangemaakt: ${error.message}`; }
}

async function evaluateScoredOpportunities() {
  const websiteId = $("#website-select").value;
  const {start, end} = contentAnalysisDates();
  const button = $("#evaluate-opportunities");
  const message = $("#content-opportunity-message");
  button.disabled = true; message.textContent = "Kansen worden berekend…";
  try {
    const result = await api(`/api/v1/websites/${websiteId}/opportunity-evaluations/evaluate?period_start=${start}&period_end=${end}`, {method: "POST"});
    message.textContent = `${result.created} nieuwe kansen; ${result.existing} bestaande beoordelingen ongewijzigd.`;
    await loadContentAnalysis();
  } catch (error) { message.textContent = `Berekenen mislukt: ${error.message}`; }
  finally { button.disabled = false; }
}

async function createScoredOpportunityTask(evaluationId) {
  const websiteId = $("#website-select").value;
  const message = $("#content-opportunity-message");
  message.textContent = "Taak wordt aangemaakt…";
  try {
    await api(`/api/v1/websites/${websiteId}/opportunity-evaluations/${evaluationId}/task`, {method: "POST"});
    message.textContent = "Taak is beschikbaar; een bestaande actieve taak wordt hergebruikt.";
  } catch (error) { message.textContent = `Taak kon niet worden aangemaakt: ${error.message}`; }
}

async function saveContentSettings(event) {
  event.preventDefault();
  const websiteId = $("#website-select").value;
  const message = $("#content-settings-message");
  const brandedTerms = $("#content-branded-terms").value.split(",").map((item) => item.trim()).filter(Boolean);
  try {
    await api(`/api/v1/websites/${websiteId}/content-analysis/settings`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({website_id: websiteId, branded_terms: brandedTerms, sector_template: $("#content-sector-template").value.trim() || null})});
    message.textContent = "Instellingen opgeslagen. Een nieuwe classificatie gebeurt alleen via een expliciete analyseactie.";
    await loadContentAnalysis();
  } catch (error) { message.textContent = `Opslaan mislukt: ${error.message}`; }
}

async function pollIntegrationHistory(websiteId) {
  const button = $("#sync-integration-history"); const message = $("#integration-history-message");
  const result = await api(`/api/v1/websites/${websiteId}/integrations/history-sync`);
  const coverage = historyCoverageText(result.coverage);
  if (result.status === "queued" || result.status === "running") {
    button.disabled = true;
    button.textContent = result.status === "queued" ? "Import wacht op worker…" : "Historie wordt geïmporteerd…";
    message.textContent = `${result.status === "queued" ? "In wachtrij" : "Bezig met importeren"}. Deze pagina controleert automatisch opnieuw.`;
    window.setTimeout(() => pollIntegrationHistory(websiteId).catch(() => {}), 5000);
    return;
  }
  button.disabled = false;
  button.textContent = "Historie tot 16 maanden synchroniseren";
  if (result.status === "succeeded") {
    message.textContent = `Historische import voltooid. ${coverage || "Datumbereik wordt nog verwerkt."}`;
    await loadGa4KeyEvents().catch(() => {});
  } else if (result.status === "failed") {
    message.textContent = `Historische import mislukt${result.error ? `: ${result.error}` : "."}`;
  } else if (coverage) {
    message.textContent = `Beschikbare historische data: ${coverage}`;
  }
}

function showView(view, updateHash = true) {
  if (state.currentUser?.role === "client") view = "reports";
  state.currentView = view;
  const visibleView = view === "reports" ? "actions" : ["clients", "team"].includes(view) ? "organization" : ["contentAnalysis", "opportunities"].includes(view) ? "content-analysis" : view;
  for (const name of ["dashboard", "tasks", "actions", "insights", "content-analysis", "urls", "changes", "vacancies", "operations", "organization", "integrations"]) {
    $(`#${name}-view`).classList.toggle("hidden", name !== visibleView);
  }
  updateNavigation(view);
  $("#context-bar").classList.toggle("hidden", ["clients", "team"].includes(view));
  applyOverviewPresentation(view === "reports");
  if (view === "dashboard") loadDashboard();
  if (view === "tasks") loadTaskCenter();
  if (view === "reports") {
    loadClientReport().catch(() => { $("#report-conclusion").textContent = "Rapportage kon niet worden geladen."; });
    loadReportSnapshots().catch(() => { $("#report-archive-list").innerHTML = "<p>Rapportagehistorie kon niet worden geladen.</p>"; });
  }
  if (view === "integrations") loadIntegrations();
  if (view === "insights") loadConsultantInsights().catch(() => {
    for (const selector of ["#search-insight-list", "#content-insight-list", "#conversion-insight-list"]) {
      $(selector).innerHTML = `<p class="insight-empty">Inzichten konden niet worden geladen. Probeer het later opnieuw.</p>`;
    }
  });
  if (["contentAnalysis", "opportunities"].includes(view)) {
    applyContentAnalysisPresentation(view);
    showContentAnalysisTab(view === "opportunities" ? "opportunities" : state.contentAnalysisTab);
    loadContentAnalysis();
  }
  if (["clients", "team"].includes(view)) { applyOrganizationPresentation(view); loadOrganization(); }
  if (view === "urls") renderUrls();
  if (view === "changes") loadChanges().catch(() => renderTableState("#change-rows", 5, "Wijzigingen konden niet worden geladen. Probeer het later opnieuw.", true));
  if (view === "vacancies") loadJobListings().catch(() => renderTableState("#vacancy-rows", 4, "Vacatures konden niet worden geladen. Probeer het later opnieuw.", true));
  if (view === "operations") { loadOperations(); startOperationsPolling(); } else stopOperationsPolling();
  if (updateHash) window.history.replaceState({}, "", `#${VIEW_HASHES[view]}`);
}

function viewFromHash() {
  const hash = window.location.hash.slice(1);
  const view = Object.keys(VIEW_HASHES).find((name) => VIEW_HASHES[name] === hash) || LEGACY_HASHES[hash] || "dashboard";
  if (LEGACY_HASHES[hash]) window.history.replaceState({}, "", `#${VIEW_HASHES[view]}`);
  return state.currentUser?.role === "client" ? "reports" : view;
}

function updateNavigation(view) {
  const analysisActive = ANALYSIS_VIEWS.has(view);
  const settingsActive = SETTINGS_VIEWS.has(view);
  for (const name of ["dashboard", "insights", "opportunities", "tasks", "reports", "operations"]) $(`#${name}-nav`).classList.toggle("nav-active", name === view);
  $("#analysis-nav").classList.toggle("nav-active", analysisActive);
  $("#settings-nav").classList.toggle("nav-active", settingsActive);
  for (const group of ["analysis", "settings"]) {
    const open = group === "analysis" ? analysisActive : settingsActive;
    $(`#${group}-subnav`).classList.toggle("hidden", !open);
    $(`#${group}-nav`).setAttribute("aria-expanded", String(open));
  }
  for (const name of [...ANALYSIS_VIEWS, ...SETTINGS_VIEWS]) {
    const navName = name === "contentAnalysis" ? "content-analysis" : name;
    $(`#${navName}-nav`).classList.toggle("subnav-active", name === view);
  }
  $("#app").classList.remove("mobile-nav-open");
  $("#mobile-nav-toggle").setAttribute("aria-expanded", "false");
}

function applyContentAnalysisPresentation(view) {
  const opportunityMode = view === "opportunities";
  $("#content-analysis-eyebrow").textContent = opportunityMode ? "KANSEN" : "METINGEN";
  $("#content-analysis-title").textContent = opportunityMode ? "Kansen" : "Content";
  $("#content-analysis-intro").textContent = opportunityMode
    ? "Onderbouwde verbeteropties en toetsbare hypotheses, met zichtbare datadekking."
    : "Zoekintentie, contentrollen en klantreis met zichtbaar bewijs en expliciete datadekking.";
}

function applyOrganizationPresentation(view) {
  const teamMode = view === "team";
  $("#organization-title").textContent = teamMode ? "Team & toegang" : "Klanten & websites";
  $("#organization-intro").textContent = teamMode ? "Nodig gebruikers uit en beheer hun toegang per klant." : "Beheer klanten, websites en de eerste crawlconfiguratie.";
  for (const selector of ["#website-onboarding-wizard", "#onboarding-form", ".client-directory", "#website-form"]) $(selector).classList.toggle("hidden", teamMode);
  for (const selector of ["#invitation-form", ".organization-members"]) $(selector).classList.toggle("hidden", !teamMode);
}

function applyOverviewPresentation(reportMode) {
  $("#overview-eyebrow").textContent = reportMode ? "SEO-RAPPORTAGE" : "ANALYSE";
  $("#overview-title").textContent = reportMode ? "Rapportages" : "Acties";
  $("#client-report-intro").textContent = reportMode ? "Organische prestaties, gerealiseerd werk en de belangrijkste vervolgstappen." : "Prioriteer technische SEO-acties en volg de afhandeling.";
  $("#client-report").classList.toggle("hidden", !reportMode);
  $("#report-archive").classList.toggle("hidden", !reportMode);
  $("#summary").classList.toggle("hidden", reportMode);
  $("#vacancy-dashboard").classList.add("hidden");
  $("#internal-action-panel").classList.toggle("hidden", reportMode);
}

function startOperationsPolling() {
  stopOperationsPolling();
  operationsPollTimer = window.setInterval(loadOperations, 4000);
}

function stopOperationsPolling() {
  if (operationsPollTimer) window.clearInterval(operationsPollTimer);
  operationsPollTimer = null;
}

const verificationStatusLabels = {not_requested:"Nog niet gecontroleerd", queued:"In wachtrij", running:"Wordt gecontroleerd", passed:"Geslaagd", likely_passed:"Waarschijnlijk geslaagd", manual_review:"Handmatige controle", failed:"Niet geslaagd", error:"Controle mislukt", cancelled:"Geannuleerd"};

function taskOwnerLabel(userId) {
  if (!userId) return "Nog niet toegewezen";
  const member = state.taskMembers.find((item) => item.id === userId);
  if (member) return member.display_name || member.email;
  if (state.currentUser?.id === userId) return state.currentUser.display_name || state.currentUser.email || "Jij";
  return "Toegewezen";
}

function taskAssigneeOptions() {
  const members = state.taskMembers.filter((item) => item.is_active && item.client_role !== "client");
  if (state.currentUser?.id && state.currentUser.role !== "client" && !members.some((item) => item.id === state.currentUser.id)) {
    members.unshift({id: state.currentUser.id, display_name: state.currentUser.display_name, email: state.currentUser.email, client_role: state.currentUser.role, is_active: true});
  }
  return members;
}

function formatTaskEffort(task) {
  if (task.effort_min_minutes == null) return "Nog niet ingeschat";
  if (task.effort_max_minutes === task.effort_min_minutes || task.effort_max_minutes == null) return `${task.effort_min_minutes} min`;
  return `${task.effort_min_minutes}–${task.effort_max_minutes} min`;
}

async function loadTaskNotifications() {
  const websiteId = $("#website-select").value;
  state.taskNotifications = websiteId ? await api(`/api/v1/websites/${websiteId}/task-notifications?limit=50`) : [];
  renderTaskNotifications();
}

function renderTaskNotifications() {
  const unread = state.taskNotifications.filter((item) => !item.read_at);
  $("#notification-count").textContent = unread.length > 99 ? "99+" : unread.length;
  $("#notification-count").classList.toggle("hidden", unread.length === 0);
  $("#notification-summary").textContent = unread.length ? `${unread.length} ongelezen` : "Alles gelezen";
  $("#tasks-nav-count").textContent = unread.length > 99 ? "99+" : unread.length;
  $("#tasks-nav-count").classList.toggle("hidden", unread.length === 0);
  $("#notification-list").innerHTML = state.taskNotifications.length ? state.taskNotifications.slice(0, 12).map((item) => `<button class="notification-item ${item.read_at ? "" : "unread"}" type="button" data-notification-id="${item.id}" data-task-id="${item.task_id}"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.message)}</span><time>${escapeHtml(new Date(item.created_at).toLocaleString("nl-NL"))}</time></button>`).join("") : `<p class="notification-empty">Er zijn nog geen taakmeldingen.</p>`;
}

async function loadTaskCenter() {
  const websiteId = $("#website-select").value;
  if (!websiteId) { state.recommendationTasks = []; renderTaskCenter(); return; }
  $("#task-center-message").textContent = "Taken worden geladen…";
  try {
    const params = new URLSearchParams({status: $("#task-status-filter").value || "active", limit:"500"});
    const filters = [["primary_role", "#task-role-filter"], ["priority", "#task-priority-filter"], ["verification_status", "#task-verification-filter"], ["search", "#task-search"]];
    for (const [name, selector] of filters) { const value = $(selector).value.trim(); if (value) params.set(name, value); }
    const ownerFilter = $("#task-owner-filter").value;
    if (ownerFilter === "unassigned") params.set("unassigned", "true");
    else if (ownerFilter) params.set("assigned_to_user_id", ownerFilter);
    const clientId = $("#client-select").value;
    const [tasks, notifications, members] = await Promise.all([
      api(`/api/v1/websites/${websiteId}/recommendation-tasks?${params}`),
      api(`/api/v1/websites/${websiteId}/task-notifications?limit=50`),
      ["superuser", "admin"].includes(state.currentUser?.role) ? api(`/api/v1/clients/${clientId}/members`).catch(() => []) : Promise.resolve([]),
    ]);
    state.recommendationTasks = tasks; state.taskNotifications = notifications; state.taskMembers = members;
    const roles = [...new Set(tasks.map((task) => task.primary_role))].sort();
    const selectedRole = $("#task-role-filter").value;
    $("#task-role-filter").innerHTML = `<option value="">Alle vakgebieden</option>${roles.map((role) => `<option value="${escapeHtml(role)}">${escapeHtml(taskRoleLabels[role] || role)}</option>`).join("")}`;
    $("#task-role-filter").value = selectedRole;
    const selectedOwner = $("#task-owner-filter").value;
    $("#task-owner-filter").innerHTML = `<option value="">Iedereen</option><option value="unassigned">Niet toegewezen</option>${taskAssigneeOptions().map((member) => `<option value="${member.id}">${escapeHtml(member.display_name || member.email)}${member.id === state.currentUser?.id ? " (jij)" : ""}</option>`).join("")}`;
    $("#task-owner-filter").value = selectedOwner;
    renderTaskCenter(); renderTaskNotifications(); $("#task-center-message").textContent = "";
  } catch (error) { $("#task-center-message").textContent = `Taken konden niet worden geladen: ${error.message}`; }
}

function renderTaskCenter() {
  const tasks = state.recommendationTasks;
  const counts = {open:0, in_progress:0, waiting_for_input:0, verification:0};
  for (const task of tasks) { if (task.status === "open" || task.status === "planned") counts.open += 1; if (task.status === "in_progress") counts.in_progress += 1; if (task.status === "waiting_for_input") counts.waiting_for_input += 1; if (["queued","running","manual_review"].includes(task.verification_status)) counts.verification += 1; }
  $("#task-summary").innerHTML = [[counts.open,"Te plannen","Open en gepland"],[counts.in_progress,"In uitvoering","Actief opgepakt"],[counts.waiting_for_input,"Wacht op input","Besluit of informatie nodig"],[counts.verification,"In controle","Automatisch of handmatig"]].map(([count,title,detail]) => `<article class="card"><strong>${count}</strong><span>${title}</span><small>${detail}</small></article>`).join("");
  $("#task-result-count").textContent = `${tasks.length} ${tasks.length === 1 ? "taak" : "taken"}`;
  $("#task-empty").classList.toggle("hidden", tasks.length !== 0);
  $("#task-list").innerHTML = tasks.map((task) => `<article class="task-center-item"><div class="task-center-main"><span class="task-priority ${escapeHtml(task.priority)}">${escapeHtml(labels[task.priority] || task.priority)} · ${escapeHtml(taskRoleLabels[task.primary_role] || task.primary_role)}</span><h3>${escapeHtml(task.title)}</h3><p>${escapeHtml(task.action)}</p></div><div class="task-center-meta"><strong>${escapeHtml(taskOwnerLabel(task.assigned_to_user_id))}</strong><small>${escapeHtml(formatTaskEffort(task))}</small></div><div class="task-center-state"><span class="task-status status-${escapeHtml(task.status)}">${escapeHtml(taskStatusLabels[task.status] || task.status)}</span><small>${escapeHtml(verificationStatusLabels[task.verification_status] || task.verification_status)}</small></div><button class="detail-button" type="button" data-task-issue-id="${task.primary_issue_id || ""}">Open taak</button></article>`).join("");
}

async function openTaskNotification(notificationId, taskId) {
  const notification = state.taskNotifications.find((item) => item.id === notificationId);
  if (notification && !notification.read_at) {
    await api(`/api/v1/task-notifications/${notificationId}/read`, {method:"POST"});
    notification.read_at = new Date().toISOString(); renderTaskNotifications();
  }
  $("#notification-popover").classList.add("hidden"); $("#notification-toggle").setAttribute("aria-expanded", "false");
  showView("tasks");
  const task = state.recommendationTasks.find((item) => item.id === taskId) || await api(`/api/v1/recommendation-tasks/${taskId}`).catch(() => null);
  if (task?.primary_issue_id) await showIssue(task.primary_issue_id);
}

async function loadIssues() {
  const websiteId = $("#website-select").value;
  if (!websiteId) {
    state.issues = [];
    state.suppressions = [];
    state.integrationHealth = {connections: [], mappings: []};
    state.selectedIssueIds.clear();
    state.selectedSuppressionIds.clear();
    render();
    return;
  }
  const status = $("#status-filter").value || "active";
  const canAdmin = ["superuser", "admin"].includes(state.currentUser?.role);
  const clientId = $("#client-select").value;
  const [issues, urls, coverage, suppressions, integrationHealth] = await Promise.all([
    api(`/api/v1/websites/${websiteId}/issues?status=${encodeURIComponent(status)}`),
    loadAllUrls(websiteId),
    api(`/api/v1/websites/${websiteId}/url-coverage`),
    api(`/api/v1/websites/${websiteId}/issue-suppressions`),
    canAdmin ? Promise.all([
      api(`/api/v1/clients/${clientId}/integrations`),
      api(`/api/v1/websites/${websiteId}/integrations`),
    ]).then(([connections, mappings]) => ({connections, mappings})).catch(() => ({connections: [], mappings: []})) : Promise.resolve({connections: [], mappings: []}),
  ]);
  state.issues = issues;
  state.suppressions = suppressions;
  state.integrationHealth = integrationHealth;
  state.selectedIssueIds.clear();
  state.selectedSuppressionIds.clear();
  state.urlRecords = urls;
  state.urlCoverage = coverage;
  state.urls = new Map(urls.map((url) => [url.id, url.normalized_url]));
  const types = [...new Set(issues.map((issue) => issue.issue_type))].sort();
  $("#type-filter").innerHTML = `<option value="">Alle issue-types</option>${types.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`).join("")}`;
  state.page = 1;
  render();
  await Promise.all([
    loadClientReport(),
    loadReportSnapshots(),
    loadTaskNotifications().catch(() => { state.taskNotifications = []; renderTaskNotifications(); }),
    state.currentUser?.role === "client" ? Promise.resolve() : loadJobListings(),
  ]);
}

async function loadAllUrls(websiteId) {
  const urls = [];
  for (let offset = 0; ; offset += 1000) {
    const batch = await api(`/api/v1/websites/${websiteId}/urls?limit=1000&offset=${offset}`);
    urls.push(...batch);
    if (batch.length < 1000) return urls;
  }
}

const vacancyLifecycleLabels = {active: "Actief", expiring_soon: "Loopt bijna af", expired: "Verlopen", removed: "Verwijderd", redirected: "Doorgestuurd"};
const vacancyValidationLabels = {error: "Fout", warning: "Waarschuwing", valid: "Geldig", not_available: "Geen schema"};
const issueScopeLabels = {seo: "SEO", seo_ux: "SEO + UX", quality: "Kwaliteitscontrole", performance: "Performance", editorial: "Redactioneel"};
const issueNatureLabels = {problem: "Probleem", review: "Controleren", optimization: "Optimalisatie"};

async function loadJobListings() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  renderTableState("#vacancy-rows", 4, "Vacatures worden geladen…");
  const result = await api(`/api/v1/websites/${websiteId}/job-listings`);
  state.jobListings = result.job_listings || [];
  state.jobSummary = result.summary || {};
  renderJobListings();
}

function renderJobListings() {
  const query = $("#vacancy-search").value.trim().toLowerCase();
  const lifecycle = $("#vacancy-status-filter").value;
  const validation = $("#vacancy-validation-filter").value;
  state.vacancyFiltered = state.jobListings.filter((listing) => {
    const searchable = `${listing.title || ""} ${listing.url || ""} ${listing.employer || ""}`.toLowerCase();
    const validationMatch = !validation || (validation === "missing_schema" ? !listing.has_job_posting_schema : listing.validation_status === validation);
    const quickMatch = state.vacancyQuickFilter !== "new_issues" || listing.issues.some((issue) => issue.status === "new");
    return (!query || searchable.includes(query)) && (!lifecycle || listing.lifecycle_status === lifecycle) && validationMatch && quickMatch;
  });
  const summary = state.jobSummary || {};
  $("#vacancy-summary").innerHTML = [["total", "Herkend"], ["active", "Actief"], ["expiring_soon", "Loopt bijna af"], ["needs_attention", "Met aandachtspunt"]]
    .map(([key, label]) => `<article class="card"><strong>${Number(summary[key] || 0).toLocaleString("nl-NL")}</strong><span>${label}</span></article>`).join("");
  $("#vacancy-result-count").textContent = `${state.vacancyFiltered.length} vacatures`;
  $("#vacancy-rows").innerHTML = state.vacancyFiltered.map((listing) => {
    const date = listing.valid_through ? `Geldig t/m ${new Date(`${listing.valid_through}T12:00:00`).toLocaleDateString("nl-NL")}` : listing.date_posted ? `Geplaatst ${new Date(`${listing.date_posted}T12:00:00`).toLocaleDateString("nl-NL")}` : "Geen datum in schema";
    const issueMarkup = listing.issues.length
      ? listing.issues.map((issue) => `<div class="vacancy-finding"><span class="severity ${escapeHtml(issue.severity)}">${issue.severity === "high" || issue.severity === "critical" ? "Fout" : "Waarschuwing"}</span><button class="detail-button" data-issue-id="${issue.id}" aria-label="Bekijk ${escapeHtml(issue.title)}">Bekijk</button></div>`).join("")
      : `<span class="vacancy-ok">Geen actieve vacature-issues</span>`;
    return `<tr><td><strong>${escapeHtml(listing.title || "Naam ontbreekt")}</strong><a class="url" title="${escapeHtml(listing.url)}" href="${escapeHtml(listing.url)}" target="_blank" rel="noopener">${escapeHtml(listing.url)}</a><small>${date}</small></td><td><span class="vacancy-badge lifecycle-${escapeHtml(listing.lifecycle_status)}">${escapeHtml(vacancyLifecycleLabels[listing.lifecycle_status] || listing.lifecycle_status)}</span><span class="vacancy-badge validation-${escapeHtml(listing.validation_status)}">${escapeHtml(vacancyValidationLabels[listing.validation_status] || listing.validation_status)}</span><small>${listing.has_job_posting_schema ? "JobPosting gevonden" : "Herkenning via URL en inhoud"}</small></td><td>${listing.inbound_internal_links || 0}</td><td class="vacancy-issues">${issueMarkup}</td></tr>`;
  }).join("");
  $("#vacancy-empty").classList.toggle("hidden", state.vacancyFiltered.length !== 0);
  renderVacancyDashboard();
}

function renderVacancyDashboard() {
  const summary = state.jobSummary || {};
  const metrics = [
    ["active", "Actief"], ["expiring_soon", "Loopt bijna af"], ["expired", "Verlopen"],
    ["technical_errors", "Technische fouten"], ["missing_schema", "Zonder JobPosting"], ["new_issues", "Nieuwe issues"],
  ];
  $("#vacancy-dashboard-stats").innerHTML = metrics.map(([key, label]) => `<button type="button" data-vacancy-filter="${key}"><strong>${Number(summary[key] || 0).toLocaleString("nl-NL")}</strong><span>${label}</span></button>`).join("");
}

function openVacanciesWithFilter(filter = "") {
  state.vacancyQuickFilter = filter === "new_issues" ? "new_issues" : null;
  $("#vacancy-search").value = "";
  $("#vacancy-status-filter").value = ["active", "expiring_soon", "expired"].includes(filter) ? filter : "";
  $("#vacancy-validation-filter").value = filter === "technical_errors" ? "error" : filter === "missing_schema" ? "missing_schema" : "";
  showView("vacancies");
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
  const source = $("#url-source-filter").value;
  const depth = $("#url-depth-filter").value;
  state.urlFiltered = state.urlRecords.filter((url) => {
    const code = url.current_status_code;
    const statusMatch = !status || (status === "none" ? code === null : code >= Number(status[0]) * 100 && code < (Number(status[0]) + 1) * 100);
    const indexMatch = !indexation || urlIndexState(url) === indexation;
    const currentSources = url.current_source_types || [];
    const sourceMatch = !source || (source === "historical_only" ? (url.source_types || []).length > 0 && currentSources.length === 0 : source === "no_source" ? (url.source_types || []).length === 0 : currentSources.includes(source));
    const depthMatch = !depth || (depth === "none" ? url.crawl_depth === null : depth === "0-2" ? url.crawl_depth >= 0 && url.crawl_depth <= 2 : depth === "3-4" ? url.crawl_depth >= 3 && url.crawl_depth <= 4 : url.crawl_depth >= 5);
    return statusMatch && indexMatch && sourceMatch && depthMatch && (!query || url.normalized_url.toLowerCase().includes(query));
  });
  renderUrlCoverage();
  const pages = Math.max(1, Math.ceil(state.urlFiltered.length / URL_PAGE_SIZE));
  state.urlPage = Math.min(state.urlPage, pages);
  const start = (state.urlPage - 1) * URL_PAGE_SIZE;
  const rows = state.urlFiltered.slice(start, start + URL_PAGE_SIZE);
  $("#url-rows").innerHTML = rows.map((url) => {
    const indexState = urlIndexState(url);
    const indexLabel = {indexable: "Indexeerbaar", blocked: "Niet indexeerbaar", unknown: "Onbekend"}[indexState];
    const checked = url.last_full_analyzed_at ? new Date(url.last_full_analyzed_at).toLocaleDateString("nl-NL") : "—";
    const depth = url.crawl_depth ?? "—";
    const depthLabel = url.crawl_depth_reliable ? depth : `${depth}*`;
    const issueTitle = url.active_issue_titles?.[0];
    const issueCount = url.active_issue_count || 0;
    const issueSignal = issueTitle ? `<div class="url-signal"><span class="severity ${escapeHtml(url.highest_issue_severity || "low")}">${escapeHtml(labels[url.highest_issue_severity] || url.highest_issue_severity || "Signaal")}</span><span class="url-signal-title">${escapeHtml(issueTitle)}${issueCount > 1 ? ` <small>+${issueCount - 1}</small>` : ""}</span></div>` : `<span class="url-signal-empty">Geen actief signaal</span>`;
    const currentSources = url.current_source_types || [];
    const historicalSources = (url.source_types || []).filter((item) => !currentSources.includes(item));
    const sourceLabels = {sitemap:"Sitemap", internal_link:"Interne link", known:"Bekend", manual:"Handmatig", hreflang:"Hreflang", structured_data:"Structured data"};
    const sources = [...currentSources.map((item) => `<span class="url-source">${escapeHtml(sourceLabels[item] || item)}</span>`), ...historicalSources.map((item) => `<span class="url-source historical" title="Niet teruggevonden in de laatste volledige crawl">${escapeHtml(sourceLabels[item] || item)} · historisch</span>`)].join("") || `<span class="url-source-empty">Geen bron</span>`;
    return `<tr><td><a class="url-address" href="${escapeHtml(url.normalized_url)}" target="_blank" rel="noopener">${escapeHtml(url.normalized_url)}</a></td><td><div class="url-source-list">${sources}</div></td><td><span class="status-code">${url.current_status_code ?? "—"}</span></td><td><span class="index-state ${indexState}">${indexLabel}</span></td><td>${issueSignal}</td><td title="${escapeHtml(url.crawl_depth_context || "")}">${depthLabel}</td><td>${checked}</td><td><button class="detail-button" data-url-id="${url.id}">Bekijk</button></td></tr>`;
  }).join("");
  $("#url-result-count").textContent = `${state.urlFiltered.length} URLs`;
  $("#url-page-label").textContent = `Pagina ${state.urlPage} van ${pages}`;
  $("#url-previous-page").disabled = state.urlPage === 1;
  $("#url-next-page").disabled = state.urlPage === pages;
  $("#url-empty").classList.toggle("hidden", rows.length !== 0);
}

function renderUrlCoverage() {
  const coverage = state.urlCoverage;
  if (!coverage) { $("#url-coverage-summary").innerHTML = ""; $("#url-coverage-context").textContent = "Dekking wordt geladen…"; return; }
  const current = coverage.current_source_counts || {};
  const metrics = [[coverage.total_active_urls,"Actieve URL’s"],[current.sitemap || 0,"In sitemap"],[current.internal_link || 0,"Intern gevonden"],[coverage.historical_only_urls || 0,"Alleen historisch"]];
  $("#url-coverage-summary").innerHTML = metrics.map(([value,label]) => `<article class="card"><strong>${Number(value).toLocaleString("nl-NL")}</strong><span>${label}</span></article>`).join("");
  $("#url-coverage-context").textContent = `${coverage.context}. ${coverage.multi_source_urls} URL’s zijn via meerdere actuele bronnen gevonden; ${coverage.no_source_urls} hebben geen bronregistratie.`;
  $("#url-coverage-context").classList.toggle("provisional", !coverage.reliable);
}

async function showUrl(urlId) {
  const url = state.urlRecords.find((item) => item.id === urlId);
  if (!url) return;
  const websiteId = $("#website-select").value;
  const [snapshots, route, inspections] = await Promise.all([
    api(`/api/v1/urls/${urlId}/snapshots?limit=1`),
    api(`/api/v1/urls/${urlId}/crawl-route`),
    api(`/api/v1/websites/${websiteId}/integrations/url_inspection/results?url_id=${urlId}&limit=1`).catch(() => []),
  ]);
  const snapshot = snapshots[0];
  const inspection = inspections[0];
  const issues = state.issues.filter((issue) => issue.url_id === urlId && ACTIVE_STATUSES.has(issue.status));
  $("#url-detail-link").textContent = url.normalized_url;
  $("#url-detail-link").href = url.normalized_url;
  $("#url-detail-status").textContent = `${url.current_status_code ?? "Niet gecontroleerd"}${url.current_final_url && url.current_final_url !== url.normalized_url ? ` → ${url.current_final_url}` : ""}`;
  $("#url-detail-indexation").textContent = {indexable: "Indexeerbaar", blocked: "Niet indexeerbaar", unknown: "Onbekend"}[urlIndexState(url)];
  $("#url-detail-canonical").textContent = snapshot?.canonical_urls?.length ? snapshot.canonical_urls.join("\n") : snapshot?.canonical || "Geen canonical gevonden.";
  $("#url-detail-hreflang").textContent = snapshot?.hreflang_links?.length ? snapshot.hreflang_links.map((item) => `${item.language}: ${item.target_url}`).join("\n") : "Geen hreflang gevonden.";
  $("#url-detail-google").textContent = inspection ? formatGoogleInspection(inspection) : "Nog geen Google URL Inspection-meting beschikbaar.";
  $("#url-detail-crawl").textContent = `Crawl-diepte: ${url.crawl_depth ?? "onbekend"} · ${url.crawl_depth_context || "Geen meetcontext"} · Paginatype: ${url.page_type || "onbekend"}`;
  $("#url-detail-route").textContent = route.route.length ? route.route.join("\n→ ") : route.context;
  $("#url-detail-snapshot").textContent = snapshot ? `${new Date(snapshot.checked_at).toLocaleString("nl-NL")} · ${snapshot.response_size ?? 0} bytes · ${snapshot.response_time_ms ?? "—"} ms · ${snapshot.word_count ?? "—"} woorden` : "Geen snapshot beschikbaar.";
  $("#url-detail-issues").textContent = issues.length ? issues.map((issue) => `${labels[issue.severity] || issue.severity}: ${issue.title}`).join("\n") : "Geen actieve issues.";
  $("#url-dialog").showModal();
}

function formatGoogleInspection(inspection) {
  const verdict = {PASS: "Geïndexeerd", NEUTRAL: "Niet bevestigd als geïndexeerd", FAIL: "Probleem vastgesteld", PARTIAL: "Gedeeltelijk"}[inspection.verdict] || inspection.verdict || "Onbekend";
  const values = [
    `${verdict} · gemeten ${new Date(inspection.inspected_at).toLocaleString("nl-NL")}`,
    inspection.coverage_state ? `Google-dekking: ${inspection.coverage_state}` : null,
    inspection.last_crawl_time ? `Laatste Google-crawl: ${new Date(inspection.last_crawl_time).toLocaleString("nl-NL")}` : "Laatste Google-crawl: onbekend",
    inspection.google_canonical ? `Google-canonical: ${inspection.google_canonical}` : null,
  ];
  return values.filter(Boolean).join("\n");
}

async function loadDashboard() {
  const websiteId = $("#website-select").value;
  if (!websiteId) { renderDashboard(); return; }
  await Promise.all([
    loadChanges().catch(() => {}),
    loadOperations().catch(() => {}),
    state.clientReport ? Promise.resolve() : loadClientReport().catch(() => {}),
    state.jobListings.length ? Promise.resolve() : loadJobListings().catch(() => {}),
  ]);
  renderDashboard();
}

function renderDashboard() {
  const activeIssues = state.issues.filter((issue) => ACTIVE_STATUSES.has(issue.status));
  const issueCounts = {total: activeIssues.length, high: 0, medium: 0, low: 0};
  activeIssues.forEach((issue) => { if (issueCounts[issue.severity] !== undefined) issueCounts[issue.severity] += 1; });
  $("#dashboard-priorities").innerHTML = [["total", "Actieve acties"], ["high", "Hoge prioriteit"], ["medium", "Middel"], ["low", "Laag"]]
    .map(([key, label]) => `<button type="button" class="card dashboard-priority ${key}" data-dashboard-priority="${key === "total" ? "" : key}" aria-label="${label}: ${issueCounts[key]}. Open actielijst"><strong>${issueCounts[key]}</strong><span>${label}</span><small>Bekijk acties →</small></button>`).join("");
  const newIssues = activeIssues.filter((issue) => issue.status === "new");
  const importantIssues = [...(newIssues.length ? newIssues : activeIssues)].sort((a, b) => ({high: 0, medium: 1, low: 2}[a.severity] - {high: 0, medium: 1, low: 2}[b.severity] || new Date(b.first_detected_at) - new Date(a.first_detected_at))).slice(0, 5);
  $("#dashboard-actions").innerHTML = importantIssues.map((issue) => `<article><strong>${escapeHtml(issue.title)}</strong><small><span class="severity ${issue.severity}">${labels[issue.severity]}</span> · ${new Date(issue.first_detected_at).toLocaleDateString("nl-NL")}</small></article>`).join("") || `<p class="dashboard-empty">Geen actieve technische acties.</p>`;
  $("#dashboard-changes").innerHTML = state.changeGroups.slice(0, 5).map((group) => {
    const target = group.incident_type === "domain_swap" ? `${group.affected_url_ids.length} geraakte URL’s` : state.urls.get(group.url_id) || "Onbekende URL";
    return `<article><strong>${escapeHtml(changeGroupLabel(group))}</strong><small>${escapeHtml(target)} · ${new Date(group.detected_at).toLocaleDateString("nl-NL")}</small></article>`;
  }).join("") || `<p class="dashboard-empty">Geen betekenisvolle wijzigingen gevonden.</p>`;
  const current = state.clientReport?.current || {};
  $("#dashboard-performance").innerHTML = [[current.clicks, "GSC-klikken"], [current.sessions, "Organische sessies"], [current.key_events, "Gekwalificeerde leads"]].map(([value, label]) => {
    const available = value !== null && value !== undefined;
    return `<article class="${available ? "" : "unavailable"}"><strong>${available ? Number(value).toLocaleString("nl-NL") : "—"}</strong><span>${label}</span>${available ? "" : "<small>Geen gekoppelde data</small>"}</article>`;
  }).join("");
  const vacancies = state.jobSummary || {};
  $("#dashboard-vacancies").innerHTML = [[vacancies.active, "Actief"], [vacancies.expiring_soon, "Loopt bijna af"], [vacancies.needs_attention, "Aandacht nodig"]].map(([value, label]) => `<article><strong>${Number(value || 0).toLocaleString("nl-NL")}</strong><span>${label}</span></article>`).join("");
  const run = state.crawlRuns[0];
  const runMetrics = run ? crawlRunMetrics(run) : null;
  $("#dashboard-crawl").innerHTML = run ? `<article><strong>${labels[run.status] || run.status} · ${runMetrics.summary}</strong><small>${new Date(run.started_at).toLocaleString("nl-NL")} · ${run.failed_urls} mislukt · ${durationLabel(run)}</small></article>` : `<p class="dashboard-empty">Nog geen crawl uitgevoerd.</p>`;
  renderIntegrationWarning();
}

async function loadOperations() {
  const websiteId = $("#website-select").value;
  if (!websiteId) return;
  const requestId = ++state.operationsRequestId;
  state.operationsLoading = true;
  try {
    const [crawlRuns, exports, activeCrawlJob] = await Promise.all([
      api(`/api/v1/websites/${websiteId}/crawl-runs?limit=20`),
      api(`/api/v1/exports?website_id=${websiteId}&limit=20`),
      api(`/api/v1/websites/${websiteId}/crawl-jobs/active`),
    ]);
    if (requestId !== state.operationsRequestId || websiteId !== $("#website-select").value) return;
    let currentJob = activeCrawlJob;
    if (!currentJob && crawlRuns[0]?.status === "failed") {
      currentJob = await api(`/api/v1/crawl-jobs/${crawlRuns[0].crawl_job_id}`);
    }
    const systemStatus = await api("/api/v1/system/status").catch(() => null);
    if (requestId !== state.operationsRequestId || websiteId !== $("#website-select").value) return;
    state.crawlRuns = crawlRuns;
    state.exports = exports;
    state.activeCrawlJob = currentJob;
    state.systemStatus = systemStatus;
    $("#operations-load-message").textContent = state.systemStatus ? "" : "De systeemstatus kon niet worden opgehaald; crawl- en exportgegevens zijn wel bijgewerkt.";
    $("#operations-load-message").classList.toggle("error", !state.systemStatus);
    renderOperations();
  } catch (error) {
    $("#operations-load-message").textContent = `Status kon niet worden bijgewerkt: ${error.message}`;
    $("#operations-load-message").classList.add("error");
  } finally {
    if (requestId === state.operationsRequestId) state.operationsLoading = false;
  }
}

function renderSystemStatus() {
  const status = state.systemStatus;
  const unavailable = {status: "unavailable", workers: 0, queued_jobs: 0};
  const crawl = status?.queues?.crawls || unavailable;
  const lightCrawls = status?.queues?.crawls_light || unavailable;
  const fullCrawls = status?.queues?.crawls_full || unavailable;
  const sitemaps = status?.queues?.sitemaps || unavailable;
  const verifications = status?.queues?.verifications || unavailable;
  const integrations = status?.queues?.integrations || unavailable;
  const maintenance = status?.queues?.maintenance || unavailable;
  const exports = status?.queues?.exports || unavailable;
  const deadLetters = Number(status?.dead_letters?.unresolved || 0);
  const healthy = status?.status === "ok";
  $("#system-status-summary").textContent = healthy ? "Alles operationeel" : "Aandacht nodig";
  $("#system-status-summary").className = `system-summary ${healthy ? "ok" : "degraded"}`;
  $("#crawl-capacity").textContent = crawl.status === "ok"
    ? `${crawl.workers} crawlworker${crawl.workers === 1 ? "" : "s"} beschikbaar · ${crawl.queued_jobs} ${crawl.queued_jobs === 1 ? "taak" : "taken"} in wachtrij`
    : "Workercapaciteit is momenteel niet beschikbaar.";
  $("#crawl-capacity").classList.toggle("degraded", crawl.status !== "ok");
  const entries = [
    ["API & database", status?.api === "ok" && status?.database === "ok" ? "ok" : "unavailable", status?.database === "ok" ? "Bereikbaar" : "Database niet bereikbaar"],
    ["Light checks", lightCrawls.status, `${lightCrawls.workers} worker · ${lightCrawls.queued_jobs} in wachtrij`],
    ["Volledige crawls", fullCrawls.status, `${fullCrawls.workers} worker · ${fullCrawls.queued_jobs} in wachtrij`],
    ["Sitemaps", sitemaps.status, `${sitemaps.workers} worker · ${sitemaps.queued_jobs} in wachtrij`],
    ["Verificaties", verifications.status, `${verifications.workers} worker · ${verifications.queued_jobs} in wachtrij`],
    ["Data-importworker", integrations.status, `${integrations.workers} beschikbaar · ${integrations.queued_jobs} in wachtrij`],
    ["Onderhoud", maintenance.status, `${maintenance.workers} worker · ${maintenance.queued_jobs} in wachtrij`],
    ["Exportworker", exports.status, `${exports.workers} beschikbaar · ${exports.queued_jobs} in wachtrij`],
    ["Definitief mislukte taken", deadLetters === 0 ? "ok" : "blocked", deadLetters ? `${deadLetters} vraagt beoordeling` : "Geen openstaande dead letters"],
  ];
  const statusLabel = {ok: "Operationeel", warning: "Bijna vol", blocked: "Geblokkeerd", degraded: "Aandacht nodig", unavailable: "Niet beschikbaar"};
  $("#system-status-grid").innerHTML = entries.map(([label, queueStatus, detail]) => `<article><span>${label}</span><strong class="${queueStatus === "ok" ? "ok" : "degraded"}">${statusLabel[queueStatus] || "Aandacht nodig"}</strong><small>${detail}</small></article>`).join("");
}

function durationLabel(run) {
  if (!run.finished_at) return run.status === "running" ? "Bezig" : "—";
  const seconds = Math.max(0, Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000));
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`;
}

function crawlRunMetrics(run) {
  const discovered = Number(run.discovered_urls || 0).toLocaleString("nl-NL");
  const crawled = Number(run.crawled_urls || 0);
  const html = Number(run.html_urls || 0);
  const assets = Number(run.asset_urls || 0);
  const processed = assets
    ? `${html.toLocaleString("nl-NL")} HTML · ${assets.toLocaleString("nl-NL")} assets`
    : `${html.toLocaleString("nl-NL")} HTML`;
  if (run.crawl_type === "fetch_sitemap") {
    return {
      discoveredLabel: "URL's geïmporteerd",
      discovered,
      processedLabel: "Sitemapbestanden verwerkt",
      processed: crawled.toLocaleString("nl-NL"),
      summary: `${discovered} URL's geïmporteerd · ${crawled.toLocaleString("nl-NL")} sitemapbestand${crawled === 1 ? "" : "en"} verwerkt`,
    };
  }
  const isLightCheck = run.crawl_type === "light_check";
  return {
    discoveredLabel: isLightCheck ? "Bekende URL's geselecteerd" : "URL's ontdekt",
    discovered,
    processedLabel: "Verwerkt",
    processed,
    summary: processed,
  };
}

function crawlProgressLabel(run) {
  const phaseLabels = {
    url_check: "URL-controle",
    "404_analysis": "404-analyse",
    internal_link_analysis: "Interne-linkanalyse",
    finalizing: "Afronden",
  };
  const phase = phaseLabels[run.phase] || "Crawl voorbereiden";
  const progress = run.phase_total > 0
    ? ` · ${Number(run.phase_current || 0).toLocaleString("nl-NL")} van ${Number(run.phase_total).toLocaleString("nl-NL")}`
    : "";
  const counts = [
    `${Number(run.html_urls || 0).toLocaleString("nl-NL")} HTML`,
    `${Number(run.asset_urls || 0).toLocaleString("nl-NL")} assets`,
    `${Number(run.skipped_urls || 0).toLocaleString("nl-NL")} overgeslagen`,
    `${Number(run.failed_urls || 0).toLocaleString("nl-NL")} mislukt`,
  ].join(" · ");
  return `${phase}${progress} · ${counts}`;
}

function crawlFailureButton(run) {
  const count = Number(run.failed_urls || 0);
  if (!count) return "0";
  return `<button type="button" class="crawl-failure-button" data-crawl-failures="${escapeHtml(run.id)}" aria-label="Bekijk ${count} mislukte URL's">${count.toLocaleString("nl-NL")}</button>`;
}

async function showCrawlFailures(runId) {
  const panel = $("#crawl-failure-panel");
  panel.classList.remove("hidden");
  $("#crawl-failure-title").textContent = "Fouten laden…";
  $("#crawl-failure-summary").textContent = "";
  $("#crawl-failure-list").innerHTML = "";
  panel.scrollIntoView({behavior: "smooth", block: "nearest"});
  try {
    const failures = await api(`/api/v1/crawl-runs/${runId}/failures`);
    const actionCount = failures.filter((failure) => failure.assessment === "action_required").length;
    const retryCount = failures.filter((failure) => failure.assessment === "retry").length;
    $("#crawl-failure-title").textContent = `${failures.length} mislukte URL${failures.length === 1 ? "" : "'s"}`;
    $("#crawl-failure-summary").textContent = `${actionCount} actie vereist · ${retryCount} opnieuw proberen · ${failures.length - actionCount - retryCount} beoordelen of informatief`;
    const assessmentLabels = {
      action_required: "Actie vereist",
      retry: "Opnieuw proberen",
      review: "Beoordelen",
      informational: "Geen actuele impact",
    };
    $("#crawl-failure-list").innerHTML = failures.map((failure) => {
      const sources = failure.source_types.length ? failure.source_types.join(", ") : "alleen historisch bekend";
      return `<article class="crawl-failure-item"><a href="${escapeHtml(failure.requested_url)}" target="_blank" rel="noopener">${escapeHtml(failure.requested_url)}</a><span class="crawl-failure-assessment ${escapeHtml(failure.assessment)}">${assessmentLabels[failure.assessment] || "Beoordelen"}</span><strong>${escapeHtml(failure.error_message)}</strong><p>${escapeHtml(failure.explanation)}</p><p><b>Bron:</b> ${escapeHtml(sources)} · ${Number(failure.incoming_internal_links).toLocaleString("nl-NL")} inkomende interne links</p><p><b>Aanpak:</b> ${escapeHtml(failure.recommended_action)}</p></article>`;
    }).join("") || "<p>Voor deze crawl zijn geen mislukte URL’s opgeslagen.</p>";
  } catch (error) {
    $("#crawl-failure-title").textContent = "Fouten konden niet worden geladen";
    $("#crawl-failure-summary").textContent = error.message;
  }
}

function renderOperations() {
  renderSystemStatus();
  const runLabels = {light_check: "Light check", full_site_crawl: "Volledige crawl", fetch_sitemap: "Sitemap", full_page_analysis: "Pagina-analyse", recalculate_issues: "Acties herberekenen"};
  const visibleRuns = state.showCrawlArchive ? state.crawlRuns : state.crawlRuns.slice(0, 3);
  $("#crawl-run-rows").innerHTML = visibleRuns.map((run) => {
    const metrics = crawlRunMetrics(run);
    return `<tr><td>${new Date(run.started_at).toLocaleString("nl-NL")}</td><td>${runLabels[run.crawl_type] || escapeHtml(run.crawl_type)}</td><td><span class="run-status ${run.status}">${labels[run.status] || run.status}</span></td><td>${metrics.discovered} ${metrics.discoveredLabel.toLowerCase()}</td><td>${metrics.processed} ${metrics.processedLabel.toLowerCase()}</td><td>${crawlFailureButton(run)}</td><td>${durationLabel(run)}</td></tr>`;
  }).join("");
  $("#crawl-run-cards").innerHTML = visibleRuns.map((run) => {
    const metrics = crawlRunMetrics(run);
    return `<article class="crawl-run-card"><div><strong>${escapeHtml(runLabels[run.crawl_type] || run.crawl_type)}</strong><span class="run-status ${run.status}">${escapeHtml(labels[run.status] || run.status)}</span></div><time datetime="${escapeHtml(run.started_at)}">${new Date(run.started_at).toLocaleString("nl-NL")}</time><dl><div><dt>${metrics.processedLabel}</dt><dd>${metrics.processed}</dd></div><div><dt>${metrics.discoveredLabel}</dt><dd>${metrics.discovered}</dd></div><div><dt>Mislukt</dt><dd>${crawlFailureButton(run)}</dd></div><div><dt>Duur</dt><dd>${durationLabel(run)}</dd></div></dl></article>`;
  }).join("");
  $("#toggle-crawl-archive").classList.toggle("hidden", state.crawlRuns.length <= 3);
  $("#toggle-crawl-archive").textContent = state.showCrawlArchive
    ? "Toon alleen laatste 3"
    : `Toon archief (${state.crawlRuns.length - 3})`;
  $("#crawl-runs-empty").classList.toggle("hidden", state.crawlRuns.length !== 0);
  const activeRun = state.crawlRuns.find((run) => ["running", "paused", "pause_requested"].includes(run.status));
  const activeJob = state.activeCrawlJob;
  const pendingRun = activeJob?.status === "pending" ? {
    crawl_type: activeJob.job_type,
    status: "pending",
    crawled_urls: 0,
    failed_urls: 0,
  } : null;
  const controlledRun = activeRun || pendingRun || (state.crawlRuns[0]?.status === "failed" ? state.crawlRuns[0] : null);
  const crawlStatus = state.activeCrawlJob?.status || controlledRun?.status;
  const hasBlockingCrawlJob = ["waiting_for_capacity", "pending", "running", "pause_requested", "paused", "cancel_requested"]
    .includes(state.activeCrawlJob?.status);
  $("#crawl-live-status").classList.toggle("hidden", !controlledRun);
  $("#start-light-check").disabled = hasBlockingCrawlJob;
  $("#start-full-crawl").disabled = hasBlockingCrawlJob;
  $("#start-issue-recalculation").disabled = hasBlockingCrawlJob;
  if (controlledRun) {
    $("#crawl-live-state").textContent = labels[crawlStatus] || crawlStatus;
    $("#crawl-live-state").className = `process-status ${crawlStatus}`;
    const queueLabel = crawlStatus === "pending" && activeJob?.queue_position
      ? `Wachtrijpositie ${activeJob.queue_position} van ${activeJob.queue_depth}`
      : crawlProgressLabel(controlledRun);
    $("#crawl-live-label").textContent = `${runLabels[controlledRun.crawl_type] || controlledRun.crawl_type} · ${queueLabel}`;
  }
  $("#crawl-progress-track").classList.toggle("hidden", ["paused", "failed", "cancelled"].includes(crawlStatus));
  $("#pause-crawl").classList.toggle("hidden", crawlStatus !== "running");
  const failedRunHasProgress = crawlStatus === "failed"
    && Number(controlledRun?.crawled_urls || 0) + Number(controlledRun?.asset_urls || 0) > 0;
  $("#resume-crawl").classList.toggle("hidden", crawlStatus !== "paused" && !failedRunHasProgress);
  $("#cancel-crawl").classList.toggle("hidden", ["failed", "cancelled"].includes(crawlStatus));
  $("#cancel-crawl").disabled = ["cancel_requested", "cancelled"].includes(crawlStatus);
  const currentExport = state.exports.find((item) => !item.downloaded_at && ["pending", "running", "succeeded"].includes(item.status));
  const exportPanel = $("#current-export"); const exportButton = $("#generate-excel"); const download = $("#current-export-download");
  exportPanel.classList.toggle("hidden", !currentExport);
  exportButton.disabled = Boolean(currentExport);
  if (currentExport) {
    $("#current-export-state").textContent = labels[currentExport.status] || currentExport.status;
    $("#current-export-state").className = `process-status ${currentExport.status}`;
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
  if (jobType === "recalculate_issues" && !window.confirm("Acties herberekenen vanuit de laatste volledige crawl? Er worden geen pagina’s opnieuw gedownload.")) return;
  const buttons = {
    light_check: $("#start-light-check"),
    full_site_crawl: $("#start-full-crawl"),
    recalculate_issues: $("#start-issue-recalculation"),
  };
  const button = buttons[jobType];
  const message = $("#crawl-action-message");
  button.disabled = true; message.classList.remove("error"); message.textContent = "Crawl wordt ingepland…";
  try {
    const job = await api("/api/v1/crawl-jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({website_id: $("#website-select").value, job_type: jobType, settings_snapshot: {}})});
    const queueLabel = job.queue_position ? ` · wachtrijpositie ${job.queue_position} van ${job.queue_depth}` : "";
    const jobLabel = jobType === "light_check" ? "Light check" : jobType === "recalculate_issues" ? "Herberekening" : "Volledige crawl";
    message.textContent = `${jobLabel} is ingepland (${job.id.slice(0, 8)})${queueLabel}.`;
    setTimeout(loadOperations, 2000);
  } catch (error) { message.classList.add("error"); message.textContent = error.message; button.disabled = false; }
}

async function controlCrawl(action) {
  const job = state.activeCrawlJob;
  if (!job) return;
  if (action === "cancel" && !window.confirm("Crawl stoppen? Reeds opgeslagen resultaten blijven behouden.")) return;
  const message = $("#crawl-action-message");
  message.classList.remove("error");
  message.textContent = action === "pause" ? "Crawl wordt na de huidige URL gepauzeerd…" : action === "resume" ? "Crawl wordt vanaf de opgeslagen voortgang hervat…" : "Crawl wordt na de huidige URL gestopt…";
  try {
    state.activeCrawlJob = await api(`/api/v1/crawl-jobs/${job.id}/${action}`, {method: "POST"});
    await loadOperations();
  } catch (error) {
    message.classList.add("error"); message.textContent = error.message;
  }
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

function selectedText(selector, emptyLabel) {
  const element = $(selector);
  return element.value ? element.selectedOptions[0]?.textContent || element.value : emptyLabel;
}

async function startPageExport({buttonSelector, exportType, itemIds, filters}) {
  const button = $(buttonSelector);
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Export voorbereiden…";
  try {
    const created = await api("/api/v1/exports", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({website_id: $("#website-select").value, export_type: exportType, item_ids: itemIds, filters}),
    });
    let current = created;
    for (let attempt = 0; attempt < 120 && ["waiting_for_capacity", "pending", "running"].includes(current.status); attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      current = await api(`/api/v1/exports/${created.id}`);
    }
    if (current.status !== "succeeded") throw new Error(current.error_message || "Export kon niet worden afgerond");
    button.textContent = "Download start…";
    window.location.assign(`/api/v1/exports/${created.id}/download`);
  } catch (error) {
    window.alert(error.message);
  } finally {
    window.setTimeout(() => { button.disabled = false; button.textContent = original; }, 1000);
  }
}

function exportUrls() {
  startPageExport({
    buttonSelector: "#export-urls", exportType: "urls",
    itemIds: state.urlFiltered.map((url) => url.id),
    filters: {
      zoekopdracht: $("#url-search").value.trim() || "Geen",
      status: selectedText("#url-status-filter", "Alle statuscodes"),
      indexatie: selectedText("#url-index-filter", "Alle indexatiestatussen"),
      bron: selectedText("#url-source-filter", "Alle bronnen"),
      crawldiepte: selectedText("#url-depth-filter", "Alle crawl-dieptes"),
    },
  });
}

function exportTasks() {
  startPageExport({
    buttonSelector: "#export-tasks", exportType: "tasks",
    itemIds: state.recommendationTasks.map((task) => task.id),
    filters: {
      zoekopdracht: $("#task-search").value.trim() || "Geen",
      status: selectedText("#task-status-filter", "Alle open taken"),
      prioriteit: selectedText("#task-priority-filter", "Alle prioriteiten"),
      vakgebied: selectedText("#task-role-filter", "Alle vakgebieden"),
      eigenaar: selectedText("#task-owner-filter", "Iedereen"),
      controle: selectedText("#task-verification-filter", "Alle controles"),
    },
  });
}

function exportChanges() {
  startPageExport({
    buttonSelector: "#export-changes", exportType: "changes",
    itemIds: state.changeFiltered.flatMap((group) => group.changes.map((change) => change.id)),
    filters: {
      zoekopdracht: $("#change-search").value.trim() || "Geen",
      wijzigingstype: selectedText("#change-type-filter", "Alle wijzigingstypen"),
      periode: selectedText("#change-period-filter", "Volledige historie"),
    },
  });
}

function exportVacancies() {
  startPageExport({
    buttonSelector: "#export-vacancies", exportType: "vacancies",
    itemIds: state.vacancyFiltered.map((listing) => listing.id),
    filters: {
      zoekopdracht: $("#vacancy-search").value.trim() || "Geen",
      status: selectedText("#vacancy-status-filter", "Alle statussen"),
      validatie: selectedText("#vacancy-validation-filter", "Alle validaties"),
      snelkeuze: state.vacancyQuickFilter || "Geen",
    },
  });
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
  const requestId = ++state.changesRequestId;
  renderTableState("#change-rows", 5, "Wijzigingen worden geladen…");
  const changes = [];
  for (let offset = 0; ; offset += 1000) {
    const batch = await api(`/api/v1/websites/${websiteId}/changes?limit=1000&offset=${offset}`);
    if (requestId !== state.changesRequestId || websiteId !== $("#website-select").value) return;
    changes.push(...batch);
    if (batch.length < 1000) break;
  }
  state.changes = changes;
  state.changeGroups = groupChanges(state.changes);
  const selected = $("#change-type-filter").value;
  const types = [...new Set(state.changeGroups.flatMap((group) => group.changes.map((change) => change.change_type)))].sort();
  $("#change-type-filter").innerHTML = `<option value="">Alle wijzigingstypen</option>${types.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(changeLabel({change_type: type}))}</option>`).join("")}`;
  if (types.includes(selected)) $("#change-type-filter").value = selected;
  state.changePage = 1;
  renderChanges();
}

function renderTableState(selector, columns, message, error = false) {
  $(selector).innerHTML = `<tr class="table-state${error ? " error" : ""}" role="status"><td colspan="${columns}">${escapeHtml(message)}</td></tr>`;
}

function groupChanges(changes) {
  const groups = new Map();
  changes.filter((change) => !change.is_baseline && isMeaningfulChange(change)).forEach((change) => {
    const key = change.current_snapshot_id;
    if (!groups.has(key)) groups.set(key, {id: key, url_id: change.url_id, detected_at: change.detected_at, previous_checked_at: change.previous_checked_at, current_checked_at: change.current_checked_at, changes: []});
    groups.get(key).changes.push(change);
  });
  const regularGroups = [...groups.values()];
  const incidentGroups = new Map();
  const retainedGroups = [];
  regularGroups.forEach((group) => {
    const canonical = group.changes.find((change) => change.change_type === "canonical_changed");
    const hostSwap = canonical && canonicalHostSwap(canonical.old_value, canonical.new_value);
    if (!hostSwap || !canonical.current_crawl_run_id) {
      retainedGroups.push(group);
      return;
    }
    const hosts = [hostSwap.oldHost, hostSwap.newHost].sort();
    const key = `domain-swap:${canonical.current_crawl_run_id}:${hosts.join(":")}`;
    if (!incidentGroups.has(key)) {
      incidentGroups.set(key, {
        id: key,
        incident_type: "domain_swap",
        hosts,
        detected_at: group.detected_at,
        previous_checked_at: group.previous_checked_at,
        current_checked_at: group.current_checked_at,
        changes: [],
        affected_url_ids: new Set(),
      });
    }
    const incident = incidentGroups.get(key);
    incident.changes.push(...group.changes);
    incident.affected_url_ids.add(group.url_id);
    if (new Date(group.detected_at) > new Date(incident.detected_at)) incident.detected_at = group.detected_at;
  });
  const incidents = [...incidentGroups.values()].map((group) => ({
    ...group,
    affected_url_ids: [...group.affected_url_ids],
  }));
  return [...retainedGroups, ...incidents].sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at));
}

function canonicalHostSwap(oldValue, newValue) {
  try {
    const oldUrl = new URL(String(oldValue || ""));
    const newUrl = new URL(String(newValue || ""));
    if (oldUrl.hostname === newUrl.hostname) return null;
    if (`${oldUrl.pathname}${oldUrl.search}${oldUrl.hash}` !== `${newUrl.pathname}${newUrl.search}${newUrl.hash}`) return null;
    return {oldHost: oldUrl.hostname, newHost: newUrl.hostname};
  } catch (_error) {
    return null;
  }
}

function changeGroupLabel(group) {
  if (group.incident_type === "domain_swap") {
    return `Websitebrede domeinverwisseling: ${group.hosts.join(" ↔ ")} · ${group.affected_url_ids.length} URL’s`;
  }
  const uniqueChanges = [...new Map(group.changes.map((change) => [change.change_type, change])).values()];
  if (uniqueChanges.length === 1) return changeLabel(uniqueChanges[0]);
  const priority = [
    "new_url", "disappeared_url", "redirect_target_changed", "status_code_changed",
    "indexability_changed", "robots_changed", "canonical_changed", "title_changed",
    "h1_changed", "description_changed", "main_content_changed",
    "internal_links_changed", "structured_data_changed",
  ];
  const dominant = [...uniqueChanges].sort((a, b) => {
    const rank = (change) => {
      const index = priority.indexOf(change.change_type);
      return index === -1 ? priority.length : index;
    };
    return rank(a) - rank(b);
  })[0];
  let dominantLabel = changeLabel(dominant);
  if (dominant.change_type === "redirect_target_changed") {
    try {
      const target = new URL(String(dominant.new_value || ""));
      if (target.pathname === "/" && !target.search && !target.hash) {
        dominantLabel = "Redirectbestemming gewijzigd naar homepage";
      }
    } catch (_error) {
      // Een niet-URL-waarde houdt de algemene omschrijving.
    }
  }
  return `${dominantLabel} · ${uniqueChanges.length - 1} afhankelijke ${uniqueChanges.length === 2 ? "wijziging" : "wijzigingen"}`;
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
  $("#change-rows").innerHTML = rows.map((group) => {
    const url = group.incident_type === "domain_swap"
      ? `${group.affected_url_ids.length} geraakte URL’s`
      : state.urls.get(group.url_id) || "Onbekende URL";
    const parts = [...new Set(group.changes.map(changeLabel))];
    const importance = group.changes.some((change) => change.importance === "high") ? "high" : group.changes.some((change) => change.importance === "medium") ? "medium" : "low";
    const urlCell = group.incident_type === "domain_swap"
      ? `<span class="change-url">${escapeHtml(url)}</span>`
      : `<a class="change-url" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>`;
    return `<tr><td><time datetime="${escapeHtml(group.detected_at)}">${new Date(group.detected_at).toLocaleString("nl-NL")}</time></td><td>${urlCell}</td><td><div class="change-row-summary"><span class="change-kind">${escapeHtml(changeGroupLabel(group))}</span><span class="change-importance ${importance}"><small>Relevantie</small>${escapeHtml(labels[importance])}</span></div></td><td><span class="change-parts">${parts.length}</span></td><td><button class="detail-button" data-change-group-id="${group.id}">Bekijk</button></td></tr>`;
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
  if (group.incident_type === "domain_swap") {
    const affectedUrls = group.affected_url_ids.map((urlId) => state.urls.get(urlId) || "Onbekende URL").sort();
    $("#change-detail-title").textContent = "Websitebrede domeinverwisseling";
    $("#change-detail-url").textContent = `${affectedUrls.length} geraakte URL’s`;
    $("#change-detail-url").removeAttribute("href");
    const previousDate = group.previous_checked_at ? new Date(group.previous_checked_at).toLocaleString("nl-NL") : "Geen eerdere meting";
    const currentDate = group.current_checked_at ? new Date(group.current_checked_at).toLocaleString("nl-NL") : new Date(group.detected_at).toLocaleString("nl-NL");
    $("#change-detail-date").textContent = `${previousDate} → ${currentDate}`;
    $("#change-detail-relevance").textContent = "Canonical, structured data en interne links verwijzen bij meerdere pagina’s gelijktijdig naar een ander domein. Dit wijst op een tenant-, cache- of hostconfiguratie-incident.";
    $("#change-detail-action").textContent = `Controleer de host- en cacheconfiguratie tussen ${group.hosts.join(" en ")}. Bevestig daarna met een nieuwe crawl dat alle pagina’s stabiel het juiste domein gebruiken.`;
    $("#change-detail-summary").textContent = `${group.changes.length} onderliggende wijzigingen op ${affectedUrls.length} URL’s zijn samengevoegd tot één incident.`;
    $("#change-detail-summary").classList.remove("hidden");
    $("#change-group-details").innerHTML = `<section class="change-detail-part"><h3>Geraakte URL’s</h3><p class="change-value">${affectedUrls.map(escapeHtml).join("<br>")}</p></section>`;
    $("#change-dialog").showModal();
    return;
  }
  const changes = await Promise.all(group.changes.map((change) => api(`/api/v1/changes/${change.id}`)));
  const url = state.urls.get(group.url_id) || "Onbekende URL";
  $("#change-detail-title").textContent = changeGroupLabel(group);
  $("#change-detail-url").textContent = url;
  $("#change-detail-url").href = url;
  const previousDate = group.previous_checked_at ? new Date(group.previous_checked_at).toLocaleString("nl-NL") : "Geen eerdere meting";
  const currentDate = group.current_checked_at ? new Date(group.current_checked_at).toLocaleString("nl-NL") : new Date(group.detected_at).toLocaleString("nl-NL");
  $("#change-detail-date").textContent = `${previousDate} → ${currentDate}`;
  $("#change-detail-relevance").textContent = [...new Set(changes.map((change) => change.relevance))].join("\n");
  $("#change-detail-action").textContent = [...new Set(changes.map((change) => change.review_action))].join("\n");
  $("#change-detail-summary").textContent = `${changes.length} betekenisvolle onderdelen zijn bij dezelfde meting gewijzigd.`;
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
  const scope = $("#scope-filter").value;
  const nature = $("#nature-filter").value;
  const type = $("#type-filter").value;
  const impact = $("#impact-filter").value;
  const status = $("#status-filter").value;
  state.filtered = state.issues.filter((issue) => {
    const statusMatch = status === "all" || (status === "active" ? ACTIVE_STATUSES.has(issue.status) : issue.status === status);
    const searchText = `${issue.title} ${issue.issue_type} ${issueUrlLabel(issue)}`.toLowerCase();
    return statusMatch && (!severity || issue.severity === severity) && (!scope || issue.scope === scope) && (!nature || issue.nature === nature) && (!type || issue.issue_type === type) && (!impact || impactLevel(issue) === impact) && (!query || searchText.includes(query));
  }).sort((a, b) => ({high: 0, medium: 1, low: 2}[a.severity] - {high: 0, medium: 1, low: 2}[b.severity] || impactRank(a) - impactRank(b) || impactVolume(b) - impactVolume(a) || new Date(b.last_detected_at) - new Date(a.last_detected_at)));
}

function renderGroups() {
  const query = $("#search-filter").value.trim().toLowerCase();
  const severity = $("#severity-filter").value;
  const scope = $("#scope-filter").value;
  const nature = $("#nature-filter").value;
  const impact = $("#impact-filter").value;
  const status = $("#status-filter").value;
  const counts = new Map();
  state.issues.forEach((issue) => {
    const statusMatch = status === "all" || (status === "active" ? ACTIVE_STATUSES.has(issue.status) : issue.status === status);
    const searchText = `${issue.title} ${issue.issue_type} ${issueUrlLabel(issue)}`.toLowerCase();
    if (statusMatch && (!severity || issue.severity === severity) && (!scope || issue.scope === scope) && (!nature || issue.nature === nature) && (!impact || impactLevel(issue) === impact) && (!query || searchText.includes(query))) counts.set(issue.issue_type, (counts.get(issue.issue_type) || 0) + 1);
  });
  $("#issue-groups").innerHTML = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)
    .map(([type, count]) => `<button data-group-type="${escapeHtml(type)}"><strong>${count}</strong><span>${escapeHtml(type.replaceAll("_", " "))}</span></button>`).join("");
}

function render() {
  renderIntegrationWarning();
  renderClientReport();
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
    <td class="selection-cell"><input class="issue-select" type="checkbox" data-select-issue-id="${issue.id}" aria-label="Selecteer ${escapeHtml(issue.title)}" ${state.selectedIssueIds.has(issue.id) ? "checked" : ""}></td>
    <td><span class="severity ${issue.severity}">${labels[issue.severity] || issue.severity}</span></td>
    <td><strong>${escapeHtml(issue.title)}</strong><span class="issue-classification"><span class="issue-scope ${escapeHtml(issue.scope)}">${escapeHtml(issueScopeLabels[issue.scope] || issue.scope)}</span><span class="issue-nature ${escapeHtml(issue.nature)}">${escapeHtml(issueNatureLabels[issue.nature] || issue.nature)}</span></span>${issueUrlMarkup(issue)}</td>
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
  const pageIds = rows.map((issue) => issue.id);
  const selectedOnPage = pageIds.filter((id) => state.selectedIssueIds.has(id)).length;
  $("#select-page-issues").checked = pageIds.length > 0 && selectedOnPage === pageIds.length;
  $("#select-page-issues").indeterminate = selectedOnPage > 0 && selectedOnPage < pageIds.length;
  renderIssueBulkBar();
  renderSuppressions();
  if (state.currentView === "dashboard") renderDashboard();
}

function renderIssueBulkBar() {
  const selected = state.selectedIssueIds.size;
  $("#issue-selection-count").textContent = `${selected} geselecteerd`;
  $("#resolve-selected-issues").disabled = selected === 0;
  $("#wont-fix-selected-issues").disabled = selected === 0;
  $("#suppress-selected-issues").disabled = selected === 0;
  $("#clear-issue-selection").disabled = selected === 0;
}

function renderSuppressions() {
  $("#suppression-rows").innerHTML = state.suppressions.map((suppression) => {
    const url = state.urls.get(suppression.url_id) || "Onbekende URL";
    return `<tr><td class="selection-cell"><input class="suppression-select" type="checkbox" data-select-suppression-id="${suppression.id}" aria-label="Selecteer afgehandelde regel" ${state.selectedSuppressionIds.has(suppression.id) ? "checked" : ""}></td><td><strong>${escapeHtml(suppression.issue_type.replaceAll("_", " "))}</strong><a class="url" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a></td><td>${escapeHtml(suppression.actor || "Systeem")}</td><td>${escapeHtml(suppression.comment || "—")}</td><td>${new Date(suppression.updated_at).toLocaleDateString("nl-NL")}</td><td><button class="detail-button" type="button" data-restore-suppression="${suppression.id}">Herstellen</button></td></tr>`;
  }).join("");
  $("#suppression-empty").classList.toggle("hidden", state.suppressions.length !== 0);
  const selected = state.selectedSuppressionIds.size;
  $("#suppression-selection-count").textContent = `${selected} regels geselecteerd`;
  $("#restore-selected-suppressions").disabled = selected === 0;
  $("#select-suppressions").checked = state.suppressions.length > 0 && selected === state.suppressions.length;
  $("#select-suppressions").indeterminate = selected > 0 && selected < state.suppressions.length;
}

async function runIssueBulkAction(action) {
  const issueIds = [...state.selectedIssueIds];
  if (!issueIds.length) return;
  const selectedIssues = state.issues.filter((issue) => state.selectedIssueIds.has(issue.id));
  if (action === "suppress_issue_type" && selectedIssues.some((issue) => !issue.url_id)) {
    window.alert("Een websitebrede diagnose kan niet blijvend per URL worden afgehandeld. Verwijder deze uit de selectie.");
    return;
  }
  const actionLabel = action === "suppress_issue_type"
    ? "blijvend afhandelen voor het geselecteerde issuetype"
    : action === "wont_fix"
      ? "afsluiten als Won’t fix (risico geaccepteerd)"
      : "als opgelost markeren en bij de volgende crawl opnieuw controleren";
  if (!window.confirm(`${issueIds.length} issue(s) ${actionLabel}?`)) return;
  const websiteId = $("#website-select").value;
  const comment = $("#issue-bulk-comment").value.trim();
  const message = $("#issue-bulk-message");
  message.classList.remove("error");
  message.textContent = "Actie wordt verwerkt…";
  try {
    const result = await api(`/api/v1/websites/${websiteId}/issues/bulk`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({issue_ids: issueIds, action, comment: comment || null}),
    });
    $("#issue-bulk-comment").value = "";
    await loadIssues();
    message.textContent = action === "suppress_issue_type"
      ? `${result.updated_count} issue(s) blijvend afgehandeld voor dit issuetype.`
      : action === "wont_fix"
        ? `${result.updated_count} issue(s) afgesloten als Won’t fix.`
        : `${result.updated_count} issue(s) opgelost en klaargezet voor hercontrole.`;
  } catch (error) {
    message.classList.add("error");
    message.textContent = `Actie mislukt: ${error.message}`;
  }
}

async function restoreSuppression(suppressionId) {
  if (!window.confirm("Deze regel herstellen? Het issue wordt weer zichtbaar en bij volgende crawls opnieuw beoordeeld.")) return;
  const websiteId = $("#website-select").value;
  const message = $("#issue-bulk-message");
  message.classList.remove("error");
  message.textContent = "Regel wordt hersteld…";
  try {
    await api(`/api/v1/websites/${websiteId}/issue-suppressions/${suppressionId}/restore`, {method: "POST"});
    await loadIssues();
    message.textContent = "De afgehandelde regel is hersteld en het issue is weer zichtbaar.";
  } catch (error) {
    message.classList.add("error");
    message.textContent = `Herstellen mislukt: ${error.message}`;
  }
}

async function restoreSelectedSuppressions() {
  const suppressionIds = [...state.selectedSuppressionIds];
  if (!suppressionIds.length || !window.confirm(`${suppressionIds.length} afgehandelde regel(s) herstellen?`)) return;
  const websiteId = $("#website-select").value;
  const message = $("#issue-bulk-message");
  message.classList.remove("error");
  message.textContent = "Geselecteerde regels worden hersteld…";
  try {
    for (const suppressionId of suppressionIds) {
      await api(`/api/v1/websites/${websiteId}/issue-suppressions/${suppressionId}/restore`, {method: "POST"});
    }
    await loadIssues();
    message.textContent = `${suppressionIds.length} afgehandelde regel(s) hersteld.`;
  } catch (error) {
    message.classList.add("error");
    message.textContent = `Herstellen mislukt: ${error.message}`;
    await loadIssues();
  }
}

async function showIssue(issueId) {
  state.selectedIssueId = issueId;
  state.selectedInspectionSnapshotId = null;
  state.selectedRecommendationTask = null;
  state.recommendationFeedback = [];
  $("#issue-context-question").value = "";
  $("#issue-context-answer").innerHTML = "";
  $("#issue-inspection").classList.add("hidden");
  $("#issue-inspection-content").innerHTML = "";
  $("#issue-inspection-message").textContent = "";
  $("#issue-inspection-recheck").classList.add("hidden");
  const summary = state.issues.find((item) => item.id === issueId);
  $("#detail-title").textContent = summary?.title || "Issuedetail";
  const summaryUrl = summary ? issueUrl(summary) : "";
  $("#detail-url").textContent = summaryUrl || "Websitebreed issue";
  if (summaryUrl) $("#detail-url").href = summaryUrl; else $("#detail-url").removeAttribute("href");
  $("#detail-impact").classList.add("hidden");
  $("#issue-detail-content").classList.add("hidden");
  $("#issue-detail-loading").classList.remove("hidden");
  $("#issue-detail-loading strong").textContent = "Details worden geladen…";
  $("#issue-dialog").showModal();
  let issue;
  try {
    issue = await api(`/api/v1/issues/${issueId}`);
  } catch (error) {
    $("#issue-detail-loading .loading-spinner").classList.add("hidden");
    $("#issue-detail-loading strong").textContent = `Laden mislukt: ${error.message}`;
    return;
  }
  if (!issue) return;
  $("#issue-detail-loading .loading-spinner").classList.remove("hidden");
  $("#issue-detail-loading").classList.add("hidden");
  $("#issue-detail-content").classList.remove("hidden");
  $("#detail-title").textContent = issue.title;
  const url = issueUrl(issue); $("#detail-url").textContent = url || "Websitebreed issue";
  if (url) $("#detail-url").href = url; else $("#detail-url").removeAttribute("href");
  $("#detail-severity").textContent = `${labels[issue.severity] || issue.severity} · ${issueScopeLabels[issue.scope] || issue.scope} · ${issueNatureLabels[issue.nature] || issue.nature}`;
  $("#detail-status").value = issue.status;
  $("#client-status-label").textContent = labels[issue.status] || issue.status;
  $("#detail-description").textContent = issue.description;
  const guidance = issue.guidance;
  $("#detail-relevance").textContent = guidance.relevance.text;
  $("#detail-guidance-sources").innerHTML = (guidance.sources || []).map((source) => `<li><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a><span>${escapeHtml(source.publisher)}</span></li>`).join("");
  $("#guidance-sources-section").classList.toggle("hidden", !(guidance.sources || []).length);
  $("#detail-cause-section").classList.toggle("hidden", !guidance.likely_cause);
  $("#detail-alternative-section").classList.toggle("hidden", !guidance.alternative_explanation);
  $("#detail-cause").textContent = guidance.likely_cause?.text || "";
  $("#detail-alternative").textContent = guidance.alternative_explanation?.text || "";
  $("#detail-steps").innerHTML = guidance.steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("");
  $("#detail-verification").textContent = guidance.verification;
  const basisLabels = {fact: "Feitelijke meting", interpretation: "Systeeminterpretatie", hypothesis: "Hypothese"};
  if (guidance.likely_cause) {
    $("#detail-cause-basis").className = `basis-badge ${guidance.likely_cause.basis}`;
    $("#detail-cause-basis").textContent = basisLabels[guidance.likely_cause.basis];
  }
  const elementLabels = {a: "Link", button: "Knop", h1: "H1-kop", h2: "H2-kop", h3: "H3-kop", img: "Afbeelding"};
  $("#detail-element-locations").innerHTML = (issue.elements || []).map((element) => `<article class="element-location"><strong>${escapeHtml(elementLabels[element.element_type] || element.element_type)}${element.occurrence_index > 1 ? ` ${element.occurrence_index}` : ""}</strong>${element.visible_text ? `<p>${escapeHtml(element.visible_text)}</p>` : ""}${element.target_url ? `<p class="element-target">Doel: ${escapeHtml(element.target_url)}</p>` : ""}<div class="element-actions"><a class="detail-button" href="${escapeHtml(element.source_url)}" target="_blank" rel="noopener">Open bronpagina</a>${element.jump_url ? `<a class="detail-button location-button" href="${escapeHtml(element.jump_url)}" target="_blank" rel="noopener">Toon locatie</a>` : ""}</div><details><summary>Technisch fragment</summary><dl><div><dt>CSS-selector</dt><dd><code>${escapeHtml(element.css_selector || "Niet beschikbaar")}</code></dd></div><div><dt>XPath</dt><dd><code>${escapeHtml(element.xpath || "Niet beschikbaar")}</code></dd></div></dl><pre>${escapeHtml(element.html_fragment)}</pre>${element.text_prefix || element.text_suffix ? `<p>Context: ${escapeHtml(element.text_prefix || "")} <mark>${escapeHtml(element.visible_text || "element")}</mark> ${escapeHtml(element.text_suffix || "")}</p>` : ""}</details></article>`).join("");
  $("#element-locations-section").classList.toggle("hidden", !(issue.elements || []).length);
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
  const brokenLinks = Array.isArray(issue.evidence.broken_links) ? issue.evidence.broken_links : [];
  $("#broken-links-heading").textContent = `Dode doelen op deze bronpagina (${brokenLinks.length})`;
  $("#detail-broken-links").innerHTML = brokenLinks.map((link) => `<li><span class="evidence-item-label">Doel-URL</span><a href="${escapeHtml(link.target_url)}" target="_blank" rel="noopener">${escapeHtml(link.target_url)}</a><span>Ankertekst: ${escapeHtml(link.anchor_text || "(geen ankertekst)")} · HTTP-status ${escapeHtml(link.status_code || 404)}</span></li>`).join("");
  $("#broken-links-section").classList.toggle("hidden", brokenLinks.length === 0);
  const vacancyClusters = Array.isArray(issue.evidence.clusters) ? issue.evidence.clusters : [];
  $("#detail-vacancy-clusters").innerHTML = vacancyClusters.map((cluster, index) => `<section><strong>Cluster ${index + 1}: ${escapeHtml(cluster.group_size)} vacatures</strong><p>Minimale inhoudsoverlap: ${escapeHtml(cluster.minimum_content_overlap_percent)}%</p><ul>${cluster.urls.map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a></li>`).join("")}</ul></section>`).join("");
  $("#vacancy-clusters-section").classList.toggle("hidden", vacancyClusters.length === 0);
  const urlPatterns = Array.isArray(issue.evidence.patterns) ? issue.evidence.patterns : [];
  $("#detail-url-patterns").innerHTML = urlPatterns.map((pattern) => `<section><strong>${escapeHtml(pattern.pattern)}</strong><p>${escapeHtml(pattern.url_count)} URL’s · ${pattern.pattern_type === "pagination" ? "paginering" : "parameters/filter"}</p><ul>${pattern.urls.map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a></li>`).join("")}</ul></section>`).join("");
  $("#url-patterns-section").classList.toggle("hidden", urlPatterns.length === 0);
  renderIssueEvidence(issue.evidence || {});
  const sourceUrls = issue.source_urls || [];
  $("#source-heading").textContent = `Bronpagina’s met dit signaal (${sourceUrls.length})`;
  $("#detail-sources").innerHTML = sourceUrls.map((source) => `<li><a href="${escapeHtml(source)}" target="_blank" rel="noopener">${escapeHtml(source)}</a></li>`).join("");
  $("#source-section").classList.toggle("hidden", sourceUrls.length === 0);
  await loadIssueInspection(issue.id);
  await loadIssueRecommendation(issue);
}

function inspectionTargetMarkup(target) {
  const kind = target.kind === "missing" ? "missing" : "located";
  const title = kind === "missing" ? "Element ontbreekt" : target.label;
  const locator = target.locator ? `${target.locator.strategy.toUpperCase()}: ${target.locator.value}` : "Geen betrouwbare locator beschikbaar";
  return `<article class="inspection-target ${kind}"><strong>${escapeHtml(title)}</strong>${target.visible_text ? `<p>${escapeHtml(target.visible_text)}</p>` : ""}<p>${escapeHtml(locator)}</p></article>`;
}

function inspectionOverlayMarkup(target, page) {
  if (!target.box || !page.screenshot_width || !page.screenshot_height) return "";
  const left = Math.max(0, Math.min(100, target.box.x / page.screenshot_width * 100));
  const top = Math.max(0, Math.min(100, target.box.y / page.screenshot_height * 100));
  const width = Math.max(0, Math.min(100 - left, target.box.width / page.screenshot_width * 100));
  const height = Math.max(0, Math.min(100 - top, target.box.height / page.screenshot_height * 100));
  return `<span class="inspection-overlay" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%" aria-hidden="true"></span>`;
}

function inspectionLiveStatusMarkup(page) {
  if (page.render_source !== "live_recheck" || page.live_target_status === "not_checked") return "";
  const statuses = {
    found: ["found", "Element live gevonden"],
    not_found: ["not-found", "Element live niet gevonden"],
    ambiguous: ["ambiguous", "Meerdere live matches"],
    inconclusive: ["inconclusive", "Live locatie niet vastgesteld"],
    present: ["found", "Element is live aanwezig"],
    missing_confirmed: ["not-found", "Element ontbreekt live nog"],
  };
  const [className, label] = statuses[page.live_target_status] || statuses.inconclusive;
  return `<span class="inspection-live-status ${className}">${label}</span>`;
}

async function loadIssueInspection(issueId) {
  const section = $("#issue-inspection");
  const content = $("#issue-inspection-content");
  try {
    const inspection = await api(`/api/v1/issues/${issueId}/inspection`);
    section.classList.remove("hidden");
    const recheckButton = $("#issue-inspection-recheck");
    const canRecheck = inspection.live_recheck_available && ["superuser", "admin"].includes(state.currentUser?.role);
    recheckButton.classList.toggle("hidden", !canRecheck);
    const selectedPage = inspection.pages.find((page) => page.snapshot_id === state.selectedInspectionSnapshotId)
      || inspection.pages.find((page) => page.is_current_occurrence)
      || inspection.pages[0];
    state.selectedInspectionSnapshotId = selectedPage?.snapshot_id || null;
    const busy = selectedPage && ["pending", "running"].includes(selectedPage.render_status);
    recheckButton.disabled = busy;
    recheckButton.textContent = busy ? "Live controle loopt…" : "Live opnieuw controleren";
    const statusLabels = {available:"Exact elementbewijs",limited:"Beperkt bewijs",unavailable:"Geen visueel bewijs"};
    $("#issue-inspection-status").textContent = statusLabels[inspection.availability] || inspection.availability;
    if (!inspection.pages.length) {
      content.innerHTML = `<p class="inspection-empty">Voor dit issue is geen historische paginaweergave beschikbaar. Gebruik het technische bewijs hierboven.</p>`;
      return;
    }
    const selectedIndex = inspection.pages.indexOf(selectedPage);
    const pageNavigation = inspection.pages.length > 1 ? `<div class="inspection-page-navigation"><label for="issue-inspection-page-select">Bronpagina</label><select id="issue-inspection-page-select">${inspection.pages.map((page, index) => `<option value="${escapeHtml(page.snapshot_id)}" ${index === selectedIndex ? "selected" : ""}>${index + 1}. ${escapeHtml(page.source_url)}</option>`).join("")}</select><span>${selectedIndex + 1} van ${inspection.pages.length}</span></div>` : "";
    content.innerHTML = `${pageNavigation}<article class="inspection-page"><div class="inspection-meta"><span>${selectedPage.render_source === "live_recheck" && selectedPage.rendered_at ? `Live weergegeven ${new Date(selectedPage.rendered_at).toLocaleString("nl-NL")}` : `Gemeten ${new Date(selectedPage.captured_at).toLocaleString("nl-NL")}`}</span><span>${selectedPage.is_current_occurrence ? "Actuele issuewaarneming" : "Eerdere waarneming"}</span>${inspectionLiveStatusMarkup(selectedPage)}</div>${selectedPage.screenshot_url ? `<div class="inspection-frame"><img src="${escapeHtml(selectedPage.screenshot_url)}" alt="Historische schermweergave van ${escapeHtml(selectedPage.source_url)}">${selectedPage.targets.map((target) => inspectionOverlayMarkup(target, selectedPage)).join("")}</div>` : `<p class="inspection-empty">Van dit meetmoment is geen schermweergave bewaard.</p>`}<div class="inspection-targets">${selectedPage.targets.map(inspectionTargetMarkup).join("")}</div></article>`;
    return inspection;
  } catch (error) {
    section.classList.remove("hidden");
    $("#issue-inspection-status").textContent = "Niet beschikbaar";
    content.innerHTML = `<p class="inspection-empty">De historische inspectie kon niet worden geladen.</p>`;
    return null;
  }
}

async function startIssueInspectionRecheck() {
  const issueId = state.selectedIssueId;
  if (!issueId) return;
  const button = $("#issue-inspection-recheck");
  const message = $("#issue-inspection-message");
  button.disabled = true;
  message.textContent = "Live controle wordt gestart…";
  try {
    const selectedPage = state.selectedInspectionSnapshotId ? `?snapshot_id=${encodeURIComponent(state.selectedInspectionSnapshotId)}` : "";
    await api(`/api/v1/issues/${issueId}/inspection/recheck${selectedPage}`, {method:"POST"});
    message.textContent = "Live controle loopt. De historische weergave blijft zichtbaar.";
    pollIssueInspection(issueId, 0);
  } catch (error) {
    message.textContent = error.message;
    button.disabled = false;
  }
}

function pollIssueInspection(issueId, attempt) {
  if (attempt >= 40 || state.selectedIssueId !== issueId) return;
  window.setTimeout(async () => {
    if (state.selectedIssueId !== issueId) return;
    const inspection = await loadIssueInspection(issueId);
    if (!inspection) return;
    const busy = inspection.pages.some((page) => ["pending", "running"].includes(page.render_status));
    if (busy) pollIssueInspection(issueId, attempt + 1);
    else $("#issue-inspection-message").textContent = inspection.pages.some((page) => page.render_status === "failed") ? "Live controle is mislukt; het historische bewijs blijft beschikbaar." : "Live controle afgerond.";
  }, 3000);
}

async function loadIssueRecommendation(issue) {
  const content = $("#recommendation-task-content");
  const message = $("#recommendation-task-message");
  content.innerHTML = '<p class="task-loading">Taakgegevens worden geladen…</p>';
  message.textContent = "";
  try {
    const definitionsPromise = state.recommendationDefinitions
      ? Promise.resolve(state.recommendationDefinitions)
      : api("/api/v1/recommendation-types");
    const membersPromise = ["superuser", "admin"].includes(state.currentUser?.role)
      ? api(`/api/v1/clients/${$("#client-select").value}/members`).catch(() => [])
      : Promise.resolve([]);
    const [tasks, definitions, members] = await Promise.all([
      api(`/api/v1/websites/${issue.website_id}/recommendation-tasks?status=all`),
      definitionsPromise,
      membersPromise,
    ]);
    if (state.selectedIssueId !== issue.id) return;
    state.recommendationDefinitions = definitions;
    state.taskMembers = members;
    const taskSummary = tasks.find((task) => task.primary_issue_id === issue.id) || null;
    if (taskSummary) {
      const taskId = taskSummary.id;
      [
        state.selectedRecommendationTask,
        state.recommendationFeedback,
        state.recommendationVerificationPlan,
        state.recommendationVerifications,
      ] = await Promise.all([
        api(`/api/v1/recommendation-tasks/${taskId}`),
        api(`/api/v1/recommendation-tasks/${taskId}/feedback`),
        api(`/api/v1/recommendation-tasks/${taskId}/verification-plan`),
        api(`/api/v1/recommendation-tasks/${taskId}/verifications`),
      ]);
    } else {
      state.selectedRecommendationTask = null;
      state.recommendationFeedback = [];
      state.recommendationVerificationPlan = null;
      state.recommendationVerifications = [];
    }
    if (state.selectedIssueId !== issue.id) return;
    const supported = definitions.some((definition) => definition.source_issue_types.includes(issue.issue_type));
    renderRecommendationTask(issue, supported);
  } catch (error) {
    content.innerHTML = `<p class="task-loading">Taakgegevens konden niet worden geladen: ${escapeHtml(error.message)}</p>`;
  }
}

function renderRecommendationTask(issue, supported = true) {
  const task = state.selectedRecommendationTask;
  const content = $("#recommendation-task-content");
  const canWrite = state.currentUser?.role !== "client";
  if (!task) {
    const explanation = supported
      ? "Maak van deze diagnose een concrete uitvoeringstaak met stappen, rol, tijdsindicatie en gereedcriteria."
      : "Voor dit diagnosetype is nog geen gestandaardiseerde uitvoeringstaak beschikbaar.";
    content.innerHTML = `<div class="task-empty"><p>${explanation}</p>${supported && canWrite ? '<button id="create-recommendation-task" class="primary-button" type="button">Maak uitvoeringstaak</button>' : ""}</div>`;
    return;
  }
  const effort = task.effort_min_minutes === null
    ? "Nog niet ingeschat"
    : `${task.effort_min_minutes}–${task.effort_max_minutes} min`;
  const transitions = TASK_TRANSITIONS[task.status] || [];
  const statusOptions = [task.status, ...transitions]
    .map((value) => `<option value="${value}">${escapeHtml(taskStatusLabels[value] || value)}</option>`)
    .join("");
  const assigneeOptions = `<option value="">Niet toegewezen</option>${taskAssigneeOptions().map((member) => `<option value="${member.id}" ${member.id === task.assigned_to_user_id ? "selected" : ""}>${escapeHtml(member.display_name || member.email)}${member.id === state.currentUser?.id ? " (jij)" : ""}</option>`).join("")}`;
  const nextStep = task.feasibility === "needs_decision"
    ? ["Neem eerst een besluit", task.required_input[0] || "Bepaal welke uitkomst voor deze pagina bedoeld is."]
    : ({
    open: ["Bepaal wie dit oppakt", "Plan de taak of zet deze op ‘In uitvoering’ zodra het werk begint."],
    planned: ["Start de uitvoering", "Zet de taak op ‘In uitvoering’ wanneer iemand ermee begint."],
    in_progress: ["Rond het werk af", "Voer de stappen uit en meld de taak daarna als ‘Uitgevoerd’."],
    waiting_for_input: ["Lever de ontbrekende input", "Zet de taak terug op ‘Gepland’ of ‘In uitvoering’ zodra de blokkade is opgelost."],
    implemented: ["Controle loopt automatisch", "SEO Monitor controleert de uitvoering en werkt de taak daarna zelf bij."],
    closed: ["Geen actie nodig", "Deze taak is afgesloten. Heropen haar alleen wanneer opnieuw werk nodig is."],
  }[task.status] || ["Bepaal de volgende stap", "Werk de taakstatus bij zodra de situatie verandert."]);
  const controls = canWrite
    ? `<section class="task-panel task-controls-panel"><div class="task-section-heading"><span>03</span><div><small>Werk bijwerken</small><h4>Kies eigenaar en taakstatus</h4></div></div><div class="task-controls"><label>Eigenaar<select id="recommendation-task-owner">${assigneeOptions}</select><small>Laat leeg zolang nog niet bekend is wie de taak oppakt.</small></label><label>Nieuwe status<select id="recommendation-task-status">${statusOptions}</select></label><label class="task-comment">Korte toelichting<textarea id="recommendation-task-comment" maxlength="2000" placeholder="Optioneel, behalve bij heropenen"></textarea></label><label id="task-close-reason-label" class="task-close-reason hidden">Waarom wordt de taak afgesloten?<select id="recommendation-task-close-reason">${Object.entries(closeReasonLabels).map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`).join("")}</select></label><button id="save-recommendation-task" class="primary-button" type="button" disabled>Taak bijwerken</button></div></section>`
    : "";
  const latestFeedback = state.recommendationFeedback[0];
  const feedbackSummary = latestFeedback
    ? `<div class="task-feedback-summary"><strong>Laatste feedback</strong><span>${latestFeedback.actual_minutes === null ? "Geen tijd ingevuld" : `${latestFeedback.actual_minutes} minuten`} · ${escapeHtml({easy:"Makkelijker dan verwacht",expected:"Zoals verwacht",hard:"Moeilijker dan verwacht",blocked:"Geblokkeerd"}[latestFeedback.difficulty] || "Geen moeilijkheid ingevuld")} · ${new Date(latestFeedback.created_at).toLocaleDateString("nl-NL")}</span></div>`
    : "";
  const feedbackForm = canWrite && ["implemented", "closed"].includes(task.status)
    ? `<form id="recommendation-feedback-form" class="task-feedback-form"><h4>Uitvoeringsfeedback</h4><p>Deze gegevens blijven klantgebonden. Vrije opmerkingen worden nooit klantoverstijgend gebruikt.</p><div class="task-feedback-fields"><label>Werkelijke tijd (minuten)<input id="feedback-actual-minutes" type="number" min="0" max="100000"></label><label>Moeilijkheid<select id="feedback-difficulty"><option value="">Niet ingevuld</option><option value="easy">Makkelijker dan verwacht</option><option value="expected">Zoals verwacht</option><option value="hard">Moeilijker dan verwacht</option><option value="blocked">Geblokkeerd</option></select></label><label>Instructie bruikbaar<select id="feedback-helpful"><option value="">Niet ingevuld</option><option value="true">Ja</option><option value="false">Nee</option></select></label><label>Eindbeoordeling<select id="feedback-assessment"><option value="completed">Voltooid</option><option value="partially_completed">Deels voltooid</option><option value="not_completed">Niet voltooid</option></select></label><label class="task-feedback-check"><input id="feedback-missing-input" type="checkbox"> Benodigde input ontbrak</label><label class="task-feedback-check"><input id="feedback-missing-dependency" type="checkbox"> Afhankelijkheid was onduidelijk</label><label class="task-feedback-notes">Toelichting<textarea id="feedback-notes" maxlength="2000" placeholder="Optioneel en alleen binnen deze klant zichtbaar"></textarea></label></div><button class="primary-button" type="submit">Feedback opslaan</button></form>`
    : "";
  const verification = renderTaskVerification(canWrite);
  const decision = task.required_input.length
    ? `<section class="task-decision"><span>Eerst beslissen</span><strong>${escapeHtml(task.required_input[0])}</strong><div><p><b>Ja:</b> geef de pagina een logische, crawlbare plek in de sitestructuur.</p><p><b>Nee:</b> voeg haar samen of redirect haar en werk daarna de sitemap bij.</p></div></section>`
    : "";
  const nextStepPanel = decision
    ? ""
    : `<section class="task-next-step" aria-label="Volgende stap"><span>Volgende stap</span><div><strong>${escapeHtml(nextStep[0])}</strong><p>${escapeHtml(nextStep[1])}</p></div></section>`;
  content.innerHTML = `<article class="task-card"><header class="task-card-head"><div><span class="task-kicker">Aanbevolen uitvoering</span><h3>${escapeHtml(task.title)}</h3><div class="task-meta"><span>${escapeHtml(taskRoleLabels[task.primary_role] || task.primary_role)}</span><span>${escapeHtml(effort)}</span><span class="task-priority ${escapeHtml(task.priority)}">${escapeHtml(labels[task.priority] || task.priority)} prioriteit</span></div></div><span class="task-status status-${escapeHtml(task.status)}">${escapeHtml(taskStatusLabels[task.status] || task.status)}</span></header>${nextStepPanel}${decision}<div class="task-columns"><section class="task-panel"><div class="task-section-heading"><span>01</span><h4>Wat moet ik doen?</h4></div><ol>${task.steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol></section><section class="task-panel task-criteria"><div class="task-section-heading"><span>02</span><h4>Wanneer is het klaar?</h4></div><ul>${task.acceptance_criteria.map((criterion) => `<li>${escapeHtml(criterion)}</li>`).join("")}</ul></section></div>${controls}${verification}${feedbackSummary}${feedbackForm}</article>`;
}

function renderTaskVerification(canWrite) {
  const task = state.selectedRecommendationTask;
  const plan = state.recommendationVerificationPlan;
  const verifications = state.recommendationVerifications || [];
  if (!plan?.supported) return "";
  const latest = verifications[0];
  const verificationActive = latest && ["queued", "running"].includes(latest.status);
  const outcomeLabels = {
    resolved: "Opgelost",
    probably_resolved: "Waarschijnlijk opgelost",
    partially_resolved: "Deels opgelost",
    not_resolved: "Niet opgelost",
    manual_review_required: "Handmatige controle nodig",
  };
  const ruleLabels = {passed: "Geslaagd", failed: "Niet geslaagd", error: "Niet controleerbaar"};
  const blockingExplanation = verificationActive
    ? "De controle loopt. Je kunt dit venster sluiten en later terugkomen."
    : task.status !== "implemented"
      ? "Meld de taak eerst als ‘Uitgevoerd’. Daarna kan SEO Monitor het resultaat controleren."
      : plan.missing_roles.length
        ? "De controle mist nog een pagina. Open de technische controlegegevens om deze toe te voegen."
        : "SEO Monitor controleert alleen de betrokken pagina’s en verandert geen andere gegevens.";
  const scope = `<p class="verification-note ${plan.missing_roles.length ? "warning" : ""}">${escapeHtml(blockingExplanation)}</p>`;
  const result = latest?.result?.outcome
    ? `<div class="verification-result"><strong>${escapeHtml(outcomeLabels[latest.result.outcome] || latest.result.outcome)}</strong><span>${new Date(latest.finished_at || latest.created_at).toLocaleString("nl-NL")}</span></div><details class="verification-proof"><summary>Controlebewijs bekijken</summary><ul class="verification-rules">${latest.rules.map((rule) => `<li class="${escapeHtml(rule.status)}"><span aria-hidden="true"></span><div><strong>${escapeHtml(rule.rule.replaceAll("_", " ").split(":")[0])}</strong><small>${escapeHtml(ruleLabels[rule.status] || rule.status)}</small></div></li>`).join("")}</ul></details>`
    : latest
      ? `<div class="verification-result pending"><strong>${escapeHtml({queued:"In wachtrij",running:"Controle wordt uitgevoerd",error:"Controle mislukt"}[latest.status] || latest.status)}</strong><span>De pagina kan later opnieuw worden geopend voor het resultaat.</span></div>`
      : "";
  const roleLabels = {
    source: "Bronpagina",
    broken_target: "Defect doel",
    replacement_target: "Vervangend doel",
    expected_target: "Verwacht einddoel",
    expected_canonical: "Verwachte canonical",
    target: "Redirect-URL",
    old: "Oude URL",
    new: "Nieuwe URL",
    changed: "Te controleren pagina",
  };
  const scopeRows = (task.urls || []).map((item) => `<li><div><strong>${escapeHtml(roleLabels[item.role] || item.role)}</strong><a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noopener">${escapeHtml(item.url || item.url_id)}</a></div>${canWrite ? `<button class="task-scope-remove" type="button" data-task-url-id="${escapeHtml(item.id)}" aria-label="Verwijder ${escapeHtml(roleLabels[item.role] || item.role)}">×</button>` : ""}</li>`).join("");
  const optionalRoles = {
    repair_broken_internal_link: ["replacement_target"],
    replace_redirected_internal_link: ["expected_target"],
    restore_or_redirect_missing_page: ["new"],
    add_or_correct_title: ["sample"],
    add_primary_heading: ["sample"],
    add_meta_description: ["sample"],
    repair_structured_data: ["sample"],
  }[task.recommendation_type] || [];
  const allowedRoles = [...new Set([...plan.required_roles, ...((task.urls || []).map((item) => item.role)), ...optionalRoles])];
  const scopeEditor = `<details class="task-scope" ${plan.missing_roles.length ? "open" : ""}><summary>Technische controlegegevens${plan.missing_roles.length ? " aanvullen" : " bekijken"}</summary><p class="task-scope-summary">${plan.url_count} pagina${plan.url_count === 1 ? "" : "’s"} in deze controle</p><ul>${scopeRows || "<li>Geen URL’s vastgelegd.</li>"}</ul>${canWrite ? `<form id="task-scope-form"><label>Functie van de pagina<select id="task-scope-role">${allowedRoles.map((role) => `<option value="${escapeHtml(role)}">${escapeHtml(roleLabels[role] || role)}</option>`).join("")}</select></label><label class="task-scope-url">Pagina-URL<input id="task-scope-url" type="url" required placeholder="https://voorbeeld.nl/pagina"></label><button class="detail-button" type="submit">Pagina toevoegen</button></form>` : ""}</details>`;
  const manualRetry = ["error", "manual_review"].includes(task.verification_status);
  const button = canWrite && manualRetry
    ? `<button id="start-recommendation-verification" class="detail-button verification-button" type="button" ${plan.can_request && !verificationActive ? "" : "disabled"}>Controle opnieuw proberen</button>`
    : "";
  return `<section class="task-panel task-verification"><div class="task-verification-head"><div class="task-section-heading"><span>04</span><div><small>Na de uitvoering</small><h4>Automatische controle</h4></div></div>${button}</div>${scope}${scopeEditor}${result}</section>`;
}

async function startRecommendationVerification() {
  const task = state.selectedRecommendationTask;
  if (!task) return;
  const button = $("#start-recommendation-verification");
  const message = $("#recommendation-task-message");
  if (button) button.disabled = true;
  message.textContent = "Gerichte controle wordt ingepland…";
  try {
    const verification = await api(`/api/v1/recommendation-tasks/${task.id}/verifications`, {method: "POST"});
    state.recommendationVerifications = [verification, ...(state.recommendationVerifications || [])];
    state.recommendationVerificationPlan = {...state.recommendationVerificationPlan, can_request: false};
    renderRecommendationTask(state.issues.find((issue) => issue.id === state.selectedIssueId));
    message.textContent = "Gerichte controle staat in de wachtrij.";
  } catch (error) {
    message.textContent = `Controle starten mislukt: ${error.message}`;
    if (button) button.disabled = false;
  }
}

async function saveTaskScope(event) {
  event.preventDefault();
  const task = state.selectedRecommendationTask;
  if (!task) return;
  const message = $("#recommendation-task-message");
  message.textContent = "URL wordt toegevoegd…";
  try {
    await api(`/api/v1/recommendation-tasks/${task.id}/urls`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        role: $("#task-scope-role").value,
        url: $("#task-scope-url").value.trim(),
      }),
    });
    await loadIssueRecommendation(state.issues.find((issue) => issue.id === state.selectedIssueId));
    message.textContent = "URL-scope bijgewerkt.";
  } catch (error) {
    message.textContent = `URL toevoegen mislukt: ${error.message}`;
  }
}

async function removeTaskScope(taskUrlId) {
  const task = state.selectedRecommendationTask;
  if (!task) return;
  const message = $("#recommendation-task-message");
  message.textContent = "URL wordt verwijderd…";
  try {
    await api(`/api/v1/recommendation-tasks/${task.id}/urls/${taskUrlId}`, {method: "DELETE"});
    await loadIssueRecommendation(state.issues.find((issue) => issue.id === state.selectedIssueId));
    message.textContent = "URL uit de verificatiescope verwijderd.";
  } catch (error) {
    message.textContent = `URL verwijderen mislukt: ${error.message}`;
  }
}

async function createRecommendationTask() {
  if (!state.selectedIssueId) return;
  const message = $("#recommendation-task-message");
  message.textContent = "Taak wordt aangemaakt…";
  try {
    await api(`/api/v1/issues/${state.selectedIssueId}/recommendation-task`, {method: "POST"});
    await loadIssueRecommendation(state.issues.find((issue) => issue.id === state.selectedIssueId));
    message.textContent = "Uitvoeringstaak aangemaakt.";
  } catch (error) {
    message.textContent = `Aanmaken mislukt: ${error.message}`;
  }
}

async function saveRecommendationTask() {
  const task = state.selectedRecommendationTask;
  if (!task) return;
  const status = $("#recommendation-task-status").value;
  const comment = $("#recommendation-task-comment").value.trim();
  const message = $("#recommendation-task-message");
  if (task.status === "closed" && status === "open" && !comment) {
    message.textContent = "Geef een toelichting om een afgesloten taak te heropenen.";
    return;
  }
  const owner = $("#recommendation-task-owner").value;
  const payload = {status, assigned_to_user_id: owner || null, comment: comment || null};
  if (status === "closed") payload.close_reason = $("#recommendation-task-close-reason").value;
  message.textContent = "Taak wordt bijgewerkt…";
  try {
    await api(`/api/v1/recommendation-tasks/${task.id}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    await loadIssueRecommendation(state.issues.find((issue) => issue.id === state.selectedIssueId));
    message.textContent = "Taak bijgewerkt.";
  } catch (error) {
    message.textContent = `Bijwerken mislukt: ${error.message}`;
  }
}

async function saveRecommendationFeedback(event) {
  event.preventDefault();
  const task = state.selectedRecommendationTask;
  if (!task) return;
  const minutes = $("#feedback-actual-minutes").value;
  const difficulty = $("#feedback-difficulty").value;
  const helpful = $("#feedback-helpful").value;
  const payload = {
    actual_minutes: minutes === "" ? null : Number(minutes),
    difficulty: difficulty || null,
    instruction_helpful: helpful === "" ? null : helpful === "true",
    missing_input: $("#feedback-missing-input").checked,
    missing_dependency: $("#feedback-missing-dependency").checked,
    final_assessment: $("#feedback-assessment").value,
    notes: $("#feedback-notes").value.trim() || null,
  };
  const message = $("#recommendation-task-message");
  message.textContent = "Feedback wordt opgeslagen…";
  try {
    const feedback = await api(`/api/v1/recommendation-tasks/${task.id}/feedback`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    state.recommendationFeedback.unshift(feedback);
    renderRecommendationTask(state.issues.find((issue) => issue.id === state.selectedIssueId));
    message.textContent = "Feedback opgeslagen.";
  } catch (error) {
    message.textContent = `Opslaan mislukt: ${error.message}`;
  }
}

const evidenceLabels = {
  affected_url_count: "Getroffen URL’s",
  application_cta_active: "Sollicitatieknop actief",
  affected_source_pages: "Getroffen bronpagina’s",
  canonical: "Canonieke URL",
  content_level: "Inhoudsniveau",
  count: "Aantal",
  crawl_depth: "Crawldiepte",
  element_count: "Betrokken elementen",
  failed_url_count: "Mislukte URL’s",
  document_count: "Documenten",
  oversized_document_count: "Grote documenten",
  affected_image_count: "Afbeeldingen met aandachtspunt",
  oversized_image_count: "Grote afbeeldingen",
  media_file_count: "Mediabestanden",
  large_media_count: "Grote mediabestanden",
  embed_count: "Embeds met aandachtspunt",
  media_markup_count: "Media-opmaakcontroles",
  group_size: "Omvang van de groep",
  generic_link_count: "Generieke interne links",
  broken_link_count: "Daarvan dode links",
  in_sitemap: "Opgenomen in sitemap",
  incoming_internal_links: "Inkomende interne links",
  limit: "Ingestelde limiet",
  minimum_content_overlap_percent: "Minimale inhoudsoverlap",
  page_count: "Betrokken pagina’s",
  redirect_count: "Redirects",
  response_size: "Responsgrootte",
  source_page_count: "Unieke bronpagina’s",
  status_code: "HTTP-status",
  target_count: "Unieke doel-URL’s",
  target_url: "Doel-URL",
  url: "URL",
  url_count: "Getroffen URL’s",
  validThrough: "Geldig tot",
  visible_closing_date: "Zichtbare sluitingsdatum",
};
const evidenceSummaryPriority = ["status_code", "source_page_count", "affected_source_pages", "document_count", "oversized_document_count", "affected_image_count", "oversized_image_count", "media_file_count", "large_media_count", "embed_count", "page_count", "url_count", "affected_url_count", "target_count", "group_size", "generic_link_count", "broken_link_count", "element_count", "incoming_internal_links", "crawl_depth"];
const evidencePresentationKeys = new Set(["alternative_explanation", "broken_links", "clusters", "likely_cause", "patterns", "verification"]);

function evidenceLabel(key) {
  if (evidenceLabels[key]) return evidenceLabels[key];
  return key.replaceAll("_", " ").replace(/^\w/, (character) => character.toUpperCase());
}

function evidenceValue(value) {
  if (value === null || value === undefined || value === "") return "Niet beschikbaar";
  if (typeof value === "boolean") return value ? "Ja" : "Nee";
  if (typeof value === "number") return new Intl.NumberFormat("nl-NL").format(value);
  return String(value);
}

function evidenceValueHtml(value) {
  if (Array.isArray(value)) {
    if (!value.length) return '<span class="evidence-empty">Geen waarden</span>';
    return `<ul>${value.map((item) => `<li>${evidenceValueHtml(item)}</li>`).join("")}</ul>`;
  }
  if (value && typeof value === "object") {
    return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
  }
  const formatted = evidenceValue(value);
  if (typeof value === "string" && /^https?:\/\//.test(value)) {
    return `<a href="${escapeHtml(value)}" target="_blank" rel="noopener">${escapeHtml(value)}</a>`;
  }
  return escapeHtml(formatted);
}

function renderIssueEvidence(rawEvidence) {
  const entries = Object.entries(rawEvidence).filter(([key]) => !evidencePresentationKeys.has(key));
  const entryMap = new Map(entries);
  const summaryEntries = evidenceSummaryPriority
    .filter((key) => entryMap.has(key) && !Array.isArray(entryMap.get(key)) && typeof entryMap.get(key) !== "object")
    .slice(0, 4)
    .map((key) => [key, entryMap.get(key)]);
  if (!summaryEntries.length) {
    summaryEntries.push(...entries.filter(([, value]) => !Array.isArray(value) && (value === null || typeof value !== "object")).slice(0, 4));
  }
  $("#detail-evidence-summary").innerHTML = summaryEntries.length
    ? summaryEntries.map(([key, value]) => `<article><span>${escapeHtml(evidenceLabel(key))}</span><strong>${escapeHtml(evidenceValue(value))}</strong></article>`).join("")
    : '<p class="evidence-empty">Geen aanvullend technisch bewijs opgeslagen.</p>';
  $("#detail-evidence").innerHTML = entries.length
    ? entries.map(([key, value]) => `<div><dt>${escapeHtml(evidenceLabel(key))}</dt><dd>${evidenceValueHtml(value)}</dd></div>`).join("")
    : '<div><dd class="evidence-empty">Geen aanvullende technische details.</dd></div>';
  $("#detail-evidence-technical").open = false;
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

async function markIssueWontFix() {
  if (!state.selectedIssueId) return;
  if (!window.confirm("Dit issue afsluiten als Won’t fix? Het wordt geregistreerd als geaccepteerd risico.")) return;
  $("#detail-status").value = "accepted_risk";
  await saveIssueStatus();
}

$("#logout").addEventListener("click", async () => { await fetch("/ui/logout", { method: "POST" }); window.location.assign("/"); });
async function openMfaSetup() {
  const setup = await api("/api/v1/me/mfa/setup", {method:"POST"});
  $("#mfa-qr-code").src = setup.qr_code_data_uri;
  $("#mfa-secret").value = setup.secret;
  $("#mfa-recovery-codes").textContent = setup.recovery_codes.join("\n");
  $("#mfa-message").textContent = "Bewaar de herstelcodes voordat je activeert.";
  $("#mfa-dialog").showModal();
}
$("#setup-mfa").addEventListener("click", () => openMfaSetup().catch((error) => { alert(error.message); }));
$("#confirm-mfa").addEventListener("click", async () => {
  try {
    await api("/api/v1/me/mfa/confirm", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({code:$("#mfa-confirm-code").value})});
    state.currentUser.mfa_enabled = true; state.currentUser.mfa_required = false;
    $("#mfa-message").textContent = "Tweestapsverificatie is actief.";
    await loadClients();
    showView(viewFromHash(), false);
    window.setTimeout(() => $("#mfa-dialog").close(), 800);
  } catch (error) { $("#mfa-message").textContent = error.message; }
});
$("#profile-toggle").addEventListener("click", () => { const open = $("#profile-popover").classList.toggle("hidden") === false; $("#profile-toggle").setAttribute("aria-expanded", String(open)); });
$("#mobile-nav-toggle").addEventListener("click", () => { const open = $("#app").classList.toggle("mobile-nav-open"); $("#mobile-nav-toggle").setAttribute("aria-expanded", String(open)); });
$("#client-select").addEventListener("change", async () => { localStorage.setItem(CLIENT_STORAGE_KEY, $("#client-select").value); localStorage.removeItem(WEBSITE_STORAGE_KEY); state.crawlRuns = []; state.changesRequestId += 1; state.changes = []; state.changeGroups = []; await loadWebsites(); if (state.currentView === "integrations") await loadIntegrations(); if (state.currentView === "dashboard") await loadDashboard(); });
$("#website-select").addEventListener("change", async () => { localStorage.setItem(WEBSITE_STORAGE_KEY, $("#website-select").value); state.selectedReportSnapshotId = null; state.consultantInsights = null; state.contentAnalysis = null; state.questionScopes = null; state.externalEvidenceRequests.clear(); state.contentAnalysisPage = 1; state.operationsRequestId += 1; state.changesRequestId += 1; state.operationsLoading = false; state.crawlRuns = []; state.showCrawlArchive = false; state.activeCrawlJob = null; state.exports = []; state.changes = []; state.changeGroups = []; if (state.currentView === "changes") renderTableState("#change-rows", 5, "Wijzigingen worden geladen…"); if (state.currentView === "operations") renderOperations(); if (state.currentView === "changes") await loadChanges(); await loadIssues(); if (state.currentView === "integrations") await loadIntegrations(); if (state.currentView === "insights") await loadConsultantInsights(); if (["contentAnalysis", "opportunities"].includes(state.currentView)) await loadContentAnalysis(); if (state.currentView === "urls") renderUrls(); if (state.currentView === "vacancies") await loadJobListings(); if (state.currentView === "operations") await loadOperations(); if (state.currentView === "dashboard") await loadDashboard(); });
for (const selector of ["#severity-filter", "#scope-filter", "#nature-filter", "#type-filter", "#impact-filter"]) $(selector).addEventListener("change", () => { state.page = 1; render(); });
$("#status-filter").addEventListener("change", loadIssues);
$("#search-filter").addEventListener("input", () => { state.page = 1; render(); });
$("#previous-page").addEventListener("click", () => { state.page -= 1; render(); });
$("#next-page").addEventListener("click", () => { state.page += 1; render(); });
$("#issues").addEventListener("click", (event) => { const button = event.target.closest("[data-issue-id]"); if (button) showIssue(button.dataset.issueId); });
$("#issues").addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-select-issue-id]");
  if (!checkbox) return;
  if (checkbox.checked) state.selectedIssueIds.add(checkbox.dataset.selectIssueId);
  else state.selectedIssueIds.delete(checkbox.dataset.selectIssueId);
  renderIssueBulkBar();
  const pageCheckboxes = [...document.querySelectorAll("#issues .issue-select")];
  const selectedOnPage = pageCheckboxes.filter((item) => item.checked).length;
  $("#select-page-issues").checked = pageCheckboxes.length > 0 && selectedOnPage === pageCheckboxes.length;
  $("#select-page-issues").indeterminate = selectedOnPage > 0 && selectedOnPage < pageCheckboxes.length;
});
$("#select-page-issues").addEventListener("change", (event) => {
  document.querySelectorAll("#issues .issue-select").forEach((checkbox) => {
    checkbox.checked = event.target.checked;
    if (event.target.checked) state.selectedIssueIds.add(checkbox.dataset.selectIssueId);
    else state.selectedIssueIds.delete(checkbox.dataset.selectIssueId);
  });
  renderIssueBulkBar();
});
$("#select-filtered-issues").addEventListener("click", () => { state.filtered.forEach((issue) => state.selectedIssueIds.add(issue.id)); render(); });
$("#clear-issue-selection").addEventListener("click", () => { state.selectedIssueIds.clear(); render(); });
$("#resolve-selected-issues").addEventListener("click", () => runIssueBulkAction("resolve_and_recheck"));
$("#wont-fix-selected-issues").addEventListener("click", () => runIssueBulkAction("wont_fix"));
$("#suppress-selected-issues").addEventListener("click", () => runIssueBulkAction("suppress_issue_type"));
$("#toggle-suppressions").addEventListener("click", (event) => {
  const show = $("#suppression-panel").classList.contains("hidden");
  $("#suppression-panel").classList.toggle("hidden", !show);
  event.currentTarget.setAttribute("aria-expanded", String(show));
  event.currentTarget.textContent = show ? "Afgehandelde regels verbergen" : "Afgehandelde regels bekijken";
});
$("#suppression-rows").addEventListener("click", (event) => { const button = event.target.closest("[data-restore-suppression]"); if (button) restoreSuppression(button.dataset.restoreSuppression); });
$("#suppression-rows").addEventListener("change", (event) => { const checkbox = event.target.closest("[data-select-suppression-id]"); if (!checkbox) return; if (checkbox.checked) state.selectedSuppressionIds.add(checkbox.dataset.selectSuppressionId); else state.selectedSuppressionIds.delete(checkbox.dataset.selectSuppressionId); renderSuppressions(); });
$("#select-suppressions").addEventListener("change", (event) => { state.selectedSuppressionIds.clear(); if (event.target.checked) state.suppressions.forEach((suppression) => state.selectedSuppressionIds.add(suppression.id)); renderSuppressions(); });
$("#select-all-suppressions").addEventListener("click", () => { state.suppressions.forEach((suppression) => state.selectedSuppressionIds.add(suppression.id)); renderSuppressions(); });
$("#restore-selected-suppressions").addEventListener("click", restoreSelectedSuppressions);
$("#issue-groups").addEventListener("click", (event) => { const button = event.target.closest("[data-group-type]"); if (button) { $("#type-filter").value = button.dataset.groupType; state.page = 1; render(); } });
$("#report-periods").addEventListener("click", async (event) => { const button = event.target.closest("[data-report-period]"); if (!button) return; state.reportPeriod = button.dataset.reportPeriod; $("#report-periods").querySelectorAll("button").forEach((item) => { const active = item === button; item.classList.toggle("active", active); item.setAttribute("aria-pressed", String(active)); }); state.clientReport = null; renderClientReport(); await loadClientReport(); });
$("#report-archive").addEventListener("click", async (event) => {
  const snapshot = event.target.closest("[data-report-snapshot]");
  if (snapshot) { state.selectedReportSnapshotId = snapshot.dataset.reportSnapshot; await loadClientReport(); await loadReportSnapshots(); return; }
  if (event.target.closest("[data-report-live]")) { state.selectedReportSnapshotId = null; await loadClientReport(); await loadReportSnapshots(); }
});
$("#close-dialog").addEventListener("click", () => { $("#issue-dialog").close(); state.selectedRecommendationTask = null; });
for (const dialog of document.querySelectorAll("dialog")) dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
$("#save-status").addEventListener("click", saveIssueStatus);
$("#wont-fix-issue").addEventListener("click", markIssueWontFix);
$("#recommendation-task-content").addEventListener("click", (event) => {
  if (event.target.closest("#create-recommendation-task")) createRecommendationTask();
  if (event.target.closest("#save-recommendation-task")) saveRecommendationTask();
  if (event.target.closest("#start-recommendation-verification")) startRecommendationVerification();
  const removeScope = event.target.closest("[data-task-url-id]");
  if (removeScope) removeTaskScope(removeScope.dataset.taskUrlId);
});
$("#recommendation-task-content").addEventListener("change", (event) => {
  if (!event.target.closest("#recommendation-task-status, #recommendation-task-owner")) return;
  const status = $("#recommendation-task-status").value;
  const owner = $("#recommendation-task-owner").value || null;
  $("#task-close-reason-label").classList.toggle("hidden", status !== "closed");
  $("#save-recommendation-task").disabled = status === state.selectedRecommendationTask?.status && owner === state.selectedRecommendationTask?.assigned_to_user_id;
});
$("#recommendation-task-content").addEventListener("submit", (event) => {
  if (event.target.closest("#recommendation-feedback-form")) saveRecommendationFeedback(event);
  if (event.target.closest("#task-scope-form")) saveTaskScope(event);
});
$("#dashboard-nav").addEventListener("click", () => showView("dashboard"));
$("#tasks-nav").addEventListener("click", () => showView("tasks"));
$("#actions-nav").addEventListener("click", () => showView("actions"));
$("#reports-nav").addEventListener("click", () => showView("reports"));
$("#insights-nav").addEventListener("click", () => showView("insights"));
$("#opportunities-nav").addEventListener("click", () => showView("opportunities"));
$("#content-analysis-nav").addEventListener("click", () => showView("contentAnalysis"));
$("#urls-nav").addEventListener("click", () => showView("urls"));
$("#changes-nav").addEventListener("click", () => showView("changes"));
$("#vacancies-nav").addEventListener("click", () => showView("vacancies"));
$("#operations-nav").addEventListener("click", () => showView("operations"));
$("#clients-nav").addEventListener("click", () => showView("clients"));
$("#team-nav").addEventListener("click", () => showView("team"));
$("#integrations-nav").addEventListener("click", () => showView("integrations"));
$("#issue-inspection-recheck").addEventListener("click", startIssueInspectionRecheck);
$("#issue-inspection-content").addEventListener("change", (event) => {
  if (event.target.id !== "issue-inspection-page-select") return;
  state.selectedInspectionSnapshotId = event.target.value;
  loadIssueInspection(state.selectedIssueId);
});
$("#save-external-evidence-controls").addEventListener("click", saveExternalEvidenceControls);
$("#notification-toggle").addEventListener("click", () => { const open = $("#notification-popover").classList.toggle("hidden") === false; $("#notification-toggle").setAttribute("aria-expanded", String(open)); });
$("#notification-all-tasks").addEventListener("click", () => { $("#notification-popover").classList.add("hidden"); $("#notification-toggle").setAttribute("aria-expanded", "false"); showView("tasks"); });
$("#notification-list").addEventListener("click", (event) => { const button = event.target.closest("[data-notification-id]"); if (button) openTaskNotification(button.dataset.notificationId, button.dataset.taskId); });
for (const selector of ["#task-status-filter", "#task-priority-filter", "#task-role-filter", "#task-owner-filter", "#task-verification-filter"]) $(selector).addEventListener("change", loadTaskCenter);
let taskSearchTimer = null;
$("#task-search").addEventListener("input", () => { window.clearTimeout(taskSearchTimer); taskSearchTimer = window.setTimeout(loadTaskCenter, 250); });
$("#task-list").addEventListener("click", (event) => { const button = event.target.closest("[data-task-issue-id]"); if (button?.dataset.taskIssueId) showIssue(button.dataset.taskIssueId); });
for (const group of ["analysis", "settings"]) $(`#${group}-nav`).addEventListener("click", () => { const subnav = $(`#${group}-subnav`); const open = subnav.classList.toggle("hidden") === false; $(`#${group}-nav`).setAttribute("aria-expanded", String(open)); });
$(".dashboard-grid").addEventListener("click", (event) => { const button = event.target.closest("[data-dashboard-view]"); if (button) showView(button.dataset.dashboardView); });
$("#dashboard-priorities").addEventListener("click", (event) => {
  const button = event.target.closest("[data-dashboard-priority]");
  if (!button) return;
  $("#severity-filter").value = button.dataset.dashboardPriority;
  state.page = 1;
  showView("actions");
  render();
});
$("#integration-warning-action").addEventListener("click", () => showView("integrations"));
$("#insight-period").addEventListener("change", async (event) => { state.insightDays = Number(event.target.value); await loadConsultantInsights(); });
$("#performance-context-question-form").addEventListener("submit", submitPerformanceContextQuestion);
$("#content-analysis-period").addEventListener("change", async (event) => { state.contentAnalysisDays = Number(event.target.value); state.contentAnalysisPage = 1; await loadContentAnalysis(); });
$("#content-analysis-tabs").addEventListener("click", (event) => { const button = event.target.closest("[data-content-tab]"); if (!button) return; if (state.currentView === "opportunities" && button.dataset.contentTab !== "opportunities") showView("contentAnalysis"); showContentAnalysisTab(button.dataset.contentTab); });
$("#content-question-list").addEventListener("click", (event) => { const taskButton = event.target.closest("[data-question-gap-task]"); if (taskButton) { const row = taskButton.closest(".question-scope-row"); const viewButton = row?.querySelector("[data-view-question-evidence]"); if (viewButton) createQuestionGapTask(viewButton.dataset.viewQuestionEvidence, taskButton.dataset.questionGapTask); return; } const viewButton = event.target.closest("[data-view-question-evidence]"); if (viewButton) { viewQuestionEvidence(viewButton.dataset.viewQuestionEvidence); return; } const button = event.target.closest("[data-question-evidence]"); if (button) requestQuestionEvidence(button.dataset.questionEvidence); });
$("#content-page-previous").addEventListener("click", () => { state.contentAnalysisPage -= 1; renderContentAnalysis(); });
$("#content-page-next").addEventListener("click", () => { state.contentAnalysisPage += 1; renderContentAnalysis(); });
$("#content-opportunity-list").addEventListener("click", (event) => { const scoredButton = event.target.closest("[data-opportunity-evaluation]"); if (scoredButton) { createScoredOpportunityTask(scoredButton.dataset.opportunityEvaluation); return; } const button = event.target.closest("[data-content-opportunity]"); if (button) createContentOpportunityTask(button.dataset.contentOpportunity); });
$("#content-opportunity-list").addEventListener("submit", (event) => { const form = event.target.closest(".context-question-form"); if (!form) return; event.preventDefault(); const context = form.closest("[data-context-type]"); submitContextQuestion(form, context.dataset.contextType, context.dataset.contextId); });
$("#evaluate-opportunities").addEventListener("click", evaluateScoredOpportunities);
$("#issue-context-question-form").addEventListener("submit", (event) => { event.preventDefault(); if (state.selectedIssueId) submitContextQuestion(event.currentTarget, "issue", state.selectedIssueId); });
$("#content-settings-form").addEventListener("submit", saveContentSettings);
$("#onboarding-form").addEventListener("submit", onboardClient);
$("#website-onboarding-form").addEventListener("submit", startWebsiteOnboarding);
$("#download-verification-file").addEventListener("click", downloadWebsiteVerificationFile);
$("#check-website-verification").addEventListener("click", checkWebsiteVerification);
$("#first-crawl-preferences").addEventListener("submit", startFirstOnboardingCrawl);
$("#restart-website-onboarding").addEventListener("click", restartWebsiteOnboarding);
$("#retry-first-crawl").addEventListener("click", retryFirstOnboardingCrawl);
$("#view-first-results").addEventListener("click", viewFirstOnboardingResults);
$("#configure-onboarding-measurement").addEventListener("click", configureOnboardingMeasurement);
$("#website-form").addEventListener("submit", createWebsite);
$("#invitation-form").addEventListener("submit", createInvitation);
$("#invitation-client").addEventListener("change", loadMembers);
function handleMemberRoleChange(event) { const select = event.target.closest(".member-role"); if (select) updateMemberRole(select.dataset.memberId, select.value); }
function handleMemberClick(event) { const button = event.target.closest(".member-remove"); if (button) removeMember(button.dataset.memberId, button.dataset.memberEmail); }
for (const selector of ["#member-rows", "#member-cards"]) {
  $(selector).addEventListener("change", handleMemberRoleChange);
  $(selector).addEventListener("click", handleMemberClick);
}
$("#client-directory-search").addEventListener("input", renderClientDirectory);
function handleClientDirectoryClick(event) {
  const open = event.target.closest(".client-open"); if (open) { openClient(open.dataset.clientId); return; }
  const save = event.target.closest(".client-save"); if (save) { saveClient(save.dataset.clientId, save.closest("tr, article").querySelector(".client-name-input")); return; }
  const remove = event.target.closest(".client-delete"); if (remove) deleteClient(remove.dataset.clientId, remove.dataset.clientName);
}
for (const selector of ["#client-rows", "#client-cards"]) $(selector).addEventListener("click", handleClientDirectoryClick);
$("#copy-invitation").addEventListener("click", async () => { await navigator.clipboard.writeText($("#invitation-link").value); $("#invitation-form-message").textContent = "Link gekopieerd."; });
for (const selector of ["#url-status-filter", "#url-index-filter", "#url-source-filter", "#url-depth-filter"]) $(selector).addEventListener("change", () => { state.urlPage = 1; renderUrls(); });
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
for (const selector of ["#vacancy-status-filter", "#vacancy-validation-filter"]) $(selector).addEventListener("change", () => { state.vacancyQuickFilter = null; renderJobListings(); });
$("#vacancy-search").addEventListener("input", () => { state.vacancyQuickFilter = null; renderJobListings(); });
$("#vacancy-rows").addEventListener("click", (event) => { const button = event.target.closest("[data-issue-id]"); if (button) showIssue(button.dataset.issueId); });
$("#vacancy-dashboard-stats").addEventListener("click", (event) => { const button = event.target.closest("[data-vacancy-filter]"); if (button) openVacanciesWithFilter(button.dataset.vacancyFilter); });
$("#open-vacancies").addEventListener("click", () => openVacanciesWithFilter());
$("#close-change-dialog").addEventListener("click", () => $("#change-dialog").close());
$("#start-light-check").addEventListener("click", () => startCrawl("light_check"));
$("#start-full-crawl").addEventListener("click", () => startCrawl("full_site_crawl"));
$("#start-issue-recalculation").addEventListener("click", () => startCrawl("recalculate_issues"));
$("#pause-crawl").addEventListener("click", () => controlCrawl("pause"));
$("#resume-crawl").addEventListener("click", () => controlCrawl("resume"));
$("#cancel-crawl").addEventListener("click", () => controlCrawl("cancel"));
$("#generate-excel").addEventListener("click", generateExcel);
$("#refresh-operations").addEventListener("click", loadOperations);
$("#toggle-crawl-archive").addEventListener("click", () => { state.showCrawlArchive = !state.showCrawlArchive; renderOperations(); });
$("#crawl-run-rows").addEventListener("click", (event) => { const button = event.target.closest("[data-crawl-failures]"); if (button) showCrawlFailures(button.dataset.crawlFailures); });
$("#crawl-run-cards").addEventListener("click", (event) => { const button = event.target.closest("[data-crawl-failures]"); if (button) showCrawlFailures(button.dataset.crawlFailures); });
$("#close-crawl-failures").addEventListener("click", () => $("#crawl-failure-panel").classList.add("hidden"));
$("#current-export-download").addEventListener("click", () => window.setTimeout(loadOperations, 2000));
$("#export-urls").addEventListener("click", exportUrls);
$("#export-tasks").addEventListener("click", exportTasks);
$("#export-changes").addEventListener("click", exportChanges);
$("#export-vacancies").addEventListener("click", exportVacancies);
$("#save-search-console").addEventListener("click", () => saveProperty("search_console", "#search-console-property", "#save-search-console", "#search-console-message", state.googleConnectionId));
$("#save-ga4").addEventListener("click", () => saveProperty("ga4", "#ga4-property", "#save-ga4", "#ga4-message", state.googleConnectionId));
$("#save-ga4-key-events").addEventListener("click", saveGa4KeyEvents);
$("#save-bing").addEventListener("click", () => saveProperty("bing_webmaster", "#bing-property", "#save-bing", "#bing-property-message", state.bingConnectionId));
$("#matomo-connect").addEventListener("click", showMatomoConnect);
$("#test-matomo").addEventListener("click", connectMatomo);
$("#save-matomo").addEventListener("click", () => saveProperty("matomo", "#matomo-property", "#save-matomo", "#matomo-property-message", state.matomoConnectionId));
$("#save-analytics-primary").addEventListener("click", savePrimaryAnalyticsSource);
$("#sync-search-console").addEventListener("click", syncSearchConsole);
$("#sync-ga4").addEventListener("click", syncGa4);
$("#sync-bing").addEventListener("click", syncBing);
$("#sync-matomo").addEventListener("click", syncMatomo);
$("#import-bing-backlinks").addEventListener("click", importBingBacklinks);
$("#bing-domains-file").addEventListener("change", () => updateBingFileName("#bing-domains-file", "#bing-domains-name"));
$("#bing-pages-file").addEventListener("change", () => updateBingFileName("#bing-pages-file", "#bing-pages-name"));
$("#bing-anchors-file").addEventListener("change", () => updateBingFileName("#bing-anchors-file", "#bing-anchors-name"));
$("#sync-integration-history").addEventListener("click", syncIntegrationHistory);

api("/api/v1/me").then(async (user) => {
  state.currentUser = user;
  applyRolePermissions();
  if (user.mfa_required) {
    showApp();
    await openMfaSetup();
    return false;
  }
  await loadClients();
  return true;
}).then((workspaceReady) => {
  if (!workspaceReady) return;
  showApp();
  const integrationResult = new URLSearchParams(window.location.search).get("integration");
  if (integrationResult) {
    showView("integrations");
    const integrationMessages = {
      "google-connected": "Google-account is succesvol gekoppeld.",
      "bing-connected": "Bing Webmaster Tools-account is succesvol gekoppeld.",
      "google-error": "Google-koppeling is niet voltooid. Probeer opnieuw.",
      "bing-error": "Bing-koppeling is niet voltooid. Probeer opnieuw.",
    };
    $("#integration-message").textContent = integrationMessages[integrationResult] || "De koppeling is niet voltooid. Probeer opnieuw.";
    $("#integration-message").classList.remove("hidden");
    window.history.replaceState({}, "", `/app#${VIEW_HASHES.integrations}`);
  } else showView(viewFromHash(), false);
}).catch(() => showLogin());
