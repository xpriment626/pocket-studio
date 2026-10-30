#!/usr/bin/env python3
"""Install an editable local launcher and Claude Code skill without package login."""
import argparse
from pathlib import Path
import shutil
import sys
import shlex
p=argparse.ArgumentParser(description='Install Pocket Studio for Claude Code, the supported driver.')
p.add_argument('--bin-dir', default=str(Path.home()/'.local/bin'))
p.add_argument('--skills', choices=['none','claude'], default='claude', help='Install the Claude Code skill (default), or only the CLI')
a=p.parse_args()
root=Path(__file__).resolve().parent
bin_dir=Path(a.bin_dir).expanduser(); bin_dir.mkdir(parents=True,exist_ok=True)
launcher=bin_dir/'pocket-studio'
content='#!/bin/sh\n# pocket-studio editable launcher\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(root/'src/pocket_studio/cli.py'))+' "$@"\n'
if launcher.exists() and 'pocket-studio editable launcher' not in launcher.read_text():
    raise SystemExit('Refusing to overwrite unrelated command: '+str(launcher))
if a.skills == 'claude':
    destination=Path.home()/'.claude/skills/pocket-studio'
    source=root/'skills/pocket-studio'
    if destination.exists() and (not (destination/'SKILL.md').exists() or (destination/'SKILL.md').read_text() != (source/'SKILL.md').read_text()):
        raise SystemExit('Existing differing skill; inspect before updating: '+str(destination))
    shutil.copytree(source,destination,dirs_exist_ok=True)
launcher.write_text(content); launcher.chmod(0o755)
print(launcher)
