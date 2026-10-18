# Draws the panel status button (Wi-Fi, Bluetooth, volume, battery) as one image for genmon.
# Runs inside the quick settings daemon; `status-icons` only prints the latest file.
import math
import os

import cairo
import gi
gi.require_version('Rsvg', '2.0'); gi.require_version('PangoCairo', '1.0')
from gi.repository import Gio, GLib, Pango, PangoCairo, Rsvg

OUT = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'status-icons')
# Adwaita's filled, rounded symbolic icons stay soft at 16 px; Qogir's thin outlines look jagged
ICONS = ['/usr/share/icons/Adwaita/symbolic/status',
         os.path.expanduser('~/.icons/Qogir-Dark/symbolic/status')]
HEIGHT, ICON, GAP = 24, 16, 13
WHITE = (0.91, 0.93, 0.98)
RED = (0xf7 / 255, 0x76 / 255, 0x8e / 255)
GREEN = (0x9e / 255, 0xce / 255, 0x6a / 255)
BAT = '/sys/class/power_supply/BAT0'


def icon_path(name):
    for d in ICONS:
        p = os.path.join(d, name + '.svg')
        if os.path.exists(p):
            return p


class StatusBar:
    def __init__(self):
        os.makedirs(OUT, exist_ok=True)
        self.state = {}
        self.last = None
        self.cache = {}
        self.volume = (50, False)
        self.bt = False
        self.poll()
        GLib.timeout_add_seconds(2, self.poll)
        GLib.timeout_add_seconds(6, self.poll_bt)
        self.poll_bt()

    # --- state -------------------------------------------------------------------------------

    def run(self, args, done):
        try:
            proc = Gio.Subprocess.new(args, Gio.SubprocessFlags.STDOUT_PIPE
                                      | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error:
            return

        def finish(p, res):
            try:
                _, out, _ = p.communicate_utf8_finish(res)
            except GLib.Error:
                out = ''
            done(out or '')
        proc.communicate_utf8_async(None, None, finish)

    def poll(self):
        self.run(['sh', '-c', 'pactl get-sink-volume @DEFAULT_SINK@; pactl get-sink-mute @DEFAULT_SINK@'],
                 self.got_volume)
        return True

    def got_volume(self, out):
        pct = next((int(w.rstrip('%')) for w in out.split() if w.endswith('%')), 0)
        self.volume = (pct, 'Mute: yes' in out)
        self.update()

    def poll_bt(self):
        self.run(['bluetoothctl', 'devices', 'Connected'],
                 lambda out: (setattr(self, 'bt', 'Device ' in out), self.update()))
        return True

    def wifi(self):
        try:
            for line in open('/proc/net/wireless').read().splitlines()[2:]:
                return int(float(line.split()[2]))
        except (OSError, ValueError, IndexError):
            pass
        return None

    def battery(self):
        try:
            return int(open(f'{BAT}/capacity').read()), open(f'{BAT}/status').read().strip()
        except (OSError, ValueError):
            return None

    # --- drawing -------------------------------------------------------------------------------

    def update(self):
        q = self.wifi()
        if q is None:
            wifi = 'network-wireless-offline-symbolic'
        else:
            wifi = 'network-wireless-signal-' + ('excellent' if q >= 55 else 'good' if q >= 40
                                                 else 'ok' if q >= 25 else 'weak') + '-symbolic'
        vol, muted = self.volume
        sound = 'audio-volume-' + ('muted' if muted or vol == 0 else 'high' if vol >= 67
                                   else 'medium' if vol >= 34 else 'low') + '-symbolic'
        state = (wifi, self.bt, sound, self.battery())
        if state == self.last:
            return
        self.last = state
        self.render(*state)
        tip = [f'Głośność {vol}%' + (' (wyciszona)' if muted else '')]
        if state[3]:
            tip.append(f'bateria {state[3][0]}%' + (', ładowanie' if state[3][1] == 'Charging' else ''))
        self.write('tooltip', ' · '.join(tip).encode())

    def svg(self, name):
        if name not in self.cache:
            path = icon_path(name)
            self.cache[name] = Rsvg.Handle.new_from_file(path) if path else None
        return self.cache[name]

    def render(self, wifi, bt, sound, battery):
        items = [wifi] + (['bluetooth-active-symbolic'] if bt else []) + [sound]
        pct_layout = None
        width = len(items) * ICON + (len(items) - 1) * GAP
        if battery:
            tmp = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
            # grey antialiasing: subpixel colour fringes show on a transparent image
            fo = cairo.FontOptions()
            fo.set_antialias(cairo.ANTIALIAS_GRAY)
            PangoCairo.context_set_font_options(PangoCairo.create_context(tmp), fo)
            pct_layout = PangoCairo.create_layout(tmp)
            PangoCairo.context_set_font_options(pct_layout.get_context(), fo)
            pct_layout.context_changed()
            desc = Pango.FontDescription('Inter Medium')
            desc.set_absolute_size(12 * Pango.SCALE)
            pct_layout.set_font_description(desc)
            pct_layout.set_text(f'{battery[0]}%', -1)
            width += GAP + 25 + 5 + pct_layout.get_pixel_size()[0]
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, HEIGHT)
        cr = cairo.Context(surf)
        x = 0
        for name in items:
            self.draw_icon(cr, name, x, (HEIGHT - ICON) / 2)
            x += ICON + GAP
        if battery:
            self.draw_battery(cr, x, HEIGHT / 2, *battery)
            cr.set_source_rgb(*WHITE)
            _, th = pct_layout.get_pixel_size()
            cr.move_to(x + 25 + 5, (HEIGHT - th) / 2)
            PangoCairo.show_layout(cr, pct_layout)
        tmp = os.path.join(OUT, 'icons.png.tmp')
        surf.write_to_png(tmp)
        os.replace(tmp, os.path.join(OUT, 'icons.png'))

    def draw_icon(self, cr, name, x, y):
        handle = self.svg(name)
        if not handle:
            return
        # render the symbolic icon as a mask and paint it in one colour
        mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, ICON, ICON)
        mcr = cairo.Context(mask)
        rect = Rsvg.Rectangle()
        rect.x, rect.y, rect.width, rect.height = 0, 0, ICON, ICON
        handle.render_document(mcr, rect)
        cr.set_source_rgb(*WHITE)
        cr.mask_surface(mask, x, y)

    def draw_battery(self, cr, x, cy, level, status):
        w, h, r = 22, 11, 3.5
        y = cy - h / 2
        cr.new_sub_path()
        for ax, ay, a0 in ((x + w - r, y + r, -math.pi / 2), (x + w - r, y + h - r, 0),
                           (x + r, y + h - r, math.pi / 2), (x + r, y + r, math.pi)):
            cr.arc(ax, ay, r, a0, a0 + math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(*WHITE, 0.5)
        cr.set_line_width(1.5)
        cr.stroke()
        cr.arc(x + w + 1.2, cy, 2, -math.pi / 2, math.pi / 2)
        cr.fill()
        fill = GREEN if status == 'Charging' else RED if level <= 20 else WHITE
        inner = max(3.6, (w - 5) * min(level, 100) / 100)
        cr.set_source_rgb(*fill)
        ir = 1.8
        cr.new_sub_path()
        cr.arc(x + 2.5 + inner - ir, y + 2.5 + ir, ir, -math.pi / 2, 0)
        cr.arc(x + 2.5 + inner - ir, y + h - 2.5 - ir, ir, 0, math.pi / 2)
        cr.arc(x + 2.5 + ir, y + h - 2.5 - ir, ir, math.pi / 2, math.pi)
        cr.arc(x + 2.5 + ir, y + 2.5 + ir, ir, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.fill()

    def write(self, name, data):
        tmp = os.path.join(OUT, name + '.tmp')
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, os.path.join(OUT, name))
