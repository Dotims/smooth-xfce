#!/usr/bin/env python3
"""Text and cover for the panel's now-playing slot, made once per track.

The text part runs while genmon waits (about 0.2 s); the cover is fetched by a detached copy of
this script, so a slow network never stalls the panel.
"""
import html
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE, RADIUS, SS = 34, 8, 4  # px; corners drawn at 4x and scaled down for a smooth edge
TEXT_W = 236  # px of text at most
TITLE_FONT, ARTIST_FONT = 'Inter SemiBold 10', 'Inter 9'
TITLE_FG, ARTIST_FG = '#c0caf5', '#7a83ad'
NOTE_FONT = '/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Regular.ttf'
NBSP = '\u00a0'


def layout():
    """A Pango layout set up like the panel's labels (96 dpi, slight hinting, hinted metrics)."""
    import cairo
    import gi
    gi.require_version('Pango', '1.0')
    gi.require_version('PangoCairo', '1.0')
    from gi.repository import Pango, PangoCairo
    fm = PangoCairo.FontMap.get_default()
    fm.set_resolution(96)
    ctx = fm.create_context()
    fo = cairo.FontOptions()
    fo.set_antialias(cairo.ANTIALIAS_SUBPIXEL)
    fo.set_hint_style(cairo.HINT_STYLE_SLIGHT)
    fo.set_hint_metrics(cairo.HINT_METRICS_ON)
    PangoCairo.context_set_font_options(ctx, fo)
    return Pango, Pango.Layout.new(ctx)


def width(lay, markup):
    lay.set_markup(markup, -1)
    return lay.get_pixel_extents()[1].width


def span(font, fg, text):
    return f"<span font='{font}' foreground='{fg}'>{html.escape(text, quote=False)}</span>"


def fit(lay, font, fg, text):
    """Longest prefix of text (with an ellipsis when cut) that is at most TEXT_W wide."""
    if width(lay, span(font, fg, text)) <= TEXT_W:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if width(lay, span(font, fg, text[:mid].rstrip() + '\u2026')) <= TEXT_W:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + '\u2026'


def text_lines(title, artist):
    """Width of the block and its two lines. genmon centres label lines, so the shorter line gets
    no-break spaces until both are as wide, which reads as left aligned."""
    _, lay = layout()
    t = fit(lay, TITLE_FONT, TITLE_FG, title or 'Spotify')
    a = fit(lay, ARTIST_FONT, ARTIST_FG, artist or '')
    lines = [[TITLE_FONT, TITLE_FG, t], [ARTIST_FONT, ARTIST_FG, a]]
    w = [width(lay, span(*ln)) for ln in lines]
    short, target = (0 if w[0] < w[1] else 1), max(w)
    cur = min(w)
    while True:  # add spaces while each one brings the line closer to the target
        lines[short][2] += NBSP
        nxt = width(lay, span(*lines[short]))
        if abs(nxt - target) >= abs(cur - target):
            lines[short][2] = lines[short][2][:-1]
            break
        cur = nxt
    return target, [span(*ln) for ln in lines]


def rounded(img):
    img = img.convert('RGB').resize((SIZE * SS, SIZE * SS), Image.LANCZOS)
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), RADIUS * SS, fill=255)
    edge = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), RADIUS * SS,
                                           outline=(255, 255, 255, 28), width=SS)
    out = img.convert('RGBA')
    out.putalpha(mask)
    return Image.alpha_composite(out, edge).resize((SIZE, SIZE), Image.LANCZOS)


def placeholder():
    tile = Image.new('RGB', (SIZE, SIZE), (41, 46, 66))
    try:
        ImageDraw.Draw(tile).text((SIZE / 2, SIZE / 2), '\U000f075a', anchor='mm',
                                  font=ImageFont.truetype(NOTE_FONT, 18), fill=(122, 131, 173))
    except OSError:
        pass
    return rounded(tile)


def fetch(url):
    if url.startswith('file://'):
        try:
            return Image.open(urllib.request.url2pathname(url[7:]))
        except OSError:
            return None
    if not url.startswith('https://'):
        return None
    # Spotify serves the same cover at 64 px under another prefix, plenty for a 34 px tile
    small = url.replace('ab67616d0000b273', 'ab67616d00004851')
    for u in dict.fromkeys((small, url)):
        try:
            with urllib.request.urlopen(u, timeout=6) as r:
                return Image.open(r).copy()
        except Exception:
            continue
    return None


def cover(cache, key, url):
    img = fetch(url)
    if img is None:
        return  # the lock stays and the panel script tries again a minute later
    tmp = cache / f'.{key}.png'
    rounded(img).save(tmp)
    tmp.rename(cache / f'{key}.png')
    (cache / f'{key}.lock').unlink(missing_ok=True)
    for ext in ('png', 'txt', 'lock'):  # keep the last 60 tracks
        old = sorted((p for p in cache.glob(f'*.{ext}') if p.name != 'placeholder.png'),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        for p in old[60:]:
            p.unlink(missing_ok=True)


def main():
    cache, key, url, title, artist = Path(sys.argv[1]), *sys.argv[2:6]
    cache.mkdir(parents=True, exist_ok=True)
    if not (cache / 'placeholder.png').exists():
        placeholder().save(cache / 'placeholder.png')
    w, lines = text_lines(title, artist)
    tmp = cache / f'.{key}.txt'
    tmp.write_text(f'{w}\n{lines[0]}\n{lines[1]}\n')
    tmp.rename(cache / f'{key}.txt')
    if not (cache / f'{key}.png').exists():
        subprocess.Popen([sys.executable, __file__, '--cover', str(cache), key, url],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--cover']:
        cover(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
    else:
        main()
