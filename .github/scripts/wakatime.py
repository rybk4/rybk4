"""Render public language totals only; no dependencies or external image service."""

import argparse
import base64
from datetime import datetime
from html import escape
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = 'https://api.wakatime.com/api/v1/users/current/stats/last_30_days'
COLORS = {
    'TypeScript': '#3178c6', 'Python': '#d4ad36', 'Markdown': '#7c8caa',
    'JavaScript': '#c2a52c', 'Other': '#88939f', 'Remaining languages': '#88939f',
    'HTML': '#df6547', 'CSS': '#8874d8', 'Rust': '#bd7658', 'Go': '#36a1b5',
}
THEMES = {
    'light': ('#ffffff', '#d1d9e0', '#1f2328', '#59636e', '#e8edf2'),
    'dark': ('#0d1117', '#30363d', '#f0f6fc', '#9da7b3', '#212830'),
}


def fetch_stats():
    token = os.environ.get('WAKATIME_TOKEN', '').strip()
    legacy = os.environ.get('WAKATIME_API_KEY', '').strip()
    if token or legacy.startswith('waka_tok_'):
        authorization = f'Bearer {token or legacy}'
    elif legacy:
        authorization = 'Basic ' + base64.b64encode(f'{legacy}:'.encode()).decode()
    else:
        raise ValueError('Set WAKATIME_TOKEN (recommended) or WAKATIME_API_KEY in Actions secrets.')
    request = Request(ENDPOINT, headers={
        'Authorization': authorization, 'Accept': 'application/json',
        'User-Agent': 'rybk4-profile',
    })
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
                data = payload.get('data')
                if response.status == 200 and isinstance(data, dict) and data.get('is_up_to_date', True):
                    return data
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504):
                raise ValueError(f'WakaTime returned HTTP {error.code}. Check the token and read_stats scope.') from None
        except (URLError, TimeoutError):
            pass
        if attempt < 3:
            time.sleep(10 * (attempt + 1))
    raise ValueError('WakaTime statistics are unavailable or still processing; existing cards were kept.')


def seconds(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError('Invalid duration in WakaTime response.')
    return result


def duration(value):
    minutes = int(value) // 60
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes:02d}m' if hours else f'{minutes}m'


def period(data):
    start = datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(data['end'].replace('Z', '+00:00'))
    return f'{start:%d %b} — {end:%d %b %Y}'


def language_rows(data):
    languages = sorted(
        [(str(item['name']), seconds(item['total_seconds'])) for item in data['languages']],
        key=lambda item: item[1], reverse=True,
    )
    languages = [(name, value) for name, value in languages if value > 0]
    total = seconds(data.get('total_seconds_including_other_language', sum(value for _, value in languages)))
    # The same denominator includes Other in the total, labels and every bar.
    if sum(value for _, value in languages) > total + 1:
        raise ValueError('Language durations exceed the total; existing cards were kept.')
    rows = languages[:5]
    remainder = total - sum(value for _, value in rows)
    if remainder > 1:
        rows.append(('Remaining languages', remainder))
    return total, rows


def render(data, theme):
    total, rows = language_rows(data)
    dates = period(data)
    bg, border, text, muted, track = THEMES[theme]
    height = 236 + max(len(rows), 1) * 49
    summary = '; '.join(f'{name}: {duration(value)}' for name, value in rows)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{height}" viewBox="0 0 720 {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">Coding activity · last 30 days</title>',
           f'<desc id="desc">{escape(dates)}. Total {duration(total)}, including Other. {escape(summary) if rows else "No activity recorded."}</desc>',
           f'<rect x="0.5" y="0.5" width="719" height="{height-1}" rx="12" fill="{bg}" stroke="{border}"/>',
           f'<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif" fill="{text}">']

    def label(x, y, value, size=14, color=None, weight=400, anchor='start'):
        out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color or text}" text-anchor="{anchor}">{escape(str(value))}</text>')

    label(28, 38, 'CODING ACTIVITY', 12, muted, 600)
    label(692, 38, 'LAST 30 DAYS', 11, muted, 600, 'end')
    label(28, 94, duration(total), 38, weight=600)
    label(28, 120, dates, 13, muted)
    label(692, 118, 'including Other', 11, muted, anchor='end')
    out.append('<defs><clipPath id="distribution"><rect x="28" y="144" width="664" height="10" rx="5"/></clipPath></defs>')
    out.append(f'<rect x="28" y="144" width="664" height="10" rx="5" fill="{track}"/>')
    out.append('<g clip-path="url(#distribution)">')
    x = 28.0
    for name, value in rows:
        width = value / total * 664 if total else 0
        out.append(f'<rect x="{x:.3f}" y="144" width="{width:.3f}" height="10" fill="{COLORS.get(name, "#56a99c")}"/>')
        x += width
    out.append('</g>')
    label(28, 188, 'LANGUAGE', 10, muted, 600)
    label(587, 188, 'TIME', 10, muted, 600, 'end')
    label(692, 188, 'SHARE', 10, muted, 600, 'end')
    for index, (name, value) in enumerate(rows):
        y = 218 + index * 49
        color = COLORS.get(name, '#56a99c')
        percent = value / total * 100 if total else 0
        out.append(f'<circle cx="33" cy="{y-5}" r="4" fill="{color}"/>')
        label(46, y, name if len(name) <= 38 else name[:35] + '…', 14, weight=500)
        label(587, y, duration(value), 13, muted, anchor='end')
        label(692, y, f'{percent:.1f}%', 13, anchor='end')
        out.append(f'<rect x="46" y="{y+10}" width="646" height="3" rx="1.5" fill="{track}"/>')
        out.append(f'<rect x="46" y="{y+10}" width="{646*percent/100:.3f}" height="3" rx="1.5" fill="{color}"/>')
    if not rows:
        label(28, 226, 'No activity recorded in this period.', 14, muted)
    label(28, height - 19, 'rybk4 / development', 11, muted)
    label(692, height - 19, 'Updated daily', 11, muted, anchor='end')
    out.append('</g></svg>\n')
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Render a local Stats data object without API access.')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8')) if args.input else fetch_stats()
    # Validate and render both before changing either checked-in card.
    cards = {theme: render(data, theme) for theme in THEMES}
    (ROOT / 'assets').mkdir(exist_ok=True)
    for theme, card in cards.items():
        (ROOT / 'assets' / f'wakatime-{theme}.svg').write_text(card, encoding='utf-8')
    print('Updated light and dark WakaTime cards.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as error:
        print(f'WakaTime update failed: {error}', file=sys.stderr)
        sys.exit(1)
