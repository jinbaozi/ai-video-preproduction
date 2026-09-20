#!/usr/bin/env python3
"""Verify release trios, isolated native tests, bundled identity and repeat builds."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NAMES=('ai-comic-drama-workflow','director-grammar','production-design-grammar','storyboard-grammar','video-prompt-compiler','image-prompt-optimizer')
PATTERNS=('test_v5_workflow.py','test_dg.py','test_art_compile.py','test_storyboard.py','test_vpc.py','test_validate_gpt_image_2_size.py')


def verify(packages,out,quick_validator=None):
    packages,out=Path(packages).resolve(),Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('suite_verify_archiver',ROOT/'scripts/skill_archive.py')
    pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
    records=[]
    with tempfile.TemporaryDirectory(prefix='v5-isolated-') as temporary:
        base=Path(temporary)
        for name,pattern in zip(NAMES,PATTERNS):
            pkg.NAME=name;receipt=pkg.verify(packages)
            parent=base/name;parent.mkdir()
            with zipfile.ZipFile(packages/(name+'.skill')) as z:z.extractall(parent)
            skill=parent/name;env=os.environ.copy();env.pop('PYTHONPATH',None);env['PYTHONDONTWRITEBYTECODE']='1'
            if name=='ai-comic-drama-workflow':env['PYTHONPATH']=str(skill/'src')
            commands=[[sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-v'],
                      [sys.executable,'scripts/package_skill.py','--out',str(base/'rebuilt'/name)]]
            if name=='director-grammar':commands.insert(1,[sys.executable,'scripts/dg.py','compile','examples/v51/director.json','--target','generic-t2v','--out',str(base/'native-director')])
            if name=='storyboard-grammar':commands.insert(1,[sys.executable,'scripts/storyboard.py','compile','examples/v51/storyboard.json','--out',str(base/'native-storyboard')])
            if name=='video-prompt-compiler':commands.insert(1,[sys.executable,'-m','unittest','discover','-s','tests','-p','test_v51.py','-v'])
            if name=='ai-comic-drama-workflow':commands.insert(1,[sys.executable,'scripts/run_v5_example.py','--version','v51','--out',str(base/'example-v51')])
            if name=='director-grammar':commands.insert(1,[sys.executable,'scripts/dg.py','compile','examples/v52/director.json','--target','generic-t2v','--out',str(base/'native-director-v52')])
            if name=='storyboard-grammar':commands.insert(1,[sys.executable,'scripts/storyboard.py','compile','examples/v52/storyboard.json','--out',str(base/'native-storyboard-v52')])
            if name=='video-prompt-compiler':commands.insert(1,[sys.executable,'-m','unittest','discover','-s','tests','-p','test_v52.py','-v'])
            if name=='ai-comic-drama-workflow':
                commands.insert(1,[sys.executable,'-m','unittest','discover','-s','tests','-p','test_v52_workflow.py','-v'])
                commands.insert(1,[sys.executable,'scripts/run_v5_example.py','--version','v52','--out',str(base/'example-v52')])
            if quick_validator:commands.insert(0,[sys.executable,str(Path(quick_validator).resolve()),str(skill)])
            if name=='ai-comic-drama-workflow':
                commands.insert(1,[sys.executable,'scripts/run_v5_example.py','--out',str(base/'example')])
                lock=json.loads((skill/'modules.lock.json').read_text())
                for module,item in lock['modules'].items():
                    data=(skill/'assets/bundled-skills'/(module+'.skill')).read_bytes()
                    if data!=(packages/(module+'.skill')).read_bytes() or hashlib.sha256(data).hexdigest()!=item['sha256']:
                        raise ValueError('Bundled and standalone module differ: '+module)
            results=[]
            for index,command in enumerate(commands):
                p=subprocess.run(command,cwd=skill,env=env,capture_output=True,text=True)
                log=f'{name}-{index:02d}.log';(out/log).write_text(p.stdout+p.stderr)
                results.append({'command':command,'exit_code':p.returncode,'log':log})
                if p.returncode:raise ValueError('Isolated check failed: '+str(out/log))
            rebuilt=base/'rebuilt'/name/(name+'.skill')
            if rebuilt.read_bytes()!=(packages/(name+'.skill')).read_bytes():raise ValueError('Repeat build differs: '+name)
            records.append({'name':name,'archive_sha256':receipt['sha256'],'file_count':receipt['files'],
                            'single_install':'PASS','repeat_build':'IDENTICAL','checks':results})
    result={'schema':'suite-verification/1.0','status':'PASS','packages':records,
            'bundled_modules_equal_standalone':True,'real_media_acceptance':'SEPARATE_RECORD_REQUIRED',
            'video_execution':'NOT_RUN','legacy_tests':'Frozen legacy runtime is outside these V5 acceptance tests; compare its separately recorded baseline.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--packages',required=True);p.add_argument('--out',required=True);p.add_argument('--quick-validator')
    a=p.parse_args();result=verify(a.packages,a.out,a.quick_validator)
    print(json.dumps({'status':result['status'],'packages':len(result['packages']),'report':str(Path(a.out).resolve()/'report.json')},ensure_ascii=False))
