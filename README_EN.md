# OnRadio Cover Bridge

![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-3-C51A4A?logo=raspberrypi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Webserver-009688?logo=fastapi&logoColor=white)
![Chromium](https://img.shields.io/badge/Chromium-Kiosk-4285F4?logo=googlechrome&logoColor=white)
![UPnP](https://img.shields.io/badge/Audio-UPnP%20%2F%20DLNA-6A5ACD)
![Display](https://img.shields.io/badge/Display-RPi%207%22-222222)

A Raspberry Pi based **radio and information display** with a **mobile web controller**, **album artwork**, **clock**, **weather**, **QR code**, and **audio output to WLAN/UPnP speakers**.

The system is designed for a Raspberry Pi 3 with the official 7-inch display as a permanent kiosk display on a local home network.  
Control is handled comfortably from an iPhone or any other smartphone on the same Wi-Fi network.

## Highlights

- Internet radio control from a smartphone on the local network
- Album artwork, track info, clock, and weather on the Raspberry Pi display
- Audio output to WLAN/UPnP speakers such as Sonos or Denon
- Touch controls directly on the Raspberry Pi
- QR code for quick access to the web controller
- Automatic kiosk start after boot
- Optimized for small Raspberry Pi touch displays

## Features

### Radio / Stations
- Many internet radio stations selectable from the mobile web controller
- Direct clickable station list, no drop-down menu
- Start / stop playback
- Station switching from the controller
- Station switching directly on the Raspberry Pi display
- Playback through WLAN/UPnP speakers

### Display
- Large cover artwork on the left
- Title and artist on the right
- Large clock and date
- QR code to the controller
- Active speaker output line
- Weather panel for Falkensee

### Weather
- current conditions
- current temperature
- air pressure
- pressure trend arrow
- forecast for today and tomorrow
- weather icons

### System
- FastAPI web server
- Chromium kiosk on the Pi
- systemd service
- display schedule
- shutdown button on the Pi
- background errors handled unobtrusively

## Architecture

```text
Smartphone / iPhone
        |
        | HTTP / WLAN
        v
+----------------------+
|   Raspberry Pi 3     |
|----------------------|
| FastAPI Webserver    |
| Kiosk-Display        |
| Cover Logic          |
| Weather Service      |
| UPnP Stream Relay    |
+----------------------+
        |            \
        |             \
        v              v
  7" Raspberry        WLAN/UPnP
  Pi Display          Speaker
```

## Requirements

- Raspberry Pi 3
- Raspberry Pi OS with Desktop
- official Raspberry Pi display
- local Wi-Fi network
- smartphone / iPhone for the controller
- WLAN/UPnP speaker
- Python 3
- Chromium in kiosk mode

## Quick Start

### 1. Prepare the system

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3-full python3-pip python3-venv unzip wtype swayidle unclutter
sudo raspi-config nonint do_ssh 0
sudo raspi-config nonint do_boot_behaviour B4
sudo raspi-config nonint do_boot_wait 1
sudo raspi-config nonint do_blanking 1
```

### 2. Copy the project to the Pi

```bash
scp onradio-cover-bridge.zip pi@<PI-IP>:~
ssh pi@<PI-IP>
```

### 3. Install the project

```bash
unzip -o ~/onradio-cover-bridge.zip -d ~
sudo rm -rf /opt/onradio-cover-bridge
sudo mv ~/onradio-cover-bridge /opt/onradio-cover-bridge
sudo chown -R pi:pi /opt/onradio-cover-bridge

cd /opt/onradio-cover-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Test start

```bash
cd /opt/onradio-cover-bridge
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Then test:
- Controller: `http://<PI-IP>:8080/controller`
- Display: `http://127.0.0.1:8080/display`

### 5. Set up the systemd service

```bash
sudo cp /opt/onradio-cover-bridge/scripts/onradio-cover.service /etc/systemd/system/onradio-cover.service
sudo systemctl daemon-reload
sudo systemctl enable --now onradio-cover.service
```

### 6. Enable the shutdown button

```bash
sudo cp /opt/onradio-cover-bridge/scripts/onradio-cover-poweroff.sudoers /etc/sudoers.d/onradio-cover-poweroff
sudo chmod 440 /etc/sudoers.d/onradio-cover-poweroff
sudo visudo -cf /etc/sudoers.d/onradio-cover-poweroff
```

### 7. Configure kiosk start

```bash
cp /opt/onradio-cover-bridge/scripts/start-radio-display.sh /home/pi/start-radio-display.sh
chmod +x /home/pi/start-radio-display.sh

mkdir -p /home/pi/.config/labwc
printf '/home/pi/start-radio-display.sh\n' > /home/pi/.config/labwc/autostart
```

### 8. Hide the mouse pointer / stabilize kiosk mode

```bash
bash /opt/onradio-cover-bridge/scripts/install-labwc-hide-cursor.sh
```

### 9. Reboot

```bash
sudo reboot
```

## Access

- Mobile controller: `http://<PI-IP>:8080/controller`
- Raspberry Pi display: `http://127.0.0.1:8080/display`

## Notes

- Local Raspberry Pi audio output has been removed.
- Playback is handled through WLAN/UPnP speakers.
- Streams that cannot be reliably verified can be removed from the station list.
- For details see `INSTALLATION_EN.md`.
