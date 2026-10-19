#!/usr/bin/env python3
# Quick settings popup: Wi-Fi, Bluetooth, do not disturb and night light tiles, sliders for
# volume (with the output picker), warmth and brightness. `quick-settings` toggles it.
import json
import os
import re

from popup import Popup, label, run
from status_bar import StatusBar
from gi.repository import Gio, GLib, Gtk

NIGHT_CFG = os.path.expanduser('~/.config/night-shift.json')
TEMP_MIN, TEMP_MAX = 1000, 6500
BAT = '/sys/class/power_supply/BAT0'

CSS = b"""
.card { padding: 14px; min-width: 330px; }
.glyph { font-family: "JetBrainsMono Nerd Font Propo"; }
.battery { font-size: 10pt; font-weight: 600; }
.battery-sub { font-size: 9pt; color: #565f89; }
.icon-btn {
  background-image: none; background-color: rgba(255, 255, 255, 0.06); border: 0;
  box-shadow: none; border-radius: 16px; min-width: 32px; min-height: 32px; padding: 0;
}
.icon-btn:hover { background-color: rgba(255, 255, 255, 0.12); }
.icon-btn label { font-size: 12pt; }
.tile { background-color: rgba(255, 255, 255, 0.06); border-radius: 14px; }
.tile.on { background-color: #7aa2f7; }
.tile button {
  background-image: none; background-color: transparent; border: 0; box-shadow: none;
  border-radius: 14px; padding: 0;
}
.tile button:hover { background-color: rgba(255, 255, 255, 0.07); }
.tile.on button:hover { background-color: rgba(255, 255, 255, 0.16); }
.tile .glyph { font-size: 14pt; }
.tile .title { font-size: 10pt; font-weight: 600; }
.tile .sub { font-size: 8.5pt; color: #a9b1d6; }
.tile.on label { color: #1a1b26; }
.row-glyph { font-size: 13pt; color: #a9b1d6; min-width: 28px; }
.row-btn {
  background-image: none; background-color: transparent; border: 0; box-shadow: none;
  border-radius: 14px; padding: 0; min-width: 28px; min-height: 28px;
}
.row-btn:hover { background-color: rgba(255, 255, 255, 0.07); }
.caption { font-size: 8.5pt; color: #565f89; }
scale trough {
  background-image: none; background-color: rgba(255, 255, 255, 0.10); border: 0;
  border-radius: 3px; min-height: 6px;
}
scale highlight { background-image: none; background-color: #7aa2f7; border: 0; border-radius: 3px; }
scale slider {
  background-image: none; background-color: #c0caf5; border: 0; border-radius: 8px;
  min-width: 16px; min-height: 16px; margin: -5px 0; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
}
.list-title { font-size: 8.5pt; font-weight: 600; color: #565f89; }
.item {
  background-image: none; background-color: transparent; border: 0; box-shadow: none;
  border-radius: 8px; padding: 6px 8px;
}
.item:hover { background-color: rgba(255, 255, 255, 0.07); }
.item label { font-size: 9.5pt; }
.item .meta { color: #565f89; font-size: 8.5pt; }
.item.current label { color: #7aa2f7; }
.rule { background-color: rgba(255, 255, 255, 0.06); min-height: 1px; }
"""


def sh(args, done=None):
    """Runs a command without blocking the popup; done(stdout) receives the output."""
    try:
        proc = Gio.Subprocess.new(args, Gio.SubprocessFlags.STDOUT_PIPE
                                  | Gio.SubprocessFlags.STDERR_SILENCE)
    except GLib.Error:
        if done:
            done('')
        return

    def finish(p, res):
        try:
            _, out, _ = p.communicate_utf8_finish(res)
        except GLib.Error:
            out = ''
        if done:
            done(out or '')
    proc.communicate_utf8_async(None, None, finish)


def nm_fields(line):
    # nmcli -t escapes ':' inside values as '\:'
    return [f.replace('\\:', ':') for f in re.split(r'(?<!\\):', line)]


class Tile(Gtk.Box):
    def __init__(self, glyph, title, on_toggle, on_more=None):
        super().__init__()
        self.get_style_context().add_class('tile')
        main = Gtk.Button(can_focus=False)
        main.connect('clicked', lambda *_: on_toggle())
        box = Gtk.Box(spacing=10, margin_start=12, margin_end=8, margin_top=9, margin_bottom=9)
        self.glyph = label('glyph', glyph)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.pack_start(label('title', title, xalign=0), False, False, 0)
        self.sub = label('sub', '…', xalign=0, ellipsize=3, max_width_chars=12)
        text.pack_start(self.sub, False, False, 0)
        box.pack_start(self.glyph, False, False, 0)
        box.pack_start(text, True, True, 0)
        main.add(box)
        self.pack_start(main, True, True, 0)
        if on_more:
            more = Gtk.Button(can_focus=False)
            more.add(label('glyph', '', margin_start=9, margin_end=9))
            more.connect('clicked', lambda *_: on_more())
            self.pack_end(more, False, False, 0)

    def set(self, on, glyph, sub):
        ctx = self.get_style_context()
        (ctx.add_class if on else ctx.remove_class)('on')
        self.glyph.set_text(glyph)
        self.sub.set_text(sub)


class Slider(Gtk.Box):
    def __init__(self, glyph, lo, hi, on_change, on_glyph=None, on_more=None):
        super().__init__(spacing=6)
        self.on_change = on_change
        if on_glyph:
            btn = Gtk.Button(can_focus=False)
            btn.get_style_context().add_class('row-btn')
            self.glyph = label('glyph row-glyph', glyph)
            btn.add(self.glyph)
            btn.connect('clicked', lambda *_: on_glyph())
            self.pack_start(btn, False, False, 0)
        else:
            self.glyph = label('glyph row-glyph', glyph)
            self.pack_start(self.glyph, False, False, 0)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        self.scale.set_draw_value(False)
        self.scale.set_can_focus(False)
        self.handler = self.scale.connect('value-changed', self.changed)
        self.pack_start(self.scale, True, True, 0)
        if on_more:
            more = Gtk.Button(can_focus=False)
            more.get_style_context().add_class('row-btn')
            more.add(label('glyph row-glyph', ''))
            more.connect('clicked', lambda *_: on_more())
            self.pack_end(more, False, False, 0)
        self.pending = None

    def changed(self, scale):
        # apply at most every 80 ms while dragging
        if self.pending is None:
            self.pending = GLib.timeout_add(80, self.flush)

    def flush(self):
        self.pending = None
        self.on_change(int(self.scale.get_value()))
        return False

    def set(self, value):
        with self.scale.handler_block(self.handler):
            self.scale.set_value(value)


class QuickSettings(Popup):
    APP_ID = 'dev.dotims.QuickSettings'
    CSS = CSS

    def build(self, card):
        top = Gtk.Box(spacing=6)
        bat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.battery = label('battery', xalign=0)
        self.battery_sub = label('battery-sub', xalign=0)
        bat.pack_start(self.battery, False, False, 0)
        bat.pack_start(self.battery_sub, False, False, 0)
        top.pack_start(bat, True, True, 0)
        for glyph, cmd in (('\U000f0493', ['xfce4-settings-manager']),
                           ('\U000f033e', [os.path.expanduser('~/.local/bin/lock-now')]),
                           # the delay lets the click release pass, or it wakes the screen again
                           ('\U000f0d90', ['sh', '-c', 'sleep 0.5; xset dpms force off']),
                           ('\U000f0425', ['rofi', '-show', 'power', '-modi',
                                           'power:' + os.path.expanduser('~/.local/bin/rofi-power')])):
            b = Gtk.Button(can_focus=False)
            b.get_style_context().add_class('icon-btn')
            b.add(label('glyph', glyph))
            b.connect('clicked', lambda _b, c=cmd: self.launch(c))
            top.pack_end(b, False, False, 0)
        card.pack_start(top, False, False, 0)

        grid = Gtk.Grid(column_homogeneous=True, row_spacing=8, column_spacing=8, margin_top=14)
        self.wifi = Tile('\U000f05a9', 'Wi-Fi', self.toggle_wifi, lambda: self.show_list('wifi'))
        self.bt = Tile('\U000f00af', 'Bluetooth', self.toggle_bt, lambda: self.show_list('bt'))
        self.dnd = Tile('\U000f009b', 'Nie przeszkadzać', self.toggle_dnd)
        self.night = Tile('\U000f0594', 'Nocne światło', self.toggle_night)
        grid.attach(self.wifi, 0, 0, 1, 1)
        grid.attach(self.bt, 1, 0, 1, 1)
        grid.attach(self.dnd, 0, 1, 1, 1)
        grid.attach(self.night, 1, 1, 1, 1)
        card.pack_start(grid, False, False, 0)

        sliders = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=14)
        self.sink_caption = label('caption', xalign=0, margin_start=34, ellipsize=3)
        sliders.pack_start(self.sink_caption, False, False, 0)
        self.volume = Slider('\U000f057e', 0, 100, self.set_volume, on_glyph=self.toggle_mute,
                             on_more=lambda: self.show_list('sinks'))
        sliders.pack_start(self.volume, False, False, 0)
        self.warmth = Slider('\U000f0594', 0, TEMP_MAX - TEMP_MIN, self.set_warmth)
        sliders.pack_start(self.warmth, False, False, 0)
        self.light = Slider('\U000f00df', 5, 100, self.set_brightness)
        sliders.pack_start(self.light, False, False, 0)
        card.pack_start(sliders, False, False, 0)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                     transition_duration=150)
        self.revealer.add(self.list_box)
        card.pack_start(self.revealer, False, False, 0)
        self.list_kind = None
        self.night_cfg = {'temp': 4500, 'on': False}
        self.status = StatusBar()

    def launch(self, cmd):
        self.close()
        try:
            Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE)
        except GLib.Error:
            pass

    # --- state -------------------------------------------------------------------------------

    def refresh(self):
        self.revealer.set_reveal_child(False)
        self.list_kind = None
        if os.environ.get('QUICK_SETTINGS_DEMO'):
            return self.demo()
        self.read_battery()
        sh(['nmcli', '-t', '-f', 'WIFI', 'general'], self.got_wifi_radio)
        sh(['bluetoothctl', 'show'], self.got_bt)
        sh(['xfconf-query', '-c', 'xfce4-notifyd', '-p', '/do-not-disturb'],
           lambda out: self.dnd.set(out.strip() == 'true', '\U000f009b' if out.strip() == 'true'
                                    else '\U000f009a', 'Włączone' if out.strip() == 'true'
                                    else 'Wyłączone'))
        self.read_night()
        self.read_sound()
        sh(['brightnessctl', '-m', '-c', 'backlight'], self.got_brightness)

    def demo(self):
        # fixed values for screenshots
        self.battery.set_markup('<span font_family="JetBrainsMono Nerd Font Propo">\U000f0082</span>  86%')
        self.battery_sub.set_text('zostało 4 h 12 min')
        self.wifi.set(True, '\U000f05a9', 'Home')
        self.bt.set(True, '\U000f00b1', 'AirPods Pro')
        self.dnd.set(False, '\U000f009a', 'Wyłączone')
        self.night.set(True, '\U000f0594', '4500 K')
        self.sink_caption.set_text('AirPods Pro')
        self.volume.set(45)
        self.warmth.set(TEMP_MAX - 4500)
        self.warmth.show()
        self.light.set(70)

    def read_battery(self):
        try:
            cap = int(open(f'{BAT}/capacity').read())
            status = open(f'{BAT}/status').read().strip()
        except OSError:
            self.battery.set_text('Zasilanie z sieci')
            self.battery_sub.set_text('')
            return
        glyph = '\U000f0084' if status == 'Charging' else '\U000f0079'
        self.battery.set_markup(f'<span font_family="JetBrainsMono Nerd Font Propo">{glyph}</span>  {cap}%')
        self.battery_sub.set_text({'Charging': 'ładowanie', 'Full': 'naładowana',
                                   'Not charging': 'podłączona'}.get(status, 'na baterii'))
        if status == 'Discharging':
            sh(['upower', '-i', '/org/freedesktop/UPower/devices/battery_BAT0'], self.got_upower)

    def got_upower(self, out):
        m = re.search(r'time to empty:\s+([\d.,]+)\s+(\w+)', out)
        if not m:
            return
        value = float(m.group(1).replace(',', '.'))
        mins = int(value * 60) if m.group(2).startswith('hour') else int(value)
        self.battery_sub.set_text(f'zostało {mins // 60} h {mins % 60} min')

    def got_wifi_radio(self, out):
        if out.strip() != 'enabled':
            self.wifi.set(False, '\U000f05aa', 'Wyłączone')
            return
        sh(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi', 'list', '--rescan', 'no'],
           self.got_wifi_active)

    def got_wifi_active(self, out):
        ssid = next((f[1] for f in map(nm_fields, out.splitlines()) if f[0] == 'yes'), None)
        self.wifi.set(True, '\U000f05a9', ssid or 'Niepołączone')

    def got_bt(self, out):
        if 'Powered: yes' not in out:
            self.bt.set(False, '\U000f00b2', 'Wyłączony')
            return
        sh(['bluetoothctl', 'devices', 'Connected'], self.got_bt_connected)

    def got_bt_connected(self, out):
        names = [line.split(' ', 2)[2] for line in out.splitlines()
                 if line.startswith('Device ') and len(line.split(' ', 2)) == 3]
        self.bt.set(True, '\U000f00b1' if names else '\U000f00af',
                    ', '.join(names) if names else 'Włączony')

    def read_night(self):
        try:
            self.night_cfg = json.load(open(NIGHT_CFG))
        except (OSError, ValueError):
            pass
        on, temp = self.night_cfg.get('on'), self.night_cfg.get('temp', 4500)
        self.night.set(bool(on), '\U000f0594', f'{temp} K' if on else 'Wyłączone')
        self.warmth.set(TEMP_MAX - temp)
        self.warmth.set_visible(bool(on))

    def read_sound(self):
        sh(['pactl', 'get-sink-volume', '@DEFAULT_SINK@'], self.got_volume)
        sh(['pactl', 'get-sink-mute', '@DEFAULT_SINK@'], self.got_mute)
        # plain text: pactl's JSON breaks on names like "Radek’s AirPods"
        sh(['pactl', 'get-default-sink'], lambda d: sh(['pactl', 'list', 'sinks'],
                                                       lambda out: self.got_sinks(d.strip(), out)))

    def got_volume(self, out):
        m = re.search(r'(\d+)%', out)
        if m:
            self.volume.set(int(m.group(1)))

    def got_mute(self, out):
        self.volume.glyph.set_text('\U000f075f' if 'yes' in out else '\U000f057e')

    def got_sinks(self, default, out):
        self.sinks = [{'name': n, 'description': d} for n, d in
                      re.findall(r'^\s*Name: (.+)\n(?:.*\n)*?\s*Description: (.+)$', out, re.M)]
        self.default_sink = default
        desc = next((s.get('description', s['name']) for s in self.sinks if s['name'] == default), '')
        self.sink_caption.set_text(desc)

    def got_brightness(self, out):
        parts = out.strip().split(',')
        if len(parts) < 4:
            self.light.hide()
            return
        self.light.show()
        self.light.set(int(parts[3].rstrip('%')))

    # --- actions -------------------------------------------------------------------------------

    def toggle_wifi(self):
        on = 'on' in self.wifi.get_style_context().list_classes()
        sh(['nmcli', 'radio', 'wifi', 'off' if on else 'on'], lambda _: self.refresh_soon())

    def toggle_bt(self):
        on = 'on' in self.bt.get_style_context().list_classes()
        sh(['bluetoothctl', 'power', 'off' if on else 'on'], lambda _: self.refresh_soon())

    def toggle_dnd(self):
        on = 'on' in self.dnd.get_style_context().list_classes()
        sh(['xfconf-query', '-c', 'xfce4-notifyd', '-p', '/do-not-disturb', '-n', '-t', 'bool',
            '-s', 'false' if on else 'true'], lambda _: self.refresh_soon())

    def toggle_night(self):
        self.night_cfg['on'] = not self.night_cfg.get('on')
        self.save_night()
        if self.night_cfg['on']:
            sh(['redshift', '-P', '-O', str(self.night_cfg.get('temp', 4500))])
        else:
            sh(['redshift', '-x'])
        self.read_night()

    def set_warmth(self, value):
        self.night_cfg['temp'] = TEMP_MAX - value
        self.save_night()
        sh(['redshift', '-P', '-O', str(self.night_cfg['temp'])])
        self.night.sub.set_text(f'{self.night_cfg["temp"]} K')

    def save_night(self):
        with open(NIGHT_CFG, 'w') as f:
            json.dump({'temp': self.night_cfg.get('temp', 4500), 'on': bool(self.night_cfg.get('on'))},
                      f, indent=2)

    def set_volume(self, value):
        sh(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{value}%'])

    def toggle_mute(self):
        sh(['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'],
           lambda _: sh(['pactl', 'get-sink-mute', '@DEFAULT_SINK@'], self.got_mute))

    def set_brightness(self, value):
        sh(['brightnessctl', '-q', '-c', 'backlight', 'set', f'{value}%'])

    def refresh_soon(self):
        GLib.timeout_add(400, lambda: (self.refresh(), False)[1])

    # --- lists ---------------------------------------------------------------------------------

    def show_list(self, kind):
        if self.list_kind == kind and self.revealer.get_reveal_child():
            self.revealer.set_reveal_child(False)
            self.list_kind = None
            return
        self.list_kind = kind
        if kind == 'wifi':
            sh(['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list',
                '--rescan', 'auto'], self.fill_wifi)
        elif kind == 'bt':
            sh(['bluetoothctl', 'devices', 'Paired'],
               lambda paired: sh(['bluetoothctl', 'devices', 'Connected'],
                                 lambda conn: self.fill_bt(paired, conn)))
        else:
            self.fill_list('Wyjście dźwięku', [
                (s.get('description', s['name']), '', s['name'] == getattr(self, 'default_sink', ''),
                 lambda n=s['name']: sh(['pactl', 'set-default-sink', n], lambda _: self.read_sound()))
                for s in getattr(self, 'sinks', [])])

    def fill_wifi(self, out):
        seen, rows = set(), []
        for f in map(nm_fields, out.splitlines()):
            if len(f) < 4 or not f[1] or f[1] in seen:
                continue
            seen.add(f[1])
            meta = f'{f[2]}%' + ('  \U000f033e' if f[3] and f[3] != '--' else '')
            rows.append((f[1], meta, f[0] == 'yes',
                         lambda s=f[1]: sh(['nmcli', 'dev', 'wifi', 'connect', s],
                                           lambda _: self.refresh_soon())))
        self.fill_list('Sieci', rows[:7])

    def fill_bt(self, paired, connected):
        conn = {line.split(' ', 2)[1] for line in connected.splitlines() if line.startswith('Device ')}
        rows = []
        for line in paired.splitlines():
            parts = line.split(' ', 2)
            if len(parts) < 3 or parts[0] != 'Device':
                continue
            mac, name = parts[1], parts[2]
            is_on = mac in conn
            rows.append((name, 'połączono' if is_on else '', is_on,
                         lambda m=mac, c=is_on: sh(['bluetoothctl', 'disconnect' if c else 'connect', m],
                                                   lambda _: self.refresh_soon())))
        self.fill_list('Urządzenia', rows)

    def fill_list(self, title, rows):
        for child in self.list_box.get_children():
            child.destroy()
        self.list_box.pack_start(Gtk.Box(margin_top=12), False, False, 0)
        rule = Gtk.Box(); rule.get_style_context().add_class('rule')
        self.list_box.pack_start(rule, False, False, 0)
        self.list_box.pack_start(label('list-title', title.upper(), xalign=0, margin_top=10,
                                       margin_bottom=4, margin_start=8), False, False, 0)
        if not rows:
            self.list_box.pack_start(label('caption', 'Nic tu nie ma', xalign=0, margin_start=8),
                                     False, False, 0)
        for name, meta, current, action in rows:
            b = Gtk.Button(can_focus=False)
            b.get_style_context().add_class('item')
            if current:
                b.get_style_context().add_class('current')
            box = Gtk.Box(spacing=8)
            box.pack_start(label('', name, xalign=0, ellipsize=3), True, True, 0)
            box.pack_end(label('meta glyph', meta), False, False, 0)
            b.add(box)
            b.connect('clicked', lambda _b, a=action: a())
            self.list_box.pack_start(b, False, False, 0)
        self.list_box.show_all()
        self.revealer.set_reveal_child(True)
        GLib.timeout_add(160, lambda: (self.place(), False)[1])


if __name__ == '__main__':
    run(QuickSettings, 'quick-settings')
