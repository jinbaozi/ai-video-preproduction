#!/usr/bin/env python3
"""Compare the same synthetic authored pipeline in two immutable checkouts.

Counts serialized UTF-8 bytes, not model tokens. Native content and real provider
latency are excluded. Validation is real; instrumentation does not bypass gates.
"""
from pathlib import Path
import argparse
import json
import os
import statistics
import subprocess
import sys
import time


def size(value):
    return len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())


def worker(skill,mode):
    sys.path[:0]=[str(skill/'src'),str(skill)]
    import unittest
    from unittest.mock import patch
    from ai_comic_drama_workflow.v5 import V5Kernel
    import ai_comic_drama_workflow.v5 as runtime
    from ai_comic_drama_workflow import workspace
    from ai_comic_drama_workflow.v5_modules import read, digest_file
    from tests import test_craft_end_to_end as e2e
    if mode=='core':
        from ai_comic_drama_workflow import minimal
        from tests.test_minimal_core import core_result
    initialize=V5Kernel.initialize;submit=V5Kernel.submit;native=runtime.native_validate
    rows=[];read_seen=set()
    def init(*args,**kwargs):
        kwargs.update(workflow_profile='lean',output_policy=workspace.POLICY)
        if mode=='core':kwargs['context_policy']=minimal.POLICY
        return initialize(*args,**kwargs)
    def authored(kernel,result):
        if mode=='core' and result.get('schema')==minimal.RESULT:return submit(kernel,result)
        task=read(kernel.path('runtime/tasks/'+result['task_id']+'.json'))
        reads=(task.get('module') or {}).get('required_reads',[])
        raw_read_bytes=sum(len(Path(r['path']).read_bytes()) for r in reads)
        new_read_bytes=sum(len(Path(r['path']).read_bytes()) for r in reads if r['sha256'] not in read_seen)
        read_seen.update(r['sha256'] for r in reads)
        if mode=='core':
            value=core_result(result,task.get('craft'));context=minimal.packet(task)
            if task['kind']=='compile-review':
                value['delivery_audit']={'build_id':task['build']['build_id'],'passed':True,
                    'checks':['SYNTHETIC final fixture finding '+item for item in task['hard_clauses']] or ['SYNTHETIC no hard clauses']}
            context_bytes=size(context)
        else:
            value=result;context_bytes=size(task)+raw_read_bytes
        rows.append({'kind':task['kind'],'host_context_bytes':context_bytes,
                     'task_json_bytes':size(task),'required_read_bytes':raw_read_bytes,
                     'new_read_bytes':new_read_bytes,'host_result_bytes':size(value)})
        if mode=='core' and task['kind']=='compile-review':return minimal.submit_final(kernel,value)[0]
        return submit(kernel,value)
    started=time.perf_counter()
    with patch.object(V5Kernel,'initialize',side_effect=init),patch.object(V5Kernel,'submit',authored),patch.object(runtime,'native_validate',wraps=native) as validator:
        case=e2e.CraftEndToEndTests('test_native_text_delivery_retains_craft_proofs_without_media_claim')
        result=unittest.TestResult();case.run(result)
        if result.errors or result.failures:raise ValueError(str(result.errors+result.failures))
        calls=validator.call_count
    import zipfile
    entry_bytes=len((skill/'SKILL.md').read_bytes())
    for name in runtime.read(skill/'modules.lock.json')['modules']:
        with zipfile.ZipFile(skill/'assets/bundled-skills'/(name+'.skill')) as archive:
            entry_bytes+=len(archive.read(name+'/SKILL.md'))
    return {'mode':mode,'status':'DELIVERED','seconds':round(time.perf_counter()-started,4),
            'seven_entry_bytes':entry_bytes,'host_turns':len(rows),'native_validator_calls':calls,
            'host_context_bytes':sum(r['host_context_bytes'] for r in rows),
            'host_result_bytes':sum(r['host_result_bytes'] for r in rows),
            'baseline_ideal_reused_reads_bytes':sum(r['task_json_bytes']+r['new_read_bytes'] for r in rows) if mode=='baseline' else None,
            'stages':rows,'real_generation':'NOT_RUN','token_count':'NOT_MEASURED'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,help='Baseline ai-comic-drama-workflow directory')
    p.add_argument('--current',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--out',type=Path);p.add_argument('--repeat',type=int,default=3)
    p.add_argument('--worker',choices=['baseline','core'])
    a=p.parse_args()
    if a.worker:
        print(json.dumps(worker(a.current.resolve(),a.worker),ensure_ascii=False));return
    if not a.baseline or not a.out or not 1<=a.repeat<=10:raise ValueError('Require baseline, out and repeat 1..10')
    a.out.mkdir(parents=True,exist_ok=False);rows=[]
    for iteration in range(a.repeat):
        # Alternating order limits cold/warm order bias; all workers are fresh processes.
        order=[('baseline',a.baseline),('core',a.current)]
        if iteration%2:order.reverse()
        for mode,root in order:
            env=os.environ.copy();env.pop('PYTHONPATH',None);env['PYTHONDONTWRITEBYTECODE']='1'
            command=[sys.executable,str(Path(__file__).resolve()),'--worker',mode,'--current',str(root.resolve())]
            process=subprocess.run(command,capture_output=True,text=True,env=env,timeout=180)
            (a.out/f'{iteration}-{mode}.log').write_text(process.stdout+process.stderr)
            if process.returncode:raise ValueError('Benchmark failed: '+process.stderr)
            row=json.loads(process.stdout);row['iteration']=iteration;rows.append(row)
    keys=['seconds','seven_entry_bytes','host_turns','native_validator_calls','host_context_bytes','host_result_bytes']
    summary={mode:{key:statistics.median(r[key] for r in rows if r['mode']==mode) for key in keys} for mode in ('baseline','core')}
    summary['reduction_percent']={key:round(100*(1-summary['core'][key]/summary['baseline'][key]),2) for key in keys}
    report={'scope':'Same pre-authored text-only cafe fixture, real native gates, no generation',
            'units':'UTF-8 bytes in compact JSON + raw required read text; NOT tokens',
            'exclusions':'Native source/IR reads and original input text are still required in both variants; excluded from context totals. No provider/LLM time included.',
            'baseline_sha':'dc954fe1579a40c50bf0e86d7059c487c8f57b61','summary':summary,'runs':rows}
    (a.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
