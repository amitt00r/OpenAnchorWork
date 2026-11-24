#!/usr/bin/env python3
"""Regenerate the README screenshots in docs/screenshots/.

Needs a supported camera connected (the controls are read from it), but never
streams from it: the preview shows an illustration drawn by tools/scene.py, so
no real camera image ends up in the docs. Close OpenAnchorWork first.

    python3 tools/make_screenshots.py
"""
import os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app, cairo  # noqa: E402
from gi.repository import GLib, Gst, Gtk, Gdk  # noqa: E402
Gst.init(None)
TMP = tempfile.mkdtemp(prefix="oaw-shots-")
OUT = os.path.join(ROOT, "docs", "screenshots")
SCENE = os.path.join(TMP, "scene.png")
subprocess.run([sys.executable, os.path.join(ROOT, "tools", "scene.py"), SCENE], check=True)
scene = Gdk.Texture.new_from_filename(SCENE)
mirrored = None


def fake_start(self, device, w, h, mirror):        # never stream from the real camera
    self.stop(); self.picture.set_paintable(scene_m() if mirror else scene); self.pipeline = object(); self.on_state(True, None)
def fake_mirror(self, mirror): self.picture.set_paintable(scene_m() if mirror else scene)
def fake_stop(self): self.pipeline = None
def scene_m():
    global mirrored
    if mirrored is None:
        src = cairo.ImageSurface.create_from_png(SCENE); W, H = src.get_width(), src.get_height()
        dst = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H); c = cairo.Context(dst)
        c.translate(W, 0); c.scale(-1, 1); c.set_source_surface(src); c.paint()
        dst.write_to_png(TMP + "/mirror.png"); mirrored = Gdk.Texture.new_from_filename(TMP + "/mirror.png")
    return mirrored
app.Preview.start, app.Preview.set_mirror, app.Preview.stop = fake_start, fake_mirror, fake_stop

a = app.App()
def snap(widget):
    p = Gtk.WidgetPaintable.new(widget); s = Gtk.Snapshot(); p.snapshot(s, widget.get_width(), widget.get_height())
    return widget.get_native().get_renderer().render_texture(s.to_node(), None)
def to_surface(tex, name):
    path = f"{TMP}/{name}.png"; tex.save_to_png(path); return cairo.ImageSurface.create_from_png(path)
def save_window(w, name, popbtn=None):
    win = to_surface(snap(w), name + "_w")
    if popbtn:
        pop = popbtn.get_popover(); ps = to_surface(snap(pop), name + "_p")
        ok, b = popbtn.compute_bounds(w)
        x = b.get_x() + b.get_width() / 2 - ps.get_width() / 2
        y = b.get_y() - ps.get_height() + 6
        c = cairo.Context(win); c.set_source_surface(ps, x, y); c.paint()
    win.write_to_png(f"{OUT}/{name}.png")
def mbs(w):
    out = []
    def walk(x):
        if isinstance(x, Gtk.MenuButton): out.append(x)
        c = x.get_first_child()
        while c: walk(c); c = c.get_next_sibling()
    walk(w); return out
def btn_named(w, name):
    for b in mbs(w):
        texts = []
        def walk(x):
            if isinstance(x, Gtk.Label): texts.append(x.get_label())
            c = x.get_first_child()
            while c: walk(c); c = c.get_next_sibling()
        walk(b)
        if name in texts: return b

def go():
    w = a.get_active_window()
    steps = [("main", None), ("video", "Video"), ("audio", "Audio"), ("image", "Image"), ("resolution", "Resolution")]
    def step(i=0):
        if i == len(steps):
            w.view_btns[1].set_active(True)
            GLib.timeout_add(500, lambda: (save_window(w, "self-view"), w.view_btns[0].set_active(True), w.close(), a.quit(), False)[4])
            return False
        name, cat = steps[i]
        b = btn_named(w, cat) if cat else None
        if b: b.popup()
        def take():
            save_window(w, name, b)
            if b: b.popdown()
            GLib.timeout_add(400, step, i + 1); return False
        GLib.timeout_add(700, take); return False
    GLib.timeout_add(800, step); return False
a.connect("activate", lambda *_: GLib.timeout_add(1500, go))
a.run([])
print("Screenshots written to", OUT)
