let state = window.__INITIAL_STATE__ || {};
const pollIntervalMs = Number(window.__POLL_INTERVAL_MS__ || 15000);

const backgroundLayer = document.getElementById('backgroundLayer');
const stationName = document.getElementById('displayStationName');
const clockText = document.getElementById('displayClock');
const dateText = document.getElementById('displayDate');
const coverImage = document.getElementById('displayCover');
const title = document.getElementById('displayTitle');
const artist = document.getElementById('displayArtist');
const errorText = document.getElementById('displayError');
const shutdownButton = document.getElementById('shutdownButton');
const shutdownStatus = document.getElementById('shutdownStatus');
const localPlayButton = document.getElementById('localPlayButton');
const localPlayer = document.getElementById('localPlayer');
const controllerQrImage = document.getElementById('controllerQrImage');
const controllerQrFallback = document.getElementById('controllerQrFallback');
const controllerQrCard = document.getElementById('controllerQrCard');
const weatherPanel = document.getElementById('weatherPanel');
const weatherLocation = document.getElementById('weatherLocation');
const weatherHeaderIcon = document.getElementById('weatherHeaderIcon');
const weatherCurrent = document.getElementById('weatherCurrent');
const weatherCurrentTemp = document.getElementById('weatherCurrentTemp');
const weatherCurrentCondition = document.getElementById('weatherCurrentCondition');
const weatherCurrentPressure = document.getElementById('weatherCurrentPressure');
const weatherCurrentPressureTrend = document.getElementById('weatherCurrentPressureTrend');
const weatherDays = document.getElementById('weatherDays');
const weatherError = document.getElementById('weatherError');
const backgroundIssueIndicator = document.getElementById('backgroundIssueIndicator');
const prevStationButton = document.getElementById('prevStationButton');
const nextStationButton = document.getElementById('nextStationButton');
const displayPlayPauseButton = document.getElementById('displayPlayPauseButton');
const displayMuteButton = document.getElementById('displayMuteButton');
const displayVolDownButton = document.getElementById('displayVolDownButton');
const displayVolUpButton = document.getElementById('displayVolUpButton');
const displayLocalVolume = document.getElementById('displayLocalVolume');
const displaySleepOverlay = document.getElementById('displaySleepOverlay');
const displaySleepText = document.getElementById('displaySleepText');
const displayMetaBlock = document.getElementById('displayMetaBlock');

let shutdownInProgress = false;
let localPlaybackRequested = false;
let localPlaybackBusy = false;
let displayErrorTimeoutId = null;
let lastTrackKey = null;

const berlinClockFormatter = typeof Intl !== 'undefined'
  ? new Intl.DateTimeFormat('de-DE', {
      timeZone: 'Europe/Berlin',
      hour: '2-digit',
      minute: '2-digit',
    })
  : null;

const berlinDateFormatter = typeof Intl !== 'undefined'
  ? new Intl.DateTimeFormat('de-DE', {
      timeZone: 'Europe/Berlin',
      weekday: 'short',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  : null;

function setCover(url) {
  const source = url || '/static/kein-cover.svg?v=20260317b';
  coverImage.src = source;
  backgroundLayer.style.backgroundImage = `url('${source.replace(/'/g, "%27")}')`;
}

function updateClock() {
  const now = new Date();
  if (berlinClockFormatter) {
    clockText.textContent = berlinClockFormatter.format(now);
  } else {
    clockText.textContent = now.toLocaleTimeString('de-DE', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  if (berlinDateFormatter) {
    dateText.textContent = berlinDateFormatter.format(now);
    return;
  }

  dateText.textContent = now.toLocaleDateString('de-DE', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function applySchedule(schedule) {
  const awake = schedule?.awake !== false;
  document.body.classList.toggle('display-is-sleeping', !awake);
  if (awake) {
    displaySleepOverlay.classList.add('hidden');
  } else {
    displaySleepText.textContent = schedule?.message || 'Aktiv von 08:00 bis 22:00';
    displaySleepOverlay.classList.remove('hidden');
  }
}

function animateSwitchIfNeeded(nextState) {
  const transitionsEnabledFlag = Boolean(nextState?.config?.transitions_enabled);
  const trackKey = `${nextState?.station?.id || ''}|${nextState?.artist || ''}|${nextState?.title || ''}`;
  if (!transitionsEnabledFlag) {
    lastTrackKey = trackKey;
    return;
  }
  if (!lastTrackKey || lastTrackKey === trackKey) {
    lastTrackKey = trackKey;
    return;
  }
  for (const element of [coverImage, displayMetaBlock]) {
    if (!element) continue;
    element.classList.remove('is-animating');
    void element.offsetWidth;
    element.classList.add('is-animating');
  }
  lastTrackKey = trackKey;
}

function renderWeather(displayWeather) {
  const days = displayWeather?.days || [];
  const current = displayWeather?.current || null;
  const location = displayWeather?.location || 'Falkensee';
  const hasDays = days.length > 0;
  const hasCurrent = Boolean(
    current && (
      current.temperature_c !== null && current.temperature_c !== undefined
      || current.surface_pressure_hpa !== null && current.surface_pressure_hpa !== undefined
      || current.condition
    )
  );

  weatherLocation.textContent = location;
  weatherDays.innerHTML = '';
  weatherError.classList.add('hidden');

  renderWeatherHeaderIcon(current, days);
  renderCurrentWeather(current);

  if (!hasDays) {
    if (!hasCurrent) {
      weatherPanel.classList.add('hidden');
    } else {
      weatherPanel.classList.remove('hidden');
    }
    return;
  }

  for (const day of days.slice(0, 2)) {
    const card = document.createElement('article');
    card.className = 'weather-day-card';
    card.innerHTML = `
      <div class="weather-day-top">
        <span class="weather-day-label">${escapeHtml(day.label || '')}</span>
        ${renderIconMarkup(day.icon_url, day.condition || 'Wetter', 'weather-day-icon-image')}
      </div>
      <p class="weather-day-condition">${escapeHtml(day.condition || 'Wetter')}</p>
      <p class="weather-day-temp">${formatTemperature(day.temp_max_c)} / ${formatTemperature(day.temp_min_c)}</p>
      <p class="weather-day-rain">${formatRainChance(day.precipitation_probability_max)}</p>
    `;
    weatherDays.appendChild(card);
  }
  weatherPanel.classList.remove('hidden');
}

function renderWeatherHeaderIcon(current, days) {
  if (!weatherHeaderIcon) {
    return;
  }

  const iconUrl = current?.icon_url || days?.[0]?.icon_url || '';
  const iconLabel = current?.condition || days?.[0]?.condition || 'Wetter';
  if (!iconUrl) {
    weatherHeaderIcon.src = '';
    weatherHeaderIcon.alt = '';
    weatherHeaderIcon.classList.add('hidden');
    return;
  }

  weatherHeaderIcon.src = iconUrl;
  weatherHeaderIcon.alt = iconLabel;
  weatherHeaderIcon.classList.remove('hidden');
}

function renderCurrentWeather(current) {
  const hasTemperature = current?.temperature_c !== null && current?.temperature_c !== undefined;
  const hasPressure = current?.surface_pressure_hpa !== null && current?.surface_pressure_hpa !== undefined;
  const hasCondition = Boolean(current?.condition);
  const hasCurrent = hasTemperature || hasPressure || hasCondition;

  if (!hasCurrent) {
    weatherCurrent.classList.add('hidden');
    weatherCurrentTemp.textContent = '--°';
    weatherCurrentCondition.textContent = '-';
    weatherCurrentPressure.textContent = 'Luftdruck: -';
    renderPressureTrend(null);
    return;
  }

  weatherCurrentTemp.textContent = formatTemperature(current?.temperature_c);
  weatherCurrentCondition.textContent = current?.condition || 'Aktuelles Wetter';
  weatherCurrentPressure.textContent = formatPressure(current?.surface_pressure_hpa);
  renderPressureTrend(current?.surface_pressure_trend || null);
  weatherCurrent.classList.remove('hidden');
}

function renderPressureTrend(trend) {
  if (!weatherCurrentPressureTrend) {
    return;
  }

  const iconMap = {
    up: { symbol: '↑', label: 'Luftdruck steigend' },
    down: { symbol: '↓', label: 'Luftdruck fallend' },
    steady: { symbol: '→', label: 'Luftdruck stabil' },
  };
  const trendConfig = iconMap[trend];

  weatherCurrentPressureTrend.classList.remove('is-up', 'is-down', 'is-steady');

  if (!trendConfig) {
    weatherCurrentPressureTrend.textContent = '';
    weatherCurrentPressureTrend.title = '';
    weatherCurrentPressureTrend.classList.add('hidden');
    return;
  }

  weatherCurrentPressureTrend.textContent = trendConfig.symbol;
  weatherCurrentPressureTrend.title = trendConfig.label;
  weatherCurrentPressureTrend.setAttribute('aria-label', trendConfig.label);
  weatherCurrentPressureTrend.classList.add(`is-${trend}`);
  weatherCurrentPressureTrend.classList.remove('hidden');
}

function renderIconMarkup(url, label, className) {
  if (!url) {
    return '<span class="weather-day-icon-fallback" aria-hidden="true"></span>';
  }
  return `<span class="weather-day-icon"><img class="${className}" src="${escapeHtml(url)}" alt="${escapeHtml(label)}"></span>`;
}

function formatTemperature(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--°';
  }
  return `${Math.round(Number(value))}°`;
}

function formatPressure(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Luftdruck: -';
  }
  return `Luftdruck: ${Math.round(Number(value))} hPa`;
}

function formatRainChance(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Niederschlag: -';
  }
  return `Niederschlag: ${Math.round(Number(value))}%`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function getLocalStreamUrl(nextState = state) {
  return nextState?.station?.stream_url || '';
}

function isUpnpRoute(audio = state?.local_audio) {
  return Boolean(audio && audio.route_kind === 'upnp' && audio.supports_transport);
}

function isUpnpTransportPlaying(audio = state?.local_audio) {
  return Boolean(audio && audio.transport_playing);
}

function updateLocalPlayerSource(nextState) {
  if (!localPlayer) {
    return;
  }

  if (isUpnpRoute(nextState?.local_audio)) {
    if (!localPlayer.paused) {
      localPlaybackRequested = false;
      localPlayer.pause();
    }
    return;
  }

  const streamUrl = getLocalStreamUrl(nextState);
  if (!streamUrl) {
    return;
  }

  if (localPlayer.dataset.streamUrl === streamUrl) {
    return;
  }

  const shouldResume = localPlaybackRequested;
  localPlayer.src = streamUrl;
  localPlayer.dataset.streamUrl = streamUrl;
  localPlayer.load();

  if (shouldResume) {
    localPlayer.play().catch((error) => {
      console.error(error);
      localPlaybackRequested = false;
      localPlaybackBusy = false;
      updateLocalPlayButton();
      setDisplayError('Lokale Wiedergabe konnte nicht neu gestartet werden.');
    });
  }
}

function updateLocalPlayButton() {
  if (!localPlayButton) {
    return;
  }

  const upnpRoute = isUpnpRoute();
  const isActive = upnpRoute
    ? isUpnpTransportPlaying()
    : Boolean(localPlayer && !localPlayer.paused && !localPlayer.ended);
  localPlayButton.classList.toggle('is-active', isActive);
  localPlayButton.classList.toggle('is-busy', localPlaybackBusy);
  localPlayButton.disabled = localPlaybackBusy;
  localPlayButton.setAttribute('aria-pressed', isActive ? 'true' : 'false');

  if (localPlaybackBusy) {
    localPlayButton.textContent = upnpRoute ? 'Sendet…' : 'Startet…';
    return;
  }

  if (upnpRoute) {
    localPlayButton.textContent = isActive ? 'WLAN aus' : 'WLAN';
    return;
  }

  localPlayButton.textContent = isActive ? 'Lokal aus' : 'Lokal';
}

function updateAudioControls(audio) {
  const available = Boolean(audio && audio.available);
  const volume = Number(audio?.volume_percent ?? 0);
  const muted = Boolean(audio?.muted);
  const prefix = isUpnpRoute(audio) ? 'WLAN' : 'RPi';
  displayLocalVolume.textContent = available
    ? `${prefix}: ${audio.selected_output_label || 'Audio'} · ${volume}%${muted ? ' · stumm' : ''}`
    : 'Ausgabe: nicht verfügbar';
  displayMuteButton.disabled = !available;
  displayVolDownButton.disabled = !available;
  displayVolUpButton.disabled = !available;
  displayMuteButton.textContent = muted ? 'Ton an' : 'Stumm';
}

function updatePlayPauseButton(nextState) {
  if (!displayPlayPauseButton) {
    return;
  }
  displayPlayPauseButton.textContent = nextState?.playing_hint ? 'Pause' : 'Play';
}

function clearDisplayError() {
  if (!errorText) {
    return;
  }
  if (displayErrorTimeoutId) {
    window.clearTimeout(displayErrorTimeoutId);
    displayErrorTimeoutId = null;
  }
  errorText.textContent = '';
  errorText.classList.add('hidden');
  delete errorText.dataset.kind;
}

function setDisplayError(message, options = {}) {
  if (!message || !errorText) {
    return;
  }

  const kind = options.kind || 'ui';
  const autoHideMs = Number.isFinite(options.autoHideMs) ? options.autoHideMs : 5000;

  if (displayErrorTimeoutId) {
    window.clearTimeout(displayErrorTimeoutId);
    displayErrorTimeoutId = null;
  }

  errorText.dataset.kind = kind;
  errorText.textContent = message;
  errorText.classList.remove('hidden');

  if (autoHideMs > 0) {
    displayErrorTimeoutId = window.setTimeout(() => {
      if (errorText.dataset.kind === kind) {
        clearDisplayError();
      }
    }, autoHideMs);
  }
}

function suppressBackgroundError(message) {
  if (!message) {
    return;
  }
  console.warn('Backend-Fehler auf Pi-Anzeige unterdrueckt:', message);
  if (errorText?.dataset.kind !== 'ui') {
    clearDisplayError();
  }
}

function setBackgroundIssueIndicator(messages) {
  if (!backgroundIssueIndicator) {
    return;
  }

  const filteredMessages = (Array.isArray(messages) ? messages : [messages])
    .filter((message) => typeof message === 'string' && message.trim().length > 0);

  if (!filteredMessages.length) {
    clearBackgroundIssueIndicator();
    return;
  }

  const tooltip = filteredMessages.join(' · ');
  backgroundIssueIndicator.textContent = '!';
  backgroundIssueIndicator.title = tooltip;
  backgroundIssueIndicator.setAttribute('aria-label', tooltip);
  backgroundIssueIndicator.classList.remove('hidden');
}

function clearBackgroundIssueIndicator() {
  if (!backgroundIssueIndicator) {
    return;
  }

  backgroundIssueIndicator.textContent = '!';
  backgroundIssueIndicator.title = '';
  backgroundIssueIndicator.removeAttribute('aria-label');
  backgroundIssueIndicator.classList.add('hidden');
}

async function startLocalPlayback() {
  if (localPlaybackBusy) {
    return;
  }

  if (isUpnpRoute()) {
    localPlaybackBusy = true;
    updateLocalPlayButton();
    try {
      const nextAudio = await postJson('/api/output/playback', { playing: true });
      state.local_audio = nextAudio;
      clearDisplayError();
      updateAudioControls(nextAudio);
    } catch (error) {
      console.error(error);
      setDisplayError('WLAN-Wiedergabe konnte nicht gestartet werden.');
    } finally {
      localPlaybackBusy = false;
      updateLocalPlayButton();
    }
    return;
  }

  if (!localPlayer) {
    return;
  }

  const streamUrl = getLocalStreamUrl(state);
  if (!streamUrl) {
    setDisplayError('Kein Sender für lokale Wiedergabe verfügbar.');
    return;
  }

  localPlaybackBusy = true;
  updateLocalPlayButton();

  try {
    if (localPlayer.dataset.streamUrl !== streamUrl) {
      localPlayer.src = streamUrl;
      localPlayer.dataset.streamUrl = streamUrl;
      localPlayer.load();
    }

    localPlaybackRequested = true;
    await localPlayer.play();
    clearDisplayError();
  } catch (error) {
    console.error(error);
    localPlaybackRequested = false;
    setDisplayError('Lokale Wiedergabe konnte nicht gestartet werden.');
  } finally {
    localPlaybackBusy = false;
    updateLocalPlayButton();
  }
}

async function stopLocalPlayback() {
  if (isUpnpRoute()) {
    localPlaybackBusy = true;
    updateLocalPlayButton();
    try {
      const nextAudio = await postJson('/api/output/playback', { playing: false });
      state.local_audio = nextAudio;
      updateAudioControls(nextAudio);
      clearDisplayError();
    } catch (error) {
      console.error(error);
      setDisplayError('WLAN-Wiedergabe konnte nicht gestoppt werden.');
    } finally {
      localPlaybackBusy = false;
      updateLocalPlayButton();
    }
    return;
  }

  if (!localPlayer) {
    return;
  }
  localPlaybackRequested = false;
  localPlaybackBusy = false;
  localPlayer.pause();
  updateLocalPlayButton();
}

async function toggleLocalPlayback() {
  if (isUpnpRoute()) {
    const isPlaying = isUpnpTransportPlaying();
    if (isPlaying) {
      await stopLocalPlayback();
      return;
    }
    await startLocalPlayback();
    return;
  }

  if (!localPlayer) {
    return;
  }

  const isPlaying = !localPlayer.paused && !localPlayer.ended;
  if (isPlaying) {
    await stopLocalPlayback();
    return;
  }

  await startLocalPlayback();
}

function applyState(nextState) {
  animateSwitchIfNeeded(nextState);
  state = nextState;
  stationName.textContent = nextState.station?.name || 'Radio Cover Bridge';
  title.textContent = nextState.title || 'Noch kein Titel';
  artist.textContent = nextState.artist || 'Bitte zuerst im Controller einen Sender auswählen.';
  setCover(nextState.cover_url);
  renderWeather(nextState.display_weather);
  updateLocalPlayerSource(nextState);
  updateAudioControls(nextState.local_audio || {});
  updatePlayPauseButton(nextState);
  applySchedule(nextState.display_schedule || null);

  if (controllerQrCard && nextState.controller_url) {
    controllerQrCard.title = nextState.controller_url;
    controllerQrCard.setAttribute('aria-label', nextState.controller_url);
  }

  const backgroundIssues = [];

  if (nextState.error) {
    backgroundIssues.push('Metadaten momentan nicht verfügbar');
    suppressBackgroundError(nextState.error);
  }

  if (nextState.display_weather?.error) {
    backgroundIssues.push('Wetterdaten momentan nicht verfügbar');
  }

  if (!backgroundIssues.length && errorText?.dataset.kind !== 'ui') {
    clearDisplayError();
  }

  if (backgroundIssues.length) {
    setBackgroundIssueIndicator(backgroundIssues);
  } else {
    clearBackgroundIssueIndicator();
  }

  updateLocalPlayButton();
}

function setShutdownStatus(message, isError = false) {
  if (!shutdownStatus) {
    return;
  }

  shutdownStatus.textContent = message;
  shutdownStatus.classList.remove('hidden');
  shutdownStatus.classList.toggle('is-error', isError);
}

async function requestPoweroff() {
  if (!shutdownButton || shutdownInProgress) {
    return;
  }

  const confirmed = window.confirm('Raspberry Pi jetzt sicher herunterfahren?');
  if (!confirmed) {
    return;
  }

  shutdownInProgress = true;
  shutdownButton.disabled = true;
  shutdownButton.textContent = 'Fährt herunter…';
  setShutdownStatus('Herunterfahren wird gestartet…');

  try {
    const response = await fetch('/api/system/poweroff', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    });

    const payload = await readJson(response);
    const message = payload?.message || payload?.detail || `HTTP ${response.status}`;
    if (!response.ok) {
      throw new Error(message);
    }

    setShutdownStatus(message);
  } catch (error) {
    shutdownInProgress = false;
    shutdownButton.disabled = false;
    shutdownButton.textContent = 'RPi aus';
    setShutdownStatus(error instanceof Error ? error.message : 'Herunterfahren fehlgeschlagen', true);
  }
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  });
  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(payload?.detail || `HTTP ${response.status}`);
  }
  return payload;
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function togglePlayingHint() {
  const nextPlaying = !Boolean(state.playing_hint);
  const nextState = await postJson('/api/playback', { playing: nextPlaying });
  applyState(nextState);
  if (localPlayer && localPlaybackRequested) {
    if (nextPlaying) {
      localPlayer.play().catch((error) => console.error(error));
    } else {
      localPlayer.pause();
    }
  }
}

async function selectRelativeStation(step) {
  const endpoint = step < 0 ? '/api/stations/prev' : '/api/stations/next';
  const nextState = await postJson(endpoint, {});
  applyState(nextState);
}

async function changeLocalVolume(delta) {
  const audio = await postJson('/api/audio/volume-delta', { delta });
  state.local_audio = audio;
  updateAudioControls(audio);
}

async function toggleMute() {
  const audio = await postJson('/api/audio/mute-toggle', {});
  state.local_audio = audio;
  updateAudioControls(audio);
}

async function loadState() {
  const response = await fetch('/api/state');
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const nextState = await response.json();
  applyState(nextState);
}

coverImage.addEventListener('error', () => {
  setCover(null);
});

if (weatherHeaderIcon) {
  weatherHeaderIcon.addEventListener('error', () => {
    weatherHeaderIcon.src = '';
    weatherHeaderIcon.alt = '';
    weatherHeaderIcon.classList.add('hidden');
  });
}

if (controllerQrImage && controllerQrFallback) {
  controllerQrImage.addEventListener('error', () => {
    controllerQrImage.classList.add('hidden');
    controllerQrFallback.classList.remove('hidden');
  });
}

if (shutdownButton) {
  shutdownButton.addEventListener('click', () => {
    requestPoweroff().catch((error) => console.error(error));
  });
}

if (localPlayButton) {
  localPlayButton.addEventListener('click', () => {
    toggleLocalPlayback().catch((error) => console.error(error));
  });
}

if (prevStationButton) {
  prevStationButton.addEventListener('click', () => {
    selectRelativeStation(-1).catch((error) => {
      console.error(error);
      setDisplayError(error instanceof Error ? error.message : 'Senderwechsel fehlgeschlagen');
    });
  });
}

if (nextStationButton) {
  nextStationButton.addEventListener('click', () => {
    selectRelativeStation(1).catch((error) => {
      console.error(error);
      setDisplayError(error instanceof Error ? error.message : 'Senderwechsel fehlgeschlagen');
    });
  });
}

if (displayPlayPauseButton) {
  displayPlayPauseButton.addEventListener('click', () => {
    togglePlayingHint().catch((error) => {
      console.error(error);
      setDisplayError(error instanceof Error ? error.message : 'Wiedergabe konnte nicht geändert werden');
    });
  });
}

if (displayMuteButton) {
  displayMuteButton.addEventListener('click', () => {
    toggleMute().catch((error) => {
      console.error(error);
      setDisplayError(error instanceof Error ? error.message : 'Stumm schalten fehlgeschlagen');
    });
  });
}

if (displayVolDownButton) {
  displayVolDownButton.addEventListener('click', () => {
    changeLocalVolume(-5).catch((error) => {
      console.error(error);
      setDisplayError(error instanceof Error ? error.message : 'Lautstärke konnte nicht verringert werden');
    });
  });
}

if (displayVolUpButton) {
  displayVolUpButton.addEventListener('click', () => {
    changeLocalVolume(5).catch((error) => {
      console.error(error);
      setDisplayError(error instanceof Error ? error.message : 'Lautstärke konnte nicht erhöht werden');
    });
  });
}

if (localPlayer) {
  localPlayer.volume = 1;
  localPlayer.addEventListener('playing', () => {
    localPlaybackRequested = true;
    localPlaybackBusy = false;
    updateLocalPlayButton();
  });
  localPlayer.addEventListener('pause', () => {
    if (!localPlaybackBusy) {
      updateLocalPlayButton();
    }
  });
  localPlayer.addEventListener('error', () => {
    localPlaybackRequested = false;
    localPlaybackBusy = false;
    updateLocalPlayButton();
    setDisplayError('Lokale Wiedergabe ist fehlgeschlagen.');
  });
}

applyState(state);
updateClock();

setInterval(() => {
  updateClock();
}, 1000);

setInterval(() => {
  loadState().catch((error) => console.error(error));
}, pollIntervalMs);
