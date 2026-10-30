import argparse
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

VERSION = '0.1.0'


# Keep direct execution of this file compatible with the original CLI.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pocket_studio.core import (now, digest, save, run, probe, media_duration,
    root_at, read, contained, new_id, project_lock, submit_feedback, inspect_project, artifact)


def init(args):
    from pocket_studio.storage import home_at, register
    home = home_at(args.home) if args.directory is None or args.home else None
    pid = new_id('project')
    root = Path(args.directory).resolve() if args.directory else contained(home, 'projects/' + pid)
    if root == home:
        raise ValueError('Project directory must differ from managed home')
    root.mkdir(parents=True, exist_ok=True)
    for filename in ('motion.json', 'BRIEF.md', 'TREATMENTS.md', '.gitignore'):
        if (root / filename).is_symlink():
            raise ValueError('Project initialization refuses symlinked files')
    if (root / 'motion.json').exists():
        raise ValueError('Project already exists; refusing to overwrite')
    save(root / 'motion.json', {'schema_version': 1, 'project_id': pid, 'title': args.title, 'created_at': now(),
         'format': {'width': 1920, 'height': 1080, 'fps': 30}, 'sources': [], 'renders': [], 'cuts': []})
    (root / 'BRIEF.md').write_text('# ' + args.title + '\n\n## Audience and intended effect\n\n## Product facts and source references\n\n## Creative freedom\n\n## Visual and sonic direction\n\n## Human acceptance criteria\n\nSuccess requires human review of motion and sound. Source slides are reference material, not the film timeline.\n')
    (root / 'TREATMENTS.md').write_text('# Treatments\n\nDevelop distinct visual ideas as style frames and short motion studies. Record the concept, source facts, camera, materials, sound and intended viewer understanding.\n')
    (root / '.gitignore').write_text('sources/\nrenders/\ncuts/\nreviews/\n.env\n')
    registration = register(home, root) if home else None
    return {'project': str(root), 'manifest': str(root / 'motion.json'), 'registration': registration}


def add_source(args):
    root = root_at(args.project)
    data = read(root)
    source = Path(args.file).resolve()
    if not source.is_file():
        raise ValueError('Source is not a file')
    source_hash = digest(source)
    existing = next((s for s in data['sources'] if s['sha256'] == source_hash), None)
    if existing:
        return existing
    sid = new_id('source')
    dest = root / 'sources' / sid / source.name
    dest.parent.mkdir(parents=True)
    shutil.copy2(source, dest)
    item = {'id': sid, 'path': str(dest.relative_to(root)), 'original_name': source.name,
            'sha256': source_hash, 'role': args.role, 'note': args.note, 'created_at': now()}
    if source.suffix.lower() == '.pdf':
        item['kind'] = 'pdf'
        if shutil.which('pdftotext'):
            run(['pdftotext', '-layout', str(dest), str(dest.parent / 'text.txt')])
            item['text'] = str((dest.parent / 'text.txt').relative_to(root))
        if shutil.which('pdftoppm'):
            run(['pdftoppm', '-scale-to', '1000', '-jpeg', str(dest), str(dest.parent / 'page')])
            item['pages'] = [str(p.relative_to(root)) for p in sorted(dest.parent.glob('page-*.jpg'))]
    elif source.suffix.lower() in ('.mp4', '.mov', '.webm', '.mkv', '.wav', '.mp3', '.m4a'):
        item['kind'] = 'media'
        item['probe'] = probe(dest)
    else:
        item['kind'] = 'reference'
    data['sources'].append(item)
    save(root / 'motion.json', data)
    return item


def render(args):
    root = root_at(args.project)
    spec = json.loads(Path(args.spec).read_text())
    argv = spec.get('argv')
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError('Render spec requires a nonempty argv array')
    if not any('{output}' in x for x in argv):
        raise ValueError('Render argv must include {output}')
    # Only explicit render executes commands. Imported sources are never executed.
    rid = new_id('render')
    directory = root / 'renders' / rid
    directory.mkdir(parents=True)
    output = directory / 'video.mp4'
    expanded = [x.replace('{project}', str(root)).replace('{output}', str(output)) for x in argv]
    save(directory / 'request.json', spec)
    result = subprocess.run(expanded, cwd=root, capture_output=True, text=True)
    (directory / 'stdout.log').write_text(result.stdout)
    (directory / 'stderr.log').write_text(result.stderr)
    if result.returncode or not output.is_file():
        raise ValueError(f'Render failed; logs preserved at {directory}')
    info = probe(output)
    if not any(s['codec_type'] == 'video' for s in info['streams']):
        raise ValueError('Renderer did not produce video')
    item = {'id': rid, 'path': str(output.relative_to(root)), 'sha256': digest(output),
            'label': spec.get('label', rid), 'duration': media_duration(info), 'created_at': now(),
            'source_refs': spec.get('source_refs', []), 'creative_status': 'unreviewed'}
    data = read(root)
    data['renders'].append(item)
    save(root / 'motion.json', data)
    return item


def assemble(args):
    root = root_at(args.project)
    spec = json.loads(Path(args.spec).read_text())
    data = read(root)
    clips = spec.get('clips', [])
    if not clips:
        raise ValueError('Cut requires at least one clip')
    fmt = data['format']
    w, h, fps = (int(fmt[k]) for k in ('width', 'height', 'fps'))
    if w <= 0 or h <= 0 or w % 2 or h % 2 or not 1 <= fps <= 120:
        raise ValueError('Format requires positive even dimensions and fps 1..120')
    cid = new_id('cut')
    directory = root / 'cuts' / cid
    directory.mkdir(parents=True)
    save(directory / 'request.json', spec)
    normalized = []
    for i, clip in enumerate(clips):
        path = contained(root, clip['path'])
        info = probe(path)
        if not any(s['codec_type'] == 'video' for s in info['streams']):
            raise ValueError('Clips must contain video; reference slides are not auto-animated')
        start = float(clip.get('in', 0))
        available = media_duration(info)
        duration = float(clip.get('duration', available - start))
        if not all(math.isfinite(x) for x in (start, duration)) or start < 0 or duration <= 0 or start + duration > available + .05:
            raise ValueError('Clip trim is outside media duration')
        part = directory / f'part-{i:03}.mp4'
        has_audio = any(s['codec_type'] == 'audio' for s in info['streams'])
        cmd = ['ffmpeg', '-v', 'error', '-y', '-ss', str(start), '-i', str(path)]
        if not has_audio:
            cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        cmd += ['-t', str(duration), '-map', '0:v:0', '-map', '0:a:0' if has_audio else '1:a:0',
                '-vf', f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-ar', '48000', '-ac', '2', str(part)]
        run(cmd)
        normalized.append(part)
    listing = directory / 'concat.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in normalized))
    joined = directory / 'joined.mp4'
    run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '1', '-i', str(listing), '-c', 'copy', str(joined)])
    output = directory / 'video.mp4'
    if spec.get('music'):
        music = contained(root, spec['music']['path'])
        gain = float(spec['music'].get('gain', .2))
        if not math.isfinite(gain) or not 0 <= gain <= 2:
            raise ValueError('Music gain must be between 0 and 2')
        run(['ffmpeg', '-v', 'error', '-y', '-i', str(joined), '-i', str(music), '-filter_complex',
             f'[1:a]volume={gain}[music];[0:a][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89[a]',
             '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart', str(output)])
    else:
        run(['ffmpeg', '-v', 'error', '-y', '-i', str(joined), '-c', 'copy', '-movflags', '+faststart', str(output)])
    item = {'id': cid, 'label': spec.get('label', cid), 'path': str(output.relative_to(root)),
            'sha256': digest(output), 'duration': media_duration(probe(output)), 'created_at': now(), 'creative_status': 'unreviewed'}
    data['cuts'].append(item)
    save(root / 'motion.json', data)
    for p in normalized + [joined]:
        p.unlink()
    return item


def review(args):
    root = root_at(args.project)
    data = read(root)
    directory = root / 'reviews'
    directory.mkdir(exist_ok=True)
    cards = []
    for item in data['renders'] + data['cuts']:
        artifact(root, data, item['id'])
        path = contained(root, item['path'])
        thumb = directory / (item['id'] + '.jpg')
        run(['ffmpeg', '-v', 'error', '-y', '-ss', str(min(item['duration'] / 2, 3)), '-i', str(path), '-frames:v', '1', '-vf', 'scale=640:-1', str(thumb)])
        url = '../' + item['path']
        cards.append(f'<article><h2>{html.escape(item["label"])}</h2><code>{item["id"]}</code><video controls preload="metadata" poster="{thumb.name}" src="{html.escape(url, quote=True)}"></video><p>{html.escape(item["creative_status"])} · SHA-256: <code>{item["sha256"]}</code></p></article>')
    payload = json.dumps([{'id': x['id'], 'sha256': x['sha256']} for x in data['renders'] + data['cuts']]).replace('<', '\\u003c')
    page = '''<!doctype html><meta charset="utf-8"><title>Pocket Studio review</title><link rel="icon" href="data:,"><style>body{background:#111;color:#eee;font:16px system-ui;margin:32px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:24px}video{width:100%;max-height:65vh}article{background:#202020;padding:20px;overflow-wrap:anywhere}textarea{width:95%;height:100px}button,select,input{font:inherit;padding:8px;margin:8px}code{font-size:12px}</style><h1>Motion review</h1><p>Play with sound. Compare versions. Technical validity does not establish creative success.</p><main>''' + ''.join(cards) + '''</main><h2>Human feedback</h2><select id="artifact"></select><select id="decision"><option>revise</option><option>approve</option></select><input id="time" type="number" min="0" step="0.1" value="0" aria-label="Time in seconds"><textarea id="note" placeholder="What works? What needs changing, and at what time?"></textarea><button id="download">Download feedback JSON</button><p>Import the downloaded file with pocket-studio feedback --project PROJECT --file FILE. Feedback applies only to the reviewed artifact hash.</p><script>const items=''' + payload + ''';for(const x of items){let o=document.createElement('option');o.textContent=x.id;artifact.append(o)}document.getElementById('download').onclick=()=>{const x=items.find(x=>x.id===artifact.value);if(!x)return;const b=new Blob([JSON.stringify({...x,decision:decision.value,time:Number(document.getElementById('time').value),note:note.value,author:'human'},null,2)],{type:'application/json'});let a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='motion-feedback.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};</script>'''
    (directory / 'index.html').write_text(page)
    return {'review': str(directory / 'index.html'), 'artifacts': len(cards)}


def feedback(args):
    if args.file:
        if any(getattr(args, k) is not None for k in ('id', 'sha256', 'decision', 'time', 'note', 'note_file', 'request_id')):
            raise ValueError('--file cannot be combined with direct feedback fields')
        entry = json.loads(Path(args.file).read_text())
    else:
        entry = dict(id=args.id, sha256=args.sha256, decision=args.decision,
                     time=args.time if args.time is not None else 0, author='human',
                     note=Path(args.note_file).read_text() if args.note_file else args.note or '',
                     request_id=args.request_id)
    return submit_feedback(root_at(args.project), entry)


def main():
    parser = argparse.ArgumentParser(prog='pocket-studio', description='Production primitives for Claude Code. No additional model login or provider keys required.')
    parser.add_argument('--json', action='store_true', help='Stable JSON output (place before command)')
    parser.add_argument('--version', action='version', version=VERSION)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='Report local tools and supported driver; session connectors require host discovery')
    p = sub.add_parser('init', help='Create a portable film project')
    p.add_argument('directory', nargs='?'); p.add_argument('--title', required=True); p.add_argument('--home')
    p = sub.add_parser('source', help='Copy and inspect reference material without executing it')
    ss = p.add_subparsers(dest='action', required=True)
    p = ss.add_parser('add'); p.add_argument('file'); p.add_argument('--project', required=True)
    p.add_argument('--role', choices=['reference', 'screen', 'recording', 'music', 'voice', 'sfx', 'data'], default='reference')
    p.add_argument('--note', default='')
    p = sub.add_parser('inspect', help='Read project manifest including stable source/artifact IDs'); p.add_argument('--project', required=True)
    for name, description in [('render', 'Execute an explicit renderer argv spec; preserve logs and immutable output'), ('assemble', 'Trim and join authored shots/recordings with optional music')]:
        p = sub.add_parser(name, help=description); p.add_argument('--project', required=True); p.add_argument('--spec', required=True)
    p = sub.add_parser('review', help='Build local playback and feedback page'); p.add_argument('--project', required=True)
    p = sub.add_parser('feedback', help='Import human feedback bound to a specific artifact hash'); p.add_argument('--project', required=True); p.add_argument('--file')
    p.add_argument('--id'); p.add_argument('--sha256'); p.add_argument('--decision', choices=['approve', 'revise'])
    p.add_argument('--time', type=float); p.add_argument('--request-id')
    notes = p.add_mutually_exclusive_group(); notes.add_argument('--note'); notes.add_argument('--note-file')
    p = sub.add_parser('projects', help='List, register or locate projects without moving files')
    p.add_argument('--home')
    ps = p.add_subparsers(dest='action', required=True)
    ps.add_parser('list')
    p = ps.add_parser('register'); p.add_argument('directory')
    p = ps.add_parser('open'); p.add_argument('id')
    p = sub.add_parser('destination', help='Pin host-observed remote destination; no upload or sync')
    ds = p.add_subparsers(dest='action', required=True)
    p = ds.add_parser('bind'); p.add_argument('--project', required=True); p.add_argument('--receipt', required=True)
    p = ds.add_parser('status'); p.add_argument('--project', required=True)
    p = sub.add_parser('evidence', help='Capture exact-version frames and validate retained evidence')
    es = p.add_subparsers(dest='action', required=True)
    p = es.add_parser('capture'); p.add_argument('--project', required=True)
    p.add_argument('--id', required=True); p.add_argument('--sha256', required=True); p.add_argument('--spec', required=True)
    p = es.add_parser('inspect'); p.add_argument('--project', required=True); p.add_argument('--id', required=True)
    p = sub.add_parser('transcript', help='Compare actual-audio transcript evidence; no transcription service')
    ts = p.add_subparsers(dest='action', required=True)
    p = ts.add_parser('compare'); p.add_argument('--project', required=True)
    for flag in ('id', 'sha256', 'script', 'raw', 'spec'):
        p.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'evidence':
            from pocket_studio.evidence import capture, inspect_evidence
            root = root_at(args.project)
            result = (inspect_evidence(root, args.id) if args.action == 'inspect' else
                      capture(root, args.id, args.sha256, json.loads(Path(args.spec).read_text())))
        elif args.command == 'transcript':
            from pocket_studio.evidence import transcript_compare
            result = transcript_compare(root_at(args.project), args.id, args.sha256,
                args.script, args.raw, json.loads(Path(args.spec).read_text()))
        elif args.command == 'projects':
            from pocket_studio.storage import home_at, register, projects
            home = home_at(args.home)
            result = (register(home, args.directory) if args.action == 'register' else
                      projects(home, args.id if args.action == 'open' else None))
        elif args.command == 'destination':
            from pocket_studio.storage import bind_destination, destination_status
            root = root_at(args.project)
            if args.action == 'bind':
                try:
                    receipt = json.loads(Path(args.receipt).read_text())
                except (ValueError, OSError):
                    raise ValueError('Cannot read destination observation JSON') from None
                result = bind_destination(root, receipt)
            else:
                result = destination_status(root)
        elif args.command == 'doctor':
            result = {'version': VERSION, 'mode': 'local', 'supported_driver': 'claude-code', 'auth': 'not_required', 'model_calls': False, 'connector_discovery': 'host_required', 'destination_transport': 'not_implemented',
                      'tools': {x: shutil.which(x) for x in ['ffmpeg', 'ffprobe', 'pdftotext', 'pdftoppm', 'blender', 'node']}}
        elif args.command == 'inspect':
            result = inspect_project(root_at(args.project))
        elif args.command in ('source', 'render', 'assemble'):
            with project_lock(root_at(args.project)):
                result = {'source': add_source, 'render': render, 'assemble': assemble}[args.command](args)
        else:
            result = {'init': init, 'source': add_source, 'render': render, 'assemble': assemble, 'review': review, 'feedback': feedback}[args.command](args)
        print(json.dumps({'ok': True, 'data': result}, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': {'type': type(exc).__name__, 'code': getattr(exc, 'code', 'operation_failed'), 'message': str(exc)}}))
        sys.exit(1)


if __name__ == '__main__':
    main()
