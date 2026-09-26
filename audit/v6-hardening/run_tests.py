#!/usr/bin/env python3
"""Focused V6 regressions, not real-agent/video or whole-repository certification."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

p=argparse.ArgumentParser()
p.add_argument('--repository',type=Path,default=Path(__file__).resolve().parents[2])
p.add_argument('--out',type=Path)
a=p.parse_args()
repo=a.repository.resolve()
paths=[repo/'ai-comic-drama-workflow/src',repo/'video-prompt-compiler/scripts']
if any(not path.is_dir() for path in paths):
    p.error('A complete checkout with both runtime and compiler is required')
sys.path[:0]=list(map(str,paths))
os.environ['PYTHONPATH']=os.pathsep.join(map(str,paths))
os.environ['AUDIT_ROOT']=str(Path(__file__).resolve().parent)
os.environ['AUDIT_REPOSITORY']=str(repo)
os.environ['AUDIT_VARIANT']='optimized'
start=time.monotonic()
suite=unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent/'tests'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
out=a.out or Path(tempfile.mkdtemp(prefix='v6-hardening-tests-'))
out.mkdir(parents=True,exist_ok=True)
report={'scope':'FOCUSED_REGRESSIONS_WITH_ISOLATED_KERNEL_GUARDS',
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skipped':len(result.skipped),'duration_seconds':round(time.monotonic()-start,3),
        'full_repository_suite':'NOT_RUN_BY_THIS_RUNNER','real_agents':'NOT_RUN',
        'real_video':'NOT_RUN','distribution_archives':'NOT_CHECKED_BY_THIS_RUNNER'}
(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('Focused test report:',out/'results.json')
raise SystemExit(0 if result.wasSuccessful() else 1)
