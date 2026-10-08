"""Fault injection with synthetic native fixtures/pixels; no provider calls."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ai_comic_drama_workflow import execution_gate as gate
from ai_comic_drama_workflow.lean import start
from ai_comic_drama_workflow.production import ProductionLedger
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_cli import main
from ai_comic_drama_workflow.v5_modules import read, digest_file
from tests.test_v5_workflow import FIXTURE, submit_fixture, result_for
from tests import test_v5_workflow as fixtures


class ExecutionGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.author = self.root/'author'
        shutil.copytree(FIXTURE, self.author)
        self.k = V5Kernel.initialize(self.root/'project', [str(self.author/'cafe.source.txt')],
            project_id='CAFE_DEMO', delivery='full', production_target='video',
            execution_policy=gate.POLICY, stop_after='images', creative_policy='automatic',
            workflow_profile='lean', output_policy='compact-workspace/1.0')
        self.k.host('available', 'SYNTHETIC HOST FIXTURE', image_tools=['fixture.image'])

    def first_image(self):
        for _ in range(12):
            response = self.k.run(); task = response['task']
            if task['kind'] == 'image': return task
            if task['kind'] == 'image-prompt':
                self.k.submit(result_for(task, prompt='SYNTHETIC prompt for ' + task['slot']))
            else: submit_fixture(self.k, self.author, task)
        self.fail('Native image task not reached')

    def media_result(self, task, generated=False):
        path = fixtures.V5Tests.pixels(self)
        result = fixtures.V5Tests.image_result(self, task, path)
        media = result['media']
        media['provenance_kind'] = 'user_provided'
        media['visual_review']['checks'] = [{'check': key, 'status': 'PASS',
            'observation': 'SYNTHETIC TEST ONLY: exercise coverage, not real visual approval.'}
            for key in gate.VISUAL_CHECKS]
        for row in media['visual_review']['findings']: row['status'] = 'PASS'
        if generated:
            media.update(provider='image_gen', call_evidence='fixture.image SYNTHETIC return')
            media.pop('provenance_kind')
        return result

    def recovery(self, record, state='UNKNOWN'):
        proof = self.root/'provider-proof.json'
        proof.write_text('SYNTHETIC PROVIDER FIXTURE, not actual execution evidence')
        return {'record_id': record['id'], 'task_sha256': record['task_sha256'], 'state': state,
                'proof_file': str(proof), 'observation': 'SYNTHETIC provider state observation',
                'provider_task_id': None}

    def finish_images(self):
        for _ in range(25):
            response = self.k.run()
            if response['status'] == 'IMAGES_DELIVERED': return response
            task = response['task']
            if task['kind'] == 'image': self.k.submit(self.media_result(task))
            elif task['kind'] == 'image-prompt':
                self.k.submit(result_for(task, prompt='SYNTHETIC prompt for ' + task['slot']))
            else: submit_fixture(self.k, self.author, task)
        self.fail('Images did not converge')

    def test_new_studio_freezes_gate_and_legacy_is_not_migrated(self):
        start(self.root/'new', ['test'], stop_after='images')
        config = read(self.root/'new/project.json')
        self.assertEqual(config['execution_policy'], gate.POLICY)
        old = V5Kernel.initialize(self.root/'old', ['test'])
        before = (old.root/'project.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'not migrated'):
            old.set_scope('images', 'user scope change')
        self.assertEqual(before, (old.root/'project.json').read_bytes())
        with self.assertRaises(ValueError): start(self.root/'bad', ['test'], stop_after='images', delivery='text-only')

    def test_generated_result_requires_reservation(self):
        task = self.first_image()
        with self.assertRaisesRegex(ValueError, 'record ID'):
            self.k.submit(self.media_result(task, generated=True))
        self.assertFalse(self.k.state['media'])

    def test_host_adapter_never_invokes_tool_before_gate(self):
        from unittest.mock import Mock
        task = self.k.run()['task']; provider = Mock()
        with self.assertRaisesRegex(ValueError, 'Only image'):
            gate.dispatch_image(self.k, task['task_id'], provider)
        provider.assert_not_called()

    def test_host_adapter_receives_candidate_without_auto_acceptance(self):
        from unittest.mock import Mock
        task = self.first_image(); path = fixtures.V5Tests.pixels(self)
        provider = Mock(return_value={'file':str(path),'call_evidence':'fixture.image TEST'})
        response = gate.dispatch_image(self.k, task['task_id'], provider)
        self.assertEqual(response['status'], 'CANDIDATE_RECEIVED')
        self.assertEqual(response['visual_review'], 'NOT_RUN')
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.k.state['media'], {})

    def test_host_adapter_timeout_is_unknown_and_cannot_retry(self):
        from unittest.mock import Mock
        task = self.first_image(); provider = Mock(side_effect=TimeoutError('fixture'))
        response = gate.dispatch_image(self.k, task['task_id'], provider)
        self.assertEqual(response['status'], 'BLOCKED_UNKNOWN')
        with self.assertRaises(ValueError): gate.dispatch_image(self.k, task['task_id'], provider)
        self.assertEqual(provider.call_count, 1)

    def test_malformed_provider_return_remains_unknown(self):
        task = self.first_image(); path = fixtures.V5Tests.pixels(self)
        response = gate.dispatch_image(self.k, task['task_id'], lambda _:
            {'file':str(path),'call_evidence':'fixture.image TEST','provider_task_id':123})
        self.assertEqual(response['status'], 'BLOCKED_UNKNOWN')
        self.assertEqual(len(gate.records(self.k)), 1)

    def test_pending_video_task_cannot_be_hidden_by_scope_change(self):
        # Fault injection of an existing unresolved provider record, no service call.
        self.k.write('runtime/production/executions/EXE_fixture.json', {'state':'UNKNOWN'})
        with self.assertRaisesRegex(ValueError, 'unresolved video'):
            self.k.set_scope('full', 'user requests resume')
        self.assertEqual(self.k.project['stop_after'], 'images')

    def test_begin_rechecks_task_prompt_and_native_prerequisites(self):
        task = self.first_image()
        path = self.k.path(task['prompt']['uri']); original = path.read_bytes()
        path.write_text('changed prompt')
        with self.assertRaisesRegex(ValueError, 'prompt'): self.k.begin_image(task['task_id'])
        path.write_bytes(original)
        state = self.k.state; state['artifacts']['screenplay']['invalidated'] = True; self.k.save(state)
        with self.assertRaisesRegex(ValueError, 'prerequisite'): self.k.begin_image(task['task_id'])
        self.assertEqual(gate.records(self.k), [])

    def test_changed_envelope_cannot_generate(self):
        task = self.first_image(); path = self.k.path('runtime/tasks/' + task['task_id'] + '.json')
        changed = read(path); changed['prompt']['params']['model'] = 'different'
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'envelope'): self.k.begin_image(task['task_id'])

    def test_one_reservation_under_concurrent_calls(self):
        task = self.first_image()
        def begin(_):
            try: return V5Kernel(self.k.root).begin_image(task['task_id'])
            except ValueError: return None
        with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(begin, range(2)))
        self.assertEqual(sum(x is not None for x in result), 1)
        self.assertEqual(len(gate.records(self.k)), 1)

    def test_unknown_retains_original_record_and_blocks_scope(self):
        task = self.first_image(); record = self.k.begin_image(task['task_id'])['execution']
        evidence = self.recovery(record)
        self.k.recover_image(evidence)
        self.assertEqual(self.k.recover_image(evidence)['state'], 'UNKNOWN')
        with self.assertRaises(ValueError): self.k.begin_image(task['task_id'])
        with self.assertRaises(ValueError): self.k.set_scope('full', 'user resumed video')
        with self.assertRaisesRegex(ValueError, 'structured'): self.k.recover_image('please retry')
        self.assertEqual(len(gate.records(self.k)), 1)
        self.assertEqual(self.k.run()['inflight']['record_id'], record['id'])

    def test_recovered_original_result_accepted_without_resubmission(self):
        task = self.first_image(); record = self.k.begin_image(task['task_id'])['execution']
        result = self.media_result(task, generated=True)
        evidence = self.recovery(record, 'RECEIVED'); evidence['file'] = result['media']['path']
        self.k.recover_image(evidence)
        self.assertIsNone(self.k.state['inflight'])
        result['media']['execution_record_id'] = record['id']
        self.assertEqual(self.k.submit(result)['status'], 'ACCEPTED')
        self.assertEqual(self.k.submit(result)['status'], 'ALREADY_ACCEPTED')
        self.assertEqual(len(gate.records(self.k)), 1)
        self.assertEqual(gate.records(self.k)[0]['state'], 'ACCEPTED')
        self.assertTrue(self.k.media_valid(self.k.state['media'][task['slot']]))

    def test_recovery_payload_provider_and_terminal_conflicts_rejected(self):
        task = self.first_image(); record = self.k.begin_image(task['task_id'])['execution']
        evidence = self.recovery(record, 'SUBMITTED'); evidence['provider_task_id'] = 'real-fixture-id'
        wrong = dict(evidence, task_sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'payload'): self.k.recover_image(wrong)
        self.k.recover_image(evidence)
        with self.assertRaisesRegex(ValueError, 'replaced'): self.k.recover_image(dict(evidence, provider_task_id='other'))
        with self.assertRaisesRegex(ValueError, 'NOT_SUBMITTED'): self.k.recover_image(dict(evidence, state='NOT_SUBMITTED'))
        failed = dict(evidence, state='FAILED'); self.k.recover_image(failed)
        self.assertEqual(self.k.recover_image(failed)['state'], 'FAILED')
        with self.assertRaisesRegex(ValueError, 'Terminal'): self.k.recover_image(dict(failed, observation='different evidence'))
        self.assertIsNone(self.k.state['inflight'])

    def test_blanket_pass_failed_check_and_missing_provenance_block_import(self):
        task = self.first_image(); result = self.media_result(task)
        result['media']['visual_review'].pop('checks')
        with self.assertRaisesRegex(ValueError, 'per-check'): self.k.submit(result)
        result = self.media_result(task); result['media']['visual_review']['checks'][1]['status'] = 'FAIL'
        with self.assertRaisesRegex(ValueError, 'Failed'): self.k.submit(result)
        result = self.media_result(task); result['media'].pop('provenance_kind')
        with self.assertRaisesRegex(ValueError, 'provenance'): self.k.submit(result)
        self.assertEqual(self.k.state['media'], {})

    def test_frozen_dimensions_checked_against_actual_decoder(self):
        # Use the public native prompt submission, not an edited accepted prompt.
        for _ in range(10):
            task = self.k.run()['task']
            if task['kind'] == 'image-prompt': break
            submit_fixture(self.k, self.author, task)
        result = result_for(task, prompt='SYNTHETIC dimension fixture')
        result['params']['expected_image'] = {'aspect_ratio': [9, 16]}
        self.k.submit(result); task = self.k.run()['task']
        # Real decoder sees the fixture's 2x2 image, not the declared target.
        with self.assertRaisesRegex(ValueError, 'aspect ratio'):
            self.k.submit(self.media_result(task))
        self.assertEqual(self.k.state['media'], {})

    def test_different_received_bytes_cannot_use_original_execution(self):
        task = self.first_image(); record = self.k.begin_image(task['task_id'])['execution']
        result = self.media_result(task, generated=True)
        evidence = self.recovery(record, 'RECEIVED'); evidence['file'] = result['media']['path']
        self.k.recover_image(evidence)
        result['media'].update(execution_record_id=record['id'], sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'Recovered image bytes'):
            self.k.submit(result)

    def test_no_accepted_media_from_untracked_folder(self):
        folder = self.k.root/'exploration'; folder.mkdir()
        (folder/'pretend-accepted.json').write_text('{"status":"ACCEPTED"}')
        self.assertEqual(self.k.export()['status'], 'BLOCKED')
        self.assertEqual(gate.image_report(self.k)['assets'], [])

    def test_receipt_tamper_invalidates_an_accepted_image(self):
        task = self.first_image(); self.k.submit(self.media_result(task))
        media = self.k.state['media'][task['slot']]
        self.assertTrue(self.k.media_valid(media))
        proof = self.k.path(media['acceptance_receipt']['uri']); proof.write_text('{}')
        self.assertFalse(self.k.media_valid(media))

    def test_scope_keeps_native_hashes_and_does_not_turn_missing_stages_into_success(self):
        self.k.set_scope('full', 'user wants complete workflow')
        task = self.k.run()['task']; submit_fixture(self.k, self.author, task)
        canon = self.k.state['artifacts']['canon']['sha256']
        self.k.set_scope('images', 'user now only wants pictures')
        self.assertEqual(self.k.state['artifacts']['canon']['sha256'], canon)
        self.assertEqual(self.k.run()['task']['kind'], 'screenplay')
        self.assertEqual(self.k.export()['status'], 'BLOCKED')
        self.assertEqual(self.k.export(draft=True)['status'], 'DRAFT')

    def test_image_delivery_roundtrip_and_stale_result_reporting(self):
        response = self.finish_images()
        self.assertTrue(response['images_complete'])
        self.assertFalse(response['preproduction_complete'])
        self.assertFalse(response['video_complete'])
        self.assertNotIn('storyboard', self.k.state['artifacts'])
        self.assertIsNone(self.k.state['build'])
        report = read(self.k.path('delivery/image-status.json'))
        self.assertTrue(report['assets']); self.assertTrue(all(a['status'] == 'ACCEPTED' for a in report['assets']))
        self.assertEqual(self.k.status()['status'], 'IMAGES_DELIVERED')
        hashes = {k:v['sha256'] for k,v in self.k.state['artifacts'].items()}
        self.k.set_scope('full', 'user resumes full work')
        self.assertEqual(self.k.run()['task']['kind'], 'storyboard')
        self.assertEqual(hashes, {k:v['sha256'] for k,v in self.k.state['artifacts'].items()})
        self.k.set_scope('images', 'pause again'); self.k.run()
        row = next(iter(self.k.state['media'].values())); self.k.path(row['uri']).write_bytes(b'changed')
        self.assertEqual(self.k.status()['status'], 'STALE')
        self.assertEqual(self.k.export()['status'], 'BLOCKED')

    def test_video_generation_cannot_use_image_delivery_as_preproduction_pass(self):
        with self.assertRaisesRegex(ValueError, 'paused'):
            ProductionLedger(self.k)._verify_current_preproduction()

    def test_cli_scope_and_readonly_report(self):
        before = (self.k.root/'state.json').read_bytes()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(['image-report', str(self.k.root)])
        self.assertEqual(code, 2); self.assertEqual(json.loads(output.getvalue())['status'], 'BLOCKED')
        self.assertEqual(before, (self.k.root/'state.json').read_bytes())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['scope', str(self.k.root), '--stop-after', 'full', '--reason', 'user resumed']), 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'SCOPE_CHANGED')


if __name__ == '__main__': unittest.main()
