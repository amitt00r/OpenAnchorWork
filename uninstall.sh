#!/bin/sh
# Remove what install.sh set up. Your saved settings in ~/.config/openanchorwork
# are kept; delete that folder yourself if you want them gone.
set -e
APPS="$HOME/.local/share/applications"
UNITS="$HOME/.config/systemd/user"

systemctl --user disable --now openanchorwork-watch.service 2>/dev/null || true
rm -f "${UNITS:?}/openanchorwork-watch.service"
systemctl --user daemon-reload
rm -f "${APPS:?}/openanchorwork.desktop"
echo "Removed the menu entry and the background watcher."

if [ -f /etc/udev/rules.d/70-openanchorwork.rules ]; then
    echo "Removing the udev rule (needs sudo)..."
    sudo rm -f /etc/udev/rules.d/70-openanchorwork.rules
    sudo udevadm control --reload-rules
fi
echo "Done."
