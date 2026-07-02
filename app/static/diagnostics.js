const diagnosticsPollIntervalMs = Number(window.__DIAGNOSTICS_POLL_INTERVAL_MS__ || 60000);

const runDiagnosticsButton = document.getElementById('runDiagnosticsButton');
const diagnosticsBadge = document.getElementById('diagnosticsBadge');
const diagnosticsHeadline = document.getElementById('diagnosticsHeadline');
const diagnosticsTimestamp = document.getElementById('diagnosticsTimestamp');
const diagnosticsSummaryGrid = document.getElementById('diagnosticsSummaryGrid');
const systemFacts = document.getElementById('systemFacts');
const playbackFacts = document.getElementById('playbackFacts');
const diagnosticsUpdateFacts = document.getElementById('diagnosticsUpdateFacts');
const appFacts = document.getElementById('appFacts');
const diagnosticsCheckCount = document.getElementById('diagnosticsCheckCount');
const diagnosticsChecks = document.getElementById('diagnosticsChecks');

async function getJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  const payload = await safeJson(response);
  if (!response.ok) {
    throw new Error(payload?.detail || `HTTP ${response.status}`);
  }
  return payload;
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function loadDiagnostics() {
  runDiagnosticsButton.disabled = true;
  diagnosticsBadge.textContent = 'Wird geprüft';
  diagnosticsBadge.className = 'badge diagnostics-status-badge is-warn';
  diagnosticsHeadline.textContent = 'Diagnose läuft…';
  try {
    const payload = await getJson('/api/diagnostics');
    renderDiagnostics(payload);
  } catch (error) {
    renderDiagnosticsError(error);
  } finally {
    runDiagnosticsButton.disabled = false;
  }
}

function renderDiagnostics(payload) {
  const summaryStatus = payload?.summary_status || 'warn';
  diagnosticsBadge.textContent = statusLabel(summaryStatus);
  diagnosticsBadge.className = `badge diagnostics-status-badge is-${summaryStatus}`;
  diagnosticsHeadline.textContent = payload?.summary_label || statusLabel(summaryStatus);
  diagnosticsTimestamp.textContent = `Geprüft: ${formatDateTime(payload?.checked_at)}`;

  renderSummaryCards(payload);
  renderSystemFacts(payload?.system || {});
  renderPlaybackFacts(payload || {});
  renderUpdateFacts(payload?.update || {});
  renderAppFacts(payload || {});
  renderChecks(payload?.checks || []);
}

function renderDiagnosticsError(error) {
  diagnosticsBadge.textContent = 'Fehler';
  diagnosticsBadge.className = 'badge diagnostics-status-badge is-error';
  diagnosticsHeadline.textContent = readableError(error);
  diagnosticsTimestamp.textContent = `Geprüft: ${formatDateTime(new Date().toISOString())}`;
  diagnosticsSummaryGrid.innerHTML = '';
  diagnosticsChecks.innerHTML = `<p class="controller-inline-note is-error">${escapeHtml(readableError(error))}</p>`;
}

function renderSummaryCards(payload) {
  const system = payload?.system || {};
  const audio = payload?.audio || {};
  const update = payload?.update || {};
  const track = payload?.app?.current_track || {};
  const cards = [
    {
      label: 'App-Laufzeit',
      value: system.app_uptime || '-',
      detail: system.hostname || 'Hostname unbekannt',
      status: 'ok',
    },
    {
      label: 'Wiedergabe',
      value: payload?.app?.playing_hint ? 'Aktiv' : 'Pause',
      detail: [track.artist, track.title].filter(Boolean).join(' - ') || payload?.app?.status_text || '-',
      status: payload?.app?.error ? 'error' : 'ok',
    },
    {
      label: 'Audio',
      value: audio.selected_output_label || 'Unbekannt',
      detail: audio.route_kind === 'upnp' ? 'UPnP/WLAN' : 'Lokal am Raspberry Pi',
      status: audio.available === false ? 'warn' : 'ok',
    },
    {
      label: 'Update',
      value: update.update_available ? 'Bereit' : update.dirty ? 'Gesperrt' : 'Aktuell',
      detail: update.message || '-',
      status: update.dirty ? 'warn' : 'ok',
    },
  ];
  diagnosticsSummaryGrid.innerHTML = '';
  for (const card of cards) {
    diagnosticsSummaryGrid.appendChild(createStatusCard(card));
  }
}

function renderSystemFacts(system) {
  renderFacts(systemFacts, [
    ['Hostname', system.hostname],
    ['Python', system.python],
    ['App-Laufzeit', system.app_uptime],
    ['CPU-Temperatur', formatTemperature(system.cpu_temp_c)],
    ['Freier Speicher', formatDisk(system)],
    ['Load Average', Array.isArray(system.load_average) ? system.load_average.join(' / ') : '-'],
  ]);
}

function renderPlaybackFacts(payload) {
  const audio = payload.audio || {};
  const app = payload.app || {};
  const track = app.current_track || {};
  renderFacts(playbackFacts, [
    ['Ausgabe', audio.selected_output_label || '-'],
    ['Lautstärke', Number.isFinite(audio.volume_percent) ? `${audio.volume_percent}%` : '-'],
    ['Stumm', audio.muted ? 'Ja' : 'Nein'],
    ['Route', audio.route_kind === 'upnp' ? 'UPnP/WLAN' : 'Lokal'],
    ['UPnP-Transport', audio.transport_playing ? 'PLAYING' : '-'],
    ['Aktueller Titel', [track.artist, track.title].filter(Boolean).join(' - ') || '-'],
  ]);
}

function renderUpdateFacts(update) {
  renderFacts(diagnosticsUpdateFacts, [
    ['Modus', update.mode || '-'],
    ['Branch', update.branch || '-'],
    ['Lokal', update.local_commit_full || update.local_commit || '-'],
    ['Remote', update.remote_commit_full || update.remote_commit || '-'],
    ['Remote URL', update.remote_url || '-'],
    ['Lokale Änderungen', update.dirty ? 'Ja' : 'Nein'],
    ['Direktupdate', update.can_update ? 'Möglich' : 'Gesperrt'],
  ]);
}

function renderAppFacts(payload) {
  const app = payload.app || {};
  renderFacts(appFacts, [
    ['Version', app.version || '-'],
    ['Station', app.station?.name || '-'],
    ['Status', app.status_text || '-'],
    ['Fehler', app.error || '-'],
    ['Controller', payload.controller_url || '-'],
    ['Display', payload.display_url || '-'],
    ['Projekt', app.project_dir || '-'],
  ]);
}

function renderChecks(checks) {
  diagnosticsChecks.innerHTML = '';
  const list = Array.isArray(checks) ? checks : [];
  diagnosticsCheckCount.textContent = `${list.length} Prüfungen`;
  if (!list.length) {
    diagnosticsChecks.innerHTML = '<p class="controller-inline-note">Noch keine Prüfdaten vorhanden.</p>';
    return;
  }
  for (const check of list) {
    const row = document.createElement('div');
    const status = check.status || 'warn';
    row.className = `selftest-row diagnostics-check-row is-${status}`;
    row.innerHTML = `
      <div class="selftest-row-main">
        <strong>${escapeHtml(check.name || '-')}</strong>
        <span>${escapeHtml(check.detail || '-')}</span>
      </div>
      <span>${escapeHtml(String(check.duration_ms ?? 0))} ms</span>
    `;
    diagnosticsChecks.appendChild(row);
  }
}

function renderFacts(container, items) {
  container.innerHTML = '';
  for (const [label, value] of items) {
    const row = document.createElement('div');
    row.className = 'kv-row';

    const key = document.createElement('span');
    key.textContent = label;

    const val = document.createElement('span');
    val.textContent = formatValue(value);

    row.append(key, val);
    container.appendChild(row);
  }
}

function createStatusCard(card) {
  const article = document.createElement('article');
  article.className = `status-card is-${card.status || 'ok'}`;

  const label = document.createElement('span');
  label.className = 'status-card-label';
  label.textContent = card.label;

  const value = document.createElement('strong');
  value.className = 'status-card-value';
  value.textContent = card.value || '-';

  const detail = document.createElement('small');
  detail.className = 'status-card-detail';
  detail.textContent = card.detail || '';

  article.append(label, value, detail);
  return article;
}

function statusLabel(status) {
  if (status === 'ok') {
    return 'Alles ok';
  }
  if (status === 'error') {
    return 'Fehler';
  }
  return 'Hinweis';
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
}

function formatTemperature(value) {
  return Number.isFinite(value) ? `${value} °C` : '-';
}

function formatDisk(system) {
  if (!Number.isFinite(system.disk_free_mb)) {
    return '-';
  }
  const percent = Number.isFinite(system.disk_free_percent) ? ` · ${system.disk_free_percent}% frei` : '';
  return `${system.disk_free_mb} MB frei${percent}`;
}

function formatDateTime(value) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(date);
}

function readableError(error) {
  return error instanceof Error ? error.message : String(error);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

runDiagnosticsButton.addEventListener('click', () => {
  loadDiagnostics().catch((error) => console.error(error));
});

loadDiagnostics().catch((error) => console.error(error));

setInterval(() => {
  loadDiagnostics().catch((error) => console.error(error));
}, Math.max(60000, diagnosticsPollIntervalMs));
