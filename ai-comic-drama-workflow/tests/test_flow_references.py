"""Flow receipt/integrity tests use synthetic pixels, never live Flow or visual QA."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ai_comic_drama_workflow.flow import (
    CRITERIA, POLICY, FlowBlockedError, accept_refinement, begin_refinement,
    plan_refinement, refinement_valid, resume_refinement, validate_configuration,
)
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import digest_file, read
from ai_comic_drama_workflow import workspace


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe required')
class FlowReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.assets.name)
        for name, color, size in [('source', 'red', '64x32'), ('output', 'blue', '2048x1024'),
                                  ('small', 'blue', '1920x960'), ('native', 'blue', '1024x512'),
                                  ('square', 'blue', '2048x2048')]:
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s={size}',
                            '-frames:v', '1', '-threads', '1', str(cls.fixture / (name + '.png'))], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.assets.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.kernel = V5Kernel(self.root)
        self.kernel.project = {'flow_refinement': {'policy': POLICY, 'max_attempts': 2}}
        self.kernel.write('project.json', self.kernel.project)
        uri = 'assets/ASSET_HERO/v001/source.png'
        self.kernel.write(uri, (self.fixture / 'source.png').read_bytes())
        sha = digest_file(self.kernel.path(uri))
        self.media = {
            'key': 'ASSET_HERO', 'uri': uri, 'filename': 'source.png', 'sha256': sha, 'revision': 1,
            'provider': 'image_gen', 'call_evidence': 'Synthetic initial tool receipt, no live model call',
            'visual_review': {'status': 'PASS', 'sha256': sha, 'findings': ['Synthetic storage fixture only']},
            'stage': 5, 'role': 'identity', 'entity_id': 'HERO', 'shot_id': None,
            'dependencies': [], 'input_bindings': [], 'input_fingerprint': 'synthetic-input',
            'prompt': {'uri': 'prompts/synthetic.json', 'sha256': 'synthetic'}, 'invalidated': False,
        }

    def receipt(self, action=None, filename='output', width=2048, height=1024):
        action = action or begin_refinement(self.kernel, self.media)
        output = self.fixture / (filename + '.png')
        sha = digest_file(output)
        return {
            'schema': 'flow-refinement-result/1.0', 'action_id': action['action_id'],
            'attempt': action['attempt'], 'status': 'SUCCEEDED', 'submitted': True,
            'source_sha256': self.media['sha256'],
            'service': {'name': 'google-flow', 'surface': 'official-browser',
                        'url': 'https://labs.google/fx/tools/flow/project/synthetic', 'model': 'Synthetic test model'},
            'call_evidence': {'tool': 'synthetic-browser-test', 'invocation_id': 'fixture-call-1',
                              'operation': 'image-to-image', 'evidence': 'Synthetic host receipt; no live service',
                              'reference_attachment': {'sha256': self.media['sha256'], 'evidence': 'Synthetic attachment fixture'},
                              'result_id': 'synthetic-image-1'},
            'output': {'path': str(output), 'sha256': sha, 'width': width, 'height': height,
                       'kind': 'downloaded-image', 'download': {'method': 'official-download',
                                                              'asset_id': 'synthetic-image-1', 'evidence': 'Synthetic export fixture'}},
            'resolution_provenance': {'kind': 'native', 'native': {'width': width, 'height': height,
                                                                  'evidence': 'Synthetic native-resolution claim'}},
            'visual_comparison': {'status': 'PASS', 'source_sha256': self.media['sha256'], 'output_sha256': sha,
                                  'reviewer': 'Synthetic test reviewer', 'evidence': 'Contract-only fixture; not actual visual QA',
                                  'criteria': {name: {'status': 'PASS',
                                                      'source_observation': 'Synthetic source criterion: ' + name,
                                                      'output_observation': 'Synthetic output criterion: ' + name} for name in CRITERIA}},
        }

    def failure(self, action, *, status='FAILED', code='SERVICE_FAILED'):
        result = self.receipt(action)
        result.update(status=status, submitted=status != 'BLOCKED')
        result['failure'] = {'code': code, 'reason': 'Synthetic observed failure', 'evidence': 'Synthetic failure tool evidence'}
        for key in ('output', 'resolution_provenance', 'visual_comparison'):
            result.pop(key)
        return result

    def test_move_project_preserves_unknown_dispatch_identity(self):
        first = begin_refinement(self.kernel, self.media)
        moved = Path(self.tmp.name) / 'moved-project'
        shutil.copytree(self.root, moved)
        recovered = V5Kernel(moved)
        recovered.project = read(moved / 'project.json')
        next_action = begin_refinement(recovered, self.media)
        self.assertEqual(next_action['action_id'], first['action_id'])
        self.assertEqual(next_action['status'], 'RECONCILE_ONLY')
        self.assertEqual(next_action['attempt'], 1)
        self.assertEqual(len(list(moved.rglob('dispatch-*.json'))), 1)

    def test_plan_is_stable_and_source_is_probed_without_dispatch(self):
        first = plan_refinement(self.kernel, self.media)
        second = plan_refinement(self.kernel, self.media)
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'AWAITING_FLOW_REFINEMENT')
        self.assertEqual(first['source']['sha256'], self.media['sha256'])
        self.assertEqual((first['source']['width'], first['source']['height']), (64, 32))
        self.assertEqual(first['source']['path'], str(self.kernel.path(self.media['uri'])))
        self.assertIsNone(first['configuration']['account_hint'])
        self.assertEqual(first['output_contract']['min_long_edge'], 2048)
        self.assertEqual(first['output_contract']['comparison_criteria'], list(CRITERIA))
        self.assertFalse(list(self.root.rglob('dispatch-*.json')))

    def test_begin_is_idempotent_and_requires_reconciliation_after_timeout(self):
        first = begin_refinement(self.kernel, self.media)
        self.assertEqual(first['status'], 'DISPATCHED')
        self.assertEqual(begin_refinement(self.kernel, self.media)['status'], 'RECONCILE_ONLY')
        self.assertEqual(plan_refinement(self.kernel, self.media)['status'], 'RECONCILE_ONLY')
        self.assertEqual(len(list(self.root.rglob('dispatch-*.json'))), 1)

    def test_receipt_without_begin_is_rejected(self):
        action = plan_refinement(self.kernel, self.media)
        with self.assertRaisesRegex(ValueError, 'previously dispatched'):
            accept_refinement(self.kernel, self.media, self.receipt(action))

    def test_success_promotes_download_and_preserves_original_provenance(self):
        result = self.receipt()
        promoted = accept_refinement(self.kernel, self.media, result)
        self.assertEqual(promoted['sha256'], result['output']['sha256'])
        self.assertEqual(promoted['revision'], 2)
        self.assertEqual(promoted['provider'], 'google_flow')
        self.assertNotEqual(promoted['uri'], self.media['uri'])
        self.assertEqual(promoted['visual_review']['sha256'], promoted['sha256'])
        self.assertEqual(promoted['flow_refinement']['original_media'], self.media)
        self.assertEqual(promoted['input_fingerprint'], self.media['input_fingerprint'])
        self.assertTrue(refinement_valid(self.kernel, promoted))
        self.assertEqual(accept_refinement(self.kernel, self.media, result), promoted)
        self.assertEqual(accept_refinement(self.kernel, promoted, result), promoted)
        self.assertEqual(plan_refinement(self.kernel, promoted)['status'], 'FLOW_REFINEMENT_ACCEPTED')
        self.assertEqual(self.kernel.path(promoted['uri']).read_bytes(), (self.fixture / 'output.png').read_bytes())

    def test_sub_2k_image_cannot_claim_2k(self):
        result = self.receipt(filename='small', width=2048, height=1024)
        with self.assertRaisesRegex(ValueError, 'below 2048'):
            accept_refinement(self.kernel, self.media, result)

    def test_wrong_dimensions_aspect_screenshot_and_pass_through_rejected(self):
        action = begin_refinement(self.kernel, self.media)
        mutations = [
            ('dimensions', lambda r: r['output'].update(width=4096)),
            ('screenshot', lambda r: r['output'].update(kind='screenshot')),
            ('preview', lambda r: r['output']['download'].update(method='preview')),
            ('source-pass-through', lambda r: (r['output'].update(path=str(self.kernel.path(self.media['uri'])), sha256=self.media['sha256']))),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                result = self.receipt(action)
                mutate(result)
                with self.assertRaises(ValueError):
                    accept_refinement(self.kernel, self.media, result)
        with self.assertRaisesRegex(ValueError, 'aspect'):
            accept_refinement(self.kernel, self.media, self.receipt(action, filename='square', width=2048, height=2048))

    def test_renaming_or_reencoding_source_is_not_a_generation(self):
        source = self.fixture / 'output.png'
        self.kernel.write(self.media['uri'], source.read_bytes())
        self.media['sha256'] = digest_file(source)
        self.media['visual_review']['sha256'] = self.media['sha256']
        reencoded = Path(self.tmp.name) / 'reencoded.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-compression_level', '0',
                        '-threads', '1', str(reencoded)], check=True)
        self.assertNotEqual(digest_file(source), digest_file(reencoded))
        result = self.receipt()
        result['output'].update(path=str(reencoded), sha256=digest_file(reencoded))
        with self.assertRaisesRegex(ValueError, 'unchanged source'):
            accept_refinement(self.kernel, self.media, result)

    def test_fake_or_changed_file_cannot_pass_probe(self):
        result = self.receipt()
        bad = Path(self.tmp.name) / 'not-image.png'
        bad.write_bytes(b'not an image; width=2048 height=1024')
        result['output'].update(path=str(bad), sha256=digest_file(bad))
        with self.assertRaises(ValueError):
            accept_refinement(self.kernel, self.media, result)

    def test_service_call_reference_and_hash_binding_are_mandatory(self):
        action = begin_refinement(self.kernel, self.media)
        for label, mutate in [
            ('service', lambda r: r['service'].update(name='another-service')),
            ('api', lambda r: r['service'].update(surface='unofficial-api')),
            ('evil-url', lambda r: r['service'].update(url='https://labs.google.attacker.test/fx/tools/flow')),
            ('other-google-product', lambda r: r['service'].update(url='https://labs.google/fx/tools/whisk')),
            ('tool', lambda r: r['call_evidence'].pop('invocation_id')),
            ('reference', lambda r: r['call_evidence']['reference_attachment'].update(sha256='bad')),
            ('reference-evidence', lambda r: r['call_evidence']['reference_attachment'].update(evidence='N/A')),
            ('source', lambda r: r.update(source_sha256='bad')),
            ('output', lambda r: r['output'].update(sha256='bad')),
            ('download', lambda r: r['output']['download'].update(asset_id='another-image')),
            ('submitted', lambda r: r.update(submitted=False)),
        ]:
            with self.subTest(label=label):
                result = self.receipt(action)
                mutate(result)
                with self.assertRaises(ValueError):
                    accept_refinement(self.kernel, self.media, result)

    def test_comparison_needs_every_criterion_and_both_images(self):
        action = begin_refinement(self.kernel, self.media)
        for label, mutate in [
            ('missing', lambda c: c['criteria'].pop('wardrobe')),
            ('source', lambda c: c.update(source_sha256='bad')),
            ('output', lambda c: c.update(output_sha256='bad')),
            ('failed', lambda c: c['criteria']['identity'].update(status='FAIL')),
            ('silent-na', lambda c: c['criteria']['text'].update(status='NA')),
            ('observation', lambda c: c['criteria']['text'].update(output_observation='N/A')),
            ('unproven-absence', lambda c: c['criteria']['text'].update(status='NOT_PRESENT')),
        ]:
            with self.subTest(label=label):
                result = self.receipt(action)
                mutate(result['visual_comparison'])
                with self.assertRaises(ValueError):
                    accept_refinement(self.kernel, self.media, result)

    def test_absent_criterion_must_be_explicitly_observed_on_both_images(self):
        result = self.receipt()
        result['visual_comparison']['criteria']['text'] = {
            'status': 'NOT_PRESENT', 'source_absent': True, 'output_absent': True,
            'source_observation': 'Synthetic source has no visible text',
            'output_observation': 'Synthetic output has no visible text',
            'reason': 'Neither synthetic fixture includes lettering',
        }
        self.assertTrue(refinement_valid(self.kernel, accept_refinement(self.kernel, self.media, result)))

    def test_official_upscaled_output_keeps_native_and_derived_dimensions(self):
        result = self.receipt()
        native = self.fixture / 'native.png'
        result['resolution_provenance'] = {
            'kind': 'official-upscaled',
            'native': {'path': str(native), 'sha256': digest_file(native), 'width': 1024, 'height': 512,
                       'evidence': 'Synthetic native export fixture'},
            'upscale': {'service': 'google-flow', 'evidence': 'Synthetic official-upscale fixture'},
        }
        promoted = accept_refinement(self.kernel, self.media, result)
        provenance = promoted['flow_refinement']['resolution_provenance']
        self.assertTrue(provenance['derived'])
        self.assertEqual(provenance['original_reference']['width'], 64)
        self.assertEqual(provenance['native']['width'], 1024)
        self.assertEqual(provenance['downloaded']['width'], 2048)
        self.assertTrue(refinement_valid(self.kernel, promoted))
        self.kernel.path(provenance['native']['uri']).write_bytes(b'changed native image')
        self.assertFalse(refinement_valid(self.kernel, promoted))

    def test_false_native_and_local_upscale_provenance_fail(self):
        action = begin_refinement(self.kernel, self.media)
        for change in ({'kind': 'local-upscaled'}, {'native': {'width': 1024, 'height': 512, 'evidence': 'Synthetic native claim'}}):
            result = self.receipt(action)
            result['resolution_provenance'].update(change)
            with self.assertRaises(ValueError):
                accept_refinement(self.kernel, self.media, result)

    def test_account_selection_is_configurable_and_not_guessed(self):
        self.kernel.project['flow_refinement']['account_hint'] = 'chosen-test-account'
        result = self.receipt()
        with self.assertRaisesRegex(ValueError, 'account'):
            accept_refinement(self.kernel, self.media, result)
        result['service']['account_hint'] = 'chosen-test-account'
        promoted = accept_refinement(self.kernel, self.media, result)
        self.assertTrue(refinement_valid(self.kernel, promoted))
        self.kernel.project['flow_refinement']['account_hint'] = 'different-test-account'
        self.assertFalse(refinement_valid(self.kernel, promoted))

    def test_known_failures_allow_only_bounded_retry(self):
        for expected in (1, 2):
            action = begin_refinement(self.kernel, self.media)
            self.assertEqual(action['attempt'], expected)
            result = self.failure(action)
            with self.assertRaises(FlowBlockedError) as blocked:
                accept_refinement(self.kernel, self.media, result)
            self.assertEqual(blocked.exception.result['status'], 'BLOCKED')
        next_action = begin_refinement(self.kernel, self.media)
        self.assertEqual(next_action['status'], 'BLOCKED')
        self.assertEqual(next_action['code'], 'ATTEMPT_LIMIT')
        self.assertEqual(len(list(self.root.rglob('dispatch-*.json'))), 2)

    def test_submitted_wrong_account_failure_is_recorded_and_requires_resolution(self):
        self.kernel.project['flow_refinement']['account_hint'] = 'chosen-test-account'
        action = begin_refinement(self.kernel, self.media)
        result = self.failure(action, status='FAILED', code='ACCOUNT_MISMATCH')
        result['service']['account_hint'] = 'observed-wrong-account'
        with self.assertRaises(FlowBlockedError) as blocked:
            accept_refinement(self.kernel, self.media, result)
        self.assertEqual(blocked.exception.result['code'], 'ACCOUNT_MISMATCH')
        plan = plan_refinement(self.kernel, self.media)
        self.assertEqual(plan['status'], 'BLOCKED')
        self.assertTrue(plan['resume_required'])
        stored = read(next(self.root.rglob('receipt-001.json')))
        self.assertEqual(stored['service']['account_hint'], 'observed-wrong-account')
        evidence = {'schema': 'flow-resume-evidence/1.0', 'action_id': action['action_id'],
                    'attempt': 1, 'code': 'ACCOUNT_MISMATCH', 'status': 'RESOLVED',
                    'observer': 'Synthetic browser tool', 'evidence': 'Synthetic selected-account observation',
                    'service': deepcopy(result['service'])}
        with self.assertRaisesRegex(ValueError, 'account'):
            resume_refinement(self.kernel, self.media, evidence)
        evidence['service']['account_hint'] = 'chosen-test-account'
        self.assertEqual(resume_refinement(self.kernel, self.media, evidence)['attempt'], 2)
        next_action = begin_refinement(self.kernel, self.media)
        success = self.receipt(next_action)
        success['service']['account_hint'] = 'chosen-test-account'
        promoted = accept_refinement(self.kernel, self.media, success)
        self.assertTrue(refinement_valid(self.kernel, promoted))

    def test_login_capability_and_subscription_are_truthful_blockers(self):
        action = begin_refinement(self.kernel, self.media)
        result = self.failure(action, status='BLOCKED', code='LOGIN_REQUIRED')
        result.pop('service')
        result.pop('call_evidence')
        with self.assertRaises(FlowBlockedError) as blocked:
            accept_refinement(self.kernel, self.media, result)
        self.assertEqual(blocked.exception.result['code'], 'LOGIN_REQUIRED')
        self.assertNotIn('flow_refinement', self.media)
        self.assertFalse(list(self.root.rglob('record.json')))
        self.assertEqual(plan_refinement(self.kernel, self.media)['status'], 'BLOCKED')
        self.assertEqual(begin_refinement(self.kernel, self.media)['status'], 'BLOCKED')
        self.assertEqual(len(list(self.root.rglob('dispatch-*.json'))), 1)
        stored = next(self.root.rglob('receipt-001.json'))
        self.assertEqual(read(stored)['submitted'], False)
        with self.assertRaisesRegex(ValueError, 'terminal'):
            changed = deepcopy(result)
            changed['failure']['code'] = 'SUBSCRIPTION_REQUIRED'
            accept_refinement(self.kernel, self.media, changed)

    def test_blocker_resume_requires_specific_resolution_evidence(self):
        action = begin_refinement(self.kernel, self.media)
        result = self.failure(action, status='BLOCKED', code='CAPABILITY_UNAVAILABLE')
        with self.assertRaises(FlowBlockedError):
            accept_refinement(self.kernel, self.media, result)
        evidence = {'schema': 'flow-resume-evidence/1.0', 'action_id': action['action_id'],
                    'attempt': 1, 'code': 'CAPABILITY_UNAVAILABLE', 'status': 'RESOLVED',
                    'observer': 'Synthetic browser observation', 'evidence': 'Synthetic resolved capability fixture',
                    'service': result['service']}
        with self.assertRaises(ValueError):
            resume_refinement(self.kernel, self.media, {**evidence, 'code': 'LOGIN_REQUIRED'})
        with self.assertRaises(ValueError):
            resume_refinement(self.kernel, self.media, {**evidence, 'evidence': 'N/A'})
        resumed = resume_refinement(self.kernel, self.media, evidence)
        self.assertEqual(resumed['status'], 'AWAITING_FLOW_REFINEMENT')
        self.assertEqual(resumed['attempt'], 2)
        self.assertEqual(resume_refinement(self.kernel, self.media, evidence), resumed)
        self.assertEqual(len(list(self.root.rglob('dispatch-*.json'))), 1)
        next_action = begin_refinement(self.kernel, self.media)
        self.assertEqual(next_action['attempt'], 2)
        with self.assertRaises(ValueError):
            resume_refinement(self.kernel, self.media, evidence)
        promoted = accept_refinement(self.kernel, self.media, self.receipt(next_action))
        self.assertTrue(refinement_valid(self.kernel, promoted))
        resume_path = next(self.root.rglob('resume-001.json'))
        resume_path.write_bytes(resume_path.read_bytes() + b' changed')
        self.assertFalse(refinement_valid(self.kernel, promoted))

    def test_success_after_retry_binds_previous_failure_history(self):
        first = begin_refinement(self.kernel, self.media)
        with self.assertRaises(FlowBlockedError):
            accept_refinement(self.kernel, self.media, self.failure(first))
        second = begin_refinement(self.kernel, self.media)
        promoted = accept_refinement(self.kernel, self.media, self.receipt(second))
        self.assertEqual(promoted['flow_refinement']['attempt'], 2)
        self.assertTrue(refinement_valid(self.kernel, promoted))
        old_receipt = next(self.root.rglob('receipt-001.json'))
        old_receipt.write_bytes(old_receipt.read_bytes() + b' changed')
        self.assertFalse(refinement_valid(self.kernel, promoted))

    def test_unknown_outcome_requires_reconcile_without_second_dispatch(self):
        action = begin_refinement(self.kernel, self.media)
        unknown = self.failure(action, status='UNKNOWN', code='UNKNOWN')
        with self.assertRaises(FlowBlockedError) as blocked:
            accept_refinement(self.kernel, self.media, unknown)
        self.assertTrue(blocked.exception.result['reconcile_only'])
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            resume_refinement(self.kernel, self.media, {})
        self.assertEqual(begin_refinement(self.kernel, self.media)['status'], 'RECONCILE_ONLY')
        promoted = accept_refinement(self.kernel, self.media, self.receipt(action))
        self.assertTrue(refinement_valid(self.kernel, promoted))
        self.assertEqual(len(list(self.root.rglob('dispatch-*.json'))), 1)
        self.assertEqual(len(list(self.root.rglob('unknown-*.json'))), 1)

    def test_tampering_source_output_receipt_plan_marker_or_record_invalidates(self):
        promoted = accept_refinement(self.kernel, self.media, self.receipt())
        metadata = promoted['flow_refinement']
        record = read(self.kernel.path(metadata['record_uri']))
        paths = [self.media['uri'], promoted['uri'], metadata['receipt_uri'], metadata['record_uri'],
                 record['plan_uri'], record['dispatch_uri']]
        for uri in paths:
            with self.subTest(uri=uri):
                path = self.kernel.path(uri)
                original = path.read_bytes()
                path.write_bytes(original + b'\nchanged')
                self.assertFalse(refinement_valid(self.kernel, promoted))
                path.write_bytes(original)
                self.assertTrue(refinement_valid(self.kernel, promoted))
        changed = deepcopy(promoted)
        changed['revision'] += 1
        self.assertFalse(refinement_valid(self.kernel, changed))
        changed = deepcopy(promoted)
        changed['flow_refinement']['original_media']['provider'] = 'provided'
        self.assertFalse(refinement_valid(self.kernel, changed))

    def test_compact_paths_use_kernel_write_and_still_validate(self):
        self.kernel.project['output_policy'] = workspace.POLICY
        self.kernel.write('project.json', self.kernel.project)
        self.kernel.write(self.media['uri'], (self.fixture / 'source.png').read_bytes())
        promoted = accept_refinement(self.kernel, self.media, self.receipt())
        self.assertTrue(promoted['uri'].startswith('05-assets/'))
        self.assertTrue(refinement_valid(self.kernel, promoted))
        self.assertTrue((self.root / '.runtime' / 'flow').is_dir())
        self.assertFalse((self.root / 'runtime').exists())

    def test_configuration_rejects_unbounded_or_unknown_settings(self):
        self.assertIsNone(validate_configuration({})['account_hint'])
        for value in (0, 4, True, '2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_configuration({'max_attempts': value})
        with self.assertRaises(ValueError):
            validate_configuration({'policy': 'unofficial-flow-api'})
        with self.assertRaises(ValueError):
            validate_configuration({'password': 'must-not-be-configurable'})
        with self.assertRaises(ValueError):
            validate_configuration(False)


if __name__ == '__main__':
    unittest.main()
