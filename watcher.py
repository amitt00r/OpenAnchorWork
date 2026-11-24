#!/usr/bin/env python3
"""OpenAnchorWork background watcher.

For every connected camera with a supported profile (see profiles.py):
* when it is plugged in: apply all saved settings;
* when any app starts streaming from it (Teams, Meet, Zoom, OBS, the preview...):
  re-send the controls its firmware resets at stream start (for the C200:
  zoom/pan/tilt, which carry the FOV preset).

Stream starts are detected from the USB VideoStreaming interface switching
from alternate setting 0 (idle) to a bandwidth-carrying setting. Polls twice
a second; uses no measurable CPU.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4l2ctl import Camera  # noqa: E402
from profiles import find_devices  # noqa: E402
from settings_store import apply_settings, load_settings  # noqa: E402

POLL = 0.5
REAPPLY_DELAYS = (0.5, 2.0)  # seconds after the stream starts


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def apply(dev, keys=None, why=""):
    try:
        cam = Camera(dev.node)
    except OSError as e:
        print(f"cannot open {dev.node}: {e.strerror}", flush=True)
        return
    try:
        n = apply_settings(cam, dev.profile, load_settings(dev.profile), keys)
        print(f"{dev.profile.name} {why}: applied {n} setting(s) to {dev.node}", flush=True)
    finally:
        cam.close()


def main():
    streaming = {}  # usb_dir -> currently streaming?
    while True:
        devices = {d.usb_dir: d for d in find_devices()}
        new = [d for k, d in devices.items() if k not in streaming]
        if new:
            time.sleep(2)  # let the firmware finish booting
            for d in new:
                apply(d, why="connected")
        streaming = {k: streaming.get(k, False) for k in devices}
        for k, d in devices.items():
            now = read(f"{d.stream_iface}/bAlternateSetting") not in (None, "0")
            if now and not streaming[k] and d.profile.stream_reset_keys:
                start = time.monotonic()
                for delay in REAPPLY_DELAYS:
                    time.sleep(max(0.0, start + delay - time.monotonic()))
                    apply(d, list(d.profile.stream_reset_keys), why=f"stream started (+{delay}s)")
            streaming[k] = now
        time.sleep(POLL)


if __name__ == "__main__":
    main()
