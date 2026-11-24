#!/bin/sh
# OpenAnchorWork installer (per user; run from wherever you keep this folder).
#  1. App menu entry.
#  2. Background watcher (user service): re-applies your settings when the camera
#     is plugged in and every time an app starts it (the C200 resets its FOV then).
#  3. udev rule (needs sudo): lets the app switch the C200's auto exposure back on.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
UNITS="$HOME/.config/systemd/user"
mkdir -p "$APPS" "$UNITS"

# Remove pieces from earlier versions ("C200 Control").
for old in c200-apply.service c200-watch.service; do
    systemctl --user disable --now "$old" 2>/dev/null || true
    rm -f "${UNITS:?}/${old:?}"
done
rm -f "${APPS:?}/c200-control.desktop"

sed "s|@DIR@|$DIR|g" "$DIR/openanchorwork.desktop" > "$APPS/openanchorwork.desktop"
echo "Menu entry installed: OpenAnchorWork"

sed "s|@DIR@|$DIR|g" "$DIR/system/openanchorwork-watch.service" > "$UNITS/openanchorwork-watch.service"
systemctl --user daemon-reload
systemctl --user enable --now openanchorwork-watch.service
systemctl --user restart openanchorwork-watch.service
echo "Background watcher running."

echo "Installing udev rule (needs sudo)..."
sudo rm -f /etc/udev/rules.d/70-anker-c200.rules
sudo cp "$DIR/system/70-openanchorwork.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change --subsystem-match=usb
echo "Done. Open OpenAnchorWork from your app menu."
