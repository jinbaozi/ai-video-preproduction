"""V5.4 production ledger, acceptance and assembly. No live model calls."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from ai_comic_drama_workflow.acceptance import decide, freeze_plan, repair_task, sequence_blocks
from ai_comic_drama_workflow.assembly import validate_edl
from ai_comic_drama_workflow.executors.agnes_api import AgnesApiExecutor
from ai_comic_drama_workflow.executors.manual import ManualExecutor
from ai_comic_drama_workflow.executors.registry import require_execution
from ai_comic_drama_workflow.production import ProductionLedger, normalize_video_capabilities
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_protocol import validate_protocol


class DeliveryTests(unittest.TestCase):
    def test_missing_production_target_means_none_and_scopes_stay(self):
        project = {
            'schema_version': '5.0', 'workflow_id': 'ai-comic-drama-v5', 'project_id': 'PROJECT',
            'execution_mode': 'current-agent', 'delivery': 'full', 'mode': 'reference', 'max_shots_per_task': 5,
        }
        validate_protocol('project', project)
        with tempfile.TemporaryDirectory() as tmp:
            kernel = V5Kernel.initialize(Path(tmp)/'p', ['甲把信封递给乙。'], delivery='text-only', production_target='none')
            self.assertEqual(kernel.project['delivery'], 'text-only')
            self.assertEqual(kernel.production_target(), 'none')
            kernel.project.pop('production_target')
            self.assertEqual(kernel.production_target(), 'none')
            self.assertFalse(kernel.status()['video_complete'])

    def test_video_target_does_not_mark_export_as_video_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            kernel = V5Kernel.initialize(Path(tmp)/'p', ['甲把信封递给乙。'], delivery='full', production_target='video')
            self.assertEqual(kernel.status()['production_target'], 'video')
            self.assertNotEqual(kernel.status()['status'], 'VIDEO_DELIVERED')


def _kernel(tmp, target='video'):
    return V5Kernel.initialize(Path(tmp)/'p', ['甲把信封递给乙。'], delivery='text-only', production_target=target)


class _Transport:
    def __init__(self):
        self.body = b'frozen-bytes'
        self.submits = 0

    def fetch(self, url):
        return self.body

    def submit(self, payload, key):
        self.submits += 1
        raise TimeoutError('no task id')

    def poll(self, task_id, key):
        raise AssertionError('poll')

    def download(self, remote, dest):
        raise AssertionError('download')

    def probe(self, dest):
        return {}


class LedgerTests(unittest.TestCase):
    def test_unknown_submit_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            kernel = _kernel(tmp)
            ledger = ProductionLedger(kernel)
            request = {'id': 'REQUEST_001', 'submitted': False, 'payload_draft': {'model': 'agnes-video-2.5-flash', 'mode': 'text', 'prompt': '甲递出信封'}}
            job = ledger.plan_job(request, 'abc', [], ['S1'], {'max_attempts': 2, 'project_cap': 2})
            executor = AgnesApiExecutor(ledger, _Transport())
            import os
            os.environ['AGNES_API_KEY'] = 'test-key'
            try:
                first = executor.execute(job['id'], Path(tmp)/'out.mp4')
            finally:
                os.environ.pop('AGNES_API_KEY', None)
            self.assertEqual(first['status'], 'UNKNOWN')
            self.assertFalse(first['resubmit'])
            with self.assertRaises(ValueError):
                ledger.begin_submit(job['id'])
            self.assertEqual(len(ledger.records(job['id'])), 1)

    def test_manual_take_is_not_automatic(self):
        with tempfile.TemporaryDirectory() as tmp:
            kernel = _kernel(tmp)
            ledger = ProductionLedger(kernel)
            media = Path(tmp)/'take.mp4'
            media.write_bytes(b'video')
            digest = hashlib.sha256(b'video').hexdigest()
            request = {'id': 'REQUEST_001', 'submitted': False, 'payload_draft': {'prompt': 'x'}}
            job = ledger.plan_job(request, 'abc', [], ['S1'], {'max_attempts': 1, 'project_cap': 1})
            result = ManualExecutor(ledger).receive(job['id'], media, {'sha256': digest, 'duration_ms': 1000})
            self.assertFalse(result['automatic'])
            self.assertFalse(result['take']['automatic'])

    def test_unregistered_video_channel_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_video_capabilities([{'model': 'not-a-model', 'mode': 'text', 'surface': 'API'}])


class AcceptanceTests(unittest.TestCase):
    def test_frozen_threshold_and_undetermined_block_completion(self):
        plan = freeze_plan([{'id': 'HAND', 'level': 'hard', 'requirement': '乙左手持信', 'acceptance': '可见', 'checks': [], 'shot_ids': ['S3']}])
        changed = dict(plan)
        changed['sha256'] = 'loose'
        with self.assertRaises(ValueError):
            decide(plan, [{'id': 'HAND', 'result': 'PASS'}], frozen_sha256=changed['sha256'])
        decision = decide(plan, [], frozen_sha256=plan['sha256'])
        self.assertEqual(decision['status'], 'INCOMPLETE')
        self.assertEqual(decision['items'][0]['result'], 'UNDETERMINED')
        self.assertTrue(sequence_blocks([decision]))
        blocked = repair_task([{'owner': 'keyframe'}], '关键帧手部姿态', 2, 2)
        self.assertEqual(blocked['status'], 'BLOCKED_BUDGET')
        self.assertIn('交由后期完成', blocked['remedies'])


class AssemblyTests(unittest.TestCase):
    def test_implicit_retime_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_edl([{'take_id': 'T', 'src_in_frame': 0, 'src_out_frame': 10, 'fps': 24, 'record_in_frame': 0, 'speed': 1.2}])
        with self.assertRaises(ValueError):
            validate_edl([{'take_id': 'T', 'src_in_frame': 0, 'src_out_frame': 10, 'fps': 24, 'record_in_frame': 0, 'setpts': '2*PTS'}])


class EntryTests(unittest.TestCase):
    def test_unvalidated_backend_cannot_be_copied_into_execution(self):
        with self.assertRaises(ValueError):
            require_execution({'backend': 'prompt_plan', 'probe_passed': False, 'quality_validated': False})
        with self.assertRaises(ValueError):
            require_execution({'backend': 'agnes_api_draft', 'probe_passed': False, 'quality_validated': False})


if __name__ == '__main__':
    unittest.main()
