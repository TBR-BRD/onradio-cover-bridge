# GitHub Publishing (English)

## Prepare the repository

Create an **empty repository** on GitHub, for example:

- `onradio-cover-bridge`

Important:
- no pre-created README
- no license file
- no `.gitignore`

## Initialize the project locally

```bash
cd onradio-cover-bridge
git init
git branch -M main
git add .
git commit -m "Initial release"
```

## Add the remote

```bash
git remote add origin https://github.com/<USER-OR-ORG>/onradio-cover-bridge.git
```

## Push

```bash
git push -u origin main
```

## Notes

- The German GitHub version uses a German `README.md`.
- The English GitHub version uses an English `README.md`.
- The archive version contains both languages side by side.
