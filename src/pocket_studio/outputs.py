"""Discover registered encoded outputs without moving media or promoting approval."""
import html
from pathlib import Path

from .core import artifact, contained, read, root_at
from .storage import projects

MARKER = '<!doctype html><!-- pocket-studio output index -->'


def outputs(root):
    data = read(root)
    records = []
    for item in data['renders'] + data['cuts']:
        record = {key: item.get(key) for key in ('id', 'label', 'created_at', 'duration', 'creative_status', 'sha256')}
        try:
            artifact(root, data, item['id'], item['sha256'])
            path = contained(root, item['path'])
            record.update(path=str(path), bytes=path.stat().st_size, available=True)
        except (ValueError, OSError):
            record.update(available=False, issue='Missing, changed or outside project; inspect before relying on this version')
        records.append(record)
    records.sort(key=lambda r: r.get('created_at') or '', reverse=True)
    return {'title': data['title'], 'project': str(root), 'outputs': records,
            'note': 'Registered media only; newest does not mean approved or final.'}


def output_index(home):
    path = contained(home, 'index.html')
    if path.exists() and not path.read_text().startswith(MARKER):
        raise ValueError('Refusing to overwrite an unrelated home index')
    sections = []
    for entry in projects(home)['projects']:
        heading = html.escape(entry['title'])
        if not entry['available']:
            sections.append(f'<section><h2>{heading}</h2><p>Project unavailable</p></section>')
            continue
        rows = []
        for item in outputs(root_at(entry['path']))['outputs']:
            label = html.escape(item.get('label') or item['id'])
            status = html.escape(item.get('creative_status') or 'unreviewed')
            if item['available']:
                link = html.escape(Path(item['path']).as_uri(), quote=True)
                rows.append(f'<li><a href="{link}">{label}</a> · {item.get("duration", 0):.2f}s · {status}<br><code>{html.escape(item["path"])}</code></li>')
            else:
                rows.append(f'<li>{label} · unavailable or changed</li>')
        sections.append(f'<section><h2>{heading}</h2><ul>' + ''.join(rows) + '</ul></section>')
    path.write_text(MARKER + '<meta charset="utf-8"><title>Pocket Studio outputs</title>'
        '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:24px;background:#17191e;color:#eee}a{color:#99cfff}li{margin:20px 0}code{font-size:12px;overflow-wrap:anywhere}</style>'
        '<h1>Pocket Studio outputs</h1><p>Registered videos, newest first within each project. Studies and earlier versions are labeled; newest does not mean approved or final. Source scenes and checkpoint parts are omitted.</p>' + ''.join(sections))
    return {'index': str(path), 'note': 'Local links to original media; no files moved or copied.'}
