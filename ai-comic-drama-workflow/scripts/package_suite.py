#!/usr/bin/env python3
"""Build the six active Skills and vendor exactly the same five module archives."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
MODULES=('director-grammar','production-design-grammar','storyboard-grammar','video-prompt-compiler','image-prompt-optimizer')


def package_suite(workspace,out):
    workspace,out=Path(workspace).resolve(),Path(out).resolve()
    spec=importlib.util.spec_from_file_location('suite_archiver',ROOT/'scripts/skill_archive.py')
    pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
    lock={'schema':'skill-modules/1.0','adapter_version':'1.2.0','modules':{}}
    from sync_v51 import sync
    sync(workspace, check=True)
    from sync_v52 import sync as sync_spatial
    sync_spatial(workspace, check=True)
    bundles=ROOT/'assets/bundled-skills';bundles.mkdir(parents=True,exist_ok=True)
    records=[]
    for name in MODULES:
        pkg.ROOT=workspace/name;pkg.NAME=name
        result=pkg.build(out);records.append(result)
        for suffix in ('.skill','.skill-manifest.json','.skill.sha256'):
            shutil.copyfile(out/(name+suffix),bundles/(name+suffix))
        lock['modules'][name]={'version':json.loads((out/(name+'.skill-manifest.json')).read_text())['version'],'sha256':result['sha256'],'archive':name+'.skill'}
    (ROOT/'modules.lock.json').write_bytes(pkg.encoded(lock))
    pkg.ROOT=ROOT;pkg.NAME=ROOT.name
    records.append(pkg.build(out))
    index={'schema':'skill-suite/1.0','active_skills':[ROOT.name,*MODULES],
           'legacy_skills':['video-storyboard-prompter-zh'],'packages':records,'modules':lock}
    (out/'suite-manifest.json').write_bytes(pkg.encoded(index))
    return index


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',default=str(ROOT.parent));p.add_argument('--out',default=str(ROOT.parent/'dists'))
    a=p.parse_args();r=package_suite(a.workspace,a.out)
    print(json.dumps({'status':'BUILT','packages':len(r['packages']),'out':str(Path(a.out).resolve())},ensure_ascii=False))
