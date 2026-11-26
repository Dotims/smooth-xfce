#!/usr/bin/env python3
# Clock popup: month grid from Monday, Polish public holidays in red, the next day off, in English
# or Polish (EN/PL in the footer, or the L key; the choice is remembered).
# Google calendars listed in google-calendars.json (their secret iCal addresses) add a dot on days
# with events, the agenda of today or of a clicked day, and what is coming up.
# Stays running hidden; `calendar-popup` toggles it over D-Bus so it opens instantly.
import datetime as dt
import hashlib
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import namedtuple

from popup import Popup, label, run
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

try:
    import icalendar
    import recurring_ical_events
except ImportError:  # the popup still works, only without Google events
    icalendar = None

CFG = os.path.expanduser('~/.config/desktop-look/calendar.json')
# [{"url": "<secret address in iCal format>", "account": "<Google login>", "routine": true?}];
# a routine calendar (a timetable) shows in the day's agenda but adds no dots and no "coming up"
GCAL = os.path.expanduser('~/.config/desktop-look/google-calendars.json')
CACHE = os.path.expanduser('~/.cache/desktop-look/gcal')
SYNC_EVERY, STALE = 600, 180  # seconds; opening the popup syncs data older than STALE
AHEAD = 60  # days "coming up" looks ahead
DAY_ROWS, COMING_ROWS = 5, 3
LANGS = ('en', 'pl')
EN_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
             'October', 'November', 'December']
TEXT = {
    'en': {
        'months': EN_MONTHS,
        'months_of': EN_MONTHS,
        'months_short': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov',
                         'Dec'],
        'weekdays': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        'days': ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
        'week': 'week {}',
        'when': ('today', 'tomorrow', 'in {} days'),
        'agenda': ('Today', 'Coming up'),
        'all_day': 'all day',
        'nothing': 'Nothing planned',
        'more': '+{} more',
    },
    'pl': {
        'months': ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień',
                   'wrzesień', 'październik', 'listopad', 'grudzień'],
        'months_of': ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca',
                      'sierpnia', 'września', 'października', 'listopada', 'grudnia'],
        'months_short': ['sty', 'lut', 'mar', 'kwi', 'maj', 'cze', 'lip', 'sie', 'wrz', 'paź', 'lis',
                         'gru'],
        'weekdays': ['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela'],
        'days': ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'So', 'Nd'],
        'week': 'tydzień {}',
        'when': ('dziś', 'jutro', 'za {} dni'),
        'agenda': ('Dziś', 'Wkrótce'),
        'all_day': 'cały dzień',
        'nothing': 'Nic zaplanowanego',
        'more': '+{} więcej',
    },
}

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
.lang { min-width: 24px; padding: 0 4px; }
.lang label { color: #565f89; }
.lang.on label { color: #7aa2f7; }
.head { color: #565f89; font-size: 8.5pt; font-weight: 600; }
.head.sun { color: rgba(247, 118, 142, 0.55); }
.day { font-size: 10pt; min-width: 30px; min-height: 30px; border-radius: 15px; }
.day.sat { color: #9aa5ce; }
.day.red { color: #f7768e; }
.day.other { color: #3b4261; }
.day.other.red { color: rgba(247, 118, 142, 0.35); }
.day.today { background-color: #7aa2f7; color: #1a1b26; font-weight: 700; }
.day.busy { background-image: radial-gradient(circle 2px at 50% 25px, #7aa2f7 80%, transparent 100%); }
.day.today.busy { background-image: radial-gradient(circle 2px at 50% 25px, #1a1b26 80%, transparent 100%); }
.day.picked { box-shadow: inset 0 0 0 1px rgba(122, 162, 247, 0.65); }
.rule { background-color: rgba(255, 255, 255, 0.06); min-height: 1px; }
.dot { color: #f7768e; font-size: 9pt; }
.hname { font-size: 10pt; font-weight: 600; }
.hwhen { color: #565f89; font-size: 9pt; }
.ahead { color: #565f89; font-size: 8.5pt; font-weight: 600; margin: 2px 0 3px 6px; }
.event {
  background-image: none; background-color: transparent; border: 0; box-shadow: none;
  border-radius: 8px; min-height: 0; padding: 4px 6px;
}
.event:hover { background-color: rgba(255, 255, 255, 0.06); }
.bar { min-width: 3px; min-height: 14px; border-radius: 2px; background-color: #7aa2f7; }
.bar.c1 { background-color: #9ece6a; }
.bar.c2 { background-color: #e0af68; }
.bar.c3 { background-color: #7dcfff; }
.bar.routine { background-color: #bb9af7; }
.etime { color: #a9b1d6; font-size: 9pt; font-feature-settings: "tnum"; }
.etitle { font-size: 9.5pt; }
.erel { color: #565f89; font-size: 9pt; }
.event.past label { color: #565f89; }
.event.past .bar { opacity: 0.4; }
.none { color: #565f89; font-size: 9pt; margin: 2px 0 0 6px; }
"""

Cal = namedtuple('Cal', 'ical color routine account')
Event = namedtuple('Event', 'day start end title cal')  # start/end are local times, None all day


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
    # {date: (English name, Polish name)}, in the order of LANGS
    e, d, w = easter(y), dt.date, dt.timedelta
    days = {
        d(y, 1, 1): ("New Year's Day", 'Nowy Rok'), d(y, 1, 6): ('Epiphany', 'Trzech Króli'),
        e: ('Easter Sunday', 'Wielkanoc'), e + w(1): ('Easter Monday', 'Poniedziałek Wielkanocny'),
        d(y, 5, 1): ('Labour Day', 'Święto Pracy'),
        d(y, 5, 3): ('Constitution Day', 'Święto Konstytucji 3 Maja'),
        e + w(49): ('Pentecost', 'Zielone Świątki'), e + w(60): ('Corpus Christi', 'Boże Ciało'),
        d(y, 8, 15): ('Assumption Day', 'Wniebowzięcie NMP'),
        d(y, 11, 1): ("All Saints' Day", 'Wszystkich Świętych'),
        d(y, 11, 11): ('Independence Day', 'Święto Niepodległości'),
        d(y, 12, 25): ('Christmas Day', 'Boże Narodzenie'),
        d(y, 12, 26): ('Second Day of Christmas', 'drugi dzień świąt'),
    }
    if y >= 2025:
        days[d(y, 12, 24)] = ('Christmas Eve', 'Wigilia')
    return days


def next_holiday(today):
    for y in (today.year, today.year + 1):
        for day, names in sorted(holidays(y).items()):
            if day >= today:
                return day, names


def in_days(n, lang):
    today, tomorrow, later = TEXT[lang]['when']
    return today if n == 0 else tomorrow if n == 1 else later.format(n)


def load_lang():
    try:
        lang = json.load(open(CFG)).get('lang')
    except (OSError, ValueError, AttributeError):
        lang = None
    return lang if lang in LANGS else 'en'


def save_lang(lang):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, 'w') as f:
        json.dump({'lang': lang}, f)


def load_sources():
    if icalendar is None:
        return []
    try:
        items = json.load(open(GCAL))
    except (OSError, ValueError):
        return []
    return [c for c in items if isinstance(c, dict) and c.get('url')] if isinstance(items, list) else []


def fetch(url):
    # the feed from Google, or the last good copy when offline (the cache holds private events: 600)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16] + '.ics')
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = r.read()
        os.makedirs(CACHE, mode=0o700, exist_ok=True)
        with open(os.open(path + '.part', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'wb') as f:
            f.write(data)
        os.replace(path + '.part', path)
        return data
    except OSError:
        try:
            with open(path, 'rb') as f:
                return f.read()
        except OSError:
            return None


def read_calendars(sources):
    cals, personal = [], 0
    for src in sources:
        data = fetch(src['url'])
        try:
            ical = icalendar.Calendar.from_ical(data) if data else None
        except ValueError:
            ical = None
        if ical is None:
            continue
        routine = bool(src.get('routine'))
        color = 'routine' if routine else f'c{personal % 4}'
        personal += not routine
        cals.append(Cal(ical, color, routine, src.get('account', '')))
    return cals


def local(t):
    # naive local time, comparable with datetime.now()
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def events(cals, first, last):
    # every event between the two dates; an all-day event is listed on each day it covers
    out = []
    for cal in cals:
        try:
            items = recurring_ical_events.of(cal.ical).between(first, last + dt.timedelta(days=1))
        except Exception:  # one malformed feed must not take the popup down
            continue
        for e in items:
            if str(e.get('STATUS', '')).upper() == 'CANCELLED':
                continue
            title = str(e.get('SUMMARY', '')).strip() or '…'
            start = e['DTSTART'].dt
            end = e['DTEND'].dt if e.get('DTEND') else None
            if isinstance(start, dt.datetime):
                start = local(start)
                end = local(end) if isinstance(end, dt.datetime) else start
                if first <= start.date() <= last:
                    out.append(Event(start.date(), start, end, title, cal))
                continue
            stop = end if type(end) is dt.date and end > start else start + dt.timedelta(days=1)
            day = max(start, first)
            while day < stop and day <= last:
                out.append(Event(day, None, None, title, cal))
                day += dt.timedelta(days=1)
    out.sort(key=lambda e: (e.day, e.start is not None, e.start or dt.datetime.min))
    return out


class Calendar(Popup):
    APP_ID = 'dev.dotims.Calendar'
    CSS = CSS

    def __init__(self, hidden):
        super().__init__(hidden)
        self.shown = dt.date.today().replace(day=1)
        self.picked = None
        self.scroll = 0.0
        self.lang = load_lang()
        self.cals = []
        self.syncing = False
        self.synced = 0.0

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
        self.today_label = Gtk.Label()
        self.today_btn = self.button(self.today_label, lambda *_: self.go(None))
        prev = self.button(Gtk.Image.new_from_icon_name('pan-start-symbolic', Gtk.IconSize.BUTTON),
                           lambda *_: self.go(-1))
        nxt = self.button(Gtk.Image.new_from_icon_name('pan-end-symbolic', Gtk.IconSize.BUTTON),
                          lambda *_: self.go(1))
        for b in (nxt, prev, self.today_btn):
            nav.pack_end(b, False, False, 0)
        card.pack_start(nav, False, False, 0)

        grid = Gtk.Grid(column_homogeneous=True, row_spacing=2, column_spacing=6)
        self.heads = []
        for c in range(7):
            head = self.label('head')
            if c == 6:
                head.get_style_context().add_class('sun')
            head.set_margin_bottom(4)
            grid.attach(head, c, 0, 1, 1)
            self.heads.append(head)
        self.cells, self.cell_days = [], [None] * 42
        for r in range(6):
            for c in range(7):
                cell = self.label('day', halign=Gtk.Align.CENTER)
                box = Gtk.EventBox(visible_window=False)
                box.add(cell)
                box.connect('button-press-event', lambda _b, _e, n=len(self.cells): self.pick(n))
                grid.attach(box, c, r + 1, 1, 1)
                self.cells.append(cell)
        card.pack_start(grid, False, False, 0)

        # agenda, shown once a Google calendar has been read
        self.agenda = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.agenda.set_no_show_all(True)
        rule = Gtk.Box(); rule.get_style_context().add_class('rule')
        rule.set_margin_top(12); rule.set_margin_bottom(6)
        self.day_head = self.label('ahead', xalign=0)
        self.day_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.coming_head = self.label('ahead', xalign=0)
        self.coming_head.set_margin_top(8)
        self.coming_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for w in (rule, self.day_head, self.day_list, self.coming_head, self.coming_list):
            self.agenda.pack_start(w, False, False, 0)
            w.show()
        card.pack_start(self.agenda, False, False, 0)
        self.when_width = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

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
        switch = Gtk.Box(valign=Gtk.Align.CENTER)
        self.lang_btns = {}
        for code in LANGS:
            b = self.button(Gtk.Label(label=code.upper()), lambda _b, c=code: self.set_lang(c))
            b.get_style_context().add_class('lang')
            switch.pack_start(b, False, False, 0)
            self.lang_btns[code] = b
        foot.pack_end(switch, False, False, 0)
        card.pack_start(foot, False, False, 0)

        self.sync()
        GLib.timeout_add_seconds(SYNC_EVERY, self.sync)

    def label(self, cls, text='', **props):
        return label(cls, text, **props)

    def button(self, child, cb):
        b = Gtk.Button(relief=Gtk.ReliefStyle.NONE, can_focus=False)
        b.get_style_context().add_class('nav')
        b.add(child)
        b.connect('clicked', cb)
        return b

    def fill(self):
        t, i = TEXT[self.lang], LANGS.index(self.lang)
        today = dt.date.today()
        self.weekday.set_text(t['weekdays'][today.weekday()])
        self.week.set_text(t['week'].format(today.isocalendar()[1]))
        self.date.set_text(f"{today.day} {t['months_of'][today.month - 1]} {today.year}")
        first = self.shown
        self.month.set_text(f"{t['months'][first.month - 1].capitalize()} {first.year}")
        self.today_label.set_text(t['when'][0])
        self.today_btn.set_visible(first != today.replace(day=1) or self.picked is not None)
        for head, name in zip(self.heads, t['days']):
            head.set_text(name)
        for code, b in self.lang_btns.items():
            ctx = b.get_style_context()
            (ctx.add_class if code == self.lang else ctx.remove_class)('on')
        red = {day: names[i] for y in (first.year - 1, first.year, first.year + 1)
               for day, names in holidays(y).items()}
        start = first - dt.timedelta(days=first.weekday())
        by_day = {}
        if self.cals:
            last = max(start + dt.timedelta(days=41), today + dt.timedelta(days=AHEAD))
            for e in events(self.cals, min(start, today), last):
                by_day.setdefault(e.day, []).append(e)
        day = start
        for n, cell in enumerate(self.cells):
            self.cell_days[n] = day
            ctx = cell.get_style_context()
            for cls in ('sat', 'red', 'other', 'today', 'busy', 'picked'):
                ctx.remove_class(cls)
            cell.set_text(str(day.day))
            evs = by_day.get(day, [])
            tip = ([red[day]] if day in red else []) + [self.describe(e, t) for e in evs[:8]]
            cell.set_tooltip_text('\n'.join(tip) or None)
            if day.month != first.month:
                ctx.add_class('other')
            if day == today:
                ctx.add_class('today')
            elif day in red or day.weekday() == 6:
                ctx.add_class('red')
            elif day.weekday() == 5:
                ctx.add_class('sat')
            if any(not e.cal.routine for e in evs):
                ctx.add_class('busy')
            if day == self.picked:
                ctx.add_class('picked')
            day += dt.timedelta(days=1)
        hday, hnames = next_holiday(today)
        self.hname.set_text(hnames[i])
        self.hwhen.set_text(f"{t['weekdays'][hday.weekday()]}, {hday.day} {t['months_of'][hday.month - 1]}"
                            f' · {in_days((hday - today).days, self.lang)}')
        if self.cals:
            self.fill_agenda(t, today, by_day)
        self.agenda.set_visible(bool(self.cals))

    def describe(self, e, t):
        return f"{e.start:%H:%M}  {e.title}" if e.start else e.title

    def fill_agenda(self, t, today, by_day):
        day = self.picked or today
        self.day_head.set_text(t['agenda'][0] if day == today else
                               f"{t['weekdays'][day.weekday()].capitalize()}, {day.day} "
                               f"{t['months_of'][day.month - 1]}")
        for box in (self.day_list, self.coming_list):
            for child in box.get_children():
                child.destroy()
        items, now = by_day.get(day, []), dt.datetime.now()
        for e in items[:DAY_ROWS]:
            past = day < today or (e.end is not None and e.end <= now)
            when = f'{e.start:%H:%M}' if e.start else t['all_day']
            self.day_list.pack_start(self.row(e, when, None, past), False, False, 0)
        if len(items) > DAY_ROWS:
            more = Event(day, None, None, t['more'].format(len(items) - DAY_ROWS), items[DAY_ROWS].cal)
            self.day_list.pack_start(self.row(more, '', None, False, bar=False), False, False, 0)
        if not items:
            self.day_list.pack_start(self.label('none', t['nothing'], xalign=0), False, False, 0)
        self.day_list.show_all()
        # the next personal events after today; an event spanning days is listed once
        seen, coming = set(), []
        for d in sorted(k for k in by_day if k > today):
            for e in by_day[d]:
                if not e.cal.routine and (e.title, id(e.cal)) not in seen:
                    seen.add((e.title, id(e.cal))); coming.append(e)
        self.coming_head.set_text(t['agenda'][1])
        self.coming_head.set_visible(bool(coming))
        for e in coming[:COMING_ROWS]:
            when = f"{e.day.day} {t['months_short'][e.day.month - 1]}"
            rel = in_days((e.day - today).days, self.lang)
            self.coming_list.pack_start(self.row(e, when, rel, False), False, False, 0)
        self.coming_list.show_all()

    def row(self, e, when, rel, past, bar=True):
        b = Gtk.Button(relief=Gtk.ReliefStyle.NONE, can_focus=False)
        b.get_style_context().add_class('event')
        if past:
            b.get_style_context().add_class('past')
        box = Gtk.Box(spacing=8)
        mark = Gtk.Box(valign=Gtk.Align.CENTER)
        if bar:
            for cls in ('bar', e.cal.color):
                mark.get_style_context().add_class(cls)
        else:
            mark.set_size_request(3, -1)
        w = self.label('etime', when, xalign=0)
        self.when_width.add_widget(w)
        title = self.label('etitle', e.title, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                           max_width_chars=24)
        box.pack_start(mark, False, False, 0); box.pack_start(w, False, False, 0)
        box.pack_start(title, True, True, 0)
        if rel:
            box.pack_end(self.label('erel', rel), False, False, 0)
        b.add(box)
        if e.start:
            b.set_tooltip_text(f'{e.start:%H:%M}–{e.end:%H:%M}  {e.title}')
        elif bar:
            b.set_tooltip_text(e.title)
        b.connect('clicked', lambda *_: self.open_day(e))
        return b

    def open_day(self, e):
        # Google Calendar's day view, in the account that owns the event
        d = e.day
        url = f'https://calendar.google.com/calendar/r/day/{d.year}/{d.month}/{d.day}'
        if e.cal.account:
            url += '?authuser=' + urllib.parse.quote(e.cal.account)
        self.close()
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except GLib.Error:
            pass

    def sync(self):
        # fetch and parse off the main thread; the timeout keeps running while this returns True
        if not self.syncing:
            sources = load_sources()
            if sources:
                self.syncing, self.synced = True, time.monotonic()
                threading.Thread(target=lambda: GLib.idle_add(self.synced_in, read_calendars(sources)),
                                 daemon=True).start()
            elif self.cals:
                self.synced_in([])
        return True

    def synced_in(self, cals):
        self.syncing = False
        self.cals = cals
        self.fill()
        if self.win.get_visible():
            self.refit()
        return False

    def pick(self, n):
        day = self.cell_days[n]
        self.picked = None if day == dt.date.today() else day
        if day.replace(day=1) != self.shown:
            self.shown = day.replace(day=1)
        self.fill()
        self.refit()
        return True

    def set_lang(self, lang):
        self.lang = lang
        save_lang(lang)
        self.fill()
        self.refit()  # Polish and English names differ in width

    def go(self, step):
        if step is None:
            self.shown = dt.date.today().replace(day=1)
            self.picked = None
        else:
            y, m = divmod(self.shown.year * 12 + self.shown.month - 1 + step, 12)
            self.shown = dt.date(y, m + 1, 1)
        self.fill()
        self.refit()

    def refresh(self):
        self.shown = dt.date.today().replace(day=1)
        self.picked = None
        self.fill()
        if time.monotonic() - self.synced > STALE:
            self.sync()

    def on_key(self, key):
        if key in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.go(-1)
        elif key in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.go(1)
        elif key in (Gdk.KEY_Home, Gdk.KEY_t):
            self.go(None)
        elif key in (Gdk.KEY_l, Gdk.KEY_L):
            self.set_lang(LANGS[1 - LANGS.index(self.lang)])
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
