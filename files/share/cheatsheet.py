#!/usr/bin/env python3
# Super+/ : glass sheet with every shortcut and gesture; any key or click closes it.
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk

SECTIONS = [
  ("Windows", [
    ("Super+Tab", "all windows at once"),
    ("Alt+Tab", "switch windows, minimized ones too"),
    ("Super+← / →", "window to half of the screen"),
    ("Super+U  I  J  K", "window to a corner"),
    ("Super+G", "arrange all windows in a grid"),
    ("Super+↑ / ↓", "maximize / minimize"),
    ("Super+D", "show desktop"),
  ]),
  ("Workspaces", [
    ("Super+1  2  3", "Work / Study / Personal"),
    ("Super+Shift+1  2  3", "move the window to a workspace"),
  ]),
  ("Search and tools", [
    ("Super+Space", "launcher, Tab switches tabs"),
    ("Super+V", "clipboard history"),
    ("Super+;", "emoji"),
    ("Super+C", "calculator, Enter copies the result"),
    ("Super+`", "drop-down terminal"),
    ("Super+T  /  Super+E", "terminal / files"),
    ("Super", "app menu"),
  ]),
  ("System", [
    ("Super+L", "lock the screen"),
    ("Super+Esc", "lock, suspend, restart"),
    ("Ctrl+Shift+S", "screenshot of an area to a file"),
    ("Super+Shift+S", "screenshot of an area to the clipboard"),
    ("Super+A", "AirPods: connect / disconnect"),
    ("Super+/", "this cheat sheet"),
  ]),
  ("Touchpad gestures", [
    ("3 fingers ↑", "all windows at once"),
    ("3 fingers ↓", "show desktop"),
    ("4 fingers ← →", "next / previous workspace"),
    ("4 fingers ↑", "windows from all workspaces"),
  ]),
]

css = b"""
#sheet { background-color: rgba(22, 22, 30, 0.92); border-radius: 20px; border: 1px solid rgba(255,255,255,0.10); padding: 30px 36px; }
#title { color: #c0caf5; font-family: Inter; font-size: 22pt; font-weight: 700; }
#hint { color: #565f89; font-family: Inter; font-size: 10.5pt; }
.section { color: #7aa2f7; font-family: Inter; font-size: 11.5pt; font-weight: 700; margin-top: 6px; }
.key { color: #c0caf5; background-color: rgba(255,255,255,0.07); border-radius: 7px; padding: 3px 9px;
       font-family: "JetBrainsMono Nerd Font"; font-size: 10.5pt; font-weight: 600; }
.desc { color: #a9b1d6; font-family: Inter; font-size: 11pt; }
"""
p = Gtk.CssProvider(); p.load_from_data(css)
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10)

w = Gtk.Window(title="Shortcuts")
w.set_decorated(False); w.set_keep_above(True); w.set_skip_taskbar_hint(True); w.set_skip_pager_hint(True)
w.set_type_hint(Gdk.WindowTypeHint.DIALOG); w.set_position(Gtk.WindowPosition.CENTER)
vis = w.get_screen().get_rgba_visual()
if vis: w.set_visual(vis)
w.set_app_paintable(True)
w.connect('draw', lambda wid, cr: (cr.set_source_rgba(0, 0, 0, 0), cr.set_operator(1), cr.paint(), cr.set_operator(2)) and False)

outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18); outer.set_name('sheet')
head = Gtk.Box(spacing=12)
t = Gtk.Label(label="Shortcuts and gestures"); t.set_name('title'); t.set_xalign(0)
h = Gtk.Label(label="any key or click closes it"); h.set_name('hint'); h.set_valign(Gtk.Align.END)
head.pack_start(t, False, False, 0); head.pack_end(h, False, False, 0); outer.add(head)

cols = Gtk.Box(spacing=48)
def column(sections):
    g = Gtk.Grid(row_spacing=9, column_spacing=14); r = 0
    for name, rows in sections:
        s = Gtk.Label(label=name); s.get_style_context().add_class('section'); s.set_xalign(0)
        g.attach(s, 0, r, 2, 1); r += 1
        for k, d in rows:
            kl = Gtk.Label(label=k); kl.get_style_context().add_class('key'); kl.set_halign(Gtk.Align.START)
            dl = Gtk.Label(label=d); dl.get_style_context().add_class('desc'); dl.set_xalign(0)
            g.attach(kl, 0, r, 1, 1); g.attach(dl, 1, r, 1, 1); r += 1
        r += 1
    return g
cols.add(column(SECTIONS[:2] + SECTIONS[4:]))
cols.add(column(SECTIONS[2:4]))
outer.add(cols); w.add(outer)

for sig in ('key-press-event', 'button-press-event', 'focus-out-event'):
    w.connect(sig, lambda *a: Gtk.main_quit())
w.show_all(); w.present()
Gtk.main()
