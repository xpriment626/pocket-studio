import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pocket_studio.core import digest, read, save
from pocket_studio.evidence import capture, compare_words, inspect_evidence, timing_report, transcript_compare, validate_cues
from support import fixture


class Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root, self.item = fixture()
        self.addCleanup(self.tmp.cleanup)
        self.spec = {'cues': [{'name': 'opening', 'start': 0, 'end': 1},
                              {'name': 'action', 'start': 1, 'end': 2}],
                     'captures': [{'cue': 'action', 'anchor': 'start', 'offset': .13},
                                  {'cue': 'opening', 'anchor': 'end', 'offset': -.5}]}

    def capture(self, spec=None):
        return capture(self.root, self.item['id'], self.item['sha256'], spec or self.spec)

    def transcript(self, **changes):
        script, raw = self.root / 'original.txt', self.root / 'provider.json'
        script.write_text('Click approve then type go go.')
        raw.write_text(json.dumps({'text': 'click approve then type go go'}))
        spec = dict(schema_version=1, method='audio_transcription', tool='synthetic-fixture',
                    media_sha256=self.item['sha256'], raw_sha256=digest(raw),
                    text='Click approve then type go go.',
                    segments=[{'start': 0, 'end': 1, 'text': 'Click approve'},
                              {'start': 1, 'end': 2, 'text': 'then type go go.'}])
        spec.update(changes)
        return script, raw, spec

    def compare(self, **changes):
        script, raw, spec = self.transcript(**changes)
        return transcript_compare(self.root, self.item['id'], self.item['sha256'], script, raw, spec)

    def test_capture_binds_decoded_frames_and_preserves_status(self):
        result = self.capture()
        self.assertEqual(result['target'], {'id': self.item['id'], 'sha256': self.item['sha256']})
        self.assertEqual(len(result['frames']), 2)
        self.assertAlmostEqual(result['frames'][0]['decoded_time'], 28 / 24, places=4)
        self.assertEqual(result['frames'][0]['requested_time'], 1.13)
        self.assertEqual(inspect_evidence(self.root, result['id']), result)
        data = read(self.root)
        self.assertEqual(data['renders'][0]['creative_status'], 'unreviewed')
        self.assertEqual(data['renders'][0]['evidence_refs'], [result['id']])
        second = self.capture()
        self.assertNotEqual(second['id'], result['id'])
        self.assertEqual(inspect_evidence(self.root, result['id']), result)
        frame = self.root / result['frames'][0]['path']
        frame.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Evidence bytes changed'):
            inspect_evidence(self.root, result['id'])

    def test_capture_stale_hash_and_symlink_boundaries(self):
        with self.assertRaises(ValueError):
            capture(self.root, self.item['id'], '0' * 64, self.spec)
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'evidence').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.capture()
            self.assertEqual(list(Path(outside).iterdir()), [])
        self.assertNotIn('evidence', read(self.root))

    def test_invalid_cues_and_targets(self):
        cases = [dict(cues=[], captures=[]),
                 dict(cues=[{'name': '../escape', 'start': 0, 'end': 1}], captures=self.spec['captures']),
                 dict(cues=[{'name': 'same', 'start': 0, 'end': 1}, {'name': 'same', 'start': 1, 'end': 2}], captures=[]),
                 dict(cues=[{'name': 'a', 'start': 1, 'end': 2}, {'name': 'b', 'start': 0, 'end': 1}], captures=[]),
                 dict(cues=[{'name': 'a', 'start': 0, 'end': float('nan')}], captures=[])]
        for field, value in [('offset', True), ('offset', float('inf')), ('offset', -10),
                             ('cue', 'missing'), ('anchor', 'middle'), ('offset', 1)]:
            request = dict(self.spec['captures'][0]); request[field] = value
            cases.append(dict(cues=self.spec['cues'], captures=[request]))
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_cues(spec, 2)
        self.assertNotIn('evidence', read(self.root))

    def test_words_and_timing_are_independent(self):
        result = self.compare(segments=[{'start': 0, 'end': 4, 'text': 'Click approve then type go go.'}])
        self.assertTrue(result['comparison']['words_equal'])
        self.assertEqual(result['timing']['status'], 'invalid')
        self.assertEqual(result['timing']['issues'][0]['code'], 'outside_duration_or_empty')
        self.assertEqual(inspect_evidence(self.root, result['id']), result)
        self.assertIn('caller asserted', result['provenance']['attribution'])
        result = self.compare(text='Click then type go.', segments=None)
        self.assertFalse(result['comparison']['words_equal'])
        self.assertEqual(result['timing']['status'], 'not_provided')
        self.assertNotIn('score', result['comparison'])
        self.assertEqual(read(self.root)['renders'][0]['creative_status'], 'unreviewed')

    def test_raw_provenance_and_original_audio_required(self):
        script, raw, spec = self.transcript()
        for changes in ({'method': 'intended_script'}, {'media_sha256': '0' * 64},
                        {'raw_sha256': '0' * 64}, {'token': 'not-allowed'},
                        {'segments': [{'start': True, 'end': 1, 'text': 'a'}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                transcript_compare(self.root, self.item['id'], self.item['sha256'], script, raw, dict(spec, **changes))
        with self.assertRaisesRegex(ValueError, 'separate artifact'):
            transcript_compare(self.root, self.item['id'], self.item['sha256'], script, script, spec)
        with patch('pocket_studio.evidence.probe', return_value={'streams': [{'codec_type': 'video'}]}):
            with self.assertRaisesRegex(ValueError, 'audio stream'):
                transcript_compare(self.root, self.item['id'], self.item['sha256'], script, raw, spec)
        self.assertNotIn('evidence', read(self.root))
        result = self.compare()
        (self.root / self.item['path']).write_bytes(b'changed original')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            inspect_evidence(self.root, result['id'])

    def test_source_audio_and_cli_evidence_inspection(self):
        data = read(self.root)
        item = dict(self.item, id='source-voice', role='voice')
        data['sources'].append(item)
        save(self.root / 'motion.json', data)
        script, raw, spec = self.transcript()
        result = transcript_compare(self.root, item['id'], item['sha256'], script, raw, spec)
        cli = subprocess.run([sys.executable, '-m', 'pocket_studio.cli', 'evidence', 'inspect',
                              '--project', str(self.root), '--id', result['id']],
                             text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(cli.stdout)['data'], result)
        self.assertEqual(read(self.root)['sources'][0]['evidence_refs'], [result['id']])

    def test_audio_bounds_are_independent_of_video_duration(self):
        info = {'streams': [{'codec_type': 'video', 'duration': '2'},
                            {'codec_type': 'audio', 'duration': '1'}],
                'format': {'duration': '2'}}
        with patch('pocket_studio.evidence.probe', return_value=info):
            result = self.compare()
        self.assertEqual(result['audio_duration'], 1)
        self.assertTrue(result['comparison']['words_equal'])
        self.assertEqual(result['timing']['status'], 'invalid')
        del info['streams'][1]['duration']
        with patch('pocket_studio.evidence.probe', return_value=info):
            with self.assertRaisesRegex(ValueError, 'duration unavailable'):
                self.compare()

    def test_script_bytes_retained_and_hardlink_rejected(self):
        script, raw, spec = self.transcript()
        script.write_bytes(b'Click approve\r\nthen type go go.\r\n')
        result = transcript_compare(self.root, self.item['id'], self.item['sha256'], script, raw, spec)
        saved = next(f for f in result['files'] if f['path'].endswith('/script.txt'))
        self.assertEqual((self.root / saved['path']).read_bytes(), script.read_bytes())
        link = self.root / 'script-hardlink'
        link.hardlink_to(script)
        with self.assertRaisesRegex(ValueError, 'separate artifact'):
            transcript_compare(self.root, self.item['id'], self.item['sha256'], script, link, spec)
        with self.assertRaisesRegex(ValueError, '5000 words'):
            compare_words('go ' * 5001, 'go')

    def test_repeated_words_do_not_infer_timing(self):
        comparison = compare_words('go go then stop', 'go then go stop')
        self.assertFalse(comparison['words_equal'])
        self.assertTrue(compare_words('Hello, WORLD!', 'hello world')['words_equal'])
        report = timing_report([{'start': 1, 'end': 1.5, 'text': 'go'},
                                {'start': .5, 'end': 1.2, 'text': 'go'}], 'go go', 2)
        self.assertEqual(report['status'], 'invalid')
        self.assertIn('out_of_order_or_overlap', [i['code'] for i in report['issues']])


if __name__ == '__main__':
    unittest.main()
