"""Minimal V4L2 control access via ioctl (no external deps)."""
import ctypes, fcntl, os

def _IOWR(t, nr, size): return (3 << 30) | (size << 16) | (ord(t) << 8) | nr

class v4l2_queryctrl(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("type", ctypes.c_uint32), ("name", ctypes.c_char * 32),
                ("minimum", ctypes.c_int32), ("maximum", ctypes.c_int32), ("step", ctypes.c_int32),
                ("default_value", ctypes.c_int32), ("flags", ctypes.c_uint32), ("reserved", ctypes.c_uint32 * 2)]

class v4l2_control(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("value", ctypes.c_int32)]

class v4l2_querymenu(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("id", ctypes.c_uint32), ("index", ctypes.c_uint32), ("name", ctypes.c_char * 32),
                ("reserved", ctypes.c_uint32)]

QUERYCTRL = _IOWR('V', 36, ctypes.sizeof(v4l2_queryctrl))
G_CTRL = _IOWR('V', 27, ctypes.sizeof(v4l2_control))
S_CTRL = _IOWR('V', 28, ctypes.sizeof(v4l2_control))
QUERYMENU = _IOWR('V', 37, ctypes.sizeof(v4l2_querymenu))
NEXT_CTRL = 0x80000000
FLAG_DISABLED, FLAG_READ_ONLY, FLAG_INACTIVE = 0x1, 0x4, 0x10
TYPE_INT, TYPE_BOOL, TYPE_MENU, TYPE_CLASS = 1, 2, 3, 6

# Well-known control IDs
CID = {
    "brightness": 0x00980900, "contrast": 0x00980901, "saturation": 0x00980902, "hue": 0x00980903,
    "wb_auto": 0x0098090c, "gamma": 0x00980910, "power_line": 0x00980918, "wb_temp": 0x0098091a,
    "sharpness": 0x0098091b, "backlight": 0x0098091c,
    "exposure_auto": 0x009a0901, "exposure_abs": 0x009a0902, "exposure_dyn_fps": 0x009a0903,
    "pan_abs": 0x009a0908, "tilt_abs": 0x009a0909, "focus_abs": 0x009a090a, "focus_auto": 0x009a090c,
    "zoom_abs": 0x009a090d,
}

class Control:
    def __init__(self, q, menu):
        self.id, self.type, self.name = q.id, q.type, q.name.decode(errors="replace")
        self.min, self.max, self.step, self.default, self.flags = q.minimum, q.maximum, q.step, q.default_value, q.flags
        self.menu = menu
    def __repr__(self):
        return f"<{self.name} 0x{self.id:08x} t={self.type} [{self.min}..{self.max}/{self.step}] def={self.default} menu={self.menu}>"

class Camera:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd = None
    def controls(self):
        out, q = {}, v4l2_queryctrl(id=NEXT_CTRL)
        while True:
            try: fcntl.ioctl(self.fd, QUERYCTRL, q)
            except OSError: break
            if q.type != TYPE_CLASS and not (q.flags & FLAG_DISABLED):
                menu = {}
                if q.type == TYPE_MENU:
                    for i in range(q.minimum, q.maximum + 1):
                        m = v4l2_querymenu(id=q.id, index=i)
                        try: fcntl.ioctl(self.fd, QUERYMENU, m); menu[i] = m.name.decode()
                        except OSError: pass
                out[q.id] = Control(q, menu)
            q = v4l2_queryctrl(id=q.id | NEXT_CTRL)
        return out
    def query(self, cid):
        q = v4l2_queryctrl(id=cid)
        fcntl.ioctl(self.fd, QUERYCTRL, q)
        return q
    def get(self, cid):
        c = v4l2_control(id=cid); fcntl.ioctl(self.fd, G_CTRL, c); return c.value
    def set(self, cid, value):
        c = v4l2_control(id=cid, value=int(value)); fcntl.ioctl(self.fd, S_CTRL, c)


# ---------------------------------------------------------------- raw USB access
# Needs write access to the camera's /dev/bus/usb node (granted to the desktop
# user by system/70-openanchorwork.rules).

def usb_node_for(devpath):
    """/dev/videoN -> /dev/bus/usb/BBB/DDD of the USB device it belongs to."""
    d = os.path.realpath(f"/sys/class/video4linux/{os.path.basename(devpath)}/device/..")
    bus, dev = (int(open(f"{d}/{f}").read()) for f in ("busnum", "devnum"))
    return f"/dev/bus/usb/{bus:03d}/{dev:03d}"


def has_usb_access(devpath):
    try:
        return os.access(usb_node_for(devpath), os.R_OK | os.W_OK)
    except OSError:
        return False


class _CtrlTransfer(ctypes.Structure):
    _fields_ = [("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8), ("wValue", ctypes.c_uint16),
                ("wIndex", ctypes.c_uint16), ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p)]


class _DevIoctl(ctypes.Structure):
    _fields_ = [("ifno", ctypes.c_int), ("ioctl_code", ctypes.c_int), ("data", ctypes.c_void_p)]


_USBDEVFS_CONTROL = _IOWR('U', 0, ctypes.sizeof(_CtrlTransfer))
_USBDEVFS_CLAIM = (2 << 30) | (4 << 16) | (ord('U') << 8) | 15
_USBDEVFS_RELEASE = (2 << 30) | (4 << 16) | (ord('U') << 8) | 16
_USBDEVFS_IOCTL = _IOWR('U', 18, ctypes.sizeof(_DevIoctl))
_USBDEVFS_DISCONNECT, _USBDEVFS_CONNECT = (ord('U') << 8) | 22, (ord('U') << 8) | 23


def force_auto_exposure(devpath, terminal_id=1, interface=0):
    """Put a camera back into auto exposure with a raw UVC SET_CUR.

    The C200 reports "manual" as its only valid exposure mode, so uvcvideo
    rejects auto mode. The camera does accept it, so the uvcvideo driver is
    briefly detached, CT_AE_MODE_CONTROL=0x02 (auto) is sent directly, and
    the driver is reattached. The video node disappears for about a second.
    Returns the AE mode the camera reports afterwards (0x02 = auto)."""
    fd = os.open(usb_node_for(devpath), os.O_RDWR)
    w_value, w_index = 0x02 << 8, (terminal_id << 8) | interface

    def ctrl(req_type, req, payload):
        buf = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        fcntl.ioctl(fd, _USBDEVFS_CONTROL, _CtrlTransfer(req_type, req, w_value, w_index, len(payload),
                                                          1000, ctypes.addressof(buf)))
        return bytes(buf)
    try:
        fcntl.ioctl(fd, _USBDEVFS_IOCTL, _DevIoctl(interface, _USBDEVFS_DISCONNECT, None))
        try:
            fcntl.ioctl(fd, _USBDEVFS_CLAIM, ctypes.c_uint(interface))
            ctrl(0x21, 0x01, b"\x02")            # SET_CUR auto
            mode = ctrl(0xA1, 0x81, b"\x00")[0]  # GET_CUR
            fcntl.ioctl(fd, _USBDEVFS_RELEASE, ctypes.c_uint(interface))
        finally:
            fcntl.ioctl(fd, _USBDEVFS_IOCTL, _DevIoctl(interface, _USBDEVFS_CONNECT, None))
    finally:
        os.close(fd)
    return mode
