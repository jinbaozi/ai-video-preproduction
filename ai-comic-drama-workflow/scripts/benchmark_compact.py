#!/usr/bin/env python3
"""Reproducible authored-fixture comparison; NOT actual LLM token or media QA."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from test_compact_workspace import fixture_run, stats


def run(destination):
    destination=Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Benchmark destination must be empty')
    destination.mkdir(parents=True,exist_ok=True)
    values={}
    for name,compact in [('audit',False),('compact',True)]:
        kernel,payloads=fixture_run(destination/name,compact)
        values[name]=stats(kernel,payloads)
        values[name]['tasks']=len(payloads)
        values[name]['status']=kernel.state['status']
        values[name]['final_native_validation']=kernel.validate(True)['valid']
    result={'schema':'compact-workspace-benchmark/1.0','fixture':'examples/v5/cafe',
            'runs':values,'reduction_percent':{key:round(100*(1-values['compact'][key]/values['audit'][key]),2)
                for key in ('content_files','content_bytes','task_bytes','handoff_bytes','files')},
            'method':'Same authored native fixture; reopen kernel after each accepted task. content excludes locked runtime modules and archives; files includes them but excludes __pycache__. UTF-8 bytes, not model tokens.',
            'not_run':['LLM generation/token metering','actual video generation','finished-film review']}
    (destination/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.out),ensure_ascii=False,indent=2))
    except (ValueError,OSError,AssertionError) as exc:parser.exit(2,str(exc)+'\n')
