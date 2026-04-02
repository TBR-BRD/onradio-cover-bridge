# GitHub-Veröffentlichung (Deutsch)

## Repository vorbereiten

Lege auf GitHub ein **leeres Repository** an, zum Beispiel:

- `onradio-cover-bridge`

Wichtig:
- kein vorinitialisiertes README
- keine Lizenzdatei
- keine `.gitignore`

## Projekt lokal initialisieren

```bash
cd onradio-cover-bridge
git init
git branch -M main
git add .
git commit -m "Initiale Veröffentlichung"
```

## Remote setzen

```bash
git remote add origin https://github.com/<BENUTZER-ODER-ORG>/onradio-cover-bridge.git
```

## Hochladen

```bash
git push -u origin main
```

## Hinweise

- Für die deutsche GitHub-Version ist `README.md` deutsch.
- Für die englische GitHub-Version ist `README.md` englisch.
- Die Archiv-Version enthält beide Sprachen parallel.
