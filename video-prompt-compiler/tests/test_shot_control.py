import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from shot_control.camera_projection import project
from shot_control.common import read, write, sha, schema_check
from shot_control.control_plan import build, frame
from shot_control.control_lowering import lower, validate_delta
from shot_control.media_review import evaluate


class ShotControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)/'package'
        self.source = ROOT/'examples/v52/cafe.avir.json'
        self.ir = read(self.source)
        self.lens = {'vertical_fov_deg': 50, 'aspect': 16/9, 'basis': 'authored_proxy', 'evidence': 'Synthetic test design'}

    def build(self):
        return build(self.source, self.out, {'schema': 'shot-control-config/0.1',
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

    def test_flash_blocks_video_and_never_submits(self):
        self.build(); plan = read(self.out/'control-plan.json')
        plan['controls'] = [{'id':'C1','requirement_id':'REQ_DURATION','shot_ids':['S1'], 'source_pointers':['/shots/0'],
                             'channel':'clay_video_reference','artifact_ids':['CLAY'],'hardness':'hard','fallback_policy':'block','status':'PLANNED'}]
        write(self.out/'control-plan.json', plan)
        result = lower(self.out, 'agnes-video-2.5-flash', 'reference', self.out/'artifact-manifest.json')
        self.assertIn('C1:UNSUPPORTED_CHANNEL', result['reasons'])
        self.assertIsNone(result['media_fields_draft']); self.assertFalse(result['submitted'])

    def test_review_artifact_rejected(self):
        self.build(); plan = read(self.out/'control-plan.json')
        plan['controls'] = [{'id':'C1','requirement_id':'REQ_DURATION','shot_ids':['S1'], 'source_pointers':['/shots/0'],
                             'channel':'first_frame','artifact_ids':['REVIEW'],'hardness':'hard','fallback_policy':'block','status':'PLANNED'}]
        write(self.out/'control-plan.json', plan)
        manifest = {'schema':'control-artifacts/0.1','submitted':False,'artifacts':[{'id':'REVIEW','path':'review/blocking-001.svg',
                    'sha256':sha(self.out/'review/blocking-001.svg'),'source_sha256':plan['source']['sha256'], 'kind':'image','role':'review','review':None,'binding':None}]}
        write(self.out/'artifact-manifest.json', manifest)
        self.assertIn('C1:REVIEW_ARTIFACT_FORBIDDEN:REVIEW', lower(self.out,'agnes-video-2.5','keyframe',self.out/'artifact-manifest.json')['reasons'])

    def test_edit_delta_overlap_blocks(self):
        delta = {'schema':'edit-delta/0.1','keyframe_id':'K1','source':{'kind':'avir/1.2','path':'source.json','sha256':'0'*64},
                 'base_asset_sha256':'1'*64,'master_anchor_ids':['IDENTITY'],'allow_changes':['/A/head'], 'preserve':['/A/identity'],'acceptance':['Review face']}
        self.assertEqual(validate_delta(delta)['status'], 'STATIC_VALID')
        delta['preserve'] = ['/A']
        with self.assertRaises(ValueError): validate_delta(delta)

    def test_tracking_reports_missing_and_timing(self):
        r = {'schema':'control-media-review/0.1','media_sha256':'0'*64,'reviewer':'test','width':100,'height':100,
             'planned_points':[{'node_id':'A','at_ms':t,'xy':[.5,.5]} for t in (0,100,200)],
             'observed_points':[{'node_id':'A','at_ms':0,'xy':[.6,.5],'visibility':'visible'},
                                {'node_id':'A','at_ms':100,'xy':None,'visibility':'occluded'}],
             'events':[{'id':'stop','planned_ms':100,'observed_ms':150}], 'findings':[]}
        result = evaluate(r)
        self.assertEqual(result['coverage'], 1/3); self.assertEqual(len(result['missing']), 2)
        self.assertEqual(result['event_errors'][0]['error_ms'], 50)
        r['observed_points'][0]['at_ms'] = 50
        with self.assertRaises(ValueError): evaluate(r)

    def test_valid_binding_then_hash_and_mode_failure(self):
        self.build()
        # This synthetic package tests one requirement, not a real generated image.
        ir = read(self.out/'production-specification.json'); ir['contract'] = ir['contract'][:1]
        write(self.out/'production-specification.json', ir)
        plan = read(self.out/'control-plan.json'); plan['source']['sha256'] = sha(self.out/'production-specification.json')
        plan['controls'] = [{'id':'C1','requirement_id':'REQ_DURATION','shot_ids':['S1'], 'source_pointers':['/output'],
                             'channel':'first_frame','artifact_ids':['K1'],'hardness':'hard','fallback_policy':'block','status':'PLANNED'}]
        write(self.out/'control-plan.json', plan)
        def chunk(kind, data):
            return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
        png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',256,256,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+b'\x80'*768)*256))+chunk(b'IEND',b'')
        path = self.out/'synthetic.png'; path.write_bytes(png); digest = sha(path)
        manifest = {'schema':'control-artifacts/0.1','submitted':False,'artifacts':[{'id':'K1','path':'synthetic.png',
                    'sha256':digest,'source_sha256':plan['source']['sha256'],'kind':'image','role':'clean_keyframe',
                    'review':{'sha256':digest,'reviewer':'synthetic fixture','result':'PASS','checks':['Fixture, not real media review']},
                    'binding':{'sha256':digest,'url':'https://example.com/fixture.png','receipt':'synthetic receipt'}}]}
        write(self.out/'artifact-manifest.json', manifest)
        result = lower(self.out,'agnes-video-2.5','keyframe',self.out/'artifact-manifest.json')
        self.assertEqual(result['status'],'BOUND_DRAFT'); self.assertFalse(result['runnable'])
        self.assertFalse(result['probe_passed']); self.assertFalse(result['quality_validated'])
        self.assertEqual(result['media_fields_draft']['first_frame'],'https://example.com/fixture.png')
        self.assertEqual(lower(self.out,'agnes-video-2.5','reference',self.out/'artifact-manifest.json')['status'],'BLOCKED')
        path.write_bytes(png+b'changed')
        self.assertIn('C1:MISSING_OR_CHANGED_FILE:K1',lower(self.out,'agnes-video-2.5','keyframe',self.out/'artifact-manifest.json')['reasons'])

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
