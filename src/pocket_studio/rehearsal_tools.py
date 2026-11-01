"""Provision optional, inspected authoring tools; never execute or install them implicitly."""
from pathlib import Path
import shutil

from .core import contained, digest, project_lock, save


def setup(root):
    source = Path(__file__).parent / 'rehearsal'
    with project_lock(root):
        destination = contained(root, 'production/rehearsal')
        if destination.exists():
            raise ValueError('Rehearsal workspace already exists; preserve edits and use it in place')
        destination.mkdir(parents=True)
        files = []
        for path in sorted(source.rglob('*')):
            if not path.is_file() or 'node_modules' in path.parts:
                continue
            output = destination / path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
            files.append({'path': str(output.relative_to(root)), 'sha256': digest(output)})
        save(destination / 'toolkit.json', {'schema_version': 1, 'files': files})
        return {'directory': str(destination), 'files': files,
                'next': 'Read README.md; run npm ci --ignore-scripts in that directory when browser rehearsal is needed.',
                'dependencies_installed': False, 'product_behavior_verified': False}
