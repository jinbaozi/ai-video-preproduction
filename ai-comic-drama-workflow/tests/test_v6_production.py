"""Strict production gates with local synthetic media; no provider calls."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from ai_comic_drama_workflow.acceptance import adjacent_decision, decide, freeze_plan, shot_decision
from ai_comic_drama_workflow.assembly import _probe, assemble_ffmpeg, timelines
from ai_comic_drama_workflow.executors.manual import ManualExecutor
from ai_comic_drama_workflow.executors.agnes_api import AgnesApiExecutor
from ai_comic_drama_workflow.production import ProductionLedger, channel_registry
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT
from ai_comic_drama_workflow.v6_production_runtime import V6ProductionRuntime, validate_host_node_candidate
from ai_comic_drama_workflow.v6_runtime import V6Runtime
from ai_comic_drama_workflow.v6_stage_adapter import slot_for
from ai_comic_drama_workflow.v6_codex_host import receipt_from_spawn_result


def _strict_kernel(root):
    kernel = V5Kernel.initialize(root, ['原创本地媒体验收案例。'], delivery='text-only', production_target='video')
    kernel.project['execution_mode'] = 'codex-agents'
    kernel.project['orchestration_protocol'] = '6.0'
    kernel.write('project.json', kernel.project)
    return kernel


def _compiled(root, request):
    path = root / 'compile.json'
    path.write_text(json.dumps({'status': 'COMPILED_DRAFT', 'submitted': False, 'requests': [request]}) + '\n')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _media(path, frequency=440):
    subprocess.check_call([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=64x64:r=24:d=1',
        '-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000:duration=1',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path),
    ])


class StrictProductionTests(unittest.TestCase):
    def test_channel_registry_uses_locked_bundle_without_sibling_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            solo = Path(temporary) / 'solo-workflow'
            bundle = solo / 'assets/bundled-skills/video-prompt-compiler.skill'
            bundle.parent.mkdir(parents=True)
            shutil.copy2(ROOT / 'modules.lock.json', solo / 'modules.lock.json')
            shutil.copy2(ROOT / 'assets/bundled-skills/video-prompt-compiler.skill', bundle)
            self.assertTrue(channel_registry(solo)['routes'])
            bundle.write_bytes(bundle.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'missing or changed'):
                channel_registry(solo)

    def _bridge(self, root):
        """Seed only the accepted preproduction predecessor in this bridge test."""
        runtime = V6Runtime.initialize(root, ['原创双镜头本地素材案例。'],
                                       delivery='text-only', production_target='video')
        scope = {'kind': 'project', 'ids': []}
        slot = slot_for('preproduction_delivery', scope, 'PreproductionDelivery')
        uri = 'runtime/v6/test-fixture/preproduction.json'
        runtime.write(uri, {'fixture': 'preproduction previously accepted'})
        digest = hashlib.sha256(runtime.path(uri).read_bytes()).hexdigest()
        def seed(state, artifacts):
            state['tasks']['FIXTURE_PREPRODUCTION'] = {
                'envelope': {'node_id': 'preproduction_delivery', 'task_id': 'FIXTURE_PREPRODUCTION',
                             'scope': scope, 'input_revision': 0, 'batch': 1,
                             'inputs': [], 'resources': [], 'dependencies': [],
                             'expected_artifacts': [{'slot': slot, 'kind': 'PreproductionDelivery'}]},
                'state': 'ACCEPTED', 'version': 1, 'receipt': None,
                'receipt_history': [], 'review_dispatch': None,
                'candidate': None, 'review': None, 'validation': [],
                'messages': [], 'history': [], 'failure_counts': {},
                'evidence_hashes': {}}
            artifacts[slot] = {'slot': slot, 'kind': 'PreproductionDelivery', 'uri': uri,
                               'sha256': digest, 'task_id': 'FIXTURE_PREPRODUCTION',
                               'batch': 1, 'candidate_digest': digest}
        runtime.kernel._apply('test_fixture', {'name': 'accepted_preproduction'},
                              'fixture-preproduction', 0, seed)
        return V6ProductionRuntime(runtime)

    def _accept_review_fixture(self, bridge, pending, observed_files):
        """Synthetic Codex tool records for testing gates, not a live agent claim."""
        runtime = bridge.runtime
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        action = pending['action']
        agent_id = '/fixture/'+action['task_name']
        receipt = receipt_from_spawn_result(action, {'task_name': agent_id},
                      project_root=runtime.root, sent_at=now, observed_at=now)
        runtime.agent_event(receipt, command_id='fixture-dispatch-'+pending['task_id'],
                            expected_revision=runtime.kernel.snapshot()['revision'])
        envelope = runtime.kernel.inspect(pending['task_id'])['envelope']
        intent = next(row for row in envelope['inputs'] if row['slot'] == 'production_intent')
        value = json.loads(runtime.path(intent['uri']).read_text())
        prefix = f"runtime/v6/candidates/{pending['task_id']}/1/"
        expected = envelope['expected_artifacts'][0]
        artifact_uri = prefix+expected['kind']+'.json'
        runtime.write(artifact_uri, value)
        artifact_sha = hashlib.sha256(runtime.path(artifact_uri).read_bytes()).hexdigest()
        review_uri = prefix+'independent-review.json'
        proof_rows = [{'uri': uri, 'sha256': hashlib.sha256(runtime.path(uri).read_bytes()).hexdigest()}
                      for uri in observed_files]
        review = {'schema': 'production-review/6.0', 'task_id': pending['task_id'],
                  'batch': 1, 'reviewer_agent_id': agent_id,
                  'decision_sha256': artifact_sha,
                  'items': [{'id': row['id'], 'status': 'PASS', 'evidence': proof_rows}
                            for row in envelope['validators']]}
        runtime.write(review_uri, review)
        candidate = {'schema': 'candidate-result/6.0', 'task_id': pending['task_id'],
                     'batch': 1, 'agent_id': agent_id, 'input_digest': envelope['input_digest'],
                     'result_uri': None, 'result_sha256': None,
                     'artifacts': [{'slot': expected['slot'], 'kind': expected['kind'],
                                    'uri': artifact_uri, 'sha256': artifact_sha}],
                     'module_receipts': [],
                     'checks': [{'id': row['id'], 'status': 'PASS', 'evidence': [review_uri]}
                                for row in envelope['validators']],
                     'handoffs': [], 'unresolved': []}
        subject_uri = prefix+'candidate.json'
        runtime.write(subject_uri, candidate)
        message = {'schema': 'agent-message/6.0', 'message_id': 'MSG_'+pending['task_id'],
                   'task_id': pending['task_id'], 'batch': 1, 'sender_id': agent_id,
                   'recipient_id': 'kernel', 'in_reply_to': None, 'type': 'RESULT',
                   'summary': 'Synthetic fixture reviewed frozen bytes', 'evidence': [review_uri],
                   'at': now, 'subject_uri': subject_uri,
                   'subject_sha256': hashlib.sha256(runtime.path(subject_uri).read_bytes()).hexdigest()}
        runtime.agent_message(message, command_id='fixture-message-'+pending['task_id'],
                              expected_revision=runtime.kernel.snapshot()['revision'])
        with patch.object(runtime, 'run', return_value={'status': 'FIXTURE_ACCEPTED'}):
            runtime.agent_result(candidate, command_id='fixture-result-'+pending['task_id'],
                                 expected_revision=runtime.kernel.snapshot()['revision'])
        self.assertEqual(runtime.kernel.inspect(pending['task_id'])['state'], 'ACCEPTED')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_complete_production_graph_with_explicit_synthetic_reviewer_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = self._bridge(root/'project')
            request = {'id': 'REQUEST_COMPLETE', 'submitted': False,
                       'status': 'COMPILED_DRAFT', 'reasons': [],
                       'payload_draft': {'prompt': '原创双镜头本地交付'},
                       'scope': {'shot_ids': ['S1', 'S2'], 'start_ms': 0, 'end_ms': 2000}}
            compiled, compile_sha = _compiled(root, request)
            job = bridge.plan_job(request, compile_sha, [], ['S1', 'S2'],
                                  {'max_attempts': 1, 'project_cap': 1}, compile_path=compiled)
            plan = freeze_plan([{'id': 'C', 'level': 'hard', 'checks': ['visible'],
                                 'shot_ids': []}])
            spec = {'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True}
            bridge.freeze_delivery(['S1', 'S2'], plan, [], spec,
                shot_ranges={'S1': {'start_ms': 0, 'end_ms': 1000},
                             'S2': {'start_ms': 1000, 'end_ms': 2000}})
            source = root/'local.mp4'
            _media(source)
            proof = root/'external-receipt.txt'
            proof.write_text('Synthetic local media fixture', encoding='utf-8')
            evidence = {'channel': 'manual', 'external_task_id': 'LOCAL_FIXTURE_1',
                        'request_id': job['request_id'], 'payload_sha256': job['payload_sha256'],
                        'attachment_sha256s': [], 'proof_uri': str(proof),
                        'proof_sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}
            take = bridge.receive_take(job['id'], source, _probe(source), evidence)['take']
            observation = [{'id': 'C', 'result': 'PASS', 'evidence': 'fixture human judgment'}]
            for shot in ('S1', 'S2'):
                decision = shot_decision(plan, observation, shot, plan['sha256'])
                decision.update(id='ACC_'+shot, take_ids={shot: take['id']})
                pending = bridge.review_take(decision)
                self._accept_review_fixture(bridge, pending, [take['uri']])
                pending = bridge.select_take(shot, take['id'])
                self._accept_review_fixture(bridge, pending, [take['uri']])
            adjacent = adjacent_decision(plan, observation, 'S1', 'S2', plan['sha256'])
            adjacent['id'] = 'ACC_S1_S2'
            pending = bridge.check_adjacent(adjacent)
            self._accept_review_fixture(bridge, pending, [take['uri']])
            edl = [{'shot_id': shot, 'take_id': take['id'],
                    'source': str(bridge.runtime.path(take['uri'])), 'src_in_frame': 0,
                    'src_out_frame': 24, 'fps': 24, 'record_in_frame': index*24}
                   for index, shot in enumerate(('S1', 'S2'))]
            assembled = bridge.assemble(edl, root/'assembled.mp4', spec)
            self.assertEqual(assembled['status'], 'CHECKED')
            self.assertEqual(bridge.runtime.kernel.snapshot()['tasks'][
                bridge._task_id('assembly', bridge._project_scope())]['state'], 'ACCEPTED')
            self.assertEqual(bridge.deliver()['status'], 'BLOCKED')
            sequence = decide(plan, observation, frozen_sha256=plan['sha256'])
            sequence.update(id='ACC_SEQUENCE', level='sequence')
            pending = bridge.review_sequence(sequence)
            self._accept_review_fixture(bridge, pending, [assembled['assembly']['output_uri']])
            self.assertEqual(bridge.ledger.video_delivery_blockers(), [])
            # The fixture supplies the preproduction predecessor only; this patch
            # isolates the production graph's final transition from native IR QA.
            with patch.object(bridge.runtime, 'validate', return_value={'valid': True, 'errors': []}):
                delivered = bridge.deliver()
            self.assertEqual(delivered['status'], 'VIDEO_DELIVERED')
            self.assertEqual(bridge.runtime.kernel.inspect(delivered['task_id'])['state'], 'ACCEPTED')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_bridge_freeze_host_recovery_and_pending_independent_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = self._bridge(root/'project')
            request = {'id': 'REQUEST_2SHOT', 'submitted': False, 'status': 'COMPILED_DRAFT',
                       'reasons': [], 'payload_draft': {'prompt': '原创双镜头'},
                       'scope': {'shot_ids': ['S1', 'S2'], 'start_ms': 0, 'end_ms': 2000}}
            compiled, digest = _compiled(root, request)
            job = bridge.plan_job(request, digest, [], ['S1', 'S2'],
                                  {'max_attempts': 1, 'project_cap': 1}, compile_path=compiled)
            plan = freeze_plan([{'id': 'C', 'level': 'hard', 'checks': ['visible'],
                                 'shot_ids': []}])
            frozen = bridge.freeze_delivery(['S1', 'S2'], plan, [],
                            {'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True},
                            shot_ranges={'S1': {'start_ms': 0, 'end_ms': 1000},
                                         'S2': {'start_ms': 1000, 'end_ms': 2000}})
            self.assertEqual(frozen['v6_task']['status'], 'ACCEPTED')
            source = root/'local.mp4'
            _media(source)
            proof = root/'receipt.txt'
            proof.write_text('Original manual local execution receipt')
            evidence = {'channel': 'manual', 'external_task_id': 'LOCAL_ORIGINAL_1',
                        'request_id': job['request_id'], 'payload_sha256': job['payload_sha256'],
                        'attachment_sha256s': [], 'proof_uri': str(proof),
                        'proof_sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}
            received = bridge.receive_take(job['id'], source, _probe(source), evidence)
            take = received['take']
            stages = bridge.status()['v6_tasks']
            self.assertEqual({row['node_id'] for row in stages.values() if row['state'] == 'ACCEPTED'},
                             {'preproduction_delivery', 'video_freeze', 'video_execution', 'take_recovery'})
            observation = [{'id': 'C', 'result': 'PASS', 'evidence': 'local observer proposal'}]
            decision = shot_decision(plan, observation, 'S1', plan['sha256'])
            decision.update(id='ACC_S1', take_ids={'S1': take['id']})
            pending = bridge.review_take(decision)
            self.assertEqual(pending['status'], 'PENDING_REVIEW')
            self.assertEqual(pending['action']['tool'], 'collaboration.spawn_agent')
            with self.assertRaisesRegex(ValueError, 'task is not running'):
                bridge.runtime.agent_result({'task_id': pending['task_id']}, command_id='fake-result',
                    expected_revision=bridge.runtime.kernel.snapshot()['revision'])
            self.assertEqual(bridge.review_take(decision)['task_id'], pending['task_id'])
            with self.assertRaisesRegex(ValueError, 'frozen stage'):
                bridge.review_take({**decision, 'id': 'ACC_OTHER'})
            old_envelope = bridge.runtime.kernel.inspect(pending['task_id'])['envelope']
            intent_uri = next(row['uri'] for row in old_envelope['inputs']
                              if row['slot'] == 'production_intent')
            bridge.runtime.path(intent_uri).write_text('{"changed":"old task input"}')
            bridge._transition(pending['task_id'], 'STALE', 'INPUT_CHANGED', evidence=[intent_uri])
            fresh = bridge.review_take(decision)
            self.assertNotEqual(fresh['task_id'], pending['task_id'])
            self.assertEqual(fresh['action']['tool'], 'collaboration.spawn_agent')
            with self.assertRaisesRegex(ValueError, 'first pass its shot review'):
                bridge.select_take('S1', take['id'])
            self.assertEqual(bridge.deliver()['status'], 'BLOCKED')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_submitted_execution_remains_auditable_after_take_changes_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = self._bridge(root/'project')
            request = {'id': 'REQUEST_UPDATE', 'submitted': False,
                       'status': 'COMPILED_DRAFT', 'reasons': [],
                       'payload_draft': {'prompt': '本地一镜头'},
                       'scope': {'shot_ids': ['S1'], 'start_ms': 0, 'end_ms': 1000}}
            compiled, digest = _compiled(root, request)
            job = bridge.plan_job(request, digest, [], ['S1'],
                                  {'max_attempts': 1, 'project_cap': 1}, compile_path=compiled)
            plan = freeze_plan([{'id': 'C', 'level': 'hard', 'checks': ['visible'],
                                 'shot_ids': ['S1']}])
            bridge.freeze_delivery(['S1'], plan, [],
                {'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True},
                shot_ranges={'S1': {'start_ms': 0, 'end_ms': 1000}})
            source = root/'source.mp4'
            _media(source)
            proof = root/'submission.txt'
            proof.write_text('Original submission ID observed', encoding='utf-8')
            started = bridge.ledger.begin_submit(job['id'], automatic=False)
            submitted = bridge.ledger.register_external_execution(started['id'],
                {'channel': 'manual', 'external_task_id': 'ORIGINAL_ID',
                 'request_id': job['request_id'], 'payload_sha256': job['payload_sha256'],
                 'attachment_sha256s': [], 'proof_uri': str(proof),
                 'proof_sha256': hashlib.sha256(proof.read_bytes()).hexdigest()})
            accepted = bridge._execution_stage(submitted)
            self.assertEqual(accepted['status'], 'ACCEPTED')
            take = bridge.ledger.save_take(job['id'], started['id'], source, _probe(source),
                                           automatic=False)
            recovered = bridge._take_stage(take)
            self.assertEqual(recovered['status'], 'ACCEPTED')
            self.assertEqual(bridge.ledger.validate_production_integrity(), [])
            self.assertEqual(bridge.runtime.kernel.recover()['tasks'][accepted['task_id']]['state'],
                             'ACCEPTED')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_accepted_execution_downgrade_stales_then_recovers_original_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = self._bridge(root/'project')
            request = {'id': 'REQUEST_RECOVER', 'submitted': False,
                       'status': 'COMPILED_DRAFT', 'reasons': [],
                       'payload_draft': {'model': 'agnes-video-2.5-flash',
                                         'mode': 'text', 'prompt': '原创本地恢复'},
                       'scope': {'shot_ids': ['S1'], 'start_ms': 0, 'end_ms': 1000}}
            compiled, digest = _compiled(root, request)
            job = bridge.plan_job(request, digest, [], ['S1'],
                                  {'max_attempts': 1, 'project_cap': 1}, compile_path=compiled)
            plan = freeze_plan([{'id': 'C', 'level': 'hard', 'checks': ['visible'],
                                 'shot_ids': ['S1']}])
            bridge.freeze_delivery(['S1'], plan, [],
                {'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True},
                shot_ranges={'S1': {'start_ms': 0, 'end_ms': 1000}})
            source = root/'source.mp4'
            _media(source)
            started = bridge.ledger.begin_submit(job['id'], automatic=True)
            submitted = bridge.ledger.mark_submitted(started['id'], 'ORIGINAL_PROVIDER_TASK')
            original = bridge._execution_stage(submitted)
            bridge.ledger.mark_unknown(started['id'], 'poll connection lost')
            # Simulate a crash after the ledger write and before graph invalidation.
            self.assertEqual(bridge.runtime.kernel.inspect(original['task_id'])['state'], 'ACCEPTED')
            self.assertIn(original['task_id'], bridge.reconcile_execution_state()['stale_task_ids'])
            self.assertEqual(bridge.runtime.kernel.inspect(original['task_id'])['state'], 'STALE')

            class Transport:
                submits = 0
                polls = []
                def submit(self, payload, key):
                    self.submits += 1
                    raise AssertionError('Recovery must not submit a second generation')
                def poll(self, task_id, key, model=None):
                    self.polls.append(task_id)
                    return 'fixture-media'
                def download(self, remote, dest):
                    shutil.copyfile(source, dest)
                def probe(self, dest):
                    return _probe(dest)

            transport = Transport()
            previous = os.environ.get('AGNES_API_KEY')
            os.environ['AGNES_API_KEY'] = 'test-only'
            try:
                recovered = bridge.recover_execution(started['id'], root/'recovered.mp4', transport)
            finally:
                if previous is None:
                    os.environ.pop('AGNES_API_KEY', None)
                else:
                    os.environ['AGNES_API_KEY'] = previous
            self.assertEqual(recovered['status'], 'SUCCEEDED')
            self.assertEqual(transport.submits, 0)
            self.assertEqual(transport.polls, ['ORIGINAL_PROVIDER_TASK'])
            latest = bridge._current_task_id('video_execution',
                         bridge._scope('generation_request', started['id']))
            self.assertNotEqual(latest, original['task_id'])
            current = bridge.runtime.kernel.inspect(latest)
            self.assertEqual(current['state'], 'ACCEPTED')
            self.assertIn('original_call_recovery', {row['slot'] for row in current['envelope']['inputs']})
            recovery = next(row for row in current['envelope']['inputs']
                            if row['slot'] == 'original_call_recovery')
            self.assertEqual(json.loads(bridge.runtime.path(recovery['uri']).read_text())['provider_task_id'],
                             'ORIGINAL_PROVIDER_TASK')
            self.assertEqual(bridge.ledger.validate_production_integrity(), [])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_status_replays_downgrade_even_after_ledger_recovered_before_graph_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = self._bridge(root/'project')
            request = {'id': 'REQUEST_CRASH_WINDOW', 'submitted': False,
                       'status': 'COMPILED_DRAFT', 'reasons': [],
                       'payload_draft': {'prompt': '本地中断恢复'},
                       'scope': {'shot_ids': ['S1'], 'start_ms': 0, 'end_ms': 1000}}
            compiled, digest = _compiled(root, request)
            job = bridge.plan_job(request, digest, [], ['S1'],
                                  {'max_attempts': 1, 'project_cap': 1}, compile_path=compiled)
            plan = freeze_plan([{'id': 'C', 'level': 'hard', 'checks': ['visible'],
                                 'shot_ids': ['S1']}])
            bridge.freeze_delivery(['S1'], plan, [],
                {'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True},
                shot_ranges={'S1': {'start_ms': 0, 'end_ms': 1000}})
            source = root/'source.mp4'
            _media(source)
            started = bridge.ledger.begin_submit(job['id'], automatic=False)
            proof = root/'external.txt'
            proof.write_text('original external task', encoding='utf-8')
            submitted = bridge.ledger.register_external_execution(started['id'],
                {'channel': 'manual', 'external_task_id': 'EXTERNAL_ORIGINAL',
                 'request_id': job['request_id'], 'payload_sha256': job['payload_sha256'],
                 'attachment_sha256s': [], 'proof_uri': str(proof),
                 'proof_sha256': hashlib.sha256(proof.read_bytes()).hexdigest()})
            original = bridge._execution_stage(submitted)
            bridge.ledger.mark_unknown(started['id'], 'result lookup interrupted')
            take = bridge.ledger.save_take(job['id'], started['id'], source, _probe(source),
                                           automatic=False)
            self.assertEqual(bridge.ledger._load('executions/'+started['id']+'.json')['state'], 'SUCCEEDED')
            old_take_stage = bridge._take_stage(take)
            bridge.status()  # read/recovery entry point repairs the missed graph event
            self.assertEqual(bridge.runtime.kernel.inspect(original['task_id'])['state'], 'STALE')
            self.assertEqual(bridge.runtime.kernel.inspect(old_take_stage['task_id'])['state'], 'STALE')
            accepted = bridge._execution_stage(bridge.ledger._load('executions/'+started['id']+'.json'))
            fresh_take_stage = bridge._take_stage(take)
            self.assertNotEqual(accepted['task_id'], original['task_id'])
            self.assertNotEqual(fresh_take_stage['task_id'], old_take_stage['task_id'])
            self.assertEqual(bridge.runtime.kernel.inspect(accepted['task_id'])['state'], 'ACCEPTED')

    def test_compile_identity_and_execution_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kernel = _strict_kernel(root / 'project')
            ledger = ProductionLedger(kernel)
            request = {'id': 'REQUEST_1', 'submitted': False, 'status': 'COMPILED_DRAFT', 'reasons': [],
                       'payload_draft': {'prompt': '信封'},
                       'scope': {'shot_ids': ['S1'], 'start_ms': 0, 'end_ms': 1000}}
            compiled, digest = _compiled(root, request)
            with self.assertRaisesRegex(ValueError, 'compiled manifest'):
                ledger.plan_job(request, digest, [], ['S1'], {'max_attempts': 1, 'project_cap': 1})
            with self.assertRaisesRegex(ValueError, 'exact member'):
                ledger.plan_job({**request, 'id': 'REQUEST_2'}, digest, [], ['S1'],
                                {'max_attempts': 1, 'project_cap': 1}, compile_path=compiled)
            with self.assertRaisesRegex(ValueError, 'budget authorization'):
                ledger.plan_job(request, digest, [], ['S1'],
                                {'max_attempts': 2, 'project_cap': 2}, compile_path=compiled)
            with self.assertRaisesRegex(ValueError, 'budget authorization'):
                ledger.plan_job(request, digest, [], ['S1'],
                                {'max_attempts': 2, 'project_cap': 2,
                                 'authorization': 'free text is not approval'}, compile_path=compiled)
            job = ledger.plan_job(request, digest, [], ['S1'], {'max_attempts': 1, 'project_cap': 1}, compile_path=compiled)
            outside = freeze_plan([{'id': 'X', 'level': 'hard', 'checks': ['visible'], 'shot_ids': ['S2']}])
            with self.assertRaisesRegex(ValueError, 'outside frozen delivery scope'):
                ledger.freeze_delivery_manifest(['S1'], outside, output_spec={'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True},
                                                shot_ranges={'S1': {'start_ms': 0, 'end_ms': 1000}})
            inside = freeze_plan([{'id': 'X', 'level': 'hard', 'checks': ['visible'], 'shot_ids': ['S1']}])
            with self.assertRaisesRegex(ValueError, 'project time range'):
                ledger.freeze_delivery_manifest(['S1'], inside, output_spec={'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True})
            with self.assertRaisesRegex(ValueError, 'outside every compiled execution request'):
                ledger.freeze_delivery_manifest(['S1'], inside, output_spec={'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True},
                                                shot_ranges={'S1': {'start_ms': 0, 'end_ms': 2000}})
            record = ledger.begin_submit(job['id'], automatic=False)
            with self.assertRaisesRegex(ValueError, 'Failure evidence'):
                ledger.mark_failed(record['id'], '')
            ledger.mark_unknown(record['id'], 'manual receipt identity unresolved')
            with self.assertRaisesRegex(ValueError, 'Unresolved execution'):
                ledger.begin_submit(job['id'], automatic=False)
            with self.assertRaisesRegex(ValueError, 'Illegal execution transition'):
                ledger.mark_unknown(record['id'], 'again')
            self.assertEqual(ledger.validate_production_integrity(), [])
            compiled.write_text('{}')
            self.assertTrue(any('Job integrity' in error for error in ledger.validate_production_integrity()))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_unknown_external_call_recovers_same_task_without_resubmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kernel = _strict_kernel(root / 'project')
            ledger = ProductionLedger(kernel)
            source = root / 'source.mp4'
            _media(source)
            request = {'id': 'REQUEST_1', 'submitted': False, 'status': 'COMPILED_DRAFT', 'reasons': [],
                       'payload_draft': {'model': 'agnes-video-2.5-flash', 'mode': 'text', 'prompt': '信封'},
                       'scope': {'shot_ids': ['S1'], 'start_ms': 0, 'end_ms': 1000}}
            compiled, digest = _compiled(root, request)
            job = ledger.plan_job(request, digest, [], ['S1'], {'max_attempts': 1, 'project_cap': 1},
                                  compile_path=compiled)

            class Transport:
                base = 'https://apihub.agnes-ai.com/v1'
                submits = 0
                polls = 0

                def submit(self, payload, key):
                    self.submits += 1
                    return 'PROVIDER_TASK_1'

                def poll(self, task_id, key, model=None):
                    self.polls += 1
                    if self.polls == 1:
                        raise TimeoutError('network response lost')
                    self.assert_task_id = task_id
                    return 'provider-media'

                def download(self, remote, dest):
                    shutil.copyfile(source, dest)

                def probe(self, dest):
                    return _probe(dest)

            transport = Transport()
            executor = AgnesApiExecutor(ledger, transport)
            previous = os.environ.get('AGNES_API_KEY')
            os.environ['AGNES_API_KEY'] = 'test-only'
            try:
                first = executor.execute(job['id'], root / 'received.mp4')
                self.assertEqual(first['status'], 'UNKNOWN')
                with self.assertRaisesRegex(ValueError, 'Unresolved execution'):
                    executor.execute(job['id'], root / 'received.mp4')
                second = executor.finish(first['record_id'], root / 'received.mp4')
            finally:
                if previous is None:
                    os.environ.pop('AGNES_API_KEY', None)
                else:
                    os.environ['AGNES_API_KEY'] = previous
            self.assertEqual(second['status'], 'SUCCEEDED')
            self.assertEqual(transport.submits, 1)
            self.assertEqual(transport.assert_task_id, 'PROVIDER_TASK_1')
            self.assertEqual(ledger.validate_production_integrity(), [])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_post_audio_track_is_byte_frozen_and_present_in_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source.mp4'
            _media(source)
            audio = root/'post.wav'
            subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                                   'sine=frequency=660:sample_rate=48000:duration=1', str(audio)])
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            edl = [{'shot_id': 'S1', 'take_id': 'TAKE_1', 'source': str(source),
                    'src_in_frame': 0, 'src_out_frame': 24, 'fps': 24,
                    'record_in_frame': 0}]
            spec = {'width': 64, 'height': 64, 'fps': 24,
                    'post_audio': [{'source': str(audio), 'sha256': digest, 'start_ms': 100,
                                    'gain': 0.5}]}
            output = root/'assembled.mp4'
            result = assemble_ffmpeg(edl, output, spec)
            self.assertEqual(result['status'], 'CHECKED')
            self.assertGreater(result['probe']['audio_streams'], 0)
            audio.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Post audio bytes'):
                assemble_ffmpeg(edl, root/'rejected.mp4', spec)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Local ffmpeg is required')
    def test_full_coverage_selected_takes_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kernel = _strict_kernel(root / 'project')
            ledger = ProductionLedger(kernel)
            request = {'id': 'REQUEST_1', 'submitted': False, 'status': 'COMPILED_DRAFT', 'reasons': [],
                       'payload_draft': {'prompt': '两镜头'},
                       'scope': {'shot_ids': ['S1', 'S2'], 'start_ms': 0, 'end_ms': 2000}}
            compiled, digest = _compiled(root, request)
            approval = root / 'budget-approval.json'
            approval.write_text(json.dumps({'decision': 'APPROVED', 'request_id': request['id'],
                                            'max_attempts': 2, 'project_cap': 2,
                                            'actor': 'test budget owner', 'evidence': 'local test approval'}))
            job = ledger.plan_job(request, digest, [], ['S1', 'S2'],
                                  {'max_attempts': 2, 'project_cap': 2, 'authorization': str(approval)},
                                  compile_path=compiled)
            plan = freeze_plan([{'id': 'CONTINUITY', 'level': 'hard', 'requirement': '信封归属连续',
                                 'acceptance': '画面可见', 'checks': ['hand'], 'shot_ids': []}])
            ledger.freeze_delivery_manifest(['S1', 'S2'], plan, [{'id': 'AUDIO', 'kind': 'audio'}],
                                            {'width': 64, 'height': 64, 'fps': 24, 'preserve_native_audio': True},
                                            shot_ranges={'S1': {'start_ms': 0, 'end_ms': 1000},
                                                         'S2': {'start_ms': 1000, 'end_ms': 2000}})
            selected = {}
            for shot, frequency in [('S1', 440), ('S2', 550)]:
                source = root / (shot + '.mp4')
                _media(source, frequency)
                proof = root / (shot + '-receipt.txt')
                proof.write_text('Local external execution for ' + shot)
                evidence = {'channel': 'manual', 'external_task_id': 'EXTERNAL_' + shot,
                            'request_id': job['request_id'], 'payload_sha256': job['payload_sha256'],
                            'attachment_sha256s': [], 'proof_uri': str(proof),
                            'proof_sha256': hashlib.sha256(proof.read_bytes()).hexdigest()}
                received = ManualExecutor(ledger).receive(job['id'], source, _probe(source),
                                                          execution_evidence=evidence)
                selected[shot] = received['take']
            take = selected['S1']
            take_uri = 'runtime/production/takes/'+take['id']+'.json'
            snapshot_uri = 'runtime/v6/candidates/host-test/1/Take.json'
            kernel.write(snapshot_uri, take)
            host_candidate = {'host_record_uri': take_uri,
                              'host_record_sha256': hashlib.sha256(kernel.path(take_uri).read_bytes()).hexdigest(),
                              'artifacts': [{'kind': 'Take', 'uri': snapshot_uri}]}
            host_envelope = {'node_id': 'take_recovery', 'scope': {'kind': 'take', 'ids': [take['id']]},
                             'expected_artifacts': [{'kind': 'Take'}]}
            self.assertEqual(validate_host_node_candidate(kernel.root, host_envelope,
                             host_candidate)['status'], 'PASS')
            with self.assertRaisesRegex(ValueError, 'record bytes'):
                validate_host_node_candidate(kernel.root, host_envelope,
                                             {**host_candidate, 'host_record_sha256': '0'*64})
            with self.assertRaisesRegex(ValueError, 'first pass its shot review'):
                ledger.select_take('S1', selected['S1']['id'])
            self.assertTrue(any('Selected take missing' in error for error in ledger.video_delivery_blockers()))
            observation = [{'id': 'CONTINUITY', 'result': 'PASS', 'evidence': 'independent local review'}]
            for shot in ('S1', 'S2'):
                decision = shot_decision(plan, observation, shot, plan['sha256'])
                decision['id'] = 'ACC_' + shot
                decision['take_ids'] = {shot: selected[shot]['id']}
                ledger.save_acceptance(decision)
                ledger.select_take(shot, selected[shot]['id'])
            self.assertTrue(any('Acceptance' in error for error in ledger.video_delivery_blockers()))
            adjacent = adjacent_decision(plan, observation, 'S1', 'S2', plan['sha256'])
            adjacent['id'] = 'ACC_S1_S2'
            ledger.save_acceptance(adjacent)
            edl = []
            for index, shot in enumerate(('S1', 'S2')):
                take = selected[shot]
                edl.append({'shot_id': shot, 'take_id': take['id'],
                            'source': str(kernel.path(take['uri'])), 'src_in_frame': 0,
                            'src_out_frame': 24, 'fps': 24, 'record_in_frame': index * 24})
            output = root / 'sequence.mp4'
            result = assemble_ffmpeg(edl, output, {'width': 64, 'height': 64, 'fps': 24})
            self.assertEqual(result['status'], 'CHECKED')
            self.assertGreater(result['probe']['audio_streams'], 0)
            self.assertEqual(result['probe']['frames'], 48)
            record = {'id': 'ASM_1', **timelines([], [], []), 'edl': edl,
                      'tool': 'ffmpeg', 'status': result['status'], 'probe': result['probe'],
                      'output_sha256': result['output_sha256']}
            short = root / 'short.mp4'
            subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-i', str(output),
                                   '-vf', 'trim=end_frame=47,setpts=PTS-STARTPTS', '-an', str(short)])
            with self.assertRaisesRegex(ValueError, 'decoded frame count'):
                ledger.save_assembly({**record, 'id': 'ASM_SHORT', 'probe': _probe(short),
                                      'output_sha256': hashlib.sha256(short.read_bytes()).hexdigest()},
                                     output_path=short)
            silent = root / 'silent.mp4'
            subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-i', str(output), '-map', '0:v:0',
                                   '-c:v', 'copy', '-an', str(silent)])
            with self.assertRaisesRegex(ValueError, 'silently dropped native audio'):
                ledger.save_assembly({**record, 'id': 'ASM_SILENT', 'probe': _probe(silent),
                                      'output_sha256': hashlib.sha256(silent.read_bytes()).hexdigest()},
                                     output_path=silent)
            ledger.save_assembly(record, output_path=output)
            sequence = decide(plan, observation, frozen_sha256=plan['sha256'])
            sequence.update({'id': 'ACC_SEQUENCE', 'level': 'sequence'})
            ledger.save_acceptance(sequence)
            self.assertTrue(any('Post obligation' in error for error in ledger.video_delivery_blockers()))
            ledger.save_post_obligation('AUDIO', {'status': 'PASS', 'uri': str(output),
                                                  'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
            self.assertEqual(ledger.video_delivery_blockers(), [])
            for filename in ('ACC_S1.json', 'ACC_S1_S2.json'):
                missing_path = ledger._path('acceptance/' + filename)
                original = missing_path.read_bytes()
                missing_path.unlink()
                self.assertTrue(any('does not cover every shot, adjacent pair' in error
                                    for error in ledger.video_delivery_blockers()))
                missing_path.write_bytes(original)
            plan_path = ledger._path('acceptance-plans/' + plan['sha256'] + '.json')
            original_plan = plan_path.read_bytes()
            bad_plan = json.loads(original_plan)
            bad_plan['items'][0]['requirement'] = 'tampered after freeze'
            plan_path.write_text(json.dumps(bad_plan))
            self.assertTrue(any('Frozen delivery manifest' in error for error in ledger.video_delivery_blockers()))
            plan_path.write_bytes(original_plan)
            selection_path = ledger._path('selections/S1.json')
            original_selection = selection_path.read_bytes()
            wrong_selection = json.loads(original_selection)
            wrong_selection['take_id'] = selected['S2']['id']
            wrong_selection['take_sha256'] = selected['S2']['sha256']
            selection_path.write_text(json.dumps(wrong_selection))
            self.assertTrue(any('non-selected take' in error or 'outdated or unselected take' in error
                                for error in ledger.video_delivery_blockers()))
            selection_path.write_bytes(original_selection)
            decision_path = ledger._path('acceptance/ACC_SEQUENCE.json')
            original_decision = decision_path.read_bytes()
            bad_decision = json.loads(original_decision)
            bad_decision['level'] = 'unknown'
            decision_path.write_text(json.dumps(bad_decision))
            self.assertTrue(any('Acceptance' in error for error in ledger.video_delivery_blockers()))
            decision_path.write_bytes(original_decision)
            output_record = ledger._load('assembly/ASM_1.json')
            kernel.path(output_record['output_uri']).write_bytes(b'tampered')
            self.assertTrue(any('Assembly invalid' in error for error in ledger.video_delivery_blockers()))


if __name__ == '__main__':
    unittest.main()
