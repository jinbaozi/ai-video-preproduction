"""Regression counterexamples found while completing the adaptive-control review."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from adaptive_control import assess
from test_adaptive_control import native, contact
from shot_control.previs import validate_readback


def moving(track, start=0, end=4000):
    track = copy.deepcopy(track)
    a, b = copy.deepcopy(track['keyframes'][0]), copy.deepcopy(track['keyframes'][0])
    a.update(at_ms=start, transition='linear'); b.update(at_ms=end, transition='none')
    b['value']['value'][0] += 1
    track.update(start_ms=start, end_ms=end, keyframes=[a, b])
    return track


class RoutingCounterexamples(unittest.TestCase):
    def test_camera_held_during_contact_does_not_require_l4(self):
        ir = native(); contact(ir, 2000, 3000)
        camera = moving(ir['timeline']['motion_tracks'][0], 0, 1000)
        camera.update(id='CAMERA_POS', node_id='N_CAMERA', end_ms=4000)
        camera['keyframes'][-1]['transition'] = 'hold'
        last = copy.deepcopy(camera['keyframes'][-1]); last.update(at_ms=4000, transition='none')
        camera['keyframes'].append(last)
        ir['timeline']['motion_tracks'].append(camera)
        self.assertEqual(assess(ir)['shots'][0]['level'], 3)

    def test_interval_contact_relation_with_camera_requires_l4(self):
        ir = native(); ir['timeline']['camera_operations'][0]['operation'] = 'orbit'
        ir['timeline']['spatial_relations'] = [{'id':'TOUCH', 'shot_ids':['S1'],
            'predicate':'touching', 'subject_node_id':'N_A', 'object_node_id':'N_B',
            'scope':{'kind':'interval','start_ms':1000,'end_ms':3000}}]
        self.assertEqual(assess(ir)['shots'][0]['level'], 4)

    def test_two_interacting_movers_require_previs_even_with_locked_camera(self):
        ir = native(); contact(ir)
        ir['timeline']['motion_tracks'] = [moving(t) for t in ir['timeline']['motion_tracks']]
        self.assertEqual(assess(ir)['shots'][0]['level'], 4)

    def test_unrelated_contact_does_not_upgrade_two_separate_movers(self):
        ir = native(); action = contact(ir); action.update(actor_id='OTHER', target_id='PROP')
        ir['timeline']['motion_tracks'] = [moving(t) for t in ir['timeline']['motion_tracks']]
        self.assertEqual(assess(ir)['shots'][0]['level'], 3)


class BlenderActionCompatibility(unittest.TestCase):
    def test_legacy_action_interpolation_is_constant(self):
        from shot_control.blender_keyframes import constant_keys
        point = Obj(interpolation='BEZIER')
        constant_keys(Obj(fcurves=[Obj(keyframe_points=[point])]))
        self.assertEqual(point.interpolation, 'CONSTANT')

    def test_layered_action_does_not_use_legacy_proxy(self):
        from shot_control.blender_keyframes import constant_keys
        point = Obj(interpolation='BEZIER')
        bag = Obj(fcurves=[Obj(keyframe_points=[point])])
        constant_keys(Obj(layers=[Obj(strips=[Obj(channelbags=[bag])])]))
        self.assertEqual(point.interpolation, 'CONSTANT')

    def test_unsupported_action_fails_instead_of_leaving_bezier(self):
        from shot_control.blender_keyframes import constant_keys
        with self.assertRaises(ValueError): constant_keys(Obj())
        with self.assertRaises(ValueError): constant_keys(Obj(layers=[], fcurves=[]))


class ReadbackCounterexamples(unittest.TestCase):
    def setUp(self):
        self.plan = {'geometry':{'resolution':[320,180]},'samples':[{'at_ms':0,
            'objects':[{'id':'A','shape':'box','position':[0,0,0],'dimensions':[1,1,1]}],
            'source_points':[{'id':'A','projection':{'xy':[.5,.5]}}]}]}
        self.data = {'samples':[{'at_ms':0,'resolution':[320,180],
            'objects':{'A':{'center':[0,0,0],'vertices':[[0,0,0]],
            'basis_vectors':[[1,0,0],[0,0,1],[0,1,0]]}}, 'projections':{'A':[.5,.5]}}]}

    def test_finite_synthetic_readback_matches_geometry(self):
        self.assertEqual(validate_readback(self.plan,self.data)['status'], 'PASS')

    def test_nonfinite_center_and_projection_fail_closed(self):
        for field in ('center','projection'):
            for value in (float('nan'),float('inf'),float('-inf')):
                data=copy.deepcopy(self.data)
                vector = data['samples'][0]['objects']['A']['center'] if field=='center' else data['samples'][0]['projections']['A']
                vector[0]=value
                with self.subTest(field=field,value=value):
                    with self.assertRaises(ValueError): validate_readback(self.plan,data)

    def test_boolean_aliases_are_not_coordinates_or_timestamps(self):
        for field in ('time','center'):
            data=copy.deepcopy(self.data)
            if field=='time': data['samples'][0]['at_ms']=False
            else: data['samples'][0]['objects']['A']['center'][0]=False
            with self.subTest(field=field):
                with self.assertRaises(ValueError): validate_readback(self.plan,data)

    def test_missing_basis_cannot_pass_via_empty_zip(self):
        self.data['samples'][0]['objects']['A']['basis_vectors']=[]
        with self.assertRaises(ValueError): validate_readback(self.plan,self.data)
