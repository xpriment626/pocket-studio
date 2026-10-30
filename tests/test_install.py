"""Exercise installer targets in disposable cloud homes, never the user's setup."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / 'bin'

    def install(self, *args, success=True):
        # Path.home is replaced only in this child; no real host configuration is touched.
        script = """import runpy, sys
from pathlib import Path
from unittest.mock import patch
home, installer, *args = sys.argv[1:]
sys.argv = [installer, *args]
with patch.object(Path, 'home', return_value=Path(home)):
    runpy.run_path(installer, run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-c', script, str(self.home), str(ROOT / 'install.py'),
                                 '--bin-dir', str(self.bin), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_default_claude_skill_and_launcher_idempotence(self):
        legacy = self.home / '.codex/skills/pocket-studio/SKILL.md'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('existing installation must remain untouched')
        self.install()
        target = self.home / '.claude/skills/pocket-studio'
        for source in (ROOT / 'skills/pocket-studio').rglob('*.md'):
            self.assertEqual((target / source.relative_to(ROOT / 'skills/pocket-studio')).read_bytes(), source.read_bytes())
        self.install('--skills', 'claude')
        self.assertEqual(legacy.read_text(), 'existing installation must remain untouched')
        result = subprocess.run([str(self.bin / 'pocket-studio'), '--json', 'doctor'],
                                cwd='/tmp', capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)['data']
        self.assertEqual(data['supported_driver'], 'claude-code')
        self.assertEqual(data['connector_discovery'], 'host_required')
        self.assertFalse(data['model_calls'])

    def test_cli_only_and_unsupported_targets(self):
        for target in ('codex', 'both'):
            self.install('--skills', target, success=False)
            self.assertFalse(self.bin.exists())
        self.install('--skills', 'none')
        self.assertTrue((self.bin / 'pocket-studio').exists())
        self.assertFalse((self.home / '.claude').exists())

    def test_existing_custom_skill_and_command_are_preserved(self):
        self.install()
        target = self.home / '.claude/skills/pocket-studio/SKILL.md'
        target.write_text('custom guidance')
        self.install(success=False)
        self.assertEqual(target.read_text(), 'custom guidance')
        launcher = self.bin / 'pocket-studio'
        launcher.write_text('unrelated command')
        self.install('--skills', 'none', success=False)
        self.assertEqual(launcher.read_text(), 'unrelated command')


if __name__ == '__main__':
    unittest.main()
