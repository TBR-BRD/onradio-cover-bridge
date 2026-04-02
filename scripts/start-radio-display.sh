#!/usr/bin/env bash
set -eu

sleep 8

mkdir -p /home/pi/.config/chromium-kiosk

# X11-Fallback
if command -v unclutter >/dev/null 2>&1; then
  pkill -x unclutter >/dev/null 2>&1 || true
  DISPLAY="${DISPLAY:-:0}" unclutter -idle 0.1 -root >/dev/null 2>&1 &
fi

# Wayland/labwc
if command -v swayidle >/dev/null 2>&1 && command -v wtype >/dev/null 2>&1; then
  pkill -x swayidle >/dev/null 2>&1 || true
  swayidle -w timeout 6 'wtype -M alt -M logo -P h' >/dev/null 2>&1 &
fi

BROWSER_BIN=""
if command -v chromium >/dev/null 2>&1; then
  BROWSER_BIN="$(command -v chromium)"
elif command -v chromium-browser >/dev/null 2>&1; then
  BROWSER_BIN="$(command -v chromium-browser)"
else
  echo "Chromium wurde nicht gefunden." >&2
  exit 1
fi

"$BROWSER_BIN" \
  http://127.0.0.1:8080/display \
  --user-data-dir=/home/pi/.config/chromium-kiosk \
  --password-store=basic \
  --kiosk \
  --incognito \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --no-default-browser-check \
  --start-maximized \
  --hide-scrollbars \
  --window-size=800,480 &

BROWSER_PID=$!

sleep 2
if command -v wtype >/dev/null 2>&1; then
  wtype -M alt -M logo -P h >/dev/null 2>&1 || true
fi

wait "$BROWSER_PID"
