import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

import wakatime


class CardsTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(Path(__file__).with_name('initial-stats.json').read_text(encoding='utf-8'))

    def test_both_themes_render_the_same_aggregate_stats(self):
        self.data.update(
            days_including_holidays=30,
            days_minus_holidays=23,
            projects=[{'name': 'Private project'}],
        )
        self.data['languages'][0]['name'] = '<private-language>'
        for theme in wakatime.THEMES:
            with self.subTest(theme=theme):
                svg = wakatime.render(self.data, theme)
                root = ET.fromstring(svg)
                self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')
                self.assertEqual(root.get('viewBox'), '0 0 680 212')
                self.assertIn('Total time 154h 37m. Average 5h 09m per calendar day.', svg)
                self.assertIn('Active on 23 of 30 days.', svg)
                self.assertIn('>23<tspan', svg)
                self.assertNotIn('private-language', svg)
                self.assertNotIn('Private project', svg)
                self.assertNotIn('Markdown', svg)
        self.assertNotEqual(wakatime.render(self.data, 'light'), wakatime.render(self.data, 'dark'))

    def test_legacy_snapshot_displays_unknown_active_days(self):
        svg = wakatime.render(self.data, 'light')
        self.assertIn('Active day count unavailable.', svg)
        self.assertIn('>—<tspan', svg)
        self.assertIn(' / 30</tspan>', svg)

    def test_zero_activity_does_not_require_language_data(self):
        self.data.pop('languages')
        self.data.update(total_seconds_including_other_language=0, days_minus_holidays=0)
        svg = wakatime.render(self.data, 'dark')
        self.assertIn('Total time 0h 00m. Average 0h 00m per calendar day.', svg)
        self.assertIn('Active on 0 of 30 days.', svg)

    def test_both_years_are_displayed_when_period_crosses_new_year(self):
        self.data.update(start='2025-12-10T00:00:00Z', end='2026-01-09T00:00:00Z')
        self.assertEqual(wakatime.period(self.data), '10 Dec 2025 – 9 Jan 2026')

    def test_invalid_aggregate_stats_are_rejected(self):
        for invalid_fields in (
            {'total_seconds_including_other_language': -1},
            {'total_seconds_including_other_language': float('nan')},
            {'days_including_holidays': 0},
            {'days_minus_holidays': 31},
        ):
            with self.subTest(invalid_fields=invalid_fields), self.assertRaises(ValueError):
                wakatime.render({**self.data, **invalid_fields}, 'light')

    @patch.dict('os.environ', {'WAKATIME_TOKEN': 'test-token', 'WAKATIME_API_KEY': ''}, clear=True)
    @patch('wakatime.time.sleep')
    @patch('wakatime.urlopen')
    def test_processing_response_is_retried(self, open_url, sleep):
        def response(status, data):
            stream = io.BytesIO(json.dumps({'data': data}).encode())
            stream.status = status
            return stream
        open_url.side_effect = [response(202, {}), response(200, self.data)]
        self.assertEqual(wakatime.fetch_stats(), self.data)
        self.assertEqual(open_url.call_count, 2)
        sleep.assert_called_once_with(10)
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
        self.assertNotIn('test-token', request.full_url)

    @patch.dict('os.environ', {'WAKATIME_TOKEN': '', 'WAKATIME_API_KEY': 'legacy-key'}, clear=True)
    @patch('wakatime.time.sleep')
    @patch('wakatime.urlopen')
    def test_auth_failure_is_not_retried_or_leaked(self, open_url, sleep):
        for status in (401, 403):
            with self.subTest(status=status):
                open_url.side_effect = HTTPError(wakatime.ENDPOINT, status, 'secret response', {}, None)
                with self.assertRaisesRegex(ValueError, f'HTTP {status}') as raised:
                    wakatime.fetch_stats()
                message = str(raised.exception)
                self.assertIn('WAKATIME_TOKEN', message)
                self.assertIn('read_stats', message)
                self.assertNotIn('legacy-key', message)
                self.assertNotIn('secret response', message)
                self.assertTrue(open_url.call_args.args[0].get_header('Authorization').startswith('Basic '))
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
