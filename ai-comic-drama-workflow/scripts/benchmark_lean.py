#!/usr/bin/env python3
"""Reproducible local engineering benchmark; no LLM, images or video are generated.

Compare an unchanged checkout with this checkout. Each row uses a fresh Python
process and the same pre-authored three-shot input. Timings are observations,
not a promise about a host session or provider generation latency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def run_case(checkout, destination, name, lean=False, fixture=False):
    checkout, destination = Path(checkout).resolve(), Path(destination).resolve()
    if destination.exists():raise ValueError('Benchmark destination already exists')
    if fixture:
        command=[sys.executable,str(checkout/'ai-comic-drama-workflow/scripts/run_v5_example.py'),
                 '--version','v52','--out',str(destination)]
        if lean:command.append('--lean')
    else:
        compiler=checkout/'video-prompt-compiler'
        command=[sys.executable,str(compiler/'scripts/vpc.py'),'compile',str(compiler/'examples/v52/cafe.avir.json'),
                 '--target','agnes-video-2.5','--mode','text','--out',str(destination)]
        if lean:command.extend(['--output-profile','lean'])
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.perf_counter()
    process=subprocess.run(command,capture_output=True,text=True)
    seconds=time.perf_counter()-start
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
    (destination.parent/(name+'.log')).write_text(process.stdout+process.stderr)
    if process.returncode:raise ValueError(f'{name} failed: {process.stderr or process.stdout}')
    result=json.loads(process.stdout)
    project=destination/'project' if fixture else destination
    compiled=next((project/'builds').glob('*/compiled')) if fixture else destination
    files=[p for p in project.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    prompt=(compiled/'prompt.txt').read_bytes()
    manifest=json.loads((compiled/'compile-manifest.json').read_text())
    return {'name':name,'seconds':round(seconds,4),'child_cpu_seconds':round(cpu,4),'status':result['status'],
            'project_files':len(files),'project_bytes':sum(p.stat().st_size for p in files),
            'transaction_backups':len(list(project.rglob('*.backup'))),
            'compiled_files':len(list(compiled.iterdir())),
            'compiled_bytes':sum(p.stat().st_size for p in compiled.iterdir() if p.is_file()),
            'prompt_sha256':hashlib.sha256(prompt).hexdigest(),
            'artifact_hash':manifest['artifact_hash'],
            'segment_status':json.loads((compiled/'segment-delivery.json').read_text())['status']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',required=True,help='Unmodified checkout')
    parser.add_argument('--out',required=True,help='Empty benchmark directory')
    parser.add_argument('--compiler-only',action='store_true')
    args=parser.parse_args();out=Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Output must be empty')
    out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for label,checkout,lean in [('baseline',Path(args.baseline),False),('lean',ROOT,True)]:
        cases.append(run_case(checkout,out/(label+'-compiler'),label+'-compiler',lean=lean))
    if not args.compiler_only:
        for label,checkout,lean in [('baseline',Path(args.baseline),False),('lean',ROOT,True)]:
            cases.append(run_case(checkout,out/(label+'-workflow'),label+'-workflow',lean=lean,fixture=True))
    for first,second in zip(cases[::2],cases[1::2]):
        if first['prompt_sha256']!=second['prompt_sha256'] or first['segment_status']!=second['segment_status']:
            raise ValueError('Benchmark changed prompt or delivery status')
    report={'scope':'Pre-authored static three-shot fixture; one fresh process per case',
            'llm_creativity':'NOT_RUN','real_image_video':'NOT_RUN','rows':cases}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
