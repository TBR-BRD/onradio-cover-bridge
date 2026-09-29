(function () {
  'use strict';

  var state = window.__INITIAL_STATE__ || {};
  var pollMs = window.__POLL_INTERVAL_MS__ || 5000;

  var cover = document.getElementById('tvCover');
  var stationName = document.getElementById('tvStationName');
  var titleEl = document.getElementById('tvTitle');
  var artistEl = document.getElementById('tvArtist');
  var clockEl = document.getElementById('tvClock');
  var dateEl = document.getElementById('tvDate');
  var weatherPanel = document.getElementById('tvWeatherPanel');
  var weatherIcon = document.getElementById('tvWeatherIcon');
  var weatherTemp = document.getElementById('tvWeatherTemp');
  var weatherCondition = document.getElementById('tvWeatherCondition');
  var weatherDays = document.getElementById('tvWeatherDays');
  var stationsList = document.getElementById('tvStationsList');

  var currentStationId = null;
  var knownStationIds = [];
  var selecting = false;

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function setCover(url) {
    var next = url || '/static/kein-cover.svg';
    if (cover.getAttribute('src') !== next) {
      cover.src = next;
    }
  }

  function renderWeather(weather) {
    var days = (weather && weather.days) || [];
    var current = (weather && weather.current) || null;
    var hasCurrent = Boolean(
      current && (
        (current.temperature_c !== null && current.temperature_c !== undefined) || current.condition
      )
    );

    if (!hasCurrent && !days.length) {
      weatherPanel.classList.add('hidden');
      return;
    }
    weatherPanel.classList.remove('hidden');

    if (current && current.icon_url) {
      weatherIcon.src = current.icon_url;
      weatherIcon.alt = current.condition || 'Wetter';
      weatherIcon.classList.remove('hidden');
    } else {
      weatherIcon.classList.add('hidden');
    }

    weatherTemp.textContent = (current && current.temperature_c !== null && current.temperature_c !== undefined)
      ? Math.round(current.temperature_c) + '°'
      : '--°';
    weatherCondition.textContent = (current && current.condition) || '-';

    weatherDays.innerHTML = days.slice(0, 3).map(function (day) {
      var max = (day.temp_max_c !== null && day.temp_max_c !== undefined) ? Math.round(day.temp_max_c) + '°' : '--°';
      var min = (day.temp_min_c !== null && day.temp_min_c !== undefined) ? Math.round(day.temp_min_c) + '°' : '--°';
      return '<div class="tv-weather-day">'
        + '<span class="tv-weather-day-label">' + escapeHtml(day.label || '') + '</span>'
        + '<span class="tv-weather-day-temp">' + max + ' / ' + min + '</span>'
        + '</div>';
    }).join('');
  }

  function stationItems() {
    return Array.prototype.slice.call(stationsList.querySelectorAll('.tv-station-item'));
  }

  function renderStations(stations, selectedId) {
    var ids = stations.map(function (s) { return s.id; });
    var listChanged = ids.length !== knownStationIds.length
      || ids.some(function (id, i) { return id !== knownStationIds[i]; });

    if (listChanged) {
      knownStationIds = ids;
      stationsList.innerHTML = stations.map(function (s) {
        return '<button type="button" class="tv-station-item" data-station-id="' + escapeHtml(s.id) + '" tabindex="0" role="option">'
          + escapeHtml(s.name)
          + '</button>';
      }).join('');

      var items = stationItems();
      items.forEach(function (btn) {
        btn.addEventListener('click', function () { selectStation(btn.dataset.stationId); });
      });

      if (!stationsList.contains(document.activeElement)) {
        var toFocus = items.find(function (btn) { return btn.dataset.stationId === selectedId; }) || items[0];
        if (toFocus) toFocus.focus();
      }
    }

    stationItems().forEach(function (btn) {
      var isCurrent = btn.dataset.stationId === selectedId;
      btn.classList.toggle('is-current', isCurrent);
      btn.setAttribute('aria-selected', isCurrent ? 'true' : 'false');
    });
  }

  function selectStation(stationId) {
    if (!stationId || selecting || stationId === currentStationId) {
      return;
    }
    selecting = true;
    fetch('/api/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ station_id: stationId }),
    })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (next) { if (next) applyState(next); })
      .catch(function () { /* next poll resyncs */ })
      .finally(function () { selecting = false; });
  }

  function applyState(next) {
    state = next;
    currentStationId = next.station && next.station.id;
    stationName.textContent = (next.station && next.station.name) || 'Radio Cover Bridge';
    titleEl.textContent = next.title || 'Noch kein Titel';
    artistEl.textContent = next.artist || 'Bitte einen Sender auswählen.';
    setCover(next.cover_url);
    renderWeather(next.display_weather);
    renderStations(next.stations || [], currentStationId);
  }

  function updateClock() {
    var now = new Date();
    clockEl.textContent = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    dateEl.textContent = now.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' });
  }

  function moveFocus(direction) {
    var items = stationItems();
    if (!items.length) return;
    var index = items.indexOf(document.activeElement);
    var nextIndex = index === -1 ? 0 : index + direction;
    if (nextIndex < 0) nextIndex = 0;
    if (nextIndex > items.length - 1) nextIndex = items.length - 1;
    items[nextIndex].focus();
    items[nextIndex].scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }

  // Android TV / Google TV remotes deliver D-pad presses as regular
  // KeyboardEvents inside a WebView (DPAD_LEFT/RIGHT -> ArrowLeft/ArrowRight,
  // DPAD_CENTER/ENTER -> Enter), so plain keydown handling is enough - no
  // native app-side key handling required.
  document.addEventListener('keydown', function (event) {
    if (event.key === 'ArrowLeft') {
      moveFocus(-1);
      event.preventDefault();
    } else if (event.key === 'ArrowRight') {
      moveFocus(1);
      event.preventDefault();
    } else if (event.key === 'Enter') {
      var active = document.activeElement;
      if (active && active.classList.contains('tv-station-item')) {
        selectStation(active.dataset.stationId);
        event.preventDefault();
      }
    }
  });

  function poll() {
    fetch('/api/state', { headers: { Accept: 'application/json' } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (next) { if (next) applyState(next); })
      .catch(function () { /* ignore, retry next interval */ });
  }

  applyState(state);
  updateClock();
  setInterval(updateClock, 1000);
  setInterval(poll, pollMs);
})();
