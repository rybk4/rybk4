import copy
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

    def test_consistent_total_includes_other_and_remaining(self):
        total, rows = wakatime.language_rows(self.data)
        self.assertEqual(wakatime.duration(total), '154h 37m')
        self.assertAlmostEqual(sum(value for _, value in rows), total)
        self.assertEqual(rows[-1], ('Remaining languages', 67740))

    def test_themes_are_valid_svg_and_escape_api_text(self):
        self.data['languages'][0]['name'] = '<script>&"'
        for theme in wakatime.THEMES:
            svg = wakatime.render(self.data, theme)
            root = ET.fromstring(svg)
            self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')
            self.assertNotIn('<script>', svg)
            self.assertIn('&lt;script&gt;', svg)

    def test_zero_activity(self):
        self.data.update(languages=[], total_seconds_including_other_language=0)
        svg = wakatime.render(self.data, 'dark')
        ET.fromstring(svg)
        self.assertIn('No activity recorded', svg)
        self.assertNotIn('nan', svg.lower())

    def test_invalid_durations_are_rejected(self):
        for invalid in (-1, float('nan'), float('inf')):
            data = copy.deepcopy(self.data)
            data['languages'][0]['total_seconds'] = invalid
            with self.assertRaises(ValueError):
                wakatime.render(data, 'light')

    def test_inconsistent_total_is_rejected(self):
        self.data['total_seconds_including_other_language'] = 1
        with self.assertRaises(ValueError):
            wakatime.render(self.data, 'dark')

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
        open_url.side_effect = HTTPError(wakatime.ENDPOINT, 401, 'secret response', {}, None)
        with self.assertRaisesRegex(ValueError, 'HTTP 401') as raised:
            wakatime.fetch_stats()
        self.assertNotIn('legacy-key', str(raised.exception))
        self.assertTrue(open_url.call_args.args[0].get_header('Authorization').startswith('Basic '))
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
