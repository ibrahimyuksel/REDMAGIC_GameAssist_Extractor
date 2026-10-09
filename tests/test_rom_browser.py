#!/usr/bin/env python3
"""Tests on small fake partitions; zero network or ROM download."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rom_browser as browser


class RomBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'rom'
        self.root.mkdir()
        for path, data in [('app/GameAssist15_5/GameAssist15_5.apk', b'APKDATA'),
                           ('lib64/libhunt.so', b'LIBDATA'),
                           ('etc/config.xml', b'<config/>')]:
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        self.output = self.base / 'out'

    def test_catalog_and_html_browser(self):
        with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(self.base / 'summary.md')}):
            browser.browse(self.root, self.output, 'gameassist,hunt')
        entries = json.loads((self.output / 'rom-index.json').read_text())
        self.assertEqual(len(entries), 3)
        with (self.output / 'rom-index.csv').open(encoding='utf-8') as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 3)
        html = (self.output / 'rom-file-browser.html').read_text()
        self.assertIn('GameAssist15_5.apk', html)
        self.assertIn('selected_paths', html)
        summary = (self.base / 'summary.md').read_text()
        self.assertIn('2', summary)
        self.assertNotIn('config.xml', summary)

    def test_selection_exact_and_glob(self):
        browser.extract(self.root, self.output, 'app/GameAssist15_5/GameAssist15_5.apk, *.so')
        self.assertEqual((self.output / 'selected/app/GameAssist15_5/GameAssist15_5.apk').read_bytes(), b'APKDATA')
        self.assertEqual((self.output / 'selected/lib64/libhunt.so').read_bytes(), b'LIBDATA')
        self.assertEqual(len(json.loads((self.output / 'selected-files.json').read_text())), 2)
        self.assertEqual(len((self.output / 'SHA256SUMS.txt').read_text().splitlines()), 2)

    def test_empty_absolute_traversal_missing_rejected(self):
        for bad in ('', '../secret', '/etc/passwd', 'a/../../secret', 'C:\\Windows'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                browser.extract(self.root, self.output, bad)
        with self.assertRaisesRegex(ValueError, 'did not match'):
            browser.extract(self.root, self.output, '*.nope')

    def test_limit_fails_before_any_copy(self):
        with patch.object(browser, 'MAX_BYTES', 3):
            with self.assertRaisesRegex(ValueError, 'exceeds limits'):
                browser.extract(self.root, self.output, '*.apk')
        self.assertFalse((self.output / 'selected').exists())

    def test_symlink_skipped(self):
        outside = self.base / 'secret.txt'
        outside.write_bytes(b'secret')
        (self.root / 'secret.txt').symlink_to(outside)
        paths = [f['path'] for f in browser.inventory(self.root)]
        self.assertNotIn('secret.txt', paths)

    def test_unsafe_filename_escaped_in_html(self):
        special = self.root / 'x<script>.txt'
        special.write_text('a')
        browser.browse(self.root, self.output, 'script')
        html = (self.output / 'rom-file-browser.html').read_text()
        self.assertNotIn('"path": "x<script>.txt"', html)
        self.assertIn('x\\u003cscript\\u003e.txt', html)


if __name__ == '__main__':
    unittest.main()
