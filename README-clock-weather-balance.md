# Clock/Weather balance update for 800x480

Changes in this patch:
- larger clock and date on the Raspberry Pi display
- slightly smaller weather block for better balance on 800x480
- compact spacing tweaks so the weather content still fits cleanly

Installation on the Pi:

```bash
unzip -o ~/clock_weather_balance_patch.zip -d ~
cp ~/clock_weather_balance_patch/app/static/styles.css /opt/onradio-cover-bridge/app/static/
sudo systemctl restart onradio-cover.service
sudo reboot
```
