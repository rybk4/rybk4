"""Render a WakaTime activity summary without external assets."""

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
THEMES = {
    # Colors are surface, border, text, secondary text, and accent.
    'light': ('#f5f7fc', '#dce2ee', '#17223b', '#525e77', '#304db4'),
    'dark': ('#141a29', '#2c374e', '#eef2ff', '#aab5cf', '#a9baff'),
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


def period(data):
    start = datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(data['end'].replace('Z', '+00:00'))
    start_date = f'{start.day} {start:%b}'
    if start.year != end.year:
        start_date += f' {start.year}'
    return f'{start_date} – {end.day} {end:%b %Y}'


def render(data, theme):
    total = seconds(data['total_seconds_including_other_language'])
    days = data.get('days_including_holidays', 30)
    active_days = data.get('days_minus_holidays')
    if type(days) is not int or days < 1:
        raise ValueError('Invalid period length in WakaTime response.')
    if active_days is not None and (type(active_days) is not int or not 0 <= active_days <= days):
        raise ValueError('Invalid active day count in WakaTime response.')

    total_hours, total_minutes = divmod(int(total) // 60, 60)
    avg_hours, avg_minutes = divmod(round(total / (days * 60)), 60)
    average = f'{avg_hours}h {avg_minutes:02d}m'
    dates = escape(period(data))
    active_value = '—' if active_days is None else str(active_days)
    active_summary = (
        'Active day count unavailable.' if active_days is None
        else f'Active on {active_days} of {days} days.'
    )
    surface, rule, ink, muted, accent = THEMES[theme]

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="680" height="212" viewBox="0 0 680 212" role="img" aria-labelledby="title description">
  <title id="title">WakaTime coding activity</title>
  <desc id="description">{dates}. Total time {total_hours}h {total_minutes:02d}m. Average {average} per calendar day. {active_summary}</desc>
  <style>
    .surface {{ fill: {surface}; stroke: {rule}; }}
    .rule {{ stroke: {rule}; }}
    .ink {{ fill: {ink}; }}
    .muted {{ fill: {muted}; }}
    .accent {{ fill: {accent}; }}
    .clock {{ fill: none; stroke: {accent}; }}
  </style>

  <rect class="surface" x="0.5" y="0.5" width="679" height="211" rx="16"/>
  <path class="rule" d="M28 65.5H652 M369.5 89V184 M397 136.5H652" fill="none"/>

  <g class="clock" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <circle cx="37" cy="34" r="8.5"/>
    <path d="M37 30v4l2.75 1.75"/>
  </g>

  <g font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif">
    <text class="ink" x="55" y="40" font-size="19" font-weight="600">Coding activity</text>
    <text class="muted" x="652" y="40" font-size="16" text-anchor="end">{dates}</text>
    <text class="muted" x="28" y="105" font-size="17" font-weight="500">Total time · Last {days} days</text>
    <text class="muted" x="397" y="114" font-size="17" font-weight="500">Daily average</text>
    <text class="muted" x="397" y="164" font-size="17" font-weight="500">Active days</text>
  </g>

  <g font-family="'SFMono-Regular', Consolas, 'Liberation Mono', monospace">
    <text class="ink" x="24" y="171" font-size="61" font-weight="700" letter-spacing="-2">{total_hours}<tspan class="accent" font-size="32" dx="2" dy="-1">h</tspan><tspan dx="12" dy="1">{total_minutes:02d}</tspan><tspan class="accent" font-size="32" dx="2" dy="-1">m</tspan></text>
    <text class="ink" x="652" y="115" font-size="24" font-weight="700" text-anchor="end">{average}</text>
    <text class="ink" x="652" y="165" font-size="24" font-weight="700" text-anchor="end">{active_value}<tspan class="muted" font-size="17" font-weight="400"> / {days}</tspan></text>
  </g>
</svg>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Render a local Stats data object without API access.')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8')) if args.input else fetch_stats()
    # Validate and render both before changing either checked-in card.
    cards = {theme: render(data, theme) for theme in THEMES}
    (ROOT / 'assets').mkdir(exist_ok=True)
    for theme, card in cards.items():
        (ROOT / 'assets' / f'wakatime-{theme}.svg').write_text(card, encoding='utf-8', newline='\n')
    print('Updated light and dark WakaTime cards.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as error:
        print(f'WakaTime update failed: {error}', file=sys.stderr)
        sys.exit(1)
