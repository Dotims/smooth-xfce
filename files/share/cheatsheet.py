#!/usr/bin/env python3
# Super+/ : glass sheet with every shortcut and gesture; any key or click closes it.
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk

SECTIONS = [
  ("Okna", [
    ("Super+Tab", "wszystkie okna naraz"),
    ("Alt+Tab", "przełączanie, też zminimalizowanych"),
    ("Super+← / →", "okno na pół ekranu"),
    ("Super+U  I  J  K", "okno w róg ekranu"),
    ("Super+G", "ułóż wszystkie okna w siatkę"),
    ("Super+↑ / ↓", "maksymalizuj / zminimalizuj"),
    ("Super+D", "pokaż pulpit"),
  ]),
  ("Pulpity", [
    ("Super+1  2  3", "Praca / Nauka / Prywatne"),
    ("Super+Shift+1  2  3", "przenieś okno na pulpit"),
  ]),
  ("Szukanie i narzędzia", [
    ("Super+Spacja", "wyszukiwarka, Tab zmienia zakładkę"),
    ("Super+V", "historia schowka"),
    ("Super+;", "emoji"),
    ("Super+C", "kalkulator, Enter kopiuje wynik"),
    ("Super+`", "terminal z góry ekranu"),
    ("Super+T  /  Super+E", "terminal / pliki"),
    ("Super", "menu aplikacji"),
  ]),
  ("System", [
    ("Super+L", "zablokuj ekran"),
    ("Super+Esc", "zablokuj, uśpij, uruchom ponownie"),
    ("Ctrl+Shift+S", "zrzut obszaru do pliku"),
    ("Super+Shift+S", "zrzut obszaru do schowka"),
    ("Super+A", "AirPods: połącz / rozłącz"),
    ("Super+/", "ta ściąga"),
  ]),
  ("Gesty touchpada", [
    ("3 palce ↑", "wszystkie okna naraz"),
    ("3 palce ↓", "pokaż pulpit"),
    ("4 palce ← →", "następny / poprzedni pulpit"),
    ("4 palce ↑", "okna ze wszystkich pulpitów"),
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

w = Gtk.Window(title="Skróty")
w.set_decorated(False); w.set_keep_above(True); w.set_skip_taskbar_hint(True); w.set_skip_pager_hint(True)
w.set_type_hint(Gdk.WindowTypeHint.DIALOG); w.set_position(Gtk.WindowPosition.CENTER)
vis = w.get_screen().get_rgba_visual()
if vis: w.set_visual(vis)
w.set_app_paintable(True)
w.connect('draw', lambda wid, cr: (cr.set_source_rgba(0, 0, 0, 0), cr.set_operator(1), cr.paint(), cr.set_operator(2)) and False)

outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18); outer.set_name('sheet')
head = Gtk.Box(spacing=12)
t = Gtk.Label(label="Skróty i gesty"); t.set_name('title'); t.set_xalign(0)
h = Gtk.Label(label="dowolny klawisz albo klik zamyka"); h.set_name('hint'); h.set_valign(Gtk.Align.END)
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
