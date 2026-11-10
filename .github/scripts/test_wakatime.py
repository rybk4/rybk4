import copy
import io
import json
from pathlib import Path
import re
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

    def test_logos_cover_languages_and_wakatime_aliases(self):
        aliases = {
            'Dart': 'dart', 'C++': 'cplusplus', 'C#': 'csharp', 'Rust': 'rust',
            'Go': 'go', 'Kotlin': 'kotlin', 'Swift': 'swift', 'F#': 'fsharp',
            'Objective-C': 'objectivec', 'Visual Basic .NET': 'visualbasic',
            'Shell': 'bash', 'PowerShell': 'powershell', 'Assembly': 'nasm',
            'Vue.js': 'vuejs', 'TSX': 'react', 'GDScript': 'godot',
            'SCSS': 'sass', 'Nix': 'nixos', 'MATLAB': 'matlab',
        }
        for name, slug in aliases.items():
            with self.subTest(language=name):
                self.assertIs(wakatime.find_language_icon(name), wakatime.icon_catalog()['icons'][slug])
        self.assertIs(wakatime.find_language_icon('c++'), wakatime.find_language_icon('C++'))
        self.assertIsNot(wakatime.find_language_icon('C'), wakatime.find_language_icon('C++'))

    @patch('wakatime.urlopen', side_effect=AssertionError('Rendering must stay offline'))
    def test_every_vendored_logo_is_valid_and_self_contained(self, open_url):
        for name, icon in wakatime.icon_catalog()['icons'].items():
            for theme, color in (('light', '#576579'), ('dark', '#b3c1d5')):
                with self.subTest(language=name, color=color):
                    svg = wakatime.language_icon(name, 20, 164, color, theme)
                    root = ET.fromstring(svg)
                    self.assertEqual(root.tag, 'svg')
                    self.assertEqual(root.get('width'), '40')
                    identifiers = {element.get('id') for element in root.iter() if element.get('id')}
                    for element in root.iter():
                        self.assertNotIn(element.tag, ('script', 'foreignObject', 'image', 'style'))
                        for attr, value in element.attrib.items():
                            self.assertFalse(attr.startswith('on'))
                            if attr.endswith('href'):
                                self.assertTrue(value.startswith('#'))
                                self.assertIn(value[1:], identifiers)
                            for reference in re.findall(r'url\(#([^)]+)\)', value):
                                self.assertIn(reference, identifiers)
                    if icon['monochrome']:
                        self.assertIn('currentColor', svg)
                        self.assertEqual(root.get('color'), color)
        open_url.assert_not_called()

    def test_two_languages_sharing_a_logo_keep_unique_gradient_ids(self):
        slug = next(name for name, icon in wakatime.icon_catalog()['icons'].items() if 'id="' in icon['svg'])
        svg = '<svg>' + wakatime.language_icon(slug, 20, 164, '#576579') + wakatime.language_icon(slug, 386, 164, '#576579') + '</svg>'
        identifiers = [element.get('id') for element in ET.fromstring(svg).iter() if element.get('id')]
        self.assertGreater(len(identifiers), 0)
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_dark_details_adapt_without_changing_logo_geometry(self):
        for name in ('YAML', 'Zsh', 'Shell', 'CoffeeScript'):
            light = ET.fromstring(wakatime.language_icon(name, 20, 164, '#576579', 'light'))
            dark = ET.fromstring(wakatime.language_icon(name, 20, 164, '#b3c1d5', 'dark'))
            self.assertEqual([el.get('d') for el in light.iter('path')], [el.get('d') for el in dark.iter('path')])
            self.assertNotEqual(ET.tostring(light), ET.tostring(dark))

    def test_unknown_language_gets_a_name_based_mark(self):
        icon = wakatime.language_icon('New Language', 20, 164, '#576579')
        ET.fromstring(icon)
        self.assertIn('>NL</text>', icon)
        self.assertNotIn('<path', icon)

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
