"""Offline graph and evidence-boundary regressions; no live media claims."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ai_comic_drama_workflow.v6_graph import configured_graph, project_graph, load_graph, stage_by_id
from ai_comic_drama_workflow.v6_stage_adapter import CHECKER_KINDS, graph_envelope_fields
from ai_comic_drama_workflow.v6_runtime import V6Runtime
from ai_comic_drama_workflow.v6_production_runtime import validate_host_node_candidate
from ai_comic_drama_workflow.flow import POLICY

class MediaGateTests(unittest.TestCase):
    def test_old_unfrozen_graph_keeps_25_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'project.json').write_text(json.dumps({}))
            graph = project_graph(directory)
            self.assertEqual(len(graph['nodes']), 25)
            self.assertIn('visual_media', stage_by_id(graph, 'storyboard')['depends_on'])
            self.assertIn('assembly', stage_by_id(graph, 'whole_acceptance')['depends_on'])

    def test_new_configured_graph_has_real_media_gates(self):
        graph = configured_graph({'flow_refinement': {'policy': POLICY}, 'editing_backend': 'jianying-headless'})
        self.assertEqual(len(graph['nodes']), 28)
        for node in ('reference_2k', 'board_reference_2k', 'jianying_edit'):
            self.assertTrue(all(check in CHECKER_KINDS for check in stage_by_id(graph, node)['checkers']))
        self.assertIn('reference_2k', stage_by_id(graph, 'storyboard')['depends_on'])
        self.assertIn('jianying_edit', stage_by_id(graph, 'whole_acceptance')['depends_on'])

    def test_frozen_graph_tampering_cannot_remove_required_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = V6Runtime.initialize(Path(directory)/'project', ['原创故事'], delivery='text-only', editing_backend='jianying-headless')
            self.assertIn('jianying_edit', [n['id'] for n in runtime.graph['nodes']])
            runtime.write('runtime/v6/workflow.json', configured_graph({}))
            with self.assertRaisesRegex(ValueError, 'Frozen workflow differs'):
                V6Runtime(runtime.root)

    def test_flow_claim_without_canonical_download_is_rejected(self):
        fake = type('Kernel', (), {'state': {'media': {}}})()
        with patch('ai_comic_drama_workflow.v6_production_runtime.V5Kernel', return_value=fake):
            with self.assertRaisesRegex(ValueError, 'verified downloaded media'):
                validate_host_node_candidate('/unused', {'node_id': 'reference_2k', 'scope': {'ids': ['ASSET_A']}}, {'checks': [{'status': 'PASS'}]})

    def test_reference_gate_adapter_blocks_unknown_predecessor(self):
        graph = load_graph()
        scope = {'kind': 'asset', 'ids': ['A']}
        row = {'state': 'UNKNOWN', 'version': 1, 'envelope': {'node_id': 'visual_media', 'scope': scope, 'task_id': 'IMAGE', 'input_revision': 1, 'batch': 1}}
        with self.assertRaisesRegex(ValueError, 'not complete'):
            graph_envelope_fields(graph, 'reference_2k', scope, 'FLOW', 1, [row], {'reference_2k': [scope], 'visual_media': [scope]})

    def test_exact_flow_replay_does_not_clear_downstream(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        media = {'flow_refinement': {'action_id': 'FLOW_fixture'}}
        state = {'media': {'A': media}, 'approvals': {'A': {'approved': True}},
                 'build': {'id': 'checked-build'}, 'compile_review': {'status': 'PASS'}}
        native = SimpleNamespace(state=state, media_valid=lambda value: True,
                                 image_jobs=lambda stage: [{'key': 'A'}], save=Mock())
        row = {'state': 'ACCEPTED', 'envelope': {}, 'candidate': {}}
        runtime = object.__new__(V6Runtime)
        runtime.root = Path('/unused')
        runtime.v5 = native
        runtime.graph = configured_graph({'flow_refinement': {'policy': POLICY}})
        runtime.kernel = SimpleNamespace(snapshot=lambda: {'tasks': {'V6F_FLOW_fixture': row}})
        runtime._scope_catalogue = lambda node: {}
        with patch('ai_comic_drama_workflow.v6_runtime.predecessor_task_ids', return_value=[]), \
             patch('ai_comic_drama_workflow.flow.accept_refinement', return_value=media), \
             patch('ai_comic_drama_workflow.flow.refinement_valid', return_value=True), \
             patch('ai_comic_drama_workflow.v6_production_runtime.validate_flow_candidate', return_value={'status': 'PASS'}):
            result = runtime._flow_action('A', result={'status': 'SUCCEEDED'})
        self.assertEqual(result['status'], 'ALREADY_ACCEPTED')
        native.save.assert_not_called()
        self.assertEqual(state['build'], {'id': 'checked-build'})
        self.assertIn('A', state['approvals'])
        self.assertEqual(state['compile_review'], {'status': 'PASS'})

    def test_missing_frozen_extension_graph_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = V6Runtime.initialize(Path(directory)/'project', ['原创故事'], delivery='text-only', editing_backend='jianying-headless')
            runtime.path('runtime/v6/workflow.json').unlink()
            with self.assertRaisesRegex(ValueError, 'missing its frozen workflow'):
                V6Runtime(runtime.root)
