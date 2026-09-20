#!/usr/bin/env python3
"""Run pre-authored three-shot artifacts through V5. No LLM or image generation."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_modules import read,digest_file
from ai_comic_drama_workflow.v5_adapters import encoded


def run_example(out, version='v5'):
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Example output must be empty')
    out.mkdir(parents=True,exist_ok=True)
    author=out/'authored-fixture';shutil.copytree(ROOT/'examples'/version/'cafe',author)
    k=V5Kernel.initialize(out/'project',[str(author/'cafe.source.txt')],project_id='CAFE_DEMO',delivery='text-only',target='agnes-video-2.5')
    for _ in range(12):
        step=k.run()
        if step['status']=='DELIVERED':return step
        if 'task' not in step:raise ValueError(str(step))
        task=step['task'];kind=task['kind']
        if kind in ('canon','screenplay'):
            value={'project_id':'CAFE_DEMO','revision':1,'content':(author/'cafe.source.txt').read_text(),
                   'source_refs':[s['id'] for s in k.state['sources']]}
            if kind=='canon':value.update(entities=[{'id':e['id']} for e in read(author/'director.json')['entities']],locks=[])
        elif kind=='qa':
            value={'project_id':'CAFE_DEMO','passed':True,'build_id':k.state['build']['build_id'],
                   'checks':['Fixed fixture: source order, B dialogue, two identities, hand custody and explicit coordinate conversion checked.','Static example only; actual images and video NOT_RUN.']}
        else:value=read(author/(kind+'.json'))
        path=author/('result-'+kind+'.json');path.write_bytes(encoded(value));handoff=[]
        for req in task['handoff']['required_handoffs']:
            cid=req['id'].split(':')[-1]
            if req.get('preservation_only'):
                handoff.append({'requirement_id':req['id'],'source_fingerprint':req['source_fingerprint'],'target_checks':[{'path':req['source_paths'][0],'op':'equals','value':req['source_values'][0]}],'reason':'Same complete temporal detail retained; no summary or creative change.'})
                continue
            checks=([{'path':'/set/scene_id','op':'equals','value':'CAFE'}] if kind=='art' else
                    next(c for c in value['contract'] if c['id']==cid)['checks'])
            handoff.append({'requirement_id':req['id'],'source_fingerprint':req['source_fingerprint'],
                'target_clause':cid,'target_checks':checks,
                'reason':'Pre-authored cafe example: same named requirements reviewed against the fixed source; ArtIR preserves the linked scene; StoryboardIR explicitly maps [x,z,y] world positions and keeps dialogue, custody and event order.'})
        result={'schema':'role-result/5.0','task_id':task['task_id'],'context_fingerprint':task['context_fingerprint'],
            'artifact':str(path),'artifact_sha256':digest_file(path),'complete':True,'handoff':handoff,
            'checks':['Fixed native example and source checked; no external model or media execution.'],'conflicts':[],'unresolved':[]}
        k.submit(result)
    raise ValueError('Example did not converge')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);parser.add_argument('--version',choices=['v5','v51','v52'],default='v5');args=parser.parse_args()
    print(encoded(run_example(args.out,args.version)).decode())
