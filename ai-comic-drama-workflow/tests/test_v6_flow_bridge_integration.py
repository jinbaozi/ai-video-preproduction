"""Offline Flow bridge regression; no Google execution or visual-quality claim.

Seed the accepted upstream image predecessor and patch only the native catalogue
and preproduction valid/data boundary. Exercise real image decoding, receipt
acceptance, graph dependencies, host state transitions, candidate verification,
and replay without mocking any Flow or host-bridge verification function.
"""
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests import test_flow_references as flow_fixtures
from ai_comic_drama_workflow.flow import POLICY
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import digest_file
from ai_comic_drama_workflow.v6_runtime import V6Runtime
from ai_comic_drama_workflow.v6_stage_adapter import slot_for


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'Local ffmpeg/ffprobe required')
class FlowBridgeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flow_fixtures.FlowReferenceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        flow_fixtures.FlowReferenceTests.tearDownClass()

    def exercise_bridge(self, stage):
        fixture = flow_fixtures.FlowReferenceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        runtime = V6Runtime.initialize(Path(temporary.name) / 'project',
            ['Synthetic offline Flow bridge fixture'], delivery='full',
            flow_refinement={'policy': POLICY, 'max_attempts': 2})
        media = deepcopy(fixture.media)
        media['stage'] = stage
        if stage == 7:
            media['role'] = 'board'
        runtime.write(media['uri'], fixture.kernel.path(media['uri']).read_bytes())
        state = runtime.v5.state
        state['media'][media['key']] = media
        runtime.v5.save(state)
        upstream, kind, output = (('visual_media', 'asset', 'ReferenceImage')
                                 if stage == 5 else ('board_media', 'panel', 'BoardImage'))
        scope = {'kind': kind, 'ids': [media['key']]}
        slot = slot_for(upstream, scope, output)
        sha = digest_file(runtime.path(media['uri']))
        task_id = 'FIXTURE_IMAGE'

        def seed(state, artifacts):
            state['tasks'][task_id] = {
                'envelope': {'node_id': upstream, 'task_id': task_id, 'scope': scope,
                    'input_revision': 0, 'batch': 1, 'inputs': [], 'resources': [],
                    'dependencies': [], 'expected_artifacts': [{'slot': slot, 'kind': output}]},
                'state': 'ACCEPTED', 'version': 1, 'receipt': None,
                'receipt_history': [], 'review_dispatch': None, 'candidate': None,
                'review': None, 'validation': [], 'messages': [], 'history': [],
                'failure_counts': {}, 'evidence_hashes': {}}
            artifacts[slot] = {'slot': slot, 'kind': output, 'uri': media['uri'],
                'sha256': sha, 'task_id': task_id, 'batch': 1, 'candidate_digest': sha}

        runtime.kernel._apply('test_fixture', {'name': 'accepted_upstream_image'},
                              'fixture-image', 0, seed)
        jobs = lambda requested: [{'key': media['key']}] if requested == stage else []
        with patch.object(V5Kernel, 'image_jobs', side_effect=jobs), \
             patch.object(V5Kernel, 'valid', return_value=True), \
             patch.object(V5Kernel, 'data', return_value={'scenes': []}):
            action = runtime.flow_action(media['key'], begin=True)
            self.assertEqual(action['status'], 'DISPATCHED')
            receipt = fixture.receipt(action)
            accepted = runtime.flow_action(media['key'], result=receipt)
            self.assertEqual(accepted['status'], 'ACCEPTED')
            expected = 'reference_2k' if stage == 5 else 'board_reference_2k'
            self.assertEqual(accepted['node_id'], expected)
            row = runtime.kernel.inspect(accepted['task_id'])
            self.assertEqual(row['state'], 'ACCEPTED')
            self.assertEqual(row['envelope']['dependencies'], [{'task_id': task_id}])
            before = runtime.v5.state
            revision = runtime.kernel.snapshot()['revision']
            replay = runtime.flow_action(media['key'], result=receipt)
            self.assertEqual(replay['status'], 'ALREADY_ACCEPTED')
            self.assertEqual(runtime.v5.state, before)
            self.assertEqual(runtime.kernel.snapshot()['revision'], revision)
            current = runtime.v5.state['media'][media['key']]
            runtime.path(current['uri']).write_bytes(b'tampered synthetic image')
            with self.assertRaisesRegex(ValueError, 'missing, changed or stale'):
                runtime.flow_action(media['key'], result=receipt)

    def test_asset_receive_replay_and_changed_output(self):
        self.exercise_bridge(5)

    def test_panel_receive_replay_and_changed_output(self):
        self.exercise_bridge(7)
