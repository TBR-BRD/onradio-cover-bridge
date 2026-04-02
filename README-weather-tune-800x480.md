800x480 Wetter-Feintuning

Geändert wurde nur die Datei:
- app/static/styles.css

Inhalt des Updates:
- Wetterkasten für 800x480 etwas schmaler gemacht
- aktuelles Wettersymbol im Header größer gemacht
- Symbole für Heute/Morgen größer gemacht
- Innenabstände und Schriftgrößen im Wetterblock leicht reduziert

Installation auf dem Raspberry Pi:
1. ZIP auf den Pi kopieren
2. entpacken
3. styles.css nach /opt/onradio-cover-bridge/app/static/ kopieren
4. Dienst neu starten

Beispiel:
  unzip -o ~/weather_tune_800x480_patch.zip -d ~
  cp ~/weather_tune_800x480_patch/app/static/styles.css /opt/onradio-cover-bridge/app/static/
  sudo systemctl restart onradio-cover.service
