#!/usr/bin/env python3
"""Distribute the single V5.2 source, alongside the unchanged V5.1 source."""
from pathlib import Path
import hashlib,importlib.util,json
ROOT=Path(__file__).resolve().parents[2]
def sync(workspace=ROOT,check=False):
 workspace=Path(workspace);src=workspace/'video-prompt-compiler/scripts/shared_v52';records={}
 spec=importlib.util.spec_from_file_location('spatial_schema',src/'spatial_schema.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 def put(dest,data):
  if check:
   if not dest.is_file() or dest.read_bytes()!=data:raise ValueError('V5.2 shared source drift: '+str(dest))
  else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
  records[str(dest.relative_to(workspace))]=hashlib.sha256(data).hexdigest()
 for name,kind in {'director-grammar':'director-ir','storyboard-grammar':'storyboard-ir','video-prompt-compiler':'avir'}.items():
  root=workspace/name
  for file in ('spatial_runtime.py','v52_support.py','upgrade_spatial.py'):
   if (src/file).exists():put(root/'scripts'/file,(src/file).read_bytes())
  schema=mod.schema(kind,json.loads((root/'schemas'/(kind+'-1.1.schema.json')).read_text()))
  put(root/'schemas'/(kind+'-1.2.schema.json'),(json.dumps(schema,ensure_ascii=False,indent=2)+'\n').encode())
 artifact=json.loads((workspace/'video-prompt-compiler/schemas/compile-artifact-1.1.schema.json').read_text());artifact['properties']['schema']={'const':'compiled-artifact/1.2'};artifact['properties']['spatial_checks']={'type':'array','items':{'type':'object'}};artifact['required'].append('spatial_checks')
 put(workspace/'video-prompt-compiler/schemas/compile-artifact-1.2.schema.json',(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n').encode())
 for file in ('spatial_runtime.py',):
  if (src/file).exists():put(workspace/'ai-comic-drama-workflow/src/ai_comic_drama_workflow'/('v52_'+file),(src/file).read_bytes())
 for name in ('ai-comic-drama-workflow','director-grammar','production-design-grammar','storyboard-grammar','video-prompt-compiler','image-prompt-optimizer'):
  if (src/'spatial-contract-v52.md').exists():put(workspace/name/'references/spatial-contract-v52.md',(src/'spatial-contract-v52.md').read_bytes())
 return records
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();print(json.dumps(sync(check=a.check),indent=2))
