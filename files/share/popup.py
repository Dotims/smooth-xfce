# Shared base of the panel popups (calendar, quick settings): a glass card above the panel that
# stays running hidden, toggles over D-Bus and closes on Esc or a click outside.
import sys

import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk

BASE_CSS = b"""
window { background-color: transparent; }
.card {
  background-color: rgba(26, 27, 38, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 12px;
  padding: 16px 18px 14px;
}
label { font-family: Inter; color: #c0caf5; }
"""


class Popup(Gtk.Application):
    APP_ID = ''
    CSS = b''

    def __init__(self, hidden):
        super().__init__(application_id=self.APP_ID)
        self.hidden = hidden
        self.win = None

    # subclasses fill the card and refresh it before every open
    def build(self, card):
        raise NotImplementedError

    def refresh(self):
        pass

    def on_key(self, key):
        return False

    def on_scroll(self, ev):
        return False

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        css = Gtk.CssProvider()
        css.load_from_data(BASE_CSS + self.CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        w = self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        w.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        w.set_visual(w.get_screen().get_rgba_visual())
        w.set_app_paintable(True)
        w.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK
                     | Gdk.EventMask.SMOOTH_SCROLL_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        w.connect('button-press-event', self._press)
        w.connect('key-press-event', self._key)
        w.connect('scroll-event', lambda _w, ev: self.on_scroll(ev))
        w.connect('grab-broken-event', lambda *_: self.close())
        self.add_window(w)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.get_style_context().add_class('card')
        w.add(card)
        self.build(card)
        card.show_all()

    def do_activate(self):
        if self.hidden:
            self.hidden = False
        elif self.win.get_visible():
            self.close()
        else:
            self.open()

    def open(self):
        self.refresh()
        self.place()
        self.win.show()
        GLib.timeout_add(30, self._grab, 10)

    def place(self):
        # above the clicked panel item, kept inside the screen
        w = self.win
        w.resize(1, 1)
        _, size = w.get_preferred_size()
        display = Gdk.Display.get_default()
        if w.get_visible():
            # content changed while open: keep the column, grow upwards
            px, py = self.anchor
        else:
            _, px, py = display.get_default_seat().get_pointer().get_position()
            self.anchor = (px, py)
        area = display.get_monitor_at_point(px, py).get_workarea()
        x = min(max(px - size.width // 2, area.x + 10), area.x + area.width - size.width - 10)
        w.move(x, area.y + area.height - size.height - 10)

    def _grab(self, tries):
        gw = self.win.get_window()
        if not self.win.get_visible() or gw is None:
            return False
        seat = Gdk.Display.get_default().get_default_seat()
        status = seat.grab(gw, Gdk.SeatCapabilities.ALL, True, None, None, None, None)
        if status != Gdk.GrabStatus.SUCCESS and tries > 0:
            GLib.timeout_add(30, self._grab, tries - 1)
        return False

    def close(self):
        Gdk.Display.get_default().get_default_seat().ungrab()
        self.win.hide()

    def _press(self, w, ev):
        alloc = w.get_allocation()
        if not (0 <= ev.x < alloc.width and 0 <= ev.y < alloc.height):
            self.close()
        return False

    def _key(self, w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return self.on_key(ev.keyval)


def label(cls, text='', **props):
    lab = Gtk.Label(label=text, **props)
    for c in cls.split():
        lab.get_style_context().add_class(c)
    return lab


def run(cls, prgname):
    GLib.set_prgname(prgname)
    Gdk.set_program_class('Panel-popup')
    hidden = '--daemon' in sys.argv
    app = cls(hidden)
    app.register(None)
    if hidden and app.get_is_remote():
        sys.exit(0)
    sys.exit(app.run([sys.argv[0]]))
