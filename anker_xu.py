"""Anker PowerConf C200 vendor controls (UVC extension unit 6).

Decoded from AnkerWork 3.0.4 (AWDeviceInterface.dll) and verified on hardware.

Selector map, unit 6, 60-byte buffers:
  13  device mode / factory reset ("01 01" = restore)  -- NEVER written here
  16  framing/FOV + mic pickup: [mode, apply, fov_lo, fov_hi, 0, pick_lo, pick_hi, 0...]
      pickup angle: 0 = omni-directional, 90 = directional (AnkerWork
      setDirectionalPickUp / setPickUpMode). The camera re-applies the FOV in
      bytes 2-3 on every write (resetting zoom), so set_pickup sends the FOV
      matching the current zoom and callers restore zoom/pan/tilt. Never read
      here: a read after a FOV change once hung the firmware.
  17  image orientation: [0 normal | 1 mirror | 2 upside down | 3 both (= rotate 180)]
      Not offered by AnkerWork for the C200, but verified against video frames.
      Applied in the camera, so every app sees it; survives stream restarts.
  18  anti-flicker in Hz    (same as the standard power-line control)
  19  HDR: [0|1]  -- write works, but GET_CUR always reports 1, so the
      state must be remembered by the app and re-sent on connect.

FOV presets: writing selector 16 makes the camera set its own zoom (values in
profiles.py, ANKER_C200.fov_zoom). We set the standard zoom control directly
instead: same picture, and it avoids a firmware hang seen when reading
selector 16 after a FOV change.
"""
import ctypes, fcntl

UNIT = 6
SEL_FRAMING = 16
SEL_FLIP = 17
SEL_HDR = 19
XU_LEN = 60


class _Query(ctypes.Structure):
    _fields_ = [("unit", ctypes.c_uint8), ("selector", ctypes.c_uint8), ("query", ctypes.c_uint8),
                ("size", ctypes.c_uint16), ("data", ctypes.c_void_p)]


_IOC = (3 << 30) | (ctypes.sizeof(_Query) << 16) | (ord('u') << 8) | 0x21
SET_CUR, GET_LEN = 0x01, 0x85
_WRITABLE = {SEL_HDR, SEL_FLIP, SEL_FRAMING}  # safety allowlist


def _xu(fd, sel, code, payload, size):
    buf = (ctypes.c_uint8 * size).from_buffer_copy(bytes(payload).ljust(size, b"\0")[:size])
    fcntl.ioctl(fd, _IOC, _Query(UNIT, sel, code, size, ctypes.addressof(buf)))
    return bytes(buf)


def _write(cam, sel, payload):
    if sel not in _WRITABLE:
        raise PermissionError(f"selector {sel} is not on the write allowlist")
    _xu(cam.fd, sel, SET_CUR, payload, XU_LEN)


def set_hdr(cam, on):
    _write(cam, SEL_HDR, bytes([1 if on else 0]))


def set_pickup(cam, angle, fov):
    """Mic pick-up mode: angle 0 (omni-directional) or 90 (directional).

    fov must be the FOV preset (degrees) closest to the current zoom; the camera
    applies it too, so restore zoom/pan/tilt afterwards if they were custom."""
    _write(cam, SEL_FRAMING, bytes([0, 0, fov & 0xFF, fov >> 8, 0, angle & 0xFF, angle >> 8]))


def set_orientation(cam, mirror, upside_down):
    _write(cam, SEL_FLIP, bytes([(1 if mirror else 0) | (2 if upside_down else 0)]))

