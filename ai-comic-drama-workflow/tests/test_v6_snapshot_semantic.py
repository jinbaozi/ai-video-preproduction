"""Verified semantic reviews survive only source-preserving V5 snapshot rebases."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import digest_file, read
from ai_comic_drama_workflow.v51_detail_runtime import content_hash, semantic_status


class SnapshotSemanticTests(unittest.TestCase):
    def test_valid_review_rebinds_relocated_upstream_hash(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = V5Kernel.initialize(base/'project', ['原创资料。'], project_id='SNAPSHOT_TEST',
                                          delivery='text-only')
            source = base/'author'
            source.mkdir()
            (source/'input.txt').write_text('原创资料。', encoding='utf-8')
            (source/'upstream.json').write_text(json.dumps({'content': 'source'}, ensure_ascii=False),
                                                encoding='utf-8')
            value = {'timeline': {'semantic_review': {
                'status': 'PASS', 'reviewer': 'independent reviewer',
                'findings': ['Source and timing checked'], 'input_sha256': ''}},
                'sources': [{'uri': 'input.txt', 'sha256': digest_file(source/'input.txt')}],
                'upstreams': [{'uri': 'upstream.json',
                               'sha256': digest_file(source/'upstream.json')}]}
            value['timeline']['semantic_review']['input_sha256'] = content_hash(value)
            original = source/'storyboard.json'
            original.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            uri, _ = project.snapshot('storyboard', original)
            imported = read(project.root/uri)
            self.assertTrue(semantic_status(value))
            self.assertTrue(semantic_status(imported))
            self.assertNotEqual(value['upstreams'][0]['sha256'], imported['upstreams'][0]['sha256'])
            self.assertEqual(read(original), value)

    def test_stale_review_is_not_rebound(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = V5Kernel.initialize(base/'project', ['原创资料。'], project_id='SNAPSHOT_TEST',
                                          delivery='text-only')
            source = base/'bad.json'
            value = {'timeline': {'semantic_review': {'status': 'PASS',
                       'reviewer': 'reviewer', 'findings': ['claim'], 'input_sha256': '0' * 64}}}
            source.write_text(json.dumps(value), encoding='utf-8')
            uri, _ = project.snapshot('storyboard', source)
            self.assertFalse(semantic_status(read(project.root/uri)))


if __name__ == '__main__':
    unittest.main()
