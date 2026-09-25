#!/usr/bin/env python3
"""Distribute the single maintained temporal implementation into standalone Skills."""
from pathlib import Path
import hashlib,importlib.util,json,shutil
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'video-prompt-compiler/scripts/shared_v51'

def sync(workspace=ROOT,check=False):
 workspace=Path(workspace);src=workspace/'video-prompt-compiler/scripts/shared_v51'
 spec=importlib.util.spec_from_file_location('v51_schema_source',src/'schema_source.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 targets={'director-grammar':'director-ir','storyboard-grammar':'storyboard-ir','video-prompt-compiler':'avir'}
 records={}
 for name,kind in targets.items():
  root=workspace/name
  for file in ('detail_runtime.py','v51_support.py','observe_video.py','upgrade_detail.py'):
   p=src/file
   if not p.exists():continue
   dest=root/'scripts'/file;data=p.read_bytes()
   if check:
    if not dest.exists() or dest.read_bytes()!=data:raise ValueError('Shared source drift: '+str(dest))
   else:dest.write_bytes(data)
   records[str(dest.relative_to(workspace))]=hashlib.sha256(data).hexdigest()
  d=mod.schema(kind,json.loads((root/'schemas'/(kind+'.schema.json')).read_text()))
  dest=root/'schemas'/(kind+'-1.1.schema.json');data=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
  if check:
   if dest.read_bytes()!=data:raise ValueError('Schema drift: '+str(dest))
  else:dest.write_bytes(data)
 # Workflow conversion uses its own shipped copy, never a sibling runtime import.
 for name in ('detail_runtime.py','observe_video.py'):
  p=src/name
  if not p.exists():continue
  dest=workspace/'ai-comic-drama-workflow/src/ai_comic_drama_workflow'/('v51_'+name)
  if check:
   if dest.read_bytes()!=p.read_bytes():raise ValueError('Workflow source drift')
  else:dest.write_bytes(p.read_bytes())
 for name in ('ai-comic-drama-workflow',*targets,'production-design-grammar','image-prompt-optimizer'):
  dest=workspace/name/'references/history/detail-contract-v51.md';data=(src/'detail-contract-v51.md').read_bytes()
  if check:
   if not dest.exists() or dest.read_bytes()!=data:raise ValueError('Detail contract drift: '+name)
  else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
  records[str(dest.relative_to(workspace))]=hashlib.sha256(data).hexdigest()
 return records
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();print(json.dumps(sync(check=a.check),indent=2))
