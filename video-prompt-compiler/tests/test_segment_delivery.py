"""Regression checks for model-sized, independently copyable prompt files."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from segment_delivery import _durations
import spatial_runtime as spatial
from vpc import run_compile, verify
from vpc_core import profile


class SegmentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.source = ROOT / 'examples/v52/cafe.avir.json'
        self.ir = json.loads(self.source.read_text(encoding='utf-8'))
        self.temp = tempfile.TemporaryDirectory(prefix='vpc-segments-')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def test_model_duration_partition_and_unverified_limit(self):
        self.assertEqual(_durations(60000, profile('seedance2.0')['duration_ms'])[0], [15000] * 4)
        self.assertEqual(_durations(60000, profile('seedance2.5')['duration_ms'])[0], [30000] * 2)
        self.assertEqual(_durations(17000, profile('seedance2.0')['duration_ms'])[0], [13000, 4000])
        self.assertEqual(_durations(12000, profile('veo3.1')['duration_ms'])[0], [8000, 4000])
        self.assertEqual(_durations(15000, profile('veo3.1')['duration_ms'])[1], 'NO_SUPPORTED_DURATION_PARTITION')
        self.assertEqual(_durations(60000, profile('wan3.0')['duration_ms'])[1], 'DURATION_CAP_UNVERIFIED')

    def test_single_file_repeats_real_reference_and_verifies_bytes(self):
        image = self.out / '角色参考.png'
        image.write_bytes(b'synthetic-reference-for-binding-test')
        self.ir['assets'].append({'id': 'REF', 'kind': 'image', 'filename': image.name,
                                  'path': str(image), 'sha256': sha256(image.read_bytes()).hexdigest(),
                                  'public_url': None, 'inspection': 'observed', 'source_refs': ['DESIGN']})
        self.ir['bindings'].append({'id': 'B_REF', 'asset_id': 'REF', 'target_id': 'A',
                                    'shot_ids': ['S1', 'S2', 'S3'], 'roles': ['identity'],
                                    'negative_roles': ['scene'], 'source_refs': ['DESIGN']})
        self.ir['timeline']['semantic_review']['input_sha256'] = spatial.content_hash(self.ir)
        package = self.out / 'single'
        run_compile(self.ir, 'seedance2.0', 'reference', self.source.parent, package)
        delivery = json.loads((package / 'segment-delivery.json').read_text(encoding='utf-8'))
        self.assertEqual(len(delivery['parts']), 1)
        part = delivery['parts'][0]
        self.assertEqual(part['status'], 'DRAFT_REQUIRES_TARGET_CHECK')
        self.assertEqual([row['filename'] for row in part['reference_files']], ['角色参考.png'])
        prompt = (package / part['prompt_file']).read_text(encoding='utf-8')
        self.assertIn('制作规格：12秒', prompt)
        self.assertIn('角色参考.png', prompt)
        self.assertIn('【镜头 S1', prompt)
        self.assertIn('【镜头 S3', prompt)
        self.assertIn('【动作', prompt)
        self.assertIn('【摄影机操作', prompt)
        self.assertGreater(part['prompt_coverage_count'], 0)
        self.assertEqual(len(json.loads((package / part['prompt_coverage_file']).read_text(encoding='utf-8'))),
                         part['prompt_coverage_count'])
        verify(package)
        (package / part['prompt_file']).write_text(prompt.replace('角色参考.png', '丢失.png'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'E_PACKAGE_CHANGED'):
            verify(package)

    def test_overlong_project_emits_all_parts_and_blocks_unsafe_seam(self):
        cap = deepcopy(profile('seedance2.0'))
        cap['duration_ms']['max'] = 6000
        package = self.out / 'split'
        with patch('vpc.profile', return_value=cap):
            run_compile(self.ir, 'seedance2.0', 'text', self.source.parent, package)
        delivery = json.loads((package / 'segment-delivery.json').read_text(encoding='utf-8'))
        self.assertEqual([(p['project_start_ms'], p['project_end_ms']) for p in delivery['parts']],
                         [(0, 6000), (6000, 12000)])
        self.assertEqual(delivery['status'], 'BLOCKED')
        self.assertTrue(all(p['prompt_file'].startswith('BLOCKED-') for p in delivery['parts']))
        self.assertTrue(any('NEEDS_KEY_POSE' in reason or 'NEEDS_EXPLICIT_PHASE_SLICE' in reason
                            for p in delivery['parts'] for reason in p['reasons']))
        for part in delivery['parts']:
            prompt = (package / part['prompt_file']).read_text(encoding='utf-8')
            self.assertIn('制作规格：6秒', prompt)
            self.assertGreater(part['prompt_coverage_count'], 0)
        self.assertTrue(any(p['post_file'] for p in delivery['parts']))
        verify(package)


if __name__ == '__main__':
    unittest.main()
