"""Native 1.1 entry points. Old validators and compilers remain untouched."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

_spec=importlib.util.spec_from_file_location('detail_runtime_'+str(Path(__file__).parent),Path(__file__).with_name('detail_runtime.py'))
detail=_spec.loader.load_module()


def validate_native(ir,root,kind,base=None):return detail.validate(ir,root,kind,base)


def compile_video(core,ir,cap,mode,base):
 errors=detail.validate(ir,core.ROOT,'avir',base)
 if any(e['severity']=='error' for e in errors):return None,errors
 bindings,be=core.resolve_assets(ir,cap,mode,base);errors+=be+core.target_errors(ir,cap,mode)
 if not detail.semantic_status(ir):errors.append(core.issue('E_SEMANTIC_REVIEW','/timeline/semantic_review','当前时间轨尚无绑定内容指纹的语义复核；完整草案保留。'))
 for a in ir['timeline']['audio_events']:
  if a['route']=='native' and cap['native_audio'] is not True:errors.append(core.issue('E_AUDIO_UNVERIFIED','/timeline/audio_events/'+a['id'],'入口原生音频未核验；保留原要求，不自动改为后期。'))
 blocks,coverage=detail.render(ir)
 errors+=detail.verify_coverage(ir,blocks,coverage)
 preamble=[f"制作规格：{ir['output']['duration_ms']/1000:g}秒，{ir['output']['aspect_ratio']}。时间均从当前片段0秒开始。"]
 for b in ir['bindings']:
  asset=next(x for x in bindings if x['id']==b['asset_id'])
  preamble.append(f"参考图片 {asset['filename']}：用于 {b['target_id']} 的 {'、'.join(b['roles'])}；禁止继承 {'、'.join(b['negative_roles']) or '未指定额外维度'}。")
 # Static information is scoped to the shot, not dumped from the entire project.
 chunks=[]
 for shot in ir['shots']:
  start,end=detail.bounds(ir)[shot['id']];scene=next(s for s in ir['scenes'] if s['id']==shot['scene_id'])
  ids={eid for s in ir['timeline']['state_samples'] if s['shot_id']==shot['id'] for eid in s['entities']}
  rows=[f"【镜头 {shot['id']}｜{start/1000:g}–{end/1000:g}秒】",'场景：'+scene['description'],'光线：'+detail.readable(scene['lighting'])]
  for e in ir['entities']:
   if e['id'] in ids:rows.append(e['label']+'：'+e['appearance']+'；保持：'+'、'.join(e['locks']))
  rows.append('构图：'+detail.readable(shot['composition']))
  rows.append('空间关系：'+detail.readable(shot['relations']))
  rows.append('切换方式：'+detail.readable(shot['transition'])+'；'+str(shot['transition_reason'] or '保持时空连续'))
  rows.append('镜头透视：'+shot['camera']['lens_intent'])
  rows.append('画面风格：'+'；'.join(shot['style']))
  text='\n'.join(rows);chunks.append(text)
  index=len(blocks);blocks.append({'text':text,'channel':'static','id':shot['id'],'path':'/shots/'+str(ir['shots'].index(shot))})
  paths=[f"/shots/{ir['shots'].index(shot)}/{field}" for field in ('start_ms','end_ms','composition','relations','transition','transition_reason','style')]
  paths += [f"/shots/{ir['shots'].index(shot)}/camera/lens_intent"]
  paths += [f"/scenes/{ir['scenes'].index(scene)}/{field}" for field in ('description','lighting')]
  for e in ir['entities']:
   if e['id'] in ids:paths += [f"/entities/{ir['entities'].index(e)}/{field}" for field in ('label','appearance','locks')]
  for path in paths:
   for field,value in detail.leaves(detail.pointer(ir,path),path):coverage.append({'source_path':field,'source_sha256':detail.digest(value),'object_id':shot['id'],'disposition':'emitted','channel':'prompt','block':index,'text_sha256':detail.digest(text),'reason':'镜头静态制作字段逐项展开'})
 post=[{'id':b['id'],'instruction':b['text'],'status':'PLANNED','channel':b['channel']} for b in blocks if b['channel'] not in ('prompt','static')]
 # Post-produced on-screen dialogue still needs visible speech in the video prompt.
 for a in ir['timeline']['audio_events']:
  if a['route']=='post' and a['placement']=='on_screen' and a['lip_sync']:
   blocks.append({'id':a['id']+'_visual','path':'/timeline/audio_events','channel':'prompt','text':f"【后期对白的画内口型｜{a['start_ms']/1000:g}–{a['end_ms']/1000:g}秒】\n{a['speaker_id']}按原文“{a['text']}”表演口型与停顿；声音由后期制作。"})
 for a in ir['timeline']['audio_events']:
  if a['route']=='post':preamble.append(f"声音安排：{a['start_ms']/1000:g}–{a['end_ms']/1000:g}秒的{detail.readable(a['kind'])}由后期按独立声音说明执行。" )
 prompt='\n\n'.join(preamble+chunks+[b['text'] for b in blocks if b['channel']=='prompt'])
 clauses=[]
 for c in ir['contract']:
  if c['channel']=='post':post.append({'id':c['id'],'instruction':c['requirement'],'status':'PLANNED','channel':'post'})
  else:clauses.append(c['requirement'])
 if clauses:prompt+='\n\n【保持与禁止变化】\n'+'\n'.join(clauses)
 # Evidence and metadata are retained distinctly from emitted production detail.
 known={r['source_path'] for r in coverage}
 for path,value in detail.leaves(ir):
  if path not in known:coverage.append({'source_path':path,'source_sha256':detail.digest(value),'object_id':None,'disposition':'retained','channel':'review','block':None,'text_sha256':None,'reason':'来源、参数意图、合同及兼容视图保留于完整制作说明；不冒充正文覆盖'})
 errors+=detail.verify_coverage(ir,blocks,coverage)
 count=core.canonical_count(prompt);budget=ir['policy']['max_canonical_units']
 if (budget is not None and count>budget) or (cap['max_prompt_chars'] is not None and len(prompt)>cap['max_prompt_chars']):errors.append(core.issue('E_BUDGET','/prompt','完整提示词超限；不得删除动作，需审查拆段提案。'))
 proposals=[deepcopy(s) for s in ir['timeline']['segments'] if s['status']=='proposed']
 if any(e['code']=='E_BUDGET' for e in errors) and not proposals:
  for sid,(start,end) in detail.bounds(ir).items():proposals.append({'shot_id':sid,'start_ms':start,'end_ms':end,'status':'NEEDS_AGENT_REVIEW','reason':'在此镜头或其已定义动作边界评估拆段；连续动作、对白、摄影机、参考与费用需共同审查，不自动执行。'})
 artifact={'schema':'compiled-artifact/1.1','target':cap['id'],'mode':mode,'status':'BLOCKED' if any(e['severity'] in ('error','blocker') for e in errors) else 'COMPILED',
  'prompt':prompt,'parameters':deepcopy(ir['output']),'parameter_semantics':'intent_only','payload_draft':None,'asset_bindings':bindings,
  'diagnostics':errors,'losses':[{'code':e['code'],'path':e['path'],'disposition':'blocked','detail':e['message'],'semantic_content_discarded':False} for e in errors if e['severity'] in ('error','blocker')],
  'trace':[{'block':i,'text':b['text'],'ir_paths':[b['path']],'source_refs':[],'source_namespace':'avir','rule':'DETAIL.LOWER.1.1'} for i,b in enumerate(blocks)],
  'coverage':[{'id':c['id'],'level':c['level'],'source_refs':c['source_refs'],'ir_paths':[x['path'] for x in c['checks']],'channel':c['channel'],'execution':c['execution'],'acceptance':c['acceptance'],'static_assertions':'PASS','realization':'NOT_RUN','status':'PLANNED' if c['channel']=='post' else 'EMITTED'} for c in ir['contract']],
  'post_production':post,'counts':{'canonical_count':count,'canonical_algorithm':'CPT-v1','native_count':None,'native_tokenizer':None,'chars':len(prompt)},
  'execution':{'submitted':False,'runnable':False,'media_qa':'NOT_RUN','next_steps':['静态编译不证明生成质量；外部执行另存真实证据。']},
  'detail_blocks':blocks,'detail_coverage':coverage,'segment_proposals':proposals,'semantic_review':deepcopy(ir['timeline']['semantic_review'])}
 failures=core.schema_errors(artifact,'compile-artifact-1.1')
 if failures:raise ValueError(str(failures))
 return artifact,{'schema':'context-ir/1.1','authoritative_ir_hash':detail.digest(ir),'shots':[{'shot_id':s['id']} for s in ir['shots']],'temporal_hash':detail.temporal_hash(ir),'projection':'complete temporal tracks; no summarization'}


def storyboard_package(module,ir,base,out):
 errors=detail.validate(ir,module.ROOT,'storyboard-ir',base)
 out=Path(out)
 if out.exists() and any(out.iterdir()):raise ValueError('输出目录非空')
 out.mkdir(parents=True,exist_ok=True)
 qa={'schema_version':'storyboard-qa/1.0','status':'INVALID' if any(e['severity']=='error' for e in errors) else 'BLOCKED' if any(e['severity']=='blocker' for e in errors) else 'VALID','structure':'FAIL' if any(e['severity']=='error' for e in errors) else 'PASS','media':'NOT_RUN','visual':'NOT_RUN','execution_ready':False,'submitted':False,'diagnostics':errors,'contract_results':[],'manual_checks':module.MANUAL}
 def emit(name,x):(out/name).write_bytes(detail.encoded(x))
 emit('qa.report.json',qa)
 if qa['status']=='INVALID':return qa
 emit('storyboard.ir.json',ir)
 blocks,coverage=detail.render(ir)
 (out/'storyboard.md').write_text('\n\n'.join(b['text'] for b in blocks)+'\n')
 emit('detail-coverage.json',coverage)
 emit('production-contract.json',{'schema_version':'storyboard-contract/1.0','project_id':ir['project_id'],'input_hash':detail.digest(ir),'requirements':ir['contract']})
 emit('panel-briefs.json',{'status':'PLANNED','generated':False,'panels':[dict(**p,shot_id=s['id'],state_evaluation=detail.panel_state(ir,s['id'],detail.ms(p['frame'],ir['delivery']['fps']))) for s in ir['shots'] for p in s['panels']]})
 emit('compiler-handoff.json',{'schema_version':'storyboard-handoff/1.1','project_id':ir['project_id'],'ir_file':'storyboard.ir.json','input_hash':detail.digest(ir),'target':'avir/1.1','source_ids':[x['id'] for x in ir['sources']],'temporal_hash':detail.temporal_hash(ir),'submitted':False})
 emit('loss.report.json',{'status':'EXPLICIT_MAPPING_REQUIRED','ir_fields_retained':True,'media':'NOT_RUN'})
 manifest={'compiler':'storyboard-grammar@'+__import__('re').search(r'^  version:\s*[\"\']?([^\"\'\n]+)',(module.ROOT/'SKILL.md').read_text(),__import__('re').M).group(1).strip(),'input_hash':detail.digest(ir),'runtime_files':{str(p.relative_to(module.ROOT)):detail.sha256(p.read_bytes()).hexdigest() for folder in ('scripts','schemas') for p in (module.ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts},'files':{p.name:detail.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}}
 manifest['build_id']=detail.digest(manifest);emit('compile-manifest.json',manifest)
 return qa
