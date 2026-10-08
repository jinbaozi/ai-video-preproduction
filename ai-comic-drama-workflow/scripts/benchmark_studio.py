#!/usr/bin/env python3
"""Compare V2 studio vs explicit legacy lean on authored native test content.

No LLM, paid provider, visual quality or production throughput measurement.
UTF-8 context/result bytes are measured, not tokens. Native validators run.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ai_comic_drama_workflow import minimal, workspace, craft_runtime as rt
from ai_comic_drama_workflow.lean import start
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import read, digest_file
from tests.test_craft_end_to_end import content_pointer
from tests.test_craft_routing import context, review, save
from tests.test_v5_workflow import FIXTURE, result_for, review as handoff_review, screenplay
from tests.test_minimal_core import core_result


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def run(profile):
    with tempfile.TemporaryDirectory(prefix='studio-benchmark-') as tmp:
        root = Path(tmp)
        author = root/'author'
        shutil.copytree(FIXTURE, author)
        started = time.perf_counter()
        kernel = V5Kernel.initialize(root/'project', [str(author/'cafe.source.txt')],
            project_id='CAFE_DEMO', delivery='text-only', target='agnes-video-2.5',
            workflow_profile='lean', output_policy=workspace.POLICY, context_policy=minimal.POLICY,
            craft_policy=rt.POLICY if profile=='lean' else 'off')
        stages = []
        for _ in range(18):
            response = kernel.run()
            if response['status'] == 'DELIVERED':
                break
            task = response['task']
            kind = task['kind']
            extras = {}
            if kind == 'compile-review':
                artifact = read(kernel.path(task['build']['uri']+'/avir.json'))
                result = result_for(task, semantic_review={
                    'build_id': task['build']['build_id'], 'equivalent': True,
                    'clauses': [{'id': item, 'finding': 'SYNTHETIC fixture semantic finding '+item}
                                for item in task.get('hard_clauses', [])],
                    'blocked': [{'id': item, 'disposition': 'held'} for item in task.get('blocked_segments', [])]})
                if task.get('craft'):
                    pointer = max(content_pointer(artifact), key=lambda v: len(v[1]))[0]
                    result['craft_review'] = review(task['craft'], artifact, pointer)
            else:
                if kind == 'canon':
                    artifact = {'project_id':'CAFE_DEMO','content':(author/'cafe.source.txt').read_text(),
                        'source_refs':[s['id'] for s in kernel.state['sources']],
                        'entities':[{'id':e['id']} for e in read(author/'director.json')['entities']], 'locks':[]}
                elif kind == 'screenplay':
                    artifact = screenplay(kernel)
                else:
                    artifact = read(author/(kind+'.json'))
                if kind == 'art':
                    artifact['director']['uri'] = str(author/'director.json')
                    artifact['director']['sha256'] = digest_file(author/'director.json')
                if task.get('craft') and kind in rt.CREATORS:
                    target = artifact
                    parts = task['craft']['native_primary_pointer'].split('/')[1:]
                    for part in parts[:-1]: target = target[part]
                    target[parts[-1]] = task['craft']['primary']
                    if kind == 'screenplay':
                        artifact['review']['content_sha256'] = kernel.screenplay_protocol().content_hash(artifact)
                    if kind == 'art':
                        artifact['director']['uri'] = str(author/'director.json')
                        artifact['director']['sha256'] = digest_file(author/'director.json')
                    pointer = max(content_pointer(artifact), key=lambda v: len(v[1]))[0]
                    extras['craft_review'] = review(task['craft'], artifact, pointer)
                    if kind == 'director':
                        for scene in artifact['scenes']: scene['style_id'] = task['craft']['primary']
                        features = context(kernel)['roles']
                        extras['craft_scene_routes'] = {scene['id']:{'continuity_group':scene['location_id'],
                            'features':{r:features[r]['features'] for r in ('art','storyboard')},
                            'evidence':{'pointer':f'/scenes/{i}/space','quote':scene['space']}}
                            for i,scene in enumerate(artifact['scenes'])}
                elif task.get('craft'):
                    extras['craft_context'] = context(kernel)
                mapping = handoff_review(task, artifact)
                path = save(author/(kind+'.json'), artifact)
                result = result_for(task, artifact=str(path), artifact_sha256=digest_file(path), handoff=mapping, **extras)
            value = core_result(result, task.get('craft'))
            if kind == 'compile-review':
                value['delivery_audit'] = {'build_id':task['build']['build_id'],'passed':True,
                    'checks':['SYNTHETIC fixture final check '+x for x in task.get('hard_clauses', [])] or ['SYNTHETIC fixture final review']}
            packet = minimal.packet(task)
            stages.append({'kind':kind,'context_bytes':size(packet),'result_bytes':size(value),
                           'craft_rule_count':len((task.get('craft') or {}).get('rules',[])) +
                                              len((task.get('craft') or {}).get('inherited',[]))})
            if kind == 'compile-review': minimal.submit_final(kernel, value)
            else: kernel.submit(value)
        else:
            raise ValueError('Fixture did not converge')
        final = kernel.validate(True)
        if not final['valid'] or final['video_generated']:
            raise ValueError('Native gate failed or fixture made a false media claim')
        return {'profile':profile,'status':'DELIVERED','seconds':round(time.perf_counter()-started,3),
                'host_turns':len(stages),'context_bytes':sum(r['context_bytes'] for r in stages),
                'result_bytes':sum(r['result_bytes'] for r in stages),'stages':stages}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    rows = [run('lean'), run('studio')]
    report = {'scope':'Same authored legacy 1.0 text-only narrative; core transport; craft on/off; real native validators; synthetic semantic findings. Adaptive control and media excluded.',
              'baseline':'Explicit legacy lean, automatic craft routing, minimal core',
              'measurement':'Serialized UTF-8 bytes; native input file reads excluded; not model tokens',
              'real_generation':'NOT_RUN','production_speedup':'NOT_MEASURED','rows':rows,
              'reduction_percent':{k:round(100*(1-rows[1][k]/rows[0][k]),2)
                                   for k in ('context_bytes','result_bytes')}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
