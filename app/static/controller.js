let state = window.__INITIAL_STATE__ || {};
const pollIntervalMs = Number(window.__POLL_INTERVAL_MS__ || 15000);
const stations = Array.isArray(window.__STATIONS__) ? window.__STATIONS__ : [];
let selectedStationId = state.station?.id || stations[0]?.id || null;
let bluetoothState = { renderers: [] };
let lastTrackKey = null;
let localVolumeCommitTimer = null;

const stationList = document.getElementById('stationList');
const playButton = document.getElementById('playButton');
const refreshButton = document.getElementById('refreshButton');
const player = document.getElementById('player');
const statusBadge = document.getElementById('statusBadge');
const stationName = document.getElementById('stationName');
const trackTitle = document.getElementById('trackTitle');
const trackArtist = document.getElementById('trackArtist');
const playedAt = document.getElementById('playedAt');
const coverSource = document.getElementById('coverSource');
const coverImage = document.getElementById('coverImage');
const errorText = document.getElementById('errorText');
const volumeSlider = document.getElementById('volumeSlider');
const localVolumeSlider = document.getElementById('localVolumeSlider');
const localMuteButton = document.getElementById('localMuteButton');
const localVolDownButton = document.getElementById('localVolDownButton');
const localVolUpButton = document.getElementById('localVolUpButton');
const localAudioSummary = document.getElementById('localAudioSummary');
const audioOutputs = document.getElementById('audioOutputs');
const audioOutputsEmpty = document.getElementById('audioOutputsEmpty');
const bluetoothScanButton = document.getElementById('bluetoothScanButton');
const bluetoothStatusText = document.getElementById('bluetoothStatusText');
const bluetoothDeviceList = document.getElementById('bluetoothDeviceList');
const selftestButton = document.getElementById('selftestButton');
const selftestResults = document.getElementById('selftestResults');
const backupButton = document.getElementById('backupButton');
const backupStatusText = document.getElementById('backupStatusText');
const backupList = document.getElementById('backupList');
const scheduleEnabled = document.getElementById('scheduleEnabled');
const scheduleOnHour = document.getElementById('scheduleOnHour');
const scheduleOffHour = document.getElementById('scheduleOffHour');
const transitionsEnabled = document.getElementById('transitionsEnabled');
const saveDisplayConfigButton = document.getElementById('saveDisplayConfigButton');
const scheduleStatusText = document.getElementById('scheduleStatusText');
const updateSourceUrl = document.getElementById('updateSourceUrl');
const saveUpdateConfigButton = document.getElementById('saveUpdateConfigButton');
const checkUpdateButton = document.getElementById('checkUpdateButton');
const applyUpdateButton = document.getElementById('applyUpdateButton');
const updateStatusText = document.getElementById('updateStatusText');
const updateDetails = document.getElementById('updateDetails');
const controllerTime = document.getElementById('controllerTime');
const controllerDate = document.getElementById('controllerDate');
const controllerWeatherIcon = document.getElementById('controllerWeatherIcon');
const controllerWeatherLocation = document.getElementById('controllerWeatherLocation');
const controllerWeatherCondition = document.getElementById('controllerWeatherCondition');
const controllerWeatherTemp = document.getElementById('controllerWeatherTemp');
const controllerWeatherPressure = document.getElementById('controllerWeatherPressure');
const controllerMetaCard = document.getElementById('controllerMetaCard');

function selectedStation() {
  return stations.find((station) => station.id === selectedStationId) || stations[0] || null;
}

function renderStationList() {
  stationList.innerHTML = '';
  for (const station of stations) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'station-list-button';
    button.dataset.stationId = station.id;
    button.setAttribute('role', 'option');
    button.textContent = station.name;
    button.addEventListener('click', () => {
      selectStation(station.id).catch((error) => console.error(error));
    });
    stationList.appendChild(button);
  }
  syncStationButtons();
}

function syncStationButtons() {
  for (const button of stationList.querySelectorAll('.station-list-button')) {
    const isActive = button.dataset.stationId === selectedStationId;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-selected', isActive ? 'true' : 'false');
  }
}

function syncPlayerSource() {
  const station = selectedStation();
  if (!station) return;
  if (player.dataset.stationId !== station.id) {
    player.src = station.stream_url;
    player.dataset.stationId = station.id;
    player.load();
  }
}

function updateClock() {
  const now = new Date();
  controllerTime.textContent = new Intl.DateTimeFormat('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Europe/Berlin',
  }).format(now);

  controllerDate.textContent = new Intl.DateTimeFormat('de-DE', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Europe/Berlin',
  }).format(now);
}

function renderControllerWeather(weather) {
  const current = (weather && weather.current) || {};
  controllerWeatherLocation.textContent = (weather && weather.location) || 'Falkensee';
  controllerWeatherCondition.textContent = current.condition || (weather && weather.error) || 'Wetter wird geladen';
  controllerWeatherTemp.textContent = Number.isFinite(current.temperature_c)
    ? `${current.temperature_c} °C`
    : '-- °C';
  controllerWeatherPressure.textContent = Number.isFinite(current.surface_pressure_hpa)
    ? `Luftdruck ${current.surface_pressure_hpa} hPa`
    : 'Luftdruck -- hPa';

  if (current.icon_url) {
    controllerWeatherIcon.src = current.icon_url;
    controllerWeatherIcon.classList.remove('hidden');
  } else {
    controllerWeatherIcon.removeAttribute('src');
    controllerWeatherIcon.classList.add('hidden');
  }
}

function renderLocalAudio(audio) {
  const available = Boolean(audio && audio.available);
  if (!available) {
    localAudioSummary.textContent = audio?.message || 'Ausgabe nicht verfügbar';
    renderAudioOutputs(audio?.outputs || [], audio?.selected_output_id || null);
    localMuteButton.disabled = true;
    localVolDownButton.disabled = true;
    localVolUpButton.disabled = true;
    localVolumeSlider.disabled = true;
    return;
  }

  localMuteButton.disabled = false;
  localVolDownButton.disabled = false;
  localVolUpButton.disabled = false;
  localVolumeSlider.disabled = false;
  if (document.activeElement !== localVolumeSlider) {
    localVolumeSlider.value = String(audio.volume_percent ?? 50);
  }
  localMuteButton.textContent = audio.muted ? 'Stumm aus' : 'Stumm';
  localAudioSummary.textContent = `${audio.selected_output_label || 'Audio'} · ${audio.volume_percent}%${audio.muted ? ' · stumm' : ''}`;

  renderAudioOutputs(audio.outputs || [], audio.selected_output_id);
}

function renderAudioOutputs(outputs, selectedOutputId) {
  audioOutputs.innerHTML = '';
  if (!Array.isArray(outputs) || !outputs.length) {
    audioOutputsEmpty.classList.remove('hidden');
    return;
  }
  audioOutputsEmpty.classList.add('hidden');
  for (const output of outputs) {
    if (!['jack', 'upnp'].includes(output.kind)) {
      continue;
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip-button';
    button.textContent = output.label;
    if (output.id === selectedOutputId || output.default) {
      button.classList.add('is-active');
    }
    button.addEventListener('click', async () => {
      try {
        const nextAudio = await postJson('/api/audio/output', { output_id: output.id });
        state.local_audio = nextAudio;
        renderLocalAudio(nextAudio);
        setInlineMessage(localAudioSummary, `${output.label} aktiv`);
      } catch (error) {
        setInlineMessage(localAudioSummary, readableError(error), true);
      }
    });
    audioOutputs.appendChild(button);
  }
}

function applyConfig(config, schedule) {
  const nextConfig = config || {};
  scheduleEnabled.checked = Boolean(nextConfig.display_schedule_enabled);
  scheduleOnHour.value = String(nextConfig.display_on_hour ?? 8);
  scheduleOffHour.value = String(nextConfig.display_off_hour ?? 22);
  transitionsEnabled.checked = Boolean(nextConfig.transitions_enabled);
  updateSourceUrl.value = nextConfig.update_source_zip_url || '';

  if (schedule) {
    const prefix = schedule.awake ? 'Gerade aktiv' : 'Gerade im Ruhemodus';
    scheduleStatusText.textContent = `${prefix} · ${schedule.message}`;
  } else {
    scheduleStatusText.textContent = 'Anzeige-Konfiguration wird geladen…';
  }
}

function applyUpdateStatus(updateStatus) {
  if (!updateStatus) {
    return;
  }
  let message = updateStatus.message || 'Update-Status unbekannt';
  if (updateStatus.local_commit) {
    message += ` · Lokal ${updateStatus.local_commit}`;
  }
  if (updateStatus.remote_commit) {
    message += ` · Remote ${updateStatus.remote_commit}`;
  }
  updateStatusText.textContent = message;
  applyUpdateButton.disabled = !updateStatus.can_update;

  updateDetails.innerHTML = '';
  const items = [
    ['Modus', updateStatus.mode || '-'],
    ['Branch', updateStatus.branch || '-'],
    ['Projekt', updateStatus.project_dir || '-'],
  ];
  for (const [label, value] of items) {
    const row = document.createElement('div');
    row.className = 'kv-row';
    row.innerHTML = `<span>${escapeHtml(label)}</span><span>${escapeHtml(String(value))}</span>`;
    updateDetails.appendChild(row);
  }
}

function animateSwitchIfNeeded(nextState) {
  const transitionsEnabledFlag = Boolean(nextState?.config?.transitions_enabled);
  if (!transitionsEnabledFlag) {
    lastTrackKey = `${nextState?.station?.id || ''}|${nextState?.artist || ''}|${nextState?.title || ''}`;
    return;
  }
  const trackKey = `${nextState?.station?.id || ''}|${nextState?.artist || ''}|${nextState?.title || ''}`;
  if (!lastTrackKey || lastTrackKey === trackKey) {
    lastTrackKey = trackKey;
    return;
  }
  for (const element of [coverImage, controllerMetaCard]) {
    if (!element) continue;
    element.classList.remove('is-animating');
    void element.offsetWidth;
    element.classList.add('is-animating');
  }
  lastTrackKey = trackKey;
}

function applyState(nextState) {
  state = nextState;
  if (nextState.station && nextState.station.id) {
    selectedStationId = nextState.station.id;
  }
  animateSwitchIfNeeded(nextState);
  syncStationButtons();
  syncPlayerSource();

  const station = nextState.station || selectedStation() || {};
  statusBadge.textContent = nextState.status_text || 'Bereit';
  stationName.textContent = station.name || '-';
  trackTitle.textContent = nextState.title || 'Noch kein Titel';
  trackArtist.textContent = nextState.artist || 'Bitte Sender wählen und Play drücken.';
  playedAt.textContent = nextState.played_at || '--:-- Uhr';
  coverSource.textContent = `Cover: ${nextState.cover_source || '-'}`;
  playButton.textContent = nextState.playing_hint ? 'Pause' : 'Play';

  if (nextState.cover_url) {
    coverImage.src = nextState.cover_url;
  } else {
    coverImage.src = '/static/kein-cover.svg?v=20260317b';
  }

  if (nextState.error) {
    errorText.textContent = nextState.error;
    errorText.classList.remove('hidden');
  } else {
    errorText.classList.add('hidden');
  }

  renderControllerWeather(nextState.display_weather || {});
  renderLocalAudio(nextState.local_audio || {});
  renderBluetoothDevices(nextState.upnp_status || bluetoothState);
  applyConfig(nextState.config || {}, nextState.display_schedule || null);
  applyUpdateStatus(nextState.update_status || null);
}

coverImage.addEventListener('error', () => {
  coverImage.src = '/static/kein-cover.svg?v=20260317b';
});

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await safeJson(response);
  if (!response.ok) {
    throw new Error(payload?.detail || `HTTP ${response.status}`);
  }
  return payload;
}

async function getJson(url) {
  const response = await fetch(url);
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

async function loadState() {
  const nextState = await getJson('/api/state');
  applyState(nextState);
  if (nextState.upnp_status) {
    renderBluetoothDevices(nextState.upnp_status);
  }
}

async function setPlayback(playing) {
  const nextState = await postJson('/api/playback', { playing });
  applyState(nextState);
}

async function selectStation(stationId) {
  if (!stationId || stationId === selectedStationId) {
    return;
  }

  const wasPlaying = !player.paused;
  selectedStationId = stationId;
  syncStationButtons();

  const nextState = await postJson('/api/select', { station_id: stationId });
  applyState(nextState);

  if (wasPlaying) {
    try {
      await player.play();
      await setPlayback(true);
    } catch (error) {
      console.error(error);
      statusBadge.textContent = 'Autoplay blockiert';
    }
  }
}

function readableError(error) {
  return error instanceof Error ? error.message : String(error);
}

function setInlineMessage(node, message, isError = false) {
  node.textContent = message;
  node.classList.toggle('is-error', Boolean(isError));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderBluetoothDevices(payload) {
  bluetoothState = payload || { renderers: [] };
  const devices = Array.isArray(payload?.renderers) ? payload.renderers : [];
  const available = payload?.available !== false;
  const selectedOutputId = state.local_audio?.selected_output_id || payload?.selected_output_id || null;
  const transportPlaying = Boolean(state.local_audio?.transport_playing);

  bluetoothStatusText.classList.remove('is-error');
  if (!available) {
    bluetoothStatusText.textContent = payload?.message || 'WLAN-Lautsprecher nicht verfügbar';
    bluetoothStatusText.classList.add('is-error');
    bluetoothDeviceList.innerHTML = '';
    return;
  }

  bluetoothStatusText.textContent = payload?.message || 'WLAN-Lautsprecher bereit';

  bluetoothDeviceList.innerHTML = '';
  if (!devices.length) {
    const empty = document.createElement('p');
    empty.className = 'controller-inline-note';
    empty.textContent = 'Noch keine WLAN-Lautsprecher gefunden.';
    bluetoothDeviceList.appendChild(empty);
    return;
  }

  for (const device of devices) {
    const card = document.createElement('article');
    card.className = 'device-card';
    const isSelected = device.id === selectedOutputId;
    const factLine = [device.host || null, isSelected ? 'als Ausgabe gewählt' : null].filter(Boolean).join(' · ');
    card.innerHTML = `
      <div class="device-card-copy">
        <strong>${escapeHtml(device.friendly_name || device.name || 'WLAN-Lautsprecher')}</strong>
        <span>${escapeHtml(device.host || '-')}</span>
        <small>${escapeHtml(factLine || 'UPnP MediaRenderer')}</small>
      </div>
      <div class="device-card-actions"></div>
    `;
    const actions = card.querySelector('.device-card-actions');

    actions.appendChild(deviceButton(isSelected ? 'Aktiv' : 'Als Ausgabe', async () => {
      if (isSelected) {
        return;
      }
      const nextAudio = await postJson('/api/audio/output', { output_id: device.id });
      state.local_audio = nextAudio;
      renderLocalAudio(nextAudio);
      await loadState();
    }, false, isSelected));

    actions.appendChild(deviceButton(transportPlaying && isSelected ? 'Stopp' : 'Jetzt senden', async () => {
      if (!isSelected) {
        const nextAudio = await postJson('/api/audio/output', { output_id: device.id });
        state.local_audio = nextAudio;
        renderLocalAudio(nextAudio);
      }
      const nextAudio = await postJson('/api/output/playback', { playing: !(transportPlaying && isSelected) });
      state.local_audio = nextAudio;
      renderLocalAudio(nextAudio);
      await loadState();
    }));

    bluetoothDeviceList.appendChild(card);
  }
}

function deviceButton(label, handler, danger = false, disabled = false) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = danger ? 'device-action danger-button' : 'device-action secondary-button';
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await handler();
    } catch (error) {
      bluetoothStatusText.textContent = readableError(error);
      bluetoothStatusText.classList.add('is-error');
    } finally {
      if (!disabled) {
        button.disabled = false;
      }
    }
  });
  return button;
}

async function refreshBluetoothState() {
  try {
    const payload = await getJson('/api/upnp/state');
    renderBluetoothDevices(payload);
  } catch (error) {
    bluetoothStatusText.textContent = readableError(error);
    bluetoothStatusText.classList.add('is-error');
  }
}

function renderSelftest(payload) {
  selftestResults.innerHTML = '';
  const checks = Array.isArray(payload?.checks) ? payload.checks : [];
  if (!checks.length) {
    selftestResults.innerHTML = '<p class="controller-inline-note">Noch kein Selbsttest durchgeführt.</p>';
    return;
  }
  for (const check of checks) {
    const row = document.createElement('div');
    row.className = `selftest-row is-${check.status}`;
    row.innerHTML = `
      <div class="selftest-row-main">
        <strong>${escapeHtml(check.name)}</strong>
        <span>${escapeHtml(check.detail)}</span>
      </div>
      <span>${escapeHtml(String(check.duration_ms))} ms</span>
    `;
    selftestResults.appendChild(row);
  }
}

async function runSelftest() {
  selftestButton.disabled = true;
  selftestResults.innerHTML = '<p class="controller-inline-note">Selbsttest läuft…</p>';
  try {
    const payload = await postJson('/api/selftest', {});
    renderSelftest(payload);
  } catch (error) {
    selftestResults.innerHTML = `<p class="controller-inline-note is-error">${escapeHtml(readableError(error))}</p>`;
  } finally {
    selftestButton.disabled = false;
  }
}

function renderBackups(payload) {
  const backups = Array.isArray(payload?.backups) ? payload.backups : [];
  backupList.innerHTML = '';
  if (!backups.length) {
    backupStatusText.textContent = 'Noch keine Sicherungen vorhanden.';
    return;
  }
  backupStatusText.textContent = `${backups.length} Sicherungen vorhanden.`;
  for (const backup of backups.slice(0, 6)) {
    const row = document.createElement('div');
    row.className = 'backup-row';
    row.innerHTML = `
      <span>${escapeHtml(backup.name)}</span>
      <small>${escapeHtml(backup.modified_at || '-')} · ${escapeHtml(String(backup.size || 0))} Byte</small>
    `;
    backupList.appendChild(row);
  }
}

async function refreshBackups() {
  try {
    renderBackups(await getJson('/api/backups'));
  } catch (error) {
    backupStatusText.textContent = readableError(error);
    backupStatusText.classList.add('is-error');
  }
}

async function saveDisplayConfig() {
  const payload = {
    display_schedule_enabled: scheduleEnabled.checked,
    display_on_hour: Number(scheduleOnHour.value),
    display_off_hour: Number(scheduleOffHour.value),
    transitions_enabled: transitionsEnabled.checked,
  };
  const nextState = await postJson('/api/config', payload);
  applyState(nextState);
  scheduleStatusText.textContent = 'Anzeige-Konfiguration gespeichert';
}

async function saveUpdateConfig() {
  const nextState = await postJson('/api/config', { update_source_zip_url: updateSourceUrl.value.trim() });
  applyState(nextState);
  updateStatusText.textContent = 'Update-Quelle gespeichert';
}

async function checkForUpdates() {
  const payload = await postJson('/api/update/check', {});
  applyUpdateStatus(payload);
}

async function applyUpdate() {
  const confirmed = window.confirm('Update jetzt starten? Der Dienst wird danach neu gestartet.');
  if (!confirmed) {
    return;
  }
  const payload = await postJson('/api/update/apply', {});
  updateStatusText.textContent = payload.message || 'Update wird gestartet';
}

playButton.addEventListener('click', async () => {
  syncPlayerSource();
  if (player.paused) {
    try {
      await player.play();
      await setPlayback(true);
    } catch (error) {
      console.error(error);
      statusBadge.textContent = 'Autoplay blockiert';
    }
    return;
  }

  player.pause();
  await setPlayback(false);
});

refreshButton.addEventListener('click', async () => {
  const nextState = await postJson('/api/refresh', {});
  applyState(nextState);
});

volumeSlider.addEventListener('input', () => {
  player.volume = Number(volumeSlider.value);
});

localVolumeSlider.addEventListener('input', () => {
  localAudioSummary.textContent = `Ausgabe-Lautstärke ${localVolumeSlider.value}%`;
  if (localVolumeCommitTimer) {
    window.clearTimeout(localVolumeCommitTimer);
  }
  localVolumeCommitTimer = window.setTimeout(async () => {
    try {
      const nextAudio = await postJson('/api/audio/volume', { percent: Number(localVolumeSlider.value) });
      state.local_audio = nextAudio;
      renderLocalAudio(nextAudio);
    } catch (error) {
      setInlineMessage(localAudioSummary, readableError(error), true);
    }
  }, 180);
});

localMuteButton.addEventListener('click', async () => {
  try {
    const nextAudio = await postJson('/api/audio/mute-toggle', {});
    state.local_audio = nextAudio;
    renderLocalAudio(nextAudio);
  } catch (error) {
    setInlineMessage(localAudioSummary, readableError(error), true);
  }
});

localVolDownButton.addEventListener('click', async () => {
  try {
    const nextAudio = await postJson('/api/audio/volume-delta', { delta: -5 });
    state.local_audio = nextAudio;
    renderLocalAudio(nextAudio);
  } catch (error) {
    setInlineMessage(localAudioSummary, readableError(error), true);
  }
});

localVolUpButton.addEventListener('click', async () => {
  try {
    const nextAudio = await postJson('/api/audio/volume-delta', { delta: 5 });
    state.local_audio = nextAudio;
    renderLocalAudio(nextAudio);
  } catch (error) {
    setInlineMessage(localAudioSummary, readableError(error), true);
  }
});

bluetoothScanButton.addEventListener('click', async () => {
  bluetoothScanButton.disabled = true;
  try {
    const payload = await postJson('/api/upnp/discover', { seconds: 5 });
    bluetoothStatusText.textContent = payload.message || 'WLAN-Suche abgeschlossen';
    bluetoothStatusText.classList.remove('is-error');
    renderBluetoothDevices(payload);
    window.setTimeout(() => {
      refreshBluetoothState().catch((error) => console.error(error));
      loadState().catch((error) => console.error(error));
    }, 1200);
  } catch (error) {
    bluetoothStatusText.textContent = readableError(error);
    bluetoothStatusText.classList.add('is-error');
  } finally {
    bluetoothScanButton.disabled = false;
  }
});

selftestButton.addEventListener('click', () => {
  runSelftest().catch((error) => console.error(error));
});

backupButton.addEventListener('click', async () => {
  backupButton.disabled = true;
  try {
    const payload = await postJson('/api/backups/create', {});
    backupStatusText.textContent = payload.backup ? `${payload.backup} erstellt` : 'Backup erstellt';
    await refreshBackups();
  } catch (error) {
    backupStatusText.textContent = readableError(error);
    backupStatusText.classList.add('is-error');
  } finally {
    backupButton.disabled = false;
  }
});

saveDisplayConfigButton.addEventListener('click', () => {
  saveDisplayConfig().catch((error) => {
    scheduleStatusText.textContent = readableError(error);
    scheduleStatusText.classList.add('is-error');
  });
});

saveUpdateConfigButton.addEventListener('click', () => {
  saveUpdateConfig().catch((error) => {
    updateStatusText.textContent = readableError(error);
  });
});

checkUpdateButton.addEventListener('click', () => {
  checkForUpdates().catch((error) => {
    updateStatusText.textContent = readableError(error);
  });
});

applyUpdateButton.addEventListener('click', () => {
  applyUpdate().catch((error) => {
    updateStatusText.textContent = readableError(error);
  });
});

renderStationList();
player.volume = Number(volumeSlider.value);
applyState(state);
updateClock();
refreshBluetoothState().catch((error) => console.error(error));
refreshBackups().catch((error) => console.error(error));

setInterval(() => {
  loadState().catch((error) => console.error(error));
}, pollIntervalMs);

setInterval(() => {
  updateClock();
}, 1000);

setInterval(() => {
  refreshBluetoothState().catch((error) => console.error(error));
}, Math.max(30000, pollIntervalMs * 2));
