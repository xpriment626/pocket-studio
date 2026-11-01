import json
from pathlib import Path
import tempfile
import unittest

from pocket_studio.core import digest
from pocket_studio.evidence import capture, contact_sheet, inspect_evidence
from pocket_studio.rehearsal_tools import setup
from support import fixture


class RehearsalTools(unittest.TestCase):
    def test_scaffold_is_complete_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            result = setup(root)
            destination = Path(result['directory'])
            for name in ('driver.mjs', 'stage.css', 'scripts/film.mjs', 'scripts/layout.mjs',
                         'scripts/jumps.mjs', 'package-lock.json', 'STAGESHOW-LICENSE', 'fixture/contact-form.mjs'):
                self.assertTrue((destination / name).is_file(), name)
            (destination / 'driver.mjs').write_text('user scene work')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                setup(root)
            self.assertEqual((destination / 'driver.mjs').read_text(), 'user scene work')

    def test_sheet_retains_exact_frame_order_and_hash_validation(self):
        tmp, root, item = fixture()
        with tmp:
            spec = {'cues': [{'name': 'save', 'start': 0, 'end': 2}],
                    'captures': [{'cue': 'save', 'anchor': 'start', 'offset': 0.2},
                                 {'cue': 'save', 'anchor': 'end', 'offset': -0.3}]}
            frames = capture(root, item['id'], item['sha256'], spec)
            before = digest(root / item['path'])
            sheet = contact_sheet(root, frames['id'], 2, 320)
            self.assertEqual(sheet['frames'], frames['frames'])
            self.assertEqual(sheet, inspect_evidence(root, sheet['id']))
            self.assertTrue((root / sheet['sheet']).is_file())
            page = (root / sheet['review']).read_text()
            self.assertIn('decoded 0.', page)
            self.assertEqual(before, digest(root / item['path']))
            (root / frames['frames'][0]['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Evidence bytes changed'):
                inspect_evidence(root, sheet['id'])
            with self.assertRaises(ValueError):
                contact_sheet(root, frames['id'])

    def test_invalid_sheet_settings_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for columns, width in ((0, 320), (9, 320), (2, 100), (True, 320)):
                with self.assertRaises(ValueError):
                    contact_sheet(Path(tmp), 'missing', columns, width)
            self.assertEqual(list(Path(tmp).iterdir()), [])
