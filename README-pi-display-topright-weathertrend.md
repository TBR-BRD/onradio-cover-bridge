# Patch: Pi-Display oben rechts + Luftdruck-Trend

Dieses Update ändert die Raspberry-Pi-Anzeige wie folgt:

- entfernt den Status "Wiedergabe läuft" auf der Pi-Display-Seite
- verschiebt den Button "RPi aus" nach oben rechts
- setzt das aktuelle Wettersymbol im Wetterkopf rechtsbündig und vertikal mittig zu "Wetter / Falkensee"
- ergänzt neben der Luftdruckanzeige einen Trendpfeil:
  - `↑` steigend
  - `↓` fallend
  - `→` stabil

Der Trend wird jeweils gegen den zuletzt erfolgreich geladenen Luftdruckwert verglichen.
Nach dem ersten Wetterabruf direkt nach einem Neustart kann der Pfeil daher noch fehlen,
bis ein zweiter Wetterabruf erfolgt ist.

## Installation auf dem Raspberry Pi

```bash
unzip -o ~/pi_display_topright_weathertrend_patch.zip -d ~
cp ~/pi_display_topright_weathertrend_patch/app/templates/display.html /opt/onradio-cover-bridge/app/templates/
cp ~/pi_display_topright_weathertrend_patch/app/static/display.js /opt/onradio-cover-bridge/app/static/
cp ~/pi_display_topright_weathertrend_patch/app/static/styles.css /opt/onradio-cover-bridge/app/static/
cp ~/pi_display_topright_weathertrend_patch/app/weather_service.py /opt/onradio-cover-bridge/app/
sudo systemctl restart onradio-cover.service
sudo reboot
```
