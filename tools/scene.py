"""Draw the flat illustrated 'video call' scene used as the preview in screenshots.

    python3 tools/scene.py out.png
"""
import cairo, math, sys
W, H = 1920, 1080
s = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H); c = cairo.Context(s)
def rr(x, y, w, h, r):
    c.new_sub_path(); c.arc(x+w-r, y+r, r, -math.pi/2, 0); c.arc(x+w-r, y+h-r, r, 0, math.pi/2)
    c.arc(x+r, y+h-r, r, math.pi/2, math.pi); c.arc(x+r, y+r, r, math.pi, 1.5*math.pi); c.close_path()
def fill(rgb): c.set_source_rgb(*[v/255 for v in rgb]); c.fill()
# wall gradient
g = cairo.LinearGradient(0, 0, 0, H); g.add_color_stop_rgb(0, .86, .84, .80); g.add_color_stop_rgb(1, .74, .71, .66)
c.set_source(g); c.paint()
# floor
c.rectangle(0, H*0.78, W, H*0.22); fill((150, 120, 92))
# window with sky
rr(1180, 140, 560, 420, 18); fill((245, 242, 236))
g = cairo.LinearGradient(0, 165, 0, 535); g.add_color_stop_rgb(0, .55, .75, .93); g.add_color_stop_rgb(1, .80, .90, .97)
rr(1205, 165, 510, 370, 10); c.set_source(g); c.fill()
c.rectangle(1455, 165, 10, 370); fill((245, 242, 236)); c.rectangle(1205, 345, 510, 10); fill((245, 242, 236))
# sun + hills in window
c.arc(1620, 240, 38, 0, 2*math.pi); fill((255, 214, 120))
# shelf with books
c.rectangle(170, 300, 520, 18); fill((120, 86, 60))
x = 200
for w_, h_, col in [(40,120,(70,110,160)),(32,100,(200,90,70)),(48,130,(90,150,110)),(36,110,(230,180,80)),(44,95,(120,100,170))]:
    c.rectangle(x, 300-h_, w_, h_); fill(col); x += w_ + 6
c.arc(560, 255, 42, 0, 2*math.pi); fill((90, 150, 110)); c.rectangle(535, 255, 50, 45); fill((200, 120, 80))
# plant on floor
c.rectangle(1620, 700, 120, 150); fill((190, 110, 75))
for ang in range(-60, 61, 30):
    c.save(); c.translate(1680, 700); c.rotate(math.radians(ang))
    c.scale(1, 3.2); c.arc(0, -40, 34, 0, 2*math.pi); c.restore(); fill((70, 135, 95))
# chair back
rr(660, 560, 600, 560, 80); fill((60, 64, 74))
# person (flat silhouette)
c.save(); c.translate(960, 0)
rr(-300, 700, 600, 520, 160); fill((64, 120, 190))      # shirt
c.rectangle(-55, 560, 110, 160); fill((222, 172, 135))  # neck
c.save(); c.scale(1, 1.18); c.arc(0, 470/1.18, 150, 0, 2*math.pi); c.restore(); fill((232, 184, 146))  # face
c.save(); c.scale(1, 0.75); c.arc(0, 380/0.75, 165, math.pi, 2*math.pi); c.restore(); fill((52, 40, 34))  # hair
for ex in (-55, 55):
    c.arc(ex, 470, 13, 0, 2*math.pi); fill((52, 40, 34))
c.set_line_width(9); c.set_line_cap(cairo.LINE_CAP_ROUND)
c.arc(0, 520, 50, 0.2*math.pi, 0.8*math.pi); c.set_source_rgb(.62, .35, .30); c.stroke()
c.restore()
s.write_to_png(sys.argv[1])
