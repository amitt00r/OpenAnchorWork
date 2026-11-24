"""Saved settings for OpenAnchorWork: load/save and push them to the camera.

One settings file per camera profile (~/.config/openanchorwork/<profile>.json).
Shared by the GUI (app.py) and the background watcher (watcher.py), so it must
not import GTK.
"""
import json, os, shutil

from v4l2ctl import CID, FLAG_INACTIVE
import anker_xu
from profiles import nearest_fov

_XDG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
CONFIG_DIR = os.path.join(_XDG, "openanchorwork")
_LEGACY_C200 = os.path.join(_XDG, "c310-control", "settings.json")  # before the rename

# Order matters when re-applying saved settings: auto modes before manual values.
PERSIST_ORDER = ["wb_auto", "focus_auto", "power_line", "brightness", "contrast", "saturation",
                 "sharpness", "gamma", "hue", "wb_temp", "focus_abs", "exposure_abs",
                 "zoom_abs", "pan_abs", "tilt_abs"]


def config_file(profile):
    return os.path.join(CONFIG_DIR, f"{profile.key}.json")


def load_settings(profile):
    path = config_file(profile)
    if not os.path.exists(path) and profile.key == "anker-c200" and os.path.exists(_LEGACY_C200):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copy2(_LEGACY_C200, path)  # carry settings over from "C200 Control"
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(profile, data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = config_file(profile)
    with open(path + ".tmp", "w") as f:
        json.dump(data, f, indent=2)
    os.replace(path + ".tmp", path)


def apply_settings(cam, profile, data, keys=None):
    """Apply saved settings to a camera, skipping values its auto modes override.

    keys limits which standard controls are sent; the profile's vendor
    controls (HDR, mirror/upside down, mic pick-up) are always sent."""
    applied = 0
    # Mic pick-up first: its command also re-applies a FOV preset, and the
    # zoom/pan/tilt sent below put any custom framing back.
    if profile.pickup_modes and "pickup" in data:
        try:
            zoom = data.get("zoom_abs")
            if zoom is None:
                zoom = cam.get(CID["zoom_abs"])
            anker_xu.set_pickup(cam, data["pickup"], nearest_fov(profile, zoom))
            applied += 1
        except OSError:
            pass
    for key in (keys or PERSIST_ORDER):
        if key not in data:
            continue
        try:
            if cam.query(CID[key]).flags & FLAG_INACTIVE:
                continue
            cam.set(CID[key], data[key])
            applied += 1
        except OSError:
            pass
    vendor = []
    if profile.hdr and "hdr" in data:
        vendor.append(lambda: anker_xu.set_hdr(cam, data["hdr"]))
    if profile.orientation and ("mirror" in data or "upside_down" in data):
        vendor.append(lambda: anker_xu.set_orientation(cam, data.get("mirror", False),
                                                       data.get("upside_down", False)))
    for send in vendor:
        try:
            send()
            applied += 1
        except OSError:
            pass
    return applied
