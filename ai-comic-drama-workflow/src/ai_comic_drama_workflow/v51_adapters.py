"""Loss-aware native StoryboardIR 1.1 conversion; temporal fields are copied intact."""
from copy import deepcopy
from fractions import Fraction
from .v51_detail_runtime import digest,leaves,bounds,ms,panel_state,temporal_hash,content_hash,semantic_status,pointer

def _storyboard_schedule(ir, avir):
 """Retain source-only beats and panel instants in an AVIR prompt field."""
 for index,row in enumerate(avir['timeline']['extensions']):
  if row['name']=='storyboard-schedule' and row['version']==ir['schema_version'].split('/')[-1]:return index
 sources=[s['id'] for s in ir['sources']]
 if not sources:raise ValueError('Storyboard schedule has no source reference')
 index=len(avir['timeline']['extensions'])
 avir['timeline']['extensions'].append({'name':'storyboard-schedule','version':ir['schema_version'].split('/')[-1],
  'channel':'prompt','instruction':'按来源节拍依赖与逐镜画格帧点执行；帧号使用 payload.fps 换算，静态画格不是模型原生镜头控制。',
  'payload':{'fps':str(ir['delivery']['fps']),'beats':deepcopy(ir['beats']),
   'panels':[{'shot_id':s['id'],'items':deepcopy(s['panels'])} for s in ir['shots']]},
  'supported':True,'origin':{'kind':'design','source_refs':[sources[0]],'locator':'StoryboardIR /beats and /shots/*/panels'}})
 return index

def _lower_check(ir, avir, report, clause, check, overrides):
 from .v5_adapters import assert_check
 source=check['path'];hard=clause['strength']=='hard'
 def lost(reason):report['losses'].append({'path':source,'severity':'error' if hard else 'notice','reason':reason})
 if not assert_check(ir,check):lost('Source assertion fails before conversion.');return None
 override=(overrides or {}).get(source)
 if override:
  if override.get('owner')!=clause['owner'] or not override.get('reason'):
   lost('Explicit mapping must identify its source owner and reason.');return None
  mapped=deepcopy(override['check']);target=mapped['path']
 else:
  parts=source.split('/');target=report['field_mapping'].get(source);mode='normal'
  if len(parts)>=3 and parts[1]=='beats':
   target='/timeline/extensions/'+str(_storyboard_schedule(ir,avir))+'/payload/beats/'+'/'.join(parts[2:]);mode='direct'
  elif len(parts)>=5 and parts[1]=='shots' and parts[3]=='panels':
   target='/timeline/extensions/'+str(_storyboard_schedule(ir,avir))+'/payload/panels/'+parts[2]+'/items/'+'/'.join(parts[4:]);mode='direct'
  elif len(parts)==4 and parts[1]=='scenes' and parts[3]=='time_of_day':
   target='/scenes/'+parts[2]+'/description';mode='contains'
   value=pointer(ir,source)
   if value not in pointer(avir,target):avir['scenes'][int(parts[2])]['description']=value+'；'+pointer(avir,target)
  elif len(parts)>=5 and parts[1]=='entities' and parts[3]=='identity_locks':
   target='/entities/'+parts[2]+'/locks/'+'/'.join(parts[4:]);mode='direct'
  elif len(parts)==5 and parts[1]=='shots' and parts[3]=='camera' and parts[4]=='axis_side':
   target='/shots/'+parts[2]+'/camera/axis_side';mode='enum'
  elif len(parts)==5 and parts[1]=='shots' and parts[3]=='camera' and parts[4]=='end_m':
   target='/shots/'+parts[2]+'/camera/trajectory';mode='text'
  elif len(parts)==5 and parts[1]=='shots' and parts[3] in ('state_start','state_end'):
   states=avir['shots'][int(parts[2])]['start_state' if parts[3]=='state_start' else 'end_state']
   matches=[i for i,row in enumerate(states) if row['entity_id']==parts[4]]
   if len(matches)==1:
    target='/shots/'+parts[2]+'/'+('start_state' if parts[3]=='state_start' else 'end_state')+'/'+str(matches[0])
  elif len(parts)==6 and parts[1]=='shots' and parts[3] in ('state_start','state_end') and parts[5] in ('condition','pose'):
   states=avir['shots'][int(parts[2])]['start_state' if parts[3]=='state_start' else 'end_state']
   matches=[i for i,row in enumerate(states) if row['entity_id']==parts[4]]
   if len(matches)==1:target='/shots/'+parts[2]+'/'+('start_state' if parts[3]=='state_start' else 'end_state')+'/'+str(matches[0])+'/pose';mode='contains'
  elif source in ('/assets','/bindings','/audio/utterances'):
   target=source;mode='direct'
  if not target:
   lost('No verified AVIR assertion mapping; explicit owner-reviewed mapping required.');return None
  try:value=pointer(avir,target)
  except (KeyError,IndexError,TypeError,ValueError):
   lost('Mapped AVIR field does not exist.');return None
  if mode=='contains':mapped={'path':target,'op':'contains','value':check.get('value',pointer(ir,source))}
  elif mode=='text':mapped={'path':target,'op':'contains','value':str(check.get('value',pointer(ir,source)))}
  elif mode=='enum':mapped={'path':target,'op':'equals','value':value}
  elif mode=='direct':
   mapped=deepcopy(check);mapped['path']=target
  else:
   mapped={'path':target,'op':'exists' if check['op']=='exists' else 'equals','value':deepcopy(value)}
 if not assert_check(avir,mapped):lost('Mapped assertion does not hold.');return None
 report['field_mapping'][source]=target
 return mapped

def lower_contract(ir, avir, report, clause, overrides=None):
 checks=[]
 for check in clause['checks']:
  mapped=_lower_check(ir,avir,report,clause,check,overrides)
  if mapped is not None:checks.append(mapped)
 if len(checks)!=len(clause['checks']):return
 avir['contract'].append({'id':clause['id'],'level':clause['strength'],'requirement':clause['statement'],
  'source_refs':clause['source_refs'],'shot_ids':clause['shot_ids'],'checks':checks,
  'channel':clause['channel'],'execution':clause['execution'],
  'acceptance':{'method':'media','criterion':'；'.join(x['criterion'] for x in clause['acceptance'])},
  'on_unsupported':{'block':'block','post':'post'}.get(clause['fallback'],'warn')})

def storyboard_to_avir(ir,base,overrides,legacy):
 proxy=deepcopy(ir);timeline=proxy.pop('timeline');proxy['schema_version']='storyboard-ir/1.0'
 proxy['delivery']['fps']=float(Fraction(str(proxy['delivery']['fps'])))
 contracts=proxy['contract'];proxy['contract']=[]
 voices={e['id'] for e in proxy['entities'] if e['kind']=='voice'}
 for e in proxy['entities']:
  if e['id'] in voices:e['kind']='environment'
 result,report=legacy(proxy,base,overrides)
 for e in result['entities']:
  if e['id'] in voices:e['kind']='voice'
 for source in result['sources']:
  original=next(x for x in ir['sources'] if x['id']==source['id']);source['utterances']=deepcopy(original.get('utterances',[]))
 result['schema']='avir/1.1';result['timeline']=deepcopy(timeline)
 size={'extreme_wide':'wide','extreme_close':'detail','insert':'detail'}
 shot_bounds=bounds(ir)
 for shot_index,shot in enumerate(result['shots']):
  source_shot=ir['shots'][shot_index]
  start,end=shot_bounds[source_shot['id']]
  shot['start_ms'],shot['end_ms']=start,end
  shot['camera']['shot_size']=size.get(shot['camera']['shot_size'],shot['camera']['shot_size'])
 boundary_coverage=[]
 sample_index={(sample['shot_id'],sample['at_ms']):(i,sample['entities'])
  for i,sample in enumerate(timeline['state_samples'])}
 for shot_index,source_shot in enumerate(ir['shots']):
  start,end=shot_bounds[source_shot['id']]
  for edge,at in (('start',start),('end',end)):
   sample=sample_index.get((source_shot['id'],at))
   if sample is None:
    report['losses'].append({'path':f"/shots/{shot_index}/state_{edge}",'severity':'error',
     'reason':'No authoritative timeline state sample exists at this shot boundary.'})
    continue
   sample_number,entities=sample
   rows=result['shots'][shot_index][edge+'_state']
   for row_index,row in enumerate(rows):
    entity=entities.get(row['entity_id'])
    if not isinstance(entity,dict) or 'visible_parts' not in entity:
     report['losses'].append({'path':f"/shots/{shot_index}/state_{edge}/{row_index}/visible_parts",'severity':'error',
      'reason':'The authoritative boundary sample has no visible_parts value for this entity.'})
     continue
    value=deepcopy(entity['visible_parts'])
    row['visible_parts']=value
    entity_id=str(row['entity_id']).replace('~','~0').replace('/','~1')
    source_path=f"/timeline/state_samples/{sample_number}/entities/{entity_id}/visible_parts"
    target_path=f"/shots/{shot_index}/{edge}_state/{row_index}/visible_parts"
    boundary_coverage.append({'source_path':source_path,'source_sha256':digest(value),
     'target_path':target_path,'target_sha256':digest(value),'disposition':'derived',
     'rule':'STATE_SAMPLE.BOUNDARY_VISIBILITY.1.1'})
 result['output']['duration_ms']=ms(ir['delivery']['total_frames'],ir['delivery']['fps'])
 for frame in report['rounding']:
  exact=Fraction(frame)*1000/Fraction(str(ir['delivery']['fps']));rounded=ms(int(frame),ir['delivery']['fps'])
  report['rounding'][frame]={'milliseconds':rounded,'error_ms':float(Fraction(rounded)-exact),'exact_ms':str(exact),'rule':'fraction-boundary-half-up'}
 coverage=[]
 for p,v in leaves(timeline,'/timeline'):
  report['field_mapping'][p]=p
  coverage.append({'source_path':p,'source_sha256':digest(v),'target_path':p,'target_sha256':digest(v),'disposition':'direct','rule':'TEMPORAL.IDENTITY.1.1'})
 for c in contracts:lower_contract(ir,result,report,c,overrides)
 if semantic_status(ir) and not any(x['severity']=='error' for x in report['losses']):
  result['timeline']['semantic_review']['input_sha256']=content_hash(result)
 for row in coverage:
  row['target_sha256']=digest(pointer(result,row['target_path']))
  if row['source_sha256']!=row['target_sha256']:row.update(disposition='derived',rule='REVIEW.DETERMINISTIC.REBIND.1.1')
 coverage.extend(boundary_coverage)
 for row in boundary_coverage:row['target_sha256']=digest(pointer(result,row['target_path']))
 report.update(adapter='1.1.0',source_hash=digest(ir),target_hash=digest(result),detail_coverage=coverage,sidecar=deepcopy(ir),
  status='BLOCKED' if any(x['severity']=='error' for x in report['losses']) else 'MAPPED',
  semantic_review='INHERITED_DETERMINISTICALLY' if semantic_status(ir) else 'PENDING',
  sidecar_scope=['native beat and panel metadata; temporal execution fields mapped directly'])
 return result,report


def image_briefs(ir):
 result=[]
 for i,s in enumerate(ir['shots']):
  for j,p in enumerate(s['panels']):
   at=ms(p['frame'],ir['delivery']['fps']);state=panel_state(ir,s['id'],at)
   relevant={x['id'] for x in state['actions']}
   paths=[f'/shots/{i}/panels/{j}',f'/shots/{i}/composition']
   for col in ('state_samples','performances','camera_operations','actions','visibility'):
    for k,x in enumerate(ir['timeline'][col]):
     if (x.get('shot_id')==s['id'] and (col!='state_samples' or x['at_ms']==at)) or (s['id'] in x.get('shot_ids',[]) and x['start_ms']<=at<x['end_ms']):paths.append(f'/timeline/{col}/{k}')
   result.append({'id':p['id'],'shot_id':s['id'],'scene_id':s['scene_id'],'kind':'board','frame':p['frame'],'moment':p['moment'],'must_show':p['must_show'],
    'state_evaluation':state,'camera':state['camera'],'performance':state['performance'],'composition':s['composition'],
    'state_start':state['state'],'events':state['actions'],'bindings':[b for b in ir['bindings'] if s['id'] in b['shot_ids']],
    'source_pointer':f'/shots/{i}/panels/{j}','source_hash':digest(ir),'dependency_paths':paths+[f'/bindings/{k}' for k,b in enumerate(ir['bindings']) if s['id'] in b['shot_ids']],
    'allowed_change':'Only this explicit instant. Missing key pose must be designed and reviewed before image generation.'})
 return result
