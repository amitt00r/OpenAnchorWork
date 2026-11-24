"""Supported camera models.

OpenAnchorWork only works with cameras that have a profile here: each profile
says how to recognise the model (USB vendor/product ID) and which of its
features the app offers. Other webcams are ignored on purpose.

To add a model later, add a Profile to PROFILES (and its USB ID to
system/70-openanchorwork.rules), then gate any model-specific code on the
profile's fields rather than on the model name.
"""
import glob, os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    key: str                    # stable id; also names the settings file
    name: str                   # shown in the UI
    vid: str                    # USB idVendor (lowercase hex)
    pid: str                    # USB idProduct
    fov_zoom: dict = field(default_factory=dict)  # FOV preset (degrees) -> zoom_absolute
    hdr: bool = False           # vendor HDR switch (anker_xu.set_hdr)
    orientation: bool = False   # vendor mirror / upside down (anker_xu.set_orientation)
    raw_auto_exposure: bool = False  # needs force_auto_exposure to re-enable auto exposure
    # Mic pick-up modes: (value sent to the camera, label); first is the default.
    pickup_modes: tuple = ()
    # Standard controls the firmware resets whenever a stream starts.
    stream_reset_keys: tuple = ()


ANKER_C200 = Profile(
    key="anker-c200",
    name="Anker PowerConf C200",
    vid="291a", pid="3369",
    fov_zoom={95: 100, 78: 175, 65: 295},
    hdr=True,
    orientation=True,
    raw_auto_exposure=True,
    pickup_modes=((0, "Omni-Directional (180°)"), (90, "Directional Pickup (90°)")),
    stream_reset_keys=("zoom_abs", "pan_abs", "tilt_abs"),
)

PROFILES = (ANKER_C200,)


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


@dataclass(frozen=True)
class Device:
    profile: Profile
    node: str          # /dev/videoN (capture node)
    usb_dir: str       # /sys/bus/usb/devices/<port>
    stream_iface: str  # sysfs dir of the UVC VideoStreaming interface

    @property
    def label(self):
        return self.profile.name


def find_devices():
    """Connected cameras that match a supported profile, in USB port order."""
    out = []
    for dev in sorted(glob.glob("/sys/bus/usb/devices/*")):
        vid, pid = _read(f"{dev}/idVendor"), _read(f"{dev}/idProduct")
        profile = next((p for p in PROFILES if (p.vid, p.pid) == (vid, pid)), None)
        if not profile:
            continue
        vs = next((i for i in sorted(glob.glob(f"{dev}/{os.path.basename(dev)}:*"))
                   if _read(f"{i}/bInterfaceClass") == "0e" and _read(f"{i}/bInterfaceSubClass") == "02"), None)
        nodes = sorted(v for v in glob.glob(f"{dev}/*/video4linux/video*") if _read(f"{v}/index") == "0")
        if vs and nodes:
            out.append(Device(profile, f"/dev/{os.path.basename(nodes[0])}", dev, vs))
    return out


def nearest_fov(profile, zoom):
    """FOV preset whose zoom value is closest to `zoom` (95 if the profile has none)."""
    if not profile.fov_zoom:
        return 95
    return min(profile.fov_zoom, key=lambda f: abs(profile.fov_zoom[f] - zoom))


def supported_names():
    return ", ".join(p.name for p in PROFILES)
