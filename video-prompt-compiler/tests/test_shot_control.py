import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import struct
import zlib
import subprocess
import wave
import math
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from shot_control.camera_projection import project
from shot_control.common import read, write, sha, schema_check, digest
from shot_control.control_plan import build, frame
from shot_control.control_lowering import lower as raw_lower, validate_delta

def lower(package, target, mode, manifest):
    return raw_lower(package, target, mode, manifest, {"start_ms":4000,"end_ms":8000})
from shot_control.media_review import evaluate
from shot_control.package import verify_package, recipe, same_json_value
from shot_control.keyframes import check_request
from shot_control.render_blocking import svg, review_files


def projection_with_roundoff(*args, **kwargs):
    result = project(*args, **kwargs)
    if result.get('xy') is not None:
        result['xy'][0] = math.nextafter(result['xy'][0], math.inf)
    return result


class ShotControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)/'package'
        self.source = ROOT/'examples/v52/cafe.avir.json'
        self.ir = read(self.source)
        self.lens = {'vertical_fov_deg': 50, 'aspect': 16/9, 'basis': 'authored_proxy', 'evidence': 'Synthetic test design'}

    def build(self):
        return build(self.source, self.out, {'schema': 'shot-control-config/0.2',
                     'lenses': {s['id']: self.lens for s in self.ir['shots']}, 'controls': []})

    def test_projection_axes_and_depth(self):
        center = project([0, 0, 4], [0, 0, 0], [0, 0, 1], 90, 1)
        self.assertEqual(center['xy'], [.5, .5])
        self.assertGreater(project([1, 0, 4], [0, 0, 0], [0, 0, 1], 90, 1)['xy'][0], .5)
        self.assertLess(project([0, 1, 4], [0, 0, 0], [0, 0, 1], 90, 1)['xy'][1], .5)
        self.assertEqual(project([0, 0, -1], [0, 0, 0], [0, 0, 1], 90, 1)['status'], 'BEHIND_CAMERA')
        with self.assertRaises(ValueError): project([0,0,1], [0,0,0], [0,1,0], 90, 1)

    def test_crop_and_roll(self):
        self.assertAlmostEqual(project([1,0,2], [0,0,0], [0,0,1], 90, 1, crop=[.5,0,.5,1])['xy'][0], .5)
        self.assertLess(project([0,1,2], [0,0,0], [0,0,1], 90, 1, 90)['xy'][0], 1)
        with self.assertRaises(ValueError): project([0,0,1], [0,0,0], [0,0,1], 90, 1, crop=[0,0,0,1])

    def test_cut_endpoint_stays_in_own_shot(self):
        a = frame(self.ir, self.ir['shots'][0], 4000, self.lens)
        b = frame(self.ir, self.ir['shots'][1], 4000, self.lens)
        self.assertEqual(a['camera']['position'], [0,1.3,-3])
        self.assertEqual(b['camera']['position'], [.2,1.3,-1.1])
        self.assertTrue(a['state']['spatial_relations'])
        self.assertTrue(all('S1' in r['shot_ids'] for r in a['state']['spatial_relations']))
        self.assertTrue(all('S2' in r['shot_ids'] for r in b['state']['spatial_relations']))

    def test_unknown_intrinsics_remain_unknown(self):
        f = frame(self.ir, self.ir['shots'][0], 0, {})
        self.assertEqual(f['camera']['status'], 'UNDETERMINED')
        self.assertTrue(all(p['projection']['xy'] is None for p in f['points']))

    def test_no_unknown_interpolation(self):
        tr = self.ir['timeline']['motion_tracks'][0]
        tr['keyframes'][0]['transition'] = 'none'
        f = frame(self.ir, self.ir['shots'][0], 500, self.lens)
        self.assertIsNone(next(p for p in f['points'] if p['id'] == tr['node_id'])['position'])

    def test_build_is_derived_and_reproducible(self):
        before = self.source.read_bytes(); self.build()
        self.assertEqual(before, self.source.read_bytes())
        plan = read(self.out/'control-plan.json'); schema_check(plan, 'shot-control')
        self.assertFalse(plan['video_generated'])
        requests = read(self.out/'keyframe-requests.json')
        self.assertTrue(any(r['at_ms'] == 1500 for r in requests))
        self.assertTrue(all(not r['generated'] for r in requests))
        other = Path(self.tmp.name)/'second'; build(self.source, other, read(self.out/'control-config.json'))
        self.assertEqual(read(self.out/'package-manifest.json'), read(other/'package-manifest.json'))
        with self.assertRaises(ValueError): self.build()

    def test_source_tampering_blocks(self):
        self.build(); (self.out/'production-specification.json').write_text('{}')
        with self.assertRaises(ValueError): lower(self.out, 'agnes-video-2.5', 'reference', self.out/'artifact-manifest.json')

    def test_projection_roundoff_preserves_frozen_baseline_and_temporal_recipe(self):
        from shot_control.repair import plan_repairs
        config,c=self.configured();asset=self.artifact(config,c);manifest=self.manifest(asset)
        before=verify_package(self.out);files={p:sha(self.out/p) for p in read(self.out/'package-manifest.json')['files']}
        # Simulate only a host libm rounding difference; validators and actual PNG probing remain real.
        with patch('shot_control.control_plan.project',projection_with_roundoff):
            after=verify_package(self.out)
            self.assertEqual(after['frames'],before['frames'])
            self.assertEqual(digest(after['evaluation']),digest(before['evaluation']))
            result=lower(self.out,'agnes-video-2.5','keyframe',manifest)
            self.assertEqual(result['status'],'BOUND_DRAFT',result['reasons'])
            self.assertEqual(plan_repairs(self.out,self.out,manifest)['status'],'UNCHANGED')
        self.assertEqual(files,{p:sha(self.out/p) for p in files})

    def test_projection_roundoff_does_not_relax_time_position_status_or_material_changes(self):
        self.build();path=self.out/'review/frames.json';frozen=read(path)
        def point(frames):return next(p for p in frames[1]['points'] if p['projection'].get('xy') is not None)
        cases=[lambda f:f[1].update(at_ms=math.nextafter(f[1]['at_ms'],math.inf)),
               lambda f:point(f)['position'].__setitem__(0,math.nextafter(point(f)['position'][0],math.inf)),
               lambda f:point(f)['projection'].update(status='UNDETERMINED'),
               lambda f:point(f)['projection']['xy'].__setitem__(0,point(f)['projection']['xy'][0]+1e-6),
               lambda f:point(f)['projection']['xy'].__setitem__(0,True)]
        for change in cases:
            changed=copy.deepcopy(frozen);change(changed);write(path,changed)
            seal=read(self.out/'package-manifest.json');seal['files']['review/frames.json']=sha(path);write(self.out/'package-manifest.json',seal)
            with self.assertRaisesRegex(ValueError,'Derived data mismatch'):verify_package(self.out)

    def configured(self, channel='first_frame', ids=None):
        c = {'id': 'C1', 'requirement_id': 'REQ_FACE', 'shot_ids': ['S2'],
             'source_pointers': ['/shots/1/camera/shot_size'], 'channel': channel,
             'artifact_ids': ids or ['K1'], 'hardness': 'hard', 'fallback_policy': 'block', 'purpose': 'supplement'}
        config = {'schema': 'shot-control-config/0.2', 'lenses': {s['id']: self.lens for s in self.ir['shots']}, 'controls': [c]}
        build(self.source, self.out, config)
        return config, c

    def artifact(self, config, c, ident='K1', role='clean_keyframe', content=128, url=None):
        def chunk(kind, data):
            return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
        png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',256,256,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+bytes([content])*768)*256))+chunk(b'IEND',b'')
        path = Path(self.tmp.name)/(ident+'.png'); path.write_bytes(png)
        uses = []
        for sid in c['shot_ids']:
            shot = next(s for s in self.ir['shots'] if s['id'] == sid)
            start, end = shot['start_ms'], shot['end_ms']
            if c['channel'] == 'first_frame': end = start
            if c['channel'] == 'last_frame': start = end
            uses.append({'control_id': c['id'], 'shot_id': sid, 'start_ms': start, 'end_ms': end,
                         'recipe_sha256': recipe(self.ir, config, c, sid, role, start, end)})
        return {'id': ident, 'path': path.name, 'sha256': sha(path), 'source_sha256': sha(self.source),
                'kind': 'image', 'role': role, 'uses': uses,
                'review': {'sha256': sha(path), 'uses_sha256': digest(uses), 'reviewer': 'synthetic fixture', 'result': 'PASS', 'checks': ['Fixture only']},
                'binding': {'sha256': sha(path), 'url': url or 'https://example.com/'+path.name, 'receipt': 'fixture only'}}

    def manifest(self, *assets):
        path = Path(self.tmp.name)/'assets.json'
        write(path, {'schema': 'control-artifacts/0.2', 'artifacts': list(assets), 'submitted': False})
        return path

    def test_review_artifact_rejected(self):
        config, c = self.configured()
        a = self.artifact(config, c, role='review')
        result = lower(self.out, 'agnes-video-2.5', 'keyframe', self.manifest(a))
        self.assertIn('C1:REVIEW_ARTIFACT_FORBIDDEN:K1', result['reasons'])

    def test_duration_cannot_be_discharged_by_first_frame(self):
        config = {'schema': 'shot-control-config/0.2', 'lenses': {}, 'controls': [{
            'id': 'C', 'requirement_id': 'REQ_DURATION', 'shot_ids': ['S1'], 'source_pointers': ['/output'],
            'channel': 'first_frame', 'artifact_ids': ['K'], 'hardness': 'hard', 'fallback_policy': 'block', 'purpose': 'supplement'}]}
        with self.assertRaisesRegex(ValueError, 'parameter'): build(self.source, self.out, config)

    def test_empty_partial_and_resealed_semantic_tamper_rejected(self):
        self.out.mkdir(); write(self.out/'package-manifest.json', {'schema': 'INVALID_SCHEMA', 'files': {}})
        with self.assertRaises(ValueError): verify_package(self.out)
        (self.out/'package-manifest.json').unlink(); self.build()
        manifest = read(self.out/'package-manifest.json'); del manifest['files']['review/index.html']
        write(self.out/'package-manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'file set'): verify_package(self.out)
        manifest['files']['review/index.html'] = sha(self.out/'review/index.html')
        frames = read(self.out/'review/frames.json'); frames[0]['camera']['fov'] = 1
        write(self.out/'review/frames.json', frames); manifest['files']['review/frames.json'] = sha(self.out/'review/frames.json')
        write(self.out/'package-manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'Derived data'): verify_package(self.out)

    def test_wrong_pointer_and_shot_scope_rejected(self):
        config, c = self.configured()
        from shot_control.package import validate_config
        c['source_pointers'] = ['/output']
        with self.assertRaisesRegex(ValueError, 'assertions'): validate_config(self.ir, config)
        c['source_pointers'] = ['/shots/1/camera/shot_size']; c['shot_ids'] = ['S1']
        with self.assertRaisesRegex(ValueError, 'scope'): validate_config(self.ir, config)

    def test_asset_scope_recipe_and_current_use_review(self):
        config, c = self.configured(); a = self.artifact(config, c)
        for field, value, expected in [('shot_id', 'S1', 'ASSET_SHOT_SCOPE'), ('start_ms', 4500, 'ASSET_TIME_SCOPE'), ('recipe_sha256', '0'*64, 'STALE_ASSET_RECIPE')]:
            bad = copy.deepcopy(a); bad['uses'][0][field] = value
            result = lower(self.out, 'agnes-video-2.5', 'keyframe', self.manifest(bad))
            self.assertTrue(any(expected in r for r in result['reasons']), result)
            self.assertEqual(result['status'], 'BLOCKED')
        changed = copy.deepcopy(config); changed['lenses']['S2']['vertical_fov_deg'] = 70
        second = Path(self.tmp.name)/'new-lens'; build(self.source, second, changed)
        result = lower(second, 'agnes-video-2.5', 'keyframe', self.manifest(a))
        self.assertIn('C1:STALE_ASSET_RECIPE:K1', result['reasons'])

    def test_url_alias_conflict_and_shared_content_index(self):
        config, c = self.configured('image_reference', ['A1','A2'])
        a = self.artifact(config, c, 'A1', 'style', 128, 'https://example.com/same.png')
        b = self.artifact(config, c, 'A2', 'style', 255, 'https://example.com/same.png')
        result = lower(self.out, 'agnes-video-2.5', 'reference', self.manifest(a,b))
        self.assertIn('C1:URL_CONTENT_CONFLICT:A2', result['reasons']); self.assertIsNone(result['media_fields_draft'])
        b = self.artifact(config, c, 'A2', 'style', 128, 'https://example.com/alias.png')
        result = lower(self.out, 'agnes-video-2.5', 'reference', self.manifest(a,b))
        self.assertEqual(len(result['attachment_index']), 1)
        self.assertEqual(len(result['media_fields_draft']['images']), 1)
        self.assertEqual(result['attachment_index'][0]['artifact_ids'], ['A1', 'A2'])
        self.assertEqual({b['label'] for b in result['coverage'][0]['bindings']}, {'<Picture 1>'})

    def test_audio_aggregate_allows_two_one_second_files(self):
        config, c = self.configured('audio_reference', ['A1','A2'])
        assets = []
        for i, ident in enumerate(c['artifact_ids']):
            a = self.artifact(config, c, ident, 'audio')
            path = Path(self.tmp.name)/(ident+'.wav')
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                wav.writeframes(struct.pack('<h', i+1)*8000)
            a.update(path=path.name, sha256=sha(path), kind='audio'); a['review']['sha256'] = sha(path); a['binding']['sha256'] = sha(path)
            assets.append(a)
        result = lower(self.out, 'agnes-video-2.5', 'reference', self.manifest(*assets))
        self.assertEqual(result['status'], 'BOUND_DRAFT', result)
        self.assertEqual(lower(self.out, 'agnes-video-2.5', 'reference', self.manifest(assets[0]))['status'], 'BLOCKED')

    def test_keyframe_fabricated_state_and_missing_edit_block(self):
        config, c = self.configured(); request = read(self.out/'keyframe-requests.json')[0]
        request['camera_state'] = {}; request['subject_state'] = {'status': 'EXPLICIT'}
        with self.assertRaisesRegex(ValueError, 'frozen'): check_request(request, self.out, self.manifest())
        request = read(self.out/'keyframe-requests.json')[0]; request.update(generation_mode='edit', master_anchors=['MISSING'])
        result = check_request(request, self.out, self.manifest())
        self.assertIn('EDIT_BASE_AND_DELTA_REQUIRED', result['reasons']); self.assertIn('MISSING_ANCHOR:MISSING', result['reasons'])

    def test_portrait_camera_canvas_preserves_aspect(self):
        f = frame(self.ir, self.ir['shots'][0], 0, {**self.lens, 'aspect': 9/16})
        self.assertIn('viewBox="0 0 202.5 360"', svg(f, 'camera', 10))

    def test_cafe_labels_do_not_overlap_or_move_points(self):
        import xml.etree.ElementTree as ET
        f = frame(self.ir, self.ir['shots'][0], 0, self.lens)
        for view in ('top', 'side', 'camera'):
            for aspect in (16/9, 9/16):
                f['camera']['output_aspect'] = aspect
                old = ET.fromstring(svg(f, view, 3.45, label_layout=1))
                new = ET.fromstring(svg(f, view, 3.45))
                ns = {'s': 'http://www.w3.org/2000/svg'}
                self.assertEqual([p.attrib for p in old.findall('s:circle', ns)],
                                 [p.attrib for p in new.findall('s:circle', ns)])
                labels = new.findall('s:text', ns)
                self.assertEqual(len(labels), len(old.findall('s:text', ns)))
                boxes = [(float(t.attrib['x']), float(t.attrib['y'])-14,
                          float(t.attrib['x'])+float(t.attrib['textLength']), float(t.attrib['y'])+3)
                         for t in labels]
                circles = new.findall('s:circle', ns)
                for i, (a, b, c, d) in enumerate(boxes):
                    self.assertGreaterEqual(a, 0); self.assertGreaterEqual(b, 0)
                    self.assertLessEqual(c, float(new.attrib['viewBox'].split()[2]))
                    self.assertLessEqual(d, 360)
                    for circle in circles:
                        x, y = float(circle.attrib['cx']), float(circle.attrib['cy'])
                        self.assertTrue(c <= x-7 or x+7 <= a or d <= y-7 or y+7 <= b)
                    for x, y, z, w in boxes[i+1:]:
                        self.assertTrue(c <= x or z <= a or d <= y or w <= b)

    def test_legacy_review_layout_still_verifies_without_baseline_changes(self):
        self.build(); bundle = verify_package(self.out)
        baseline = digest(bundle['evaluation'])
        manifest = read(self.out/'package-manifest.json')
        for name, content in review_files(bundle['frames'], label_layout=1).items():
            (self.out/name).write_text(content)
            manifest['files'][name] = sha(self.out/name)
        write(self.out/'package-manifest.json', manifest)
        self.assertEqual(digest(verify_package(self.out)['evaluation']), baseline)
        html = self.out/'review/index.html'
        html.write_text(html.read_text().replace('<html lang="zh">', '<html lang="zh" data-label-layout="2">'))
        manifest['files']['review/index.html'] = sha(html); write(self.out/'package-manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'Derived review mismatch'):
            verify_package(self.out)

    def test_resealed_boolean_cannot_replace_derived_number(self):
        self.build()
        for name, change in (
                ('review/frames.json', lambda v: v[0].update(at_ms=False)),
                ('review/frames.json', lambda v: v[0]['points'][0]['position'].__setitem__(2, False)),
                ('evaluation-plan.json', lambda v: v['points'][0].update(at_ms=False))):
            with self.subTest(name=name):
                path = self.out/name; original = path.read_bytes()
                data = read(path); change(data); write(path, data)
                manifest = read(self.out/'package-manifest.json')
                manifest['files'][name] = sha(path); write(self.out/'package-manifest.json', manifest)
                with self.assertRaisesRegex(ValueError, 'Derived data mismatch'):
                    verify_package(self.out)
                path.write_bytes(original)
                manifest['files'][name] = sha(path); write(self.out/'package-manifest.json', manifest)
        self.assertTrue(same_json_value({'value':[0,1.0,True]}, {'value':[0.0,1,True]}))
        self.assertFalse(same_json_value({'value':[0,1]}, {'value':[False,True]}))

    def test_flash_rejects_conditioned_video(self):
        self.configured('clay_video_reference')
        result = lower(self.out, 'agnes-video-2.5-flash', 'reference', self.manifest())
        self.assertIn('C1:UNSUPPORTED_CHANNEL', result['reasons'])
        self.assertIsNone(result['media_fields_draft'])

    def test_master_recipe_ignores_unrelated_motion_change(self):
        config, c = self.configured('image_reference')
        before = recipe(self.ir, config, c, 'S2', 'identity', 4000, 8000)
        self.ir['timeline']['motion_tracks'][0]['keyframes'][0]['value'] = {'changed': True}
        self.assertEqual(recipe(self.ir, config, c, 'S2', 'identity', 4000, 8000), before)

    def test_edit_delta_overlap_blocks(self):
        delta = {'schema':'edit-delta/0.1','keyframe_id':'K1','source':{'kind':'avir/1.2','path':'source.json','sha256':'0'*64},
                 'base_asset_sha256':'1'*64,'master_anchor_ids':['IDENTITY'],'allow_changes':['/A/head'], 'preserve':['/A/identity'],'acceptance':['Review face']}
        self.assertEqual(validate_delta(delta)['status'], 'STATIC_VALID')
        delta['preserve'] = ['/A']
        with self.assertRaises(ValueError): validate_delta(delta)

    def test_frozen_tracking_and_actual_video(self):
        self.build(); baseline = verify_package(self.out)['evaluation']
        path = Path(self.tmp.name)/'observed.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=320x180:r=24:d=12','-c:v','libx264','-pix_fmt','yuv420p',str(path)], check=True)
        planned = next(p for p in baseline['points'] if p['status'] == 'IN_FRAME')
        point = {k: planned[k] for k in ('shot_id','node_id','at_ms','xy')}; point['visibility'] = 'visible'
        r = {'schema': 'control-media-review/0.2', 'media_sha256': sha(path), 'reviewer': 'fixture',
             'evaluation_plan_sha256': digest(baseline), 'observed_points': [point], 'events': [], 'findings': []}
        result = evaluate(r, self.out, path)
        self.assertEqual(result['coverage'], 1/len(baseline['points']))
        self.assertEqual(result['samples'][0]['error'], 0)
        self.assertEqual(len(result['event_errors']), len(baseline['events']))
        r['planned_points'] = [point]
        with self.assertRaises(ValueError): evaluate(r, self.out, path)
        del r['planned_points']; r['evaluation_plan_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'plan mismatch'): evaluate(r, self.out, path)
        r['evaluation_plan_sha256'] = digest(baseline); r['observed_points'][0]['at_ms'] = 99999
        with self.assertRaises(ValueError): evaluate(r, self.out, path)
        text = Path(self.tmp.name)/'fake.txt'; text.write_text('not a video'); r['media_sha256'] = sha(text)
        with self.assertRaises(ValueError): evaluate(r, self.out, text)

    def test_valid_binding_remains_supplementary_and_hash_failure_blocks(self):
        config, c = self.configured(); a = self.artifact(config, c); manifest = self.manifest(a)
        result = lower(self.out, 'agnes-video-2.5', 'keyframe', manifest)
        self.assertEqual(result['status'], 'BOUND_DRAFT'); self.assertFalse(result['runnable'])
        self.assertTrue(all(x['status'] == 'NOT_COMPILED' for x in result['primary_obligations']))
        self.assertFalse(result['probe_passed']); self.assertFalse(result['quality_validated'])
        self.assertEqual(lower(self.out,'agnes-video-2.5','reference',manifest)['status'],'BLOCKED')
        with (Path(self.tmp.name)/a['path']).open('ab') as stream: stream.write(b'changed')
        self.assertIn('C1:MISSING_OR_CHANGED_FILE:K1',lower(self.out,'agnes-video-2.5','keyframe',manifest)['reasons'])

    def test_event_partition_requires_explicit_states(self):
        import spatial_runtime as spatial
        from shot_control.segment_candidates import propose
        limits = {'min':4000,'max':4000,'allowed':[4000],'step':None}
        good = propose(self.ir, spatial, limits)
        self.assertEqual(good['status'],'DRAFT_REQUIRES_TARGET_CHECK')
        self.assertEqual(len(good['parts']),3)
        self.ir['timeline']['state_samples'] = [s for s in self.ir['timeline']['state_samples'] if s['at_ms'] != 4000]
        self.assertEqual(propose(self.ir,spatial,limits)['status'],'BLOCKED')


if __name__ == '__main__': unittest.main()
