"""Deterministic inspection mechanics; no transcription service or quality gate."""
import difflib
import math
import re
import shutil
import subprocess
from pathlib import Path

from .core import artifact, contained, digest, media_duration, new_id, now, probe, project_lock, read, save


def number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def target(root, data, item_id, sha256):
    if not isinstance(sha256, str) or not re.fullmatch('[a-f0-9]{64}', sha256):
        raise ValueError('An exact SHA-256 is required')
    item = next((s for s in data['sources'] if s['id'] == item_id), None)
    if item is None:
        return artifact(root, data, item_id, sha256)
    if item['sha256'] != sha256 or digest(contained(root, item['path'])) != sha256:
        raise ValueError('Source missing or changed; register a new version')
    return item


def validate_cues(spec, duration):
    if not isinstance(spec, dict) or set(spec) != {'cues', 'captures'}:
        raise ValueError('Capture spec requires only cues and captures')
    cues, captures = spec['cues'], spec['captures']
    if not isinstance(cues, list) or not 1 <= len(cues) <= 1000:
        raise ValueError('Supply 1..1000 named cues')
    names, previous_end = {}, 0
    for cue in cues:
        if not isinstance(cue, dict) or set(cue) != {'name', 'start', 'end'}:
            raise ValueError('Each cue requires name, start and end')
        name, start, end = cue['name'], cue['start'], cue['end']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name) or name in names:
            raise ValueError('Cue names must be unique safe identifiers')
        if not number(start) or not number(end) or not previous_end <= start < end <= duration:
            raise ValueError('Cues must be ordered, non-overlapping and within media duration')
        previous_end = end
        names[name] = cue
    if not isinstance(captures, list) or not 1 <= len(captures) <= 100:
        raise ValueError('Supply 1..100 capture targets')
    resolved = []
    for request in captures:
        if not isinstance(request, dict) or set(request) != {'cue', 'anchor', 'offset'}:
            raise ValueError('Each capture requires cue, anchor and offset')
        cue_name, anchor, offset = request['cue'], request['anchor'], request['offset']
        if not isinstance(cue_name, str) or cue_name not in names or anchor not in ('start', 'end') or not number(offset):
            raise ValueError('Capture requires a known cue, start/end anchor and finite offset')
        cue = names[cue_name]
        seconds = cue[anchor] + offset
        if not cue['start'] <= seconds < cue['end']:
            raise ValueError('Capture target must be inside its cue; no automatic clamping')
        resolved.append(dict(request, requested_time=seconds))
    return resolved


def file_record(root, path):
    return {'path': str(path.relative_to(root)), 'sha256': digest(path)}


def commit_evidence(root, data, item, directory, kind, files, details):
    # Recheck original bytes after processing, before attaching any evidence.
    target(root, data, item['id'], item['sha256'])
    record = dict(id=directory.name, kind=kind, created_at=now(),
                  target={'id': item['id'], 'sha256': item['sha256']}, files=files, **details)
    data.setdefault('evidence', []).append(record)
    item.setdefault('evidence_refs', []).append(record['id'])
    save(contained(root, 'motion.json'), data)
    return record


def capture(root, item_id, sha256, spec):
    with project_lock(root):
        data = read(root)
        item = target(root, data, item_id, sha256)
        path = contained(root, item['path'])
        info = probe(path)
        if not any(s['codec_type'] == 'video' for s in info['streams']):
            raise ValueError('Frame capture requires video')
        targets = validate_cues(spec, media_duration(info))
        directory = contained(root, 'evidence/' + new_id('evidence'))
        directory.mkdir(parents=True)
        request_path = directory / 'request.json'
        save(request_path, spec)
        files, frames = [file_record(root, request_path)], []
        for index, request in enumerate(targets):
            output = directory / f'frame-{index:03}.png'
            # Decode from the start to retain an explicit timestamp basis. This
            # deliberately favors correctness over an approximate fast seek.
            filters = (f"setpts=PTS-STARTPTS,select=gte(t\\,{request['requested_time']}),"
                       'showinfo,scale=min(960\\,iw):-2')
            result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'info', '-i', str(path),
                '-map', '0:v:0', '-vf', filters, '-frames:v', '1', '-fps_mode', 'passthrough',
                '-update', '1', str(output)], capture_output=True, text=True)
            pts_values = re.findall(r'\bn:\s*\d+\s+pts:\s*(-?\d+)', result.stderr)
            time_base = re.search(r'config in time_base: (\d+)/(\d+)', result.stderr)
            if result.returncode or not output.is_file() or not pts_values or not time_base:
                raise ValueError('Frame capture failed; unregistered request retained in evidence directory')
            numerator, denominator = map(int, time_base.groups())
            if denominator <= 0 or numerator <= 0:
                raise ValueError('Invalid decoded frame time base')
            pts = int(pts_values[0])
            actual = pts * numerator / denominator
            cue = next(c for c in spec['cues'] if c['name'] == request['cue'])
            if not number(actual) or not request['requested_time'] - 1e-6 <= actual < cue['end']:
                raise ValueError('No decoded frame at or after target inside cue; evidence not attached')
            frame = dict(request, decoded_time=actual, decoded_pts=pts,
                         time_base=[numerator, denominator], **file_record(root, output))
            frames.append(frame)
            files.append(file_record(root, output))
        return commit_evidence(root, data, item, directory, 'frame_capture', files,
            {'frames': frames, 'time_basis': 'seconds from first decoded video frame',
             'inspection_status': 'captured; not visually inspected'})


def words(text):
    return re.findall(r'[^\W_]+', text.casefold())


def compare_words(script, transcript):
    intended, observed = words(script), words(transcript)
    if max(len(intended), len(observed)) > 5000:
        raise ValueError('Text comparison supports at most 5000 words per input')
    changes = []
    for operation, a, b, c, d in difflib.SequenceMatcher(None, intended, observed, autojunk=False).get_opcodes():
        if operation != 'equal':
            changes.append({'operation': operation, 'script_range': [a, b], 'transcript_range': [c, d],
                            'intended': intended[a:b], 'observed': observed[c:d]})
    return {'normalization': 'Unicode casefold; alphanumeric words; punctuation ignored',
            'script_words': len(intended), 'transcript_words': len(observed),
            'words_equal': intended == observed, 'changes': changes,
            'alignment': 'text only; repeated words are not reliable timing anchors'}


def timing_report(segments, transcript, duration):
    if segments is None:
        return {'status': 'not_provided', 'issues': [], 'basis': 'no timing evidence supplied'}
    if not isinstance(segments, list) or len(segments) > 10000:
        raise ValueError('Segments must be a list of at most 10000 entries')
    issues, texts, previous_end = [], [], 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict) or set(segment) != {'start', 'end', 'text'}:
            raise ValueError('Segments require start, end and text')
        start, end, text = segment['start'], segment['end'], segment['text']
        if not number(start) or not number(end) or not isinstance(text, str):
            raise ValueError('Segment times must be finite numbers and text must be a string')
        if not 0 <= start < end <= duration:
            issues.append({'segment': index, 'code': 'outside_duration_or_empty'})
        if start < previous_end:
            issues.append({'segment': index, 'code': 'out_of_order_or_overlap'})
        previous_end = end
        texts.append(text)
    if words(' '.join(texts)) != words(transcript):
        issues.append({'code': 'segment_text_differs_from_transcript'})
    return {'status': 'invalid' if issues else 'valid', 'issues': issues,
            'basis': 'supplied segment bounds and text only; not forced alignment or audibility validation'}


def transcript_compare(root, item_id, sha256, script_path, raw_path, spec):
    required = {'schema_version', 'method', 'tool', 'media_sha256', 'raw_sha256', 'text'}
    if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - {'segments'}:
        raise ValueError('Transcription spec fields do not match the documented schema')
    if type(spec['schema_version']) is not int or spec['schema_version'] != 1 or spec['method'] != 'audio_transcription':
        raise ValueError('Requires an audio_transcription provenance assertion, not an intended script')
    if not isinstance(spec['tool'], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', spec['tool']):
        raise ValueError('Provide the transcription tool identifier, not raw credentials or tool output')
    if not isinstance(spec['text'], str) or len(spec['text']) > 200000:
        raise ValueError('Transcript text must be at most 200000 characters')
    if spec['media_sha256'] != sha256:
        raise ValueError('Transcription provenance belongs to different media bytes')
    script_path, raw_path = Path(script_path).resolve(), Path(raw_path).resolve()
    if script_path.samefile(raw_path):
        raise ValueError('Raw transcription evidence must be a separate artifact from the intended script')
    with project_lock(root):
        data = read(root)
        item = target(root, data, item_id, sha256)
        info = probe(contained(root, item['path']))
        if not any(s['codec_type'] == 'audio' for s in info['streams']):
            raise ValueError('Transcription evidence requires media with an audio stream')
        audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
        try:
            duration = float(audio['duration'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Audio stream duration unavailable; timing bounds cannot be established') from None
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Audio stream requires a positive finite duration')
        if digest(raw_path) != spec['raw_sha256']:
            raise ValueError('Raw transcript hash differs from provenance')
        script_bytes = script_path.read_bytes()
        script = script_bytes.decode('utf-8')
        if len(script) > 200000:
            raise ValueError('Script must be at most 200000 characters')
        comparison = compare_words(script, spec['text'])
        timing = timing_report(spec.get('segments'), spec['text'], duration)
        directory = contained(root, 'evidence/' + new_id('evidence'))
        directory.mkdir(parents=True)
        raw_copy, script_copy, spec_copy = directory / 'raw-transcript.bin', directory / 'script.txt', directory / 'transcription.json'
        shutil.copyfile(raw_path, raw_copy)
        script_copy.write_bytes(script_bytes)
        save(spec_copy, spec)
        if digest(raw_copy) != spec['raw_sha256']:
            raise ValueError('Raw transcript changed during copy; evidence not attached')
        return commit_evidence(root, data, item, directory, 'transcript_comparison',
            [file_record(root, p) for p in (raw_copy, script_copy, spec_copy)],
            {'comparison': comparison, 'timing': timing, 'audio_duration': duration,
             'time_basis': 'seconds from start of first audio stream',
             'provenance': {'method': spec['method'], 'tool': spec['tool'],
                            'raw_sha256': spec['raw_sha256'], 'media_sha256': sha256,
                            'attribution': 'caller asserted extraction and normalization; not independently verified'},
             'inspection_status': 'text and timing mechanics only; no creative acceptance'})


def inspect_evidence(root, evidence_id):
    with project_lock(root):
        data = read(root)
        record = next((e for e in data.get('evidence', []) if e['id'] == evidence_id), None)
        if record is None:
            raise ValueError('Unknown evidence ID')
        target(root, data, record['target']['id'], record['target']['sha256'])
        for entry in record['files']:
            if digest(contained(root, entry['path'])) != entry['sha256']:
                raise ValueError('Evidence bytes changed; repeat inspection on a new evidence record')
        return record
