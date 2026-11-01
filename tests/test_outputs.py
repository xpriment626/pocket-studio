from pathlib import Path
import tempfile
import unittest

from pocket_studio.outputs import outputs, output_index
from pocket_studio.storage import register
from support import fixture


class Outputs(unittest.TestCase):
    def test_index_links_originals_and_stale_media_stays_unavailable(self):
        tmp, root, item = fixture()
        with tmp, tempfile.TemporaryDirectory() as home_dir:
            home = Path(home_dir).resolve()
            register(home, root)
            result = outputs(root)
            self.assertTrue(result['outputs'][0]['available'])
            self.assertEqual(result['outputs'][0]['path'], str(root / item['path']))
            index = Path(output_index(home)['index'])
            self.assertIn((root / item['path']).as_uri(), index.read_text())
            (root / item['path']).write_bytes(b'changed media')
            self.assertFalse(outputs(root)['outputs'][0]['available'])
            output_index(home)
            self.assertNotIn((root / item['path']).as_uri(), index.read_text())
            index.write_text('unrelated home page')
            with self.assertRaisesRegex(ValueError, 'unrelated'):
                output_index(home)
