# Installation Guide (English)

## 1. Recommended setup

Use:
- Raspberry Pi 3
- Raspberry Pi OS with Desktop
- official Raspberry Pi 7-inch display
- Wi-Fi network
- UPnP / DLNA speaker such as Sonos or Denon

## 2. Prepare Raspberry Pi OS

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3-full python3-pip python3-venv unzip wtype swayidle unclutter
sudo raspi-config nonint do_ssh 0
sudo raspi-config nonint do_boot_behaviour B4
sudo raspi-config nonint do_boot_wait 1
sudo raspi-config nonint do_blanking 1
```

## 3. Copy the project

```bash
scp onradio-cover-bridge.zip pi@<PI-IP>:~
ssh pi@<PI-IP>
```

## 4. Install the application

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

## 5. Test start

```bash
cd /opt/onradio-cover-bridge
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Test:
- Controller: `http://<PI-IP>:8080/controller`
- Display: `http://127.0.0.1:8080/display`

Stop with `Ctrl+C`.

## 6. Install systemd service

```bash
sudo cp /opt/onradio-cover-bridge/scripts/onradio-cover.service /etc/systemd/system/onradio-cover.service
sudo systemctl daemon-reload
sudo systemctl enable --now onradio-cover.service
```

## 7. Enable shutdown button

```bash
sudo cp /opt/onradio-cover-bridge/scripts/onradio-cover-poweroff.sudoers /etc/sudoers.d/onradio-cover-poweroff
sudo chmod 440 /etc/sudoers.d/onradio-cover-poweroff
sudo visudo -cf /etc/sudoers.d/onradio-cover-poweroff
```

## 8. Configure kiosk start

```bash
cp /opt/onradio-cover-bridge/scripts/start-radio-display.sh /home/pi/start-radio-display.sh
chmod +x /home/pi/start-radio-display.sh

mkdir -p /home/pi/.config/labwc
printf '/home/pi/start-radio-display.sh\n' > /home/pi/.config/labwc/autostart
```

## 9. Hide cursor

```bash
bash /opt/onradio-cover-bridge/scripts/install-labwc-hide-cursor.sh
```

## 10. Reboot

```bash
sudo reboot
```
