#!/usr/bin/env python3
# Lock screen look for xsecurelock: live clock, avatar, password pill with dots.
#   lockscreen.py saver   idle screen (xsecurelock saver module)
#   lockscreen.py auth    same screen, reads keys from stdin and checks them with
#                         xsecurelock's PAM helper (xsecurelock auth module)
# Any error in auth mode replaces this process with the stock auth_x11 prompt, so a bug here
# never leaves the screen locked without a way in.
import codecs
import datetime as dt
import getpass
import math
import os
import signal
import subprocess
import sys
import time
import traceback

AUTH_X11 = '/usr/lib/xsecurelock/auth_x11'


def fallback():
    if sys.argv[1:2] == ['auth']:
        os.execv(AUTH_X11, [AUTH_X11])
    os._exit(1)


try:
    import cairo
    import gi
    gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
    gi.require_version('GdkX11', '3.0'); gi.require_version('PangoCairo', '1.0')
    from gi.repository import Gdk, GdkX11, GLib, Gtk, Pango, PangoCairo
except Exception:
    traceback.print_exc()
    fallback()

EXIT_OK, EXIT_FAIL = 0, 1
BG = os.path.expanduser('~/.cache/lock-bg.png')
AUTHPROTO = os.environ.get('XSECURELOCK_AUTHPROTO') or '/usr/lib/xsecurelock/authproto_pam'
IDLE_EXIT = 60  # seconds without a key before the prompt gives up

MONTHS_OF = ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia',
             'września', 'października', 'listopada', 'grudnia']
WEEKDAYS = ['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela']

FG = (0xc0 / 255, 0xca / 255, 0xf5 / 255)
FG_DIM = (0xa9 / 255, 0xb1 / 255, 0xd6 / 255)
BLUE = (0x7a / 255, 0xa2 / 255, 0xf7 / 255)
PURPLE = (0xbb / 255, 0x9a / 255, 0xf7 / 255)
RED = (0xf7 / 255, 0x76 / 255, 0x8e / 255)
AMBER = (0xe0 / 255, 0xaf / 255, 0x68 / 255)
NAVY = (0x1a / 255, 0x1b / 255, 0x26 / 255)


def text(cr, s, font, px, rgba, cx, top):
    """Draws s centred on cx with its top at top; returns the text height."""
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription(font)
    desc.set_absolute_size(px * Pango.SCALE)
    layout.set_font_description(desc)
    layout.set_text(s, -1)
    w, h = layout.get_pixel_size()
    cr.set_source_rgba(*rgba)
    cr.move_to(cx - w / 2, top)
    PangoCairo.show_layout(cr, layout)
    return h


def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class LockScreen:
    def __init__(self, auth):
        self.auth = auth
        self.user = getpass.getuser()
        self.chars = []
        self.state = 'idle'        # idle, typing, checking, wrong
        self.message = None        # (text, rgb) under the pill
        self.shake_start = 0.0
        self.last_key = time.monotonic()
        self.bg = cairo.ImageSurface.create_from_png(BG) if os.path.exists(BG) else None
        self.bg_cache = {}

        xid = int(os.environ['XSCREENSAVER_WINDOW'], 0)
        display = Gdk.Display.get_default()
        parent = GdkX11.X11Window.foreign_new_for_display(display, xid)
        _, _, w, h = parent.get_geometry()
        self.parent = parent
        if auth:
            _, _, w, h = Gdk.get_default_root_window().get_geometry()
            rects = [display.get_monitor(i).get_geometry() for i in range(display.get_n_monitors())]
            self.monitors = [(r.x, r.y, r.width, r.height) for r in rects] or [(0, 0, w, h)]
        else:
            self.monitors = [(0, 0, w, h)]  # saver_multiplex gives each monitor its own window

        self.win = self.area = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_app_paintable(True)
        self.win.set_size_request(w, h)
        self.win.connect('draw', self.draw)
        self.win.realize()
        # the first frame as the X background, so mapping never shows black before GTK draws
        self.first = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        self.draw(None, cairo.Context(self.first))
        self.first_pattern = cairo.SurfacePattern(self.first)
        self.win.get_window().set_background_pattern(self.first_pattern)
        self.win.get_window().reparent(parent, 0, 0)
        self.win.show_all()
        if auth:
            # like auth_x11: the auth window is ours to size and map (main keeps it on top)
            parent.set_background_pattern(self.first_pattern)
            parent.move_resize(0, 0, w, h)
            parent.show()

        GLib.timeout_add(1000 - int(time.time() * 1000) % 1000 + 5, self.tick)
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self.quit, EXIT_FAIL if auth else EXIT_OK)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGUSR1, lambda: True)

    # --- drawing -------------------------------------------------------------------------------

    def background(self, w, h):
        if (w, h) not in self.bg_cache:
            surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
            cr = cairo.Context(surf)
            cr.set_source_rgb(*NAVY)
            cr.paint()
            if self.bg:
                s = max(w / self.bg.get_width(), h / self.bg.get_height())
                cr.translate((w - self.bg.get_width() * s) / 2, (h - self.bg.get_height() * s) / 2)
                cr.scale(s, s)
                cr.set_source_surface(self.bg, 0, 0)
                cr.get_source().set_filter(cairo.FILTER_GOOD)
                cr.paint()
            self.bg_cache[(w, h)] = surf
        return self.bg_cache[(w, h)]

    def draw(self, widget, cr):
        for mx, my, mw, mh in self.monitors:
            cr.save()
            cr.translate(mx, my)
            cr.rectangle(0, 0, mw, mh)
            cr.clip()
            cr.set_source_surface(self.background(mw, mh), 0, 0)
            cr.paint()
            self.draw_monitor(cr, mw, mh)
            cr.restore()
        return True

    def draw_monitor(self, cr, w, h):
        s = h / 1080
        cx = w / 2
        now = dt.datetime.now()

        top = h * 0.17
        top += text(cr, now.strftime('%H:%M'), 'Inter Display SemiBold', 128 * s, (*FG, 0.96), cx, top)
        date = f'{WEEKDAYS[now.weekday()]}, {now.day} {MONTHS_OF[now.month - 1]}'
        text(cr, date, 'Inter Medium', 22 * s, (*FG_DIM, 0.9), cx, top - 6 * s)

        # avatar: initial on the accent gradient
        r = 44 * s
        ay = h * 0.60
        grad = cairo.LinearGradient(cx - r, ay - r, cx + r, ay + r)
        grad.add_color_stop_rgb(0, *BLUE)
        grad.add_color_stop_rgb(1, *PURPLE)
        cr.arc(cx, ay, r, 0, 2 * math.pi)
        cr.set_source(grad)
        cr.fill()
        initial = self.user[:1].upper()
        text(cr, initial, 'Inter SemiBold', 40 * s, (*NAVY, 1), cx, ay - 25 * s)
        ny = ay + r + 14 * s
        ny += text(cr, self.user, 'Inter SemiBold', 20 * s, (*FG, 1), cx, ny)

        # password pill
        pw, ph = 264 * s, 40 * s
        py = ny + 18 * s
        shake = 0.0
        if self.state == 'wrong':
            t = time.monotonic() - self.shake_start
            if t < 0.45:
                shake = math.sin(t * 42) * 11 * s * (1 - t / 0.45)
        px = cx - pw / 2 + shake
        rounded(cr, px, py, pw, ph, ph / 2)
        cr.set_source_rgba(1, 1, 1, 0.10)
        cr.fill_preserve()
        cr.set_line_width(max(1, s))
        cr.set_source_rgba(*(RED if self.state == 'wrong' else (1, 1, 1)),
                           0.85 if self.state == 'wrong' else 0.16)
        cr.stroke()

        n = len(self.chars)
        if n == 0:
            hint = 'Sprawdzanie…' if self.state == 'checking' else 'Wpisz hasło'
            text(cr, hint, 'Inter', 15 * s, (*FG, 0.45), px + pw / 2, py + 10 * s)
        else:
            gap, dr = 14 * s, 4 * s
            room = int((pw - 64 * s) // gap)
            shown = min(n, room)
            x0 = px + pw / 2 - (shown - 1) * gap / 2 - 12 * s
            alpha = 1.0
            if self.state == 'checking':
                alpha = 0.45 + 0.4 * (0.5 + 0.5 * math.sin(time.monotonic() * 8))
            cr.set_source_rgba(*FG, alpha)
            for i in range(shown):
                cr.arc(x0 + i * gap, py + ph / 2, dr, 0, 2 * math.pi)
                cr.fill()
            # Enter button
            br = 13 * s
            bx, by = px + pw - br - 7 * s, py + ph / 2
            cr.arc(bx, by, br, 0, 2 * math.pi)
            cr.set_source_rgba(*BLUE, 0.95)
            cr.fill()
            cr.set_source_rgba(*NAVY, 1)
            cr.set_line_width(2 * s)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.move_to(bx - 5 * s, by)
            cr.line_to(bx + 5 * s, by)
            cr.move_to(bx + 1 * s, by - 4 * s)
            cr.line_to(bx + 5 * s, by)
            cr.line_to(bx + 1 * s, by + 4 * s)
            cr.stroke()

        my = py + ph + 14 * s
        if self.message:
            msg, rgb = self.message
            text(cr, msg, 'Inter Medium', 14 * s, (*rgb, 1), cx, my)
        elif self.caps_lock():
            text(cr, 'Caps Lock jest włączony', 'Inter Medium', 14 * s, (*AMBER, 1), cx, my)

        hint = 'Enter odblokowuje · Esc anuluje' if self.auth else 'Zacznij pisać, aby odblokować'
        text(cr, hint, 'Inter', 13 * s, (*FG_DIM, 0.55), cx, h - 64 * s)

    def caps_lock(self):
        keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        return keymap.get_caps_lock_state()

    def tick(self):
        self.area.queue_draw()
        if self.auth and time.monotonic() - self.last_key > IDLE_EXIT and self.state != 'checking':
            self.quit(EXIT_FAIL)
        GLib.timeout_add(1000 - int(time.time() * 1000) % 1000 + 5, self.tick)
        return False

    def animate(self, seconds):
        end = time.monotonic() + seconds

        def frame():
            self.area.queue_draw()
            return time.monotonic() < end or self.state == 'checking'
        GLib.timeout_add(16, frame)

    def quit(self, code):
        self.code = code
        if self.auth:
            self.parent.hide()
            Gdk.Display.get_default().flush()
        Gtk.main_quit()
        return False


class Auth(LockScreen):
    def __init__(self):
        super().__init__(auth=True)
        self.code = EXIT_FAIL
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='ignore')
        self.proto = None
        self.inbuf = b''
        self.prompted = False
        self.submitted = False
        os.set_blocking(0, False)
        GLib.io_add_watch(0, GLib.PRIORITY_DEFAULT, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.on_stdin)
        self.start_proto()

    def start_proto(self):
        self.proto = subprocess.Popen([AUTHPROTO], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.inbuf = b''
        self.prompted = False
        os.set_blocking(self.proto.stdout.fileno(), False)
        GLib.io_add_watch(self.proto.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                          GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.on_proto, self.proto)

    # keys arrive on stdin from xsecurelock as UTF-8 text plus control characters
    def on_stdin(self, fd, cond):
        try:
            data = os.read(0, 256)
        except BlockingIOError:
            return True
        if not data:
            self.cancel()
            return False
        self.last_key = time.monotonic()
        for ch in self.decoder.decode(data):
            self.key(ch)
        self.area.queue_draw()
        return True

    def key(self, ch):
        if self.state == 'checking':
            return
        if self.state == 'wrong':
            self.state, self.message = 'idle', None
        if ch in ('\b', '\x7f'):
            if self.chars:
                self.chars.pop()
        elif ch == '\x15':  # Ctrl-U
            self.chars.clear()
        elif ch == '\x1b':
            self.cancel()
        elif ch in ('\r', '\n'):
            if self.chars:
                self.submitted = True
                self.state = 'checking'
                self.animate(0)
                self.send_password()
        elif ch >= ' ':
            self.chars.append(ch)
        if self.state != 'checking':
            self.state = 'typing' if self.chars else 'idle'

    def send_password(self):
        if not (self.prompted and self.submitted):
            return
        pw = bytearray(''.join(self.chars).encode())
        self.chars.clear()
        packet = bytearray(b'p %d\n' % len(pw)) + pw + b'\n'
        try:
            self.proto.stdin.write(packet)
            self.proto.stdin.flush()
        except BrokenPipeError:
            pass
        for buf in (pw, packet):
            buf[:] = bytes(len(buf))
        self.prompted = self.submitted = False

    # authproto packets: "<type> <len>\n<message>\n"
    def on_proto(self, fd, cond, proto):
        if proto is not self.proto:
            return False
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            return True
        self.inbuf += chunk
        while True:
            head, sep, rest = self.inbuf.partition(b'\n')
            if not sep:
                break
            kind, _, length = head.decode(errors='replace').partition(' ')
            length = int(length or 0)
            if len(rest) < length + 1:
                break
            msg = rest[:length].decode(errors='replace')
            self.inbuf = rest[length + 1:]
            self.packet(kind, msg)
        if not chunk:
            self.finished(proto)
            return False
        return True

    def packet(self, kind, msg):
        if kind in ('P', 'U'):
            # authproto_pam retries a wrong password itself: a new prompt after ours means "wrong"
            if self.state == 'checking':
                self.wrong()
            self.prompted = True
            self.send_password()
        elif kind == 'e':
            text_ = 'Złe hasło' if 'failure' in msg.lower() else msg
            self.message = (text_, RED)
        elif kind == 'i':
            self.message = (msg, FG_DIM)
        self.area.queue_draw()

    def finished(self, proto):
        rc = proto.wait()
        if rc == 0:
            self.quit(EXIT_OK)
            return
        if self.state == 'checking':
            self.wrong()
        GLib.timeout_add(400, lambda: (self.start_proto(), False)[1])

    def wrong(self):
        self.state = 'wrong'
        self.chars.clear()
        self.submitted = False
        if not self.message or self.message[1] != RED:
            self.message = ('Złe hasło, spróbuj jeszcze raz', RED)
        self.shake_start = time.monotonic()
        self.animate(0.5)

    def cancel(self):
        if self.proto and self.proto.poll() is None:
            try:
                self.proto.stdin.write(b'x 0\n\n')
                self.proto.stdin.flush()
            except BrokenPipeError:
                pass
        self.quit(EXIT_FAIL)


def crashed(*exc):
    # any error, also inside a GTK callback
    traceback.print_exception(*exc)
    proto = getattr(SCREEN, 'proto', None)
    if proto and proto.poll() is None:
        proto.kill()
    fallback()


SCREEN = None


def main():
    global SCREEN
    sys.excepthook = crashed
    mode = sys.argv[1] if len(sys.argv) > 1 else 'saver'
    try:
        screen = SCREEN = Auth() if mode == 'auth' else LockScreen(auth=False)
    except Exception:
        crashed(*sys.exc_info())
    screen.code = getattr(screen, 'code', EXIT_OK if mode == 'saver' else EXIT_FAIL)
    Gtk.main()
    if mode == 'auth' and screen.proto and screen.proto.poll() is None:
        screen.proto.terminate()
    return screen.code


if __name__ == '__main__':
    sys.exit(main())
