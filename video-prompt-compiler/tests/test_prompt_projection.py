"""The model prompt is a chronological projection with its own coverage."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prompt_projection as projection
import spatial_runtime as spatial
import vpc_core as core
from vpc import run_compile, verify


class PromptProjectionTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / 'examples/v52/cafe.avir.json'
        self.ir = json.loads(self.path.read_text())

    def compile(self, target='agnes-video-2.5'):
        return core.compile_ir(self.ir, core.profile(target), 'text', self.path.parent)[0]

    def test_shot_order_and_complete_execution_coverage(self):
        artifact = self.compile()
        self.assertEqual(artifact['status'], 'COMPILED')
        text = artifact['prompt']
        self.assertLess(text.index('【镜头 S1'), text.index('【镜头 S2'))
        self.assertLess(text.index('【镜头 S2'), text.index('【镜头 S3'))
        self.assertLess(text.index('0.5秒起：'), text.index('1秒起：'))
        self.assertLess(text.index('【空间与构图｜0–4秒】'), text.index('【动作 第1项动作'))
        self.assertEqual(text.count('场景：A与B相对而坐'), 1)
        self.assertLess(text.count('秒状态：'), len(self.ir['timeline']['state_samples']))
        covered = {row['source_path'] for row in artifact['prompt_coverage']}
        fields = {'actions': 'operation', 'camera_operations': 'operation',
                  'motion_tracks': 'property', 'composition_tracks': 'framing',
                  'spatial_relations': 'predicate'}
        for collection, field in fields.items():
            for i, item in enumerate(self.ir['timeline'][collection]):
                path = f'/timeline/{collection}/{i}'
                self.assertIn(path + '/' + field, covered, item['id'])

    def test_prompt_span_tamper_is_detected(self):
        artifact = self.compile()
        self.assertEqual(projection.verify(self.ir, artifact['prompt'], artifact['prompt_coverage'], spatial), [])
        changed = artifact['prompt'].replace('右手', '左手', 1)
        self.assertTrue(projection.verify(self.ir, changed, artifact['prompt_coverage'], spatial))

    def test_h3_keeps_its_documented_field_shape(self):
        artifact = self.compile('minimax-h3')
        self.assertEqual(artifact['status'], 'COMPILED')
        text = artifact['prompt']
        self.assertIn('integrated_multimodal_description:', text)
        self.assertIn('overall_soundscape:', text)
        self.assertIn('non_diegetic_music:', text)
        self.assertLess(text.index('integrated_multimodal_description:'), text.index('overall_soundscape:'))

    def test_seedance_kling_and_agnes_use_distinct_shot_layouts(self):
        blocks, coverage = spatial.render(self.ir)
        cases = [('seedance2.0', 'shot_timeline', '【镜头 S1'),
                 ('kling-v3', 'kling_multi_shot_plan', 'Shot 1 (4s): S1'),
                 ('agnes-video-2.5', 'single_prompt_timeline', '【镜头 S1')]
        for target, layout, heading in cases:
            with self.subTest(target=target):
                prompt, mapped, _, gaps = projection.render(
                    self.ir, [], target, 'text', spatial, blocks, coverage, layout=layout)
                self.assertEqual(gaps, [])
                self.assertIn(heading, prompt)
                self.assertIn('你确定？', prompt)
                self.assertIn('声音由后期制作', prompt)
                self.assertTrue(mapped)

    def test_h3_reference_field_shape_retains_filename(self):
        self.ir['assets'].append({'id': 'REF', 'filename': 'reference.jpg'})
        self.ir['bindings'].append({'id': 'B_REF', 'asset_id': 'REF', 'target_id': 'A',
                                    'roles': ['identity'], 'negative_roles': ['scene'],
                                    'shot_ids': ['S1']})
        blocks, coverage = spatial.render(self.ir)
        prompt, _, _, gaps = projection.render(
            self.ir, [{'id': 'REF', 'filename': 'reference.jpg'}], 'minimax-h3',
            'reference', spatial, blocks, coverage, layout='h3_fields')
        self.assertEqual(gaps, [])
        for field in ('subject_definitions:', 'summary:', 'retention_analysis:',
                      'detailed_description:', 'overall_soundscape:', 'non_diegetic_music:'):
            self.assertIn(field, prompt)
        self.assertIn('reference.jpg', prompt)

    def test_cli_sidecar_and_replay_inputs_are_coherent(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'compile'
            result, code = run_compile(self.ir, 'agnes-video-2.5', 'text', self.path.parent, out)
            self.assertEqual(code, 0, result)
            artifact = json.loads((out / 'artifact.json').read_text())
            self.assertEqual(json.loads((out / 'prompt-coverage.json').read_text()), artifact['prompt_coverage'])
            self.assertEqual(json.loads((out / 'prompt-review.json').read_text()), artifact['prompt_review'])
            self.assertEqual(artifact['prompt_review']['status'], 'PENDING_AGENT_REVIEW')
            self.assertEqual((out / 'prompt.txt').read_text(), artifact['prompt'] + '\n')
            self.assertEqual(verify(out)['compiler'], 'video-prompt-compiler@1.6.0')

    def test_segment_draft_uses_local_chronological_projection(self):
        self.ir['timeline']['segments'] = [{
            'id': 'PART_S1', 'start_ms': 0, 'end_ms': 4000, 'shot_ids': ['S1'],
            'status': 'accepted', 'continuous_shot': True, 'entry_state': '原镜头初态',
            'exit_state': 'S1明确终态', 'camera_continuity': '原机位',
            'audio_continuity': '后期轨全局执行', 'reference_plan': '保留同一参考',
            'overlap_ms': 0, 'cost_impact': '待目标核验'}]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'compile'
            run_compile(self.ir, 'agnes-video-2.5', 'text', self.path.parent, out)
            drafts = json.loads((out / 'segment-plan.json').read_text())
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]['status'], 'DRAFT_REQUIRES_TARGET_CHECK')
            self.assertIn('【镜头 S1', drafts[0]['prompt'])
            self.assertNotIn('【镜头 S2', drafts[0]['prompt'])
            self.assertTrue(drafts[0]['prompt_coverage'])
            self.assertEqual(drafts[0]['execution'], 'NOT_RUN')


if __name__ == '__main__':
    unittest.main()
