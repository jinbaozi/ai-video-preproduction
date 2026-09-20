from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'validate_production_contract.py'
SPEC = importlib.util.spec_from_file_location('contract_validator', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EXAMPLE = ROOT / 'examples' / 'production-contract.json'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EXAMPLE.read_text())

    def rejects(self, phrase):
        errors = MODULE.validate(self.data)
        self.assertTrue(any(phrase in error for error in errors), errors)

    def test_example_and_identical_baseline(self):
        self.assertEqual(MODULE.validate(self.data), [])
        self.assertEqual(MODULE.validate(self.data, deepcopy(self.data)), [])

    def test_rejects_incomplete_schema_and_unknown_field(self):
        del self.data['sources']
        self.data['imaginary_runtime'] = True
        self.rejects('required')
        self.rejects('unknown field')

    def test_boolean_is_not_pixel_integer(self):
        self.data['icir']['output']['requested_pixels'] = {'width': True, 'height': 100}
        self.rejects('allowed shape')

    def test_duplicate_entity_id(self):
        self.data['icir']['entities'].append(deepcopy(self.data['icir']['entities'][0]))
        self.rejects('duplicate id')

    def test_dangling_source(self):
        self.data['constraints'][0]['source_ids'] = ['missing-file']
        self.rejects('unknown reference')

    def test_unseen_reference_cannot_be_observed(self):
        self.data['facts'][0]['origin'] = 'observed'
        self.data['sources'][0]['reviewed'] = False
        self.rejects('unreviewed source')

    def test_missing_and_changed_ir_value(self):
        self.data['constraints'][0]['path'] = '/icir/nonexistent'
        self.rejects('unresolved ICIR pointer')
        self.data['constraints'][0]['path'] = '/icir/intent'
        self.rejects('value does not match')

    def test_no_python_negative_index_pointer(self):
        with self.assertRaises(ValueError):
            MODULE.pointer(self.data, '/icir/frames/-1')

    def test_hard_coverage_must_be_actual_prompt_substring(self):
        self.data['compilations'][0]['constraint_clauses']['H1'] = 'not in prompt'
        self.rejects('hard clause missing')

    def test_lock_removal_rejected_against_baseline(self):
        baseline = deepcopy(self.data)
        self.data['constraints'][0]['level'] = 'soft'
        self.assertTrue(any('hard constraint changed' in x for x in MODULE.validate(self.data, baseline)))

    def test_source_rewrite_rejected_against_baseline(self):
        baseline = deepcopy(self.data)
        self.data['sources'][0]['excerpt'] = 'new user intent'
        self.assertTrue(any('hard source changed' in x for x in MODULE.validate(self.data, baseline)))

    def test_soft_camera_revision_allowed(self):
        baseline = deepcopy(self.data)
        camera = self.data['icir']['frames'][0]['camera']
        camera['distance_intent'] = 'slightly farther while preserving framing'
        for fact in self.data['facts']:
            if fact['path'] == '/icir/frames/0/camera':
                fact['value'] = deepcopy(camera)
        self.assertEqual(MODULE.validate(self.data, baseline), [])

    def test_relation_target_must_be_present_in_frame(self):
        self.data['icir']['relations'][1]['to'] = 'C'
        self.rejects('relation entity: unknown reference')

    def test_spatial_cycle_including_inverse_direction(self):
        row = deepcopy(self.data['icir']['relations'][0])
        row['relation'] = 'right_of'
        self.data['icir']['relations'].append(row)
        self.rejects('spatial: cyclic')

    def test_different_coordinate_system_not_false_cycle(self):
        row = deepcopy(self.data['icir']['relations'][0])
        row['relation'] = 'right_of'
        row['coordinate_system'] = 'world'
        self.data['icir']['relations'].append(row)
        self.assertEqual(MODULE.validate(self.data), [])

    def test_continuity_cycle(self):
        self.data['icir']['frames'][0]['continuity'] = {'previous_frame_id': 'F1'}
        self.rejects('cyclic frame order')

    def test_partial_mutual_occlusion_is_legal_but_full_is_not(self):
        rows = [dict(frame_id='F1', coordinate_system='screen', relation='occludes',
                     description='crossed arms', **{'from': a, 'to': b}) for a, b in [('A','B'),('B','A')]]
        self.data['icir']['relations'].extend(rows)
        self.assertEqual(MODULE.validate(self.data), [])
        for row in rows:
            row['relation'] = 'fully_occludes'
        self.rejects('spatial: cyclic')

    def test_subject_coordinates_need_named_owner(self):
        row = deepcopy(self.data['icir']['relations'][0])
        row['coordinate_system'] = 'subject'
        self.data['icir']['relations'].append(row)
        self.rejects('require coordinate_owner')
        row['coordinate_owner'] = 'A'
        self.assertEqual(MODULE.validate(self.data), [])

    def test_missing_speaker_and_visible_text(self):
        text = self.data['icir']['texts'][0]
        text['speaker_id'] = None
        self.rejects('requires speaker')
        text['channel'] = 'visible'
        self.rejects('requires placement')
        self.rejects('visible text missing')

    def test_unknown_api_parameter_is_not_exported(self):
        self.data['compilations'][0]['native_params'] = {'seed': 42}
        self.rejects('require verified executable surface')
        self.rejects('native parameter: unknown reference')

    def test_positive_only_cannot_emit_negative_field(self):
        out = self.data['compilations'][0]
        out['negative_prompt'] = 'bad anatomy'
        out['capability']['negative_mode'] = 'positive_only'
        self.rejects('independent negative prompt')

    def test_verified_capability_requires_official_sources(self):
        cap = self.data['compilations'][0]['capability']
        cap.update(status='verified', checked_at='2026-09-19', source_ids=['U1'])
        self.rejects('reviewed official evidence')

    def test_blocked_output_requires_issue(self):
        out = self.data['compilations'][0]
        out.update(status='BLOCKED', prompt='', constraint_clauses={})
        self.rejects('needs unresolved issue')
        self.data['unresolved'] = [{'id':'I1','owner':'user','source_ids':['U1'],
            'field':'/icir/output','impact':'unsupported exact size',
            'resolution_options':['select another supported surface']}]
        self.assertEqual(MODULE.validate(self.data), [])

    def test_unfinished_generation_cannot_have_done_dependent_review(self):
        self.data['execution'][2]['status'] = 'DONE'
        self.rejects('unfinished dependency')

    def test_execution_cycle(self):
        self.data['execution'][0]['depends_on'] = ['S3']
        self.rejects('cyclic dependencies')

    def test_visual_pass_requires_evidence(self):
        self.data['acceptance'][1]['status'] = 'PASS'
        self.rejects('requires evidence')

    def test_hard_requirement_needs_acceptance(self):
        self.data['acceptance'] = [r for r in self.data['acceptance'] if 'H1' not in r['constraint_ids']]
        self.rejects('missing hard requirement H1')

    def test_actual_pixels_and_native_claims_need_evidence(self):
        self.data['icir']['output'].update(delivered_pixels={'width':2160,'height':2700}, native_resolution='verified')
        self.rejects('require visual evidence')

    def test_wrong_orientation_rejected(self):
        self.data['icir']['output']['requested_pixels'] = {'width':2700,'height':2160}
        self.rejects('aspect ratio mismatch')

    def test_cli_exit_codes_and_bad_json(self):
        good = subprocess.run([sys.executable, str(SCRIPT), str(EXAMPLE)], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)['status'], 'STATIC_VALID')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            for text in ('{', '{"x":1,"x":2}', '{"x":NaN}'):
                path.write_text(text)
                bad = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
                self.assertEqual(bad.returncode, 1, bad.stderr)
                self.assertEqual(json.loads(bad.stdout)['status'], 'INVALID')


if __name__ == '__main__':
    unittest.main()
