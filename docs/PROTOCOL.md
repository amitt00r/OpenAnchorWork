# Anker PowerConf C200: vendor protocol and firmware quirks

Notes on how OpenAnchorWork controls the C200 (USB `291a:3369`). Everything here was worked out by studying
how AnkerWork 3.0.4 for Windows talks to the camera (`AWDeviceInterface.dll`) and then checked on real
hardware. No AnkerWork code is used or distributed.

## Standard controls

Brightness, contrast, saturation, sharpness, gamma, hue, white balance, focus, exposure, anti-flicker, zoom,
pan and tilt are ordinary UVC controls, set through V4L2 (`VIDIOC_S_CTRL`) in `v4l2ctl.py`.

## Vendor extension unit

The Anker features use UVC extension unit **6** (GUID `41769ea2-04de-e347-8b2b-f4341aff003b`), sent with
`UVCIOC_CTRL_QUERY`. Every selector uses a **60-byte** buffer.

| Selector | Meaning | Payload | Notes |
|---|---|---|---|
| 13 | Device mode / factory reset | `01 01` = restore | **Never written by OpenAnchorWork.** |
| 16 | Framing (FOV) + microphone pick-up | `[mode, apply, fov_lo, fov_hi, 0, pick_lo, pick_hi, 0…]` | See below. |
| 17 | Image orientation | `0` normal, `1` mirror, `2` upside down, `3` both (rotate 180°) | Not offered by AnkerWork for the C200, but verified against captured video frames. Survives stream restarts. |
| 18 | Anti-flicker (Hz) | | Same as the standard power-line control, which the app uses instead. |
| 19 | HDR | `0` / `1` | Writes work, but reads always return `1`, so the app remembers the state itself. |

`anker_xu.py` only writes selectors on an allowlist (16, 17, 19).

### Selector 16: FOV and Pick-Up Mode

AnkerWork's `setFov` writes `[mode, 1, fov_lo, fov_hi, 0]` with the angle in degrees (95, 78 or 65). The
camera then sets its own digital zoom:

| FOV | `zoom_absolute` |
|---|---|
| 95° | 100 |
| 78° | 175 |
| 65° | 295 |

OpenAnchorWork sets those zoom values through the standard zoom control instead. It gives the same picture,
and reading selector 16 right after a FOV change once hung the firmware until the camera was replugged.

AnkerWork's `setDirectionalPickUp` reads selector 16, keeps bytes 0–4 and writes the pick-up angle as a
little-endian 16-bit value in bytes 5–6: **`0` = omni-directional, `90` = directional**.

**Quirk:** every write to selector 16 re-applies the FOV in bytes 2–3, even with the apply byte at 0, which
resets the zoom. OpenAnchorWork never reads selector 16. It writes the FOV preset closest to the current zoom
together with the pick-up angle, then restores zoom, pan and tilt.

## Zoom resets at every stream start

The C200 resets digital zoom, and with it the FOV preset, whenever any app starts streaming. Teams, Meet or
Zoom would always get 95°.

`watcher.py` (the `openanchorwork-watch` user service) polls the camera's USB VideoStreaming interface twice
a second. When `bAlternateSetting` leaves 0 (idle), a stream has started, and it re-sends zoom, pan, tilt,
HDR, orientation and Pick-Up Mode about 0.5 s and 2 s later. The app's own preview does the same when its
first frame arrives.

## Auto exposure

The C200 reports "manual" as its only valid exposure mode (`GET_RES` on `CT_AE_MODE_CONTROL` returns
`0x01`). The Linux `uvcvideo` driver trusts that, so once exposure is set to manual it refuses to switch
back to auto, although the camera accepts it.

A USB reset does not help: the firmware keeps the mode. What works:

1. Detach `uvcvideo` from the camera's VideoControl interface (`USBDEVFS_DISCONNECT`).
2. Claim the interface and send `SET_CUR` on `CT_AE_MODE_CONTROL` (request type `0x21`, request `0x01`,
   `wValue 0x0200`, `wIndex 0x0100`, data `0x02` = auto).
3. Release the interface and let `uvcvideo` reattach (`USBDEVFS_CONNECT`).

This needs write access to the camera's `/dev/bus/usb/…` node, which `system/70-openanchorwork.rules` grants
to the logged-in user (`TAG+="uaccess"`). See `force_auto_exposure` in `v4l2ctl.py`. Without the rule,
replugging the camera restores auto exposure.

## Not on the C200

AI framing, Auto-Frame/Solo-Frame, gesture control and the other AnkerWork camera features belong to other
models (C300, C310, C302). The C200's AnkerWork screen only offers FOV, HDR, anti-flicker, resolution, the
standard image controls and Pick-Up Mode.
