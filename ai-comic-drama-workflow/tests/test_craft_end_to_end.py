"""Run the authored text-only cafe fixture through real native validators and craft gates.

All author/review text here is SYNTHETIC TEST EVIDENCE, not a model or visual review.
No production bypass, no mocks of acceptance, no media or external model calls.
"""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from ai_comic_drama_workflow import craft_runtime as rt, craft_router as cr
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import ROOT, read, digest_file
sys.path.insert(0, str(ROOT/'tests'))
from test_v5_workflow import FIXTURE, result_for, review as handoff_review, submit_fixture, screenplay
from test_craft_routing import save, context, review


def content_pointer(value, prefix=''):
    candidates = []
    excluded = {'sources', 'source_refs', 'canon', 'canon_ref', 'review', 'checks', 'style',
                'contract', 'bindings', 'references', 'assets', 'rationale', 'uri', 'sha256'}
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in excluded:
                candidates += content_pointer(item, prefix+'/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            candidates += content_pointer(item, prefix+'/'+str(i))
    elif isinstance(value, str) and len(value) >= 12 and any('\u4e00' <= c <= '\u9fff' for c in value):
        candidates.append((prefix, value))
    return candidates


class CraftEndToEndTests(unittest.TestCase):
    def test_native_text_delivery_retains_craft_proofs_without_media_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            author = root/'author'
            shutil.copytree(FIXTURE, author)
            kernel = V5Kernel.initialize(root/'project', [str(author/'cafe.source.txt')],
                project_id='CAFE_DEMO', delivery='text-only', target='agnes-video-2.5', craft_policy=rt.POLICY)
            seen = []
            for _ in range(18):
                response = kernel.run()
                if response['status'] == 'DELIVERED':
                    break
                self.assertIn('task', response, response)
                task = response['task']
                kind = task['kind']; seen.append(kind)
                if kind in ('qa', 'control'):
                    submit_fixture(kernel, author, task)
                    continue
                if kind == 'compile-review':
                    artifact = read(kernel.path(task['build']['uri']+'/avir.json'))
                    candidates = content_pointer(artifact)
                    pointer = max(candidates, key=lambda v: len(v[1]))[0]
                    result = result_for(task, semantic_review={
                        'build_id': kernel.state['build']['build_id'], 'equivalent': True,
                        'clauses': [{'id': item, 'finding': 'SYNTHETIC fixture semantic finding '+item} for item in task.get('hard_clauses', [])],
                        'blocked': [{'id': item, 'disposition': 'held'} for item in task.get('blocked_segments', [])]},
                        craft_review=review(task['craft'], artifact, pointer))
                    kernel.submit(result)
                    ids = [row['id'] for row in task['craft']['inherited']]
                    for prefix in ('screenplay/', 'director/', 'art:CAFE/', 'storyboard/'):
                        self.assertTrue(any(identifier.startswith(prefix) for identifier in ids), (prefix, ids))
                    continue
                if kind == 'canon':
                    artifact = {'project_id': 'CAFE_DEMO', 'content': (author/'cafe.source.txt').read_text(),
                        'source_refs': [s['id'] for s in kernel.state['sources']],
                        'entities': [{'id': e['id']} for e in read(author/'director.json')['entities']], 'locks': []}
                elif kind == 'screenplay':
                    artifact = screenplay(kernel)
                else:
                    artifact = read(author/(kind+'.json'))
                extras = {}
                if kind in rt.CREATORS:
                    target = artifact
                    parts = task['craft']['native_primary_pointer'].split('/')[1:]
                    for part in parts[:-1]: target = target[part]
                    target[parts[-1]] = task['craft']['primary']
                    if kind == 'screenplay':
                        artifact['review']['content_sha256'] = kernel.screenplay_protocol().content_hash(artifact)
                    if kind == 'art':
                        artifact['director']['uri'] = str(author/'director.json')
                        artifact['director']['sha256'] = digest_file(author/'director.json')
                    candidates = content_pointer(artifact)
                    pointer = max(candidates, key=lambda v: len(v[1]))[0]
                    extras['craft_review'] = review(task['craft'], artifact, pointer)
                    if kind == 'director':
                        for scene in artifact['scenes']:
                            scene['style_id'] = task['craft']['primary']
                        features = context(kernel)['roles']
                        extras['craft_scene_routes'] = {
                            scene['id']: {'continuity_group': scene['location_id'],
                                'features': {r: features[r]['features'] for r in ('art', 'storyboard')},
                                'evidence': {'pointer': f'/scenes/{i}/space', 'quote': scene['space']}}
                            for i, scene in enumerate(artifact['scenes'])}
                else:
                    extras['craft_context'] = context(kernel)
                mapping = handoff_review(task, artifact)
                path = save(author/(kind+'.json'), artifact)
                kernel.submit(result_for(task, artifact=str(path), artifact_sha256=digest_file(path), handoff=mapping, **extras))
                self.assertTrue(kernel.valid(task['slot']), task['slot'])
            else:
                self.fail('The fixture did not converge')
            self.assertEqual(response['status'], 'DELIVERED')
            self.assertIn('compile-review', seen)
            self.assertEqual(kernel.state['media'], {})
            for slot in ('canon', 'screenplay', 'director', 'art:CAFE', 'storyboard'):
                self.assertTrue(kernel.state['artifacts'][slot].get('craft_proof'))
            final = kernel.validate(True)
            self.assertTrue(final['valid'], final)
            self.assertFalse(final['video_generated'])
            compiled = kernel.path(kernel.state['build']['uri'] + '/compiled')
            self.assertEqual(read(compiled/'compile-manifest.json')['template_ids'], ['dialogue-performance-beats'])
            self.assertEqual(read(compiled/'artifact.json')['prompt_techniques']['templates'][0]['id'], 'dialogue-performance-beats')
            self.assertFalse(read(compiled/'artifact.json')['prompt_techniques']['execution']['submitted'])
            community = read(compiled/'artifact.json')['prompt_techniques']['community']
            self.assertTrue(community['cards'])
            self.assertTrue(all(r['reading']['read_status'] == 'READ_LOCAL_NOTE' for r in community['cards']))
            self.assertFalse(community['execution']['runnable'])


if __name__ == '__main__':
    unittest.main()
