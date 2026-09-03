(function () {
  'use strict';

  var cover = document.getElementById('cover');
  // PNG is intentionally used here because the very old Android 5.1 WebView
  // on the BBuzzCanvas does not render the SVG placeholder reliably.
  var fallback = '/static/kein-cover.png';
  var currentUrl = '';
  var pollMs = 5000;

  function hasParam(name, value) {
    var search = (window.location.search || '').replace(/^\?/, '').split('&');
    var i;
    for (i = 0; i < search.length; i += 1) {
      var parts = search[i].split('=');
      if (decodeURIComponent(parts[0] || '') === name &&
          decodeURIComponent(parts[1] || '') === value) {
        return true;
      }
    }
    return false;
  }

  function getFitMode() {
    return hasParam('fit', 'cover') ? 'cover' : 'contain';
  }

  function getRotation() {
    if (hasParam('rotate', 'left')) {
      return -90;
    }
    if (hasParam('rotate', 'right')) {
      return 90;
    }
    if (hasParam('rotate', '180')) {
      return 180;
    }
    return 0;
  }

  function layoutCover() {
    var fit = getFitMode();
    var rotation = getRotation();
    var width = window.innerWidth || document.documentElement.clientWidth || 1;
    var height = window.innerHeight || document.documentElement.clientHeight || 1;
    var size = fit === 'cover' ? Math.max(width, height) : Math.min(width, height);

    cover.style.width = size + 'px';
    cover.style.height = size + 'px';
    cover.style.left = Math.round((width - size) / 2) + 'px';
    cover.style.top = Math.round((height - size) / 2) + 'px';
    cover.style.objectFit = fit;
    cover.style.webkitTransform = 'rotate(' + rotation + 'deg)';
    cover.style.transform = 'rotate(' + rotation + 'deg)';
    cover.style.webkitTransformOrigin = '50% 50%';
    cover.style.transformOrigin = '50% 50%';
  }

  function normalizeUrl(url) {
    if (!url) {
      return fallback;
    }
    return String(url);
  }

  function setCover(url) {
    var next = normalizeUrl(url);
    if (next === currentUrl) {
      return;
    }

    currentUrl = next;
    cover.className = 'fade';

    var probe = new Image();
    probe.onload = function () {
      cover.src = next;
      window.setTimeout(function () {
        cover.className = '';
      }, 40);
    };
    probe.onerror = function () {
      cover.src = fallback;
      currentUrl = fallback;
      window.setTimeout(function () {
        cover.className = '';
      }, 40);
    };
    probe.src = next;
  }

  function refresh() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/state?_=' + new Date().getTime(), true);
    xhr.timeout = 8000;

    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) {
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          var state = JSON.parse(xhr.responseText);
          setCover(state.cover_url || fallback);
        } catch (e) {
          // Keep the current cover on malformed state responses.
        }
      }
    };

    xhr.ontimeout = function () {};
    xhr.onerror = function () {};
    xhr.send();
  }

  cover.onerror = function () {
    if (cover.src.indexOf('kein-cover.png') === -1) {
      cover.src = fallback;
      currentUrl = fallback;
    }
  };

  layoutCover();
  window.onresize = layoutCover;
  refresh();
  window.setInterval(refresh, pollMs);
})();
