"""Derivation tests: no native IR validation, spatial solver or real media claim."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from shot_control import control_plan as cp


def fixture():
    shot = {'id': 'S1', 'scene_id': 'room', 'start_ms': 0, 'end_ms': 4000}
    timeline = {name: [] for name in ('actions', 'performances', 'camera_operations',
                'composition_tracks', 'motion_tracks', 'state_samples', 'audio_events')}
    return {'shots': [shot], 'timeline': timeline, 'bindings': [],
            'scenes': [{'id': 'room', 'lighting': 'motivated window light'}]}, shot


def track(prop='focus', shot_id='S1', start=1000, end=2500):
    return {'id': 'T1', 'shot_ids': [shot_id], 'start_ms': start, 'end_ms': end,
            'property': prop, 'keyframes': [{'at_ms': 1500}]}


class ControlIntentTests(unittest.TestCase):
    def test_motion_boundaries_are_event_samples(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track()]
        self.assertEqual(cp.event_times(ir, shot), [0, 1000, 1500, 2500, 4000])

    def test_color_boundaries_are_event_samples(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track('color', start=800, end=2000)]
        self.assertTrue({800, 2000} <= set(cp.event_times(ir, shot)))

    def test_out_of_shot_state_sample_excluded(self):
        ir, shot = fixture()
        ir['timeline']['state_samples'] = [{'shot_id': 'S1', 'at_ms': 4500}]
        self.assertNotIn(4500, cp.event_times(ir, shot))

    def test_other_shot_tracks_not_borrowed_at_cut(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track(shot_id='S2')]
        self.assertEqual(cp.event_times(ir, shot), [0, 4000])
        self.assertEqual(cp.shot_view(ir, 'S1')['timeline']['motion_tracks'], [])

    def test_cross_shot_tracks_are_clipped_not_retimed(self):
        ir, shot = fixture()
        value = track(start=-100, end=4500)
        value['keyframes'] = [{'at_ms': -100}, {'at_ms': 1000}, {'at_ms': 4500}]
        ir['timeline']['motion_tracks'] = [value]
        self.assertEqual(cp.event_times(ir, shot), [0, 1000, 4000])

    def test_existing_authored_event_boundaries_retained(self):
        ir, shot = fixture()
        for i, name in enumerate(('actions', 'performances', 'camera_operations', 'composition_tracks')):
            ir['timeline'][name] = [{'shot_ids': ['S1'], 'start_ms': 100+i, 'end_ms': 200+i}]
        self.assertTrue(set(range(100, 104)) | set(range(200, 204)) <= set(cp.event_times(ir, shot)))

    def test_focus_review_references_original_track(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track()]
        text = '\n'.join(cp.keyframe_acceptance(ir, shot, 1500, {}))
        self.assertIn('/timeline/motion_tracks/0', text)
        self.assertIn('UNDETERMINED', text)
        self.assertIn('单帧不证明转焦成功', text)
        self.assertIn('切镜、变焦或换脸', text)

    def test_focus_review_not_added_outside_track(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track()]
        self.assertNotIn('转焦', '\n'.join(cp.keyframe_acceptance(ir, shot, 500, {})))

    def test_focus_review_not_borrowed_from_other_shot(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track(shot_id='S2')]
        self.assertNotIn('转焦', '\n'.join(cp.keyframe_acceptance(ir, shot, 1500, {})))

    def test_color_emotion_does_not_rewrite_identity_or_drama(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track('color')]
        ir['timeline']['performances'] = [{'shot_ids': ['S1'], 'start_ms': 0, 'end_ms': 4000}]
        text = '\n'.join(cp.keyframe_acceptance(ir, shot, 1500, {}))
        self.assertIn('不额外增加情绪转折', text)
        self.assertIn('不得用情绪调色改写身份或服装', text)
        self.assertIn('POST_PRODUCTION_NOT_MODEL_PARAMETER', text)

    def test_grading_intent_remains_post_production(self):
        ir, shot = fixture()
        config = {'look_design': {'grading_plan': [{'shot_id': 'S1'}]}}
        text = '\n'.join(cp.keyframe_acceptance(ir, shot, 500, config))
        self.assertIn('control-config.json:/look_design/grading_plan/0', text)
        self.assertIn('不能用首帧代替成片调色验收', text)

    def test_static_palette_does_not_invent_emotion_obligation(self):
        ir, shot = fixture()
        config = {'look_design': {'material_palette': [{'shot_ids': ['S1']}]}}
        text = '\n'.join(cp.keyframe_acceptance(ir, shot, 500, config))
        self.assertIn('静态色板不自动产生情绪目标', text)
        self.assertNotIn('光色与表演依据', text)

    def test_unrelated_palette_does_not_leak(self):
        ir, shot = fixture()
        config = {'look_design': {'material_palette': [{'shot_ids': ['S2']}]}}
        self.assertEqual(len(cp.keyframe_acceptance(ir, shot, 500, config)), 3)

    def test_derivation_preserves_source_and_not_run_status(self):
        ir, shot = fixture()
        ir['timeline']['motion_tracks'] = [track()]
        original = deepcopy(ir)
        def fake_frame(ir, shot, at, lens):
            return {'camera': {'status': 'UNDETERMINED'}, 'state': {}, 'at_ms': at}
        with patch.object(cp, 'frame', fake_frame):
            frames, requests = cp.derive(ir, {'lenses': {}}, {'source': {'fixture': True}})
        self.assertEqual(ir, original)
        self.assertTrue(all(not item['generated'] and item['visual_review'] == 'NOT_RUN' for item in requests))
        self.assertTrue(all(item['camera_state']['status'] == 'UNDETERMINED' for item in requests))
        middle = next(item for item in requests if item['at_ms'] == 1500)
        self.assertIn('单帧不证明转焦成功', '\n'.join(middle['acceptance']))
        self.assertTrue({1000, 2500} <= {item['at_ms'] for item in requests})


if __name__ == '__main__':
    unittest.main(verbosity=2)
