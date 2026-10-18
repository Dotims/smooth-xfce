#!/usr/bin/env python3
# Short glass label in the lower middle of the screen: osd.py "Text" [seconds]
import sys, gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
css = b"""
#osd { background-color: rgba(22, 22, 30, 0.88); border-radius: 16px; border: 1px solid rgba(255,255,255,0.10); padding: 14px 30px; }
#osd label { color: #c0caf5; font-family: Inter; font-size: 17pt; font-weight: 600; }
"""
p = Gtk.CssProvider(); p.load_from_data(css)
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10)
w = Gtk.Window(type=Gtk.WindowType.POPUP); w.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
vis = w.get_screen().get_rgba_visual()
if vis: w.set_visual(vis)
w.set_app_paintable(True)
w.connect('draw', lambda wid, cr: (cr.set_source_rgba(0, 0, 0, 0), cr.set_operator(1), cr.paint(), cr.set_operator(2)) and False)
box = Gtk.Box(); box.set_name('osd'); box.add(Gtk.Label(label=sys.argv[1])); w.add(box)
w.resize(1, 1); w.show_all()
mon = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
g = mon.get_geometry(); ww, wh = w.get_size()
w.move(g.x + (g.width - ww) // 2, g.y + int(g.height * 0.78))
GLib.timeout_add(int(float(sys.argv[2] if len(sys.argv) > 2 else 0.9) * 1000), Gtk.main_quit)
Gtk.main()
