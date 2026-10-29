import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from pocket_studio.storage import ERRORS


class Storage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / 'studio'
        self.env = dict(os.environ, POCKET_STUDIO_HOME=str(self.home))

    def call(self, *args, success=True):
        result = subprocess.run([sys.executable, '-m', 'pocket_studio.cli', '--json', *map(str, args)],
                                cwd='/tmp', env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def create(self):
        result = self.call('init', '--title', '../A title is not a path')['data']
        return Path(result['project']), result['registration']['id']

    def receipt(self, **changes):
        current = datetime.now(timezone.utc)
        data = dict(schema_version=1, provider='google_drive', status='ready',
                    account_id='account-1', folder_id='folder-1', host='codex', can_upload=True,
                    observed_at=(current - timedelta(minutes=1)).isoformat(),
                    expires_at=(current + timedelta(hours=1)).isoformat())
        data.update(changes)
        path = self.base / 'receipt.json'
        path.write_text(json.dumps(data))
        return path

    def test_managed_identity_and_explicit_compatibility(self):
        root, pid = self.create()
        self.assertEqual(root, self.home / 'projects' / pid)
        self.assertEqual(self.call('projects', 'open', pid)['data']['path'], str(root))
        self.call('projects', 'register', root)
        self.assertEqual(len(self.call('projects', 'list')['data']['projects']), 1)
        explicit = self.base / 'explicit'
        self.call('init', explicit, '--title', 'Portable')
        self.assertEqual(len(self.call('projects', 'list')['data']['projects']), 1)
        manifest = json.loads((explicit / 'motion.json').read_text())
        del manifest['project_id']
        (explicit / 'motion.json').write_text(json.dumps(manifest))
        first = self.call('projects', 'register', explicit)['data']
        self.assertEqual(first, self.call('projects', 'register', explicit)['data'])
        self.assertTrue((explicit / 'BRIEF.md').exists())
        copy = self.base / 'copy'
        shutil.copytree(explicit, copy)
        self.call('projects', 'register', copy, success=False)
        shutil.rmtree(root)
        self.call('projects', 'open', pid, success=False)
        self.assertFalse(self.call('projects', 'list')['data']['projects'][0]['available'])
        self.call('projects', 'open', '../../etc', success=False)

    def test_present_invalid_project_ids_are_rejected_without_mutation(self):
        root = self.base / 'legacy'
        self.call('init', root, '--title', 'Legacy project')
        data = json.loads((root / 'motion.json').read_text())
        for invalid in (None, '', False, 0, [], {}):
            with self.subTest(project_id=invalid):
                data['project_id'] = invalid
                (root / 'motion.json').write_text(json.dumps(data))
                before = (root / 'motion.json').read_bytes()
                self.call('projects', 'register', root, success=False)
                self.assertEqual(before, (root / 'motion.json').read_bytes())
                self.assertEqual(self.call('projects', 'list')['data']['projects'], [])
        del data['project_id']
        (root / 'motion.json').write_text(json.dumps(data))
        registered = self.call('projects', 'register', root)['data']
        self.assertEqual(json.loads((root / 'motion.json').read_text())['project_id'], registered['id'])
        self.assertEqual(self.call('projects', 'open', registered['id'])['data']['path'], str(root))

    def test_home_override_and_symlink_boundaries(self):
        override = self.base / 'override'
        self.call('init', '--home', override, '--title', 'Other home')
        self.assertFalse(self.home.exists())
        self.assertEqual(len(self.call('projects', '--home', override, 'list')['data']['projects']), 1)
        self.home.mkdir()
        outside = self.base / 'outside'
        outside.mkdir()
        (self.home / 'projects').symlink_to(outside, target_is_directory=True)
        self.call('init', '--title', 'Escape', success=False)
        self.assertEqual(list(outside.iterdir()), [])
        (self.home / 'registry.json').symlink_to(outside / 'index.json')
        self.call('projects', 'list', success=False)
        target = outside / 'brief'
        target.write_text('keep')
        (outside / 'BRIEF.md').symlink_to(target)
        self.call('init', outside, '--title', 'Escape', success=False)
        self.assertEqual(target.read_text(), 'keep')

    def test_destination_idempotence_and_no_upload(self):
        root, _ = self.create()
        self.assertFalse(self.call('destination', 'status', '--project', root)['data']['bound'])
        path = self.receipt()
        first = self.call('destination', 'bind', '--project', root, '--receipt', path)['data']
        self.assertEqual(first, self.call('destination', 'bind', '--project', root, '--receipt', path)['data'])
        status = self.call('destination', 'status', '--project', root)['data']
        self.assertFalse(status['upload_available'])
        self.assertEqual(first['transport'], 'not_implemented')
        self.assertIn('not independently verified', first['evidence'])
        path = self.receipt(folder_id='another-folder')
        second = self.call('destination', 'bind', '--project', root, '--receipt', path)['data']
        self.assertNotEqual(first['id'], second['id'])

    def test_setup_errors_and_no_secret_echo_or_mutation(self):
        root, _ = self.create()
        original = (root / 'motion.json').read_bytes()
        for code in ERRORS:
            with self.subTest(code=code):
                path = self.receipt(status=code)
                result = self.call('destination', 'bind', '--project', root, '--receipt', path, success=False)
                self.assertEqual(result['error']['code'], code)
        for changes in [dict(token='SECRET_SENTINEL'), dict(can_upload=False), dict(can_upload=1),
                        dict(expires_at='2000-01-01T00:00:00Z'), dict(observed_at='bad'),
                        dict(account_id=None), dict(folder_id='../escape'), dict(provider=[]),
                        dict(status=[]), dict(schema_version=True)]:
            path = self.receipt(**changes)
            result = self.call('destination', 'bind', '--project', root, '--receipt', path, success=False)
            self.assertNotIn('SECRET_SENTINEL', json.dumps(result))
        path.write_text('{"token":"SECRET_SENTINEL" invalid}')
        result = self.call('destination', 'bind', '--project', root, '--receipt', path, success=False)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(result))
        self.assertEqual(original, (root / 'motion.json').read_bytes())

    def test_binding_expiry_reported(self):
        root, _ = self.create()
        self.call('destination', 'bind', '--project', root, '--receipt', self.receipt())
        data = json.loads((root / 'motion.json').read_text())
        data['destination']['observation']['expires_at'] = '2000-01-01T00:00:00Z'
        (root / 'motion.json').write_text(json.dumps(data))
        self.assertEqual(self.call('destination', 'status', '--project', root)['data']['status'], 'stale_observation')


if __name__ == '__main__':
    unittest.main()
