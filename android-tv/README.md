# OnRadio TV (Google TV / Android TV)

Eigenständige Android-TV-App, die das Radio-Erlebnis des Raspberry-Pi-Projekts
(`app/`) **ohne laufenden Pi** direkt auf einem Google-TV-/Android-TV-Gerät
nachbildet: Albumcover links, Sendername/Titel/Interpret/Uhr/Wetter rechts,
Sender per Fernbedienung (D-Pad) auswählbar, Wiedergabe direkt auf dem
Fernseher.

Dies ist **Phase 1** eines mehrstufigen Plans (siehe Projekt-Chat):

| Phase | Inhalt | Status |
|---|---|---|
| 1 | Senderliste, Metadaten, Cover, Wetter, Wiedergabe auf dem TV selbst | **diese App** |
| 2 | Google Cast (an Chromecast-fähige Geräte werfen) | offen |
| 3 | UPnP/DLNA (Sonos, Denon) | offen |
| – | AirPlay | **bewusst ausgeschlossen** - siehe unten |

## Warum kein AirPlay

Das Pi-Projekt nutzt dafür `pyatv`, eine Python-spezifische Bibliothek. Für
Android/Kotlin gibt es keine funktionierende, gepflegte AirPlay-Sender-
Implementierung. Wer AirPlay-Lautsprecher weiter nutzen möchte, braucht dafür
weiterhin den Pi (oder ein anderes AirPlay-fähiges Quellgerät) - diese App
deckt das nicht ab.

## Woher die Senderliste kommt

`app/src/main/res/raw/stations.json` enthält **alle 253 Sender** aus
`app/stations.py` (Python-Seite) - erzeugt durch ein einmaliges Skript, das
`station_catalog()` direkt ausführt und als JSON exportiert (kein manuelles
Abtippen, keine Übertragungsfehler). Wird die Senderliste auf der Pi-Seite
geändert, muss dieses JSON neu generiert werden:

```bash
cd .. # Projekt-Root
python3 - <<'EOF'
import dataclasses, sys, json
_orig = dataclasses.dataclass
def patched(*a, **kw):
    kw.pop("slots", None)
    return _orig(*a, **kw)
dataclasses.dataclass = patched  # nur noetig auf Python < 3.10

sys.path.insert(0, ".")
from app.stations import STATIONS

def group_for(station_id):
    if station_id.startswith("on-"): return "ON Radio"
    if station_id.startswith("80s80s-"): return "80s80s"
    if station_id.startswith("sunshine-live"): return "Sunshine Live"
    if station_id.startswith("radio-bob-"): return "RADIO BOB!"
    if station_id.startswith("ffh-"): return "HIT RADIO FFH"
    if station_id.startswith("absolut-"): return "Absolut Radio"
    if station_id.startswith("energy-"): return "ENERGY"
    return "Weitere Sender"

out = []
for s in STATIONS:
    d = dataclasses.asdict(s)
    out.append({
        "id": d["id"], "name": d["name"], "group": group_for(d["id"]),
        "homepageUrl": d["homepage_url"],
        "audioUrl": d["audio_url"], "audioMode": d["audio_mode"],
        "metadataUrl": d["metadata_url"], "metadataMode": d["metadata_mode"],
        "metadataStationLabel": d["metadata_station_label"],
        "metadataStationAliases": list(d["metadata_station_aliases"]),
        "metadataStationId": d["metadata_station_id"],
    })
with open("android-tv/app/src/main/res/raw/stations.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
EOF
```

## Metadaten-Abdeckung (ehrlicher Stand)

Von den 253 Sendern nutzen:

- **193** `icy_stream` (Titel direkt aus dem Audio-Stream, ICY-Protokoll) - **voll implementiert**
- **18** `0nradio_json` (JSON-API der ON-Radio-Familie) - **voll implementiert**
- **42** `80s80s_api` (80s80s-eigene JSON-API mit Sender-Matching) - **nicht implementiert**, zeigt nur Sendername + „Livestream" statt echtem Titel

Das deckt **83 % der Sender mit echten Titel-/Interpret-Infos** ab. Die
80s80s-Sender funktionieren zum Abspielen genauso gut, zeigen nur keine
Metadaten.

## Cover-Art

Nur **iTunes Search API** (öffentlich, kein Key nötig), einfachste
Treffer-Auswahl. Die MusicBrainz/Cover-Art-Archive- und Amazon-Fallbacks aus
`app/cover_provider.py` sind (noch) nicht portiert - Cover-Trefferquote ist
dadurch etwas niedriger als auf der Pi-Seite, aber für die meisten aktuellen/
bekannten Titel ausreichend.

## Bauen

1. Android Studio (aktuelle Version) öffnen, diesen Ordner (`android-tv/`)
   als Projekt öffnen lassen, Gradle-Sync abwarten.
2. Google-TV-Gerät per ADB verbinden (`adb connect <tv-ip>:5555`, ADB-Debugging
   in den Google-TV-Entwicklereinstellungen aktivieren) oder einen
   Android-TV-Emulator in Android Studio anlegen.
3. „Run" - die App erscheint danach auch als normale App-Kachel auf dem
   Google-TV-Startbildschirm (Leanback-Launcher-Kategorie ist gesetzt).

**Wichtiger Hinweis:** Dieser Code wurde außerhalb von Android Studio
geschrieben (kein Android-SDK/Emulator in der Entwicklungsumgebung verfügbar)
und daher **nicht kompiliert getestet** - nur sorgfältig gegengelesen. Der
erste Build in Android Studio ist der eigentliche Test. Meldungen zu
Fehlern gerne zurückmelden, dann wird gezielt nachgebessert.

## Bedienung

- **OK** auf dem „Sender"-Knopf öffnet die Senderauswahl
- Die Auswahl ist **zweispaltig**: links Kategorien (ON Radio, RADIO BOB!, ENERGY, HIT RADIO FFH, Absolut Radio, 80s80s, Sunshine Live, Weitere Sender), rechts die Sender der markierten Kategorie
- **◀ / ▶**: zwischen Kategorie- und Senderspalte wechseln
- **▲ / ▼**: innerhalb der aktiven Spalte navigieren
- **OK** auf einem Sender: abspielen und Auswahl schließen
- **Zurück**: Auswahl schließen, ohne umzuschalten
- Metadaten/Cover aktualisieren sich alle 15 Sekunden, Wetter alle 10 Minuten

## Standort für Wetter ändern

Aktuell fest auf „Falkensee" (`WeatherRepository`-Konstruktor in
`TvViewModel.kt`) - bei Bedarf dort `locationName`/`countryCode` anpassen.
