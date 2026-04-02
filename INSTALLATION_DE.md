# Installationsanleitung – von Raspberry Pi OS frisch bis zum aktuellen Stand

Diese Anleitung installiert die aktuelle Version des Projekts auf einem frisch installierten **Raspberry Pi 3** mit **Raspberry Pi OS with Desktop**.

Die Anleitung geht davon aus:

- Benutzername auf dem Pi: `pi`
- IP-Adresse des Pi: `192.168.42.212`
- Das ZIP liegt auf dem Mac unter `~/Downloads/onradio-cover-bridge-feature-pack.zip`

## 1. Raspberry Pi OS installieren

1. Raspberry Pi Imager öffnen.
2. **Raspberry Pi OS with Desktop** auswählen.
3. SD-Karte schreiben.
4. Pi starten und mit WLAN oder LAN verbinden.
5. Auf dem Pi anmelden.

## 2. System vorbereiten

Direkt auf dem Raspberry Pi im Terminal:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3-full python3-pip python3-venv unzip wtype swayidle unclutter git bluez pulseaudio-utils
sudo raspi-config nonint do_ssh 0
sudo raspi-config nonint do_boot_behaviour B4
sudo raspi-config nonint do_boot_wait 1
sudo raspi-config nonint do_blanking 1
hostname -I
```

## 3. ZIP vom Mac auf den Pi kopieren

Auf dem Mac:

```bash
scp ~/Downloads/onradio-cover-bridge-feature-pack.zip pi@192.168.42.212:~
ssh pi@192.168.42.212
```

## 4. Projekt entpacken und nach /opt kopieren

Auf dem Pi:

```bash
unzip -o ~/onradio-cover-bridge-feature-pack.zip -d ~
sudo rm -rf /opt/onradio-cover-bridge
sudo mv ~/onradio-cover-bridge /opt/onradio-cover-bridge
sudo chown -R pi:pi /opt/onradio-cover-bridge
cd /opt/onradio-cover-bridge
```

## 5. Python-Umgebung anlegen

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Teststart

```bash
cd /opt/onradio-cover-bridge
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Testen:

- Mobile, Tablet oder Mac: `http://192.168.42.212:8080/controller`
- Pi: `http://127.0.0.1:8080/display`

Dann mit `Ctrl+C` wieder beenden.

## 7. systemd-Dienst einrichten

```bash
sudo cp /opt/onradio-cover-bridge/scripts/onradio-cover.service /etc/systemd/system/onradio-cover.service
sudo systemctl daemon-reload
sudo systemctl enable --now onradio-cover.service
sudo systemctl status onradio-cover.service
```

Wenn du die Controller-URL fest vorgeben willst, bearbeite die Service-Datei:

```bash
sudo nano /etc/systemd/system/onradio-cover.service
```

Im `[Service]`-Block ergänzen:

```ini
Environment=CONTROLLER_URL_OVERRIDE=http://192.168.42.212:8080/controller
```

Danach:

```bash
sudo systemctl daemon-reload
sudo systemctl restart onradio-cover.service
```

## 8. Shutdown-Button und Update-Neustart freischalten

```bash
sudo cp /opt/onradio-cover-bridge/scripts/onradio-cover-poweroff.sudoers /etc/sudoers.d/onradio-cover-poweroff
sudo chmod 440 /etc/sudoers.d/onradio-cover-poweroff
sudo visudo -cf /etc/sudoers.d/onradio-cover-poweroff

sudo cp /opt/onradio-cover-bridge/scripts/onradio-cover-restart.sudoers /etc/sudoers.d/onradio-cover-restart
sudo chmod 440 /etc/sudoers.d/onradio-cover-restart
sudo visudo -cf /etc/sudoers.d/onradio-cover-restart
```

## 9. labwc-Cursor-Hide einrichten

```bash
/opt/onradio-cover-bridge/scripts/install-labwc-hide-cursor.sh
```

## 10. Kiosk-Startskript einrichten

```bash
cp /opt/onradio-cover-bridge/scripts/start-radio-display.sh /home/pi/start-radio-display.sh
chmod +x /home/pi/start-radio-display.sh
mkdir -p /home/pi/.config/labwc
printf '/home/pi/start-radio-display.sh
' > /home/pi/.config/labwc/autostart
```

## 11. Panel-Notifications optional abschalten

Wenn du im Kiosk keine Update-Meldungen willst:

```bash
sudo cp /etc/xdg/labwc/autostart /etc/xdg/labwc/autostart.bak
sudo sed -i '/wf-panel-pi/s/^/# /' /etc/xdg/labwc/autostart
mkdir -p /home/pi/.config/wf-panel-pi
cat > /home/pi/.config/wf-panel-pi/wf-panel-pi.ini <<'EOF2'
notify_enable=false
notify_timeout=1
EOF2
```

## 12. Neustart

```bash
sudo reboot
```

## 13. Nach dem Neustart

- Auf dem Pi startet automatisch die Kiosk-Anzeige.
- Auf dem Mobile, Tablet oder Mac steuerst du das System über:

```text
http://192.168.42.212:8080/controller
```

## 14. WLAN-Lautsprecher (UPnP) nutzen

- Lautsprecher in den Pairing-Modus setzen.
- Im Controller **WLAN-Lautsprecher suchen** antippen.
- Beim gefundenen Gerät **Koppeln** oder **Verbinden** wählen.
- Danach **Als Ausgabe** wählen.
- Für Klinke im Bereich **Audio am Raspberry Pi** einfach **Klinke** antippen.

## 15. Update-Funktion im Controller

Das Direkt-Update im Controller ist nur für eine **Git-Installation** aktiv.

Wenn du Updates direkt aus dem Controller willst, installiere das Projekt später per `git clone` in `/opt/onradio-cover-bridge` statt per ZIP. Für eine ZIP-Installation zeigt der Controller den Update-Status an, startet aber kein Direkt-Update.

## 16. Fehlerdiagnose

Dienststatus:

```bash
sudo systemctl status onradio-cover.service
```

Live-Log:

```bash
sudo journalctl -u onradio-cover.service -f
```

Aktuellen Zustand prüfen:

```bash
curl http://127.0.0.1:8080/api/state
```
