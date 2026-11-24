#!/usr/bin/env python3
"""OpenAnchorWork — an open-source Linux companion app for Anker webcams.

Only cameras with a profile in profiles.py are offered (currently the Anker
PowerConf C200). Standard UVC controls plus the vendor features decoded from
AnkerWork (FOV presets, HDR, mirror / upside down; see anker_xu.py).
"""
import json, os, subprocess, sys, threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")
from gi.repository import Adw, Gdk, GLib, Gst, Gtk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4l2ctl import CID, FLAG_INACTIVE, Camera, force_auto_exposure, has_usb_access  # noqa: E402
import anker_xu  # noqa: E402
from profiles import find_devices, nearest_fov, supported_names  # noqa: E402
from settings_store import PERSIST_ORDER, apply_settings, load_settings, save_settings  # noqa: E402

APP_NAME = "OpenAnchorWork"
APP_ID = "io.github.openanchorwork"
SERVICE = "openanchorwork-watch.service"
PREVIEW_MODES = [(2560, 1440, "2K"), (1920, 1080, "1080p"), (1280, 720, "720p"), (640, 360, "360p")]

CSS = """
@define-color accent_bg_color #00a0e9;
@define-color accent_fg_color #ffffff;
@define-color accent_color #33b5f0;
window.oaw { background-color: #0f1115; color: #e8eaee; }
.oaw headerbar { background-color: #0f1115; box-shadow: none; border-bottom: 1px solid #1f232b; }
.oaw .app-title { font-weight: 700; font-size: 15px; letter-spacing: 0.3px; }
.oaw .device-chip { background-color: #1b1f26; border-radius: 18px; padding: 2px 6px; }
.oaw .preview-card { background-color: #000; border-radius: 16px; }
.oaw .preview-placeholder { color: #6b7280; font-size: 14px; }
.oaw .choice { padding: 8px 10px; border-radius: 10px; }
.oaw .choice:hover { background-color: #232832; }
.oaw .choice radio { margin-right: 10px; }
.oaw .choice radio:checked { background-color: #00a0e9; color: #fff; }
.oaw .section-title { color: #8b93a1; font-size: 12px; font-weight: 700; letter-spacing: 0.8px;
                       margin: 18px 4px 8px 4px; }
.oaw .card { background-color: #1c2028; border-radius: 14px; padding: 4px 0; box-shadow: none; }
.oaw .row { padding: 12px 16px; }
.oaw .row + .row { border-top: 1px solid #262b34; }
.oaw .row-title { font-size: 14px; }
.oaw .row-sub { color: #7d8594; font-size: 12px; }
.oaw .preview-note { color: #7d8594; font-size: 12px; }
.oaw .view-seg button { padding: 2px 12px; min-height: 24px; font-size: 12px; }
.oaw .row-value { color: #9aa3b2; font-size: 13px; font-feature-settings: "tnum"; }
.oaw .badge { background-color: #2a2f39; color: #9aa3b2; border-radius: 6px; padding: 1px 7px;
               font-size: 11px; font-weight: 600; }
.oaw switch:checked { background-color: #00a0e9; }
.oaw scale highlight { background-color: #00a0e9; }
.oaw scale trough { background-color: #2c313b; min-height: 4px; }
.oaw scale slider { background-color: #ffffff; min-width: 16px; min-height: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.5); }
.oaw .segmented { background-color: #12151a; border-radius: 10px; padding: 3px; }
.oaw .segmented button { background: none; border-radius: 8px; min-height: 30px; font-weight: 600;
                          color: #aab2bf; box-shadow: none; }
.oaw .segmented button:checked { background-color: #00a0e9; color: #fff; }
.oaw .dpad button { min-width: 34px; min-height: 34px; border-radius: 17px; background-color: #262b34; }
.oaw .dpad button:hover { background-color: #303642; }
.oaw .accent-btn { background-color: #00a0e9; color: #fff; font-weight: 600; border-radius: 10px; }
.oaw .ghost-btn { background-color: #232832; color: #d6dae1; font-weight: 600; border-radius: 10px; }
.oaw .disabled-row { opacity: 0.55; }
.oaw .badge-on { background-color: rgba(0,160,233,.18); color: #4cc3f5; border-radius: 6px; padding: 2px 8px;
                  font-size: 11px; font-weight: 700; }
.oaw .dock { background-color: #15181e; border-top: 1px solid #1f232b; }
.oaw .dock-bar { padding: 12px 20px; }
.oaw .dock-caption { color: #8b93a1; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; }
.oaw .dock-sep { margin: 4px 14px; background-color: #262b34; }
.oaw .dock-btn > button { min-width: 84px; padding: 8px 6px; border-radius: 12px; background: none; color: #c9ced6; }
.oaw .dock-btn > button:hover { background-color: #1f232b; }
.oaw .dock-btn > button:checked { background-color: #23384a; color: #ffffff; }
.oaw .dock-btn image { -gtk-icon-size: 22px; }
.oaw .dock-label { font-size: 12px; font-weight: 600; }
popover.oaw-popover > contents { background-color: #1c2028; border-radius: 16px; padding: 4px 0;
                                  box-shadow: 0 8px 28px rgba(0,0,0,.55); border: 1px solid #2a2f39; }
popover.oaw-popover > arrow { background-color: #1c2028; border: 1px solid #2a2f39; }
popover.oaw-popover .card { background: none; }
"""


# --------------------------------------------------------------------------- settings
# --------------------------------------------------------------------------- preview
class Preview:
    """GStreamer MJPEG preview rendered into a Gtk.Picture."""

    def __init__(self, picture, on_state, on_first_frame=None):
        self.picture, self.on_state, self.on_first_frame = picture, on_state, on_first_frame
        self._got_frame = False
        self.pipeline = None
        self._pending = None
        self._lock = threading.Lock()

    def start(self, device, width, height, mirror):
        self.stop()
        self._got_frame = False
        # videoflip is always present so mirroring can be toggled live, without
        # restarting the stream (which would make the C200 reset its zoom).
        desc = (f"v4l2src device={device} ! image/jpeg,width={width},height={height} ! "
                f"jpegdec ! videoconvert ! videoflip name=flip video-direction={'horiz' if mirror else 'identity'} ! "
                "video/x-raw,format=RGB ! "
                "appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false")
        try:
            self.pipeline = Gst.parse_launch(desc)
        except GLib.Error as e:
            self.on_state(False, str(e))
            return
        self.pipeline.get_by_name("sink").connect("new-sample", self._on_sample)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_error)
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.stop()
            self.on_state(False, "Camera is busy — close other apps using it")
        else:
            self.on_state(True, None)

    def set_mirror(self, mirror):
        if self.pipeline:
            self.pipeline.get_by_name("flip").set_property("video-direction", "horiz" if mirror else "identity")

    def stop(self):
        if self.pipeline:
            self.pipeline.get_bus().remove_signal_watch()
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        self.picture.set_paintable(None)

    def _on_error(self, _bus, msg):
        err, _dbg = msg.parse_error()
        self.stop()
        busy = "busy" in err.message.lower() or "resource" in err.message.lower()
        self.on_state(False, "Camera is busy — close other apps using it" if busy else err.message)

    def _on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        s = sample.get_caps().get_structure(0)
        w, h = s.get_value("width"), s.get_value("height")
        buf = sample.get_buffer()
        data = buf.extract_dup(0, buf.get_size())
        with self._lock:
            first = self._pending is None
            self._pending = (w, h, data)
        if first:
            GLib.idle_add(self._present)
        return Gst.FlowReturn.OK

    def _present(self):
        with self._lock:
            frame, self._pending = self._pending, None
        if frame and self.pipeline:
            w, h, data = frame
            stride = len(data) // h
            tex = Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(data), stride)
            self.picture.set_paintable(tex)
            if not self._got_frame:
                self._got_frame = True
                if self.on_first_frame:
                    self.on_first_frame()
        return False


# --------------------------------------------------------------------------- UI helpers
def label(text, *classes, xalign=0.0, hexpand=False):
    lb = Gtk.Label(label=text, xalign=xalign, hexpand=hexpand)
    for c in classes:
        lb.add_css_class(c)
    return lb


def card():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.add_css_class("card")
    return box


def row_box(vertical=False):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                  spacing=8 if vertical else 12)
    box.add_css_class("row")
    return box


# --------------------------------------------------------------------------- window
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.add_css_class("oaw")
        self.set_default_size(1180, 860)

        self.cam = None
        self.ctrls = {}
        self.rows = {}           # key -> dict(widgets)
        self._updating = False
        self._save_src = 0
        self._retry_src = 0
        # Per-camera state; filled in when a supported camera is opened.
        self.devices = []
        self.dev = self.profile = None
        self.settings = {}
        self.preview_mode = 2
        self.self_view = False

        self.toasts = Adw.ToastOverlay()
        tv = Adw.ToolbarView()
        tv.add_top_bar(self._build_header())
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self._build_preview())
        self.dock = Adw.Bin()
        self.dock.add_css_class("dock")
        body.append(self.dock)
        tv.set_content(body)
        self.toasts.set_child(tv)
        self.set_content(self.toasts)

        self.preview = Preview(self.picture, self._on_preview_state, self._on_stream_started)
        self.connect("close-request", self._on_close)
        self.refresh_devices()

    # ---------------- header
    def _build_header(self):
        hb = Adw.HeaderBar()
        title = Gtk.Box(spacing=8)
        icon = Gtk.Image.new_from_icon_name("camera-web-symbolic")
        title.append(icon)
        title.append(label(APP_NAME, "app-title"))
        hb.set_title_widget(title)

        chip = Gtk.Box(spacing=4)
        chip.add_css_class("device-chip")
        self.device_model = Gtk.StringList()
        self.device_dd = Gtk.DropDown(model=self.device_model)
        self.device_dd.add_css_class("flat")
        self.device_dd.connect("notify::selected", lambda *_: self._open_selected())
        chip.append(self.device_dd)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Rescan cameras")
        refresh.add_css_class("flat")
        refresh.connect("clicked", lambda *_: self.refresh_devices())
        chip.append(refresh)
        hb.pack_start(chip)
        return hb

    # ---------------- preview
    def _build_preview(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        outer.set_margin_top(20); outer.set_margin_bottom(12)
        outer.set_margin_start(20); outer.set_margin_end(20)

        aspect = Gtk.AspectFrame(ratio=16 / 9, obey_child=False, hexpand=True, vexpand=True)
        overlay = Gtk.Overlay(hexpand=True, vexpand=True)
        aspect.set_child(overlay)
        frame = Gtk.Box(hexpand=True, vexpand=True)
        frame.add_css_class("preview-card")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.picture = Gtk.Picture(hexpand=True, vexpand=True, content_fit=Gtk.ContentFit.COVER)
        frame.append(self.picture)
        overlay.set_child(frame)

        self.placeholder = label("Starting preview…", "preview-placeholder", xalign=0.5)
        self.placeholder.set_halign(Gtk.Align.CENTER); self.placeholder.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.placeholder)

        outer.append(aspect)

        # "Others see" shows the camera's own output unchanged (what call apps send);
        # "Self view" mirrors it like the self-view thumbnail in those apps.
        note = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        note.add_css_class("preview-note")
        note.set_margin_top(10)
        seg = Gtk.Box(homogeneous=True, spacing=2, valign=Gtk.Align.CENTER)
        seg.add_css_class("segmented"); seg.add_css_class("view-seg")
        others = Gtk.ToggleButton(label="Other's View", active=not self.self_view)
        mine = Gtk.ToggleButton(label="Self View", group=others, active=self.self_view)
        others.set_tooltip_text("The camera's output unchanged: what other people in the call see")
        mine.set_tooltip_text("Mirrored, like the self-view thumbnail in Teams, Google Meet and Zoom")
        mine.connect("toggled", self._on_view_toggled)
        self.view_btns = (others, mine)
        self.view_bar = note
        seg.append(others); seg.append(mine)
        note.append(seg)
        outer.append(note)
        return outer

    def _on_view_toggled(self, btn):
        if self._updating:
            return
        self.self_view = btn.get_active()
        self.settings["_self_view"] = self.self_view
        self._queue_save()
        self.preview.set_mirror(self.self_view)

    def _on_preview_state(self, playing, error):
        self.placeholder.set_visible(not playing)
        if playing:
            return
        self.placeholder.set_label(error or ("Starting preview…" if self.cam else "No supported camera connected"))
        if error and self.cam and not self._retry_src:
            # Always-on preview: keep retrying (e.g. while another app is using the camera).
            self._retry_src = GLib.timeout_add_seconds(3, self._retry_preview)

    def _on_stream_started(self):
        # The C200 resets zoom (FOV) and mirror whenever a stream starts: re-send them.
        if self.cam:
            GLib.timeout_add(300, self._reapply_stream_settings)

    def _reapply_stream_settings(self):
        if self.cam:
            apply_settings(self.cam, self.profile, self.settings, list(self.profile.stream_reset_keys))
        return False

    def _retry_preview(self):
        self._retry_src = 0
        self._restart_preview()
        return False

    def _restart_preview(self):
        if self.cam:
            w, h, _ = PREVIEW_MODES[self.preview_mode]
            self.preview.start(self.cam.path, w, h, self.self_view)
        else:
            self.preview.stop()
            self._on_preview_state(False, None)

    # ---------------- devices
    def refresh_devices(self):
        # Only cameras with a supported profile are listed; other webcams are ignored.
        self.devices = find_devices()
        names = [d.label for d in self.devices]
        names = [f"{n} ({names[:i].count(n) + 1})" if names.count(n) > 1 else n for i, n in enumerate(names)]
        self._updating = True
        self.device_model.splice(0, self.device_model.get_n_items(), names or ["No supported camera"])
        self.device_dd.set_selected(0)
        self.device_dd.set_sensitive(len(self.devices) > 1)
        self._updating = False
        self._open_selected()

    def _open_selected(self):
        if self._updating:
            return
        self.preview.stop()
        if self.cam:
            self.cam.close(); self.cam = None
        i = self.device_dd.get_selected()
        self.dev = self.devices[i] if self.devices and i < len(self.devices) else None
        self.profile = self.dev.profile if self.dev else None
        self.settings = load_settings(self.profile) if self.profile else {}
        for old in ("_mirror", "flip"):  # keys from earlier versions
            self.settings.pop(old, None)
        self.preview_mode = self.settings.get("_preview_mode", 2)
        self.self_view = bool(self.settings.get("_self_view", False))
        self._updating = True
        self.view_btns[1 if self.self_view else 0].set_active(True)
        self._updating = False
        self.view_bar.set_visible(self.dev is not None)
        if self.dev:
            try:
                self.cam = Camera(self.dev.node)
                self.ctrls = self.cam.controls()
                apply_settings(self.cam, self.profile, self.settings)
            except OSError as e:
                self.cam, self.ctrls = None, {}
                self.toast(f"Cannot open camera: {e.strerror}")
        self._build_controls()
        self._restart_preview()

    # ---------------- bottom control dock
    def _category(self, icon, title, rows):
        """A dock button that opens a popover holding one category's controls."""
        rows = [r for r in rows if r is not None]
        if not rows:
            return None
        c = card()
        c.add_css_class("popover-card")
        c.set_size_request(380, -1)
        head = label(title.upper(), "section-title")
        head.set_margin_start(16)
        c.append(head)
        for r in rows:
            c.append(r)
        pop = Gtk.Popover(child=c, position=Gtk.PositionType.TOP)
        pop.add_css_class("oaw-popover")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.append(Gtk.Image.new_from_icon_name(icon))
        inner.append(label(title, "dock-label", xalign=0.5))
        btn = Gtk.MenuButton(child=inner, popover=pop, direction=Gtk.ArrowType.UP,
                             always_show_arrow=False, tooltip_text=f"{title} settings")
        btn.add_css_class("dock-btn")
        return btn

    def _resolution_row(self):
        """Radio list of preview resolutions, shown inside the Resolution popup."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("choice-list")
        group = None
        for i, (w, h, name) in enumerate(PREVIEW_MODES):
            row = Gtk.Box(spacing=12)
            row.append(label(name, "row-title", hexpand=True))
            row.append(label(f"{w} × {h}", "row-sub"))
            b = Gtk.CheckButton(child=row, active=(i == self.preview_mode))
            b.add_css_class("choice")
            if group:
                b.set_group(group)
            group = group or b
            b.connect("toggled", self._on_res_selected, i)
            box.append(b)
        note = label("Preview only — video calls choose their own resolution.", "row-sub")
        note.set_margin_top(6); note.set_margin_start(6)
        box.append(note)
        r = row_box(vertical=True)
        r.append(box)
        return r

    def _pickup_row(self):
        """Mic Pick-Up Mode: radio list of the profile's modes."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("choice-list")
        title = label("Pick-Up Mode", "row-title")
        title.set_margin_start(6); title.set_margin_bottom(4)
        box.append(title)
        modes = self.profile.pickup_modes
        current = self.settings.get("pickup", modes[0][0])
        self.pickup_btns = {}
        group = None
        for value, name in modes:
            b = Gtk.CheckButton(child=label(name, "row-title", hexpand=True), active=(value == current))
            b.add_css_class("choice")
            if group:
                b.set_group(group)
            group = group or b
            b.connect("toggled", self._on_pickup_selected, value)
            box.append(b)
            self.pickup_btns[value] = b
        note = label("Directional focuses on voices in front of the camera and suppresses sound "
                     "from the sides.", "row-sub")
        note.set_wrap(True); note.set_max_width_chars(40)
        note.set_margin_top(6); note.set_margin_start(6)
        box.append(note)
        r = row_box(vertical=True)
        r.append(box)
        return r

    def _on_pickup_selected(self, btn, value):
        if not btn.get_active() or self._updating or not self.cam:
            return
        keep = {}
        for key in ("zoom_abs", "pan_abs", "tilt_abs"):  # the command also re-applies a FOV preset
            try:
                keep[key] = self.cam.get(CID[key])
            except OSError:
                pass
        try:
            anker_xu.set_pickup(self.cam, value, nearest_fov(self.profile, keep.get("zoom_abs", 100)))
        except OSError as e:
            self.toast(f"Could not set Pick-Up Mode: {e.strerror}")
            return
        for key, v in keep.items():
            try:
                self.cam.set(CID[key], v)
            except OSError:
                pass
        self.settings["pickup"] = value
        self._queue_save()

    def _on_res_selected(self, btn, index):
        if not btn.get_active() or index == self.preview_mode:
            return
        self.preview_mode = index
        self.settings["_preview_mode"] = index
        self._queue_save()
        self._restart_preview()
        GLib.timeout_add(150, lambda: self.res_popover.popdown() or False)

    def _service_row(self):
        """Shows whether the background watcher (openanchorwork-watch.service) is running."""
        r = row_box()
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        txt.append(label("Background Service", "row-title"))
        active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE]).returncode == 0
        sub = label("Keeps your FOV and HDR when other apps use the camera" if active
                    else "Not running: FOV resets to 95° in other apps. Run install.sh", "row-sub")
        sub.set_wrap(True); sub.set_max_width_chars(34)
        txt.append(sub)
        r.append(txt)
        badge = label("Active" if active else "Off", "badge-on" if active else "badge")
        badge.set_valign(Gtk.Align.CENTER)
        r.append(badge)
        return r

    def _have(self, *keys):
        return all(CID[k] in self.ctrls for k in keys)

    def _build_controls(self):
        self.rows = {}
        self.vendor_switches = {}
        self.fov_btns = {}
        self.pickup_btns = {}
        if not self.cam:
            empty = label(f"Connect a supported camera ({supported_names()}) and press rescan.",
                          "row-sub", xalign=0.5)
            empty.set_margin_top(24); empty.set_margin_bottom(24)
            self.dock.set_child(empty)
            return
        prof = self.profile

        bar = Gtk.Box(spacing=6)
        bar.add_css_class("dock-bar")

        # FOV presets inline — discrete buttons, nothing to drag by accident
        if prof.fov_zoom and self._have("zoom_abs"):
            fov = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
            fov.append(label("FIELD OF VIEW", "dock-caption", xalign=0.5))
            seg = Gtk.Box(homogeneous=True, spacing=2)
            seg.add_css_class("segmented")
            group = None
            for f in prof.fov_zoom:
                b = Gtk.ToggleButton(label=f"{f}°")
                if group: b.set_group(group)
                group = group or b
                b.connect("toggled", self._on_fov, f)
                seg.append(b)
                self.fov_btns[f] = b
            seg.set_size_request(210, -1)
            fov.append(seg)
            bar.append(fov)
            bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, css_classes=["dock-sep"]))

        cats = Gtk.Box(spacing=2, hexpand=True, halign=Gtk.Align.CENTER)
        z = lambda k, *a, **kw: self._slider_row(k, *a, **kw) if self._have(k) else None
        sw = lambda k, *a, **kw: self._switch_row(k, *a, **kw) if self._have(k) else None
        groups = [
            ("camera-video-symbolic", "Video", [
                self._vendor_row("hdr", "HDR", "Balances bright and dark areas", anker_xu.set_hdr, True)
                if prof.hdr else None,
                self._vendor_row("mirror", "Mirror", "Flip left and right, in every app",
                                 lambda cam, on: anker_xu.set_orientation(
                                     cam, on, self.settings.get("upside_down", False)), False)
                if prof.orientation else None,
                self._vendor_row("upside_down", "Upside Down", "Flip top and bottom, for a camera mounted upside down",
                                 lambda cam, on: anker_xu.set_orientation(
                                     cam, self.settings.get("mirror", False), on), False)
                if prof.orientation else None]),
            ("audio-input-microphone-symbolic", "Audio", [
                self._pickup_row() if prof.pickup_modes else None]),
            ("zoom-in-symbolic", "Zoom", [
                z("zoom_abs", "Zoom", fmt=lambda v: f"{v / 100:.1f}×"),
                self._pan_tilt_row() if self._have("pan_abs", "tilt_abs") else None]),
            ("image-x-generic-symbolic", "Image", [
                z("brightness", "Brightness"), z("contrast", "Contrast"),
                z("saturation", "Saturation"), z("sharpness", "Sharpness")]),
            ("weather-clear-symbolic", "White Balance", [
                sw("wb_auto", "Auto White Balance"),
                z("wb_temp", "Color Temperature", fmt=lambda v: f"{v} K")]),
            ("find-location-symbolic", "Focus", [
                sw("focus_auto", "Autofocus"), z("focus_abs", "Manual Focus")]),
            ("display-brightness-symbolic", "Exposure", [
                sw("exposure_auto", "Auto Exposure", getter=lambda v: v != 1, setter=self._set_auto_exposure,
                   sub=None if self._can_raw_ae() else "Turning it back on needs a camera replug"),
                z("exposure_abs", "Exposure Time")]),
            ("emblem-system-symbolic", "Advanced", [
                self._menu_row("power_line", "Anti-Flicker") if self._have("power_line") else None,
                z("gamma", "Gamma"), z("hue", "Hue"),
                self._service_row() if prof.stream_reset_keys else None]),
        ]
        res_btn = self._category("video-display-symbolic", "Resolution", [self._resolution_row()])
        cats.append(res_btn)
        self.res_popover = res_btn.get_popover()
        for icon, title, rows in groups:
            b = self._category(icon, title, rows)
            if b:
                cats.append(b)
        bar.append(cats)

        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, css_classes=["dock-sep"]))
        actions = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        reset = Gtk.Button(label="Restore Defaults")
        reset.add_css_class("ghost-btn")
        reset.connect("clicked", self._on_reset)
        actions.append(reset)
        apply_ = Gtk.Button(label="Apply", tooltip_text="Send your saved settings to the camera again")
        apply_.add_css_class("accent-btn")
        apply_.connect("clicked", self._on_reapply)
        actions.append(apply_)
        bar.append(actions)

        self.dock.set_child(bar)
        self.sync_from_camera()

    def _vendor_row(self, key, title, sub, setter, default):
        """Switch for a write-only vendor control; state is remembered in settings."""
        r = row_box()
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        txt.append(label(title, "row-title"))
        txt.append(label(sub, "row-sub"))
        r.append(txt)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=self.settings.get(key, default))

        def toggled(s, _p):
            try:
                setter(self.cam, s.get_active())
            except OSError as e:
                self.toast(f"Could not set {title}: {e.strerror}")
                return
            self.settings[key] = s.get_active()
            self._queue_save()
        sw.connect("notify::active", toggled)
        self.vendor_switches[key] = (sw, default)
        r.append(sw)
        return r

    def _disabled_row(self, title, sub):
        r = row_box()
        r.add_css_class("disabled-row")
        r.set_tooltip_text("Uses Anker's proprietary protocol, which has not been decoded yet")
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        head = Gtk.Box(spacing=8)
        head.append(label(title, "row-title"))
        head.append(label("Coming soon", "badge"))
        txt.append(head)
        txt.append(label(sub, "row-sub"))
        r.append(txt)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER, sensitive=False)
        r.append(sw)
        return r

    def _slider_row(self, key, title, fmt=str):
        ctrl = self.ctrls[CID[key]]
        r = row_box(vertical=True)
        head = Gtk.Box()
        head.append(label(title, "row-title", hexpand=True))
        val = label("", "row-value")
        head.append(val)
        r.append(head)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, ctrl.min, ctrl.max, max(ctrl.step, 1))
        scale.set_draw_value(False)
        scale.set_round_digits(0)
        # Never change a value from the scroll wheel — only by dragging/clicking.
        block = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        block.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        block.connect("scroll", lambda *_: True)
        scale.add_controller(block)
        # Double-click the title row to reset to default
        g = Gtk.GestureClick(button=1)
        g.connect("pressed", lambda _g, n, *_: n == 2 and scale.set_value(ctrl.default))
        head.add_controller(g)
        head.set_tooltip_text("Double-click to reset")

        def changed(s):
            v = int(round(s.get_value() / max(ctrl.step, 1)) * max(ctrl.step, 1))
            val.set_label(fmt(v))
            if not self._updating:
                self._set(key, v)
        scale.connect("value-changed", changed)
        r.append(scale)
        self.rows[key] = {"kind": "slider", "row": r, "scale": scale, "label": val, "fmt": fmt}
        return r

    def _switch_row(self, key, title, getter=bool, setter=None, sub=None):
        r = row_box()
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
        txt.append(label(title, "row-title"))
        if sub:
            s_lbl = label(sub, "row-sub")
            s_lbl.set_wrap(True); s_lbl.set_max_width_chars(34)
            txt.append(s_lbl)
        r.append(txt)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER)

        def toggled(s, _p):
            if not self._updating:
                (setter or (lambda on: self._set(key, 1 if on else 0)))(s.get_active())
        sw.connect("notify::active", toggled)
        r.append(sw)
        self.rows[key] = {"kind": "switch", "row": r, "switch": sw, "getter": getter}
        return r

    def _menu_row(self, key, title):
        ctrl = self.ctrls[CID[key]]
        r = row_box()
        r.append(label(title, "row-title", hexpand=True))
        items = sorted(ctrl.menu.items())
        names = {"Disabled": "Off"}
        dd = Gtk.DropDown.new_from_strings([names.get(n, n) for _, n in items])
        dd.set_valign(Gtk.Align.CENTER)
        dd.connect("notify::selected", lambda d, _p: not self._updating and
                   self._set(key, items[d.get_selected()][0]))
        r.append(dd)
        self.rows[key] = {"kind": "menu", "row": r, "dd": dd, "items": [k for k, _ in items]}
        return r

    def _pan_tilt_row(self):
        r = row_box()
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
        txt.append(label("Pan & Tilt", "row-title"))
        txt.append(label("Moves the view while zoomed in", "row-sub"))
        r.append(txt)
        grid = Gtk.Grid(row_spacing=4, column_spacing=4)
        grid.add_css_class("dpad")

        def btn(icon, col, rowi, cb, tip):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.connect("clicked", lambda *_: cb())
            grid.attach(b, col, rowi, 1, 1)
        pan, tilt = self.ctrls[CID["pan_abs"]], self.ctrls[CID["tilt_abs"]]
        btn("go-up-symbolic", 1, 0, lambda: self._nudge("tilt_abs", tilt.step), "Tilt up")
        btn("go-down-symbolic", 1, 2, lambda: self._nudge("tilt_abs", -tilt.step), "Tilt down")
        btn("go-previous-symbolic", 0, 1, lambda: self._nudge("pan_abs", -pan.step), "Pan left")
        btn("go-next-symbolic", 2, 1, lambda: self._nudge("pan_abs", pan.step), "Pan right")
        btn("find-location-symbolic", 1, 1, self._center, "Re-centre")
        r.append(grid)
        return r

    # ---------------- control actions
    def _set(self, key, value, quiet=False):
        if not self.cam:
            return False
        try:
            self.cam.set(CID[key], value)
        except OSError as e:
            if not quiet:
                self.toast(f"Could not set {key.replace('_', ' ')}: {e.strerror}")
            self.sync_from_camera()
            return False
        if key in PERSIST_ORDER:
            self.settings[key] = int(value)
            self._queue_save()
        if key.endswith("_auto") or key == "zoom_abs":
            self.sync_from_camera()
        return True

    def _can_raw_ae(self):
        """Can auto exposure be switched back on without a replug?"""
        return bool(self.profile and self.cam) and (not self.profile.raw_auto_exposure
                                                    or has_usb_access(self.cam.path))

    def _set_auto_exposure(self, on):
        if not self.cam:
            return
        if not on and self._can_raw_ae():
            self._set("exposure_auto", 1)
            return
        if not on:
            body = ("This camera's firmware does not let Linux switch back to auto exposure. "
                    "To restore it you will need to unplug and replug the camera "
                    "(or run install.sh once so the app can switch it back for you).")
            dlg = Adw.AlertDialog(heading="Switch to manual exposure?", body=body)
            dlg.add_response("cancel", "Cancel")
            dlg.add_response("manual", "Use Manual")
            dlg.set_response_appearance("manual", Adw.ResponseAppearance.DESTRUCTIVE)

            def done(d, res):
                if d.choose_finish(res) == "manual":
                    self._set("exposure_auto", 1)
                else:
                    self.sync_from_camera()
            dlg.choose(self, None, done)
            return
        for v in (3, 0, 2):  # aperture-priority / auto / shutter-priority
            if self._set("exposure_auto", v, quiet=True):
                return
        if self.cam and self.profile.raw_auto_exposure and has_usb_access(self.cam.path):
            self._reattach_camera(force_auto_exposure, "Auto exposure on")
        else:
            self.toast("Replug the camera to restore auto exposure (or run install.sh)")
            self.sync_from_camera()

    def _reattach_camera(self, action, done_msg):
        """Run a raw-USB action that briefly detaches the video driver, then reopen the camera."""
        path = self.cam.path
        self.preview.stop()
        self.cam.close()
        self.cam = None
        self.dock.set_sensitive(False)
        try:
            action(path)
        except OSError as e:
            self.toast(f"Could not switch: {e.strerror}")
        state = {"tries": 0}

        def poll():
            state["tries"] += 1
            if find_devices() or state["tries"] > 20:
                self.dock.set_sensitive(True)
                self.refresh_devices()  # reopens the camera, re-applies settings, restarts preview
                self.toast(done_msg if self.cam else "Camera did not come back — try replugging it")
                return False
            return True
        GLib.timeout_add(500, poll)

    def _on_fov(self, btn, fov):
        if btn.get_active() and not self._updating:
            z = self.ctrls[CID["zoom_abs"]]
            self._set("zoom_abs", max(z.min, min(z.max, self.profile.fov_zoom[fov])))
            self._center()

    def _nudge(self, key, delta):
        c = self.ctrls[CID[key]]
        try:
            cur = self.cam.get(CID[key])
        except OSError:
            return
        self._set(key, max(c.min, min(c.max, cur + delta)))

    def _center(self):
        self._set("pan_abs", 0, quiet=True)
        self._set("tilt_abs", 0, quiet=True)

    def _on_reset(self, *_):
        for key in PERSIST_ORDER:
            ctrl = self.ctrls.get(CID[key])
            if ctrl:
                try:
                    if not (self.cam.query(CID[key]).flags & FLAG_INACTIVE):
                        self.cam.set(CID[key], ctrl.default)
                except OSError:
                    pass
            self.settings.pop(key, None)
        if getattr(self, "pickup_btns", None):
            self.pickup_btns[self.profile.pickup_modes[0][0]].set_active(True)
            self.settings.pop("pickup", None)
        for key, (sw, default) in getattr(self, "vendor_switches", {}).items():
            self.settings.pop(key, None)
            sw.set_active(default)  # toggling re-sends the value to the camera
            self.settings.pop(key, None)
        self._queue_save()
        self.sync_from_camera()
        self.toast("Restored camera defaults")

    def _on_reapply(self, *_):
        n = apply_settings(self.cam, self.profile, self.settings)
        self.sync_from_camera()
        self.toast(f"Applied {n} setting{'s' if n != 1 else ''}")

    def sync_from_camera(self):
        """Pull current values/flags from the camera into the widgets."""
        if not self.cam:
            return
        self._updating = True
        try:
            for key, w in self.rows.items():
                try:
                    v = self.cam.get(CID[key])
                    flags = self.cam.query(CID[key]).flags
                except OSError:
                    continue
                w["row"].set_sensitive(not (flags & FLAG_INACTIVE))
                if w["kind"] == "slider":
                    w["scale"].set_value(v)
                    w["label"].set_label(w["fmt"](v))
                elif w["kind"] == "switch":
                    w["switch"].set_active(w["getter"](v))
                elif w["kind"] == "menu" and v in w["items"]:
                    w["dd"].set_selected(w["items"].index(v))
            if self.fov_btns:
                z = self.cam.get(CID["zoom_abs"])
                match = next((f for f, fz in self.profile.fov_zoom.items() if abs(fz - z) <= 1), None)
                for f, b in self.fov_btns.items():
                    b.set_active(f == match)
        finally:
            self._updating = False

    # ---------------- misc
    def toast(self, msg):
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=3))

    def _queue_save(self):
        if self._save_src:
            GLib.source_remove(self._save_src)
        self._save_src = GLib.timeout_add(400, self._do_save)

    def _do_save(self):
        self._save_src = 0
        try:
            if self.profile:
                save_settings(self.profile, self.settings)
        except OSError as e:
            self.toast(f"Could not save settings: {e.strerror}")
        return False

    def _on_close(self, *_):
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._do_save()
        if self._retry_src:
            GLib.source_remove(self._retry_src)
        self.preview.stop()
        if self.cam:
            self.cam.close()
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = self.get_active_window() or MainWindow(self)
        win.present()


def cli_apply():
    """`app.py --apply`: push saved settings to every supported camera and exit."""
    devices = find_devices()
    for dev in devices:
        cam = Camera(dev.node)
        n = apply_settings(cam, dev.profile, load_settings(dev.profile))
        cam.close()
        print(f"Applied {n} settings to {dev.profile.name} ({dev.node})")
    if not devices:
        print(f"No supported camera found (supported: {supported_names()})", file=sys.stderr)
    return 0 if devices else 1


if __name__ == "__main__":
    if "--apply" in sys.argv:
        sys.exit(cli_apply())
    Gst.init(None)
    sys.exit(App().run([a for a in sys.argv if a != "--apply"]))
