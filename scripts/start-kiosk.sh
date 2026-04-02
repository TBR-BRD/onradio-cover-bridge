#!/usr/bin/env bash
set -eu

sleep 8

if command -v unclutter >/dev/null 2>&1; then
  pkill -x unclutter >/dev/null 2>&1 || true
  unclutter -idle 0.1 -root &
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

exec "$BROWSER_BIN" \
  http://127.0.0.1:8080/display \
  --kiosk \
  --incognito \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --start-maximized \
  --hide-scrollbars \
  --window-size=800,480
