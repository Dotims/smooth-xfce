#!/usr/bin/env python3
# Clock popup: month grid from Monday, Polish public holidays in red, the next day off.
# Stays running hidden; `calendar-popup` toggles it over D-Bus so it opens instantly.
import datetime as dt

from popup import Popup, label, run
from gi.repository import Gdk, Gtk

MONTHS = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień',
          'wrzesień', 'październik', 'listopad', 'grudzień']
MONTHS_OF = ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia',
             'września', 'października', 'listopada', 'grudnia']
WEEKDAYS = ['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela']
DAY_LABELS = ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'So', 'Nd']

CSS = b""".weekday { color: #7aa2f7; font-size: 10pt; font-weight: 600; }
.week { color: #565f89; font-size: 9pt; }
.date { font-size: 19pt; font-weight: 600; }
.month { font-size: 11pt; font-weight: 600; }
.nav {
  background-image: none; background-color: transparent; border: 0; box-shadow: none;
  border-radius: 8px; color: #a9b1d6; min-height: 26px; min-width: 26px; padding: 0 6px;
}
.nav:hover { background-color: rgba(255, 255, 255, 0.07); color: #c0caf5; }
.nav label { color: #7aa2f7; font-size: 9pt; font-weight: 600; }
.head { color: #565f89; font-size: 8.5pt; font-weight: 600; }
.head.sun { color: rgba(247, 118, 142, 0.55); }
.day { font-size: 10pt; min-width: 30px; min-height: 30px; border-radius: 15px; }
.day.sat { color: #9aa5ce; }
.day.red { color: #f7768e; }
.day.other { color: #3b4261; }
.day.other.red { color: rgba(247, 118, 142, 0.35); }
.day.today { background-color: #7aa2f7; color: #1a1b26; font-weight: 700; }
.rule { background-color: rgba(255, 255, 255, 0.06); min-height: 1px; }
.dot { color: #f7768e; font-size: 9pt; }
.hname { font-size: 10pt; font-weight: 600; }
.hwhen { color: #565f89; font-size: 9pt; }
"""


def easter(y):
    # anonymous Gregorian algorithm
    a, b, c = y % 19, y // 100, y % 100
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(y, month, day + 1)


def holidays(y):
    e, d, w = easter(y), dt.date, dt.timedelta
    days = {
        d(y, 1, 1): 'Nowy Rok', d(y, 1, 6): 'Trzech Króli',
        e: 'Wielkanoc', e + w(1): 'Poniedziałek Wielkanocny',
        d(y, 5, 1): 'Święto Pracy', d(y, 5, 3): 'Święto Konstytucji 3 Maja',
        e + w(49): 'Zielone Świątki', e + w(60): 'Boże Ciało',
        d(y, 8, 15): 'Wniebowzięcie NMP', d(y, 11, 1): 'Wszystkich Świętych',
        d(y, 11, 11): 'Święto Niepodległości',
        d(y, 12, 25): 'Boże Narodzenie', d(y, 12, 26): 'drugi dzień świąt',
    }
    if y >= 2025:
        days[d(y, 12, 24)] = 'Wigilia'
    return days


def next_holiday(today):
    for y in (today.year, today.year + 1):
        for day, name in sorted(holidays(y).items()):
            if day >= today:
                return day, name


def in_days(n):
    return 'dziś' if n == 0 else 'jutro' if n == 1 else f'za {n} dni'


class Calendar(Popup):
    APP_ID = 'dev.dotims.Calendar'
    CSS = CSS

    def __init__(self, hidden):
        super().__init__(hidden)
        self.shown = dt.date.today().replace(day=1)
        self.scroll = 0.0

    def build(self, card):
        top = Gtk.Box(spacing=8)
        self.weekday = self.label('weekday', xalign=0)
        self.week = self.label('week', xalign=1)
        top.pack_start(self.weekday, True, True, 0); top.pack_end(self.week, False, False, 0)
        card.pack_start(top, False, False, 0)
        self.date = self.label('date', xalign=0)
        self.date.set_margin_top(2)
        card.pack_start(self.date, False, False, 0)

        nav = Gtk.Box(spacing=2)
        nav.set_margin_top(14); nav.set_margin_bottom(6)
        self.month = self.label('month', xalign=0)
        nav.pack_start(self.month, True, True, 0)
        self.today_btn = self.button(Gtk.Label(label='dziś'), lambda *_: self.go(None))
        prev = self.button(Gtk.Image.new_from_icon_name('pan-start-symbolic', Gtk.IconSize.BUTTON),
                           lambda *_: self.go(-1))
        nxt = self.button(Gtk.Image.new_from_icon_name('pan-end-symbolic', Gtk.IconSize.BUTTON),
                          lambda *_: self.go(1))
        for b in (nxt, prev, self.today_btn):
            nav.pack_end(b, False, False, 0)
        card.pack_start(nav, False, False, 0)

        grid = Gtk.Grid(column_homogeneous=True, row_spacing=2, column_spacing=6)
        for c, name in enumerate(DAY_LABELS):
            head = self.label('head', name)
            if c == 6:
                head.get_style_context().add_class('sun')
            head.set_margin_bottom(4)
            grid.attach(head, c, 0, 1, 1)
        self.cells = []
        for r in range(6):
            for c in range(7):
                cell = self.label('day', halign=Gtk.Align.CENTER)
                grid.attach(cell, c, r + 1, 1, 1)
                self.cells.append(cell)
        card.pack_start(grid, False, False, 0)

        rule = Gtk.Box(); rule.get_style_context().add_class('rule')
        rule.set_margin_top(12); rule.set_margin_bottom(10)
        card.pack_start(rule, False, False, 0)
        foot = Gtk.Box(spacing=8)
        dot = self.label('dot', '●', valign=Gtk.Align.START)
        dot.set_margin_top(1)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.hname = self.label('hname', xalign=0)
        self.hwhen = self.label('hwhen', xalign=0)
        text.pack_start(self.hname, False, False, 0); text.pack_start(self.hwhen, False, False, 0)
        foot.pack_start(dot, False, False, 0); foot.pack_start(text, True, True, 0)
        card.pack_start(foot, False, False, 0)

    def label(self, cls, text='', **props):
        return label(cls, text, **props)

    def button(self, child, cb):
        b = Gtk.Button(relief=Gtk.ReliefStyle.NONE, can_focus=False)
        b.get_style_context().add_class('nav')
        b.add(child)
        b.connect('clicked', cb)
        return b

    def fill(self):
        today = dt.date.today()
        self.weekday.set_text(WEEKDAYS[today.weekday()])
        self.week.set_text(f'tydzień {today.isocalendar()[1]}')
        self.date.set_text(f'{today.day} {MONTHS_OF[today.month - 1]} {today.year}')
        first = self.shown
        self.month.set_text(f'{MONTHS[first.month - 1].capitalize()} {first.year}')
        self.today_btn.set_visible(first != today.replace(day=1))
        red = {**holidays(first.year - 1), **holidays(first.year), **holidays(first.year + 1)}
        day = first - dt.timedelta(days=first.weekday())
        for cell in self.cells:
            ctx = cell.get_style_context()
            for cls in ('sat', 'red', 'other', 'today'):
                ctx.remove_class(cls)
            cell.set_text(str(day.day))
            cell.set_tooltip_text(red.get(day))
            if day.month != first.month:
                ctx.add_class('other')
            if day == today:
                ctx.add_class('today')
            elif day in red or day.weekday() == 6:
                ctx.add_class('red')
            elif day.weekday() == 5:
                ctx.add_class('sat')
            day += dt.timedelta(days=1)
        hday, hname = next_holiday(today)
        self.hname.set_text(hname)
        self.hwhen.set_text(f'{WEEKDAYS[hday.weekday()]}, {hday.day} {MONTHS_OF[hday.month - 1]}'
                            f' · {in_days((hday - today).days)}')

    def go(self, step):
        if step is None:
            self.shown = dt.date.today().replace(day=1)
        else:
            y, m = divmod(self.shown.year * 12 + self.shown.month - 1 + step, 12)
            self.shown = dt.date(y, m + 1, 1)
        self.fill()

    def refresh(self):
        self.shown = dt.date.today().replace(day=1)
        self.fill()

    def on_key(self, key):
        if key in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.go(-1)
        elif key in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.go(1)
        elif key in (Gdk.KEY_Home, Gdk.KEY_t):
            self.go(None)
        return True

    def on_scroll(self, ev):
        if ev.direction == Gdk.ScrollDirection.SMOOTH:
            # touchpads send small deltas; flip a month per full notch
            self.scroll += ev.delta_y
            if abs(self.scroll) >= 1:
                self.go(1 if self.scroll > 0 else -1)
                self.scroll = 0.0
        elif ev.direction in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.DOWN):
            self.go(-1 if ev.direction == Gdk.ScrollDirection.UP else 1)
        return True


if __name__ == '__main__':
    run(Calendar, 'calendar-popup')
