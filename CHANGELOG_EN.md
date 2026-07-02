# Changelog

## [Unreleased]

- Added Apple iTunes Search API as an additional cover source before MusicBrainz and Amazon.
- UPnP stream relay now reconnects after upstream timeouts instead of ending the speaker stream.
- Added a UPnP playback watchdog that restarts Sonos/renderers after unexpected stops.
- Removed display sleep mode/schedule; the kiosk display now stays active.
- Added the controller address below the WLAN output line on the kiosk display and disabled QR code caching.

## [1.0.0] - 2026-03-31

### First public release
- Mobile web controller with clickable station list and no drop-down
- Raspberry Pi kiosk UI with cover art, clock, date, weather and QR code
- Weather panel for Falkensee with current conditions, temperature, pressure and forecast for today and tomorrow
- Cover proxy and placeholder image for missing album art
- Audio output via WLAN/UPnP speakers
- Support for Sonos- and Denon-like renderers
- Local UPnP stream relay on the Raspberry Pi
- QR code to open the controller directly
- Shutdown button on the Raspberry Pi display
- Display schedule from 08:00 to 22:00
- systemd service and Chromium kiosk startup script
- Hidden mouse cursor in kiosk mode
- Project structure prepared for a first GitHub publication
