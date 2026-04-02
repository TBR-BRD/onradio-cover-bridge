#!/usr/bin/env bash
set -eu

CONFIG_DIR="${HOME}/.config/labwc"
TARGET_RC="${CONFIG_DIR}/rc.xml"
SOURCE_RC=""

mkdir -p "${CONFIG_DIR}"

if [ -f "${TARGET_RC}" ]; then
  :
elif [ -f /etc/xdg/labwc/rc.xml ]; then
  SOURCE_RC=/etc/xdg/labwc/rc.xml
elif [ -f /usr/share/labwc/rc.xml ]; then
  SOURCE_RC=/usr/share/labwc/rc.xml
else
  echo "Keine labwc rc.xml gefunden." >&2
  exit 1
fi

if [ -n "${SOURCE_RC}" ]; then
  cp "${SOURCE_RC}" "${TARGET_RC}"
fi

cp "${TARGET_RC}" "${TARGET_RC}.bak.$(date +%Y%m%d-%H%M%S)"

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

path = Path.home() / ".config/labwc/rc.xml"
text = path.read_text(encoding="utf-8")
root = ET.fromstring(text)

# Extract namespace if present
if root.tag.startswith("{"):
    ns_uri = root.tag.split("}", 1)[0][1:]
    ET.register_namespace("", ns_uri)
    def q(name: str) -> str:
        return f"{{{ns_uri}}}{name}"
else:
    def q(name: str) -> str:
        return name

keyboard = root.find(q("keyboard"))
if keyboard is None:
    keyboard = ET.SubElement(root, q("keyboard"))

already = False
for keybind in keyboard.findall(q("keybind")):
    if keybind.get("key") == "A-W-h":
        actions = [a.get("name") for a in keybind.findall(q("action"))]
        if "HideCursor" in actions:
            already = True
            break

if not already:
    keybind = ET.SubElement(keyboard, q("keybind"), {"key": "A-W-h"})
    ET.SubElement(keybind, q("action"), {"name": "HideCursor"})
    ET.SubElement(keybind, q("action"), {"name": "WarpCursor", "x": "-1", "y": "-1"})

ET.indent(root)  # Python 3.9+
ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
print(path)
PY

echo "labwc rc.xml aktualisiert: ${TARGET_RC}"
echo "Bitte anschließend den Kiosk-Start aktualisieren und neu booten."
