# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [Unreleased]

- Apple iTunes Search API als zusätzliche Coverquelle vor MusicBrainz und Amazon ergänzt.
- UPnP-Stream-Relay verbindet sich nach Upstream-Timeouts automatisch neu, statt den Lautsprecher-Stream zu beenden.
- UPnP-Wiedergabe-Watchdog ergänzt, der Sonos/Renderer nach einem unerwarteten Stopp automatisch neu startet.
- Display-Ruhemodus/Zeitfenster entfernt; die Kiosk-Anzeige bleibt dauerhaft aktiv.
- Controller-Adresse unter der WLAN-Ausgabe auf dem Kiosk-Display ergänzt und QR-Code-Caching deaktiviert.

## [1.0.0] - 2026-03-31

### Erste öffentliche Version
- Mobile-Webcontroller mit klickbarer Senderliste ohne Drop-down
- Kiosk-Oberfläche für Raspberry Pi mit Cover, Uhrzeit, Datum, Wetter und QR-Code
- Wetteranzeige für Falkensee mit aktuellem Zustand, Temperatur, Luftdruck und Vorhersage für heute und morgen
- Cover-Proxy und Platzhalterbild für fehlende Albumcover
- Audio-Ausgabe über WLAN-/UPnP-Lautsprecher
- Unterstützung für Sonos- und Denon-ähnliche Renderer
- Lokaler UPnP-Stream-Relay über den Raspberry Pi
- QR-Code zum direkten Öffnen des Controllers
- Shutdown-Button direkt auf dem Raspberry-Pi-Display
- Display-Zeitfenster von 08:00 bis 22:00 Uhr
- systemd-Service und Kiosk-Startskript für Chromium
- Ausblenden des Mauszeigers im Kiosk-Betrieb
- Deutsche Projektdokumentation und GitHub-taugliche Struktur
