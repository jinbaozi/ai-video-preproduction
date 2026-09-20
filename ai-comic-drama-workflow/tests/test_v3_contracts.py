from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from ai_comic_drama_workflow.schema import collect_issues, load_schema, validate, SchemaValidationError
from ai_comic_drama_workflow.spatial import evaluate_state, world_position, snapshot_prompt, validate_spatial_timeline
from ai_comic_drama_workflow.media_bridge import HostMediaRequired, acquire_candidate, import_candidate
from ai_comic_drama_workflow.storage import ProjectStore
from ai_comic_drama_workflow.utils import sha256_file
from tests.helpers import _scene_space, _timeline_shot


def physical_fixture():
    stub = SimpleNamespace(store=SimpleNamespace(read=lambda path: {'segments': [{'segment_id': 'SEG-001'}]}),
                           state={'decisions': {'spatial_representation': '2.5d-structured-previsualization'}})
    scene = _scene_space(stub)['scenes'][0]
    shot = _timeline_shot({'duration_s': 4, 'index': 1, 'shot_id': 'SHOT-001', 'segment_id': 'SEG-001', 'narrative_purpose': 'handoff'})
    return scene, shot


class ContractsV3Tests(unittest.TestCase):
    def test_prop_track_requires_documented_id_before_commit(self):
        _, shot = physical_fixture()
        from ai_comic_drama_workflow.timing import normalize_timing
        shot = normalize_timing(shot)
        shot['prop_tracks'] = [{'prop_id': 'letter', 'trajectory': []}]
        issues = collect_issues(shot, load_schema('shot-timeline-spec.schema.json'))
        self.assertTrue(any('asset_id' in i.message for i in issues))

    def test_six_shot_director_fixture_evaluates_handoff_in_frames(self):
        from tests.golden_director import director_scene
        from ai_comic_drama_workflow.spatial_qa import audit_shot, audit_handoff
        scene, shots = director_scene()
        self.assertEqual(576, sum(s['timing']['frame_count'] for s in shots))
        for index, shot in enumerate(shots):
            self.assertTrue(audit_shot(scene, shot)['passed'])
            if index:
                self.assertEqual([], audit_handoff(scene, shots[index-1], scene, shot))
        self.assertEqual('CHAR-002', evaluate_state(scene, shots[2], 2)['props'][0]['holder_id'])

    def test_frame_authority_rejects_divergent_seconds(self):
        from ai_comic_drama_workflow.timing import normalize_timing, validate_timing
        _, shot = physical_fixture()
        shot = normalize_timing(shot)
        self.assertEqual(96, shot['timing']['frame_count'])
        validate_timing(shot)
        shot['character_tracks'][0]['trajectory'][1]['time_s'] = 1
        with self.assertRaisesRegex(ValueError, 'conflict'):
            validate_timing(shot)

    def test_proxy_geometry_and_prop_errors_are_reported(self):
        from ai_comic_drama_workflow.spatial_qa import audit_shot
        scene, shot = physical_fixture()
        scene['fixed_elements'] = [{'element_id': 'WALL', 'position': {'x': .5, 'y': -.5, 'z': 1}, 'size_m': {'x': 2, 'y': 2, 'z': 2}}]
        report = audit_shot(scene, shot)
        codes = {issue['code'] for issue in report['errors']}
        self.assertIn('camera-inside-fixed-geometry', codes)
        self.assertIn('missing-prop-interaction-track', codes)
        self.assertEqual(97, report['samples'])

    def test_continuous_handoff_and_explicit_time_jump(self):
        from ai_comic_drama_workflow.spatial_qa import audit_handoff
        scene, previous = physical_fixture()
        shot = deepcopy(previous)
        shot['continuity']['transition'] = {'type': 'continuous'}
        self.assertTrue(audit_handoff(scene, previous, scene, shot))
        shot['continuity']['transition'] = {'type': 'time_jump', 'reason': 'approved later beat', 'approval_ref': 'synthetic-review'}
        self.assertEqual([], audit_handoff(scene, previous, scene, shot))

    def test_standard_draft_checks_and_remote_refs_are_closed(self):
        self.assertTrue(collect_issues(1, {'not': {'const': 1}}))
        self.assertTrue(collect_issues(float('nan'), {'type': 'number'}))
        with self.assertRaises(Exception):
            validate({}, {'$ref': 'https://not-registered.invalid/never-fetch'})

    def test_camera_projection_and_meter_conversion(self):
        scene, shot = physical_fixture()
        first = evaluate_state(scene, shot, 1)
        self.assertAlmostEqual(3, first['characters'][0]['position']['x'])
        shot['camera_track'][0]['position']['x'] = 7
        changed = evaluate_state(scene, shot, 1)
        self.assertNotEqual(first['characters'][0]['screen_position'], changed['characters'][0]['screen_position'])
        self.assertEqual(20, world_position(scene, {'x': 2, 'y': 0, 'z': 0})['x'])
        self.assertEqual(24, first['frame_time']['numerator'])

    def test_offscreen_state_and_parallel_tracks(self):
        scene, shot = physical_fixture()
        shot['character_tracks'][0]['visible_interval'] = {'start_s': 2, 'end_s': 4}
        self.assertEqual([], validate_spatial_timeline(scene, shot))
        frame = evaluate_state(scene, shot, 1)
        self.assertEqual(2, len(frame['characters']))
        self.assertFalse(frame['characters'][0]['visible'])
        self.assertTrue(frame['characters'][1]['visible'])

    def test_illegal_gaze_and_duplicate_time(self):
        scene, shot = physical_fixture()
        shot['character_tracks'][0]['trajectory'][0]['gaze_target_id'] = 'UNKNOWN'
        self.assertEqual('unknown-gaze-target', validate_spatial_timeline(scene, shot)[0]['code'])
        shot['character_tracks'][0]['trajectory'][1]['time_s'] = 0
        with self.assertRaises(ValueError):
            validate_spatial_timeline(scene, shot)

    def test_snapshot_changes_with_expression_and_describes_single_moment(self):
        scene, shot = physical_fixture()
        before = snapshot_prompt(evaluate_state(scene, shot, 1), style={}, reference_bindings=[])
        shot['character_tracks'][0]['emotion_events'][0]['visible_cues'] = ['tears']
        after = snapshot_prompt(evaluate_state(scene, shot, 1), style={}, reference_bindings=[])
        self.assertNotEqual(before, after)
        self.assertIn('只绘制这一瞬间', after)

    def test_host_bridge_requires_actual_file_and_imports_it(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / 'project')
            args = dict(stage_id='asset_generation_or_prompt', key='CHAR-001', prompt='fixture, not native proof',
                        bindings=[], folder='stages/07-美术资产/assets', output_kind='asset')
            with self.assertRaises(HostMediaRequired) as caught:
                acquire_candidate(store, **args)
            job = caught.exception.job
            image = Path(directory) / 'provided.png'
            Image.new('RGB', (48, 48), 'blue').save(image)
            result = {'job_id': job['job_id'], 'input_hash': job['input_hash'], 'output_path': str(image),
                      'sha256': sha256_file(image), 'provider': 'provided', 'call_evidence': {}, 'reference_bindings': []}
            wrong = {**result, 'sha256': '0'*64}
            with self.assertRaises(ValueError):
                import_candidate(store, job, wrong)
            with store.transaction():
                imported = import_candidate(store, job, result)
            image.unlink()
            self.assertEqual(imported, acquire_candidate(store, **args))
            self.assertEqual('pending', imported['human_approval'])


if __name__ == '__main__':
    unittest.main()
