"""Render public language totals only; no dependencies or external image service."""

import argparse
import base64
from datetime import datetime
from functools import lru_cache
from html import escape
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = 'https://api.wakatime.com/api/v1/users/current/stats/last_30_days'
THEMES = {
    'light': ('#1f2328', '#59636e', '#576579'),
    'dark': ('#f0f6fc', '#9da7b3', '#b3c1d5'),
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
            if error.code in (401, 403):
                raise ValueError(
                    f'WakaTime returned HTTP {error.code}. Set the WAKATIME_TOKEN Actions secret '
                    'to a personal OAuth token with read_stats scope '
                    '(https://wakatime.com/developers/#authentication). '
                    'Plugin API keys cannot read statistics.'
                ) from None
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
    # The same denominator includes Other in the total and every percentage.
    if sum(value for _, value in languages) > total + 1:
        raise ValueError('Language durations exceed the total; existing cards were kept.')
    rows = languages[:5]
    remainder = total - sum(value for _, value in rows)
    if remainder > 1:
        rows.append(('Remaining languages', remainder))
    return total, rows


@lru_cache(maxsize=1)
def icon_catalog():
    return json.loads(Path(__file__).with_name('language-icons.json').read_text(encoding='utf-8'))


def find_language_icon(name):
    key = re.sub(r'[\s_.-]+', '', name.casefold())
    catalog = icon_catalog()
    return catalog['icons'].get(catalog['aliases'].get(key))


def language_icon(name, x, y, color, theme='light'):
    """Embed local logos directly, including their gradients and theme-aware ink."""
    icon = find_language_icon(name)
    if icon:
        svg = icon['svg']
        if (icon['dark_adjust'] and theme == 'dark') or (icon['light_adjust'] and theme == 'light'):
            def adjust_paint(match):
                value = match[2][1:]
                if len(value) == 3:
                    value = ''.join(channel * 2 for channel in value)
                if len(value) != 6:
                    return match[0]
                channels = [int(value[index:index + 2], 16) for index in (0, 2, 4)]
                if theme == 'dark':
                    channels = [round(channel * 0.55 + 114) for channel in channels]
                elif min(channels) > 220:
                    channels = [89, 99, 110]
                return match[1] + '#' + ''.join(f'{channel:02x}' for channel in channels) + match[3]
            svg = re.sub(r'((?:fill|stroke|color|stop-color)=")(#[\da-fA-F]+)(")', adjust_paint, svg)
        # Two aliases can share a logo; each placement needs its own gradient IDs.
        for identifier in re.findall(r'\bid="([^"]+)"', svg):
            unique = f'icon-{x}-{y}-{identifier}'
            svg = svg.replace(f'id="{identifier}"', f'id="{unique}"')
            svg = svg.replace(f'url(#{identifier})', f'url(#{unique})')
            svg = svg.replace(f'href="#{identifier}"', f'href="#{unique}"')
        return svg.replace('<svg ', f'<svg x="{x}" y="{y}" width="40" height="40" color="{color}" aria-hidden="true" ', 1)
    if name == 'Other':
        shapes = ''.join(f'<circle cx="{cx}" cy="12" r="2.3" fill="{color}"/>' for cx in (5, 12, 19))
    elif name == 'Remaining languages':
        shapes = ''.join(
            f'<rect x="{cx}" y="{cy}" width="7" height="7" rx="1.7" fill="{color}"/>'
            for cx, cy in ((3, 3), (14, 3), (3, 14), (14, 14))
        )
    else:
        # Some languages have no logo. Give each a readable name-based mark.
        words = re.findall(r'[^\W_]+', name, flags=re.UNICODE)
        initials = ''.join(word[0] for word in words[:3]) if len(words) > 1 else ''.join(words)[:3]
        initials = escape(initials.upper() or '?')
        shapes = (
            f'<text x="12" y="16" font-family="Consolas,monospace" font-size="10" font-weight="700" '
            f'text-anchor="middle" fill="{color}">{initials}</text>'
        )
    return f'<g transform="translate({x} {y}) scale(1.6667)" aria-hidden="true">{shapes}</g>'


def render(data, theme):
    total, rows = language_rows(data)
    dates = period(data)
    text, muted, icon_muted = THEMES[theme]
    grid_rows = max(math.ceil(len(rows) / 2), 1)
    height = 154 + grid_rows * 84
    summary = '; '.join(f'{name}: {duration(value)}' for name, value in rows)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{height}" viewBox="0 0 720 {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">Coding activity · last 30 days</title>',
           f'<desc id="desc">{escape(dates)}. Total {duration(total)}, including Other. {escape(summary) if rows else "No activity recorded."}</desc>',
           f'<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif" fill="{text}">']

    def label(x, y, value, size=14, color=None, weight=400, anchor='start'):
        out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color or text}" text-anchor="{anchor}">{escape(str(value))}</text>')

    label(20, 100, duration(total), 48, weight=600)
    label(21, 124, 'coding time · including Other', 13, muted)
    label(700, 97, dates, 13, muted, anchor='end')
    label(700, 121, 'Updated daily', 11, muted, anchor='end')
    for index, (name, value) in enumerate(rows):
        x = 20 + (index % 2) * 366
        y = 164 + (index // 2) * 84
        color = icon_muted
        percent = value / total * 100 if total else 0
        out.append(language_icon(name, x, y, color, theme))
        display_name = 'More languages' if name == 'Remaining languages' else name
        label(x + 58, y + 15, display_name if len(display_name) <= 19 else display_name[:17] + '…', 18, weight=600)
        label(x + 58, y + 39, duration(value), 14, muted)
        label(x + 314, y + 32, f'{percent:.1f}%', 22, muted, weight=400, anchor='end')
    if not rows:
        label(20, 188, 'No activity recorded in this period.', 16, muted)
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
